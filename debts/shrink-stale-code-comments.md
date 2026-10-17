# Two code comments cite deleted rules

- **What.** A case comment in `hooks/test_guard.py` names `git-wait-for-required-checks`. `hooks/guard_kill.py` quotes the dropped `pkill -f` sentence.
- **Where.** `hooks/test_guard.py`, `hooks/guard_kill.py`.
- **Decision.** `claude-md-shrink` (CLAUDE.md drops the prose of a rule that a guard or gate enforces).
- **Retire.** Both comments name what enforces the act now.
