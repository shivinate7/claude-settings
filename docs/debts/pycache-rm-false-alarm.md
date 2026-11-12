# Cache cleanup inside a test folder is refused for a builder

**What.** `rm -rf tests/__pycache__` and `rm -rf tests/.pytest_cache` are refused for a builder, because the path sits in a test folder. Cache cleanup is not a test change.

**Where.** `hooks/guard.py`, `builder_test_path` and `is_test_rel` (`TEST_DIRS` holds `tests`). The shell check (rule 7c, `builder-test-edit`) reads the path through it.

**Decision.** `builders-cannot-edit-tests`, builders cannot edit tests (the shell check).

**Retire.** Exempt the cache folders `__pycache__` and `.pytest_cache` from the builder test predicate. Keep every other path under a test folder as a test path. Closed when a case allows both `rm -rf` forms above for a builder, and `rm -rf` on a test file in the tests folder, such as `test_x.py`, stays refused.
