# The /safe-stop origin check is a block-list

- **What.** The origin check is a block-list. An unclassified origin still runs `/safe-stop`. A command from "unclassified" is an example. The desktop app can send "unclassified". The check does not prove that a person typed the command.
- **Where.** The origin check in `hooks/lib.mjs` of `mods/session-board`.
- **Decision.** `session-board-mod-limits` (session-board keeps small records, and /safe-stop queues one prompt).
- **Retire.** The check becomes an allow-list of origins, and a case with "unclassified" is refused.
