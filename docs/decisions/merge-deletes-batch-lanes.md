# A merge deletes its own branch only

## The ruling

Owner pick A for R42 part 2 (per-lane merge). Each merge deletes only the merged pull request's own branch. A branch that the merged head brought in is another lane's, and stays.

The local side follows the same rule. Roadmap step c44 (owner, 2026-10-25) gave the local cleanup; it now covers the pull request's own branch only.

Outcome protected: origin keeps no merged branch that a later session could read as open work.

## The design

Built in `merge/merge.py`. After the merge, when `merge.deleteBranch` is true (an absent key reads as false, so nothing is deleted):

- `cut_branch` deletes the pull request's head branch on origin. It prints one line: deleted, already deleted, or not deleted with git's last line. It never fails the merge.
- `cut_local` runs next. It deletes the local branch only when its tip is an ancestor of the merged head. A tip outside it holds local-only commits, and stays with one line. A worktree that holds the branch goes first when the sweep's `--fast` judgment says reap (`remove_held_tree`). No `--force`.
- Nothing else is deleted. The tool reads no lane tips, no open pull requests and no lane set.
- `merge.keepBranches` is checked for shape only. The own-branch delete does not read it (debt `long-lived-head-lost-in-batch`).

Kind: process
Home: merge/merge.py

## Safety holes, named

- (a) A long-lived branch merged as its own pull request loses its name. Its commits stay on main; restoring it is one push. Debt: `long-lived-head-lost-in-batch`.
- (b) A squash-merged pull request keeps its local branch, because its tip is not an ancestor of the squash commit. Its origin branch is deleted. Debt: `squash-lane-branch-kept`.
- (c) A merge tool older than this change refuses main's stamp.json (unknown field `keepBranches`) with a clear stop. `merge/install_from_main.sh` fixes it. Debt: `old-merge-tool-refuses-stamp`.
