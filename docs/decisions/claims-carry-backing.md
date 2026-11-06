# A definitive prose claim carries its backing or a route row

## Ruling

Owner goal, 2026-11-06 11:36 CST: every definitive prose claim is backed and verifiable.

Coordinator pick, 2026-11-06 11:47 CST, process-only, reversible: facts about outside behaviour live in one data home, `hooks/route_rows.json`. Prose cites a route row as `(route <id>)` and never restates it. The sibling lane `github-route-claims` builds that file. The term is "route row" (`GLOSSARY.md`).

A route row has the fields `id`, `act`, `route`, `surface`, `outcome`, `measured`, `cc_version`, `evidence` and `by`.

## Incident

`docs/decisions/session-tiers.md:64` said "The cloud cannot close a pull request". One fact sat in three places: that line, the 2026-10-30 refusal in `docs/decisions/auto-mode-owner-acts.md` (lines 84-86), and the grant "Acts the cloud refuses" in `.claude/CLAUDE.md:16-19`. It stayed on main with no check. Measured 2026-11-06 at 7975f6d8: a grep of `lint`, `hooks`, `merge` and `actions` finds no check that reads the phrase.

## Backing form

A definitive claim in prose carries one of two backings:

- A premise line: `[<kind>]`, where the kind is one of `PREMISE_KINDS` in `hooks/precompact_handoff.py`, then `Source: <where>`. The form is set by decision `premise-format` (the premise format record).
- `(route <id>)`, citing a route row.

A claim with neither backing is unbacked.

## STALE005: a capability stated without a backing

STALE005 (the route-claim check) reports a changed line that states a capability by route with no backing. It is report-only until it measures 10% or fewer false alarms over 20 real hits. Then it refuses.

## Falsifiers

When an act contradicts a route row, the falsifier notes it: `hooks/refusal_note.py`, and the Stop read in `lint/report_guard.py`.

## Model judge at merge

`merge/merge.py` calls `invoke_model` (in `hooks/decision_watch.py`) on each line that the reverse map of `lint/stale_cites.py` selects. The reverse map (code to the prose lines that cite it) is planned. The judge is report-only until it is measured on the labelled set. No labelled set exists yet. An error from the model means UNKNOWN, never a pass.

## Re-measure on use

Before a fallback route is used, the session tries one act that can be undone, once, and updates that route row.

## Unmeasured

A route row is read as unmeasured when its `measured` date is more than N days old. The reader computes the age at read time, so no timer runs. N is unset.

## Cost

No long-lived process and no timer. One extra `git diff -U0` start in the ste-lint step per changed-scope run.

## Owner-only

`.claude/CLAUDE.md:16-19`, the grant "Acts the cloud refuses", restates a route fact. Only the owner edits that file. It stays as it is until the owner edits it.

## Status

Planned. Nothing above is built on main. `hooks/route_rows.json` is absent on main.

Kind: build
Plan: docs/plans/pointer-system.md#lanes (all)
Home: lint/stale_cites.py
