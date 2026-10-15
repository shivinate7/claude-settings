# Some git-env guard forms have no test case

- **What.** No case pins the PowerShell backtick escape, the shared group-opener pattern, or quote text in a heredoc body.
- **Where.** `hooks/test_guard.py`, the git-env family.
- **Decision.** `git-env-set-denied` (a command that sets a git location variable is denied).
- **Retire.** Each form gets a case that turns red on a broken form, shown by a mutant in `hooks/mutate_guard.py`.
