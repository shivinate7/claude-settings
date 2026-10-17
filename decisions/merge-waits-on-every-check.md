# The merge waits on every check, before and after the claim

## The ruling

1. **Check first, then claim.** Before `--confirm` pushes a claim, it reads the head's own
   checks with the same wait. Red or cancelled: nothing is claimed or pushed, and the lock is
   released. Pending: it waits, then claims only on green. The wait after the claim push
   stays. With nothing to claim and no records page to rebuild, the head is waited on once.
2. **Never merge while any check on the head is failing or running,** required or not (rule
   `git-never-merge-failing-ci`). The wait ends green only when every check has finished and
   none failed. A check name can repeat, such as one job in two workflows. Every entry
   counts, and one red entry ends the wait. A repo may list `merge.ignoreChecks`, each entry
   with a reason.

Reason: a claim push cancelled a run whose failure was already there, so the claim was reverted
twice (ruling 1). A merge ran while a non-required check was pending, and it went red after (ruling 2).

Kind: build
Plan: decisions/merge-waits-on-every-check.md#the-ruling (all)
Home: merge/merge.py

## Holes, named

- A workflow that GitHub has not created yet still reads as green. Debt `late-workflow-reads-green`.

## Related

- merge-needs-a-proven-head (a head with only skipped checks is unproven).
- ci-wait-reads-run-status (the wait reads status, never `gh run watch`).
- merge-config-defaults (the `merge.ignoreChecks` shape).
- records-index-at-merge (the wait after a records-page heal).
