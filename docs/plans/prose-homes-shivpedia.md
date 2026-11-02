# Plan: one home per kind of prose, and shivpedia

Roadmap step `craft-book` (the experience book). The step record is
`roadmap/data/steps/craft-book.json` on branch `roadmap`. This is a plan only. No build lane starts
until the owner signs off on the whole plan.

The owner's words, 2026-11-01 CST:
- 21:02: "if i learned how to build something better one way, i should be able to use that again
  some other day".
- 21:05: the book is named shivpedia. It lives in claude-settings.
- 21:06: "it needs to actually be tight, rewritten (not appended ...) low slop". GLOSSARY.md moves
  into shivpedia.
- 21:07: experiences, not "evergreen commandments". "maybe we need to do a larger refactor of our
  prose". Plan end to end, with every piece double-checked, before any build.
- 21:08: shivpedia stays current "in a shared way", through the same mechanism as the map and triage.

Every count below was read at commit 55b27ac2 (main). A count marked "proxy" comes from a text
pattern, not from a hand read of each file.

## 1. The five kinds and their one home each

| Kind | What it holds | Its one home | Its check |
|---|---|---|---|
| Law | A rule that binds every session. | A `<!-- rule:ID -->` item in `CLAUDE.md` or `output-styles/shiv-stylisms.md`. A guard or check holds it where it can. | `lint/rule_audit.py` with `lint/rule_mechanisms.json` |
| Argument | Why a rule holds: the ruling in full, the reason, the evidence, the kind and the home. | A record in `docs/decisions/`. | `rulings-declare-kind` (decision: each ruling declares its kind) |
| Vocabulary | One name per workflow thing, and the names to avoid. | `skills/shivpedia/vocabulary.md` (moved from `GLOSSARY.md`). | `lint/check_glossary.py` |
| Experience | What happened, what worked, where it applied, and how sure we are. It informs judgment. It binds nobody. | `skills/shivpedia/<topic>/<slug>.md` | new `lint/check_shivpedia.py` |
| Procedure | How to do a task, step by step. | A skill (`skills/*/SKILL.md`). An agent file holds its role's procedure only. | the skill's own tests |

One more home stays as it is: the debt store (`docs/debts/`) holds known gaps. It is not prose
guidance, so it is out of scope, except as a seed source for shivpedia.

## 2. What the survey found (counts at 55b27ac2)

Law files:
- `lint/rule_mechanisms.json` maps 119 rules (97 in CLAUDE.md, 22 in the style file). 33 have a
  guard, check or CI step. 86 are prose only (62 unmechanized, 24 judgment).
- 11 CLAUDE.md rules hold a reason. 4 of them hold argument that belongs in a decision:
  `roles-review-cap-three`, `verification-cry-wolf-guard-is-spent`, `speak-cite-id-plus-gloss`,
  `questions-go-to-owner`.
- 7 CLAUDE.md rules hold procedure: `git-integration-branch-merge`, `roles-review-cap-three`,
  `questions-go-to-owner`, `parallelism-keep-going`, `reports-batch-pace-numbers`,
  `reports-offer-sweep-after-merge`, `outcomes-stale-decision-protocol`. So does the unanchored
  "Compact instructions" block.
- 7 CLAUDE.md rules define a term inline (the survey list is in section 4, move M6).
- `.claude/CLAUDE.md` holds a dated standing grant with no anchor, no record and no reader.

Decision records (149 records, 4971 lines):
- By a line pattern (proxy), about 88% of body lines are ruling or spec text, 7.7% are reason and
  about 7% are evidence or history. So a record today is the full law spec plus a thin reason.
- 8 records with a `Home: rule:ID` line repeat their rule word for word:
  `guard-guards-mistakes-only`, `guard-that-cries-wolf-is-spent`, `hold-unsafe-after-round-3`,
  `port-keeps-behaviour`, `question-form`, `questions-go-to-owner`,
  `recovery-independent-of-state`, `uniform-over-variants`.
- 34 rule-and-record pairs share text word for word (20 rules, 24 records; proxy: a shared run of
  8 or more words, 10 pairs read by hand).
