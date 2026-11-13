# Plan: move each prose store to the shared tending contract

Owner ruling R28 step 3 (plan restart-plan, section 3.14). Decision `prose-tending-contract`. Dies when every
store below is `live` or retired. Audit read 2026-11-12 16:00 CST over main plus origin/roadmap by an Explore agent;
counts are from that read of main at commit d2cce9ec. A later main moves them by a few per cent, so recount before relying on one. Timings are local (Linux). CI cost is unmeasured.

Rule: a store moves when a lane next touches it (R28). This plan names each store's gap, so that lane knows what to build.

Refuter: refuter opus, 2026-11-13, REVISE

Revision taken for findings 2 to 6 of the refuter, settled below. Two simpler routes are declined. One table in the contract plan instead of this plan: this plan keeps its own death condition and the per-store gaps, and the contract plan's table is a different record. Dropping the four new tests: the audit counts 0 stale today. But a test is what finds a stale item, so a lane that moves a store builds only its own test. Open unknown: whether step notes-sightings-expiry's expiry is the `until-date` test or a second one.

## Findings that hold for every store

- Only debts notes, decisions and handoffs have one line per item. Roadmap (0 of 1622 files), queue (0 of 636),
  page copies and the mailbox score 0 on an item regex. A caller must render one line per item first. That
  rendering is the main cost of moving them.
- The shared `home-held` test passes on any ref (about 3000 refs; 3326 at last count). `hooks/ruling_home.py` on main has no `rule:<id>` branch; `lint/tending.py` on this stack has one. Two things serve decisions
  and the feedback log: keep the `rule:` branch on `RULE_FILES` and `ANCHOR_RE` from `lint/check_ruling_kind.py`, and add a main-only read.
- Dated-claim age is read in `skills/roadmap/build.py` (dated claims; `STALE_DAYS`). `hooks/precompact_handoff.py` reads premise stamps and `hooks/guard.py` writes them: related, but neither holds an age check. One shared `checked-age` test could serve handoffs and roadmap.
- The `triage-status` call point has no caller yet. The first step that makes a store run from it wires the point, so the debts, roadmap, queue and mailbox moves each need that step first.
- Fixed in this lane: the `rules` entry named a folder with no anchors (now `claude-md`); the `page-copies` entry named a
  folder absent on main (now `external:waiting-page`).

## Per store

| Store | Item shape read | Real stale today | Next move | Gap to gold (live, tested, one call point) |
|---|---|---|---|---|
| debts (notes.md) | 2211 bullets, 2203 slug first | 0; 1416 `Until` dates fall 11-19 to 11-26, so 130-297 go stale a day from 11-19 | `until-date`, run at triage-status only, where the `mark` close writes marks into notes.md; never at merge-check (every PR would go red) | Moves inside lane prose-debts (step notes-sightings-expiry builds the same expiry); the 129 debt records need a `retire-resolves` test |
| decisions | 245 `Home:` lines in 203 files; 11 of 214 records carry `Plan:` instead | 0 (39 flagged, all `rule:` ids resolve) | Keep the runner's `rule:` branch and add a main-only read (`_Reads.held_main` is a start); then live at merge-check, remeasure in CI (43 s locally) | No full-tree sweep today; the cull stopped 2026-10-19 |
| rules | 98 anchors in `CLAUDE.md` and 29 in `output-styles/shiv-stylisms.md`; the entry's one-id-per-line regex reads 57 of the 98 | 1 false alarm: `building-never-guess-answer`, because `CITE` reads "cites where it was read" as a record id | Widen `where` to both rule files, or have the entry call `lint/rule_audit.py`, which already holds it in CI. Fix `CITE` to skip prose first | Entry reads `CLAUDE.md` only; `output-styles/shiv-stylisms.md` anchors are missed |
| docs | todo.md 18 of 18 lines; plans 1 of 32 | `lint/stale_cites.py --tree`: 159 findings, precision unmeasured | Wrap `stale_cites --tree` after step stale-cites-tree-clean lands; add `step-done` for todo lines | Plans and design have no shape |
| feedback-log | one line per item | 0 | Already `live` at stop and compact (step feedback-log-tends-itself) | Closes by file existence only (debt `feedback-close-reads-file-only`) |
| handoffs | 13 of 13 bullets, but the ids are not all premises | 0; 13 unknown | New `checked-age` test (shared with roadmap) | The store may move (step handoff-lands-tracked-first) |
| roadmap | 0 of 1622 | 2 dated claims | Wrap the existing `upkeep` rows in `skills/roadmap/build.py` (2.7 s) | Needs one rendered line per step; the record branch has no CI |
| queue | 0 of 636 (`home` is free text) | 0; 10 of 15 open homes unknown | A parser for `home`, then `home-held` | Free-text homes |
| page-copies | none | n/a | Do not move: steps waiting-copy-backup-only and retire-page-copy may retire it. An `external:` store is skipped silently at every point, so a live `page-copies` would pass a stale copy; its `runs-from` is now `stop` only: an external store never lists `merge-check` (contract plan). Which point runs it needs an owner pick first | The live source is a claude.ai page a script cannot read; the check cannot catch the 11 h lag |
| mailbox | `Msg <id> from ... re <id> try <n>` | unknown (no mail ref on origin) | `open-age` or close on a `re <id>` reply | No date in the line |

Order by value over cost: debts, decisions, docs, handoffs, then roadmap and queue, then rules; page copies and
the mailbox wait.

The store table in `docs/plans/prose-tending-contract.md` lists `rules` and `waiting-data` where this stack changes them. The lane that makes the first store live updates that table.
