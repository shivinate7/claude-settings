# A branch is redundant by patch, not by ancestry

## The ruling

The sweep (`the-janitor-is-one-machine-wide-sweep`, the janitor is one machine-wide sweep) reaps a local branch when the branch is an ancestor of the base, or when `git cherry <base> <branch>` prints no `+`. It keeps the branch, and names it as the only copy, when a `+` survives and no remote ref contains it.

Why: `git merge-base --is-ancestor` reads commit ids, and a rebase writes new ids for the same patch, so ancestry holds work that nobody can lose. `git cherry` compares patch ids. The direction is safe: an altered commit prints `+` and is kept, and a false `-` needs two identical patches, so the content already sits on the base.

Limit: a squash merge writes one new patch id, so `git cherry` still prints `+`. The known fix runs `git cherry` against a synthetic commit from `git commit-tree <tree> -p <base>`. The sweep does not ship it, because no branch of that shape exists to prove it.

Protected by the rebase-ghost fixture in `janitor/test_sweep.py`, which goes red against a sweep that tests ancestry alone.

Kind: process
Home: janitor/sweep.py
