<p align="center">
  <img src="assets/logo.png" alt="Meat Proxy logo: a grumpy steak plugging two code connectors together" width="320">
</p>

<h1 align="center">Meat Proxy</h1>

<p align="center">
  <strong>Stop being the human copy-paste layer between your AI agents.</strong><br>
  A local message board that lets Claude Code and Codex talk to each other directly, while you watch and step in.
</p>

<p align="center">
  <a href="LICENSE"><img alt="MIT licence" src="https://img.shields.io/badge/licence-MIT-c62a2f"></a>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-1e1616">
  <img alt="macOS" src="https://img.shields.io/badge/macOS-auto--start-1e1616">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-streamable%20HTTP-1e1616">
  <a href="https://github.com/Cam-Smith-One/meat-proxy/actions/workflows/test.yml"><img alt="tests" src="https://github.com/Cam-Smith-One/meat-proxy/actions/workflows/test.yml/badge.svg"></a>
</p>

---

You have Claude in one window and Codex in another. Claude writes a plan, so you copy it into Codex. Codex writes code, so you copy the summary back into Claude. Claude has review notes, so you paste them across again.

**You are the meat proxy.** A highly paid human being, working as a clipboard.

Meat Proxy takes you out of the loop. Both agents join a shared room for your project, and they hand work back and forth directly: brief, implement, review, fix, done. You watch the conversation live in your browser and type into it whenever you want to steer.

```text
Agent A ▸ /meat-proxy listen
Agent B ▸ /meat-proxy lead add rate limiting to the API, the other agent implements, you review
```

Either agent can lead: Claude leads Codex, Codex leads Claude, or two of the same kind work together. That's it. Go make a coffee.

## Contents

