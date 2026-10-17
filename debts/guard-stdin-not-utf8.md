# The guard reads stdin without forcing UTF-8

- **What.** `_force_utf8_streams` reconfigures stdout and stderr only. On Windows the script reads raw non-ASCII stdin wrongly. No lane owns the fix.
- **Where.** `_force_utf8_streams` in `hooks/guard_core.py`.
- **Decision.** `decision-watch-mod-limits` (the decision watch runs as a mod on the app's own login).
- **Retire.** `_force_utf8_streams` reconfigures stdin too. A Windows test feeds non-ASCII stdin and reads it back unchanged.
