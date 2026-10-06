# A bare `gh pr merge` in a repo that uses `merge`

**What waits.** hooks/guard.py could refuse, or warn on, a bare `gh pr merge` in a repo whose
`.github/stamp.json` has a `merge` block. A bare merge skips the claim and does not move the
local main.

**Incident.** claude-sharables, 2026-10-06: four merges by plain `gh pr merge` left the local
main four commits behind origin. A later session read a stale file and nearly bumped a version
wrong.

**Why it waits.** Owner, 2026-10-06: build it last. Until `~/.claude/bin` is on PATH and a second
repo has opted into `merge` (`sharables-adopts-the-stamp`), a refusal blocks the only merge path
that works (`verification-recovery-not-gated-on-own-state`).

**Trigger that brings it back.** Both of these are on main: the installers put `~/.claude/bin`
on PATH, and a repo other than this one has a stamp config `merge` block.

**Owner.** The claude-settings orchestrator that lands the second `merge` adoption.
