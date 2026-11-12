# Fan-out lanes, 2026-11-12 07:23 CST (triage)

Source: plans/fanout-2026-11-12.md, minus the steps laned at 07:20 CST and the two waiting on owner sign-off (spawn-rules-skill, mechanize-cost-to-hooks-rule). 307 steps in 57 lanes.

How lanes were cut: steps of one repo and one kind (code or prose) that name the same file, or the same home when they name no file, are one group, so no two lanes edit one file. A group over 8 steps splits into parts that run in order ("after" names the part before). Files and homes are read from step text, not from code: each lane confirms its files first. Steps marked "unmapped" named no file or home; their lanes share nothing known and may still clash. Each lane checks every step's ruling source first and reports a step with none instead of building it (coordinator 07:21 CST, owner ruling 13:51 CST Nov 11).

## Coordinator picks (process-only, can be undone; 07:31 CST Nov 12)

1. A step with an old open PR is carried forward on a fresh branch from main, not rebuilt.
2. A lane builds a step of the other kind too and hands it in under its true kind; kind splits batches, not lanes.
3. A step already done on main is closed, not built.
4. A base PR that no live lane holds is carried by the lane that needs it; that lane tells triage the step, and triage sets its lane field (07:35 CST).
5. Before carrying a base PR, a lane looks it up in plans/open-pr-owners-2026-11-12.md (07:33 CST).

## code-agents

- Kind: code. Repo: claude-settings.
- Files or homes: agents
- Steps:
  - agent-asks-become-refusals: A guard that asks the owner about an agent's act that is always wrong there refuses it to the agent  (ruling text: "Owner 09:08")
  - agent-output-terse-line: Each agent role file and the lane start text carry one short-output line, proven by a check (ruling text: "owner 2026-11-11 12:49")
  - brief-write-needs-writer: A brief that asks a read-only agent to write a file is refused (ruling text: "owner 13:51")
  - commit-trailer-model: An agent's commit names the agent's own model in its Co-Authored-By trailer, and a check refuses one (ruling text: "owner 13:20")
  - guard-relative-write-escape: The write-outside-the-checkout guard refuses a relative `../` path that leaves the agent's worktree (ruling text: "owner 13:20")
  - model-guard-next-only: The model-name report guard does not ask for a model on agents named only under Next (ruling text: "owner 13:20")
  - resume-msg-role-check: A message to a running agent passes the same role check as its spawn brief (ruling text: "Owner Q2 = B (09:12")

## code-check-cost-pins

- Kind: code. Repo: claude-settings.
- Files or homes: .github/workflows/checks.yml, handoffs/session_013NEJL43txwp8ioromcR8yF.md, lint/check_cost_pins.py, lint/check_python_floor.py, lint/check_unknown_reads_contract.py, lint/test_agent_push_form.py, lint/test_check_python_floor.py
- Steps:
  - cost-line-has-reader: A record's cost-line counts have a checked reader, or state a bound (ruling text: "coordinator pick")
  - lane-lint-cloud-time-limit: Lane lint gives a verdict inside the cloud's command time limit (ruling text: "owner's word")
  - unknown-read-one-rule: One rule for an unknown read: every check fails in CI when it can't read its input (ruling text: "Owner on item 275 (12:19")

## code-decisions

- Kind: code. Repo: claude-settings.
- Files or homes: docs/debts, docs/decisions, docs/decisions/stall-watch.md, docs/plans/child-guard-promotion.md, docs/plans/r42-part2-design.md, docs/plans/sim-lease-gaps.md
- Steps:
  - child-copies-cleanup: One cleanup lane per child repo removes copies that decision child-cites-not-copies replaces with ci (ruling text: "owner 20:24")
  - merge-flow-after-anthropic: Design a merge flow after Anthropic's: lanes merge on own green checks, main bisects and reverts, se (ruling text: "owner 2026-11-11 13:39")
  - push-agent-branch-asks: The push guard asks before an agent-worktree branch with no upstream is pushed (ruling text: "owner 13:20")
  - ruling-cite-in-commit: A commit message that cites a ruling names its home and time (ruling text: "owner ruling")
  - ruling-skip-check: A pick skipped under a ruling cites it, and a Sonnet confirms the ruling names the act (ruling text: "Owner picked b on item 284, 13:08")
  - sim-lease-gaps: Close the sim-lease and sim-test gaps the Mac sim gatekeeper found (ruling text: "Owner ask ask-mw6q8p58kl, 12:18")
  - stale011-note-to-debt: Note stale011-batch-moves-cite becomes a debt (ruling text: "owner 20:24")
  - stall-watch-quiet-lint: A quiet lane-lint run does not trip the stall watch at 300 s (ruling text: "owner 13:20")

## code-glossary

