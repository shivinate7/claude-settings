# Standing merge grant

## The ruling

Owner rulings, 2026-10-10, 2026-10-29 16:47 CDT, 2026-10-29 20:33 CDT and 2026-10-30 15:06 CDT: the coordinator holds a standing merge grant in claude-settings and in the owner's other repos. The other repos are banchi, q_max, home, degen, mailaudit, ios-adblock and joyous (the coordinator's list, 2026-10-29). Each build has one holder. In a build with a coordinator, the coordinator holds the grant, and only the batch runner runs the merge, under it (waiting-page item 111, pick a, 2026-11-01 11:53 CST). Outside the cloud, solo and one-lane sessions merge their own work. The merge tool's confirm check (`merge/merge.py`, `--confirm` with `CLAUDE_CODE_REMOTE` set to `true`) requires a merge role only in the cloud, so in the cloud it refuses their confirm (`session-tiers`, Merge role). A session with no coordinator (solo or one lane) in claude-settings holds the 2026-10-10 grant there. A lane session that a coordinator started never merges. The grant holds "for now", until the owner withdraws it. This is the repo grant that `git-main-only-by-pr` (main moves only by pull request) names.

## The switch

Owner pick, 2026-10-30 15:06 CDT (waiting item `merge-grant-claude-md-line`, option c): the grant's home in each repo is a true/false switch, `merge.standingGrant`, in that repo's merge settings, `.github/stamp.json`. The rule `questions-go-to-owner` (questions go to the owner) allows the merge tool's config as a grant's home. The owner's words: "can we basically have like a =true/false on either claude.md or some sorta guard so it can be enabled / disabled on the session? adding to the parent claude.md makes less sense".

- The merge tool reads the switch from the base branch on origin, never from the pull request's tree. A pull request cannot turn its own grant on.
- Absent key, or no `stamp.json`: the grant holds. That keeps the behaviour from before the switch. A merge tool older than the switch never meets an unknown field in a repo that leaves the key out.
- `false`: in a cloud session, the merge tool refuses `merge <pr> --confirm` for both merge roles, the coordinator and the batch runner. The batch runner holds no grant of its own, so it reads the same switch. The refusal names no key and no file, so a session does not learn to turn the grant back on.
- A value that is not `true` or `false` stops the merge tool as a broken config.
- Outside the cloud the switch changes nothing. There the tool cannot tell the owner from a session, and the owner must stay able to merge the pull request that turns the switch back on.
- The owner withdraws the grant in a repo by setting the switch to `false` on main, or by telling a session to. A withdrawal in chat still binds every session. The switch makes the merge tool enforce it.

The owner's words, 2026-10-29 16:47 CDT, in web chat:

- "Coordinator just keep it known u will have perpetual standing merge authority that i will withdraw when i decide so no need to ask about merging"
- "on the other repos too for now"

- The batch runner merges by pull request with the merge tool of each repo, on green checks and a done review where one is required. It never asks the owner to merge.
- The batch runner still builds the batches. It runs the merge tool under the coordinator's grant. It holds no grant of its own.
- While another owner repo's own sessions are not working, the claude-settings coordinator works there only as decision `session-tiers` (the session tiers) allows (bullet "A coordinator in another repo"; owner, 2026-10-30 13:22 and 13:25 CDT). A repo is not working when the session list shows no live session for it. The coordinator hands each merge to its own batch runner, the claude-settings build's, under the same grant and the same checks. It runs no build or review agents there. It never widens what that repo's tools accept, because a shared tool never grows a second form (decision `uniform-over-variants`: a repo matches a shared format).
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
