# The decision-watch textOf drops the abort reason

- **What.** `textOf` drops `r.reason`, so an aborted call reads `no text`.
- **Where.** `textOf` in `mods/decision-watch/hooks/register.mjs`.
- **Decision.** `decision-watch-mod-limits` (what the decision-watch mod cannot do yet).
- **Retire.** `textOf` keeps `r.reason`, and `mods/decision-watch/decision-watch.test.mjs` shows an aborted call names its reason.
