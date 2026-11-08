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

Coordinator, 2026-11-07 14:36 CST, process-only: the waiting page judges a task's "Why yours" line by guard rule `task-why-cited`. It accepts a route-row cite and a dated measured cite only, and reads no refusals file, so a backtick tool-name cite does not pass there.

## Incident

`docs/decisions/session-tiers.md:64` (origin/main 7975f6d8) said "The cloud cannot close a pull request". One fact sat in three places: that line, the 2026-10-30 refusals in `docs/decisions/auto-mode-owner-acts.md` (lines 79-82 on origin/main), and the grant "Acts the cloud refuses" in `.claude/CLAUDE.md:16-19`. It stayed on main with no check. Measured 2026-11-06 on origin/main (7975f6d8): a grep of `lint`, `hooks`, `merge` and `actions` finds no check that reads the phrase.

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

Built, report-only. `merge/merge.py` selects prose lines and sends each file to the model once (read merge/merge.py:2459-2496; read merge/merge.py:2559-2575; read merge/merge.py:2599-2641).

- Selection: each line that cites a changed backing file, from `backed_lines`, the reverse map of code to the prose that cites it (read lint/stale_cites.py:613-630). Plus each non-heading line the range adds to a governed file (read merge/merge.py:2483-2489).
- Call: `decision_watch.invoke_model` with the `LINE_VERDICTS` shape, which reads `holds`, `stale` or `unbacked` per line (read hooks/decision_watch.py:675; read merge/merge.py:2617). The prompt also carries an excerpt of each backticked path a line names but does not cite, when the line also names another backticked name or number: the lines of that file within 3 of each of its lines that holds one of those names (read merge/merge.py:2544-2553; read lint/stale_cites.py:652-681).
- Cap: 3 files per merge (read merge/merge.py:2454). The lines of a file past the cap read UNKNOWN, counted under "past the call cap" (read merge/merge.py:2571-2572). The report prints each stale or unbacked line, at most 20, then one count line for the rest (read merge/merge.py:2635-2636).
- Errors: a model error, a timeout or an unreadable reply reads UNKNOWN, never a pass. The report prints one UNKNOWN count line for every line not judged, by cause, with no raw error text (read merge/merge.py:2617-2624; read merge/merge.py:2640). A failure of the whole plan prints one UNKNOWN line in place of that count (read merge/merge.py:2633).
- Report only: the call runs after the lock is released and refuses nothing (read merge/merge.py:2600-2602).

Scored. `lint/prove_route_judge.py` scores the judge on `lint/route_claims_labelled.json`. The file has 38 rows. Each row holds its line text and the commit it was judged at (read lint/route_claims_labelled.json:1-23). Only a `stale` verdict counts against the labels. A false alarm is a TRUE row judged stale. A hit is a STALE, PARTLY_STALE or HALF row judged stale (read lint/prove_route_judge.py:113-131). `unbacked` is counted apart, because no labelled row carries a backing cite. UNKNOWN and HISTORY rows are skipped, and so is a row with no rev (read lint/prove_route_judge.py:39-40, :115-116). Source: "only a 'stale' verdict scores against the labels; 'unbacked' is counted on its own" (lane pick, 2026-11-07 02:46 CST, process-only).

Result, in the record's backing form: `(measured 2026-11-07, lint/prove_route_judge.py: false alarms 0/13 (0.0%), hits 3/21, unbacked 19/34, unknown 10 (model result carried no JSON verdict), skipped 4)`.

What it shows: the judge raised no false alarm, and it found 3 of the 21 STALE, PARTLY_STALE or HALF rows. On lines without a backing cite it answers "unbacked", not "stale". So it stays report-only. Whether 21 such rows are enough for a rate is unmeasured. A score needs more stale rows, or rows that carry a backing cite.

## Re-measure on use

Before a fallback route is used, the session tries one act that can be undone, once, and updates that route row.

Not built, since no code reads a route row before a fallback is used.

## Unmeasured

A route row is read as unmeasured when its `measured` date is more than N days old. Not built: `read_rows` returns each row as written, with no age check (read hooks/route_match.py:61-70). N is unset.

## Cost

No daemon and no timer.

- The range scan starts one `git diff -M --raw -p -z -U0`. It carries the changed names and the added lines that STALE005 reads (read lint/stale_cites.py:1120; read lint/stale_cites.py:257-266).
- Blob reads share one `git cat-file --batch` process. It starts on the first read and closes at the end of the run (read lint/stale_cites.py:150-175; read lint/stale_cites.py:1131).
- The head blob of a file is read only when one of its added lines holds a verb or a route word (read lint/stale_cites.py:776-797).
- A range that changes `hooks/route_rows.json` reads it at base and at head (read lint/stale_cites.py:858-861; not pinned: no test counts these reads). A sentence with a route cite reads the head blob once more (read lint/stale_cites.py:882-900).
- When a row id is removed, one `git ls-tree` runs and each tracked `.md` is read (read lint/stale_cites.py:855-880; read lint/stale_cites.py:913-916).
- STALE005's judge, `judge()`, is rule-based and starts no model (read lint/stale_cites.py:823-853).
- The merge takes the changed names from a `--name-only` diff (read merge/merge.py:2941). The merge judge runs its own `git diff -U0` (read merge/merge.py:2480) and up to 3 model starts per merge (read merge/merge.py:2454). Its model starts are unmeasured.

## Owner-only

`.claude/CLAUDE.md:16-19`, the grant "Acts the cloud refuses", restates a route fact. Only the owner edits that file. It stays as it is until the owner edits it.

## Status

Built:

- The route rows file, `hooks/route_rows.json`, and its one path reader, `rows_path()` (read hooks/route_match.py:40-42).
- The falsifier flags: `route_flag` in `hooks/refusal_note.py` (read hooks/refusal_note.py:43) and the Stop read (read lint/report_guard.py:1327-1345).
- Part (v) layer (a), `hand_off_problem`, run at Stop (read lint/report_guard.py:1484-1509; read lint/report_guard.py:1944).
- Part (v) on the waiting page: guard rule `task-why-cited` refuses a task's Why yours line that gives a capability reason with no route-row or dated measured cite (`why_cited_hit` in hooks/question_form.py; the verdict is `why_yours_verdict` in lint/report_guard.py).
- The reply judge's route block (read hooks/reply_judge.py:146-152).
- STALE005, report-only (read lint/stale_cites.py:759-764).
- The merge's model judge, report-only (see Model judge at merge).
- A labelled set that can score the merge judge (see Model judge at merge).

Not built:

- The generator that fills the route-rows table in `docs/decisions/auto-mode-owner-acts.md` from `hooks/route_rows.json`. The table is empty between its markers (read docs/decisions/auto-mode-owner-acts.md:31-32).
- The row-age reader (see Unmeasured).
- The judge is unmeasured beyond the run above (see Model judge at merge).

Kind: build
Plan: docs/plans/pointer-system.md#lanes (all)
Home: lint/stale_cites.py
