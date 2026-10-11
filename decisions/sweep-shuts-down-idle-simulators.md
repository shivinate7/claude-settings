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

Why the cap: it needs no knowledge of who booted a device.

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
  run of the same call records each `Shutdown` to `Booted` change. A Bash call is read only
  when its text names a simulator tool as a whole word, such as simctl, xcodebuild or xcrun.
  An MCP call is read only when its action is `launch`. Bandaid: a boot behind a script
  that names no such word goes unrecorded, and an unrecorded device is kept. Matchers for
  Bash and the simulator MCP tool are in `settings.json`, Pre and Post.
- `hooks/guard.py`: rules `simulator-boot-cap` and `simulator-boot-twin`. A boot is
  `simctl boot`, an `xcodebuild -destination` with `id=` or `name=`, or MCP `launch` with
  `device` or `udid`. The guard judges each of the two that is a non-empty string. A UDID
  matches in any case. A name must match exactly. `simctl list` runs only after a call
  matched as a boot of a shut-down device. A launch with neither field is not judged. The guard imports `sweep` on a match only.

## Measured, 2026-10-10

- `xcrun simctl list devices --json`: 0.19 to 0.48 s in 3 runs. This is why the record hook
  skips Bash calls that name no simulator tool.
- One `simctl shutdown`: unmeasured. The only booted device was in use by a running
  `xcodebuild test`, so no shutdown ran.
- On this Mac, `launchd_sim` argv holds the UDID, and an Xcode-bundled `python3` has
  `Xcode.app` in its path. The Xcode test matches only the `Xcode*.app/Contents/MacOS/Xcode`
  executable, so that python does not count as Xcode running.
