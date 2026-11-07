# The waiting page counts presses in its own database

## The ruling

- The waiting page counts each counted press in its own database. Collection `usage`, one doc per key, `{n, at}`. Never browser storage.
- A count is kept only for a named reader (rule `outcomes-mechanize-rules`).
- Status: not built yet.
- Why: two roadmap steps need the owner's use before they cut anything.
  - Step `page-ask-box-one-send` (one Ask box, one Send) reads the Ask box and Send counts.
  - Step `page-status-cut-unread` (cut the Status tiles, trend and burn if unread) reads the Status counts.
- Keys:
  - `ask-add`: Add to list.
  - `ask-send`: Send ask.
  - `answers-send`: Send answers.
  - `copy-answers`: Copy answers.
  - `status-tab`: Status tab opened.
  - `view-plan`, `view-log`, `view-ref`, `view-rec`: a Status view opened.
  - `tile-<key>`: a Status tile opened. The key is lowercased. A character outside `[a-z0-9-]` becomes `_`.
- Code home: one helper, `countUse`, in `skills/waiting-page/page.html`. Every counted press calls it (rule `building-one-home-per-capability`).
- Readers:
  - Step `page-ask-box-one-send` reads `ask-add`, `ask-send` and `answers-send`.
  - Step `page-status-cut-unread` reads `status-tab`, `view-*` and `tile-*`.
  - Query: `ArtifactData` action `list`, collection `usage`, `url` set to the repo's waiting page.
- Export: the copy does not include `usage`. The export's five collections are `items`, `answers`, `groups`, `asks` and `meta`. None of them is `usage`.
- Coordinator ruling, 2026-11-07 12:11 CST: picks accepted.

## Cost

- 0 processes started. 0 files written. No timer. No listener.
- One database read and one database write per counted press.
- 0 database calls on page load.
- Proof: none yet. The planned test is in `skills/waiting-page/tests/page.test.mjs` (no write on load, one +1 per press). Until it lands, the cost is unmeasured.

## Known limits

- Trend and burn have no control. A view opening means "shown", not "read". Step `page-status-cut-unread` must not cut on view counts alone.
- The Ask box has no open control. Presses are counted, not opens.
- Store down: Copy answers shows mostly when the store is unreachable, and nothing is counted then. A low `copy-answers` count does not mean unused.
- Get, then set, across two tabs: the database has no atomic increment. Two open views that press at once can both read the same `n`, and one count is lost.
- Counts start at merge. Earlier use is unknown.

Kind: process
Home: rule:outcomes-mechanize-rules
