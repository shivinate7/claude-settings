# Unattended sweep stops proven orphans

## The ruling

**What an unattended run can stop.** A `--confirm` run, run by the SessionEnd hook or the scheduled task, can send one signal to one process. All of these must be true first:

- The process is orphaned. The read is per-OS and answers three states: orphaned, not orphaned, or unreadable.
- No live Claude session has a cwd in the same checkout. `guard.worktree_live_session` is the oracle. This sweep never re-derives that answer.
- The process is owned by the account running the sweep.

The signal is SIGTERM on Linux and macOS, and `TerminateProcess` on Windows. Both go by pid, never by a name or a pattern. The sweep never sends a second, stronger signal on its own.

**No arm flag, every checkout.** Owner, 2026-09-24: both unattended paths may stop a proven orphan with no separate arm flag, in every checkout. A primary checkout gets no exemption. The three reads above are the whole gate. Reason: a stopped process cannot come back, but a reaped branch keeps a tombstone and a kept worktree stays whole.

**A process this sweep cannot read is out of scope.** It is counted. It is never acted on, and never a reason to keep something else. A single process whose cwd cannot be read never blocks a worktree removal. Only the WHOLE pid enumeration failing means keep-everything. Reason: on a real machine many processes belong to another account, so keeping on any one of them would refuse to reap anything. Measured on a Windows machine: 272 of 580 running processes answered None to the cwd read.

**Dead-rooted servers follow the same gate.** `find_dead_rooted` finds a process whose argv names a script file and whose parent directory are both gone, under a deleted checkout or worktree. It stops that process only on two reads: orphaned, and owned by the account running the sweep. It has no session read, because a deleted tree has no checkout left to hold a session. The one signal, the grace period, and the keep on an unreadable answer are the same.

**Loose processes are never stopped.** `find_loose_processes` lists a process whose argv contains a shell-snapshots path. It stops none, under any flag. That path does not prove a Claude Code Bash call started the process, or that the process is abandoned. A live session owns its own wrapper. The tier reports, and a person decides.

Kind: process
Home: janitor/test_sweep.py
