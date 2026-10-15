# node --env-file with -e prints the env file

- **What.** `node --env-file=.env -e 'console.log(process.env)'` prints the file through the runner. The runner allow-list is the limit. Main allowed it before the 2026-10-12 change.
- **Where.** The runner allow-list in `hooks/guard_env.py`.
- **Decision.** `env-file-wrappers` (the env-file rule and its wrappers).
- **Retire.** The rule refuses `node --env-file` with `-e`, and a case in `hooks/test_guard.py` pins the refusal.
