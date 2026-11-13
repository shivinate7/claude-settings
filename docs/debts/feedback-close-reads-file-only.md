# The auto-close reads that a file is on main, not what it holds

**What.** The feedback log closes a ruling or task item once its home file is a blob on main. It never reads the file's content. A ruling homed to an existing `docs/decisions/` file, or a grant ruling homed to `settings.json`, closes at the first Stop, before the edit it names has landed. The item then leaves the compaction note and is never checked again, so a pending ruling can be forgotten.

**Where.** `hooks/feedback_guard.py` (`Homes`, `close_settled`) and `lint/tending.py` (the `open-until-home-on-main` test).

**Decision.** owner-feedback-inbox (owner feedback goes to a log before the turn ends); `prose-tending-contract` (one shared tending contract).

**Retire.** The test reads the home's content for the item's id or a cite of it, or a ruling item names a section; closes only then. `lint/test_tending.py` shows it closed.
