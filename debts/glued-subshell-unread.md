# A glued subshell is unread

- **What.** `(rm -rf .)` and `x=$(tail -f y)` pass, because the closing parenthesis is glued to the last word.
- **Where.** `hooks/guard_push_delete.py`, `hooks/guard_stream.py`.
- **Decision.** `guard-reads-wrapped-commands` (the stream and delete guards read the command a wrapper runs).
- **Retire.** Split parentheses as separate tokens before the read.
