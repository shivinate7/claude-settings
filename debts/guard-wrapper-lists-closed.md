# Guard wrapper lists are closed

- **What.** The guard skips only the wrappers in `COMMAND_WRAPPERS` and the value flags in `WRAPPER_VALUE_FLAGS`. An unlisted wrapper or value flag hides the real command word.
- **Where.** `COMMAND_WRAPPERS` and `WRAPPER_VALUE_FLAGS` in `hooks/guard_core.py`.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** A new wrapper or flag gets a list entry and a guard test that refuses a refused command behind it. Or the guard reads every word for refused commands.
