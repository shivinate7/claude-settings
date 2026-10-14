# Three tools glob the guard modules on their own

- **What.** `lint/rule_audit.py`, `lint/check_landed_dirs.py` and `hooks/mutate_shared.py` each glob `hooks/guard*.py`. The lints run without the hooks folder on their import path, so they cannot share one helper yet.
- **Where.** The three tools named above.
- **Decision.** `guard-split-by-family` (the guard splits into one module per rule family).
- **Retire.** One shared helper lists the guard modules, all three tools call it, and a test pins the list.
