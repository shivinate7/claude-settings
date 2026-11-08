# Open merge's untouched test conflict is refused when the checkout converts files

- **What.** Any working-tree conversion (`core.autocrlf`, the Git for Windows default; `.gitattributes` text, eol or ident; an LFS smudge) makes the worktree bytes differ from git's merge blob. So a builder's open merge, with a conflicted test file left as git wrote it, is still refused at commit, push and stop on such a checkout. Harm: a false alarm on Windows sessions.
- **Where.** `merge_resolved` and `bytes_at` in `hooks/guard.py`: the open merge reads the working-tree file and compares it to the blob of `git merge-tree`.
- **Decision.** `builders-cannot-edit-tests` (a builder's test change is refused; the Named limit line points here).
- **Retire.** Compare the working-tree side after the same conversion git applies (for example read it as `git add --renormalize` would store it), then add a case with `core.autocrlf=true` that allows an untouched conflicted test file. The case passes in `hooks/test_guard.py`.
