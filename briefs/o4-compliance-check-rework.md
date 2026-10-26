# o4: rework compliance-check

Cloud build thread brief. Build advisor (3), Oct 26. Base: main after batch #614 merges (it
carries o2's lint/layout.json and lint/layout.py); the dispatcher names the commit. Never rebase
onto main after review. Push roadmap edits to the branch only; only "Triage the roadmap (3)"
republishes the roadmap page.

## Task

Rework `skills/compliance-check` (SKILL.md, probes.md) so it sees folder shape and screen
readiness, not only CLAUDE.md rules:
1. Layout group: read lint/layout.json through lint/layout.py (the one home; never copy its
   paths) plus the child's `.claude/layout-extras.json`. Report each folder the child has that
   is neither a layout kind nor an extra, and each core kind it lacks. A child with no extras
   file is "not rolled out", not failing.
2. Design group: screen readiness against ux/ (ux/checklist.md, ux/layout.md, ux/tokens.md):
   does the repo name its screens, sizes and themes, have a screenshot command (d6), and one
   token file. Report per item, never a single score that hides a gap.
3. Leftovers homed here by triage: a probe for a guessed lane cap in a repo's briefs (rule
   parallelism-no-guessed-lane-cap), and the STE lint's gap on UI files (from c15): report it
   as a known gap, do not build an STE linter for UI files.
4. Leave one heading, "Copies", for o11 (one home per shared thing), which adds its own probe
   file; do not build a copy finder.

## Fences

- compliance-check reads and reports only. Never edit a child repo. Never push to child repos;
  you may read them under /home/user to test the probes.
- Do not edit lint/layout.py or lint/layout.json; if they lack something, say so.
- Any new record: put it at the decisions path lint/layout.json names on your base.

## Failure classes and proof

- Run the reworked skill read-only against at least banchi, mailaudit and one repo with no
  extras file. Each new probe must go red on a real gap it guards, and show no false alarm on a
  repo that is fine (verification-trust-guard-after-red, verification-cry-wolf-guard-is-spent).
- This changes a skill's behaviour: a fresh Sonnet reviewer reads the diff.
- Run ste-changed and the skill's tests through `verdict`.

## Report

Cap 20 lines: Done, Deviations, Next, and the per-repo results in one line each. Send the green,
reviewed head and branch to "Advise the claude-settings build (3)". Do not merge, and do not
rebase onto main. No question for shiv: park any in the PR body.
