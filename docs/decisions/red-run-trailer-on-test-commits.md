# A commit that adds test lines carries the red run of those lines

## The ruling

`lint/check_red_run.py` is the one home. CI runs it on each pull request (step "Red-run trailer" in `checks.yml`), with `BASE_SHA` set to the PR base. A lane runs it with `--base origin/main`.

1. It reads each non-merge commit in `<base>..HEAD`. A commit that adds lines to a test path needs a trailer in its message: `Red-run: <command> -> <N> failed on <sha>` (N is 1 or more, sha is 7 or more hex digits), or `Red-run: none: <reason>`.
2. A test path is what `is_test_rel` in `hooks/guard.py` judges. The check imports it and keeps no copy.
3. `Red-run: none: <reason>` is for a change that adds no new claim, such as a re-pointed fixture. A reviewer reads each reason, because a junk reason passes.
4. A commit that only deletes test lines needs no trailer. A merge is not judged; the commits it brings in are.
5. A commit whose parent tree has no `lint/check_red_run.py` is not judged. The commits from before the check landed stay as they are.
6. A range git cannot read, or a run with no base, prints UNKNOWN and exits 2. It never exits 0. Locally and in CI the answer is the same (`ci-unknown-is-red` sets the CI half).

Why: the plan found 17 red runs recorded for 29 test changes (`docs/plans/test-ci-standard.md`, standard S5, step 2). A test that was never seen red on the old code may not be able to fail. `agents/test-author.md` names the trailer as the record of the run.

Known limits:

- The check reads that a run is claimed, not that it ran. A reviewer re-runs a claim only when the claim is in doubt (`roles-each-layer-proves-once`).
- A pure rename of a test file reads as a delete and an add, so it needs `Red-run: none: <reason>`.
- A branch that merged a newer main carries main's commits in the range, and each is judged like the rest.

Risk kind: likely risk, per `building-guard-needs-incident`. Test-author work adds new tests in normal work, and 12 of 29 recorded changes carried no red run. Landed 2026-11-01.

Cost: no new process, no log, no timer. One `git log` read and one `git diff` read per commit in the range, once per pull request run.

Kind: process
Home: lint/check_red_run.py
