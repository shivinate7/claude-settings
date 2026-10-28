# The machine-load brake

## The ruling

Owner, 2026-10-21 (spec), 2026-10-22 (foreground), 2026-10-23 (disk) and 2026-10-25 (CPU dropped: a 200 ms sample is noise; memory and disk are what stall a machine): a lane-start call reads the machine's load, and a busy or full machine refuses new lanes (disk is the smaller of a share and a GB cap). Owner, 2026-10-26 (incident) and 2026-10-27 11:45 CDT (option a): a running lane stops at full only, never at busy. The brake lives in `hooks/guard.py` (`read_load`, `load_hit`, rule `load-brake`), on every device.

- **Readings.** `read_load()` reads memory in use as a share of the machine's memory, and free GB and total GB of the home drive (2**30 bytes to the GB, never clamped). It reads no CPU, and counts no claude process and no running lane.
- **Busy.** Memory over 85%, or disk free under the smaller of 10% of the disk and 15 GB. A 926 GB disk: busy under 15 GB. A 100 GB disk: busy under 10 GB. Any Workflow is refused. An Agent or Task call passes only when it leaves `run_in_background` out or sets it to exactly false. Any other present value (true, "true", null, 1) is refused. In the desktop app a left-out call still runs in the background and the field is not offered, so busy no longer slows Agent lanes there. Only full does. The owner chose this on 2026-10-22: a memory spike must not stall a session that cannot choose a foreground form.
- **Full.** Memory over 95%, or disk free under the smaller of 5% and 5 GB. Every lane call is refused.
- **Not covered at busy.** `start_session` has no foreground form, and the rulings name only Agent, Task and Workflow. It is refused at full only.
- **The refusal** names each reading that tripped it. At busy, an Agent or Task call is told to wait for the load to drop (memory) or free disk space (disk). It is also told to start the lane as an Agent call that leaves `run_in_background` out or sets it false. A Workflow has no foreground form, so it gets only the wait or free-disk remedy.
- **A read error counts as normal.** On Linux memory is unread, so only disk can trip the brake there. A reading that fails or cannot be read is unread, and one unread reading hides no other.
- **Running lanes.** An agent's own Bash, PowerShell, Edit, Write, MultiEdit or NotebookEdit call reads the load once (`running_lane_hit`, `RUNNING_LANE_TOOLS`). Full refuses it and tells the lane to stop and report. Busy lets it run. The hook already runs for each such call, so the brake does not depend on the orchestrator's turn: a lane stops even while its orchestrator waits on the owner. A call is an agent's when its payload carries a valid `agent_id`.
- **Not covered for running lanes.** A lane started by `start_session` or Remote Control is its own session, with no `agent_id`, so it is braked only at its start. A command already running (a long build) keeps writing; only its next call is refused. An MCP tool that writes files (such as a GitHub file push) is not read. At full a lane cannot commit its last pass either, so that pass stays uncommitted in its worktree until the orchestrator frees space.
- **Full only.** A running lane is refused only at a full machine: memory over 95%, or disk free under the smaller of 5% of the disk and 5 GB. A busy machine never stops it.
- **Rule exception.** Rule `outcomes-mechanize-rules` lets an agent's own write read the machine load once, inside the guard hook already running for it. Its cost is one memory read and one `statfs` per agent write. It starts no process, writes no file and sets no timer. The rule's sentence cites this decision.
- **The orchestrator is never braked on its own shell or writes.** It is the session that frees the disk, so a recovery does not depend on the full disk it recovers (`verification-recovery-independent-of-state`).
- **Which calls read.** Agent, Task, Workflow and `start_session`, once each, and an agent's shell or file write, once each. No other tool reads load.
- **How it reads.** Windows: `GlobalMemoryStatusEx`, through ctypes. Mac: `kern.memorystatus_level`, through ctypes. Linux: memory unread. Disk everywhere: `shutil.disk_usage`. Never the load average (107 on 15 cores while `top` showed half idle). No platform starts a child process.
- **An owner override lifts a refusal.** The brake is not in the never-lifted list (`owner-override`).

Why: many lanes at once can exhaust memory or disk and stall every session.

Risk kind: lane starts, likely, landed 2026-10-22; running lanes, incident, landed with this change. The incident (owner, 2026-10-26): a session waited on the owner's answer while its background lanes kept writing. The brake read only on lane starts, so nothing refused them, the Mac's disk filled and the lanes crashed. The memory level is a placeholder for the owner to tune.

Cost, per `outcomes-mechanize-rules`: process starts, none. Files written, none on an allowed call; a refusal adds one line to `guard.log`, which `lint/guard_log_report.py` reads. How often: once per lane-start call, and once per agent shell or file write. Each read is one memory counter and one `statfs`, inside the hook process that already runs. No read waits, on any platform. No timer, no watcher, no read on any other call, and none on the orchestrator's own shell or writes. `hooks/test_guard.py` (family `load-brake`) pins the zero children, zero files, one read per lane call and one per agent write. `hooks/test_guard_load_os.py` checks each reading against the OS's own tool on the Windows and Mac runners.

Kind: build
Plan: docs/decisions/machine-load-brake.md#the-ruling (windows)
Plan: docs/decisions/machine-load-brake.md#the-ruling (macos)
Plan: docs/decisions/machine-load-brake.md#the-ruling (linux)
