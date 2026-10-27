# The checks job runs near its cap

**What.** The checks job took 13.7-17.8 min over 12 green runs on 2026-10-17. Two runs were
cancelled at 18m10s by the old 18 min cap, with every CI step green. The cap is now 36 min, 2x
the slowest green run. Suite growth is the cause, and the cap only hides it.

**Where.** `.github/workflows/checks.yml`, the `checks` job, `timeout-minutes`.

**Decision.** none.

**Retire.** Split the slowest suite into its own job, so the checks job's slowest green run
is under half the cap. A checks run shows it.
