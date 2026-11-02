# Lane list for the next coordinator

Base: main `da8d8073`. Each head below comes from the 13:25 CST plan or the 16:xx CST handoff. Read the live head before you act. Lanes are named by branch slug. Order is given in words.

Rules for every lane:

- A lane that edits `hooks/guard.py` or `hooks/mutate_guard.py` joins the guard train, and merges main first. The guard train runs in this order: report-guard slice 2, other-clone refusal, branch cleanup slice 3a, tier boundaries.
- A lane session runs Opus at medium effort. Start it with `/effort medium` alone, then the brief.
- The coordinator briefs each lane once. The batch runner merges it.
- Before the batch takes a lane, the batch runner runs `merge --lane-lint <pr>` on the lane head.
- A lane's handoff lives on `handoff/<slug>`, never in the lane PR.

## Start now (batch 1)

### questions-reach-page-r

- PR #1108 (owner questions reach the waiting page). Head `b0d8b100`. Round 1 review done, by Haiku. The head holds the scaffold fix `03e79cfc`.
- Serves fb-2331-1, fb-2324-1, fb-2326-1 and fb-2334-1 (questions reach the page in the same turn), and item 158.
- Replaces PR #1070, which closes as replaced. Batch #1109 closed earlier: #1108 broke the janitor mutation test. Confirm that test is green on `b0d8b100`.
- Confirm the round-1 reviewer ran at the model `agent-model-cap` gives. The Opus review says a Haiku round 1 falls below the role's model. It flagged #1104 and #1105. If this one does not meet the rule, re-review on Sonnet.
- Blocking owner item: none.

### page-filed-check-r

