# A path from a verbless sentence carries to any pathless edit

- **What.** A builder is refused "CI is red on hooks/test_guard.py:13480. Fix the guard." and "Red cases are in hooks/test_guard.py. Make them green." A test-author is refused "The bug is in hooks/guard.py. Add a red case that shows it." The path carries from the sentence before to a pathless edit clause, not only to an anaphor.
- **Where.** The carry in `message_edit_paths`, `hooks/guard.py`.
- **Decision.** `message-role-scope` (a message to an agent stays inside its role).
- **Retire.** Lane `msg-role-false-alarms` holds the red cases and a fix. Its fix check found that a green word after the anaphor ("Replace it with a passing assert") also cleared the incident form. Narrow that window to the word right after the anaphor.
