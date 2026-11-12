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
- Verdicts are per line, so a repeated id never merges two lines; `close` marks only a stale line.
- Command line: `python3 lint/tending.py --point <call point> [--store S] [--root R]`. A store runs only
  when its `state` is `live` and its `runs-from` names the point. Exit 1 when the contract is malformed, a
  live store's file is missing, or (at `merge-check`) a live store holds a stale item. `merge-check` writes
  nothing; `stop`, `compact` and `triage-status` close stale lines. A file that cannot be read (non-UTF-8)
  or a bullet line whose shape the item regex misses prints `unknown <store>: <why>` and exits 0. A store
  asked for by `--store` that does not run at the point prints `skipped <store>: <why>`. A store with
  `where: external:<name>` has no file: the caller supplies the text.

## Cost (proved by a test)

No new timer, watcher or process. Call points import the module in the process they already run.
The merge check adds two steps (the fixture suite and the contract check) to the existing `checks` job. Files written: only the store's own file, and only by
the close step, only when a verdict changed. Reads: the store file plus the reads its `home-held`
test already makes.

## Steps

1. This step: contract, runner, decision, tests, entries for all stores (`declared`).
2. feedback-log-tends-itself: the feedback log is the first `live` store (R27 points 1-4).
3. prose-tending-move-stores: deeper audit, then each store goes live when a lane next touches it.
