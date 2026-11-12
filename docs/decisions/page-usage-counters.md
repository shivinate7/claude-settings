# The waiting page counts presses in its own database

## The ruling

- The waiting page counts each counted press in its own database. Collection `usage`, one doc per key, `{n, at}`. Never browser storage.
- A count is kept only for a named reader (rule `outcomes-mechanize-rules`).
- Status: built. `countUse` in `skills/waiting-page/page.html` writes `usage`. The press does not await it (read from the code; no test holds a write open), and a refused write is proved not to stop the press. It does nothing with no store. A load reads and writes no counter.
- Why: two roadmap steps need the owner's use before they cut anything.
  - Step `page-ask-box-one-send` (one Ask box, one Send) reads the Ask box and Send counts.
  - Step `page-status-cut-unread` (cut the Status tiles, trend and burn if unread) reads the Status counts.
- Keys:
  - `ask-add`: Add to list.
  - `ask-send`: Send ask, in the Ask box. Send reply in a thread is not counted: step `page-ask-box-one-send` weighs the box against Send answers, not thread replies.
  - `answers-send`: Send answers.
  - `copy-answers`: Copy answers.
  - `status-tab`: Status tab opened.
  - `view-plan`, `view-log`, `view-ref`, `view-rec`: a Status view opened.
  - `tile-<key>`: a Status tile opened. The key is lowercased. A character outside `[a-z0-9-]` becomes `_`.
- Code home: one helper, `countUse`, in `skills/waiting-page/page.html`. Every counted press calls it (rule `building-one-home-per-capability`).
- Readers:
  - Step `page-ask-box-one-send` reads `ask-add`, `ask-send`, `answers-send` and `copy-answers`. Copy answers sits on the Send answers row that step reshapes.
  - Step `page-status-cut-unread` reads `status-tab`, `view-*` and `tile-*`.
  - Query: `ArtifactData` action `list`, collection `usage`, `url` set to the repo's waiting page.
- Export: the copy does not include `usage`. The export's five collections are `items`, `answers`, `groups`, `asks` and `meta`. None of them is `usage`.
- Cost:
  - 0 processes started. 0 files written. No timer. No listener.
  - One database read and one database write per counted press. 0 counter reads or writes on page load (the page's own items, answers and meta loads are not counts).
  - Proof: the `usage:` cases in `skills/waiting-page/tests/page.test.mjs`.
    - A load reads and writes no counter, and each Add to list counts up: "a load reads and writes no counter, and each Add to list writes ask-add with n counting up".
    - One +1 per press, and a press that changes nothing writes nothing: the Send ask, Send answers, Copy answers, Status tab, Status view and tile cases.
    - No store writes none and throws nothing: "with a store a press writes its counter, and with no store the same presses write none and throw nothing".
    - A refused usage write does not stop the press: "a usage write the store refuses does not stop the press it counts, and the bar does not say Not saved".
- Known limit: trend and burn have no control. A view opening means "shown", not "read". Step `page-status-cut-unread` must not cut on view counts alone.
- Known limit: the Ask box has no open control. Presses are counted, not opens.
- Known limit: store down. Copy answers shows mostly when the store is unreachable, and nothing is counted then. A low `copy-answers` count does not mean unused.
- Known limit: get, then set. The database has no atomic increment. Two presses whose writes overlap read the same `n`, and one count is lost: two open tabs, or one fast repeat in one tab.
- Known limit: a press counts before its writes land. A Send answers press that only withdraws, or whose every write fails, still counts once.
- Known limit: two tile keys that differ only outside `[a-z0-9-]` share one count.
- Known limit: counts start at merge. Earlier use is unknown.
- Coordinator ruling, 2026-11-07 12:11 CST: picks accepted.
- Owner ruling, 2026-11-12 12:40 CST (cited in step `page-usage-counters`): the page database is the one store; counts live there.

Kind: process
Home: rule:outcomes-mechanize-rules
