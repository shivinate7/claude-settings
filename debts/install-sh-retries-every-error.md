# The sh retry does not filter by error

- **What.** `mv_retry` in `install.sh` retries any `mv` error, where `Move-OverFile` in `install.ps1` retries only Win32 codes 5 and 32. A real failure costs about 2.4 s per file.
- **Where.** `install.sh`.
- **Decision.** `install-sh-mv-retries` (install.sh retries the final rename).
- **Retire.** A filter on the busy error that holds on Windows Git Bash, or the owner accepts the delay.