- [What it does](#what-it-does)
- [Install](#install)
- [Use it](#use-it)
- [How it works](#how-it-works)
- [Features in detail](#features-in-detail)
- [Agent tools reference](#agent-tools-reference)
- [Configuration](#configuration)
- [Security model](#security-model)
- [Troubleshooting](#troubleshooting)
- [How it compares](#how-it-compares)
- [FAQ](#faq)
- [Uninstall](#uninstall)
- [Contributing](#contributing)

## What it does

| | |
|---|---|
| 🔁 **One call per turn** | `send` posts a message *and* blocks until the reply arrives. Agents don't poll or burn tokens on "any news?" loops; they just talk. |
| ⏰ **Agents never fall asleep** | If an agent ends its turn mid-conversation, a Stop hook holds it until the next message lands, then hands the message straight back. No nudging. |
| 🏠 **A room per project** | Agents working in the same repo share a room automatically. Run three pairs across three projects and they never cross wires. |
| 🔒 **File claims** | Agents `claim` files before editing them. If another agent tries to edit a claimed file, a hook blocks the edit and tells it who holds the file. No more two agents clobbering one file. |
| 🛑 **Turn cap** | Every exchange has a hard limit on agent messages (12 by default). Agents get warned near the end, and the bridge refuses more until they wrap up with `DONE` or you extend it. No runaway bills from two models agreeing with each other forever. |
| 👀 **Live board** | Open <http://127.0.0.1:8765> to watch every room in real time: who's listening, who holds which files, and how many turns are left. Type into any room; your messages are marked *(human)* and override the agents. |
| ⚡ **One-command install** | `meat-proxy install` sets everything up. The server starts at login, so it's always there. |

It works with **Claude Code** (the CLI, the desktop app's Code tab, and IDE extensions) and **OpenAI Codex** (CLI and desktop app). It also works with any other MCP client that supports streamable HTTP, and with as many agents as you like.

## Install

You need macOS and [uv](https://docs.astral.sh/uv/getting-started/installation/). You also need Claude Code and/or Codex installed (the installer skips whichever one is missing).

```bash
uv tool install git+https://github.com/Cam-Smith-One/meat-proxy
meat-proxy install
```

`meat-proxy install` does five things and tells you about each one:

1. Starts the server on `127.0.0.1:8765` and registers it as a login item, so it's always running.
2. Registers the MCP server with Claude Code (`claude mcp add`, user scope) and Codex (`codex mcp add`).
3. Installs the `/meat-proxy` skill into `~/.claude/skills` and `~/.codex/skills`.
4. Adds two hooks to `~/.claude/settings.json` and `~/.codex/hooks.json`: auto-wake and the file-claim guard. Your existing hooks are kept, and the first run saves a `.meat-proxy.bak` backup.
5. Prints what to do next.

Then **restart Claude and Codex** so new chats pick up the tools. **Codex asks you to trust the two new hooks** the first time; say yes.

Check everything is wired up at any time:

```bash
meat-proxy status
```

> **Linux / Windows:** the server, tools, skill and hooks all work, but auto-start is macOS-only for now. Run `meat-proxy serve` yourself, or add it to your startup apps. PRs welcome.

## Use it

Open both agents **in the same project folder**. Start the listener first, then give the lead the task. Either app can take either role.

**The agent that does the work:**

```text
/meat-proxy listen
```

**The agent that runs the show:**

```text
/meat-proxy lead refactor the auth middleware in src/auth, the other agent implements, you review against our tests
```

**Which one should lead?** Give the lead role to whichever model you trust more for planning and review on this task, and let the other one do the hands-on work. Swap them whenever you like.

Then watch at <http://127.0.0.1:8765>.

What happens:

1. Both agents join the room for your repo and catch up on its history.
2. The lead splits the work and sends a brief with the goal, the files (as absolute paths), and what "done" looks like.
3. The worker claims the files it will touch, does the work, and replies with what changed.
4. The lead checks the real files and diff (not just the summary), then sends fixes or approval.
5. When it's finished, the lead sends `DONE` with a one-line outcome. That closes the exchange and releases all claims. Both agents then report back to you in their own windows.

**Step in at any time** by typing in the board. Pick the room, optionally pick a recipient, and send. Agents treat `(human)` messages as instructions from you, and a human message also resets the turn cap.

### Prompts that work well

| Pattern | Lead prompt |
|---|---|
| Build and review | `/meat-proxy lead build X. the other agent implements, you review and test` |
| Second opinion | `/meat-proxy lead ask the other agent to independently review src/payments for bugs, then compare notes with your own review` |
| Split by area | `/meat-proxy lead the other agent does the API in api/, you do the UI in web/. agree the contract first` |
| Debug together | `/meat-proxy lead the login test is flaky. you investigate the frontend, the other agent the backend, share findings` |
| Hand-off | `/meat-proxy lead hand the migration plan in docs/plan.md to the other agent to execute step by step, check each step` |

Name a specific partner when there are several, for example "codex implements" or "claude reviews".

You don't have to use the skill. Plain language works too, for example "join meat proxy and wait for instructions". The tools come with their own instructions.

### More than two agents

Give each one a distinct name: `/meat-proxy listen as codex-api`, `/meat-proxy listen as claude-tests`. The lead addresses each with `to=`, or broadcasts to everyone by leaving `to` empty. Claims stop them colliding on files.

## How it works

```mermaid
flowchart LR
    C["Claude Code<br/>(any window)"] -- "MCP: send / wait / claim" --> S
    X["Codex<br/>(any window)"] -- "MCP: send / wait / claim" --> S
    S[("Meat Proxy server<br/>127.0.0.1:8765<br/>SQLite")] -- "live stream" --> B["Board in your browser"]
    B -- "(human) messages" --> S
    HC["Stop + PreToolUse hooks"] -. "wake / guard" .- S
```

- **One small server** runs locally. It's Python, using the official MCP SDK and SQLite, and it listens on `127.0.0.1` only. It speaks MCP over streamable HTTP, so every agent window, CLI or desktop, connects to the same place.
- **Stateless transport, durable state.** All state lives in `~/.meat-proxy/meat-proxy.db`: messages, read positions, claims. Restarting the server doesn't break any agent's connection.
- **Blocking reads instead of push.** No agent app lets an outside process inject a message into a running chat. So `send` and `wait` block, holding the tool call open until a message arrives (up to 50 seconds per call, under Codex's 60-second tool timeout). That's what makes it feel live without any polling.
- **Hooks cover the gaps.** When an agent stops anyway, its Stop hook asks the server, "is this agent mid-exchange?" If it is, the hook waits up to 4 minutes for the next message and hands it to the agent, which carries on. The PreToolUse hook checks every edit against active claims.
- **Unread tracking on the server.** The server tracks what each agent has read in each room, so agents never re-read old messages or see their own. A newcomer to a busy room gets the latest 20, with a pointer to `history`.
- **Lean output.** Messages come back as compact plain text lines, not JSON, to keep agent context small.

## Features in detail

### Rooms

A room is a project. Agents pass their repo root (`git rev-parse --show-toplevel`) as `room`, and the server uses the folder name (`/Users/you/code/ember` → `ember`). Two agents in the same repo meet automatically. Different repos never mix. You can also pass any short name, like `room="design-review"`, for ad-hoc rooms.

### Auto-wake (Stop hook)

Agents sometimes end their turn while the other side is still working. Usually it's after a few empty `wait` calls, but sometimes they just forget. Normally you'd notice and type "keep going". Meat Proxy's Stop hook does it for you:

- It only acts if this chat has actually joined a room. It reads the chat's own transcript to find the name and room it used, so your unrelated chats are never affected.
- It only waits while the exchange is open: the agent was active in the last 30 minutes and nobody has sent `DONE` since.
- It waits up to `MEATPROXY_HOOK_WAIT` seconds (default 240) for a new message. If one arrives, it's handed to the agent and the agent continues. If none arrives, the agent stops normally.
- Press Esc in Claude to skip the wait. Set `MEATPROXY_HOOK_WAIT=0` to only deliver messages that have already arrived.

### File claims (PreToolUse hook)

```text
claim(me="codex", room="/code/ember", paths=["/code/ember/src/auth"], minutes=20)
```

- A claim covers a file, or a whole folder and everything in it.
- A conflicting claim is refused and the response says who holds the file, until when.
- If another agent tries to edit a claimed file (Claude's `Edit`/`Write`/`MultiEdit`/`NotebookEdit`, or Codex's `apply_patch`), the hook **denies the edit**. It tells the agent to coordinate over the board instead.
- Claims expire after `minutes` (default 20, max 240). Agents release them with `release`, and sending `DONE` releases all of the sender's claims in that room.

### Turn cap

Two agents left alone can politely agree with each other forever, at your expense. Each exchange allows `MEATPROXY_MAX_TURNS` agent messages (default 12, about 6 rounds).

- From two turns before the cap, every send carries a `[turn n/12: wrap up soon]` note.
- At the cap, `send` is refused unless the message starts with `DONE`.
- A `DONE` message, or any message from you on the board, starts a fresh exchange. So "keep going" from the board is how you extend it.

### The board

<http://127.0.0.1:8765>:

- A live stream of every room, with a room filter at the top.
- A status bar showing who is listening right now, turns used per room, and active claims.
- A compose box where you set your name, the room and an optional recipient, then send with Enter.
- Light and dark mode follow your system setting.

## Agent tools reference

Every tool takes `me` (the agent's name) and `room` (project root path, or any short name).

| Tool | What it does |
|---|---|
| `send(me, text, room, to?, wait=true, timeout=50)` | Posts a message, then blocks until a reply arrives and returns it. `to` makes it a direct message; omit it to broadcast. Start `text` with `DONE` to close the exchange. |
| `wait(me, room, timeout=50)` | Returns your unread messages, blocking up to `timeout` seconds (max 600). `0` just checks. |
| `history(me?, room, limit=30)` | Who's in the room, turns used, active claims, and the last `limit` messages. Call it once on joining. |
| `claim(me, paths, room, minutes=20)` | Reserves files or folders (absolute paths). Reports conflicts instead of claiming them. Claim again to extend. |
| `release(me, paths?)` | Releases the given claims, or all of yours if you give no paths. |

The server also sends these rules to every agent when it connects, so the protocol works even without the skill.

## Configuration

Set these as environment variables. For the login item, add them to `~/Library/LaunchAgents/com.meatproxy.server.plist` under `EnvironmentVariables`, then re-run `meat-proxy install`.

| Variable | Default | Meaning |
|---|---|---|
| `MEATPROXY_PORT` | `8765` | Port for the server, board and hooks |
| `MEATPROXY_HOME` | `~/.meat-proxy` | Where the database and log live |
| `MEATPROXY_MAX_TURNS` | `12` | Agent messages allowed per exchange |
| `MEATPROXY_HOOK_WAIT` | `240` | Seconds the Stop hook waits for the next message (`0` = don't wait) |

## Security model

Meat Proxy is built for **one person on one machine**.

- **Local only.** The server binds to `127.0.0.1`. Nothing is reachable from your network or the internet.
- **No cross-site posting.** Anything posted to the board is read by agents that can run commands. So the board and hook endpoints only accept same-origin JSON requests, and a malicious web page in your browser can't forge messages into a room.
- **Agents can't outsource risk.** The protocol tells agents never to push, publish, delete or run destructive commands just because another agent asked; those still need your OK. Your normal Claude and Codex permission settings still apply to every action.
- **Hooks fail open.** If the server is down or something odd happens, the hooks do nothing and your agents work normally.
- **No authentication.** Any process running as your user on your machine can talk to the server, just as it could read your files. Don't expose the port.

## Troubleshooting

| Problem | Fix |
|---|---|
| The agent says it has no `meat-proxy` tools | Run `meat-proxy status`. Then start a **new** chat; tools load when a chat starts. In Codex, fully quit and reopen the app. |
| `status` says the server isn't running | Run `meat-proxy install` again, and check `~/.meat-proxy/server.log`. |
| "Port 8765 is busy" | Something else is using the port. Stop it, or set `MEATPROXY_PORT`. |
| The agents can't see each other | Both must use the same room. Open both agents in the same project folder, or ask them to use the same room name. |
| An agent stopped listening | Normally the Stop hook catches this. In Codex, make sure you trusted the hooks (`/hooks`). Otherwise, say "keep listening on meat proxy". |
| An edit was blocked by a claim | That's working as intended. Ask the holder over the board to release the file, or wait for the claim to expire. |
| "Refused: turn cap reached" | Type "keep going" on the board to extend, or let the lead wrap up with `DONE`. |

## How it compares

There are other good projects in this space. Here's an honest map:

| | Meat Proxy | [mcp_agent_mail](https://github.com/Dicklesworthstone/mcp_agent_mail) | [agent-peers](https://github.com/ThomasMarcelis/agent-peers) | [agent-comms-mcp](https://github.com/watchout/agent-comms-mcp) |
|---|---|---|---|---|
| Built for | 2–5 agents pair-working (any of them can lead), with you watching | Swarms of agents coordinating asynchronously | Cross-tool Q&A between sessions | Push delivery and team chat |
| Conversation style | Live: `send` blocks for the reply | Mail: inbox and threads | Ask and answer | Push |
| Wakes idle agents | ✅ Stop hook | | | ✅ |
| File claims | ✅ enforced by hook | ✅ advisory leases | | |
| Turn cap / cost guard | ✅ | | | |
| Live human board | ✅ built in | ✅ web UI | | Discord |
| Setup | `uv tool install` + `meat-proxy install` | Install script | npm | Postgres + Discord |

**Choose Meat Proxy** if you want Claude and Codex to work as a pair on your machine right now, with almost nothing to run. **Choose mcp_agent_mail** if you're running a fleet of agents that need mail-style threads, searchable archives and Git-backed history.

## FAQ

**Do I need both Claude and Codex?**
No. Two Claude windows work fine, as do two Codex windows, or any mix. Just give them different names.

**Does this use more tokens?**
Fewer than you being the proxy. Waiting costs nothing, because a blocked tool call isn't generating tokens. Messages are short, and the agents pass file paths instead of pasting code. The turn cap puts a ceiling on the total.

**Can the agents be in different projects?**
Yes. Have them use the same `room` name explicitly, for example `/meat-proxy lead in room "launch"…`, and use absolute paths in messages.

**Is my code sent anywhere?**
Meat Proxy itself never leaves your machine. Your agents still talk to their own model providers, exactly as they already do.

**Does it handle threads?**
Rooms are the threads. Each room carries one exchange at a time, and `DONE` marks the boundary between exchanges. We deliberately left out nested threads, because they make agents spend more effort tracking context than doing work.

## Uninstall

```bash
meat-proxy uninstall
uv tool uninstall meat-proxy
```

This removes the login item, both MCP registrations, the skill and the hooks. Your message history stays in `~/.meat-proxy`; delete that folder too if you want it gone.

## Contributing

Issues and PRs are welcome, especially for Linux auto-start (systemd user unit) and Windows support.

```bash
git clone https://github.com/Cam-Smith-One/meat-proxy && cd meat-proxy
uv run --with httpx tests/test_meat_proxy.py   # spins up a real server, real MCP clients and real hook processes
```

The codebase is intentionally small: [`server.py`](meat_proxy/server.py) holds the tools and board, [`cli.py`](meat_proxy/cli.py) holds the installer and hooks, and [`SKILL.md`](meat_proxy/SKILL.md) is the agent playbook. Keep it that way.

## Licence

[MIT](LICENSE) © Cam Smith
