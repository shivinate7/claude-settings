# The guard's segment split ignores backslash escapes

- **What.** The split now honors every backslash escape outside single quotes. It also honors `$'...'`. A guard test denies the `$'a\'b'` form. No guard test denies the `\'` and `\"` forms, such as `echo \'; pkill foo; echo 'x'`, so a regression there would go unseen. Also, `background_steps` in `hooks/guard.py` counts `echo \" & echo b` as one step, and bash runs two. Hole L1: a nested PowerShell or cmd script is cut with bash escapes. So a path that ends in `\` before `;` hides the next command, as in `pwsh -c "cd C:\x\; wsl --shutdown"`. That command is now allowed. Before lane silent-write-narrow it was denied. Lane swn-pwsh-escape fixes it.
- **Where.** `quote_advance` and `split_segments` in `hooks/guard_core.py`, and `background_steps` in `hooks/guard.py`.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** `split_segments` honors a backslash outside single quotes, and `$'...'` quoting. Guard tests deny the three forms with `\'`, `\"` and `$'a\'b'`. A nested PowerShell or cmd script is cut with that shell's own escape, and a guard test denies the L1 form.
