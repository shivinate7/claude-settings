# The 2-device simulator cap outlives the owner ruling that rules it out

- **What.** The owner ruled out every hard-coded simulator limit, the guard's 2-device cap included. The cap still stands: `bin/sim-test` and the guard refuse a third booted device. A session that needs a third simulator is refused although the ruling lets the load brake alone decide.
- **Where.** `bin/sim-test`, `CAP`; `hooks/guard.py`, `SIM_BOOT_CAP`, rule `simulator-boot-cap`; `lint/test_sim_test.sh`, case 107; `skills/ios-apps/SKILL.md`, "Boot bars".
- **Decision.** `sims-load-brake-only`, the owner ruling "No hard-coded simulator limit" (owner, 2026-11-12 21:59 CST, on the roadmap branch under `roadmap/rulings/`, whose text names the cap). The cap's own home is `sweep-shuts-down-idle-simulators`, ruling 3, the 2-device cap.
- **Retire.** A follow-up lane removes `CAP` from `bin/sim-test` and `SIM_BOOT_CAP` from the guard, re-points case 107 and the matching guard cases, and rewrites ruling 3 of `sweep-shuts-down-idle-simulators` and the "Boot bars" text. Proof: `lint/test_sim_test.sh` passes with a third device allowed under the load bars.
