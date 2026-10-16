# A scan the deadline skips can read as clean

- **What.** When the deadline skips a scan, the record does not say so. The run log has no count of trees not judged. The summary prints a husk UNKNOWN line but no trash UNKNOWN line. `sweep_repo` sets the listener result to None on a deadline skip and on a failed enumeration. The listener line prints "enumeration failed" for both. `session_end_sweep.py` drops the sweep's stdout, so the report does not reach the user. Named in review round 3, item 3.
- **Where.** In `janitor/sweep.py`: `append_run_log` (no not-judged count), `print_sweep_report` (summary and listener line), and `sweep_repo` (listener set to None). In `janitor/session_end_sweep.py`: the `subprocess.run` call, which drops stdout.
- **Decision.** `agent-end-reap-stops-what-a-finished-agent-left` (the sweep that reaps what a finished agent left).
- **Retire.** The run log writes a not-judged count for each repository. The summary prints a trash UNKNOWN line when the deadline skips the scan. The listener line names the deadline as the cause when the deadline caused it. The hook keeps the sweep's stdout. Check: a case with a deadline that skips a scan shows all four lines.
