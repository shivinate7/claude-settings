# A quoted notice closes a job that still runs

- **What.** The closing match also reads the text of user tool_result blocks. A tool_result that quotes a task notification closes a job that is still running.
- **Where.** The closing match in `hooks/stall_watch.py`.
- **Decision.** `stall-watch-stop-check` (the stall watch flags open jobs at Stop).
- **Retire.** Count a notice only from a notice record, never from tool_result text. A test with a quoted notice keeps the job open.
