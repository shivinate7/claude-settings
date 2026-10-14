# SubagentStop fails open on a missing guard module

- **What.** On SubagentStop, a missing guard module still fails open, and one log line records it. Rule 3 of `guard-audit-high` says a missing guard module makes the guard refuse. `gate-hooks-fail-closed` keeps the SubagentStop guard open on purpose, because exit 2 there sends the agent back to work.
- **Where.** The SubagentStop guard in `hooks/guard.py`.
- **Decision.** `guard-audit-high` (guard rules from the 2026-10-13 audit).
- **Retire.** The two decisions agree by a recorded owner ruling, and a test pins the chosen behavior.
