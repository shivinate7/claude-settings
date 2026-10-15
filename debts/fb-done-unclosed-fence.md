# A `fb done` line after an unclosed code fence closes capture

- **What.** The close rule reads only the last line of a message. A message such as "X", then an opening fence, then a last line `fb done` with no closing fence, still closes capture. The line is inside the fence, so by the rule it must not close.
- **Where.** `CLOSE_LINE` in `hooks/local_time.py`.
- **Decision.** `owner-feedback-inbox` (owner feedback goes to one inbox per session).
- **Retire.** The capture reads fence state before it tests the last line. A test with an unclosed fence and a last `fb done` line keeps capture open.
