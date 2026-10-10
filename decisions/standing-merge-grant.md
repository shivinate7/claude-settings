# Standing merge grant for this repo

Owner ruling, 2026-10-10: the orchestrating session has standing merge authority in
claude-settings. This is the repo grant that `git-main-only-by-pr` names.

- Merge only by pull request. The required checks must pass on the head that merges
  (`git-wait-for-required-checks`, `git-never-merge-failing-ci`).
- A diff that touches a rule's behaviour, a gate's verdict, or program logic merges only after a
  fresh reviewer approves it.
- Batch green PRs into one integration branch (`git-integration-branch-merge`).
- The grant covers this repo only. Other repos need their own grant.
