# Sessions boot simulators. The sweep stops idle ones.

## The rulings

This extends unattended-sweep-stops-proven-orphans. It adds a new act: a per-device shutdown with
`xcrun simctl shutdown <UDID>`, which is not a signal. The tier lives in `janitor/sweep.py`, the one
machine-wide sweep of the-janitor-is-one-machine-wide-sweep. Simulators belong to the machine, not to a
repository. Reason: seven booted simulators used about 15 GB on a 24 GB Mac, and no session stops one.
After a boot, nothing tells who booted it.

1. Record. A PostToolUse hook on Bash and on `mcp__Claude_Code_iOS_Simulator__control` records each
   device that the call names and that went from `Shutdown` to `Booted` during the call. A call names a
   device by UDID (`-destination id=`, `simctl boot`, MCP `device` or its alias `udid`). It can also name
   a device by a name that matches a simctl device name (`-destination name=`, MCP `device` or `udid`). A
   call that names none records nothing. The record goes to `state/sim-boots.jsonl`. Each line holds the
   pid and the start time of the device's launchd_sim, read when the device booted. If the table holds no
   launchd_sim for the UDID, or more than one, the hook records nothing for that device. A name that
   matches devices on more than one runtime records none, unless `OS=` in the destination picks exactly
   one runtime. An owner-booted device is never stopped, and an unclear case means keep. A Bash call is
   read only when its text names a simulator tool as a whole word, such as simctl, xcodebuild or xcrun.
   An MCP call is read only when its action is `launch`. Bandaid: a boot behind a script that names no
   such word goes unrecorded, and an unrecorded device is kept. Accepted limit: the owner may boot the
   very device that a session's call names, during that call. The hook then records the device as the
   session's.
2. Stop only recorded devices. When all of these hold for a device, the tier in `janitor/sweep.py` stops it:
   - The device was booted 1 hour or more ago.
   - The boot matches the record. The live launchd_sim has the pid and the start time of the newest
     record line. If it does not, the owner booted the device again by hand. The code is `boot-record-mismatch`.
   - No process outside that device's launchd_sim tree names its UDID, its name or `booted`.
   - Simulator.app and Xcode.app (Xcode-beta.app too) are not running.
   - All reads succeeded.

   Any read that cannot tell means keep. Each device gets one `xcrun simctl shutdown <UDID>`. Never
   `all`. Never erase. A run stops at most 4 devices. The rest wait for the next run.
3. Cap 2. Guard rule `simulator-boot-cap` refuses a session's boot when 2 devices are already booted. It
   names them. A boot is `simctl boot`, an `xcodebuild -destination` with `id=` or `name=`, or MCP
   `launch` with `device` or `udid`. The cap counts every booted device, whoever booted it, owner-booted devices included. RAM
   is the limit. With two owner-booted devices, no session can boot until the owner stops one. The cap
   needs no knowledge of who booted a device.
4. Reuse. Guard rule `simulator-boot-twin` refuses a boot when an idle booted device of the same type
   and runtime exists. It names that device's UDID. "Idle" is the ruling 2 test in full. A device that
   fails any part of it is not idle. The twin rule matches the device type, not the runtime. So
   `OS=latest` with an idle twin on an older runtime is refused.
5. Boot check. The record hook checks each device that a `simctl boot` names, or that an MCP `launch`
   names, when the call took it from `Shutdown` to `Booted`. No other boot path is checked. The check
   passes when `xcrun simctl bootstatus <UDID>` exits 0 and `xcrun simctl io <UDID> screenshot <file>`
   exits 0. A timeout is a fail. On a fail, the hook runs `simctl shutdown <UDID>` and then `simctl boot
   <UDID>` once, then checks again. The boot runs even when the shutdown failed. Reason: a boot can leave
   the device `Booted` with no display, and SpringBoard crashes until a shutdown and boot fixes it.
   - Pass after the retry: the hook tells the session that the device was booted again, and that an app
     launched by the call must be launched again.
   - Fail after the retry: the hook tells the session that the device is broken, names its UDID, and says
     to stop using it. The hook does not shut it down. The sweep stops it once it is idle (ruling 2).

   The hook writes the record line before the check. After a retry it writes one more line with the retry
   boot's launchd_sim pid. The sweep reads the newest line, so it does not see `boot-record-mismatch`, and
   a hook killed during the check still leaves a record. The hook writes to stdout only when the check
   failed.

Kind: process
Home: janitor/sweep.py
