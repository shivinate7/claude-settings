# The start checks run in the started session

## The ruling

Every session that starts from source `startup` runs two checks at its own start. The checks are in `hooks/start_check.py`, a SessionStart hook. `settings.json` runs it with matcher `startup`, so it runs on no other source.

The two checks are the model floor (decision `agent-model-cap`, the agent model cap) and the full-machine load brake (decision `machine-load-brake`, the machine-load brake). A hit prints one stop line: `continue` false, with a `stopReason`.

Decision `start-session-not-pretooluse` (start_session is not judged at PreToolUse) left both checks lost from the caller's side. This record moves the model floor and the load brake to the started session. It does not move the handoff check. Whether the desktop app honours the stop is unknown (see Unknown).

## Why the started session

A PreToolUse hook that covers `mcp__ccd_session__start_session` makes the desktop app show its start card on every start. The public bug is anthropics/claude-code#103832, the open issue on that card.

A SessionStart hook is not a PreToolUse hook, and it does not list the start tool. Whether the app shows a card for it is unmeasured. The owner's test covered PreToolUse matchers only.

## What it checks

The hook acts on source `startup` only. A resume, compact, clear or fork prints nothing.

1. The model floor, first. `start_check.py` `stop_reason` asks `guard.py` `floor_hit`, the one home of the floor. A model below the floor stops the start. Local and cloud sessions both get this check.
2. The full-machine load brake, second. Local sessions only. `guard.py` `read_load` reads the load once. `guard.py` `load_full` names each reading over the full line: memory over 95% (`hooks/guard.py: LOAD_FULL_MEMORY = 95.0`), or disk free under the smaller of 5% and 5 GB. A cloud session skips this check, and only this one.
3. The model is checked first, so a run prints one stop at most.
4. It fails open. A bad payload, a payload that is not an object, or any error prints nothing and exits 0. A broken check lets a start through. That is the choice: a session must still start.

## Departs from main

Departs from: main (`machine-load-brake`) stops only Agent, Task and Workflow starts at full. This hook stops every local startup at full, owner sessions included. A started session has no own lane record to read at start (`machine-load-brake`, lane sessions). So it cannot tell a lane start from an owner session.

Open question for the owner. It is not blocking. Options:

- (a) As built: stop every local startup at full.
- (b) Stop lane starts only. This needs a start signal that marks a lane. `start_check.py` `stop_reason` reads only the source and the model.
- (c) No load stop at start. Keep the brake on Agent, Task, Workflow and a lane's own shell and file writes.

Recommendation: (a). A full machine stalls every session, not only lanes. A stop at start only delays a new session until space is freed.

## What stays with the audit

Handoff-unread does not move. The handoff check reads the caller's handoff flag (`reread_check.py` `unread_handoff`). That is the caller's state. `start_check.py` `stop_reason` does not read it. It stays flag-only in the PostToolUse audit, `start_session_audit.py`. The caller's next call on a listed tool is still refused until it reads the handoff (`guard.py` `judge`).

## Unknown

Whether the desktop app honours `continue: false` from a SessionStart hook for a started session. The code prints it. No run in the app has tested it. If the app ignores it, a Haiku start or a full-machine start runs. Then the audit flags a Haiku start, and nothing stops a full-machine start.

## Cost

Per `outcomes-mechanize-rules` (the rule that each hook states its cost):

- Process starts: one hook process per `startup`, started by the harness. The hook starts no child process. `hooks/test_start_check.py` class `CostProof` proves it: `test_a_braked_startup_starts_no_process_and_writes_no_file`, `test_a_model_floor_stop_starts_no_process_and_writes_no_file` and `test_an_unbraked_startup_reads_the_load_and_starts_no_process`. Class `HarnessControls` proves the import starts none: `test_control_importing_guard_starts_no_process`.
- Reads: the payload. A local startup also reads the load once: one memory counter and one `statfs`. A cloud startup reads no load.
- Files written: none, by those cases.
- Bytecode cache: Python may write one for the imported guard module on a first run. The hook does not write it itself (`start_check.py` `main`), and the test sets `PYTHONDONTWRITEBYTECODE`, so it cannot see it. Unmeasured.
- Timer, watcher or log: none. `start_check.py` `main` writes no log line.
- How often: once per startup. Not on resume, compact, clear or fork.

## Tests

- `hooks/test_start_check.py` runs the hook as a subprocess (`test_start_check.py` `run_hook`), with the load reading and process starts patched. Its classes: `StartupLoadBrake`, `CloudSession`, `ModelFloor`, `BrakeOnlyAtStartup`, `FailOpen`, `CostProof` and `HarnessControls`.
- `lint/test_start_check_wiring.py` pins the `settings.json` wiring: one SessionStart command, matcher `startup`.
- Both pass on this branch.

## Related

- Decision `start-session-not-pretooluse` (start_session is not judged at PreToolUse): why no PreToolUse hook covers the start tool. Its load and floor bullets point here.
- Debt `start-session-load-unbraked` (the load debt: a start on a full machine).
- Debt `start-session-checks-after` (the checks-after debt: a start that is flagged after it starts).

Kind: build
Plan: docs/decisions/start-checks-after-call.md#the-ruling (macos)
Plan: docs/decisions/start-checks-after-call.md#the-ruling (windows)
Plan: docs/decisions/start-checks-after-call.md#the-ruling (linux)
