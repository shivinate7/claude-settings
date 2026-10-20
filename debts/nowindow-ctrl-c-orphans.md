# Ctrl-C under verdict may orphan grandchildren

- **What.** With CREATE_NO_WINDOW the child gets its own hidden console, so Ctrl-C may not reach grandchildren. Unmeasured.
- **Where.** bin/verdict, its kill path.
- **Decision.** `spawns-use-no-window` (helper programs start with no window).
- **Retire.** Measure Ctrl-C on a verdict run that starts grandchildren. Fix the kill path if they live on.
