# A merge needs a proven head

## The ruling

Required checks on main cannot close this: GitHub counts a skipped job as passing.

- A head is proven only when at least one check on it passed. A head whose checks all read "skipping", with none pending, is
  unproven. `classify` returns it as red. The refusal names the remedy: `gh workflow run gates.yml --ref <branch>`, or a new push
  after `gh pr ready`.
- A run list where every run completed as skipped, with none pending, is red for the same reason.
- A skipped run never outranks a run of the same name that ran. It is dropped when any other run of that name is not skipped. Then
  only the newest run per workflow name counts. "Newest" follows gh's order (newest first) among the runs that ran, not a
  timestamp, so an older failure under a newer pass of the same name is superseded.
- A cancelled run never outranks a run of the same name that ran, completed or in progress, in either list order. A cancelled run
  with no other run of its name stays red. A newer skipped run does not erase an older cancelled run.
- A skipped job beside a passing check still reads as passing. A docs-only PR, with `scope` passed and the code suites skipped,
  stays green.

Reason: `bin/merge` merged a head whose every check said "skipping", and it refused a green head because a cancelled run
outranked a passing run of the same name.

Kind: process
Home: merge/merge.py
