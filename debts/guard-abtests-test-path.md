# A product folder named ABTests reads as a test path

- **What.** The test-path rule reads `native/ABTests/` as a test folder, so a builder cannot edit product code there. This is a false alarm. Four pins of it were cut in lane cut-tests-guard.
- **Where.** The test-path match in `hooks/guard.py`.
- **Decision.** `test-strategy-reset` (a hole pin becomes a debt).
- **Retire.** The match needs `Tests` as a whole path word, and a case allows `native/ABTests/`.
