# sed in-place flag forms miss the test-path check

**What.** The builder test-path check misses `sed -Ei`, `-ni`, `-zi`, `-ibak` and `--in-place` aimed at a test file, because the sed write match needs `-i\b`. Claude writes these forms in normal work.

**Where.** hooks/guard_frozen.py `writes_to`.

**Decision.** `builders-cannot-edit-tests` (a builder never changes a test or test config).

**Retire.** The check refuses each form on a test file (tests/x.py), run by `hooks/test_guard.py`.
