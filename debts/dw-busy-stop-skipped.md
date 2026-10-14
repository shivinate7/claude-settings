# A Stop that lands during a judge is never judged

- **What.** A Stop that lands while a judge runs is skipped (`SKIP busy`). `decision_watch.py` scopes a turn by file time after the last human message, so for a new turn that Stop is never judged. The next Stop of that turn judges it only if one comes.
- **Where.** `hooks/decision_watch.py` (turn scoping), and the `SKIP busy` path in `mods/decision-watch/hooks/register.mjs`.
- **Decision.** `decision-watch-mod-limits` (what the decision-watch mod cannot do yet).
- **Retire.** A skipped Stop is judged on its own turn, and a case pins it.
