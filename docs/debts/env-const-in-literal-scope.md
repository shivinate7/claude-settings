# Env-const scan skips most test files

**What.** `lint/check_env_const_in_literal.py` reads only `hooks/test_*.py` and `lint/test_*.py`, so 27 `test_*.py` files in other folders (`merge/`, `janitor/`, `actions/`, `skills/*/`) are never read, and an incident there passes. The harm: a guard test that splices an env name into one literal runs on no env file and passes while testing nothing, the failure the check exists to stop. Claude writes tests in these folders in normal work, so the gap is one it will hit: a debt, not a note. Its glob also reads only `test_*.py` names, so `*_test.py` files (3 in the tree) are never read. The fix belongs to roadmap step `env-const-in-literal` (the check's own build step).

**Where.** `lint/check_env_const_in_literal.py`: `SCANNED` (line 40) and the glob in `scan` (line 82).

**Decision.** none

**Retire.** Widen `SCANNED` and the glob to every test file in the tree. The runnable check `lint/test_check_env_const_in_literal.py` gets a case that plants an incident in a merge test file and expects a hit. Widening the scan gave 0 hits on today's tree (round 3 review), so no current test turns red.
