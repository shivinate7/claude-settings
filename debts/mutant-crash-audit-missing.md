# Mutants other than the watch target are not audited for hidden crashes

- **What.** The fix colocates `guard.py` for `watch` mutants only. It does not audit whether another mutant, of either target, could crash for a different, unseen reason. Such a crash could still read as a false `KILLED`. The required-name field narrows this risk, because a crash's output rarely contains the exact case name a mutation claims to break. It is not proof against every crash shape.
- **Where.** The verdict loop in `hooks/mutate_guard.py`.
- **Decision.** `mutant-cause-of-death` (a mutant proves nothing until its own cause is checked).
- **Retire.** Each mutant's kill is traced to its named case, or a check flags a crash-shaped `KILLED`. A test pins the check.
