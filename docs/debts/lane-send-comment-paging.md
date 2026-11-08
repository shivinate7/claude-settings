# A hand-off naming an old pull request pages every comment since it opened

- **What.** Rule `lane-lint-send` (a hand-off to the batch runner needs a lint pass) reads the repo's issue comments since the oldest open pull request the message names. A pull request open for weeks in a busy repo makes that read page many times, so the read can pass the 25 s budget, and the hand-off passes as unknown.
- **Where.** `merge/merge.py` `hand_off_read`, through `Host.review_comments`.
- **Decision.** `lane-lint-send` (a lane hands a batch runner only a pull request that passed its lint).
- **Retire.** The read takes each named pull request's own comments, so its cost does not grow with the repo's other comments. A case in family `lane-lint-send` in `hooks/test_guard.py` counts the comment reads for an old pull request.
