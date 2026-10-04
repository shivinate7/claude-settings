# Rewrite the handoff after compaction

Compaction just dropped detail. Rewrite the handoff now, in this order.

## 1. Read the prior handoff first

Read the prior handoff before you write anything. It holds the last known state.

## 2. Pick the handoff path

Check the repo root for `HANDOFF.md` or `handoff.md`, outside any `history` folder.
Use that file when one exists. Otherwise use `.claude/handoff.md`.

## 3. Gather your sources

Use the compaction summary above. Read the digest file the reorient message named, when
it named one. Read the prior handoff too. Early detail may live only in that prior
handoff, since the digest keeps only its own tail.

## 4. Rewrite the file in place

Rewrite the handoff file at the path from step 2. Never make a dated copy.

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
