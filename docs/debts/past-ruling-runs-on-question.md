# The past-ruling check runs only when a question is asked

**What.** The past-ruling check runs only for a question. The question form attaches it (`hooks/call_judge.py` item 8, and `past_ruling_context`, which calls `question_form.past_rulings`). Starting a lane runs no such check, so a lane can start against a ruling that a later record changed (seen 02:12 CST Nov 24, 2026).

**Where.** `hooks/call_judge.py` (lines 35, 131-134, 370-375); `hooks/question_form.py` (`past_rulings`).

**Decision.** `question-form` (the question form and its past-ruling vetting).

**Retire.** None yet. Close when a lane start runs the same check over the decision records.

Fix: none built.
