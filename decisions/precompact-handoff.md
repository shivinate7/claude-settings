# Checkpoints keep the handoff current

## Ruling

Auto-compact drops detail. These rules keep the handoff and plan current across a compaction, in every
repo that uses claude-settings.

1. Auto-compact fires at 500k tokens on a 1M Opus window. `settings.json` sets
   `"autoCompactWindow": 500000`, a token count. Claude Code caps it at the model's own window, so a
   200k model keeps 200k. `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` is not used: it is a percent of a window
   that Claude Code picks per model, and the docs do not give that window's size.
2. The session updates its handoff at context checkpoints, while it has full context: 200k tokens, then
   every +150k below the compaction limit minus 50k, then a last one at that limit minus 50k. After each
   compaction, auto or manual, it rewrites the handoff whole: what is true now, nothing appended. The
   plan file is updated too, when the session works from one and its state changed.
3. After compaction, a short message reorients the session.
4. It must work in the desktop app with no other login. No second `claude -p` with its own
   command-line login.
5. The handoff is per session and outside git: `~/.claude/handoffs/<session_id>.md`. A repo's own
   handoff.md is a project document, changed only by PR.

Why per session, outside git: a scratchpad handoff was lost when something outside the session deleted
that folder. A shared, committed handoff would conflict on every PR, and the last merge would erase the
other sessions' state. Rulings still go to tracked homes at once, so a lost machine loses only
short-term state. The handoff is not in `state/handoff/` beside the digest, because `hooks/guard.py`
freezes `state`. A test asks the guard whether the handoff path is frozen.

## The design

One file, `hooks/precompact_handoff.py`, with three modes. No mode calls a model.

**PreCompact mode** (hook `PreCompact`, no matcher, so auto and manual both fire):

- Read the hook input: `session_id`, `transcript_path`, `cwd`.
- Build a digest of the transcript: user and assistant text only. Drop tool results and thinking. Keep
  the last 60,000 characters.
- Write the digest to `~/.claude/state/handoff/<session_id>.digest.md`. Write
  `~/.claude/state/handoff/<session_id>.json` with the digest path, the session's cwd, ok or failed,
  and the time.
- Never block compaction. On any error, log it and exit 0.

**Nudge mode** (hook `Stop`, flag `--nudge`):

- Context size: the last assistant entry's usage (input + cache creation + cache read).
- Limit: `autoCompactWindow` from settings.json, 500,000 when missing. Checkpoints: 200k, +150k steps
  below limit-50k, then limit-50k. With limit-50k at or below 200k, limit-50k is the only checkpoint.
- When the context reaches a new checkpoint, block the stop once, with a reason that names the handoff
  path and the prompt file. Store the checkpoint in `~/.claude/state/handoff/<session_id>.nudge.json`.
  When the context shrinks (a compaction), store the lower checkpoint and stay silent. With
  `stop_hook_active`, or on any error, stay silent and exit 0.

**Reorient mode** (hook `SessionStart`, matcher `compact`): print one short message into context. The
session itself does the rewrite, under the desktop app's own login. The message tells the session to:

1. Follow `~/.claude/hooks/precompact_handoff_prompt.md` before anything else.
2. Rewrite the handoff at `~/.claude/handoffs/<session_id>.md`. The message names the exact path.
3. Use the compaction summary, the digest at its path, and the prior handoff.
4. Then confirm checkout and branch, and continue the last task.

With no state file, or a failed one, the message says the digest is missing. The session then rewrites
the handoff from the compaction summary and the prior handoff alone. The session id stays the same
across a compaction, so reorient finds the state that PreCompact wrote.

**The prompt file** tells the session how to rewrite the handoff:

- Use the path the reorient message names. Never a scratchpad or temp folder. The repo's own handoff.md
  is context, never the update target.
- At a checkpoint and after compaction, read the prior handoff, then rewrite the whole file with what is
  true now. Never append. Never make a dated copy. Patching let sessions append block after block, and
  rulings with no home sank under them.
- If the work names a plan file (`~/.claude/plans/*.md` or the repo's `plans/*.md`) and the plan's state
  changed, update that plan in place.

**What the handoff holds.** Rulings with NO HOME YET come first. Then where things stand (branch, head,
PRs and their CI), and the owner's rulings this session with their tracked homes, one line each. Then
work in flight: agents, workflow runs, servers with pid and port. Then next steps, and the files and
commands that matter. A handoff is a short-term note. It is never a ruling's only home
(memory-is-never-a-rulings-only-home).

Kind: process
Home: hooks/precompact_handoff.py

## Known limits

- The post-compaction rewrite covers the work since the last checkpoint, up to about 50k tokens, from
  the summary and the digest. The digest keeps only the last 60,000 characters of text, so a long,
  talk-heavy gap can lose detail.
- The hook reads the limit from settings.json. Claude Code also caps compaction at the model's own
  window, which the hook cannot see. On a smaller model, compaction can fire before a checkpoint.
- The reply written after a checkpoint block runs with `stop_hook_active` set, so the other Stop gates
  skip it. When another Stop hook blocked first, the checkpoint fires one stop later.
- Each checkpoint costs one handoff rewrite. After compaction, the rewrite also costs one read of the
  digest, about 15k tokens.
- Nothing checks that a session rewrote the file and did not append. The prompt asks for a rewrite, and
  the owner reads the result.
