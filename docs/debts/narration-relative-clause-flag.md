# The narration check flags a colour in a relative clause as history

**What.** The run-state form skips a colour phrase only after when, if, unless, until, while or once in the same clause. A relative clause that states a condition, such as "Refuses a merge whose head is not green on main", is logic but flags. Claude writes such clauses in guard and check comments, so it costs a reword in normal work.

**Where.** `lint/check_comment_narration.py`, `HistoryPhrase` (the CONDITION skip).

**Decision.** none

**Retire.** "Refuses a merge whose head is not green on main" and "a head that is not green on main is refused" stay clean, and every run-state hit still hits, in `lint/test_check_comment_narration.py`.
