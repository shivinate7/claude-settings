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
- The merge tool retries a network error 3 times with a short pause (owner ruling 2026-10-13). A rate-limit wait follows a ladder of 60, 300 and 900 s, and 3 retries stay (owner ruling 2026-10-16).
- A rate wait is the exception to the 600 s lock cap. `LOCK_MAX_HOLD`, 6 h from the take, bounds one run's hold (owner ruling 2026-10-17).
- Only a proven refusal reverts the claim: a refusal reply with the pull request still OPEN (owner ruling).

Kind: process
Home: merge/merge.py
