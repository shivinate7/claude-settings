# A branch is redundant by patch, not by ancestry

The sweep in `plans/janitor-build-plan.md` keeps or reaps a local branch. This
entry records the test it uses, and the measurement behind it.

## The defect in the older rule

A sibling repository runs a sweep with one test:

    git merge-base --is-ancestor <branch> <base>

That test reads commit ids. A rebase writes new commit ids for the same patch.
The test then goes false while the same patch sits on the base branch. The
sweep holds the branch, and it reports work that nobody can lose.

## The rule

`git cherry <base> <branch>` compares patch ids. A commit already on the base
prints `-`. A new commit prints `+`.

The sweep reaps a branch when the branch is an ancestor of the base, OR when
`git cherry` prints no `+`. The sweep keeps the branch, and names it as the
only copy, when a `+` survives and no remote ref contains it.

## Why the direction is safe

A rebase can alter a commit. An altered commit prints `+`, so the sweep keeps
it. A kept branch is the safe error.

A false `-` needs two identical patches. Two identical patches mean that the
content really sits on the base. The delete then costs nothing.

## The measurement

Taken on 2026-09-20, across the five repositories under `~/Developer`. Of 98
local branches, the ancestry test reaps 46. The patch test reaps 5 more. One of
those 5 carries 47 commits, and `git cherry` marks every one of them `-`.

Six branches hold the only copy of their work. The sweep keeps all six and
names them.

## The gap this entry does not close

A squash merge writes one new patch id, so `git cherry` still prints `+`. The
known fix builds a synthetic commit with `git commit-tree <tree> -p <base>`,
and runs `git cherry` against that commit.

This machine holds no branch of that shape today. The measurement found zero.
A rule that ships without a subject is a rule nobody sees work, so the sweep
does not ship this test. The suite carries a fixture that proves the gap, so
the record holds it.

## The mechanism

`janitor/test_sweep.py` holds the rebase-ghost fixture. That fixture goes red
against a sweep that tests ancestry alone.
