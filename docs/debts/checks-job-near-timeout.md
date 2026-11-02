# The checks job runs near its cap

**What.** The checks job took 35.4 min slowest over 16 green runs (median 28.9, range 25.2-35.4), 68% of its 52 min cap, from 2026-11-01 to 2026-11-02. At its old 36 min cap the slowest was 98%. The cap is a stopgap under the owner's 2026-11-01 18:44 CST ruling. The step "install.sh checkout-detection suite" is the only step that grew by more than 1 min (mean 3.67 to 5.83 min). Suite growth is the cause, and the cap only hides it. Figures: decision `ci-job-caps`.

**Where.** `.github/workflows/checks.yml`, the `checks` job, `timeout-minutes`.

**Decision.** `ci-job-caps`.

**Retire.** The checks job's slowest green run is under half the cap (26 min). Then delete this debt.
