# Guard calls fail for up to 10 s during each install

- **What.** While an install replaces the hook files, the guard loads modules from two installs, sees two INSTALL_ID values and logs `guard-crash`. On 2026-10-14 three installs each showed it: 4 lines at 13:45 CDT, 3 at 14:31 and 7 over 10 s at 14:41. A session that runs a command in that window gets a crash line instead of a verdict. The earlier estimate of about 5 s is low.
- **Where.** The module swap in `install.ps1` and `merge/install_from_main.sh`; the INSTALL_ID check in `hooks/guard_core.py`.
- **Decision.** `install-hooks-whole` (an install never shows a session a half-copied hook).
- **Retire.** An install swaps all guard modules in one rename, or the guard retries the load once after a short wait, and a day of merges logs no install-id crash.
