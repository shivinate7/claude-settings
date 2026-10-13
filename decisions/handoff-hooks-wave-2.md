# Handoff hooks, wave 2: clear, fork, re-read and CI wake-up

Three hooks close gaps in how a session keeps its handoff and waits for CI.

## The question

How does a session find its handoff after /clear or a fork? How do we know it read the handoff
after compaction? How does it learn a CI run ended without a waiting command?

## The incident

- Only a compaction pointed a session at its handoff. After /clear or a fork, the session started blind.
- After compaction, nothing checked that the session read its handoff. It could go on from the summary alone.
- Sessions waited for CI with long background commands. Some ran on for hours after the run ended.

## The ruling

Owner ruling, 2026-10-13 11:20 CDT: build all three in claude-settings. The mods session drops
its own CI wake-up step (B5 step 1). The /safe-stop entry point into precompact_handoff stays
stable.

1. **Reorient after /clear or a fork.** SessionStart has the sources `clear` and `fork`. Its
   input carries no previous session id. So a SessionEnd hook with reason `clear` writes a
   pointer: the old session id and the project directory. The SessionStart `clear` or `fork`
   hook reads the newest pointer for the same project directory. It then tells the session to
   read that handoff and to rewrite its own handoff from it. With no pointer, it names the
   newest handoff for the same project directory. With none, it says so.
2. **Re-read check after compaction.** A PostCompact hook sets a flag for the session. A
   PreToolUse hook on Read clears the flag when the path is the session's handoff. A Stop hook
   blocks once while the flag is set, and names the handoff path. It exits on
   `stop_hook_active`, so it cannot loop.
3. **CI wake-up.** A PostToolUse hook on Bash starts an `asyncRewake` watcher after `gh pr
   ready` or a push to a branch with an open ready PR. The watcher waits on that head's runs
   once. It exits 2 with a one-line verdict, which wakes the session even when it is idle. The
   hook `timeout` caps the wait. The watcher never loops on a red run.

## Build plan

All three are Python hooks registered in settings.json. Each has a red test first.

### windows

Build and prove on this machine (Claude Code 2.1.296, after the 2.1.287 asyncRewake loop fix).
Install with install.ps1.

### macos

Same files. Prove on the Mac clone after `git pull` and install.sh.

## Named limits

- The /clear pointer matches by project directory. Two sessions that clear in the same
  directory at the same time can swap pointers.
- The docs give no minimum version for `asyncRewake`. A version below 2.1.287 can wake the
  session over and over.
- A foreground command that times out and moves to the background is not seen by any hook
  event (not documented). The stall watch misses it. That gap is not part of this record.

Kind: build
Plan: decisions/handoff-hooks-wave-2.md#windows (windows)
Plan: decisions/handoff-hooks-wave-2.md#macos (macos)
