# Every file the guard suite reads turns the guard flag on

## The rule

Source: owner, 22:48 CST, Nov 24, 2026, typed in the consultant's chat, on the guard test suite: "a blind opus agent to review, a refuter, and then land all the fixes that improve it in every aspect, speed, actual quality of checks, utiliziation of items, etc." The per-file rule below is one of those fixes.

- Only files the guard suite truly reads turn on `guard`, not whole folders. `truly_read_paths()` in `lint/test_guard_inputs.py` is that set: the import walk, `TRACED_READS`, `GUARD_READ_FILES` and `agents_folder_reads()`. It holds 207 files at b755fe1134.
- Agents: every top-level `agents/*.md` turns on `guard` and `checks_guard`, with no list entry. `role_agent_keys` in `hooks/guard.py` lists that folder. An edit to a nested `.md` file under `agents/` turns on neither: an empty arm in `.github/scripts/ci-scope.sh` takes it before the `agents/*.md` arm.
- `GUARD_READ_FILES` (`hooks/mutate_guard.py`) names `bin/sim-lease`, `merge/merge.py`, `actions/ci-alarm/events.json` and `actions/ci-alarm/clear_rule.py`. Each sets `guard` in its own arm in `.github/scripts/ci-scope.sh`.
- The import-closure files under the `GUARD_READ_FOLDERS` folders (`lint`, `janitor`, `skills`, `testing`) number 17 (`import_closure()`, `lint/test_guard_inputs.py`). `guard_read_paths()` returns 25, the union of those 17 and the 21 `TRACED_READS` files under the folders (13 are in both). The fifth case in `.github/scripts/ci-scope.sh` lists 15 files: 12 under the folders and 3 outside them (`bin/sim-test`, `merge/install_from_main.sh`, `docs/decisions/agent-model-cap.md`).
- `TRACED_READS` (`lint/test_guard_inputs.py`) names 203 files, 21 under the folders. It is a recorded trace, an strace of the twelve guard shards on Linux. Its currency is unmeasured.
- `GuardReadsTurnGuardOn` in `lint/test_guard_inputs.py` proves that each file of `truly_read_paths()` sets `guard` and `checks_guard` on its own edit, and that an unread `lint/` file or doc sets neither. It passes at b755fe1134.
- The case `Scope.test_every_guard_read_file_turns_on_the_guard_suite` in `lint/test_ci_scope.py` reads the list from the code with `ast`. Class `GuardReadsReader` tests that reader. It fails on a second assignment, an augmented or annotated assignment, a rebind at any depth, an item store, and a call to a mutating list method by name (`GUARD_MUTATORS`). Not caught: an alias, `getattr`, a call through the class (`list.append(GUARD_READ_FILES, x)`), or a method outside `GUARD_MUTATORS`. Forms no one writes by mistake are out of scope (rule `guard-guards-mistakes-only`: guards stop Claude's mistakes, not an attacker).

Mistake it stops: Claude edits a file the guard suite reads, CI skips the guard suite, and a broken guard read merges green. Harm: a guard that reads stale or broken input in every later session.

Consultant picks, not owner rulings:
- 04:46 CST Nov 25, 2026: `bin/sim-lease` sets `guard` too, with no exemption.
- 05:22 CST Nov 25, 2026: the list reader fails on the forms listed above.
- Per-file over folder, undoable (see Cost).

Cost, measured Nov 25, 2026 over merged PRs:
- A folder rule would start the guard suite on 7 of the last 57 merged PRs, about 120 job-minutes each (1 run measured). The read-files rule adds 0 for the import closure.
- Agents: the folder read adds a file to the set only when a top-level agents file is added, with no script edit. Each PR that edits one of the eleven traced docs (the ten `agents/*.md` files and `docs/decisions/agent-model-cap.md`) runs the guard suite: 3 of the last 60 merged PRs (#3885, #3886, #3900), counted over origin/main's first-parent merges at 10:28 CST.
- `bin/sim-test` and `merge/install_from_main.sh`: unmeasured.

Scope notes:
- An edit to `skills/impeccable/SKILL.md` alone sets `guard` and `checks_guard`, not `code`. On a ready pull request it runs the guard mutation test and the Windows slice of the guard fixture suite (`.github/guard-inputs.txt` lists the file). The Linux fixture shards (`checks-guard` to `checks-guard-4`) run too: their steps gate on `checks_guard`, which this edit sets.
- An edit to `actions/ci-alarm/events.json` or `actions/ci-alarm/clear_rule.py` sets `checks_windows_merge` (the Windows merge job), `code`, `guard` and `checks_guard`. `merge/merge.py` reads both (`ALARM_EVENTS`, `load_clear_rule`), and `merge/test_merge.py` imports it.

Kind: process
Home: .github/scripts/ci-scope.sh
