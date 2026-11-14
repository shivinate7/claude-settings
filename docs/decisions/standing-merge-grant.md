# Standing merge grant

## The ruling

Owner rulings, 2026-10-10, 2026-10-29 16:47 CDT, 2026-10-29 20:33 CDT, 2026-10-30 15:06 CDT, 2026-11-01 17:37 CST, 2026-11-01 19:23 CST, 2026-11-02 14:02 CST, 2026-11-02 15:14 CST and 2026-11-02 15:38 CST. The coordinator holds a standing merge grant in claude-settings and in every repo of the owner (`shivinate7`). It is not a fixed list of repos. The batch runner merges under the coordinator's grant, so it has the same scope.

Owner, 2026-11-01 21:34 CST: a batch runner runs every merge under the coordinator's grant. The coordinator never merges.

- Owner, 19:23 CST, typed in the pr-acts-grant lane session: `yes coordinators can merge across repos that is okay it doens't need to juts be in its repo`.
- Owner, 17:37 CST, relayed by the coordinator: `YOU HAVE EXPLICIT APPROVAL FOR ANY AND ALL REPOS YOU WANT OF MINE TO MARK PR READY, MERGE, REVIEW, ETC.` Per the 19:23 ruling, "REVIEW" there means reviewer agents.
- Each build has one holder. In a build with a coordinator, the coordinator holds the grant and a batch runner uses it.
- A lane with no coordinator above it holds the 2026-10-10 grant in claude-settings only. The 19:23 ruling does not widen it.
- In a cloud session, `merge.py` refuses `--confirm` unless the session recorded the batch-runner role.
- A lane with no coordinator above it merges with no batch runner (owner, 2026-11-02 14:02 CST). The merge tool still refuses its cloud confirm, because the role is missing. It merges only under that repo's own merge grant or the owner's named act, and it widens no grant (decision `session-tiers`, Lane the owner starts).
- A lane the owner started merges its own lone lane under the same limits (owner, 2026-11-02 15:14 CST; decision `session-tiers`). A cloud confirm still fails without the batch-runner role.
- A lane that a coordinator started never merges. Owner, 19:23 CST, on the option that lets such a lane merge its own PR: `option C absolutely not correct`.
- The grant holds "for now", until the owner withdraws it.

This is the repo grant that `git-main-only-by-pr` (main moves only by pull request) names.

## Reviews

Owner, 2026-11-01 19:23 CST: `just me and claude building and maintaining these repos`. This lane reads that as: a review is a reviewer agent's report only, and no session posts a GitHub review or approval, in any repo. The owner did not state the no-GitHub-review rule in those words.

## The switch

Owner pick, 2026-10-30 15:06 CDT (waiting item `merge-grant-claude-md-line`, option c): the grant's home in each repo is a true/false switch, `merge.standingGrant`, in that repo's merge settings, `.github/stamp.json`. The rule `questions-go-to-owner` (questions go to the owner) allows the merge tool's config as a grant's home. The owner's words: "can we basically have like a =true/false on either claude.md or some sorta guard so it can be enabled / disabled on the session? adding to the parent claude.md makes less sense".

- The merge tool reads the switch from the base branch on origin, never from the pull request's tree. A pull request cannot turn its own grant on.
- Absent key, or no `stamp.json`: the grant holds. That keeps the behaviour from before the switch. A merge tool older than the switch never meets an unknown field in a repo that leaves the key out.
- `false`: in a cloud session, the merge tool refuses `merge <pr> --confirm` for the coordinator and the batch runner. The coordinator never merges (owner, 2026-11-01 21:34 CST). The batch runner holds no grant of its own, so it reads the same switch. The refusal names no key and no file, so a session does not learn to turn the grant back on.
- A value that is not `true` or `false` stops the merge tool as a broken config.
- Outside the cloud the switch changes nothing. There the tool cannot tell the owner from a session, and the owner must stay able to merge the pull request that turns the switch back on.
- The owner withdraws the grant in a repo by setting the switch to `false` on main, or by telling a session to. A withdrawal in chat still binds every session. The switch makes the merge tool enforce it.

The owner's words, 2026-10-29 16:47 CDT, in web chat:

- "Coordinator just keep it known u will have perpetual standing merge authority that i will withdraw when i decide so no need to ask about merging"
- "on the other repos too for now"

