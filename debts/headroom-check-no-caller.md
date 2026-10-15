# headroom_within_bounds has no caller

- **What.** The headroom tests and mutant were cut. `headroom_within_bounds` now has no caller. Its upper edge guards latency only. The lower edge still has cases.
- **Where.** `headroom_within_bounds` in `janitor/session_end_sweep.py`.
- **Decision.** `test-strategy-reset` (cut tests that name no real failure).
- **Retire.** The builder lane for code cuts deletes the function and its constant.
