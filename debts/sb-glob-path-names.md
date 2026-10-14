# Grep and Glob paths that look like file names show by name

- **What.** Grep and Glob paths that look like a file name show by name. A folder named `v1.2` is an example. The file system check is not built.
- **Where.** The name rule for the recent list in `mods/session-board`.
- **Decision.** `session-board-mod-limits` (session-board keeps small records, and /safe-stop queues one prompt).
- **Retire.** The file system check is built, and a case with a folder named `v1.2` shows no name.
