# c165-sim-test-cap (sim-test caps its own boots)

Status: reviewed, green locally, draft PR #755 (shivinate7/claude-settings), head eef927c1.
- Fix: bin/sim-test counts booted devices before its own boot; at 2+ it exits 1, boots nothing. Guard parsing unchanged. test_guard `sim_test_cap_check` ties CAP to SIM_BOOT_CAP (red on CAP=3).
- Red: case 21 failed on the old script. Gates: test_sim_test.sh PASS; ci-job gates --lint PASS; silent-undo clean; test_guard simulator family 36/36.
- Review: reviewer opus round 1 APPROVE. Net-value test not reached (round 1).
- Notes, not debts: count-to-boot race (tool takes no lock by design); no test for a device name with parentheses; failed `simctl list` fails open, like the guard.
- Found, not this lane's: test_guard "load-brake: probe control: a child process the probe starts is counted" fails on origin/main in the cloud container (counts 2, want 1). Reviewer confirmed it on main. Candidate CI-fix lane; orchestrator's call.
- Unproven: bash 3.2 (container has bash 5 only); CI's macOS shell job proves it.
