# Load-balance findings

Source: 25 handoffs read on 2026-11-02, with origin checks at 13:25 CST. Four groups: overlap, conflict, shape, archive practice. Rule changes are proposals only. Each one waits for the owner. A finding marked "needs owner ruling: no" is a process step the coordinator can take under its own grant. The lane plan is in `handoffs/next-coordinator-lanes.md`.

## Overlap

Two or more lanes edit the same file or build the same goal.

### O1. Six lanes edit hooks/guard.py and hooks/mutate_guard.py

- Evidence: other-clone-cd-refuse, branch-cleanup, mockup-homes, tier-boundaries-enforced, refusal-cite-reach and questions-reach-page all list hooks/guard.py or hooks/mutate_guard.py. PR #1070 (questions reach the page) fell out of batch 69 on red checks-mutate-guard.
- Proposal: run them as one guard train, one lane per batch. Order: #1070, other-clone-cd-refuse, branch-cleanup guard slice, mockup-homes, #919 and #1042. Each lane merges main and re-runs mutate_guard first. A new refusal cites its record, because PR #1061 widened the uncited-refusal check.
- Needs owner ruling: no.

### O2. Four lanes edit merge/merge.py

- Evidence: red-main-same-sha-green, no-undo-lane-commits, tier-boundaries #1065 (review record) and refusal-cite-reach (already on main through #1103).
- Proposal: order #1065, then #1099 (lane undo check), then the red-main lane. Each merges main before its checks.
- Needs owner ruling: no.

### O3. Four lanes edit root CLAUDE.md, three edit agents/*.md