- Kind: code. Repo: claude-settings.
- Files or homes: GLOSSARY.md
- Steps:
  - glossary-renames-in-code: Rename the glossary terms in code, guards, tests and tools (fix verifier, review log, feedback log,  (ruling text: "owner 14:29")

## code-guard

- Kind: code. Repo: claude-settings. Flags: after guard-tables-per-section.
- Files or homes: hooks/feedback_guard.py, hooks/guard.py, hooks/question_form.py, hooks/test_question_form.py
- Steps:
  - auto-merge-refused: A hook refuses auto-merge for Claude; the merge button stays the owner's (ruling text: "pick a")
  - banchi-make-hooks-arms: banchi: `make hooks` stays armed on a fresh clone, and its final check reads the config (ruling text: "Owner ask ask-mw6vybwdb8 part 1, 14:58")
  - batch-ci-merge-guard: The merge tool and the guard refuse a merge or push to main while an open integration PR's CI run is (ruling text: "Owner 20:31")
  - both-session-starts-judged: Guards that judge a lane start judge start_session as well as create_session (ruling text: "Owner glossary ruling topic 1, 14:36")
  - inbox-dup-heading-merge: The feedback guard counts a repeated heading with the same time and quote as one message (ruling text: "owner 16:20")
  - page-checks-reach-triage: The page-item checks run on triage's own page writes (ruling text: "Owner, page comment 13:18")
  - page-filing-check: The feedback guard proves a page item exists, not only that it was sent (ruling text: "Owner grant Nov 2 13:12")
  - parked-line-id-guard: Waiting page: refuse a parked line with no id at write time (ruling text: "Owner, page comment Nov 3 19:26")
  - handoff-ruling-guard: A guard refuses a ruling kept only in a handoff (ruling text: "coordinator pick 07:57 CST Nov 12; first guard lane, 08:06 CST")

## code-guard-2

- Kind: code. Repo: claude-settings.
- Files or homes: hooks/ci_wake.py, hooks/guard.py, hooks/precompact_handoff.py, hooks/test_install_src.sh
- Steps:
  - branch-force-other-worktree: The one-worktree-per-branch check also refuses `git branch -f` and `git update-ref` of a branch anot (ruling text: "Owner 20:25")
  - branch-slug-no-git: A new lane's branch name never contains "git", and a check refuses one that does (ruling text: "Coordinator pick")
  - c203: A per-session compaction window must not dirty settings.json; the handoff hook must read the window  (ruling text: "owner's pick")
  - child-repo-archive-scope: An archive refused because the lane's repo is out of this session's scope names the cause and routes (ruling text: "owner 13:20")
  - ci-wake-mcp-ready: The CI-done wake fires in the cloud, where a PR is marked ready through the GitHub MCP tool (ruling text: "Owner 11:55")
  - cost-line-pinned: A check refuses a decision's cost line that names a file no test pins (ruling text: "owner 13:20")
  - guard-interpreter-body-git: The guard reads a git command inside a python3 -c, sh -c or bash -c body, or a PowerShell & ('git')  (ruling text: "owner 13:20")
  - lane-lint-parallel-cap: Lane lints in parallel finish under the 1200 s cap (ruling text: "owner 13:20")

## code-guard-3

- Kind: code. Repo: claude-settings.
- Files or homes: hooks/guard.py
- Steps:
  - lane-lint-windows-guard-slice: A guard lane proves its Windows guard tests before hand-off (ruling text: "owner, relayed 10:02")
  - lane-session-model-check: A guard refuses a lane session started on a model other than the lane-session row's (ruling text: "owner item 439 (12:21")
  - lease-remedy-form: The force-push guard's remedy names the lease form that passes: `--force-with-lease=<ref>:<sha>` (ruling text: "owner 13:20")
  - local-folder-for-owner-acts: A session on shiv's Mac runs the acts the cloud refuses: protection writes, branch deletes, closing  (ruling text: "pick a")
  - mistake-rule-opening: Rule building-mistake-names-its-guard opens by reading a mistake as a missing guard (ruling text: "owner ruling")
  - notes-name-their-fix: Each new notes or debt line names its fix, and the report guard refuses a RECORDED gap with no start (ruling text: "Owner, 13:25")
  - one-load-definition: The guard and sim-lease read machine load from one shared definition (ruling text: "Owner picked a on item 304 (15:24")
  - other-checkout-heredoc-text: The other-checkout guard does not read a harmless python heredoc body as shell (ruling text: "owner 13:20")

## code-guard-4

- Kind: code. Repo: claude-settings. Flags: after guard-tables-per-section.
- Files or homes: hooks/guard.py, hooks/shared_names.py
- Steps:
  - page-grant-typed-line: A page answer that grants an act auto mode refuses gets a typed-line task, not a 'routed' reply (ruling text: "owner's word")
  - page-tool-every-name: The page hooks know the page tool under every surface's name (ruling text: "Owner 19:56")
  - refusal-ends-short-fix-line: Every Stop-hook refusal that blocks a reply ends with one line: post only the corrected lines, never (ruling text: "Owner 15:44")
  - reviewer-model-hook-latest: The report hook that checks reviewer model names stops flagging an earlier round's correct model (ruling text: "Owner ask, 13:20")
  - ruling-record-not-docs-only: The docs-only review path refuses a record that files an owner ruling (ruling text: "owner ruling")
  - scratchpad-owner-refuse-not-ask: Guard rule scratchpad-owner refuses, with a fresh-name remedy, where it asks today (ruling text: "owner permission boxes 2026-11-11 10:00")
  - sed-script-not-a-path: The guard does not read a sed script as a path (ruling text: "owner 13:20")
  - sim-tool-lease-check: The iOS Simulator tool refuses a device whose lease the caller does not hold (ruling text: "owner as ask ask-mw839r77zp (11:11")

## code-guard-5

- Kind: code. Repo: claude-settings. Flags: after guard-tables-per-section.
- Files or homes: hooks/guard.py
- Steps:
  - test-author-ci-step-false-alarm: The test-author-scope guard lets a test-author add a whole CI test-run step, as decision builders-ca (ruling text: "owner 13:20")
  - windows-guard-cap-stopgap: Main's checks-windows-guard shards get the 75-minute stopgap cap, so main's push runs finish (ruling text: "Owner 11:53")

## code-guard-shell

- Kind: code. Repo: claude-settings. Flags: after guard-tables-per-section.
- Files or homes: hooks/guard.py, scripts/guard-shell.py
- Steps:
  - c174: Banchi's guard allows notes folders and leaves the tree check to the shared rule (ruling text: "Owner pick b on page item 143 (saved Nov 1 17:25")

## code-handoffs

- Kind: code. Repo: claude-settings.
- Files or homes: handoffs/session_013NEJKzVTWMbokJ3KFanBBC.md, handoffs/session_013NEJL1JwGYbs71pjwKZCfb.md, handoffs/session_013NEJL1nA83YuznrBBaUdv6.md, handoffs/session_013NEJL232Ko7dmr4v3fmrvF.md, handoffs/session_013NEJL3qSsV2LJ6R1a1HMCB.md, handoffs/session_013NEJL4DPEKRiC91yHkQV7m.md, lint/test_check_glossary.py
- Steps:
  - agent-branch-push-refuses: A push of an agent-named branch is refused with its remedy, so the prompt never reaches the owner (ruling text: "owner, who asked at 13:14")
  - builder-diff-merge-commit: The builder-diff guard counts test paths against MERGE_HEAD, not HEAD, at the commit that makes a me (ruling text: "owner 13:20")
  - draft-pr-unquoted-body-sq-subst: The draft-PR guard catches a PR create inside single quotes in an unquoted heredoc (ruling text: "owner 13:20")
  - export-after-page-write: Find why the export Stop check (#1288) let a page writer skip exports all day (ruling text: "Owner 19:02")
  - fed-write-followups-3: The fed-write guard reads any folder root from disk, not only the current folder (ruling text: "Coordinator pick")
  - resume-finished-reviewer-no-tree: Resuming a finished reviewer is refused, and the refusal says to send a fresh reviewer the prior rep (ruling text: "Owner item 409 a (06:11")
  - resume-guard-subagent-sends: The resume guard refuses a subagent's message to a finished reviewer (ruling text: "pick a")
  - resume-guard-workflow-agents: The resume guard refuses a Workflow agent's message to a finished reviewer (ruling text: "pick a")

## code-handoffs-2

- Kind: code. Repo: claude-settings.
- Files or homes: handoffs/session_013NEJKzXyKNARtJsbz3Q1R2.md, handoffs/session_013NEJKza5KBoiFbNuiDDxQn.md, handoffs/session_013NEJL1h7mKMtSVohetjaW1.md, handoffs/session_013NEJL36oZi9XZ76KB8nFQy.md, handoffs/session_013NEJL3RdQ8rPEF8bMo6YPB.md, handoffs/session_013NEJL4TDRWqka4aSU2Bv7L.md
- Steps:
  - handoff-keeps-owner-waits: A coordinator's handoff lists every item in its session that waits on the owner, and a check refuses (ruling text: "Owner ask ask-mw864dcumn, 12:30")
  - input-needed-reads-page-status: A report check refuses an Input Needed item whose page item is closed (ruling text: "Owner 11:44")
  - lint-before-record-push: A push of Markdown that fails the STE lint is refused (ruling text: "pick a")
  - pe-guard-false-alarms: The pre-existing guard reads "a pre-existing issue" as a claim, and stops its false alarms (ruling text: "owner 13:20")
  - replay-profile-parts: Each one-install replay profile has parts, so a failed install claims only its own defects (ruling text: "pick A")
  - reviewed-head-push-ask: The guard asks before a push past a reviewed head that already has a fix check (ruling text: "coordinator pick")

## code-install

- Kind: code. Repo: claude-settings. Flags: after guard-tables-per-section.
- Files or homes: claude/hooks/guard.py, hooks/guard.py, install.sh, merge/install_from_main.sh, root/.claude/CLAUDE.md
- Steps:
  - cloud-hooks-stale-copy: A long cloud session picks up hook changes from main, not only the copy it installed at start (ruling text: "Owner 12:59")
  - install-hash-skips-pycache: install.sh tree_hash skips __pycache__ (ruling text: "owner 2026-11-11 13:36")

## code-layout-extras

- Kind: code. Repo: claude-settings. Flags: after guard-tables-per-section.
- Files or homes: claude/layout-extras.json, claude/settings.json, etc/claude-code/managed-settings.json, hooks/guard.py, scripts/typecheck-hook.py
- Steps:
  - repo-protected-paths: A repo-declared protected-path list that the guard enforces (ruling text: "Owner ask ask-mw6vyc57pi part 2, 14:58")
  - repo-typecheck-hook: A repo-declared TypeScript check after each edit, one claude-settings hook (ruling text: "Owner ask ask-mw6vyc57pi part 1, 14:58")

## code-lint-1

- Kind: code. Repo: claude-settings.
- Files or homes: lint
- Steps:
  - builder-report-in-head: A builder's report names each file it changed, and the lane checks each one is in the pushed head's  (ruling text: "owner 13:20")
  - check-line-reader: A blind reader flags a done-check that can pass with the ask unmet (ruling text: "Owner picked c on item 284, 13:08")
  - first-fix-check-net-value: The first fix check on a round-3 record cannot carry a lane-written net value that clears a negative (ruling text: "owner 13:20")
  - fix-base-own-round-head: A fix check may take the record's own top-round head as its fix base (ruling text: "coordinator pick")
  - lane-lint-bg-timeout: A background lane-lint run sets a time limit above the lint's own bound (LINT_SECONDS plus the pushe (ruling text: "owner 11:26")
  - lane-undo-check: No-undo check: narrow to the two undo shapes (ruling text: "Owner picked a on page item 167 (Nov 3 18:16")
  - merge-conflict-mixed-roles: A builder resolves a merge that conflicts in a test file, and a check proves no test was lost (ruling text: "owner 2026-11-11 11:02")
  - one-check-other-repos: home, mailaudit and banchi each get one required rollup check (ruling text: "pick a")

## code-lint-2

- Kind: code. Repo: claude-settings. Flags: after code-lint-1.
- Files or homes: lint
- Steps:
  - qmax-d369-failed-reason: q_max: the D-369 browser check (a run outlives its browser) goes green on main (ruling text: "owner chat 11:26")
  - qmax-geometry-reds: q_max browser geometry checks are green (ruling text: "Coordinator pick")

## code-merge-1

- Kind: code. Repo: claude-settings. Flags: after guard-tables-per-section.
- Files or homes: claude/CLAUDE.md, docs/debts/notes.md, handoffs/session_013NEJKzDBTjFbhzwzV96i8v.md, handoffs/session_013NEJKznZeoFs9GZiN7syv9.md, hooks/guard.py, hooks/mutate_guard.py, hooks/test_guard.py, lint/check_ruling_kind.py, lint/hook_catalog.py, lint/report_guard.py, lint/ste_lint.py, merge/merge.py, merge/test_lane_lint.py
- Steps:
  - agent-report-shas-resolve: An agent's hand-back refuses when its report names a commit that does not exist (ruling text: "owner 13:20")
  - artifact-guard-matcher-names: Guards meant for artifact tools match the names sessions really call (ruling text: "owner as ask ask-mw839r77zp (11:11")
  - backtick-mask-one-home: Every lint that skips inline code reads backtick spans through one home, INLINE_CODE_RE (ruling text: "owner 13:20")
  - batch-freeze-lane-set-enforce: The merge tool enforces the batch freeze: `merge --batch-build` freezes the lane set, `--batch-drop` (ruling text: "Owner, 20:30")
  - batch-local-checks-cmd: One command runs a batch's local checks, with the flags read from checks.yml (ruling text: "Owner goal: fix slow merges (Nov 8 20:24")
  - builder-checkout-restore-forms: A builder cannot restore a mutation-test file from another commit (ruling text: "owner 09:18")
  - builder-probe-false-alarm: Rule builder-test-edit lets a builder write a probe under /tmp (ruling text: "Owner item 396 a (06:08")
  - child-repo-gap: Check how far each child repo is from claude-settings main (ruling text: "owner 14:05")

## code-merge-2

- Kind: code. Repo: claude-settings. Flags: after guard-tables-per-section; after code-merge-1.
- Files or homes: claude/CLAUDE.md, docs/debts/notes.md, handoffs/session_013NEJKzp1xjTHtzDvmMRpKj.md, hooks/guard.py, hooks/guard_core.py, hooks/session_start.sh, lint/check_comment_narration.py, lint/report_guard.py, merge/merge.py
- Steps:
  - comment-check-scans-shell: The comment-narration check scans shell files (ruling text: "owner 13:20")
  - draft-pr-guard-heredoc: The draft-PR guard skips PR-create words that sit inside a heredoc or string (ruling text: "Owner picked b on page item 381 at 21:26")
  - fix-check-after-main-merge: A review record survives a clean merge of main, and a conflicted merge after a fix check takes anoth (ruling text: "Owner ruling 14:07")
  - fixed-number-limits-census: Drop the 30-word sentence cap, and retire every fixed number that refuses or fails without an owner  (ruling text: "owner ruling")
  - gate-never-ran-not-red: The merge tool tells a gate job that never ran from a red one (ruling text: "owner allowed --base-red-ok at 15:39")
  - grants-read-from-main: A session that cites a standing grant reads it from origin/main, not from its own checkout (ruling text: "owner ask ask-mw8gfqzlws, coordinator fold 17:20")
  - guard-false-alarm-cull: One cull lane fixes or deletes each guard or check with a recorded wrong refusal (ruling text: "Owner ruling R5, 15:04")
  - guard-python-quoted-redirect: The other-checkout guard stops reading a redirect inside quoted or heredoc text on an interpreter li (ruling text: "owner, 11:00")

## code-merge-3

- Kind: code. Repo: claude-settings. Flags: after guard-tables-per-section; after code-merge-2.
- Files or homes: CLAUDE.md, docs/catalog.md, docs/debts/notes.md, hooks/call_judge.py, hooks/guard.py, hooks/guard_core.py, hooks/test_guard.py, lint/hook_catalog.py, lint/report_guard.py, merge/cloud_allow.json, merge/merge.py
- Steps:
  - habit-is-not-a-guard: A guard named as a habit or a brief wording does not count; a report names a PR, commit, step or deb (ruling text: "Owner ruling")
  - harness-worktree-git-probe: Raise upstream: the Claude Code harness's worktree isolation refuses a git probe (ruling text: "owner's yes")
  - heredoc-keep-gap-cases: The heredoc-keep reader in guard_core gets cases and mutants for its four known gaps (ruling text: "owner 13:20")
  - hook-catalog-whole: The hook catalog covers every hook and setting, with a runs-on column, linked from the page's Status (ruling text: "Owner 16:00")
  - job-cap-expressions: The merge tool reads a job cap written as an expression, so the merge-lock floor is not too low (ruling text: "owner 13:20")
  - judge-timeout-retries-once: The past-ruling check retries once before it refuses on a timeout (ruling text: "owner asked (page ask ask-mw6pwif5wv, 12:09")
  - keep-warm-check-in: A standing session keeps warm with a one-time check-in when it costs less than a context rewrite (ruling text: "owner 2026-11-11 13:20")
  - lane-lint-body-tidy: Tidy the lane-lint PR-body change: two records, one test of the temp-file removal, one tie between t (ruling text: "owner 13:20")

## code-merge-4

- Kind: code. Repo: claude-settings. Flags: after guard-tables-per-section; after code-merge-3.
- Files or homes: docs/debts/notes.md, handoffs/session_013NEJKz3Pbvh8FJVoT2ydk8.md, handoffs/session_013NEJL3JoPTyn7Ny4jUb88L.md, hooks/guard.py, hooks/guard_core.py, hooks/mutate_guard.py, hooks/test_checks_never_raise.py, hooks/test_guard.py, janitor/mutate_sweep.py, lint/check_comment_narration.py, lint/check_debt_retire.py, merge/merge.py, merge/test_lane_lint.py
- Steps:
  - lane-lint-hook-suites: Lane lint runs the hooks test suites that load a file the lane changed (ruling text: "owner 13:20")
  - lane-lint-mutant-anchors: The lane lint runs the mutation anchor pre-check, so a stale or ambiguous anchor fails before CI (ruling text: "owner 13:20")
  - lane-lint-runs-comment-check: Lane lint runs every check the checks job runs on the lane's changed files (ruling text: "Owner pick on the waiting page (13:09")
  - lint-slot-review-fixes: The lint slot cap gets its review fixes, and test_install_src.sh stops failing under load (ruling text: "owner 13:20")
  - local-caps-interim-raise: Local tool time limits rise generously until time-pinned tests are gone, so no check reads unknown o (ruling text: "Owner chat 12:11")
  - merge-batch-split-and-pipeline: The merge tool splits a red batch, and builds the next batch while one runs (ruling text: "Owner pick on item 386 a (page save, 22:25")
  - merge-builds-batches: The merge tool builds each batch from PR state (ruling text: "Owner pick on item 386, a+b+c (page save, 22:25")
  - merge-claim-survives-timeout: The merge tool keeps its record claim when a GitHub read times out (ruling text: "Owner, 15:10")

## code-merge-5

- Kind: code. Repo: claude-settings. Flags: after code-merge-4.
- Files or homes: CLAUDE.md, docs/debts/notes.md, docs/records.md, handoffs/session_013NEJL3G6vFtN2TjNZrMETW.md, hooks/mutate_guard.py, hooks/test_guard.py, lint/check_comment_narration.py, lint/check_record_slugs.py, merge/merge.py, skills/project-ops/scripts/protect.py
- Steps:
  - merge-reads-ruleset: The merge tool reads main's ruleset first, then the old branch protection (ruling text: "Owner 19:49")
  - merge-red-main-latest-run: The merge tool judges main by its newest run, not an older red one (ruling text: "Owner 20:25")
  - mistake-prose-files-guard: A mistake reads first as a missing guard; a Stop hook spots a mistake told in a reply and its judge  (ruling text: "Owner R16, 16:22")
  - mixed-merge-resolver: A role resolves a base merge whose conflicts touch both test and product files (ruling text: "owner 11:02")
  - narration-gloss-round-followups: The comment-narration check stops flagging a review round written inside or beside a decision gloss (ruling text: "owner 13:20")
  - narration-owner-ruling-ok: The comment-narration check passes an 'owner's ruling' that names a rule, not history (ruling text: "owner's ruling")
  - narration-ruling-cite: The comment-narration check passes a ruling cite with its time (ruling text: "Owner, 2026-11-01 16:30")
  - notes-slug-unique: A check refuses a duplicate slug in docs/debts/notes.md, and the nine pairs on main are merged (ruling text: "owner 13:20")

## code-merge-6

- Kind: code. Repo: claude-settings. Flags: after guard-tables-per-section; after code-merge-5.
- Files or homes: CLAUDE.md, docs/debts/notes.md, docs/plans/one-home-check.md, docs/records.md, handoffs/session_013NEJKypkpzqdbSUr7rAwAn.md, handoffs/session_013NEJKzHURrN9PNYKYoXWNg.md, handoffs/session_013NEJL1N3YkCMouc1pELXyu.md, handoffs/session_013NEJL1rJepBiu21f6Rv9jG.md, hooks/call_judge.py, hooks/guard.py, hooks/test_guard.py, lint/find_copies.py, lint/report_guard.py, lint/test_report_guard_remedy.py, merge/merge.py, merge/test_merge.py
- Steps:
  - notes-union-unretire: A merge that re-adds a line the branch's own diff deleted from docs/debts/notes.md is refused (ruling text: "owner 13:20")
  - one-home-check: Rule one-home-per-capability is enforced by a check, both ways (ruling text: "Owner pick a, Nov 2 13:38")
  - pass-claim-cites-verdict: A pass claim cites its verdict line; checks run only through verdict (ruling text: "owner 18:36")
  - past-ruling-timeout: The past-ruling check logs its duration and prompt size, and its time limit is set from those measur (ruling text: "Owner ask ask-mw8bz5rj1f, 15:14")
  - push-ask-reads-brief: A test-author's or builder's push asks when its brief names no branch to push to (ruling text: "owner 13:20")
  - record-replacement-pr-rounds: The merge tool tells a replacement PR from a new one, so the replacement keeps the review rounds its (ruling text: "owner 13:20")
  - records-page-before-ready: One CI run per merge: the merge tool rebuilds the records page before the ready run (ruling text: "owner ask, Oct 31 14:12")
  - refusal-names-way-out: Every guard refusal and ask names an allowed way out, and a test proves each one is allowed (ruling text: "Owner grant, 09:16")

## code-merge-7

- Kind: code. Repo: claude-settings. Flags: after guard-tables-per-section; after code-merge-6.
- Files or homes: CLAUDE.md, claude/hooks/sim_boot_record.py, docs/debts/notes.md, handoffs/freeze-2026-10-30.md, handoffs/session_013NEJKzjkypcToggneCjJN8.md, handoffs/session_013NEJL2jTS37z97cavLKVTC.md, hooks/call_judge.py, hooks/guard.py, hooks/sim_boot_record.py, hooks/test_guard.py, lint/check_debt_retire.py, lint/check_silent_undo.py, merge/merge.py, merge/test_merge_grant.py, skills/project-ops/templates/brief.md, templates/roster.md
- Steps:
  - release-pairwise-clash: A release check runs merge-tree pairwise across the whole release set and the building batch, and na (ruling text: "owner, Nov 8 20:24")
  - retire-check-whole-suite: Checks that run only at merge run before the batch's CI, so a lane that would fail them is refused f (ruling text: "owner 14:07")
  - review-fix-check-round: A failed fix check counts as the next review round, inside the three-round cap (ruling text: "Owner, item 347 a, 13:12")
  - role-ids-in-brief: A lane brief names the coordinator, triage and batch runner session ids, and a check refuses one sen (ruling text: "owner 13:20")
  - rounds-rules-one-record: Fold the review-round rules into one record: round 3 only for a guard or check change that failed a  (ruling text: "Owner 15:44")
  - ruling-challenge-passes: The past-ruling check passes a measured challenge, refuses a bare re-ask, and the reply judge flags  (ruling text: "owner 2026-11-11 13:01")
  - silent-undo-cli-ignores-pr-body: The silent-undo check's CLI reads the PR body, so a `Drops-lines:` line in the body clears it (ruling text: "owner 13:20")
  - sim-boot-screen-check: After a simulator boots, a one-screen check proves the screen is live (ruling text: "owner as ask ask-mw839r77zp (11:11")

## code-merge-8

- Kind: code. Repo: claude-settings. Flags: after guard-tables-per-section; after code-merge-7.
- Files or homes: claude/CLAUDE.md, docs/debts/ste-push-mutants.md, docs/plans/time-pinned-tests.md, handoffs/session_013NEJKz3J95T7tJBtSYUXZ9.md, handoffs/session_013NEJL39dinAf2VGG2b3Weo.md, hooks/guard.py, hooks/guard_merge.py, hooks/guard_ste.py, hooks/mutate_guard.py, hooks/session_start.sh, lint/find_time_pinned.py, lint/md_sweep.py, lint/ste_gate.py, lint/ste_lint.py, merge/test_lane_lint.py, roadmap/build.py
- Steps:
  - ste-lint-rename: The plain-prose lint, its CI step and shared action drop the STE name (ruling text: "Owner pick b, Nov 2 13:22")
  - ste-push-mutants: hooks/mutate_guard.py has mutants for the ste-push rule (ruling text: "owner 13:20")
  - step-file-similar-title: roadmap/build.py warns when a new step's title shares most of its key words with an open step (ruling text: "owner 11:27")
  - step-names-its-gap: A roadmap commit that stages a step whose gap key matches an open step's is refused (ruling text: "owner item 383 (record-branch-merge), 20:54")
  - stop-push-skips-merged: The Stop hook's unpushed-commits nudge skips a branch whose head is already on origin/main (ruling text: "Owner pick on the waiting page (13:09")
  - time-pinned-tests-go: Tests that pass or fail on clock speed become outcome checks, then CI caps return to measured (ruling text: "Owner, Nov 1 18:44")
  - prose-judge-call-cap: The merge-time prose judge's call cap leaves no batch with lines unjudged (ruling text: "coordinator 08:06 CST Nov 12, last in the code-merge chain")

## code-pinned-settings

- Kind: code. Repo: claude-settings.
- Files or homes: harness/pinned-settings.mjs
- Steps:
  - merge-passes-settings-dir: The merge tool sets CLAUDE_SETTINGS_DIR to its own checkout for each pinned run and each repo's read (ruling text: "owner 13:20")

## code-precompact

- Kind: code. Repo: claude-settings. Flags: after guard-tables-per-section.
- Files or homes: harness/check_rules.py, hooks/agent_brief.py, hooks/guard.py, hooks/precompact, test/move.ps1
- Steps:
  - argv-dump-guard: High: a guard stops a session from printing process arguments, which can hold secrets (ruling text: "Owner 20:25")
  - brief-role-scope-check: The agent-brief check refuses a brief that asks a role to write paths its role may not write (ruling text: "owner chat 11:24")
  - builder-runs-comment-check: A builder brief's done check runs the comment-narration scan on the touched files (ruling text: "Owner ruling")
  - pick-ack-past-ruling: A lane or coordinator that takes or agrees to a departing pick cites the past rulings it checked (ruling text: "owner ruling")
  - report-model-across-compact: The report guard's model check reads spawns from before a compaction (ruling text: "owner 13:20")
  - sort281-env-frozen-stack: Land the env and frozen-path guard stack (lane notes-fix-large-1) that only the handoff ledger track (ruling text: "Owner 15:31")
  - sort281-granted-round4: Land the granted-round-4 model guard stack that only the handoff ledger tracks (ruling text: "Owner 15:31")
  - sort281-notes-fix-page: Land the waiting-page and report-guard fixes (lane notes-fix-page) that only the handoff ledger trac (ruling text: "Owner 15:31")

## code-roadmap

- Kind: code. Repo: claude-settings.
- Files or homes: roadmap
- Steps:
  - coordinator-transcript-reconcile: Sonnet extractors read the coordinator transcript, and one Sonnet reconciler checks what they find a (ruling text: "Owner 09:05")

## code-shallow-clone

- Kind: code. Repo: claude-settings.
- Files or homes: testing/shallow_clone.py
- Steps:
  - test-dirs-include-testing: The test-author scope guard lets a test-author edit files under testing/ (ruling text: "owner 13:20")

## code-stamp

- Kind: code. Repo: claude-settings.
- Files or homes: .github/stamp.json
- Steps:
  - c33: Sessions in repos with no CI still catch and fix their errors (ruling text: "owner R17, 16:36")

## code-test-author

- Kind: code. Repo: claude-settings. Flags: after guard-tables-per-section.
- Files or homes: agents/reviewer.md, agents/test-author.md, claude/agents/reviewer.md, handoffs/session_013NEJL382EZLqWkzVvjj7UP.md, hooks/guard.py
- Steps:
  - agent-worktree-add-in-tool-dir: Inside .claude/worktrees/, the guard refuses an agent's git worktree add unless the target is its re (ruling text: "Coordinator pick")
  - report-guard-role-default-model: The report guard resolves a spawn with no model field to its role file's model, and maps a full mode (ruling text: "owner 13:20")

## code-test-ci-standard

- Kind: code. Repo: claude-settings.
- Files or homes: docs/plans/builtin-hook-survey.md, docs/plans/test-ci-standard.md
- Steps:
  - tci-5-platform-tested: Each shipped platform names where it is tested (ruling text: "owner's word")
  - watcher-fire-count-week: Count each of the six model-call hooks' fires over one week, then delete each that never fired (ruling text: "owner chat 11:26")

## code-unmapped

- Kind: code. Repo: claude-settings.
- Files or homes: unmapped
- Steps:
  - builder-test-config-check: A builder cannot edit test config (ruling text: "pick a")
  - ios-ship-export-method: ios-ship's export-only build takes --method debugging|release-testing (ruling text: "Owner 20:25")
  - reviewed-batch-line-reads: merge --reviewed reads open heads once, tests ancestry locally, and lets stacked done PRs into the b (ruling text: "Owner ask, 10:15")
  - stale-flags-test-gaps: Tests cover every STALE007 form, and the stale-cites-at-merge Test copy bullet matches the reader (ruling text: "owner 13:20")
  - stale009-sweep: Fix the real stale cites that STALE009 finds (ruling text: "owner 20:24")
  - why-cite-matches-act: A page task's route cite must name a route row that covers its act (ruling text: "Coordinator pick")

## code-waiting-page

- Kind: code. Repo: claude-settings.
- Files or homes: skills/waiting-page, skills/waiting-page/SKILL.md
- Steps:
  - page-answered-not-closed: A check flags a waiting-page item that holds an owner answer but stays open (ruling text: "owner answer but stays open On 13:28")
  - page-thread-reply-refused: A session's reply to a comment thread on the waiting page is refused, and the session rewrites the i (ruling text: "owner, Oct 28 02:44")
  - page-time-field-valid: Refuse a page or step write with a blank or non-ISO time (ruling text: "owner ruling")
  - stamp-check-page-and-roadmap: The time-stamp check also covers page item and roadmap step writes (ruling text: "Coordinator pick")
  - step-pick-claims-match-page: A check matches each step note's "the owner picked X" claim against the page's recorded answers (ruling text: "owner ruling")

## code-workflows

- Kind: code. Repo: claude-settings.
- Files or homes: .github/workflows
- Steps:
  - judge-replay-corpus: Replay known allow and deny cases in CI when a judge changes (ruling text: "Owner added the secret, 13:08")
  - main-job-cap-alarm: A main CI job that ends at its time cap raises an alarm the same day (ruling text: "owner 11:53")
  - mutate-harness-change-timed-run: A PR that changes the mutation harness runs a CI-sized mutate-guard run before it joins a batch (ruling text: "Owner pick on the waiting page (13:09")
  - no-ci-starter: A repo with no CI gets a starter CI from skill project-ops, and a refusal for no CI names that step  (ruling text: "Owner R17, 16:25")

## prose-agents

- Kind: prose. Repo: claude-settings.
- Files or homes: agents, agents/builder.md, handoffs/session_013NEJL3hRvWLoxZuEPVQkD2.md
- Steps:
  - brief-reads-owner-rulings: A lane brief that contradicts an owner-ruled decision is flagged before it is sent (ruling text: "owner ruling")
  - builder-model-pin: agents/builder.md pins its model, so a builder never inherits the session's Opus (ruling text: "Owner 20:25")
  - lane-brief-cites-grant: A lane starts with effort medium and its whole brief, opening with a Grant line, as its first prompt (ruling text: "owner grant")
  - reviewer-brief-blind: A reviewer's brief holds only the task, the diff and the rulings (ruling text: "Owner picked a on item 279, 12:43")
  - stall-watch-agents: Stall watch sees a stalled agent, not only Bash jobs (ruling text: "Coordinator pick")
  - stall-watch-open-call-cap: The stall watch lists an agent whose foreground tool call has been open more than 900 s (ruling text: "Coordinator pick")
  - subagent-handback-skipped: Find why background agents end without calling SubagentHandback, and fix the cause (ruling text: "owner feedback 2026-11-11 12:57")

## prose-build

- Kind: prose. Repo: claude-settings.
- Files or homes: skills/roadmap/build.py, skills/waiting-page/SKILL.md
- Steps:
  - idle-lane-archive-at-merge: Each batch merge archives the lane sessions whose PRs all merged or closed (ruling text: "owner ask 10:15")
  - page-grant-counts-closed: page_grant counts an owner answer on an item that triage closed after routing it (ruling text: "Coordinator pick")

## prose-claude-1

- Kind: prose. Repo: claude-settings.
- Files or homes: CLAUDE.md, GLOSSARY.md, docs/todo.md, merge/merge.py, skills/roadmap/SKILL.md
- Steps:
  - banchi-revive-944-961: banchi #961 (glossary) and #944 (dry-run decode) wait for the owner's keep or close (ruling text: "Owner item 385 a (06:18")
  - base-red-reads-gate: Degen #509 merges over the old red milestone-proof run, on the owner's word (ruling text: "owner's word")
  - child-claude-md-dedupe: Child repos: drop STE and the repeated text from their CLAUDE.md files (ruling text: "owner chat 11:26")
  - degen-deploy-from-cloud: Degen deploys run from a cloud session through Tailscale, with the image built in GitHub Actions (ruling text: "owner's word")
  - glossary-one-page-row: One glossary row for the repo's one page: the waiting items and the Status tab (the roadmap) (ruling text: "Owner 15:52")
  - glossary-page-row: GLOSSARY.md gets a 'page' row, and 'roadmap page' is retired (ruling text: "owner ruling")
  - glossary-same-local-cloud: One clean glossary of roles (coordinator, agent, session, lane, arbiter, triage) that reads and acts (ruling text: "Owner 14:17")
  - lane-finds-triage: A lane finds triage's session without searching recent sessions (ruling text: "owner's word")

## prose-claude-2

- Kind: prose. Repo: claude-settings. Flags: after prose-claude-1.
- Files or homes: CLAUDE.md, actions/mutation-report/action.yml, docs/debts/notes.md, docs/todo.md, handoffs/session_013NEJL2pSKbDkTpUe76U2wp.md, hooks/mutate_guard.py, hooks/test_mutate_ci.py
- Steps:
  - lane-no-popup: A lane never raises a popup: each one becomes a refusal plus a question routed to its parent, then t (ruling text: "Owner R13, 16:16")
  - lane-sim-hold-path: A lane can boot or hold one simulator under a grant, tap and screenshot it, and wait for its GO (ruling text: "owner as ask ask-mw839r77zp (11:11")
  - lease-sha-form-hint: Lane brief and lease refusal name the sha form of force-with-lease (ruling text: "Owner picked b on item 286, 13:08")
  - model-table-one-home: The agent-model-cap role table is the one home for each role's and round's model and effort, and eve (ruling text: "Owner 15:44")
  - mutate-changed-no-mutant-fails: mutate_guard --changed fails when the change has mutants and none of them ran (ruling text: "Owner, in this triage session's chat, 16:47")
  - notes-1796-fix-lines: #1796's archive-then-delete notes each carry a Fix line (ruling text: "owner 20:24")
  - notes-204-ponytail-drop: Drop docs/debts/notes.md:204 and the unused ponytail marketplace (ruling text: "owner 2026-11-11 13:36")
  - owner-health-tab: A tab on claude-settings' page shows the owner what he sees, what makes it happen, and how healthy e (ruling text: "Owner 11:35")

## prose-claude-3

- Kind: prose. Repo: claude-settings. Flags: after guard-tables-per-section; after prose-claude-2.
- Files or homes: CLAUDE.md, GLOSSARY.md, agents/reviewer.md, docs/debts/notes.md, hooks/guard.py, hooks/guard_merge.py, hooks/mutate_guard.py, hooks/ruling_home.py, janitor/mutate_sweep.py, lint/check_debt_retire.py, lint/check_ruling_kind.py, lint/layout.json, lint/rule_audit.py, merge/merge.py, skills/design-review/SKILL.md
- Steps:
  - owner-override-one-route: One override route with a receipt: the owner's typed words are judged, override with any length form (ruling text: "Owner R12, 16:10")
  - pr-state-is-on-the-pr: One ledger gives each open PR one next act, and reports two numbers (ruling text: "Owner ask, 12:17")
  - prose-tending-contract: One shared tending contract and runner for every prose store (ruling text: "owner 2026-11-11 10:19")
  - review-needs-pr-notes: File #2364's six review-needs-pr limits in docs/debts/notes.md (ruling text: "owner 20:24")
  - review-rounds-rework: Measure what each review round catches, then propose models and prompts per round (ruling text: "Owner question on item 356, 13:41")
  - ruling-text-quotes-owner: Each owner ruling in a decision record carries his own words beside its rule text (ruling text: "owner ruling")
  - session-worktree-strands-agents: A session does not enter a new worktree while its agents run (ruling text: "owner 13:20")
  - time-limits-end-hangs-only: Runs stop on silence, not total time; a stop reads hung, never failed (ruling text: "owner ruled")

## prose-claude-4

- Kind: prose. Repo: claude-settings. Flags: after guard-tables-per-section; after prose-claude-3.
- Files or homes: CLAUDE.md, README.md, docs/debts/README.md, hooks/guard.py
- Steps:
  - triage-owns-debts-notes: Triage reviews debts and notes like the roadmap, and the page shows both (ruling text: "owner 17:00")

## prose-debts

- Kind: prose. Repo: claude-settings.
- Files or homes: docs/debts, docs/design.md, docs/plans/align-watchers.md, docs/plans/sim-standard.md, src/styles.md
- Steps:
  - drift-audit-lanes: Each capability's drifted copies are replaced with pointers, per the drift map (ruling text: "Owner pick a, Nov 2 13:45")
  - local-time-model-row: The model table lists local_time's model call (ruling text: "owner 20:24")
  - notes-fix-large-1: Fix the large findings, part 1, from the notes sort (ruling text: "Coordinator pick")
  - notes-fix-large-2: Fix the large findings, part 2, from the notes sort (ruling text: "Coordinator pick")
  - notes-fix-page: Fix the small waiting-page findings from the notes sort (ruling text: "Owner item 448 a (page answer 00:39")
  - notes-sightings-expiry: A note counts its sightings and expires; each batch carries one debt-fix lane (ruling text: "Owner, item 358, 14:41")
  - r4: q_max: merge its six design homes into one DESIGN.md (ruling text: "Owner go, Nov 1 17:26")
  - records-gloss-link-sweep: Every record glosses its ids and every debt links its decision (ruling text: "Owner, item 365, 14:41")

## prose-decisions

- Kind: prose. Repo: claude-settings.
- Files or homes: docs/decisions, docs/decisions/lane-inflow-hold.md, docs/decisions/recent-checks-can-be-undone.md
- Steps:
  - ask-again-reset-undo: Ask again: can a Reset be undone from mailaudit's Recent list? (ruling text: "owner (19:08")
  - consultant-role-record: Decision session-tiers names the consultant as a sixth session role (ruling text: "owner ruling")
  - coordinator-pick-needs-record: A coordinator pick that changes how work merges or batches lives in a decision record (ruling text: "coordinator pick")
  - decision-watch-finds-transcript: Decision watch finds the transcript by session id when the given path fails (ruling text: "owner 2026-11-11 13:36")
  - outbox-ruling-home-check: At status time, list each outbox ruling and whether its home on main holds its words (ruling text: "Owner 15:22")
  - past-ruling-reads-owner-only: The past-ruling judge counts only an owner ruling, never an incident or a recommended pick (ruling text: "owner ruling")
  - ruled-step-coordinator-queue: A step that holds an owner ruling and has no lane is the coordinator's queue, started under parallel (ruling text: "owner ruling")
  - timer-rule-reason-only: Rule outcomes-mechanize-rules allows a timer whose record shows it pays (ruling text: "owner ruling")

## prose-find-copies

- Kind: prose. Repo: claude-settings.
- Files or homes: handoffs/session_013NEJL1Umc5vUUPV286bXnV.md, lint/check_silent_undo.py, lint/find_copies.py, lint/layout.py, lint/rule_mechanisms.json, scripts/readme_links.py
- Steps:
  - r5: Each repo drops its copies of claude-settings things and reads the one home (ruling text: "Owner go, Nov 1 17:26")
  - roadmap-blank-pages: Repo pages with a blank Status tab although the repo has plans (ruling text: "Owner ask ask-mw1exqmkne (Nov 3 19:03")
  - rule-mechanisms-style-count: rule_mechanisms.json counts the reply judge's style rules; the hand-off bullet splits (ruling text: "owner 2026-11-11 13:36")
  - silent-undo-checks-pr-base: A local silent-undo run compares against the PR's base, not main (ruling text: "owner 13:20")

## prose-guard

- Kind: prose. Repo: claude-settings. Flags: after guard-tables-per-section.
- Files or homes: hooks/agent_brief.py, hooks/guard.py, hooks/precompact
- Steps:
  - commit-msg-heredoc-guidance: Agent start rules name git commit -F - with a heredoc as the commit-message form (ruling text: "owner feedback 2026-11-11 13:24")
  - compact-pct-override: Set CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=92 in settings env and prove it wins in a cloud session (ruling text: "owner 2026-11-11 13:21")
  - coordinator-refuter-spawn: A cloud coordinator may start a plan refuter, as decision plan-refuter requires (ruling text: "owner's word")
  - draft-remedy-mcp-grant: Owner question: widen the H1 grant so the draft refusal's remedy names the MCP form (ruling text: "owner's word")
  - env-file-shell-c: The env-file rule reads bash -c, sh -c and zsh -c command strings (ruling text: "Owner item 399 a (06:08")
  - idle-resume-compacts-rewrite: Decision idle-resume-compacts drops /autocompact as a cloud lever (ruling text: "owner ruling")
  - judge-send-message-refusals: Auto mode's judge stops refusing ordinary lane messages (ruling text: "Owner on item 301 (15:24")
  - sort281-loose-twelve: Land or drop the twelve loose PRs that only the handoff ledger tracks (ruling text: "Owner 15:31")

## prose-guard-2

- Kind: prose. Repo: claude-settings.
- Files or homes: handoffs/session_013NEJL232Ko7dmr4v3fmrvF.md, hooks/call_judge.py, hooks/guard.py, hooks/local_time.py, hooks/override.py, hooks/question_form.py, hooks/stall_watch.py
- Steps:
  - notes-fix-no-owner-line: A Stop refusal about a session's own notes is fixed with no line to the owner (ruling text: "owner Owner R14, 16:22")
  - option-tradeoff-pushback: When a question's options carry a large tradeoff, the option judge pushes back and asks for a better (ruling text: "Owner ask ask-mw80xweioa (10:05")
  - override-strips-status-block: A typed override takes even when the app puts a status block before it (ruling text: "Owner page note ask-mw5m8up8g8, 17:38")
  - page-answer-session-field: Page answers carry a session field, and a session reads only its own (ruling text: "Owner, item 367, 15:01")
  - stall-watch-live-run: The stall watch resolves a relative log path against the command's folder, and does not kill a live  (ruling text: "owner 13:20")
  - widening-rule-guideline: Widening mark: per-repo exceptions only, worded as a guideline (ruling text: "Owner on item 278, 12:41")

## prose-handoffs

- Kind: prose. Repo: claude-settings.
- Files or homes: handoffs/next-coordinator-lanes.md, handoffs/session_013NEJKyuRd6zdQhuiRC27g9.md, handoffs/session_013NEJKza5KBoiFbNuiDDxQn.md, handoffs/session_013NEJL213WYGvCs1ZRhXX4V.md, handoffs/session_013NEJL25kXsYSFJpzGQnKKe.md, handoffs/session_013NEJL3K9EJKrLHccAdQtmi.md, handoffs/session_013NEJL4DPEKRiC91yHkQV7m.md, handoffs/session_013NEJL4PiqDj45oM8x6XYaK.md
- Steps:
  - agent-process-marker: A per-agent marker shows which processes an agent's own Bash started (ruling text: "owner ruling 2026-10-15 19:43")
  - answered-section-folded: The waiting page folds the Answered section to one line while nothing in it needs the owner (ruling text: "owner Owner 12:31")
  - artifact-lane: Git is every artifact's home; designer-gap fixes, scan false alarms, the 14 step links (ruling text: "Coordinator pick")
  - findings-ride-in-lane: A lane's findings ride in its own PR, or one follow-up PR per topic (ruling text: "Owner pick on item 386, a+b+c (page save, 22:25")
  - grant-reaches-lanes: A grant typed in one session reaches the session it names (ruling text: "Owner, chat, Nov 1 22:37")
  - notes-fix-large-3: Fix the large findings, part 3, from the notes sort (ruling text: "Coordinator pick")
  - pwsh-followups: PowerShell follow-ups to #1774: an unquoted `env -S pwsh -c` is caught, and smart quotes in PowerShe (ruling text: "owner 13:20")
  - replay-block-failed-imports: In the known-defect replay, an import of a failed part's package raises, so a fallback catcher reads (ruling text: "pick A")

## prose-handoffs-2

- Kind: prose. Repo: claude-settings.
- Files or homes: handoffs/session_013NEJL2NVN5RjCgjRQFXeps.md
- Steps:
  - step-landed-from-prs: A roadmap step counts as landed from its lane's merged PRs, not from Step: trailers (ruling text: "Owner ask, 10:15")

## prose-roadmap

- Kind: prose. Repo: claude-settings.
- Files or homes: roadmap
- Steps:
  - artifact-pages-other-account: 8 of 9 roadmap-linked artifact pages live in another account (ruling text: "Owner note on item 438 (18:24")
  - lane-end-releases-steps: A lane that ends releases or names each roadmap step still doing under its id (ruling text: "owner 13:20")

## prose-stall-watch

- Kind: prose. Repo: claude-settings.
- Files or homes: docs/decisions/stall-watch.md
- Steps:
  - stall-watch-round3-notes: Decision stall-watch drops its hard-coded step count, and the beat debt note names the fetch window (ruling text: "owner 13:20")

## prose-stamp

- Kind: prose. Repo: claude-settings.
- Files or homes: actions/stamp/stamp.mjs, .github/stamp.json
- Steps:
  - stamp-unscanned-pending-cite: A stamp refusal names the unscanned file and its fix (ruling text: "Owner feedback relayed 15:08")

## prose-unmapped

- Kind: prose. Repo: claude-settings.
- Files or homes: unmapped
- Steps:
  - challenger-page-against: Page questions get a blind best case against the pick (ruling text: "Owner picked a on item 284, 13:08")
  - close-replaced-at-open: A PR closes as replaced the moment the PR that replaces it opens (ruling text: "owner called 'so massive' (owner, 21:27")
  - cloud-artifactdata-allow: Cloud page writes: allow the cloud page tool, or keep page writes local (ruling text: "owner 13:51")
  - cloud-branch-delete: Cloud sessions delete branches the Oct 30 grant allows (ruling text: "Owner 14:25")
  - cloud-mod-bands-missing: Find why mod bands (weather) do not draw on cloud sessions (ruling text: "owner 2026-11-11 13:36")
  - craft-book: shivpedia: what a session learns in one repo, the next repo starts with (ruling text: "Owner, Nov 1 21:02")
  - dead-pr-waits: No open step waits on a pull request that closed without a merge (ruling text: "Owner chat 13:09")
  - drain-sort-against-plan: Sort every open PR outside the named queue against the restart plan (ruling text: "owner pick 19:23")

## prose-unmapped-2

- Kind: prose. Repo: claude-settings.
- Files or homes: unmapped
- Steps:
  - export-scan-key-followups: The export scan passes everyday hyphen and snake_case keys, and its comments say what the code does (ruling text: "owner 13:20")
  - express-pass-owner-quotes: A PR whose owner quotes match the feedback log word for word skips the review round (ruling text: "Owner 15:22")
  - idle-lane-steps-unknown: The idle-lane archive can judge a lane whose step is not on the record branch (ruling text: "owner 13:20")
  - item-reply-back: The owner can reply to Claude's reply on a page question (ruling text: "Owner on item 278, 12:58")
  - lane-title-slug: A lane session's title opens with "Lane <branch slug>:" (ruling text: "owner 13:51")
  - local-triage-tier-build: Local triage proves its tier on Mac and Windows (ruling text: "Owner, 2026-11-06 15:45")
  - mailbox-all-messages: Cloud-to-cloud messages move to the mailbox (ruling text: "Owner ruling")
  - mailbox-wake-routes: Measure how a mailbox update wakes an idle session (ruling text: "Owner ask, 09:33")

## prose-unmapped-3

- Kind: prose. Repo: claude-settings.
- Files or homes: unmapped
- Steps:
  - merge-lock-expired-delete-race: The merge lock's expired-lock delete does not race a new holder (ruling text: "owner ruling")
  - merge-role-raw-paths: A solo owner session gets its own merge role, and only it may use it (ruling text: "Coordinator pick")
  - model-call-auth-check: The claude -p model-call setup works on every account and device, or asks once (ruling text: "Owner, 11:43")
  - no-undo-lane-commits: Builders never undo earlier lane work, and the silent-undo scan catches it (ruling text: "Owner ruling in chat, Nov 2 10:41")
  - option-keys-match-chat: A question sent to both chat and page keeps the same option letters and labels in each, and a stored (ruling text: "Owner 12:35")
  - page-item-id-check: Every page reader takes an item's id from its doc key (ruling text: "Owner comment 13:44")
  - page-save-reaches-auto-mode: Auto mode counts a page save as the owner's grant (ruling text: "Owner answered c in the lane's chat, 11:47")
  - page-write-no-card: A page database write never opens a permission card in a cloud session (ruling text: "owner 19:01")

## prose-unmapped-4

- Kind: prose. Repo: claude-settings.
- Files or homes: unmapped
- Steps:
  - pr-backlog-clear: Give every open PR in claude-settings and q_max one next act and an owner (ruling text: "owner Owner, 12:17")
  - pr-review-range-check: A PR body's review range starts at the parent head (ruling text: "owner ruling")
  - pre-existing-needs-main-run: A report that calls a failure "pre-existing" names a run on the base branch's tip (ruling text: "owner 13:20")
  - pro-slot-udid: #1709 goes into the next batch (ruling text: "Owner chat ask at 06:19")
  - qmax-browser-shard: q_max browser runs in parallel shards (ruling text: "Owner, 16:52")
  - qmax-worktree-db-after-neon-purge: q_max: the 4 old worktrees get a working Neon branch again after the wt- purge (ruling text: "Owner item 361 done (11:49")
  - r2: q_max: merge its three token layers (ruling text: "Owner go, Nov 1 17:26")
  - repeat-judge-never-blocks: The repeat judge skips the item's own home and the same owner message, and never blocks (ruling text: "owner 2026-11-11 13:03")

## prose-unmapped-5

- Kind: prose. Repo: claude-settings.
- Files or homes: unmapped
- Steps:
  - reviewed-sends-back: merge --reviewed names each draft over 12 h old with a missing, stale or bad record, for the runner  (ruling text: "Owner ask, 10:15")
  - roster-on-record-branch: The roster lives on the record branch, and no item stores a session id (ruling text: "owner 19:19")
  - ruleset-pr-bypass: Main is protected by one shared GitHub ruleset with a PR-only admin bypass (ruling text: "Owner 16:42")
  - runner-drops-handed-lane: A batch runner says so when a handed-over lane is left out of a batch (ruling text: "Owner ruling 11:57")
  - send-message-refs-resolve: A message to another session that names a commit, record or PR that does not exist is caught (ruling text: "owner 13:20")
  - shivpedia-count: Count whether the practice records earn their keep (ruling text: "owner 20:24")
  - shoot-touch-per-size: bin/shoot sets hasTouch for each size, and a full-page shot keeps it (ruling text: "Owner item 423 c (10:20")
  - sort281-merge-main-list: Merge main into the wanted PRs from the 281 sort, then land, in this order (ruling text: "Owner 15:31")

## prose-unmapped-6

- Kind: prose. Repo: claude-settings.
- Files or homes: unmapped
- Steps:
  - spend-log-per-batch: The batch runner logs each session's spend at each batch merge (ruling text: "Owner 11:55")
  - token-spend-sources: Measure where this operation's tokens go: models per role, context size, and waste (ruling text: "Owner ask ask-mw83yebd18 (11:30")
  - usage-brake: On a rate-limited account, usage at 90% winds work down and 94% stops new work (ruling text: "owner 2026-11-11 13:48")

## prose-waiting-page

- Kind: prose. Repo: claude-settings.
- Files or homes: docs/debts/114-waiting-scan-misses.md, docs/debts/waiting-scan-kept-rule-gaps.md, docs/design/ask-phase-out.html, skills/waiting-page, skills/waiting-page/export_page.py, skills/waiting-page/page.html
- Steps:
  - ask-phase-out: A routed ask or answered item shows one line on the waiting page and leaves when the owner marks it  (ruling text: "Owner pick 480 a (09:14")
  - export-scan-gaps: The export secret scan closes two named limits: a value whose first digit sits past 256 characters,  (ruling text: "owner, 13:20")
  - open-asks-listed-at-wake: The page writer's wake lists every owner ask with no reply, so a routed ask is also closed on the pa (ruling text: "owner chat 11:26")
  - page-feedback-to-template: An owner comment on any repo's waiting page about the page's form becomes a claude-settings step tha (ruling text: "Owner 09:13")
  - page-pics-fill-card: A waiting-page option picture fills its card width (ruling text: "Owner, 2026-11-09 20:47")
  - page-wakes-and-relays: Only triage watches the page; each item names who wakes; one home per answer; a relayed grant carrie (ruling text: "Owner R18, 16:46")
  - past-ruling-on-send: The past-ruling judge runs on a question sent to the page writer, before the send (ruling text: "owner ruling")
  - waiting-export-receipts: The page export and WAITING_COLLECTIONS include receipts (ruling text: "Owner ask, 13:20")

