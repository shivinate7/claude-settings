# Dismissed line misses focus on main CI

**What.** The main push CI run read no focus on the Dismissed line, 2 of 2 tries, on run 42357626483 (ebc810f56). PR, schedule and dispatch runs on the same tree passed. It did not reproduce locally (throttle, one core, Playwright 1.64.1). The page sets the focus in the same task as it draws the line, so the cause is unfound. The next red run's message names where focus went.

**Where.** `skills/waiting-page/page.html`, `writeDismissed` (the `f.focus` call after `renderAskList`). The test is "dismiss: the thread stays in place as a Dismissed line ..." in `skills/waiting-page/tests/page.test.mjs`.

**Decision.** test-practices (P6: a flake is a defect report, so find its cause before you widen a bound).

**Retire.** A red run names the focused element and the focus moves, the cause is found, and the page or the test is fixed at that cause. `skills/waiting-page/tests/page.test.mjs` is green on the fix.
