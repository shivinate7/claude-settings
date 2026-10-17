# Standing merge grant for this repo

## The ruling

Owner ruling, 2026-10-10: the orchestrating session has standing merge authority in
claude-settings. This is the repo grant that `git-main-only-by-pr` names.

- Merge only by pull request. The required checks must pass on the head that merges
  (the `merge-checks` guard rule, `git-never-merge-failing-ci`).
- A diff that touches a rule's behaviour, a gate's verdict, or program logic merges only after a
  fresh reviewer approves it.
- Batch lanes into one integration PR, the only PR that goes ready and runs CI
  (`git-integration-branch-merge`).
- The grant covers this repo only. Other repos need their own grant.

Kind: process
Home: merge/merge.py
