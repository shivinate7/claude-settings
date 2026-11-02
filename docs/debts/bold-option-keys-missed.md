# Bold and inline option keys are missed

- **What.** In `OPTION_KEY` of `hooks/question_form.py` and `LABEL_RE` of `lint/report_guard.py`, a bold key at line start (`**a)** x`, `**a** x`) ends the Input Needed section. An inline `Q? a) x b) y` is not read, so a key clash is missed.
- **Where.** `hooks/question_form.py` `OPTION_KEY`; `lint/report_guard.py` `LABEL_RE`.
- **Decision.** question-form (one question form and one guard, for the chat box and the waiting page).
- **Retire.** A test with bold keys and inline keys goes red, then green.