- Head `b4661d34`. Round 3 review by Sonnet: CLEAR, net value positive. No PR yet. Open a draft PR.
- Serves fb-1312-1 (a writer's filing lands: page item `n` exists in the waiting store), fb-1313-1 (keep the check in `hooks/feedback_guard.py`), and fb-1311-3 (verify each filing on origin or by read-back).
- Hold: fb-1312-1 says build the check after `waiting-data-in-repo` merges. That lane is on owner hold (11:00 CST). Ask the owner on the waiting page before you mark the PR ready. Merge waits on the answer.
- Notes to file, one line each in the notes file: `owner-feedback-inbox.md` lines 121-124 miss one `rev-parse` on a read-back. The word "blocks" is a glossary Not-name.

## Start after batch 1 lands, in this order

### report-guard slice 2

- Goal: the report guard sees every landing tool.
- Work: add LANDING_TOOLS (`gh pr merge`, `gh pr create`, `git revert`, `git cherry-pick`, `delete_file`, `update_pull_request_branch`) with a red test first. Fold in two trial-tz questions: a chat answer clears an item, and a lane sends to its parent.
- Roadmap steps: ask-reaches-writer and option-key-guard-gap.
- Serves owner pick a (2026-11-01 16:23 CST) for LANDING_TOOLS, and the fb-2331-1 chain.
- Blocking owner item: none.
- First step: if the stale mutation still names `roadmap-one-writer` `set_session_tags` in `hooks/mutate_guard.py`, a test-author re-points it at `hooks/own_session.py`. Then run `verdict python3 hooks/mutate_guard.py` in full, run `check_silent_undo --strict`, merge main, and send the head to the batch runner.

### other-clone refusal (other-clone-cd-refuse)

- Goal: guard rule `other-checkout` (`other_checkout_hit` in `hooks/guard.py`) refuses a cd into, or a write into, a separate clone of the same repo.
- Branch head `e46e284e`, base main `62bdb8a6`. No PR.
- Serves: banchi #1003 waits on it. No fb id in the handoff.
- Blocking owner item: none.
- Hazard: agent worktrees share one local branch ref. One agent reverted `guard.py` by mistake (`acd5fb5f`, restored by `d632c8a0`).
- First step: merge main. Review round 3 of 3 (reviewer Sonnet, xhigh), with the net-value test against main. Run lane lint, open a draft PR, and send the number, head and verdict to the batch runner. Remove the `handoffs/` file before the batch. Push with `git push origin HEAD:other-clone-cd-refuse`.

### branch cleanup (branch-cleanup)

- Goal: `worktree-agent-*` branches never reach origin. The Mac delete brief exists. The branch count joins the pace numbers (fb-1041-3).
- Branch head `c2fc5ebf`. It conflicts with main in `hooks/guard_push_delete.py`. No PR.
- Blocking owner item: item 170 (branch-delete-list), for the Mac half.
- Start fresh from three slices, not a merge:
  - 3a: guard rule `agent-branch-push` (`hooks/guard_push_delete.py`, `hooks/guard.py`; decision `agent-branch-never-pushed`). Keep main's `_push_parse`, `_push_dest` and `push_destinations`. Add `AGENT_PUSH_RULE` in `push_verdict`. It joins the guard train.
  - 3b: the Mac deletes brief. Record-writer, Markdown only.
  - 3c: adds the branch count, which makes five pace numbers in `reports-batch-pace-numbers`. It joins the prose lane.
- After the merge, delete branches `branch-cleanup-records` and `branch-cleanup-tests`.
- Open question for the owner: an agent with no brief branch keeps its commits local only. The owner's 10:41 CST ruling reads as yes. Confirm it.

### tier boundaries (PRs #1065, #919, #1042)

- Goal: a coordinator-scope guard and a review record on each PR (owner, 2026-10-31 15:31 CDT).
- #1065 (review record): draft, head `42fdc267`. It needs main merged. It conflicts in `merge/merge.py`.
- #919 (`own_tier_tagged`): head `568e606e`. Held by the coordinator (set 10:17 CST).
- #1042: head `49adc89e`. It contains #919. Held.
- Blocking owner item: none. The holds are the coordinator's.
- First step: #1065. Merge main, resolve `merge/merge.py`, run checks, post the review record for the new head, and send the head to the batch runner. Then #919. Finish its open items 2 to 4 (`docs/decisions/session-tiers.md` line 81 and its Limits section; the cost line near line 83; `notes.md` line 829). Run all checks. Then a round 3 reviewer (Sonnet) with the net-value test.
- This lane owns the "Open" section of `session-tiers`, which waits on the limit values (item 53).
- Unstarted debts that wait: `session-start-handoff-text` (waits on #1042) and `mcp-merge-matcher-missing` (waits on #1065).

### lane undo check (PR #1099)

- Goal: a builder cannot undo earlier work of its own lane (fb-1041-1). One excuse line, Drops-lines (item 165, pick a). The sitting ruling 13a lands here: the check reads two shapes.
- PR #1099, draft, head `43dfc3b0`.
- Blocking owner item: the narrowing from "any line" to two shapes needs the owner's grant. It is pending (coordinator ruling 2026-11-02 11:26 CST). The net-loss dial (3 lines or 6) needs the owner too.
- First step: re-measure the sweep. At `43dfc3b0`, 16 of 31 batches are red. Bring the narrowing to the owner once, with that measured sweep, under `outcomes-stale-decision-protocol`. Pick the dial with the owner. Verify that `43dfc3b0` excuses. Run `merge/test_merge.py`. Review round 2. Run `merge --lane-lint 1099`, then send it to the batch runner.
- Merge order in `merge/merge.py`: tier boundaries first, then this lane, then red-main.

### red-main same-sha green

- Goal: the merge tool lets a newer green run on the same or a newer main sha clear a red main. The lane also holds the claim-revert excuse (merge half of `no-undo-lane-commits`).
- WIP head `64cf676e`. No PR.
- Blocking owner item: 166 (newer-run-clears-red). Do not merge the red-main part before the owner rules. Items 154 and 161 close into 166.
- Chain: item 166, then this lane, then joyous #68, then joyous #67.
- First step: on `64cf676e`, run `pytest merge/test_merge.py`, `ci-job checks --lint` and `merge --lane-lint`. After the owner rules, either rewrite the cross-group bullet of `no-merge-onto-red-main` in place, or archive the lane if the answer is "change nothing". Then open a draft PR and run a net-value review (Sonnet).

### usage tally text (rotation-text-current)

- Goal: text that tells sessions to rotate by a self-reported usage tally goes. The coordinator reads use with `get_session` (fb-1540-1, item 169 pick a). No usage limit (item 109 pick b).
- Stale text: `skills/project-ops/SKILL.md` lines 3 and 17; `README.md` line 289; `docs/catalog.md` line 79; `operating-model.md` lines 70-71.
- Branch `rotation-text-current`, head `092b733f`. No PR. The test-author work is done (`9915deb4`, red on `74be1279`).
- First step: the builder edits the stale lines above, the templates `operating-model.md` and `roster.md`, and README line 289. Then it runs `lint/hook_catalog.py`.
- Open: `home`, `degen` and `mailaudit` need briefs that re-paste the rotation section. None is written.
- Blocking owner item: none.

### STE follow-ups (drop-ste-name)

- Goal: finish dropping STE as a named standard (fb-1321-1, fb-1322-1). The record landed in #1110.
- Follow-ups: rename the lint, the action and the CI step. Child repos' `CLAUDE.md` files name STE. Ask the owner before you touch another repo.
- Delete `lint/ste_gate.py` and `lint/md_sweep.py`. Both still sit on main and are unwired. Decision `ste-guard-fixes-not-nags` says they are deleted.
- Blocking owner item: none.

### retired names

- Goal: the retired names go. The rulings behind them say that a builder is an agent only, that the page writer is triage (else the coordinator), and that a lane is the unit of work (fb-1402 range, the terms rulings).
- Still in use:
  - "waiting-page writer": `skills/roadmap/SKILL.md` lines 7 and 39; `skills/project-ops/SKILL.md` line 65; `operating-model.md` line 25; `skills/waiting-page/SKILL.md` line 498.
  - "bridge session": `hooks/guard_merge.py` line 672.
  - A script called "builder": `skills/roadmap/build.py`.
- Blocking owner item: none.

### session-start merge line

- `hooks/session_start.sh` line 18 tells every session to hand its merge to the batch runner. That is wrong under fb-1538-1. A session the owner started merges its own PR under the repo's grant. A coordinator-started lane hands off.
- Blocking owner item: none.
- First step: write a red test in `hooks/test_session_start.py` first. Then fix the line.

### building-guard-needs-incident gloss

- Fix the old gloss in `merge-lock.md` line 61 and `env-file-stays-unread.md` line 27. `notes.md` line 1159 cites by line. Cite by id instead.
- Serves the sitting rewording of `building-guard-needs-incident`. The handoff does not map that ruling to one fb id (fb-1402 to fb-1429 range).
- Blocking owner item: none.

### auto-mode and compliance text

- `auto-mode-owner-acts.md` lines 23 and 55 say "no coordinator started". Make them match `session-tiers`, section "Who starts which session".
- The compliance-defined grant bullet has no check. Add a check, or mark it process-only.
- No fb id in the handoff.

### Sonnet is the default (agent-model-cap)

- `agent-model-cap.md` line 5 says "Sonnet is the default", against its own table. Fix the prose to match the table. Rename the anchor `roles-sonnet-is-the-default`. In `banchi`, `CLAUDE.md` line 372 becomes a pointer.
- Serves fb-1600-1 (the misread cause).
- Blocking owner item: none.

### timing tests

- Serves fb-1627-2.
- Write a decision record first. Logic tests use fake clocks. Real-time checks run only on a quiet runner, with a threshold from measured variance, or on counts.
- Seeds: degen `one-xcode-build-at-a-time`; joyous #68 (pin the tour test clock); mailaudit `ci-runs-in-utc`; `machine-load-brake`.
- Blocking owner item: none.

### CI wall time

- Serves fb-1723-1 (owner, 17:23 CST). A full run takes 37 to 42 minutes, from 4 main runs on Nov 2.
- The `checks-macos` "Guard fixture suite" runs 1006 s whole. Linux and Windows shard it. `shell-macos` used its full 18-minute cap.
- Plan, per `ci-hygiene` step 15: shard the Mac guard suite. Measure the slowest steps of the 134-step `checks` job. Split that job. Report wall time before and after.
- Blocking owner item: none.

### artifact lane

- Serves fb-1456-1, fb-1458-1, fb-1458-2 and fb-1512-1 (git is every artifact's home; the copy lives on the roadmap branch). It also serves fb-1509-1 (degen PR #324, duplicate export: degen moves its copy to the roadmap branch), and fb-1510-1 (the designer-gap causes fold in here).
- Work: designer-gap fixes, degen's copy move, scan false alarms, and the 14 step links.
- The designer-gap notes sit in the previous coordinator's scratch space. Copy them into git on this lane's branch first.
- Blocking owner item: none.

### one-home and cite checks

- One-home build: PR #1106 (fb-1338-1, mechanize one-home-per-capability both ways). Roadmap step `one-home-check`.
- Owner-cite check: the list names it "11d". Session-tiers uses 11d for the ruling push. Confirm the id before you brief it.
- A6: the check that refuses a `handoffs/` file in a lane PR. The Opus review (13:50 CST) marks it stray: no incident. The owner decides whether it stays.

### drift lanes and child-repo pointers

- Drift lanes: degen 1 and mailaudit 2, on branch `audit/drift-map` (head `4d0d069c`).
- Child-repo pointer lanes: the coordinator may run them in any child repo (fb-1543-1).
- The citation check that landed with #1098 misses reworded copies. One line in the notes file.

### child-repo merges

- Restart a child batch runner. Runner 8 is archived. No merger exists for these PRs.
- banchi #1003 (guard skip for the tree clause): ready, green, head `119c2e857`. Blocked by item 166, or by the nightly main check going green. It waits on the other-clone refusal.
- banchi #1005 (CLAUDE.md into rules): draft, head `f25397f49`. Blocked by item 155 (banchi-codex-rules). Options: a (per-folder `AGENTS.md` symlinks, recommended), b (generated root `AGENTS.md`), c (drop the split).
- q_max #1011 (batch): head `b602fd459`. Blocked by item 154 (qmax-1011-batch).
- q_max #1006 (`7bf8a510e`), #1010 (`df93ef675`), #1007 (`97b3d4693`) and #1008 (`331072c26`): all draft. #1007 conflicts with #1010. After #1010 merges, merge main into #1007. Expect conflicts in `harness/check-invariants.mjs` (`laneContext`), `docs/commands.md` and `docs/debts/notes.md`.
- joyous #68 (pin the tour test clock): ready, head `ba8fc5f85`. Item 161 is settled (pick b, no override). It waits on the merge-tool fix in the red-main lane.
- joyous #67 (pins to `49a41651`): draft, head `d70be0275`. Red only from the tour clock fault on main (item 166).
- Auto mode refuses `gh` closes and `--base-red-ok`. The coordinator asks a session on the owner's computer for those.
- After q_max #1007 merges, the cross-repo `repo-colours.json` change for `accents.q_max` belongs to the coordinator.
- Delete degen branch `pins-d8037a4` after it is archived.

### child-repo pins

- Every child repo pins claude-settings at `49a41651`, pin lines only.
- PRs: q_max #1012 (`c2633701d`, draft) and joyous #67.
- Blocking owner item: 166. Start after the red-main lane's fix. One reviewer reads it once.
- Playwright on Ubuntu 26 is cut.

### session reach

- Goal: a grant or a message crosses between sessions past the auto-mode classifier and the trust card.
- PRs: #1049 (grant plan, draft, head `24ec84de`) and #1051 (reach plan, draft, head `2930e70b`). Merge the two plans into one. #1051 carries a lane handoff file to drop before merge.
- Blocking owner items: 152 (grant-plan-signoff) and 153 (local-reach-plan). Item 153 reads differently in triage and in the lane. Read it with ArtifactData before you route it.
- First step: after the owner answers, one probe lane answers two unmeasured premises. Does a PreToolUse hook allow skip the classifier? What does the trust card allow for cloud replies? Then build the `mod tool.check` gate. Keep Design A for grants. The board (B) is the fallback.

### plans waiting for sign-off

- No fb id. These are plans only, with no session until sign-off.
- craft-book: PR #1034, plan head `f3c93049`. Waits on item 150 (shivpedia-plan-signoff, Q0 to Q4). It carries a lane handoff file to drop before merge.
- plugin-assess-three: PR #1036, head `db760690`. Fix the title, which says "skip all three". Score the shadow pairs. Settle the Ambition Lenses verdict. The plugin trial has 8 scored cases.
- Message lane test-practices-first-principles (draft PR #1028) the path `skills/shivpedia/testing/`. Then brief the build lanes from plan section 8, starting with glossary-to-shivpedia.

### account switch (owner hold)

- Goal: waiting-page data and mockups survive a Claude account switch.
- Branches: `waiting-data-in-repo` (head `b655208f0`, no PR), and `mockup-homes` code (head `f2caab9f`, base `74be1279`).
- Blocking owner item: owner hold, 2026-11-02 11:00 CST. Draft only. No merge and no batch until the owner says. The hold also blocks the page-item check in fb-1312-1.
- Ask the owner one item: lift the hold for a draft PR, or keep it.
- Meanwhile the test-author fixes the `item480-a` case (use `1item48-a`), adds two ruling cases, and runs `hooks/mutate_guard.py` for `mockup-home`.
- `mockup-homes` lands first. Then `waiting-data-in-repo` rebases onto it. Both edit `skills/waiting-page/SKILL.md` and `lint/test_layout.py`.
- Settled (12:50 CST): the roadmap build reads open steps only.

### close and clean on the owner's computer

- Standing grant "Acts the cloud refuses" (owner, 2026-10-30 16:20 CDT): a session on the owner's computer may set branch protection to the shared form, delete merged branches, and close PRs the coordinator names as replaced or empty. Any other act needs the owner's grant.
- Close as replaced, once each has merged or been replaced: #1070, #1104, #1105, #1107, #1098 and #1100. PR #1061 is already closed (13:38 CST).
- Then delete the item 170 branches, after archive pushes are checked. Item 170 is a paste for the owner's Mac.

### deep audit

- Run 1 runs in the previous coordinator's session. Plan: `docs/plans/deep-audit.md` on branch `deep-audit-plan` (head `f0c1e4e6`).
- Run 2 is not recorded as started. When Run 2 ends, Run 1's findings and its one-home lanes land in the handoff.
- Owner asks: fb-1602-1, fb-1604-1, fb-1605-1, fb-1605-2 and fb-1702-1. `opus 24h` until 2026-11-03 16:05 CST.
