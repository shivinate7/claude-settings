# Rewrite the handoff before compaction

Compaction is about to drop detail. Rewrite the handoff now, in this order.

## 1. Read the prior handoff first

Read the prior handoff before you write anything. It holds the last known state.

## 2. Pick the handoff path

Check the repo root for `HANDOFF.md` or `handoff.md`, outside any `history` folder.
Use that file when one exists. Otherwise use `.claude/handoff.md`.

## 3. Rewrite the file in place

Rewrite the handoff file at that same path. Never make a dated copy.

Write these sections:

- Where things stand: the branch, the head commit, open PRs, and their CI state.
- The owner's rulings from this session. Give each ruling its tracked home, a file
  and a section. Write "NO HOME YET" when a ruling has no tracked home.
- Work in flight: agents, workflow runs, and servers. Give each server its pid
  and its port.
- Next steps.
- The files and commands that matter.

## 4. Update the plan, only when it changed

Look in the digest for a named plan file, under `~/.claude/plans` or the repo's
own `plans` folder. Update that plan only when the digest names one, and its
state changed since the prior handoff. Otherwise leave the plan alone, and
report its path as `null`.

## 5. Print the summary line

Print one JSON line as your last line of output. Print no other text after it:

`{"handoff": "<handoff file path>", "plan": "<plan file path, or null>"}`

## Your tools

You have Read, Write, Edit, Glob, and Grep. You have no other tool. You run no
hooks.

## The transcript digest

The digest follows this line. It holds the session's user and assistant text,
newest text last. Early detail may be missing from it. Use the prior handoff
for anything the digest does not cover.

---
