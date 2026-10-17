# Five install renames are tried once

- **What.** Five `mv` calls in `install.sh` run once: the first-run backups of a person's own file, the cloud skills backup, the cloud `settings.json` swap of a temp file over the live file, and the `settings.json` backup. A Windows reader that holds the file fails them.
- **Where.** `install.sh`, the `mv` calls outside `put_file`.
- **Decision.** `install-sh-mv-retries` (install.sh retries the final rename).
- **Retire.** Route each through `mv_retry`, or measure that they never fail.
