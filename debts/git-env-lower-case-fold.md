# Lower-case git env names fold to the rule

- **What.** Lower-case names fold to the rule, so `git_dir=x cmd` is denied too. No recorded call names this as the accepted rule.
- **Where.** The name match for git env sets in the guard hooks.
- **Decision.** `git-env-set-denied` (a command that sets git env vars is denied).
- **Retire.** A recorded ruling on lower-case names, and a test that pins it.
