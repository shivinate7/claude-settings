# The checks job runs near its cap

**What.** The checks job took 35.4 min slowest over 16 green runs (median 28.9, range 25.2-35.4), 68% of its 52 min cap, from 2026-11-01 to 2026-11-02; its old 36 min cap was at 98%. The cause is unmeasured: the three grown steps add 2.4 min, but the median rose 6.8 min (figures: decision `ci-job-caps`).

**Where.** `.github/workflows/checks.yml`, the `checks` job, `timeout-minutes`.

**Decision.** `ci-job-caps`.

**Retire.** The checks job's slowest green run is under half the cap (26 min). Then delete this debt.
