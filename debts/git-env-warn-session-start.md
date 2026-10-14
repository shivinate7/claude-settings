# The git env warning runs at session start only

- **What.** The warning runs at session start only, so damage done mid-session shows at the next start.
- **Where.** The git env set warning in the guard hooks.
- **Decision.** `git-env-set-denied` (a command that sets git env vars is denied).
- **Retire.** The warning also runs on each mid-session set. A test with a mid-session set shows the warning.
