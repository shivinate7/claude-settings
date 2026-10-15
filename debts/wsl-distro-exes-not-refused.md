# debian.exe and kali.exe are not refused

- **What.** `debian.exe` and `kali.exe` are not refused.
- **Where.** The WSL distro list in `hooks/guard_wsl.py`.
- **Decision.** `wsl-allow-list` (the WSL allow list).
- **Retire.** Add both names to the refused list. A test per name shows the refusal.
