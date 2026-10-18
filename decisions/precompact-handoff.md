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

A handoff is a short-term note. It is never a ruling's only home (`memory-is-never-a-rulings-only-home`).

Kind: process
Home: hooks/precompact_handoff.py
