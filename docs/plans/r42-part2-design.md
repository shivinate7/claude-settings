# R42 part 2: per-lane merges, test after merge, stable branch

Design for ruling R42 part 2 (docs/plans/restart-plan.md), not yet decided. Plan agent (Opus) report, then the refuter (Opus) verdict, both 2026-11-11 CST. Owner questions are in the coordinator report of 23:00 CST. Nothing here is built.

## Plan

Point: R42 part 2 (per-lane merges, test after merge, revert, stable branch) is buildable from existing homes, but 4 premises fail against live records. The "Never revert" rule and M3 (green run on current main) are the load-bearing ones. The installers are the easy part. Order is forced: stable branch, then installers, then bisect/revert, then delete the batch brake; deleting the brake first ships a red main to every session through the installers.

Premises (decision premise-format):
- P1 [ruling] Owner picked A for R42 part 2. Source: restart-plan.md:762. Checked 2026-11-11. HOLDS.
- P2 [ruling] "A lane merges on its own green checks". Source: restart-plan.md:756. Checked 2026-11-11. FAILS if it means that the lane session merges: standing-merge-grant.md:16 (owner 2026-11-01 19:23, "option C absolutely not correct"); session-tiers.md:121 (cloud confirm needs batch-runner role). Plan reads it as: each lane PR merges alone, batch runner still runs merge.
- P3 [read] Main's CI runs after each merge, one verdict per commit. Source: checks.yml:4 (push main), :26 (group = run_id, never cancelled). Checked 2026-11-11. HOLDS. So bisect is a read: first red push run whose parent's run is green.
- P4 [ruling] A red main run reverts the breaking commit. Source: restart-plan.md:757. Checked 2026-11-11. FAILS against skills/ci-hygiene/SKILL.md:103-104 ("Never revert") and merge-deletes-batch-lanes.md:47 (batch #663 lost 11 of 13 files, refuse_dropped_lane). Needs a re-land route (act 3).
- P5 [read] Lanes are "green alone" today. Source: main-branch-protection.md:11-21. Checked 2026-11-11. FAILS partly: a draft PR runs no checks.yml job; Windows shards never run on a PR, so the first Windows verdict is main's (debt windows-main-run-flakes: false reds there).
- P6 [read] Per-lane merges are fast. Source: merge.py:3535 (lock taken) then wait_checks under lock :3587, :3630 (after claim push), :3702; merge-needs-current-base.md:25 (small-move check ~13 min). Checked 2026-11-11. FAILS: each merge would hold the lock ~35 min.
- P7 [ruling] Child CI uses @stable (R44 part 1). Source: restart-plan.md:729. Checked 2026-11-11. FAILS against ci-hygiene SKILL.md:47, :291 (40-hex pins), lanes-run-no-full-ci-job.md:25 (--pinned runs local copy for non-sha ref), action-pins-follow-sessions (ste-changed reads @<sha>). zizmor unpinned-uses policy: UNKNOWN.
- P8 [notes] Main has a finished green run. Source: restart-plan.md:759 (#2591). Checked never. UNKNOWN; blocks act 0.
- P9 [notes] Baseline 147 drops / 15 merges. Source: restart-plan.md:266-267. Checked never (not re-measured).
- Simpler route: no new bisect machinery (P3); the lone-lane path exists ("A lone lane is its own integration PR", SKILL.md:92); risk sizing exists in review-record kinds (REVIEW_KINDS/REVIEW_GUARDS, merge.py:3814) and roles rules.

(1) Acts, in landing order (acts 0-3 land through today's batches):
0. Prerequisite: #2591 lands, main finishes a green push run, step merge-reads-ruleset lands (R45 ruling c, restart-plan.md:949). Done: `merge <pr>` preview reads main green on the ruleset.
1. Stable branch + mover. New .github/workflows/stable.yml: on workflow_run of checks (push, main, success), fast-forward-only push of `stable` to head_sha with GITHUB_TOKEN; refuses a non-descendant. Ruleset on stable blocks delete/force-push (skills/project-ops/scripts/protect.py). .github/stamp.json keepBranches += stable; R45 sweep skips it. Done: test_action cases red first (P2) on failed-run and non-descendant; one real move observed after a green main run.
2. Installers read stable: install.sh:23 default REF=stable; cloud-setup.sh:10 RAW uses stable; install.sh:212/:319/:376/:398 and install_from_main.sh:40 read stable, not refs/heads/main. Pin moves when origin/stable moves, read on demand at SessionStart (hooks/session_start.sh:225-271), no longer in afterMerge per merge. CLAUDE_SETTINGS_REF=main stays as recovery (verification-recovery-independent-of-state). Done: merge/test_install_from_main.sh and install tests red first for stable; a cloud start logs "refreshed ... to stable".
3. Bisect + revert in the merge tool's one home: red_base (merge.py:3319) names the breaking merge commit and PR from the same runs page; it names `gh run rerun --failed` first and blames only when the re-run is red again (P6 flake rule). New `merge --revert <sha>`: branch from main, `git revert -m 1`, trailer `Reverts: #N`, PR by MCP in cloud, merges under --base-red-ok. Re-land = fresh branch from main that reverts the revert plus the fix; never merge main into the old lane branch (#663). Done: test_merge cases red first: blames first red with green parent; refuses a revert of a revert; refuses a second revert of one PR.
4. Cutover to per-lane merge sized by risk: delete batch_refusal (merge.py:3336), MERGE_BATCH_REASON (guard_merge.py:229), --batch-build/--batch-drop. M3 becomes: green PR run on its own base plus a clean merge-tree against tip; drop the small-move suite run (merge.py:2176-2300). confirm merges only an already-green head, no CI wait under the lock (claim-only commit counts as green head, as lane lint already allows, lanes-run-no-full-ci-job.md:13). Risk sizes review: docs-only gets lint + green; normal gets one reviewer; guard/check change keeps rounds + net value. Done: test_merge red first: a green head behind by a non-conflicting merge merges with no wait; a conflicting head is refused (P11: test the rule's allowed cases).
5. Records, rules, glossary per (2). Done: lint/rule_audit, test_all_jobs_passed, stale-cites pass.
6. Child repos on @stable, last: zizmor policy, bin/ste-changed and --pinned learn @stable. Done: one q_max PR green on @stable.

(2) Rule and decision changes, with the new sentence:
- git-integration-branch-merge: "Each lane PR merges alone through the merge tool, on its own green run and the review its risk needs."
- git-no-merge-during-batch-ci: retired. New anchor git-red-main-reverts: "While main's newest finished run is red, only the revert of the blamed commit merges."
- git-never-merge-failing-ci: "Never merge a PR whose own run is red, or onto a red main, except its revert."
- roles-review-cap-three: "remove it from the batch" -> "it does not merge"; "A red batch still drops the lane first" -> "A red main reverts the blamed lane first".
- roles-each-layer-proves-once: "The PR run is the merge check; main's run after the merge runs the full suites and the Windows shards."
- reports-batch-pace-numbers: read at each report after merges, plus reverts per merge (R42 part 3).
- Decisions retired: no-merge-during-batch-ci, batch-freeze-lane-set. Rewritten: merge-needs-current-base and merge-practices M3 ("green on its own base plus a clean merge with the tip"); merge-reinstalls-from-main ("pin follows stable"); merge-deletes-batch-lanes ("the PR's own branch only"); standing-merge-grant:51-52 ("each lane PR merges alone"); session-tiers Batch runner bullet (drop "integration batch", add bisect and revert); action-pins-follow-sessions (child pins follow stable); ci-hygiene step 8 rewritten as "Merge lanes".
- GLOSSARY.md: retire batch, integration branch, integration PR rows; add "stable branch: the branch sessions install from; it moves only to a main commit whose push run is green." No "Not" cell clash.
- Practices used: P2, P6, P11 (test-practices); M2 kept, M3 changed, M7 kept (merge-practices).

(3) Risks and guards:
- Red main: sessions never see it, because stable does not move (acts 1-2); the red-main check (no-merge-onto-red-main) stops other merges until the revert's run is green (33-38 min per run, restart-plan.md:268).
- Two lanes green alone, red together: lane-lint's merge-tree catches text clashes (lanes-run-no-full-ci-job.md:17); silent-undo check stays at merge (SKILL.md:124); main's run catches the rest and bisect names the later commit, so that lane is reverted.
- Revert loops: a revert is never itself reverted (trailer). A red that survives one revert stops all reverts and posts one waiting-page item. A PR reverted twice goes to a fix lane (R26 part 2 shape). A flake re-run comes before any blame (debt windows-main-run-flakes).
- Child repos on stable: stable moves only on a fully green main run that includes the actions' own tests (checks.yml:618-619). A child red from an action is fixed by a revert on claude-settings main. A child may hold a sha pin as a cited exception (R44).
- CI runners: each ready lane PR and each merge start 11 runners (main-branch-protection.md). The repo is public (README.md:185), so no minutes bill. The account concurrent-job limit is unmeasured. Measure queue time in the pace numbers before changing push-run grouping.

(4) Until act 4 lands, everything stays batched: R26/3.4 batches, the batch brake, the freeze, blame-and-drop. The merge lock stays after cutover too: one merge at a time (merge-lock.md), but with no CI wait under it.

Input Needed (plan does not wait on them):
- P2: may a lane session merge its own PR, against the 2026-11-01 19:23 ruling? Recommend no: the batch runner merges each PR alone. Departs from: nothing if no.
- Red main: halt all merges (today's check), or let lanes not touching the blamed paths merge? Recommend halt first, measure.
- Batch runner keeps its name after batches end, or is renamed? Recommend keep it until you rename it.
- Departs from: ci-hygiene step 7 SHA pinning for claude-settings actions in child repos (R44 part 1 already rules the move).

## Refuter

Refuter verdict: HOLDS WITH CHANGES (Opus, 22:58 CST Nov 11).

Refuter: refuter opus, 2026-11-11, HOLDS WITH CHANGES (gaps 1 to 6 below).
Premises P1-P6 hold (P2 as the plan reads it). P7, P8, P9 unknown.
Gaps:
1. No wake on a red main run: ci-done runs only on PRs (checks.yml:1981); ci-alarm is tested (checks.yml:618-619) but never called; Issues ruled out (p'). Act 3 needs a named trigger, for example the batch runner sets a one-time check-in on main's push run after each merge (git-ci-wait-checks-in).
2. Part (2) misses decision draft-until-reviewed (owner: "Lane PRs stay drafts. Only one integration PR per batch goes ready."); per-lane merge needs that ruling changed. 13 decisions name the integration PR; the plan lists ~9 and omits auto-mode-owner-acts, records-index-at-merge, pr-review-record, pr-ledger, notes-merge-union, claims-carry-backing, child-cites-not-copies, plus skills/project-ops/SKILL.md and templates/operating-model.md.
3. The merge tool is shared (~/.claude/bin/merge runs claude-settings merge.py for every repo). Act 4 removes batching and the green-on-current-base check in child repos too, which get no stable branch or revert route. A per-repo switch conflicts with decision uniform-over-variants. Owner question.
4. Act 2 misses install.ps1:39 (refs/heads/main) and merge/launch.py:39-47 (merge tool runs from origin/main; say main or stable). The SessionStart pin move is new (session_start.sh:264-271 only warns); its done check covers only cloud.
5. Act 3 contradicts itself: re-land reverts the revert, but the done check refuses a revert of a revert. Revert-of-revert already counted at merge.py:2445.
6. Act 1's ruleset has no tool: protect.py sets only classic protection; act 0 names protect.py getting ruleset support (restart-plan.md:951).
Simpler routes: (a) revert as an ordinary lane PR merged with --base-red-ok (merge.py:3321-3322 already names it); drop merge --revert and its trailer guards (no incident; building-guard-needs-incident). (b) Stable mover as a last job in checks.yml on push to main, needing every job like ci-done, instead of a new workflow_run file; costs contents: write on that one job.
Unchanged: landing order (stable, installers, revert, delete batch brake) and part (4).
