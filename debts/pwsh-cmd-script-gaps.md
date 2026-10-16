# Five shapes of a pwsh or cmd script pass the guard

- **What.** These shapes are allowed on main and on this branch. (1) `pwsh -c "taskkill /F /IM node.exe"`: the kill rule does not read a pwsh script. (2) `cmd /c "echo a & wsl --shutdown"`: the WSL rule does not cut a cmd script at its lone `&`. (3) `pwsh -EncodedCommand <base64>`: the script is not decoded, so no rule reads it. (4) `pwsh -c 'echo "$(wsl --shutdown)"'`: a substitution inside the script is not read. (5) `iex 'echo C:\x\; taskkill /F /IM node.exe'` and the same with `npm run dev` under run_in_background: the kill and stream rules do not read an `iex` script. The wsl form of (5) is denied.
- **Where.** `nested_script` and `_pwsh_script` in `hooks/guard_core.py`; the kill rule in `hooks/guard_kill.py`; the stream rule in `hooks/guard_stream.py`; `wsl_hit` in `hooks/guard_wsl.py`.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** Each rule judges the script that `nested_script` returns, and the guard decodes `-EncodedCommand`. One guard test per shape denies it, and each goes red on the current code.
