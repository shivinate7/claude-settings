# Sessions boot simulators. The sweep stops idle ones.

Owner rulings, 2026-10-10. This record extends unattended-sweep-stops-proven-orphans,
where an unattended run sends one signal to one proven orphan process. It adds a new act:
a per-device shutdown with `xcrun simctl shutdown <UDID>`. The act is not a signal. The
tier lives in `janitor/sweep.py`, the one machine-wide sweep of
the-janitor-is-one-machine-wide-sweep. Simulators belong to the machine, not to a
repository.

## Incident

Measured 2026-10-10. Seven iOS simulators were booted at once on a 24 GB Mac. They used
about 15 GB, about 2 GB each.

## Incident, 2026-10-14

At 14:18 CDT a session ran `simctl boot` on an iPhone 18 Pro. CoreSimulator.log shows
that SimRenderingServices refused the boot ("Invalid connectionUUID"). The device still
came up `Booted`, with no display. SpringBoard crashed 14 times, with no main display,
until the session ran shutdown and boot at 14:20:11. That fixed it. One device was
booted, so the cap did not fire. Memory was not the cause. Why the render service
refused the boot is unmeasured. Ruling 5 rests on this incident.

## Why nothing reaps them today

Three paths boot a simulator: xcodebuild auto-boot, `simctl boot`, and the iOS Simulator
MCP panel. No session stops one. After a boot, nothing tells who booted it. The
launchd_sim process has ppid 1. CoreSimulator.log has no requester.

## Rulings

1. Record. A PostToolUse hook on Bash and on `mcp__Claude_Code_iOS_Simulator__control`
   records each device that the call names and that went from `Shutdown` to `Booted`
   during the call. A call names a device by UDID (`-destination id=`, `simctl boot`, MCP
   `device` or its alias `udid`). It can also name a device by a name that matches a simctl
   device name (`-destination name=`, MCP `device` or `udid`). A call that names none records nothing. The
   record goes to `state/sim-boots.jsonl`. Each line holds the pid and the start time of
   the device's launchd_sim, read when the device booted. If the table holds no
   launchd_sim for the UDID, or more than one, the hook records nothing for that device.
   A name that matches devices on more than one runtime records none, unless `OS=` in the
   destination picks exactly one runtime. Owner ruling: an owner-booted device is never
   stopped, and an unclear case means keep.
   Accepted limit, owner ruling 2026-10-10: the owner may boot the very device that a
   session's call names, during that call. The hook then records the device as the
   session's.
2. Stop only recorded devices. When all four of these hold for a device, the new tier in
   `janitor/sweep.py` stops it:
   - The device was booted 1 hour or more ago.
   - The boot matches the record. The live launchd_sim has the pid and the start time of
     the newest record line. If it does not, the owner booted the device again by hand.
     The code is `boot-record-mismatch`.
   - No process outside that device's launchd_sim tree names its UDID, its name or
     `booted`.
   - Simulator.app and Xcode.app (Xcode-beta.app too) are not running.
   - All reads succeeded.

   Any read that cannot tell means keep. Each device gets one `xcrun simctl shutdown
   <UDID>`. Never `all`. Never erase. A device the owner booted is never stopped.
3. Cap 2. A guard rule refuses a session's boot when 2 devices are already booted. It
   names them. The cap counts every booted device, whoever booted it, owner-booted
   devices included. Owner answer, 2026-10-10: RAM is the limit. With two owner-booted
   devices, no session can boot until the owner stops one.
4. Reuse. A guard rule refuses a boot when an idle booted device of the same type and
   runtime exists. It names that device's UDID. Owner answer, 2026-10-10: "idle" is the
   rule 2 test in full. A device that fails any part of it is not idle.
5. Boot check. Owner ruling, 2026-10-14: "add boot check", over "note only". The record
   hook checks each device that a `simctl boot` names, or that an MCP `launch` names, when
   the call took it from `Shutdown` to `Booted`. The check passes when `xcrun simctl bootstatus
   <UDID>` exits 0 and `xcrun simctl io <UDID> screenshot <file>` exits 0. A timeout is a
   fail. On a fail, the hook runs `simctl shutdown <UDID>` and then `simctl boot <UDID>`
   once, then checks again. The boot runs even when the shutdown failed.
   - Pass after the retry: the hook tells the session that the device was booted again,
     and that an app launched by the call must be launched again.
   - Fail after the retry: the hook tells the session that the device is broken, names
     its UDID, and says to stop using it. The hook does not shut it down. The sweep stops
     it once it is idle (ruling 2).
   The hook writes the record line before the check. After a retry it writes one more
   line with the retry boot's launchd_sim pid. The sweep reads the newest line, so it does
   not see `boot-record-mismatch`, and a hook killed during the check still leaves a
   record.

