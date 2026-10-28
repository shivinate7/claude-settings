---
name: compliance-check
description: Use when the user asks how well a repo follows the global rules, or says "compliance check", "audit this repo against CLAUDE.md", or "bring this repo into shape". Not for ordinary code edits. Reads the repo, scores it per rule group, folder shape and screen readiness, and gives a ranked plan of lanes.
---

Audit the current repo (the child) against the global rules (the parent). Read and report
only. Never edit, commit, fetch, or run a `--fix` in the child.

## 1. Find the parent

Read the first `@<dir>/CLAUDE.md` line of `${CLAUDE_CONFIG_DIR:-~/.claude}/CLAUDE.md`, as the
SessionStart hook in the parent's `settings.json` does. Expand a leading `~`. Call `<dir>` the
parent. If the line or `<dir>/.git` is missing, stop and report the audit as unknown.

## 2. Load the rules

- Rule ids: the `<!-- rule:<id> -->` anchors in the parent's `CLAUDE.md` and
  `output-styles/shiv-stylisms.md`. `RULE_FILES` in `lint/rule_audit.py` names
  both files. Read them with `grep`, never the whole file.
- Group: the id prefix. `outcomes`, `roles`, `parallelism`, `shared-trees`, `git`,
  `verification`, `tokens`, `building`, `speak`, `output`, `reports`. These are the 11 bold
  headings of `CLAUDE.md`. The style file adds `style`.
- Mechanism: `<parent>/lint/rule_mechanisms.json`, key `rules.<id>.mechanism.kind`.

A `guard` or `check` rule has a mechanism in the parent. Mark that rule `parent-covered`, and
do not probe it, only when both checks pass:

- The live `${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json` has the same `hooks` block as
  `<parent>/settings.json`.
- `${CLAUDE_CONFIG_DIR:-~/.claude}/guard.log` has a verdict line from the last 7 days. Run
  `lint/guard_log_report.py --days 7` from the parent to read it.

If a check fails, the mechanism does not cover the child: report the rule as a finding in the
parent's install. If a file is missing or unreadable, mark the rule `unknown`.

Probe only what lives in the child's tree, from `probes.md` in this skill folder. A rule about
session practice, with no trace in the tree, is `n/a (session)`.

Three groups read the tree, not a rule prefix. Each comes after the rule groups:

- `Layout`: folder shape against `lint/layout.json` and the child's extras file.
- `Design`: screen readiness against `docs/design/`.
- `Copies`: copies of shared things the child holds, from the probe in `copies.md`.
- `iOS`: drift from the iOS standard of the `ios-apps` skill. A child with no iOS app is `n/a`.
- `Caution`: listing only, for the owner to prune. It has no grade. Run `python3 <parent>/lint/layout.py caution <child>`
  and print the level it resolves. Then list each rule in the child's `CLAUDE.md` and `.claude/rules/` that
  restricts what Claude does with a password, a token, a login, a secret or a private datum, as
  `<file>: "<the rule, quoted>"`. Example: "Claude never types a password or token into a field". Mark a
  rule that blocks a login to the owner's own low-stakes device (Home Assistant, the speakers) with
  `blocks own login`. The owner decides which to prune. Change none of them. A file that cannot be read is
  `unknown`.

## 3. Run the probes

Run each probe in `probes.md` from the child's root. Run the copy probe in `copies.md` too. One bounded command per probe, and keep
its verdict, not its stream. Some probes cannot run, for example with no `gh` login or no
network. Mark each of them `unknown`, never pass or fail. Defer CI shape to the `ci-hygiene`
skill and docs staleness to the `fresh-prose` skill. Name the skill and its top finding, and do
not repeat its steps.

## 4. Scorecard

One line per group, in the order of step 2, then Layout, Design, Copies, iOS and the Caution listing:

```
<Group>: <in shape | partial | out | parent-covered | not rolled out | n/a | unknown> - <finding> (<file:line or command>)
```

Each finding cites a file or a command result. A group with mixed probes takes its worst
known score, and lists each unknown probe after it. Layout, Design and iOS list each item under the
group line, with its own grade, so one score never hides a finding. A child with no extras file
scores Layout `not rolled out`, not `out`, and its preview lines feed the roll-out lane. Under the group lines, name each parent rule
that no probe and no mechanism covers.

Write the scorecard to one file, the layout's `scorecard` kind (`docs/health/compliance.md`) in the checked repo. Pipe the group
lines into `python3 lint/compliance_probes.py scorecard <child root>`. It rewrites the file in place
on each run. Never write a dated copy beside it. The file holds one table, with the columns
Group, Score, Gold standard, Gap, Source. Gold standard is `in shape`. The script always adds a row
`STE lint on UI files`, scored `partial`: the lint does not read UI text, and that is a known gap.
Write each item line after its group line. An indented item line, `- <item>: <grade> - <finding> (<source>)`, becomes its own row
after the group row above it. Its grade is pass, gap or partial, not a group score. An indented line with no grade
becomes a row scored `finding`. Raw probe output works too: each probe prints its group line first, then its
item lines. The script keeps every other line, and every item line above the first group line, under
Notes and drops none. Report the UI gap as a known
gap. Do not build a UI linter.

## 5. Plan

Rank the findings. First, a finding that can lose work or ship a wrong result to the person the repo
serves. Next, a finding that hides defects. Last, cost and tidiness. Give each finding one lane the
orchestrator can brief:

```
<n>. <verb-first title> - rules: <id>, <id>
   files: <child paths>
   done when: <one bounded command and its expected verdict>
```

Keep each lane under 40 lines of change. Split a larger finding into lanes. A finding that needs an
owner ruling is a question with options and a recommendation, not a lane.
