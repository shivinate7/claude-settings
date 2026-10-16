# The kill rule does not read a `cmd /c` script as a command

- **What.** `cmd /c taskkill /F /IM node.exe` is allowed. So is `cmd /c cd C:\x\& taskkill /F /IM node.exe`, where cmd runs the taskkill after `&`. Both are allowed on main too. The kill rule judges the words of the segment, and it does not judge the script that `cmd /c` runs. Lane swn-pwsh-escape found the gap and left it, because it was not a regression.
- **Where.** The machine-wide kill rule in `hooks/guard_kill.py`; `nested_script` in `hooks/guard_core.py` returns the `cmd /c` script that the rule would judge.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** The kill rule judges each segment of the `cmd /c` script as a command. Guard tests in family kill deny both forms above, and they go red on the current code.
