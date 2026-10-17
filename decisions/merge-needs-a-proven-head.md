# A merge needs a proven head

## The ruling

Required checks on main cannot close this: GitHub counts a skipped job as passing.

- A head is proven only when at least one check on it passed. A head whose checks all read
  "skipping", with none pending, is unproven. `classify` returns it as red. The refusal names the
  remedy: `gh workflow run gates.yml --ref <branch>`, or a new push after `gh pr ready`.
- A run list where every run completed as skipped, with none pending, is red for the same reason.
- A skipped run never outranks a run of the same name that ran. It is dropped when any other run of
  that name is not skipped. Then only the newest run per workflow name counts; gh lists runs newest
  first.
- A cancelled run never outranks a run of the same name that ran, completed or in progress, in
  either list order. A cancelled run with no other run of its name stays red. A newer skipped run
  does not erase an older cancelled run.
- A skipped job beside a passing check still reads as passing. A docs-only PR, with `scope` passed
  and the code suites skipped, stays green (docs-only-prs-skip-code-suites).

Reason: `bin/merge` merged a head whose every check said "skipping", and it refused a green head
because a cancelled run outranked a passing run of the same name.

Kind: process
Home: merge/merge.py

## Holes, named

Debts: `merge-head-race-remains` (the push-to-ready race stays), `merge-head-any-check-licenses`,
`merge-head-neutral-split`, `merge-head-wait-no-remedy`, `merge-head-preview-wrong`,
`merge-head-shared-name-slot`, `merge-head-empty-reads-green`.

## Named limits

- An older failure under a newer pass of the same name is superseded, as a cancelled run is.
- "Newest" follows gh's order among the runs that ran, not a timestamp.
