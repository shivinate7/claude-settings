# One session at a time holds the iPhone Duo simulator

## The rulings

1. The lease.

The shared iPhone Duo simulator (UDID `AC2E94F9-0E44-4D9C-B27A-54DA45BC4698`) has one holder at a time. `bin/sim-lease` keeps the lease and the line. Reason: several repos test on the one Duo, and two sessions that fold it or run tests on it at once break each other's runs.

- A session runs `sim-lease want WHO NOTE` to join the line, then `sim-lease take WHO` before it touches the Duo. `take` wins only when the lease is free or expired and the line is empty or WHO is first.
- The holder runs `sim-lease renew WHO` while it works, with `--pid PID` for a long job, and `sim-lease release WHO` when done. `release` prints the next in line.
- The lease expires 20 minutes after the last `take` or `renew` (`SIM_LEASE_TTL_MIN` overrides; 20 is unmeasured). A recorded pid that is still alive keeps it.
- The gatekeeper session ranks the line with `sim-lease rank`: a wait that blocks a merge first, then a wait that blocks a design.
- No timer and no daemon. Each call checks expiry itself. State is one file, `state/sim-lease.json` under the config dir, under a file lock.
- The existing simulator rules stay: the boot cap 2, the reuse rule and the idle sweep of `sweep-shuts-down-idle-simulators`.
- The lease covers only the shared Duo. A lane may make its own throwaway Duo (`simctl create`) and delete it after use. That device needs no lease, but it counts toward the boot cap.
- `sim-lease` replaces the untracked lock `~/.claude/locks/ios-simulator.lock`. Do not read or honour that path.

2. `bin/sim-test` tests on the Duo first. It takes the lease as `SIM_LEASE_WHO` and refuses when that is unset. It renews the lease with its own pid and releases it at exit. It boots the Duo with `simctl bootstatus -b` and shuts it down at exit only if it booted it. With `SIM_TEST_ALSO_PRO=1`, it then runs the same tests on the iPhone 18 Pro, which needs no lease. The exit code is non-zero if either run fails. Reason: the Duo is the phone the apps target, and both runs is best (owner, chat, 2026-11-02 13:17 CST).

How to work on the Duo once you hold it lives in the shivinate7/home repo, record `duo-simulator`. This record does not restate it.

Gap: nothing makes a session take the lease. The simulator MCP tool, `hinge` and raw `simctl` are not gated. Sessions run `sim-lease take` first by hand. A guard rule waits for an incident.

Risk: owner-named need (chat, 2026-11-02 13:00 CST). The owner ruled at 13:05 CST that the gated device is the iPhone Duo, not the iPhone 17.

Kind: process
Home: bin/sim-lease
