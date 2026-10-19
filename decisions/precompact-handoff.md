# Checkpoints keep the handoff current

## Ruling

Auto-compact drops detail. These rules keep the handoff and plan current across a compaction, in every repo that uses claude-settings.

1. Auto-compact fires at 500k tokens. `settings.json` sets `"autoCompactWindow": 500000`, a token count. `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` is not used: the docs do not give the window it is a percent of.
2. The session updates its handoff at context checkpoints, while it has full context: 200k tokens, then every +150k below the compaction limit minus 50k, then a last one at that limit minus 50k. After each compaction, auto or manual, it rewrites the handoff whole: what is true now, nothing appended. It updates the plan file too, when it works from one and the plan's state changed.
3. After compaction, a short message reorients the session.
4. It must work in the desktop app with no other login. No second `claude -p` with its own command-line login. So no mode of `hooks/precompact_handoff.py` calls a model.
5. The handoff is per session and outside git: `~/.claude/handoffs/<session_id>.md`. A repo's own handoff.md is a project document, changed only by PR. Reason: a scratchpad handoff was lost when something outside the session deleted that folder, and a shared, committed handoff would conflict on every PR. Rulings still go to tracked homes at once. The handoff is not in `state/handoff/` beside the digest, because `hooks/guard_frozen.py` freezes `state`.
6. Every mode fails open: on any error it logs and exits 0. PreCompact never blocks compaction. The Stop nudge blocks once at each new checkpoint and stays silent after a compaction and when `stop_hook_active`.
7. `hooks/precompact_handoff_prompt.md` tells the session how to rewrite the handoff. It uses the path the reorient message names, never a scratchpad or temp folder. It rewrites the whole file and never appends or makes a dated copy. Reason: patching let sessions append block after block, and rulings with no home sank under them.

Owner, 2026-10-13 11:20 CDT: the reorient and re-read hooks live in claude-settings. Each is a Python hook registered in `settings.json`, with a red test first. The /safe-stop entry point into `precompact_handoff` stays stable.

8. **Reorient after /clear or a fork.** SessionStart has the sources `clear` and `fork`, with no previous session id.
   - On `clear`: a SessionEnd hook with reason `clear` writes a pointer, the old session id and the project directory. SessionStart reads the newest pointer for the same directory and names that handoff. A /clear pointer whose session has no handoff names none.
   - On `fork`: no pointer is read, because a pointer can name an older cleared session. The hook names the newest handoff for the same directory, which is the parent's.
   - A session's project directory is recorded each time a handoff hook runs for it (nudge, PreCompact, SessionEnd).
   - With nothing found, it says so. The session reads the named handoff and rewrites its own handoff from it.
   - At SessionStart reorient, stale pointers and `.dir` and `.reread` files are swept after 30 days (`STALE_AGE`, Claude Code's default `cleanupPeriodDays`). A malformed pointer is swept in every directory. A pointer with no handoff is swept only in the current directory. A failed pointer delete is logged.
   - After compaction, the reorient message ends with the owner feedback inbox note. After /clear or a fork, it has none.
9. **Re-read check after compaction** (`hooks/reread_check.py`). A PostCompact hook sets a flag for the session. A PreToolUse hook on Read clears the flag when the path is the session's handoff. A Stop hook blocks once per turn while the flag is set and the handoff file exists, and names its path. It exits on `stop_hook_active`, so it cannot loop.

Reason for items 8 and 9: after /clear or a fork a session started blind. After compaction nothing checked that it read its handoff.

A handoff is a short-term note. It is never a ruling's only home (`memory-is-never-a-rulings-only-home`).

Kind: process
Home: hooks/precompact_handoff.py
Home: hooks/reread_check.py
