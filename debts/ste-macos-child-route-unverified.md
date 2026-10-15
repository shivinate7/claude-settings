# The macOS child-process route is unverified

- **What.** The child-process route for the STE autofix is not verified on macOS.
- **Where.** The child-process call in `lint/ste_gate.py`.
- **Decision.** `ste-gate-fixes-not-nags` (the STE gate fixes text, not nags).
- **Retire.** Run the child-process route on a macOS runner. The test passes there.
