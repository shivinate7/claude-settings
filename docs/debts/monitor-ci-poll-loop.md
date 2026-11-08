# A Monitor loop can poll CI status

**What.** Mistake: an agent refused a CI watch writes a poll loop under Monitor instead. `waiter_verdict` (its `monitor` branch) refuses only `gh run watch`, `gh pr checks --watch` and `timeout /t`. Probe: `while [ "$(gh run view 1 --json status -q .status)" != completed ]; do sleep 1; done` with `timeout_ms` passes under Monitor. The pass is a code read, not a run. A plain Bash call refuses that loop. Harm: up to about 3,600 status reads an hour, one a second, computed and unmeasured, against the shared 5,000-an-hour core limit. The recorded figure, 131 calls in 60 s from `gh run watch`, sits in decision `ci-wait-reads-run-status` (CI waits read the run status). `WAITER_MONITOR_REASON` tells an agent to poll another condition in a loop with a short pause, so the hit is likely.

**Where.** `hooks/guard_stream.py`: `waiter_verdict` (its `monitor` branch), `WAITER_REASON`, `WAITER_MONITOR_REASON`.

**Decision.** `agents-wait-with-monitor` (agents wait with Monitor), and `ci-wait-reads-run-status` (CI waits read the run status).

**Retire.** Fix, either way: refuse a Monitor loop that polls CI status with a short pause, or point its remedy at the CI-wake notice. End state: a `hooks/test_guard.py` case runs the probe with `timeout_ms` and expects deny. The case goes red on today's code first.
