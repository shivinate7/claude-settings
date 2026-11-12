# Plan: Global CLAUDE.md scope audit

Read-only audit. Nothing moves until the owner signs off the results.

- Roadmap step: the CLAUDE.md scope audit, id `global-claude-md-scope-audit`. Step 1 of 3.
- Related step: child CLAUDE.md dedupe, id `child-claude-md-dedupe`.
- Base: origin/main 6892e6419.
- Written: 2026-11-11 22:55 CST.

## Goal

Map each section of the root `CLAUDE.md` to the repos and session roles where it matters. For each section, propose one home: stay global, a path-scoped rule in `.claude/rules/`, or an existing skill. This record proposes only. It does not decide.

Gold standard, used in every row of the scope table: a rule loads only in sessions that need it, and each rule is stated once.

## Premise

The owner wrote these on the roadmap note for this step:

- 12:38 CST Nov 11: "im wondering whether i properly keep claude.md's just at the repo level and claude-settings level as its parent and no where further"
- 12:40 CST Nov 11: `"yes that's fine it would need my sign off (the actual results of the review) but just marking it as an item for review is good to do now"`

Ruling R35 (in `docs/plans/restart-plan.md`, line 821) records the owner's read at 12:39 CST: the levels are right. The levels are global, repo, and path-scoped rules in `.claude/rules/`. Restart plan line 734 adds that the output style's 23 rules join this review.

The note cites commit 6f94a10 for R35. That commit is not in this clone. Whether it exists on another branch: unmeasured.

## Measured

- Root `CLAUDE.md`: 108 lines and 3,890 words by `wc -w`. Remove the 98 rule anchors (`<!-- rule:... -->` comments) and 3,694 prose words remain.
- Size check: `lint/check_claude_md_size.py` counts lines, not words. Its limit is 200 lines (`MAX = 200`). It warns and never fails. Today it prints `ok` at 108 lines. Its test, `lint/test_check_claude_md_size.py`, asserts line counts at 200 and 201. Step 3 must change the check and its test to count words.
- The check's docstring says Claude Code loads each `CLAUDE.md` whole into every session. The note says the global file "loads in every turn of every repo". Per-turn cost: unmeasured.
- Per the header of `.claude/CLAUDE.md`, the root file loads in every repo. Not measured here.
- Section totals add to 3,694. Group totals add to their section totals.
- Checked by reading: the candidate homes named below exist. That covers `.claude/rules/hooks.md` (`paths: hooks/**`), `output-styles/shiv-stylisms.md`, `agents/reviewer.md`, `bin/verdict`, `hooks/precompact_handoff_prompt.md`, and the skills `ci-hygiene`, `design-explore`, `design-review`, `fresh-prose`, `impeccable`, `plain-english-map`, `project-ops`, `waiting-page`.

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

"Needed before first file read" asks whether the rule must be in view before the session's first read. It comes from reading the rule's text. It is not measured. Repo conditions are quoted from the rules.

