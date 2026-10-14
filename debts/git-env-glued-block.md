# A glued block that opens a group hides a set

- **What.** If a glued PowerShell block opener is followed by a group, the guard does not read the group. `1..2|%{($env:GIT_DIR='x')}` is allowed. The spaced form `if ($t) {(...)}` denies.
- **Where.** `_open_script_blocks` in `hooks/guard_kill.py`: the part after a glued `{` skips the opener loop.
- **Decision.** `git-env-set-denied` (the guard denies a command that sets a git location variable).
- **Retire.** Each part after a glued `{` goes through the opener loop. A case with `%{(...)}` and a set denies.
