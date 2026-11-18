# New standing session's first start records no role

- **What.** A brand-new standing session's first start likely records no merge role. Its roster row is written after the session exists, and the start hook runs before that row exists. The session gets the role at its next resume. Cloud compact, clear and fork starts do not run the hook, so they do not fix it. Not verified: the row-writing order.
- **Where.** `hooks/own_session.py`, `sync_standing_merge_role` (the role write). `hooks/session_start.sh`, the `merge-role` call in the roster block.
- **Decision.** `session-tiers`, session roles. Its start-up hook bullet names this gap.
- **Retire.** Close it when a row written after a session's first start gets its role at that start, or when the row is written before the start. `hooks/test_session_start.py` must hold a case for that order, and it must pass.
