# A commit-tree judged before an add in the same command reads the old index

- **What.** In `git add -A && git commit-tree $(git write-tree) -p HEAD`, the guard runs `write-tree` before the `add`, so it judges the index without the added paths. A commit moved in by `update-ref` or `reset --soft` leaves no `commit:` reflog line, so the push and stop checks do not read it either. Main allowed this too.
- **Where.** `plumbing_diff` in `hooks/guard.py`, over `ENTRY_OWN`.
- **Decision.** `builders-cannot-edit-tests` (a builder never changes a test or test config).
- **Retire.** Judge the working tree against the parent when an `add` precedes the commit-tree in the same command, or log it unread. A case for `git add -A && git commit-tree $(git write-tree)` with a test file in the work tree is refused in `hooks/test_guard.py`.
