# Another session's compact can sweep a /clear pointer

- **What.** Another session's compact reorient in the same directory can sweep a /clear pointer between SessionEnd and SessionStart. The clear then names the newest handoff there instead.
- **Where.** The reorient sweep in the SessionStart hook.
- **Decision.** `handoff-hooks-wave-2` (clear, fork, re-read and CI wake-up).
- **Retire.** The sweep keeps a pointer that a SessionEnd wrote in the same directory, and a case pins it.
