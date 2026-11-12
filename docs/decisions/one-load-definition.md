# One definition of a loaded machine

## The ruling

Owner, 2026-11-06 15:24 CST (waiting-page item 304, option a, plan `align-watchers` Q6; attested by the coordinator's step record for step `one-load-definition`, not by a decision file): the guard and `sim-lease`
share one definition of "the machine is loaded".

- **The home.** `hooks/guard_load.py`. It holds the readings (`read_load`), the verdict (`load_verdict`) and the
  limits, as named constants. The guard (`hooks/guard.py`) and `bin/sim-lease` call it. Neither keeps a reading or a
  limit of its own.
- **Readings.** Memory in use, as a share of the machine's memory. Free GB and total GB of the drive that holds
  the home folder (2**30 bytes to the GB). No CPU and no load average: decision `machine-load-brake` measured a
  load of 107 on 15 cores while `top` showed half the machine idle.
- **Levels.** Full: memory over 95%, or disk free under the smaller of 5% of the disk and 5 GB. Busy: memory over
  85%, or disk free under the smaller of 10% of the disk and 15 GB. Else normal.
- **Unread.** A reading that fails or that the platform does not offer is unread. The verdict names it in
  `unread`, and one unread reading hides no other. The level is computed from the readings that were read. Each
  caller states what an unread reading does to its act.
- **Each platform.** Windows: memory from `GlobalMemoryStatusEx` (ctypes), disk from `shutil.disk_usage`. Mac:
  memory from `kern.memorystatus_level` (ctypes), disk the same. Linux: memory unread, disk the same. No platform
  starts a child process.

## What each caller does with the verdict

- **The guard** (decision `machine-load-brake`): busy refuses a background lane or agent start. Full refuses
  every start and stops a running agent or lane session at its next shell or file write. An unread reading
  counts as normal, since Linux memory is always unread and the brake must not refuse every Linux start.
- **`sim-lease`** (decision `sim-lease-tool`): a grant needs a machine that is not full. Slot 2 needs a normal
  machine. An unread reading holds the grant, and `take` and `status` print it as unknown. That hold is this step's
  reading, awaiting owner confirmation, and no step-record entry holds it. Applying the "a check that cannot read its input fails" ruling (item 276 a, which on main is only
  the page-check ruling in decision `page-check-at-export`) to `sim-lease` is this lane's reading, awaiting owner confirmation. "Slot 2 needs a normal machine" is this lane's mapping too. The queue order
  and the 18 Pro's slot rules are not load rules.
- **Changed by this step.** The shared definition reads memory and disk only, and `sim-lease` drops its load-average bars (item 309 a, owner 2026-11-06 15:45 CST). So a Mac with a high load average but free
  memory and disk grants a boot. The guard's verdicts are unchanged.

Why: one capability has one home (`building-one-home-per-capability`), so the two readers can never disagree.

Cost, per `outcomes-mechanize-rules`: the read runs on demand inside the process already running, the guard hook
or `sim-lease`. Process starts: none. Files written: none. How often: for the guard, as decision
`machine-load-brake` states; for `sim-lease`, once per take poll and per status. No timer, no watcher.

Test: `hooks/test_guard.py` (family `load-brake`) and `lint/test_sim_lease.py` judge the same readings through
`load_verdict`, and show both callers act on the same level. `hooks/test_guard_load_os.py` checks each reading
against the OS's own tool on the Windows and Mac runners.

Kind: build
Plan: docs/decisions/one-load-definition.md#the-ruling (windows)
Plan: docs/decisions/one-load-definition.md#the-ruling (macos)
Plan: docs/decisions/one-load-definition.md#the-ruling (linux)
