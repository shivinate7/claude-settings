# One lock makes sim-test the one boot path on a Mac

## The rulings

Each Mac boots simulators through `bin/sim-test`, under one lock. Two boot paths still skip the lock. Ruling 4 names them.

1. One lock per Mac. `bin/sim-test` takes the lock folder `<config>/state/sim-test.lock`. `<config>` is `$CLAUDE_CONFIG_DIR`, else `~/.claude`. It takes the lock with one atomic `mkdir`. It writes its pid into a file named `pid` inside the folder. It holds the lock for the whole run: boot, tests and shutdown. It releases the lock on every exit, INT and TERM too. Reason: with a lock around the boot alone, run A can shut down a simulator that run B reuses.
2. A second run refuses at once. While the lock is held, `sim-test` names the holder pid. It says to wait with `wait-pid <pid>` and run again. It exits 1. It boots nothing and runs no tests. A lock whose pid is not alive is taken over.
3. Guard rule `simulator-boot-bypass` (the bypass rule, in `hooks/guard.py`) refuses a session's direct boot. It refuses:
   - `simctl boot`, through `xcrun` or bare;
   - a Simulator.app open: `open -a Simulator`, `open -a Simulator.app`, `open` of a path that ends in `Simulator.app`, or `open -b com.apple.iphonesimulator`.

   The remedy names `sim-test`. The owner's override lifts the rule. The bypass rule is judged before `simulator-boot-cap` (the boot cap) and `simulator-boot-twin` (the reuse rule). So those two judge only `xcodebuild -destination` and the simulator MCP `launch`.
4. Not covered. An `xcodebuild -destination` that names a shut-down device still boots outside the lock. So does MCP `launch`.
5. Cost: one `mkdir`, one pid file and one folder removal per run. No process and no timer.

Test: a second run refuses while the lock is held. A raw `simctl boot` is refused.

Incidents:

- Reported 2026-11-01 19:02 CST, home repo: a simulator crash-looped for 7 minutes. The lane that reported it said that `sim-test` takes no machine-wide lock. It also said that a lane that boots with `simctl` or the Simulator panel skips `sim-test`.

Basis: named incident, the home crash loop, 2026-11-01 19:02 CST. Landed: 2026-11-02 for rule 3. Rules 1 and 2 are not built yet.

Kind: process
Home: bin/sim-test
