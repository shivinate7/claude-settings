# Feedback audit: 234 owner items, re-read Nov 1 after 19:23 CST

This record holds the audit of the owner's feedback. It has 234 rows: F1 to F229 and F248 to F252. Eighteen row numbers, F230 to F247, were never written. Section 2 lists each change made after the read, with its evidence.

Glosses: each id carries a short gloss where it first appears in a section. Section 7 glosses every row id and every PR, step and decision the rows cite.

Owner rules that govern this record (Nov 1, 18:48 to 18:50 CST): "record all of it, show me where we fell short, and how we intend to get back on course"; "nothing in that report should be ommitted or marked superceded unless oyu can trace that supercession exactly back to something i stated. dont be easy on yourself."

## 1. Unknown reads and gaps

- F230 to F247 (unassigned row numbers): 18 numbers. The merged list said F1 to F247, but its table stopped at F229. The raw-item match found no owner point outside F1 to F229 and F248 to F252. The numbers stay unassigned. Their state is unknown.
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
| LANDED | 169 |
| IN FLIGHT | 40 |
| FILED NOT STARTED | 7 |
| UNKNOWN | 6 rows, plus F230 to F247 (18 numbers, unassigned) |
| NOT OWNER WORDS | 4 |
| SUPERSEDED | 1 |
| CONTRADICTED | 2 |
| DROPPED | 5 |
| PROMISED NOT FILED | 0 |

The rows total 234. The draft counted 164 landed and 5 unknown before this update.

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
23. **Unknown, with no evidence beyond a session's word or a read that could not run.** F39, F82, F84, F93, F251 and F252, plus F230 to F247 (18 numbers, unassigned).
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
23. Unknown rows (F39, F82, F84, F93, F251, F252, F230 to F247): no owner yet. Each unknown names the read that could not run (section 1).
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