- 5 pairs of records hold one ruling twice (matched by the owner's timestamp):
  `main-branch-protection` and `same-check-kinds`; `standing-merge-grant` and `session-tiers`;
  `owner-judge-test` and `session-tiers`; `questions-go-to-owner` and `port-keeps-behaviour`;
  `agent-model-cap` and `session-tiers`.
- `same-check-kinds` line 20 says this repo has no all-jobs-passed job. That is false:
  `.github/workflows/checks.yml` has it at line 1346.
- 9 records hold law that has no home outside the record: `session-tiers`, `mods-deferred-table`,
  `worktree-setup-is-per-repo`, `an-agent-outside-its-home-tree-must-stop`,
  `ci-wait-reads-run-status`, `claude-md-change-is-flagged`, `lanes-start-in-tool-worktrees`,
  `machine-load-brake`, `owner-override`.
- 3 records go past the evidence allowance of about 10 lines (`cull-rules`):
  `hook-inputs-carry-token-counts` (24), `mutation-report-scores-suites` (19),
  `feel-fix-waits-device-check` (13). Rule `speak-rewrite-superseded-in-place` covers the
  history wording in `ios-mac-install-first` (lines 7-8).
- 14 records are cited nowhere outside `docs/decisions/` and the generated `docs/records.md`.
  The list is in move M9.

Vocabulary:
- GLOSSARY.md has 49 rows. 8 rows hold a law or argument clause: guard, grant, check, decision,
  builder, reviewer, design reviewer, CI step.
- 5 terms are defined again outside GLOSSARY.md, in `skills/project-ops/templates/operating-model.md`
  (orchestrator, coordinator, triage, batch runner, lane session). 3 terms take a second sense:
  lane (`skills/waiting-page/SKILL.md:10`, `skills/roadmap/SKILL.md:48`), owner
  (`skills/waiting-page/SKILL.md:277`, `operating-model.md:81`) and debt
  (`docs/plans/shared-merge-tool.md:48`).

Skills, agents and hook messages (proxy: a shared run of 6 or more words):
- 41 skill or agent paragraphs restate a rule or ruling and cite no id. 13 of them are in
  `agents/*.md`.
- 48 of 132 hook messages restate a rule or ruling and cite no id. 18 of them are in
  `hooks/question_form.py`.
- The report form "Done, Deviations, Input Needed, Next" is copied into 6 of 9 agent files.
- 4 rulings live only in a skill: `skills/ios-apps/SKILL.md:44-47` (the `hinge` choice) and `:6-8`
  ("each app is its own product"), `skills/waiting-page/SKILL.md:322-323` (never write `answers/`),
  `skills/project-ops/SKILL.md:7` (no setup without the owner's grant). One more lives only in plans:
  the owner's ruling of 2026-11-01 12:23 CST (no optional standard becomes builder load), in
  `docs/plans/test-ci-standard.md:9`.

Experience today:
- Experience has no home. It lives in `docs/debts/notes.md` (43 of 908 lines hold a date, measure or
  incident), in 16 of 64 debt records, in `docs/todo.md`, and in 2 hook messages
  (`hooks/guard_kill.py:915`, `:940`).
- Experience that already became law: `skills/ci-hygiene` (commits b49b7068, e2e0d9cf) and the
  mailaudit lessons that became CLAUDE.md rules (commit 27fea033). Shivpedia points at these. It never
  restates them.

## 3. The rule for each kind

- Law is short. A rule says what to do. It cites its decision by id for the why, the spec and the
  procedure. It never copies them.
- A decision holds the full ruling, the reason and up to about 10 lines of evidence. It never copies
  its rule's text. It cites the rule by id.
- A skill or an agent file cites a rule or a decision by id. It never restates one. An agent file
  keeps its role's own steps and its report cap only.
- A hook message names its rule or decision id and the remedy. It keeps no reason text. The reason
  is in the decision.
- Vocabulary defines a term once. A rule or skill uses the term and never defines it again.
- An experience is never a rule. It never says "always" or "never". The case at hand can outweigh
  it.

## 4. The moves

Each move lists its count, the files and checks it touches, and its invariants. These invariants
hold for every move:
- I1. Each `<!-- rule:ID -->` anchor stays, with its `lint/rule_mechanisms.json` row.
- I2. Text that leaves a rule leaves an id cite in its place.
- I3. No move deletes a guard, check or test.
- I4. A hook-message edit names the test that asserts that string, and changes it red then green.
- I5. `lint/rule_audit.py`, `lint/stale_cites.py`, `lint/check_glossary.py` and
  `lint/compliance_probes.py` pass after each move.

| Move | What | Count | Touches |
|---|---|---|---|
| M1 | Cut the rule text that 8 decisions repeat word for word. Each decision keeps its ruling as argument and cites the rule. | 8 records | the 8 records; `rule_audit.py` |
| M2 | For the other 34 rule-and-record pairs, keep the words in one place: the rule if it is law, the record if it is reason or spec. | 34 pairs | 20 rules, 24 records; `rule_audit.py` |
| M3 | Merge each of the 5 duplicate-ruling pairs into one record. Fix `same-check-kinds:20` in the same move. | 5 pairs | 7 records; every cite of the retired id (`stale_cites.py` finds them) |
| M4 | Move the argument out of 4 rules into their decision: `roles-review-cap-three` to `hold-unsafe-after-round-3`, `verification-cry-wolf-guard-is-spent` to `guard-that-cries-wolf-is-spent`, `questions-go-to-owner` to its decision, `speak-cite-id-plus-gloss` to a new record. | 4 rules | CLAUDE.md; 3 records plus 1 new |
| M5 | Move the procedure out of 7 rules and "Compact instructions" into the skill that does the task. Example: the batch steps of `git-integration-branch-merge` go to `skills/project-ops`. The rule keeps its one law line. | 8 items | CLAUDE.md; `skills/project-ops`, `hooks/precompact_handoff_prompt.md` |
| M6 | Move 7 inline definitions out of rules into vocabulary: safety hole, net-value test, debt, note, one lane, coordinator, cannot be undone, ruling, batch merge, advisor. | 7 rules, 10 terms | CLAUDE.md; vocabulary |
| M7 | Strip the law and argument clauses from 8 glossary rows. Each row keeps its definition and its home. | 8 rows | vocabulary; `check_glossary.py` |
| M8 | Remove the 5 redefinitions in `operating-model.md`. Rename the 3 second senses (lane, owner, debt) to distinct terms in vocabulary. | 8 terms | `skills/project-ops`, `skills/waiting-page`, `skills/roadmap`, `docs/plans/shared-merge-tool.md` |
| M9 | Give the 9 hard-law records a home: add a rule anchor, or record `Kind: build` with its code as home. Then review the 14 uncited records: cite each from its home, or retire it. | 23 records | CLAUDE.md, `rule_mechanisms.json`, `docs/decisions` |
| M10 | Replace the 41 uncited restatements in skills and agents with an id cite. Move the report form to one home, the `reports-*` rules, and cite it from each agent file. | 41 paragraphs | `agents/*.md`, 7 skills |
| M11 | Make the 48 hook messages that restate law name their id. Cut the reason text the decision holds. Move the 2 measured stories in `hooks/guard_kill.py` to their decisions. | 48 messages | 11 hook files and the tests that assert their strings |
| M12 | Give the 5 rulings that live only in a skill or a plan a decision record each. | 5 rulings | 3 skills, 1 plan; 5 new records |
| M13 | Give the `.claude/CLAUDE.md` standing grant a record and a rule anchor. | 1 grant | `.claude/CLAUDE.md`, `rule_mechanisms.json` |
| M14 | Trim the 3 records over the evidence allowance. Rewrite the history wording in place. | 4 records | those records |
| M15 | Move GLOSSARY.md to `skills/shivpedia/vocabulary.md`. See section 5.4. | 1 file, 20 readers | see section 5.4 |
| M16 | Move experience out of `docs/debts/notes.md`, debt records and `docs/todo.md` into shivpedia experiences only when it taught a practice. A gap stays a debt or a note. | unknown, triage judges each | `docs/debts`, shivpedia |

Order: M15 and the shivpedia build go first, because later moves cite vocabulary at its new path. M3,
M9, M12 and M13 come next, because they create or retire record ids that later moves cite. M1, M2,
M4 to M8, M10, M11 and M14 follow, one lane per home file so no two lanes edit one file. M16 is
triage's work after shivpedia exists.

## 5. Shivpedia

### 5.1 Home and shape

- Home: `skills/shivpedia/`. `skills/` already lands (`landed-dirs.txt`), so no layout row changes.
  The skill loads on demand. Nothing loads it at session start.
- `SKILL.md`: a description with 300 characters or fewer, the load steps, the write-back steps and the
  cull. 60 lines or fewer.
- One folder per topic: `testing`, `ci`, `merging`, `guards`, `ui`, `records`, `orchestration`.
  One file per experience (rule `git-record-own-file-per-kind`). A rewrite replaces one file, so two
  lanes conflict only when they rewrite the same experience.
- Each topic folder has a `README.md` with `see:` links to the topic's own law and procedure homes
  (for example `skills/ci-hygiene`, `test-strategy-reset`, `docs/design/principles.md`). Shivpedia
  points at them and never restates them.
- `vocabulary.md` is the moved glossary (section 5.4).

### 5.2 One experience

Front matter, then fields, one line each:

```
---
paths: [".github/workflows/**"]
words: [ci, job, cap, timeout]
---
Happened: <what the work met, in one sentence>
Worked: <what worked, in one sentence>
Applies: <where it applied>
Confidence: low|medium|high, <N> cases
Dates it: <what change would make it stale>
Evidence: <one link: PR, decision id or commit>
Example: <one short use>
Misses: <number>
```

- Size caps: 12 lines in all, 30 words per field.
- Rewrite, never append. A new lesson on the same experience rewrites the file whole. It keeps only
  what is true now. Git keeps the history.
- `lint/check_shivpedia.py` fails a file with a missing field, a second link in Evidence, a date
  or month name, the words "always" or "never", history narration (it imports the patterns of
  `lint/check_comment_narration.py`, one home) or a cap overrun. It also fails a second experience
  with the same slug. It skips `vocabulary.md` and the topic `README.md` files.
- STE lint applies if its scope covers `skills/**/*.md`. That is unknown. The builder checks it and
  widens the scope if needed.
- Code term: `experience`. The word "entry" is in the `record` row's "Not" cell in GLOSSARY.md, so
  it cannot name code (question Q1).

### 5.3 Load by topic, and the test that proves it

- `skills/shivpedia/select.py --task TEXT [--paths P ...] [--base REF]` reads the front matter of each
  experience and prints the topic folders that match. `paths` are matched by glob. `words` are
  matched whole-word and case-blind. `--base` runs one `git diff --name-only`.
- The skill steps: before a plan, run `select.py` and read the experiences it names.
- Red-first tests (`skills/shivpedia/test_select.py`), red on main because the module does not exist:
  - S1: path `.github/workflows/checks.yml` and the task "split the job near its time cap" give `ci`
    only.
  - S2: `docs/design/x.html` gives `ui`, not `ci`.
  - S3: no input gives no output and exit 0.
  - S4: a mixed input gives both topics.
  - S5: the word "circle" does not pick `ci`.
  - S6: an experience with no front matter exits 2 and names the file.
  - C1: the description is 300 characters or fewer.
  - C2: no SessionStart command in `settings.json` names shivpedia.
  - C3: `--paths` starts no git process. `--base` starts exactly one (a probe as in
    `hooks/test_feedback_inbox.py`).
- Red-first tests (`lint/test_check_shivpedia.py`): a tombstone sample (a date, "we used to", an
  incident story, two links) is red, and each fault is named. A padded sample (a 40-word field, 14
  lines) is red. An "always" line, a missing Confidence field and a duplicate slug are each red. One
  clean sample is green.

### 5.4 The glossary move (move M15)

`GLOSSARY.md` becomes `skills/shivpedia/vocabulary.md`. One change updates every reader:
- Rule: CLAUDE.md `speak-one-name-per-thing` ("beside this file"). A form change only.
- Code: `lint/check_glossary.py:45` (the path constant); `lint/compliance_probes.py:41` (text only;
  it reads through the constant at `:872`).
- Tests: `lint/test_check_glossary.py:613`, `:622`; `lint/test_retired_names.py:20`, `:59`;
  `lint/test_compliance_probes.py:846`.
- CI: the step names at `.github/workflows/checks.yml:341-345`.
- Agents: `agents/builder.md:11`, `agents/designer.md:27`, `agents/plan.md:18`, `agents/reviewer.md:17`.
- Skills: `skills/compliance-check/probes.md` (lines 111, 114, 118, 128, 138, 140);
  `skills/project-ops/SKILL.md:33`.
- Prose: `docs/debts/notes.md:898`, `docs/design/last-answer-notes.md:59`; rebuild `docs/records.md`.
- Unchanged: the reads of each child repo's own `GLOSSARY.md` (`lint/compliance_probes.py:879`,
  `lint/test_compliance_probes.py:871-1028`). A child repo's glossary stays at its root.
- Gain: `skills/` lands under `~/.claude`, so a session in any repo can read the vocabulary. Today the
  glossary is not landed (`landed-dirs.txt` names 7 folders), and how a cloud session reaches it is
  unknown.
- Readers in other repos: unknown, because no other repo is attached to this lane. A repo glossary
  that points at `GLOSSARY.md` in claude-settings needs the new path. Triage lists them.

### 5.5 The feed: lessons come in at lane end

- A lane's closing report carries a `Lessons:` line under Next, with 0 to 3 items, or `none`. Each
  item is `<topic>/<slug>: skip|rewrite|add, <one line>`.
- Before it writes the line, the lane runs `select.py` and reads the matching experience. Then it
  skips it, rewrites it whole, or adds a new one. It never adds a second experience for one lesson
  (rule `building-one-home-per-capability`).
- Check: extend `lint/report_guard.py` beside its Unstarted check (`unstarted_problem`,
  `lint/report_guard.py:405`). If a builder-shaped report has no `Lessons:` line, or has
  4 or more items, it is red. It is green on `Lessons: none`. `lint/report_gate.py` is a stub due for deletion,
  so it is not extended. Tests sit in `lint/test_report_guard.py` beside `UnstartedItemsTests`.
- The rule text goes in a new `reports-*` anchor in CLAUDE.md, a `rule_mechanisms.json` row, and
  `skills/project-ops/templates/brief.md`.
- Triage is the one reader. A lane in another repo puts its Lessons in that repo's outbox
  (`skills/project-ops/templates/operating-model.md:118-120`). The claude-settings triage folds them
  in through a records PR (question Q2).

### 5.6 Upkeep: misses and the cull

- Misses: when a new incident matches an experience's Applies field, triage adds 1 to Misses and
  rewrites Worked and Confidence. It keeps no list of stories. The match uses the repeat judge from
  step `feedback-repeat-detect` (commit 0afb9a9f). This plan adds no second matcher.
- The cull: extend `lint/ruling_census.py`, which already reads transcripts on demand, to count the
  shivpedia skill calls and the reads of each experience. At each cull, an experience with 0 loads and
  0 Misses is removed. Cloud transcripts are not on the owner's machine, so a count that cannot be
  read is unknown. An unknown count never culls.

### 5.7 Staying current, through one shared home

The survey read 8 mechanisms that keep a derived doc current. Only one has all four parts
(generator, CI check, rebuild at merge, lane guard): the records page, built by `lint/hook_catalog.py`
and rebuilt by `merge/merge.py` (`rebuild_records`).
- The map cannot be the home. It is checked prose with no generator (`map-check.mjs` checks, a
  session writes each sentence).
- Triage, the roadmap and the waiting page cannot be the home. They publish through the Artifact tool,
  so only a session can run them.

The plan:
- Add a `generator` field to the `lint/layout.json` kinds: a command and a policy, `rebuild-at-merge`
  or `check-only`. Start with the records page.
- Make the 4 consumers of the records path loop over that list: `merge/merge.py` (`RECORDS`,
  `rebuild_records`, `records_proof`, `draft_step`), `hooks/guard_merge.py` (`RECORDS_PAGE`),
  `lint/check_silent_undo.py` (`generated_page`) and `lint/stale_cites.py` (`RECORDS_PAGE`). Then a
  new page edits no consumer. `--records-only` becomes `--page <kind>`.
- Register:
  - the records page (`rebuild-at-merge`)
  - the hook catalog (`rebuild-at-merge`, waived on PR runs like the records page). This closes a
    found gap: the merge tool never rebuilds `docs/catalog.md`, so two lanes that each add a hook
    conflict on it.
  - the map (`check-only`, `.github/scripts/map-check.sh`)
  - shivpedia (`check-only`, `lint/check_shivpedia.py`).
- Shivpedia is checked prose, not a generated page. Each experience is its own source, and
  `select.py` reads front matter at load time, so nothing derived can go stale. It adds nothing to the
  merge-time rebuild. That rebuild caused tonight's incidents (steps `records-page-before-ready` and
  `records-stale-refuses-on-ready`).
