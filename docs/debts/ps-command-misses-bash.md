# PowerShell command check misses some bash-only forms

- **What.** Guard rule `command-in-item` refuses a `powershell` string only for `&&`, `||`, `<<`, `<<<`, `/dev/null` and `export`. A bash line such as `git log | head -5`, `FOO=1 git push`, `if [ -f x ]; then` or a `\` line end passes, and fails in PowerShell 5.1 as item 78 did.
- **Where.** The PowerShell form list and `_command_ok` in `hooks/question_form.py`.
- **Decision.** `act-in-place` (the owner acts where he reads).
- **Retire.** Refuse a pipe into a Unix-only program (`head`, `tail`, `grep`, `xargs`, `sed`, `awk`), a leading `NAME=value`, `[ ... ]` tests and a `\` line end. Tests for each are red on the old code and green on the new.
