# The env-file rule refuses four safe commands

- **What.** `ag -f` and `ack -f` refuse now, though `-f` is a boolean in those tools. `grep -r --exclude=.env` and `rg -t py .env` are false alarms.
- **Where.** `hooks/guard_env.py`.
- **Decision.** `env-file-wrappers` (the env-file rule and its wrappers).
- **Retire.** Each of the four commands passes, and a case in `hooks/test_guard.py` pins each.