Why the cap: it needs no knowledge of who booted a device.

Kind: build
Plan: decisions/sweep-shuts-down-idle-simulators.md#mechanism-built (macos)

## Sources

- The measured incident above. Rules 3 and 4 rest on it and on the owner's rulings.
- CircleCI support article 15090412, "Reducing iOS Simulator CPU Overhead on macOS
  Executors". The article covers boot cost. It caches warm data, then overlays that data
  on a fresh simulator before boot. It does not say to reuse a booted device. Cite it for
  boot cost only. Checked on 2026-10-10 through a summarizing fetch, not the full page.

## Mechanism, built

- `janitor/sweep.py`: `sim_tier`, the last tier of a full run. `sim_keep_code` is the one
  idle test. A run stops at most 4 devices. The rest wait for the next run.
- `hooks/sim_boot_record.py`: a PreToolUse run saves each device's state. The PostToolUse
  run of the same call records each `Shutdown` to `Booted` change. For a `simctl boot` or
  an MCP `launch`, it first runs the ruling 5 check on each such device. The hook writes to
  stdout only when the check failed: a `decision: "block"` reason when the device is
  broken, an `additionalContext` note when the retry passed. Otherwise stdout stays empty.
  Each step has its own timeout: bootstatus 90 s, screenshot 15 s, shutdown 30 s, boot
  60 s. For one device the worst case is 480 s: the list read 60 s, two launchd_sim reads
  of 60 s each, one check, one retry and a second check. The PostToolUse entry in
  `settings.json` allows 600 s. A call that boots two or more devices, such as
  `simctl boot A && simctl boot B` or an MCP `launch` whose `device` and `udid` differ,
  can pass 600 s. The hook is then killed after the record lines are written, and
  the session gets no message. A Bash call is read only
  when its text names a simulator tool as a whole word, such as simctl, xcodebuild or xcrun.
  An MCP call is read only when its action is `launch`. Bandaid: a boot behind a script
  that names no such word goes unrecorded, and an unrecorded device is kept. Matchers for
  Bash and the simulator MCP tool are in `settings.json`, Pre and Post.
- `hooks/guard.py`: rules `simulator-boot-cap` and `simulator-boot-twin`. A boot is
  `simctl boot`, an `xcodebuild -destination` with `id=` or `name=`, or MCP `launch` with
  `device` or `udid`. The guard judges each of the two that is a non-empty string. A UDID
  matches in any case. A name must match exactly. A numeric `OS=` in a `name=` destination
  keeps only the copies on that runtime. When it keeps none, all copies count. An `id=`
  destination, `OS=latest` or no OS uses no filter. Only the shut-down devices a call names
  count as a boot, and the twin rule judges each of them.
  `simctl list` runs for each call that names a device. A launch with neither field is not
  judged. The guard imports `sweep` on a match only.
  Named limits: a shut-down device whose name is the target's UDID string is denied at the
  cap. A name can match a booted copy and a shut-down copy on two runtimes. With no
  numeric OS, the call counts as a boot of the shut-down copy. The MCP takes no OS, so this
  holds for it too. `OS=latest` with an idle twin on an older runtime is refused: the twin rule matches
  the device type, not the runtime. The record hook records nothing for `OS=latest` on such
  a name, so the sweep keeps that device.
  Ruling 5 checks only `simctl boot` and MCP `launch`. An `xcodebuild -destination` boot
  is not checked. Nor is a boot by `simctl bootstatus -b`, or a `simctl boot` with a flag
  before the device. A broken device is left booted until the sweep stops it. When no
  single launchd_sim is readable after the retry, no second line goes in, and the newest
  line keeps the old pid. The device is then most likely shut down, so the sweep does not
  judge it.

## Measured, 2026-10-10

- `xcrun simctl list devices --json`: 0.19 to 0.48 s in 3 runs. This is why the record hook
  skips Bash calls that name no simulator tool.
- On a device already booted, 2026-10-14: `simctl bootstatus` 0.10 to 0.14 s, `simctl io
  screenshot` 0.38 to 0.47 s, 3 runs. Bootstatus right after a fresh boot is unmeasured.
  The ruling 5 timeouts are sized by judgment, not by measure.
- One `simctl shutdown`: unmeasured. The only booted device was in use by a running
  `xcodebuild test`, so no shutdown ran.
- On this Mac, `launchd_sim` argv holds the UDID, and an Xcode-bundled `python3` has
  `Xcode.app` in its path. The Xcode test matches only the `Xcode*.app/Contents/MacOS/Xcode`
  executable, so that python does not count as Xcode running.
