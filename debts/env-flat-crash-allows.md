# A crash in the env-file reader allows the call

- **What.** A runtime crash in `_env_flat` allows the call.
- **Where.** `_env_flat` in `hooks/guard_env.py`.
- **Decision.** `env-file-wrappers` (the env-file rule and its wrappers).
- **Retire.** A crash in `_env_flat` refuses the call, and a case injects the crash and checks the refusal.
