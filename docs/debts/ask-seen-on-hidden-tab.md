# An ask counts as seen when its tab is hidden

**What.** `markAsksSeen` stamps the current time into `waiting.askSeen` on every hide (`visibilitychange` to hidden) and on every `pagehide`. An answer that arrives while the page sits in a hidden tab therefore counts as seen at the next load, though the owner never looked at the Ask section. With three newer seen answers, it drops behind "Show N older asks" with no New mark. Reachable in normal work, by code read; not run in a browser. This is the miss the Ask box exists to prevent. Step: page-ask-box (the waiting-page Ask box, a roadmap step). No test covers it: no test fires `visibilitychange` or `pagehide`.

**Where.** `skills/waiting-page/page.html`, `markAsksSeen` and its two listeners. The seen time is read at load into `ASK_SEEN`.

**Decision.** none.

**Retire.** Stamp only while the Ask section is on screen. The check: a test in `skills/waiting-page/tests/page.test.mjs` fires `visibilitychange` to hidden and `pagehide` with an answer that arrives while hidden, reloads, and finds that answer with the New mark, above "Show N older asks".
