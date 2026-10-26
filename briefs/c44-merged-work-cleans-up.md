# c44. Merged work leaves no worktrees or branches behind

Paste this whole file into a claude-settings session (Windows; the Mac holds main only). Written by
the advisor, Oct 26, against main f463787. Owner agreed Oct 25.

## Why

Mac session, Oct 25: after the ios-ship and guard-cull PRs merged, their worktrees and local
branches stayed. The merge tool deletes the remote branch, keeps a local branch a worktree has
checked out, and never removes worktrees. The Agent tool locks a builder's worktree with the host
session's pid, and the sweep frees such a lock only when that pid is dead, so a merged tree waits
for the session to end. Cleaning by hand cost several guard refusals and left a throwaway branch
the owner had to delete.

## First check

Read decisions when-a-worktree-may-be-removed and the-janitor-is-one-machine-wide-sweep, and the
merge tool's docstring. If "the merge tool never removes worktrees" has a recorded reason, bring it
to the advisor with this brief's lanes before building (rule outcomes-stale-decision-protocol).

## Lane 1, the merge tool cleans its own branch

After a merge succeeds, the merge tool removes the merged branch's worktree when it is clean and its
HEAD is in the default branch, by calling the sweep's existing --fast removal for that one tree (one
home; no second removal path). Then it deletes the local branch, as it does today when no worktree
holds it. A dirty tree, an unmerged HEAD, the caller's own cwd, or any unread fact keeps the tree and
prints one line saying why.

## Lane 2, the sweep frees the caller's own lock on a finished agent's tree

The sweep may free an Agent-tool lock whose pid is the calling session's own process, only when the
tree is clean, its HEAD is in the default branch, and no live process stands in it. Every other lock
stays as today.

## Lane 3, the offer

One sentence in the reports rule's home: when a session's last PR has merged and no lane is open, its
final report offers `python3 ~/.claude/janitor/sweep.py --root <repo> --attended --fast` (preview, then
--confirm) as one command, unless lanes 1 and 2 left nothing to remove.

## Proof

test-author, red on main: a merged clean worktree survives a merge today and is gone after lane 1;
a dirty one and an unmerged one stay; a tree locked by the caller's own pid, clean and merged, is
freed by lane 2, and one locked by another live pid stays. Builder makes them green. A reviewer reads
the diff (it changes what a deletion tool removes). Usual merge rules.
