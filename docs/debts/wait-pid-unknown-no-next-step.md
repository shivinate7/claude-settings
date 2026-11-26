# wait-pid's unknown line names no next step

- **What.** On macOS, a session's own job whose program is Apple-signed (`sleep`, `sh`, `env`) hides its environment from other processes. `wait-pid` then prints "environ unknown ... not waited on", exits 3, and names no next step. The guard's waiter remedies name `wait-pid` as the only wait, so the session has no step to take. Claude hits this in normal work on this Mac: `lint/test_wait_pid.py` was red on main here on 2026-11-25.
- **Where.** `bin/wait-pid`, lines 49-50 (the `environ_unknown` line) and line 65 (the call that returns it). Its header, lines 11-12, says the same.
- **Decision.** `stall-watch` (the one allowed wait on a stranded job is `wait-pid`; this debt is that wait's dead end) and `a-kill-by-pid-needs-an-owned-pid` (ownership reads the process environment, which macOS hides for system programs).
- **Retire.** Make the unknown line name the next step, or prove ownership another way, for example with a pid file the session wrote at start. Add a case to `lint/test_wait_pid.py` that takes the hidden-environment path and asserts the one line names that step. It fails on today's code, since the line names none.
