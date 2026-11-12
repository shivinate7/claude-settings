# Plan: one shared tending contract and runner

Owner rulings R27 and R28 (plan restart-plan, section 3.14). Decision `prose-tending-contract`.
Dies when steps feedback-log-tends-itself and prose-tending-move-stores ship.

## Contract (lint/layout.json, key "tending")

One entry per prose store: `where` (a layout kind, or `external:<name>` for a store outside the repo),
`item` (a regex whose first group is the id), `still-true` (the name of one test in `lint/tending.py`),
`close` (`mark` adds a `[closed]` token, `delete` drops the item, `none` only reports), `runs-from`
(a subset of `merge-check`, `stop`, `compact`, `triage-status`), and `state` (`live` or `declared`).
A `declared` store is named but no call point runs it yet.

## Runner (lint/tending.py)

- `tend(store, text, root)` returns a verdict per item: `true`, `stale` or `unknown`, and the close step.
  Never `true` for a read that could not run (rule `verification-report-unknown-reads`).
- `close(store, text, verdicts)` returns the rewritten text; `[closed]` marking is idempotent.
- Shared tests: `home-held` (the item's home is a tracked file or `step:<slug>` on some ref),
  `until-date` (a dated claim past its date), `cite-resolves` (an id cite still names a record),
  `copy-matches-live` (a copy equals its live source).
- Command line: `python3 lint/tending.py --point <call point> [--store S] [--root R]`; exit 1 when a store
  with `state: live` and `runs-from` naming the point holds a stale item that its close step cannot fix, or
  when the contract itself is malformed.

## Cost (proved by a test)

No new timer, watcher or process. Call points import the module in the process they already run.
The merge check adds one step to an existing CI job. Files written: only the store's own file, and only by
the close step, only when a verdict changed. Reads: the store file plus the reads its `home-held`
test already makes.

## Steps

1. This step: contract, runner, decision, tests, entries for all stores (`declared`).
2. feedback-log-tends-itself: the feedback log is the first `live` store (R27 points 1-4).
3. prose-tending-move-stores: deeper audit, then each store goes live when a lane next touches it.
