# The decision-watch pickPython runs where.exe in both phases

- **What.** `pickPython` runs `where.exe` in both phases.
- **Where.** `pickPython` in `mods/decision-watch/hooks/register.mjs`.
- **Decision.** `decision-watch-mod-limits` (what the decision-watch mod cannot do yet).
- **Retire.** `where.exe` runs once per turn or is cached, and `mods/decision-watch/decision-watch.test.mjs` pins one run.
