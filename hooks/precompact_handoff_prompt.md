# Keep the handoff current

A Stop-hook checkpoint asks you to update the handoff while you still have full context:
update every section of step 4 from what you know. After a compaction, patch it instead,
in this order. The last checkpoint wrote it with full context, so keep what still holds.

## 1. Read the prior handoff first

Read the prior handoff (the file from step 2) before you write anything, when it exists.
It holds the last known state.

## 2. Use the session's own handoff

The reorient message names your handoff file:
`~/.claude/state/handoff/<session_id>.handoff.md` (under `CLAUDE_CONFIG_DIR` when set).
Use that path. It is per session and
outside git, so sessions on other branches never collide on it. Never keep the handoff
in a scratchpad or a temp folder.

A repo's own `HANDOFF.md` or `handoff.md` is a project document. Read it for context.
Change it only in a PR, never as this update.

## 3. Gather your sources

Use the compaction summary above. Read the digest file the reorient message named, when
it named one. Together they cover the work since the handoff's last write.

## 4. Patch the file in place

Add what changed since the handoff's last write, and correct what is now false. Keep the
rest. When no handoff exists yet, write it whole. Never make a dated copy.

The handoff holds these sections:

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
