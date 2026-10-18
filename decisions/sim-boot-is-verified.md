# A simulator boot is verified

## The ruling

The record hook of `sweep-shuts-down-idle-simulators` (ruling 1) checks each device that a `simctl boot` or an MCP `launch` took from `Shutdown` to `Booted`. No other boot path is checked.

The check passes when `xcrun simctl bootstatus <UDID>` exits 0 and `xcrun simctl io <UDID> screenshot <file>` exits 0. A timeout is a fail. On a fail, the hook runs `simctl shutdown <UDID>` and then `simctl boot <UDID>` once, even when the shutdown failed, then checks again. Reason: a boot can leave the device `Booted` with no display, and SpringBoard crashes until a shutdown and boot fixes it.

- Pass after the retry: the hook tells the session that the device was booted again, and that an app launched by the call must be launched again.
- Fail after the retry: the hook tells the session that the device is broken, names its UDID, and says to stop using it. The hook does not shut it down. The sweep stops it once it is idle (`sweep-shuts-down-idle-simulators`, ruling 2).

The hook writes the record line before the check, and one more line after a retry with the retry boot's launchd_sim pid, so the sweep sees no `boot-record-mismatch`. The hook writes to stdout only when the check failed.

Kind: process
Home: hooks/sim_boot_record.py
