"""End-to-end check: real server, real MCP clients, real hook processes. Run: uv run --with httpx tests/test_meat_proxy.py"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

PORT = "8799"
BASE = f"http://127.0.0.1:{PORT}"
TMP = Path(tempfile.mkdtemp())
ENV = {**os.environ, "MEATPROXY_PORT": PORT, "MEATPROXY_HOME": str(TMP), "MEATPROXY_MAX_TURNS": "4",
       "MEATPROXY_HOOK_WAIT": "2"}


async def call(tool, **args):
    async with streamablehttp_client(BASE + "/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return (await s.call_tool(tool, args)).content[0].text


def transcript(me, room):
    p = TMP / f"{me}.jsonl"
    p.write_text(json.dumps({"type": "tool_use", "name": "mcp__meat-proxy__wait",
                             "input": {"me": me, "room": room}}) + "\n")
    return str(p)


def hook(kind, payload):
    out = subprocess.run([sys.executable, "-m", "meat_proxy.cli", "hook", kind], input=json.dumps(payload),
                         capture_output=True, text=True, env=ENV, timeout=30).stdout.strip()
    return json.loads(out) if out else None


async def main():
    # ping-pong: send blocks for the reply, DMs stay private, nobody sees their own messages
    async def bob():
        got = await call("wait", me="bob", room="/code/demo", timeout=10)
        assert "alice→bob: ping" in got, got
        return await call("send", me="bob", room="/code/demo", to="alice", text="pong", wait=False)
    a, _ = await asyncio.gather(call("send", me="alice", room="/code/demo", to="bob", text="ping", timeout=10), bob())
    assert "bob→alice: pong" in a and "ping" not in a.split("\n", 1)[1], a
    assert "ping" not in await call("wait", me="carol", room="demo", timeout=0)
    assert "No new messages" in await call("wait", me="bob", room="demo", timeout=0)

    # rooms are isolated; full paths and folder names map to the same room
    await call("send", me="alice", room="/code/other", text="elsewhere", wait=False)
    assert "elsewhere" not in await call("wait", me="bob", room="/code/demo", timeout=0)
    assert "Room 'demo'" in await call("history", me="bob", room="/code/demo")

    # turn cap: 4 agent messages, then refused until DONE or a human steps in
    for i in range(4):
        await call("send", me="alice", room="cap", text=f"t{i}", wait=False)
    assert (await call("send", me="alice", room="cap", text="t5", wait=False)).startswith("Refused")
    async with httpx.AsyncClient() as h:
        assert (await h.post(BASE + "/post", json={"room": "cap", "text": "keep going"})).status_code == 200
        assert (await h.post(BASE + "/post", content='{"text":"x"}',
                             headers={"content-type": "text/plain"})).status_code == 403
    assert (await call("send", me="alice", room="cap", text="t6", wait=False)).startswith("Posted")
    got = await call("wait", me="bob", room="cap", timeout=0)
    assert "(human): keep going" in got, got

    # claims: conflicts reported, hook denies other agents' edits, DONE releases
    assert "Claimed" in await call("claim", me="alice", room="demo", paths=["/code/demo/src"])
    assert "held by alice" in await call("claim", me="bob", room="demo", paths=["/code/demo/src/app.py"])
    as_bob = {"transcript_path": transcript("bob", "/code/demo"), "cwd": "/code/demo"}
    deny = hook("pre-tool", {**as_bob, "tool_name": "Edit", "tool_input": {"file_path": "src/app.py"}})
    assert deny["hookSpecificOutput"]["permissionDecision"] == "deny", deny
    patch = {"command": ["apply_patch", "*** Begin Patch\n*** Update File: src/x.py\n@@\n-a\n+b\n*** End Patch"]}
    assert hook("pre-tool", {**as_bob, "tool_name": "apply_patch", "tool_input": patch})
    as_alice = {"transcript_path": transcript("alice", "/code/demo"), "cwd": "/code/demo"}
    assert hook("pre-tool", {**as_alice, "tool_name": "Edit", "tool_input": {"file_path": "src/app.py"}}) is None

    # auto-wake: a stopping agent mid-exchange gets its new messages handed back
    await call("send", me="alice", room="demo", to="bob", text="wake up", wait=False)
    woke = hook("stop", as_bob)
    assert woke["decision"] == "block" and "wake up" in woke["reason"], woke
    assert hook("stop", as_bob) is None                       # nothing new: let it stop
    await call("send", me="alice", room="demo", text="DONE shipped", wait=False)
    assert "none" in (await call("history", room="demo")).split("Claims: ")[1].split("\n")[0]  # DONE released claims
    await call("send", me="carol", room="demo", to="bob", text="late", wait=False)
    await call("send", me="carol", room="demo", text="DONE", wait=False)
    assert hook("stop", as_bob) is None                       # exchange closed: don't hold the agent
    assert hook("stop", {"transcript_path": "/nope", "cwd": "/"}) is None  # never joined: no-op

    # shell fallback: an old chat with no MCP tools talks to an MCP agent via `meat-proxy send/wait`
    def shell(*args):
        return subprocess.run([sys.executable, "-m", "meat_proxy.cli", *args], capture_output=True, text=True,
                              env=ENV, timeout=40, cwd=TMP).stdout

    async def mcp_side():
        got = await call("wait", me="mia", room=str(TMP), timeout=15)
        assert "old→mia: hello from the shell" in got, got
        return await call("send", me="mia", room=str(TMP), to="old", text="hi shell", wait=False)
    out, _ = await asyncio.gather(asyncio.to_thread(shell, "send", "--me", "old", "--to", "mia", "--timeout", "15",
                                                    "hello", "from", "the", "shell"), mcp_side())
    assert "mia→old: hi shell" in out, out                    # room defaulted to cwd, same as the MCP agent's
    assert "Claimed" in shell("claim", "--me", "old", "notes.md")
    line = json.dumps({"type": "tool_use", "name": "Bash",
                       "input": {"command": f'meat-proxy send --me old --room "{TMP}" --to mia "x"'}})
    (TMP / "old.jsonl").write_text(line + "\n")
    as_old = {"transcript_path": str(TMP / "old.jsonl"), "cwd": str(TMP)}
    as_mia = {"transcript_path": transcript("mia", str(TMP)), "cwd": str(TMP)}
    assert hook("pre-tool", {**as_old, "tool_name": "Write", "tool_input": {"file_path": "notes.md"}}) is None
    assert hook("pre-tool", {**as_mia, "tool_name": "Write", "tool_input": {"file_path": "notes.md"}})
    await call("send", me="mia", room=str(TMP), to="old", text="ping old", wait=False)
    assert "ping old" in hook("stop", as_old)["reason"]        # auto-wake works for shell users too

    # hook config merge keeps the user's own hooks and is reversible
    from meat_proxy.cli import set_hooks
    cfg = TMP / "settings.json"
    cfg.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "say hi"}]}]}}))
    set_hooks(cfg, "/bin/meat-proxy")
    set_hooks(cfg, "/bin/meat-proxy")
    assert len(json.loads(cfg.read_text())["hooks"]["Stop"]) == 2
    set_hooks(cfg, None)
    assert json.loads(cfg.read_text()) == {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "say hi"}]}]}}
    print("ok")


server = subprocess.Popen([sys.executable, "-m", "meat_proxy.cli", "serve"], env=ENV)
try:
    for _ in range(60):
        try:
            if httpx.get(BASE + "/api/health").json()["app"] == "meat-proxy":
                break
        except httpx.HTTPError:
            time.sleep(0.25)
    asyncio.run(main())
finally:
    server.terminate()
