# A first hand-off to a parent is refused once for no record

- **What.** A lane's or runner's first send that names a pull request to its parent or coordinator is refused once, because its transcript holds no get_session, create_session or list_sessions record of that target. With an unreadable get_session, each different message costs one more refusal.
- **Where.** `hooks/guard_merge.py` `lane_lint_send_hit` (~1744-1752, the no-record steer) and `_send_refusal_spent`.
- **Decision.** `lane-lint-send` (a lane hands a batch runner only a pull request whose live head passed its lint).
- **Retire.** The sender passes its own parent, the `parent_session_id` of its own record, with no steer. A case in family `lane-lint-send` in `hooks/test_guard.py` shows the first send to that parent passing.
