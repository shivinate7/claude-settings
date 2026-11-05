# bin/sim-lease is the one simulator queue and lease on a Mac

## The rulings

One tool, `bin/sim-lease`, holds the Mac-wide queue and lease for phone simulators. It replaces the Mac sim gatekeeper session as the thing that grants a boot. The gatekeeper (a session) reads `sim-lease status` and need not stay awake. The mistake it stops: a session boots a phone simulator outside the gatekeeper's one queue, or over the load bars.

1. Owner rulings, degen `shared-sim-lease`, 2026-11-02 13:49 to 14:47 CST, as `skills/ios-apps/SKILL.md` ("Sharing the Mac") cites them. One phone simulator boots at a time. The two Duos may run together when the load allows. The 18 Pro never runs beside a Duo. A boot needs a 5-minute load under 100. Slot 2 needs a 5-minute load under 60 and slot 1 in use. Each boot needs a 1-minute load under 60. The next in line takes the first slot to free.
2. `sim-lease take --device duo|pro --pid PID [--udid]` joins one strict FIFO queue and waits for its turn. Only the head is granted. It prints the slot (`1`, `2` or `pro`), or with `--udid` that slot's device UDID from `SLOT_UDID`, and exits 0. At the wait limit (`SIM_LEASE_WAIT`, default 300 s) it exits 1 with one stderr line that names the holders and the load. `--pid` is required on `take` and `give`; a usage error, a missing `--pid` included, prints one usage line on stderr and exits 2.
3. Limits on every grant: 5-minute load under 100, 1-minute load under 60. Duo takes slot 1, or slot 2 only while slot 1 is held and the 5-minute load is under 60. Pro is exclusive both ways. The load is read from `sysctl -n vm.loadavg` only.
4. `bin/sim-test` takes the lease for its role (`--device duo` by default, else `pro`; it boots the UDID from `take --udid`) on its own-boot path only, after its lock and the cap check and before `simctl boot`. It gives the lease back after the shutdown and before it frees its lock, on every exit, INT and TERM too. The reuse path takes no lease. A `--hold` run keeps its lease for the whole hold.
5. Recovery does not depend on the holder ending well (`verification-recovery-independent-of-state`). Each call reaps a lease or a waiter whose pid is dead, or whose `ps -o lstart=` start time differs from the one recorded at take (a reused pid). `ps` runs with `TZ=UTC`, so a start time does not change with the caller's `TZ`. A holder that dies never has to give.
6. State: `<config>/state/sim-lease/leases.json`, under `fcntl.flock` on `lock` in the same folder, written through a temp file and `os.replace`. `<config>` is `$CLAUDE_CONFIG_DIR`, else `~/.claude`.
7. No-op: when `uname -s` is not Darwin, or `CI` or `GITHUB_ACTIONS` equals `true`, `take` prints `none` (with `--udid` too) and exits 0, `give` exits 0, and no file is written. On Darwin, a no-op `take` also prints one stderr line saying no lease was taken. Any other value, `false` or empty, is not a no-op. So CI runs and Linux hosts are never queued.
8. Cost: per call, one `uname` and one `ps` per recorded pid. Take and status add one `sysctl`; a waiting take adds one `sysctl` and one `ps` per recorded pid each `SIM_LEASE_POLL` seconds (default 2). It writes `leases.json` only when the content changes, plus the empty `lock` file. No daemon, no timer, no log.

Test: `lint/test_sim_lease.py` (slots, load bars, queue order, reaping by dead pid and by changed start time, give, usage, no-op, concurrent takes) and cases 47 to 50 of `lint/test_sim_test.sh` (lease held at boot, released after the run and after TERM, refusal at load 100 boots nothing, reuse path takes none). Both use shims for `uname`, `sysctl` and `ps`.

Not proven here: there is no Mac in the cloud. The real `sysctl -n vm.loadavg` text, the real `ps -o lstart=` format on macOS and a real `simctl` boot under the lease are untested here. The shims write those formats as the tool expects them. The shell-macos CI job runs the sim-test suite on a Mac, but with shimmed load and `ps`.

Not covered: a SIGKILL of `sim-test` skips its EXIT trap, so its simulator (a Duo or the 18 Pro) stays booted while its lease is reaped. The next `sim-test` run reads the booted list after its grant: the same role reuses the device, the other role refuses (debt note `sim-test-sigkill-leaves-sim-booted`). An `xcodebuild -destination` boot skips the lease, and the route rule refuses it (decision `sim-test-is-the-one-boot-path`, ruling 5). A simulator MCP `launch` of a shut-down device is allowed only to a session that holds a live lease for that device. The guard reads `leases.json` through `live_leases` and `SLOT_UDID` in `bin/sim-lease`.

Basis: owner rulings (degen `shared-sim-lease`, 2026-11-02 13:49 to 14:47 CST), and the standing need that a session never boots over the load bars. Landed: 2026-11-04.

Kind: process
Home: bin/sim-lease
