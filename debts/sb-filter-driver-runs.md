# A repo filter driver can run during the session-board git status

- **What.** A filter driver named in repo git config can run during `git status`. The mod sets `core.fsmonitor=false`, but it does not disable filter drivers. A clean filter with a matching `.gitattributes` entry is an example. The user already trusts the repo config that names the driver.
- **Where.** The git read in `mods/session-board`.
- **Decision.** `session-board-mod-limits` (session-board keeps small records, and /safe-stop queues one prompt).
- **Retire.** The git read disables filter drivers, and a case with a clean filter shows the driver does not run.
