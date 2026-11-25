# The failing-name cap in the verdict excerpt has no test

**What.** `bin/verdict` keeps at most 300 failing case names in a FAIL excerpt (`NAMES = 300`). No test in `lint/test_verdict.py` reads that cap, so the cap is unpinned. From PR 3849's round 1 review (finding F6, a reviewer's report); the no-test part was checked by search on main.

**Where.** `bin/verdict`, the `NAMES` constant (line 19) and the excerpt code that uses it.

**Decision.** none

**Retire.** A case in `lint/test_verdict.py` that feeds more than 300 failing case names and checks the excerpt keeps at most 300 of them.
