# Some install writes are still in place

- **What.** The `CLAUDE.md` pointer, `settings.json` in `install.sh`, the skills folder, the install log and the marker are written in place. Hooks other than the guard import guard modules with no reload.
- **Where.** `install.ps1`, `install.sh`, and the imports in `hooks/stall_watch.py`, `hooks/ci_wake.py` and `hooks/sendmessage_state.py`.
- **Decision.** `install-hooks-whole` (an install never shows a session a half-copied hook).
- **Retire.** Every installer write goes through the temp-then-rename helper. The reader loop in `install-no-gap.test.ps1` reads these files too and stays green.
