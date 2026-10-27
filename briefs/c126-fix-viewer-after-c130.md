# Fix lane: c126+d9 with c131 is red on the waiting-page viewer tests after c130

Cloud build thread brief. Build advisor (10), Oct 27, against claude-settings main 6a3e842.
Branch: claude/project-thread-xczmrz (head c9a6311). Merge main 6a3e842 into it (a merge
commit, no rebase), fix, push. Send the green, reviewed head to the build advisor; never merge.

## Failure (batch #710, run 40554948699, job gates-shoot)
skills/waiting-page/tests/page.test.mjs:
- test 88, "the viewer head is one row, and the mockup is whole and centered, at 390 wide":
  "the mockup is cut: 9 to 399".
- test 90, same test at 1440 wide: "the mockup is not centered".
This lane is the only one in the batch that touches skills/waiting-page. c130 (#702, merged in
#704) changed page.html too. Green on its own, red on main with c130.

## Task
Reproduce red on the merged tree (`node --test skills/waiting-page/tests/page.test.mjs`).
Find which change moves the mockup. Fix the page, never the test, unless the test asserts
something the owner's ruling no longer wants (then stop and say so). Keep c130's behaviour.

## Done when
page.test.mjs green on the merged head; the gates-shoot job's other tests unchanged.
Review: one fresh Sonnet reviewer, round 1. Report cap 15 lines.
