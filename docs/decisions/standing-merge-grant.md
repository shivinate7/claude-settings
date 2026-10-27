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
- The merge tool retries a network error 3 times with a short pause (owner ruling 2026-10-13). A rate-limit wait follows a ladder of 60, 300 and 900 s (the orchestrator's call, 2026-10-16). The 3 retries stay (owner ruling 2026-10-16).
- A rate wait is the exception to the 600 s lock cap. Before each rate wait the lock extends to now + wait + 300 s. If it cannot extend, the call stops as a network stop. `LOCK_MAX_HOLD`, 6 h from the take, bounds one run's hold (owner ruling 2026-10-17).
- The lock-break path never waits or retries. A rate-limited delete of an expired lock is a network stop, because a late retry could delete another run's fresh lock (owner ruling 2026-10-17).
- On one head, a run that ran outranks a cancelled run of its name, in either list order (owner ruling 2026-10-13, option a).
- With no `.github/stamp.json`, the merge tool runs on defaults and names the file once (owner ruling 2026-10-10).
- Only a proven refusal reverts the claim: a refusal reply with the pull request still OPEN (owner ruling).

Kind: process
Home: merge/merge.py
