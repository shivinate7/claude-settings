# Plan: Global CLAUDE.md scope audit

Read-only audit. Nothing moves until the owner signs off the results.

Refuter: refuter opus, 2026-11-11, PARTIAL (5 findings, all fixed in head 0dc9fef19: 6f94a10 premise, project-ops home, load test on every stop-an-act row, rule-audit cost, step 3 as proposal; dropping the gold-standard column left to the owner)

- Roadmap step: the CLAUDE.md scope audit, id `global-claude-md-scope-audit`. Step 1 of 3.
- Related step: child CLAUDE.md dedupe, id `child-claude-md-dedupe`.
- Base: origin/main 6892e6419.
- Written: 2026-11-11 22:55 CST. Revised: 2026-11-11 23:08 CST.

## Goal

Map each section of the root `CLAUDE.md` to the repos and session roles where it matters. For each section, propose one home: stay global, a path-scoped rule in `.claude/rules/`, or an existing skill. This record proposes only. It does not decide.

Gold standard, used in every row of the scope table: a rule loads only in sessions that need it, and each rule is stated once.

## Premise

The owner wrote these on the roadmap note for this step:

- 12:38 CST Nov 11: "im wondering whether i properly keep claude.md's just at the repo level and claude-settings level as its parent and no where further"
- 12:40 CST Nov 11: `"yes that's fine it would need my sign off (the actual results of the review) but just marking it as an item for review is good to do now"`

Ruling R35 (in `docs/plans/restart-plan.md`, line 821) records the owner's read at 12:39 CST: the levels are right. The levels are global, repo, and path-scoped rules in `.claude/rules/`. Restart plan line 734 adds that the output style's 23 rules join this review.

The note cites commit 6f94a10 for R35. It is on `origin/restart-plan`, with the subject "plan: R35 global CLAUDE.md weight review, owner signs off results (owner 12:38, 12:40 CST)". Checked with `git branch -r --contains 6f94a10`.

## Measured

- Root `CLAUDE.md`: 108 lines and 3,890 words by `wc -w`. Remove the 98 rule anchors (`<!-- rule:... -->` comments) and 3,694 prose words remain.
- Size check: `lint/check_claude_md_size.py` counts lines, not words. Its limit is 200 lines (`MAX = 200`). It warns and never fails. Today it prints `ok` at 108 lines. Its test, `lint/test_check_claude_md_size.py`, asserts line counts at 200 and 201. Proposal: step 3 changes the check and its test to count words.
- Rule audit: `lint/rule_audit.py` reads anchors only from `RULE_FILES` (line 91): `CLAUDE.md` and `output-styles/shiv-stylisms.md`. Its docstring says a rule recorded in any other file is "ungoverned here". `lint/rule_mechanisms.json` holds 121 rows: 98 root anchors and 23 output-style anchors. The check fails when an anchor has no row (lines 451-453). It also fails when a row names no anchor left in the rule files (lines 455-459). Any problem exits 1 (lines 584-587). CI runs it at `.github/workflows/checks.yml` line 334. Run on this branch: PASS.
- Cost of a move: an anchor moved out of those two files makes the audit fail, unless its row is removed or `RULE_FILES` is extended. Removing a row drops that rule from the audit. Extending `RULE_FILES` to the new homes is code work. Proposal: step 3 does it, once the owner signs off.
- The check's docstring says Claude Code loads each `CLAUDE.md` whole into every session. The note says the global file "loads in every turn of every repo". Per-turn cost: unmeasured.
- Per the header of `.claude/CLAUDE.md`, the root file loads in every repo. Not measured here.
- Section totals add to 3,694. Group totals add to their section totals.
- Checked by reading: the candidate homes named below exist. That covers `.claude/rules/hooks.md` (`paths: hooks/**`), `output-styles/shiv-stylisms.md`, `bin/verdict`, and the skills in `skills/`: `ci-hygiene`, `design-explore`, `design-review`, `fresh-prose`, `impeccable`, `plain-english-map`, `project-ops`, `waiting-page`.

## Section totals

