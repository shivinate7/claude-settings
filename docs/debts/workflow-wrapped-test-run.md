# A wrapped test run is refused as a dropped test

**What.** A builder who wraps a bare test run in a workflow is refused as a dropped test path. The wrapped forms are `timeout 600 python3 x/test_a.py`, `xvfb-run -a python3 x/test_a.py`, `coverage run x/test_a.py`, `uv run x/test_a.py`, `env FOO=1 python3 x/test_a.py` and `nice python3 x/test_a.py`. The test-author cannot add a wrapped run either, so the edit is a dead end for both roles. Found in the round-3 review of lane `checks-yml-role-gap`.

**Where.** `hooks/guard.py`, `workflow_command_tests`. It reads the first token of each command segment as the command, and skips only `VAR=`, `npx`, `sudo` and `time`. A wrapper hides the test, so `workflow_drops_tests` (called by `workflow_builder_refused`) counts it as not run. `workflow_run_is_test` has the same first-token rule for a test-author's single-line `run:`.

**Decision.** `builders-cannot-edit-tests`, builders cannot edit tests (the workflow test-step rule).

**Retire.** Skip the known wrapper commands before the interpreter or test path, in both `workflow_command_tests` and `workflow_run_is_test`. A wrapper's flags and values (`-a`, `600`, `FOO=1`) and its subcommand (`run` after `coverage` or `uv`) are skipped with it. Closed when a red case in `hooks/test_guard.py` shows each wrapped form above passes: a builder's wrap of a bare run is not refused, and a test-author's wrapped single-line `run:` passes `workflow_run_is_test`.
