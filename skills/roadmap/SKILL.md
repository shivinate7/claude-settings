---
name: roadmap
description: Use when a session builds or publishes a repo's roadmap page, or the user says "build the roadmap" or "roadmap page". Bakes the steps on the repo's record branch and the record homes in the checkout into one read-only page, and prints the upkeep list for triage.
---

The roadmap page shows a repo's plan from its homes. It stores no copy: each panel prints the commit
it read, or "unknown" and why.

## Build

Run from any folder:

    python3 ~/.claude/skills/roadmap/build.py --repo <checkout> [--record-branch roadmap] [--out FILE]

- **On the record branch.** The checkout stands on the record branch: the builder reads the working
  tree and writes `roadmap/roadmap.html` there. Build after each edit to `roadmap/data/`.
- **Anywhere else.** The builder reads the record branch through git, `origin/<branch>` first, and
  writes the page to `--out`. Fetch the branch first, because the page is as old as the fetch.

The record homes (decisions, debts, debt notes, plans, specs) come from the checkout, at the paths
`lint/layout.py` gives. A home that is not there reads "unknown", never "none".

## Refusals

- A file under `roadmap/`, `briefs/`, `plans/` or `handoffs/` on the record branch holds a git
  conflict marker. The builder names each file and line, and writes no page. Resolve, then build again.
- The checkout is not on the record branch and no `--out` is given.

## Upkeep list

After each build the builder prints the upkeep list for the triage thread: long notes, untouched
steps and empty notes in a live phase, and new top steps with no "Placed ahead of" line.

## Cost

About six git processes and one page written per build. No watcher, no timer, no log.

## Tests

`python3 skills/roadmap/test_build.py` in the claude-settings checkout.
