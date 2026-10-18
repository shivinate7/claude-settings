# A stalled background command is reported, never stopped

## The ruling

The session learns within minutes that a background command stalled, and diagnoses the cause. When the
stall is reported, the stuck command keeps running. Reason: a `playwright install` hung unnoticed behind a
stale cache lock, and the report names the lock file. A stop on a timer would kill a slow but healthy job
and lose the state that explains the stall. A polling timer in the session is refused by the `waiter`
guard rule, so the watcher does the waiting and the session is told once.

`hooks/stall_watch.py` does it.

- The hook (`--hook`, a PreToolUse hook on Bash) returns `updatedInput` only for a call with
  `run_in_background` true. It sets no permission decision, so no permission changes.
- The original command stays as unquoted top-level shell code inside `{ ... }`, so a settings deny rule
  still sees it. Allow rules still match a rewritten command.
- The STALL report names the pids to stop, so stopping every one ends the job (owner ruling,
  2026-10-18). The shell gives the watcher the pid of `&`. In sh, bash and zsh a `{ }` group runs in a
  forked copy of the shell, which has the same command line. Per shape, the report names:
  - One command: its own pid. sh and bash step down through the copy. zsh runs the command without a
    copy, so the pid of `&` is the command.
  - A sequence, a subshell or an `exec`: the command that runs now.
  - A pipeline, nested ones too: each member's pid, and no shell copy.
  - A loop of builtins only: the shell copy that runs it.
  - A command where `while`, `until` or `for` starts a command (the hook's `--loop 1`): the shell copy
    that runs the loop, because the loop starts each body command again. A process tree cannot tell a
    loop from a sequence, so the hook reads the command text with the stdlib shell tokenizer.
  - Limit: stopping a loop's copy leaves its current body command running. The report's process table
    lists that command. The flag covers the whole command, so a command that runs after the loop ends
    (`until curl ...; do sleep 1; done; npm start`) is named by its shell copy too, not by its own pid.
- The watcher (`--watch-pid`) prints a STALL report and exits 3 after 300 quiet seconds. The job keeps
  running and the watcher never stops it.
- The report tells the session to ask the owner to stop the job. After the report, the job is not a child
  of the session, and the guard denies a stop of a process outside the session.
- A tool that is quiet by design must print a short progress line at least every 120 seconds. The watcher
  does not change, because a false STALL teaches the reader to scroll past a real one
  (guard-that-cries-wolf-is-spent). The merge tool prints `merge: waiting on ...` while it waits on checks,
  and while GitHub still shows the head before the push. `verdict` prints a `still running` line every 120
  seconds.

Kind: process
Home: hooks/stall_watch.py