- Each path runs on no timer and starts no long-lived process. Check-only runs in CI on each PR. A
  rebuild runs once per `merge --confirm`.

## 6. Cost (rule outcomes-mechanize-rules)

| Path | Trigger | Runs | Writes | Process starts |
|---|---|---|---|---|
| Session start | none | never | nothing | 0; about 75 tokens for the skill description |
| Load | the skill, before a plan | on demand | nothing | 1 python; 1 git with `--base` |
| Shape check | CI `checks` job, `bin/ste-changed` | each PR | nothing | 1 python per CI run |
| Lessons check | `lint/report_guard.py`, where it runs today | each report it reads | nothing | 0 new |
| Fold | triage wake | at each batch merge | experience files, in a records PR | 0 new |
| Cull count | `lint/ruling_census.py` at each cull | on demand | nothing | 0 new; one transcript pass |
| Registry rebuild | `merge --confirm` | once per merge | the registered pages | 1 per `rebuild-at-merge` page |

A test proves each zero: C2 (no SessionStart command) and C3 (process count).

## 7. Seed experiences

Each seed is one experience file. Evidence is one link. The seeds come from:
- the owner-feedback audit, patterns P1-P6 (`docs/plans/owner-feedback-audit.md:162-167` on branch
  `owner-feedback-audit`, commit 6827a12e, draft PR #1008)
- `overlapping-batches` (the merge tool was stricter than its rule; joyous PRs #63 and #65)
- `records-page-before-ready` (the records page was rebuilt after green CI; PR #895)
- `records-stale-refuses-on-ready` (PR #1009, head d39a0040)
- `runner-refuses-lint-red` (lint reds dropped whole batches; PR #979)
- `question-checks-past-rulings` (questions asked again after a ruling)
- `skills/ci-hygiene` (commits b49b7068 and e2e0d9cf): as `see:` links, not copies.

The testing topic links to decision `test-strategy-reset` and to step `test-practices-first-principles`.
That step has no record yet (no branch, no commit). After sign-off, this lane sends that lane one
message with the path `skills/shivpedia/testing/`.

## 8. Build lanes after sign-off

Each lane is briefed from this plan. Each runs test-author, then builder, then reviewer.
1. `shivpedia-core`: `SKILL.md`, `select.py`, `check_shivpedia.py`, topic folders, seeds, the
   skill model row in `docs/decisions/agent-model-cap.md`, rebuild `docs/catalog.md`.
2. `glossary-to-shivpedia`: move M15.
3. `lessons-line`: section 5.5.
4. `derived-doc-registry`: section 5.7.
5. `record-ids`: moves M3, M9, M12, M13.
6. `prose-dedupe-*`: moves M1, M2, M4 to M8, M10, M11, M14, one lane per home file.
7. Triage: M16 and the cull, after lanes 1 to 3 merge.

Lanes 1, 2, 4 and 5 can run at once: they touch different files. Lane 3 waits on lane 1. Lane 6
waits on lanes 2 and 5.

## 9. Questions for the owner

Each blocks only the lane that it names. The plan's recommended pick is marked.

- Q1. The code name for one item in shivpedia. A (recommended): `experience`. B: `entry`, which
  needs the `record` row's "Not" cell in the glossary changed. Blocks lane 1.
- Q2. How a lesson from another repo reaches claude-settings. A (recommended): claude-settings
  triage reads each repo's outbox, and that repo's triage removes the lines it filed. B: each lane
  opens a claude-settings PR. That is work in a second repo, which needs an ask each time under
  `parallelism-keep-going`. Blocks lane 3.
- Q3. What a decision record holds. A (recommended): the full ruling and spec, plus the reason and
  evidence. The rule holds the short law, and neither copies the other. This rewrites only the
  measured duplicates (moves M1 to M4). B: reason only. Then about 138 records split into a rule
  and a reason. Blocks lane 6.
- Q4. Which report must carry `Lessons:`. A (recommended): a report from a builder-shaped turn, the
  same trigger the Unstarted check uses. B: every report that lands work. Blocks lane 3.

## 10. Unknowns

- Whether STE lint covers `skills/**/*.md`.
- How a cloud session reaches GLOSSARY.md today.
- Readers of the glossary path in other repos.
- Load counts for cloud sessions: their transcripts are not on the owner's machine.
- The 12 rule-homed glossary rows not sampled: whether each defines its term or only uses it.
- Proxy counts: section 2 counts come from text patterns. Paraphrase is missed, so the restated-law
  counts are lower bounds.
