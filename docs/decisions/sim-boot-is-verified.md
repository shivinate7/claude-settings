# A simulator boot is verified

## The ruling

The record hook of `sweep-shuts-down-idle-simulators` (ruling 1) checks each device that an MCP `launch` took from `Shutdown` to `Booted`, and each device that an overridden `simctl boot` took the same way. Unless the owner overrides it, `simulator-boot-bypass` refuses a raw `simctl boot` (see `sim-test-is-the-one-boot-path`). `bin/sim-test` checks its own boot through the hook's `--check <UDID>` mode, which runs the same `sim_ok` once after the record call (owner pick, page item 433 a, 2026-11-08 12:00 CST). On a fail it prints one stderr line, runs no tests or hold child, exits 1 and shuts down only what it booted. It does not retry. A device it reuses is not checked. Any other outcome, a missing hook or `python3` too, passes. It also writes one `sim-boots.jsonl` line through the record mode (`sim-test-is-the-one-boot-path`, ruling 6). No other boot path is checked. The SpringBoard crash symptom is stopped instead by `sim-test-stops-a-crash-loop`, which runs inside sim-test. It shuts down only a simulator that sim-test booted.

The check passes when `xcrun simctl bootstatus <UDID>` exits 0, `xcrun simctl io <UDID> screenshot <file>` exits 0, and the screenshot is not one colour. A timeout is a fail. A frame of one colour (a black or blank display) is a fail, because a screenshot of a dead display still exits 0. A file the check cannot judge (not an 8-bit RGB or RGBA PNG, interlaced, truncated, empty or missing) passes, because a reboot on a file the check cannot read is a false alarm and a reboot loop. On a fail, the hook runs `simctl shutdown <UDID>` and then `simctl boot <UDID>` once, even when the shutdown failed, then checks again. Reason: a boot can leave the device `Booted` with no display, and SpringBoard crashes until a shutdown and boot fixes it.

The frame judge is `frame_uniform` in the hook. It reads the PNG with the standard library only, because the Mac system `python3` has no PIL. It inflates the image data and compares each row, byte for byte, with the one row a uniform frame would hold under that row's PNG filter. The comparison is exact and stops at the first row that differs. A pixel's colour includes its alpha byte, the rule `isBlank` in `bin/shoot` uses: a black frame with transparent corners is not one colour, and passes. Cost: one read of the file, one inflate, and Python work on one row for each of ten row forms; the row comparisons run in C. Measured on a 1206 by 2622 RGBA frame (Linux, Python 3, best of 3): 0.02 s for a uniform frame, 0.02 s for a live frame. Limit: the judge tests for exactly one colour. A near-uniform frame, such as black with dithered noise, passes.

Two homes judge a one-colour PNG: `isBlank` in `bin/shoot` (Node) and `frame_uniform` (Python). Reason: the hook runs as Python on every checked boot, and a Node start per boot would add a process and a dependency. Both apply the same rule: 8-bit RGB or RGBA, non-interlaced, every pixel equal, alpha included.

- Pass after the retry: the hook tells the session that the device was booted again, and that an app launched by the call must be launched again.
- Fail after the retry: the hook tells the session that the device is broken, names its UDID, and says to stop using it. The hook does not shut it down. The sweep stops it once it is idle (`sweep-shuts-down-idle-simulators`, ruling 2).

The hook writes the record line before the check, and one more line after a retry with the retry boot's launchd_sim pid, so the sweep sees no `boot-record-mismatch`. The hook writes to stdout only when the check failed.

Kind: process
Home: hooks/sim_boot_record.py
