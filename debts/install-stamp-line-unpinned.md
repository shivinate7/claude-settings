# The install stamp line has no pin to the guard files

- **What.** Tests pin each stamper only to fixture copies. If the placeholder line in one `hooks/guard*.py` drifts, that file installs unstamped. The installer exits 0, and the guard then denies every call.
- **Where.** `install.ps1` (`$StampPlaceholder`), `install.sh`, and the `# INSTALL_ID` line in each `hooks/guard*.py`.
- **Decision.** `install-hooks-whole` (an install never shows a session a half-copied hook).
- **Retire.** A test reads each `hooks/guard*.py` in the repo and finds exactly one placeholder line that equals the stampers' text.
