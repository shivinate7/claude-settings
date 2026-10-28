# Sessions boot simulators. The sweep stops idle ones.

## The rulings

This extends `unattended-sweep-stops-proven-orphans`. It adds a new act: a per-device shutdown with `xcrun simctl shutdown <UDID>`, which is not a signal. The tier lives in `janitor/sweep.py`, the one machine-wide sweep of `the-janitor-is-one-machine-wide-sweep`. Simulators belong to the machine, not to a repository. Reason: booted simulators eat RAM, no session stops one, and after a boot nothing tells who booted it.

1. Record. A PostToolUse hook on Bash and on `mcp__Claude_Code_iOS_Simulator__control` records each device that the call names and that went from `Shutdown` to `Booted` during the call. A call names a device by UDID or by a name that matches a simctl device name. A call that names none records nothing. The record goes to `state/sim-boots.jsonl`, with the pid and start time of the device's launchd_sim. The hook records nothing for a device when the table holds no launchd_sim for the UDID, or more than one. It also records nothing when a name matches devices on more than one runtime, unless `OS=` picks one. An owner-booted device is never stopped, and an unclear case means keep. A Bash call is read only when its text names a simulator tool as a whole word (simctl, xcodebuild, xcrun). An MCP call is read only when its action is `launch`.
2. Stop only recorded devices. The tier stops a device only when all of these hold:
   - It was booted 1 hour or more ago.
   - The boot matches the record: the live launchd_sim has the pid and start time of the newest record line. If not, the owner booted it again by hand (code `boot-record-mismatch`).
   - No process outside that device's launchd_sim tree names its UDID, its name or `booted`.
   - Simulator.app and Xcode.app (Xcode-beta.app too) are not running.
   - All reads succeeded.

   Any read that cannot tell means keep. Each device gets one `xcrun simctl shutdown <UDID>`. Never `all`. Never erase. A run stops at most 4 devices. The rest wait for the next run.
3. Cap 2. Guard rule `simulator-boot-cap` refuses a session's boot when 2 devices are already booted, and names them. A boot is `simctl boot`, an `xcodebuild -destination` with `id=` or `name=`, or MCP `launch` with `device` or `udid`. The cap counts every booted device, owner-booted ones included, because RAM is the limit and the cap needs no knowledge of who booted a device. With two owner-booted devices, no session can boot until the owner stops one. `bin/sim-test` applies the same cap before its own boot, because the guard does not see a boot inside that tool.
4. Reuse. Guard rule `simulator-boot-twin` refuses a boot when an idle booted device of the same type and runtime exists, and names its UDID. "Idle" is the ruling 2 test in full. The rule matches the device type, so `OS=latest` with an idle twin on an older runtime is refused.

The boot check is in `sim-boot-is-verified`.

Kind: process
Home: janitor/sweep.py
