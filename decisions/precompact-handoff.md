# Compaction rewrites the handoff first

## The question

Auto-compact drops detail. The post-compact session must re-learn where the work stands.
How do the handoff and plan stay current across a compaction, in every repo that uses
claude-settings?

## Ruling (owner, 2026-10-03)

1. Auto-compact fires at 50% of the window: 500k tokens on a 1M Opus window, 100k on a
   200k window. `settings.json` sets `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` to `50`.
2. Before each compaction, auto or manual, the session's handoff is rewritten in place.
   The plan file is updated too, when the session works from one and its state changed.
3. After compaction, a short message reorients the session: read the handoff, then the
   plan, confirm checkout and branch, continue.

## The design

One file, `hooks/precompact_handoff.py`, with two modes.

**PreCompact mode** (hook `PreCompact`, no matcher, so auto and manual both fire):

- Read the hook input: `session_id`, `transcript_path`, `cwd`.
- If `CLAUDE_HANDOFF_CHILD` is set, exit 0 at once. This stops recursion.
- Build a digest of the transcript: user and assistant text only. Drop tool results and
  thinking. Keep the last 150,000 characters.
- Run `claude -p` once, model `sonnet`, cwd at the repo top level, env
  `CLAUDE_HANDOFF_CHILD=1`. Its tools are Read, Write, Edit, Glob, and Grep only. It runs
  no hooks. Its prompt is `hooks/precompact_handoff_prompt.md`, with the digest attached.
- The child picks the handoff path: the repo's live handoff file if one exists (a
  `HANDOFF.md` or `handoff.md` outside any `history/` folder). Otherwise
  `.claude/handoff.md`. It rewrites that file in place. It never makes a dated copy.
- The child updates a plan file only when the digest names one (`~/.claude/plans/*.md` or
  the repo's `plans/*.md`) and the plan's state changed.
- The child's last output line is JSON: `{"handoff": <path>, "plan": <path or null>}`.
- The hook writes `~/.claude/state/handoff/<session_id>.json` with the handoff path, the plan
  path, ok or failed, and the time.
- The hook never blocks compaction. A failed or timed-out child is logged, and the hook
  exits 0. The child's budget is 240 s, inside the hook's 300 s timeout.

**Reorient mode** (hook `SessionStart`, matcher `compact`):

- Read the state file for `session_id`. Print one short message into context:
  "Context was compacted. Read the handoff at <path> first, then the plan at <path>.
  Confirm checkout and branch before any git write. Then continue the last task."
- With no state file, or a failed one, say the handoff update failed, and give the
  failure text. Tell the session to rewrite the handoff itself, from the compaction
  summary, at the path the child would have picked. Then continue.

## What the handoff holds

Where things stand (branch, head, PRs and their CI). The owner's rulings this session, each
with its tracked home, or marked "NO HOME YET". Work in flight: agents, workflow runs,
servers with pid and port. Next steps. The files and commands that matter. A handoff is a
short-term note. It is never a ruling's only home (see memory-is-never-a-rulings-only-home).

## Known limits

- The digest keeps the tail. Early detail lives on only through the prior handoff, which
  the child reads first.
- Each compaction adds one Sonnet call and delays compaction by up to 240 s.
- The child uses the command-line tool's own login. That login is separate from the
  desktop app's. The CLI login can expire while desktop sessions still work. The
  reorient fallback covers this: a failed child still gets its handoff rewritten, by
  the next session, from the compaction summary.
