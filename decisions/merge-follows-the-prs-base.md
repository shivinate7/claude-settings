# The merge follows the pull request's own base

## The question

A pull request can target a branch that is not the default branch. Which branch do the steps
of the merge tool use, and when does the tool claim record numbers?

## The ruling

Settled by the owner, written down 2026-10-07. `<base>` is the pull request's own base, read
from `gh`.

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

Kind: build
Plan: decisions/merge-follows-the-prs-base.md#the-ruling (all)
Home: merge/merge.py

## Why

Incident: q_max #497 merged into `claude/speed-wave-2` and claimed D-720 against main's
D-719. The next claim on main would take D-720 too.

## Holes, named

- A base that changes after the last pass of the wait and before `gh pr merge` is not caught.
  Deferred item `merge-retarget-before-merge` (a base change just before the merge command).

## Proof

Cases are in `merge/test_merge.py`, class `BaseAware`.
