# "Go green" is no goal word

- **What.** A builder is refused "Red cases are in tests/x.py. Make them go green." and "... Make it turn green." The goal check reads only a green word in its window, and "go" or "turn" before it is not a filler. A refusal sends the work to the wrong role.
- **Where.** `MESSAGE_GREEN` and `_anaphor_carry` in `hooks/guard.py`.
- **Decision.** `message-role-scope` (a message to an agent stays inside its role).
- **Retire.** Add "go" and "turn" as goal fillers, with an allow case for each form in `hooks/test_guard.py`.
