# A stash push is clone-wide, not lane-wide

## The ruling

`git stash push`, `save` and a bare `git stash` deny in every tree, worktree or not. The TAKE arm (`pop`,
`drop`, `clear`, `apply`, `branch`) already denies in every tree. The guard no longer runs the
`is_worktree` check for this arm. The read that decides whether the call would discard anything is
unchanged. `stash_subject` checks the WORKING TREE for this arm, so a push over a clean tree still
passes, because it takes nothing. Once the tree is dirty enough to be taken, the call denies.

Reason: the worktree "ask" is earned by its argument that the loss is limited to this lane. That holds
for `reset --hard`, `restore` and `checkout <path>`, which touch the worktree's own tree. It is false for
a push. A push writes an entry to `refs/stash`, which lives in the common git directory. The primary
checkout and every linked worktree share that one-entry-wide slot. An "ask" also has no human behind it
in a fanned-out worker. A worker briefed to "set work aside" reads the ask as permission, against the
rule "never a stash".

`stash_takes_the_stack` already names the TAKE arm's subject as clone-wide. The three actions stay grouped
as PUT versus TAKE versus READ. Only the tree that each judgment consults changes for PUT. The discard
side of the shared-tree rule (named files in a linked worktree, the discard forms, the worktree remove)
is in `agent-worktree-discard-is-noted`.

Kind: process
Home: hooks/guard_shared_tree.py
