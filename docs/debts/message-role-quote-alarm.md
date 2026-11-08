# A double-quoted example is read as an order

- **What.** A message that quotes a sample order in double quotes, such as a case text "Fix guard.py to pass tests/test_guard.py.", is read as an order. Five of six messages one lane sent its test-author were refused this way; none was a true hit.
- **Where.** The masking in `message_edit_paths`, `hooks/guard.py`: only fences and backtick spans of several words are masked.
- **Decision.** `message-role-scope` (a message to an agent stays inside its role).
- **Retire.** Lane `msg-role-false-alarms` masks double-quoted spans of several words; its fix check passed that part.
