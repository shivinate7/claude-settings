# Plan: shiv-stylisms rules table

Read-only table. No rule changes in this pull request. The owner signed the six changes (ruling `own-807-a`). A later lane edits the style file.

- Roadmap step: `stylisms-rules-table`. Ruling `own-795-a-stylisms-table` (owner, 21:39 CST Nov 13, waiting-page item 795, pick a).
- Base: origin/main 309fa5ed5. Written: 21:42 CST Nov 13. Revised: 23:26 CST Nov 13.

## Summary

- Real rule count in `output-styles/shiv-stylisms.md` on main: **29** (counted with `grep -o 'rule:[a-z0-9-]*'`; each mark appears once). The older text says 23, so it is stale.
- Verdicts: **23 keep, 6 change, 0 drop** (29 total). Owner ruling `own-800-stylisms-two-keeps` (22:24 CST Nov 13) turned two rows to keep: `style-offer-screen-takeover` and `style-press-has-link`. Owner ruling `own-807-a` (22:28 CST Nov 13, via triage) signed the six changes. The 23 keeps stand as the table's verdicts.
- Prior audit: restart-plan R41 (owner 13:36 CST Nov 11, "r41 yes on all") found the output style "in the right folders" and earning "their place": a placement check. R44 part 3 sends the content (are its rules still right) to R35's review, which the owner signs. This table is that review's rule-by-rule read.
- The file is 92 lines and 1144 words. Four rules hold 40% of the words: `style-question-form` 210, `output-never-hand-off-doable-step` 116, `style-hand-off-runs-as-is` 67, `style-hand-off-irreversible` 61 (454 of 1144; the sum of those four counts).
- Cloud limits: no `guard.log` here, so no rule's fire rate is measured. Every "unmeasured" below means that. Mechanism and size are read from `lint/rule_mechanisms.json` and the file.

## Gold standard, used in every row

A rule earns its place when it meets three tests. (a) A hook, a check or a named reader enforces it. (b) It is stated once. (c) It loads only where it matters.

## Table

Mechanism words in the Evidence column come from `lint/rule_mechanisms.json` (guard, check, judgment, unmechanized). "Judge" means `hooks/reply_judge.py` flags it; it never refuses (decision `reply-judge-samples-never-refuses`).

