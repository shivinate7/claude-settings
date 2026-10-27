# Build advisor outbox

- 2026-10-27 01:40 CDT: merged batch #678 (c109, blind brief template) as 724b7a70; #676 closed as replaced. c109 is done.
- 2026-10-27 01:49 CDT: batch #680 opened with c80+c85 (#679, override reaches every gate) alone; CI running.

- 2026-10-27 02:05 CDT: batch #680 red on gates; lint/test_settings_matcher.py still reads the moved judges from settings.json. Closed; c80+c85 sent back to its lane. Defect: the lane suites did not include test_settings_matcher.

- 2026-10-27 03:27 CDT: #679 went green after one pointer-windows re-run (a harness IOException in install-set.test.ps1:247, a file read while still held open; flaky). Its merge was refused because main moved (#664). Batch #683 now holds #679, #681 (c105) and #682 (c100), built from main d99ba766.

- 2026-10-27 04:15 CDT: batch #683 merged as b031394f: #679 (c80+c85, override reaches every gate), #681 (c105, repo colours), #682 (c100, waiting page final look). c80, c85, c100 and c105 are done. The live waiting pages still need a republish, home-app first. Advisor (7) is finished; the successor reads handoffs/build-2026-10-27c.md.

- 2026-10-27 04:25 CDT (advisor 8): the live waiting pages (home-app, degen, mailaudit) live in another account; the cloud cannot read them. Republish goes to a Mac session through the local liaison: briefs/c100-republish-live-pages.md.
- 2026-10-27 04:25 CDT: briefed and asked for build threads: c114 (CI reads by REST), c118 (a pick reaches a click), c117 (scratch delete shape), c116 (limits kept silently), c113+c115 (repo kind and caution, one lane). Marked doing.
- For triage: c112 (Designs tab) looks built on main b031394f (skills/waiting-page/page.html has the Designs tab and sandboxed frame); check and close. c80, c85, c100, c105 still read "doing" in the data; they merged in #683.
- 2026-10-27 04:25 CDT: c100 republish deferred on shiv: the live pages belong to a third account (cloud and Mac both get 404); shiv asked to share. Finding for triage: the Mac's auto mode refused a claude-settings reinstall as "Self-Modification", so a Mac session cannot pick up merged claude-settings work by reinstalling. Candidate new step.
- 2026-10-27 04:30 CDT: c116 green and reviewed (#684, head 8316987). Joined integration branch batch-oct27m; the batch PR opens when more lanes arrive.
- 2026-10-27 04:30 CDT: c114 green and reviewed (#685, head 6fd0a4b). Joined batch-oct27m.
- 2026-10-27 04:32 CDT: c113+c115 (#686, 044eb71) and c118 (#687, 8f0e026) joined batch-oct27m (head 73c54cf; docs/debts/notes.md conflict resolved as a union of both lanes' notes). Lane tests, rule_audit, hook_catalog, settings_matcher and test_gates green on the combined tree. Waiting on c117, then the batch PR opens.
- 2026-10-27 05:20 CDT: batch #689 (batch-oct27n, from main b031394) is ready with c116 #684, c114 #685, c113+c115 #686, c118 #687, c117 #688. Two form fixes on lane branches: c117's record slug was over 32 characters; c114 had one long note sentence. batch-oct27m is a dead first build of this batch; its force-push was refused, so it stays on origin until the merge cleanup.
- 2026-10-27 05:45 CDT: batch #689 red. c114 failed on Windows: the `&` in its REST URL is read by cmd. c114 was dropped and sent back to its lane. Two unrelated failures (a test_sendmessage_state hang on Windows, a test_check_mod_versions teardown race on Linux) get their one re-run in the new batch. #690 (batch-oct27o) holds c116, c113+c115, c118 and c117. #689 closed as replaced.
- 2026-10-27 06:00 CDT: #690 gates red: c118 used the retired name subagent (first form strike). Fixed on the lane branch (c3a7d4f) and re-merged as 01e28ec.
- 2026-10-27 06:20 CDT: #690 gates red again in lint/test_check_mod_versions.py: a git auto-gc race in teardown (also hit #689). Fixed in its own lane ci-mod-versions-no-gc (gc.auto=0, maintenance.auto=false), joined #690 as f27b68e. Note for triage: four other lint tests copy the same rm_tree helper (glossary, hook_stubs, record_slugs, ruling_kind); one home for it would stop the race everywhere.
- 2026-10-27 06:20 CDT: c114 fixed on Windows (#685, head 041b4ac, Windows gates run green). Joins the next batch.
- 2026-10-27 06:45 CDT: #690 gates red on a c117 comment date (lint/check_comment_narration.py); fixed on its lane (8b9e1c5), re-merged as bd75108. Lesson for the next brief: lanes should run every gates lint step (check_comment_narration, test_check_glossary), not only their own tests; both reds this batch were lint the lanes skipped.
- 2026-10-27 07:10 CDT: #690 red a third time on the gc race, now in test_check_ruling_kind. The fix moved to gates.yml's workflow env (gc.auto=0, maintenance.auto=false), lane ci-mod-versions-no-gc 0db3420, re-merged as ba025be. Note stands: five lint tests copy rm_tree; one shared helper is a cleanup step for triage.
- 2026-10-27 07:45 CDT: batch #690 merged as 2e5fde3: c116, c113+c115, c118, c117, plus lane ci-mod-versions-no-gc (CI turns off git auto gc). For triage: close c113, c115, c116, c117, c118. c114 opened alone as #691 (batch-oct27p).
- 2026-10-27 08:10 CDT: new step for triage: hooks/test_stall_watch.py case 23b (tee job gets a STALL while its log grows) fails intermittently on gates-macos. Red on main b031394, green on 2e5fde3, red on #691. A flaky required check costs every batch a re-run. Port: no; the test lives in claude-settings.
- 2026-10-27 08:40 CDT: batch #691 merged as d4e1b86: c114 (CI-read hook reads by REST). For triage: close c114. No lane is open; the build queue needs triage's next work order.
