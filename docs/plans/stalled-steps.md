# Plan: stalled steps (lane doing-needs-live-lane)

Goal (owner, 2026-11-06 11:39 CST): a step's shown state is true by construction. A `doing` or
`active` step with no live lane and no open PR shows STALLED until it gets a disposition.

## build.py (skills/roadmap/build.py; do not touch `live_work`)

- Split `unlaned` (~:1020) into a structured core `laneless(open_, marks, work)` returning
  `(why, [(id, fix)])`, fix = "todo" or the landed marks. Keep the feel-fix skip and the liveness
  set. `unlaned` formats today's strings from it; its upkeep row output does not change. Unknown
  status entries stay in `unlaned` only and never count as stalled.
- Add `stalled(steps, marks, work)` -> `{"why", "steps": [{"id","fix"}] | None, "paused": [ids],
  "badPause": [{"id","why"}]}`. `steps` is None only when `why` is set (unknown). Never `[]` for unknown.
- Disposition field on a step, written by triage only: `"paused": {"why": str non-empty,
  "decides": "owner"|"coordinator"|"triage", "at": ISO with zone, "by": "triage"}`. A valid one
  removes the step from `steps` and lists it in `paused`. A wrong-shaped one keeps the step stalled
  and lists it in `badPause`. Resume is not stored: a live lane makes the step not stalled. Done is
  status `done`.
- `main()`: set `info["stalled"]` before the page is written (with no data: why "unknown (steps unknown)").
- `STALLED_LINE = "stalled step"`. Print `stalled step: <id> (resume, pause or done)`, or
  `stalled step: <id> (done: landed in #N)` when landed; unknown prints `stalled step: unknown (<why>)`.
- Exit: `if pairs or misses or stalled_steps: raise SystemExit(1)`, after the page is written.
  Unknown exits 0.

## Waiting-page items (scope add, coordinator 2026-11-06 11:45 CST)

- An open item (status not `closed`) whose `lane` is a non-empty string and is not live joins the
  stalled list: `info["stalled"]["items"] = [{"n","lane"}] | None`, with `itemsWhy`-style reason.
- Lane liveness: a slug lane is live when an open pull's branch equals it. It is also live when a
  live session in this repo carries `cs-step:<slug>` or `cs-topic:<slug>`. A tier lane, such as `batch-runner`, is live
  when a live session in this repo carries `cs-build:<tier>`. One liveness helper serves steps and items.
- `live_work` keeps only n/status/home today; the item `lane` field comes from lane
  idle-lane-archive. Until `lane` reaches the parsed rows, items read unknown (exit 0). Do not
  parse the file a second time.
- Printed: `stalled step: item <n> (lane <slug>: re-route, close or resume)`; unknown prints
  `stalled step: items unknown (<why>)`.

## Pages

- skills/waiting-page/page.html: a stalled band at the top of the Status tab (beside `liveWork()`
  ~:2976, mounted first in `build()` ~:3252). Unknown: a not-read line plus its reason. Else
  "Stalled: N" with id, title, "Resume, pause or done"; items as "Item N: answer routed to <lane>;
  lane gone"; paused steps in a `<details>` "Paused: N" with why, who decides, when. Zero: "No
  stalled step". `stepRow` gets a Stalled or Paused tag like `landed`.
- skills/roadmap/page/index.html: the same band, edits inside the build blocks only.

## Docs

roadmap SKILL.md (red line, upkeep, live-file shape, `paused` field); waiting-page SKILL.md
(exit 1 on a stalled line: splice, publish, then dispose); project-ops operating-model.md (triage
disposes stalled steps at each publish); README.md.tmpl; GLOSSARY.md rows "stalled step", "paused step".

## Rulings (coordinator, 2026-11-06 11:48 CST, process picks reported to the owner)

1. Backlog: an audit classifies each stalled step against its done check on main; triage writes
   each disposition (done -> done; unstarted or partial -> todo with a note; waits -> paused with
   who decides). The hold lands after that commit.
2. Hold: build exit 1 plus triage's Stop refuses to end a wake while `stalled step:` lines print.
3. Pages: a live `doing` step reads "In progress"; otherwise the Stalled or Paused tag.

## Part 2: ready-not-started (coordinator scope add, 11:48 CST)

- build.py prints `ready not started: <id> (<age>h)` for each step with status `todo` or `ready`,
  phase `now`, no live lane, no valid `paused` field, and no open unanswered page item homed on
  it. Age is whole hours from `updatedAt` to the live read. `info["ready"]` carries the list. The
  lines never change the exit code. Doing steps stay with the stalled view.
- `ready` is a known status, read as todo.
- The `Unstarted:` refusal is held (coordinator pick A, 2026-11-06 14:38 CST): debt
  `unstarted-guard-held` (the Unstarted guard waits on paused fields and a re-measure).

## Red run

Base 7975f6d (the merge of batch 30). Command: `python3 skills/roadmap/test_build.py`. The new cases
fail on the base: 45 failures. StalledStep fails 16 times in 11 cases, StalledItem fails 5 times, and the
re-pointed StaleInProgress and FeelRows cases fail 24 subtests (they now expect exit 1 where a step
is stalled). On this branch the same command passes.

Triage hold, lint/test_report_guard_stalled.py on d23c7bc94: 12 failed, 11 passed.
Fix round 1, test_build.py on 8e7186568: 3 failed.

Round 2, lint/test_report_guard_stalled.py on 57c242324: 3 failed.
