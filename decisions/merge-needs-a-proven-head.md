# A merge needs a proven head

## The question

When has a head enough CI behind it for `bin/merge` to merge it?

## The incident

MEASURED 2026-10-12 07:22Z. `bin/merge 352` merged head f18b6d9 while every check on it
said "skipping". The push and `gh pr ready` landed two seconds apart. The synchronize run
(38216941352) read the PR as a draft and skipped every job. The ready run (38216938408)
landed on the older head 3f4437e. `merge/merge.py` read `skipped` as a pass in `judge_runs`
and `skipping` as a pass in `classify`, so the head looked green. The code was proven only
by luck: the older head's run passed, and the newer head added one Markdown commit.

Required checks on main cannot close this hole. GitHub counts a skipped job as passing.

Second defect, same file, found 2026-10-11. `judge_runs` counted a cancelled run as red
after a later run with the same name passed on the same head. The merge then refused a
green head.

## The ruling

Owner, 2026-10-12: "Fix both now, one lane."

- A head is proven only when at least one check on it passed. A head whose checks all
  read "skipping", with none pending, is unproven. `classify` returns it as red. The
  refusal names the remedy: `gh workflow run gates.yml --ref <branch>`, or a new push
  after `gh pr ready`.
- A run list where every run completed as skipped, with none pending, is red for the
  same reason.
- Only the newest run per workflow name counts. gh lists runs newest first. An older
  cancelled run under a newer pass of the same name is superseded. A newest cancelled
  run stays red.
- A skipped job beside a passing check still reads as passing. A docs-only PR, with
  `scope` passed and the code suites skipped, stays green (decision
  docs-only-prs-skip-code-suites).

## What protects it

`merge/test_merge.py`, class `GhHalf`: eight cases added 2026-10-12, four of them red on
the old reader. The re-pointed `test_a_required_check_that_is_skipped_reads_green` now
carries a passing `scope` entry beside the skipped one.

## Holes, named

- The race itself stays. Mark a PR ready only after its push run exists, or dispatch the
  workflow by hand. The tool refuses now; it does not dispatch.
- A head with one passing check and a skipped required job still reads green. The
  `scope` job decides which jobs skip, so a passing `scope` check is the proof that a
  skip is intended. The tool does not check that the passing check is `scope`.
- "Newest" follows gh's order, not a timestamp.
