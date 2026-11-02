# One lock makes sim-test the one boot path on a Mac

## The rulings

Each Mac boots simulators through `bin/sim-test`, under one lock. Two boot paths still skip the lock. Ruling 5 names them.

1. One lock per Mac. `bin/sim-test` takes the lock folder `<config>/state/sim-test.lock`. `<config>` is `$CLAUDE_CONFIG_DIR`, else `~/.claude`. It takes the lock with one atomic `mkdir`. It writes its pid into a file named `pid` inside the folder. It holds the lock for the whole run: boot, tests and shutdown. It releases the lock on every exit, INT and TERM too. Reason: with a lock around the boot alone, run A can shut down a simulator that run B reuses.
2. A second run waits. While the lock is held, `sim-test` prints one line that names the holder pid. It checks the lock every 2 seconds. When the holder ends, it takes the lock and runs as in rule 1. It waits at most `SIM_TEST_LOCK_WAIT` seconds, default 300, which stays under Bash's 600 second cap. At that limit it exits 1, naming the holder pid. It boots nothing and runs no tests.
3. A lock whose pid is not alive is taken over. `sim-test` renames the lock folder to a name unique to itself. Only one rename wins. The winner removes the folder, then retries `mkdir`. A run whose rename loses removes nothing. A lock folder with no pid file counts as held for 60 seconds, then as dead and taken over the same way.
4. Guard rule `simulator-boot-bypass` (the bypass rule, in `hooks/guard.py`) refuses a session's direct boot. It refuses:
   - `simctl boot`, through `xcrun` or bare;
   - a Simulator.app open: `open -a Simulator`, `open -a Simulator.app`, `open` of a path that ends in `Simulator.app`, or `open -b com.apple.iphonesimulator`.

   The remedy names `sim-test`. The owner's override lifts the rule. The bypass rule is judged before `simulator-boot-cap` (the boot cap) and `simulator-boot-twin` (the reuse rule). So those two judge only `xcodebuild -destination` and the simulator MCP `launch`.
5. Not covered. An `xcodebuild -destination` that names a shut-down device still boots outside the lock. So does MCP `launch`.
6. Cost: one `mkdir`, one pid file and one folder removal per run. A waiting run reads the lock every 2 seconds, up to `SIM_TEST_LOCK_WAIT`. No new process.

Test: a second run waits and takes the lock when the holder ends. At the wait limit it exits 1, naming the pid, with no boot. A raw `simctl boot` is refused.

Incidents:

- Reported 2026-11-01 19:02 CST, home repo: a simulator crash-looped for 7 minutes. The lane that reported it said that `sim-test` takes no machine-wide lock. It also said that a lane that boots with `simctl` or the Simulator panel skips `sim-test`.

Basis: named incident, the home crash loop, 2026-11-01 19:02 CST. Landed: 2026-11-02.

Kind: process
Home: bin/sim-test
