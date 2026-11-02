# Plan: one home per kind of prose, and shivpedia

Roadmap step `craft-book` (the experience book). The step record
`roadmap/data/steps/craft-book.json` on branch `roadmap` holds the owner's words of 21:02, 21:05 and
21:07. This record is the home of his 21:06 and 21:08 asks (rule `output-answer-has-a-home`). This is a
plan only. No build lane starts until the owner signs off on the whole plan.

The owner's asks, 2026-11-01 CST, in short:
- 21:02: a practice learned once is used again in each later repo, as a carpenter grows more skilled.
- 21:05: the book is named shivpedia. It lives in claude-settings.
- 21:06: tight, low slop, rewritten in place and never appended. GLOSSARY.md moves into shivpedia.
- 21:07: experiences, not evergreen commandments. A wider prose refactor. Every piece double-checked
  before any build.
- 21:08: shivpedia stays current through the same shared mechanism as the map and triage.

Counts are read at main d8037a44 unless marked "at 55b27ac2". A count at 55b27ac2 was read 90 commits
earlier. Each build lane measures its own count again at its base. "Proxy" marks a count from a text
pattern. A proxy misses paraphrase, so it is a lower bound. Cites name an id or a symbol. A line number
is given only where no symbol exists.

## 1. The five forms

"Form" here is not the `Kind:` line of a record, nor a layout kind. Skill `fresh-prose` sorts the same
prose on a different axis: what rots, and the rung that holds it current. Lane 1 lands this table as
decision `prose-forms`, which cites that skill, so the table outlives this plan.

| Form | What it holds | Its one home | Its check |
|---|---|---|---|
| Law | A rule that binds every session. | A `<!-- rule:ID -->` item in `CLAUDE.md` or `output-styles/shiv-stylisms.md`. A guard or check where one can judge it. | `lint/rule_audit.py`, `lint/rule_mechanisms.json` |
| Ruling | The ruling in force, plus a one-line reason, plus evidence of about 10 lines at most (decision `cull-rules`). | A record in `docs/decisions/`. | `lint/check_ruling_kind.py` (decision `rulings-declare-kind`) |
| Glossary | One name per workflow thing, and the names to avoid. | `skills/shivpedia/glossary.md`, moved from `GLOSSARY.md`. | `lint/check_glossary.py` |
| Experience | A practice that worked, where it applied, and how sure we are. It informs judgment and binds nobody. | `skills/shivpedia/<topic>/<slug>.md` | new `lint/check_shivpedia.py` |
| Procedure | How to do a task, step by step. | A skill. An agent file holds its own role's steps only. | the skill's tests |

No new rule is needed. Existing law already says each form has one home and every other place cites
it: rules `building-one-home-per-capability`, `speak-one-name-per-thing`, `speak-cite-id-plus-gloss`
and decision `audit-rework-order` (delete copies first; a mandate stays in its central home).

The debt store (`docs/debts/`) holds known gaps. It is out of scope, except as a seed source.

## 2. Findings

Law files (main):
- `lint/rule_mechanisms.json`: 119 rules (97 in CLAUDE.md, 22 in the style file). 34 have a guard,
  check or CI step. 61 are unmechanized and 24 are judgment.
- 4 CLAUDE.md rules hold reasoning longer than one line: `roles-review-cap-three`, `verification-cry-wolf-guard-is-spent`,
  `speak-cite-id-plus-gloss`, `questions-go-to-owner` (at 55b27ac2). Decision `claude-md-shrink` keeps
  `speak-cite-id-plus-gloss` as it is, so M4 moves 3.
- 6 CLAUDE.md rules hold procedure steps: `git-integration-branch-merge`, `roles-review-cap-three`,
  `questions-go-to-owner`, `parallelism-keep-going`, `reports-batch-pace-numbers`,
  `outcomes-stale-decision-protocol` (at 55b27ac2).
- `.claude/CLAUDE.md` holds the "Acts the cloud refuses" standing grant, with no record.

Decision records (main: 152 records, 5083 lines):
- By proxy at 55b27ac2, most body lines are ruling or spec text, and about 8% are reason. Ruling
  text is allowed. Decision `cull-rules` limits the reason to one line and the evidence to about 10
  lines.
