# Standing merge grant

## The ruling

Owner rulings, 2026-10-10 and 2026-10-29 16:47 CDT: the coordinator holds a standing merge grant in claude-settings and in the owner's other repos. The other repos are banchi, q_max, home, degen, mailaudit, ios-adblock and joyous (the coordinator's list, 2026-10-29). Each build has one holder. In a build with a coordinator, the coordinator holds the grant. A session with no coordinator (solo or one lane) in claude-settings holds the 2026-10-10 grant there. A lane session that a coordinator started never merges. The grant holds "for now", until the owner withdraws it in chat. This is the repo grant that `git-main-only-by-pr` (main moves only by pull request) names.

The owner's words, 2026-10-29 16:47 CDT, in web chat:

- "Coordinator just keep it known u will have perpetual standing merge authority that i will withdraw when i decide so no need to ask about merging"
- "on the other repos too for now"

- The coordinator merges by pull request with the merge tool of each repo, on green checks and a done review where one is required. It never asks the owner to merge.
- The batch runner still builds the batches. It may run the merge tool under the coordinator's grant. It holds no grant of its own.
- While another owner repo's own sessions are not working, the claude-settings coordinator may run that repo's work end to end. It uses the agents it starts in its own session to build, review and batch. It merges under the same grant and the same checks. It never widens what that repo's tools accept. Process-only (owner, 2026-10-29 20:33 CDT, paraphrased): the owner's other repos are not working, so the coordinator may complete any of that work end to end.
- The grant covers the merge act only. It lifts no check. These limits still apply:
  - Merge only by pull request. The required checks must pass on the head that merges (the `merge-checks` guard rule, `git-never-merge-failing-ci`: never merge failing CI).
  - Nothing merges while a batch's integration PR has a CI run in progress (`git-no-merge-during-batch-ci`: no merge during a batch CI run).
  - A diff that touches a rule's behaviour, a guard's or check's verdict, or program logic merges only after a
    fresh reviewer approves it.
  - After review round 3, a change that changes a guard or check gets the net-value test (`hold-unsafe-after-round-3`: the net-value hold after round 3). A held lane stays parked until the owner decides.
  - Batch lanes into one integration PR, the only PR that goes ready and runs CI
    (`git-integration-branch-merge`: how lanes join a batch).
- The merge tool retries a network error 3 times with a short pause (owner ruling 2026-10-13). A rate-limit wait follows a ladder of 60, 300 and 900 s (the orchestrator's call, 2026-10-16). The 3 retries stay (owner ruling 2026-10-16).
- A rate wait is the exception to the 600 s lock cap. Before each rate wait the lock extends to now + wait + 300 s. If it cannot extend, the call stops as a network stop. `LOCK_MAX_HOLD`, 6 h from the take, bounds one run's hold (owner ruling 2026-10-17).
- The lock-break path never waits or retries. A rate-limited delete of an expired lock is a network stop, because a late retry could delete another run's fresh lock (owner ruling 2026-10-17).
- On one head, a run that ran outranks a cancelled run of its name, in either list order (owner ruling 2026-10-13, option a).
- With no `.github/stamp.json`, the merge tool runs on defaults and names the file once (owner ruling 2026-10-10).
- Only a proven refusal reverts the claim: a refusal reply with the pull request still OPEN (owner ruling).

Kind: process
Home: merge/merge.py
