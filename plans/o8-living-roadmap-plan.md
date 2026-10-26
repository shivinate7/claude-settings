# o8: a living roadmap page for every repo (plan)

Plan only. Checked against claude-settings main 7ce2d89, roadmap branch 496ddbc, project-ops PR #618
(head of `pr618`), banchi d0b09df, q_max b47bd003, home-app 01d29e7 (all fetched Oct 26).

## 1. What the page shows, and where each item comes from

One builder reads each item from its one home and stores no copy. Each panel prints the commit or time
it read. A home that does not exist or cannot be read shows "unknown", never "none".

| Panel | Home | Read by |
|---|---|---|
| Steps, phases, numbers, topics | the repo's record branch, `roadmap/data/` (project-ops shape) | git, at build |
| Decisions, debts, debt notes, plans, specs | `lint/layout.json` kinds through `lint/layout.py` (legacy map until the repo rolls out) | git, at build |
| Feedback items and where each went | none yet: o15 (tasks and rulings land in tracked files) makes the home | unknown until o15 |
| Open PRs and branches | GitHub | `gh` or the GitHub API, at build |
| Repo map | the repo's own map (banchi `docs/map.py`, q_max `docs/map/`, claude-settings `docs/catalog.md`) | named per repo in its extras file |
| Compliance-check scores | none: the scorecard lives only in chat | unknown until lane 4 |
| Session-board progress, session plans | this machine's `$.store` and `~/.claude/handoffs/` | local build only; unknown on a cloud build |
| Waiting decisions | c71's waiting page | a link, not a copy |

"When the page opens" (c26, watching costs less than what it watches) becomes "when the page is built":
a published artifact cannot run git. The publisher builds at each wake. No watcher, no timer, no new
log. Cost per build: one `git log` per repo read, one GitHub list call, no file written but the page.

## 2. Layout (design B, the logbook)

The logbook mockup itself (artifact 9H4Ng...) could not be read from here: unknown. Today's
`roadmap/page/index.html` already carries the mockup brief's one theme-token block, so the plan takes
it as the logbook with your UI changes started. Order, top to bottom:

1. **Where you are.** Current phase, active steps, next three, off-track items, and "read at" stamps.
2. **Steps by phase.** Folded to id plus plain title. Done steps struck through and folded away. A step
   with a merged PR shows "landed in #N" until triage closes it.
3. **Health** (from o7): map, compliance scores per rule group, session-board summary. Unknown cells say why.
4. **Records.** Counts of decisions, debts and plans, newest five each, linked to GitHub.
5. **Reference.** Topics and the hand-off guide.

Theme: each repo supplies only the token block (`--repo-name`, accent set, fonts, radii; light and
dark), from its extras file. Status colours stay shared.

## 3. How a merge updates a step

A lane commit carries a `Step: <id>` trailer, beside the `Record-claim` trailer the merge tool already
writes. At build, the builder reads main's log for `Step:` trailers and marks each named open step
"landed in #N". It never closes a step: only triage closes (c55, the gatekeeper ruling). Triage sees the
mark in the upkeep list, closes the step and rewrites its note. A step with no trailer stays as its
JSON says. No hook writes to the record branch from a merge.

## 4. Where the builder lives

