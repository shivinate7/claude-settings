# verdict prints PASS for a run that skipped cases

- **What.** If a run prints SKIP lines and exits 0, `bin/verdict` prints only PASS. A test that always skips stays green.
- **Where.** `bin/verdict`.
- **Decision.** `test-strategy-reset` (tests prove outcomes and never fail on runner speed).
- **Retire.** verdict prints the skip count with PASS, such as PASS, 1 skipped.
