# A repeat mark can name the wrong home when two same-minute blocks share an item id

**What.** Two blocks stamped in the same minute can share an item id. `example_item` makes `fb-HHMM-1` for every block, so the id repeats. `judge` reads each item's home from the last block that holds the id (`rests`), but `new_items` and `mark_items` keep the first. The item then takes a home that is not its own block's. In the reviewer's case, block A (home: the todo file) and block B (home: the handoff) share `fb-1303-1`. A's prompt line says only "never for this item: inbox:...#1", so A's todo lines stay candidates and can take a false mark. Cost: a false mark line, not a blocked turn.

**Where.** `judge`, `new_items` and `mark_items` in `hooks/feedback_guard.py`, and `own_refs`, which drops an item's own refs from its candidates.

**Decision.** owner-feedback-inbox (the Repeats bullet: a model matches each new owner message against older feedback and work, and an item never repeats its own block or its own home).

**Retire.** A new case in `hooks/test_feedback_inbox.py`: two blocks stamped in the same minute that share an item id. Each item takes its own block's home, and block A's todo lines are dropped for block A's item.
