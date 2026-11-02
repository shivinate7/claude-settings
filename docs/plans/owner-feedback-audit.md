# Feedback audit: 234 owner items, re-read Nov 1 after 19:23 CST

This record holds the audit of the owner's feedback. It has 237 F rows: F1 to F232 and F248 to F252, with F233 to F247 unassigned. Five rows, N1 to N5, record rulings found after the read. Section 2 lists each change made after the read, with its evidence.

Glosses: each id carries a short gloss where it first appears in a section. Section 7 glosses every row id and every PR, step and decision the rows cite.

Owner rules that govern this record (Nov 1, 18:48 to 18:50 CST): "record all of it, show me where we fell short, and how we intend to get back on course"; "nothing in that report should be ommitted or marked superceded unless oyu can trace that supercession exactly back to something i stated. dont be easy on yourself."

## 1. Unknown reads and gaps

- F233 to F247 (unassigned row numbers): 15 numbers. The merged list said F1 to F247, but its table stopped at F229. The raw-item check found three points with no row of their own. They are F230 to F232 (section 7e). The other 15 numbers stay unassigned, and their state is unknown.
- F39 (earlier session report), F82 (waiting-page width), F84 (Oct 29 re-save), F93 (deleted page), F251 (phone screenshots) and F252 (debug-port question) are unknown. Section 7 gives the reason for each.
- F138 (the "137 a" pick): delivery to the lane is not verified.
- Not re-read: the triage "Answered" rows, such as F30, F85 and F99. No triage transcript was in scope for them.
- F134 and F135 (item 127) and F142 (items 117 and 118) are closed on the page. They are not matched to a pull request.
- Bare numbers name more than one repo. #1001 is a claude-settings draft (ci-job-caps stopgap, F119). It is also the q_max pull request that F44 cites. #995 and #997 are in the same position. #1003 is a banchi pull request (F43, F46) and a claude-settings draft (section 2c).
- The owner words for F1 to F229 are not in this record. The merge source holds them, and that file is not tracked. Copying them in is open work (section 6).
- Sources and gaps: section 8.

## 2. Changes after the read

### 2a. Verified state changes

