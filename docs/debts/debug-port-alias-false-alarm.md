# Debug-port aliases raise a false alarm

- **What.** Guard rule `debug-port-ask` skips a text command only when its program is in `DEBUG_PORT_TEXT_COMMANDS`. The PowerShell aliases `?`, `%`, `ForEach-Object`, `sls` and `gc` are missing. So a read-only search asks, or is refused as a chained ask, where main lets it through. For example, `Get-Process | ? { $_.CommandLine -match "--remote-debugging-port=9222" }` asks. Claude is likely to write this while it debugs a Windows desktop app.
- **Where.** `DEBUG_PORT_TEXT_COMMANDS` and `debug_port_segment_hit` in `hooks/guard.py`.
- **Decision.** `design-skills` (the design-skills record, its debug-port-ask bullet), and `guard-that-cries-wolf-is-spent` (a guard that goes red when nothing is wrong is spent).
- **Retire.** Add the five aliases to the set, in lower case as `debug_port_name` returns them. A test of each alias form goes green as allow, and a launch with the flag still asks.
