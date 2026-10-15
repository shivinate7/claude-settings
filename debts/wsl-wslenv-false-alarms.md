# WSLENV reads in the same command raise false alarms

- **What.** False alarms occur when the same command also runs wsl. Examples: `echo "WSLENV=x"`, `${env:WSLENV}` reads, and `grep "WSLENV"`.
- **Where.** The WSLENV check in `hooks/guard_wsl.py`.
- **Decision.** `wsl-allow-list` (the WSL allow list).
- **Retire.** Read only assignments and sets as WSLENV writes. A test per example gives no alarm.
