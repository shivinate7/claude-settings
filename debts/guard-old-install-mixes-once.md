# Guard installs from before the switch mix once

- **What.** An install made before the switch rule copies guard files one at a time into `~/.claude/hooks`. During that copy a session can load modules from two installs. The mix stays on that machine until its first install under the new rule.
- **Where.** The per-file copy in `put_file` in `install.sh`, and its twin in `install.ps1`, as they stand before the switch. It affects each machine's installed `~/.claude/hooks`.
- **Decision.** `merge-reinstalls-from-main` (the guard set switches as one folder and one rename).
- **Retire.** The first install under the new rule on each machine. Check: after that install, `~/.claude/hooks/guard.py` loads from one `guard.d/<id>/` folder, and the guard logs no install-id crash for a day.
