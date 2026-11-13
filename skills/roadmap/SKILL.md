---
name: roadmap
description: Use when a session builds a repo's roadmap block, or the user says "build the roadmap", "roadmap page" or "update the status tab". Bakes the steps on the repo's record branch and the record homes in the checkout into the roadmap block of the repo's one page, and prints the upkeep list for triage.
---

A repo has one page: the waiting page. Its Status tab shows the repo's plan from its homes. This
skill publishes no page. The script makes one marked roadmap block, and the page writer splices
it into the live page (see "Publish the roadmap block"). The old roadmap URL retires: it gets no more
publishes. The page's URL is the `waiting-page` key of the layout extras file. The `roadmap` key there
is the `{map, github}` object build.py reads, never a URL. The tab stores
no copy: each panel prints the commit it read, or "unknown" and why.

## Build

Run from any folder:

    python3 ~/.claude/skills/roadmap/build.py --repo <checkout> [--record-branch <branch>] --block --out FILE

`--record-branch` defaults to the extras key `record-branch` in `.claude/layout-extras.json`, else `roadmap`.
With no flag, an extras file that cannot be read warns and reads `roadmap`. A `record-branch` value that is
not a plain git branch name stops the script.

`--block` writes only the roadmap block, the text between `<!-- roadmap:data -->` and `<!-- /roadmap:data -->`. It holds
`window.ROADMAP_DATA` and `window.ROADMAP_BUILD`, and never a database stand-in. With no record branch,
`ROADMAP_DATA` is null and the Status tab says the plan is unknown. Without `--block` the roadmap build script writes
the whole old read-only page. Nothing publishes it.

- **On the record branch.** The checkout stands on the record branch: the roadmap build script reads the working
  tree. Build after each edit to `roadmap/data/`.
- **Anywhere else.** The roadmap build script reads the record branch through the repo history, `origin/<branch>`
  first. Fetch the branch first, because the roadmap block is as old as the fetch.
- `--block` needs `--out`, on either path.

The record homes (decisions, debts, debt notes, plans, specs) come from the checkout, at the paths
`lint/layout.py` gives. A home that is not there reads "unknown", never "none".

## Publish the roadmap block

The page writer alone publishes the page (skill waiting-page, "Update the roadmap block").
This skill never calls `Artifact` for a page.

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
lists the threads, the pull requests and the branches. The roadmap build script cannot reach project threads or
GitHub, so the publisher reads them just before the build and passes one file:

    python3 ~/.claude/skills/roadmap/build.py --repo <checkout> --live live.json --block --out FILE

    {"readAt": "<ISO time of the reads>",
     "threads"?: [{"title", "state", "lastActivity"?, "step"?, "pr"?}],
     "pulls": [{"number", "title", "branch"?, "draft"?, "createdAt"?, "held"?, "reviewLog"?, "head"?, "url"?, "checks"?}],
     "branches": [{"name", "updatedAt"?}],
     "sessions": [{"id", "session_status", "tags", "status_bucket"?}],
     "items": [{"n", "status", "home", "lane"?}]}

- `threads`: `list_threads`, every page. Leave out resolved threads. `state` is the thread state as
  listed. Add `step` only when the thread's brief names it.
- `pulls`: the repo's open pull requests. `createdAt` is GitHub's `created_at` for the pull. It is
  optional. A missing or unreadable `createdAt` is not a wrong shape. The stale-draft row lists it as
  unknown. `head` is the pull's head commit sha, also optional: the lanes-to-archive row reads it to
  release a lane whose draft pull is already in the default branch. `held` and `reviewLog` are optional JSON
  bools (absent means false) that triage fills: `held` is true when the batch runner's hand-in or hold list names
  the pull, `reviewLog` when the pull has a posted review log. The stale-draft row skips a draft with either
  true. A present key must be a JSON bool (`null` counts as non-bool); a pull row with a non-bool value is skipped, so the
  stale-draft, pair, unlaned and lanes-to-archive rows read unknown. `branches`: lane branches with no open pull request.
- `landedPulls` (optional, beside the keys above): `[{"number", "branch", "head"?, "merged"?}]`, the repo's pull
  requests closed in the last 14 days whose base is the default branch, each with its head ref (`branch`), head sha
  (`head`) and GitHub's `merged` flag. Triage's live-file brief must fill it; see "A merge marks a step".
- `sessions`: `list_sessions`, every page, each row copied as it comes with only these fields.
  `status_bucket` is the bucket list_sessions returns (`SESSION_STATUS_BUCKET_WORKING`, `_BLOCKED`, `_REVIEW_READY`, `_COMPLETED`, `_FAILED`);
  it is optional, and a row without it reads as not completed. The upkeep list reads the rows for steps
  in progress and for lanes to archive. A live file with no `sessions` list still renders
  Live work.
