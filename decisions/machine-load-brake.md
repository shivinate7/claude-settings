# The machine-load brake

## The ruling

Owner, 2026-10-21 (spec) and 2026-10-22 (rulings; CPU and foreground at 15:00 CDT): a lane-start call reads the machine's load, and a busy or full machine refuses new lanes. The brake lives in `hooks/guard.py` (`read_load`, `load_hit`, rule `load-brake`). It applies on every device that installs claude-settings.

- **Readings.** `read_load()` reads memory in use and free disk on the home drive, each as a share of this machine's capacity. CPU is a second signal. It counts no claude process and no running lane.
- **Busy.** Memory over 85%, disk free under 15%, or CPU over 85% with memory over 75%. CPU alone is never busy: a 200 ms CPU sample is a spike, not load. Any Workflow is refused. An Agent or Task call passes only when it leaves `run_in_background` out or sets it to exactly false. Any other present value (true, "true", null, 1) is refused. In the desktop app a left-out call still runs in the background and the field is not offered, so busy no longer slows Agent lanes there. Only full does. The owner chose this on 2026-10-22: a CPU or memory spike must not stall a session that cannot choose a foreground form.
- **Full.** Memory over 95%, or disk free under 5%. Every lane call is refused. CPU never makes the machine full.
- **Not covered at busy.** `start_session` has no foreground form, and the rulings name only Agent, Task and Workflow. It is refused at full only.
- **The refusal** names each reading that tripped it. When CPU and memory trip busy together, it names both. At busy, an Agent or Task call is told to wait for the load to drop (memory, CPU) or free disk space (disk). It is also told to start the lane as an Agent call that leaves `run_in_background` out or sets it false. A Workflow has no foreground form, so it gets only the wait or free-disk remedy.
- **A read error counts as normal.** On Linux memory is unread, so CPU never makes busy there. A reading that fails or cannot be read is unread, and one unread reading hides no other.
- **Which calls read.** Agent, Task, Workflow and `start_session`, once each. Bash, PowerShell, Edit, Write and every other tool read no load.
- **How it reads.** Windows: `GlobalMemoryStatusEx`, and `GetSystemTimes` twice, 200 ms apart, through ctypes. Mac: `kern.memorystatus_level` through ctypes, and the 1-minute load average per core. Disk on both: `shutil.disk_usage`. Linux reads disk and CPU (load average per core) and leaves memory unread. No platform starts a child process.
- **An owner override pass lifts a refusal.** The brake is not in the never-passed list (`owner-override-pass`).

Why: many lanes at once can exhaust memory or disk, and the machine then stalls every session on it.

Risk kind: likely, per `building-guard-needs-incident`. A session that fans out lanes is likely to hit it in normal work. No incident and no measurement of a stalled machine is recorded, and the 85, 95, 15 and 5 levels are placeholders for the owner to tune. Landed 2026-10-22.

Cost, per `outcomes-mechanize-rules`: process starts, none. Files written, none on an allowed call; a refusal adds one line to `guard.log`, which `lint/guard_log_report.py` reads. How often: once per lane-start call. A Windows read waits 200 ms for its CPU sample. No timer, no watcher, no read on any other call. `hooks/test_guard.py` (family `load-brake`) pins the zero children, zero files and one read per lane call. `hooks/test_guard_load_os.py` checks each reading against the OS's own tool on the Windows and Mac runners.

Kind: build
Plan: decisions/machine-load-brake.md#the-ruling (windows)
Plan: decisions/machine-load-brake.md#the-ruling (macos)
Plan: decisions/machine-load-brake.md#the-ruling (linux)
