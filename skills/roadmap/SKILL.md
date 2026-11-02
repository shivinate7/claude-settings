---
name: roadmap
description: Use when a session builds a repo's roadmap block, or the user says "build the roadmap", "roadmap page" or "update the status tab". Bakes the steps on the repo's record branch and the record homes in the checkout into the roadmap block of the repo's one page, and prints the upkeep list for triage.
---

A repo has one page: the waiting page. Its Status tab shows the repo's plan from its homes. This
skill publishes no page. The build makes one marked roadmap block, and the waiting-page writer splices
it into the live page (see "Publish the roadmap block"). The old roadmap URL retires: it gets no more
publishes. The page's URL is the `waiting-page` key of the layout extras file. The `roadmap` key there
is the `{map, github}` object the build reads, never a URL. The tab stores
no copy: each panel prints the commit it read, or "unknown" and why.

## Build

Run from any folder:

    python3 ~/.claude/skills/roadmap/build.py --repo <checkout> [--record-branch <branch>] --block --out FILE

`--record-branch` defaults to the extras key `record-branch` in `.claude/layout-extras.json`, else `roadmap`.
With no flag, an extras file that cannot be read warns and reads `roadmap`. A `record-branch` value that is
not a plain git branch name stops the build.

`--block` writes only the roadmap block, the text between `<!-- roadmap:data -->` and `<!-- /roadmap:data -->`. It holds
`window.ROADMAP_DATA` and `window.ROADMAP_BUILD`, and never a database stand-in. With no record branch,
`ROADMAP_DATA` is null and the Status tab says the plan is unknown. Without `--block` the builder writes
the whole old read-only page. Nothing publishes it.

- **On the record branch.** The checkout stands on the record branch: the builder reads the working
  tree. Build after each edit to `roadmap/data/`.
- **Anywhere else.** The builder reads the record branch through the repo history, `origin/<branch>`
  first. Fetch the branch first, because the roadmap block is as old as the fetch.
- `--block` needs `--out`, on either path.

The record homes (decisions, debts, debt notes, plans, specs) come from the checkout, at the paths
`lint/layout.py` gives. A home that is not there reads "unknown", never "none".

## Publish the roadmap block

The waiting-page writer alone publishes the page (skill waiting-page, "Update the roadmap block").
It reads the live page first, splices this roadmap block in with `splice.py`, and publishes one at a time,
never with `force`, with the capabilities `db` and `{comments: {}}`. This skill never calls
`Artifact` for a page.

## Lane and grants

Two step fields serve the guard, not the page:

- `lane`: `"session_<id>"`, the one lane session bound to the step. The coordinator writes it when it
  starts the lane. One step per lane.
- `grants`: a list of step grants, written by triage only. Each is `{"words": "<the owner's exact
  words>", "at": "<ISO-8601 with offset>", "role": null | "<role>", "by": "triage"}`. A null `role`
  covers every Opus spawn of the lane, else one role from `OPUS_ROLES` in `hooks/override.py`.

The guard reads them from the lane's local `origin/roadmap`, so a lane fetches it after triage writes a
grant (decision `agent-model-cap`).

## Records and health

The Records view shows Health, then each listed record kind (decisions, debts, plans): its count, as
`ls | wc -l` counts it, and its newest five entries by add commit, linked to GitHub. In a shallow
clone the newest list reads "unknown", because the history stops before the files were added.

Health shows the repo map, the compliance scores and the session board. The map's path comes from
the extras: `{"map": "<path>", "github": "<owner>/<repo>"}`, under `"roadmap"` in the
layout extras file, else in `roadmap/extras.json` on the record branch. The compliance scores have no
home yet, and the session board's store lives on one machine, so both read "unknown" and say why.

## Live work

The Status tab's Live work line shows each open project thread's state (asking in its chat, working,
ready for review, failed, stopped) and the open pull requests, folded to one line of counts. Its body
lists the threads, the pull requests and the branches. The builder cannot reach project threads or
GitHub, so the publisher reads them just before the build and passes one file:

    python3 ~/.claude/skills/roadmap/build.py --repo <checkout> --live live.json --block --out FILE

    {"readAt": "<ISO time of the reads>",
     "threads": [{"title", "state", "lastActivity"?, "step"?, "pr"?}],
     "pulls": [{"number", "title", "branch"?, "draft"?, "url"?, "checks"?}],
     "branches": [{"name", "updatedAt"?}],
     "sessions": [{"id", "session_status", "tags"}],
     "items": [{"n", "status", "home"}]}

- `threads`: `list_threads`, every page. Leave out resolved threads. `state` is the thread state as
  listed. Add `step` only when the thread's brief names it.
- `pulls`: the repo's open pull requests. `branches`: lane branches with no open pull request.
- `sessions`: `list_sessions`, every page, each row copied as it comes with only these three fields.
  The upkeep list reads it for steps in progress. A live file with no `sessions` list still renders
  Live work.
- `items`: `ArtifactData list items` of the repo's waiting page, every page, each row copied with only
  `n`, `status` and `home`. The upkeep list reads it for page rulings. A live file with no `items` list
  still renders Live work.
