# A merge needs a clean merge with the base tip, and a green run or a lane-lint PASS

## The ruling

Owner pick A for R42 part 2 (per-lane merge). Rule M3, per lane: the head must merge cleanly with the base tip. Its own run must be green, or still pending under a lane-lint PASS that names its live head, or the head sits on a green proof (below). The head need not hold the tip.

Owner ruling `own-merge-on-lint-pass` (owner, 2026-11-15 18:21 CST, typed "B for sure") added the pending case. Main's run after the merge is the check, and a red main gets a revert or a fix (ruling Q5 v).

- The run read is one read, with no wait under the lock. The lint proof is asked only when the read says the head is pending. A pending head with no PASS stops the merge at that read.
- A PASS lifts a pending run only for the head it names. It carries to the live head over claim commits. For a PR that replaces a source PR, it also carries over an identical tree. Any other PASS refuses.
- A finished red run refuses. A red main does not: a PR may merge onto it (ruling Q5 v). A lane-lint PASS still lifts no pending head while main is red (decision `no-merge-onto-red-main`).
- The clean merge is `git merge-tree --write-tree` of the head and the base tip. `confirm` reads it before the claim and again after the claim push. A conflict refuses. So does a read that cannot run.
- A confirm that must push a claim commit pushes it and stops. The next confirm merges the claim head once its run is green, or pending under a PASS that carries over the claim commit.
- The tool sends its PUT past a BLOCKED read only when a PASS lifted the pending run, or a carried proof sits under the head (below). BEHIND still refuses.
- A stale records page on a ready PR heals inside `--confirm`, on the default base, under any `merge.requiredChecks`. The tool merges the base in when the base gained a record, pushes one page commit, and waits on no check. Under `"none"` no check gates the merge. Otherwise the proof is the green checks of the proven head: the head under this tool's own page-only commits and clean merges of the base, with no cap on how many (`proven_head`). A pending or red proven head refuses. A lint PASS that lifted a pending run does not heal. The live head's own run is then read: red or unknown refuses, pending carries. A record-claim commit is not carried; its own run is read.
- The batch's wait for the base to move and the small-move suite run are gone.

Rule d. Lanes bring main in only on conflict; the merge tool does one main-in at merge time and keeps the green run (needs #3481 and #3552 on main). Skill `ci-hygiene` step 8 holds the same rule.

Coordinator's reading, not the owner's: until both are on main, rule d is not in force and ruling `own-923-c-ready-lanes-bring-main-in` stands.

- Based on (ruling): owner, chat, 2026-11-23 15:36 CST, option a: no cap on stacked clean merges of main above a proven head, on either path. A busy main never forces a second full CI run; main's own run is the net. It extends R1 (owner, chat, 10:49 CST: no second full run).
- Based on (ruling): owner, chat, 2026-11-23 15:31 CST, option a: the carried proof reaches the relayed yes (`relayed_head_holds`), the Lane draft PR grant and rule `git-integration-branch-merge`.
- Based on (ruling): owner, 2026-11-17 14:20 CST, page item 925 `main-in-once-before-lint`, pick d, item closed 14:27 CST. His words: "Lanes bring main in only on conflict; the merge tool does one main-in at merge time and keeps the green run (needs #3481 and #3552 on main)."
- Based on (ruling): owner, 2026-11-16 13:46 CST, page item 923 pick c, typed in the coordinator's chat, ruling `own-923-c-ready-lanes-bring-main-in`: ready lanes, or lanes one step from ready, bring main in after each merge. Ruling c was never filed to a record on main.
- Closed, nothing to build: no grade by priority for lane PRs (page item 924, option c, no grade; the consultant closed it at 09:57 CST, 2026-11-17). Nothing tiers a lane. A lane brings main in only as this record says: under ruling `own-923-c-ready-lanes-bring-main-in` until rule d is in force.

Why: branch protection on `main` has `strict` false, so GitHub reports BEHIND only when `strict` is on (`main-branch-protection`). The tool's own reads are the gate.

Residual risk: a clean merge can still break a suite, and a head can merge before its own run ends. Main's run after the merge finds it. The red does not hold merges. The red becomes the top lane at once, by revert or fix (decision `no-merge-onto-red-main`: a PR may merge onto a red main; UNKNOWN still refuses).

Kind: process
Home: merge/merge.py

Cost: per merge, one read of the head's run and two `git merge-tree --write-tree` starts (unmeasured). A carried proof adds one `git log` per commit walked, one base fetch when a base merge is met, and one read of the live head's run (unmeasured). A pending head adds one paged read of the repo's comments and the carry checks (unmeasured).

Risk: likely. Lanes merge while main moves, so main often moves under a green or pending head.
