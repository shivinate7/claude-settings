# Records index

This page lists every record in this repo: the rules in `CLAUDE.md`, and the files in `decisions/`, `debts/`, `deferred/` and `plans/`. A script writes it. Do not edit it by hand.

The merge tool writes this page again when a pull request merges, so a pull request need not carry a fresh one. To write it by hand, run `python3 lint/hook_catalog.py` from the claude-settings checkout, with `--root` set to this repo. The check on the default branch fails when the page is stale.

Each row has the slug, the first sentence of the record, and a link to it. A record that a ruling overrules is rewritten in place, so no row holds old text.

## Mandates

| Slug | Gist | Link |
|---|---|---|
| `outcomes-judge-by-outcome` | Judge every rule, check, and design by the outcome for the person the software serves. | [`CLAUDE.md`](../CLAUDE.md) |
| `outcomes-decision-is-argument` | Treat a recorded decision as an argument, not a law. | [`CLAUDE.md`](../CLAUDE.md) |
| `outcomes-stale-decision-protocol` | When a decision looks stale, name the entry and the sentence. | [`CLAUDE.md`](../CLAUDE.md) |
| `outcomes-tests-are-claims` | A failing test is a claim, not law. | [`CLAUDE.md`](../CLAUDE.md) |
| `outcomes-word-covers-named-act` | My word covers the act it names, never a variant of it. | [`CLAUDE.md`](../CLAUDE.md) |
| `outcomes-mechanize-rules` | Once ready, turn each rule below into a hook or check. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-pick-mode-from-request` | Pick solo or orchestrate from my request. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-solo-builds-short-edit-list` | Solo: the request is a short list of edits with nothing to run in parallel. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-solo-reviews-logic-diffs-only` | In solo, a fresh reviewer reads the diff before merge only when it touches a rule's behaviour, a gate's verdict, or program logic. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-solo-grows-switch-to-orchestrate` | If a solo job grows, switch to orchestrate and say so in one line. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-orchestrator-never-builds` | Orchestrate: every other job. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-one-role-per-worker` | Each worker is one role: builder, reviewer, or Explore, never two. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-sonnet-is-the-default` | A workflow agent takes the builder or reviewer role through `agentType`. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-sonnet-is-the-floor` | Haiku runs only in the roles that table names. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-sonnet-is-the-ceiling` | Sonnet is the ceiling, except Plan, the advisor, and a builder's third try (`roles-third-try-steps-up`), which run Opus. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-opus-shaped-say-so` | When a task is Opus-shaped (long-horizon, whole-codebase, or many-hour autonomous work), say so in one line before you dispatch, name why, and offer the switch. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-opus-override-guarded` | Only on my word, write the repo's `.claude/settings.local.json` with an `env` block that raises `CLAUDE_CODE_SUBAGENT_MODEL` to `opus`. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-override-carries-expiry` | The file also carries `_subagentCapUntil`, an ISO-8601 time no more than 24 hours ahead. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-remove-override-file` | Remove the file when the raise is no longer needed. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-workers-never-spawn` | Workers never spawn: nested reports misroute (Sept 2026). | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-brief-contents` | A brief carries the task, the files, governing rulings, failure classes from `outcomes-tests-are-claims`, and the check that proves the task done—in the fewest words. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-each-layer-proves-once` | Each layer proves a change once. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-review-cap-three` | A change gets at most three review rounds. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-holes-are-debts` | Each known gap is a debt in the repo's debt store. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-third-try-steps-up` | Builders get two Sonnet tries; if review round 2 fails, the third (`Try 3 of 3`) runs on Opus by the owner's standing word. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-resume-by-name` | Resume a dead agent by name, never fresh. | [`CLAUDE.md`](../CLAUDE.md) |
| `parallelism-each-own-checkout` | Fan tasks out to workers now, each in its own checkout. | [`CLAUDE.md`](../CLAUDE.md) |
| `parallelism-own-lane-orchestrator` | A read-only workflow agent shares the caller's checkout. | [`CLAUDE.md`](../CLAUDE.md) |
| `parallelism-no-mid-task-talk` | Never let lanes talk mid-task. | [`CLAUDE.md`](../CLAUDE.md) |
| `parallelism-argue-max-parallelism` | Argue "at max parallelism" by naming the open lanes, never by assuming the claim. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-no-destructive-git` | Never run `git stash`, `git reset`, `git checkout <path>`, or `git restore` in a shared checkout. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-no-machine-wide-kill` | A stash entry belongs to no branch. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-one-checkout-per-agent` | Give one checkout to each concurrent agent. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-own-ports-data` | A branch switch is a whole-tree act. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-confirm-before-write` | Confirm which checkout and branch you stand in before any git write or merge. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-reverify-after-incident` | Re-verify every edit after an incident. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-install-refusal-hook` | On first use, install a hook that refuses these commands. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-main-only-by-pr` | Move main only by pull request, merged only when I name the act, or under a repo grant. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-wait-for-required-checks` | Wait for required checks after every push. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-never-merge-failing-ci` | Never merge failing CI. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-never-discard-output` | Never discard a command's output. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-remedy-never-names-target` | A refusal's printed remedy never names the forbidden target. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-slug-then-claim-number` | Never allocate a numbered record on a branch. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-cite-by-id` | Cite by id, never by path. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-record-own-file-per-kind` | Give each record its own file, one folder per kind. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-one-entry-per-question` | One entry per question. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-integration-branch-merge` | Batch lane PRs that pass their local checks into one integration branch. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-draft-until-reviewed` | Open every PR as a draft. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-screens-verdict` | If the repo has screens, check each screen at every size and theme it ships in. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-browser-login-only-needed` | Prefer a headless or isolated browser over my own, and use my login only when needed. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-announce-own-screen` | Before a window or a screen capture lands on my screen, say so in one line. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-trust-guard-after-red` | Trust a guard only once it goes red on the defect it guards. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-cry-wolf-guard-is-spent` | A guard that goes red when nothing is wrong is spent, because the reader learns to scroll past it. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-green-proves-only-its-fixtures` | A green check proves only its platform and the states its fixtures build. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-recovery-not-gated-on-own-state` | A recovery control must not depend on the state it recovers, or it fails on the one day it is needed. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-verify-against-repo` | Verify long work against the repo, not your status line. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-never-waiter-loop` | Never write a waiter loop. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-never-dry-run-blocklist` | Never dry-run a block-list. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-bump-first-fix-version` | Bump a dependency to the first version fixing the problem, never the latest. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-checked-reader-for-numbers` | If this repo lints markdown, give every published number and path a checked reader. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-report-unknown-reads` | Verify a claim before you rely on it, a document's own claims too. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-never-load-whole-doc` | Never load a long document whole. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-verdict-not-stream` | A verification command's answer is its verdict, not its stream. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-run-through-verdict` | Run every verification command through `verdict <cmd>`, which prints the verdict and keeps the full output in a log. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-point-brief-at-files` | Point a brief at files. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-read-report-not-transcript` | Read a sub-agent's report, never its transcript. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-compacting-keep-essentials` | When compacting, keep the files, the commands, each ruling's home, and the pid and port of each server still running. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-never-guess-answer` | Never guess an answer the code should give you. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-surface-ambiguity` | Surface ambiguity instead of resolving it silently. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-never-drop-item-silently` | Never drop an item without saying so. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-one-home-per-capability` | Give each capability one home, and call it from everywhere. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-allow-list-is-the-constant` | A gate's allow list must point at the constant the code emits, never a copy of it. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-guard-needs-incident` | Build a new guard or gate rule only against a named incident or a measured risk. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-fix-cause-not-symptom` | Fix the cause, not the symptom. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-scanner-respects-strings` | Scan source code with the language's own parser or tokenizer when the repo has one. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-land-design-or-abandon` | A capability no user can reach is not built. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-memory-never-only-home` | A memory entry may point to a ruling. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-memory-is-short-term` | Memory stays on, as short-term notes. | [`CLAUDE.md`](../CLAUDE.md) |
| `speak-cite-id-plus-gloss` | Cite a record by id plus a short gloss, like "D12, short titles for records". | [`CLAUDE.md`](../CLAUDE.md) |
| `speak-never-explain-in-paragraph` | Never explain a rule in a paragraph. | [`CLAUDE.md`](../CLAUDE.md) |
| `speak-rewrite-superseded-in-place` | Rewrite superseded text in place. | [`CLAUDE.md`](../CLAUDE.md) |
| `output-write-in-ste` | Write in Simplified Technical English by default, to me and between agents, unless told otherwise. | [`CLAUDE.md`](../CLAUDE.md) |
| `output-never-paste-passing-output` | Rules for replies to me, and not to agents, live in the `shiv-stylisms` output style. | [`CLAUDE.md`](../CLAUDE.md) |
| `output-bring-decisions-as-question` | Bring my decisions as a question with options and a recommendation. | [`CLAUDE.md`](../CLAUDE.md) |
| `output-answer-has-a-home` | An answer to a question I bring is a ruling. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-order-of-labels` | Done, Deviations, Input Needed, Next. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-done-format` | Done: one line per item, BUILT, RECORDED, or OTHER. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-drop-unused-label` | Drop a label that does not apply. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-no-report-when-nothing-landed` | No report when nothing landed. | [`CLAUDE.md`](../CLAUDE.md) |

