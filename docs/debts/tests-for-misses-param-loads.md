# The mutation selector misses a load whose path is a parameter

**What.** `--tests-for` reads a file load only when the path argument holds a `<stem>.py` literal, inline or through a name bound to one. A path passed in through a function parameter is missed. So `hooks/test_call_judge.py` (`load_file_module(GUARD, ...)`) is not selected for `hooks/guard.py`. The mutation report then reads such lines as untested when a suite does test them.

**Where.** `_suite_profile` in `hooks/mutate_guard.py`.

**Decision.** `mutation-ci-report-and-replay`, the mutation report job and the known-defect replay.

**Retire.** The selector follows a path parameter to its call sites, or the wrapper suites name their module in a form the selector reads. `--tests-for hooks/guard.py` then prints `hooks/test_call_judge.py`.
