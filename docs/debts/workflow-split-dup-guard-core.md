# The builder test-step guard repeats the shell splitters

**What.** PR #2096 (builder workflow guard: refuse a test step that can no longer fail) adds `workflow_split_top` and `workflow_cd`. They repeat `guard_core.split_segments` and `dir_before_segment`, and the change states no reason for the copies. `workflow_command_tests` still splits a line with its own regex, `WORKFLOW_COMMAND_SPLIT`. So one shell line has three splitters.

**Where.** `hooks/guard.py`, `workflow_split_top`, `workflow_cd` and `workflow_command_tests` on the PR #2096 branch. The one homes are `split_segments` and `dir_before_segment` in `hooks/guard_core.py`.

**Decision.** `builders-cannot-edit-tests`, builders cannot edit tests (the workflow test-step rule). The rule `building-one-home-per-capability`, give each capability one home, names this finding.

**Retire.** Read the workflow lines with `guard_core.split_segments` and `dir_before_segment`, and delete `workflow_split_top` and `workflow_cd`. Or write in the code the reason each copy differs. When `hooks/guard.py` no longer defines `workflow_split_top` or `workflow_cd`, and a case in `hooks/test_guard.py` shows the workflow test-step verdicts unchanged after the switch, the debt closes.
