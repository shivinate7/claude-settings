# A named item cite refuses when a pick letter or detail sits before its name

**What.** A numbered item cite that carries a name is refused when a pick letter or a slug with detail sits between the number and the name. `Waiting page item 46 a (search pill clear)` refuses 46. `item 82 b, designer skills` refuses 82. `item 439 (lane-model-sonnet, 2026-11-08 ...)` refuses 439. A reviewer's scoped read of 407 doc lines with `item N` found 64 refusals, about 6 of them on named cites. That is one sample, not a full measure.

**Where.** `lint/report_guard.py`: `ITEM_SLUG_AFTER_RE` (about :688) matches a name only when `)` follows the slug at once. Nothing reads a pick letter (`a`, `b`) between the number and the name. `_item_named` (about :719) reads that regex.

**Decision.** None; rule `speak-cite-id-plus-gloss` (an id carries a short name).

**Retire.** A pick letter and a slug with detail between the number and the name pass. `lint/test_report_guard.py` gets the three probes above, each expecting no refusal, and it passes.
