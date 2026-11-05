# The mutation selector misses suites that import a file

**What.** `hooks/mutate_guard.py --tests-for` maps a file only to the `test_<stem>` files beside it, or to its `REPORT_TARGETS` line. A suite that imports or loads the file by another name is not run. So the first mutation report (run 42064515414) read 0 of 9 caught: every survivor sat in the replay and CI code of `hooks/mutate_shared.py`, which `hooks/test_mutate_replay.py` and `hooks/test_mutate_ci.py` test.

**Where.** `tests_for_main` in `hooks/mutate_guard.py`.

**Decision.** `mutation-ci-report-and-replay`, the mutation report job and the known-defect replay.

**Retire.** `--tests-for hooks/mutate_shared.py` prints `hooks/test_mutate_replay.py` and `hooks/test_mutate_ci.py` too, and a test in `hooks/test_mutate_ci.py` pins it.
