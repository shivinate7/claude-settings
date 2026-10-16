# The bash reader counts a cmd /c quote differently from cmd

- **What.** cmd reads `\` as a plain character, and each `"` toggles its quote state. The bash reader of a Bash command reads `\"` inside double quotes as an escape, so that quote does not toggle. The two readings can disagree on where a `cmd /c "..."` string ends. A command that cmd runs after that point can sit inside a quote the guard reads as text. Rules that read only the outer segment would miss it. The passing shapes are unmeasured. This is not `pwsh-cmd-script-gaps` (the lone `&`), and not `guard-split-ignores-backslash` (bash text only).
- **Where.** `quote_advance` and `walk_quotes` in `hooks/guard_core.py` (the escape at line 170); `background_steps` in `hooks/guard.py` (line 1679) reads `\"` as an escape too.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** The outer reader reads a `cmd /c` string with cmd's quote rule. A guard test with `cmd /c "echo \" & X"`, where X is a command a rule denies, is denied by a rule that reads only the outer segment. The test goes red on the current code first.
