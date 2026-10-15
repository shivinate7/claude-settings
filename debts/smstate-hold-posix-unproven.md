# The SendMessage hold case is proven red on Windows only

- **What.** No run shows the hold case red on a POSIX host with a hook that waits on the held pipe.
- **Where.** The hold case in `hooks/test_sendmessage_state.py`.
- **Decision.** `test-strategy-reset` (tests prove outcomes and never fail on runner speed).
- **Retire.** A POSIX run of the pipe-held mutant goes red.
