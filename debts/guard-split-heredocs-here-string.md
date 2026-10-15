# The heredoc splitter reads a here-string as a heredoc

- **What.** `guard_core._split_heredocs` reads a quoted or commented `<<X`, or a here-string `<<<word`, as a real heredoc. It then strips later lines, so no rule sees them. Example: `cat <<<word`, then a newline, then a commit naming N20, is allowed. This is shared guard code.
- **Where.** `_split_heredocs` in `hooks/guard_core.py`.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** A here-string and a quoted `<<X` are not read as heredocs, and a case with `cat <<<word` then a commit naming N20 is refused.