- 8 records repeat their own Home rule word for word (at 55b27ac2): `guard-guards-mistakes-only`,
  `guard-that-cries-wolf-is-spent`, `hold-unsafe-after-round-3`, `port-keeps-behaviour`,
  `question-form`, `questions-go-to-owner`, `recovery-independent-of-state`, `uniform-over-variants`.
- 34 rule-and-record pairs share text word for word, with 20 rules and 24 records (proxy, at
  55b27ac2: a shared run of 8 or more words; 10 pairs read by hand).
- 5 pairs of records hold one ruling twice, matched by the owner's timestamp (at 55b27ac2).
- 9 records hold law with no home outside the record (at 55b27ac2): `session-tiers`,
  `mods-deferred-table`, `worktree-setup-is-per-repo`, `an-agent-outside-its-home-tree-must-stop`,
  `ci-wait-reads-run-status`, `claude-md-change-is-flagged`, `lanes-start-in-tool-worktrees`,
  `machine-load-brake`, `owner-override`.
- 3 records go past the evidence allowance: `hook-inputs-carry-token-counts`,
  `mutation-report-scores-suites`, `feel-fix-waits-device-check`. One more record,
  `ios-mac-install-first`, holds history wording.
- 11 records are cited nowhere outside `docs/decisions/` and the generated `docs/records.md` (at
  55b27ac2, corrected in review). 2 of them hold law. The list is in move M9.

Vocabulary (main: 49 rows in GLOSSARY.md):
- 12 rows hold a law or reasoning clause: guard, grant, check, decision, builder, reviewer, design
  reviewer, CI step, safety hole, round, orchestrator, owner.
- 5 terms are defined again in `skills/project-ops/templates/operating-model.md`: orchestrator,
  coordinator, triage, batch runner, lane session. 3 terms have a second sense: lane (skills
  `waiting-page` and `roadmap`), owner (skill `waiting-page`, `operating-model.md`), debt
  (`docs/plans/shared-merge-tool.md`).

Skills, agents and hooks (proxy, at 55b27ac2: a shared run of 6 or more words):
- 41 skill or agent paragraphs restate a rule or ruling and cite no id. 13 are in `agents/*.md`.
- 48 of 132 hook messages restate a rule or ruling and cite no id. 18 are in `hooks/question_form.py`.
- 6 of 9 agent files copy the report form.
- 5 rulings live only in a skill or a plan: the `hinge` choice and "each app is its own product"
  (skill `ios-apps`), "never write `answers/`" (skill `waiting-page`), "no setup without the owner's
  grant" (skill `project-ops`), and the owner's ruling of 2026-11-01 12:23 CST (no optional standard
  becomes builder load), in `docs/plans/test-ci-standard.md`.

Experience today has no home. At 55b27ac2 it sits in 43 lines of `docs/debts/notes.md`, in 16 of 64
debt records, in 7 lines of `docs/todo.md`, and in 2 hook messages (`GIT_ENV_REASON`,
`PLAYWRIGHT_PATH_REASON` in `hooks/guard_kill.py`). Experience that already became law lives in skill
`ci-hygiene` and in the CLAUDE.md rules from branch `archive/propose/lessons-from-mailaudit`. Shivpedia links these and copies none.

## 3. Invariants for every move

- I1. Each `<!-- rule:ID -->` anchor stays, with its `lint/rule_mechanisms.json` row.
- I2. Text that leaves a rule leaves an id cite in its place.
- I3. A binding clause stays in its rule. Only steps, definitions and reasoning past one line move.
- I4. No move deletes a guard, check, test or CI step.
- I5. An edit to any text that a test pins (a hook message, a skill or agent line) names that test and
  re-points it red then green. Known pins: `skills/project-ops/tests/test_scaffold.py`
  (`test_tiers_start_as_a_trio`), `hooks/test_blind_brief.py` (designer anchors),
  `lint/test_check_agent_models.py` (the "Premises first" paragraph of `agents/plan.md`).
