# The Windows CI result for the stop suite is unknown

- **What.** The Windows CI step runs on a Windows runner that this change has not run on. The Windows CI result is unknown. Local runs passed.
- **Where.** The Windows CI step for the stop suite.
- **Decision.** `stall-watch-stop-check` (the stall watch flags open jobs at Stop).
- **Retire.** Run the Windows stop suite step in CI, and read its verdict.