- `items`: `ArtifactData list items` of the repo's waiting page, every page, each row copied with only
  `n`, `status`, `home`, `lane` and `owner`. `lane` is where the item's answer went: the lane's slug, a tier name
  such as `batch-runner`, or `null` for none. Copy it when the item has one; leave the key out when the
  page row has none. `owner` is the session that reads the answer, also optional. The build keeps each
  exactly when its key is present. The upkeep list reads the items for page rulings and for lanes to archive,
  and the red line reads `lane` for stalled items. A live file with no `items` list still renders Live work.
- An entry with the wrong shape is counted on the page and in the upkeep list, never dropped. A
  `step` that names no open step goes in the upkeep list.
- With no `--live`, no `pulls` list, or a `readAt` that is not an ISO time, the
  line or its stamp says it was not read, and why. With no `threads` list the read stays valid: pulls still show and only the thread count reads unknown. A local session's state does not show yet.
  That waits on step o8's option (c): each session writing its own line.

## A merge marks a step

A lane commit names its step in a `Step: <id>` trailer, in the last paragraph of the message, beside
the other trailers. Several ids may share one line, split by commas. At build, the roadmap build script reads
the log of `origin/main` (`--main-branch` names another). It marks each named open step "Landed in
#N", where #N is the pull request whose merge put the commit on main. It never closes a step: triage
closes it, from the upkeep list. A trailer that names no step is listed there too.

A step has also landed when the live file's `landedPulls` holds a row for it. The row is
`{"number": int, "branch": str, "head"?: sha, "merged"?: bool}`. It counts when its branch is the step id or
`lane/<id>`, the step is open, and one more test holds. Either `merged` is JSON true, or `head` (7-64 hex) is an
ancestor of main (`git merge-base --is-ancestor`). The row has no base field, so `merged: true` means merged into
main. The build marks that step "Landed in #N" with the row's number. With no main ref in the checkout, nothing
marks, `merged: true` rows included, as with the trailers. A failed merge-base read marks no head-only row. A
`merged: true` row needs no git, but still needs the main ref. A row is counted
in `skipped` when it is not an object, its `number` is not an int, or its `branch` is not text. A row whose
`merged` is present and not a JSON bool is skipped too. Each skipped row, and a `landedPulls` that is not a list, makes the stale-step and
pull readings `unknown (<n> landedPulls rows skipped)`. The publisher (triage) must fill `landedPulls` from
GitHub. It lists the closed pull requests of the last 14 days whose base is the default branch, each with its head
ref, head sha and merged flag. That filter makes `merged: true` mean merged into main. A merge
that drops the `Step:` trailer, or a lane that closes its pull unmerged, then still reads right.

## Refusals

- A file under `roadmap/`, `briefs/`, `plans/` or `handoffs/` on the record branch holds a git
  conflict marker. The roadmap build script names each file and line, and writes no page. Resolve, then build again.
- The checkout is not on the record branch and no `--out` is given.

## The red line

build.py exits 1 when a `todo` step is named by an open pull request. A `ready` step reads as `todo`
here and in the ready todo steps row. It prints
`todo step with an open PR: <id> (#N)` for each pair, writes the page, then exits 1. A pull names a
step when its branch is exactly the step id, or its title holds the id as a whole word, in any case. The
fix is to set the step to `doing`, or to close the pull. With no usable `--live` read of `readAt` and
`pulls` (the `sessions` list is not needed), the line reads
`todo step with an open PR: unknown (<why>)` and build.py exits 0. The conflict-marker refusal also
exits 1. The printed line tells the two apart.

build.py also exits 1 on a stalled step. A `doing` or `active` step with no live lane and no open PR is
stalled until it has a disposition (the same test as the in-progress upkeep row, so the two never
disagree). It prints `stalled step: <id> (resume, pause or done)`, or `stalled step: <id> (done: landed in
#N)` when a `Step:` trailer is on main or a `landedPulls` row proves it, writes the page, then exits 1. A landed feel-fix with no valid
device trial is not stalled; the device row lists it. A step is live by `cs-step:<id>` on
a live session of this repo, or an open pull whose branch is the id or `lane/<id>`. A session whose status
bucket is completed or failed has ended and holds no step; an idle or review ready one still does. The tag value is
read stripped, as idle_lanes reads it. A `cs-topic:` tag never keeps a step live. The page's stalled block lists the ids.

