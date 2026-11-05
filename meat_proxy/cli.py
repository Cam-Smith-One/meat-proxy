"""meat-proxy command line: serve, install, uninstall, status, and the agent hooks.

Everything except `serve` is stdlib-only so hooks start fast.
"""
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from importlib.resources import files
from pathlib import Path

from . import __version__, overlaps

PORT = int(os.environ.get("MEATPROXY_PORT", 8765))
BASE = f"http://127.0.0.1:{PORT}"
HOME = Path(os.path.expanduser(os.environ.get("MEATPROXY_HOME", "~/.meat-proxy")))
LABEL = "com.meatproxy.server"
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
CLAUDE_SETTINGS = Path.home() / ".claude/settings.json"
CODEX_HOOKS = Path.home() / ".codex/hooks.json"
SKILL_DIRS = [Path.home() / ".claude/skills/meat-proxy", Path.home() / ".codex/skills/meat-proxy"]
EDIT_TOOLS = "Edit|Write|MultiEdit|NotebookEdit|apply_patch"
LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never route localhost via HTTP_PROXY

USAGE = f"""meat-proxy {__version__}: stop being the human copy-paste layer between your AI agents.

  meat-proxy install     start the server at login, register it with Claude Code and Codex, add skill + hooks
  meat-proxy uninstall   undo all of that (your message history stays in {HOME})
  meat-proxy status      check the server and what's installed
  meat-proxy serve       run the server in the foreground
  meat-proxy hook stop|pre-tool   (called by Claude/Codex hooks, not by you)

Agent commands (for chats without the MCP tools; room defaults to this repo):
  meat-proxy send --me NAME [--to NAME] [--no-wait] [--timeout 50] TEXT
  meat-proxy wait --me NAME [--timeout 50]
  meat-proxy history [--me NAME] [--limit 30]
  meat-proxy claim --me NAME [--minutes 20] PATH...
  meat-proxy release --me NAME [PATH...]

Board: {BASE}"""


# --- small utilities ---------------------------------------------------------------------------

def api(method, path, body=None, timeout=5):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    with LOCAL.open(req, timeout=timeout) as r:
        return json.load(r)


def server_up(version=None):
    try:
        h = api("GET", "/api/health", timeout=2)
        return h.get("app") == "meat-proxy" and version in (None, h.get("version"))
    except Exception:
        return False


def say(ok, msg):
    print(f"  {'✓' if ok else '!'} {msg}")


def run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def backup_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not path.with_suffix(path.suffix + ".meat-proxy.bak").exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".meat-proxy.bak"))
    path.write_text(text)


def exe_path():
    exe = shutil.which("meat-proxy") or os.path.abspath(sys.argv[0])
    if any(t in exe for t in ("/.cache/", "/tmp/", "/T/")):
        sys.exit(f"meat-proxy is running from a temporary location ({exe}).\n"
                 "Install it permanently first:  uv tool install git+https://github.com/Cam-Smith-One/meat-proxy")
    return exe


# --- hooks config (same JSON shape for Claude Code and Codex) ----------------------------------

def is_ours(hook):
    return "meat-proxy" in hook.get("command", "") and " hook " in hook.get("command", "")


def strip_hooks(cfg):
    for event in list(cfg.get("hooks", {})):
        groups = [{**g, "hooks": [h for h in g.get("hooks", []) if not is_ours(h)]} for g in cfg["hooks"][event]]
        cfg["hooks"][event] = [g for g in groups if g["hooks"]]
        if not cfg["hooks"][event]:
            del cfg["hooks"][event]
    if "hooks" in cfg and not cfg["hooks"]:
        del cfg["hooks"]
    return cfg


def set_hooks(path: Path, exe: str | None):
    cfg = json.loads(path.read_text() or "{}") if path.exists() else {}
    strip_hooks(cfg)
    if exe:
        hooks = cfg.setdefault("hooks", {})
        hooks.setdefault("Stop", []).append(
            {"hooks": [{"type": "command", "command": f'"{exe}" hook stop', "timeout": 300}]})
        hooks.setdefault("PreToolUse", []).append(
            {"matcher": EDIT_TOOLS, "hooks": [{"type": "command", "command": f'"{exe}" hook pre-tool', "timeout": 10}]})
    backup_write(path, json.dumps(cfg, indent=2) + "\n")


# --- install / uninstall -------------------------------------------------------------------------

