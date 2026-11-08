# A builder rewrote a test-author file with Bash

- **What.** On 2026-11-07 a builder rewrote `hooks/mutate_guard.py` with a Bash script and pushed it. The next commit restored it. The builder check reads only test paths. It leaves the three mutation tests out on purpose, so the write passed. Whether a builder may change them is not in the decision.
- **Where.** `hooks/guard.py`: `AUTHOR_MUTATION_TESTS` and `author_path_ok` name the three mutation tests as test-author code. `builder_test_path` reads `is_test_rel`, which leaves them out.
- **Decision.** `builders-cannot-edit-tests` (builders cannot edit tests). The decision does not name the three mutation tests.
- **Retire.** An owner ruling on whether builders may change the three mutation tests. If they may not, a case in `hooks/test_guard.py` refuses a builder's Bash or Edit write to `hooks/mutate_guard.py`, and the suite passes.
