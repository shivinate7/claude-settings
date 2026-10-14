# Glued PowerShell blocks and heredoc quotes hide a set

- **What.** If a PowerShell block opener is glued to its word, the guard does not read the block. `1..2|%{$env:GIT_DIR='x'}` is allowed. If an unquoted heredoc body holds an apostrophe, the env-file rule misses a later substitution that reads an env file.
- **Where.** `_open_script_blocks` in `hooks/guard_kill.py`; `env_heredoc_refusal` in `hooks/guard_env.py`.
- **Decision.** `git-env-set-denied` (the guard denies a command that sets a git location variable).
- **Retire.** Lane git-env-glued ships. Glued openers deny, and the env-file rule reads heredoc bodies with `heredoc=True`.
