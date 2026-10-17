# The merge follows the pull request's own base

## The ruling

`<base>` is the pull request's own base, read from `gh`.

1. `<base>` drives every step: the claim, the lock, the required checks, the silent-undo
   check and the local fast-forward.
2. The claim runs only when `<base>` is the default branch. For any other base, records stay
   `id: pending`, and the preview says so. The pull request that takes that base into the
   default branch claims them.
3. `merge --unlock [<branch>]` removes the lock of `<branch>`. With no branch, it removes the
   lock of the default branch.
4. The head can hold a `Record-claim` commit while `<base>` is not the default branch. Then
   the run stops before the wait. It names that commit to revert.
5. Each pass of the wait reads the base. A changed base ends the wait.

Reason: a PR into a non-default base claimed a record number against main's, so the next claim on main took the same number.

Kind: build
Plan: decisions/merge-follows-the-prs-base.md#the-ruling (all)
Home: merge/merge.py

## Holes, named

- A base that changes after the last pass of the wait and before `gh pr merge` is not caught.
  Deferred item `merge-retarget-before-merge`.
