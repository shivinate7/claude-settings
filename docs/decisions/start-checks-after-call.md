# The start checks run in the started session

## The ruling

Every session that starts from source `startup` gets two checks at its own start. The checks are in `hooks/start_check.py`, a SessionStart hook. `settings.json` runs it with matcher `startup`, so it runs on no other source.

The checks flag. They do not stop. `start_check.py` `main` prints one line: SessionStart `additionalContext`. It has no `continue` and no `stopReason`. The two checks are the model floor (decision `agent-model-cap`, the agent model cap) and the full-machine load brake (decision `machine-load-brake`, the machine-load brake).

The flag text tells the session what to do. A session with a `parent_session_id` (a lane) does no work and tells its parent it started in this state. A session with no parent (the owner's own) goes on.

Decision `start-session-not-pretooluse` (start_session is not judged at PreToolUse) left both checks lost from the caller's side. This record moves both checks to the started session, as flags. It does not move the handoff check.

## Why the started session

A PreToolUse hook that covers `mcp__ccd_session__start_session` makes the desktop app show its start card on every start. The public bug is anthropics/claude-code#103832, the open issue on that card.

A SessionStart hook is not a PreToolUse hook, and it does not list the start tool. Whether the app shows a card for it is unmeasured. The owner's test covered PreToolUse matchers only.

## What it checks

The hook acts on source `startup` only. A resume, compact, clear or fork prints nothing.

1. The model floor, first. `start_check.py` `flag_text` asks `guard.py` `floor_hit`, the one home of the floor. A model below the floor is flagged. Local and cloud sessions both get this check.
2. The full-machine load brake, second. Local sessions only. `guard.py` `read_load` reads the load once. `guard.py` `load_full` names each reading over the full line: memory over 95% (`hooks/guard.py: LOAD_FULL_MEMORY = 95.0`), or disk free under the smaller of 5% and 5 GB. A cloud session skips this check, and only this one.
3. The model is checked first, so a run prints one flag at most.
4. It fails open. A failed import of `guard`, a bad payload, a payload that is not an object, or any error prints nothing and exits 0. A broken check lets a start through with no flag. That is the choice: a session must still start.

## Departs from main

Departs from: main stops no `start_session` at full. The load brake does not reach that tool (`machine-load-brake`; since PR 3501). Main still refuses Agent, Task and Workflow starts at full. This hook flags every startup below the floor, and every local startup at full load.

It flags rather than stops, because the started session cannot tell a lane from an owner session. A started session has no own lane record to read at start (`machine-load-brake`, lane sessions). The flag text addresses a session with a `parent_session_id`. The earlier plan to stop owner sessions at full no longer applies: an owner session goes on after the flag.

Chosen: a flag, not a stop (coordinator, 2026-11-15).

## Why both the hook and the audit flag a Haiku start

The PostToolUse audit (`start_session_audit.py`) flags a Haiku start too. The audit runs in the caller, after the `start_session` call. This hook (`start_check.py` `flag_text`) runs in the started session, so it also covers a start that did not come through `start_session`. Each reads `guard.py` `floor_hit`. Both flag. Neither stops.

## What stays with the audit

Handoff-unread does not move. The handoff check reads the caller's handoff flag (`reread_check.py` `unread_handoff`). That is the caller's state. `start_check.py` `flag_text` does not read it. It stays flag-only in the PostToolUse audit, `start_session_audit.py`. The caller's next call on a listed tool is still refused until it reads the handoff (`guard.py` `judge`).

## What a flag loses

A model can ignore the flag. The text says what to do, but nothing enforces it. The PostToolUse audit has the same gap. A Haiku session, or a session started on a full machine, can keep working.

## Unknown

Both are unmeasured. No command settles either here.

1. Whether the desktop app delivers SessionStart `additionalContext` to a `start_session` session. If not, the flag never reaches the model.
2. Whether a `start_session` session runs its startup SessionStart hook at all. If not, neither check (`start_check.py` `flag_text`) runs there.

## Cost

Per `outcomes-mechanize-rules` (the rule that each hook states its cost):

- Process starts: one hook process per `startup`, started by the harness. The hook starts no child process. `hooks/test_start_check.py` class `CostProof` proves it: `test_a_braked_startup_starts_no_process_and_writes_no_file`, `test_a_model_floor_flag_starts_no_process_and_writes_no_file` and `test_an_unflagged_startup_reads_the_load_and_starts_no_process`. Class `HarnessControls` proves the import starts none: `test_control_importing_guard_starts_no_process`.
- Reads: the payload. A local startup also reads the load once: one memory counter and one `statfs`. A cloud startup reads no load.
- Files written: none, by those cases.
- Bytecode cache: Python may write one for the imported guard module on a first run. The hook does not write it itself (`start_check.py` `main`), and the test sets `PYTHONDONTWRITEBYTECODE`, so it cannot see it. Unmeasured.
- Timer, watcher or log: none. `start_check.py` `main` writes no log line.
- How often: once per startup. Not on resume, compact, clear or fork.

## Tests

- `hooks/test_start_check.py` runs the hook as a subprocess (`test_start_check.py` `run_hook`), with the load reading and process starts patched. Its classes: `StartupLoadBrake`, `BrakeOnlyAtStartup`, `CloudSession`, `ModelFloor`, `FailOpen`, `CostProof` and `HarnessControls`.
- `lint/test_start_check_wiring.py` pins the `settings.json` wiring: one SessionStart command, matcher `startup`.
- Both pass on this branch.

## Related

- Decision `start-session-not-pretooluse` (start_session is not judged at PreToolUse): why no PreToolUse hook covers the start tool. Its load and floor bullets point here.
- Debt `start-session-load-unbraked` (the load debt: a full-machine start is flagged, and it stays open).
- Debt `start-session-checks-after` (the checks-after debt: a start is flagged after it starts).

Kind: build
Plan: docs/decisions/start-checks-after-call.md#the-ruling (macos)
Plan: docs/decisions/start-checks-after-call.md#the-ruling (windows)
Plan: docs/decisions/start-checks-after-call.md#the-ruling (linux)
