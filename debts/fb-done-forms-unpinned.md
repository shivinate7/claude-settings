# The close forms of a last `fb done` line are not pinned by tests

- **What.** The tests check only a plain last line `fb done`. The colon, case, trailing punctuation, CRLF, trailing blank lines and leading-space forms that the decision names have no case. The pattern also closes when `fb` and `done` sit on the two last lines, because its space match spans a line break.
- **Where.** `CLOSE_LINE` in `hooks/local_time.py`; `hooks/test_feedback_inbox.py`.
- **Decision.** `owner-feedback-inbox` (owner feedback goes to one inbox per session).
- **Retire.** One case per named form closes, and `fb` and `done` on two lines do not close.
