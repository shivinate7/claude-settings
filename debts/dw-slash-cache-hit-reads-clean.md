# A /dw cache hit reads like a clean turn

- **What.** On a cache hit `/dw` prints `nothing to say (no protected change, no model call)`, so a second `/dw` after a FLAG reads like a clean turn. A second `/dw` on the same turn says `nothing to say`, because `/dw` keeps its own cache. `Stops seen` counts only lines still in the 500-line log, so N is at most 500.
- **Where.** `mods/decision-watch/` (the `/dw` output, its cache and `Stops seen`).
- **Decision.** `decision-watch-mod-limits` (what the decision-watch mod cannot do yet).
- **Retire.** A cache hit prints a line that differs from a clean turn, and `mods/decision-watch/decision-watch.test.mjs` pins it.
