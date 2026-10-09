# The SessionEnd sweep is armed, because Windows liveness is proven

## The ruling

The `SessionEnd` hook in `settings.json` runs `janitor/session_end_sweep.py`. That
script runs `janitor/sweep.py --confirm` on the repository of the session that ends.
The hook is armed on every platform. The file name of this entry keeps the word
"disarmed", because other files cite it by that name.

## Why it was off, and what armed it again

The owner removed the hook on 2026-09-21. The defect: `hooks/guard.py` read a process
start time with `ps -o lstart=`. On Windows the `ps` in this environment has no `-o`
option, so every session read as dead. The sweep could then remove a worktree that a
live session stood in. MEASURED on 2026-09-21: this session's own record read
`live=False` while it ran.

Two conditions armed it again. Both are MEASURED:

1. The liveness read answers three states: alive, dead, and unreadable. On Windows it
   reads a process start time through `kernel32.OpenProcess` and `GetProcessTimes`
   (pull request #93). Error 87 means dead. Error 5 means unreadable. Unreadable
   reaches the caller as `None`, and every caller keeps or refuses on `None`.
2. A Windows job in `.github/workflows/gates.yml` runs the guard and sweep suites and
   their mutation harnesses, and passes. The first green run was 35766479009, on pull
   request #107.

Pull request #109 put the hook back.

## The mechanism

`hooks/session_start.sh` prints a notice at the top of each session when the
`SessionEnd` hook is absent from `settings.json`. The notice names this entry. The
check reads the config, so it stops on its own when the hook returns. A config that
cannot be read is reported as unknown, never as armed or disarmed.

`janitor/test_session_end_sweep.py` has three budget arms. They skip only when
`SessionEnd` is absent from `settings.json`.
