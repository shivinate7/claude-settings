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
- `(test path::name)`, `(read path::name)` or `(read path:line)`. Each backs a claim only if the file exists at head.

A code span used as a claim's subject still counts as a claim. A claim with no backing is unbacked.

## STALE005: a capability stated without a backing

STALE005 (the route-claim check) reports a sentence that states a capability by route with no backing. The unit it judges is a sentence in a paragraph the range touches, not a changed line. It is report-only until it measures 10% or fewer false alarms over 20 real hits. Then it refuses. Source for the threshold: coordinator pick Q3 (the threshold question), 2026-11-06 11:47 CST, process-only.

## Falsifiers

When an act contradicts a route row, the falsifier notes it: `hooks/refusal_note.py`, and the Stop read in `lint/report_guard.py`.

## Model judge at merge

Built, report-only. `merge/merge.py` calls the model judge once per merge, after the `merge: #N merged as ...` line and before the ff (read merge/merge.py::prose_judge_report) (test merge/test_merge.py::ProseJudge). Planned, not built: the call moves after the `deleteBranch` block (after ff, afterMerge, the branch delete and `cut_lanes`), still after the merged-as line and inside the merge lock. The model call waits at most 60 s (read hooks/prose_judge.py::MERGE_TIMEOUT) while the lock is held.

Selection is `changed_sentences` in `lint/stale_cites.py`: each sentence of a governed Markdown paragraph that the PR adds a line to. It takes paragraphs with `touched_paragraphs` and splits them with `sentence_spans` (read lint/stale_cites.py::touched_paragraphs) (read lint/stale_cites.py::sentence_spans) (test lint/test_stale_cites.py::SelectionTests).

The judge is `merge_findings` in `hooks/prose_judge.py` (read hooks/prose_judge.py::merge_findings). It makes one `invoke_model` call (read hooks/decision_watch.py::invoke_model), with the sentences, the route rows at the merged sha, and each repo file a sentence names, read at that sha. The prompt is capped at 200000 characters (read hooks/prose_judge.py::PROMPT_CAP) and says what it cut (test hooks/test_prose_judge.py::case_h_an_oversized_input_is_capped_and_the_prompt_says_what_it_cut).

Output lines: `merge: #N prose judge: <path>:<line>: <why>` per finding; `merge: #N prose judge: no finding (report-only).`; `merge: #N prose judge: no changed prose to judge.` (no call made).

The judge never refuses. A model error, timeout, odd answer or exception prints `merge: #N prose judge: unknown (<reason>).`, never a pass and never a hold. The merge lands either way (test merge/test_merge.py::ProseJudge).

Flip to refusing: the owner's call, once findings show 10% or fewer false alarms over 20 real findings, the STALE005 threshold (coordinator pick Q3, 2026-11-06 11:47 CST, process-only). The labeller is the named reader: they read each finding from merge output and mark it real or false. No log is written.

## Re-measure on use

Before a fallback route is used, the session tries one act that can be undone, once, and updates that route row.

## Unmeasured

A route row is read as unmeasured when its `measured` date is more than N days old. The reader computes the age at read time, so no timer runs. N is unset.

## Cost

No long-lived process and no timer. One `git diff -M --raw -p -U0` gives the paths and the added lines (read lint/stale_cites.py::read_diff). One `cat-file` read happens only when a line is a claim candidate. A range that changes `hooks/route_rows.json` opens one `cat-file`. When a row id is removed, it also runs one `ls-tree` and reads each tracked `.md`. STALE005 (`judge_paragraph`) selects each claim sentence that holds an added row, not each claim line (read lint/stale_cites.py::judge_paragraph).

The model judge starts one model per merge that adds governed prose, and none otherwise (test merge/test_merge.py::ProseJudge). Each call copies the login credential file into a temp dir when one exists, and deletes that dir after the call (read hooks/decision_watch.py::_judge_isolation) (read hooks/decision_watch.py::invoke_model). Git starts on every merge: `merge-base` and `diff` (read lint/stale_cites.py::changed_sentences). With changed prose, the judge adds one `cat-file --batch`, once a governed Markdown file gets added lines. It adds one `git show` of the route rows file at the merged sha, and one per distinct repo path a sentence names, up to 40 (read merge/merge.py::PROSE_FILES_MAX). A path missing at the merged sha starts again each time a sentence names it (read merge/merge.py::prose_judge_call). The prompt is capped at 200000 characters, not the reads (read hooks/prose_judge.py::PROMPT_CAP). It leaves no process or timer running (read hooks/decision_watch.py::invoke_model).

## Owner-only

`.claude/CLAUDE.md:16-19`, the grant "Acts the cloud refuses", restates a route fact. Only the owner edits that file. It stays as it is until the owner edits it.

## Status

Built on main. Part 1, route rows and falsifiers, is PR #1355 (read hooks/route_rows.json; read hooks/refusal_note.py). Part 2, STALE005, is PR #1328 (read lint/stale_cites.py::RouteClaimReader). Part 3, the hand-off cite, is PR #1360 (read lint/report_guard.py:1461). The reply judge's route rows are on main too (read hooks/reply_judge.py:146).

Part 4, the model judge at merge, is built on lane `prose-judge-at-merge` and is not on main yet (test merge/test_merge.py::ProseJudge).

Not built: the generator that fills the route-rows table in `docs/decisions/auto-mode-owner-acts.md` from `hooks/route_rows.json`. No file in lint, hooks, bin, actions or merge names that page path (measured 2026-11-07, git grep on origin/main 2c67fc4b0). Only `hooks/test_auto_mode_allow.py` names the decision, `auto-mode-owner-acts`, and it is a test, not a generator (read hooks/test_auto_mode_allow.py).

Kind: build
Plan: docs/plans/pointer-system.md#lanes (all)
Home: lint/stale_cites.py
