# grep long-option abbreviations are not pinned

- **What.** `grep --regex=` style abbreviations of `--regexp`, `--expression` and `--source` are a hole. No case pins them.
- **Where.** The grep handling in `hooks/guard_env.py`.
- **Decision.** `env-file-wrappers` (the env-file rule and its wrappers).
- **Retire.** A case for each abbreviation passes in the env family of `hooks/test_guard.py`, and the rule reads it as the full option.
