# The start checks run in the started session

## The ruling

Every session that starts from source `startup` gets two checks at its own start. The checks are in `hooks/start_check.py`, a SessionStart hook. `settings.json` runs it with matcher `startup`, so it runs on no other source.

The checks flag. They do not stop. `start_check.py` `main` prints one line: SessionStart `additionalContext`. It has no `continue` and no `stopReason`. The one check is the full-machine load brake (decision `machine-load-brake`, the machine-load brake). The model floor is not checked here (decision `agent-model-cap`, the owner's word for a model). The coordinator picked a flag over a stop (08:40 CST, 2026-11-15). The owner has not ruled; owner confirmation is open.

The flag text tells the session what to do. It addresses a session tagged `cs-build:lane`, read with `get_session` and passing no session_id: that session does no work and tells its parent it started in this state. A session that is not a lane (the owner's own) goes on.

Decision `start-session-not-pretooluse` (start_session is not judged at PreToolUse) left both checks lost from the caller's side. This record moves both checks to the started session, as flags. It does not move the handoff check.

## Why the started session

A PreToolUse hook that covers `mcp__ccd_session__start_session` makes the desktop app show its start card on every start. The public bug is anthropics/claude-code#103832, the open issue on that card.

A SessionStart hook is not a PreToolUse hook, and it does not list the start tool. Whether the app shows a card for it is unmeasured. The owner's test covered PreToolUse matchers only.

## What it checks

The hook acts on source `startup` only. A resume, compact, clear or fork prints nothing.

1. No model check (owner, 2026-11-18 19:03 CST, "if i say haiku it should work, there shouldnt be any guards on a FLOOR"; consultant pick, same time). `start_check.py` `flag_text` reads no model. The spawn guard already checked the owner's word for the model (`guard.py` `owner_names_model`), and the started session cannot read that word, so a Haiku start is not flagged.
2. The full-machine load brake. Local sessions only. `guard.py` `read_load` reads the load once. `guard.py` `load_full` names each reading over the full line: memory over 95% (`hooks/guard.py: LOAD_FULL_MEMORY = 95.0`), or disk free under the smaller of 5% and 5 GB. A cloud session skips this check.
3. A run prints one flag at most.
4. It fails open. A failed import of `guard`, a bad payload, a payload that is not an object, or any error prints nothing and exits 0. A broken check lets a start through with no flag. That is the choice: a session must still start.

## Departs from main

Departs from: main stops no `start_session` at full. The load brake does not reach that tool (`machine-load-brake`; since PR 3501). Main still refuses Agent, Task and Workflow starts at full. This hook flags every local startup at full load.

It flags rather than stops, because the hook cannot tell a lane from an owner session. `start_check.py` `flag_text` reads only the source, so it reads no lane tag. The flag text tells the session to read its own tags with `get_session`. The lane check is that session's own read. `machine-load-brake`, lane sessions, says: "A `parent_session_id` alone makes no lane: triage and the batch runner carry one."

Coordinator pick, 08:40 CST Nov 15: a flag, not a stop. This is not an owner ruling. Owner confirmation: open.

## Why no check flags a Haiku start

Owner, 2026-11-18 19:03 CST: "if i say haiku it should work, there shouldnt be any guards on a FLOOR". The spawn guard checks the owner's last typed turn for the model word (`guard.py` `owner_names_model`). A started session, and the PostToolUse audit (`start_session_audit.py`), cannot read that word, so a flag there would fire on a start the owner asked for. Neither flags a Haiku start.

## What stays with the audit

Handoff-unread does not move. The handoff check reads the caller's handoff flag (`reread_check.py` `unread_handoff`). That is the caller's state. `start_check.py` `flag_text` does not read it. It stays flag-only in the PostToolUse audit, `start_session_audit.py`. The caller's next call on a listed tool is still refused until it reads the handoff (`guard.py` `judge`).

## What a flag loses

A model can ignore the flag. The text says what to do, but nothing enforces it. The PostToolUse audit has the same gap. A session started on a full machine can keep working.

## Unknown

All four are unmeasured. No command settles them here.

1. Whether the desktop app delivers SessionStart `additionalContext` to a `start_session` session. If not, the flag never reaches the model.
2. Whether a `start_session` session runs its startup SessionStart hook at all. If not, neither check (`start_check.py` `flag_text`) runs there.
3. Cloud delivery. The generated cloud settings step of `install.sh` drops startup entries from the cloud `settings.json`. The startup loop in the refresh hook's child runs them instead. There the JSON line shares stdout with plain-text startup hooks such as daily_note and session_start.sh. Whether a cloud session receives the flag is unmeasured. The cloud tests run the hook directly, not through `install.sh`.
4. Lane tag at first read. `session-tiers` sets the lane tag on `create_session` calls. Whether a `start_session` session already carries `cs-build:lane` at its first `get_session` is unmeasured. If the tag is set after the start, the session reads no tag and goes on.

## Cost

Per `outcomes-mechanize-rules` (the rule that each hook states its cost):

- Process starts: one hook process per startup, from the harness: unmeasured. `hooks/test_start_check.py` class `CostProof` shows the hook starts no child: `test_a_braked_startup_starts_no_process_and_writes_no_file`, `test_a_model_floor_flag_starts_no_process_and_writes_no_file` and `test_an_unflagged_startup_reads_the_load_and_starts_no_process`. Class `HarnessControls` shows the import starts none: `test_control_importing_guard_starts_no_process`.
- Reads: the payload. A local startup also reads the load: one memory counter and one `statfs`. A cloud startup reads no load. The number of reads is unmeasured: `test_an_unflagged_startup_reads_the_load_and_starts_no_process` shows a read, not a count.
- Files written: none on success.
- Crash line: `hooks/test_start_check.py` pins only the silence on a failed guard import, in `test_guard_import_failure_on_a_haiku_startup_fails_open`. The guard-crash line that `hooks/guard.py` may append to the guard log, after a retry of up to 5 s (`_LOAD_WAIT_SECONDS`), is unmeasured.
- Timer, watcher or log: none. `hooks/test_start_check.py` shows `start_check.py` `main` writes no log line on success. The crash line above is the only log write.
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
