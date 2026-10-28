# c126 viewer fix lane (with d9, c131)

Branch claude/project-thread-xczmrz, head 6c4dfc04, draft PR #732. Lane session session_013NEJL1Njy2efqjaZTYpMWt.

Status (Oct 28): green and reviewed, ready for the next batch. Nothing open.
- Merged main e0f9e2d (58a69e7). d9's renderer is the one home for the option-card picture; #713's
  renderer and its tap-picks test are dropped per the d9 ruling (Oct 27 12:13 CDT).
- 390 cut: the `.dsheet` grid column grew to the head's width; fixed with minmax(0,1fr) and the head
  set before the fit (bce10f6). Design fixes: `drawn` width for wide mockups, a viewer caption while
  the head cuts the title, a ready line that does not wrap (5383bfe1, 8e0c4033).
- Ruled (shiv, Oct 27 23:40 CDT): every look-question option shows a picture. Home: SKILL.md on this branch.
- Local gates pass (page.test.mjs, test_reply_judge, test_call_judge, ci-job gates --lint, ste-changed).
  Design review (opus) PASS at round 3, all screens at 320/360/390/768/1440, light and dark.
  Code review (sonnet) clear at round 3. Eight findings are filed as notes in docs/debts/notes.md.
