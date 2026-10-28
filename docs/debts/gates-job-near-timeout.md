# The gates job runs near its cap

**What.** The gates job took 30.4 min slowest over 30 runs (median 22.1), 84% of its 36 min cap, on 2026-10-27. The guard fixture suite alone took 10.6 min slowest, so it moved to the `gates-guard` job. The gates job is projected at 19.8 min slowest, 55% of its cap. Suite growth is the cause, and the cap only hides it. Figures: decision `ci-job-caps`.

**Where.** `.github/workflows/gates.yml`, the `gates` job, `timeout-minutes`.

**Decision.** `ci-job-caps`.

**Retire.** The gates job's slowest green run is under half the cap (18 min). A gates run after the split shows it. Then delete this debt.
