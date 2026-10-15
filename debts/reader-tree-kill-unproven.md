# No test proves that the SendMessage hook kills the reader's process tree

- **What.** On a reader timeout, the hook kills the process tree that it started. A review mutant that kills only the top process still passed every case: the hook returned in time, but the held child stayed alive. A hung `claude agents` call can then linger after each timeout.
- **Where.** `kill_tree` in `hooks/sendmessage_state.py`; the held-pipe case in `hooks/test_sendmessage_state.py`.
- **Decision.** None. The incident of 2026-10-14: on PR 432 CI, the reader timed out on a slow Windows runner.
- **Retire.** The stub reader writes its child's pid, and the test asserts that the child is dead after the hook returns. The test goes red on the kill-only-the-top mutant.
