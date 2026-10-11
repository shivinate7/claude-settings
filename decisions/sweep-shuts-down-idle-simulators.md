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
   records each device that went from `Shutdown` to `Booted` during a session call. The
   record goes to `state/sim-boots.jsonl`.
2. Stop only recorded devices. When all four of these hold for a device, the new tier in
   `janitor/sweep.py` stops it:
   - The device was booted 1 hour or more ago.
   - No process outside that device's launchd_sim tree names its UDID, its name or
     `booted`.
   - Simulator.app and Xcode.app are not running.
   - Both reads succeeded.

   Any read that cannot tell means keep. Each device gets one `xcrun simctl shutdown
   <UDID>`. Never `all`. Never erase. A device the owner booted is never stopped.
3. Cap 2. A guard rule refuses a session's boot when 2 devices are already booted. It
   names them. The cap counts every booted device, whoever booted it.
4. Reuse. A guard rule refuses a boot when an idle booted device of the same type and
   runtime exists. It names that device's UDID.

Why the cap: it needs no knowledge of who booted a device.

## Sources

- The measured incident above. Rules 3 and 4 rest on it and on the owner's rulings.
- CircleCI support article 15090412, "Reducing iOS Simulator CPU Overhead on macOS
  Executors". The article covers boot cost. It caches warm data, then overlays that data
  on a fresh simulator before boot. It does not say to reuse a booted device. Cite it for
  boot cost only. Checked on 2026-10-10 through a summarizing fetch, not the full page.

## Open questions

- "Idle" in rule 4 has no definition. Option A: the rule 2 test. Option B: any booted
  device that no session holds. Recommendation: A. Under B, a device that a live session
  uses could be named for reuse.
- Rule 3 counts the owner's devices, and the sweep never stops those. With two
  owner-booted devices, no session can boot until the owner stops one. The owner chose
  this. It is recorded so the outcome is visible.

## Unmeasured

- A PostToolUse hook sees the state after a call. Knowing that a device went from
  `Shutdown` to `Booted` needs a read from before the call. The method is not chosen.
- Rules 3 and 4 are guard rules, so they run before a call. xcodebuild auto-boots only
  while it runs. Which calls the guard can see as a boot is not measured.

## Mechanism

Not built. The builder owns these files:

- `janitor/sweep.py`: the tier in rule 2.
- `hooks/guard.py`: rules 3 and 4.
- The new PostToolUse hook for rule 1, and its matcher in `settings.json`. The current
  matcher is `Bash|PowerShell|Write|Edit|MultiEdit|NotebookEdit`. It lacks
  `mcp__Claude_Code_iOS_Simulator__control`. The builder adds it.

Each guard rule goes red on the defect it guards before it is trusted.
