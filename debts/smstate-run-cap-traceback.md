# The SendMessage state test hang cap prints a traceback

- **What.** The 120 s cap in `run_hook` raises an uncaught `TimeoutExpired`. A hang then shows as a traceback, not as a FAIL or SKIP line.
- **Where.** `run_hook` in `hooks/test_sendmessage_state.py`.
- **Decision.** `test-strategy-reset` (tests prove outcomes and never fail on runner speed).
- **Retire.** A hit on the cap prints one clear line that names the case.
