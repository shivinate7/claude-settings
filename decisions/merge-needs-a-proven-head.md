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
  counts; gh lists runs newest first. An older cancelled run under a newer pass of the
  same name is superseded. A newest cancelled run stays red. Incident 2026-10-12 17:05Z:
  a draft PR made ready in the same second got two runs, and the skipped `opened` run
  carried the higher id, so the green `ready_for_review` run was outranked and #360 was
  refused.
- A skipped job beside a passing check still reads as passing. A docs-only PR, with
  `scope` passed and the code suites skipped, stays green (decision
  docs-only-prs-skip-code-suites).

## What protects it

`merge/test_merge.py`, class `GhHalf`: thirteen cases added 2026-10-12 over two rounds,
nine of them red first. The re-pointed `test_a_required_check_that_is_skipped_reads_green`
now carries a passing `scope` entry beside the skipped one.

## Holes, named

Three review rounds, 2026-10-12. Round 1 found two defects: the all-skipped red fired
while a check was pending, and the dedup hid an older run still in progress. Round 2
closed both. Round 3 found the rest, named here under the owner's three-round cap.

- The race itself stays. Mark a PR ready only after its push run exists, or dispatch the
  workflow by hand. The tool refuses now; it does not dispatch.
- Any passing check licenses a skipped required job, not only `scope`. The tool does not
  check which check passed.
- An older failure under a newer pass of the same name is superseded, like a cancelled one.
- `neutral` reads red in `classify` and green in `judge_runs`. Pre-existing split.
- A passing check beside runs that all skipped reads red, with no remedy. Rare: it needs a
  newest run that skipped under a check that passed.
- A required name with no entry beside skipped runs holds the wait to the deadline, with no
  remedy.
- The preview (`head_state`) prints a literal `<branch>`; the wait and the read name the
  real branch.
- Two workflow files with one `name` share one dedup slot; a job-level failure still reaches
  `classify`.
- Pre-existing: with no required names, zero checks and zero runs, the wait reads green
  after its 30 s settle, while the read says pending.
- "Newest" follows gh's order among the runs that ran, not a timestamp. A skipped run never
  outranks a run that ran, whatever its position.
