# A frame in a hidden part saves a bad size

**What.** A frame inside a hidden part of the waiting page posts its size: height 40, focus box 0 by 0. The message handler keeps that size, saves it to the browser store `waiting.fit`, and refits the boxes that use it. Showing the Questions tab or the Answered section refits no box, so the bad size stays on screen. Measured in design review of commit 611d607dd (the lane's latest commit) against main (commit ddaa393c0). After a Status tab round trip, a focus picture collapses to 4 by 2 px (3 by 2 on main). A picture loaded while its part is hidden has its first frame after show 476 to 571 px off the settled height (main: 451 to 456 px). On the next visit the first frame is 279 by 29 or 4 by 2 px, then it jumps. The owner switches tabs often, so this is likely in normal work.

**Where.** `skills/waiting-page/page.html`: the `message` listener that sets `FIT[m.key]` (about line 2923), and `showTab` (about lines 2978 to 2985). The Answered section is built by `sectionEl` (about line 1940). Opening it refits no box.

**Decision.** `page-pic-fills-card` (an option picture fills its card and grows to a phone). Its first-paint rule, that a box's first frame equals its settled height, fails here after a show.

**Retire.** A size posted from a hidden frame is ignored, and every box refits on show. The fix adds a case to `skills/waiting-page/tests/page.test.mjs` and runs it red first. The case covers a picture after a Status tab round trip, and a picture loaded while its part is hidden. Its first frame after show is the settled height.