- **F171 (merge-grant switch, owner item 85 c, Oct 30 15:06 CDT). Filed, not started, now LANDED.** Commit 12760618 (Oct 30) is an ancestor of origin/main. merge/merge.py refuses a cloud merge when merge.standingGrant is false (line 2477). Class StandingGrantSwitch exists in merge/test_merge.py. Step merge-grant-switch (switch step) now says done. The step note and the coordinator report a pass at a 19:36 CST lane check. This record did not run the tests.
- **F47 and F50 (all-repos grant). Promised, not filed, now IN FLIGHT.** Draft PR #1007 (all-repos grant draft, head pr-acts-grant, opened 19:33 CST) holds the grant. It is not merged. Section 4, item 1, has the details.
- **Batch 59, PR #992 (batch 59 integration PR). Merged at 19:31:46 CST as main 55b27ac2.** The merge commits for PR #972, #973, #975, #976, #978, #980 and #987 are in it. Rows that waited on those lanes moved to LANDED: F48 (remote tools allow list), F79 (none-with-note rule), F80 (feel-fix device check), F168 (stale prose rule) and F172 (session turn limit). F133 (blind Opus model review) stays LANDED, but its "open draft" evidence was out of date. Three lanes stayed out and are still open drafts: PR #974, #979 and #984.
- **F46 and F43 (item 143 b; banchi item 99).** The draft tied the other-checkout lane to F43. The owner's "143 b" is in F46. Branch other-checkout-cd-gap is on origin with three commits, the last at 19:40 CST. It has no PR. Whether the lane is running is not verified. F43 is the banchi item 99 follow-on. Its banchi PR #1003 (guard-shell tree clause) is still an open draft.
- **F119 (ci-job-caps question asked again). Draft PR #1001, opened 19:23 CST.** The draft said the time-pinned lane had started. That is not verified. No branch or PR named time-pinned-tests-go exists. Step time-pinned-tests-go (time-pinned tests step) is todo on origin/roadmap.
- **F252 (debug-port question, Nov 1 06:52 CST). LANDED, now UNKNOWN.** The owner words were not recovered. The answer (F214, debug-port answer) and the guard drop (PR #959, batch 54 r2) are real. They do not show that the owner's question was answered.
- **F248 to F250 (item 128, branch deletes). Verified.** Branches lane/impeccable-4.8.0, lane/drop-debug-port-ask, lane/fd-float-cc-newest and lane/cc-pin-2.1.311 are absent on origin.
- **N1 to N5 (rulings after the read). Added as rows.** The 19:19 and 19:23 CST rulings are quoted in draft PR #1007 (N1 to N4). The 19:27 CST ruling behind claude-settings draft PR #1003 has no owner words in the inputs (N5, unknown).
- **Rows still in flight.** F79, F80 and F168 are LANDED because their lanes are on main. Their roadmap steps are still doing (origin/roadmap), and each row names its step.

### 2b. Corrections to the draft

- Step names. "tci-9" has no step file. Use tci-9-live-protection (branch-protection step). "tci-11" is tci-11-qmax-shards (q_max shards step). "tci-5" is tci-5-platform-tested (platform test step). "tci-6" is tci-6-mutation-replay (mutation replay step).
- stale-note-recheck is the head branch of PR #988 (roadmap dated-claims check). It is not a step.
- The draft said the q_max decision ci-spend-gate exists nowhere. That was wrong. It exists on q_max main (strict pass).
- The checks in section 6 are proposals. No step file exists for them.
- Shortfall 3 (F171): the draft read the step status, not the code.

### 2c. Changed after the read, not applied to states

The update instruction limits state changes to the ones above. These rows now have stale text. Their states stay as they were.

- F150 (ponytail on the desktop app): step ponytail-local-still-on (ponytail on-device step) is done on origin/roadmap. The row says todo.
- F76 (repeat detection): step feedback-repeat-detect (repeat detect step) is doing. The row says todo.
- F78 (one inbox per repo): step one-inbox-per-repo (one inbox step) is doing. The row says todo.
- F106 (newer questions rise): step page-stale-asks-sink (stale asks step) is doing. The row says todo.
- F177 (handoff read before write): step handoff-read-before-write (handoff read step) is doing. The row says todo.
- F178 (compaction carry watch): step compaction-carry-watch (compaction watch step) is doing. The row says todo.
- F100 (parked items): draft PR #1005 (waiting page: unpark and drop) opened after the read.
- F180 (idle compaction): draft PR #1002 (idle-resume-compacts decision) opened after the read.
- Claude-settings draft PR #1003 (idle compaction off) sets idle compaction off. Its title cites an owner ruling at 19:27 CST. The owner words are not in this record's inputs, and no row holds the ruling. The ruling needs a row.

## 3. Counts after the changes

| State | Rows |
|---|---|
| LANDED | 172 |
| IN FLIGHT | 40 |
| FILED NOT STARTED | 7 |
| UNKNOWN | 6 rows |
| NOT OWNER WORDS | 4 |
| SUPERSEDED | 1 |
| CONTRADICTED | 2 |
| DROPPED | 5 |
| PROMISED NOT FILED | 0 |

The 237 F rows total 237. The draft counted 164 landed and 5 unknown before the first update. Five more rows, N1 to N5, record post-read rulings: four IN FLIGHT and one UNKNOWN.

## 4. Where we fell short (worst first)

1. **F47 and F50 (all-repos grant; allow-list complaint). Promised, now in a draft PR.**
   - Owner, Nov 1 17:37 CST, relayed by the coordinator: "YOU HAVE EXPLICIT APPROVAL FOR ANY AND ALL REPOS YOU WANT OF MINE TO MARK PR READY, MERGE, REVIEW, ETC." <!-- ste-disable-line STE011 --> The coordinator's relay is not verbatim in the transcript read.
   - F50, the allow-list complaint, is the owner's view of the same gap: "IS IT ALSO REALLY DUMB THE ALLOW LIST WAS SO RIGID THAT IT BLOCKED THIS."
   - The owner also said that earlier asks were ignored (F49, auto-mode owner-acts decision).
   - Now draft PR #1007 (all-repos grant draft) holds the grant text. It quotes the 17:37 CST grant and the owner's 19:19 and 19:23 CST rulings. It is not merged.
   - The standing grants in .claude/CLAUDE.md do not carry it. The "Owner PR Housekeeping" allow in settings.json is not widened on main.
   - Cause: the session asked for the owner's typed word after he had typed it, and filed nothing. The draft PR is the first filing.
2. **F113, F117, F118, F119 and F159 (settled questions asked again). In flight.**
   - Owner: "WHERE IS THE FUCKING ADVISOR" (18:45), "so many memory issues" (18:39), and item 133 asked a third time.
   - The question judge landed (PR #956 and PR #961). The check that searches past rulings (step question-checks-past-rulings, past-rulings check step) is doing. It has no PR.
   - F119 is also a false claim. Sessions said ci-job-caps was rewritten under test-strategy-reset. That is still false on main. ci-job-caps was last touched Oct 28.
   - Draft PR #1001 (ci-job-caps stopgap), opened 19:23 CST, rewrites ci-job-caps for the owner's 18:44 ruling. It lists an open clash with the kept rule "a cap rises only with a measured figure".
   - Step time-pinned-tests-go (time-pinned tests step) is todo. Its "why" quotes the owner's 18:44 words.
3. **F171 (merge-grant switch, owner item 85 c). Corrected: landed.**
   - The draft listed this as filed, not started. That was a reading error. The draft read the step status, not the code.
   - Commit 12760618 refuses a cloud merge when merge.standingGrant is false. It is on origin/main.
   - The step was set back to todo at 18:03 CST because no lane was live. Step merge-grant-switch (switch step) now says done. Its lane session started at 19:30 CST.
4. **F155 (refresh the ci-hygiene skill in every repo, Oct 30 15:08 CDT). Filed, not started.**
   - The skill half merged in PR #923 (batch 40 integration PR).
   - No per-repo fix lane started. Step ci-hygiene-refresh (ci-hygiene refresh step) is todo.
   - Cause: the lane stopped after the first half.
5. **F36 and F58 (shared branch protection). Filed, not started.**
   - The owner's rule: the same required checks in every repo.
   - Live read of degen main: check all-jobs-passed, with strict true. The shared form is strict false (decision main-branch-protection).
   - Live read of q_max main: HTTP 404, not protected.
   - The decisions exist. Protection is not applied. Step tci-9-live-protection (branch-protection step) is todo. No step file named tci-9 exists.
6. **F6, F7, F220 and F224 ("it needs to be like an actual fix", Oct 31 15:32 CDT). In flight, stalled.**
   - Draft PR #919 (guard for coordinator scope) had been a draft for about 23 hours at the read. It is not in batch 59.
   - F220 (item 113 a) waits on PR #919.
   - F224, the guard log the owner asked for, is not in PR #919 yet.
   - Step tier-boundaries-enforced (tier boundary step) is doing.
7. **F21, F38, F34 and F37 (child repos catching up). Asked twice.**
   - Step child-repo-gap (child-repo gap step, doing since Oct 29) and step r5 (child repo copies step, doing).
   - Steps r6 (project way step), one-check-other-repos (rollup check step), c91 (iOS standard step) and c196 (Mac load step) are todo.
   - Compliance-check is not done.
8. **F19 and F23 (roadmap out of step with live work). In flight, still broken.**
   - The draft counted nine todo steps that had an open PR. Two of those PRs, #980 and #987, merged in batch 59. Several steps moved to doing after the read (section 2c).
   - Eight todo steps say "Ready: no open question" but have no lane.
9. **F188 and F190 (the trust error). In flight.**
   - F188: "no permission rule can lift it" was reported as an answer. It is an inference. The docs are silent (coordinator transcript, chunk 3, line 314). The owner asked for permissions to be added, and none were. Only the one-way pc-bridge workaround exists (F189, pc-bridge trust test session).
   - F190: the docs research is back and says nothing on the trust error. The coordinator's question about the owner's plan is unanswered. No step exists.
10. **F46 and F43 (item 143 b; banchi item 99).**
    - Page item 143 is open with no recorded answer. The owner answered "143 b" at 17:25 CST.
    - Branch other-checkout-cd-gap (other-checkout guard lane), which builds the 143 b guard, has three commits on origin. It has no PR.
    - F43: the owner finished item 99 at 16:32 CST. Banchi PR #1003 (guard-shell tree clause) is still an open draft.
11. **F138 (the "137 a" answer, 18:39 CST).**
    - It is not on the page. Item 137 still shows the 17:25 note and is open.
    - Step one-model-rule (model rule step) was last updated 16:53 CST, before the answer. It still says it waits on the owner for item 137.
    - Only the coordinator's own line (chunk 3, line 474, "Sent your item 137 pick (a)") says the pick reached the lane. Delivery is not verified.
12. **F45 and F150 (answers the owner already gave).**
    - Item 138 is still open after "138 done" and the degen PR #313 merge (degen repo PR, merged).
    - Step ponytail-local-still-on (ponytail on-device step) was todo at the read, after "140 done". It is done on origin/roadmap now (section 2c).
13. **F106 and F105 (the waiting page). Each said twice ("i said already").**
    - Newer questions should rise and stale ones should sink. Draft PR #997 (waiting page: stale asks sink) opened at 19:10 CST. Its step, page-stale-asks-sink, is doing.
    - Items are checked when written. Draft PR #985 (waiting-page pictures check) is open. Its step, page-item-checked-at-write, is doing.
14. **F100 and F107 (parked items and the ask box). Filed, not started.**
    - Step page-parked-actions (parked items step) is todo. Draft PR #1005 (waiting page: unpark and drop) opened after the read.
    - Step page-ask-box (ask box step) is todo, with no PR.
15. **F158 (each platform names where it is tested).** Step tci-5-platform-tested (platform test step) is todo.
16. **F163 (q_max in 12 test groups).** Step tci-11-qmax-shards (q_max shards step) is doing. The q_max record docs/decisions/ci-spend-gate.md (D-718, q_max CI spend decision) is on origin/main (commit e8f990272). The draft's claim that it exists nowhere was wrong.
17. **F123 (the q_max question re-posed).** The coordinator re-posed it with option d. The owner picked 12 groups. The coordinator reports "your 18:43 CST ruling". That is relayed, not verbatim. Step tci-11-qmax-shards (q_max shards step) is doing.
18. **F20 (the refusal note).** Draft PR #979 (auto-mode refusal note) was dropped from batch 59 because a form check was red. No step exists for it.
19. **F31, F70, F17 and F28 (dropped or contradicted).**
    - F31 (contradicted): item 100's grant lives only in a handoff. The mandate says a chat grant must land in CLAUDE.md or the merge tool's config.
    - F70 (dropped): "never judge something broken without asking" stayed only as a handoff premise.
    - F17 (contradicted): by the session's own report, triage wrote the freeze record after PAUSE. No pause record is on main.
    - F28 (dropped): "org instructions are often outdated" has no home.
20. **F88, F122 and F203 (dropped).**
    - The grey Send button and "failed to fetch" got no diagnosis.
    - The "hallucination" was answered with an apology only.
    - The "I'm at my computer" offer got no reply.
21. **F173 (superseded on a conditional answer).**
    - The page item 109 answer (Nov 1 17:56 CST) is choice b, with the note "I lean towards B if it works and maybe somehow log to see if i should revisit".
    - Option b is "No limit; let compaction and the handoff rewrite carry the session".
    - The record change sat in draft PR #978 (session turn limit lane). PR #978 merged in batch 59 (commit c76a3447 on main). The draft said main still carried the tally limit. That is out of date. Whether main's code still holds the limit is not checked here.
    - The owner's condition, "if it works", is not checked.
22. **Work that waited on batch 59 or a draft PR. In flight.**
    - Feedback inbox and records: F76 and F77 (draft PR #999, repeat detect), F78 (draft PR #983, one inbox per repo), F81 (draft PR #989, records-first close). F48, F79 and F80 landed in batch 59.
    - Models, tests and lint: F120 (draft PR #995, glossary meets owner), F132 (draft PR #993, brief-marker scanner), F160 (draft PR #996, mutation engine), F165 (draft PR #998, comment check). F168 landed in batch 59.
    - Stale prose and session limits: F172 landed in batch 59 (PR #978).
    - Handoff and compaction: F177 (draft PR #994, handoff read guard), F178 and F183 (draft PR #986, compaction carry watch), F179 (draft PR #994 and held PR #982, handoff checkpoint), F180 (draft PR #1002), F182 (held PR #982).
23. **Unknown, with no evidence beyond a session's word or a read that could not run.** F39, F82, F84, F93, F251 and F252, plus F233 to F247 (15 numbers, unassigned).
24. **Items the owner raised that landed late or by his own act.** F248 to F250 (item 128, the delete of three merged branches) were done by the owner's own pasted PowerShell run (Nov 1 16:23 CST). Item 128 closed at 16:34 CST. The four branches are absent on origin. F252 (the debug-port question) moved to unknown (section 2a).

## 5. Patterns

| # | Root cause | Items it explains |
|---|---|---|
| P1 | The roadmap and the page lag behind the real state. An answer or a merge happens, but the step or the item does not change. | 13: F23, F24, F45, F46, F76, F78, F79, F80, F106, F138, F150, F177, F178 |
| P2 | Ready work is not started, and draft PRs stall. The flywheel does not turn. | 16: F6, F7, F19, F21, F34, F36, F37, F38, F43, F58, F100, F107, F155, F158, F220, F224 |
| P3 | A ruling or a grant stays in chat or a handoff, or a session claims a home that does not exist. | 8: F17, F20, F28, F31, F47, F50, F70, F119 |
| P4 | Questions are not checked against past rulings, so settled rulings are asked again. | 8: F113, F117, F118, F119, F122, F123, F159, F162 |
| P5 | Batches drag. Batch 59 merged at 19:31 CST with seven lanes. Three lanes stayed out (#974, #979, #984) for form reds that a local lint would catch. The rows still in flight mostly sit on a draft PR or on a step that is still doing. | 40 in-flight rows |
| P6 | Owner reports leave no trace. A session gives no proof that a claimed act happened, or it states an inference as an answer. | 13: F28, F39, F82, F84, F88, F93, F94, F122, F188, F189, F190, F203, F251 |

F171 left P2 after verification. Its code landed on Oct 30. F163 is not in P3. Its cited record exists.

## 6. How we get back on course

One line per shortfall, in the same order as section 4. Each line names a step, a PR or a lane that exists on origin. "No owner yet" means no step, PR or lane closes it.

1. F47 and F50 (all-repos grant): draft PR #1007 (all-repos grant draft). It closes when it merges. Its merge needs a named owner act or the standing grant.
2. Repeat questions (F113, F117, F118, F119, F159): step question-checks-past-rulings (past-rulings check step, doing, no PR). For F119, draft PR #1001 (ci-job-caps stopgap) and step time-pinned-tests-go (time-pinned tests step, todo).
3. F171 (merge-grant switch): none needed. Landed in commit 12760618. Step merge-grant-switch (switch step) now says done.
4. F155 (ci-hygiene refresh): step ci-hygiene-refresh (ci-hygiene refresh step, todo) for the per-repo half. No lane.
5. F36 and F58 (shared branch protection): step tci-9-live-protection (branch-protection step, todo). No lane.
6. F6, F7, F220 and F224 (tier boundary guard): draft PR #919 (guard for coordinator scope). The guard log for F224 has no owner yet.
7. F21, F38, F34 and F37 (child repos): steps child-repo-gap and r5 (doing). Steps r6, one-check-other-repos, c91 and c196 (todo) have no lane.
8. F19 and F23 (roadmap lag): steps roadmap-live-check-true (live-check step) and roadmap-one-writer (writer step), both doing. Step page-ruling-reaches-step (page ruling step, doing, with draft PR #981).
9. F188 and F190 (the trust error): no owner yet.
10. F46 and F43 (item 143 b; banchi item 99): branch other-checkout-cd-gap (no PR) for item 143 b. Banchi draft PR #1003 for item 99. No owner yet for the missing page answer to item 143.
11. F138 (the "137 a" pick): step one-model-rule (model rule step, doing) must confirm delivery. No owner yet for that check.
12. F45 and F150 (answers already given): no owner yet for item 138. Step ponytail-local-still-on (ponytail on-device step) is done.
13. F106 and F105 (waiting page): draft PR #997 (stale asks sink) with step page-stale-asks-sink (doing), and draft PR #985 (waiting-page pictures check) with step page-item-checked-at-write (doing).
14. F100 and F107 (parked items, ask box): step page-parked-actions (parked items step, todo) with draft PR #1005. Step page-ask-box (ask box step, todo) has no PR.
15. F158 (platform test homes): step tci-5-platform-tested (platform test step, todo).
16. F163 (q_max in 12 groups): step tci-11-qmax-shards (q_max shards step, doing).
17. F123 (q_max question): step tci-11-qmax-shards (q_max shards step, doing).
18. F20 (refusal note): draft PR #979 (auto-mode refusal note). No step exists. No owner yet.
19. F31, F70, F17 and F28 (grants and homes): F31 has draft PR #1007, which writes the grant to a decision and to settings.json. A CLAUDE.md line has no owner yet. F70, F17 and F28: no owner yet.
20. F88, F122 and F203 (dropped replies): no owner yet.
21. F173 (tally limit): PR #978 merged. The owner's condition ("if it works") has no owner yet.
22. Waiting work: draft PR #999 and step feedback-repeat-detect (repeat detect step, doing) for F76 and F77. Draft PR #983 and step one-inbox-per-repo (one inbox step, doing) for F78. Draft PR #989 and step lane-closes-after-records (records-first close step, doing) for F81. Draft PR #995 and step glossary-meets-owner-halfway (glossary step, doing) for F120. Draft PR #993 and step one-model-rule (model rule step, doing) for F132. Draft PR #996 and step tci-6-mutation-replay (mutation replay step, doing) for F160. Draft PR #998 for F165, with step comment-narration-patterns (comment narration step, todo). Draft PR #994 and step handoff-read-before-write (handoff read step, doing) for F177 and F179. Draft PR #986 and step compaction-carry-watch (compaction watch step, doing) for F178 and F183. Held PR #982 (handoff checkpoint) for F179 and F182. Draft PR #1002 and step idle-resume-compacts (idle compaction step, doing) for F180.
23. Unknown rows (F39, F82, F84, F93, F251, F252, F233 to F247, N5): no owner yet. Each unknown names the read that could not run (section 1).
24. Owner items that landed by his own act (F248 to F250): none needed.

### Start now, by hand (existing items only)

- Step ci-hygiene-refresh (ci-hygiene refresh step), the per-repo half.
- Step tci-9-live-protection (branch-protection step), so degen and q_max match decision main-branch-protection.
- Steps page-parked-actions (parked items step) and page-ask-box (ask box step), as one lane with a designer.
- Finish draft PR #919 (guard for coordinator scope).

### Proposed checks (not filed, so no owner yet)

These checks came from the draft. No step file exists for any of them.

- A roadmap build that goes red when a todo step has an open PR for its slug.
- A replay of the owner's chat answer "143 b" with no last answer written, which goes red.
- A triage report that lists each ready todo step, and each draft PR older than 12 hours with no live lane.
- A check at turn end that a chat grant with no line in .claude/CLAUDE.md or settings.json goes red.
- A report that cites a rewriting decision goes red if the record's last commit on main is older than that decision. Replay F119: ci-job-caps, last touched Oct 28. This check does not rest on the ci-spend-gate claim, which was wrong.
- A batch runner that refuses a lane whose lint run is red at its head. Replay: PR #979.
- An inbox item that closes with no step, record or answer, which goes red. Replay F88.
- A report line that says "answered" with no cited source, which goes red. Replay F188.
- Prose only: a trust-error decision that records "docs silent" and names the owner's plan (F190).

### Open work for this record

- Copy the owner words for F1 to F229 into this record. The merge source holds them.
- Re-read the triage "Answered" rows (F30, F85, F99 and similar) against a triage transcript.
- Record the 19:27 CST ruling behind claude-settings draft PR #1003 (section 2c).
- Decide the state of F252 (section 2a) and of F173 (section 4, item 21).
## 7. Full table

Each row id carries its gloss. The evidence column cites PRs, steps and decisions by id. The lists below gloss every such id that the rows cite.

### 7a. Pull requests

- #174: mailaudit pull request, merged.
- #313: degen pull request, merged 17:19 CST.
- #806: waiting-page card picture and long links (c204 items), merged.
- #869: batch 34 integration PR.
- #874: waiting-page name "<repo> Queue".
- #878: merge role for the coordinator and batch runner (batch 37).
- #879: setup script installs claude-settings before a cloud session.
- #880: waiting-page answered card tightens after Send.
- #894: waiting-page task command as PowerShell and Mac.
- #895: merge tool rebuilds the records page before ready.
- #897: refuse trust and folder cards in a cs-build session.
- #898: waiting-page option keys are the shown letters.
- #899: refuse an agent spawn above its role's model.
- #901: a fork keeps its own waiting page.
- #902: question-departs check, each question names its change from main.
- #903: subagent hand-backs stay out of the feedback inbox.
- #904: batch 37 integration PR, ten lanes.
- #905: gh account clear, a gh command switches login first.
- #910: claude-settings rule wins over child repo text (decision compliance-defined).
- #916: batch 39 integration PR, nine lanes.
- #919: guard for coordinator scope, a draft.
- #923: batch 40 integration PR, six lanes (ci-hygiene skill half).
- #939: cry-wolf rule, read the guard's record before routing around a refusal.
- #940: feedback inbox block names the file and item form.
- #950: widening ruling in plain words.
- #951: ponytail plugin off until the deep dive.
- #952: session-board drops its Stop handler.
- #953: kill guard, main session may stop its own job under an orphan shell.
- #955: principles, haptics rule.
- #956: waiting-page question gets a model review.
- #957: Explore runs Sonnet only with an audit marker.
- #959: batch 54 r2 integration PR, six lanes (debug-port rule removed, design skills).
- #960: spawn judge remedy names the audit marker.
- #961: page question judge also reviews task items.
- #962: browser and 3D house rules (docs).
- #964: 3D tools survey plan.
- #966: tracking-turn rule, a turn that pushes ends with the report.
- #967: waiting-page option label refusal.
- #969: test-ci-standard plan.
- #971: waiting-page publish refused when page code is behind main.
- #972: role lists lint lane, merged in batch 59.
- #973: compact threshold formula lane, merged in batch 59.
- #974: guard.log UTC offset lane, a draft, not in batch 59.
- #975: prose-named-file refusal lane, merged in batch 59.
- #976: remote add_repo and archive_session allow list lane, merged in batch 59.
- #977: batch 58 integration PR.
- #978: no usage limit for standing sessions, merged in batch 59.
- #979: auto-mode refusal note, a draft, not in batch 59.
- #980: none-with-note direction lane, merged in batch 59.
- #981: roadmap check of page rulings that never reached their step, a draft.
- #982: handoff checkpoint before compaction, held draft.
- #983: one feedback inbox per repo, a draft.
- #984: silent-undo rename scan, a draft, not in batch 59.
- #985: waiting-page pictures check at write, a draft.
- #986: compaction carry watch, a draft.
- #987: feel-fix device check lane, merged in batch 59.
- #988: roadmap check of dated claims, a draft.
- #989: records-first lane close, a draft.
- #992: batch 59 integration PR, merged 19:31 CST as main 55b27ac2.
- #993: brief-marker scanner, a draft.
- #994: handoff read before write, a draft.
- #995: glossary meets the owner, a draft. q_max #995 is another PR.
- #996: mutation engine for tci-6, a draft.
- #997: waiting-page stale asks sink, a draft. q_max #997 is another PR.
- #998: comment check in every repo, a draft.
- #999: repeat feedback detect, a draft.
- #1001: ci-job-caps stopgap, claude-settings draft, opened 19:23 CST.
- #1002: idle-resume-compacts decision, a draft.
- #1005: waiting-page unpark and drop, a draft.
- #1007: all-repos grant, a draft (head pr-acts-grant).
- banchi #1003: guard-shell tree clause, a draft. Banchi #1004: merged banchi pull request.
- joyous #53 and #59: joyous pull requests, merged.
- q_max #995, #997 and #1001: q_max pull requests cited by F33 and F44.

### 7b. Steps and decisions

Steps (origin/roadmap):

- roadmap-live-check-true: roadmap live-check step.
- roadmap-one-writer: only triage writes the roadmap.
- child-repo-gap: child-repo gap step.
- r1: compliance-check on each child repo.
- r5: each repo drops its copies of claude-settings things.
- r6: each repo adopts the project way of working.
- one-check-other-repos: one rollup check in each repo.
- c91: one iOS standard step.
- c196: Mac load step.
- tci-5-platform-tested: platform test step.
- tci-6-mutation-replay: mutation replay step.
- tci-9-live-protection: branch-protection step.
- tci-11-qmax-shards: q_max shards step.
- tier-boundaries-enforced: tier boundary step.
- time-pinned-tests-go: time-pinned tests step.
- merge-grant-switch: merge-grant switch step.
- ci-hygiene-refresh: ci-hygiene refresh step.
- stale-prose-standing: stale prose step.
- one-model-rule: model rule step.
- feedback-repeat-detect: repeat detect step.
- one-inbox-per-repo: one inbox step.
- lane-closes-after-records: records-first close step.
- glossary-meets-owner-halfway: glossary step.
- comment-narration-patterns: comment narration step.
- handoff-read-before-write: handoff read step.
- compaction-carry-watch: compaction watch step.
- idle-resume-compacts: idle compaction step.
- handoff-no-copied-lists: handoff points at a home, not a copy.
- question-checks-past-rulings: past-rulings check step.
- page-ruling-reaches-step: page ruling step.
- page-stale-asks-sink: stale asks step.
- page-item-checked-at-write: item check step.
- page-parked-actions: parked items step.
- page-ask-box: ask box step.
- page-question-shape: page question shape step.
- page-shows-last-answer: last answer card step.
- note-always-open: note box step.
- drop-take-pick: drop take-pick step.
- command-per-os: command per operating system step.
- gh-account-clear: gh account clear step.
- triage-watches-page: triage watches page step.
- tracking-turn-report-clash: turn-report clash step.
- resume-lost-worktree: lost worktree step.
- c95-milestone-runs: full CI at milestones step.
- d4: first design test step (Banchi).
- mods-relevance-review: mod relevance review step.
- lane-effort-medium: lane effort step.
- local-cc-version-lag: Claude Code version lag step.
- local-folder-for-owner-acts: owner acts on the Mac step.
- sim-no-diagnose: iPhone test diagnose step.
- test-merge-conflict-role: test merge conflict role step.
- trust-card-guard: trust-card guard step.
- coordinator-merge-grant: coordinator merge grant step.
- ponytail-local-still-on: ponytail on-device step.
- ponytail-off-deep-dive: ponytail off step.
- stale-note-recheck: not a step. It is the head branch of PR #988.

Decisions (docs/decisions on origin/main):

- session-tiers: session tiers decision.
- compliance-defined: claude-settings rule wins over child repo text.
- agent-model-cap: agent model cap decision.
- design-skills: design skills decision.
- main-branch-protection: main branch protection decision.
- same-check-kinds: every repo runs the same kinds of checks.
- standing-merge-grant: standing merge grant decision.
- auto-mode-owner-acts: which acts auto mode allows with no ask.
- owner-feedback-inbox: owner feedback goes to an inbox first.
- option-keys-are-letters: waiting-page option keys are letters.
- rework-leaves-page: a reworked waiting-page item leaves the page.
- session-board-mod-limits: session-board keeps small records.
- act-in-place: the owner acts where he reads.
- a-kill-by-pid-needs-an-owned-pid: a kill needs a pid the session started.
- ux-house-rules: house UX rules.
- ci-spend-gate: q_max decision on CI spend (D-718).
- test-strategy-reset: tests prove outcomes, run where their subject lives, and never fail on runner speed (docs/decisions/test-strategy-reset.md).
- precompact-handoff: checkpoints keep the handoff current (cited by claude-settings PR #1003).

### 7c. Other ids

- item N: a waiting-page item number, as the page shows it.
- c-numbers (c29, c95, c146, c174, c203, c204): older roadmap step labels. Each row says what it covers.
- Commit hashes (for example 12760618, 55b27ac2): one git commit each. The row names what the commit does.
- session ids (session_013NEJ...): one Claude Code session each. The row names its role.
- d4v3-slot-word: a record name for item 95 b. It was not found on origin/roadmap.

### 7d. Rows

Unknown rows, with the read that could not run:

- F39: the source is a session report only. The triage transcript from before Oct 28 20:37 CDT is needed.
- F82: a headless render of the waiting-page template at 360 to 430 px is needed.
- F84: page items keep only the last answer, so the Oct 29 14:49 re-save cannot be rebuilt.
- F93: the Artifact read answers "not found". That cannot tell "deleted" from "not shared".
- F251: the phone screenshots are image-only and unreadable.
- F252: the owner words were not recovered (section 2a).
- F233 to F247: 15 row numbers with no row text (section 1).
- N5: the owner words for the 19:27 CST ruling are not in the inputs.

| id | when | owner words | state | evidence |
|---|---|---|---|---|
| F1, flywheel restart | 10-31 14:12 (C0; relayed C1 ×2); said 1 | "Restart the flywheel from it: tag yourself cs-build:coordinator … start triage and a batch runner, then one lane per open step." | LANDED | Batches 39 to 58 merged (#916 to #977). |
| F2, batch 37 rebuild | 10-31 14:12 (C0); said 1 | "Batch 37 … must merge main (84a56038) first. Lose no work" | LANDED | #904 merged Oct 31 17:09 CDT. |
| F3, trust-card guard merge | 10-31 14:49 (C0); said 1 | "trust-card-guard … what's this? I don't remember" | LANDED | #897 merged in batch 39 (#916); step trust-card-guard done. |
| F4, answered chat question | 10-31 15:17 (C0); said 1 | "what is the role as established on main of coordinator?" (truncated) | LANDED | Answered in chat (matches the coordinator transcript). |
| F5, wrong-tier rule | 10-31 15:31 (C0; C1 relay; T-1KK; T-292; T-3DB P2); said 2 (refers to Oct 28 15:12 "Wrong tier") | "why are you doing so much work and/or asking me so many questions if that's not really your part of the job? do you remember i set something like sessions should kindly point me in the right direction?" | LANDED | "Wrong tier" in decision session-tiers and the shiv-stylisms style. The hook is F6. |
| F6, tier-boundary guard | 10-31 15:32 (C0; C1 relay; T-1KK); said 1 | "not only fixing that now it needs to be like an actual fix right?" | IN FLIGHT | #919 still a draft, opened Oct 31 20:14 CDT, about 23 h; not in batch 59. Step tier-boundaries-enforced doing. |
| F7, tier-boundary guard folded into PR 919 | 10-31 15:31–15:32 (C0; T-1KK); said 1 | Classifier refusing the #1002 merge handoff "also sounds like a fault?" | IN FLIGHT | Folded into #919 (draft). |
| F8, answered chat question | 10-31 15:33 (C0); said 1 | "explain what it means to hold the merge grant?" | LANDED | Answered in chat (matches the coordinator transcript). |
| F9, session-tiers decision | 10-29 13:45 (T-292; T-3Mw); said 1 | "a role that's whole job is to be pushing stuff from triage into more lanes … a flywheel" | LANDED | Decision session-tiers. |
| F10, session-tiers decision | 10-29 13:44 (T-292); said 1 | "I shouldn't be expected to be around to do something I'd already signed off for" | LANDED | Decision session-tiers. |
| F11, grants in roadmap | 10-29 13:44 (T-292); said 1 | "Grants living in roadmap actually does make a lot of sense" | LANDED | Decision session-tiers names "Grants living in roadmap". |
| F12, compliance-only rule | 10-30 13:22, 13:25 (T-292); said 1 | "i entirely meant compliance" (a coordinator in another repo does compliance only) | LANDED | Decision session-tiers "compliance only". |
| F13, roadmap-one-writer guard | 10-28, time not given (T-292); said 1 | Triage is the only writer of the roadmap and the waiting page | LANDED | Decision session-tiers. The guard is step roadmap-one-writer: doing, no PR. |
| F14, arbiter effort rule | 10-29 14:55 and 16:42, items 72 and 81 a (T-292; T-3Mw); said 2 | "i should be able to tell coordinator to *spawn arbiter* … it uniquely gets high effort too" | LANDED | Decision session-tiers line 57: arbiter high effort. |
| F15, session-tiers overturn | 10-30 12:44, item 86 a (T-3DB; T-292); said 1 | Owner keeps the power to overrule the arbiter, on rulings he sees | LANDED | #869 merged (batch 34); "Overturn" in decision session-tiers. |
| F16, lane effort rule | 10-30 15:11 (T-3DB, relayed); said 1 | "lane sessions run Opus at medium effort." | LANDED | Decision session-tiers line 46; step lane-effort-medium done. |
| F17, freeze record after PAUSE | 10-30 17:27 (T-3Mw, relayed via coordinator 2); said 1 | "PAUSE … Stop at the next safe point … Resume only when I say so." | CONTRADICTED | By the session's own report, triage wrote the freeze record after PAUSE. No pause record on main. Its reply was not seen. |
| F18, waiting-page reply rule | 10-28 02:44 (T-3Mw, relayed); said 1 | "never reply in a waiting-page thread, revise the item" | LANDED | skills/waiting-page/SKILL.md: "Never reply in a comment thread". |
| F19, roadmap live check | 11-01 17:19 (C2; C3 summary); said 1 | "why has so much remained to do on the roadmap when sessions could've been spawning? isn't that coordinator's fault?" | IN FLIGHT | Step roadmap-live-check-true doing, no PR. Still true at 19:15 CST: 8 todo steps say "Ready: no open question". |
| F20, refusal note PR 979 | 11-01 17:19 (C3 summary); said 1 | "how … were you able write down that refusal for yourself and no hook nor yourself told you to mark it somewhere more tangible?" | IN FLIGHT | #979 draft. Dropped from batch 59 for a red form check. No roadmap step. |
| F21, child repos catch up | 11-01 16:29 (C2); said 1 (related to F64) | "is compliance check skill done completely and/or my other repos are able to take work on … how has coordinator status been at archiving and starting sessions" <!-- ste-disable-line STE011 --> | IN FLIGHT | child-repo-gap and r5 doing; r6 and one-check-other-repos todo; compliance-check is not done. Archiving: #976 merged in batch 59 and #989 (draft). |
| F22, item 147 closed | 11-01 17:53 (C2); said 1 | "whats this about" (the q_max token status line) | LANDED | Item 147 closed. |
| F23, roadmap out of step | 11-01 17:59 and "00:00" (likely 18:00) (T-1qE); said 1 | "were/are roadmap steps and triage just no longer remaining in sync? who's responsible…" / "that seems like concerning feedback that should be addressed?" | IN FLIGHT | roadmap-live-check-true and roadmap-one-writer doing; page-ruling-reaches-step todo with #981 draft. Not fixed yet: 9 steps say todo while their PR is open. |
| F24, answers routed to roadmap | 11-01 18:28 (T-1qE); said 1 | "status?" | LANDED | Answered. The answers had sat unrouted (P1). |
| F25, visits held process | 11-01 item 16 a (C2); said 1 | Warn which repo sessions to pause before each roll-out visit | LANDED | Process only: visits held, then F26. |
| F26, three repo merges | 11-01 17:26 (C2; C3 summary); said 1 | "only session im doing active work in is just the home repo -- rest are all go ahead" | LANDED | joyous#59, banchi#1004 and mailaudit#174 merged Nov 1. |
| F27, turn-report clash step | 11-01 16:23 (T-1qE, relayed); said 1 | Triage ends every turn that pushes the roadmap with the full report | LANDED | Step tracking-turn-report-clash done (#966). |
| F28, org instructions note | 11-01 16:35 (T-1qE, compaction summary); said 1 | IT/org instructions are often outdated; the user's specifics are the source of truth | DROPPED | No home on main or the roadmap. Compaction summaries only. |
| F29, lost-worktree step | 10-29 16:49 (T-3Mw); said 1 | "if a session lost its worktree and was resumed it would just work off of main rather than first recreating a new worktree?" | LANDED | Step resume-lost-worktree done (6f89e45). |
| F30, step c29 answer | 11-01 16:12 (T-1qE); said 1 | "what is step c29" | LANDED | Answered (triage-sourced; not re-read). |
| F31, chat grant home | 10-31 14:49 (C0; T-1KK); said 1 | "this option is fine" (option a: add q_max and banchi) | CONTRADICTED | Item 100's home is "process only (coordinator handoff)". The mandate puts a chat grant in CLAUDE.md or the merge config, never only in a handoff. |
| F32, compliance-defined decision | 10-31 15:04 (C0; C1; T-292; T-1KK); restated 11-01 17:25 (T-1qE, 133 note); said 2 (restated) | "if there's anything claude-settings rules on, it usually supersedes what repos have unless … explicitly mentioning claude-settings' rules … 'known exemption'" / "i thought i also made an affirmation that…" | LANDED | Decision compliance-defined ("known exemption"); #910 merged in batch 39. |
| F33, q_max PR 995 merge | 10-31, open (C0); said 0, unanswered | (no owner words) q_max#995 merge yes/no | LANDED | q_max#995 merged Oct 31 20:06 CDT. |
| F34, child-repo-gap step | 10-29 14:49, item 74 (T-3Mw); said 1 | "mailaudit and … home … haphazardly tried to adopt ur renovation before it was complete so probably just send lanes fixing all the repos" | IN FLIGHT | Step child-repo-gap doing since Oct 29 (3 days). |
| F35, item 70 closed | 10-29 14:46, item 70 (T-3Mw); said 1 | "approved" (banchi chat OK, c174) | LANDED | Item 70 closed. Its follow-on, banchi#1003, is still open (F43). |
| F36, shared branch protection | 10-29 14:46, item 71 (T-3Mw); said 1 | "71 a (protect degen's main like claude-settings)" | FILED NOT STARTED | Item 78 closed with "78 done" (owner act). A live read of degen main protection gives check all-jobs-passed with strict: true. The shared form is strict: false (main-branch-protection line 22). Step tci-9-live-protection is todo. |
| F37, picks filed for iOS and Mac load | 10-29 14:55 (T-3Mw); said 1 | "Items: 75 a, 73 a, 76 a, 72 b." | FILED NOT STARTED | Picks are filed (f236bcc). c91 (iOS standard) and c196 (Mac load cap) still todo; child-repo-gap doing. |
| F38, child repos asked twice | 10-29 14:37 (T-3Mw); said 2 (asked again 11-01 16:29, F21) | "whats the status on when we'll build out/update our skills like compliance check so repos get caught up" | IN FLIGHT | Asked twice (with F21). Step r1 done, but the repo fixes (child-repo-gap, r5, r6) are open. |
| F39, earlier session report | 10-30 03:56 (T-3Mw; origin unclear); said 1 | "Read-only research … find each session's compliance report" | UNKNOWN | Session report only. No file or step evidence found. Origin unclear; may not be owner words. Needs the triage transcript from before Oct 28 20:37. |
| F40, item 99 closed | 10-31 14:55 and 11-01 04:26, item 99 note (C1; T-2Ki; T-3DB; T-292; T-1KK); said 2 | "after switching to github shivinate7 does this still not work??" | LANDED | Item 99 closed. |
| F41, item 99 closed later version | 11-01 11:33, item 99 (C2; T-2Ki); said 1 | "99 done (changed … to 'GUARD_SHELL_SKIP= tree')" | LANDED | Item 99 closed (v5 and later). |
| F42, page judge partial-step check | 11-01 11:53 and 16:23, item 99 (C2; T-2Ki); said 2 | "this is so fucking stupid explain why i have to undo what you told me to do??" | LANDED | #961 merged in batch 55: the page judge flags a partial-line step. |
| F43, banchi item 99 follow-on | 11-01 16:32–16:34 (C2; T-2Ki); said 1 | "99 a (done)" (pushed banchi c174 1039411b) | IN FLIGHT | Owner finished item 99 a at 16:32 CST: banchi c174 pushed (commit 1039411b). The coordinator first said it was not pushed, from a stale fetch, then verified. Banchi PR #1003 (guard-shell tree clause) is still an open draft (checked after the read). |
| F44, q_max PR 997 merge | 11-01 16:23 item 123 a (C2; T-2Ki); 17:14 item 139 note (T-1qE); 17:16 chat (C2; C3); said 3 | "123 a" / "139 … you can for sure do it?" / "mark q_max #997 ready and merge it" | LANDED | q_max#997 merged via #1001, Nov 1 18:14 CST. The owner had to ask 3 times. |
| F45, attach repos and degen PR 313 merge | 11-01 17:14 item 138 note (T-1qE; C2 page note); 17:16 chat (C2; C3); 17:25 "138 done" (T-1qE); said 3 | "pretty sure you're able to just do that -- i had already given this coordinator permission to attach these?" / "attach degen and joyous with push access" | LANDED | degen#313 merged 17:19 CST; joyous#53 merged. Page item 138 is still open (P1). |
| F46, item 143 b, other-checkout guard | 11-01 17:25, item 143 (T-1qE); said 1 | "143 b" (shared guard refuses cd into another checkout, then banchi#1003 merges) | IN FLIGHT | Item 143 b (owner, 17:25 CST): the shared guard refuses cd into another checkout, then banchi PR #1003 merges. Page item 143 is open with no recorded answer. Branch other-checkout-cd-gap (origin) has three commits, the last at 19:40 CST. It is not on main and has no PR. Whether the lane is running is not verified. |
| F47, all-repos grant | 11-01 17:37 (C2; C3; T-1qE); said 1 | "YOU HAVE EXPLICIT APPROVAL FOR ANY AND ALL REPOS YOU WANT OF MINE TO MARK PR READY, MERGE, REVIEW, ETC." <!-- ste-disable-line STE011 --> | IN FLIGHT | Draft PR #1007 (all-repos grant draft, head pr-acts-grant, opened 19:33 CST) holds the grant in docs/decisions/standing-merge-grant.md and docs/decisions/auto-mode-owner-acts.md. It quotes the 17:37 CST grant, which the coordinator relayed and which is not verbatim in the transcript read, and the owner's 19:19 and 19:23 CST rulings. Not merged. Not in .claude/CLAUDE.md. The roadmap note on step merge-grant-switch names lane classifier-refusals-allowed. No branch by that name exists on origin. |
| F48, remote tools in allow list | 11-01 17:16 and 17:19 (C2; C3); said 2 | "'mcp__claude-code-remote__add_repo' get this done too" / "we need archive_session to go into the permission allow block too" | LANDED | PR #976 (remote add_repo and archive_session allow list) merged in batch 59 (main 55b27ac2, 19:31 CST). |
| F49, auto-mode owner-acts decision | 11-01 17:37 (C3 summary); said 2 (said before) | "i had a bunch of stuff i told you to have auto always allow … all the allow has to be at one referenceable area" | LANDED | One home: decision auto-mode-owner-acts plus settings.json autoMode.allow. The widening it needed is F47. |
| F50, allow list too rigid | 11-01 ~17:38 (C3; C2); said 1 | "IS IT ALSO REALLY DUMB THE ALLOW LIST WAS SO RIGID THAT IT BLOCKED THIS" | IN FLIGHT | Owner, Nov 1 about 17:38 CST: "IS IT ALSO REALLY DUMB THE ALLOW LIST WAS SO RIGID THAT IT BLOCKED THIS." The widening sits in draft PR #1007 (all-repos grant draft). Not merged. |
| F51, standing grants in CLAUDE.md | 10-30 16:20 (C1, relayed); said 1 | Standing grant "Acts the cloud refuses": branch protection, delete merged branches, close replaced PRs | LANDED | .claude/CLAUDE.md, Standing grants. |
| F52, PR 878 merge | 10-29 16:54 (T-292); said 1 | Batch runner merges with no per-session owner step and no widening | LANDED | #878 merged (batch 37). |
| F53, standing merge grant decision | 10-29 16:47 (T-292; T-3Mw); said 1 | Coordinator holds a standing merge grant | LANDED | Decision standing-merge-grant; step coordinator-merge-grant done. |
| F54, PR 878 and item 98 | 10-30 15:35 item 97; 15:40 item 98; Oct 30 or 31 15:36 (T-3Mw; T-1KK); said 2 | "why stop here leaving a hole known" / "this is for sure solvable … send an opus agent … surf the web, first confirm … the outcome" | LANDED | #878 merged; item 98 closed. |
| F55, accepted ruling | 10-30 15:43 (T-3Mw); said 1 | "i answered to coordinator already" | LANDED | Accepted. |
| F56, answered question | 10-30 16:05 (T-3Mw); said 1 | "did it reply" | LANDED | Answered. |
| F57, batch runner may merge | 10-30 12:45 / 14:45 / 15:05, item 92 (T-3Mw); said 2 | "to confirm, B makes a lot more sense or no?" → "92 b" | LANDED | #878 merged (batch runner may merge). |
| F58, same required checks | 10-30 12:45 / 14:45 / 15:03, item 87 (T-3Mw); said 3 | "same kinds of checks … as long as it's looking at the same OUTCOMES then … the quantity scales" / "confirm you understood … before you continue" | FILED NOT STARTED | Decision same-check-kinds exists; item 87 closed. A live read of q_max main gives HTTP 404 and .protected false. The owner's rule was the same required checks in every repo. Step tci-9-live-protection is todo. No step file named tci-9 exists. |
| F59, main-branch-protection decision | 10-31 14:49 (C0; T-1KK); said 1 | "we have two github logins. and if you use shivinate7 it works?" | LANDED | Decision main-branch-protection. |
| F60, answered question | 10-31 14:50 (C0); said 1 | "Give me the powershell command" | LANDED | Answered (matches the coordinator transcript). |
| F61, item 101 closed | 10-31 14:52 (C0; T-1KK); said 1 | (pasted gh auth switch output) | LANDED | Item 101 closed. |
| F62, gh account clear | 10-31 14:53 (C0; T-1KK); said 1 | "I dont even know when I switched to the other GH … probably something we should address" | LANDED | #905 merged in batch 45; step gh-account-clear done. |
| F63, act-in-place default account | 10-31 14:55 (C0; C1; T-1KK); said 1 | "shivinate7 should be the default unless … shivinate7 doesn't have access" | LANDED | Decision act-in-place names shivinate7 as the default. |
| F64, answered question | 10-31 14:53 (C0); said 1 | "turned on auto make pull requests … draft … let me know if that helps the 403" | LANDED | Answered. |
| F65, answered question | 10-31 14:54 (C0); said 1 | "should i just leave it off then?" | LANDED | Answered. |
| F66, owner's own setting | 10-31 14:55 (C0; T-1KK); said 1 | "ok i turned it off" | LANDED | Item 103 closed (owner's own setting). |
| F67, item 78 Mac run | 10-30 12:45 / 14:40 / 14:47, item 78 (T-3Mw); said 3 | "do i have to run it specifically from my mac, and why?" / pasted PS output / "78 done" | LANDED | Item 78 closed. |
| F68, command-per-os step | 10-30 14:47 (T-3Mw; T-292); said 1 | "ensure they're given as powershell and macos … collapsible to just copy" | LANDED | #894 merged; step command-per-os done. |
| F69, answered question | 10-31 15:12 (C0); said 1 | Asked what the inbox and ponytail messages meant (text not shown) | LANDED | Answered. |
| F70, never judge broken without asking | 10-31 15:16 (C0; C1 relay); said 1 | "What made you confirm on the feedback inbox that it's working wrongly? You didn't even ask me" | DROPPED | "Never judge something broken without asking" was kept only as a handoff premise. No record on main. |
| F71, options a to d for item 108 | 10-31 15:17 (C0); said 1 | "send a lane to just read the inbox … describe my paths and what each outcome would mean" | LANDED | Report gave options a to d (item 108). |
| F72, inbox skip PR 903 | 10-31 15:44, item 108 d (C0; C1; T-292; T-1KK); said 1 | "108 d" ("only hand-backs are skipped") | LANDED | #903 merged (batch 40). Partly replaced by F75 (owner, Nov 1 04:29). |
| F73, Apple TV loop fix | 11-01 03:56 (C1; C2); said 1 | Pasted the Apple TV loop complaint, plus "Did something break?" | LANDED | Answered; #940. |
| F74, PR 940 merge | 11-01 04:09 (C1; C2; T-2Ki); said 1 | "this needs to be fixed properly send a session out for it" | LANDED | #940 merged in batch 46. |
| F75, owner-feedback-inbox decision | 11-01 04:29 (C1; C2; T-2Ki); said 1 | "neither seem like great options A likely the better bandaid with a debt" | LANDED | Decision owner-feedback-inbox names the bandaid; debt inbox-saves-other-notices. |
| F76, repeat detection | 11-01 17:44 (T-1qE; C2); said 1 | "No repeat detection … You said 'carousel' and the repo said 'wheel'" | IN FLIGHT | #999 draft. Step feedback-repeat-detect still says todo. |
| F77, meaning match | 11-01 17:57 (T-1qE; C2); said 1 | "doesnt even need to be a straight glossary … ai semantic word mappings" | IN FLIGHT | #999 draft (meaning match, 1f40e864). |
| F78, one inbox per repo | 11-01 17:44 (T-1qE; C2); said 1 | "Each repo needs one inbox that every session writes to." | IN FLIGHT | #983 draft. Step one-inbox-per-repo still says todo. |
| F79, none-with-note direction | 11-01 17:44 (T-1qE; C2); said 2 (repeats his many "none of these" notes) | "A 'none' with a clear note should close the item and become a step." | LANDED | PR #980 merged in batch 59 (main 55b27ac2, 19:31 CST). Step none-with-note-is-direction is doing (origin/roadmap). Said twice. |
| F80, feel-fix device check | 11-01 17:44 (T-1qE; C2); said 1 | "A check should keep a feel-fix open until a simulator or device check is recorded" | LANDED | PR #987 merged in batch 59 (main 55b27ac2, 19:31 CST). Step feel-fix-needs-device-check is doing (origin/roadmap). |
| F81, lane closes after records | 11-01 17:44 (T-1qE; C2); said 1 | "A lane shouldn't archive until its record step merges." | IN FLIGHT | #989 draft, not in batch 59. |
| F82, waiting-page width check | 10-29 14:42 (T-3Mw); said 1 | "artifact itself a little cropped/chopped on mobile" | UNKNOWN | Session report (v20 at 360 to 430 px). Not re-checked. Needs a headless render of the waiting-page template at 360 to 430 px. |
| F83, waiting-page republish | 10-29 14:47 (T-3Mw); 11-01 16:17 (T-2Ki; C2); said 2 | "the current one i see i think is older code … ensure u and all my other repos know to do that proactively" / "can we ensure there's some sort of hook that forces artifacts to auto rewrite to the newer standard across my repos" | LANDED | #971 merged in batch 58; steps page-stale-hook and wp-republish-on-template done. |
| F84, Oct 29 re-save | 10-29 14:47 (T-3Mw); said 1 | "i also already left notes on some of the questions … on the old one" | UNKNOWN | Re-save is a session claim. No evidence. Page items keep only the last answer, so the Oct 29 14:49 re-save cannot be rebuilt. |
| F85, answered triage question | 10-30 12:31 (T-3Mw); said 1 | "do we know if claude picks a chat or spawns a new one if all i have is the artifact open?" | LANDED | Answered (triage-sourced; not re-read). |
| F86, triage watches page | 10-30 12:35 (T-3Mw); said 1 | "Yes please do that's exactly right." | LANDED | Step triage-watches-page done. |
| F87, page Status tab | 10-30 12:45 (T-3Mw); said 1 | "what is this 'Status' tab … not supposed to be the integration of the roadmap" | LANDED | The page's Status tab carries the roadmap data (read at 19:15 CST). |
| F88, grey Send button | 10-30 12:45 (T-3Mw); said 1 | "the send button is grayed, i had a short error of 'failed to fetch'" | DROPPED | The grey Send button and "failed to fetch" got no diagnosis and no step. |
| F89, c204 page items | 10-30 12:45 and 14:45, items 83/84 (T-3Mw); said 2 | "mockups here look the same with them being black screens" / "can you confirm you built this right?" | LANDED | c204 items closed; #806. |
| F90, page shows last answer | 10-30 12:57 (T-3Mw; T-292); said 1 | "im seeing more questions that i'd already answered? did compaction make you forget?" | LANDED | Step page-shows-last-answer done. The page still lags (P1). |
| F91, note box always open | 10-30 14:30 (T-3Mw; T-3DB); said 1 | "why does note hide behind an add a note button" | LANDED | Step note-always-open done. |
| F92, Queue title | 10-30 14:33 (T-3Mw; T-292); said 1 | "has roadmap fully ported over … the name of the artifact should just be *repo name* Queue" | LANDED | #874 merged; page titled Queue. |
| F93, deleted Artifact page | 10-30 14:37 (T-3Mw); said 1 | "yes delete it" (old roadmap artifact) | UNKNOWN | Delete is a session claim. The Artifact read of JGqfvgXBuLqWUm1CX6Bv5h answers "not found, may be deleted or not shared with you", which cannot tell the two apart. |
| F94, item 94 pick a | 10-30 14:48 (T-3Mw); said 1 | "i can't answer #94 its all unselectable" | LANDED | Page item 94 is closed with pick a. Step d4 records "item 94 a, Oct 30 15:02 CDT", after the 14:48 complaint. So he could answer it. |
| F95, drop-take-pick step | 10-30 15:01 (T-3Mw; T-3DB); said 1 | "dont offer this button since u already have that magic blurb insert thing" | LANDED | Step drop-take-pick done. |
| F96, PR 880 merge | 10-30 15:06 and 15:40 (T-3Mw; T-292); said 2 | "why is this green area still so large after submitting" / "have you rebuilt the artifact with the latest code?" | LANDED | #880 merged. |
| F97, option keys are letters | 10-30 15:09 (T-3Mw; T-292); said 1 | "what is e2 btw it's not shown on these questions" | LANDED | #898 merged; decision option-keys-are-letters. |
| F98, rework leaves page | 10-30 15:37 (T-3Mw); said 1 | "Item 97 is being reworked? if so, why am i able to answer?" | LANDED | Decision rework-leaves-page. |
| F99, item 99 answer | 10-30 16:08 (T-3Mw); said 1 | "what is this parked by you area" | LANDED | Answered (triage-sourced; not re-read). |
| F100, parked-item actions | 11-01 17:35 (T-1qE); said 1 | "the parked by you area has no way of being addressed" | FILED NOT STARTED | Step page-parked-actions is todo and ready. Draft PR #1005 (waiting page: unpark and drop) opened after the read. The state is not changed here (section 2c). |
| F101, PR 901 merge | 10-31 14:57 (T-1KK); 15:02 (C0; T-292; T-1KK); said 1 | "will it … first boot … create this exact type of artifact?" → "as soon as like the first triage occurs it should auto spawn the artifact" | LANDED | #901 merged. |
| F102, answered question | 10-31 14:59 (T-1KK); said 1 | "confirm the recipe that's on main is like the latest recipe" | LANDED | Answered. |
| F103, PR 901 merge | 10-31 14:59 and 15:00 (C0; T-292; T-1KK); said 1 | "semi fork, how will that scenario work with … artifacts" → "A" | LANDED | #901 merged. |
| F104, PR 967 merge | 11-01 16:12 (C2; T-2Ki); said 1 | "do you see the problem in this artifact that was built in another repo?" (option letters) | LANDED | #967 merged in batch 58. |
| F105, page item check at write | 11-01 17:07 and 17:09 (T-1qE); said 2 | "did something like this make it to the artifact exactly because we lost advisor … this shouldn't have happened" / "this prob too" | IN FLIGHT | #985 draft; step page-item-checked-at-write doing. Said twice. |
| F106, newer questions rise | 11-01 17:16 and 17:32 (T-1qE); said 2 | "items previously asked and weren't answered sink lower (… collapse …)" / "i said already that artifacts need to have answered questions move lower" | IN FLIGHT | #997 draft opened 19:10 CST; step still says todo. Said twice ("i said already"). |
| F107, waiting-page ask box | 11-01 17:31 (T-1qE); said 1 | "this queue artifact to also have an area at the bottom where i can just ask questions" | FILED NOT STARTED | Step page-ask-box todo, ready, no lane. |
| F108, item 142 closed | 11-01 17:16 (T-1qE); said 1 | "142 … dismiss this item from here" | LANDED | Item 142 closed. |
| F109, page question shape step | 10-30 12:46 (T-3Mw); said 1 | "are questions that make it to triage running the same kinds of pre-tool use checks … quality … lower" | LANDED | Step page-question-shape done. |
| F110, page question shape step | 10-30 12:49 (T-3Mw); said 1 | "they can be merged into one form not just append two kinds of checks" | LANDED | Step page-question-shape done. |
| F111, PR 902 merge | 10-30 17:24 (T-3DB; T-292; T-1KK); said 1 | Remark: the three "departures" restated agent-model-cap | LANDED | #902 merged. |
| F112, answered question | 11-01 11:48 (T-2Ki); said 1 | "Didn't we also have … the 'Advisor' session?" / "(maybe advisor is coordinator?)" | LANDED | Answered. |
| F113, repeated questions | 11-01 11:49, 11:51 (C1; C2; T-2Ki); 16:26 (T-2Ki); 18:45 (C3); said 3 | "each question doesn't reach an advisor first?" → "yes please add it that's incredibly important" / "status on getting our advisor on questions back?" / "WHERE IS THE FUCKING ADVISOR THAT WAS SU…" | IN FLIGHT | Judge landed (#956, #961). The past-rulings check (question-checks-past-rulings) is doing with no PR. Said 3 times; the last was angry, at 18:45. |
| F114, handoff without copied lists | 10-30 12:55 (T-3Mw); said 1 | "handoff … out of date … probably a fault in needing to remember no?" | LANDED | Step handoff-no-copied-lists done. |
| F115, PR 950 merge | 11-01 11:43 (C1; C2; T-2Ki); said 2 (said before; rule speak-cite-id-plus-gloss) | "what was my uniform ruling (t18)? … never just quote a variable to me" | LANDED | #950 merged in batch 55. |
| F116, item 114 closed | 11-01 04:26, item 114 (T-2Ki); said 1 | "u've gone on circles with me deliberating this walk me through the whole timeline" | LANDED | Item 114 closed. |
| F117, past-rulings check for item 117 | 11-01 17:35, item 145 (T-1qE); said 2 (Oct 28 14:40 keep ruling) | "why remove them? I thought I already said I'd prefer to keep them? … is this a cloud gap???" | IN FLIGHT | Step question-checks-past-rulings doing, no PR; page-ruling-reaches-step #981 draft. A repeat miss. |
| F118, past-rulings check for item 118 | 11-01 18:39 (T-1qE; C3); said 2 (same class as F117, F133) | "super fucking weird that so many memory issues are occurring recently" | IN FLIGHT | Same lane; no PR. |
| F119, ci-job-caps question asked again | 11-01 18:44 (C3, not verbatim); said 2 (re-ask pattern) | ci-job-caps question should not have been asked | IN FLIGHT | Claude-settings draft PR #1001 (ci-job-caps stopgap, head ci-job-caps-stopgap) opened 19:23 CST, after the read. It rewrites ci-job-caps for the owner's 18:44 CST ruling. It lists an open clash with the kept rule "a cap rises only with a measured figure". Step time-pinned-tests-go is todo on origin/roadmap (updated 19:25 CST). No branch or PR named time-pinned-tests-go exists, so the lane start is not verified. The claim that ci-job-caps was rewritten under test-strategy-reset is still false on main: ci-job-caps was last touched Oct 28 (strict pass). |
| F120, glossary meets owner | 11-01 18:46 (C3, not verbatim); said 1 | Glossary rule: sessions understand synonyms and answer in the glossary term | IN FLIGHT | #995 draft; step glossary-meets-owner-halfway doing. |
| F121, coordinator text, not owner words | 11-01 18:48 (C3) | Not owner words: coordinator told the lane to refuse a repeat question before the owner sees it | NOT OWNER WORDS | Context only. The coordinator's own text is in coord-03.txt and coord-02.txt (line 2324). No typed owner message in the 18:10 to 18:30 CST window says "override". |
| F122, apology-only answer | 11-01 18:04 (T-1qE); said 2 (memory class) | "weird hallucination again from you" (terminal remote control) | DROPPED | Apology only. No step for this class beyond the P4 lane. |
| F123, q_max CI groups | 11-01 18:42 (C3); said 1 | "a" (ambiguous between two questions) | IN FLIGHT | coord-03.txt lines 676 to 679: the coordinator re-posed the q_max question with option d. The owner picked 12 groups; the coordinator reports "your 18:43 CST ruling" (relayed, not verbatim). Step tci-11-qmax-shards is doing. |
| F124, item 77 closed | 10-29 16:42, item 77 (T-3Mw); said 1 | "is this really my only route" | LANDED | Item 77 closed. |
| F125, PR 879 merge | 10-30 12:45 (T-3Mw); said 1 | "why can't the setupscript just be improved to where it's called first" | LANDED | #879 merged. |
| F126, answered question | 10-30 14:40 (T-3Mw); said 1 | "the builder's markdown … has no agent model line … is that potentially a factor" | LANDED | Answered. |
| F127, PR 879 and PR 899 merges | 10-30 15:05, 15:09 (C1; T-292; T-3Mw); said 2 | "77 e2 (im open to considering C too, but i think A is good?)" → A | LANDED | #879 and #899 merged. Not superseded. |
| F128, item 115 closed | 11-01 11:43, item 115 (C1; T-2Ki); said 1 | "A is basically the same as pinning though? And explain why B was problematic" | LANDED | Item 115 closed. |
| F129, agent-model-cap decision | 11-01 16:23, item 115 (T-2Ki); said 2 (pushed since item 77) | "there was a period … a round 3 builder on opus etc WITHOUT prompting me … you seem rigid" | LANDED | Decision agent-model-cap: round-3 builder on Opus. |
| F130, PR 957 and PR 960 merges | 11-01 11:43, item 107 a (C1; C2; T-2Ki); said 1 | "107 a" (Explore runs Sonnet only with an audit marker) | LANDED | #957 and #960 merged. |
| F131, one-model-rule routing | 11-01 16:23, item 127 (T-2Ki); said 1 | "i don't understand why consistency is so hard here -- can you get me a larger analysis" | LANDED | Routed to step one-model-rule. |
| F132, one-model-rule step | 11-01 16:45, item 127 (T-1qE); said 1 | "we currently have multiple workable ways and we're picking which to use randomly?" | IN FLIGHT | Step one-model-rule doing; #993 draft, #972 merged in batch 59. |
| F133, blind Opus model review | 11-01 16:45 (T-1qE; C2); said 1 | "Send a blind opus agent … only then show it how we are currently doing things … criticize" | LANDED | The blind Opus agent ran. Its findings are in the "why" of step one-model-rule. PR #972 (role lists lint) merged in batch 59 (main 55b27ac2). At the read it was still an open draft. |
| F134, item 127 rewrite | 11-01 17:14, item 127 (T-1qE); said 1 | "these are not all the options … there's more options" | LANDED | Item 127 rewritten. Page-closed; not matched to a PR. |
| F135, item 127 closed late | 11-01 17:25, item 127 (T-1qE); said 1 | "A is fine -- but … I thought we've covered all the ways … so is this moot?" | LANDED | Item 127 closed (routed late). Page-closed; not matched to a PR. |
| F136, answered question | 11-01 17:14, item 137 (T-1qE); said 1 | "is this explorer agents? I thought those are haiku or sonnet?" | LANDED | Answered. |
| F137, item 137 search agent | 11-01 17:25, item 137 (T-1qE); said 1 | "D is fine isn't it? … is the guard lift a blanket approval …" | IN FLIGHT | Item 137 still open, reworked into a, b and c. |
| F138, the "137 a" delivery | 11-01 18:39, item 137 a (C3); said 1 | (page answer 137 a, not verbatim) | IN FLIGHT | The 18:39 "137 a" is not on the page: the item shows the 17:25 note (last answer 17:25 CST) and is open. Step one-model-rule was last updated 16:53 CST and still says it waits on shiv for item 137. Only coord-03.txt line 474 ("Sent your item 137 pick (a)") says the pick reached the lane; delivery is unverified. |
| F139, PR 962 and PR 964 merges | 11-01 12:21 and 12:24 (T-2Ki); said 1 | Named Opus for the web-design and 3D lanes | LANDED | #962 and #964 merged. |
| F140, mods relevance review | 10-31 15:08 (T-1KK); said 1 | "can we also get lanes to review the mods we had added like ponytail" | LANDED | Step mods-relevance-review done. |
| F141, answered question | 10-31 15:08, 15:10 (T-1KK); said 1 | "do mods not work in claude cloud sessions? i dont see like that weather thingy" | LANDED | Answered. |
| F142, items 117 and 118 closed | 11-01 04:26, item 105 a (C1; T-2Ki); said 1 | "105 a" (fix token-weather and session-board) | LANDED | Items 117 and 118 closed. Page-closed; not matched to a PR. |
| F143, session-board mod limits | 11-01 11:43 / 11:53, item 117 (C1; C2; T-2Ki); said 1 | "is this true or just cloud sessions?" → "117 a+b" | LANDED | #952 merged (batch 54) in decision session-board-mod-limits. No record named session-board-stop-limit exists. |
| F144, item 118 closed | 11-01 11:43 and 16:23, item 118 (C1; C2; T-2Ki); said 2 | "this isnt true" / "look at the mod and the outcome more holistically" | LANDED | Item 118 closed, no build. |
| F145, item 106 vetted | 10-31 15:11, 15:14 (T-1KK); said 1 | "i've never heard of this" / "vet it … i dont remember how much of it is being actively employed" | LANDED | Item 106 vetted. |
| F146, item 106 rewrite | 11-01 04:26, item 106 (T-2Ki); said 1 | "i need more information" | LANDED | Item 106 rewritten. |
| F147, item 106 rework | 11-01 11:43, item 106 (T-2Ki); said 1 | "all I wanted were the skills … we must've accidentally enabled … the whole thing … an agent misdid something" | LANDED | Item 106 reworked. |
| F148, ponytail off and deep dive | 11-01 11:53, item 106 (C2; T-2Ki); said 1 | "if none of this happened, then just turn it off for now and we'll have to deep dive. this is a new and big problem." | LANDED | #951 merged; step ponytail-off-deep-dive done. |
| F149, item 122 closed | 11-01 16:23 / 16:34 / 16:35, item 122 (T-2Ki); said 3 | "just give me a prompt …" / "do i … do the powershell command?" / pasted local ponytail report | LANDED | Item 122 closed; 0de0e1bb. |
| F150, ponytail removal on desktop | 11-01 17:25 / 17:35 / 17:56, item 140 (T-1qE; C2); said 3 | "will this have taken effect on my app too" / "prompt to check in a new sesh?" / "140 done" | LANDED | Item 140 closed. Step ponytail-local-still-on still says todo (P1). |
| F151, CI figure of 25 of 80 | 10-31 14:12 (C0; T-292; T-1KK); said 1 | "stop the double CI run: 25 of 80 merges …" | LANDED | #895 merged in batch 39. The owner's 25-of-80 figure is unmeasured. |
| F152, c95 milestone steps | 10-27, item 27 (T-292); said 2 (same as F153) | "I still find the amount of CI used to be preposterous … run a check but not every merge" | LANDED | Steps c95 and c95-milestone-runs done. |
| F153, c95 milestone runs | 10-27 12:07, item 31 e (T-3DB; T-292; C3 18:39 relay); said 2 | "trust first, then cut in steps … step 3 is milestone runs" | LANDED | Step c95-milestone-runs done (a1431e3b). |
| F154, c95 note | 10-28 13:23 and 13:40, items 38 a / 34 b (T-3DB); said 1 | No minutes billed here; step 2 ports to repos that pay | LANDED | c95 note. |
| F155, ci-hygiene refresh | 10-30 15:08 (T-3DB); said 1 | "refresh the ci-hygiene skill and apply it to every repo." | FILED NOT STARTED | Skill refresh merged (#923). The per-repo fix lanes never started: step todo, set back at 18:03 CST. Asked Oct 30 15:08 CDT. |
| F156, test-ci-standard plan | 11-01 16:20 (C2; T-2Ki); said 1 | "spawn another session … how good tests/ci can/should be made, how far we're off, and a plan" | LANDED | #969 merged (plan test-ci-standard). |
| F157, item 133 rewrite | 11-01 16:45, item 133 (T-1qE); said 1 | "is C somehow a deviation from how things are otherwise done" | LANDED | Item 133 rewritten. |
| F158, platform test homes | 11-01 17:14, item 133 (T-1qE); said 2 (Oct 27 ruling) | "I thought we literally had a whole mandate on making testing more efficient … prose or code or history?" | FILED NOT STARTED | Step tci-5-platform-tested todo (waits). |
| F159, Swift test ruling for item 133 | 11-01 18:39, item 133 (C3; T-1qE); said 3 | Page answer on 133 (not verbatim); "Your milestone memory is right (Oct 27 ruling) … again" | LANDED | Item 133 withdrawn. Asked 3 times about a settled Oct 27 ruling (P4). |
| F160, tci-6 mutation engine | 11-01 16:45 and 17:14, item 134 (T-1qE); said 1 | "dont we have tons of past closed prs to cross review" → "134 a" | IN FLIGHT | Step tci-6 doing; #996 draft. |
| F161, phone lane dropped | 11-01 16:45, item 135 (T-1qE); said 1 | "Banchi is used on a desktop primarily -- what made you think … phone?" | LANDED | Item 135 closed; phone lane dropped. |
| F162, q_max CI question answered | 11-01 18:42 (C3); said 1 | "this is after we did our outcomes based test audits for all of the repos too right" | LANDED | coord-03.txt line 656: the coordinator answered "Partly" with detail, so the question was answered. |
| F163, q_max record ci-spend-gate | 11-01 18:43 (C3, not verbatim); said 1 | q_max moves to 12 test groups | IN FLIGHT | Step tci-11-qmax-shards doing. The cited record exists: q_max docs/decisions/ci-spend-gate.md (D-718) on origin/main e8f990272, last touched in 71c355f07. |
| F164, sim-no-diagnose step | 10-29 16:35 (T-3Mw); said 1 | pasted iOS session: "add -collect-test-diagnostics never …" | LANDED | Step sim-no-diagnose done. |
| F165, comment narration patterns | 11-01 18:39 (T-1qE); said 1 | "whats the status on the lint work … on code and comments? done?" | IN FLIGHT | #998 draft; comment-narration-patterns todo. |
| F166, PR 966 merge | 11-01 16:45, item 136 (C2; T-1qE); said 1 | "136 b" (report on lands) | LANDED | #966 merged. |
| F167, turn-report clash, said many times | 11-01 16:18, 16:20 (T-2Ki); said 2 (said repeatedly) | "we've gone back and forth on this 10000 times" / "look through our PR history" | LANDED | Step tracking-turn-report-clash done (#966). Said many times. |
| F168, stale prose rule | 11-01 16:30 (C2; T-2Ki); said 2 (he says possibly addressed before) | "make it a standing thing that stale prose never makes it anymore" | LANDED | PR #975 merged in batch 59 (main 55b27ac2, 19:31 CST). Step stale-prose-standing is doing on origin/roadmap. |
| F169, design-skills decision | 11-01 11:43, item 120 (C1; C2; T-2Ki); said 1 | "our rule now is that we stay as current … this ruling was out of date and somehow our audits didn't catch this" | LANDED | Decision design-skills (batch 54, #959). |
| F170, c146 plan fix | 10-30 16:09 (T-1KK); said 1 | c146 picks "each pick below stands" | LANDED | c146 plan fixed (d228ab79). |
| F171, merge-grant switch | 10-30 12:45 / 14:45 / 15:06, item 85 (T-3Mw); said 3 | "should it not just be in the coordinator's handoff" / "a =true/false" → "85 c" | LANDED | Commit 12760618 (Oct 30, on origin/main) refuses a cloud merge when merge.standingGrant is false (merge/merge.py line 2477). Test class StandingGrantSwitch exists in merge/test_merge.py. Decision standing-merge-grant names the switch. The step was set back to todo at 18:03 CST, and it says done now (origin/roadmap, 19:41 CST). Its lane session started 19:30 CST. The draft read the step status, not the code. Said 3 times. |
| F172, session turn limit | 10-31 15:12 (C0); said 1 | "did we … decide about whether any sessions need to count their turns to eventually retire" | LANDED | PR #978 merged in batch 59 (main 55b27ac2, commit c76a3447, 19:31 CST). Its title: session-tiers, no usage limit for standing sessions. |
| F173, usage-tally rotation limit | 10-29 16:42, item 81 a (T-292); said 1 | Rotation by usage tally | SUPERSEDED | Traced to the page item 109 answer (Nov 1 17:56:23 CST): choice b, with the note "I lean towards B if it works and maybe somehow log to see if i should revisit". Option b is "No limit; let compaction and the handoff rewrite carry the session". The answer is conditional. The record change sat in draft PR #978; PR #978 merged in batch 59 (main 55b27ac2, commit c76a3447, 19:31 CST). Whether main's code still holds the tally limit is not checked. |
| F174, item 109 rework | 11-01 11:43, item 109 (C1; T-2Ki); said 1 | "this doesn't seem to take into effect the compaction hooks" | LANDED | Item 109 reworked. |
| F175, answered question | 11-01 16:45, item 109 (T-1qE); said 1 | "will cloud sessions need a different set of rules then as local?" | LANDED | Answered. |
| F176, answered question | 11-01 17:25, item 109 (T-1qE); said 1 | "u just said earlier that ur cloud sessions dont have the token used checkpoints …?" | LANDED | Answered. |
| F177, handoff read before write | 11-01 17:35, item 109 (T-1qE); said 1 | "shouldn't the slip never have been possible to occur though? the hook should be better?" | IN FLIGHT | #994 draft. Step handoff-read-before-write still says todo. |
| F178, compaction carry watch | 11-01 17:56, item 109 b (C2; T-1qE); said 1 | "I lean towards B … maybe somehow log to see if i should revisit" | IN FLIGHT | #978 merged in batch 59; #986 draft. Step compaction-carry-watch still says todo. |
| F179, handoff fixes | 11-01 17:37 (C3); said 1 | "seems like ur handoffs or something is going stale" | IN FLIGHT | Handoff fixes #982 (held) and #994 (draft). |
| F180, idle resume compacts | 11-01 17:54, 17:55 (C2; C3; T-1qE); said 1 | "if sessions idle for a couple hours … it compacts before responding" / "moreso cloud" | IN FLIGHT | Step idle-resume-compacts is doing. Draft PR #1002 (decision idle-resume-compacts) opened after the read. Claude-settings draft PR #1003 (idle compaction off) sets idle compaction off. |
| F181, handoff checkpoint | 11-01 18:14 (C2; C3); said 1 | "I thought we have the handoff rewrite a couple times not just once" | LANDED | Answered; #982. |
| F182, handoff analysis lane | 11-01 18:24 (C3); 18:36 open; said 1 | "PR 982 I want more analysis first … not outcomes based" | IN FLIGHT | #982 held; analysis lane; the pick is open. |
| F183, handoff lines in PR 986 | 11-01 18:29 (C3); said 1 | "would be valuable to log whether our handoff hooks have caused any benefit" | IN FLIGHT | Added to #986 (draft). |
| F184, answered question | 11-01 17:42 (C2); said 1 | "is any of this problematic btw? [image]" | LANDED | Answered. |
| F185, owner's own setting | 11-01 17:43 (C2; C3); said 1 | "switching it from ask me to always do it here." | LANDED | Owner's own setting. No record owed. |
| F186, answered question | 11-01 18:13 (C2; C3); said 1 | "ok doing that -- but … why did we also build the claude code remote on powershell?" | LANDED | Answered; ambiguity flagged. |
| F187, coordinator text, not owner words | 11-01 18:10 (C2) | Not owner words: coordinator offered "override"; the owner did not type it | NOT OWNER WORDS | Context only. The coordinator's own text is in coord-02.txt (line 2309). No typed owner message in the 18:10 to 18:30 CST window says "override". |
| F188, no permission rule claim | 11-01 18:19 (C2; C3); said 1 | "add permissions to allow messages from cloud back to my pc" | IN FLIGHT | "No permission rule can lift it" is an inference. The docs are silent (coord-03.txt line 314). The owner asked for permissions to be added and none were. Only the one-way pc-bridge workaround exists. |
| F189, pc-bridge trust test session | 11-01 18:21 (C2; C3); said 1 | "should we do it on a test cloud session u spawn first" | LANDED | Session session_013NEJL4LniUvGXrcRXsLkcK exists, titled "pc-bridge (trust test)", created 00:21Z (18:21 CST), parent is the coordinator. It tags itself pc-bridge. |
| F190, trust error and owner's plan | 11-01 18:24 (C3); said 1 | "is it possible that old sessions aren't trusted … surf the web too" | IN FLIGHT | coord-03.txt line 314: the docs research is back and says nothing on the trust error. The coordinator's question about the owner's plan is unanswered, and no step exists. |
| F191, coordinator text, not owner words | 11-01 18:23–18:30 (C3) | Not owner words: coordinator asked owner to discard settings.json on the PC | NOT OWNER WORDS | Context only. The coordinator's own text is in coord-02.txt (line 2331). No typed owner message in the 18:10 to 18:30 CST window says "override". |
| F192, item 144 closed | 11-01 17:35 (T-1qE); said 1 | "144 … this has been done i dont think a session ever checked" | LANDED | Item 144 closed. |
| F193, answered question | 11-01 17:56 (T-1qE); said 1 | "'Add Folder' is only available on local sessions … process gap" | LANDED | Answered. |
| F194, answered question | 11-01 18:04 (T-1qE); said 1 | "I have a long dated oauth token now where do I need to leave it" | LANDED | Answered. |
| F195, spawn mode prompt | 11-01 18:07 / 18:09 (T-1qE); said 1 | Pasted spawn-mode prompt → "144 done" | LANDED | Item 144 closed. The cloud start gap waits in step local-folder-for-owner-acts (todo). |
| F196, answered question | 11-01 17:14 (T-1qE); said 1 | "141 … i use the claude code desktop app tho" | LANDED | Answered. |
| F197, local CC version lag note | 11-01 17:25 (T-1qE); said 1 | "141 … why did the audit read the terminal copy" | LANDED | Noted on step local-cc-version-lag. |
| F198, local CC version lag step | 11-01 17:35 (T-1qE); said 1 | "141 … big problem" | LANDED | Step local-cc-version-lag done. |
| F199, answered question | 11-01 18:04 (T-1qE); said 1 | "surf the web to see if there's newer … powershell way to update" | LANDED | Answered. |
| F200, claude update switch | 11-01 18:09 (T-1qE); said 1 | Pasted winget "No available upgrade"; 2.1.310 | LANDED | Switched to claude update. |
| F201, step 102cff36 done | 11-01 18:30 (T-1qE); said 1 | "141 done" | LANDED | Step done (102cff36). No version is recorded. |
| F202, local and cloud setup steps | 11-01 16:30, 16:31, 17:14 (T-2Ki; T-1qE); said 2 (17:14 repeat paste) | "give me a prompt … to diff how cloud sessions might act" / table ask / pasted table | LANDED | Steps filed (a5d733c0, 5087b7ce, 48a2dc28). |
| F203, at-my-computer offer | 10-30 12:45, item 61 b (T-3Mw); said 1 | "Im at my computer if you want to request spawning a remote/local session" | DROPPED | The offer got no reply. |
| F204, item 9 closed | 10-30 12:45, 14:40, item 9 (T-3Mw); said 2 | "I'd like to keep this … revisit if it starts getting bloated." | LANDED | Item 9 closed. |
| F205, answered question | 11-01 12:16, 12:17 (T-2Ki); said 1 | "do we already have an ios design language" / "what makes for good design in general" | LANDED | Answered. |
| F206, PR 955 merge principles | 11-01 12:18 (C2; T-2Ki); said 1 | "apps should consider integrating haptics on things like sliders" | LANDED | #955 merged; docs/design/principles.md. |
| F207, answered question | 11-01 12:19 (T-2Ki); said 1 | "are apples guidelines hard rules" | LANDED | Answered. |
| F208, answered question | 11-01 12:21 (T-2Ki); said 1 | "do we check when impeccable updates" | LANDED | Answered. |
| F209, PR 962 merge | 11-01 12:21 (C2; T-2Ki); said 1 | "we need browser design guidelines dos and donts … send an opus lane" | LANDED | #962 merged in batch 56. |
| F210, ux-house-rules decision | 11-01 12:23 (T-2Ki); said 1 | "i dont want to treat guidelines as hard rules unless … better build" | LANDED | Decision ux-house-rules: each rule names its outcome. |
| F211, PR 964 merge | 11-01 12:24 (C2; T-2Ki); said 1 | "spawn another opus session that looks at 3d and engine mcps" | LANDED | #964 merged. Items 130 and 131 are open for the owner. |
| F212, item 132 closed | 11-01 16:23, item 132 (T-2Ki); said 1 | "doesnt matter" | LANDED | Item 132 closed. |
| F213, item 129 closed | 11-01 16:23, item 129 a (T-2Ki); said 1 | "129 a" | LANDED | Item 129 closed. |
| F214, debug-port answer and PR 959 | 11-01 11:43, item 119 b (C1; C2; T-2Ki); said 1 | "how do we ensure the port wont clash?" | LANDED | #959 merged. Tested on headless Chrome only. |
| F215, d4 rewrite | 10-29 16:45, 62 b / 63 (T-3Mw); said 1 | "do you remember why we sent a session on banchi … did the agents do anything materially more nice looking" | LANDED | d4 rewritten. |
| F216, item 82 rework | 10-29 16:48 (T-3Mw); said 1 | "did the design agents employ the forked skills" | LANDED | Item 82 reworked. |
| F217, item 95 b record | 10-30 14:45, 15:02, item 95 (T-3Mw); said 2 | "isn't this part of the glossary fixes" / "what … does that mean? banchi's a fully built … web app" | LANDED | 95 b recorded (d4v3-slot-word). |
| F218, d4 logged | 10-30 15:02, items 94 a and 96 a (T-3Mw); said 1 | "tokens.md is this for banchi or claude-settings?" | LANDED | Logged on d4 (1adea163). |
| F219, test-merge-conflict-role step | 10-31 15:21 (T-1KK) and 11-01 04:26, item 110 a (C1; T-2Ki); said 1 | "neither I, the builder nor the reviewer asked whether this refusal is intended" → "110 a" | LANDED | #939 merged; step test-merge-conflict-role done. |
| F220, held for PR 919 | 11-01 04:26, item 113 a (C1; T-2Ki); said 1 | "113 a" | IN FLIGHT | Held for #919 (draft). |
| F221, rescoped item | 11-01 11:43, item 111 (T-2Ki); said 1 | "solo sessions that do work and handle a merge … i dislike the way you expressed the fault in A" | LANDED | Rescoped. |
| F222, item 111 closed | 11-01 11:53, item 111 a (C2; T-2Ki); said 1 | "111 a" | LANDED | Item 111 closed. |
| F223, re-explained | 11-01 11:43, item 112 (T-2Ki); said 1 | "re-analyze i need more context im confused" | LANDED | Re-explained. |
| F224, PR 919 guard log | 11-01 16:45, item 112 a (C2; T-1qE); said 1 | "i want to also keep logging to see how this is working" | IN FLIGHT | The step note says the log is new work for the lane; it is not in #919 yet. |
| F225, a-kill-by-pid decision | 10-21 and 10-26 (T-292); said 1 | The tag kill counts only for a PPID-1 process, from the main session | LANDED | Decision a-kill-by-pid-needs-an-owned-pid. |
| F226, PR 953 merge | 11-01 11:53, item 114 b (C2; T-2Ki); said 1 | "114 b" | LANDED | #953 merged in batch 54. |
| F227, trust-card guard lane | 10-31 14:12 (C0; T-292; T-1KK); said 1 | Trust-card guard lane | LANDED | #897 merged. |
| F228, items 137 and 133 | 10-31, open (C0; T-1KK) | (no owner words) items 99, 105–113 open | NOT OWNER WORDS | Context: those items are now closed and were answered later under other rows. It carries no owner words. |
| F229, items 106, 109, 111, 112 and 114 rework | 11-01 11:43 (C1; C2); said 1 | "106, 109, 111, 112 and 114 … reworked by triage" | LANDED | Items reworked. |
| F230, pasted setup table (raw item 137) | 2026-11-01 17:14 CST; said 1 | data from the local ponytail scan: ... machine setup report ... system time zone is Eastern Standard Time | LANDED | The reply named four steps as the filing: guard-log-time-offset, install-drops-retired-files, ponytail-local-still-on and local-cc-version-lag. All four step files exist on origin/roadmap (checked). |
| F231, owner runs branch-protection switch (raw item 286) | Oct 31 14:49 CDT; said 1 | (coordinator relay, not owner words) You agreed in chat, 14:49 CDT, to run this yourself. (the branch-protection switch to the one check all-jobs-passed; the classifier refused the coordinator's PATCH, so the owner runs it) | LANDED | Read on Nov 2: claude-settings main requires one check, all-jobs-passed, with strict false. That matches the coordinator's read-back at 14:52 CDT. Degen and q_max are not covered by this row (F36, F58). |
| F232, ready list at each wake (raw item 371) | Oct 29 13:45 CDT (relayed standing rule in a compaction summary); said 1 | (relayed) Flywheel duty (shiv via the coordinator, Oct 29 13:45 CDT): at every wake and at each hourly check-in, send the coordinator a ready list. | LANDED | Recorded in decision session-tiers (docs/decisions/session-tiers.md, line 71) on main. Compliance is a session claim: triage says it sent the list at wakes. |
| F233 to F247, unassigned row numbers | — | none recovered | UNKNOWN | 15 row numbers. The merged list said F1 to F247, but its table stopped at F229. No raw item maps to these numbers. Their state is unknown. |
| F248, item 128 branch deletes | 2026-11-01 16:23 CST, page save, item 128 (triage `session_013NEJL2KiRdp1PFjjJxDuzq`) | `128 note, not done (PS C:\Users\ShivamSemwal> cd ~ ... foreach ($b in 'lane/impeccable-4.8.0','lane/drop-debug-port-ask','lane/fd-float-cc-newest') { gh api -X DELETE ... } PS C:\Users\ShivamSemwal>)`. He pasted the PowerShell run. The coordinator noted the second block pasted was the Mac version. | LANDED | Owner, Nov 1 16:23 CST, page save, item 128 (triage session_013NEJL2KiRdp1PFjjJxDuzq): "128 note, not done (PS C:\Users\ShivamSemwal> cd ~ ... foreach ($b in 'lane/impeccable-4.8.0','lane/drop-debug-port-ask','lane/fd-float-cc-newest') { gh api -X DELETE ... } PS C:\Users\ShivamSemwal>)". He pasted the PowerShell run; the coordinator noted the second pasted block was the Mac version. Reads of claude-settings branches for lane/impeccable-4.8.0, lane/drop-debug-port-ask and lane/fd-float-cc-newest return 404. The item was reopened later for lane/cc-pin-2.1.311, which is also gone. The standing grant "Acts the cloud refuses" (F51) does not cover item 128. |
| F249, item 128 done | 2026-11-01 16:34 CST, page save | `128 done` | LANDED | Owner, Nov 1 16:34 CST, page save: "128 done". Triage closed item 128, and the coordinator confirmed lane/cc-pin-2.1.311 gone. Same evidence as F248. |
| F250, branches-deleted note | 2026-11-01 16:23 CST, page save, relayed in coordinator compaction summary 2 | "Item 128: branches deleted." (coordinator's wording, not the owner's) | LANDED | Coordinator wording, not the owner's, in compaction summary 2 (Nov 1 16:23 CST): "Item 128: branches deleted." Ask: delete three merged branches. Same evidence as F248. The PC session later deleted one merged branch and kept seven unmerged. |
| F251, phone screenshots | 2026-10-30 12:48 to 14:04 CDT, triage `session_013NEJKzjtAeP99bACEE6uZw` | `[Image: original 332x2261 ...]` and later screenshots 358x2085 x3, 358x2131, 358x2026, 358x2257. These are phone screenshots of the waiting page, content unreadable. | UNKNOWN | Oct 30 12:48 to 14:04 CDT, triage session_013NEJKzjtAeP99bACEE6uZw: image-only phone screenshots of the waiting page ("[Image: original 332x2261 ...]", then 358x2085 three times, 358x2131, 358x2026, 358x2257). The reader could not read the images. They fall in the same window as the F88 and F94 complaints (send button grayed, unselectable), but I cannot trace them to a specific point. |
| F252, debug-port question (06:52 CST) | 2026-11-01 06:52 CST (the 12:52Z minute), triage `session_013NEJL2KiRdp1PFjjJxDuzq`, owner chat about the debug port | **Owner words not recovered.** The best match for the topic is the coordinator's chat question at 12:51:36Z, which `coord-01.txt` shows. It asked: "may agents open a debug port on an app?" with options a, b and c. Paging triage `2KiRdp...` backward with `list_events` takes about 8 minutes of transcript per page, so reaching 12:52Z needs roughly 70 more pages. I stopped. No earlier reader transcript holds the 12:52Z owner message. | UNKNOWN | Changed from LANDED. The owner words were not recovered, so LANDED cannot be verified. The evidence follows. Nov 1 06:52 CST, triage session_013NEJL2KiRdp1PFjjJxDuzq: owner chat about the debug port. The owner's words were not recovered verbatim. The nearest match is the coordinator's question at 12:51:36Z: "may agents open a debug port on an app?" with options a, b and c. The owner answered item 119 with "119 b (how do we ensure the port wont clash?)" on Nov 1 11:43 CST (F214). Guard rule debug-port-ask was dropped in commits 8179ec7e and c07ba54c, merged as #959 (batch-54-r2, merge e88b16d1). Decision design-skills on origin/main says the port question is answered by launching with --remote-debugging-port=0. Measured on headless Chrome; unmeasured for Electron and WebView2. |
### 7e. Missing rows (strict pass, M1 to M5)

The strict pass listed five points that no row covered. Each one maps to a row that is already in the table. This record adds no new rows.

| Strict-pass id | Row | State | Note |
|---|---|---|---|
| M1, item 128 branch deletes | F248 | LANDED | The four branches are absent on origin (checked). |
| M2, "128 done" (16:34 CST) | F249 | LANDED | Triage closed item 128. |
| M3, "Item 128: branches deleted." | F250 | LANDED | Coordinator wording, not owner words. |
| M4, phone screenshots | F251 | UNKNOWN | Image-only. The reader could not read the images. |
| M5, debug-port question (06:52 CST) | F252 | UNKNOWN | Changed from LANDED (section 2a). |

Three raw items had no row of their own. The strict pass covered them only inside host rows F149, F59 and F9. They are now rows: F230 (raw item 137, the pasted setup table), F231 (raw item 286, the owner runs the branch-protection switch) and F232 (raw item 371, the ready-list duty).

Method: the strict pass matched all 374 raw items to rows by content. This record checked four matches by hand: F30 ("what is step c29"), F67 (item 78), F204 (item 9) and F219 (item 110). Each held. A word-overlap check could not confirm the matches, because the rows paraphrase the owner.

## 8. Sources read and their gaps

Triage session keys follow the merge source. The short key is first. The session id follows it.

- Coordinator chunk 0 (Oct 31 19:12Z to Nov 1 00:33Z): about 14 owner messages. Several are truncated or relayed. The rulings at 15:00, 15:02 and 15:44 CDT are known only through relays.
- Coordinator chunk 1 (Nov 1 00:34Z to 17:52Z): three typed owner messages (03:56, 04:09 and 04:29 CST). The page saves at 04:26 and 11:43 CST, and the 11:51 yes, are known only through relays.
- Coordinator chunk 2 (Nov 1 17:55Z to Nov 2 00:23Z): 11 typed owner messages. The 17:37 CST grant and the 17:19 CST question are not verbatim.
- Coordinator chunk 3 (Nov 2 00:23Z to about 00:49Z): four direct owner messages. The answers at 18:39 to 18:46 CST are coordinator paraphrase. The 18:45 message is truncated.
- T-1qE (session_013NEJL1qEunLpTi68de3Jrv): 21 pages, Nov 1 16:34 CST to about 18:50 CST. Images are unreadable. The 16:23 and 16:31 items are relayed. The 17:37 grant appears only in a report.
- T-2Ki (session_013NEJL2KiRdp1PFjjJxDuzq): the whole transcript. Some lines are truncated. The 06:52 CST debug-port question is omitted.
- T-3DB (id ends 3DBJRohQygNLERynG): Nov 1 01:03Z to 06:13Z. No typed owner messages and no page saves. Its item 99 note is direct.
- T-292 (session_013NEJL292VcSHWeJrxDfTAE): 381 events, Oct 31 16:22 CDT to Nov 1 20:04 CDT. Only the item 99 page save is direct. Earlier owner feedback is not covered.
- T-1KK (id ends 1KKagcGMN1wVnKnmD): Oct 31 14:15 to 16:22 CDT. A gap runs from 19:17Z to 19:48Z, when the container was down. Relay bodies were cut to about 300 characters.
- T-3Mw (session_013NEJKzjtAeP99bACEE6uZw): read back to Oct 28 20:37 CDT, with more pages unread. Earlier owner messages are not covered (F39).
- Roadmap: the step files on origin/roadmap at 09fb532a.
- Main: decision records, .claude/CLAUDE.md, settings.json and the waiting-page skill.
- GitHub: pull request states, and a live read of branch protection on degen and q_max. Post-read checks used gh api for PRs #992, #1001, #1003 and #1007, and the branch list on origin.
- Waiting page: 147 items, read through its database at the read. Six items were open then.

| N1, lone PR ready (owner, 19:19 CST) | 2026-11-01 19:19 CST | when an operation is occuring solo and/or there is only one "outcome" PR (ie it's not going into an integration branch) then of course they can be marked ready (typed in the pr-acts-grant lane session; quoted in draft PR #1007) | IN FLIGHT | Quoted in docs/decisions/auto-mode-owner-acts.md on draft PR #1007. Not merged, so not on main. |
| N2, coordinators merge across repos (owner, 19:23 CST) | 2026-11-01 19:23 CST | yes coordinators can merge across repos that is okay it doens't need to juts be in its repo (quoted in draft PR #1007) | IN FLIGHT | Quoted in docs/decisions/standing-merge-grant.md on draft PR #1007. Not merged. |
| N3, option C refused (owner, 19:23 CST) | 2026-11-01 19:23 CST | option C absolutely not correct (on the option that lets a lane merge its own PR; quoted in draft PR #1007) | IN FLIGHT | Quoted in docs/decisions/standing-merge-grant.md on draft PR #1007. Not merged. A lane that a coordinator started never merges. |
| N4, just me and claude (owner, 19:23 CST) | 2026-11-01 19:23 CST | just me and claude building and maintaining these repos (quoted in draft PR #1007) | IN FLIGHT | Quoted in docs/decisions/standing-merge-grant.md on draft PR #1007. Not merged. The decision reads it as a no-GitHub-review rule. The owner did not state that rule in those words. |
| N5, idle compaction off (owner, 19:27 CST) | 2026-11-01 19:27 CST (per the title of claude-settings draft PR #1003) | owner words not in inputs | UNKNOWN | Draft PR #1003 sets idleCompaction false and cites decision precompact-handoff, rule 3. The owner words are not in this record's inputs. |