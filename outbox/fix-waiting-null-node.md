# fix-waiting-null-node, stray "null" text in waiting-page decision cards

- State: green and reviewed. Draft PR #778, branch fix-waiting-null-node, head 9080678f (origin/main a065acdb merged in; the page.test.mjs conflict was two appended tests, both kept).
- Fix: skills/waiting-page/page.html buildCard, one line. The difkey paragraph is spread in only when a mark exists.
- Test: skills/waiting-page/tests/page.test.mjs, no "null"/"undefined" text node in a decision card. Red on c71b22e's page, green on the fix.
- Other append sites in page.html and docs/design/waiting-page.html: none can receive null.
- Checks on 9080678f: page test file PASS, `ci-job checks --lint --base origin/main` PASS, silent-undo --strict clean.
- Review: fresh reviewer, round 1, approve, no findings. Optional, not done: assert .difkey absent in that fixture.
- After merge: live waiting pages need republish (skills/waiting-page/stale_pages.py names them).
