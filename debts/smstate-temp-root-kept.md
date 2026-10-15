# The SendMessage state test leaves its temp folders

- **What.** Each run makes a folder in the temp directory and never removes it. 59 such folders were found on 2026-10-15.
- **Where.** `ROOT` in `hooks/test_sendmessage_state.py`.
- **Decision.** `test-strategy-reset` (tests prove outcomes and never fail on runner speed).
- **Retire.** The test removes its folder at exit, also after a failure.
