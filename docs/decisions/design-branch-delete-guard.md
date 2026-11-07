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
- The tip holds a file under the layout's `design` folder that the default branch lacks, or holds other bytes at that path than the default branch does. A mockup the branch modified counts as the only copy, as an added one does; a blob identical to the default branch's does not.
- No `archive/*` ref on origin holds the tip. Any archive name counts, not only `archive/<b>`, because the rule allows a new archive name when the first is taken.

It asks, never allows, when a read cannot answer: no tip resolves (no tracking ref, no local branch, or a name such as `$B`), the design-file read fails, the archive-ref read fails, the default branch is unreadable, or the layout's `design` folder is unread (no readable layout file). A dry run (`--dry-run`, `-n`) removes nothing and is not judged, as main's push asks skip it.

### A local delete

`git branch -d/-D` leaves origin's copy. It stays allowed while any origin ref holds the tip. It asks only when its subject read is already unreadable (the default branch cannot be read), the tip holds a design file, and no origin ref holds the tip. It also asks when the `design` folder is unread, for any branch named on that unreadable-subject path.

## Cost

The design-file read still starts one `diff`; the filter widening from added to added-or-modified changes no start count, only the diff's own work (it compares blobs of files that differ, which it already did to list them). A dry run starts none of this. An unread design folder asks after at most 2 starts per name (tip lookup, tag read).

A call that deletes nothing runs none of this.

A remote delete of one design branch, with the remote named in the command, measured 10 git starts. The push verdict takes 3 (the reviewer's count). The design check takes 7, measured here: tip lookup 1, default-branch read 2, ancestor read 2, design-file read 1, archive-ref read 1. The ancestor read is 1 start when it answers "yes": the shallow-clone probe runs only on "no", and a "yes" ends the check. A name with no tip costs 3 starts: tip lookup 2, tag read 1. That holds because the default branch is read at the first tip that resolves. A local delete adds nothing unless its subject read is unreadable.

## Known limits

- The tip is the last-fetched tracking ref, not origin's live tip. A commit pushed to the branch after this clone's last fetch is not read, so a design file on it is not judged. Lane ruling, 2026-11-03 18:55 CST: accepted. An `ls-remote` per delete costs a network call and more than it saves.
- A plain name with no branch tip that is a local tag is skipped, as is a `refs/tags/` spelling. A design branch on origin that this clone never fetched, and that shares a local tag's name, is not judged.
- A local-only design branch is refused by the only-copy rule (`shared-tree`), not by this one.
