# Some done forms do not close inbox capture

- **What.** While capture is open, `fb:done` and `` `fb done` `` in backticks are captured and do not close it. The turn-end reminder shows each time, so the owner can send `fb done` again. No test covers `fb<TAB>done` or `fb - done` while capture is open. The code handles both.
- **Where.** The close-trigger check in the capture hook.
- **Decision.** `owner-feedback-inbox` (owner feedback goes to an inbox before the turn ends).
- **Retire.** Each done form has a case, and the backtick form is either closed or recorded as quoted text by ruling.
