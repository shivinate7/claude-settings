# Every file the guard suite reads turns the guard flag on

## The rule

Source: owner, 22:48 CST, Nov 24, 2026, typed in the consultant's chat, on the guard test suite: "a blind opus agent to review, a refuter, and then land all the fixes that improve it in every aspect, speed, actual quality of checks, utiliziation of items, etc." This change is one of those fixes, on branch `ci-scope-guard-reads`.

- Every file in `GUARD_READ_FILES` (`hooks/mutate_guard.py`) turns the `guard` flag on in `.github/scripts/ci-scope.sh`. The list names `bin/sim-lease`, `merge/merge.py`, `actions/ci-alarm/events.json` and `actions/ci-alarm/clear_rule.py`. Folder reads (`GUARD_READ_FOLDERS`) are not part of this rule.
- The case `Scope.test_every_guard_read_file_turns_on_the_guard_suite` in `lint/test_ci_scope.py` reads the list from the code with `ast`. Class `GuardReadsReader` tests that reader. It fails on a second assignment, an augmented or annotated assignment, a rebind at any depth, an item store, and a call to a mutating list method by name (`GUARD_MUTATORS`). Not caught: an alias, `getattr`, a call through the class (`list.append(GUARD_READ_FILES, x)`), or a method outside `GUARD_MUTATORS`. Forms no one writes by mistake are out of scope (`guard-guards-mistakes-only`).

Mistake it stops: Claude edits a file the guard suite reads, CI skips the guard suite, and a broken guard read merges green. Harm: a guard that reads stale or broken input in every later session.

Consultant picks, not owner rulings:
- 04:46 CST Nov 25, 2026: `bin/sim-lease` sets `guard` too, with no exemption.
- 05:22 CST Nov 25, 2026: the list reader fails on the forms listed above.

Known gaps, still open:
- An edit to an existing `janitor/` file leaves `guard` off, though the guard copies read `janitor/`. Probe: `run(..., existing=[path])` with `path` `janitor/sweep.py` leaves `guard` false. A new file sets every flag.
- An edit to an existing `actions/ci-alarm/` file leaves `checks_windows_merge` off, though `merge/merge.py` loads those files. Probe: `run(..., existing=[path])` with `path` `actions/ci-alarm/clear_rule.py` leaves `checks_windows_merge` false.

Kind: process
Home: .github/scripts/ci-scope.sh
