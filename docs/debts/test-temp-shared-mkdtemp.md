# The test-temp check misses a mkdtemp() folder that tests share

**What.** The test-temp check (cull-test-temp-run) does not catch a `mkdtemp()` folder that several tests share. Tests that share one folder can break each other. Unmeasured how often this happens.

**Where.** `hooks/guard_frozen.py`, where the temp calls are listed (`_PY_TEMP_CALLS`).

**Decision.** rule `roles-findings-are-debts-or-notes` (a known gap is a debt only if Claude is likely to hit it in normal work).

**Retire.** A case in `hooks/test_guard.py` that refuses a second test sharing a `mkdtemp()` folder with another test closes this debt.
