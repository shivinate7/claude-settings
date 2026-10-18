# Handoff hooks, wave 2: clear, fork, re-read and CI wake-up

## The ruling

Owner, 2026-10-13 11:20 CDT: three hooks live in claude-settings. The mods session drops its own CI wake-up step. The /safe-stop entry point into precompact_handoff stays stable. All three are Python hooks registered in `settings.json`, each with a red test first.

1. **Reorient after /clear or a fork.** SessionStart has the sources `clear` and `fork`, with no previous session id.
   - On `clear`: a SessionEnd hook with reason `clear` writes a pointer, the old session id and the project directory. SessionStart reads the newest pointer for the same directory and names that handoff. A /clear pointer whose session has no handoff names none.
   - On `fork`: no pointer is read, because a pointer can name an older cleared session. The hook names the newest handoff for the same directory, which is the parent's.
   - A session's project directory is recorded each time a handoff hook runs for it (nudge, PreCompact, SessionEnd).
   - With nothing found, it says so. The session reads the named handoff and rewrites its own handoff from it.
   - At SessionStart reorient, stale pointers and `.dir` and `.reread` files are swept after 30 days (`STALE_AGE`, Claude Code's default `cleanupPeriodDays`). A malformed pointer is swept in every directory. A pointer with no handoff is swept only in the current directory. A failed pointer delete is logged.
   - After compaction, the reorient message ends with the owner feedback inbox note. After /clear or a fork, it has none.
2. **Re-read check after compaction.** A PostCompact hook sets a flag for the session. A PreToolUse hook on Read clears the flag when the path is the session's handoff. A Stop hook blocks once per turn while the flag is set and the handoff file exists, and names its path. It exits on `stop_hook_active`, so it cannot loop.
3. **CI wake-up.** A PostToolUse hook on Bash and PowerShell starts an `asyncRewake` watcher after `gh pr ready <n>`. Each `gh pr ready` in one command gets its own watch. A push alone starts no watch, because a PR goes ready after its last push and a push read can see the old head. A draft PR starts no watch. The hook exits before imports when the command has no `ready`.
   - The watcher reads the PR head once and waits on its runs. A head whose only runs are skipped counts as no run yet.
   - It exits 2 with a one-line verdict, which wakes the session even when idle. It stops at its own deadline, under the hook `timeout`, and wakes with "still running".
   - One watcher runs per PR: a second one for the same PR exits at once.
   - Text in quotes, in a heredoc body or after `#` never starts a watch. Any error, including an import or flush error, wakes with an "unknown" line.

Why: after /clear or a fork a session started blind. After compaction nothing checked that it read its handoff. Sessions waited for CI with long background commands that ran on for hours.

Kind: process
Home: hooks/precompact_handoff.py
Home: hooks/reread_check.py
Home: hooks/ci_wake.py
