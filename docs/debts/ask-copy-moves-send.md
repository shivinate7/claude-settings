# Copy ask moves Send ask at 390px with the store unreachable

**What.** At 390px, with the store unreachable (`state.db === false`), a press on Copy ask shortens the hint from 3 lines to 1. The `.askrow` shrinks from 121px to 100px. Copy ask and Send ask move 21px up, under the thumb. This breaks rule `ux-press-moves-nothing` (a press moves no control). Step: page-ask-box (the waiting-page Ask box, a roadmap step). Design review found it after review round 3, so it shipped as a debt.

**Where.** `skills/waiting-page/page.html`: the `.askrow` grid and its narrow-screen rules, and `renderAskForm`, which writes the hint (`askHint`) and the Copy ask slot (`askSlot`).

**Decision.** none.

**Retire.** Give the hint a fixed height on narrow screens, so a press does not change the row height. This is a fix idea, not yet built. The check: a test in `skills/waiting-page/tests/page.test.mjs` sets 390px and an unreachable store, reads the boxes of Send ask and Copy ask, presses Copy ask, and reads them again. Neither box may move.
