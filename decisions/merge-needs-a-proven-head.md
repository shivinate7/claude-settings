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
- A skipped run never outranks a run of the same name that ran. It is dropped when any
  other run of that name is not skipped. Then only the newest run per workflow name
  counts; gh lists runs newest first. Incident 2026-10-12 17:05Z:
  a draft PR made ready in the same second got two runs. The skipped `opened` run carried
  the higher id. It outranked the green `ready_for_review` run, and #360 was refused.
- A cancelled run never outranks a run of the same name that ran, completed or in
  progress, in either list order. Owner, 2026-10-13. A cancelled run with no other run of
  its name stays red. A newer skipped run does not erase an older cancelled run.
  Incident 2026-10-13, PR 381: two gates runs started in the same second. Concurrency
  cancelled one. `judge_runs` kept the first listed run per name, so the cancelled run
  read red and the wait stopped while the other run was still going.
- A skipped job beside a passing check still reads as passing. A docs-only PR, with
  `scope` passed and the code suites skipped, stays green (decision
  docs-only-prs-skip-code-suites).

## What protects it

`merge/test_merge.py`, class `GhHalf`: thirteen cases added 2026-10-12 over two rounds,
nine of them red first. The re-pointed `test_a_required_check_that_is_skipped_reads_green`
now carries a passing `scope` entry beside the skipped one.

## Holes, named

Debts: `merge-head-race-remains` (the push-to-ready race stays), `merge-head-any-check-licenses` (any passing check licenses a skipped required job), `merge-head-neutral-split` (`neutral` reads red in `classify` and green in `judge_runs`), `merge-head-wait-no-remedy` (some red and waiting states give no remedy), `merge-head-preview-wrong` (the preview disagrees with the wait), `merge-head-shared-name-slot` (two workflow files with one name share a dedup slot), `merge-head-empty-reads-green` (the wait reads green with no checks and no runs).

## Named limits

- An older failure under a newer pass of the same name is superseded, as a cancelled run is.
- "Newest" follows gh's order among the runs that ran, not a timestamp. A skipped run never outranks a run that ran.

Kind: process
Home: merge/merge.py
