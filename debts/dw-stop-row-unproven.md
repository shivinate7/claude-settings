# The Stop row drop is unproven in the desktop app

- **What.** The Stop row is removed. It is unproven live that `classic.Stop` reaches a mod in the desktop app. The drop stays unproven until the mod log shows `STOP seen` lines after merge.
- **Where.** The Stop row in `settings.json`, and the Stop handling in `mods/decision-watch/hooks/register.mjs`.
- **Decision.** `decision-watch-mod-limits` (what the decision-watch mod cannot do yet).
- **Retire.** The mod log shows `STOP seen` lines after merge. If none show, restore the Stop row.
