# Plan: child guards go up or out

Owner, 2026-11-03 15:58 CST: "evaluate guards individual repos have, like banchi for example, and
whether they should be promoted up to claude-settings and removed from the child repo."

This plan gives each child guard one verdict and one home. A child repo follows claude-settings
(cs), the repo that holds the rules, hooks and shared actions. Owner, 2026-11-02 14:02 and 14:11
CST: cs is the law in each child. A child differs only with a cited exemption and the owner's
grant. Decision child-cites-not-copies (a child names the cs record and never copies it) holds too.

## Intro

- **PROMOTE:** the guard moves to cs. The child drops its copy after cs pins the shared piece.
- **DUPLICATE:** cs already holds the guard. The child copy goes. The row names the cs guard.
- **STAYS:** the guard is a fact of that repo. It does not move.
- **DELETE:** no caller, or no mistake or incident backs it. Rule building-guard-needs-incident
  (in CLAUDE.md: a guard needs a mistake or incident behind it) and decision
  guard-guards-mistakes-only (guards stop Claude's mistakes, not an attacker's) decide it.
- **CONSUMER:** a child calls a cs action or uses a cs setting. The child keeps it.
- **?:** the reader could not confirm the verdict.

A guard is a hook rule that refuses an act. A check is a CI job or a test. The owner's ask
"guards" covers both. The tables keep that word.

| Repo | Visibility | Pinned head |
|---|---|---|
| banchi | public | 0657163 |
| mailaudit | public | cd3e12f |
| q_max | private | 5bbf10e |
| degen | private | 1edba70 |
| joyous | private | 53b5046 |

The cs base is da8d807 (origin/main when this was written).

Public repos get full rows: guard, record, incident, verdict, home or fact. Private repos get a row
number and three fields: guard (file and symbol), verdict, cs home. Private rows carry no prose, no
record ids and no incident text.

## Method

- Five read-only Explore agents (Sonnet, marked `Audit:`), one per repo. Each read the repo's
  records and file headers.
- Shallow clones hold no git history. Incidents come from records and file headers only.
- A "?" marks a verdict the reader could not confirm.
- A row counts once, under its stronger verdict: PROMOTE, then DUPLICATE, then STAYS, then DELETE.
  A split row counts under PROMOTE when one of its parts promotes.
- CONSUMER rows count apart in the counts table.
- Gap: the child copies that cs must absorb. It counts each DUPLICATE part, "?" included, and the
  DUPLICATE part of a split row. mailaudit adds three prose copies moved out of its table.
- Overlap source: the deep audit report, commit 6b6a41f3 (branch audit/deep-1102). Its lane names
  are reused by name. Its line numbers are not cited, because it pinned other heads.
- Shape model: the refusal-vs-rule plan record (docs/plans/refusal-vs-rule.md).
- Lane spot checks on cs main, confirmed:
  - actions/ste-lint/run.sh:54-57 (the STE lint action, STE being the plain-English style the repo
    lints) reads git diff through process substitution. It has no fail-closed check.
  - lint/test_all_jobs_passed.py reads only the cs checks workflow, through CHECKS_YML (the
    variable that sets that path).
  - lint/code_check_standard.json:53 skips the typecheck for javascript. checkJs is not adopted.
  - .github/workflows/checks.yml:89-90 runs zizmor (a GitHub workflow linter) as a plain step.
  - lint/rule_audit.py reads only CLAUDE.md and the shiv-stylisms output style (RULE_FILES).
  - lint/stale_cites.py takes --range only. It has no whole-tree mode.
  - Root settings.json lines 17-28 hold the .env deny rules.
  - lint/test_ci_job.py has no concurrency or draft-if check.
- Private-repo spot checks, reported by the lane and not re-run here: q_max reference-transaction is
  a drifted copy of githooks/main-ref; the q_max skip-locally copy differs from the testing/ copy.
- Source notes:
  - The q_max header counts (STAYS 17, 33 rows) do not match its rows. This record uses the rows:
    STAYS 14, 30 rows.
  - Degen row 8a names a new lint/check_paths.py. This record uses lane prose-path-check-whole-tree,
    which extends lint/stale_cites.py.
  - Joyous rows 2-5 are consumer calls. Joyous row 6 stays, not consumer: it is the child's own
    workflow form, and no cs check covers its concurrency or draft rules.
  - Joyous row 7 and mailaudit row 15 stay "?": cs lint/hook_catalog.py builds cs's own index only.
  - Gold column: it sits on the counts table only. The private rows hold a number and three fields.

## Counts

Target for every row: 0 DUPLICATE copies left in a child.

| Repo | PROMOTE | DUPLICATE | STAYS | DELETE | CONSUMER | "?" rows | Gold |
|---|---|---|---|---|---|---|---|
| banchi (public, 52 rows) | 14 | 14 | 19 | 4 | 1 | 20 | target: 0 DUPLICATE copies left in a child; gap 17 |
| mailaudit (public, 27 rows) | 6 | 1 | 17 | 0 | 3 | 11 | target: 0 DUPLICATE copies left in a child; gap 4 (1 guard, 3 prose) |
| q_max (private, 30 rows) | 6 | 8 | 15 | 0 | 1 | 8 | target: 0 DUPLICATE copies left in a child; gap 8 |
| degen (private, 26 rows) | 5 | 3 | 14 | 1 | 3 | 13 | target: 0 DUPLICATE copies left in a child; gap 3 |
| joyous (private, 19 rows) | 3 | 1 | 11 | 0 | 4 | 7 | target: 0 DUPLICATE copies left in a child; gap 1 |

## Per-repo tables

### banchi (public, 52 rows)

The Record column holds banchi's own decision numbers (D-numbers). Where a row names a cs record
slug, the slug is a cs record. Titles are not carried into this record, so the ids have no per-id
gloss here. The reader did not return the titles.

