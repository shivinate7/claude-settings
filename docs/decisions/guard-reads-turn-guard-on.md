# Every file the guard suite reads turns the guard flag on

## The rule

Source: owner, 22:48 CST, Nov 24, 2026, typed in the consultant's chat, on the guard test suite: "a blind opus agent to review, a refuter, and then land all the fixes that improve it in every aspect, speed, actual quality of checks, utiliziation of items, etc." The per-file rule below is one of those fixes.

- The rule is per file, not per folder. The `guard` flag turns on for each file the guard suite truly reads: the files of `GUARD_READ_FILES` (`hooks/mutate_guard.py`: `bin/sim-lease`, `merge/merge.py`, `actions/ci-alarm/events.json`, `actions/ci-alarm/clear_rule.py`), and each file under the `GUARD_READ_FOLDERS` folders (`lint`, `janitor`, `skills`, `testing`) that the suite's import closure or `TRACED_READS` names. Each has its own arm or case in `.github/scripts/ci-scope.sh`.
- Twelve files set `guard` in the script's new case and left it off on main: `janitor/sweep.py`, `janitor/temp_sweep.py`, `lint/_guard_sections.py`, `lint/check_record_slugs.py`, `lint/check_red_run.py`, `lint/check_skill_model_rows.py`, `lint/hook_catalog.py`, `lint/rule_audit.py`, `lint/ruled_store.py`, `lint/stale_cites.py`, `skills/impeccable/SKILL.md`, `testing/shallow_clone.py`.
- The case list in the script is a copy. `lint/test_guard_inputs.py` (class `GuardReadsTurnGuardOn`) runs the script once per read path under those folders, and once for a control that must leave `guard` off. The read paths come from the import closure plus `TRACED_READS`.
- `TRACED_READS` is a recorded trace, an strace of the twelve guard shards on Linux. Its currency is unmeasured.
- The case `Scope.test_every_guard_read_file_turns_on_the_guard_suite` in `lint/test_ci_scope.py` reads the list from the code with `ast`. Class `GuardReadsReader` tests that reader. It fails on a second assignment, an augmented or annotated assignment, a rebind at any depth, an item store, and a call to a mutating list method by name (`GUARD_MUTATORS`). Not caught: an alias, `getattr`, a call through the class (`list.append(GUARD_READ_FILES, x)`), or a method outside `GUARD_MUTATORS`. Forms no one writes by mistake are out of scope (rule `guard-guards-mistakes-only`: guards stop Claude's mistakes, not an attacker).

Mistake it stops: Claude edits a file the guard suite reads, CI skips the guard suite, and a broken guard read merges green. Harm: a guard that reads stale or broken input in every later session.

Consultant picks, not owner rulings:
- 04:46 CST Nov 25, 2026: `bin/sim-lease` sets `guard` too, with no exemption.
- 05:22 CST Nov 25, 2026: the list reader fails on the forms listed above.
- Per-file over folder, undoable: a folder rule would start the guard suite on 7 of the last 57 merged PRs at about 120 job-minutes each (1 run measured); the per-file rule on none of them.

Scope notes:
- An edit to `skills/impeccable/SKILL.md` alone sets `guard`, not `code`. On a ready pull request it runs the guard mutation test and the Windows slice of the guard fixture suite. The Linux fixture shards (`checks-guard` to `checks-guard-4`) do not run: they gate on `checks_guard`, which needs `code` and `guard`.
- An edit to `actions/ci-alarm/events.json` or `actions/ci-alarm/clear_rule.py` sets `checks_windows_merge` (the Windows merge job), `code` and `guard`. `merge/test_merge.py` reads both.

Kind: process
Home: .github/scripts/ci-scope.sh
