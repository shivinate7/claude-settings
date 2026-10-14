# Guard calls fail for up to 10 s during each install

- **What.** An install replaces the hook files one by one. In that window, the guard loads modules from two installs. It sees two INSTALL_ID values and logs `guard-crash`. On 2026-10-14 three installs did this: 4 lines at 13:45 CDT, 3 at 14:31, and 7 over 10 s at 14:41. A command in that window gets a crash line, not a verdict. The earlier estimate of about 5 s is low.
- **Where.** The module swap in `install.ps1` and `merge/install_from_main.sh`. The INSTALL_ID check in `hooks/guard_core.py`.
- **Decision.** `install-hooks-whole` (an install never shows a session a half-copied hook).
- **Retire.** Swap all guard modules in one rename, or retry the load once after a short wait. A day of merges then logs no install-id crash.