- An entry with the wrong shape is counted on the page and in the upkeep list, never dropped. A
  `step` that names no open step goes in the upkeep list.
- With no `--live`, no `threads` or `pulls` list, or a `readAt` that is not an ISO time, the
  line or its stamp says it was not read, and why. A local session's state does not show yet.
  That waits on step o8's option (c): each session writing its own line.

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
- landed feel-fix steps with no valid device trial, in the row `landed, waiting for a device trial`. A
  feel-fix is a step whose `feel` is set to anything but `false` or `null` (decision
  `feel-fix-waits-device-check`, a feel-fix waits for a device trial). Each entry is `<id> (<marks>)`, where `<marks>` is the step's pull request (`#N`), or its
  commit's short hash when no pull request is known. It reads `<id> (<marks>; device trial unreadable)` when
  `deviceCheck` is present but not valid;
- landed steps that wait for triage to close them. A feel-fix step with a valid device trial reads
  `<id> (<marks>; open a try-it item)`. Triage then opens one try-it item (decision
  `feel-fix-waits-device-check`, a waiting-page item of kind `task`) for it, with `ref` set to the step id,
  so no step gets two. Its `Why yours:` line names the device trial and says a feel on a real device is the
  owner's to judge;
- steps marked `doing` or `active` with no live lane or open PR, except a landed feel-fix with no valid
  device trial, which the row above lists. A step is live when a session that is
  not archived has the tag `cs-step:<step id>`, or an open pull request's branch equals the step
  id. Both match the id exactly. The session also needs the tag `cs-repo:<owner>/<repo>` for this
  repo's GitHub name, in any case, because `list_sessions` is account-wide and step ids repeat across
  repos. A session row with no `tags` key, or null `tags`, has no tags and is not skipped. A step
  whose status is none of `todo`, `doing`, `active` or `done` is listed as `<id> (unknown status
  "<status>")`. Each other entry reads `<id> (set to todo)`, or `<id> (set to done: landed in #N)` when
  a `Step:` trailer is on main. Triage sets each step back. The row reads one `unknown (<why>)` entry,
  never an empty list, in these cases:
  - `--live` is missing or unreadable, or has no `sessions` list;
  - a session row or a pull row has the wrong shape;
  - the repo's GitHub name cannot be read;
  - `readAt` is not an ISO time, has no time zone, is over 60 minutes old (an old list counts a dead
    lane as live), or is more than 5 minutes ahead;
- page rulings not on their step: each closed waiting-page item whose `home` is a step that is not
  done, where none of that step's `note`, `why` or `ask` cites the item. The `home` is trimmed, an
  optional leading `step ` (in any case) is dropped, and the rest must equal the step id exactly. A cite
  is the words `item <n>` in any case, with an optional `#` (`page item 9`). Cite each item on its
  own, as `item <n>`. "items 9 and 10" cites neither item, and "item 9 and 10" cites item 9 only.
  Each entry reads `<id> (page item <n>)`. Triage files the ruling on the step's note. The row reads
  one `unknown (<why>)` entry, never an empty list, when:
  - `--live` is missing or unreadable;
  - the live file is not a JSON object;
  - the live file has no `threads` or `pulls` list;
  - `readAt` is not an ISO time, has no time zone, is over 60 minutes old or is more than 5 minutes ahead;
  - there is no `items` list;
  - an `items` row has the wrong shape (`n` not an int, `status` or `home` not a string).

  A skipped session row does not blank this row. An empty `items` list reads zero;
- dated claims to re-check before a lane starts: each `doing` or `active` step whose `note` holds a
  stale claim. A claim is the word `Finding` or `Checked` in any case. No letter, digit or hyphen may
  touch it, so `Findings`, `Rechecked`, `Re-checked` and `c146-checked-map` do not count. A date follows
  within 40 characters, with no `.` or newline between. The date is `Mon D` or `Month D` with an
  optional `, YYYY` or ` YYYY`, or ISO `YYYY-MM-DD`. A month name needs a capital first letter, so
  `May 2` counts and `may 2` does not. A date with no year takes the build year, or the year before if
  it would be in the future. When the newest claim in the note is 5 or more days old, the entry reads
  `<id> (<date as written>)`. Triage asks for a
  re-check of that claim on main before a lane starts. The row reads the notes only, so it needs no
  `--live` file;
- `Step:` trailers that name no step.

## Cost

About six git processes and one file written per build. With `--live`, the publisher's reads add
one `list_threads` walk and one or two GitHub list calls, and one file it writes and the builder
reads. The stale-step row adds one more `list_sessions` walk inside that publish, and three more
fields per session in the file. The page-ruling row adds one `ArtifactData list items` read (every
page) to the same publish. The builder adds no git process, file, timer or log for either row. The
dated-claim row reads the notes already loaded and adds nothing.
No watcher, no timer, no log.

## Tests

`python3 skills/roadmap/test_build.py` in the claude-settings checkout.