An open waiting-page item whose `lane` is a non-empty text and has no live work is stalled too. It
prints `stalled step: item <n> (lane <slug>: re-route, close or resume)` and exits 1. The lane is live
by the same `cs-step:` tag and pulls, and also by `cs-topic:<slug>`, or `cs-build:<tier>` for a tier lane such as `batch-runner`. A closed item is
never stalled, and a `null` lane names no lane.

With no usable live read the lines read `stalled step: unknown (<why>)` and `stalled step: items
unknown (<why>)`, and build.py exits 0; the page's stalled block then reads not read, never zero. An
open item row with no `lane` key reads the items unknown, so a publisher that does not send `lane` never
passes for zero stalled items.

build.py also prints `ready not started: <id> (<age>h)` for each step with status `todo` or `ready` and
phase `now`. The step needs no live lane (the same test as above), no open pull that names it (the pair line
names the two), and no valid `paused` field. No open item homed on it may lack a lane. The age is whole hours from `updatedAt` to the live read, or `(age unknown)` when `updatedAt`
is missing or has no zone. The same list rides in the build info (`window.ROADMAP_BUILD.ready`). No page draws it yet.
One function, `next_act`, gives each ready step and each stalled step `id`, `act`, `owner` and `age`. A ready
step's act is `start lane`. The owner is the step's `owner` field, else `coordinator`.
A ready step more than `READY_AGE_LIMIT_HOURS` (24, unmeasured) old prints
`ready over limit: <id> (start lane; owner <owner>; age <N>h)`, and build.py exits 1, as on a stalled step. A step
with no age is never over. A `todo` or `ready` step that has landed on main (a `Step:` trailer or a `landedPulls` row) is not listed: it has
no lane to start, and the landed upkeep rows name it. A `todo` or `ready` step with a missing or wrongly cased phase
prints `ready not started: unknown (<id> has no usable phase)` and is not listed. Every build prints
`ready not started count: <N>`, zero included, or `ready not started count: unknown (<why>)` when a phase is unusable.
With no usable live read, or main unread (no step can be shown landed), the list and the count each read
`unknown (<why>)`, never zero, and there is no red line. A ready step inside the limit never changes the exit code.
Unmeasured limits: age counts from the step's `updatedAt`, so a weekend or a note edit moves it; a landed doing step
goes red, but a landed todo step is excluded.

Triage disposes each stalled step by writing, on the record branch, one of three things. It sets the step
`todo` (the lane is gone and the work is not done) or `done` (it landed). Or it adds `paused`:
`{"why": "<text>", "decides": "owner" | "coordinator" | "triage", "at": "<ISO time with a zone>", "by":
"triage"}`.
A valid `paused` field moves the step off the stalled list and into the page's Paused list. A wrong-shaped `paused` field keeps the
step stalled and lists it as a bad pause. That means that a missing or empty `why`, a `decides` outside the set, an `at`
with no zone, or a `by` other than `triage`. Resume is not stored: a live lane makes the step not stalled.

## Mockups

A step's note, why or ask may cite a mockup by its id, `item<N>-<letter>` as a whole token (`item48-a`). The step then
carries the field `mockups`, `{"<id>": "<path>"}`, one entry per cited id. Each path is a repo path under the design folder
(`docs/design/<item folder>/<file>`), and the file is on origin as a file, on any ref under `refs/remotes/origin/` (decision `mockup-home`).

The build judges only open steps (status not done); a done step is skipped. It prints `mockup with no file: <step id> <mockup id> (commit the file under the design folder and push it; if it is pushed, run git fetch)` for each cited id that has no usable file. A cited id misses when it has no entry, or its path is outside the
design folder (a machine-home path, a link or a folder too). It also misses when origin does not hold the file, even if the checkout does. The build writes the
page, then exits 1. The fix is to commit the file, push it, and name it in `mockups`.

A checkout with no origin ref, or a shallow one, cannot show origin. So does a failed git read or an unreadable layout. The entry reads unknown, never a miss or a
pass: the build prints `mockup file unread: <step id> <mockup id> (<why>)` and exits 0.

## Upkeep list

After each build the roadmap build script prints the upkeep list for the triage thread. It names:

