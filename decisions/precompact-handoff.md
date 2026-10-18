# Checkpoints keep the handoff current

## Ruling

Auto-compact drops detail. These rules keep the handoff and plan current across a compaction, in every repo that uses claude-settings.

1. Auto-compact fires at 500k tokens on a 1M Opus window. `settings.json` sets `"autoCompactWindow": 500000`, a token count. `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` is not used: the docs do not give the window it is a percent of.
2. The session updates its handoff at context checkpoints, while it has full context: 200k tokens, then every +150k below the compaction limit minus 50k, then a last one at that limit minus 50k. After each compaction, auto or manual, it rewrites the handoff whole: what is true now, nothing appended. It updates the plan file too, when it works from one and the plan's state changed.
3. After compaction, a short message reorients the session.
4. It must work in the desktop app with no other login. No second `claude -p` with its own command-line login.
5. The handoff is per session and outside git: `~/.claude/handoffs/<session_id>.md`. A repo's own handoff.md is a project document, changed only by PR. Reason: a scratchpad handoff was lost when something outside the session deleted that folder, and a shared, committed handoff would conflict on every PR. Rulings still go to tracked homes at once. The handoff is not in `state/handoff/` beside the digest, because `hooks/guard.py` freezes `state`.

`hooks/precompact_handoff.py` is the one file, with three modes. No mode calls a model.

- **PreCompact** (no matcher, so auto and manual both fire) writes a digest of the transcript's user and assistant text to `~/.claude/state/handoff/<session_id>.digest.md`. It never blocks compaction.
- **Nudge** (`Stop`, `--nudge`) blocks the stop once at each new checkpoint. The reason names the handoff path and the prompt file. After a compaction it stays silent.
- **Reorient** (`SessionStart`, matcher `compact`) prints one short message. The session does the rewrite under the desktop app's own login. The message names the exact handoff path and tells the session to follow `~/.claude/hooks/precompact_handoff_prompt.md`, using the compaction summary, the digest and the prior handoff. With no digest, it uses the summary and the prior handoff alone. Then the session confirms checkout and branch and continues the last task.

Every mode fails open: on any error it logs and exits 0. Nudge also stays silent when `stop_hook_active`.

The prompt file tells the session how to rewrite the handoff:

- Use the path the reorient message names. Never a scratchpad or temp folder. The repo's own handoff.md is context, never the update target.
- Read the prior handoff, then rewrite the whole file with what is true now. Never append. Never make a dated copy. Reason: patching let sessions append block after block, and rulings with no home sank under them.
- If the work names a plan file (`~/.claude/plans/*.md` or the repo's `plans/*.md`) and the plan's state changed, update that plan in place.

The handoff holds these, in order:

1. Rulings with NO HOME YET.
2. Where things stand (branch, head, PRs and their CI), and the owner's rulings this session with their tracked homes, one line each.
3. Work in flight: agents, workflow runs, servers with pid and port.
4. Next steps, and the files and commands that matter.

A handoff is a short-term note. It is never a ruling's only home (`memory-is-never-a-rulings-only-home`).

Kind: process
Home: hooks/precompact_handoff.py
