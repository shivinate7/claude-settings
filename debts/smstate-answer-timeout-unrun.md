# No SendMessage state test runs the shipped reader timeout

- **What.** The answer cases run with no reader timeout, so no case uses the shipped value. A timeout of 0.001 s passes every case.
- **Where.** The answer cases in `hooks/test_sendmessage_state.py`.
- **Decision.** `test-strategy-reset` (tests prove outcomes and never fail on runner speed).
- **Retire.** One case runs the shipped timeout with a reader that answers at once, and goes red when the timeout is too short to start the reader.
