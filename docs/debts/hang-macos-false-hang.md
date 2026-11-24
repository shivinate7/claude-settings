# A healthy macOS step can read as a HANG

**What.** On macOS the hang check cannot read a reaped child's CPU. A step whose child burned CPU and exited, with the parent now asleep, shows no CPU advance and no new pid, so the check stops the tree as a HANG. The five CI steps that set `VERDICT_HANG_SECONDS` include macOS steps (the shell-macos install suite and the checks-macos guard fixture slice), so a working step can go red. Unmeasured: no run has been read for a false macOS HANG.

**Where.** `bin/verdict` lines 169-177 (the macOS branch of the hang check).

**Decision.** `hang-stop` (the hang detector and its macOS limit).

**Retire.** None yet. Close when counted macOS HANG lines in CI runs with the switch set show none false, or when the macOS branch reads reaped CPU.

Fix: none built; the time it takes to fix is not sized yet.