- I6. Each commit that adds or re-kinds an anchor updates `RULE_FLOOR`, `UNMECHANIZED_EXPECTED` and
  `JUDGMENT_EXPECTED` in `lint/rule_audit.py`.
- I7. After each move, `lint/rule_audit.py`, `lint/stale_cites.py`, `lint/check_ruling_kind.py`,
  `lint/check_glossary.py` and `lint/compliance_probes.py` pass. A deleted record id is also searched
  for with `git grep` over every tracked file, because `stale_cites.py` reads Markdown and def names
  only (for example `.gitattributes` cites `notes-merge-union`).
- I8. Rewording a kept rule is allowed only when the result has fewer lines and words and keeps the
  reason (owner answer of 2026-10-17 12:53 CDT in decision `cull-rules`, later than the "never reword"
  line in decision `claude-md-shrink`).

## 4. The moves

| Move | What | Touches |
|---|---|---|
| M1 | M2 applied first to the 8 records whose `Home:` names their rule. Cut the rule text that the 8 records repeat. Each record keeps its ruling and one-line reason, and cites its rule. | the 8 records |
| M2 | For the other 34 pairs (M1 first), keep each text in the home a check or code reads (`audit-rework-order`, step 1). The other home cites it. | 20 rules, 24 records |
| M3 | For the 5 same-ruling pairs, keep the ruling in the narrower record. The other one cites it: `main-branch-protection` (cited by `same-check-kinds`), `standing-merge-grant`, `owner-judge-test` and `agent-model-cap` (each cited by `session-tiers`), `questions-go-to-owner` (cited by `port-keeps-behaviour`). No id is retired. | 8 records |
| M4 | Move the reasoning past one line out of 3 rules into their records (each rule keeps a one-line reason, I8): `roles-review-cap-three` to `hold-unsafe-after-round-3`, `verification-cry-wolf-guard-is-spent` to `guard-that-cries-wolf-is-spent`, `questions-go-to-owner` to its record. `speak-cite-id-plus-gloss` stays as it is (decision `claude-md-shrink`: keep). | CLAUDE.md, 3 records |
| M5 | Move the procedure steps out of the 6 rules into the skill that does the task. Each binding clause stays (I3), and the rule cites the skill by name (I2). Example: "a held change is parked" and "never fix inside the integration branch" stay in `git-integration-branch-merge`; the drop-and-rebuild steps go to skill `project-ops`. "Compact instructions" stays in CLAUDE.md, because Claude Code reads that block at compaction. | CLAUDE.md, skill `project-ops` |
| M6 | 5 terms that rules define inline already have rows: safety hole, debt, note, coordinator, ruling. Delete only the definition text that the row already holds. A clause the row lacks stays in the rule, for example "turning a main refusal into an ask is also a safety hole". Reconcile the coordinator wording with its row. The other 5 terms (net-value test, one lane, cannot be undone, batch merge, advisor) have no row and stay in CLAUDE.md. | 5 rules, glossary |
| M7 | In the 12 rows, cut each law clause that a rule or record holds word for word, for example "A lint or CI check never asks." (decision `guard-guards-mistakes-only`). Each clause with no copy stays in its row. The lane lists both sets. | glossary |
| M8 | Delete the 5 redefinitions in `operating-model.md` and cite the rows. Give the 3 second senses their own terms in the glossary. | skills `project-ops`, `waiting-page`, `roadmap`; `docs/plans/shared-merge-tool.md` |
| M9 | Give each of the 9 hard-law records a home: a rule anchor, or `Kind: build` with a `Plan:` line in the form `<md path>#<heading slug> (<platform>)` (`lint/check_ruling_kind.py`, `plan_problem`). Review the 9 other records that nothing cites (at 55b27ac2, re-measured by the lane): `adoptions-declined-2026-09-28`, `browser-prompts-are-the-apps`, `docs-only-prs-skip-review`, `hook-if-filters`, `install-sh-stays-off-windows`, `lanes-start-as-agents`, `mods-no-cli-key-headless`, `reuse-needs-checkout-proof`, `source-prose-lint-ships-dark`. Cite each from its home, or delete it under `cull-rules`. `mods-deferred-table` and `worktree-setup-is-per-repo` are also uncited, but they hold law, so they get a home and are never deleted. | records, CLAUDE.md, `rule_mechanisms.json` |
| M10 | Replace the 41 restatements in skills and agents with an id cite. The report form lives in the `reports-*` rules, and each agent file cites them. | `agents/*.md`, 7 skills |
| M11 | The 48 hook messages that restate law name their id and keep the remedy. The reason text goes to the record. `GIT_ENV_REASON` and `PLAYWRIGHT_PATH_REASON` move their measures into the records `git-env-set-refused` and `playwright-browsers-path`. | 11 hook files and their string tests |
| M12 | Give the 5 rulings that live only in a skill or plan a record each. | 3 skills, 1 plan, 5 new records |
| M13 | Give the "Acts the cloud refuses" grant a record with `Home: .claude/CLAUDE.md`. Add no anchor: `lint/rule_audit.py` reads root CLAUDE.md and the style file only. | `.claude/CLAUDE.md`, 1 new record |
| M14 | Trim the 3 records that go past the evidence allowance. Rewrite the history wording in `ios-mac-install-first` in place. | 4 records |
| M15 | Move GLOSSARY.md (section 5.4). | see 5.4 |
| M16 | Triage moves a seed source into shivpedia only where it taught a practice. A gap stays a debt or a note. Sources are listed in section 2. | `docs/debts`, `docs/todo.md`, shivpedia |

