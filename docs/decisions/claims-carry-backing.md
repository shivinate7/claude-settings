# A definitive prose claim carries its backing or a route row

## Ruling

Owner goal, 2026-11-06 11:36 CST: every definitive prose claim is backed and verifiable.

Coordinator pick, 2026-11-06 11:47 CST, process-only, reversible: facts about outside behaviour live in one data home, `hooks/route_rows.json`. Prose cites a route row as `(route <id>)` and never restates it. The sibling lane `github-route-claims` builds that file. The term is "route row" (`GLOSSARY.md`).

A route row has the fields `id`, `act`, `route`, `surface`, `outcome`, `measured`, `cc_version`, `evidence`, `by` and `pattern`. `pattern` is a regex over the tool call, read by `hooks/route_match.py` (the route matcher). A row may also carry `alternates`, the other acts that reach the same outcome.

Backing form, 2026-11-06 12:28 CST, process-only: a backing is `(KIND source)`, with KIND from `PREMISE_KINDS` (the kinds list in `hooks/precompact_handoff.py`). The weak kinds `notes` and `assumed` do not back a claim. `(test path::name)` and `(read path:line)` back a claim only if the file exists at head. Spec: Backing form below.

Code spans, 2026-11-06 12:28 CST, process-only: a code span used as a claim's subject still counts as a claim.

Part (v), the owner hand-off check. Coordinator agreed 2026-11-06 12:00 and 12:21 CST, process-only.

- (a) At Stop, report_guard (the Stop check in `lint/report_guard.py`) refuses an owner hand-off whose "Why yours" line gives a capability reason, unless the line carries a cite that the rulings below allow (read lint/report_guard.py:1461-1470).
- (b) `hooks/reply_judge.py` (the reply judge) judges the hand-off's cite against the cited route row and the act's alternates. When the cited id has no row on this surface, it reads the act from the other surface's row and carries neither that row nor its alternates (read hooks/reply_judge.py:146-152; read hooks/reply_judge.py:174-176).

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

Built, report-only. `merge/merge.py` selects prose lines and sends each file to the model once (read merge/merge.py:2415-2452; read merge/merge.py:2497-2513; read merge/merge.py:2525-2559).

- Selection: each line that cites a changed backing file, from `backed_lines`, the reverse map of code to the prose that cites it (read lint/stale_cites.py:611-628). Plus each non-heading line the range adds to a governed file (read merge/merge.py:2439-2445).
- Call: `decision_watch.invoke_model` with the `LINE_VERDICTS` shape, which reads `holds`, `stale` or `unbacked` per line (read hooks/decision_watch.py:671; read merge/merge.py:2540).
- Cap: 3 files per merge (read merge/merge.py:2412). A file past the cap reads UNKNOWN (read merge/merge.py:2507-2508). The report prints at most 20 lines, then one count line (read merge/merge.py:2557-2558).
- Errors: a model error, a timeout or an unreadable reply reads UNKNOWN, never a pass (read merge/merge.py:2539-2545).
- Report only: the call runs after the lock is released and refuses nothing (read merge/merge.py:2526-2529).

Scored. `lint/prove_route_judge.py` scores the judge on `lint/route_claims_labelled.json`. The file has 21 rows. Each row holds its line text and the commit it was judged at (read lint/route_claims_labelled.json:1-23). Only a `stale` verdict counts against the labels. A false alarm is a TRUE row judged stale. A hit is a STALE, PARTLY_STALE or HALF row judged stale (read lint/prove_route_judge.py:113-131). `unbacked` is counted apart, because no labelled row carries a backing cite. UNKNOWN and HISTORY rows are skipped, and so is a row with no rev (read lint/prove_route_judge.py:39-40, :115-116). Source: "only a 'stale' verdict scores against the labels; 'unbacked' is counted on its own" (lane pick, 2026-11-07 02:46 CST, process-only).

Result, in the record's backing form: `(measured 2026-11-07, lint/prove_route_judge.py: false alarms 0/13 (0.0%), hits 0/4, unbacked 12/17, unknown 4 (model result carried no JSON verdict), skipped 4)`.

What it shows: the judge raised no false alarm, but it found none of the 4 STALE, PARTLY_STALE or HALF rows. On lines without a backing cite it answers "unbacked", not "stale". So it stays report-only. Four such rows are too few for a rate. A score needs more stale rows, or rows that carry a backing cite.

## Re-measure on use

Before a fallback route is used, the session tries one act that can be undone, once, and updates that route row.

Not built, since no code reads a route row before a fallback is used.

## Unmeasured

A route row is read as unmeasured when its `measured` date is more than N days old. Not built: `read_rows` returns each row as written, with no age check (read hooks/route_match.py:61-70). N is unset.

## Cost

No daemon and no timer.

- The range scan starts one `git diff -M --raw -p -z -U0`. It carries the changed names and the added lines that STALE005 reads (read lint/stale_cites.py:1066; read lint/stale_cites.py:257-266).
- Blob reads share one `git cat-file --batch` process. It starts on the first read and closes at the end of the run (read lint/stale_cites.py:150-175; read lint/stale_cites.py:1077).
- The head blob of a file is read only when one of its added lines holds a verb or a route word (read lint/stale_cites.py:722-743).
- A range that changes `hooks/route_rows.json` reads it at base and at head (read lint/stale_cites.py:804-807). A sentence with a route cite reads the head blob once more (read lint/stale_cites.py:828-846).
- When a row id is removed, one `git ls-tree` runs and each tracked `.md` is read (read lint/stale_cites.py:801-826; read lint/stale_cites.py:859-862).
- STALE005's judge, `judge()`, is rule-based and starts no model (read lint/stale_cites.py:769-799).
- The merge takes the changed names from a `--name-only` diff (read merge/merge.py:2859). The merge judge runs its own `git diff -U0` (read merge/merge.py:2436) and up to 3 model starts per merge (read merge/merge.py:2412). Its model starts are unmeasured.

## Owner-only

`.claude/CLAUDE.md:16-19`, the grant "Acts the cloud refuses", restates a route fact. Only the owner edits that file. It stays as it is until the owner edits it.

## Status

Built:

- The route rows file, `hooks/route_rows.json`, and its one path reader, `rows_path()` (read hooks/route_match.py:40-42).
- The falsifier flags: `route_flag` in `hooks/refusal_note.py` (read hooks/refusal_note.py:43) and the Stop read (read lint/report_guard.py:1327-1345).
- Part (v) layer (a), `hand_off_problem`, run at Stop (read lint/report_guard.py:1461-1470; read lint/report_guard.py:1928).
- The reply judge's route block (read hooks/reply_judge.py:146-152).
- STALE005, report-only (read lint/stale_cites.py:705-710).
- The merge's model judge, report-only (see Model judge at merge).
- A labelled set that can score the merge judge (see Model judge at merge).

Not built:

- The generator that fills the route-rows table in `docs/decisions/auto-mode-owner-acts.md` from `hooks/route_rows.json`. The table is empty between its markers (read docs/decisions/auto-mode-owner-acts.md:31-32).
- The row-age reader (see Unmeasured).
- The judge is unmeasured beyond the run above (see Model judge at merge).

Kind: build
Plan: docs/plans/pointer-system.md#lanes (all)
Home: lint/stale_cites.py
