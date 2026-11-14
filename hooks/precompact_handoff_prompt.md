# Keep the handoff current

A Stop-hook checkpoint asks you to update the handoff while you still have full context.
After a compaction, the reorient message asks again. Each time, rewrite the whole file.
Never append to it.
Read each time you write from `~/.claude/bin/now-central --full`, never from memory.

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

After a compaction, also send one Explore agent on Sonnet to audit the handoff. Its brief's
first line is `Audit:`. It reads the session transcript from the previous
"This session is being continued" marker to the end (with no earlier marker, from the start),
and compares it with the handoff. A marker is a `compact_boundary` system record and the
summary that follows it. A line that only quotes the text, such as this prompt in a tool
result, is no marker. The transcript is
`<config dir>/projects/<project>/<session_id>.jsonl`; the session id is in the handoff's
path. It reports three lists in 40 lines or fewer: MISSING (rulings, facts and work in the transcript
that the handoff lacks), STALE (handoff lines the transcript replaced) and DONE (handoff
lines whose work landed). Then rewrite the handoff whole (step 4) from that report. One
agent per compaction, never per Stop checkpoint.

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
  `- P1 [ruling|measured|read|notes|assumed] <statement>. Source: <where>. Checked <date or never>.`
  The kinds and what each means: docs/decisions/premise-format.md. A fact with no source is
  `assumed`.
- Where things stand: the branch, the head commit, and the GitHub query for its open PRs and their CI state.
- Work in flight: agents, workflow runs, and servers. Give each server its pid
  and its port.
- Next steps.
- Files and commands: the files and commands that matter.

A hold, freeze or "waiting" line in any section carries `Ends: <the event that ends it>` in the
same line, such as `Held: no merges. Ends: the owner lifts the freeze.` When that event happens,
lift the hold in the same turn.

The marker line below is the one list of the required sections. The guard refuses a write that
drops one, and the Stop hook names one that is missing. Each sits under its own `## ` heading.
"Rulings with NO HOME YET" is conditional and not in the list.

<!-- handoff-sections: Goal | Working premises | Where things stand | Work in flight | Next steps | Files and commands -->

For a list that has a home (a page collection, a roadmap ref, a git ref or a GitHub query), name the home and never copy the list.

## 5. Check premises

A premise is a statement, not a fact. After a compaction, a /clear or a fork, treat every
premise as a statement, and every fact in the compaction summary as `notes`. Before you act on a
weak or stale premise, check it. Then rewrite its line with the new source and date. The guard rule `handoff-checked-stamp` refuses a changed `Checked` value on a premise you have not read or run a check of since the last compaction, so check before you restamp. When
the check shows it wrong, delete the line or replace it with the true fact and its source.
Keep no "was wrong" note. Fix the wrong fact in any brief, decision or plan that holds it. If
work already rested on it, say so under Deviations in the next report. The way to check each
kind, and which kinds are weak: docs/decisions/premise-format.md. After a compaction, put two lines under Deviations: `Recovered: <each ruling or fact you recovered, with its source: git, page or digest; items split on ";" outside parentheses>` or `Recovered: none`, and `Handoff gave: <facts the handoff supplied that the summary did not>` or `Handoff gave: none`. Start each line with its label, at line start or after a report label. The report guard (`lint/report_guard.py`) accepts each line in the report and refuses until it lands after the compaction. Triage counts the `Handoff gave:` lines at each roadmap review.

## 6. Update the plan, only when it changed

Look for a named plan file, under `~/.claude/plans` or the repo's own `plans` folder.
Update that plan only when your sources name one, and its state changed since the
prior handoff. Otherwise leave the plan alone.

## 7. Confirm, then continue

Confirm your checkout and your branch before any git write. Then continue the last
task.
