# The mockup cost test covers the all-miss path only

**What.** The cost cap test for the mockup check runs on the all-miss path, where no file is on origin. That path makes 3 git starts. A mutant that does one link read per blob makes 353 starts and still passes. So "at most four" git processes for files on origin is unproven.

**Where.** `skills/roadmap/test_build.py:1937-1953`, `test_five_entries_over_fifty_origin_refs_start_at_most_four_git_processes`. The code it tests is `mockup_misses` and `mockup_on_origin` in `skills/roadmap/build.py`.

- **Decision.** `mockup-home` (mockups live in the design folder). Its Cost section names this test as the check.

**Retire.** Add a case with five files on origin/main and 50 refs that asserts at most four git starts. It passes on the code and fails on the one-read-per-blob mutant.
