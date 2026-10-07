# Rewrite the handoff after compaction

Compaction just dropped detail. Rewrite the handoff now, in this order.

## 1. Read the prior handoff first

Read the prior handoff (the file from step 2) before you write anything, when it exists.
It holds the last known state.

## 2. Use the session's own handoff

The reorient message names your handoff file:
`~/.claude/state/handoff/<session_id>.handoff.md`. Use that path. It is per session and
outside git, so sessions on other branches never collide on it. Never keep the handoff
in a scratchpad or a temp folder.

A repo's own `HANDOFF.md` or `handoff.md` is a project document. Read it for context.
Change it only in a PR, never as this rewrite.

## 3. Gather your sources

Use the compaction summary above. Read the digest file the reorient message named, when
it named one. Read the prior handoff too. Early detail may live only in that prior
handoff, since the digest keeps only its own tail.

## 4. Rewrite the file in place

Rewrite the handoff file from step 2. Never make a dated copy.

Write these sections:

- Where things stand: the branch, the head commit, open PRs, and their CI state.
- The owner's rulings from this session. Give each ruling its tracked home, a file
  and a section. Write "NO HOME YET" when a ruling has no tracked home.
- Work in flight: agents, workflow runs, and servers. Give each server its pid
  and its port.
- Next steps.
- The files and commands that matter.

## 5. Update the plan, only when it changed

Look for a named plan file, under `~/.claude/plans` or the repo's own `plans` folder.
Update that plan only when your sources name one, and its state changed since the
prior handoff. Otherwise leave the plan alone.

## 6. Confirm, then continue

Confirm your checkout and your branch before any git write. Then continue the last
task.
