# A body fed by here-string or a shell variable to a shell is not read

- **What.** The impeccable rule keeps a heredoc body only when the shell word stands before `<<`. A body that reaches a shell another way is skipped, so `$SHELL <<EOF` and `bash <<< "npx impeccable install"` run impeccable and are allowed.
- **Where.** `SHELL_HEREDOC` in `hooks/guard_core.py`, and `impeccable_command_hit` in `hooks/guard.py`.
- **Decision.** `design-skills` (only a reviewer runs the impeccable skill).
- **Retire.** Read a shell variable before a heredoc, and the text of a `<<<` here-string, as shell lines. A case for each of the two shapes denies. (The pipe into a shell closed in heredoc-one-step: `_PIPED_SHELL`.)
