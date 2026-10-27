# Brief: c100, the waiting page gets its final look, in every repo at once

Repo: shivinate7/claude-settings. One screen lane: builder, then design reviewer, then reviewer. Runs beside c105.

## Task
Rebuild `skills/waiting-page/page.html` to match the approved final design. Every repo's page comes from this one template.
- Design: https://claude.ai/artifact/2DodmME3zxVTmi26B3KzBR. The source is `/mnt/project-files/plans/waiting-mockups/final-combined.html`. Its "Design notes" view lists the template changes. Build what that list names. Treat the page's sample items and repo chips as mockup only.
- Must hold: one stable list in three tiers (Blocking, Upcoming, Whenever), derived from holds and by fields. Related items share one frame with one sentence. A slim 44px repo-colour header. State colours turned away from the repo hue. Nothing preselected; my pick starred, with Take my pick in one tap. One Send with a stamp and Undo. A receipts trail (c99's data). A left overview in plain words, with no symbol key. Each label shown once (c106). A Designs tab with inline mockups in a sheet (c112, which lands here). A last "Pick stands" section.
- Repo colour: the page takes one brand hex and derives its `--r-*` tokens with contrast checks. c105 supplies the hex through `colour_for(repo)` in `docs/design/repo-colours.json`. Until c105 merges, use the page's neutral defaults; do not draw a colour in the page.
- Update `skills/waiting-page/SKILL.md` where the page's data fields change (stands, related frame, tiers). Keep the page's store keys, so answers already saved on each repo's live page survive a republish.

## Rulings
- shiv approved the final look, Oct 27 02:38 CDT ("Approved", cmsg_01DoF7thf3iq2Srr1UsfXgh28T1okSz7qJT6gkwr4EowHq), and Oct 27 01:01 CDT (cmsg_01DoF7thf3iq2Srr1UsfXgh2RuC7HdpGEa99YN7j3ztLUk).
- Pick stands, shiv Oct 27 02:27 CDT (cmsg_01DoF7thf3iq2Srr1UsfXgh2XJphRcvzru8mtAcr3kFpGu): a question that changes no rule carries `stands: true`, sits in the last section, and my pick goes with the next Send unless changed. A question that touches a rule starts blank.
- Review-page standard, in roadmap/outbox/waiting-page-design.md on the roadmap branch.
- verification-screens-verdict: a verdict per screen at phone and desktop width, light and dark.

## Failure classes
- A saved answer lost on republish (store keys changed).
- A stands item sent without the owner seeing it in the last section.
- A preselected option on a rule question.
- A layout shift when an answer is picked or sent.
- Contrast below 4.5:1 for text on the repo header, for any registry colour.

## Check that proves it done
`skills/waiting-page/tests/page.test.mjs` gets new cases first, red on the old page, then green. Screen verdicts come from `bin/shoot` in headless Chromium at 390 and 1280, light and dark. The design reviewer judges against the mockup. Also run lint/rule_audit.py, lint/test_check_skill_model_rows.py and bin/ste-changed origin/main. Republish no live page; that happens after merge.

## Report
At most 20 lines: PR, head, red run, green run, screen verdicts, review verdicts.
