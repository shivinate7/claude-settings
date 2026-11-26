# A carried head that is red or cancelled has no test

- **What.** No test case has a carried head that is red or cancelled under a green own run. `merge.py` reads the carried state only for "unknown (", so red, cancelled and pending take one branch, and only pending is pinned. The fake reads "skipped" and "pending" as one string.
- **Where.** `merge/test_merge.py` lines 11427-11505; `merge/merge.py` line 5973.
- **Decision.** `merge-needs-current-base` (the carried proof of a stale records page, and the live head's own run).
- **Retire.** One case each for red, cancelled and skipped under a green live head. Check: `merge/test_merge.py`.
