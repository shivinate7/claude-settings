# Sessions boot simulators. The sweep stops idle ones.

## The rulings

This extends `unattended-sweep-stops-proven-orphans`. It adds a new act: a per-device shutdown with `xcrun simctl shutdown <UDID>`, which is not a signal. The tier lives in `janitor/sweep.py`, the one machine-wide sweep of `the-janitor-is-one-machine-wide-sweep`. Simulators belong to the machine, not to a repository. The tier runs at SessionEnd and in the scheduled job. A boot record names no repository, so the SessionEnd run cannot scope it. A tier run only by the scheduled job would leave an idle device booted for up to a day. The owner's note on Cockpit item 250 a (2026-11-04 07:53 CST) reads "too many remnant processes linger too long". Reason: booted simulators eat RAM, no session stops one, and after a boot nothing tells who booted it.

1. Record. A PostToolUse hook on Bash and on `mcp__Claude_Code_iOS_Simulator__control` records each device that the call names and that went from `Shutdown` to `Booted` during the call. A call names a device by UDID or by a name that matches a simctl device name. A call that names none records nothing. The record goes to `state/sim-boots.jsonl`, with the pid and start time of the device's launchd_sim. The hook records nothing for a device when the table holds no launchd_sim for the UDID, or more than one. It also records nothing when a name matches devices on more than one runtime, unless `OS=` picks one. An owner-booted device is never stopped, and an unclear case means keep. A Bash call is read only when its text names a simulator tool as a whole word (simctl, xcodebuild, xcrun). An MCP call is read only when its action is `launch`. `bin/sim-test` records its own boot through the same hook (`sim-test-is-the-one-boot-path`, ruling 6).
2. Stop only recorded devices. The tier stops a device only when all of these hold:
   - It was booted 1 hour or more ago.
   - The boot matches the record: the live launchd_sim has the pid and start time of the newest record line. If not, the owner booted it again by hand (code `boot-record-mismatch`).
   - No process outside that device's launchd_sim tree names its UDID, its name or `booted`.
   - Simulator.app and Xcode.app (Xcode-beta.app too) are not running.
   - All reads succeeded.

   Any read that cannot tell means keep. Each device gets one `xcrun simctl shutdown <UDID>`. Never `all`. Never erase. A run stops at most 4 devices (`janitor/sweep.py: SIM_SHUTDOWN_CAP = 4`). The rest wait for the next run.
3. Boot cap. Guard rule `simulator-boot-cap` (the boot cap) refuses a session's boot while the machine is busy by the load brake's bar, and names the readings and the booted devices (`sims-load-brake-only`, owner 2026-11-12 21:59 CST; it replaced the cap of two booted devices). A cloud session is not braked, and an unread reading counts as normal. It judges only an `xcodebuild -destination` with `id=` or `name=`, and MCP `launch` with `device` or `udid`. A raw `simctl boot` is refused first by `simulator-boot-bypass`, so the cap does not judge it. A boot that the cap and the reuse rule pass is then judged by `simulator-boot-route` or `simulator-boot-lease` (see `sim-test-is-the-one-boot-path`). The bar is the machine's, so owner-booted devices count through the load they cause and no count of devices refuses a boot. `bin/sim-test` takes its lease from `bin/sim-lease` before its own boot, which applies the same bar, because the guard does not see a boot inside that tool. The boot cap reads the load at most once per call, one memory and one disk read in the guard's own process. An agent's or a lane session's Bash boot reads it at most twice, since the load brake reads it first for that call. No test counts these reads (unmeasured).
4. Reuse. Guard rule `simulator-boot-twin` (the reuse rule) refuses a boot when an idle booted device of the same type and runtime exists, and names its UDID. "Idle" is the ruling 2 test in full. The rule matches the device type, so `OS=latest` with an idle twin on an older runtime is refused. Like ruling 3, it judges only `xcodebuild -destination` and MCP `launch`. A raw `simctl boot` is refused first by `simulator-boot-bypass`.

The boot check is in `sim-boot-is-verified`.

Kind: process
Home: janitor/sweep.py