| Section | Lines | Prose words | Rule anchors |
|---|---|---|---|
| Title and Outcomes first | 1-12 | 274 | 6 |
| Roles | 13-39 | 1,081 | 16 |
| Parallelism | 40-46 | 301 | 6 |
| Shared trees | 47-51 | 115 | 7 |
| Git | 52-59 | 324 | 13 |
| Verification | 60-73 | 229 | 12 |
| Tokens | 74-80 | 138 | 8 |
| Building | 81-90 | 361 | 13 |
| Speak plainly | 91-95 | 245 | 4 |
| Output | 96-100 | 334 | 5 |
| Reports | 101-104 | 258 | 8 |
| Compact instructions | 105-108 | 34 | 0 |
| Total | 1-108 | 3,694 | 98 |

Method: a one-line Python count on the worktree file. Words are whitespace tokens after the anchor comments are removed. A per-anchor count is the words since the previous anchor, so it can include the sentence before it.

## Scope by group

"Needed before first file read" asks whether the rule must be in view before the session's first read. "Stops an act" asks whether the rule stops or limits an act, so it must load before that act (the load test, see Method notes). Both come from reading the rule's text. They are not measured. Repo conditions are quoted from the rules.

| Group | Words | Where it matters | Needed before first file read | Stops an act? | Candidate home | Gold standard |
|---|---|---|---|---|---|---|
| **Outcomes first** | | | | | | |
| Judge by outcome; stale decisions | 75 | Every session | Yes. It frames all judgement. | No | Stay global | One short frame. Stale-decision steps stated once. |
| Tests are claims | 33 | Sessions that edit tests | No | No | Stay global | Stated once. |
| Grant covers named act | 29 | Any session that acts on a grant | No | Yes: a grant covers only the act it names | Stay global | Stated once. |
| Mechanize rules | 137 | Sessions that build hooks, checks or logs | No | No | Stay global. Its exception already sits in `.claude/rules/hooks.md`. | Global states the goal. The hooks rule states the exception. |
| **Roles** | | | | | | |
| Pick role; solo lane | 131 | Spawner sessions (coordinator or lane). The pick comes first. | Yes, for spawner and lane sessions | Yes: the pick line comes before the work | Stay global. Skill `project-ops` fires only on an owner ask for session roles, not at the pick. | Pick line first, stated once. |
| Spawner agent rules | 346 | Spawner sessions only (glossary term "spawner") | No. Needed before the first agent starts. | Yes: the model ceiling refuses Opus spawns; the plan refuter gate | Stay global, or a new skill that loads on spawn (does not exist today) | Only spawner sessions load these. Each cap cites its decision once. |
| Briefs and proof layers | 132 | Spawners writing briefs. Repos with tests and CI. | No | No | Stay global, or a new skill that loads on spawn (does not exist today). `ci-hygiene` names CI config, not test layers. | Brief fields live in one place. |
| Review round cap | 449 | Spawner sessions that run reviews | No | Yes: the round cap stops a fourth round and holds unsafe changes | Stay global, or a new skill that loads on spawn (does not exist today) | Largest group. Round rules stated once. |
| Resume agents | 23 | Spawner sessions | No | Yes: "never fresh" | Stay global, or a new skill that loads on spawn (does not exist today) | With the spawner rules. |
| **Parallelism** | | | | | | |
| Fan-out; own lane | 62 | Any session that starts agents or lanes | No | No | Stay global | Stated once. |
| No mid-task talk; lane caps | 75 | Spawner and lane sessions | No | Yes: no mid-task talk; no guessed caps | Stay global, or a new skill that loads on spawn (does not exist today) | Stated once. |
| Keep going; queue | 164 | Coordinator and lane sessions, when a lane ends | No | Yes: the ask-first list stops acts that cannot be undone | Stay global. `project-ops` does not fire at lane end. | Ask-first test in one place. |
| **Shared trees** | | | | | | |
| No destructive git; archive; no machine-wide kill | 65 | Any session in a shared tree (worktrees). Child repos: unmeasured. | No. Needed before any git write. | Yes | Stay global | Global. It guards every repo. |
| Own ports; confirm; reverify; absolute delete path | 50 | Same as above | No. Needed before any git write or delete. | Yes: confirm before a write; no delete after a `cd` | Stay global | Global. |
| **Git** | | | | | | |
| Main only by PR; no failing merge; cloud gh refused | 53 | Repos with pull requests (the section's own condition) | No. Needed before a merge. | Yes | Stay global | One merge rule, stated once. |
| No merge during batch CI | 21 | Repos with pull requests that batch lanes | No. Needed before a merge. | Yes: stops a merge while the batch run is in progress | Stay global | Global. |
| CI wait and wake rules | 54 | Any session that waits on CI | No | No | None fits today. Skill `ci-hygiene` fires on CI config edits, slow, queued or flaky CI, batching and red batch runs. It does not name a CI wait. | Stated once, in one home. |
| Output and remedy | 20 | Any session that runs git | No | Yes: never discard output | Stay global | Short. Stated once. |
| Record ids and files | 74 | Repos with records (`docs/decisions/`, `docs/debts/`, `docs/plans/`) | No | Yes: never allocate a numbered record on a branch | Skill `fresh-prose`. Its description fires on writing "decision records", before the write. It covers docs and records, not chat replies. | Record rules in the record skill. |
| Batch into one integration branch | 102 | Repos with pull requests that batch lanes | No | Yes: only the integration PR goes ready | Skill `ci-hygiene`. Its description fires on "batches lane PRs into one integration branch", before the batch starts. The merge stays global (see "No merge during batch CI"). | The rule stays in the file. The steps stay in ci-hygiene. No copy. |
| **Verification** | | | | | | |
| Screen verdict | 25 | Repos with screens (the rule's condition) | No | Yes: a verdict per screen before done | Skill `design-review`. Its description fires "after a change to a screen in a repo that has screens". | Screen verdict rule with design-review. |
| Browser login; screen-capture line | 32 | Sessions that drive a browser or capture the owner's screen | No | Yes: use the owner's login only when needed; say before a capture | Stay global. No skill fits. | Stated once. |
| Trust a guard after red | 13 | Sessions that build or change guards (`hooks/`) | No | No | Path-scoped rule `.claude/rules/hooks.md` (exists; `paths: hooks/**`). It loads on a read of a hooks file, before an edit. | Loads only when a session edits `hooks/`. |
| Cry-wolf rule (includes the route-around step) | 43 | Any session that meets a refusal | No | Yes: "Before you route around a refusal, read the guard's record." | Stay global. A path rule would not load in a session that never reads `hooks/`. | Stated once. |
| Fixtures and recovery | 34 | Any repo with checks and recovery controls | No | No | Stay global. `ci-hygiene` fires on CI config edits. This rule also covers tests and recovery controls. | Stated once. |
| Checked reader for numbers | 14 | Sessions that write docs and records | No | No | Skill `fresh-prose`. Its description says it binds "each claim to a check". | One home. |
| Verify against repo; never dry-run; newest that passes; unknown reads | 68 | Any repo | No | Yes for "never dry-run a refusal list" | Stay global. No skill description names these. | Each rule in one home. |
| **Tokens** | | | | | | |
| Never load a long document whole | 16 | Every session | Yes. It governs the first read. | Yes | Stay global | Stated once. |
| Read the map first | 12 | Repos with `map.config.json` (the rule's `docs/map/` condition) | Yes, before answering how code works | Yes: no answer before the map is read | Skill `plain-english-map`. Its description fires "before answering how code in this repo works", in a repo with `map.config.json`. | Map rule lives with the map skill. |
| Folder rules | 25 | Rule upkeep: moving a section to a path-scoped rule | No | No | Stay global | Stated once. |
| Compaction keep list | 23 | Every session at compaction | No. Needed at compaction. | No | Stay global | One compaction list, with Compact instructions below. |
| Command output (verdict) | 46 | Sessions that run checks. `bin/verdict` exists in this clone. Child repos: unmeasured. | No | Yes: never scroll a log to find a verdict | Stay global | One tool, one rule. |
| Brief and report reads | 16 | Spawner sessions | No | Yes: never paste a brief in | Stay global, or a new skill that loads on spawn (does not exist today) | With the brief rules. |
| **Building** | | | | | | |
| Never guess; port keeps behaviour; ambiguity; no dropped items | 84 | Any session that builds or ports code | No | Yes: never guess; a question goes to the owner only when the work departs from main | Stay global | Stated once. |
| One home; allow list is the constant | 43 | Repos with code | No | Yes: an allow list points at the constant | Stay global | The allow list points at the constant, never a copy. |
| Guards need incidents | 95 | Sessions that build guards or checks (here: claude-settings) | No | No | Path-scoped rule with `paths: hooks/**` and `lint/**` (new file, or extend `hooks.md`). Proposal. | Loads only when a session edits a guard or check. |
| Fix cause; scanners | 67 | Any session. Scanners: sessions that write one. | No | No | Stay global. A path rule would miss a scanner written outside `lint/` and `hooks/`. | One home. |
| Designs, memory, comments | 72 | Design rule: sessions that make a design. Memory: every session. Comments: repos with code. | No | No | Design rule: fit unclear, stay global until step 2. Memory and comments: stay global. | Each rule sits with its own kind of work. |
| **Speak plainly** | | | | | | |
| Ids and one name per thing | 219 | Every reply, plan and doc | No | No (a style rule) | Stay global. Skill `fresh-prose` covers docs and records only, so it would miss replies and plans. `GLOSSARY.md` already holds the terms. | Global keeps one line. Terms live in the glossary. |
| Prose rules (no explanation in a paragraph; rewrite superseded text in place) | 26 | Every writer | No | No | Stay global. The "Superseded text" section of `fresh-prose` covers docs only. | Stated once. |
| **Output** | | | | | | |
| Write plainly | 11 | Every reply | No | No | Output style `output-styles/shiv-stylisms.md`. It already holds the reply rules, and `RULE_FILES` reads it. | Reply style in the output style only. |
| Replies and evidence | 82 | Every reply | No | Yes: never paste a passing run's output; answers go to a home | Stay global. | Each rule once. |
| Questions to owner | 241 | Any session that asks the owner | No. Needed before the first question. | Yes: the stop line (no question box while agents run) | Split. The stop line stays global, as one pointer. The rest goes to skill `waiting-page`, whose description fires when "a session has a question, a decision or a task for the owner". The rest's word count is unmeasured. | Full rule in the skill. The stop line in global. |
| **Reports** | | | | | | |
| Labels and content | 92 | Every session's final report | No. Needed at report time. | Yes: no report when nothing landed | Stay global (the order applies to every report) | Order and labels stated once. |
| Batch pace numbers | 126 | Spawner or batch-runner sessions, at each batch merge | No | No | Stay global. `ci-hygiene` covers batching and red runs, not the merge. | With the merge rules. |
| Offer sweep | 40 | Any session whose last PR merged | No | No | Stay global. No skill in `skills/` names the sweep. | Fit unmeasured. |
| **Compact instructions** | | | | | | |
| Compact instructions | 34 | Every session at compaction | No. Needed at compaction. | No | Stay global | One list, shared with the compaction rule in Tokens. Two lists exist today. |

## Rule anchors by group

Each id takes the plain name of its group. Words per id follow the id.

- **Judge by outcome; stale decisions** (75): `outcomes-judge-by-outcome` 24, `outcomes-decision-is-argument` 16, `outcomes-stale-decision-protocol` 35.
- **Tests are claims** (33): `outcomes-tests-are-statements` 33.
- **Grant covers named act** (29): `outcomes-grant-covers-named-act` 29.
- **Mechanize rules** (137): `outcomes-mechanize-rules` 137.
- **Pick role; solo lane** (131): `roles-pick-mode-from-request` 63, `roles-solo-reviews-logic-diffs-only` 55, `roles-solo-grows-switch-to-orchestrate` 13.
- **Spawner agent rules** (346): `roles-orchestrator-never-builds` 97, `roles-one-role-per-agent` 45, `roles-model-per-role-table` 24, `roles-sonnet-is-the-ceiling` 76, `roles-plan-gets-refuter` 60, `roles-opus-shaped-say-so` 30, `roles-opus-override-guarded` 14.
- **Briefs and proof layers** (132): `roles-brief-contents` 46, `roles-each-layer-proves-once` 86.
- **Review round cap** (449): `roles-review-cap-three` 360, `roles-findings-are-debts-or-notes` 56, `roles-third-round-steps-up` 33.
- **Resume agents** (23): `roles-resume-by-name` 23.
- **Fan-out; own lane** (62): `parallelism-each-own-checkout` 33, `parallelism-own-lane-orchestrator` 29.
- **No mid-task talk; lane caps** (75): `parallelism-no-mid-task-talk` 19, `parallelism-argue-max-parallelism` 14, `parallelism-no-guessed-lane-cap` 42.
- **Keep going; queue** (164): `parallelism-keep-going` 164.
- **No destructive git; archive; no machine-wide kill** (65): `shared-trees-no-destructive-git` 15, `shared-trees-archive-then-delete` 28, `shared-trees-no-machine-wide-kill` 22.
- **Own ports; confirm; reverify; absolute delete path** (50): `shared-trees-own-ports-data` 15, `shared-trees-confirm-before-write` 14, `shared-trees-reverify-after-incident` 6, `shared-trees-delete-names-absolute-path` 15.
- **Main only by PR; no failing merge; cloud gh refused** (53): `git-main-only-by-pr` 25, `git-never-merge-failing-ci` 4, `gh-write-cloud` 24.
- **No merge during batch CI, retired** (21): cites of `git-no-merge-during-batch-ci` 21. Its replacement is `git-red-main-reverts`.
- **CI wait and wake rules** (54): `git-ci-wait-checks-in` 36, `git-ci-done-comment-wakes` 18.
- **Output and remedy** (20): `git-never-discard-output` 11, `git-remedy-never-names-target` 9.
- **Record ids and files** (74): `git-slug-then-claim-number` 33, `git-cite-by-id` 10, `git-record-own-file-per-kind` 10, `git-one-record-per-question` 21.
- **Batch into one integration branch** (102): `git-integration-branch-merge` 102.
- **Screen verdict** (25): `verification-screens-verdict` 25.
- **Browser login; screen-capture line** (32): `verification-browser-login-only-needed` 16, `verification-announce-own-screen` 16.
- **Trust a guard after red** (13): `verification-trust-guard-after-red` 13.
- **Cry-wolf rule** (43): `verification-cry-wolf-guard-is-spent` 43.
- **Fixtures and recovery** (34): `verification-green-proves-only-its-fixtures` 13, `verification-recovery-independent-of-state` 21.
- **Checked reader for numbers** (14): `verification-checked-reader-for-numbers` 14.
- **Verify against repo; never dry-run; newest that passes; unknown reads** (68): `verification-verify-against-repo` 10, `verification-never-dry-run-refusal-list` 5, `verification-newest-that-passes` 26, `verification-report-unknown-reads` 27.
- **Never load a long document whole** (16): `tokens-never-load-whole-doc` 16.
- **Read the map first** (12): `tokens-read-map-first` 12.
- **Folder rules** (25): `tokens-folder-rules-load-by-path` 25.
- **Command output** (46): `tokens-verdict-not-stream` 27, `tokens-run-through-verdict` 19.
- **Brief and report reads** (16): `tokens-point-brief-at-files` 9, `tokens-read-report-not-transcript` 7.
- **Compaction keep list** (23): `tokens-compacting-keep-essentials` 23.
- **Never guess; port keeps behaviour; ambiguity; no dropped items** (84): `building-never-guess-answer` 10, `building-port-keeps-behaviour` 60, `building-surface-ambiguity` 7, `building-never-drop-item-silently` 7.
- **One home; allow list is the constant** (43): `building-one-home-per-capability` 24, `building-allow-list-is-the-constant` 19.
- **Guards need incidents** (95): `building-guard-needs-incident` 47, `building-mistake-names-its-guard` 48.
- **Fix cause; scanners** (67): `building-fix-cause-not-symptom` 17, `building-scanner-respects-strings` 50.
- **Designs, memory, comments** (72): `building-land-design-or-abandon` 33, `building-memory-is-short-term` 25, `building-comments-say-why` 14.
- **Ids and one name per thing** (219): `speak-cite-id-plus-gloss` 62, `speak-one-name-per-thing` 157.
- **Prose rules** (26): `speak-never-explain-in-paragraph` 7, `speak-rewrite-superseded-in-place` 19.
- **Write plainly** (11): `output-write-in-ste` 11.
- **Replies and evidence** (82): `output-never-paste-passing-output` 27, `output-bring-decisions-as-question` 11, `output-answer-has-a-home` 44.
- **Questions to owner** (241): `questions-go-to-owner` 241.
- **Labels and content** (92): `reports-order-of-labels` 8, `reports-done-format` 25, `reports-done-names-models` 20, `reports-drop-unused-label` 7, `reports-name-unstarted-items` 27, `reports-no-report-when-nothing-landed` 5.
- **Batch pace numbers** (126): `reports-batch-pace-numbers` 126.
- **Offer sweep** (40): `reports-offer-sweep-after-merge` 40.

## Method notes and risks

- The load test. A rule that stops or limits an act must load before that act. A skill loads only when its description's trigger fires. A `.claude/rules/` file loads only when a matching file is read. Each row marked "Yes" under "Stops an act?" stays global, unless its candidate home fires before the act.
- Skill descriptions checked on 2026-11-11, from each file's frontmatter. `project-ops`: an owner ask to give a repo session roles, compaction of standing sessions, a roadmap record and briefs. `ci-hygiene`: CI config edits, CI that is slow, queued or flaky, batching lane PRs into one integration branch, a red batch run. `waiting-page`: a session with a question, a decision or a task for the owner. `fresh-prose`: writing a README, docs, CLAUDE.md, agent files or decision records. `design-review`: after a change to a screen in a repo with screens. `plain-english-map`: only in a repo with `map.config.json`, and before answering how code in this repo works.
- No existing skill fires at spawn time. The spawner rules, the review round cap and the lane rules have no skill home today. A new skill that loads on spawn would need its own record.
- The question-box stop line stays global. The `waiting-page` skill loads on a question. A session that opens a box without that question would not load it.
- Audit cost of a move (see Measured). Each moved anchor fails `lint/rule_audit.py` in CI until its row is removed or `RULE_FILES` is extended. Removing the row drops the rule from the audit. Extending the list is step 3 work.
- Moves change what child repos repeat. That is why the child dedupe step sits after this one.

## Related

- Child dedupe step `child-claude-md-dedupe`: "Child repos: drop STE and the repeated text from their CLAUDE.md files". STE means Simplified Technical English. Phase `records`, status `ready`, order 532. Its lane sits with the child repos coordinator (roadmap note, 2026-11-10 11:28 CST). Proposal: run it after the step 2 sign-off, from the signed results.
- Prose wave (owner item 521, 20:24 CST Nov 11): the first wave of prose work. It touches the Speak plainly groups. Check overlap before a move.
- Output style rules (`output-styles/shiv-stylisms.md`, 23 rules): in the owner's review (restart plan line 734). This record does not audit them.

## Not measured

- The share of sessions that are spawners, lanes or coordinators: unmeasured.
- Which child repos have pull requests, screens, guards, `docs/map/` or `bin/verdict`: unmeasured. Child repos are outside this clone.
- Per-turn token cost of the root file: unmeasured.
- Whether each skill trigger fires every time it should: unmeasured.
- Which rules have a hook or check behind them, beyond the rule audit's rows: unmeasured.
- The gold standard column holds proposed targets, not results.

## Input Needed

One question for the owner. Sign off each of the 12 sections: accept, reject, or changes?

- A. Accept all 12 sections as proposed.
- B. Decide each section: accept, reject, or changes.
- C. Sign off nothing yet. Keep the file as it is, and wait for a second read of the proposed homes.

Recommendation: B. Start with Roles (1,081 words), which holds most of the spawner-only rules, and Output (334 words), which holds the question rule (241 words). The stop line of that rule stays global either way. Each section that moves an anchor also needs the rule audit choice from Measured: extend `RULE_FILES` or remove the row. Accept Shared trees and Compact instructions without a vote. Every row in those sections stays global.

## Next

1. The owner signs off each section (step 2). No section moves before that.
2. Proposal, for step 3 (a lane): move the signed sections, change `lint/check_claude_md_size.py` and its test to count words, and extend `RULE_FILES` in `lint/rule_audit.py` to each new home, or remove the rows. That is code work for a builder. It is not part of this record.
3. After sign-off: run the child dedupe step (see Related).
