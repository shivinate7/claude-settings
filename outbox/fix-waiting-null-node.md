# fix-waiting-null-node, stray "null" text in waiting-page decision cards

- State: green and reviewed. Draft PR #778, branch fix-waiting-null-node, head e1794be.
- Fix: skills/waiting-page/page.html buildCard, one line. The difkey paragraph is spread in only when a mark exists.
- Test: skills/waiting-page/tests/page.test.mjs, no "null"/"undefined" text node in a decision card. Red on c71b22e's page, green on the fix. Whole file 147/147.
- Other append sites in page.html and docs/design/waiting-page.html: none can receive null.
- Gates: `ci-job gates --lint --base origin/main` PASS. Silent-undo clean.
- Review: fresh reviewer, round 1, approve, no findings. Optional, not done: assert .difkey absent in that fixture.
- After merge: live waiting pages need republish (skills/waiting-page/stale_pages.py names them).