def start_service(exe):
    if sys.platform != "darwin":
        say(False, "Auto-start is macOS-only for now: run `meat-proxy serve` in a terminal or your startup apps.")
        return
    HOME.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_bytes(plistlib.dumps({
        "Label": LABEL, "ProgramArguments": [exe, "serve"], "RunAtLoad": True, "KeepAlive": True,
        "StandardOutPath": str(HOME / "server.log"), "StandardErrorPath": str(HOME / "server.log"),
    }))
    domain = f"gui/{os.getuid()}"
    run("launchctl", "bootout", f"{domain}/{LABEL}")
    if server_up():  # an old server outside launchd (or slow to exit) would keep the port and block the new one
        for pid in run("lsof", "-ti", f"tcp:{PORT}", "-sTCP:LISTEN").stdout.split():
            run("kill", pid)
        time.sleep(1)
    r = run("launchctl", "bootstrap", domain, str(PLIST))
    for _ in range(60):
        if server_up(__version__):  # bootout is async: don't mistake the old server for the new one
            return say(True, f"Server running at {BASE} (starts at login)")
        time.sleep(0.5)
    say(False, f"Server didn't come up. Is something else on port {PORT}? See {HOME / 'server.log'} {r.stderr.strip()}")


def install():
    exe = exe_path()
    print("Installing Meat Proxy…")
    if not server_up() and run("lsof", "-ti", f"tcp:{PORT}").stdout.strip():
        sys.exit(f"Port {PORT} is busy with something else. Stop it, or set MEATPROXY_PORT, then re-run install.")
    start_service(exe)

    if shutil.which("claude"):
        run("claude", "mcp", "remove", "meat-proxy", "-s", "user")
        r = run("claude", "mcp", "add", "--transport", "http", "--scope", "user", "meat-proxy", BASE + "/mcp")
        say(r.returncode == 0, "Claude Code: MCP server registered" if r.returncode == 0 else r.stderr.strip())
    else:
        say(False, "Claude Code CLI not found: skipped MCP registration")
    if shutil.which("codex"):
        run("codex", "mcp", "remove", "meat-proxy")
        r = run("codex", "mcp", "add", "meat-proxy", "--url", BASE + "/mcp")
        say(r.returncode == 0, "Codex: MCP server registered" if r.returncode == 0 else r.stderr.strip())
    else:
        say(False, "Codex CLI not found: skipped MCP registration")

    skill = files(__package__).joinpath("SKILL.md").read_text()
    for d in SKILL_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(skill)
    say(True, "Skill installed: /meat-proxy in Claude Code and Codex")

    set_hooks(CLAUDE_SETTINGS, exe)
    set_hooks(CODEX_HOOKS, exe)
    say(True, "Hooks installed: auto-wake (Stop) and file-claim guard (PreToolUse)")
    print(f"""
Done. Next:
  1. Restart Claude and Codex (new chats pick up the tools). Codex asks you to trust the two new hooks once.
  2. In one agent (Claude or Codex):  /meat-proxy listen
     In the other:                    /meat-proxy lead <your task>
  3. Watch and step in at {BASE}
""")


def uninstall():
    print("Uninstalling Meat Proxy…")
    if sys.platform == "darwin":
        run("launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}")
        PLIST.unlink(missing_ok=True)
        say(True, "Server stopped and removed from login items")
    if shutil.which("claude"):
        run("claude", "mcp", "remove", "meat-proxy", "-s", "user")
    if shutil.which("codex"):
        run("codex", "mcp", "remove", "meat-proxy")
    say(True, "MCP registrations removed")
    for d in SKILL_DIRS:
        shutil.rmtree(d, ignore_errors=True)
    say(True, "Skill removed")
    for p in (CLAUDE_SETTINGS, CODEX_HOOKS):
        if p.exists():
            set_hooks(p, None)
    say(True, "Hooks removed")
    print(f"History kept in {HOME}. To remove the command too:  uv tool uninstall meat-proxy")


def status():
    up = server_up()
    say(up, f"Server {'running' if up else 'not running'} at {BASE}")
    say(sys.platform == "darwin" and PLIST.exists(), "Starts at login")
    for name, cli in (("Claude Code", "claude"), ("Codex", "codex")):
        ok = bool(shutil.which(cli)) and run(cli, "mcp", "get", "meat-proxy").returncode == 0
        say(ok, f"{name}: MCP server {'registered' if ok else 'not registered'}")
    say(all((d / "SKILL.md").exists() for d in SKILL_DIRS), "Skill installed")
    for name, p in (("Claude Code", CLAUDE_SETTINGS), ("Codex", CODEX_HOOKS)):
        ok = p.exists() and "meat-proxy" in p.read_text() and " hook " in p.read_text()
        say(ok, f"{name}: hooks {'installed' if ok else 'missing'}")


# --- hooks (run by Claude Code / Codex; must never break the agent) ------------------------------

# MCP calls look like "me": "claude"; shell-fallback calls look like --me claude
ME = re.compile(r'\\*"me\\*"\s*:\s*\\*"([^"\\]+)|--me[ =]\\*["\']?([\w.-]+)')
ROOM = re.compile(r'\\*"room\\*"\s*:\s*\\*"([^"\\]+)|--room[ =]\\*["\']?([^"\'\\\s]+)')
PATCH_FILE = re.compile(r"\*\*\* (?:Update|Add|Delete) File: ([^\n\\]+)")


