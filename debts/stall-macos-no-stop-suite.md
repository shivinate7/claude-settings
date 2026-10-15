# The macOS CI jobs run no stop suite

- **What.** The macOS CI jobs run no stop suite. The Stop path has no macOS run.
- **Where.** The macOS jobs in CI.
- **Decision.** `stall-watch-stop-check` (the stall watch flags open jobs at Stop).
- **Retire.** Add the stop suite step to the macOS jobs. The step is green on macOS.
