# A simulator boot is verified

## The ruling

The record hook of `sweep-shuts-down-idle-simulators` (ruling 1) checks each device that an MCP `launch` took from `Shutdown` to `Booted`, and each device that an overridden `simctl boot` took the same way. Unless the owner overrides it, `simulator-boot-bypass` refuses a raw `simctl boot` (see `sim-test-is-the-one-boot-path`). A boot by `bin/sim-test` is not checked, and it writes no `sim-boots.jsonl` line. No other boot path is checked. The SpringBoard crash symptom is stopped instead by `sim-test-stops-a-crash-loop`, which runs inside sim-test. It shuts down only a simulator that sim-test booted.

The check passes when `xcrun simctl bootstatus <UDID>` exits 0 and `xcrun simctl io <UDID> screenshot <file>` exits 0. A timeout is a fail. On a fail, the hook runs `simctl shutdown <UDID>` and then `simctl boot <UDID>` once, even when the shutdown failed, then checks again. Reason: a boot can leave the device `Booted` with no display, and SpringBoard crashes until a shutdown and boot fixes it.

- Pass after the retry: the hook tells the session that the device was booted again, and that an app launched by the call must be launched again.
- Fail after the retry: the hook tells the session that the device is broken, names its UDID, and says to stop using it. The hook does not shut it down. The sweep stops it once it is idle (`sweep-shuts-down-idle-simulators`, ruling 2).

The hook writes the record line before the check, and one more line after a retry with the retry boot's launchd_sim pid, so the sweep sees no `boot-record-mismatch`. The hook writes to stdout only when the check failed.

Kind: process
Home: hooks/sim_boot_record.py