def identity(data):
    """The name and room this session last used with Meat Proxy, read from its transcript."""
    path = data.get("transcript_path")
    if not path or not os.path.exists(path):
        return None, None
    with open(path, "rb") as f:
        f.seek(max(0, os.path.getsize(path) - 2_000_000))
        tail = f.read().decode(errors="ignore")
    me = room = None
    for line in tail.splitlines():
        if "meat-proxy" in line or "meat_proxy" in line:
            if m := ME.search(line):
                me = m.group(1) or m.group(2)
                if r := ROOM.search(line):
                    room = r.group(1) or r.group(2)
    return me, room


def hook_stop(data):
    me, room = identity(data)
    if not me:
        return  # this session never joined a room
    wait = int(os.environ.get("MEATPROXY_HOOK_WAIT", 240))
    room = room or default_room(data.get("cwd"))
    res = api("POST", "/api/stop", {"me": me, "room": room, "wait": wait}, timeout=wait + 15)
    if res.get("messages"):
        print(json.dumps({"decision": "block", "reason": (
            f"Meat Proxy: new messages for you ({me}) in room '{res['room']}':\n{res['messages']}\n"
            f"Handle them, then reply with send(me=\"{me}\", room=\"{room}\", ...).")}))


def edited_paths(data):
    tool_input = data.get("tool_input") or {}
    cwd = data.get("cwd") or os.getcwd()
    paths = [tool_input[k] for k in ("file_path", "notebook_path", "path") if isinstance(tool_input.get(k), str)]
    paths += PATCH_FILE.findall(json.dumps(tool_input))
    return [os.path.normpath(os.path.join(cwd, p.strip())) for p in paths]


def hook_pre_tool(data):
    paths = edited_paths(data)
    if not paths:
        return
    leases = api("GET", "/api/leases", timeout=2)["leases"]
    me, _ = identity(data)
    for p in paths:
        for lease in leases:
            if lease["holder"] != me and overlaps(p, lease["path"]):
                until = time.strftime("%H:%M", time.localtime(lease["expires"]))
                print(json.dumps({"hookSpecificOutput": {
                    "hookEventName": "PreToolUse", "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"{p} is claimed by {lease['holder']} on Meat Proxy (room '{lease['room']}') until {until}. "
                        f"Ask {lease['holder']} to release it with send(), or work on something else.")}}))
                return


def hook(kind):
    try:
        data = json.load(sys.stdin)
        {"stop": hook_stop, "pre-tool": hook_pre_tool}[kind](data)
    except Exception:
        pass  # proxy down or odd input: never block the agent's real work


def default_room(cwd=None):
    """The repo root (or cwd), matching what agents pass as `room` over MCP."""
    r = run("git", "-C", cwd or os.getcwd(), "rev-parse", "--show-toplevel")
    return r.stdout.strip() if r.returncode == 0 else (cwd or os.getcwd())


def agent_cmd(argv):
    """Shell fallback for chats that started before Meat Proxy was installed and so have no MCP tools."""
    import argparse
    p = argparse.ArgumentParser(prog="meat-proxy")
    sub = p.add_subparsers(dest="tool", required=True)
    for name in ("send", "wait", "history", "claim", "release"):
        s = sub.add_parser(name)
        s.add_argument("--me", required=name != "history", help="your agent name, e.g. claude or codex")
        if name != "release":
            s.add_argument("--room", default=None, help="project root or room name (default: this repo)")
        if name == "send":
            s.add_argument("text", nargs="+")
            s.add_argument("--to")
            s.add_argument("--no-wait", dest="wait", action="store_false")
        if name in ("send", "wait"):
            s.add_argument("--timeout", type=int, default=50)
        if name == "history":
            s.add_argument("--limit", type=int, default=30)
        if name in ("claim", "release"):
            s.add_argument("paths", nargs="*")
        if name == "claim":
            s.add_argument("--minutes", type=int, default=20)
    a = vars(p.parse_args(argv))
    tool = a.pop("tool")
    if "room" in a:
        a["room"] = a["room"] or default_room()
    if tool == "send":
        a["text"] = " ".join(a["text"])
    if tool == "claim":
        a["paths"] = [os.path.abspath(x) for x in a["paths"]]
    if tool == "release":
        a["paths"] = [os.path.abspath(x) for x in a["paths"]] or None
    try:
        res = api("POST", "/api/call", {"tool": tool, "args": a}, timeout=a.get("timeout", 0) + 15)
    except Exception as e:
        sys.exit(f"Meat Proxy server not reachable at {BASE} ({e}). Run: meat-proxy status")
    print(res.get("text") or res)


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    if cmd in ("send", "wait", "history", "claim", "release"):
        agent_cmd(args)
    elif cmd == "serve":
        from .server import run as serve
        serve()
    elif cmd in ("install", "uninstall", "status"):
        globals()[cmd]()
    elif cmd == "hook" and len(args) > 1:
        hook(args[1])
    elif cmd in ("--version", "-V"):
        print(__version__)
    else:
        print(USAGE)


if __name__ == "__main__":
    main()
