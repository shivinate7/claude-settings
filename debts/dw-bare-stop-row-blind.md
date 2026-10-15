# No test catches a detector that misses a bare Stop row

- **What.** Case M5c was cut. `test_no_stop_row_runs_decision_watch` now passes with a detector that sees only the quoted form of a Stop row. A miss needs two faults: a quote-only detector, and a bare Stop row written by hand into `settings.json`.
- **Where.** `lint/test_settings_matcher.py`.
- **Decision.** `test-strategy-reset` (cut tests that name no real failure).
- **Retire.** One case feeds a bare Stop row and goes red on a quote-only detector.
