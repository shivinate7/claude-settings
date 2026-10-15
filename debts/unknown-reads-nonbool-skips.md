# The unknown-reads check reads any non-bool answer as a skip

- **What.** The check prints PASS for True, FAIL for False, and SKIP for any other answer. A member that returns 0, None or an empty list prints SKIP, and the check exits 0. No real member returns such a value today.
- **Where.** `lint/check_unknown_reads_contract.py`.
- **Decision.** `test-strategy-reset` (tests prove outcomes and never fail on runner speed).
- **Retire.** The check prints SKIP only for the `test_guard.SKIP` token, prints FAIL for any other value, and fails when every member skips. A test pins each case.
