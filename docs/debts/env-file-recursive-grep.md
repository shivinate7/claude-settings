# Env-file guard refuses a search that names no env file

- **What.** After a `cd` into a scratchpad folder, a read-only search that names no env file was refused as env-file. First sighting: `grep -r --exclude-dir=proj K` (also with `.`, `'.*'`, `../proj`) in a folder that held one plain file and no env file. Second sighting, 2026-11-23: `git grep` naming no env file, with the command kept and the folder not kept. Cause unknown. A recursive read that may reach an env file elsewhere is one guess, and it could be by design.
- **Where.** `hooks/guard_env.py`, the env-file guard. The cause is not located.
- **Decision.** `env-file-stays-unread` (no session reads an environment file). This debt is a false refusal, so the decision's rule is not in question.
- **Retire.** Close when a `git grep` and a `grep -r` that name no env file pass the guard in a scratchpad folder, and a case pins it in `hooks/test_guard.py`, which runs green.

Seen: 2026-11-23 x2
