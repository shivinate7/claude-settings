# A mutant of the PowerShell path reads in guard_frozen.py goes uncaught

- **What.** `GUARD_MODULE_FAMILIES` maps `hooks/guard_frozen.py` to the `frozen` family only. The PowerShell path reads (`cp`, `sc`, `ac`, `cpi`, `ni`, argument slots, comma lists) have their cases in family `paths`. The mutation job runs no case against a mutant there, so a mutant that breaks one is not caught.
- **Where.** `GUARD_MODULE_FAMILIES` in `hooks/mutate_guard.py`; the reads in `hooks/guard_frozen.py` (`_PS_COPY`, `_PS_CONTENT`, `_ALIAS_COMMAND`); the cases in `tests/guard/s20369-paths.py`. Found in review round 1 of PRs 2723, 2744 and 2753.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver); `frozen-path-resolves-shell-vars` (rule 7 resolves shell variables before it matches a write target). Neither names the PowerShell write rules.
- **Retire.** Add `paths` to the `hooks/guard_frozen.py` row, and show a mutant of a PowerShell read killed under it, in `hooks/test_mutate_ci.py`.