| # | Guard (file:symbol, what it stops) | Record | Incident | Verdict | Home or fact |
|---|---|---|---|---|---|
| 1 | guard-shell.py: clause_checkout, clause_stash, clause_reset. Stops a checkout or restore path, a stash pop or drop, and reset --hard over a dirty tree. | D179, D173 | 2026-09-06 checkout lost about 240 lines | PROMOTE (reset --merge, --keep); DUPLICATE ? (Codex half) | cs hooks/guard_shared_tree.py:shared_tree_hit missed reset --merge and --keep. Those two are placed in hooks/guard_shared_tree.py reset_discards by lane guard-reset-merge-keep. Skipped in Claude Code. The Codex half has no cs runner (D135). Waits on owner question 1 |
| 2 | guard-shell.py: clause_tree_bash, clause_tree_write. Stops a write outside this checkout. | D179 | 2026-09-06 about 1,500 lines written into the main checkout | DUPLICATE | cs hooks/guard.py rule other-checkout. Double fire live in Claude Code |
| 3 | guard-shell.py: clause_wait. Stops a sleep or poll loop, and a waiter that matches itself in pgrep. | D179, D173 | 2026-09-12 pgrep waiter; 119-round merge loop | DUPLICATE | cs hooks/guard_stream.py:waiter_verdict. Double fire live |
| 4 | guard-shell.py: clause_narrate (NARRATORS). Stops make merge piped into tail. | D235, D179 | 2026-09-20 | PROMOTE (--confirm spelling); DUPLICATE (rest) | cs hooks/guard_stream.py:narrated_tail_hit misses make merge with --confirm piped into tail (probed). Promote that spelling (not placed). The rest double fires live |
| 5 | guard-shell.py: clause_push. Stops git push <remote> HEAD when the upstream has another name. | D179 | 2026-09-12 stray branch on origin | PROMOTE | cs hooks/guard_push_delete.py, beside push_verdict. Lane push-head-upstream-name |
| 6 | guard-shell.py: clause_owner_only, _hatches_set, and the hatch audit rows. Stops an agent that sets a BANCHI_* hatch (an environment switch that turns a guard off). | D179 | none found | STAYS ? | Repo fact: BANCHI_* hatches. cs uses hooks/override.py. Goes if the hatches go |
| 7 | silent-write-guard.py, with its selftest. Stops a git write whose output is discarded. | D171 | 2026-09-12 nine in 24 hours | PROMOTE (file and bash-c clauses); DUPLICATE (rest) | cs hooks/guard.py:silent_write_hit allows an unread-file sink and a bash -c git write. Banchi's Claude-side copy runs only those two clauses (BANCHI_SILENT_WRITE_ONLY=file,bash-c). Promote them (not placed). The rest runs in Codex only. Waits on owner question 1 |
| 8 | reap.py: hook; reap_mark.py, with selftest. Stops a kill by name, or of another session's pid. | D127 | 2026-09-09 and 09-10 pkill -f hit :8000; 2026-09-27 | DUPLICATE ? | cs hooks/guard_kill.py:foreign_pid_kill, pid_is_session_job. Codex only, so no cs runner. Waits on owner question 1 |
| 9 | shell_parse.py. Tokenizer for rows 1, 7 and 8. | D179 | none (library) | DUPLICATE ? | cs hooks/guard_core.py:split_segments, resolve_command, strip_heredoc_bodies (drifted). Codex half has no cs runner. Removal waits on owner question 1 |
| 10 | Permission rule Read(./.env) in banchi's settings. Stops reads of .env. | none | none | DUPLICATE | cs settings.json deny rules (lines 17-28) |
| 11 | guard-opsec.sh. Stops a write that holds a live code-card literal. | D16, D24, D70 | 2026-08-03 two false refusals, narrowed | STAYS | Repo fact: codes/ printed card layout |
| 12 | Permission rules Write(./fixtures/**) and Edit(./fixtures/**), and the pre-commit fixtures rule. Stops edits to fixtures. | no record | none | STAYS ? | Repo fact: fixtures/ holds the round-trip ground truth |
| 13 | typecheck-hook.py. Runs tsc (the TypeScript compiler) after a .ts edit (PostToolUse). | none | 8 days of noise, 2026-08 | DELETE ? | cs actions/code-check runs tsc in CI |
| 14 | decision-context.py. Shows advisory decisions for a file. | D17, D16 | D3 found by violating it | STAYS | Repo fact: docs/map.py governed_by |
| 15 | worktree-guard.sh, githooks/post-checkout, worktree-create.sh, worktree-provision.sh, session-teardown.sh. Stops a bare worktree and orphan supervisors. | D47, D257, D138 | 2026-08-29; 2026-09-06 | STAYS | Repo fact: .venv, harness/.cache, node_modules. Owner ruling: worktree setup per repo |
| 16 | githooks/reference-transaction. Stops local main moving to a commit that is not origin's. | D42 | twice in one day | DUPLICATE | cs githooks/main-ref/reference-transaction |
| 17 | githooks/pre-push main-push refusal. Stops a push to main. | D42 | 5 pushes | DUPLICATE ? | cs main-branch-protection requires one check. It does not refuse pushes. Owner question 4 |
| 18 | githooks/pre-push: guard_branch; revert-audit.py; CI revert-guard. Stops a branch that reverts a file to main's content. | D133 | PR #221 (a banchi pull request) undid PR #218 | DUPLICATE | cs lint/check_silent_undo.py, merge/merge.py undo_check. Lane silent-undo-action |
| 19 | githooks/pre-commit: secrets rule. Stops a wildcard stage that takes a .env file. | D312 | none | PROMOTE | cs githooks/pre-commit (new). The named form is already refused by cs hooks/guard_env.py:env_refusal. Lane precommit-secrets-symlinks |
| 20 | githooks/pre-commit: symlink rules. Stops an absolute or outside symlink from being staged. | D47 | 2026-08-29 a symlink lost a 133 MB mirror | PROMOTE | cs githooks/pre-commit (new). Lane precommit-secrets-symlinks |
| 21 | githooks/pre-commit: zeroth rule (armed hook copy behind main). Stops a stale armed hook copy. | no record | 2026-09-01 unarmed for 4 days | PROMOTE | cs githooks/main-ref/install.sh --check, called by githooks/pre-commit. Lane hook-installer-armed-copy. Owner ruling 2026-11-03 (Cockpit item 208 a) |
| 22 | pre-commit QR rule and qr-clear-check.py; code-layout. Stops a decodable QR image. | D303, D70, D24 | none | STAYS | Repo fact: codes/ |
| 23 | pre-commit bare-hash rule and sigil-check.py. Stops a bare #. | D92, D58, D68 | three renderers | STAYS | Repo fact: D58 sigil |
| 24 | check.yml ci-check shards and ci-static; checks.py registry rows. Suite wiring. | D18, D16 | 121 commits red | STAYS | Repo fact: banchi check registry |
| 25 | check.yml: all-jobs-passed, ci-done, records, code-check; readme-links.yml. Consumes cs actions at pin 49a4165. | n/a | n/a | CONSUMER | Kept |
| 26 | check.yml zizmor. Stops unpinned actions and similar. | no record | none | PROMOTE ? | cs ci-hygiene or a shared action. Lane zizmor-shared-action |
| 27 | check.yml nightly-alarm; demo.yml alarm. Stops a red nightly that shows nowhere. | no record | demo red unseen | DUPLICATE | cs actions/ci-alarm |
| 28 | dropped-start-alarm.yml. Stops a PR with no all-jobs-passed run after a dropped event. | no record | two waits of 1,309 s and 4,141 s | PROMOTE | cs actions/ beside ci-alarm. Lane dropped-start-alarm |
| 29 | check.yml browser-scope and similar; demo.yml. Stops browser matrix cost from running over. | D136, D141, D215, D295 | minutes ran out 2026-09-11 | STAYS | Repo fact: app/tests matrix |
| 30 | suite-lock.py. Stops two browser fleets on one machine. | D122 | 2026-09-07 18 failures | PROMOTE ? | cs testing/ or actions/playwright-setup. Owner question 3 |
| 31 | guard-scope.py, serve-scope.py. Selftests when a host is unreachable. | D247 | 76.6 s of 163.85 s | STAYS ? | Roster. Shrinks as duplicates go |
| 32 | janitor.py, serve-selftest. Stops a supervisor left running. | D138 | 4 orphans | STAYS | Repo fact: serve.py supervisor |
| 33 | primary_sync.py. Keeps the primary checkout off main. | D176, D158 | 3 live sessions | STAYS | Repo fact: the primary serves the live app |
| 34 | mutate-guards.py. Checks that guard suites can go red. | D173 | count drift | STAYS ? | cs hooks/mutate_shared.py is plumbing for cs mutate_guard.py, not a driver a child can run |
| 35 | refusal_log.py, refusal-log-assert.sh. Refusal history. | no record | none | DUPLICATE | cs guard_core log and lint/guard_log_report.py |
| 36 | ste/ste_lint.py. STE (the plain-English style the repo lints) prose check. | D60, D280 | none | DUPLICATE | cs lint/ste_lint.py, actions/ste-lint. Deep-audit lane banchi-ste-lint-one-home (the copy has drifted) |
| 37 | ste_measure.py. Offender counts. | D60, D280 | none | DELETE | Own header: no caller |
| 38 | prose-guard.py --facts. Stops a dropped fact. | D60 | none | DELETE ? | Run by no check |
| 39 | docs-audit line anchors. Checks path:N cites. | D16 | none | PROMOTE | cs lint/stale_cites.py (rule git-cite-by-id: cite by id, not path). Lane prose-path-check-whole-tree |
| 40 | docs-audit paths, allowlist, doc hygiene. Stops missing paths. | D16, D18 | none | PROMOTE | cs lint/stale_cites.py is --range only. Lane prose-path-check-whole-tree |
| 41 | docs-audit make targets and shell substitution. Checks docs against the Makefile and record format. | D16, D135, D160 | silent degrade | STAYS | Repo fact: Makefile, readme_gen.py |
| 42 | docs-audit repo map family. Checks map drift. | D17 | none | STAYS ? | docs/map.py against cs plain-english-map. Owner question 4 |
| 43 | docs-audit slug length, number growth, ids. Slug over 32 characters; number on a branch; ids. | D16 | none | DUPLICATE (ids: STAYS ?) | cs lint/check_record_slugs.py (slug length); actions/stamp (number on a branch) |
| 44 | docs-audit rule enforcement. Hard rule with no enforcer. | D173 | 2026-09-12 | STAYS ? | cs lint/rule_audit.py reads only cs rule files (RULE_FILES). No check reads child rule files. Not placed |
| 45 | docs-audit agent model override. Opus override (a prompt that lifts the Opus refusal) left in settings.local.json. | D178 | 2026-09-19 | DUPLICATE | cs hooks/config_watch.py |
| 46 | docs-audit all-jobs-passed. Checks needs against jobs. | cs same-check-kinds | none | PROMOTE ? | cs actions/all-jobs-passed or compliance_probes. Lane all-jobs-passed-wiring |
| 47 | docs-audit fixed sleeps. waitForTimeout in specs. | no record | none | PROMOTE ? | cs lint/ for Playwright repos. No lane yet |
| 48 | docs-audit design rows and css-var-check and similar. Design floor drift. | D118 and others | D118 | STAYS | Repo fact: docs/DESIGN.md |
| 49 | docs-audit code-invariant rows (about 30). Product rules. | D63 and others | mixed | STAYS | Repo fact: store/, pipeline/ |
| 50 | docs-audit threshold, model-bytes and similar agreement rows. Two copies drift. | D173 | none dated | DELETE ? | False alarms unmeasured. A single source is cheaper |
| 51 | Harness and 31 product selftests. | per D | n/a | STAYS | Product |
| 52 | Makefile pytypes, lint (ruff), typecheck. Runs mypy, ruff and tsc. | D18, D82 | 2026-09-06 | DUPLICATE ? | cs actions/code-check. No lane yet |

Notes: rows 2, 3 and the DUPLICATE part of row 4 double fire live in Claude Code. Codex (the second
agent, which reads banchi's .codex/hooks.json) runs rows 1 and 8 and the rest of row 7. Row 9 is the
tokenizer for them. cs ships no Codex hooks.

### mailaudit (public, 27 rows)

The Record column holds mailaudit's record slugs. Their titles are not carried into this record.
Rows that restated cs rules moved to the Duplicate removals section as prose copies.

| # | Guard (file:symbol, what it stops) | Record | Incident | Verdict | Home or fact |
|---|---|---|---|---|---|
| 1 | test.yml all-jobs-passed and ci-done; ci-alarm.yml; test.yml ste-lint. Stops a bad rollup, a red nightly, and bad prose. | ci-skips-draft-prs and others | none | CONSUMER | cs actions/* |
| 2 | test.yml zizmor; dependabot cooldown. Supply-chain checks. | ux-house-rules-govern | none | DUPLICATE ? | cs skills/ci-hygiene snippet s7. Each repo copies it. Lane zizmor-shared-action |
| 3 | test.yml scope and native; .github/native-paths.regex. Stops the Mac runner on a diff with no native code. | native-ci-on-hosted-macos | none | STAYS | Repo fact: the native-paths regex. cs skills/ios-apps/templates/.github/workflows/ios.yml.tmpl has no such regex, and its scope skips docs-only diffs |
| 4 | test.yml workflow shape (draft if, concurrency, timeout). Stops hung or cancelled runs. | ci-skips-draft-prs | none | STAYS | cs lint/test_ci_job.py has no concurrency or draft-if check. ci-hygiene step 11 is prose. No shared check (not placed) |
| 5 | test/ci-wiring.test.mjs asserts 0-8, 3c, 7. Stops a rollup missing a job, a missing draft guard, and pin drift. | ci-skips-draft-prs | cs action-pins-follow-sessions (the incident) | PROMOTE | lint/test_all_jobs_passed.py reads only the cs checks workflow. Generalize with lint/workflow_steps.py. Lane all-jobs-passed-wiring |
| 6 | ci-wiring asserts 9-11, a-n, i1-i5. Milestone and stamp wiring. | milestone-runs-full-suite | none | STAYS ? | Repo workflows |
| 7 | scripts/milestone-due.mjs; milestone jobs. Stops a broken native batch on main. | milestone-runs-full-suite | cs waiting-page item 133 (open question on Swift tests) | PROMOTE ? | skills/ios-apps (its template has no milestone job). After the first green hosted run. Owner question 3 |
| 8 | build.mjs --check. Stops a stale committed index.html. | build-and-deploy | none | STAYS | Committed Pages build |
| 9 | build.mjs --check-seed; test 38d.5. Stops ledger data in the public page. | check-seed-backstop-not-proof | stamp-note leak | STAYS ? | Public Pages build. Two checks read the same thing |
| 10 | build.mjs --check-rules. Stops stale rules.js for Swift. | rules-run-in-javascriptcore | none | STAYS | JSC (JavaScriptCore, the JS engine in Swift) bundle |
| 11 | scripts/check-golden.mjs. Stops golden drift. | shared-tokens-and-fixtures | none | STAYS | Fixtures |
| 12 | check-docs.mjs claim 1: suite count. Stops a wrong published count. | ci-runs-in-utc, suite-size | UTC, one fewer | STAYS ? | Closest to DELETE. Owner question 6 |
| 13 | check-docs.mjs claims 2-4: paths, code names, links. Stops prose that names a missing path. | records-hold-current-text-only | none | PROMOTE ? | lint/stale_cites.py (lane prose-path-check-whole-tree). Rule verification-checked-reader-for-numbers is unmechanized (lint/rule_mechanisms.json:331) |
| 14 | check-records.mjs claims 1-4 and 8: cites resolve, fences, duplicate slug, debt Decision. Stops a dead cite, a broken fence, and a debt with no decision. | debts-hold-known-gaps | fenced old text skipped lint | PROMOTE ? | lint/check_record_slugs.py. No lane yet. Debt format mismatch |
| 15 | check-records.mjs claim 5: orphan and hand index. Stops a record missing from the hand index. | invariants-cited-by-slug | false orphans, fixed | STAYS ? | cs lint/hook_catalog.py builds cs's own index only |
| 16 | check-records.mjs claim 6: invariant names a test. Stops an invariant without a test. | invariants-cited-by-slug | one number, two rules | STAYS | Invariants kind |
| 17 | check-records.mjs claim 7: Holds while. Stops a decision that outlives its reason. | records-name-what-dates-them | public-ledger line outlived | PROMOTE ? | Owner question 3. Fact: 0 of 169 cs decisions carry the line |
| 18 | test/screens.mjs claims 1, 8, 9: overflow, a11y, 44 px targets. | screens-checked-headless-in-ci | 3 unexplained reds (flake debts) | PROMOTE ? | bin/shoot checks blank and HTTP only. Owner question 3 |
| 19 | test/screens.mjs other claims. Layout. | no-layout-shift-under-pointer | none | STAYS | App layout |
| 20 | .claude/shoot.json. Config. | none | none | CONSUMER | Config, kept. cs bin/shoot |
| 21 | app.test.mjs:186 FORBIDDEN_WORDS, :216, :7922; SyncLineTests.swift:25. GitHub words in sync UI. | ruled-head-one-advisory-entrance | none | STAYS | Sync is Worker-only (the server-side script). Four lists differ and need one home in the repo |
| 22 | AuditSkippingTabBarUITests.swift. Accessibility audit that skips too much. | audit-skips-measured-flags | caught 3 faults | STAYS ? | Could join the iOS template |
| 23 | Product tests. | invariants | per test | STAYS | Product |
| 24 | Branch protection and stamp.json. Stops a merge without all-jobs-passed. | main-moves-only-by-pr | none | CONSUMER | Use of cs main-branch-protection, not a file copy. Kept |
| 25 | claims-and-tests-change-together. Claim and test drift. | n/a | none | STAYS | Banner convention |
| 26 | .claude/rules/*.md; layout-extras.json. Indexes. | n/a | none | STAYS | Path globs |
| 27 | test.yml push paths filter. Data push triggers a build. | ci-filters-guarantee-no-rebuild | none | STAYS | Data branch |

Notes: check-records claim 8 cites a retired anchor (see side findings).

### q_max (private, 30 rows)

Labels such as DOC1 and ENV1 are the audit's row labels. The audit gives no file and symbol for them.

| # | Guard (file:symbol) | Verdict | cs home |
|---|---|---|---|
| 1 | .claude/hooks/reference-transaction (drifted copy) | DUPLICATE | githooks/main-ref/reference-transaction |
| 2 | .claude/hooks/session_start_deps.py:install_main_ref_hook | DUPLICATE ? | githooks/main-ref/install.sh |
| 3 | .claude/hooks/session_start_deps.py (deps, report) | STAYS | none |
| 4 | .claude/hooks/stop_budget.py | STAYS | none |
| 5 | harness/janitor-tier.sh | STAYS ? | none |
| 6 | .claude/skills/plain-english-map/ | DUPLICATE | skills/plain-english-map (owner question 2) |
| 7 | harness/checks/plain-english-map.mjs:registerPlainEnglishMap | STAYS | none |
| 8 | harness/import-reader.mjs, source-text.mjs, lazy-typescript.mjs | DUPLICATE ? | skills/plain-english-map/scripts/lib/ |
| 9 | harness/tests/skip-locally-fail-in-ci.mjs | DUPLICATE | testing/skip-locally-fail-in-ci.mjs |
| 10 | CI workflow: zizmor step | DUPLICATE | lane zizmor-shared-action |
| 11 | CI workflow: calls to cs actions, and the job that runs all-jobs-passed | CONSUMER | actions/* (kept) |
| 12 | CI workflow: static type-check step | DUPLICATE ? | actions/code-check run_tsc |
| 13 | CI workflow: base-commit read step | PROMOTE | actions/ste-lint/run.sh fail-closed (lane ste-lint-diff-fail-closed) |
| 14 | CI workflow: silent-undo glue (about 50 lines) | PROMOTE | new shared action wrapping lint/check_silent_undo.py (lane silent-undo-action) |
| 15 | harness/tests/all-jobs-passed.test.mjs | PROMOTE ? | lint/test_all_jobs_passed.py (lane all-jobs-passed-wiring) |
| 16 | harness/ci-changes.mjs | STAYS | none |
| 17 | harness/assert-node-floor.mjs | STAYS | none |
| 18 | harness/load-files.mjs | STAYS, partly | actions/code-check (lane mjs-load-files, PR #1135) |
| 19 | tiers.yml, harness/probes/*, browser.yml | STAYS | none |
| 20 | harness/browser/* | STAYS | none |
| 21 | harness/specimen/* | STAYS | none |
| 22 | check-invariants.mjs:check frame | STAYS | none |
| 23 | DOC4, DOC5, DOC6 (labels) | PROMOTE ? | lint/stale_cites.py (lane prose-path-check-whole-tree) |
| 24 | DOC1 (label) | PROMOTE | lint/stale_cites.py (lane prose-path-check-whole-tree) |
| 25 | DOC11 (label) | DUPLICATE | actions/stamp, stamp.mjs --check |
| 26 | DOC2, DOC3, DOC8, DOC12, DOC13, DOC14, DC1-3 (labels) | STAYS | none |
| 27 | ENV1 (label) | PROMOTE ? | none in cs yet (hooks/guard_env.py covers .env files only). No lane yet |
| 28 | SEC1, SEC2, ST3 (labels) | STAYS ? | none |
| 29 | Product check groups (4) | STAYS | none |
| 30 | Product tests | STAYS | none |

### degen (private, 26 rows)

| # | Guard (file:symbol) | Verdict | cs home |
|---|---|---|---|
| 1 | .github/workflows/check.yml scope step | STAYS ? | none |
| 2 | Check, links and nightly workflow jobs that call cs actions | CONSUMER | cs actions/* (pinned da8d8073) |
| 3 | Makefile lint-py: ruff check (ruff, a Python linter) | DUPLICATE ? | lint/code_check_standard.json (ruff 0.17.3). This repo pins 0.17.0. Remove the local pin |
| 3b | Makefile lint-py: ruff format check | STAYS ? | none |
| 4 | Makefile lint-js: tsc --noEmit | DUPLICATE | actions/code-check typescript (runs twice in CI today) |
| 5 | Makefile lint-actions: zizmor | PROMOTE ? | new actions/zizmor (lane zizmor-shared-action) |
| 6 | check.yml STE step; Makefile lint-ste | CONSUMER | actions/ste-lint |
| 7 | scripts/gen.py BLOCKS, FILES gen-check | STAYS ? | none |
| 8a | scripts/paths_check.py main, parts 1-2 | PROMOTE | lint/stale_cites.py (lane prose-path-check-whole-tree) |
| 8b | scripts/paths_check.py MAX_SLUG | DUPLICATE | lint/check_record_slugs.py |
| 8c | scripts/paths_check.py REQUIRED_LINES | STAYS ? | none |
| 9 | Makefile records-check | CONSUMER | actions/stamp, lint/check_record_slugs.py |
| 10 | scripts/bulk_pace_check.py | STAYS | none |
| 11 | scripts/addon_check.py | STAYS | none |
| 12 | ops/<add-on>/guard.sh:job_problem | STAYS | none |
| 13 | scripts/native_ci_check.py:problems | DELETE ? | none (section Deletes) |
| 14 | scripts/native_run_check.py, and its native-record job | STAYS ? | none |
| 15 | tools/deploy-degen deploy steps | STAYS | none |
| 16 | ops/lan-check.py | STAYS ? | none |
| 17 | tools/waiting_export.py SCAN_RULES | PROMOTE ? | skills/waiting-page (no export scan in cs). Owner question 3 |
| 18 | scripts/comment_check.py (make comment-check) | PROMOTE | actions/code-check local entry point (lane comment-check-local-entry) |
| 19 | tests/run.py main | PROMOTE ? | bin/verdict per-module refusal (lane empty-test-run-guard). cs bin/verdict covers whole runs only (lint/test_verdict.py:222) |
| 20 | tests/run.py check_shards | STAYS ? | none |
| 21 | contract, types and tokens checks | STAYS | none |
| 22 | native ScanTests.swift | STAYS ? | none |
| 23 | Product tests | STAYS | none |

### joyous (private, 19 rows)

| # | Guard (file:symbol) | Verdict | cs home |
|---|---|---|---|
| 1 | .github/workflows/checks.yml ste-lint job: zizmor step | DUPLICATE | lane zizmor-shared-action. The job's call to actions/ste-lint is consumer, kept |
| 2 | .github/workflows/checks.yml code-check job | CONSUMER | actions/code-check |
| 3 | .github/workflows/checks.yml all-jobs-passed job; .github/stamp.json | CONSUMER | actions/all-jobs-passed |
| 4 | .github/workflows/checks.yml ci-done job | CONSUMER | actions/ci-done-comment |
| 5 | .github/workflows/links.yml readme-links | CONSUMER | actions/readme-links |
| 6 | .github/workflows/checks.yml workflow form (caps, pins, permissions, concurrency, draft skip) | STAYS | none (no shared check, see Not placed) |
| 7 | docs/records.md index claim | STAYS ? | none (cs lint/hook_catalog.py builds cs's own index only) |
| 8 | .github/workflows/checks.yml scope step (runs the base branch copy of the scope script) | PROMOTE ? | skills/ci-hygiene/snippets.md s.19. Not placed |
| 9 | package.json scripts.test (empty-glob check) | PROMOTE ? | skills/ci-hygiene/snippets.md (lane empty-test-run-guard) |
| 10 | tests/docs.test.mjs 1a | STAYS ? | none (cs lint/rule_audit.py reads cs rule files only) |
| 11 | tests/docs.test.mjs 1b | PROMOTE ? | lint/stale_cites.py (lane prose-path-check-whole-tree) |
| 12 | tests/docs.test.mjs 1c: Re-check when | STAYS ? | none |
| 13 | .github/scripts/ci-scope.sh; tests/ci/scope.test.ts | STAYS | none |
| 14 | tests/no-media.test.mjs | STAYS | none |
| 15 | private-data tests (file names withheld) | STAYS | none |
| 16 | tests/redirects.test.mjs | STAYS | none |
| 17 | two screen tests (names withheld) | STAYS | none |
| 18 | tests/isolation.test.mjs | STAYS ? | none |
| 19 | Product tests | STAYS | none |

## Promotion lanes

Rank is the work order. Rank 1 ships first. Each lane's slug is its branch name. Child removals
are lanes in that child. A child removal starts only on the owner's ask.

Every lane follows one order: the child pins the shared action or hook first, then removes its
copy, so no CI gap.

### 1. prose-path-check-whole-tree

- **cs files:** lint/stale_cites.py gets a whole-tree mode for dead and typo paths, and path:N
  line anchors. The script runs in --range mode only today. Rule git-cite-by-id requires cites by
  id, because a path breaks when its file moves. Tests: lint/test_stale_cites.py.
- **Done check:** new cases in lint/test_stale_cites.py run red on the current script, then green
  after the change.
- **Child removals:** banchi rows 39 and 40 (docs-audit line anchors and paths). Degen row 8a
  (scripts/paths_check.py parts 1-2), and its copy of the hook catalog's records list
  (scripts/paths_check.py:23-24). Joyous row 11. Mailaudit row 13. Q_max rows 23-24.
- **Order:** the child pins the shared action or hook first, then removes its copy, so no CI gap.
- **Repos:** five.

### 2. ste-lint-diff-fail-closed

- **cs files:** actions/ste-lint/run.sh. Its git diff reads at lines 54-57 fail open. Tests:
  actions/ste-lint/test_action.py.
- **Done check:** new case in actions/ste-lint/test_action.py: a bad base makes the step exit
  non-zero. Red on the current script, green after.
- **Child removals:** every child re-pins the action and gets the fix. Removal of a copy: q_max
  row 13 (its own base-commit read step).
- **Order:** the child pins the shared action or hook first, then removes its copy, so no CI gap.

### 3. zizmor-shared-action

- **cs files:** new actions/zizmor/ (action.yml, test_action.sh). The plain zizmor step at
  .github/workflows/checks.yml:89-90 switches to the action. The pin stays zizmor==1.30.1.
- **Done check:** actions/zizmor/test_action.sh is red before the action exists and green after.
  checks.yml runs the action with the same pin.
- **Child removals:** banchi row 26 (check.yml zizmor step); degen row 5 (Makefile lint-actions
  target); joyous row 1 (ste-lint zizmor step); mailaudit row 2 (test.yml zizmor step); q_max
  row 10 (its zizmor step).
- **Order:** the child pins the shared action or hook first, then removes its copy, so no CI gap.
- **Note:** one home for one tool. No incident found.

### 4. all-jobs-passed-wiring

- **cs files:** lint/test_all_jobs_passed.py takes any workflow path. Today it reads only the cs
  checks workflow (CHECKS_YML). Checks.yml:257 runs it. It reads steps through lint/workflow_steps.py,
  the one home of the step parser. The action actions/all-jobs-passed (action.yml, check.sh,
  test_action.sh) passes the path through.
- **Done check:** new case in lint/test_all_jobs_passed.py gives a second workflow path and expects
  that workflow's all-jobs-passed job to be checked. Red on the current script, green after.
  actions/all-jobs-passed/test_action.sh stays green.
- **Child removals:** mailaudit row 5 (test/ci-wiring.test.mjs assertions 0-8, 3c and 7); q_max
  row 15 (its all-jobs-passed test); banchi row 46.
- **Order:** the child pins the shared action or hook first, then removes its copy, so no CI gap.

### 5. silent-undo-action

- **cs files:** new actions/silent-undo/ (action.yml, test_action.sh). It wraps
  lint/check_silent_undo.py, which keeps its own tests in lint/test_check_silent_undo.py.
- **Done check:** actions/silent-undo/test_action.sh: a branch that reverts a file to its main
  content fails through the action. Red before the action exists, green after.
- **Child removals:** q_max row 14 (its silent-undo glue, about 50 lines); banchi row 18
  (revert-audit.py, the CI revert-guard and the pre-push guard_branch rule). Incident: PR #221 (a
  banchi pull request) undid PR #218.
- **Order:** the child pins the shared action or hook first, then removes its copy, so no CI gap.

### 6. comment-check-local-entry

- **cs files:** actions/code-check/code_check.py gains a local entry point, so drafts are checked.
  Tests: actions/code-check/test_action.py.
- **Done check:** new case in actions/code-check/test_action.py runs the local entry point on a
  draft and expects it checked. Red before, green after.
- **Child removals:** degen row 18 (scripts/comment_check.py and its make target).
- **Order:** the child pins the shared action or hook first, then removes its copy, so no CI gap.

### 7. precommit-secrets-symlinks

- **cs files:** new githooks/pre-commit, beside githooks/main-ref/. It refuses a wildcard stage
  (git add -A, git add .) that would take a .env file, and a symlink that is absolute or points
  outside the repo. The named form git add .env is already refused by env_refusal. Tests: new
  githooks/test_pre_commit.sh.
- **Done check:** githooks/test_pre_commit.sh: a wildcard stage that takes a .env file, and an
  outside symlink, are both refused. Red before the hook exists, green after.
- **Child removals:** banchi row 19 (wildcard .env rule) and row 20 (symlink rules). Incident:
  2026-08-29 a symlink lost a 133 MB mirror.
- **Order:** the child pins the shared action or hook first, then removes its copy, so no CI gap.

### 8. push-head-upstream-name (?)

- **cs files:** hooks/guard_push_delete.py. push_verdict allows a push that is not forced. An
  explicit HEAD takes the checkout's current name (_push_dest). So a HEAD push to a name other
  than the upstream passes. The lane judges that push. Tests: new cases in hooks/test_guard.py.
- **Gap:** read from the code. Not run. Confirm the stray-branch case before the lane starts.
- **Done check:** new cases in hooks/test_guard.py: git push origin HEAD, on a branch whose upstream
  has another name, is asked. Red on the current code, green after.
- **Child removals:** banchi row 5 (clause_push). Incident: 2026-09-12 a stray branch on origin.
- **Order:** the child pins the shared action or hook first, then removes its copy, so no CI gap.

### 9. dropped-start-alarm

- **cs files:** actions/ci-alarm/ (alarm.sh, events.json) gains the dropped-start case: a PR with
  no all-jobs-passed run after a dropped event. Tests: new case in
  actions/ci-alarm/test_action.sh.
- **Done check:** a dropped-start fixture in actions/ci-alarm/test_action.sh. Red before, green after.
- **Child removals:** banchi row 28 (dropped-start-alarm.yml). Evidence: two waits of 1,309 s and
  4,141 s.
- **Order:** the child pins the shared action or hook first, then removes its copy, so no CI gap.

### 10. empty-test-run-guard (?)

- **cs files:** skills/ci-hygiene/snippets.md gets the empty-glob snippet. bin/verdict refuses a
  module that ran no test. Today bin/verdict covers whole runs only (lint/test_verdict.py:222).
  Tests: new case in lint/test_verdict.py.
- **Done check:** a module with zero tests is a FAIL in lint/test_verdict.py. Red before, green after.
- **Child removals:** degen row 19 (tests/run.py main); joyous row 9 (package.json test script,
  empty-glob check).
- **Order:** the child pins the shared action or hook first, then removes its copy, so no CI gap.
- **Note:** "?" because no incident was found.

### 11. mjs-load-files

- **cs files:** actions/code-check covers .mjs imports. Its standard, lint/code_check_standard.json, skips the javascript
  typecheck (checkJs not adopted). Tests: new case in actions/code-check/test_action.py.
- **Done check:** a .mjs file with a broken import is red on the current code, green after.
- **Child removals:** q_max row 18 (harness/load-files.mjs) stays, partly. PR #1135 (lane mjs-load-files) found that the shared check misses a bare package absent from node_modules, and .ts files run through tsx. The child keeps its own check for those until its own tsc covers them.
- **Order:** the child pins the shared action or hook first, then removes its copy, so no CI gap.

### Not placed in a lane

These items have no lane and no owner question yet. Each needs a lane or an owner call:

- banchi row 4: promote the --confirm spelling into hooks/guard_stream.py.
- banchi row 7: promote the file and bash-c clauses into hooks/guard.py silent_write_hit.
- banchi row 21 (zeroth hook copy) and row 47 (fixed sleeps in Playwright specs).
- banchi row 44 and joyous row 10: lint/rule_audit.py reads only cs rule files. No check reads child
  rule files.
- Workflow shape (mailaudit row 4, joyous row 6): no shared check. lint/test_ci_job.py has no
  concurrency or draft-if check.
- mailaudit row 14 (check-records claims 1-4 and 8).
- joyous row 8 (scope step).
- q_max row 27 (ENV1).

## Duplicate removals

These removals have no cs lane. Each is a child lane, and starts only on the owner's ask. A row
that waits on a lane or an owner question says so.

### banchi

- Double fire live in Claude Code: rows 2, 3, and the DUPLICATE part of row 4. Remove each child
  copy. cs holds the guard: row 2, hooks/guard.py rule other-checkout; row 3,
  hooks/guard_stream.py:waiter_verdict; row 4, hooks/guard_stream.py:narrated_tail_hit.
- Row 7, DUPLICATE part: cs hooks/guard.py:silent_write_hit holds it. It runs in Codex only and
  waits on owner question 1.
- Rows 1 and 8 (Codex halves) and row 9 (tokenizer): wait on owner question 1.
- Row 10: cs settings.json deny rules (lines 17-28).
- Row 16: cs githooks/main-ref/reference-transaction.
- Row 17: cs main-branch-protection does not refuse pushes. Waits on owner question 4.
- Row 18: waits on lane silent-undo-action (rank 5).
- Row 27: cs actions/ci-alarm.
- Row 35: cs guard_core log and lint/guard_log_report.py.
- Row 36: deep-audit lane banchi-ste-lint-one-home (the copy has drifted from cs lint/ste_lint.py).
- Row 43: cs lint/check_record_slugs.py (slug length) and actions/stamp (number on a branch).
- Row 45: cs hooks/config_watch.py.
- Row 52: cs actions/code-check. No lane yet.
- Deep-audit lanes dup-broad-roots and dup-shell-set cover copies inside banchi's own guard files.
  They match no row here, so they stay with the deep audit.
- banchi's CLAUDE.md copies are not table rows. Deep-audit lanes claude-md-copies (one home for
  copied rules) and banchi-opus-list-cites (the Opus list copy) cite the cs rule instead.

### mailaudit

- Row 2: lane zizmor-shared-action (rank 3).
- Records that restate cs rules, prose copies (cs rule: child-cites-not-copies). Shrink each to a
  pointer. No lane yet:
  - Six records restate cs rulings. Shrink each to a pointer.
  - Fourteen testing-* lesson records (DUPLICATE ?). cs docs/decisions/test-practices.md holds the
    same habits.
  - Records that hold current text and debts that hold known gaps restate prose habits. Rule
    speak-rewrite-superseded-in-place (rewrite old text in place) holds them.
- Row 1 (consumer), row 20 (config) and row 24 (use of cs main-branch-protection) stay.

### q_max

- Rows 1 and 2: the drifted copy of the reference-transaction hook, and install_main_ref_hook.
  Replace both with the cs githooks/main-ref install and hook.
- Row 9: import the cs testing/skip-locally-fail-in-ci.mjs copy.
- Row 6: the plain-english-map skill copy. Owner question 2. Its three helpers (row 8) belong in cs
  skills/plain-english-map/scripts/lib/. No lane yet.
- Row 12 ("?"): cs actions/code-check run_tsc. No lane yet.
- Row 10: the zizmor step. Lane zizmor-shared-action.
- Row 25: cs actions/stamp, stamp.mjs --check.
- Rows 23-24 are lane prose-path-check-whole-tree (rank 1).
- Row 11 (consumer calls) stays.

### degen

- Row 3 (ruff, "?"): cs lint/code_check_standard.json pins ruff 0.17.3. This repo pins 0.17.0.
  Remove the local pin. Ruff format stays.
- Row 4: tsc --noEmit runs twice in CI. Remove the local step. cs actions/code-check typescript runs
  it.
- Row 8b: cs lint/check_record_slugs.py.
- Rows 2, 6 and 9 (consumer calls) stay.

### joyous

- Row 1 (zizmor step): lane zizmor-shared-action (rank 3).
- Rows 2-5 are consumer calls. They stay.
- Row 6 stays. Row 7 stays "?" (cs hook_catalog builds cs's own index only).

## Deletes

- banchi scripts/ste_measure.py (row 37): DELETE, firm. Its header says it has no caller.
- banchi typecheck-hook.py (row 13, "?"): cs actions/code-check runs tsc in CI.
- banchi prose-guard.py --facts (row 38, "?"): run by no check.
- banchi docs-audit agreement rows (row 50, "?"): false alarms unmeasured. A single source is
  cheaper.
- degen scripts/native_ci_check.py (row 13, "?"): tied to an open item in a degen record. Not
  decided here. Owner question 5.

## Owner questions

Wording belongs to the lane that asks.

1. Codex-only banchi guards: rows 1 and 8 (Codex halves), row 9 (the tokenizer), and the rest of
   row 7. cs ships no Codex hooks. Keep, port, or delete?
2. q_max plain-english-map skill copy (q_max row 6) against cs SKILL.md ("a host never copies").
   Which rule holds?
3. Single-repo PROMOTE rows: mailaudit rows 7, 17 and 18; banchi row 30; degen row 17. Promote now,
   or wait for a second repo?
4. banchi's own owner calls: row 5 (lane push-head-upstream-name), row 17 (a push-to-main guard,
   since cs main-branch-protection does not refuse pushes), row 21 (the zeroth hook copy), row 30,
   and row 42 (the repo map family).
5. Degen native check (degen row 13, section Deletes). Delete, or keep?
6. mailaudit row 12 (the suite count claim). Closest to DELETE. Keep, or delete?
7. cs main, docs/plans/test-ci-standard.md line 105, names a degen rule and a degen script. cs is
   public. Keep that text, or remove it?

## Side findings

- mailaudit check-records.mjs claim 8 cites a retired anchor name. The live anchor
  is roles-findings-are-debts-or-notes (a finding becomes a debt or a note).
- actions/claude-md-cites runs in no child CI. The deep audit says the same. actions/ruling-kind is
  wired in neither mailaudit nor joyous. The reader also says banchi, per the deep audit. Not
  checked here.
- mailaudit's screens job runs `npx playwright install` in place of actions/playwright-setup.
- cs .github/workflows/checks.yml:71 runs .github/scripts/ci-scope.sh from the checkout. Joyous
  runs the base branch's copy (joyous row 8). Whether the cs checkout is the PR head is "?", not
  checked here. Related: deep-audit lane ci-scope-playwright-action (a PR that edits the Playwright
  action skips the run that uses it).
- Owner question 7 covers the public cs file that names a degen rule and script.
- Rule verification-checked-reader-for-numbers (every published number gets a checked reader) is
  unmechanized, per mailaudit row 13.
