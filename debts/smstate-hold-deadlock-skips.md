# A hook that deadlocks in the hold case reads as a skip

- **What.** When the hold case hits the harness cap, it prints SKIP and a warning. A hook that never returns reads the same way, so a real deadlock does not fail.
- **Where.** The hold case in `hooks/test_sendmessage_state.py`.
- **Decision.** `test-strategy-reset` (tests prove outcomes and never fail on runner speed).
- **Retire.** The case tells a slow runner from a hook that never returns, and fails the second.