## Rulings

| Slug | Gist | Link |
|---|---|---|
| `background-needs-end-note` | Owner ruling, 2026-10-13 23:41 CDT: "End condition at start." | [`decisions/background-needs-end-note.md`](../decisions/background-needs-end-note.md) |
| `debts-have-their-own-store` | Every known gap is a debt. | [`decisions/debts-have-their-own-store.md`](../decisions/debts-have-their-own-store.md) |
| `decision-watch-mod-limits` | Yes. | [`decisions/decision-watch-mod-limits.md`](../decisions/decision-watch-mod-limits.md) |
| `design-skills` | Owner ruling, 2026-10-10. | [`decisions/design-skills.md`](../decisions/design-skills.md) |
| `env-file-wrappers` | The `env-file` rule allows `--env-file` only when the command word is a runner (`ENV_LOADER_COMMANDS`). | [`decisions/env-file-wrappers.md`](../decisions/env-file-wrappers.md) |
| `gate-hooks-fail-closed` | Owner, 2026-10-12: a gate whose script or python is missing refuses the call. | [`decisions/gate-hooks-fail-closed.md`](../decisions/gate-hooks-fail-closed.md) |
| `guard-audit-high` | Which guard refusals are false alarms or gaps? | [`decisions/guard-audit-high.md`](../decisions/guard-audit-high.md) |
| `guard-log-read-weekly` | `hooks/guard_core.py:record()` appends one line per verdict to `~/.claude/guard.log`. | [`decisions/guard-log-read-weekly.md`](../decisions/guard-log-read-weekly.md) |
| `haiku-prompt-hooks` | The owner ruled on 2026-10-07 which hooks may call a model. | [`decisions/haiku-prompt-hooks.md`](../decisions/haiku-prompt-hooks.md) |
| `janitor-dirty-test-stays` | Owner word, 2026-10-13 15:56 CDT: option A. | [`decisions/janitor-dirty-test-stays.md`](../decisions/janitor-dirty-test-stays.md) |
| `lane-by-slug` | Owner, 2026-10-13 14:13 CDT, relayed by the oversight session: | [`decisions/lane-by-slug.md`](../decisions/lane-by-slug.md) |
| `local-time-central` | Owner, 2026-10-12: US Central (America/Chicago), DST-aware, 24-hour clock. | [`decisions/local-time-central.md`](../decisions/local-time-central.md) |
| `mods-deferred-table` | Owner word, 2026-10-13 21:00 CDT: leave these as deferred recordings on the repo. | [`decisions/mods-deferred-table.md`](../decisions/mods-deferred-table.md) |
| `mods-install-via-marketplace` | The shared `settings.json` declares one marketplace, `claude-settings`. | [`decisions/mods-install-via-marketplace.md`](../decisions/mods-install-via-marketplace.md) |
| `mods-no-cli-key-headless` | No CLI API key for headless runs. | [`decisions/mods-no-cli-key-headless.md`](../decisions/mods-no-cli-key-headless.md) |
| `mods-tests-run-in-gates` | Merge session, 2026-10-13, 13:16 CDT. | [`decisions/mods-tests-run-in-gates.md`](../decisions/mods-tests-run-in-gates.md) |
| `opt-in-ci-templates-composite` | Owner approved six templates any repo can adopt. | [`decisions/opt-in-ci-templates-composite.md`](../decisions/opt-in-ci-templates-composite.md) |
| `purge-keeps-younger-restore-ref` | The purge drops a restore ref only when both hold: | [`decisions/purge-keeps-younger-restore-ref.md`](../decisions/purge-keeps-younger-restore-ref.md) |
| `question-outcome-check` | Owner ruling, 2026-10-13 19:48 CDT: the standard question format is a `Goal:` line first, then a `Problem:` sentence, then the options. | [`decisions/question-outcome-check.md`](../decisions/question-outcome-check.md) |
| `review-cap-red-ci` | Owner ruling, 2026-10-13 14:50 CDT: "Split, then ask." | [`decisions/review-cap-red-ci.md`](../decisions/review-cap-red-ci.md) |
| `rulings-declare-kind` | Owner ruling, 2026-10-12. | [`decisions/rulings-declare-kind.md`](../decisions/rulings-declare-kind.md) |
| `silent-undo-check-design` | `lint/check_silent_undo.py` is the one home. | [`decisions/silent-undo-check-design.md`](../decisions/silent-undo-check-design.md) |
| `stall-watch` | A background command can stop making progress. | [`decisions/stall-watch.md`](../decisions/stall-watch.md) |
| `stall-watch-stop-check` | A background shell can stay open after a turn ends. | [`decisions/stall-watch-stop-check.md`](../decisions/stall-watch-stop-check.md) |
| `stamp-cite-near-miss` | Where does the check for a wrongly wrapped cite live, and how does an agent learn the right form? | [`decisions/stamp-cite-near-miss.md`](../decisions/stamp-cite-near-miss.md) |
| `ste-gate-fixes-not-nags` | The gate fixes first. | [`decisions/ste-gate-fixes-not-nags.md`](../decisions/ste-gate-fixes-not-nags.md) |
| `subagent-model-cap` | CLAUDE.md says: "Once ready, turn each rule below into a hook or check." This entry records how the worker-model rule is mechanized after `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` is dropped. | [`decisions/subagent-model-cap.md`](../decisions/subagent-model-cap.md) |
| `wsl-allow-list` | Owner ruling, 2026-10-13 15:20: "fixed test list is fine; surf the web for a consensus first". | [`decisions/wsl-allow-list.md`](../decisions/wsl-allow-list.md) |

