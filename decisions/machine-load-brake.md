# The machine-load brake

## The ruling

Owner, 2026-10-21 (spec), 2026-10-22 (CPU and foreground) and 2026-10-23 (disk): a lane-start call reads the machine's load, and a busy or full machine refuses new lanes (disk is the smaller of a share and a GB cap, CPU comes from ticks). The brake lives in `hooks/guard.py` (`read_load`, `load_hit`, rule `load-brake`), on every device.

- **Readings.** `read_load()` reads memory in use as a share of the machine's memory, and free GB and total GB of the home drive (2**30 bytes to the GB, never clamped). CPU, from ticks, is a second signal.
- **Busy.** Memory over 85%, disk free under the smaller of 10% of the disk and 15 GB, or CPU over 85% with memory over 75%. A 926 GB disk: busy under 15 GB. A 100 GB disk: busy under 10 GB. CPU alone is never busy: a 200 ms CPU sample is a spike, not load. Any Workflow is refused. An Agent or Task call passes only when it leaves `run_in_background` out or sets it to exactly false. Any other present value (true, "true", null, 1) is refused. In the desktop app a left-out call still runs in the background and the field is not offered, so busy no longer slows Agent lanes there. Only full does.
- **Full.** Memory over 95%, or disk free under the smaller of 5% and 5 GB. Every lane call is refused. CPU never makes the machine full.
- **Not covered at busy.** `start_session` has no foreground form, and the rulings name only Agent, Task and Workflow. It is refused at full only.
- **The refusal** names each reading that tripped it. When CPU and memory trip busy together, it names both. At busy, an Agent or Task call is told to wait for the load to drop (memory, CPU) or free disk space (disk). It is also told to start the lane as an Agent call that leaves `run_in_background` out or sets it false. A Workflow has no foreground form, so it gets only the wait or free-disk remedy.
- **A read error counts as normal.** On Linux memory is unread, so CPU never makes busy there. An unread reading hides no other.
- **Which calls read.** Agent, Task, Workflow and `start_session`, once each. No other tool reads load.
- **How it reads.** Windows: `GlobalMemoryStatusEx`, and `GetSystemTimes` twice, 200 ms apart, through ctypes. Mac: `kern.memorystatus_level`, and Mach `host_statistics` CPU ticks twice, through ctypes. Linux: `/proc/stat` twice, memory unread. Disk everywhere: `shutil.disk_usage`. Never the load average (107 on 15 cores while `top` showed half idle). No platform starts a child process.
- **An owner override pass lifts a refusal.** The brake is not in the never-passed list (`owner-override-pass`).

Why: many lanes at once can exhaust memory or disk and stall every session.

Risk kind: likely, per `building-guard-needs-incident`. A session that fans out lanes is likely to hit it in normal work. No incident and no measurement of a stalled machine is recorded, and the memory and CPU levels are placeholders for the owner to tune. Landed 2026-10-22.

Cost, per `outcomes-mechanize-rules`: process starts, none. Files written, none on an allowed call; a refusal adds one line to `guard.log`, which `lint/guard_log_report.py` reads. How often: once per lane-start call. Each read waits 200 ms. No timer, no watcher, no read on any other call. `hooks/test_guard.py` (family `load-brake`) pins the zero children, zero files and one read per lane call. `hooks/test_guard_load_os.py` checks each reading against the OS's own tool on the Windows and Mac runners (the Mac CPU against `top -l 2`).

Kind: build
Plan: decisions/machine-load-brake.md#the-ruling (windows)
Plan: decisions/machine-load-brake.md#the-ruling (macos)
Plan: decisions/machine-load-brake.md#the-ruling (linux)
