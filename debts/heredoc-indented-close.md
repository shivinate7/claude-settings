# An indented closing line ends a heredoc early

- **What.** `_split_heredocs` matches the closing line after `.strip()`, so an indented `  EOF` closes a heredoc. Bash closes only on a line that is exactly the delimiter (or tab-indented with `<<-`). Text after the indented line is read as commands by the guard, though bash still reads it as body.
- **Where.** `_split_heredocs` in `hooks/guard_core.py`.
- **Decision.** `design-skills` (only a reviewer runs the impeccable skill), for the impeccable rule. Every family that strips a heredoc body shares the gap.
- **Retire.** Match the delimiter exactly, and with only leading tabs when the header is `<<-`. A case with an indented `EOF` line inside a body, followed by a line naming a refused command, allows.