## Build designs

| Slug | Gist | Link |
|---|---|---|
| `handoff-hooks-wave-2` | Owner ruling, 2026-10-13 11:20 CDT: build all three in claude-settings. | [`decisions/handoff-hooks-wave-2.md`](../decisions/handoff-hooks-wave-2.md) |
| `install-hooks-whole` | The installer writes each file to a temp name in the same folder, then renames it over the target. | [`decisions/install-hooks-whole.md`](../decisions/install-hooks-whole.md) |
| `merge-net-retry` | Owner, 2026-10-13, about 16:25 CDT: "Retry 3 times." | [`decisions/merge-net-retry.md`](../decisions/merge-net-retry.md) |
| `owner-feedback-inbox` | Owner ruling, 2026-10-13, from an interview in the claude-settings audit session. | [`decisions/owner-feedback-inbox.md`](../decisions/owner-feedback-inbox.md) |
| `stash-stack-is-a-shared-subject` | CLAUDE.md says: "Never run `git stash` ... | [`decisions/stash-stack-is-a-shared-subject.md`](../decisions/stash-stack-is-a-shared-subject.md) |

## Unsorted decisions

| Slug | Gist | Link |
|---|---|---|
| `a-branch-is-redundant-by-patch-not-by-ancestry` | The sweep in `plans/janitor-build-plan.md` keeps or reaps a local branch. | [`decisions/a-branch-is-redundant-by-patch-not-by-ancestry.md`](../decisions/a-branch-is-redundant-by-patch-not-by-ancestry.md) |
| `a-gates-allow-list-is-the-constant` | CLAUDE.md now names this rule: a gate's allow list must point at the constant the code emits, never a copy of it. | [`decisions/a-gates-allow-list-is-the-constant.md`](../decisions/a-gates-allow-list-is-the-constant.md) |
| `a-kill-by-pid-needs-an-owned-pid` | CLAUDE.md says: "Never kill a process you did not start." The guard denied a kill by name or by pattern. | [`decisions/a-kill-by-pid-needs-an-owned-pid.md`](../decisions/a-kill-by-pid-needs-an-owned-pid.md) |
| `a-rule-with-no-gate-leaves-claude-md` | On 2026-09-28 the owner ruled that the semicolon line leaves `CLAUDE.md`. | [`decisions/a-rule-with-no-gate-leaves-claude-md.md`](../decisions/a-rule-with-no-gate-leaves-claude-md.md) |
| `a-test-fixture-name-can-overflow-windows-path-length` | A fixture name built from a test's own description can overflow Windows path length | [`decisions/a-test-fixture-name-can-overflow-windows-path-length.md`](../decisions/a-test-fixture-name-can-overflow-windows-path-length.md) |
| `adoptions-declined-2026-09-28` | A review of public Claude Code configs and native features proposed these. | [`decisions/adoptions-declined-2026-09-28.md`](../decisions/adoptions-declined-2026-09-28.md) |
| `agent-end-reap-stops-what-a-finished-agent-left` | This record is step 2 of the plan in `which-start-shapes-outlive-the-agent-on-windows` (start shapes that outlive a subagent on Windows; PR #144). | [`decisions/agent-end-reap-stops-what-a-finished-agent-left.md`](../decisions/agent-end-reap-stops-what-a-finished-agent-left.md) |
| `agent-worktree-discard-is-noted` | The shared-tree rule asks the owner before a discarding git command runs. | [`decisions/agent-worktree-discard-is-noted.md`](../decisions/agent-worktree-discard-is-noted.md) |
| `agents-get-standing-rules` | Owner, 2026-10-12: a SubagentStart hook injects them. | [`decisions/agents-get-standing-rules.md`](../decisions/agents-get-standing-rules.md) |
| `agents-wait-with-monitor` | Which way may an agent wait for a condition? | [`decisions/agents-wait-with-monitor.md`](../decisions/agents-wait-with-monitor.md) |
| `an-agent-outside-its-home-tree-must-stop` | An agent outside its home tree must stop | [`decisions/an-agent-outside-its-home-tree-must-stop.md`](../decisions/an-agent-outside-its-home-tree-must-stop.md) |
| `bare-bash-on-windows-can-resolve-to-the-wsl-stub` | `hooks/test_config_watch.py`'s bypass cases handed `subprocess.run(["bash", "-c", command], ...)` a bare command name. | [`decisions/bare-bash-on-windows-can-resolve-to-the-wsl-stub.md`](../decisions/bare-bash-on-windows-can-resolve-to-the-wsl-stub.md) |
| `bash-path-breaks-only-when-the-snapshot-breaks` | The Bash tool's PATH breaks only when its shell snapshot breaks | [`decisions/bash-path-breaks-only-when-the-snapshot-breaks.md`](../decisions/bash-path-breaks-only-when-the-snapshot-breaks.md) |
| `branch-delete-wrong-cause-was-a-filename-collision` | `decisions/branch-delete-wrong-cause-on-windows-unexplained.md` named a real defect and said its cause stayed unexplained. | [`decisions/branch-delete-wrong-cause-was-a-filename-collision.md`](../decisions/branch-delete-wrong-cause-was-a-filename-collision.md) |
| `browser-prompts-are-the-apps` | Owner, 2026-10-11: no. | [`decisions/browser-prompts-are-the-apps.md`](../decisions/browser-prompts-are-the-apps.md) |
| `build-dirs-reaped-at-agent-end` | Owner ruling, 2026-10-11, labeled "Agent-end hook + low-disk guard". | [`decisions/build-dirs-reaped-at-agent-end.md`](../decisions/build-dirs-reaped-at-agent-end.md) |
| `builders-cannot-edit-tests` | Builders cannot edit tests | [`decisions/builders-cannot-edit-tests.md`](../decisions/builders-cannot-edit-tests.md) |
| `ci-spend-rules` | Skill steps 1 and 11 to 14 hold these rules. | [`decisions/ci-spend-rules.md`](../decisions/ci-spend-rules.md) |
| `ci-unknown-is-red-and-dedup` | A lint that cannot read its input prints UNKNOWN. | [`decisions/ci-unknown-is-red-and-dedup.md`](../decisions/ci-unknown-is-red-and-dedup.md) |
| `ci-wall-time-cuts` | The owner chose cuts A to D on 2026-10-07. | [`decisions/ci-wall-time-cuts.md`](../decisions/ci-wall-time-cuts.md) |
| `copy-mode-overwrites-no-backup` | Owner, 2026-10-03: in copy mode, an installer overwrites its own old copy. | [`decisions/copy-mode-overwrites-no-backup.md`](../decisions/copy-mode-overwrites-no-backup.md) |
| `default-discover-roots-needed-normpath-on-windows` | `default_discover_roots()` needed `normpath`, and its test needed `USERPROFILE` | [`decisions/default-discover-roots-needed-normpath-on-windows.md`](../decisions/default-discover-roots-needed-normpath-on-windows.md) |
| `docs-only-prs-skip-code-suites` | `hooks/test_install_src.sh` takes case names as arguments and runs only those. | [`decisions/docs-only-prs-skip-code-suites.md`](../decisions/docs-only-prs-skip-code-suites.md) |
| `docs-only-prs-skip-review` | Docs-only pull requests skip the reviewer | [`decisions/docs-only-prs-skip-review.md`](../decisions/docs-only-prs-skip-review.md) |
| `draft-until-reviewed` | Owner rulings, 2026-10-10 and 2026-10-13. | [`decisions/draft-until-reviewed.md`](../decisions/draft-until-reviewed.md) |
| `drops-lines-trailer-exempt` | Owner, 2026-10-12: the `Drops-lines: <record path> -- <reason>` trailer is the one place a record path is allowed in a commit message. | [`decisions/drops-lines-trailer-exempt.md`](../decisions/drops-lines-trailer-exempt.md) |
| `every-lint-rule-blocks-or-does-not-exist` | CLAUDE.md says: "Judge every rule, check, and design by the outcome for the person the software serves." `lint/ste_lint.py` held 19 rules. | [`decisions/every-lint-rule-blocks-or-does-not-exist.md`](../decisions/every-lint-rule-blocks-or-does-not-exist.md) |
| `fewest-words-mandate` | On 2026-09-28 the owner asked for a verbiage mandate. | [`decisions/fewest-words-mandate.md`](../decisions/fewest-words-mandate.md) |
| `frozen-path-resolves-shell-vars` | Rule 7 resolves shell variables before it matches a write target | [`decisions/frozen-path-resolves-shell-vars.md`](../decisions/frozen-path-resolves-shell-vars.md) |
| `guard-split-by-family` | Owner, 2026-10-12 and 2026-10-13: | [`decisions/guard-split-by-family.md`](../decisions/guard-split-by-family.md) |
| `guard-that-cries-wolf-is-spent` | CLAUDE.md says: "Trust a guard only once it goes red on the defect it guards." This entry records the missing half, and the two false alarms that made the half worth writing down. | [`decisions/guard-that-cries-wolf-is-spent.md`](../decisions/guard-that-cries-wolf-is-spent.md) |
| `guard-trims-from-the-audit` | The owner approved these trims from an audit of `~/.claude/guard.log`: 2,713 lines, 2026-09-16 to 2026-10-02. | [`decisions/guard-trims-from-the-audit.md`](../decisions/guard-trims-from-the-audit.md) |
| `hooks-share-the-transcript-reader` | Four hooks each carried their own copy of the same transcript readers. | [`decisions/hooks-share-the-transcript-reader.md`](../decisions/hooks-share-the-transcript-reader.md) |
| `known-bad-input-proves-the-gate` | A `gate` row cites a `test` id (`path::name`, `path::Class.name`) or a `setting` value. | [`decisions/known-bad-input-proves-the-gate.md`](../decisions/known-bad-input-proves-the-gate.md) |
| `list-form-subprocess-ignores-a-path-shim-on-windows` | Three suites drive a blind `git` stand-in through a directory placed first on `PATH`. | [`decisions/list-form-subprocess-ignores-a-path-shim-on-windows.md`](../decisions/list-form-subprocess-ignores-a-path-shim-on-windows.md) |
| `liveness-read-is-platform-specific-and-unreadable-is-not-death` | `hooks/guard.py`'s liveness oracle (`_process_start_ms`, `session_is_live`, `worktree_live_session`) folded two different facts into one answer. | [`decisions/liveness-read-is-platform-specific-and-unreadable-is-not-death.md`](../decisions/liveness-read-is-platform-specific-and-unreadable-is-not-death.md) |
| `main-branch-protection` | main branch protection | [`decisions/main-branch-protection.md`](../decisions/main-branch-protection.md) |
| `memory-is-never-a-rulings-only-home` | The owner's rulings must reach a tracked file. | [`decisions/memory-is-never-a-rulings-only-home.md`](../decisions/memory-is-never-a-rulings-only-home.md) |
| `merge-config-defaults` | Must a repo have `.github/stamp.json` before the merge tool works in it? | [`decisions/merge-config-defaults.md`](../decisions/merge-config-defaults.md) |
| `merge-needs-a-proven-head` | Owner, 2026-10-12: "Fix both now, one lane." | [`decisions/merge-needs-a-proven-head.md`](../decisions/merge-needs-a-proven-head.md) |
| `merge-notice-checks-the-report` | CLAUDE.md: "A guard that goes red when nothing is wrong is spent, because the reader learns to scroll past it." And: trust a guard only once it goes red on the defect it guards. | [`decisions/merge-notice-checks-the-report.md`](../decisions/merge-notice-checks-the-report.md) |
| `merge-reinstalls-from-main` | `install.sh` links the shipped skills, hooks and tools into `~/.claude`. | [`decisions/merge-reinstalls-from-main.md`](../decisions/merge-reinstalls-from-main.md) |
| `mutant-cause-of-death` | CLAUDE.md says: "Trust a guard only once it goes red on the defect it guards." This entry is that sentence applied to the guard's own test harness. | [`decisions/mutant-cause-of-death.md`](../decisions/mutant-cause-of-death.md) |
| `mutation-harnesses-run-when-their-code-changes` | `.github/scripts/harness-scope.sh` reads `git diff --name-only` against the merge base and sets one output per harness. | [`decisions/mutation-harnesses-run-when-their-code-changes.md`](../decisions/mutation-harnesses-run-when-their-code-changes.md) |
| `one-entry-per-question` | On 2026-09-29 the owner ruled that a decision entry answers one question, and a changed ruling rewrites that entry. | [`decisions/one-entry-per-question.md`](../decisions/one-entry-per-question.md) |
| `one-shared-record-stamp` | **Changed in part on 2026-09-28** by `record-stamp-stays-generic`, the stamp stays generic. | [`decisions/one-shared-record-stamp.md`](../decisions/one-shared-record-stamp.md) |
| `plain-diff-mod-limits` | The mod sends a diff to `$.model.complete` only for a file that passes the secret filter. | [`decisions/plain-diff-mod-limits.md`](../decisions/plain-diff-mod-limits.md) |
| `playwright-browsers-path` | No. | [`decisions/playwright-browsers-path.md`](../decisions/playwright-browsers-path.md) |
| `playwright-install-once` | Owner, 2026-10-11 (rule `playwright-install` in `hooks/guard.py`): | [`decisions/playwright-install-once.md`](../decisions/playwright-install-once.md) |
| `precompact-handoff` | Auto-compact drops detail. | [`decisions/precompact-handoff.md`](../decisions/precompact-handoff.md) |
| `predicate-is-the-act` | CLAUDE.md says: "Fix the cause, not the symptom." It also says: "Check whether the primitive exists before building a workaround." This entry records why the markdown sweep stopped reading command text, and what that rule means for the next gate. | [`decisions/predicate-is-the-act.md`](../decisions/predicate-is-the-act.md) |
| `prune-cases-skip-without-symlink-privilege` | Prune cases skip when this account cannot make a real symlink | [`decisions/prune-cases-skip-without-symlink-privilege.md`](../decisions/prune-cases-skip-without-symlink-privilege.md) |
| `record-stamp-stays-generic` | On 2026-09-28 the owner said: "I think moreso you need to remain generic and provide me briefs that allow each of the repos to individually get compliant, rather than carving out exceptions for each repo." | [`decisions/record-stamp-stays-generic.md`](../decisions/record-stamp-stays-generic.md) |
| `recovery-must-not-gate-on-its-own-state` | CLAUDE.md's Verification paragraph now states this rule. | [`decisions/recovery-must-not-gate-on-its-own-state.md`](../decisions/recovery-must-not-gate-on-its-own-state.md) |
| `repeal-the-no-prefix-report-rule` | CLAUDE.md's Reports paragraph said: | [`decisions/repeal-the-no-prefix-report-rule.md`](../decisions/repeal-the-no-prefix-report-rule.md) |
| `retired-numbers-list` | A record may be deleted when its number is named in the kind's `RETIRED` file, in the same tree. | [`decisions/retired-numbers-list.md`](../decisions/retired-numbers-list.md) |
| `reuse-needs-checkout-proof` | Lanes run in separate worktrees of one clone. | [`decisions/reuse-needs-checkout-proof.md`](../decisions/reuse-needs-checkout-proof.md) |
| `rm-on-a-variable-needs-a-guard` | Owner, 2026-10-11 ("Ship guard now, hook later"): | [`decisions/rm-on-a-variable-needs-a-guard.md`](../decisions/rm-on-a-variable-needs-a-guard.md) |
| `schtasks-xml-requires-utf16` | schtasks /create /xml requires UTF-16, not UTF-8 | [`decisions/schtasks-xml-requires-utf16.md`](../decisions/schtasks-xml-requires-utf16.md) |
| `semicolon-and-gendered-pronoun-rules-leave-the-gate` | The owner ruled in chat on 2026-09-23. | [`decisions/semicolon-and-gendered-pronoun-rules-leave-the-gate.md`](../decisions/semicolon-and-gendered-pronoun-rules-leave-the-gate.md) |
| `session-board-mod-limits` | Owner intent: stop typing "status?" into many sessions. | [`decisions/session-board-mod-limits.md`](../decisions/session-board-mod-limits.md) |
| `session-end-sweep-is-disarmed-until-liveness-is-proven` | The `SessionEnd` hook in `settings.json` runs `janitor/session_end_sweep.py`. | [`decisions/session-end-sweep-is-disarmed-until-liveness-is-proven.md`](../decisions/session-end-sweep-is-disarmed-until-liveness-is-proven.md) |
| `source-prose-lint-ships-dark` | CLAUDE.md says: "A guard that goes red when nothing is wrong is spent, because the reader learns to scroll past it." This entry names why `ste_lint.py`'s new comment-and-docstring mode stays off by default. | [`decisions/source-prose-lint-ships-dark.md`](../decisions/source-prose-lint-ships-dark.md) |
| `split-segments-comment-rule` | `hooks/guard.py:split_segments` tracked single and double quotes. | [`decisions/split-segments-comment-rule.md`](../decisions/split-segments-comment-rule.md) |
| `stale-safe-force-push` | CLAUDE.md says: "Judge every rule, check, and design by the outcome for the person the software serves." The outcome here: the owner gets no prompt for a safe push, and no push overwrites newer remote work with a stale copy. | [`decisions/stale-safe-force-push.md`](../decisions/stale-safe-force-push.md) |
| `standing-merge-grant` | Owner ruling, 2026-10-10: the orchestrating session has standing merge authority in claude-settings. | [`decisions/standing-merge-grant.md`](../decisions/standing-merge-grant.md) |
| `stash-push-is-clone-wide` | CLAUDE.md says: "Set work aside with a commit on your own branch, never a stash." It also says: "A stash entry belongs to no branch. | [`decisions/stash-push-is-clone-wide.md`](../decisions/stash-push-is-clone-wide.md) |
| `ste-lint-gloss-collapse` | `lint/ste_lint.py`'s `STE001` counts words per sentence. | [`decisions/ste-lint-gloss-collapse.md`](../decisions/ste-lint-gloss-collapse.md) |
| `stop-guardrail-became-a-command-hook` | The `type: agent` Stop hook in `settings.json` judged every turn for a silent change to a decision, gate, build-order, CLAUDE.md rule, or setting. | [`decisions/stop-guardrail-became-a-command-hook.md`](../decisions/stop-guardrail-became-a-command-hook.md) |
| `sweep-shuts-down-idle-simulators` | Owner rulings, 2026-10-10. | [`decisions/sweep-shuts-down-idle-simulators.md`](../decisions/sweep-shuts-down-idle-simulators.md) |
| `tests-are-claims-not-law` | Tests are claims, not law | [`decisions/tests-are-claims-not-law.md`](../decisions/tests-are-claims-not-law.md) |
| `the-janitor-is-one-machine-wide-sweep` | The sweep deletes a local branch when that branch holds no unique work. | [`decisions/the-janitor-is-one-machine-wide-sweep.md`](../decisions/the-janitor-is-one-machine-wide-sweep.md) |
| `the-orchestrator-builds-by-verdict-not-by-line-count` | Supersedes README Decision 13, "the orchestrator and product code: judge the act, not the file". | [`decisions/the-orchestrator-builds-by-verdict-not-by-line-count.md`](../decisions/the-orchestrator-builds-by-verdict-not-by-line-count.md) |
| `the-stop-guardrail-is-disarmed-until-the-command-hook-lands` | The `Stop` hook entry of `type: "agent"` is removed from `settings.json`. | [`decisions/the-stop-guardrail-is-disarmed-until-the-command-hook-lands.md`](../decisions/the-stop-guardrail-is-disarmed-until-the-command-hook-lands.md) |
| `unattended-sweep-stops-proven-orphans` | PR #132 added an orphaned-listener check to `janitor/sweep.py`. | [`decisions/unattended-sweep-stops-proven-orphans.md`](../decisions/unattended-sweep-stops-proven-orphans.md) |
| `ux-house-rules` | Owner ruling, 2026-10-11: "build a ux folder". | [`decisions/ux-house-rules.md`](../decisions/ux-house-rules.md) |
| `verdict-reads-runner-markers` | Owner, 2026-10-11 ("start the verdict lane"): | [`decisions/verdict-reads-runner-markers.md`](../decisions/verdict-reads-runner-markers.md) |
| `which-start-shapes-outlive-the-agent-on-windows` | This entry is step 1 of a plan. | [`decisions/which-start-shapes-outlive-the-agent-on-windows.md`](../decisions/which-start-shapes-outlive-the-agent-on-windows.md) |
| `worktree-setup-is-per-repo` | Owner, 2026-10-10: no. | [`decisions/worktree-setup-is-per-repo.md`](../decisions/worktree-setup-is-per-repo.md) |

## Debts

| Slug | Gist | Link |
|---|---|---|
| `bg-end-false-alarms` | The rule splits script names on `:` and `-`, so `build:dev` and `test-watch-ci` read as servers. | [`debts/bg-end-false-alarms.md`](../debts/bg-end-false-alarms.md) |
| `bg-end-roster-gaps` | The roster is a closed list. | [`debts/bg-end-roster-gaps.md`](../debts/bg-end-roster-gaps.md) |
| `catalog-mode-detect-flags` | The catalog finds a script's modes only from a `"$g" --flag` argument. | [`debts/catalog-mode-detect-flags.md`](../debts/catalog-mode-detect-flags.md) |
| `debt-decision-link-unchecked` | No check confirms that a debt's decision still names its gap. | [`debts/debt-decision-link-unchecked.md`](../debts/debt-decision-link-unchecked.md) |
| `dw-notice-lead-space-lost` | The mod's log folds whitespace, so whitespace at the very start of a notice is lost in the log. | [`debts/dw-notice-lead-space-lost.md`](../debts/dw-notice-lead-space-lost.md) |
| `guard-timeout-fails-open` | If the PreToolUse guard times out or crashes, Claude Code lets the call run. | [`debts/guard-timeout-fails-open.md`](../debts/guard-timeout-fails-open.md) |
| `guard-timing-case-flaky` | The rm-var case "64000 bindings before a delete are judged in under 2 s CPU" took 2.14 s on a macOS runner (PR 419). | [`debts/guard-timing-case-flaky.md`](../debts/guard-timing-case-flaky.md) |
| `hint-signed-commit-sha` | With `log.showSignature=true` in config, git prints a signature line before a signed commit's record. | [`debts/hint-signed-commit-sha.md`](../debts/hint-signed-commit-sha.md) |
| `holes-await-debts-migrate` | The "Holes, named" sections in `decisions/` have no debt files yet. | [`debts/holes-await-debts-migrate.md`](../debts/holes-await-debts-migrate.md) |
| `inplace-edit-under-0-9-flagged` | A branch can edit a line that main only added. | [`debts/inplace-edit-under-0-9-flagged.md`](../debts/inplace-edit-under-0-9-flagged.md) |
| `install-reader-can-die-silent` | `HookReader` counts each read fault, but two lines sit outside its try: the file-name read and the body index. | [`debts/install-reader-can-die-silent.md`](../debts/install-reader-can-die-silent.md) |
| `install-skill-fail-exits-0` | If `Install-Dir` cannot replace a skill folder, the run does not retry it and exits 0. | [`debts/install-skill-fail-exits-0.md`](../debts/install-skill-fail-exits-0.md) |
| `install-stamp-line-unpinned` | Tests pin each stamper only to fixture copies. | [`debts/install-stamp-line-unpinned.md`](../debts/install-stamp-line-unpinned.md) |
| `install-writes-in-place` | The `CLAUDE.md` pointer, `settings.json` in `install.sh`, the skills folder, the install log and the marker are written in place. | [`debts/install-writes-in-place.md`](../debts/install-writes-in-place.md) |
| `judge-cut-mark-reserve-over` | `fit_span` keeps 37 chars for the cut mark even when no owner message can be cut. | [`debts/judge-cut-mark-reserve-over.md`](../debts/judge-cut-mark-reserve-over.md) |
| `lock-expiry-read-no-retry` | The merge lock reads its commit message once, with no retry. | [`debts/lock-expiry-read-no-retry.md`](../debts/lock-expiry-read-no-retry.md) |
| `merge-by-button-stale-page` | The merge tool rebuilds the records page before it merges. | [`debts/merge-by-button-stale-page.md`](../debts/merge-by-button-stale-page.md) |
| `merge-say-surrogate-crash` | The merge tool prints ALLOWED notes and an excused UNKNOWN to stdout with a plain print. | [`debts/merge-say-surrogate-crash.md`](../debts/merge-say-surrogate-crash.md) |
| `model-clip-unmeasured` | The prompt now goes to `claude -p` on stdin, so no argv cap bounds it. | [`debts/model-clip-unmeasured.md`](../debts/model-clip-unmeasured.md) |
| `net-error-colon-http-refusal` | `NET_ERROR` matches `: HTTP 5xx (url)` at a line end. | [`debts/net-error-colon-http-refusal.md`](../debts/net-error-colon-http-refusal.md) |
| `node-file-server-unchecked` | `node <file>` under `run_in_background` is not refused without an `until:` note. | [`debts/node-file-server-unchecked.md`](../debts/node-file-server-unchecked.md) |
| `off-line-fork-reads-pre-cut` | A branch can be cut from a PR branch that merged later. | [`debts/off-line-fork-reads-pre-cut.md`](../debts/off-line-fork-reads-pre-cut.md) |
| `question-text-not-defanged` | The question text and option labels go into the judge prompt with no fence and no defang, so an asker can forge an Owner block. | [`debts/question-text-not-defanged.md`](../debts/question-text-not-defanged.md) |
| `rebase-loss-before-base-unread` | After a rebase, the silent-undo window starts at the rebase base. | [`debts/rebase-loss-before-base-unread.md`](../debts/rebase-loss-before-base-unread.md) |
| `rule-audit-crashes-on-windows` | `lint/rule_audit.py` crashes on default Windows at line 212, reached from the per-row loop at line 457. | [`debts/rule-audit-crashes-on-windows.md`](../debts/rule-audit-crashes-on-windows.md) |
| `ruling-kind-dir-equals-open` | `lint/check_ruling_kind.py` reads `--dir=x`, or any other unknown option, as a file name. | [`debts/ruling-kind-dir-equals-open.md`](../debts/ruling-kind-dir-equals-open.md) |
| `sendmessage-judge-blind-recvs` | The busy-state layer reads an agent id, a `uds:` address, `main` and `*` as unseen, so it allows. | [`debts/sendmessage-judge-blind-recvs.md`](../debts/sendmessage-judge-blind-recvs.md) |
| `sendmessage-judge-dup-names` | When two sessions share a name, `receiverState` returns unseen and the message is allowed with no state check. | [`debts/sendmessage-judge-dup-names.md`](../debts/sendmessage-judge-dup-names.md) |
| `sendmessage-wording-judge-always` | The SendMessage prompt hook in `settings.json` runs a model call on every send. | [`debts/sendmessage-wording-judge-always.md`](../debts/sendmessage-wording-judge-always.md) |
| `server-wrappers-unread` | The `background-end` rule does not read some wrappers and forms, so a background server behind them is not refused without an `until:` note. | [`debts/server-wrappers-unread.md`](../debts/server-wrappers-unread.md) |
| `slug-lint-skips-abs-and-md` | `lint/check_record_slugs.py` and `lint/check_ruling_kind.py` do not judge an absolute file argument or a name ending in `.MD`. | [`debts/slug-lint-skips-abs-and-md.md`](../debts/slug-lint-skips-abs-and-md.md) |
| `stash-all-ignored-tree-passes` | `git stash -a` and `git stash --all` pass the guard over a tree that holds only ignored files. | [`debts/stash-all-ignored-tree-passes.md`](../debts/stash-all-ignored-tree-passes.md) |
| `stash-export-comment-stale` | The comment above the import and export rows in `hooks/test_guard.py` says `import` and `export` are not git subcommands. | [`debts/stash-export-comment-stale.md`](../debts/stash-export-comment-stale.md) |
| `stash-help-flag-refused-as-push` | `git stash -h` and `git stash --help` are refused over a dirty tree. | [`debts/stash-help-flag-refused-as-push.md`](../debts/stash-help-flag-refused-as-push.md) |
| `ste-exclude-star-crosses-dir` | After the git glob exclude, `run.sh` matches each file again with a bash pattern. | [`debts/ste-exclude-star-crosses-dir.md`](../debts/ste-exclude-star-crosses-dir.md) |
| `symrun-link-gap-unmeasured` | The symrun case wants at least one mixed-id window during run 2. | [`debts/symrun-link-gap-unmeasured.md`](../debts/symrun-link-gap-unmeasured.md) |
| `timeout-moved-server-unchecked` | A foreground server that the harness moves to background at its 120 s timeout is not checked. | [`debts/timeout-moved-server-unchecked.md`](../debts/timeout-moved-server-unchecked.md) |
| `undo-scan-cr-nul-false-alarm` | The scan reads `git log -p` as text. | [`debts/undo-scan-cr-nul-false-alarm.md`](../debts/undo-scan-cr-nul-false-alarm.md) |
| `unknown-stash-word-tree-only` | An unknown stash word is read as a push, so the guard judges it on the working tree only. | [`debts/unknown-stash-word-tree-only.md`](../debts/unknown-stash-word-tree-only.md) |
| `until-note-unjudged` | The `background-end` rule accepts any non-empty `until:` text, such as `until: n/a`. | [`debts/until-note-unjudged.md`](../debts/until-note-unjudged.md) |

## Deferred

| Slug | Gist | Link |
|---|---|---|
| `banchi-build-steps` | Banchi build steps are not claimed by the shared stamp | [`deferred/banchi-build-steps.md`](../deferred/banchi-build-steps.md) |
| `bare-gh-merge-refusal` | A bare `gh pr merge` in a repo that uses `merge` | [`deferred/bare-gh-merge-refusal.md`](../deferred/bare-gh-merge-refusal.md) |
| `build-disk-guard` | Low-disk guard refuses builds below 20 GB | [`deferred/build-disk-guard.md`](../deferred/build-disk-guard.md) |
| `install-copies-from-main` | Install copies from main, not links into the clone | [`deferred/install-copies-from-main.md`](../deferred/install-copies-from-main.md) |
| `measured-time-table` | A measured-time table for machine steps | [`deferred/measured-time-table.md`](../deferred/measured-time-table.md) |
| `merge-retarget-before-merge` | A base change just before the merge command is not caught | [`deferred/merge-retarget-before-merge.md`](../deferred/merge-retarget-before-merge.md) |
| `push-head-mismatch-trap` | A push of HEAD to a branch of another name is not guarded yet | [`deferred/push-head-mismatch-trap.md`](../deferred/push-head-mismatch-trap.md) |
| `refusal-route-around-guard` | No guard stops an agent that routes around a refusal | [`deferred/refusal-route-around-guard.md`](../deferred/refusal-route-around-guard.md) |
| `rm-path-wrapper` | An rm wrapper on PATH, active only in Claude sessions | [`deferred/rm-path-wrapper.md`](../deferred/rm-path-wrapper.md) |
| `sharables-adopts-the-stamp` | claude-sharables adopts the stamp, not a claim-command setting | [`deferred/sharables-adopts-the-stamp.md`](../deferred/sharables-adopts-the-stamp.md) |
| `stamp-shallow-depth-two` | The stamp check does not read a shallow checkout | [`deferred/stamp-shallow-depth-two.md`](../deferred/stamp-shallow-depth-two.md) |
| `three-skill-findings` | Three skills have findings that wait | [`deferred/three-skill-findings.md`](../deferred/three-skill-findings.md) |
| `undo-check-rename-alarm` | The silent-undo check flags a rename that main edited | [`deferred/undo-check-rename-alarm.md`](../deferred/undo-check-rename-alarm.md) |
| `undo-trailer-hint` | The silent-undo refusal does not say where the trailer goes | [`deferred/undo-trailer-hint.md`](../deferred/undo-trailer-hint.md) |
| `verdict-cmd-untested` | The Windows launcher bin/verdict.cmd has no test | [`deferred/verdict-cmd-untested.md`](../deferred/verdict-cmd-untested.md) |

## Plans

| Slug | Gist | Link |
|---|---|---|
| `janitor-build-plan` | Build plan: the machine-wide janitor | [`plans/janitor-build-plan.md`](../plans/janitor-build-plan.md) |
| `shared-merge-tool` | Plan: the shared merge tool | [`plans/shared-merge-tool.md`](../plans/shared-merge-tool.md) |
