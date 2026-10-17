# The merge waits on every check, before and after the claim

## The question

Which checks must be done, and in what order, before the merge tool pushes a claim and before
it merges?

## The ruling

Settled by the owner, written down 2026-10-01.

1. **Check first, then claim.** Before `--confirm` pushes a claim, it reads the head's own
   checks with the same wait. Red or cancelled: nothing is claimed or pushed, and the lock is
   released. Pending: it waits, then claims only on green. The wait after the claim push
   stays. With nothing to claim and no records page to rebuild, the head is waited on once.
2. **Never merge while any check on the head is failing or running,** required or not (rule
   `git-never-merge-failing-ci`). The wait ends green only when every check has finished and
   none failed. A check name can repeat, such as one job in two workflows. Every entry
   counts, and one red entry ends the wait. A repo may list `merge.ignoreChecks`, each entry
   with a reason.

Kind: build
Plan: decisions/merge-waits-on-every-check.md#the-ruling (all)
Home: merge/merge.py

## Why

- Banchi #595: a claim push cancelled a run whose failure was already there, and the claim
  was reverted twice. Ruling 1 follows.
- Banchi #604: the merge ran while a non-required check was pending, and the check went red
  after the merge. Ruling 2 follows.

## Related

- Decision merge-needs-a-proven-head (a head with only skipped checks is unproven).
- Decision ci-wait-reads-run-status (the wait reads status, never `gh run watch`).
- Decision merge-config-defaults (the `merge.ignoreChecks` shape).
- Decision records-index-at-merge (the wait after a records-page heal).