| id | state | evidence |
|---|---|---|
| F1, flywheel restart | LANDED | Batches 39 to 58 merged (#916 to #977). |
| F2, batch 37 rebuild | LANDED | #904 merged Oct 31 17:09 CDT. |
| F3, trust-card guard merge | LANDED | #897 merged in batch 39 (#916); step trust-card-guard done. |
| F4, answered chat question | LANDED | Answered in chat (matches the coordinator transcript). |
| F5, wrong-tier rule | LANDED | "Wrong tier" in decision session-tiers and the shiv-stylisms style. The hook is F6. |
| F6, tier-boundary guard | IN FLIGHT | #919 still a draft, opened Oct 31 20:14 CDT, about 23 h; not in batch 59. Step tier-boundaries-enforced doing. |
| F7, tier-boundary guard folded into PR 919 | IN FLIGHT | Folded into #919 (draft). |
| F8, answered chat question | LANDED | Answered in chat (matches the coordinator transcript). |
| F9, session-tiers decision | LANDED | Decision session-tiers. |
| F10, session-tiers decision | LANDED | Decision session-tiers. |
| F11, grants in roadmap | LANDED | Decision session-tiers names "Grants living in roadmap". |
| F12, compliance-only rule | LANDED | Decision session-tiers "compliance only". |
| F13, roadmap-one-writer guard | LANDED | Decision session-tiers. The guard is step roadmap-one-writer: doing, no PR. |
| F14, arbiter effort rule | LANDED | Decision session-tiers line 57: arbiter high effort. |
| F15, session-tiers overturn | LANDED | #869 merged (batch 34); "Overturn" in decision session-tiers. |
| F16, lane effort rule | LANDED | Decision session-tiers line 46; step lane-effort-medium done. |
| F17, freeze record after PAUSE | CONTRADICTED | By the session's own report, triage wrote the freeze record after PAUSE. No pause record on main. Its reply was not seen. |
| F18, waiting-page reply rule | LANDED | skills/waiting-page/SKILL.md: "Never reply in a comment thread". |
| F19, roadmap live check | IN FLIGHT | Step roadmap-live-check-true doing, no PR. Still true at 19:15 CST: 8 todo steps say "Ready: no open question". |
| F20, refusal note PR 979 | IN FLIGHT | #979 draft. Dropped from batch 59 for a red form check. No roadmap step. |
| F21, child repos catch up | IN FLIGHT | child-repo-gap and r5 doing; r6 and one-check-other-repos todo; compliance-check is not done. Archiving: #976 merged in batch 59 and #989 (draft). |
| F22, item 147 closed | LANDED | Item 147 closed. |
| F23, roadmap out of step | IN FLIGHT | roadmap-live-check-true and roadmap-one-writer doing; page-ruling-reaches-step todo with #981 draft. Not fixed yet: 9 steps say todo while their PR is open. |
| F24, answers routed to roadmap | LANDED | Answered. The answers had sat unrouted (P1). |
| F25, visits held process | LANDED | Process only: visits held, then F26. |
| F26, three repo merges | LANDED | joyous#59, banchi#1004 and mailaudit#174 merged Nov 1. |
| F27, turn-report clash step | LANDED | Step tracking-turn-report-clash done (#966). |
| F28, org instructions note | DROPPED | No home on main or the roadmap. Compaction summaries only. |
| F29, lost-worktree step | LANDED | Step resume-lost-worktree done (6f89e45). |
| F30, step c29 answer | LANDED | Answered (triage-sourced; not re-read). |
| F31, chat grant home | CONTRADICTED | Item 100's home is "process only (coordinator handoff)". The mandate puts a chat grant in CLAUDE.md or the merge config, never only in a handoff. |
| F32, compliance-defined decision | LANDED | Decision compliance-defined ("known exemption"); #910 merged in batch 39. |
| F33, q_max PR 995 merge | LANDED | q_max#995 merged Oct 31 20:06 CDT. |
| F34, child-repo-gap step | IN FLIGHT | Step child-repo-gap doing since Oct 29 (3 days). |
| F35, item 70 closed | LANDED | Item 70 closed. Its follow-on, banchi#1003, is still open (F43). |
| F36, shared branch protection | FILED NOT STARTED | Item 78 closed with "78 done" (owner act). A live read of degen main protection gives check all-jobs-passed with strict: true. The shared form is strict: false (main-branch-protection line 22). Step tci-9-live-protection is todo. |
| F37, picks filed for iOS and Mac load | FILED NOT STARTED | Picks are filed (f236bcc). c91 (iOS standard) and c196 (Mac load cap) still todo; child-repo-gap doing. |
| F38, child repos asked twice | IN FLIGHT | Asked twice (with F21). Step r1 done, but the repo fixes (child-repo-gap, r5, r6) are open. |
| F39, earlier session report | UNKNOWN | Session report only. No file or step evidence found. Origin unclear; may not be owner words. Needs the triage transcript from before Oct 28 20:37. |
| F40, item 99 closed | LANDED | Item 99 closed. |
| F41, item 99 closed later version | LANDED | Item 99 closed (v5 and later). |
| F42, page judge partial-step check | LANDED | #961 merged in batch 55: the page judge flags a partial-line step. |
| F43, banchi item 99 follow-on | IN FLIGHT | Owner finished item 99 a at 16:32 CST: banchi c174 pushed (commit 1039411b). The coordinator first said it was not pushed, from a stale fetch, then verified. Banchi PR #1003 (guard-shell tree clause) is still an open draft (checked after the read). |
| F44, q_max PR 997 merge | LANDED | q_max#997 merged via #1001, Nov 1 18:14 CST. The owner had to ask 3 times. |
| F45, attach repos and degen PR 313 merge | LANDED | degen#313 merged 17:19 CST; joyous#53 merged. Page item 138 is still open (P1). |
| F46, item 143 b, other-checkout guard | IN FLIGHT | Item 143 b (owner, 17:25 CST): the shared guard refuses cd into another checkout, then banchi PR #1003 merges. Page item 143 is open with no recorded answer. Branch other-checkout-cd-gap (origin) has three commits, the last at 19:40 CST. It is not on main and has no PR. Whether the lane is running is not verified. |
| F47, all-repos grant | IN FLIGHT | Draft PR #1007 (all-repos grant draft, head pr-acts-grant, opened 19:33 CST) holds the grant in docs/decisions/standing-merge-grant.md and docs/decisions/auto-mode-owner-acts.md. It quotes the 17:37 CST grant, which the coordinator relayed and which is not verbatim in the transcript read, and the owner's 19:19 and 19:23 CST rulings. Not merged. Not in .claude/CLAUDE.md. The roadmap note on step merge-grant-switch names lane classifier-refusals-allowed. No branch by that name exists on origin. |
| F48, remote tools in allow list | LANDED | PR #976 (remote add_repo and archive_session allow list) merged in batch 59 (main 55b27ac2, 19:31 CST). |
| F49, auto-mode owner-acts decision | LANDED | One home: decision auto-mode-owner-acts plus settings.json autoMode.allow. The widening it needed is F47. |
| F50, allow list too rigid | IN FLIGHT | Owner, Nov 1 about 17:38 CST: "IS IT ALSO REALLY DUMB THE ALLOW LIST WAS SO RIGID THAT IT BLOCKED THIS." The widening sits in draft PR #1007 (all-repos grant draft). Not merged. |
| F51, standing grants in CLAUDE.md | LANDED | .claude/CLAUDE.md, Standing grants. |
| F52, PR 878 merge | LANDED | #878 merged (batch 37). |
| F53, standing merge grant decision | LANDED | Decision standing-merge-grant; step coordinator-merge-grant done. |
| F54, PR 878 and item 98 | LANDED | #878 merged; item 98 closed. |
| F55, accepted ruling | LANDED | Accepted. |
| F56, answered question | LANDED | Answered. |
| F57, batch runner may merge | LANDED | #878 merged (batch runner may merge). |
| F58, same required checks | FILED NOT STARTED | Decision same-check-kinds exists; item 87 closed. A live read of q_max main gives HTTP 404 and .protected false. The owner's rule was the same required checks in every repo. Step tci-9-live-protection is todo. No step file named tci-9 exists. |
| F59, main-branch-protection decision | LANDED | Decision main-branch-protection. |
| F60, answered question | LANDED | Answered (matches the coordinator transcript). |
| F61, item 101 closed | LANDED | Item 101 closed. |
| F62, gh account clear | LANDED | #905 merged in batch 45; step gh-account-clear done. |
| F63, act-in-place default account | LANDED | Decision act-in-place names shivinate7 as the default. |
| F64, answered question | LANDED | Answered. |
| F65, answered question | LANDED | Answered. |
| F66, owner's own setting | LANDED | Item 103 closed (owner's own setting). |
| F67, item 78 Mac run | LANDED | Item 78 closed. |
| F68, command-per-os step | LANDED | #894 merged; step command-per-os done. |
| F69, answered question | LANDED | Answered. |
| F70, never judge broken without asking | DROPPED | "Never judge something broken without asking" was kept only as a handoff premise. No record on main. |
| F71, options a to d for item 108 | LANDED | Report gave options a to d (item 108). |
| F72, inbox skip PR 903 | LANDED | #903 merged (batch 40). Partly replaced by F75 (owner, Nov 1 04:29). |
| F73, Apple TV loop fix | LANDED | Answered; #940. |
| F74, PR 940 merge | LANDED | #940 merged in batch 46. |
| F75, owner-feedback-inbox decision | LANDED | Decision owner-feedback-inbox names the bandaid; debt inbox-saves-other-notices. |
| F76, repeat detection | IN FLIGHT | #999 draft. Step feedback-repeat-detect still says todo. |
| F77, meaning match | IN FLIGHT | #999 draft (meaning match, 1f40e864). |
| F78, one inbox per repo | IN FLIGHT | #983 draft. Step one-inbox-per-repo still says todo. |
| F79, none-with-note direction | LANDED | PR #980 merged in batch 59 (main 55b27ac2, 19:31 CST). Step none-with-note-is-direction was not checked after the merge. Said twice. |
| F80, feel-fix device check | LANDED | PR #987 merged in batch 59 (main 55b27ac2, 19:31 CST). Step feel-fix-needs-device-check was not checked after the merge. |
| F81, lane closes after records | IN FLIGHT | #989 draft, not in batch 59. |
| F82, waiting-page width check | UNKNOWN | Session report (v20 at 360 to 430 px). Not re-checked. Needs a headless render of the waiting-page template at 360 to 430 px. |
| F83, waiting-page republish | LANDED | #971 merged in batch 58; steps page-stale-hook and wp-republish-on-template done. |
| F84, Oct 29 re-save | UNKNOWN | Re-save is a session claim. No evidence. Page items keep only the last answer, so the Oct 29 14:49 re-save cannot be rebuilt. |
| F85, answered triage question | LANDED | Answered (triage-sourced; not re-read). |
| F86, triage watches page | LANDED | Step triage-watches-page done. |
| F87, page Status tab | LANDED | The page's Status tab carries the roadmap data (read at 19:15 CST). |
| F88, grey Send button | DROPPED | The grey Send button and "failed to fetch" got no diagnosis and no step. |
| F89, c204 page items | LANDED | c204 items closed; #806. |
| F90, page shows last answer | LANDED | Step page-shows-last-answer done. The page still lags (P1). |
| F91, note box always open | LANDED | Step note-always-open done. |
| F92, Queue title | LANDED | #874 merged; page titled Queue. |
| F93, deleted Artifact page | UNKNOWN | Delete is a session claim. The Artifact read of JGqfvgXBuLqWUm1CX6Bv5h answers "not found, may be deleted or not shared with you", which cannot tell the two apart. |
| F94, item 94 pick a | LANDED | Page item 94 is closed with pick a. Step d4 records "item 94 a, Oct 30 15:02 CDT", after the 14:48 complaint. So he could answer it. |
| F95, drop-take-pick step | LANDED | Step drop-take-pick done. |
| F96, PR 880 merge | LANDED | #880 merged. |
| F97, option keys are letters | LANDED | #898 merged; decision option-keys-are-letters. |
| F98, rework leaves page | LANDED | Decision rework-leaves-page. |
| F99, item 99 answer | LANDED | Answered (triage-sourced; not re-read). |
| F100, parked-item actions | FILED NOT STARTED | Step page-parked-actions is todo and ready. Draft PR #1005 (waiting page: unpark and drop) opened after the read. The state is not changed here (section 2c). |
| F101, PR 901 merge | LANDED | #901 merged. |
| F102, answered question | LANDED | Answered. |
| F103, PR 901 merge | LANDED | #901 merged. |
| F104, PR 967 merge | LANDED | #967 merged in batch 58. |
| F105, page item check at write | IN FLIGHT | #985 draft; step page-item-checked-at-write doing. Said twice. |
| F106, newer questions rise | IN FLIGHT | #997 draft opened 19:10 CST; step still says todo. Said twice ("i said already"). |
| F107, waiting-page ask box | FILED NOT STARTED | Step page-ask-box todo, ready, no lane. |
| F108, item 142 closed | LANDED | Item 142 closed. |
| F109, page question shape step | LANDED | Step page-question-shape done. |
| F110, page question shape step | LANDED | Step page-question-shape done. |
| F111, PR 902 merge | LANDED | #902 merged. |
| F112, answered question | LANDED | Answered. |
| F113, repeated questions | IN FLIGHT | Judge landed (#956, #961). The past-rulings check (question-checks-past-rulings) is doing with no PR. Said 3 times; the last was angry, at 18:45. |
| F114, handoff without copied lists | LANDED | Step handoff-no-copied-lists done. |
| F115, PR 950 merge | LANDED | #950 merged in batch 55. |
| F116, item 114 closed | LANDED | Item 114 closed. |
| F117, past-rulings check for item 117 | IN FLIGHT | Step question-checks-past-rulings doing, no PR; page-ruling-reaches-step #981 draft. A repeat miss. |
| F118, past-rulings check for item 118 | IN FLIGHT | Same lane; no PR. |
| F119, ci-job-caps question asked again | IN FLIGHT | Claude-settings draft PR #1001 (ci-job-caps stopgap, head ci-job-caps-stopgap) opened 19:23 CST, after the read. It rewrites ci-job-caps for the owner's 18:44 CST ruling. It lists an open clash with the kept rule "a cap rises only with a measured figure". Step time-pinned-tests-go is todo on origin/roadmap (updated 19:25 CST). No branch or PR named time-pinned-tests-go exists, so the lane start is not verified. The claim that ci-job-caps was rewritten under test-strategy-reset is still false on main: ci-job-caps was last touched Oct 28 (strict pass). |
| F120, glossary meets owner | IN FLIGHT | #995 draft; step glossary-meets-owner-halfway doing. |
| F121, coordinator text, not owner words | NOT OWNER WORDS | Context only. The coordinator's own text is in coord-03.txt and coord-02.txt (line 2324). No typed owner message in the 18:10 to 18:30 CST window says "override". |
| F122, apology-only answer | DROPPED | Apology only. No step for this class beyond the P4 lane. |
| F123, q_max CI groups | IN FLIGHT | coord-03.txt lines 676 to 679: the coordinator re-posed the q_max question with option d. The owner picked 12 groups; the coordinator reports "your 18:43 CST ruling" (relayed, not verbatim). Step tci-11-qmax-shards is doing. |
| F124, item 77 closed | LANDED | Item 77 closed. |
| F125, PR 879 merge | LANDED | #879 merged. |
| F126, answered question | LANDED | Answered. |
| F127, PR 879 and PR 899 merges | LANDED | #879 and #899 merged. Not superseded. |
| F128, item 115 closed | LANDED | Item 115 closed. |
| F129, agent-model-cap decision | LANDED | Decision agent-model-cap: round-3 builder on Opus. |
| F130, PR 957 and PR 960 merges | LANDED | #957 and #960 merged. |
| F131, one-model-rule routing | LANDED | Routed to step one-model-rule. |
| F132, one-model-rule step | IN FLIGHT | Step one-model-rule doing; #993 draft, #972 merged in batch 59. |
| F133, blind Opus model review | LANDED | The blind Opus agent ran. Its findings are in the "why" of step one-model-rule. PR #972 (role lists lint) merged in batch 59 (main 55b27ac2). At the read it was still an open draft. |
| F134, item 127 rewrite | LANDED | Item 127 rewritten. Page-closed; not matched to a PR. |
| F135, item 127 closed late | LANDED | Item 127 closed (routed late). Page-closed; not matched to a PR. |
| F136, answered question | LANDED | Answered. |
| F137, item 137 search agent | IN FLIGHT | Item 137 still open, reworked into a, b and c. |
| F138, the "137 a" delivery | IN FLIGHT | The 18:39 "137 a" is not on the page: the item shows the 17:25 note (last answer 17:25 CST) and is open. Step one-model-rule was last updated 16:53 CST and still says it waits on shiv for item 137. Only coord-03.txt line 474 ("Sent your item 137 pick (a)") says the pick reached the lane; delivery is unverified. |
| F139, PR 962 and PR 964 merges | LANDED | #962 and #964 merged. |
| F140, mods relevance review | LANDED | Step mods-relevance-review done. |
| F141, answered question | LANDED | Answered. |
| F142, items 117 and 118 closed | LANDED | Items 117 and 118 closed. Page-closed; not matched to a PR. |
| F143, session-board mod limits | LANDED | #952 merged (batch 54) in decision session-board-mod-limits. No record named session-board-stop-limit exists. |
| F144, item 118 closed | LANDED | Item 118 closed, no build. |
| F145, item 106 vetted | LANDED | Item 106 vetted. |
| F146, item 106 rewrite | LANDED | Item 106 rewritten. |
| F147, item 106 rework | LANDED | Item 106 reworked. |
| F148, ponytail off and deep dive | LANDED | #951 merged; step ponytail-off-deep-dive done. |
| F149, item 122 closed | LANDED | Item 122 closed; 0de0e1bb. |
| F150, ponytail removal on desktop | LANDED | Item 140 closed. Step ponytail-local-still-on still says todo (P1). |
| F151, CI figure of 25 of 80 | LANDED | #895 merged in batch 39. The owner's 25-of-80 figure is unmeasured. |
| F152, c95 milestone steps | LANDED | Steps c95 and c95-milestone-runs done. |
| F153, c95 milestone runs | LANDED | Step c95-milestone-runs done (a1431e3b). |
| F154, c95 note | LANDED | c95 note. |
| F155, ci-hygiene refresh | FILED NOT STARTED | Skill refresh merged (#923). The per-repo fix lanes never started: step todo, set back at 18:03 CST. Asked Oct 30 15:08 CDT. |
| F156, test-ci-standard plan | LANDED | #969 merged (plan test-ci-standard). |
| F157, item 133 rewrite | LANDED | Item 133 rewritten. |
| F158, platform test homes | FILED NOT STARTED | Step tci-5-platform-tested todo (waits). |
| F159, Swift test ruling for item 133 | LANDED | Item 133 withdrawn. Asked 3 times about a settled Oct 27 ruling (P4). |
| F160, tci-6 mutation engine | IN FLIGHT | Step tci-6 doing; #996 draft. |
| F161, phone lane dropped | LANDED | Item 135 closed; phone lane dropped. |
| F162, q_max CI question answered | LANDED | coord-03.txt line 656: the coordinator answered "Partly" with detail, so the question was answered. |
| F163, q_max record ci-spend-gate | IN FLIGHT | Step tci-11-qmax-shards doing. The cited record exists: q_max docs/decisions/ci-spend-gate.md (D-718) on origin/main e8f990272, last touched in 71c355f07. |
| F164, sim-no-diagnose step | LANDED | Step sim-no-diagnose done. |
| F165, comment narration patterns | IN FLIGHT | #998 draft; comment-narration-patterns todo. |
| F166, PR 966 merge | LANDED | #966 merged. |
| F167, turn-report clash, said many times | LANDED | Step tracking-turn-report-clash done (#966). Said many times. |
| F168, stale prose rule | LANDED | PR #975 merged in batch 59 (main 55b27ac2, 19:31 CST). Step stale-prose-standing is doing on origin/roadmap. |
| F169, design-skills decision | LANDED | Decision design-skills (batch 54, #959). |
| F170, c146 plan fix | LANDED | c146 plan fixed (d228ab79). |
| F171, merge-grant switch | LANDED | Commit 12760618 (Oct 30, on origin/main) refuses a cloud merge when merge.standingGrant is false (merge/merge.py line 2477). Test class StandingGrantSwitch exists in merge/test_merge.py. Decision standing-merge-grant names the switch. The step was set back to todo at 18:03 CST, and it says done now (origin/roadmap, 19:41 CST). Its lane session started 19:30 CST. The draft read the step status, not the code. Said 3 times. |
| F172, session turn limit | LANDED | PR #978 merged in batch 59 (main 55b27ac2, commit c76a3447, 19:31 CST). Its title: session-tiers, no usage limit for standing sessions. |
| F173, usage-tally rotation limit | SUPERSEDED | Traced to the page item 109 answer (Nov 1 17:56:23 CST): choice b, with the note "I lean towards B if it works and maybe somehow log to see if i should revisit". Option b is "No limit; let compaction and the handoff rewrite carry the session". The answer is conditional. The record change sat in draft PR #978; PR #978 merged in batch 59 (main 55b27ac2, commit c76a3447, 19:31 CST). Whether main's code still holds the tally limit is not checked. |
| F174, item 109 rework | LANDED | Item 109 reworked. |
| F175, answered question | LANDED | Answered. |
| F176, answered question | LANDED | Answered. |
| F177, handoff read before write | IN FLIGHT | #994 draft. Step handoff-read-before-write still says todo. |
| F178, compaction carry watch | IN FLIGHT | #978 merged in batch 59; #986 draft. Step compaction-carry-watch still says todo. |
| F179, handoff fixes | IN FLIGHT | Handoff fixes #982 (held) and #994 (draft). |
| F180, idle resume compacts | IN FLIGHT | Step idle-resume-compacts is doing. Draft PR #1002 (decision idle-resume-compacts) opened after the read. Claude-settings draft PR #1003 (idle compaction off) sets idle compaction off. |
| F181, handoff checkpoint | LANDED | Answered; #982. |
| F182, handoff analysis lane | IN FLIGHT | #982 held; analysis lane; the pick is open. |
| F183, handoff lines in PR 986 | IN FLIGHT | Added to #986 (draft). |
| F184, answered question | LANDED | Answered. |
| F185, owner's own setting | LANDED | Owner's own setting. No record owed. |
| F186, answered question | LANDED | Answered; ambiguity flagged. |
| F187, coordinator text, not owner words | NOT OWNER WORDS | Context only. The coordinator's own text is in coord-02.txt (line 2309). No typed owner message in the 18:10 to 18:30 CST window says "override". |
| F188, no permission rule claim | IN FLIGHT | "No permission rule can lift it" is an inference. The docs are silent (coord-03.txt line 314). The owner asked for permissions to be added and none were. Only the one-way pc-bridge workaround exists. |
| F189, pc-bridge trust test session | LANDED | Session session_013NEJL4LniUvGXrcRXsLkcK exists, titled "pc-bridge (trust test)", created 00:21Z (18:21 CST), parent is the coordinator. It tags itself pc-bridge. |
| F190, trust error and owner's plan | IN FLIGHT | coord-03.txt line 314: the docs research is back and says nothing on the trust error. The coordinator's question about the owner's plan is unanswered, and no step exists. |
| F191, coordinator text, not owner words | NOT OWNER WORDS | Context only. The coordinator's own text is in coord-02.txt (line 2331). No typed owner message in the 18:10 to 18:30 CST window says "override". |
| F192, item 144 closed | LANDED | Item 144 closed. |
| F193, answered question | LANDED | Answered. |
| F194, answered question | LANDED | Answered. |
| F195, spawn mode prompt | LANDED | Item 144 closed. The cloud start gap waits in step local-folder-for-owner-acts (todo). |
| F196, answered question | LANDED | Answered. |
| F197, local CC version lag note | LANDED | Noted on step local-cc-version-lag. |
| F198, local CC version lag step | LANDED | Step local-cc-version-lag done. |
| F199, answered question | LANDED | Answered. |
| F200, claude update switch | LANDED | Switched to claude update. |
| F201, step 102cff36 done | LANDED | Step done (102cff36). No version is recorded. |
| F202, local and cloud setup steps | LANDED | Steps filed (a5d733c0, 5087b7ce, 48a2dc28). |
| F203, at-my-computer offer | DROPPED | The offer got no reply. |
| F204, item 9 closed | LANDED | Item 9 closed. |
| F205, answered question | LANDED | Answered. |
| F206, PR 955 merge principles | LANDED | #955 merged; docs/design/principles.md. |
| F207, answered question | LANDED | Answered. |
| F208, answered question | LANDED | Answered. |
| F209, PR 962 merge | LANDED | #962 merged in batch 56. |
| F210, ux-house-rules decision | LANDED | Decision ux-house-rules: each rule names its outcome. |
| F211, PR 964 merge | LANDED | #964 merged. Items 130 and 131 are open for the owner. |
| F212, item 132 closed | LANDED | Item 132 closed. |
| F213, item 129 closed | LANDED | Item 129 closed. |
| F214, debug-port answer and PR 959 | LANDED | #959 merged. Tested on headless Chrome only. |
| F215, d4 rewrite | LANDED | d4 rewritten. |
| F216, item 82 rework | LANDED | Item 82 reworked. |
| F217, item 95 b record | LANDED | 95 b recorded (d4v3-slot-word). |
| F218, d4 logged | LANDED | Logged on d4 (1adea163). |
| F219, test-merge-conflict-role step | LANDED | #939 merged; step test-merge-conflict-role done. |
| F220, held for PR 919 | IN FLIGHT | Held for #919 (draft). |
| F221, rescoped item | LANDED | Rescoped. |
| F222, item 111 closed | LANDED | Item 111 closed. |
| F223, re-explained | LANDED | Re-explained. |
| F224, PR 919 guard log | IN FLIGHT | The step note says the log is new work for the lane; it is not in #919 yet. |
| F225, a-kill-by-pid decision | LANDED | Decision a-kill-by-pid-needs-an-owned-pid. |
| F226, PR 953 merge | LANDED | #953 merged in batch 54. |
| F227, trust-card guard lane | LANDED | #897 merged. |
| F228, items 137 and 133 | NOT OWNER WORDS | Context: those items are now closed and were answered later under other rows. It carries no owner words. |
| F229, items 106, 109, 111, 112 and 114 rework | LANDED | Items reworked. |
| F230 to F247, unassigned row numbers | UNKNOWN | 18 rows. The merged list claims F1 to F247 but its table stops at F229. The 374 raw items cannot be mapped to these rows. The missing read is the merger's lost rows. They probably held finer points that F1 to F229 carry only in part. |
| F248, item 128 branch deletes | LANDED | Owner, Nov 1 16:23 CST, page save, item 128 (triage session_013NEJL2KiRdp1PFjjJxDuzq): "128 note, not done (PS C:\Users\ShivamSemwal> cd ~ ... foreach ($b in 'lane/impeccable-4.8.0','lane/drop-debug-port-ask','lane/fd-float-cc-newest') { gh api -X DELETE ... } PS C:\Users\ShivamSemwal>)". He pasted the PowerShell run; the coordinator noted the second pasted block was the Mac version. Reads of claude-settings branches for lane/impeccable-4.8.0, lane/drop-debug-port-ask and lane/fd-float-cc-newest return 404. The item was reopened later for lane/cc-pin-2.1.311, which is also gone. The standing grant "Acts the cloud refuses" (F51) does not cover item 128. |
| F249, item 128 done | LANDED | Owner, Nov 1 16:34 CST, page save: "128 done". Triage closed item 128, and the coordinator confirmed lane/cc-pin-2.1.311 gone. Same evidence as F248. |
| F250, branches-deleted note | LANDED | Coordinator wording, not the owner's, in compaction summary 2 (Nov 1 16:23 CST): "Item 128: branches deleted." Ask: delete three merged branches. Same evidence as F248. The PC session later deleted one merged branch and kept seven unmerged. |
| F251, phone screenshots | UNKNOWN | Oct 30 12:48 to 14:04 CDT, triage session_013NEJKzjtAeP99bACEE6uZw: image-only phone screenshots of the waiting page ("[Image: original 332x2261 ...]", then 358x2085 three times, 358x2131, 358x2026, 358x2257). The reader could not read the images. They fall in the same window as the F88 and F94 complaints (send button grayed, unselectable), but I cannot trace them to a specific point. |
| F252, debug-port question (06:52 CST) | UNKNOWN | Changed from LANDED. The owner words were not recovered, so LANDED cannot be verified. The evidence follows. Nov 1 06:52 CST, triage session_013NEJL2KiRdp1PFjjJxDuzq: owner chat about the debug port. The owner's words were not recovered verbatim. The nearest match is the coordinator's question at 12:51:36Z: "may agents open a debug port on an app?" with options a, b and c. The owner answered item 119 with "119 b (how do we ensure the port wont clash?)" on Nov 1 11:43 CST (F214). Guard rule debug-port-ask was dropped in commits 8179ec7e and c07ba54c, merged as #959 (batch-54-r2, merge e88b16d1). Decision design-skills on origin/main says the port question is answered by launching with --remote-debugging-port=0. Measured on headless Chrome; unmeasured for Electron and WebView2. |
### 7e. Missing rows (strict pass, M1 to M5)

The strict pass listed five points that no row covered. Each one maps to a row that is already in the table. This record adds no new rows.

| Strict-pass id | Row | State | Note |
|---|---|---|---|
| M1, item 128 branch deletes | F248 | LANDED | The four branches are absent on origin (checked). |
| M2, "128 done" (16:34 CST) | F249 | LANDED | Triage closed item 128. |
| M3, "Item 128: branches deleted." | F250 | LANDED | Coordinator wording, not owner words. |
| M4, phone screenshots | F251 | UNKNOWN | Image-only. The reader could not read the images. |
| M5, debug-port question (06:52 CST) | F252 | UNKNOWN | Changed from LANDED (section 2a). |

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
