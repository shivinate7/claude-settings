# A quoted PowerShell path ending in a backslash counts as a step

- **What.** `UNSAFE_TEXT` reads `\"` as an escaped quote in every shell. PowerShell has no such escape, so `Set-Location "C:\Program Files\"; <ask>` counts a step and denies. `background_steps` already skips the escape in PowerShell. `UNSAFE_TEXT` does not. Safe direction: an over-deny.
- **Where.** `UNSAFE_TEXT` in `hooks/guard.py`, which has no PowerShell branch.
- **Decision.** `ask-steps-run-alone`, a step that asks the owner runs alone.
- **Retire.** `UNSAFE_TEXT` skips `\"` in a PowerShell call, as `background_steps` does. A row in `hooks/test_guard.py` shows a quoted Windows path ending in a backslash, then an ask step in the PowerShell tool, asks alone.
