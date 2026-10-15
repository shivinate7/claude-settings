# The token cost of the local time line is unmeasured

- **What.** The token cost of one line per prompt is unmeasured.
- **Where.** The `UserPromptSubmit` line from `hooks/local_time.py`.
- **Decision.** `local-time-central` (sessions speak times in US Central).
- **Retire.** The token cost of one line per prompt is measured, and the number is recorded in the decision.
