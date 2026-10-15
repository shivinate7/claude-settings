# A WSLENV set with no equals sign is not refused

- **What.** A WSLENV set with no `=` is not refused. Examples: `New-Item Env:`, `Set-Item` after `cd env:`, `read`, `${WSLENV:=x}`, and `printf -v`.
- **Where.** The WSLENV check in `hooks/guard_wsl.py`.
- **Decision.** `wsl-allow-list` (the WSL allow list).
- **Retire.** Refuse each set form, or name the form as a limit. A test per example gives the chosen verdict.
