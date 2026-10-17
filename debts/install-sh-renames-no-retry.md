# Five install renames are tried once

- **What.** Five `mv` calls in `install.sh` run once. Two are first-run backups of a person's own file. One is the cloud skills backup. One swaps a temp file over the live cloud `settings.json`. One is the `settings.json` backup. A Windows reader that holds the file fails them.
- **Where.** `install.sh`, the `mv` calls outside `put_file`.
- **Decision.** `install-sh-mv-retries` (install.sh retries the final rename).
- **Retire.** Route each through `mv_retry`, or measure that they never fail.
