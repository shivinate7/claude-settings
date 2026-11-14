# The agent stop ends no background process on macOS or Windows

- **What.** Start ticks come from `/proc`, so off Linux every background pid is recorded "unclear" and none ends. Windows records none. Only Office pids end there. The step done check holds on Linux only. The Windows kill forms `taskkill /FI "PID eq N"` and `Get-Process -Id N | Stop-Process` pass the kill guard for another agent's pid.
- **Where.** `hooks/agent_procs.py`, the start read, and `hooks/guard_kill.py`, `_windows_kill_pids`. Unmeasured on macOS and Windows.
- **Decision.** `none`. The step names Linux only as a gap. Macs and Windows keep the tree.
- **Retire.** A case in `hooks/test_agent_procs.py` shows a start read that works off Linux, so a recorded pid ends there, and the two Windows forms are refused for another agent's pid. The suite passes.
