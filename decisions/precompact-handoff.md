# Compaction rewrites the handoff first

## The question

Auto-compact drops detail. The post-compact session must re-learn where the work stands.
How do the handoff and plan stay current across a compaction, in every repo that uses
claude-settings?

## Ruling (owner, 2026-10-03; handoff home 2026-10-07)

1. Auto-compact fires at 500k tokens on a 1M Opus window. `settings.json` sets
   `"autoCompactWindow": 500000`, a token count. Claude Code caps it at the model's own
   window, so a 200k model keeps 200k. `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` is not used: it
   is a percent of a window that Claude Code picks per model, and the docs do not give
   that window's size.
2. At each compaction, auto or manual, the session's handoff is rewritten in place. The
   plan file is updated too, when the session works from one and its state changed.
3. After compaction, a short message reorients the session.
4. It must work in the desktop app with no other login. The owner rejected a design that
   ran a second `claude -p` with its own command-line login.
5. The handoff is per session and outside git:
   `~/.claude/state/handoff/<session_id>.handoff.md`. A repo's own handoff.md is a
   project document, changed only by PR.

## The design

One file, `hooks/precompact_handoff.py`, with two modes. Neither mode calls a model.

**PreCompact mode** (hook `PreCompact`, no matcher, so auto and manual both fire):

- Read the hook input: `session_id`, `transcript_path`, `cwd`.
- Build a digest of the transcript: user and assistant text only. Drop tool results and
  thinking. Keep the last 60,000 characters.
- Write the digest to `~/.claude/state/handoff/<session_id>.digest.md`. Write
  `~/.claude/state/handoff/<session_id>.json` with the digest path, the session's cwd,
  ok or failed, and the time.
- Never block compaction. On any error, log it and exit 0.

**Reorient mode** (hook `SessionStart`, matcher `compact`):

Print one short message into context. The session itself does the rewrite, under the
desktop app's own login. The message tells the session to:

1. Follow `~/.claude/hooks/precompact_handoff_prompt.md` before anything else.
2. Rewrite the handoff at `~/.claude/state/handoff/<session_id>.handoff.md`. The
   message names the exact path.
3. Use the compaction summary, the digest at its path, and the prior handoff.
4. Then confirm checkout and branch, and continue the last task.

With no state file, or a failed one, the message says the digest is missing. The session
then rewrites from the compaction summary and the prior handoff alone.

**The prompt file** tells the session how to rewrite:

- The handoff path: the one the reorient message names. Never a scratchpad or temp
  folder. The repo's own handoff.md is context, never the rewrite target.
- Read the prior handoff first. Rewrite it in place. Never make a dated copy.
- If the work names a plan file (`~/.claude/plans/*.md` or the repo's `plans/*.md`) and
  the plan's state changed, update that plan in place.

## What the handoff holds

Where things stand (branch, head, PRs and their CI). The owner's rulings this session, each
with its tracked home, or marked "NO HOME YET". Work in flight: agents, workflow runs,
servers with pid and port. Next steps. The files and commands that matter. A handoff is a
short-term note. It is never a ruling's only home (see memory-is-never-a-rulings-only-home).

## Why the handoff is per session and outside git

Incident, 2026-10-07: a q_max orchestrator kept its handoff in its session scratchpad,
under `AppData\Local\Temp\claude`. Something outside the session deleted that folder
(cause unmeasured; this repo's janitor does not sweep there). The old rule named only a
root handoff.md or `.claude/handoff.md`. q_max could use neither: a second handoff.md
breaks its DOC3 check, and its CLAUDE.md puts session state in `specs/handoff.md`.

A shared, committed handoff does not fix it. Several sessions run at once, each on its
own branch. Each would rewrite one file, every PR would conflict on it, and the last
merge would erase the others' state. So each session gets its own file, in the folder
the hook already owns. Rulings still go to tracked homes at once
(memory-is-never-a-rulings-only-home), so a lost machine loses only short-term state.

## Known limits

- The rewrite happens after compaction, so the session writes from the summary and the
  digest, not from its full context. The digest keeps only the tail. Early detail lives on
  through the prior handoff. A session's first compaction has no prior handoff.
- The rewrite costs the post-compact session one read of the digest, about 15k tokens.

## Measured facts

The session id stays the same across a compaction. This session's transcript has its
compact boundary at line 2486. All 2,876 entries carry one `sessionId`. So reorient finds
the state that PreCompact wrote.
