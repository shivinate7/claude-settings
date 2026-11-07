# A definitive prose claim carries its backing or a route row

## Ruling

Owner goal, 2026-11-06 11:36 CST: every definitive prose claim is backed and verifiable.

Coordinator pick, 2026-11-06 11:47 CST, process-only, reversible: facts about outside behaviour live in one data home, `hooks/route_rows.json`. Prose cites a route row as `(route <id>)` and never restates it. The sibling lane `github-route-claims` builds that file. The term is "route row" (`GLOSSARY.md`).

A route row has the fields `id`, `act`, `route`, `surface`, `outcome`, `measured`, `cc_version`, `evidence`, `by` and `pattern`. `pattern` is a regex over the tool call, read by `hooks/route_match.py` (the route matcher). A row may also carry `alternates`, the other acts that reach the same outcome.

Backing form, 2026-11-06 12:28 CST, process-only: a backing is `(KIND source)`, with KIND from `PREMISE_KINDS` (the kinds list in `hooks/precompact_handoff.py`). The weak kinds `notes` and `assumed` do not back a claim. `(test path::name)` and `(read path:line)` back a claim only if the file exists at head. Spec: Backing form below.

Code spans, 2026-11-06 12:28 CST, process-only: a code span used as a claim's subject still counts as a claim.

Part (v), the owner hand-off check. Coordinator agreed 2026-11-06 12:00 and 12:21 CST, process-only.

- (a) At Stop, report_guard (the Stop check in `lint/report_guard.py`) will refuse an owner hand-off whose "Why yours" line gives a capability reason, unless the line carries a cite that the rulings below allow. It ships as its own PR.
- (b) `hooks/reply_judge.py` (the reply judge) will judge the cite against the route row and the act's alternates. Evidence: PR #1299 (a commit cherry-picked to a new branch, with no refusal).

Lane ruling, 2026-11-06 12:34 CST, process-only: layer (a) checks only "Why yours" lines. A route cite passes only when the row's outcome is refused or asks. A row whose outcome is works refuses the cite. An unknown outcome reads UNKNOWN.

Lane ruling, 2026-11-06 12:47 CST, process-only: a verb in a code span is a mention. A route word in a code span used as the subject counts.

Lane ruling, 2026-11-06 12:47 CST, process-only: the rows path has one home, `rows_path()` in `hooks/route_match.py` (the route matcher).

Coordinator, 2026-11-06 12:59 CST, process-only (option b of the coordinator's cite question): a "Why yours" line with a capability reason needs one of these cites. A capability reason uses a word such as can not, cannot, refuses, blocked or not available. The cites: `(route <id>)` with outcome refused or asks, a refusal from this session, or `(measured <date>, <check and result>)`. A choice, login or safety-kept reason needs no cite.

Lane ruling, 2026-11-06 13:25 CST, process-only, under coordinator pick Q1 (b): a choice, login or safety phrase exempts the line. The capability verbs widen to refused, unable to, denied, forbidden, no access, not allowed or permitted, unavailable and 403. "blocked until" and "not available until" are dependencies, not capabilities. Layer (a) is built in `lint/report_guard.py` (`hand_off_problem`). It reads the reply text. It reads this session's refusals file and the route rows file only for a capability line that needs them.

## Incident

`docs/decisions/session-tiers.md:64` said "The cloud cannot close a pull request". One fact sat in three places: that line, the 2026-10-30 refusals in `docs/decisions/auto-mode-owner-acts.md` (lines 79-82 on origin/main), and the grant "Acts the cloud refuses" in `.claude/CLAUDE.md:16-19`. It stayed on main with no check. Measured 2026-11-06 on origin/main (7975f6d8): a grep of `lint`, `hooks`, `merge` and `actions` finds no check that reads the phrase.

## Backing form

A definitive claim in prose carries one of these backings:

- `(KIND source)`, with KIND from `PREMISE_KINDS` (the kinds list in `hooks/precompact_handoff.py`). The weak kinds `notes` and `assumed` do not back a claim.
- `(route <id>)`, citing a route row.
- `(test path::name)` or `(read path:line)`. Either backs a claim only if the file exists at head.

A code span used as a claim's subject still counts as a claim. A claim with no backing is unbacked.

## STALE005: a capability stated without a backing

STALE005 (the route-claim check) reports a sentence that states a capability by route with no backing. The unit it judges is a sentence in a paragraph the range touches, not a changed line. It is report-only until it measures 10% or fewer false alarms over 20 real hits. Then it refuses. Source for the threshold: coordinator pick Q3 (the threshold question), 2026-11-06 11:47 CST, process-only.

## Falsifiers

When an act contradicts a route row, the falsifier notes it: `hooks/refusal_note.py`, and the Stop read in `lint/report_guard.py`.

## Model judge at merge

`merge/merge.py` will call `invoke_model` (in `hooks/decision_watch.py`) on each line that the reverse map of `lint/stale_cites.py` selects. The reverse map (code to the prose lines that cite it) is planned. The judge is report-only until it is measured on the labelled set. No labelled set exists yet. An error from the model means UNKNOWN, never a pass. The report prints each stale or unbacked line (at most 20, then a count of the rest), then one count line for every line not judged, by cause. A failure of the whole plan prints one UNKNOWN line in place of that count.

## Re-measure on use

Before a fallback route is used, the session tries one act that can be undone, once, and updates that route row.

## Unmeasured

A route row is read as unmeasured when its `measured` date is more than N days old. The reader computes the age at read time, so no timer runs. N is unset.

## Cost

No long-lived process and no timer. Planned cost: one `git diff -U0`-style diff replaces the name-status diff. One `cat-file` read happens only when a line is a claim candidate. A range that changes `hooks/route_rows.json` opens one `cat-file`. When a row id is removed, it also runs one `ls-tree` and reads each tracked `.md`. The merge judge (`judge_paragraph`, `lint/stale_cites.py`) judges each claim sentence that holds an added row. It selects by added row, not by claim line. Model starts: up to 3 per merge, planned and unmeasured. The judge code on this branch starts no model.

## Owner-only

`.claude/CLAUDE.md:16-19`, the grant "Acts the cloud refuses", restates a route fact. Only the owner edits that file. It stays as it is until the owner edits it.

## Status

Planned. Nothing above is built on main, except part (v) layer (a), built in `lint/report_guard.py` (`hand_off_problem`) on this branch and not yet on main. `hooks/route_rows.json` is absent on main.

Planned, not built: the generator that fills the route-rows table in `docs/decisions/auto-mode-owner-acts.md` from `hooks/route_rows.json`.

Kind: build
Plan: docs/plans/pointer-system.md#lanes (all)
Home: lint/stale_cites.py
