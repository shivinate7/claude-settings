# A branch delete keeps the design file it holds

## The ruling

Rule `shared-trees-archive-then-delete`: a delete never removes the only copy of a design file.

Incident, repo degen, 2026-11-03: an unmerged branch was deleted, and the owner's picked mockup `docs/design/jd-deferred.html` was lost with it.

Code: `guard_branch_worktree.design_push_delete_verdict` (remote delete) and `design_branch_delete_ask` (local delete). Tests: family `branch-worktree` in `hooks/test_guard.py`.

Kind: build
Plan: docs/decisions/design-branch-delete-guard.md#the-ruling (all)
Home: hooks/guard_branch_worktree.py

### A remote delete

`git push origin --delete <b>` and `git push origin :<b>` remove origin's copy. Origin only, tags skipped: a delete pushed to another remote keeps the other push rules, and a name that is only a local tag is not judged. The guard reads the branch tip: the remote-tracking ref, else the local branch. It refuses the delete when all of these hold:

- The tip is not an ancestor of origin's default branch.
- The branch added or changed a file under the layout's `design` folder since its merge base with the default branch (`base...tip`). The file's bytes at the tip must differ from the default branch's. A mockup the branch modified counts as the only copy, as an added one does. A file the branch never touched does not count, even when the default branch edited, deleted or renamed it after the fork. A file whose bytes the default branch holds does not count. No merge base (a shallow clone, unrelated history) fails the read, so the delete asks. The folder is read from the repo root, so the cwd does not matter.
- No other ref under `refs/remotes/origin` holds the tip. Any name counts, not only `archive/*`, because the rule allows a new archive name when the first is taken. `<remote>/HEAD` never counts. Every branch the whole command deletes on that remote, from this checkout, is no holder: chained `&&` or `;` deletes count, so `push --delete a b`, with both at one tip, has none.

It asks, never allows, when a read cannot answer. These reads count: no tip resolves (no tracking ref, no local branch, or a name such as `$B`), the design-file read fails, the remote-ref read fails, the default branch is unreadable, or the layout's `design` folder is unread (no readable layout file). A dry run (`--dry-run`, `-n`) removes nothing and is not judged, as main's push asks skip it.

### A local delete

`git branch -d/-D` leaves origin's copy. It stays allowed while any remote-tracking ref (`<remote>/HEAD` aside), on any remote, holds the tip. It asks only when its subject read is already unreadable (the default branch cannot be read), the tip holds a design file, and no remote-tracking ref holds the tip. It also asks when the `design` folder is unread, for any branch named on that unreadable-subject path.

## Cost

The design-file read starts one `diff` for the files the branch changed. When it changed any, a second `diff` compares those files with the default branch's bytes. A branch that changed no design file costs the one start. A remote delete of a design branch that changed a mockup costs 11 git starts with the remote named: the push verdict 3, the design check 8. A dry run starts none of this. An unread design folder asks after at most 3 starts per name (two tip lookups, then a tag read when no tip resolves).

A call that deletes nothing runs none of this.

A remote delete of one design branch that changed a mockup, with the remote named in the command, costs 11 git starts. Every non-dry-run push reads its deleted names before any verdict. With no remote named, a delete's read starts `git symbolic-ref` and `git config --get` (the config skipped under a `-c branch.<name>.remote=` override), and the push verdict starts the same two for a delete. With the remote named, the read starts none. The push verdict takes 3 (the reviewer's count). The design check takes 8, from a probe: tip lookup 1, default-branch read 2, ancestor read 2, design-file read 2 (two diffs), remote-ref read 1. The design check takes 6 when the branch changed no design file, since the ref read is skipped. The ancestor read is 1 start when it answers "yes": the shallow-clone probe runs only on "no", and a "yes" ends the check. A name with no tip costs 3 starts: tip lookup 2, tag read 1. That holds because the default branch is read at the first tip that resolves. A local delete adds nothing unless its subject read is unreadable.

## Known limits

- A squash-merged branch whose mockup main then edited reads as a change: the bytes differ, so the delete is refused until another ref on origin holds the tip. The archive remedy covers it. A squash whose mockup main still holds byte for byte is allowed.
- The tip is the last-fetched tracking ref, not origin's live tip. A commit pushed to the branch after this clone's last fetch is not read, so a design file on it is not judged. Lane ruling, 2026-11-03 18:55 CST: accepted. An `ls-remote` per delete costs a network call and more than it saves.
- A plain name with no branch tip that is a local tag is skipped, as is a `refs/tags/` spelling. A design branch on origin that this clone never fetched, and that shares a local tag's name, is not judged.
- A local-only design branch is refused by the only-copy rule (`shared-tree`), not by this one.
- A tracking ref of a branch deleted on origin and not pruned still counts as a holder of the tip. So the guard allows a delete that leaves no copy on origin. The ref is read from the local clone, not from origin.
