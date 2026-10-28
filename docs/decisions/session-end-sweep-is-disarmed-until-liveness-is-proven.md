# The SessionEnd sweep is armed, because Windows liveness is proven

## The ruling

The `SessionEnd` hook in `settings.json` runs `janitor/session_end_sweep.py`. That script runs `janitor/sweep.py --confirm` on the
repository of the session that ends. The hook is armed on every platform. The file name of this record keeps the word "disarmed", because
other files cite it by that name.

`GUARD_GIT_CALL_TIMEOUT_SECONDS` in `janitor/session_end_sweep.py` is a hand-typed constant, and the module imports no `inspect` (owner ask, undated). A test pins the constant to the timeout in `guard._git`.

`hooks/session_start.sh` prints a notice at the top of each session when the `SessionEnd` hook is absent from `settings.json`. The notice
names this record. A config that cannot be read is reported as unknown, never as armed or disarmed.

Reason: the sweep may run only where the liveness read is proven. The read answers alive, dead, or unreadable. Unreadable reaches the
caller as `None`, and every caller keeps or refuses on `None`. A Windows job in `.github/workflows/checks.yml` runs the guard and sweep
suites and their mutation tests.

Kind: process
Home: janitor/session_end_sweep.py
