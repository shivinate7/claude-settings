# Two install renames are tried once

- **What.** The first-run backup of a person's own file and the `settings.json` backup in `install.sh` run `mv` once. A Windows reader holding the file fails them.
- **Where.** `install.sh`.
- **Decision.** `install-sh-mv-retries` (install.sh retries the final rename).
- **Retire.** Route both through `mv_retry`, or measure that they never fail.
