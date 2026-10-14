# A message value with `;`, `|` or a newline is not blanked

- **What.** The guard blanks the message value of a commit or a pull request, so prose that names a shell reads as text. It splits the command at `;`, `|`, `&&`, `||` and newlines first, also inside a quoted value. A value such as `-m "fix; bash <<EOF note"` is cut in two, the second part is not blanked, and a following heredoc body stays under inspection. Main denies these too, so this is no regression.
- **Where.** `_without_message_values` in `hooks/guard_core.py`, which calls `_blank_messages` in `hooks/guard_env.py`.
- **Decision.** `design-skills` (only a reviewer runs the impeccable skill).
- **Retire.** Blank the message values on the whole command with a quote-aware reading before the split. Test a commit whose `-m` value holds `;`, `|` or a newline and names a shell, ahead of a heredoc: it allows. A real `bash <<EOF` after the commit still keeps its body.