Decision `cull-rules` already answers what a record holds: the ruling in force plus a one-line reason.
The plan follows it and asks no question about it. Decision `claude-md-shrink` deletes the prose of a
guarded or checked rule down to a reminder of 3 words or fewer. M2 keeps a rule's text only where no
guard or check holds it.

## 5. Shivpedia

### 5.1 Home and shape

- `skills/shivpedia/`. `skills/` already lands under `~/.claude` (`landed-dirs.txt`), so a session in
  any repo can read it.
- `SKILL.md`: a description of 300 characters or fewer. The steps to load, write back and cull. 60
  lines or fewer.
- One folder per topic: `testing`, `ci`, `merging`, `guards`, `ui`, `records`, `orchestration`. One
  file per experience (rule `git-record-own-file-per-kind`). A rewrite replaces one file.
- Each topic folder has a `README.md` with `see:` links to that topic's law and procedure homes, for
  example skill `ci-hygiene`, decision `test-strategy-reset`, `docs/design/principles.md`.
- `glossary.md` is the moved glossary.

### 5.2 One experience

```
---
paths: [".github/workflows/**"]
words: [ci, job, cap, timeout]
---
Situation: <the kind of problem met, in one sentence; no story, no date>
Worked: <the practice that worked>
Applies: <where it applies, and where it does not>
Confidence: low|medium|high, <N> cases
Dates it: <the change that would make it stale>
Evidence: <one link: a PR, a decision id or a commit>
Example: <one short use>
Misses: <number>
```

