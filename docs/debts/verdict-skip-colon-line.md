# verdict reads a `SKIP:` line as no skip

- **What.** `bin/verdict` counts marker lines that start `SKIP ` or `SKIPPED`. A suite that prints `SKIP: <case>` and no summary reads PASS. Measured: `verdict python3 hooks/test_handoff_wave2.py` printed PASS with 4 `SKIP:` lines in its log.
- **Where.** `bin/verdict` (`SKIP_LINE`); suites that print `SKIP:`, such as `hooks/test_handoff_wave2.py` and `hooks/test_decision_watch.py`.
- **Decision.** none. Plan row S8 (a skip is counted and shown) in `docs/plans/test-ci-standard.md`.
- **Retire.** a `SKIP:` line counts as one skip, and a summary line such as `SKIP: N check(s)` in `hooks/test_sendmessage_state.py` is not counted twice; a test pins both.
