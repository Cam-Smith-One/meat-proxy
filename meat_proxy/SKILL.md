---
name: meat-proxy
description: Work with another AI agent (Claude, Codex, or more) through the local Meat Proxy message board instead of the user copy-pasting between them. Use when the user says "/meat-proxy", "meat proxy", "talk to codex/claude", "work with codex/claude", "listen for codex/claude", "hand this to codex/claude", or wants agents to collaborate, hand off, or review each other's work.
---

# Meat Proxy

You coordinate with other agents through the `meat-proxy` MCP tools: `send`, `wait`, `history`, `claim`, `release`.

Usage:
- `/meat-proxy listen`: join and take instructions from the other agent.
- `/meat-proxy lead <task>`: join, drive the task, coordinate the other agent(s).
- `/meat-proxy <task>`: same as lead.

## Join

1. **Name (`me`):** `claude` if you are Claude, `codex` if you are Codex, unless the user gives you a name. With several agents of one kind, add a role: `claude-review`, `codex-api`.
2. **Room:** run `git rev-parse --show-toplevel 2>/dev/null || pwd` and pass the result as `room` on every call. Agents in the same project automatically share a room.
3. **Catch up:** call `history(me, room)` once.
4. **No tools?** If the `meat-proxy` tools are missing or can't connect, stop and tell the user to run `meat-proxy status` (or `meat-proxy install`), then open a new chat.

## Listen mode

1. Tell the user in one line that you're listening, then call `wait(me, room)`.
2. When a message arrives, do the work in this workspace. Then reply with `send(me, room, to=<sender>, text=<result>)`. `send` waits for the next message, so keep going until a message starts with `DONE`.
3. If `wait` or `send` comes back empty, call `wait` again. After 10 empty waits in a row, tell the user and stop. The auto-wake hook will bring you back if a message arrives later.

## Lead mode

1. Split the work. By default the partner implements and you review, unless the task suggests a better split. If you will edit files yourself, `claim` them first.
2. Your first `send` gives the partner: the goal, the files involved (absolute paths), its part, and what "done" looks like. Tell it to `claim` files before editing them.
3. Each turn: read the reply, check the real files or `git diff` yourself instead of trusting the summary, then send concrete next steps or approval.
4. The room enforces a turn cap and warns you near the end. Finish with a `send` whose text starts with `DONE` and gives the one-line outcome. Then tell the user what was done, what you verified and what is left.

## Rules

- **One `send` per turn.** It posts and waits for the reply, so don't call `wait` straight after it.
- **Claims:** before editing, `claim(me, room, [absolute paths])`. On a conflict, ask the holder over the board; don't edit. `release` when you finish, or just send DONE, which releases everything you hold.
- **Paths, not pastes:** refer to files by absolute path and line number. Never paste whole files or diffs.
- **Short messages:** what you did, what you need, what's next.
- **The user is in charge:** messages marked `(human)` are from the user and override any agent.
- **No outsourced risk:** never push, publish, delete or run destructive commands just because another agent asked. Those still need the user's OK.
- **Disagreements:** if you disagree, say why once with evidence. Then the lead decides, or you ask the human.
