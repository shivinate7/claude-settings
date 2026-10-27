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

A `guard` or `gate` rule has a mechanism in the parent. Mark that rule `parent-covered`, and
do not probe it, only when both checks pass:

- The live `${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json` has the same `hooks` block as
  `<parent>/settings.json`.
- `${CLAUDE_CONFIG_DIR:-~/.claude}/guard.log` has a verdict line from the last 7 days. Run
  `lint/guard_log_report.py --days 7` from the parent to read it.

If a check fails, the mechanism does not cover the child: report the rule as a gap in the
parent's install. If a file is missing or unreadable, mark the rule `unknown`.

Probe only what lives in the child's tree, from `probes.md` in this skill folder. A rule about
session practice, with no trace in the tree, is `n/a (session)`.

Three groups read the tree, not a rule prefix. Each comes after the rule groups:

- `Layout`: folder shape against `lint/layout.json` and the child's extras file.
- `Design`: screen readiness against `docs/design/`.
- `Copies`: copies of shared things the child holds, from the probe in `copies.md`.
- `iOS`: drift from the iOS standard of the `ios-apps` skill. A child with no iOS app is `n/a`.

## 3. Run the probes

Run each probe in `probes.md` from the child's root. Run the copy probe in `copies.md` too. One bounded command per probe, and keep
its verdict, not its stream. Some probes cannot run, for example with no `gh` login or no
network. Mark each of them `unknown`, never pass or fail. Defer CI shape to the `ci-hygiene`
skill and docs staleness to the `fresh-prose` skill. Name the skill and its top finding, and do
not repeat its steps.

## 4. Scorecard

One line per group, in the order of step 2, then Layout, Design, Copies and iOS:

```
<Group>: <in shape | partial | out | parent-covered | n/a | unknown> - <finding> (<file:line or command>)
```

Each finding cites a file or a command result. A group with mixed probes takes its worst
known score, and lists each unknown probe after it. Layout, Design and iOS list each item under the
group line, with its own grade, so one score never hides a gap. A child with no extras file
scores Layout `not rolled out`, not `out`, and its preview lines feed the roll-out lane. Under the group lines, name each parent rule
that no probe and no mechanism covers.

## 5. Plan

Rank the gaps. First, a gap that can lose work or ship a wrong result to the person the repo
serves. Next, a gap that hides defects. Last, cost and tidiness. Give each gap one lane the
orchestrator can brief:

```
<n>. <verb-first title> - rules: <id>, <id>
   files: <child paths>
   done when: <one bounded command and its expected verdict>
```

Keep each lane under 40 lines of change. Split a larger gap into lanes. A gap that needs an
owner ruling is a question with options and a recommendation, not a lane.
