# A script heredoc body that runs impeccable is not read

- **What.** The impeccable rule reads a heredoc body when a shell word (`bash`, `sh`, `zsh`, `dash`, `ksh`, `pwsh`, `powershell`) stands before the `<<` on its header line. A body fed to Python, Node, Perl or Ruby is skipped, so `os.system("npx impeccable install")` in a `python3 - <<'EOF'` body is allowed. Reading that body as shell lines refused text that only named the word, as a field denial on 2026-10-13 showed.
- **Where.** `impeccable_command_hit` in `hooks/guard.py`, and `SHELL_HEREDOC` in `hooks/guard_core.py`.
- **Decision.** `design-skills` (only a reviewer runs the impeccable skill).
- **Retire.** Parse the body with the language's own parser and judge the string a `os.system`, `subprocess` or `child_process` call runs. A case with such a call and `install` denies, and the line `if 'impeccable' in f: continue` still allows.
