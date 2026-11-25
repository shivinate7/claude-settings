# Every file the guard suite reads turns the guard flag on

## The rule

Source: owner, 22:48 CST, Nov 24, 2026, typed in the consultant's chat, on the guard test suite: "a blind opus agent to review, a refuter, and then land all the fixes that improve it in every aspect, speed, actual quality of checks, utiliziation of items, etc." The per-file rule below is one of those fixes.

- Only files the guard suite truly reads turn on `guard`, not whole folders. `truly_read_paths()` in `lint/test_guard_inputs.py` is that set: the import walk, `TRACED_READS` and `GUARD_READ_FILES`.
- `GUARD_READ_FILES` (`hooks/mutate_guard.py`) names `bin/sim-lease`, `merge/merge.py`, `actions/ci-alarm/events.json` and `actions/ci-alarm/clear_rule.py`. Each sets `guard` in its own arm in `.github/scripts/ci-scope.sh`.
- The import-closure files under the `GUARD_READ_FOLDERS` folders (`lint`, `janitor`, `skills`, `testing`) are these twelve, in the script's fifth case: `janitor/sweep.py`, `janitor/temp_sweep.py`, `lint/_guard_sections.py`, `lint/check_record_slugs.py`, `lint/check_red_run.py`, `lint/check_skill_model_rows.py`, `lint/hook_catalog.py`, `lint/rule_audit.py`, `lint/ruled_store.py`, `lint/stale_cites.py`, `skills/impeccable/SKILL.md`, `testing/shallow_clone.py`. `guard_read_paths()` in `lint/test_guard_inputs.py` computes the closure and fails on a file the case misses.
- The fifth case also covers 13 `TRACED_READS` files (`lint/test_guard_inputs.py`). It lists them explicitly; no glob.
- `TRACED_READS` is a recorded trace, an strace of the twelve guard shards on Linux. Its currency is unmeasured.
- `GuardReadsTurnGuardOn` in `lint/test_guard_inputs.py` proves that each truly read file sets `guard` and `checks_guard` on its own edit, and that an unread `lint/` file or doc sets neither.
- The case `Scope.test_every_guard_read_file_turns_on_the_guard_suite` in `lint/test_ci_scope.py` reads the list from the code with `ast`. Class `GuardReadsReader` tests that reader. It fails on a second assignment, an augmented or annotated assignment, a rebind at any depth, an item store, and a call to a mutating list method by name (`GUARD_MUTATORS`). Not caught: an alias, `getattr`, a call through the class (`list.append(GUARD_READ_FILES, x)`), or a method outside `GUARD_MUTATORS`. Forms no one writes by mistake are out of scope (rule `guard-guards-mistakes-only`: guards stop Claude's mistakes, not an attacker).

Mistake it stops: Claude edits a file the guard suite reads, CI skips the guard suite, and a broken guard read merges green. Harm: a guard that reads stale or broken input in every later session.

Consultant picks, not owner rulings:
- 04:46 CST Nov 25, 2026: `bin/sim-lease` sets `guard` too, with no exemption.
- 05:22 CST Nov 25, 2026: the list reader fails on the forms listed above.
- Per-file over folder, undoable (see Cost).

Cost, measured Nov 25, 2026 over merged PRs:
- A folder rule would start the guard suite on 7 of the last 57 merged PRs, about 120 job-minutes each (1 run measured). The read-files rule adds 0 for the import closure.
- The eleven traced docs (the ten `agents/*.md` files and `docs/decisions/agent-model-cap.md` in the fifth case) add 1 of the last 60 merged PRs (#3885).
- `bin/sim-test` and `merge/install_from_main.sh`: unmeasured.

Scope notes:
- An edit to `skills/impeccable/SKILL.md` alone sets `guard` and `checks_guard`, not `code`. On a ready pull request it runs the guard mutation test and the Windows slice of the guard fixture suite (`.github/guard-inputs.txt` lists the file). The Linux fixture shards (`checks-guard` to `checks-guard-4`) run too: their steps gate on `checks_guard`, which this edit sets.
- An edit to `actions/ci-alarm/events.json` or `actions/ci-alarm/clear_rule.py` sets `checks_windows_merge` (the Windows merge job), `code`, `guard` and `checks_guard`. `merge/merge.py` reads both (`ALARM_EVENTS`, `load_clear_rule`), and `merge/test_merge.py` imports it.

Kind: process
Home: .github/scripts/ci-scope.sh