- Evidence: #1070 (questions-go-to-owner wording), no-undo (roles-brief-contents), branch-cleanup (reports-batch-pace-numbers, five numbers), child-rules-cite-records. Also rotation-text-current and the drop-ste-name branch edit agents and project-ops text.
- Proposal: one prose lane (lane 7) is the only writer of root rule wording and agents/*.md per batch. Code lanes hand it wording. The owner reads one diff.
- Needs owner ruling: yes. It changes who may edit rule text.

### O4. waiting-page SKILL.md and lint layout tests

- Evidence: mockup-homes says "waiting-data-in-repo also edits waiting-page SKILL.md". Both edit lint/test_layout.py or lint/layout.py.
- Proposal: mockup-homes lands first. waiting-data-in-repo rebases onto it. Treat both as lane 9.
- Needs owner ruling: no.

### O5. docs/debts/notes.md has seven writers

- Evidence: #1070, tier-boundaries, refusal-cite-reach (six notes), other-clone-cd-refuse (two notes), roadmap-live-check-true, trial-tz. Triage owes 7 notes. Two debts wait on #1042 and #1065.
- Proposal: the merge tool orders them and the lane dedupes by id. Triage lands its 7 notes through the next lane that touches the file.
- Needs owner ruling: no.

### O6. Two builds of one goal: PR #1070 and archive/trial-tz

- Evidence: both build the report_guard check for questions-go-to-owner. trial-tz has 11 commits and 6 fixes. trial-lg edits the same file.
- Proposal: #1070 is the only build. Take two open questions from trial-tz into lane 1. Do not open a PR from either trial.
- Needs owner ruling: no.

### O7. Two reach plans turn on one unmeasured fact

- Evidence: grant-reaches-lanes says "unmeasured; may end Design A". local-session-reach says "unknown". Both depend on what the classifier and the trust card allow. Runner 8 was refused even under merge/cloud_allow.json.
- Proposal: merge the two plans (#1049, #1051) into one plan lane and run one probe before any build. Bring the owner one item for items 152 and 153.
- Needs owner ruling: yes. Items 152 and 153 await sign-off.

### O8. Possible helper collision: hooks/local_time.py

- Evidence: trial-tz built hooks/local_time.py. PR #1104 (time zone in every time) is a draft in the same area. Unverified.
- Proposal: name one home for the time helper in a record, and make #1070 import it.
- Needs owner ruling: no.

## Conflict

Two sources disagree. The side origin shows is named.

### C1. PR #1100 ready or draft

- Evidence: runner 7 and triage say ready. gh api pulls/1100 says draft, head 6e5e38ce. The head agrees.
- Proposal: origin is true. Mark it ready before batch 70.
- Needs owner ruling: no.

### C2. PRs #1061, #1097, #1101 "to close as replaced"

- Evidence: runner 7 lists all three. Origin shows #1097 and #1101 closed and merged. #1061 is open. Batch 69 took its head 0e8edd82. Its handoff head fc78547f is a main merge only.
- Proposal: only #1061 needs a close. A session on the owner's computer does it (auto mode refuses gh closes).
- Needs owner ruling: no.

### C3. Item 161 open or settled

- Evidence: joyous-gap-and-lint says "Owner decides". Runner 8 and triage say pick b, no override.
- Proposal: settled, b. Chain: item 166, red-main lane, joyous #68, then #67. Tell no lane to ask again.
- Needs owner ruling: no.

### C4. Item 153 answered or not

- Evidence: triage says "last answer b". local-session-reach says "no answer saved as of 12:53 CST".
- Proposal: unknown. Read item 153 with ArtifactData before routing.
- Needs owner ruling: no.

### C5. trial-lg question open or picked

- Evidence: trial-lg lists options a and b as open. The coordinator handoff says pick a was the owner's of 2026-11-01 16:23 CST.
- Proposal: pick a wins. Add the roadmap step. Check that main 5a5f081e does not already hold the sentence.
- Needs owner ruling: no.

### C6. Owner of session-tiers line 136

- Evidence: rotation-text-current says child-rules-cite-records owns it. That lane's files list does not touch session-tiers.md. #919 edits the same file.
- Proposal: give it to lane 4.
- Needs owner ruling: no.

### C7. waiting-data-in-repo: hold on a PR that does not exist

- Evidence: the runner says "never batch or merge". The lane says no draft PR is open. The page:<n> check (fb-1312-1) waits behind this hold.
- Proposal: bring the owner one item: allow a draft PR now, or keep the hold. The hold then blocks the check only until the draft lands.
- Needs owner ruling: yes.

## Shape

### S1. Guard lanes serialise

- Evidence: see O1.
- Proposal: lanes 1 to 4 form a train with one lane per batch.
- Needs owner ruling: no.

### S2. One merge-tool lane

- Evidence: see O2. no-undo splits cleanly into lint/check_silent_undo.py and a merge.py edit.
- Proposal: lane 5 takes the merge.py edits. Lane 6 keeps the lint half.
- Needs owner ruling: no.

### S3. Items 154, 161 and 166 are one question

- Evidence: all three ask whether a newer green run may clear a red main. Seven PRs in three repos wait: banchi #1003, q_max #1011 (and #1008 inside it), joyous #68 and #67, and the red-main lane. Item 155 gates banchi #1005.
- Proposal: bring the owner one item for 166. Close 154 and 161 into it. Name 155 as a separate item.
- Needs owner ruling: yes.

### S4. Seven sessions ended waiting on the owner

- Evidence: grant-reaches-lanes, local-session-reach, craft-book, joyous-gap-and-lint, o3, waiting-data-in-repo and red-main-same-sha-green. Some waited over 12 hours.
- Proposal: a lane whose only open work is an owner answer finishes to a draft PR plus one page item, then archives. The item carries the resume path. A plan-only lane hands a plan and an item, never a session.
- Needs owner ruling: yes.

### S5. branch-cleanup is three jobs

- Evidence: the Mac delete brief, the agent-branch-push guard and the pace-number wording. The head c2fc5ebf conflicts with main.
- Proposal: restart from three slices (lane 3).
- Needs owner ruling: no.

### S6. One prose lane

- Evidence: rotation-text, drop-ste-name, #1104, the line 136 fix and the Mac brief are Markdown only.
- Proposal: lane 7, one record-writer.
- Needs owner ruling: no.

### S7. Sessions too wide

- Evidence: o3 merged 8 PRs, joyous-gap-and-lint merged 10, runner 8 covered five repos and ended with no merge recorded.
- Proposal: one lane per roll-out step and per repo. One child batch runner for two repos at most. A runner holding a ready green PR it cannot merge hands it to the next runner.
- Needs owner ruling: yes. It sets a lane size.

### S8. Trials are not lanes

- Evidence: trial-lg and trial-tz say "Trial", "no PR". plugin-assess-three attaches a trial to a real plan.
- Proposal: run a trial only with a named comparison. Never rebase or merge one.
- Needs owner ruling: no.

### S9. One pin lane and one tci-1 lane

- Evidence: q_max #1012, joyous #67, banchi and degen pins all move to 49a41651. tci-1 waits on a degen lane.
- Proposal: lane 12. One reviewer, pin lines only, after the red-main fix.
- Needs owner ruling: no.

## Archive practice

### A1. Standing sessions archived at wind-down

- Evidence: session-tiers says "There is no usage limit ... rotates a session only when it goes stale or breaks". Triage and both runners were archived on the owner's one-time order (fb-1231-1) while healthy.
- Proposal: for triage, runners and the arbiter, a wind-down pauses and compacts in place. Archive only when stale or broken. If archived, the coordinator respawns them in the same turn it restarts work.
- Needs owner ruling: yes.

### A2. Triage archived while it is the only page writer

- Evidence: the roadmap-one-writer guard and session-tiers make triage the only writer of the page and the roadmap branch. About 14 owner items are open. Item 155 names triage as owner. #1100 needs a page republish.
- Proposal: never archive triage while it owns open items or an unpublished page change. On respawn, read the live items first and reassign owners. The coordinator rule "triage files it or I decide" needs a live fallback.
- Needs owner ruling: yes.

### A3. A runner's archive drops its notices

- Evidence: runner 7: "lanes not told" of the replacement. "#1098, #1099 lanes sent no head". Runner 8's PRs have no merger.
- Proposal: before a runner is archived, it sends each lane its status, or the coordinator does. A runner's handoff lists PRs closed as replaced.
- Needs owner ruling: yes.

### A4. Lanes ended before the work landed

- Evidence: ten lanes. Examples: red-main (no PR, "pytest and lint not run on final head"), rotation-text (builder never ran), other-clone-cd-refuse (round 3 not started), waiting-data-in-repo (5 red cases), mockup-homes (no PR, no review).
- Proposal: a stop needs a no-loss point: push the head, record the review round and the checks run on it (or "none"), open a draft PR. Respawn at the start of a review round, with the round number in the brief. Re-run lane lint on the moved head.
- Needs owner ruling: yes.

### A5. Respawn loses agent models and clean trees

- Evidence: test-author ran Haiku (rotation-text). Trailers name the wrong model (child-rules). A reviewer with no model field ran Haiku (grant-reaches-lanes). A stale worktree holds 67 staged files (tier-boundaries). Shallow clones give a false off-main (o3, qmax, joyous).
- Proposal: add a respawn checklist line to the brief template: unshallow, remove stale agent worktrees, name each agent's model, push HEAD:<branch>.
- Needs owner ruling: no. Template line only.

### A6. Handoff files ride in lane branches

- Evidence: #1051 and #1034 carry a handoff file. other-clone-cd-refuse says "remove the handoffs/ file before the batch". The drop relies on memory.
- Proposal: lane handoffs live on handoff/<slug> branches, or the merge tool refuses a PR diff that touches handoffs/.
- Needs owner ruling: yes. It adds a merge refusal.

### A7. A trial ends at its report

- Evidence: trial-tz left a stray origin branch questions-reach-page-tests-tests2. trial-lg's next step says check whether the lane is still needed.
- Proposal: a trial pushes once to archive/<name>, reports, and is archived. It is never compacted or respawned. A real run starts as a new lane at round 1.
- Needs owner ruling: no.

### A8. Coordinator handoff drift

- Evidence: the coordinator handoff carries about 58 bare fb ids with no gloss and premises timed hours earlier. Rule speak-cite-id-plus-gloss asks for a gloss.
- Proposal: at each compaction, keep only open ids, re-check premises older than about an hour, and keep the Goal. This handoff keeps every fb id by instruction. The ids have homes, so the next coordinator may prune them.
- Needs owner ruling: no.

## Counts

- Overlaps 8, conflicts 7, shape findings 9, archive findings 8. Total 32.
- Needs owner ruling: yes for O3, O7, C7, S3, S4, S7, A1, A2, A3, A4, A6 (11). No for the other 21.
