# A bare bash.exe -c is not refused

- **What.** A bare `bash.exe -c` is not refused. It runs the System32 `bash.exe` when Git bash is not first on PATH.
- **Where.** The command check in `hooks/guard_wsl.py`.
- **Decision.** `wsl-allow-list` (the WSL allow list). `bare-bash-on-windows-can-resolve-to-the-wsl-stub` (the WSL stub record).
- **Retire.** Refuse a bare `bash.exe -c`, or refuse the System32 path. A test with a bare call goes red on the current code.