| Rule mark | The rule in a few words | Verdict | Evidence | Recommendation |
|---|---|---|---|---|
| `output-start-with-point` | Lead with the result | keep | Judge rule (in `JUDGED_RULES`). Fire rate unmeasured. | Keep. |
| `style-cut-narration` | Cut narration and recaps | keep | Judge rule. Fire rate unmeasured. | Keep. |
| `style-limits-kept-silently` | Name a limit only when it blocks or changes the plan | keep | Judge rule. Fire rate unmeasured. Root `building-never-drop-item-silently` covers the dropped-item half. | Keep. |
| `output-tracking-turn-one-line` | Tracking turn gets one line | keep | Judgment, no check (rule map). Unmeasured. | Keep. |
| `output-landing-turn-ends-with-report` | Landing turn ends with the report | keep | Check: `lint/report_guard.py`, tests 61, 64, 67 in `lint/test_report_guard.py`. | Keep. |
| `output-never-echo-agent-report` | Never echo a report or describe a screenshot | keep | Unmechanized (rule map: no check compares reply to report). Unmeasured. | Keep. |
| `style-simple-answer-short` | Simple question gets 1 to 3 sentences | keep | Judgment. Unmeasured. 12 words. | Keep. |
| `style-full-detail-on-request` | Give full detail when asked | keep | Unmechanized. 12 words; it protects the owner's override of the short rules. | Keep. |
| `style-keep-critical-full` | Errors, warnings, destructive confirmations stay full | keep | Unmechanized. Unmeasured. | Keep. |
| `style-correct-over-brief` | Never trade correctness for brevity | keep | Judgment. 8 words. | Keep. |
| `reports-blockquote-no-fence` | Report in one blockquote, no code fence | keep | Check: `lint/report_guard.py`, test 03 (code fence in blockquote blocks). | Keep. |
| `style-plain-words` | Plain words everywhere | change | Unmechanized (no jargon list). 47 words; its last sentence points to root `speak-one-name-per-thing`, and root `output-write-in-ste` also covers plain writing. Unmeasured. | Cut to one sentence; keep the pointer to root. |
| `style-question-form` | Question form: goal, problem, based-on, departs-from, gain/lose | change | Guard: `question-form` (`hooks/question_form.py`). 13 lines, 210 words (18% of the file). R41 item 5 already says the decision should state what the code does. The guard enforces the form, so the prose repeats the check. This reverses decision `question-form`, "Text" bullet: today this rule holds the form, and the `waiting-page` skill points to it. | Shrink to a pointer to decision `question-form` plus the one line of intent; keep the guard. |
| `style-question-inside-box` | Put all a question needs inside the box | change | Unmechanized (a hook cannot see the box). Root `questions-go-to-owner` already holds the box rules and "no box while work runs". Its one unique clause is "text before the box may not show". | Fold that clause into `style-question-form`; drop the rest. |
| `output-never-hand-off-doable-step` | Do an act yourself before handing it over | keep | Judge rule; the judge reads every report with Input Needed (decision `reply-judge-samples-never-refuses`). Named in 8 files, against 7 for `style-question-form` (grep over docs, hooks, lint, skills, agents, root `CLAUDE.md`, `.claude`; the rule map, the style file and this plan left out). | Keep. Candidate to trim later; 116 words. |
| `style-hand-off-cleanup` | A thing you made, you clean up | change | Unmechanized; rule map says no hook sees branches, test ids or data. 19 words. Same topic as `style-hand-off-irreversible` (acts and their cleanup). | Merge into `style-hand-off-irreversible`. R41 item 4 (restart-plan) ruled that the hand-off bullet splits. Commit 48eb533ef6 ("Split the hand-off rule into seven short bullets") made seven rules. This merge partly reverses that split; the owner signed it (`own-807-a`). |
| `style-hand-off-irreversible` | Irreversible act: one yes or no, cleanup named | keep | Judgment. Unmeasured. | Keep; takes the cleanup line. |
| `style-hand-off-runs-as-is` | Handed block runs as is, in its own fence | keep | Judge flags a command with no runnable block (rule map). 67 words. | Keep; takes the one-shell line. |
| `style-hand-off-gh-login` | gh block starts with `gh auth switch` | keep | Guard: `gh-login-switch` for the waiting page; judge for chat. Decision `act-in-place`. | Keep. |
| `style-hand-off-one-shell` | One shell per pasted block | change | No check. The judge files it under `output-never-hand-off-doable-step`, because `JUDGED_RULES` names no id for it (rule map). 24 words. | Merge into `style-hand-off-runs-as-is`. Partly reverses the R41 item 4 split, as above. |
| `style-offer-screen-takeover` | Offer to take over the screen where a tool can | keep | Unmechanized (no hook sees which screen tools exist). Zero mentions outside the file and the rule map (grep over docs, hooks, lint, root `CLAUDE.md`, `.claude`). Whether sessions ever act on it: unmeasured. | Keep (owner ruling own-800-stylisms-two-keeps, 22:24 CST Nov 13). |
| `style-press-has-link` | A press step carries a link | keep | Guard: `press-link` (reads words; misses verbs outside its list). Applies only on the waiting page; `skills/waiting-page/SKILL.md` already names press and links (8 matching lines by grep). | Keep in the style file with its guard (owner ruling own-800-stylisms-two-keeps, 22:24 CST Nov 13). |
| `style-command-in-item` | Command sits in the item's `command` field | change | Guard: `command-in-item`. `skills/waiting-page/SKILL.md` line 127 already defines the `command` field `{powershell, mac}`. Same home problem. | Move to the waiting-page skill; keep the guard. |
| `style-table-gold-column` | Comparison table has a gold-standard column | keep | Code in `hooks/reply_judge.py` finds a table and sends it to the judge. Judge rule. | Keep. |
| `style-time-central-24h` | Times in US Central, 24-hour, with zone | keep | Hook `hooks/local_time.py` is on main and wired in `settings.json` (lines 359 and 370). The rule map entry says the hook is "not yet on main"; that is stale. The hook gives the clock; no check reads the reply's zone. | Keep. Rule map entry needs its own fix (not in this pull request). |
| `style-no-unmeasured-estimate` | No time estimate without a measured range | keep | Judgment. Unmeasured. | Keep. |
| `style-status-is-report` | Status question gets the report shape | keep | Judgment. Root `reports-order-of-labels` holds the shape; this rule holds the trigger. | Keep. |
| `style-offer-override-line` | Offer a refusal's override line as a ready answer | keep | Judgment. Unmeasured. | Keep. |
| `style-wrong-session-one-line` | Wrong session named: one line, then route | keep | Judgment. Root `speak-one-name-per-thing` cites this mark by id, so it is the one home. | Keep. |

## Counts

- keep: 23
- change: 6 (`style-plain-words`, `style-question-form`, `style-question-inside-box`, `style-hand-off-cleanup`, `style-hand-off-one-shell`, `style-command-in-item`)
- drop: 0

If the six changes stand: 29 marks become 25 (three merges into other rules, one move to the waiting-page skill). Word effect is unmeasured.

## What the owner signed

The six `change` rows (ruling `own-807-a`, 22:28 CST Nov 13). This pull request changes nothing in `output-styles/shiv-stylisms.md`. A later lane edits the file, red test first where a check cites a mark (`outcomes-tests-are-statements`).
