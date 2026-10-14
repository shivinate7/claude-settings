# A substitution inside a token is not read

- **What.** A substitution inside a token is not read. Examples: `x=$(...)` and backticks.
- **Where.** The command-word reader in `hooks/guard_wsl.py`.
- **Decision.** `guard-command-position` (the one command-word resolver).
- **Retire.** Read substitutions inside tokens with the one command-word resolver. A test per example shows the refusal.
