# Every file the guard suite reads turns the guard flag on

## The ruling

Source: guard-suite audit (lane L8), under the owner's standing word on the guard test suite, 22:48 CST Nov 24, 2026.

- Every file in `GUARD_READ_FILES` (`hooks/mutate_guard.py`) turns the `guard` flag on in `.github/scripts/ci-scope.sh`. The list names `bin/sim-lease`, `merge/merge.py`, `actions/ci-alarm/events.json` and `actions/ci-alarm/clear_rule.py`. Folder reads (`GUARD_READ_FOLDERS`) are not part of this rule.
- The case `Scope.test_every_guard_read_file_turns_on_the_guard_suite` in `lint/test_ci_scope.py` reads the list from the code with `ast`. Class `GuardReadsReader` tests that reader. It fails on any form it cannot read whole: a second assignment, `+=`, an annotated assignment, or a rebinding or mutation of the name.

Mistake it stops: Claude edits a file the guard suite reads, CI skips the guard suite, and a broken guard read merges green. Harm: a guard that reads stale or broken input in every later session.

Consultant picks, not owner rulings:
- 04:46 CST Nov 25, 2026: `bin/sim-lease` sets `guard` too, with no exemption.
- 05:22 CST Nov 25, 2026: the list reader fails on a form it cannot read whole, as listed above.

Known gaps. Claims, round 1, unproven on a main run:
- A `janitor/*` edit sets no `guard`, though the guard copies read `janitor/`. Probe: run `ci-scope.sh` on a diff of one `janitor/` file and read `guard`. Claim: it is off.
- An `actions/ci-alarm/` edit sets no `checks_windows_merge`, though `merge/merge.py` loads those files. Probe: run `ci-scope.sh` on a diff of only `actions/ci-alarm/clear_rule.py` and read `checks_windows_merge`. Claim: it is off.

Kind: process
Home: .github/scripts/ci-scope.sh
