# A "do not take" line to the batch runner is refused

- **What.** Rule `lane-lint-send` (a hand-off to the batch runner needs a lint pass) judges every pull request a message to a runner names, from any sender, in any sense. A coordinator that writes "Do not take #1513" to the runner is refused when #1513 has no record at its head, though the message holds the pull request back.
- **Where.** `hooks/guard_merge.py` `lane_lint_send_hit` and `_send_refs`.
- **Decision.** `lane-lint-send` (a lane hands a batch runner only a pull request that passed its lint).
- **Retire.** The rule judges only a lane's hand-off, by the sender's own record or by the message's form, and a coordinator's hold line passes. A case in family `lane-lint-send` in `hooks/test_guard.py` allows "Do not take #1513" from a coordinator.
