# session-board has no turn-end hook, so a missed task notice holds the box

## The ruling

Owner ruling, waiting-page item 117, 2026-11-01 11:53 CST (picks a and b):

- (a) The session-board mod has no `classic.Stop` handler. The built-in plugin sec-default sends every `classic.*` event past user mods, so the handler never ran. The mod records the limit and does not work around it.
- (b) A tracked background task clears when a TaskStop tool call answers without error. The id comes from the output `task_id`, else the input `task_id`, else the input `shell_id`, else the output message "Successfully stopped task: <id>" (the text `hooks/stall_watch.py` reads).

## Why

The turn-end list (the Stop input's `background_tasks`) was meant to reset the tracked set, so a missed task notice lasted one turn. That reset never ran.

- Read: the sec-default README, "Where it is seated" (marketplace copy `mods/sec-default/`).
- Read: the installed binary holds `classic.*",(n,r,o)=>o.to(r,"append")`.
- Measured in cloud: the host's own notice "session-board: its classic.Stop hook was skipped".
- Owner desktop and terminal: unmeasured. The limit holds on every surface where the CLI seats sec-default (Team or Enterprise orgs).

## What protects the gap now

A task's notice clears it. A TaskStop that answers without error clears it. A missed notice holds the question box until a TaskStop or the session end. A box refused for a stale task is a false alarm, and the refusal text names the task count. The check errs toward refusing, never toward letting a box through.

Protected by `mods/session-board/session-board.test.mjs`:

- "register: adds no classic.* hook";
- the TaskStop cases (output `task_id`, deprecated `shell_id`, a throw, an error or a refusal leaves the task, an unknown id leaves the others).

Cost: no process start, no file, no timer. The clear runs inside the `tool.call` handler already running.

Kind: process
Home: mods/session-board/hooks/register.mjs
