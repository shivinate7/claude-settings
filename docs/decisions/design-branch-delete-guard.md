# A branch delete keeps the design file it holds

## The ruling

Rule `shared-trees-archive-then-delete`: a delete never removes the only copy of a design file.

Incident, repo degen, 2026-11-03: an unmerged branch was deleted, and the owner's picked mockup `docs/design/jd-deferred.html` was lost with it.

Code: `guard_branch_worktree.design_push_delete_verdict` (remote delete) and `design_branch_delete_ask` (local delete). Tests: family `branch-worktree` in `hooks/test_guard.py`.

Kind: build
Plan: docs/decisions/design-branch-delete-guard.md#the-ruling (all)
Home: hooks/guard_branch_worktree.py

### A remote delete

`git push origin --delete <b>` and `git push origin :<b>` remove origin's copy. The guard reads the branch tip: the remote-tracking ref, else the local branch. It denies the delete when all of these hold:

- The tip is not an ancestor of origin's default branch.
- The tip holds a file under the layout's `design` folder that the default branch lacks.
- No `archive/*` ref on origin holds the tip. Any archive name counts, not only `archive/<b>`, because the rule allows a new archive name when the first is taken.

It asks, never allows, when a read cannot answer: no tip resolves (no tracking ref, no local branch, or a name such as `$B`), the design-file read fails, the archive-ref read fails, or the default branch is unreadable.

### A local delete

`git branch -d/-D` leaves origin's copy. It stays allowed while any origin ref holds the tip. It asks only when its subject read is already unreadable (the default branch cannot be read), the tip holds a design file, and no origin ref holds the tip.

## Cost

A call that deletes nothing runs none of this.

A remote delete of one design branch, with the remote named in the command, measured 10 git starts. The push verdict takes 3 (the reviewer's count). The design check takes 7, measured here: tip lookup 1, default-branch read 2, ancestor read 2, design-file read 1, archive-ref read 1. The ancestor read is 1 start when it answers "yes": the shallow-clone probe runs only on "no", and a "yes" ends the check. A name with no tip costs 2 starts, because the default branch is read at the first tip that resolves. A local delete adds nothing unless its subject read is unreadable.

## Known limits

- The tip is the last-fetched tracking ref, not origin's live tip. A commit pushed to the branch after this clone's last fetch is not read, so a design file on it is not judged. Lane ruling, 2026-11-03 18:55 CST: accepted. An `ls-remote` per delete costs a network call and more than it saves.
- A plain name that is a tag, `git push origin --delete <tag>`, has no branch tip, so it asks. A `refs/tags/` spelling is skipped.
- A local-only design branch is refused by the only-copy rule (`shared-tree`), not by this one.
