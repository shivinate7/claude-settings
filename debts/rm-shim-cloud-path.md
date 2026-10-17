# A cloud install adds no PATH line

- **What.** The PATH step in `install.sh` skips cloud mode, so the shim is off in cloud sessions.
- **Where.** The PATH step in `install.sh`.
- **Decision.** `rm-path-wrapper` (an rm shim on PATH, active only in Claude sessions).
- **Retire.** A cloud install puts `~/.claude/bin` first on PATH, with a fixture. Or the decision records the cloud gap as accepted.
