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

## Records and health

The Records tab shows Health, then each listed record kind (decisions, debts, plans): its count, as
`ls | wc -l` counts it, and its newest five entries by add commit, linked to GitHub. In a shallow
clone the newest list reads "unknown", because the history stops before the files were added.

Health shows the repo map, the compliance scores and the session board. The map's path comes from
the extras: `{"map": "<path>", "github": "<owner>/<repo>"}`, under `"roadmap"` in the
layout extras file, else in `roadmap/extras.json` on the record branch. The compliance scores have no
home yet, and the session board's store lives on one machine, so both read "unknown" and say why.

## Live work

A strip under the read-at stamps shows each open project thread's state (waiting on you, working,
ready for review, failed, stopped) and the open pull requests, folded to one line of counts. A thread
that names a step also tags that step with its state. The builder cannot reach project threads or
GitHub, so the publisher reads them just before the build and passes one file:

    python3 ~/.claude/skills/roadmap/build.py --repo <checkout> --live live.json --out FILE

    {"readAt": "<ISO time of the reads>",
     "threads": [{"title", "state", "lastActivity"?, "step"?, "pr"?}],
     "pulls": [{"number", "title", "branch"?, "draft"?, "url"?, "checks"?}],
     "branches": [{"name", "updatedAt"?}]}

- `threads`: `list_threads`, every page. Leave out resolved threads. `state` is the thread state as
  listed. Add `step` only when the thread's brief names it.
- `pulls`: the repo's open pull requests. `branches`: lane branches with no open pull request.
- An entry with the wrong shape is counted on the page and in the upkeep list, never dropped. A
  `step` that names no open step goes in the upkeep list.
- With no `--live`, with no `threads` or `pulls` list, or with a `readAt` that is not an ISO time, the
  strip or its stamp reads "unknown" and says why. A local session's state does not show
  yet: that waits on step o8's option (c), each session writing its own line.

## A merge marks a step

A lane commit names its step in a `Step: <id>` trailer, in the last paragraph of the message, beside
the other trailers. Several ids may share one line, split by commas. At build, the builder reads
the log of `origin/main` (`--main-branch` names another) and marks each named open step "Landed in
#N", where #N is the pull request whose merge put the commit on main. It never closes a step: triage
closes it, from the upkeep list. A trailer that names no step is listed there too.

## Refusals

- A file under `roadmap/`, `briefs/`, `plans/` or `handoffs/` on the record branch holds a git
  conflict marker. The builder names each file and line, and writes no page. Resolve, then build again.
- The checkout is not on the record branch and no `--out` is given.

## Upkeep list

After each build the builder prints the upkeep list for the triage thread. It names:

- open-step notes that are too long;
- untouched steps and empty notes in a live phase;
- new top steps with no "Placed ahead of" line;
- landed steps that wait for triage to close them;
- `Step:` trailers that name no step.

## Cost

About six git processes and one page written per build. With `--live`, the publisher's reads add
one `list_threads` walk and one or two GitHub list calls, and one file it writes and the builder
reads. No watcher, no timer, no log.

## Tests

`python3 skills/roadmap/test_build.py` in the claude-settings checkout.
