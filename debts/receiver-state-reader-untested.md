# No test runs the real board reader that the SendMessage hook calls

- **What.** The SendMessage state tests now use a stub reader, so a slow runner cannot fail them. No test runs the real `receiver-state.mjs`: its `claude agents --json` call, its 8 s timeout, its argument read, and its fall back to "unseen". A break there reads as "unseen", so the state judge goes blind with no alarm.
- **Where.** `mods/session-board/hooks/receiver-state.mjs`; `hooks/test_sendmessage_state.py`; the unused agents branch in its fake `claude`.
- **Decision.** `test-strategy-reset` (tests prove outcomes and never fail on runner speed).
- **Retire.** One case runs the real reader through the fake `claude`, with no time bound. It checks each answer: idle, busy and unseen.
