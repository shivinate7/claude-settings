# The SessionEnd sweep is armed, because Windows liveness is proven

## The ruling

The `SessionEnd` hook in `settings.json` runs `janitor/session_end_sweep.py`. That script runs `janitor/sweep.py --confirm` on the
repository of the session that ends. The hook is armed on every platform. The file name of this entry keeps the word "disarmed", because
other files cite it by that name.

`hooks/session_start.sh` prints a notice at the top of each session when the `SessionEnd` hook is absent from `settings.json`. The notice
names this entry. A config that cannot be read is reported as unknown, never as armed or disarmed.

Reason: the sweep may run only where the liveness read is proven. The read answers alive, dead, or unreadable. Unreadable reaches the
caller as `None`, and every caller keeps or refuses on `None`. A Windows job in `.github/workflows/gates.yml` runs the guard and sweep
suites and their mutation harnesses.

Kind: process
Home: janitor/session_end_sweep.py
