# verdict reads SKIP when a test label holds the word "skipped"

**What.** `bin/verdict` prints `SKIP <cmd>, N skipped` for a run that passes, when the unittest labels in its output contain the word "skipped". A run with no skipped test then reads as a skip.

**Where.** `bin/verdict`, the `SKIPPED` pattern and the SKIP verdict it sets. Its test file is `lint/test_verdict.py`.

**Decision.** `none`.

**Retire.** `lint/test_verdict.py`, a case red first on the current code: a passing unittest run whose labels contain the word "skipped" reads PASS, with no SKIP line. The case goes green when verdict counts only real skips.