| Group | Words | Where it matters | Needed before first file read | Candidate home | Gold standard |
|---|---|---|---|---|---|
| **Outcomes first** | | | | | |
| Judge by outcome; stale decisions | 75 | Every session | Yes. It frames all judgement. | Stay global | One short frame. Stale-decision steps stated once. |
| Tests are claims | 33 | Sessions that edit tests | No | Stay global | Stated once. |
| Grant covers named act | 29 | Any session that acts on a grant | No | Stay global | Stated once. |
| Mechanize rules | 137 | Sessions that build hooks, checks or logs | No | Stay global for the goal. The cost clause to `.claude/rules/hooks.md` (proposal). | Global states the goal. The hooks rule states the cost. |
| **Roles** | | | | | |
| Pick role; solo lane | 131 | Spawner sessions (coordinator or lane). The pick comes before work. | Yes, for spawner and lane sessions | Stay global for the pick line. Solo and grow rules to skill `project-ops`. | Pick line first, stated once. |
| Spawner agent rules | 346 | Spawner sessions only (glossary term "spawner") | No. Needed before the first agent starts. | Skill `project-ops`. No existing skill holds model caps. | Only spawner sessions load these. Each cap cites its decision once. |
| Briefs and proof layers | 132 | Spawners (briefs). Any repo with CI (proof layers). | No | Skill `project-ops` (brief template `templates/brief.md`). Proof layers to skill `ci-hygiene`. | Brief fields live in the brief template only. |
| Review round cap | 449 | Spawner sessions that run reviews | No | Skill `project-ops`, or reviewer agent file `agents/reviewer.md` (extra home) | Largest group. Round rules stated once, in one home. |
| Resume agents | 23 | Spawner sessions | No | Skill `project-ops` | With the spawner rules. |
| **Parallelism** | | | | | |
| Fan-out; own lane | 62 | Any session that starts agents or lanes | No | Stay global | Stated once. |
| No mid-task talk; lane caps | 75 | Spawner and lane sessions | No | Skill `project-ops` | Stated once, with the lane rules. |
| Keep going; queue | 164 | Coordinator and lane sessions, when a lane ends | No | Split. The ask-first list stays global (it covers any act that cannot be undone). Queue steps to skill `project-ops`. | Ask-first test in one place. Queue steps in one place. |
| **Shared trees** | | | | | |
| No destructive git; archive; no machine-wide kill | 65 | Any session in a shared tree (worktrees). Child repos: unmeasured. | No. Needed before any git write. | Stay global | Global. It guards every repo. |
| Own ports; confirm; reverify; absolute delete path | 50 | Same as above | No. Needed before any git write or delete. | Stay global | Global. |
| **Git** | | | | | |
| Main only by PR; no failing merge; cloud gh refused | 53 | Repos with pull requests (the section's own condition) | No. Needed before a merge. | Stay global | One merge rule, stated once. |
| CI waits and wakes | 75 | Any session that waits on CI | No | Skill `ci-hygiene` (step 9, "Wait without loops", already covers waiting) | The wait steps live in ci-hygiene. The file keeps one pointer. |
| Output and remedy | 20 | Any session that runs git | No | Stay global | Short. Stated once. |
| Record ids and files | 74 | Repos with records (`docs/decisions/`, `docs/debts/`, `docs/plans/`) | No | Skill `fresh-prose` (decision-record rung, "Superseded text") | Record rules in the record skill. |
| Batch into one integration branch | 102 | Repos with pull requests that batch lanes | No | Skill `ci-hygiene` (step 8, "Batch lanes", already holds the rest, as the rule's own text says) | The rule stays in the file. The steps stay in ci-hygiene. No copy. |
| **Verification** | | | | | |
| Screens | 57 | Repos with screens (the rule's condition). The screen-capture line applies to any session that captures the owner's screen. | No | Skill `design-review` for screen verdicts. The capture line stays global. | Screen verdict rule with design-review. |
| Trust guards | 56 | Repos with guards. In this clone, guards live under `hooks/`. Child repos: unmeasured. | No | Path-scoped rule `.claude/rules/hooks.md` (exists; `paths: hooks/**`) | Loads only when a session edits `hooks/`. |
| Fixtures and recovery | 34 | Any repo with checks and recovery controls | No | Skill `ci-hygiene` (fixtures), or stay global | Stated once. |
| Claims, versions, numbers, unknowns | 82 | Any repo | No | Skill `fresh-prose` (numbers and paths). The unknown-read rule stays global. | Each rule in one home. |
| **Tokens** | | | | | |
| Read less | 53 | Never-load-whole: every session. Map rule: repos with `docs/map/`. Folder rules: rule upkeep. | Never-load-whole and folder rules: yes. Map rule: no. | Never-load-whole and folder rules: stay global. Map rule: skill `plain-english-map` (its description already says "before answering how code in this repo works"). | Map rule lives with the map skill. |
| Command output | 46 | Sessions that run checks. `bin/verdict` exists in this clone. Child repos: unmeasured. | No | Stay global | One tool, one rule. |
| Brief and report reads | 16 | Spawner sessions | No | Skill `project-ops` (brief template) | With the brief rules. |
| Compaction | 23 | Every session at compaction | No. Needed at compaction. | Stay global. Merge with Compact instructions (below). | One compaction list. |
| **Building** | | | | | |
| Never guess; port keeps behaviour; ambiguity; no dropped items | 84 | Any session that builds or ports code | No | Stay global | Stated once. |
| One home; allow list is the constant | 43 | Repos with code | No | Stay global. The allow-list half could move to a hooks rule (proposal). | The allow list points at the constant, never a copy. |
| Guards need incidents | 95 | Repos that build guards or checks (here: claude-settings). Child repos: unmeasured. | No | Path-scoped rule with `paths: hooks/**` and `lint/**` (new file, or extend `hooks.md`) | Loads only when a session edits a guard or check. |
| Fix cause; scanners | 67 | Fix cause: any session. Scanners: sessions that write scanners. | No | Fix cause: stay global. Scanner rule: path-scoped to `lint/**` and `hooks/**`. | Scanner rule loads with scanner code. |
| Designs, memory, comments | 72 | Design rule: repos that make designs. Memory: every session. Comments: repos with code. | No | Design rule: fit unclear, stay global until step 2. Memory and comments: stay global. | Each rule sits with its own kind of work. |
| **Speak plainly** | | | | | |
| Ids and one name per thing | 219 | Every session that writes prose | No | Skill `fresh-prose` for the rules. `GLOSSARY.md` already holds the terms. | Global keeps one line. Terms live in the glossary. |
| Prose rules | 26 | Every session that writes prose | No | Skill `fresh-prose` ("Superseded text" already holds the rewrite rule) | Stated once. |
| **Output** | | | | | |
| Write plainly | 11 | Every reply | No | Output style `output-styles/shiv-stylisms.md` (the rule already says reply rules live there) | Reply style in the output style only. |
| Replies and evidence | 82 | Every reply | No | Output style (reply and evidence rules). Answer-home rule to skill `waiting-page`. | Each rule once. |
| Questions to owner | 241 | Any session that asks the owner | No. Needed before the first question. | Skill `waiting-page` (its description covers any question, decision or task for the owner) | Full rule in the skill. One pointer stays in global. See Method notes. |
| **Reports** | | | | | |
| Labels and content | 92 | Every session's final report | No. Needed at report time. | Stay global (the order applies to every report) | Order and labels stated once. |
| Batch pace numbers | 126 | Spawner or batch-runner sessions, at each batch merge | No | Skill `ci-hygiene` (batch steps) | With the batch steps. |
| Offer sweep | 40 | Any session whose last PR merged | No | Stay global. No skill in `skills/` covers the sweep. | Fit unmeasured. |
| **Compact instructions** | | | | | |
| Compact instructions | 34 | Every session at compaction | No. Needed at compaction. | Stay global | One list, shared with the compaction group in Tokens. Two lists exist today. |

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
- **CI waits and wakes** (75): `git-no-merge-during-batch-ci` 21, `git-ci-wait-checks-in` 36, `git-ci-done-comment-wakes` 18.
- **Output and remedy** (20): `git-never-discard-output` 11, `git-remedy-never-names-target` 9.
- **Record ids and files** (74): `git-slug-then-claim-number` 33, `git-cite-by-id` 10, `git-record-own-file-per-kind` 10, `git-one-record-per-question` 21.
- **Batch into one integration branch** (102): `git-integration-branch-merge` 102.
- **Screens** (57): `verification-screens-verdict` 25, `verification-browser-login-only-needed` 16, `verification-announce-own-screen` 16.
- **Trust guards** (56): `verification-trust-guard-after-red` 13, `verification-cry-wolf-guard-is-spent` 43.
- **Fixtures and recovery** (34): `verification-green-proves-only-its-fixtures` 13, `verification-recovery-independent-of-state` 21.
- **Claims, versions, numbers, unknowns** (82): `verification-verify-against-repo` 10, `verification-never-dry-run-refusal-list` 5, `verification-newest-that-passes` 26, `verification-checked-reader-for-numbers` 14, `verification-report-unknown-reads` 27.
- **Read less** (53): `tokens-never-load-whole-doc` 16, `tokens-read-map-first` 12, `tokens-folder-rules-load-by-path` 25.
- **Command output** (46): `tokens-verdict-not-stream` 27, `tokens-run-through-verdict` 19.
- **Brief and report reads** (16): `tokens-point-brief-at-files` 9, `tokens-read-report-not-transcript` 7.
- **Compaction** (23): `tokens-compacting-keep-essentials` 23.
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

- A rule that moves to a skill loads only when the skill triggers. A rule that stops an act must still load before that act. Check each move against this. The clearest case is the question-box rule in the Questions to owner group. It keeps a session from opening a question box while agents run. A session that has not loaded the skill would not see it. Keep a pointer in the global file.
- A rule that moves to `.claude/rules/` loads only when a matching file is read. Rules about roles, briefs and reports name no file. The path home does not fit them.
- No existing skill holds model caps or the review round cap. Those need a home decided at step 2.
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
- Which rules have a hook or check behind them: unmeasured. This audit did not read `lint/rule_mechanisms.json`.
- The gold standard column holds proposed targets, not results.

## Input Needed

One question for the owner. Sign off each of the 12 sections: accept, reject, or changes?

- A. Accept all 12 sections as proposed.
- B. Decide each section: accept, reject, or changes.
- C. Sign off nothing yet. Keep the file as it is, and wait for a second read of the proposed homes.

Recommendation: B. Start with Roles (1,081 words), which holds most of the spawner-only rules, and Output (334 words), which holds the question rule (241 words). The question rule needs the check in Method notes first. Accept Shared trees and Compact instructions without a vote. Every row in those sections stays global.

## Next

1. The owner signs off each section (step 2). No section moves before that.
2. Step 3, a lane: move the signed sections, and change `lint/check_claude_md_size.py` and its test to count words. That is code work for a builder. It is not part of this record.
3. After sign-off: run the child dedupe step (see Related).
