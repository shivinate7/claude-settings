# The root-scope mutant is killed only inside a git checkout

- **What.** PR0 measured a kill count of 310 of 314 on the branch, against 309 on main. The one change is "root-scope: _git drops -C". That mutant is killed only when the harness runs inside a git checkout. CI does. The fragility is older than the split.
- **Where.** The root-scope mutant in the mutation harness, `hooks/mutate_guard.py`.
- **Decision.** `guard-split-by-family` (the guard splits into one module per rule family).
- **Retire.** The mutant is killed outside a git checkout too, and the kill count matches main.