- open-step notes that are too long;
- untouched steps and empty notes in a live phase (a phase that holds a `doing` or `active` step). The two rows read `todo`, `ready`, `queued`, `doing` and `active` steps; `blocked` and `folded` steps, and a step with no phase, are never listed;
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
  id or `lane/<step id>`. Both match the id exactly. A `cs-topic:` or `cs-build:` tag never keeps a step live.
  The session also needs the tag `cs-repo:<owner>/<repo>` for this
  repo's GitHub name, in any case, because `list_sessions` is account-wide and step ids repeat across
  repos. A session row with no `tags` key, or null `tags`, has no tags and is not skipped. A step
  whose status is none of the known ones (`todo`, `ready`, `queued`, `blocked`, `folded`, `doing`, `active`, `done`; `KNOWN_STATUS` in `build.py`) is listed as `<id> (unknown status
  "<status>")`. Each other entry reads `<id> (set to todo)`, or `<id> (set to done: landed in #N)` when
  a `Step:` trailer is on main or a `landedPulls` row proves it. Triage sets each step back. The red line prints a `stalled step:` line
  for each entry except an unknown-status one, built from the same test. The row reads one `unknown (<why>)` entry,
  never an empty list, in these cases:
  - `--live` is missing or unreadable, or has no `sessions` list;
  - a session row or a pull row has the wrong shape;
  - the repo's GitHub name cannot be read;
  - `readAt` is not an ISO time, has no time zone, is over 60 minutes old (an old list counts a dead
    lane as live), or is more than 5 minutes ahead;
- `todo` steps whose note has the sentence `Ready.`, in the row `ready todo steps`. A live phase is not
  needed. Each entry is the step id;
- draft pull requests over 12 hours old with no live lane, in the row `draft PRs over 12 h with no live
  lane`. A pull's age is `createdAt` against the live file's `readAt`. A pull has a live lane when a
  live session step equals its branch exactly (the in-progress row also counts a `lane/<id>` branch). An ended
  session holds no draft. A draft whose `held` or `reviewLog` is true is skipped. Each entry is `#N (<branch or
  title>)`. A draft with no readable `createdAt` reads `unknown (#N has no createdAt)`. With no usable
  live file the row reads one `unknown (<why>)` entry;
- page rulings not on their step: each closed waiting-page item whose `home` is a step that is not
  done, where none of that step's `note`, `why` or `ask` cites the item. The `home` is trimmed, an
  optional leading `step ` (in any case) is dropped, and the rest must equal the step id exactly. A cite
  is the words `item <n>` in any case, with an optional `#` (`page item 9`). Cite each item on its
  own, as `item <n>`. "items 9 and 10" cites neither item, and "item 9 and 10" cites item 9 only.
  Each entry reads `<id> (page item <n>)`. Triage files the ruling on the step's note. The row reads
  one `unknown (<why>)` entry, never an empty list, when:
  - `--live` is missing or unreadable;
  - the live file is not a JSON object;
  - the live file has no `pulls` list (a missing `threads` list makes only the thread count unknown);
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
- lanes to archive, in the row `lanes to archive`. A session is listed when all of these hold:
  - its tags hold `cs-build:lane` and this repo's `cs-repo:` tag, and its status is not archived;
  - its `status_bucket` is `SESSION_STATUS_BUCKET_COMPLETED` or `SESSION_STATUS_BUCKET_REVIEW_READY`. A lane that is blocked, failed, working or
    has no bucket is never listed;
  - it has at least one `cs-step:` tag, and each step it names has landed. A step has landed when a
    `Step:` trailer is on main, a `landedPulls` row proves it, or its status is `done`. A step off the record branch has landed only by its trailer;
  - no open pull holds it. A pull holds a lane when its `branch` is a step slug or `lane/<slug>`. A
    draft pull whose `head` sha is already in the default branch (`git merge-base --is-ancestor`)
    releases the lane. A ready pull always holds it. A failed git read reads as not landed;
  - no open page item holds it. An item holds a lane when its `lane` is one of the lane's steps and
    its `status` is not `closed`. An item whose `owner` is the lane's own session id holds the lane the same way.
    The page writes `open` and `closed` only, so only `closed` releases a lane;
  - no step is still doing under it (its `lane` field names the session, status `doing` or `active`, not landed on main). A lane that passes the other tests reads a hold line instead.

  A lane whose only holders are stale drafts reads `joint (close #<n> ...; archive archive/<branch> ...; archive lane
  <session id>)`, and the row counts it. A stale draft is a draft over 12 h old at `readAt`, not held, with no review log,
  a `head` sha (a draft with none gives no joint line) not in the default branch, and no doing step named in its branch
  or title. The lane's session row needs `idle_since` (ISO time with a zone) over 12 h before `readAt` and
  `unarchived_epoch` the JSON int 0 (not false, 0.0 or text). One open pull whose title or branch holds the word
  `records` stops every joint line. The batch runner pushes each branch to `archive/<branch>`, closes each draft, then
  archives the lane. The joint pass reads rows already loaded: no process, file or log of its own.

  An idle lane not to archive now reads `hold (<reason>; lane <session id>)`. The reason is one of three.
  `no cs-step tag`: the archive guard refuses such a lane. A step id that is off the record branch with no
  `Step:` trailer on main. When the lane also carries another repo's `cs-repo:` tag, that reason ends `; also tagged <those tags>`.
  `step <ids> still doing under this lane`: each step whose `lane` is the session, with status doing or active, not landed on main.
  The last clears when the step's status is set to todo or done. A lane that waits (a step not done, an
  open pull, an open item) prints no line, except the joint case below. The row's count leaves holds out. A live file with no `items` list makes the row unknown. An `items` row with the
  wrong shape makes the row unknown. Each entry reads `<session id> (<steps>; topic <cs-topic or ->)`,
  sorted. The row reads one `unknown (<why>)` entry, never an empty list, when:
  - `--live` is missing or unreadable;
  - `readAt` is bad, over 60 minutes old or in the future;
  - there is no `sessions` list, or a session or pull row has the wrong shape (a pull `branch` that is not text or null counts);
  - no live lane row of the repo carries one of the five `SESSION_STATUS_BUCKET_*` names. Archived rows
    are not counted, so only archived lanes, or no live lane rows, read an empty row;
  - main or its git log cannot be read;
  - the record branch has no steps;
  - the repo's GitHub name cannot be read.

  `merge --idle-lanes --live FILE` prints the same list for the batch runner: lane lines and hold lines, then
  a summary line that gives the held count when there are holds. It exits 1, with no summary line, when every entry is unknown;
