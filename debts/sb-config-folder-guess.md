# The session-board config folder is a guess

- **What.** A drive-letter USERPROFILE means Windows. Under Git Bash, HOME may be `/c/Users/x`, which a Windows program cannot use. That form is avoided only when USERPROFILE holds a drive letter. Other MSYS forms are not handled. With no USERPROFILE and HOME set to `/c/Users/x`, the guess fails. `CLAUDE_CONFIG_DIR` overrides it.
- **Where.** The config folder lookup in `mods/session-board`.
- **Decision.** `session-board-mod-limits` (session-board keeps small records, and /safe-stop queues one prompt).
- **Retire.** The lookup handles each MSYS form, and a case per form pins the folder.
