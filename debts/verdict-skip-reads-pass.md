# verdict prints PASS for a run that skipped cases

- **What.** `bin/verdict` prints PASS on exit 0, even when the run printed SKIP lines. A test that always skips stays green.
- **Where.** `bin/verdict`.
- **Decision.** `test-strategy-reset` (tests prove outcomes and never fail on runner speed).
- **Retire.** verdict prints the skip count with PASS, such as PASS, 1 skipped.