- `Step:` trailers that name no step;
- `open step waits on a closed unmerged PR`: an open step whose title, why or note waits on PR #N. A wait is a phrase in `WAIT_ON_PULL_PHRASES` in `build.py`. The word `PR` may sit before `#N`. A `#N` followed by `closed` or `merged` is history, not a wait. The row lists the step when `landedPulls` has a row for #N with `merged` false. It skips #N when `landedPulls` has a `merged` true row for #N, or when #N is an open pull. It also skips #N when the head of its `merged` false row is on main (`head_on_main`, as for the landed rows). A PR closed before the 14-day `landedPulls` window is not seen. Each entry is `<step id> (#N)`. The row reads `unknown (the live file has no landedPulls list)` when the live file has no `landedPulls` key. A live read that is unknown, such as no `--live` file, makes the row unknown too. An empty `landedPulls` list reads none. The fix is to name the step slug it waits on in the step's `blockedBy` list (owner, 2026-11-10 13:10 CST);
- `done without check`: a `done` step updated on or after the cutoff (`DONE_CHECK_SINCE`, in the build script) that names no Done check. It is also listed when its note, why and ask hold no `Done check green on main:` (any case) with a `#N`, `PR N`, URL or commit hash right after it. Triage's close writes that line, such as `Done check green on main: #1312.` The instruction is in the Triage bullet of the operating model (skill `project-ops`). A `done` step updated before the cutoff is not judged, because the Done check line had not shipped then.

## Cost

About six git processes, plus up to four when a step cites a mockup, and one file written per build. With `--live`, the publisher's reads add
one `list_threads` walk and one or two GitHub list calls, and one file it writes and the roadmap build script
reads. The stale-step row adds one more `list_sessions` walk inside that publish, and three more
fields per session in the file. The page-ruling row adds one `ArtifactData list items` read (every
page) to the same publish. The roadmap build script adds no git process, file, timer or log for either row. The
dated-claim row reads the notes already loaded and adds nothing.
The red line, the stalled lines, the ready lines and the two stale-ready rows read the live file and steps build.py
already reads. They add no process, file, timer or log. The publisher's `createdAt` per pull row comes from the
GitHub list call it already makes.
The `landedPulls` rows cost the publisher one more GitHub list call (closed pulls) per publish. The closed-pull wait row runs
one `git merge-base` per closed unmerged PR that an open step waits on, once per build. A closed row no open step
waits on runs no git for this row. It writes no file. The landed rows add their own `git merge-base` per distinct head of an unmerged
row whose branch is an open step, and a row with `merged: true` runs no git. They add no file, timer or log.
The mockup check runs at most four git processes per build, however many entries and origin refs (the ref listing, the shallow check, one batched type read, and one batched link read when a ref holds a blob at an entry's path). Check: `test_five_entries_over_fifty_origin_refs_start_at_most_four_git_processes` in `skills/roadmap/test_build.py`. It adds no file, timer or log.
No watcher, no timer, no log.

## Tests

`python3 skills/roadmap/test_build.py` in the claude-settings checkout.
