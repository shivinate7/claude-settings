# Merged plan of open work

Base: origin main 5a5f081e (batch 69, PR #1103). Source handoffs are named branch:path. A PR is named with its number, gloss and head. Every head below is what a handoff or origin showed at 13:25 CST. Read the live head before you act.

A lane starts only when its blocking owner item is clear. A lane that edits hooks/guard.py or hooks/mutate_guard.py joins the guard train (lanes 1 to 4) and merges main first. The coordinator briefs each lane once. The batch runner merges.

## Lane 1: report-guard

- Goal: an owner question reaches the waiting page by a check (rule questions-go-to-owner), and the report guard sees every landing tool.
- Absorbs: questions-reach-page-handoff:handoffs/questions-reach-page.md, archive/trial-tz:handoffs/trial-tz.md (reference only), archive/trial-lg:handoffs/trial-lg.md (reference only). Roadmap steps ask-reaches-writer and option-key-guard-gap, and the LANDING_TOOLS gap (owner pick a, 2026-11-01 16:23 CST).
- PRs: #1070 (questions reach the page), draft, head 7373ce61. Dropped from batch 69 on red checks-mutate-guard.
- Blocking owner item: none. The owner reads the root CLAUDE.md wording edit to rule questions-go-to-owner. That read does not block the build.
- Conflict, origin side: the trial lanes are not real lanes. Do not rebase or open a PR from either one. Main 5a5f081e may already hold the trial-lg style sentence. Check first.
- First step: a test-author re-points the stale mutation in hooks/mutate_guard.py (about line 1996, roadmap-one-writer set_session_tags) at hooks/own_session.py. Then run `verdict python3 hooks/mutate_guard.py` in full, run check_silent_undo --strict, merge main, and send the head to the batch runner. After #1070 lands, a second slice adds LANDING_TOOLS (gh pr merge, gh pr create, git revert, git cherry-pick, delete_file, update_pull_request_branch) red test first, and folds in the two trial-tz questions (a chat answer clears an item, a lane sends to its parent).
- Open, cause unknown: janitor/mutate_sweep killed 0 of 187 mutants in CI once (runner 7 handoff). The test-author notes it while the full mutation run is open.
- Size: split. Slice 1a is #1070 alone. Slice 1b is everything after it.

## Lane 2: other-clone refusal

- Goal: guard rule other-checkout (hooks/guard.py other_checkout_hit) refuses a cd into, or a write into, a separate clone of the same repo.
- Absorbs: other-clone-cd-refuse:handoffs/other-clone-cd-refuse.md.
- PRs: none. Branch head e46e284e, base main 62bdb8a6.
- Blocking owner item: none.
- Conflict: none. Hazard from the handoff: agent worktrees share the local branch ref, and one agent reverted guard.py by mistake (acd5fb5f, restored by d632c8a0). Push with `git push origin HEAD:other-clone-cd-refuse`.
- First step: merge main, then review round 3 of 3 (reviewer sonnet, xhigh) with the net-value test against main. Then lane lint, draft PR, send number, head and verdict to the batch runner. Remove the handoffs/ file before the batch.
- Unlocks: the banchi follow-up in lane 11 that closes DEBT-guard-misses-other-clones.

## Lane 3: branch cleanup, split in three

- Goal: worktree-agent-* branches never reach origin, the Mac delete brief exists, and the branch count joins the pace numbers (owner fb-1041-3).
- Absorbs: branch-cleanup:handoffs/branch-cleanup.md.
- PRs: none. Head c2fc5ebf. It conflicts with main in hooks/guard_push_delete.py.
- Blocking owner item: item 170 (the 136-branch delete paste) for the Mac half.
- First step: start fresh from three slices, not a merge. 3a: guard rule agent-branch-push (hooks/guard_push_delete.py, hooks/guard.py, decision agent-branch-never-pushed). Keep main's _push_parse, _push_dest and push_destinations, and add AGENT_PUSH_RULE in push_verdict. It joins the guard train after lane 2. 3b: the Mac deletes brief, record-writer, Markdown only. It joins lane 7. 3c: the five-number pace wording in reports-batch-pace-numbers. It joins lane 7. After the merge, delete branches branch-cleanup-records and branch-cleanup-tests.
- Open question for the coordinator: an agent with no brief branch keeps its commits local only. The lane reads the owner's 10:41 ruling as yes. Confirm.

## Lane 4: tier boundaries

- Goal: coordinator-scope guard and a review record on each PR (owner 2026-10-31 15:31 CDT).
- Absorbs: handoff/tier-boundaries-enforced:handoffs/tier-boundaries-enforced.md.
- PRs: #1065 (review record), draft, head 42fdc267, needs a main merge. #919 (own_tier_tagged), head 568e606e, held by the coordinator. #1042, head 49adc89e (it contains #919), held.
- Blocking owner item: none. The holds are the coordinator's, set 2026-11-02 10:17 CST.
- First step: #1065 first. Merge main, resolve merge/merge.py, run checks, post the review record for the new full head, send the head to the batch runner. Then #919: a builder finishes items 2 to 4 (session-tiers.md line 81 and Limits, the cost line near 83, notes.md line 829), runs all checks, then round 3 reviewer sonnet with the net-value test.
- Conflict, origin side: nobody owns the stale line 136 of session-tiers ("Open: the context limit for each tier"). Give it to this lane, since #919 already edits session-tiers.md. Session-tiers line 16 says the limit is gone.
- Unstarted debts that wait: session-start-handoff-text (waits on #1042), mcp-merge-matcher-missing (waits on #1065).

## Lane 5: merge tool

- Goal: the merge tool (merge/merge.py) lets a newer green run on the same or a newer main sha clear a red main, and holds the claim-revert excuse.
- Absorbs: handoff/red-main-same-sha-green:handoffs/red-main-same-sha-green.md, no-undo-lane-commits:handoffs/no-undo-lane-commits.md (merge half only).
- PRs: none for red-main (WIP head 64cf676e). #1099 (lane undo check), draft, head 43dfc3b0.
- Blocking owner item: 166 newer-run-clears-red. Do not merge the red-main part before the owner rules. Items 154 and 161 are the same question in other repos and close into 166.
- Conflict, origin side: item 161 is settled (pick b, no override). The joyous lane still lists it as open. Tell it nothing. Chain: 166, then this lane, then joyous #68, then #67.
- First step: on head 64cf676e run `pytest merge/test_merge.py`, `ci-job checks --lint` and `merge --lane-lint`. After the owner rules, rewrite the cross-group bullet of no-merge-onto-red-main in place, or archive the lane if the answer is "change nothing". Then draft PR, net-value review (sonnet).
- Order on merge.py: #1065 (lane 4), then #1099, then this lane.

## Lane 6: lane undo check

- Goal: a builder cannot undo earlier work of its own lane (owner fb-1041-1). One excuse line, Drops-lines (item 165, pick a).
- Absorbs: no-undo-lane-commits:handoffs/no-undo-lane-commits.md (lint half: lint/check_silent_undo.py).
- PRs: #1099, draft, head 43dfc3b0.
- Blocking owner item: the owner grant for narrowing "any line" to two shapes is pending (coordinator ruling 2026-11-02 11:26 CST). The net-loss dial (3 lines or 6 lines) needs the coordinator or the owner.
- First step: re-measure the sweep (16 of 31 batches red at 43dfc3b0). Pick the dial. Verify 43dfc3b0 excuses. Run merge/test_merge.py. Review round 2. Then `merge --lane-lint 1099` and send to the batch runner.

## Lane 7: prose records (record-writer, Markdown only)

- Goal: owner rulings that land as prose have one writer per batch.
- Absorbs: rotation-text-current:handoffs/rotation-text-current.md (head 092b733f, no PR), the drop-ste-name branch (fb-1322-1), PR #1104 (time zone in every time, head 3a3375fb), branch-cleanup slices 3b and 3c, the root CLAUDE.md wording edits from lanes 1, 3 and 6.
- Blocking owner item: item 169 (drop the self-reported tally) does not block.
- Conflict, origin side: three lanes edit agents/*.md and project-ops. Merge drop-ste-name first. Then rotation-text (it never ran its builder). Then the rest.
- First step: the builder edits project-ops SKILL.md lines 3 and 17, templates/operating-model.md, templates/roster.md and README.md line 289, then runs lint/hook_catalog.py. The test-author work is done (9915deb4, red on 74be1279).
- Open: home, degen and mailaudit need briefs to re-paste the rotation section. None written.

## Lane 8: child repos cite records (code half)

- Goal: a child repo's CLAUDE.md cites claude-settings records and never copies them (owner fb-1041-2).
- Absorbs: child-rules-cite-records:handoffs/child-rules-cite-records.md.
- PRs: #1098 (child CLAUDE.md check), draft. Round 2 approve (sonnet).
- Blocking owner item: none.
- First step: run lane lint on the final head (`ci-job checks --lint`, `check_silent_undo --strict`, `merge --lane-lint 1098`). Send number, head and "round 2 approve" to the batch runner. Triage puts the three child briefs (home, degen, ios-adblock) in the roadmap outbox. Note: its commit trailers name Haiku and Opus, though the builders ran Sonnet.
- Open: a stray empty session session_013NEJL2ADRZmTmGqap9Vryt, and the check misses reworded copies.

## Lane 9: survive an account switch

- Goal: waiting-page data and mockups survive a Claude account switch.
- Absorbs: waiting-data-in-repo:handoffs/waiting-data-in-repo.md, mockup-homes:handoffs/mockup-homes.md.
- PRs: none. waiting-data-in-repo head b655208f0. mockup-homes code head f2caab9f, base 74be1279.
- Blocking owner item: owner hold, 2026-11-02 11:00 CST. Draft only. No merge and no batch until the owner says. It also blocks the page:<n> check in fb-1312-1.
- Conflict, origin side: waiting-data-in-repo has no PR. The runner handoff speaks of a PR to hold, but only a branch exists. Mockup-homes lands first. waiting-data-in-repo then rebases onto it, because both edit skills/waiting-page/SKILL.md and lint/test_layout.py.
- First step: bring the owner one item: lift the hold for a draft PR, or keep it. Meanwhile the test-author fixes the item480-a case (use 1item48-a) and adds two ruling cases, then runs `hooks/mutate_guard.py` for mockup-home.
- Open: the roadmap build checks steps of every status. Skip done steps? The lane leans open steps only. The coordinator ruled this on 12:50 CST.

## Lane 10: page title Cockpit, batch 70

- Goal: the page is titled "<repo> Cockpit" (owner 2026-11-02 11:12 CST).
- Absorbs: roadmap:handoffs/triage-claude-settings.md (the republish step), handoff/batch-runner-claude-settings:handoffs/batch-runner-claude-settings.md.
- PRs: #1100 (page title Cockpit), head 6e5e38ce.
- Conflict, origin side: both handoffs say ready. Origin says it is a draft. Mark it ready before batch 70.
- Blocking owner item: none.
- First step: batch runner marks #1100 ready and starts batch 70 with it alone. After it merges, triage republishes the page as "claude-settings Cockpit" and lands the 7 owed debt notes through the next lane that touches notes.md.

## Lane 11: child-repo merges (needs a child batch runner)

- Goal: merge the held PRs in banchi, q_max and joyous without an override.
- Absorbs: handoff/batch-runner-child-repos:handoffs/batch-runner-child-repos.md, banchi handoff/c174:handoffs/c174.md, banchi handoff/o3:handoffs/o3.md, q_max handoff/qmax-rollout-visit:handoffs/qmax-rollout-visit.md, joyous handoff/joyous-gap-and-lint:handoffs/joyous-gap-and-lint.md.
- PRs and heads: banchi #1003 (guard skip for the tree clause), ready, green, 119c2e857. banchi #1005 (CLAUDE.md into rules), draft, f25397f49. q_max #1011 (batch), b602fd459. q_max #1006 7bf8a510e, #1010 df93ef675, #1007 97b3d4693, #1008 331072c26, #1012 c2633701d, all draft. #1007 conflicts with #1010. joyous #68 (pin the tour test clock), ready, ba8fc5f85. joyous #67 (pins to 49a41651), draft, d70be0275.
- Blocking owner items: 166 (banchi #1003, joyous #68 and #67 through lane 5), 154 (q_max #1011), 155 (banchi #1005; options a per-folder AGENTS.md symlinks recommended, b generated root AGENTS.md, c drop the split).
- Conflict, origin side: item 161 is settled (b). Item 154 and 155 are open. Runner 8 is archived. No merger exists for these PRs.
- First step: restart a child batch runner. It reads each PR live, then merges #1003 when item 166 or the nightly main check is green. After #1010 merges, merge main into #1007 (expect conflicts in harness/check-invariants.mjs laneContext, docs/commands.md, docs/debts/notes.md). Delete degen branch pins-d8037a4 after archive. Auto mode refuses gh closes and --base-red-ok, so the coordinator asks the owner's computer for those.
- Size: split one runner per two repos at most (q_max and banchi; degen, joyous and mailaudit while they hold PRs).

## Lane 12: roll-out pins and tci-1

- Goal: every child repo pins claude-settings at 49a41651 (pin lines only), then playwright on ubuntu 26 (tci-1).
- Absorbs: q_max #1012, joyous #67, and the pin steps in the o3, qmax and joyous handoffs.
- PRs: q_max #1012, joyous #67.
- Blocking owner item: 166 (joyous #67 is red only from the tour clock fault on main).
- First step: one pin lane after lane 5 and the red-main fix. One reviewer reads it once. tci-1 waits on a degen lane and on the coordinator. It is not started. After q_max #1007 merges, the cross-repo repo-colours.json accents.q_max change belongs to the coordinator.

## Lane 13: session reach (one plan, one probe)

- Goal: a grant or a message crosses between sessions past the auto-mode classifier and the trust card.
- Absorbs: grant-reaches-lanes:handoffs/grant-reaches-lanes.md, local-session-reach:handoffs/local-session-reach.md.
- PRs: #1049 (grant plan), draft, head 24ec84de. #1051 (reach plan), draft, head 2930e70b. #1051 carries a lane handoff file to drop before merge.
- Blocking owner items: 152 grant-plan-signoff, 153 local-reach-plan.
- Conflict, origin side: item 153 is "last answer b" in triage and "no answer saved" in the lane. Unknown. Read item 153 with ArtifactData before you route it.
- First step: after the owner answers, run one probe lane that answers both unmeasured premises: does a PreToolUse hook allow skip the classifier, and what does the trust card allow for cloud replies. Then build the mod tool.check gate. Keep Design A for grants and the board B as the fallback.

## Lane 14: plans that wait for sign-off

- Goal: keep two plan-only lanes as plans, not sessions.
- Absorbs: prose-homes-shivpedia:handoffs/craft-book.md (PR #1034, plan head f3c93049), plugin-assess-three:handoffs/plugin-assess-three.md (PR #1036, head db760690).
- Blocking owner item: 150 shivpedia-plan-signoff (Q0 to Q4 in the handoff). Plugin trial: 8 scored cases.
- First step: craft-book waits on Q0. Then message lane test-practices-first-principles (draft PR #1028) the path skills/shivpedia/testing/, then brief build lanes from plan section 8, starting with glossary-to-shivpedia. For #1036 fix the title (it says "skip all three"), score the shadow pairs, then settle the Ambition Lenses verdict. #1034 carries a lane handoff to drop before merge.

## Lane 15: close and clean on the owner's computer

- Goal: close replaced PRs and delete merged branches that the cloud refuses.
- Absorbs: runner 7 and runner 8 open questions, item 170.
- Blocking owner item: item 170 (the paste), and the standing grant "Acts the cloud refuses".
- First step: one prompt to a session on the owner's computer: close #1061 as replaced. Only #1061 is needed, since #1097 and #1101 are already closed. Then the item 170 branch delete after archive pushes are checked.
