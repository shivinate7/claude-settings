# Only the WSL rule reads env -S

- **What.** `env -S 'cmd'` runs `cmd`. Only the WSL rule reads that script. The impeccable-review-only, draft-pr, detached-launch and rm-var-unguarded rules do not see inside it.
- **Where.** `nested_script` in `hooks/guard_core.py` has one caller, `hooks/guard_wsl.py`.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** Each of those rules reads `nested_script`. A guard test per rule with its refused command inside `env -S '...'` refuses.
