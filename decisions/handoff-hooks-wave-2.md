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
   input carries no previous session id.
   - On `clear`: a SessionEnd hook with reason `clear` writes a pointer, the old session id and
     the project directory. SessionStart reads the newest pointer for the same directory and
     names that handoff. A /clear pointer whose session has no handoff names none.
   - On `fork`: no pointer is read, because a pointer can name an older cleared session. The
     hook names the newest handoff for the same directory, which is the parent's.
   - A session's project directory is recorded each time a handoff hook runs for it (nudge,
     PreCompact, SessionEnd), so a session that never compacted is still found.
   - With nothing found, it says so. The session reads the named handoff and rewrites its own
     handoff from it.
   - At SessionStart reorient, stale pointers and `.dir` and `.reread` files are swept after
     30 days (`STALE_AGE`). This matches Claude Code's default `cleanupPeriodDays` of 30.
   - A malformed pointer is swept in every directory. A pointer with no handoff is swept only
     in the current directory.
   - A failed pointer delete is logged.
   - After compaction, the reorient message ends with the owner feedback inbox note. After
     /clear or a fork, it has no inbox note.
2. **Re-read check after compaction.** A PostCompact hook sets a flag for the session. A
   PreToolUse hook on Read clears the flag when the path is the session's handoff. A Stop hook
   blocks once per turn while the flag is set and the handoff file exists, and names its path. It exits on
   `stop_hook_active`, so it cannot loop.
3. **CI wake-up.** A PostToolUse hook on Bash and PowerShell starts an `asyncRewake` watcher
   after `gh pr ready <n>`. Each `gh pr ready` in one command gets its own watch. A push alone
   starts no watch: in this workflow a PR goes ready after its last push, and a push read can
   see the old head (review round 1). A draft PR starts no watch. The hook exits before imports
   when the command has no `ready`. The watcher reads the PR head once and waits on its
   runs. A head whose only runs are skipped counts as no run yet. It exits 2 with a one-line
   verdict, which wakes the session even when it is idle. It stops at its own deadline, under
   the hook `timeout`, and then wakes with "still running". One watcher runs per PR: a second
   one for the same PR exits at once. Text in quotes, in a heredoc body or after `#` never
   starts a watch. Any error, including an import or flush error, wakes with an "unknown" line.

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

## Holes, named

Debts: `handoff-wake-misses-ready-forms` (the CI wake misses an obfuscated `gh pr re''ady` and a `gh pr ready 2>&1` form), `handoff-pointer-swept-compact` (another session's compact reorient can sweep a /clear pointer), `handoff-pointers-age-out` (pointers with a handoff have no age rule, and a raised `cleanupPeriodDays` still sweeps after 30 days).

Kind: build
Plan: decisions/handoff-hooks-wave-2.md#windows (windows)
Plan: decisions/handoff-hooks-wave-2.md#macos (macos)
