# Keep the handoff current

A Stop-hook checkpoint asks you to update the handoff while you still have full context.
After a compaction, the reorient message asks again. Each time, rewrite the whole file.
Never append to it.

## 1. Read the prior handoff first

Read the prior handoff (the file from step 2) before you write anything, when it exists.
It holds the last known state.

## 2. Use the session's own handoff

The reorient message names your handoff file:
`~/.claude/handoffs/<session_id>.md` (under `CLAUDE_CONFIG_DIR` when set).
Use that path. It is per session and
outside git, so sessions on other branches never collide on it. Never keep the handoff
in a scratchpad or a temp folder.

A repo's own `HANDOFF.md` or `handoff.md` is a project document. Read it for context.
Change it only in a PR, never as this update.

## 3. Gather your sources

Use the compaction summary above. Read the digest file the reorient message named, when
it named one. Together they cover the work since the handoff's last write.

## 4. Rewrite the whole file

Write the file again from the top, with one whole-file write. Never append a block, a
dated line, or a "CURRENT STATE" section below the old ones. Keep only what is true now,
in the fewest words. Drop work that landed on main and text that a later fact replaced.
Git and the transcript keep the history. Never make a dated copy.

The handoff holds these sections, in this order:

- Rulings with NO HOME YET, first: only a ruling whose record is being written now. Name
  the branch that writes it. File every other ruling and task at once, in a decision record,
  a rule, or the repo's todo or debt store. The handoff is never their home.
- Goal: one line, the owner's goal in the owner's words, with its source (the owner
  message and its date).
- Working premises: the facts the next steps lean on, at most about 15, under the heading
  `## Working premises`. One line each, in this form:
  `- P1 [ruling|measured|read|notes|assumed] <claim>. Source: <where>. Checked <date or never>.`
  The kinds and what each means: docs/decisions/premise-format.md. A fact with no source is
  `assumed`.
- Where things stand: the branch, the head commit, open PRs, and their CI state.
- Work in flight: agents, workflow runs, and servers. Give each server its pid
  and its port.
- Next steps.
- The files and commands that matter.

## 5. Check premises

A premise is a claim, not a fact. After a compaction, a /clear or a fork, treat every
premise as a claim, and every fact in the compaction summary as `notes`. Before you act on a
weak or stale premise, check it. Then rewrite its line with the new source and date. When
the check shows it wrong, delete the line or replace it with the true fact and its source.
Keep no "was wrong" note. Fix the wrong fact in any brief, decision or plan that holds it. If
work already rested on it, say so under Deviations in the next report. The way to check each
kind, and which kinds are weak: docs/decisions/premise-format.md.

## 6. Update the plan, only when it changed

Look for a named plan file, under `~/.claude/plans` or the repo's own `plans` folder.
Update that plan only when your sources name one, and its state changed since the
prior handoff. Otherwise leave the plan alone.

## 7. Confirm, then continue

Confirm your checkout and your branch before any git write. Then continue the last
task.
