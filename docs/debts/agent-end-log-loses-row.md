# Agent-end log loses a row under parallel writers

- **What.** On Windows, test_parallel_writers_lose_no_row lost one of 24 rows (run 39086341296) though the same tree passed before. Either the payload log append races, or the test is flaky; either way it blocked a merge.
- **Where.** The agent-end payload log append in `janitor/agent_end_reap.py`, and its test in the checks-windows-rest job.
- **Decision.** `agent-end-reap-stops-what-a-finished-agent-left` (a finished agent's leftovers are reaped).
- **Retire.** Find whether the append can drop a row on Windows. Fix the append or the test, and the case passes on repeat Windows runs.
