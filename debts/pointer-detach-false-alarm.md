# The pointer guard refuses a detach onto main's commit

- **What.** The pointer guard refuses `checkout --detach main` in the live install checkout, but `hooks/session_start.sh` counts a checkout detached at main's commit as on main. A fast-forward merge does the same move and passes.
- **Where.** `hooks/guard_pointer.py`, `head_move_target`.
- **Decision.** none
- **Retire.** A detach whose target resolves to local main's commit passes, and a case pins it.