- A batch runner merges by pull request with the merge tool of each repo, on green checks and a done review (record `pr-review-record`) where one is required. The coordinator never merges (owner ruling, 2026-11-01 21:34 CST). A batch runner never asks the owner to merge. A lane session that a coordinator started never merges.
- The batch runner still builds the batches. It runs every merge under the coordinator's grant. It holds no grant of its own.
- Auto mode allows that merge: `settings.json` `autoMode.allow`, entry "Batch Runner Merge" (owner, 2026-11-07 13:27 CST; decision `auto-mode-owner-acts`).
- A batch runner's merge names the head its CI ran on, with `--head <sha>`. The coordinator's merge go carries that head (coordinator, 2026-11-08 12:55 CST; same ruling as decision `auto-mode-owner-acts`).
- While another owner repo's own sessions are not working, the claude-settings coordinator works there only as decision `session-tiers` (the session tiers) allows (bullet "A coordinator in another repo"; owner, 2026-10-30 13:22 and 13:25 CDT). A repo is not working when the session list shows no live session for it. The coordinator uses the agents it starts in its own session to build, review and batch. A batch runner merges under the same grant and the same checks. It never widens what that repo's tools accept, because a shared tool never grows a second form (decision `uniform-over-variants`: a repo matches a shared format).
- The grant covers the merge act only. It lifts no check. These limits still apply:
  - Merge only by pull request. The required checks must pass on the head that merges (the `merge-checks` guard rule, `git-never-merge-failing-ci`: never merge failing CI).
  - Until the cutover, nothing merges while a batch's integration PR has a CI run in progress (`git-no-merge-during-batch-ci`: no merge during a batch CI run). After the cutover, the red-main check (decision `no-merge-onto-red-main`) is the pause.
  - Nothing merges onto a red main, except the revert of the blamed commit (`git-red-main-reverts`: while main's newest finished run is red, only that revert merges).
  - A change merges once its review ends, on green checks (rule `roles-review-cap-three`). A passing round, or a passing fix check after any round, ends the review for every change (record `pr-review-record`).
  - A change with negative net value is held (`hold-unsafe-after-round-3`: the net-value hold). A held lane stays parked until the owner decides.
  - Until the cutover, batch lanes into one integration PR, the only PR that goes ready and runs CI
    (`git-integration-branch-merge`: how lanes join a batch). After the cutover, each lane PR merges alone on its own green run (decision `all-repos-switch-together`).
  - A pull request that GitHub reads as BLOCKED or BEHIND, when read just before the merge call, gets no merge call (sweep row `blocked-or-behind`).
- The merge tool retries a network error 3 times with a short pause (owner ruling 2026-10-13). A rate-limit wait follows a ladder of 60, 300 and 900 s (the orchestrator's call, 2026-10-16). The 3 retries stay (owner ruling 2026-10-16) for a GET, a call its caller marks idempotent, and a rate limit. A write that may have landed on a 5xx or network error is checked first, then resent only if it did not land, up to 3 times (owner ruling 2026-11-13 00:51 CST, page item 650, option c, relayed by triage). The merge PUT and the lock ref POST carry the check. Any other write with no check is sent once, and its check is a new step.
- A rate wait is the exception to the lock's take expiry. The take sets the expiry to 20 minutes (`LOCK_TTL_SECONDS`), at every `merge.deadlineMinutes`. Before each rate wait the lock extends to now + wait + `LOCK_MARGIN` (300 s). If it cannot extend, the call stops as a network stop. `LOCK_MAX_HOLD`, 6 h from the take, bounds how far an extension reaches (owner ruling 2026-10-17). It does not cap the take's own expiry (`merge/merge.py` `confirm`; debt note rate-wait-outside-ttl-budget).
- The lock-break path never waits or retries. A rate-limited delete of an expired lock is a network stop, because a late retry could delete another run's fresh lock (owner ruling 2026-10-17).
- On one head, a run that ran outranks a cancelled run of its name, in either list order (owner ruling 2026-10-13, option a).
- With no `.github/stamp.json`, the merge tool runs on defaults and names the file once (owner ruling 2026-10-10).
- Only a proven refusal reverts the claim (owner ruling, 2026-10-13). A refusal reply with the pull request still OPEN is one (wording recorded 2026-10-18).
- Coordinator reading, 2026-11-07, not an owner ruling: a read answered HTTP 401 or 403 counts as a proven refusal, and any other read that cannot run keeps the claim. A rate-limit 403 is retried, then stops as a network stop, and keeps the claim (merge/merge.py `retry_net`, `Host.gh`, `HTTP_DENIED`).

Kind: process
Home: merge/merge.py
