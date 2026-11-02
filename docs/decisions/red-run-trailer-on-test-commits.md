# A commit that adds test lines carries the red run of those lines

## The ruling

`lint/check_red_run.py` is the one home. CI runs it on each pull request (step "Red-run trailer" in `checks.yml`), with `BASE_SHA` set to the PR base. The test-author runs `python3 ~/.claude/lint/check_red_run.py --base origin/main` before it pushes, in whatever repo it works in (`agents/test-author.md`).

1. It reads each non-merge commit in `<base>..HEAD`. A commit that adds lines to a test path needs a trailer in its message: `Red-run: <command> -> <N> failed on <sha>` (N is 1 or more, sha is 7 or more hex digits), or `Red-run: none: <reason>`.
2. A test path is what `is_test_rel` in `hooks/guard.py` judges. The check imports it and keeps no copy.
3. `Red-run: none: <reason>` is for a change that adds no new claim, such as a re-pointed fixture. A reviewer reads each reason, because a junk reason passes.
4. A commit that only deletes test lines needs no trailer. A merge is not judged; the commits it brings in are.
5. Rollout: when the tree at HEAD holds `lint/check_red_run.py`, a commit whose parent tree has no such file is not judged. The commits from before the check landed stay as they are. The check reads this with `git ls-tree HEAD`, never from disk. In a repo whose HEAD has no such file, each non-merge, non-revert commit in the range is judged.
6. The check reads the repo it runs in: the current directory, or the folder `--root <dir>` names. It imports `is_test_rel` from its own install (`../hooks/guard.py` beside the script), never from the repo it reads. Other repos get the check from the installed copy at `~/.claude/lint/check_red_run.py` now. Their CI runs it later, through a separate lane. This repo's CI step stays as it is.
7. A commit whose message has git's `This reverts commit <sha>.` line is not judged. Its lines were judged once already, when the commit it reverts landed.
8. A range git cannot read, or a run with no base, prints UNKNOWN and exits 2. It never exits 0, locally or in CI. This differs from the shape in `ci-unknown-is-red`, where an unknown read exits 0 locally and non-zero only when env `CI` is set.

Why: the plan found 17 red runs recorded for 29 test changes (`docs/plans/test-ci-standard.md`, standard S5, step 2). A test that was never seen red on the old code may not be able to fail. `agents/test-author.md` names the trailer as the record of the run.

Known limits:

- The check reads that a run is claimed, not that it ran. A reviewer re-runs a claim only when the claim is in doubt (`roles-each-layer-proves-once`).
- A pure rename of a test file reads as a delete and an add, so it needs `Red-run: none: <reason>`.
- A branch that merged a newer main carries main's commits in the range, and each is judged like the rest.
- A lane begun before the check landed escapes for its commits from before that, unless it is rebased.
- Conflict-resolution lines in a merge commit are not judged.
- Mutation tests are not test paths, so they need no trailer.
- The check path is fixed in the check. Renaming the check turns it off.
- In a repo whose HEAD has no `lint/check_red_run.py`, a range that reaches back past the repo's first trailered test commit judges old commits too (item 5). The test-author's `--base origin/main` keeps the range to its own lane.

Risk kind: likely risk, per `building-guard-needs-incident`. Test-author work adds new tests in normal work, and 12 of 29 recorded changes carried no red run. Landed 2026-11-01.

Cost: no long-lived process, no log, no timer. One python process per run, once per pull request run and once per test-author push. It starts these git children. One `rev-parse` and one `log` read the range, and one `ls-tree` reads HEAD. Each non-revert commit in the range then costs one `diff`. When HEAD holds the check, each also costs one `ls-tree` first, and the `diff` runs only when the parent tree holds the check.

Kind: process
Home: lint/check_red_run.py
