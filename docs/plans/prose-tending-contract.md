# Plan: one shared tending contract and runner

Owner rulings R27 and R28 (plan restart-plan, section 3.14). Decision `prose-tending-contract`.
Dies when steps feedback-log-tends-itself and prose-tending-move-stores ship.

Refuter: refuter opus, 2026-11-12, REVISE

Revision taken for gaps (a) to (e), settled below. Simpler route declined: `external:` and `copy-matches-live` are in use, and dropping `delete` would change lint/tending.py, which this revision adds.

## Contract (lint/layout.json, key "tending")

One entry per prose store: `where` (a layout kind, or `external:<name>` for a store outside the repo),
`item` (a regex whose first group is the id), `still-true` (the name of one test in `lint/tending.py`),
`close` (`mark` adds a `[closed]` token, `delete` drops the item, `none` only reports), `runs-from`
(a subset of `merge-check`, `stop`, `compact`, `triage-status`), and `state` (`live` or `declared`).
A `declared` store is named but no call point runs it yet.

### Stores at this head

All ten are `declared`. Each item is a regex, described here in words. Its group 1 is the id, except in `decisions` and `docs`, where it is the home path.

| Store | Where | Item | Still true | Close | Runs from |
|---|---|---|---|---|---|
| decisions | `decisions` | a `home:` line | home-held | none | merge-check |
| rules | `rules` | a rule anchor in a rule file | cite-resolves | none | merge-check |
| docs | `plans` | a `Home:` line | home-held | none | merge-check |
| debts | `debt-notes` | a bullet | until-date | mark | merge-check, triage-status |
| handoffs | `external:handoffs` | a bullet | home-held | mark | stop, compact |
| feedback-log | `external:feedback-log` | a bullet with `[tag] ->` | home-held | mark | stop |
| roadmap | `external:roadmap` | a bullet | until-date | none | triage-status |
| queue | `external:queue` | a bullet | home-held | mark | triage-status |
| page-copies | `waiting-data` | a bullet with `copy of` | copy-matches-live | none | merge-check, stop |
| mailbox | `external:mailbox` | a bullet | until-date | mark | stop, triage-status |

Test use: `home-held` in five stores, `until-date` in three, `cite-resolves` in one and `copy-matches-live` in one. Close use: `mark` in five stores and `none` in five. No store uses `delete`. Five stores use `external:`, which is a `where` form, not a close mode.

No store needs two still-true tests. A store that needs two cannot be written today: `still-true` takes one name, and a list makes the runner exit with a traceback (open note `tending-still-true-unhashable`). Such a store would need one combined test added to `TESTS` in lint/tending.py.

An external store never lists `merge-check`. CI has no file to read for it, and the runner reads no file for an external store at any point. No check in the code refuses that combination yet. The rule rests on this plan, and a check that enforces it is open work.

## Runner (lint/tending.py)

- `tend(entry, text, root)` returns one row per open item line: (line index, id, verdict), the verdict
  `true`, `stale` or `unknown`. `entry` is one store's entry in the layout.
  Never `true` for a read that could not run (rule `verification-report-unknown-reads`).
- `close(entry, text, verdicts)` returns the rewritten text; `[closed]` marking is idempotent.
- Shared tests: `home-held` (the item's home is a tracked file or `step:<slug>` on some ref, a `rule:<id>`
  whose anchor is in CLAUDE.md or output-styles/shiv-stylisms.md, or the `process-only` value, which is true),
  `until-date` (a dated claim past its date), `cite-resolves` (an id cite still names a record),
  `copy-matches-live` (a copy equals its live source).
- Verdicts are per line, so a repeated id never merges two lines; `close` marks only a stale line.
- Command line: `python3 lint/tending.py --point <call point> [--store S] [--root R]`. A store runs only
  when its `state` is `live` and its `runs-from` names the point. Exit 1 when the contract is malformed or a
  live store's file is missing. It also exits 1 when a live store holds a stale item at `merge-check`, or when
  a stale item at `stop`, `compact` or `triage-status` has `close` set to `none`. `merge-check` writes nothing; `stop`, `compact` and
  `triage-status` close the stale lines of a store whose `close` is `mark` or `delete`. A file that cannot be read (non-UTF-8)
  or a bullet line whose shape the item regex misses prints `unknown <store>: <why>` and exits 0. A store
  asked for by `--store` that does not run at the point prints `skipped <store>: <why>`. A store with
  `where: external:<name>` has no file: the caller supplies the text.

Call points at this head: only the merge check. The `checks` job in `.github/workflows/checks.yml` runs
the fixture suite and `lint/tending.py --point merge-check`. At this head no hook, script or compaction step
imports the runner. The next step, feedback-log-tends-itself, is not merged. Its branch imports the runner
only in `hooks/feedback_guard.py`, in `tend_text` and `close_settled`. The Stop hook reaches it there. The
compaction note reaches it through `feedback_guard`, which `hooks/precompact_handoff.py` imports and whose
`needs_work_ids` calls `tend_text`.
No step named here wires `triage-status`. A store is `live` only once a call point runs it, so the step
that first makes a store running from `triage-status` live wires that point.

## Cost (proved by a test)

No new timer, watcher or long-lived process. The merge check adds two steps to the existing `checks` job of
`.github/workflows/checks.yml`: `Prose tending fixture suite` and `Prose tending contract check`. When CI runs a step, the step starts one short process. The Stop, compaction and triage-status points are meant to import
the module in the process they already run. None does yet.

Files written: the store's own file, by the close step only, and only where a verdict changed. The merge
check writes none. Reads: the store's files, none for an external store, whose text the caller supplies. The tests read
more: the rule files for a `rule:` home, the record folders for `cite-resolves`, and the live source for
`copy-matches-live`. The runner also reads the layout files and loads the `hooks/` modules it imports on
first use, plus the git reads that `home-held` makes. A run lists the refs once and reads each home once.

Proof, in `lint/test_tending.py`:
- `test_import_starts_no_thread_or_timer` and `test_import_starts_no_child_process`: importing the runner
  starts no thread, timer or child process.
- `test_home_held_store_starts_only_git_reads`: the home test starts only git reads.
- `test_store_of_several_files_lists_refs_once_per_run` and
  `test_store_of_several_files_reads_each_home_once_per_run`: one ref listing and one read per home in a run.
- `test_no_file_is_written_when_no_verdict_changed`, with its control `test_a_changed_verdict_is_written`:
  a run with no changed verdict writes nothing.
- `test_merge_check_leaves_the_store_file_byte_identical`: the merge check writes nothing.

No test pins the two CI steps. CI runs them.

## Steps

1. This step: contract, runner, decision, tests, entries for all stores (`declared`).
2. feedback-log-tends-itself: the feedback log is the first `live` store (R27 points 1-4).
3. prose-tending-move-stores: deeper audit. When a lane next touches a store, that store goes live.
