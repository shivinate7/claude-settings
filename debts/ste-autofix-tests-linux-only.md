# The autofix tests run on Linux only

- **What.** `lint/test_ste_autofix.py` runs on the Linux job only. The macOS and Windows runner cost is unmeasured.
- **Where.** The CI job list for `lint/test_ste_autofix.py`.
- **Decision.** `ste-gate-fixes-not-nags` (the STE gate fixes text, not nags).
- **Retire.** Run the test on the macOS and Windows jobs. Record the runner cost, then decide whether to keep it there.