Move `build.py` and `page/index.html` from the claude-settings roadmap branch to claude-settings main,
as `skills/roadmap/` (one home, installed on every machine). The record branch keeps only data, briefs
and hand-offs. project-ops (#618) then points at the skill, not at a branch file.
`python3 ~/.claude/skills/roadmap/build.py --repo <checkout> [--record-branch roadmap]`.

## 5. Port to each repo

| Repo | Port | Why (measured) |
|---|---|---|
| claude-settings | yes, first | Has the record and page now; `decisions/` 114, `debts/` 54, legacy paths. |
| banchi | yes, second | `docs/decisions` 256, `docs/debts` 68, `docs/specs` 44, map with `OPEN` build order. No plans folder, no extras, no record branch. The page reads `OPEN` as its step list until a record branch exists, so no second order. |
| q_max | yes, after roll-out | `docs/decisions` 570, `docs/debts` 819, `docs/gaps` 13, open queue in `specs/todo.md`. Counts plus newest only, or the page is unreadable. Last commit Oct 20. |
| home-app | yes, after it has a debt store | No decisions or debts folders. Plan and backlog are `records/plan.md` and `records/backlog.md`, which keep timed counts (a log, not a current record). |
| home | no | Merged into home-app Oct 26. |
| degen, mailaudit | yes, later | Have decisions and debts (degen 39 and 136; mailaudit 220 and 82, root paths). Local clones, not fetched. |
| joyous | yes, later | 11 decisions, no debts. Local clone at Oct 11, not fetched. |
| ios-adblock, adblock-lists | no | 2 debts and 1 file: nothing for a page to show. |

Each yes still needs your word per repo (o16's deferred part). Port of this process: yes, through
project-ops, because every repo with a plan needs a current record you can skim.

## 6. Build lanes, in order

1. **Builder takes a repo.** Move the builder to `skills/roadmap/`, add `--repo`, read layout kinds
   through `lint/layout.py`, print "read at" stamps. Check: built on claude-settings, the page equals
   today's page apart from the stamps (a diff test), and a missing home renders "unknown" (test red first).
2. **Merge marks a step.** `Step:` trailer, builder reads it, "landed in #N", upkeep row for triage.
   Check: a fixture repo with a trailer commit marks only that step; a trailer naming no step is listed.
3. **Records and health panels.** Counts, newest five, repo map from the extras file. Check: build
   on banchi and q_max checkouts, counts equal `ls | wc -l` of each home.
4. **Compliance scorecard gets a home.** compliance-check writes its scorecard lines to a layout kind
   (proposed `docs/health/compliance.md`, one file, rewritten in place; the page is its named reader).
   Check: a run writes the file and the page shows each group's score. Rides with o4.
5. **Live worker state** (waits on the parked question below).
6. **project-ops points at the skill.** One-line edit after lane 1. Check: no path to the roadmap
   branch's build.py left in `skills/`.

Lanes 1 to 3 need no answer from you. Lane 4 joins o4's lane. Lane 5 is deferred.

## 7. Where each worker's live state comes from

Ruling (shiv, Oct 26, waiting page): (a) now, (c) once a local write is measured. The three options
never excluded each other. They are three feeds into one strip, so the only real question was order.

- **(a) Project threads and GitHub, read at build. Built (lane 5).** The publisher reads
  `list_threads` and the open pull requests just before the build and passes them in `--live FILE`
  (`skills/roadmap/SKILL.md`, "Live work"). A thread that names a step tags it. Local sessions do not
  show, and the strip is as old as the last build.
- **(b) session-board's store. Do not add.** It lives on one machine, and the page is built and
  published from the cloud, so it would show only after a build on that machine and go stale between.
  What it holds that (a) lacks (agents, context left, update ready) a local session can put in its
  own (c) line, so (c) covers it.
- **(c) Each session writes its own line to the page's database. Planned below.**

### (c) plan: one line per session in the page's database

c71 measured that a Mac session can write a page's database (liaison, Oct 26). Windows is unknown.

- **Home.** A `live` collection in the published roadmap page's database, one doc per session:
  `live/<session id>` = {title, where ("cloud", "mac", "windows"), state (the same five states as (a)),
  step?, pr?, at (ISO)}. The doc is the session's own; nobody else writes it.
- **When it writes.** Only on a state change: start, waiting on the owner, ready for review, done.
  Never on a timer, never each turn (cost rule: one ArtifactData call per change, no new process,
  no file). A session that is done deletes its doc. A doc older than 6 hours shows as "quiet", not
  as working.
- **Who makes it happen.** A hook cannot call ArtifactData, so the session does it: one paragraph in
  the roadmap skill and one line in the waiting-page skill's protocol (the same moments it already
  writes). The page URL comes from the layout extras, beside the waiting-page key.
- **The page.** The viewer reads `live` from the real database when the page is published, and from
  the baked stub as an empty collection on disk. Rows from (c) merge with (a) by title; (c) wins
  when it is newer.
- **Lane checks.** A fixture database with one fresh doc, one stale doc and one malformed doc: the
  strip shows one working, one quiet and one skipped. Measure first on Windows (local liaison): one
  ArtifactData write from a Windows session. Until then a Windows session reads "unknown".
- **Needs before the lane:** claude-settings' layout roll-out (o2) for the page key, and the Windows
  measure. No answer from shiv is needed.

Port of the live strip: yes, with the builder, because any repo with threads or PRs gains it at no
new cost; (c) ports with the waiting-page skill.
