# A hand-off naming six pull requests is not judged

- **What.** Rule `lane-lint-send` (a hand-off to the batch runner needs a lint pass) judges at most five pull requests in one message. A sixth makes the whole message unknown, so a batch hand-off of six unlinted pull requests passes with one note. The cap of five is unmeasured: no read timing backs it.
- **Where.** `hooks/guard_merge.py` `LANE_SEND_MAX` and `lane_lint_send_hit`.
- **Decision.** `lane-lint-send` (a lane hands a batch runner only a pull request that passed its lint).
- **Retire.** The cap rests on a measured read time, or a message past it judges its first five pull requests and notes the rest. A case in family `lane-lint-send` in `hooks/test_guard.py` refuses a six-PR hand-off whose first PR has no record.