- Caps: 12 lines in all, 30 words per field.
- A new lesson on an experience rewrites its file whole (rule `speak-rewrite-superseded-in-place`).
- `lint/check_shivpedia.py` fails on:
  - a missing field, or a second link in Evidence
  - a date: a day number with a month name, a year, or an ISO date. A bare word such as "may" passes.
  - the words "always" or "never"
  - history narration: its own list `HISTORY_WORDS` ("used to", "previously", "before this", "no
    longer"), plus a PR number or commit hash outside the Evidence field. The `PATTERNS` of
    `lint/check_comment_narration.py` stay as they are: they target code comments and catch neither
    "used to" nor a story.
  - a cap overrun, or a second experience with the same slug.
  It skips `glossary.md` and the topic `README.md` files. `select.py` skips the same files, through one
  shared constant `NOT_EXPERIENCE`.
- STE lint covers `skills/**/*.md` already: the CI step runs `actions/ste-lint` on `**/*.md`, and
  `.ste-lint-exclude` drops only `skills/impeccable/**`.
- Code term: `experience`. The word "entry" is in the "Not" cell of the `record` row, so it cannot name
  code (question Q1).

### 5.3 Load by topic

- `skills/shivpedia/select.py --task TEXT [--paths P ...] [--base REF]` reads each experience's front
  matter. It prints the topic folders that match. It matches `paths` by glob, and `words` whole-word
  and case-blind. `--base` runs one `git diff --name-only`.
- The skill's first step: before a plan, run `select.py` and read the experiences it names.
- Why not a `.claude/rules/` file with `paths:` (rule `tokens-folder-rules-load-by-path`): a rule
  file loads as an instruction that binds. An experience must not bind (owner, 21:07). `select.py`
  matches. It loads no law.
- Red-first tests in `skills/shivpedia/test_select.py`, red on main because the module does not exist:
  - S1: path `.github/workflows/checks.yml` and the task "split the job near its time cap" give `ci`
    only.
  - S2: `docs/design/x.html` gives `ui`, not `ci`.
  - S3: no input gives no output and exit 0.
  - S4: a mixed input gives both topics.
  - S5: the word "circle" does not pick `ci`.
  - S6: an experience with no front matter exits 2 and names the file.
  - C1: the description is 300 characters or fewer.
  - C2: no SessionStart command in `settings.json` names shivpedia.
  - C3: `--paths` starts no git process. `--base` starts one, through `hooks/_nowindow.py`
    (`lint/test_no_window_spawn.py` scans `skills/`). The test writes its own process probe.
- Red-first tests in `lint/test_check_shivpedia.py`: a tombstone sample (a date, "we used to", an
  incident story, two links) is red, with each fault named. A padded sample (a 40-word field, 14 lines)
  is red. An "always" line, a missing Confidence field and a duplicate slug are each red. One clean
  sample is green.

### 5.4 The glossary move (M15)

`GLOSSARY.md` becomes `skills/shivpedia/glossary.md`. One change updates each reader on main:
- Rule `speak-one-name-per-thing` in CLAUDE.md: the path only.
- `lint/check_glossary.py`: the path constant `GLOSSARY` and the skip list `SKIP_CODE`. The new path
  joins `SKIP_CODE`, or the retired-name scan reads its own "Not" cells.
- `lint/compliance_probes.py`: the text that names the path. The read goes through the constant.
- Tests: `lint/test_check_glossary.py` (the real-file tests and its `SKIP` list),
  `lint/test_retired_names.py`, `lint/test_compliance_probes.py`.
- CI: the steps "Glossary fixture suite", "Glossary homes and avoided names" and "Retired names" in
  `.github/workflows/checks.yml`.
- Agents: `builder.md`, `designer.md`, `plan.md`, `reviewer.md`.
- Skills: `compliance-check/probes.md`, `project-ops/SKILL.md`.
- Records and prose: decision `glossary-meets-owner-halfway`, `docs/debts/notes.md`,
  `docs/design/last-answer-notes.md`. The merge tool rebuilds `docs/records.md`.
- Unchanged: the reads of a child repo's own `GLOSSARY.md` in `lint/compliance_probes.py` and its
  test. A child repo's glossary stays at its root.
- The builder runs `git grep -n GLOSSARY` at its base and adds any reader not listed here. A Markdown
  line that still names a child repo's own `GLOSSARY.md` (for example in `skills/compliance-check/probes.md`)
  is reworded so `lint/stale_cites.py` (STALE001) does not read it as a cite of the moved file.
- New rows in the same change: shivpedia, experience, topic, lesson (a candidate experience named on a
  `Lessons:` line), form (home: decision `prose-forms`). The file keeps the name glossary, so one
  thing keeps one name.
- Readers in other repos: unknown, because no other repo is attached to this lane. Triage lists them.

### 5.5 The feed

- A lane's closing report carries `Lessons:` under Next: 0 to 3 items, or `none`. Each item is
  `<topic>/<slug>: skip|rewrite|add, <one line>`.
- Before it writes the line, the lane runs `select.py` and reads the matching experience. Then it
  skips it, rewrites it whole, or adds one. One lesson has one experience (rule
  `building-one-home-per-capability`).
- Check: `lint/report_guard.py` gets a Lessons check beside `unstarted_problem`, on the same trigger.
  If a builder-shaped report has no `Lessons:` line, or has 4 or more items, it is red. `Lessons: none`
  is green. Tests go in `lint/test_report_guard.py` beside `UnstartedItemsTests`. `lint/report_gate.py`
  is a stub due for deletion, so it is not extended.
- The rule goes in a new `reports-*` anchor, a `rule_mechanisms.json` row, and
  `skills/project-ops/templates/brief.md`.
- Triage is the one reader that folds lessons in. A lane in another repo puts its Lessons in that
  repo's outbox (`roadmap/outbox/<session-slug>.md`, per `operating-model.md`). The claude-settings triage folds them in
  through a records PR (question Q2).

### 5.6 Misses and the cull

- Misses: when a new incident matches an experience's Applies field, triage adds 1 to Misses and
  rewrites Worked and Confidence. No list of stories is kept. The match uses the repeat judge from step
  `feedback-repeat-detect`, which is still being built. This plan adds no second matcher. Until that
  step ships, Misses stays 0 and the count is unknown (section 10).
- The cull is one bullet added to decision `cull-rules`, the one home for culls. An experience with 0
  loads and 0 Misses since it landed is deleted. `lint/ruling_census.py` already reads transcripts on
  demand, and it gets a count of shivpedia loads. A count that cannot be read is unknown, for example
  cloud transcripts on the owner's machine. An unknown count never culls.

### 5.7 Staying current through one shared home

Of 8 mechanisms that keep a derived doc current (at 55b27ac2), only the records page has a generator, a
CI check, a rebuild at merge and a lane guard (decision `records-index-at-merge`). `lint/hook_catalog.py`
writes it and `merge/merge.py` rebuilds it.
- The map cannot be the home: it is checked prose with no generator (decision `map-facts-are-checked`).
- Triage, the roadmap and the waiting page cannot be the home: they publish through the Artifact tool,
  so only a session can run them.

So two shared homes already exist, one per class of derived doc:
- A generated page is built by `lint/hook_catalog.py` and checked by its `--check` in CI. The records
  page is also rebuilt by the merge tool.
- Checked prose is written by a session and held current by its own check, run as a step in the CI
  `checks` job. The map works this way.

Shivpedia is checked prose. It joins the second home: `lint/check_shivpedia.py` runs as a CI step, the
same way the map check does. `select.py` reads front matter at load time, so nothing derived exists to
go stale, and shivpedia adds nothing to the rebuild at merge (steps `records-page-before-ready` and
`records-stale-refuses-on-ready` show that rebuild's risk). Triage keeps its experiences current by the
feed (5.5) and the cull (5.6). Nothing else needs a keeper.

A registry of generated pages was weighed and is not in the build (question Q4). Shivpedia gains nothing
from it. Its 10 code readers and 5 test files were listed in review round 2, at head 108b2de0 of this
record.

One gap found on the way goes to `docs/debts/notes.md` as a note: the merge tool never rebuilds
`docs/catalog.md`, so two lanes that each add a hook conflict on it.

## 6. Cost (rule outcomes-mechanize-rules)

| Path | Trigger | Writes | Process starts |
|---|---|---|---|
| Session start | none | nothing | 0; about 75 tokens for the skill description |
| Load | the skill, before a plan | nothing | 1 python; 1 git with `--base` |
| Shape check | its CI step in the `checks` job | nothing | 1 python per run |
| Lessons check | `lint/report_guard.py`, where it runs today | nothing | 0 new |
| Fold | triage, at each batch merge | experience files, in a records PR | 0 new |
| Cull count | `lint/ruling_census.py`, at each cull | nothing | 0 new |

Nothing runs on a timer. Nothing starts a long-lived process. Tests C2 and C3 prove the session-start
and load counts.

## 7. Seed experiences

A seed lands only when its source has a practice that worked and that no guard or check already holds
(shivpedia copies no law). Lane 2 judges each candidate at its base and lists the ones it skips:
- the 6 patterns of the owner-feedback audit (draft PR #1008): up to 6 files
- step `records-page-before-ready` (PR #895), if its practice is not held by the merge tool
- steps `overlapping-batches`, `records-stale-refuses-on-ready`, `runner-refuses-lint-red` and
  `question-checks-past-rulings`: each is still open and each may end as a guard. Each one seeds an
  experience only if, once shipped, it leaves a practice no guard holds.

The `ci` topic `README.md` links skill `ci-hygiene` and copies nothing from it. The `testing` topic
`README.md` links decision `test-strategy-reset`. Draft PR #1028 (lane `test-practices-first-principles`)
adds decision `test-practices`, 11 testing practices P1 to P11, each a do-this line with evidence.
`test-strategy-reset` points to it. That record holds experience in a decision home. Each practice that a
check or a role file enforces stays in `test-practices` as a ruling. Each other practice moves to
`skills/shivpedia/testing/` as one experience, and `test-practices` keeps only the ruled ones. After
sign-off, this lane sends that lane one message with the path and the list of practices to move.

## 8. Build lanes after sign-off

Each lane runs test-author, then builder, then reviewer. Lanes never commit `docs/records.md` (decision
`records-index-at-merge`). Each lane that adds a test or check adds its CI step to
`.github/workflows/checks.yml`, and checks that `.github/scripts/ci-scope.sh` runs it for the new
paths (a `.md`-only change counts as docs-only today).
1. `glossary-to-shivpedia`: M15, and decision `prose-forms` (the table in section 1). It runs first,
   because later lanes cite the new path.
2. `shivpedia-core`: SKILL.md, `select.py`, `check_shivpedia.py`, their CI steps, topics, seeds, the
   skill row in decision `agent-model-cap`, `docs/catalog.md`. It also adds `shivpedia` to
   `CONFIG_FROZEN_SKILLS` in `hooks/guard_frozen.py` (`lint/check_landed_dirs.py` requires it), with
   the frozen cases in `hooks/test_guard.py`. That guard change runs the guard CI job and gets the
   review the roles rules require for a guard change.
3. `record-homes`: M3 (except the `agent-model-cap` pair), M9, M12, M13.
4. `lessons-line`: section 5.5.
5. `shivpedia-cull`: the cull bullet in decision `cull-rules` and the load count in
   `lint/ruling_census.py` (section 5.6).
6. `prose-dedupe-<home>`: M1, M2, M4 to M8, M10, M11, M14, and the `agent-model-cap` pair of M3. One
   lane per home file.
7. Triage: M16.

Order: lane 1 alone. Then lanes 2 and 3 together: lane 2 edits `skills/shivpedia/`, the catalog and
`agent-model-cap`; lane 3 edits other records and CLAUDE.md. Then lane 4 (after lane 3, as both edit
CLAUDE.md) and lane 5 (after lane 2). Then the lane-6 set, one at a time per home file. Triage acts
after lanes 2 and 4 merge.

## 9. Questions for the owner

Each blocks only the lane it names.
- Q1. The code name for one item. A (recommended): `experience`. B: `entry`, which needs the `record`
  row's "Not" cell changed. Blocks lane 2.
- Q2. How a lesson from another repo reaches claude-settings. A (recommended): the claude-settings
  triage reads each repo's outbox, and that repo's triage removes the lines it filed. B: each lane opens
  a claude-settings PR, which is work in a second repo and needs an ask each time under
  `parallelism-keep-going`. Blocks lane 4.
- Q3. Which report carries `Lessons:`. A (recommended): a builder-shaped report, the trigger the
  Unstarted check uses. B: every report that lands work. Blocks lane 4.
- Q4. A registry of generated pages in `.claude/layout-extras.json` (section 5.7). A (recommended):
  not now. Shivpedia joins the CI check home and gains nothing from a registry. B: build it as its own
  lane. Gain: a new generated page edits no consumer. Lose: one lane over 10 code files and 5 test
  files. Blocks nothing in this plan.

## 10. Unknowns

- Readers of the glossary path in other repos.
- Load counts for cloud sessions.
- Misses, until step `feedback-repeat-detect` ships.
