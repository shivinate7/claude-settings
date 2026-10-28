# c161-cloud-probe-count

Status: draft PR #765 (three cloud test reds fixed in each test's control), head 442cbf74, reviewer (opus) approved in round 1.

- Load-brake probe: Python 3.13 spawns through os.posix_spawn, so one child counted twice. Fixed in the probe.
- test_handoff_wave2: a root run now locks the pointer with chattr +i.
- install_from_main case 8: the suite unsets CLAUDE_CODE_REMOTE.
- githooks main-ref: already green on main 599dd58.
Gates (--lint --base origin/main) and silent-undo --strict pass. Waiting on the orchestrator to batch it.
