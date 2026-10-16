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
| `agent-end-reap-stops-what-a-finished-agent-left` | This record is step 2 of the plan in `which-start-shapes-outlive-the-agent-on-windows` (start shapes that outlive a subagent on Windows; PR #144). | [`decisions/agent-end-reap-stops-what-a-finished-agent-left.md`](../decisions/agent-end-reap-stops-what-a-finished-agent-left.md) |
| `ask-steps-run-alone` | Owner ruling, 2026-10-14. | [`decisions/ask-steps-run-alone.md`](../decisions/ask-steps-run-alone.md) |
| `background-needs-end-note` | Owner ruling, 2026-10-13 23:41 CDT: "End condition at start." | [`decisions/background-needs-end-note.md`](../decisions/background-needs-end-note.md) |
| `ci-unknown-is-red-and-dedup` | A lint that cannot read its input prints UNKNOWN. | [`decisions/ci-unknown-is-red-and-dedup.md`](../decisions/ci-unknown-is-red-and-dedup.md) |
| `debts-have-their-own-store` | Every known gap is a debt. | [`decisions/debts-have-their-own-store.md`](../decisions/debts-have-their-own-store.md) |
| `decision-watch-mod-limits` | Yes. | [`decisions/decision-watch-mod-limits.md`](../decisions/decision-watch-mod-limits.md) |
| `design-skills` | Owner ruling, 2026-10-10. | [`decisions/design-skills.md`](../decisions/design-skills.md) |
| `draft-until-reviewed` | Owner rulings, 2026-10-10 and 2026-10-13. | [`decisions/draft-until-reviewed.md`](../decisions/draft-until-reviewed.md) |
| `drops-lines-trailer-exempt` | Owner, 2026-10-12: the `Drops-lines: <record path> -- <reason>` trailer is the one place a record path is allowed in a commit message. | [`decisions/drops-lines-trailer-exempt.md`](../decisions/drops-lines-trailer-exempt.md) |
| `env-file-wrappers` | The `env-file` rule allows `--env-file` only when the command word is a runner (`ENV_LOADER_COMMANDS`). | [`decisions/env-file-wrappers.md`](../decisions/env-file-wrappers.md) |
| `gate-hooks-fail-closed` | Owner, 2026-10-12: a gate whose script or python is missing refuses the call. | [`decisions/gate-hooks-fail-closed.md`](../decisions/gate-hooks-fail-closed.md) |
| `guard-audit-high` | Which guard refusals are false alarms or gaps? | [`decisions/guard-audit-high.md`](../decisions/guard-audit-high.md) |
| `guard-command-position` | One resolver finds the command word for every rule. | [`decisions/guard-command-position.md`](../decisions/guard-command-position.md) |
| `guard-guards-mistakes-only` | Owner ruling, 2026-10-15 15:47 CDT. | [`decisions/guard-guards-mistakes-only.md`](../decisions/guard-guards-mistakes-only.md) |
| `guard-log-read-weekly` | `hooks/guard_core.py:record()` appends one line per verdict to `~/.claude/guard.log`. | [`decisions/guard-log-read-weekly.md`](../decisions/guard-log-read-weekly.md) |
| `haiku-prompt-hooks` | The owner ruled on 2026-10-07 which hooks may call a model. | [`decisions/haiku-prompt-hooks.md`](../decisions/haiku-prompt-hooks.md) |
| `hold-unsafe-after-round-3` | Owner ruling, 2026-10-15 12:00 CDT. | [`decisions/hold-unsafe-after-round-3.md`](../decisions/hold-unsafe-after-round-3.md) |
| `janitor-dirty-test-stays` | Owner word, 2026-10-13 15:56 CDT: option A. | [`decisions/janitor-dirty-test-stays.md`](../decisions/janitor-dirty-test-stays.md) |
| `lane-by-slug` | Owner, 2026-10-13 14:13 CDT, relayed by the oversight session: | [`decisions/lane-by-slug.md`](../decisions/lane-by-slug.md) |
| `list-form-subprocess-ignores-a-path-shim-on-windows` | Three suites drive a blind `git` stand-in through a directory placed first on `PATH`. | [`decisions/list-form-subprocess-ignores-a-path-shim-on-windows.md`](../decisions/list-form-subprocess-ignores-a-path-shim-on-windows.md) |
| `local-time-central` | Owner, 2026-10-12: US Central (America/Chicago), DST-aware, 24-hour clock. | [`decisions/local-time-central.md`](../decisions/local-time-central.md) |
| `merge-needs-a-proven-head` | Owner, 2026-10-12: "Fix both now, one lane." | [`decisions/merge-needs-a-proven-head.md`](../decisions/merge-needs-a-proven-head.md) |
| `mods-deferred-table` | Owner word, 2026-10-13 21:00 CDT: leave these as deferred recordings on the repo. | [`decisions/mods-deferred-table.md`](../decisions/mods-deferred-table.md) |
| `mods-install-via-marketplace` | The shared `settings.json` declares one marketplace, `claude-settings`. | [`decisions/mods-install-via-marketplace.md`](../decisions/mods-install-via-marketplace.md) |
| `mods-no-cli-key-headless` | No CLI API key for headless runs. | [`decisions/mods-no-cli-key-headless.md`](../decisions/mods-no-cli-key-headless.md) |
| `mods-tests-run-in-gates` | Merge session, 2026-10-13, 13:16 CDT. | [`decisions/mods-tests-run-in-gates.md`](../decisions/mods-tests-run-in-gates.md) |
| `mutant-cause-of-death` | CLAUDE.md says: "Trust a guard only once it goes red on the defect it guards." This entry is that sentence applied to the guard's own test harness. | [`decisions/mutant-cause-of-death.md`](../decisions/mutant-cause-of-death.md) |
| `mutation-harnesses-run-when-their-code-changes` | `.github/scripts/harness-scope.sh` reads `git diff --name-only` against the merge base and sets one output per harness. | [`decisions/mutation-harnesses-run-when-their-code-changes.md`](../decisions/mutation-harnesses-run-when-their-code-changes.md) |
| `one-context-bar` | Owner ruling, 2026-10-14. | [`decisions/one-context-bar.md`](../decisions/one-context-bar.md) |
| `opt-in-ci-templates-composite` | Owner approved six templates any repo can adopt. | [`decisions/opt-in-ci-templates-composite.md`](../decisions/opt-in-ci-templates-composite.md) |
| `purge-keeps-younger-restore-ref` | The purge drops a restore ref only when both hold: | [`decisions/purge-keeps-younger-restore-ref.md`](../decisions/purge-keeps-younger-restore-ref.md) |
| `question-judge-reads-rulings` | Owner ruling, 2026-10-12 22:10 CDT: the question judge reads the repo's decision and deferred records and refuses a question the owner already settled. | [`decisions/question-judge-reads-rulings.md`](../decisions/question-judge-reads-rulings.md) |
| `question-outcome-check` | Owner ruling, 2026-10-13 19:48 CDT: the standard question format is a `Goal:` line first, then a `Problem:` sentence, then the options. | [`decisions/question-outcome-check.md`](../decisions/question-outcome-check.md) |
| `review-cap-red-ci` | Owner ruling, 2026-10-13 14:50 CDT: "Split, then ask." | [`decisions/review-cap-red-ci.md`](../decisions/review-cap-red-ci.md) |
| `rulings-declare-kind` | Owner ruling, 2026-10-12. | [`decisions/rulings-declare-kind.md`](../decisions/rulings-declare-kind.md) |
| `silent-undo-check-design` | `lint/check_silent_undo.py` is the one home. | [`decisions/silent-undo-check-design.md`](../decisions/silent-undo-check-design.md) |
| `stall-watch` | A background command can stop making progress. | [`decisions/stall-watch.md`](../decisions/stall-watch.md) |
| `stall-watch-stop-check` | A background shell can stay open after a turn ends. | [`decisions/stall-watch-stop-check.md`](../decisions/stall-watch-stop-check.md) |
| `stamp-cite-near-miss` | Where does the check for a wrongly wrapped cite live, and how does an agent learn the right form? | [`decisions/stamp-cite-near-miss.md`](../decisions/stamp-cite-near-miss.md) |
| `stash-push-is-clone-wide` | CLAUDE.md says: "Set work aside with a commit on your own branch, never a stash." It also says: "A stash entry belongs to no branch. | [`decisions/stash-push-is-clone-wide.md`](../decisions/stash-push-is-clone-wide.md) |
| `ste-gate-fixes-not-nags` | The gate fixes first. | [`decisions/ste-gate-fixes-not-nags.md`](../decisions/ste-gate-fixes-not-nags.md) |
| `subagent-model-cap` | CLAUDE.md says: "Once ready, turn each rule below into a hook or check." This entry records how the worker-model rule is mechanized after `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` is dropped. | [`decisions/subagent-model-cap.md`](../decisions/subagent-model-cap.md) |
| `test-strategy-reset` | Owner ruling, 2026-10-14 17:14 CDT. | [`decisions/test-strategy-reset.md`](../decisions/test-strategy-reset.md) |
| `unattended-sweep-stops-proven-orphans` | PR #132 added an orphaned-listener check to `janitor/sweep.py`. | [`decisions/unattended-sweep-stops-proven-orphans.md`](../decisions/unattended-sweep-stops-proven-orphans.md) |
| `wsl-allow-list` | Owner ruling, 2026-10-13 15:20: "fixed test list is fine; surf the web for a consensus first". | [`decisions/wsl-allow-list.md`](../decisions/wsl-allow-list.md) |

## Build designs

| Slug | Gist | Link |
|---|---|---|
| `agents-get-standing-rules` | Owner, 2026-10-12: a SubagentStart hook injects them. | [`decisions/agents-get-standing-rules.md`](../decisions/agents-get-standing-rules.md) |
| `git-env-set-denied` | No. | [`decisions/git-env-set-denied.md`](../decisions/git-env-set-denied.md) |
| `guard-split-by-family` | Owner, 2026-10-12 and 2026-10-13: | [`decisions/guard-split-by-family.md`](../decisions/guard-split-by-family.md) |
| `handoff-hooks-wave-2` | Owner ruling, 2026-10-13 11:20 CDT: build all three in claude-settings. | [`decisions/handoff-hooks-wave-2.md`](../decisions/handoff-hooks-wave-2.md) |
| `install-hooks-whole` | The installer writes each file to a temp name in the same folder, then renames it over the target. | [`decisions/install-hooks-whole.md`](../decisions/install-hooks-whole.md) |
| `liveness-read-is-platform-specific-and-unreadable-is-not-death` | `hooks/guard.py`'s liveness oracle (`_process_start_ms`, `session_is_live`, `worktree_live_session`) folded two different facts into one answer. | [`decisions/liveness-read-is-platform-specific-and-unreadable-is-not-death.md`](../decisions/liveness-read-is-platform-specific-and-unreadable-is-not-death.md) |
| `merge-net-retry` | Owner, 2026-10-13, about 16:25 CDT: "Retry 3 times." | [`decisions/merge-net-retry.md`](../decisions/merge-net-retry.md) |
| `merge-notice-checks-the-report` | CLAUDE.md: "A guard that goes red when nothing is wrong is spent, because the reader learns to scroll past it." And: trust a guard only once it goes red on the defect it guards. | [`decisions/merge-notice-checks-the-report.md`](../decisions/merge-notice-checks-the-report.md) |
| `owner-feedback-inbox` | Owner ruling, 2026-10-13, from an interview in the claude-settings audit session. | [`decisions/owner-feedback-inbox.md`](../decisions/owner-feedback-inbox.md) |
| `plain-diff-mod-limits` | The mod sends a diff to `$.model.complete` only for a file that passes the secret filter. | [`decisions/plain-diff-mod-limits.md`](../decisions/plain-diff-mod-limits.md) |
| `prune-cases-skip-without-symlink-privilege` | Prune cases skip when this account cannot make a real symlink | [`decisions/prune-cases-skip-without-symlink-privilege.md`](../decisions/prune-cases-skip-without-symlink-privilege.md) |
| `records-index-at-merge` | Owner ruling, 2026-10-14 10:59 and 13:18 CDT. | [`decisions/records-index-at-merge.md`](../decisions/records-index-at-merge.md) |
| `session-board-mod-limits` | Owner intent: stop typing "status?" into many sessions. | [`decisions/session-board-mod-limits.md`](../decisions/session-board-mod-limits.md) |
| `split-segments-comment-rule` | `hooks/guard.py:split_segments` tracked single and double quotes. | [`decisions/split-segments-comment-rule.md`](../decisions/split-segments-comment-rule.md) |
| `stash-stack-is-a-shared-subject` | CLAUDE.md says: "Never run `git stash` ... | [`decisions/stash-stack-is-a-shared-subject.md`](../decisions/stash-stack-is-a-shared-subject.md) |
| `sweep-shuts-down-idle-simulators` | Owner rulings, 2026-10-10. | [`decisions/sweep-shuts-down-idle-simulators.md`](../decisions/sweep-shuts-down-idle-simulators.md) |

## Unsorted decisions

| Slug | Gist | Link |
|---|---|---|
| `a-branch-is-redundant-by-patch-not-by-ancestry` | The sweep in `plans/janitor-build-plan.md` keeps or reaps a local branch. | [`decisions/a-branch-is-redundant-by-patch-not-by-ancestry.md`](../decisions/a-branch-is-redundant-by-patch-not-by-ancestry.md) |
| `a-gates-allow-list-is-the-constant` | CLAUDE.md now names this rule: a gate's allow list must point at the constant the code emits, never a copy of it. | [`decisions/a-gates-allow-list-is-the-constant.md`](../decisions/a-gates-allow-list-is-the-constant.md) |
| `a-kill-by-pid-needs-an-owned-pid` | CLAUDE.md says: "Never kill a process you did not start." The guard denied a kill by name or by pattern. | [`decisions/a-kill-by-pid-needs-an-owned-pid.md`](../decisions/a-kill-by-pid-needs-an-owned-pid.md) |
| `a-rule-with-no-gate-leaves-claude-md` | On 2026-09-28 the owner ruled that the semicolon line leaves `CLAUDE.md`. | [`decisions/a-rule-with-no-gate-leaves-claude-md.md`](../decisions/a-rule-with-no-gate-leaves-claude-md.md) |
| `a-test-fixture-name-can-overflow-windows-path-length` | A fixture name built from a test's own description can overflow Windows path length | [`decisions/a-test-fixture-name-can-overflow-windows-path-length.md`](../decisions/a-test-fixture-name-can-overflow-windows-path-length.md) |
| `adoptions-declined-2026-09-28` | A review of public Claude Code configs and native features proposed these. | [`decisions/adoptions-declined-2026-09-28.md`](../decisions/adoptions-declined-2026-09-28.md) |
| `agent-worktree-discard-is-noted` | The shared-tree rule asks the owner before a discarding git command runs. | [`decisions/agent-worktree-discard-is-noted.md`](../decisions/agent-worktree-discard-is-noted.md) |
| `agents-wait-with-monitor` | Which way may an agent wait for a condition? | [`decisions/agents-wait-with-monitor.md`](../decisions/agents-wait-with-monitor.md) |
| `an-agent-outside-its-home-tree-must-stop` | An agent outside its home tree must stop | [`decisions/an-agent-outside-its-home-tree-must-stop.md`](../decisions/an-agent-outside-its-home-tree-must-stop.md) |
| `bare-bash-on-windows-can-resolve-to-the-wsl-stub` | `hooks/test_config_watch.py`'s bypass cases handed `subprocess.run(["bash", "-c", command], ...)` a bare command name. | [`decisions/bare-bash-on-windows-can-resolve-to-the-wsl-stub.md`](../decisions/bare-bash-on-windows-can-resolve-to-the-wsl-stub.md) |
| `bash-path-breaks-only-when-the-snapshot-breaks` | The Bash tool's PATH breaks only when its shell snapshot breaks | [`decisions/bash-path-breaks-only-when-the-snapshot-breaks.md`](../decisions/bash-path-breaks-only-when-the-snapshot-breaks.md) |
| `branch-delete-wrong-cause-was-a-filename-collision` | `decisions/branch-delete-wrong-cause-on-windows-unexplained.md` named a real defect and said its cause stayed unexplained. | [`decisions/branch-delete-wrong-cause-was-a-filename-collision.md`](../decisions/branch-delete-wrong-cause-was-a-filename-collision.md) |
| `browser-prompts-are-the-apps` | Owner, 2026-10-11: no. | [`decisions/browser-prompts-are-the-apps.md`](../decisions/browser-prompts-are-the-apps.md) |
| `build-dirs-reaped-at-agent-end` | Owner ruling, 2026-10-11, labeled "Agent-end hook + low-disk guard". | [`decisions/build-dirs-reaped-at-agent-end.md`](../decisions/build-dirs-reaped-at-agent-end.md) |
| `builders-cannot-edit-tests` | Builders cannot edit tests | [`decisions/builders-cannot-edit-tests.md`](../decisions/builders-cannot-edit-tests.md) |
| `ci-spend-rules` | Skill steps 1 and 11 to 14 hold these rules. | [`decisions/ci-spend-rules.md`](../decisions/ci-spend-rules.md) |
| `ci-wall-time-cuts` | The owner chose cuts A to D on 2026-10-07. | [`decisions/ci-wall-time-cuts.md`](../decisions/ci-wall-time-cuts.md) |
| `copy-mode-overwrites-no-backup` | Owner, 2026-10-03: in copy mode, an installer overwrites its own old copy. | [`decisions/copy-mode-overwrites-no-backup.md`](../decisions/copy-mode-overwrites-no-backup.md) |
| `default-discover-roots-needed-normpath-on-windows` | `default_discover_roots()` needed `normpath`, and its test needed `USERPROFILE` | [`decisions/default-discover-roots-needed-normpath-on-windows.md`](../decisions/default-discover-roots-needed-normpath-on-windows.md) |
| `docs-only-prs-skip-code-suites` | `hooks/test_install_src.sh` takes case names as arguments and runs only those. | [`decisions/docs-only-prs-skip-code-suites.md`](../decisions/docs-only-prs-skip-code-suites.md) |
| `docs-only-prs-skip-review` | Docs-only pull requests skip the reviewer | [`decisions/docs-only-prs-skip-review.md`](../decisions/docs-only-prs-skip-review.md) |
| `every-lint-rule-blocks-or-does-not-exist` | CLAUDE.md says: "Judge every rule, check, and design by the outcome for the person the software serves." `lint/ste_lint.py` held 19 rules. | [`decisions/every-lint-rule-blocks-or-does-not-exist.md`](../decisions/every-lint-rule-blocks-or-does-not-exist.md) |
| `fewest-words-mandate` | On 2026-09-28 the owner asked for a verbiage mandate. | [`decisions/fewest-words-mandate.md`](../decisions/fewest-words-mandate.md) |
| `frozen-path-resolves-shell-vars` | Rule 7 resolves shell variables before it matches a write target | [`decisions/frozen-path-resolves-shell-vars.md`](../decisions/frozen-path-resolves-shell-vars.md) |
| `guard-that-cries-wolf-is-spent` | CLAUDE.md says: "Trust a guard only once it goes red on the defect it guards." This entry records the missing half, and the two false alarms that made the half worth writing down. | [`decisions/guard-that-cries-wolf-is-spent.md`](../decisions/guard-that-cries-wolf-is-spent.md) |
| `guard-trims-from-the-audit` | The owner approved these trims from an audit of `~/.claude/guard.log`: 2,713 lines, 2026-09-16 to 2026-10-02. | [`decisions/guard-trims-from-the-audit.md`](../decisions/guard-trims-from-the-audit.md) |
| `hooks-share-the-transcript-reader` | Four hooks each carried their own copy of the same transcript readers. | [`decisions/hooks-share-the-transcript-reader.md`](../decisions/hooks-share-the-transcript-reader.md) |
| `known-bad-input-proves-the-gate` | A `gate` row cites a `test` id (`path::name`, `path::Class.name`) or a `setting` value. | [`decisions/known-bad-input-proves-the-gate.md`](../decisions/known-bad-input-proves-the-gate.md) |
| `main-branch-protection` | main branch protection | [`decisions/main-branch-protection.md`](../decisions/main-branch-protection.md) |
| `memory-is-never-a-rulings-only-home` | The owner's rulings must reach a tracked file. | [`decisions/memory-is-never-a-rulings-only-home.md`](../decisions/memory-is-never-a-rulings-only-home.md) |
| `merge-config-defaults` | Must a repo have `.github/stamp.json` before the merge tool works in it? | [`decisions/merge-config-defaults.md`](../decisions/merge-config-defaults.md) |
| `merge-reinstalls-from-main` | `install.sh` links the shipped skills, hooks and tools into `~/.claude`. | [`decisions/merge-reinstalls-from-main.md`](../decisions/merge-reinstalls-from-main.md) |
| `one-entry-per-question` | On 2026-09-29 the owner ruled that a decision entry answers one question, and a changed ruling rewrites that entry. | [`decisions/one-entry-per-question.md`](../decisions/one-entry-per-question.md) |
| `one-shared-record-stamp` | **Changed in part on 2026-09-28** by `record-stamp-stays-generic`, the stamp stays generic. | [`decisions/one-shared-record-stamp.md`](../decisions/one-shared-record-stamp.md) |
| `playwright-browsers-path` | No. | [`decisions/playwright-browsers-path.md`](../decisions/playwright-browsers-path.md) |
| `playwright-install-once` | Owner, 2026-10-11 (rule `playwright-install` in `hooks/guard.py`): | [`decisions/playwright-install-once.md`](../decisions/playwright-install-once.md) |
| `precompact-handoff` | Auto-compact drops detail. | [`decisions/precompact-handoff.md`](../decisions/precompact-handoff.md) |
| `predicate-is-the-act` | CLAUDE.md says: "Fix the cause, not the symptom." It also says: "Check whether the primitive exists before building a workaround." This entry records why the markdown sweep stopped reading command text, and what that rule means for the next gate. | [`decisions/predicate-is-the-act.md`](../decisions/predicate-is-the-act.md) |
| `record-stamp-stays-generic` | On 2026-09-28 the owner said: "I think moreso you need to remain generic and provide me briefs that allow each of the repos to individually get compliant, rather than carving out exceptions for each repo." | [`decisions/record-stamp-stays-generic.md`](../decisions/record-stamp-stays-generic.md) |
| `recovery-must-not-gate-on-its-own-state` | CLAUDE.md's Verification paragraph now states this rule. | [`decisions/recovery-must-not-gate-on-its-own-state.md`](../decisions/recovery-must-not-gate-on-its-own-state.md) |
| `repeal-the-no-prefix-report-rule` | CLAUDE.md's Reports paragraph said: | [`decisions/repeal-the-no-prefix-report-rule.md`](../decisions/repeal-the-no-prefix-report-rule.md) |
| `retired-numbers-list` | A record may be deleted when its number is named in the kind's `RETIRED` file, in the same tree. | [`decisions/retired-numbers-list.md`](../decisions/retired-numbers-list.md) |
| `reuse-needs-checkout-proof` | Lanes run in separate worktrees of one clone. | [`decisions/reuse-needs-checkout-proof.md`](../decisions/reuse-needs-checkout-proof.md) |
| `rm-on-a-variable-needs-a-guard` | Owner, 2026-10-11 ("Ship guard now, hook later"): | [`decisions/rm-on-a-variable-needs-a-guard.md`](../decisions/rm-on-a-variable-needs-a-guard.md) |
| `schtasks-xml-requires-utf16` | schtasks /create /xml requires UTF-16, not UTF-8 | [`decisions/schtasks-xml-requires-utf16.md`](../decisions/schtasks-xml-requires-utf16.md) |
| `semicolon-and-gendered-pronoun-rules-leave-the-gate` | The owner ruled in chat on 2026-09-23. | [`decisions/semicolon-and-gendered-pronoun-rules-leave-the-gate.md`](../decisions/semicolon-and-gendered-pronoun-rules-leave-the-gate.md) |
| `session-end-sweep-is-disarmed-until-liveness-is-proven` | The `SessionEnd` hook in `settings.json` runs `janitor/session_end_sweep.py`. | [`decisions/session-end-sweep-is-disarmed-until-liveness-is-proven.md`](../decisions/session-end-sweep-is-disarmed-until-liveness-is-proven.md) |
| `source-prose-lint-ships-dark` | CLAUDE.md says: "A guard that goes red when nothing is wrong is spent, because the reader learns to scroll past it." This entry names why `ste_lint.py`'s new comment-and-docstring mode stays off by default. | [`decisions/source-prose-lint-ships-dark.md`](../decisions/source-prose-lint-ships-dark.md) |
| `stale-safe-force-push` | CLAUDE.md says: "Judge every rule, check, and design by the outcome for the person the software serves." The outcome here: the owner gets no prompt for a safe push, and no push overwrites newer remote work with a stale copy. | [`decisions/stale-safe-force-push.md`](../decisions/stale-safe-force-push.md) |
| `standing-merge-grant` | Owner ruling, 2026-10-10: the orchestrating session has standing merge authority in claude-settings. | [`decisions/standing-merge-grant.md`](../decisions/standing-merge-grant.md) |
| `ste-lint-gloss-collapse` | `lint/ste_lint.py`'s `STE001` counts words per sentence. | [`decisions/ste-lint-gloss-collapse.md`](../decisions/ste-lint-gloss-collapse.md) |
| `stop-guardrail-became-a-command-hook` | The `type: agent` Stop hook in `settings.json` judged every turn for a silent change to a decision, gate, build-order, CLAUDE.md rule, or setting. | [`decisions/stop-guardrail-became-a-command-hook.md`](../decisions/stop-guardrail-became-a-command-hook.md) |
| `tests-are-claims-not-law` | Tests are claims, not law | [`decisions/tests-are-claims-not-law.md`](../decisions/tests-are-claims-not-law.md) |
| `the-janitor-is-one-machine-wide-sweep` | The sweep deletes a local branch when that branch holds no unique work. | [`decisions/the-janitor-is-one-machine-wide-sweep.md`](../decisions/the-janitor-is-one-machine-wide-sweep.md) |
| `the-orchestrator-builds-by-verdict-not-by-line-count` | Supersedes README Decision 13, "the orchestrator and product code: judge the act, not the file". | [`decisions/the-orchestrator-builds-by-verdict-not-by-line-count.md`](../decisions/the-orchestrator-builds-by-verdict-not-by-line-count.md) |
| `the-stop-guardrail-is-disarmed-until-the-command-hook-lands` | The `Stop` hook entry of `type: "agent"` is removed from `settings.json`. | [`decisions/the-stop-guardrail-is-disarmed-until-the-command-hook-lands.md`](../decisions/the-stop-guardrail-is-disarmed-until-the-command-hook-lands.md) |
| `ux-house-rules` | Owner ruling, 2026-10-11: "build a ux folder". | [`decisions/ux-house-rules.md`](../decisions/ux-house-rules.md) |
| `verdict-reads-runner-markers` | Owner, 2026-10-11 ("start the verdict lane"): | [`decisions/verdict-reads-runner-markers.md`](../decisions/verdict-reads-runner-markers.md) |
| `which-start-shapes-outlive-the-agent-on-windows` | This entry is step 1 of a plan. | [`decisions/which-start-shapes-outlive-the-agent-on-windows.md`](../decisions/which-start-shapes-outlive-the-agent-on-windows.md) |
| `worktree-setup-is-per-repo` | Owner, 2026-10-10: no. | [`decisions/worktree-setup-is-per-repo.md`](../decisions/worktree-setup-is-per-repo.md) |

## Debts

| Slug | Gist | Link |
|---|---|---|
| `agent-brief-crash-silent` | On an internal error the hook prints no context and writes one `agent_brief:` line to stderr. | [`debts/agent-brief-crash-silent.md`](../debts/agent-brief-crash-silent.md) |
| `agent-brief-no-matcher` | The SubagentStart hook has no matcher, so every agent type gets the standing rules. | [`debts/agent-brief-no-matcher.md`](../debts/agent-brief-no-matcher.md) |
| `agent-brief-text-copy-drifts` | The SubagentStart hook's rule text is a copy of the rules in CLAUDE.md and `agents/*.md`. | [`debts/agent-brief-text-copy-drifts.md`](../debts/agent-brief-text-copy-drifts.md) |
| `agent-plan-scope-line-general` | Plan and claude-code-guide get the general scope line, which names only reviewer and Explore as never-edit. | [`debts/agent-plan-scope-line-general.md`](../debts/agent-plan-scope-line-general.md) |
| `agent-type-match-case-sensitive` | `Builder` or `explore` gets the general writer scope, not the scope of its role. | [`debts/agent-type-match-case-sensitive.md`](../debts/agent-type-match-case-sensitive.md) |
| `alias-skip-misses-case-forms` | The alias skip matches `/WindowsApps/` in the POSIX path Git Bash prints. | [`debts/alias-skip-misses-case-forms.md`](../debts/alias-skip-misses-case-forms.md) |
| `ansi-c-escape-not-decoded` | Lane cap-ask-hole decodes a plain `$'path'` word for the frozen and model-cap checks. | [`debts/ansi-c-escape-not-decoded.md`](../debts/ansi-c-escape-not-decoded.md) |
| `ask-step-hidden-in-script` | The guard does not see a settings write of the subagent model cap in some shapes. | [`debts/ask-step-hidden-in-script.md`](../debts/ask-step-hidden-in-script.md) |
| `bg-end-false-alarms` | The rule splits script names on `:` and `-`, so `build:dev` and `test-watch-ci` read as servers. | [`debts/bg-end-false-alarms.md`](../debts/bg-end-false-alarms.md) |
| `bg-end-roster-gaps` | The roster is a closed list. | [`debts/bg-end-roster-gaps.md`](../debts/bg-end-roster-gaps.md) |
| `blind-git-fixtures-unaudited` | The entry does not audit every blind-command fixture in the repository for the PATH shim gap. | [`debts/blind-git-fixtures-unaudited.md`](../debts/blind-git-fixtures-unaudited.md) |
| `cap-basename-false-alarm` | A heredoc that writes a fixture named like a settings file (`fixtures/settings.json`) with the cap key asks, though no real settings file changes. | [`debts/cap-basename-false-alarm.md`](../debts/cap-basename-false-alarm.md) |
| `cap-write-by-python-unseen` | A Python command that writes `CLAUDE_CODE_SUBAGENT_MODEL` into a settings file is allowed with no ask. | [`debts/cap-write-by-python-unseen.md`](../debts/cap-write-by-python-unseen.md) |
| `catalog-mode-detect-flags` | The catalog finds a script's modes only from a `"$g" --flag` argument. | [`debts/catalog-mode-detect-flags.md`](../debts/catalog-mode-detect-flags.md) |
| `catalog-root-needs-skills-dir` | `skill_names` lists `skills/` with no check that the folder exists. | [`debts/catalog-root-needs-skills-dir.md`](../debts/catalog-root-needs-skills-dir.md) |
| `cite-by-id-skips-merge-subject` | The cite-by-id rule does not read a `gh pr merge` subject. | [`debts/cite-by-id-skips-merge-subject.md`](../debts/cite-by-id-skips-merge-subject.md) |
| `debt-decision-link-unchecked` | No check confirms that a debt's decision still names its gap. | [`debts/debt-decision-link-unchecked.md`](../debts/debt-decision-link-unchecked.md) |
| `debts-no-check-reads-parts` | No check reads the four parts of a debt file. | [`debts/debts-no-check-reads-parts.md`](../debts/debts-no-check-reads-parts.md) |
| `drops-cite-forms-unchecked` | `git commit --trailer`, a `Refs:deferred/a.md` token with no space, `git merge -m` and `git tag -m` are never cite-checked. | [`debts/drops-cite-forms-unchecked.md`](../debts/drops-cite-forms-unchecked.md) |
| `drops-dot-slash-guard-lint` | `./deferred/a.md` after the `Drops-lines:` key passes the guard. | [`debts/drops-dot-slash-guard-lint.md`](../debts/drops-dot-slash-guard-lint.md) |
| `drops-mixed-paragraph-exempt` | The guard exempts a last paragraph that mixes a prose line with the Drops-lines trailer. | [`debts/drops-mixed-paragraph-exempt.md`](../debts/drops-mixed-paragraph-exempt.md) |
| `drops-reads-msg-unlike-git` | Three round-3 false refusals. | [`debts/drops-reads-msg-unlike-git.md`](../debts/drops-reads-msg-unlike-git.md) |
| `drops-stdin-message-unread` | A message from `-F -` stdin is never read, so a prose cite there passes. | [`debts/drops-stdin-message-unread.md`](../debts/drops-stdin-message-unread.md) |
| `drops-whole-token-no-mutant` | No mutant removes the whole-token match. | [`debts/drops-whole-token-no-mutant.md`](../debts/drops-whole-token-no-mutant.md) |
| `dw-bare-stop-row-blind` | Case M5c was cut. | [`debts/dw-bare-stop-row-blind.md`](../debts/dw-bare-stop-row-blind.md) |
| `dw-busy-stop-skipped` | A Stop that lands while a judge runs is skipped (`SKIP busy`). | [`debts/dw-busy-stop-skipped.md`](../debts/dw-busy-stop-skipped.md) |
| `dw-ffff-regex-literal` | The `asciiJson` regex holds a literal U+FFFF character. | [`debts/dw-ffff-regex-literal.md`](../debts/dw-ffff-regex-literal.md) |
| `dw-log-keeps-model-text` | The log keeps the FLAG `why` up to 2000 characters. | [`debts/dw-log-keeps-model-text.md`](../debts/dw-log-keeps-model-text.md) |
| `dw-log-write-failures-silent` | The log is the only output for an ALLOW. | [`debts/dw-log-write-failures-silent.md`](../debts/dw-log-write-failures-silent.md) |
| `dw-notice-lead-space-lost` | The mod's log folds whitespace, so whitespace at the very start of a notice is lost in the log. | [`debts/dw-notice-lead-space-lost.md`](../debts/dw-notice-lead-space-lost.md) |
| `dw-slash-cache-hit-reads-clean` | On a cache hit `/dw` prints `nothing to say (no protected change, no model call)`, so a second `/dw` after a FLAG reads like a clean turn. | [`debts/dw-slash-cache-hit-reads-clean.md`](../debts/dw-slash-cache-hit-reads-clean.md) |
| `dw-slot-timers-unmeasured` | Each step that holds the slot has a mod timer: each python finder 6 s (two per run), each python run 31 s (a 30 s host limit, unmeasured against a real run), the model call 50 s, each toast 5 s (a verdict and up to three notices), each log write 2 s (up to six). | [`debts/dw-slot-timers-unmeasured.md`](../debts/dw-slot-timers-unmeasured.md) |
| `dw-stop-row-unproven` | The Stop row is removed. | [`debts/dw-stop-row-unproven.md`](../debts/dw-stop-row-unproven.md) |
| `dw-text-of-drops-reason` | `textOf` drops `r.reason`, so an aborted call reads `no text`. | [`debts/dw-text-of-drops-reason.md`](../debts/dw-text-of-drops-reason.md) |
| `dw-where-exe-both-phases` | `pickPython` runs `where.exe` in both phases. | [`debts/dw-where-exe-both-phases.md`](../debts/dw-where-exe-both-phases.md) |
| `env-file-rule-false-alarms` | `ag -f` and `ack -f` refuse now, though `-f` is a boolean in those tools. | [`debts/env-file-rule-false-alarms.md`](../debts/env-file-rule-false-alarms.md) |
| `env-flat-crash-allows` | A runtime crash in `_env_flat` allows the call. | [`debts/env-flat-crash-allows.md`](../debts/env-flat-crash-allows.md) |
| `env-grep-long-abbrev-unpinned` | `grep --regex=` style abbreviations of `--regexp`, `--expression` and `--source` are a hole. | [`debts/env-grep-long-abbrev-unpinned.md`](../debts/env-grep-long-abbrev-unpinned.md) |
| `env-node-env-file-prints` | `node --env-file=.env -e 'console.log(process.env)'` prints the file through the runner. | [`debts/env-node-env-file-prints.md`](../debts/env-node-env-file-prints.md) |
| `env-split-string-wsl-only` | `env -S 'cmd'` runs `cmd`. | [`debts/env-split-string-wsl-only.md`](../debts/env-split-string-wsl-only.md) |
| `fb-done-forms-unpinned` | The tests check only a plain last line `fb done`. | [`debts/fb-done-forms-unpinned.md`](../debts/fb-done-forms-unpinned.md) |
| `fb-done-unclosed-fence` | The close rule reads only the last line of a message. | [`debts/fb-done-unclosed-fence.md`](../debts/fb-done-unclosed-fence.md) |
| `fb-inbox-append-race` | On Windows, two processes that append with `open(..., "ab")` at the same time lost 406 of 8000 lines in a stress test. | [`debts/fb-inbox-append-race.md`](../debts/fb-inbox-append-race.md) |
| `fb-judge-marker-race` | The judge child checks that its message is still the last one, then removes the capture marker. | [`debts/fb-judge-marker-race.md`](../debts/fb-judge-marker-race.md) |
| `frozen-path-ansi-c-quote` | Main allows `echo ok > $'<frozen path>'` at top level, and inside `bash -c`, `sh -c` and `eval`. | [`debts/frozen-path-ansi-c-quote.md`](../debts/frozen-path-ansi-c-quote.md) |
| `gate-exit-7-unprobed` | With `onFailure: block`, a timeout refused the call (measured in the 2026-10-12 incident). | [`debts/gate-exit-7-unprobed.md`](../debts/gate-exit-7-unprobed.md) |
| `gate-own-errors-fail-open` | Errors a gate catches itself fail open. | [`debts/gate-own-errors-fail-open.md`](../debts/gate-own-errors-fail-open.md) |
| `gate-remedy-needs-bash` | The remedy names `sh install.sh`. | [`debts/gate-remedy-needs-bash.md`](../debts/gate-remedy-needs-bash.md) |
| `git-env-glued-block` | If a glued PowerShell block opener is followed by a group, the guard does not read the group. | [`debts/git-env-glued-block.md`](../debts/git-env-glued-block.md) |
| `git-env-lower-case-fold` | Lower-case names fold to the rule, so `git_dir=x cmd` is denied too. | [`debts/git-env-lower-case-fold.md`](../debts/git-env-lower-case-fold.md) |
| `git-env-set-false-alarms` | False alarms on the safe side. | [`debts/git-env-set-false-alarms.md`](../debts/git-env-set-false-alarms.md) |
| `git-env-set-indirect-forms` | The guard reads literal set forms only. | [`debts/git-env-set-indirect-forms.md`](../debts/git-env-set-indirect-forms.md) |
| `git-env-set-untested-forms` | No case pins the PowerShell backtick escape, the shared group-opener pattern, or quote text in a heredoc body. | [`debts/git-env-set-untested-forms.md`](../debts/git-env-set-untested-forms.md) |
| `git-env-warn-session-start` | The warning runs at session start only, so damage done mid-session shows at the next start. | [`debts/git-env-warn-session-start.md`](../debts/git-env-warn-session-start.md) |
| `guard-abtests-test-path` | The test-path rule reads `native/ABTests/` as a test folder, so a builder cannot edit product code there. | [`debts/guard-abtests-test-path.md`](../debts/guard-abtests-test-path.md) |
| `guard-audit-subagent-stop-open` | On SubagentStop, a missing guard module still fails open, and one log line records it. | [`debts/guard-audit-subagent-stop-open.md`](../debts/guard-audit-subagent-stop-open.md) |
| `guard-bash-c-silent-write` | A silent git write inside `bash -c '...'` is allowed. | [`debts/guard-bash-c-silent-write.md`](../debts/guard-bash-c-silent-write.md) |
| `guard-cd-walk-extra-reading` | When a command ends inside an open quote, the guard also judges a second reading. | [`debts/guard-cd-walk-extra-reading.md`](../debts/guard-cd-walk-extra-reading.md) |
| `guard-env-read-grep` | The guard's env rule allows the Read and Grep tools on an environment file. | [`debts/guard-env-read-grep.md`](../debts/guard-env-read-grep.md) |
| `guard-first-c-reads-wrong-tree` | The discard rule judges each git call in its own checkout. | [`debts/guard-first-c-reads-wrong-tree.md`](../debts/guard-first-c-reads-wrong-tree.md) |
| `guard-glob-three-tools` | `lint/rule_audit.py`, `lint/check_landed_dirs.py` and `hooks/mutate_shared.py` each glob `hooks/guard*.py`. | [`debts/guard-glob-three-tools.md`](../debts/guard-glob-three-tools.md) |
| `guard-heredoc-os-system` | `python - <<EOF` with a body that calls `os.system("git stash")` is allowed. | [`debts/guard-heredoc-os-system.md`](../debts/guard-heredoc-os-system.md) |
| `guard-home-delete-literal` | `rm -rf /home/x` and `rd /s /q C:\Users\x` are allowed. | [`debts/guard-home-delete-literal.md`](../debts/guard-home-delete-literal.md) |
| `guard-interp-heredoc-lone-quote` | If an interpreter heredoc body such as `python3 - <<'PY'` holds a lone `'`, the guard reads the rest of the command as quoted. | [`debts/guard-interp-heredoc-lone-quote.md`](../debts/guard-interp-heredoc-lone-quote.md) |
| `guard-log-extra-ci` | An edit to `lint/guard_log_report.py` selects `gates_windows_merge` and the `guard` suite, as well as `code`. | [`debts/guard-log-extra-ci.md`](../debts/guard-log-extra-ci.md) |
| `guard-log-install-skew` | A new `hooks/guard_core.py` writes six fields. | [`debts/guard-log-install-skew.md`](../debts/guard-log-install-skew.md) |
| `guard-log-lines-lost` | A plain append from many processes is not atomic on Windows. | [`debts/guard-log-lines-lost.md`](../debts/guard-log-lines-lost.md) |
| `guard-log-off-silent` | A missing `hooks/guard_core.py`, or an older one without `set_log_session`, disables STE logging. | [`debts/guard-log-off-silent.md`](../debts/guard-log-off-silent.md) |
| `guard-log-one-reader-gaps` | `OneReaderTests` flags only a literal `.split("\t")` call in `hooks/*.py` and `lint/*.py` files that name guard.log. | [`debts/guard-log-one-reader-gaps.md`](../debts/guard-log-one-reader-gaps.md) |
| `guard-log-session-id-fence` | A `\|` in a session id splits its cell in the `--by-session` table. | [`debts/guard-log-session-id-fence.md`](../debts/guard-log-session-id-fence.md) |
| `guard-log-tool-field-tab` | The reader reads `session` as field 6, and `matched` as field 5 plus the later fields. | [`debts/guard-log-tool-field-tab.md`](../debts/guard-log-tool-field-tab.md) |
| `guard-lone-quote-overdeny` | Commit-message rules read heredoc bodies by both readings. | [`debts/guard-lone-quote-overdeny.md`](../debts/guard-lone-quote-overdeny.md) |
| `guard-msg-blank-segment-split` | The guard blanks the message value of a commit or a pull request, so prose that names a shell reads as text. | [`debts/guard-msg-blank-segment-split.md`](../debts/guard-msg-blank-segment-split.md) |
| `guard-redirect-paren-heredoc` | These hide a refused command, and main allows them too: a leading redirect before the command word (`2>/dev/null pkill foo`), and `)#` that opens no comment. | [`debts/guard-redirect-paren-heredoc.md`](../debts/guard-redirect-paren-heredoc.md) |
| `guard-shell-wrap-discard-unread` | A discard inside `sh -c`, `eval`, or a `$(…)` substitution is not read. | [`debts/guard-shell-wrap-discard-unread.md`](../debts/guard-shell-wrap-discard-unread.md) |
| `guard-split-heredocs-here-string` | `guard_core._split_heredocs` reads a quoted or commented `<<X`, or a here-string `<<<word`, as a real heredoc. | [`debts/guard-split-heredocs-here-string.md`](../debts/guard-split-heredocs-here-string.md) |
| `guard-split-ignores-backslash` | The segment split ignores backslash escapes, so `echo '; pkill foo; echo 'x'` hides `pkill`. | [`debts/guard-split-ignores-backslash.md`](../debts/guard-split-ignores-backslash.md) |
| `guard-split-mutant-needs-git` | PR0 measured a kill count of 310 of 314 on the branch, against 309 on main. | [`debts/guard-split-mutant-needs-git.md`](../debts/guard-split-mutant-needs-git.md) |
| `guard-split-sibling-mutant-case` | PR2 needs a case that kills a sibling mutant through the in-process load in `hooks/test_guard.py`. | [`debts/guard-split-sibling-mutant-case.md`](../debts/guard-split-sibling-mutant-case.md) |
| `guard-substitution-in-token` | A command inside a token is not read as a command: `$(...)` glued after other text, backticks, and `x=$(...)`. | [`debts/guard-substitution-in-token.md`](../debts/guard-substitution-in-token.md) |
| `guard-timeout-fails-open` | If the PreToolUse guard times out or crashes, Claude Code lets the call run. | [`debts/guard-timeout-fails-open.md`](../debts/guard-timeout-fails-open.md) |
| `guard-timing-case-flaky` | The rm-var cases now bound a ratio to a baseline run in the same process (bound 3, eighth-size baseline), so a uniformly slow runner does not fail it. | [`debts/guard-timing-case-flaky.md`](../debts/guard-timing-case-flaky.md) |
| `guard-wrapper-lists-closed` | The guard skips only the wrappers in `COMMAND_WRAPPERS` and the value flags in `WRAPPER_VALUE_FLAGS`. | [`debts/guard-wrapper-lists-closed.md`](../debts/guard-wrapper-lists-closed.md) |
| `haiku-counter-files-not-purged` | No code purges `state/`. | [`debts/haiku-counter-files-not-purged.md`](../debts/haiku-counter-files-not-purged.md) |
| `haiku-counter-lost-updates` | Heavy parallel calls of one session lose counter updates. | [`debts/haiku-counter-lost-updates.md`](../debts/haiku-counter-lost-updates.md) |
| `haiku-session-key-copied` | The session key line is copied from `decision_watch._seen_store_path`, with no stated reason. | [`debts/haiku-session-key-copied.md`](../debts/haiku-session-key-copied.md) |
| `haiku-stop-no-reply-uncounted` | The counter counts only Stops that carry a reply. | [`debts/haiku-stop-no-reply-uncounted.md`](../debts/haiku-stop-no-reply-uncounted.md) |
| `handoff-pointer-swept-compact` | Another session's compact reorient in the same directory can sweep a /clear pointer between SessionEnd and SessionStart. | [`debts/handoff-pointer-swept-compact.md`](../debts/handoff-pointer-swept-compact.md) |
| `handoff-pointers-age-out` | Pointers that have a handoff have no age rule. | [`debts/handoff-pointers-age-out.md`](../debts/handoff-pointers-age-out.md) |
| `handoff-wake-misses-ready-forms` | An obfuscated `gh pr re''ady` skips the wake. | [`debts/handoff-wake-misses-ready-forms.md`](../debts/handoff-wake-misses-ready-forms.md) |
| `harness-scope-line5-too-long` | `.github/scripts/harness-scope.sh` line 5 is about 140 characters long. | [`debts/harness-scope-line5-too-long.md`](../debts/harness-scope-line5-too-long.md) |
| `harness-scope-mods-flag-missing` | `STEP_FLAGS` (line 24 of `lint/test_harness_scope.py`) lacks `mods`. | [`debts/harness-scope-mods-flag-missing.md`](../debts/harness-scope-mods-flag-missing.md) |
| `harness-scope-pipe-regex-quotes` | The pipe regex in `mods_step_problems` ignores quotes and comments. | [`debts/harness-scope-pipe-regex-quotes.md`](../debts/harness-scope-pipe-regex-quotes.md) |
| `harness-scope-stale-comment` | `lint/test_harness_scope.py` lines 215-217 hold the stale comment "ALL stays as it is". | [`debts/harness-scope-stale-comment.md`](../debts/harness-scope-stale-comment.md) |
| `here-string-scan-quadratic` | The guard finds PowerShell here-strings with a lazy match. | [`debts/here-string-scan-quadratic.md`](../debts/here-string-scan-quadratic.md) |
| `heredoc-indented-close` | `_split_heredocs` matches the closing line after `.strip()`, so an indented ` EOF` closes a heredoc. | [`debts/heredoc-indented-close.md`](../debts/heredoc-indented-close.md) |
| `heredoc-run-other-path` | Some bodies run, but the guard reads them as text. | [`debts/heredoc-run-other-path.md`](../debts/heredoc-run-other-path.md) |
| `heredoc-script-then-run` | Main allows `cat <<EOF2 > x.sh`, with a body that holds a step the guard denies, followed by `sh x.sh` in the same command. | [`debts/heredoc-script-then-run.md`](../debts/heredoc-script-then-run.md) |
| `hint-signed-commit-sha` | With `log.showSignature=true` in config, git prints a signature line before a signed commit's record. | [`debts/hint-signed-commit-sha.md`](../debts/hint-signed-commit-sha.md) |
| `hold-own-hole-unrecorded` | The rule turns each open finding after round 3 into a debt. | [`debts/hold-own-hole-unrecorded.md`](../debts/hold-own-hole-unrecorded.md) |
| `impeccable-piped-shell-body` | The impeccable rule keeps a heredoc body only when the shell word stands before `<<`. | [`debts/impeccable-piped-shell-body.md`](../debts/impeccable-piped-shell-body.md) |
| `impeccable-python-body` | The impeccable rule reads a heredoc body when a shell word (`bash`, `sh`, `zsh`, `dash`, `ksh`, `pwsh`, `powershell`) stands before the `<<` on its header line. | [`debts/impeccable-python-body.md`](../debts/impeccable-python-body.md) |
| `inbox-done-forms` | While capture is open, `fb:done` and `` `fb done` `` in backticks are captured and do not close it. | [`debts/inbox-done-forms.md`](../debts/inbox-done-forms.md) |
| `inbox-midturn-prompt-untested` | UserPromptSubmit fired for owner messages sent mid-turn in the audit session of 2026-10-13, and the time line showed on each. | [`debts/inbox-midturn-prompt-untested.md`](../debts/inbox-midturn-prompt-untested.md) |
| `inbox-partial-write-fence` | A partial write can leave a fence open. | [`debts/inbox-partial-write-fence.md`](../debts/inbox-partial-write-fence.md) |
| `inbox-path-drop-silent` | If the inbox path cannot be built, an `fb` message is dropped with one stderr line only. | [`debts/inbox-path-drop-silent.md`](../debts/inbox-path-drop-silent.md) |
| `inbox-unreadable-drops-ids` | An unreadable inbox drops the open ids from the post-compaction note. | [`debts/inbox-unreadable-drops-ids.md`](../debts/inbox-unreadable-drops-ids.md) |
| `index-row-drop-no-finding` | The records page can lose a row with no finding in two cases. | [`debts/index-row-drop-no-finding.md`](../debts/index-row-drop-no-finding.md) |
| `inplace-edit-under-0-9-flagged` | A branch can edit a line that main only added. | [`debts/inplace-edit-under-0-9-flagged.md`](../debts/inplace-edit-under-0-9-flagged.md) |
| `install-family-list-by-hand` | The guard's module list `_FAMILY_MODULES` is kept by hand. | [`debts/install-family-list-by-hand.md`](../debts/install-family-list-by-hand.md) |
| `install-hook-path-from-checkout` | The post-merge git hook runs the installer from the checkout that ran the pull. | [`debts/install-hook-path-from-checkout.md`](../debts/install-hook-path-from-checkout.md) |
| `install-ps1-counts-store-alias` | A machine whose only python is the Store python gets the no-python remedy on every gated call. | [`debts/install-ps1-counts-store-alias.md`](../debts/install-ps1-counts-store-alias.md) |
| `install-reader-can-die-silent` | `HookReader` counts each read fault, but two lines sit outside its try: the file-name read and the body index. | [`debts/install-reader-can-die-silent.md`](../debts/install-reader-can-die-silent.md) |
| `install-sh-no-python-warning` | A Mac without `python3` gets no warning from `install.sh`. | [`debts/install-sh-no-python-warning.md`](../debts/install-sh-no-python-warning.md) |
| `install-skill-fail-exits-0` | If `Install-Dir` cannot replace a skill folder, the run does not retry it and exits 0. | [`debts/install-skill-fail-exits-0.md`](../debts/install-skill-fail-exits-0.md) |
| `install-stamp-line-unpinned` | Tests pin each stamper only to fixture copies. | [`debts/install-stamp-line-unpinned.md`](../debts/install-stamp-line-unpinned.md) |
| `install-window-guard-refusals` | An install replaces the hook files one by one. | [`debts/install-window-guard-refusals.md`](../debts/install-window-guard-refusals.md) |
| `install-worktree-check-gaps` | Four gaps, found in review: | [`debts/install-worktree-check-gaps.md`](../debts/install-worktree-check-gaps.md) |
| `install-writes-in-place` | The `CLAUDE.md` pointer, `settings.json` in `install.sh`, the skills folder, the install log and the marker are written in place. | [`debts/install-writes-in-place.md`](../debts/install-writes-in-place.md) |
| `interp-keep-body-unpinned` | The guard keeps the heredoc body under inspection for `ts-node -`, `babel-node -`, `git-bash.exe -c` and `node.cmd -`. | [`debts/interp-keep-body-unpinned.md`](../debts/interp-keep-body-unpinned.md) |
| `janitor-loop-no-alias-skip` | `bin/claude-janitor` keeps the old loop with no skip. | [`debts/janitor-loop-no-alias-skip.md`](../debts/janitor-loop-no-alias-skip.md) |
| `judge-cap-drops-old-rulings` | Measured 2026-10-14 (review round 1): 87 rulings, 100,887 chars uncapped. | [`debts/judge-cap-drops-old-rulings.md`](../debts/judge-cap-drops-old-rulings.md) |
| `judge-cut-mark-reserve-over` | `fit_span` keeps 37 chars for the cut mark even when no owner message can be cut. | [`debts/judge-cut-mark-reserve-over.md`](../debts/judge-cut-mark-reserve-over.md) |
| `judge-cuts-long-ruling` | A ruling over 800 chars is cut at a sentence end, so a settled point late in a long ruling may be missed. | [`debts/judge-cuts-long-ruling.md`](../debts/judge-cuts-long-ruling.md) |
| `judge-fence-lookalikes` | `_defang` changes only a run of 3 or more ASCII `<` before `BEGIN` or `END` in upper case. | [`debts/judge-fence-lookalikes.md`](../debts/judge-fence-lookalikes.md) |
| `judge-heading-false-match` | The ruling-heading pattern also matches a heading such as "Ruling out ...", so a heading that is not a ruling is read as one. | [`debts/judge-heading-false-match.md`](../debts/judge-heading-false-match.md) |
| `judge-skips-other-headings` | Rulings under another heading are not read. | [`debts/judge-skips-other-headings.md`](../debts/judge-skips-other-headings.md) |
| `judge-title-stem-collision` | A `decisions/` record and a `deferred/` record with the same file stem collide in the rulings titles, because the title names the stem only. | [`debts/judge-title-stem-collision.md`](../debts/judge-title-stem-collision.md) |
| `judge-uncommitted-order` | A record git does not list (new and not committed) is ordered by file mtime, after the listed ones. | [`debts/judge-uncommitted-order.md`](../debts/judge-uncommitted-order.md) |
| `lane-slug-gh-m-flag-passes` | In gh, `-m` is a milestone or merge flag, never a message. | [`debts/lane-slug-gh-m-flag-passes.md`](../debts/lane-slug-gh-m-flag-passes.md) |
| `lane-slug-header-count-shift` | An unquoted `<<word` in an interpreter-fed heredoc body, such as `x = 1 << y`, or a `case` `)` inside `$(`, shifts the header count. | [`debts/lane-slug-header-count-shift.md`](../debts/lane-slug-header-count-shift.md) |
| `lane-slug-heredoc-untested` | No test pins a `#` inside a string, a lone apostrophe in a comment, or multi-line quoted text before a header. | [`debts/lane-slug-heredoc-untested.md`](../debts/lane-slug-heredoc-untested.md) |
| `lane-slug-lowercase-n-passes` | Lowercase `n20` passes. | [`debts/lane-slug-lowercase-n-passes.md`](../debts/lane-slug-lowercase-n-passes.md) |
| `lane-slug-part-code-refused` | Any `N` plus one to three digits, as a whole word, is refused. | [`debts/lane-slug-part-code-refused.md`](../debts/lane-slug-part-code-refused.md) |
| `lane-slug-piped-body-unread` | A piped body, such as `echo ... \| gh pr create -F -`, is not read. | [`debts/lane-slug-piped-body-unread.md`](../debts/lane-slug-piped-body-unread.md) |
| `lane-slug-tag-messages-unchecked` | Tag messages are out of scope. | [`debts/lane-slug-tag-messages-unchecked.md`](../debts/lane-slug-tag-messages-unchecked.md) |
| `lane-slug-tilde-fence-refused` | A tilde fence (`~~~`) is not blanked. | [`debts/lane-slug-tilde-fence-refused.md`](../debts/lane-slug-tilde-fence-refused.md) |
| `liveness-windows-arm-unproven` | The repository has no Windows machine to run the Windows arm on. | [`debts/liveness-windows-arm-unproven.md`](../debts/liveness-windows-arm-unproven.md) |
| `local-time-hard-coded-dst` | The rule is the US rule in force since 2007, and it is coded in `hooks/local_time.py`. | [`debts/local-time-hard-coded-dst.md`](../debts/local-time-hard-coded-dst.md) |
| `local-time-line-cost-unmeasured` | The token cost of one line per prompt is unmeasured. | [`debts/local-time-line-cost-unmeasured.md`](../debts/local-time-line-cost-unmeasured.md) |
| `lock-delete-retry-window` | When `GhLock.acquire` finds an expired lock, it deletes it. | [`debts/lock-delete-retry-window.md`](../debts/lock-delete-retry-window.md) |
| `lock-read-error-never-expires` | When `GhLock.read` cannot read the lock commit for a reason that is not a network or rate error, it returns an expiry of infinity. | [`debts/lock-read-error-never-expires.md`](../debts/lock-read-error-never-expires.md) |
| `lock-ttl-rate-wait` | Every `GhLock` call retries a rate limit up to 3 times with a 60 s wait, so one call can wait 180 s. | [`debts/lock-ttl-rate-wait.md`](../debts/lock-ttl-rate-wait.md) |
| `merge-by-button-stale-page` | The merge tool rebuilds the records page before it merges. | [`debts/merge-by-button-stale-page.md`](../debts/merge-by-button-stale-page.md) |
| `merge-head-any-check-licenses` | Any passing check licenses a skipped required job, not only `scope`. | [`debts/merge-head-any-check-licenses.md`](../debts/merge-head-any-check-licenses.md) |
| `merge-head-empty-reads-green` | With no required names, zero checks and zero runs, the wait reads green after its 30 s settle. | [`debts/merge-head-empty-reads-green.md`](../debts/merge-head-empty-reads-green.md) |
| `merge-head-neutral-split` | `neutral` reads red in `classify` and green in `judge_runs`. | [`debts/merge-head-neutral-split.md`](../debts/merge-head-neutral-split.md) |
| `merge-head-preview-wrong` | The preview (`head_state`) prints a literal `<branch>`. | [`debts/merge-head-preview-wrong.md`](../debts/merge-head-preview-wrong.md) |
| `merge-head-race-remains` | The race between a push and `gh pr ready` remains. | [`debts/merge-head-race-remains.md`](../debts/merge-head-race-remains.md) |
| `merge-head-shared-name-slot` | Two workflow files with one `name` share one dedup slot. | [`debts/merge-head-shared-name-slot.md`](../debts/merge-head-shared-name-slot.md) |
| `merge-head-wait-no-remedy` | A passing check beside runs that all skipped reads red, with no remedy. | [`debts/merge-head-wait-no-remedy.md`](../debts/merge-head-wait-no-remedy.md) |
| `merge-net-5xx-unmatched` | REST 5xx texts from `gh api` do not match `NET_ERROR`: `gh: Server Error (HTTP 502)`, `gh: HTTP 503`, and `HTTP 502 (url)`. | [`debts/merge-net-5xx-unmatched.md`](../debts/merge-net-5xx-unmatched.md) |
| `merge-net-fetch-texts-missed` | The `git fetch` pattern misses some network texts. | [`debts/merge-net-fetch-texts-missed.md`](../debts/merge-net-fetch-texts-missed.md) |
| `merge-net-no-retry-in-deadline` | No retry runs inside `shared_deadline`, which wraps the guard's head read. | [`debts/merge-net-no-retry-in-deadline.md`](../debts/merge-net-no-retry-in-deadline.md) |
| `merge-net-open-reverts` | A `gh pr merge` reply with exit 0 and a state read of OPEN still reverts (`merge/merge.py` lines 549-550). | [`debts/merge-net-open-reverts.md`](../debts/merge-net-open-reverts.md) |
| `merge-net-stop-may-have-merged` | The NetStop text says "Run again." The merge may have landed. | [`debts/merge-net-stop-may-have-merged.md`](../debts/merge-net-stop-may-have-merged.md) |
| `merge-notice-unrelated-number` | A reply's blockquote can hold digits that match a merged PR's number for an unrelated reason. | [`debts/merge-notice-unrelated-number.md`](../debts/merge-notice-unrelated-number.md) |
| `merge-say-surrogate-crash` | The merge tool prints ALLOWED notes and an excused UNKNOWN to stdout with a plain print. | [`debts/merge-say-surrogate-crash.md`](../debts/merge-say-surrogate-crash.md) |
| `merge-text-allows-untested` | Test rows allow `grep` and `git log` commands that name merge words. | [`debts/merge-text-allows-untested.md`](../debts/merge-text-allows-untested.md) |
| `mod-gate-name-edges` | A mod folder with a non-ASCII name that the marketplace does not list comes back quoted from git. | [`debts/mod-gate-name-edges.md`](../debts/mod-gate-name-edges.md) |
| `model-clip-unmeasured` | The prompt now goes to `claude -p` on stdin, so no argv cap bounds it. | [`debts/model-clip-unmeasured.md`](../debts/model-clip-unmeasured.md) |
| `mods-check-mjs-skipped` | `mods/plain-diff/check.mjs` is a self-check script, and the glob skips it. | [`debts/mods-check-mjs-skipped.md`](../debts/mods-check-mjs-skipped.md) |
| `mods-linux-proof-pending` | The builder ran the mod tests on Windows only. | [`debts/mods-linux-proof-pending.md`](../debts/mods-linux-proof-pending.md) |
| `mods-load-needs-new-session` | A mod loads only in a session that starts after the change. | [`debts/mods-load-needs-new-session.md`](../debts/mods-load-needs-new-session.md) |
| `mods-macos-untested` | macOS is untested for all four mods: `token-weather`, `desktop-statusline`, `plain-diff` and `session-board`. | [`debts/mods-macos-untested.md`](../debts/mods-macos-untested.md) |
| `mods-marketplace-no-ref-pin` | The marketplace source has no `ref` pin. | [`debts/mods-marketplace-no-ref-pin.md`](../debts/mods-marketplace-no-ref-pin.md) |
| `mods-node-version-unpinned` | The runner's Node version is unknown. | [`debts/mods-node-version-unpinned.md`](../debts/mods-node-version-unpinned.md) |
| `mods-refresh-cadence-unmeasured` | How often the app refreshes a marketplace is unmeasured. | [`debts/mods-refresh-cadence-unmeasured.md`](../debts/mods-refresh-cadence-unmeasured.md) |
| `mods-session-board-timer-margins` | `mods/session-board/session-board.test.mjs` has two real-timer margins, about lines 709-718 and 928-940. | [`debts/mods-session-board-timer-margins.md`](../debts/mods-session-board-timer-margins.md) |
| `mods-step-order-unpinned` | No test pins that the mod test step is last. | [`debts/mods-step-order-unpinned.md`](../debts/mods-step-order-unpinned.md) |
| `mods-tests-glob-too-narrow` | The glob reaches only root-level `mods/<name>/*.test.mjs`. | [`debts/mods-tests-glob-too-narrow.md`](../debts/mods-tests-glob-too-narrow.md) |
| `mutant-crash-audit-missing` | The fix colocates `guard.py` for `watch` mutants only. | [`debts/mutant-crash-audit-missing.md`](../debts/mutant-crash-audit-missing.md) |
| `net-error-colon-http-refusal` | `NET_ERROR` matches `: HTTP 5xx (url)` at a line end. | [`debts/net-error-colon-http-refusal.md`](../debts/net-error-colon-http-refusal.md) |
| `node-file-server-unchecked` | `node <file>` under `run_in_background` is not refused without an `until:` note. | [`debts/node-file-server-unchecked.md`](../debts/node-file-server-unchecked.md) |
| `off-line-fork-reads-pre-cut` | A branch can be cut from a PR branch that merged later. | [`debts/off-line-fork-reads-pre-cut.md`](../debts/off-line-fork-reads-pre-cut.md) |
| `old-before-was-flags-history` | The rule flags `was:` when the word `old` comes earlier in the same block. | [`debts/old-before-was-flags-history.md`](../debts/old-before-was-flags-history.md) |
| `page-excuse-trailer-only` | In a repo whose upstream has no `lint/hook_catalog.py`, a standalone run of the check has no generator, so the page excuse never passes. | [`debts/page-excuse-trailer-only.md`](../debts/page-excuse-trailer-only.md) |
| `plain-diff-4mib-unconfirmed` | Output over the host's limit is cut, and the header says "Diff truncated". | [`debts/plain-diff-4mib-unconfirmed.md`](../debts/plain-diff-4mib-unconfirmed.md) |
| `plain-diff-desktop-untested` | The pane draw, and the turn-text match against a real `$.session.messages()`, are untested in the desktop app. | [`debts/plain-diff-desktop-untested.md`](../debts/plain-diff-desktop-untested.md) |
| `plain-diff-env-innocent-name` | A `.env` body under an innocent name, such as `notes.txt`, passes the path test. | [`debts/plain-diff-env-innocent-name.md`](../debts/plain-diff-env-innocent-name.md) |
| `plain-diff-keyvalue-misses` | The `KEY=value` rule skips all-digit values, values under 8 characters, and values with characters outside `A-Za-z0-9/+_=-`. | [`debts/plain-diff-keyvalue-misses.md`](../debts/plain-diff-keyvalue-misses.md) |
| `plain-diff-limiter-slot-early` | A call that outlasts the 25 s limiter timeout frees its slot while the host call may still run. | [`debts/plain-diff-limiter-slot-early.md`](../debts/plain-diff-limiter-slot-early.md) |
| `plain-diff-long-line-anchor` | On a line over 3000 characters, the end-of-line anchor can match at a chunk end. | [`debts/plain-diff-long-line-anchor.md`](../debts/plain-diff-long-line-anchor.md) |
| `plain-diff-model-error-note` | Case F8 was cut. | [`debts/plain-diff-model-error-note.md`](../debts/plain-diff-model-error-note.md) |
| `plain-diff-quoted-path-label` | A quoted path with an emoji shows a wrong label, so no turn note matches it. | [`debts/plain-diff-quoted-path-label.md`](../debts/plain-diff-quoted-path-label.md) |
| `plain-diff-secret-file-names` | Some secret file names are not caught by name. | [`debts/plain-diff-secret-file-names.md`](../debts/plain-diff-secret-file-names.md) |
| `plain-diff-trimnote-regex` | The table-row regex in `trimNote` was quadratic only on absurd input. | [`debts/plain-diff-trimnote-regex.md`](../debts/plain-diff-trimnote-regex.md) |
| `process-record-dead-plan-line` | The record mods-tests-run-in-gates is `Kind: process`, but it also holds a `Plan:` line. | [`debts/process-record-dead-plan-line.md`](../debts/process-record-dead-plan-line.md) |
| `prompt-hooks-fail-open` | Prompt hooks (Agent, AskUserQuestion, Edit and Write under `decisions/`, SendMessage) can deny, but the docs give them no `onFailure`. | [`debts/prompt-hooks-fail-open.md`](../debts/prompt-hooks-fail-open.md) |
| `prune-symlink-positive-unproven` | No Windows machine here can grant `SeCreateSymbolicLinkPrivilege` to this account. | [`debts/prune-symlink-positive-unproven.md`](../debts/prune-symlink-positive-unproven.md) |
| `ps-quote-forms-unread` | On main, a frozen path in smart quotes (U+201C, U+201D, U+2018, U+2019) and a `<# note #> Set-Content P` read as plain text or as no command. | [`debts/ps-quote-forms-unread.md`](../debts/ps-quote-forms-unread.md) |
| `purge-bad-row-key-raises` | A log row with a list or dict `branch` or `commit`, and a live `time_ms`, raises TypeError. | [`debts/purge-bad-row-key-raises.md`](../debts/purge-bad-row-key-raises.md) |
| `purge-confirm-total-wrong` | The "purge: N" total in the confirm report counts rows whose ref was kept. | [`debts/purge-confirm-total-wrong.md`](../debts/purge-confirm-total-wrong.md) |
| `purge-git-trace-missing-ref` | With `GIT_TRACE=1` or `GIT_TRACE2=1` set, git writes to stderr on a missing ref. | [`debts/purge-git-trace-missing-ref.md`](../debts/purge-git-trace-missing-ref.md) |
| `purge-key-case-folds` | Branch names compare with exact case, but NTFS ref names fold case. | [`debts/purge-key-case-folds.md`](../debts/purge-key-case-folds.md) |
| `purge-orphan-ref-kept` | The purge keeps a ref when no log entry names its commit. | [`debts/purge-orphan-ref-kept.md`](../debts/purge-orphan-ref-kept.md) |
| `purge-realpath-per-row` | `realpath` runs once per unexpired row, in preview too. | [`debts/purge-realpath-per-row.md`](../debts/purge-realpath-per-row.md) |
| `purge-snapshot-race` | The set of unexpired rows is read once, at purge start. | [`debts/purge-snapshot-race.md`](../debts/purge-snapshot-race.md) |
| `purge-update-ref-mutant-missing` | The harness has no mutant that drops only the commit argument of `update-ref -d`. | [`debts/purge-update-ref-mutant-missing.md`](../debts/purge-update-ref-mutant-missing.md) |
| `question-goal-line-masks-order` | A decorated Goal line earlier in the question, such as `- goal: old`, masks a real Problem-first order. | [`debts/question-goal-line-masks-order.md`](../debts/question-goal-line-masks-order.md) |
| `question-preface-punctuation` | A punctuation-led preface line before `Goal:`, such as `- problem: note`, is denied. | [`debts/question-preface-punctuation.md`](../debts/question-preface-punctuation.md) |
| `question-problem-line-forms` | `1. Problem:` (digit prefix) and `Problem :` (space before the colon) do not count as Problem lines. | [`debts/question-problem-line-forms.md`](../debts/question-problem-line-forms.md) |
| `rate-retry-budget-short` | The merge tool retries a rate limit 3 times with a 60 s wait. | [`debts/rate-retry-budget-short.md`](../debts/rate-retry-budget-short.md) |
| `reader-tree-kill-unproven` | On a reader timeout, the hook kills the process tree that it started. | [`debts/reader-tree-kill-unproven.md`](../debts/reader-tree-kill-unproven.md) |
| `rebase-loss-before-base-unread` | After a rebase, the silent-undo window starts at the rebase base. | [`debts/rebase-loss-before-base-unread.md`](../debts/rebase-loss-before-base-unread.md) |
| `receiver-state-reader-untested` | The SendMessage state tests now use a stub reader, so a slow runner cannot fail them. | [`debts/receiver-state-reader-untested.md`](../debts/receiver-state-reader-untested.md) |
| `reload-missing-file-unpinned` | Lane merge-guard-b removed `_damage_missing` and its two reload cases: a missing `guard_pointer.py` that comes back during the wait is allowed, and one that stays missing is refused. | [`debts/reload-missing-file-unpinned.md`](../debts/reload-missing-file-unpinned.md) |
| `rule-audit-crashes-on-windows` | `lint/rule_audit.py` crashes on default Windows at line 212, reached from the per-row loop at line 457. | [`debts/rule-audit-crashes-on-windows.md`](../debts/rule-audit-crashes-on-windows.md) |
| `ruling-home-isabs-unproven` | `value_resolves` refuses each absolute `home:` value. | [`debts/ruling-home-isabs-unproven.md`](../debts/ruling-home-isabs-unproven.md) |
| `ruling-kind-dir-equals-open` | `lint/check_ruling_kind.py` reads `--dir=x`, or any other unknown option, as a file name. | [`debts/ruling-kind-dir-equals-open.md`](../debts/ruling-kind-dir-equals-open.md) |
| `safety-hole-test-is-judgment` | No check measures a change's net safety value against main. | [`debts/safety-hole-test-is-judgment.md`](../debts/safety-hole-test-is-judgment.md) |
| `safety-line-unread-at-merge` | No check makes the orchestrator read the round-3 line `Net safety value:` before a merge. | [`debts/safety-line-unread-at-merge.md`](../debts/safety-line-unread-at-merge.md) |
| `sb-agents-json-cost` | `claude agents --json` runs on each board refresh. | [`debts/sb-agents-json-cost.md`](../debts/sb-agents-json-cost.md) |
| `sb-auto-approve-unseen` | An auto-approve mode can answer an "ask" with no person present. | [`debts/sb-auto-approve-unseen.md`](../debts/sb-auto-approve-unseen.md) |
| `sb-backoff-cap` | A quick git read resets the back-off. | [`debts/sb-backoff-cap.md`](../debts/sb-backoff-cap.md) |
| `sb-command-turn-unknown` | It is unknown whether a prompt sent from a command starts a turn in the app. | [`debts/sb-command-turn-unknown.md`](../debts/sb-command-turn-unknown.md) |
| `sb-config-folder-guess` | A drive-letter USERPROFILE means Windows. | [`debts/sb-config-folder-guess.md`](../debts/sb-config-folder-guess.md) |
| `sb-filter-driver-runs` | A filter driver named in repo git config can run during `git status`. | [`debts/sb-filter-driver-runs.md`](../debts/sb-filter-driver-runs.md) |
| `sb-ghost-row-race` | The end hook deletes the records before it marks the old id as retired. | [`debts/sb-ghost-row-race.md`](../debts/sb-ghost-row-race.md) |
| `sb-glob-path-names` | Grep and Glob paths that look like a file name show by name. | [`debts/sb-glob-path-names.md`](../debts/sb-glob-path-names.md) |
| `sb-hook-order-unproven` | The host hook order is untested. | [`debts/sb-hook-order-unproven.md`](../debts/sb-hook-order-unproven.md) |
| `sb-host-calls-unbounded` | The 100 ms wait does not bound every host call. | [`debts/sb-host-calls-unbounded.md`](../debts/sb-host-calls-unbounded.md) |
| `sb-pane-untested` | The pane draw is untested in the desktop app. | [`debts/sb-pane-untested.md`](../debts/sb-pane-untested.md) |
| `sb-process-desktop-unknown` | The API notes `$.process` as CLI only. | [`debts/sb-process-desktop-unknown.md`](../debts/sb-process-desktop-unknown.md) |
| `sb-prompt-turn-end` | The permission signal is a tool check that returns "ask". | [`debts/sb-prompt-turn-end.md`](../debts/sb-prompt-turn-end.md) |
| `sb-safe-stop-origin` | The origin check is a block-list. | [`debts/sb-safe-stop-origin.md`](../debts/sb-safe-stop-origin.md) |
| `sb-store-not-shared` | The store is per plugin and per config folder. | [`debts/sb-store-not-shared.md`](../debts/sb-store-not-shared.md) |
| `schtasks-test-not-in-ci` | `janitor/test_install_schtasks.py` was not wired into any CI job. | [`debts/schtasks-test-not-in-ci.md`](../debts/schtasks-test-not-in-ci.md) |
| `sendmessage-judge-blind-recvs` | The busy-state layer reads an agent id, a `uds:` address, `main` and `*` as unseen, so it allows. | [`debts/sendmessage-judge-blind-recvs.md`](../debts/sendmessage-judge-blind-recvs.md) |
| `sendmessage-judge-dup-names` | When two sessions share a name, `receiverState` returns unseen and the message is allowed with no state check. | [`debts/sendmessage-judge-dup-names.md`](../debts/sendmessage-judge-dup-names.md) |
| `sendmessage-wording-judge-always` | The SendMessage prompt hook in `settings.json` runs a model call on every send. | [`debts/sendmessage-wording-judge-always.md`](../debts/sendmessage-wording-judge-always.md) |
| `server-wrappers-unread` | The `background-end` rule does not read some wrappers and forms, so a background server behind them is not refused without an `until:` note. | [`debts/server-wrappers-unread.md`](../debts/server-wrappers-unread.md) |
| `shell-write-miss-dq-substitution` | A write inside a command substitution in double quotes, `"$( ... > P)"`, is not seen, for the same glued-parenthesis reason. | [`debts/shell-write-miss-dq-substitution.md`](../debts/shell-write-miss-dq-substitution.md) |
| `shell-write-miss-eval-heredoc` | An eval of a heredoc body that writes a settings or frozen path is not seen. | [`debts/shell-write-miss-eval-heredoc.md`](../debts/shell-write-miss-eval-heredoc.md) |
| `shell-write-miss-git-config-file` | `git config --file P a.b c` writes P, but the flag value is not read as a target, so the write is not seen. | [`debts/shell-write-miss-git-config-file.md`](../debts/shell-write-miss-git-config-file.md) |
| `shell-write-miss-git-diff-output` | `git diff --output=P` writes P, but the flag value is not read as a target, so the write is not seen. | [`debts/shell-write-miss-git-diff-output.md`](../debts/shell-write-miss-git-diff-output.md) |
| `shell-write-miss-noclobber` | `echo x >\| P` writes P, but `REDIRECT` reads only `>` and `>>`, so the word after it is `\|P` and the write is not seen. | [`debts/shell-write-miss-noclobber.md`](../debts/shell-write-miss-noclobber.md) |
| `shell-write-miss-pipe-heredoc` | A heredoc piped into a shell (`cat <<EOF \| sh`) that writes a settings or frozen path is not seen. | [`debts/shell-write-miss-pipe-heredoc.md`](../debts/shell-write-miss-pipe-heredoc.md) |
| `shell-write-miss-sort-output` | `sort -o P` writes P, but `sort` is not in `MUTATING_COMMAND` and `-o` is not a redirect, so the write is not seen. | [`debts/shell-write-miss-sort-output.md`](../debts/shell-write-miss-sort-output.md) |
| `shell-write-miss-spaced-target` | `cat > "dir with space/.claude/settings.json"` writes the settings file, but the reader splits the quoted path on its space, and no fragment of it follows the `>`. | [`debts/shell-write-miss-spaced-target.md`](../debts/shell-write-miss-spaced-target.md) |
| `shell-write-miss-subshell` | A write inside a subshell, `( ... > P)`, is not seen: the closing parenthesis stays glued to the path word, so the path never matches. | [`debts/shell-write-miss-subshell.md`](../debts/shell-write-miss-subshell.md) |
| `silent-undo-oracle-hides-cause` | When the records page generator fails, is missing, or reports a problem, the silent-undo check reports only "hunk reversed" for `docs/records.md` and discards the generator's stderr. | [`debts/silent-undo-oracle-hides-cause.md`](../debts/silent-undo-oracle-hides-cause.md) |
| `sim-boot-check-xcodebuild` | The ruling 5 boot check runs only after `simctl boot` and MCP `launch`. | [`debts/sim-boot-check-xcodebuild.md`](../debts/sim-boot-check-xcodebuild.md) |
| `skill-rows-dir-named-skill-md` | A directory named `SKILL.md` counts as a skill. | [`debts/skill-rows-dir-named-skill-md.md`](../debts/skill-rows-dir-named-skill-md.md) |
| `skill-rows-fence-indent` | In the check, a line of 4 spaces, then a fence mark, inside a fence closes it. | [`debts/skill-rows-fence-indent.md`](../debts/skill-rows-fence-indent.md) |
| `skill-rows-phrase-any-cell` | The check matches the two phrases anywhere on the row line. | [`debts/skill-rows-phrase-any-cell.md`](../debts/skill-rows-phrase-any-cell.md) |
| `skill-rows-posix-only-test` | The unreadable-folder exit 2 test runs only on POSIX. | [`debts/skill-rows-posix-only-test.md`](../debts/skill-rows-posix-only-test.md) |
| `skill-rows-test-gaps` | No test covers a tilde line inside a backtick fence. | [`debts/skill-rows-test-gaps.md`](../debts/skill-rows-test-gaps.md) |
| `skill-rows-unclosed-fence-silent` | An unclosed fence or comment hides every later row. | [`debts/skill-rows-unclosed-fence-silent.md`](../debts/skill-rows-unclosed-fence-silent.md) |
| `slug-lint-skips-abs-and-md` | `lint/check_record_slugs.py` and `lint/check_ruling_kind.py` do not judge an absolute file argument or a name ending in `.MD`. | [`debts/slug-lint-skips-abs-and-md.md`](../debts/slug-lint-skips-abs-and-md.md) |
| `smstate-answer-timeout-unrun` | The answer cases run with no reader timeout, so no case uses the shipped value. | [`debts/smstate-answer-timeout-unrun.md`](../debts/smstate-answer-timeout-unrun.md) |
| `smstate-hold-deadlock-skips` | When the hold case hits the harness cap, it prints SKIP and a warning. | [`debts/smstate-hold-deadlock-skips.md`](../debts/smstate-hold-deadlock-skips.md) |
| `smstate-hold-posix-unproven` | No run shows the hold case red on a POSIX host with a hook that waits on the held pipe. | [`debts/smstate-hold-posix-unproven.md`](../debts/smstate-hold-posix-unproven.md) |
| `smstate-run-cap-traceback` | The 120 s cap in `run_hook` raises an uncaught `TimeoutExpired`. | [`debts/smstate-run-cap-traceback.md`](../debts/smstate-run-cap-traceback.md) |
| `smstate-temp-root-kept` | Each run makes a folder in the temp directory and never removes it. | [`debts/smstate-temp-root-kept.md`](../debts/smstate-temp-root-kept.md) |
| `source-prose-scanner-cases` | Rule `building-scanner-respects-strings` asks each scanner for two test shapes. | [`debts/source-prose-scanner-cases.md`](../debts/source-prose-scanner-cases.md) |
| `split-comment-shapes-unmeasured` | The comment rule is unmeasured against every quoting shape a real shell accepts. | [`debts/split-comment-shapes-unmeasured.md`](../debts/split-comment-shapes-unmeasured.md) |
| `split-paren-pkill-unpinned` | Lane merge-guard-b dropped the row `echo don't (x; pkill foo`. | [`debts/split-paren-pkill-unpinned.md`](../debts/split-paren-pkill-unpinned.md) |
| `split-quoted-hash-unpinned` | Lane merge-guard-b dropped the row `echo a's # b'; pkill foo`. | [`debts/split-quoted-hash-unpinned.md`](../debts/split-quoted-hash-unpinned.md) |
| `split-reader-misses-cd-forms` | `split_segments` does not model `$'...'` ANSI-C quoting, `$(...)`, or backtick substitution. | [`debts/split-reader-misses-cd-forms.md`](../debts/split-reader-misses-cd-forms.md) |
| `stall-closes-on-quoted-notice` | The closing match also reads the text of user tool_result blocks. | [`debts/stall-closes-on-quoted-notice.md`](../debts/stall-closes-on-quoted-notice.md) |
| `stall-list-result-first-block` | A list-form result closes a job only from its first text block. | [`debts/stall-list-result-first-block.md`](../debts/stall-list-result-first-block.md) |
| `stall-macos-no-stop-suite` | The macOS CI jobs run no stop suite. | [`debts/stall-macos-no-stop-suite.md`](../debts/stall-macos-no-stop-suite.md) |
| `stall-message-delivery-unproven` | No run shows that a Stop systemMessage reaches the model. | [`debts/stall-message-delivery-unproven.md`](../debts/stall-message-delivery-unproven.md) |
| `stall-message-repeats-every-stop` | There is no dedupe. | [`debts/stall-message-repeats-every-stop.md`](../debts/stall-message-repeats-every-stop.md) |
| `stall-nul-path-drops-run` | `os.stat` raises ValueError on a path with a NUL byte, and the check does not catch it. | [`debts/stall-nul-path-drops-run.md`](../debts/stall-nul-path-drops-run.md) |
| `stall-open-job-no-age-ceiling` | Open jobs have no age ceiling. | [`debts/stall-open-job-no-age-ceiling.md`](../debts/stall-open-job-no-age-ceiling.md) |
| `stall-status-case-sensitive` | The status match is case-sensitive. | [`debts/stall-status-case-sensitive.md`](../debts/stall-status-case-sensitive.md) |
| `stall-windows-ci-unknown` | The Windows CI step runs on a Windows runner that this change has not run on. | [`debts/stall-windows-ci-unknown.md`](../debts/stall-windows-ci-unknown.md) |
| `stamp-blank-line-quote-fence` | A blank line with no `>` inside a quoted fence does not end the quote. | [`debts/stamp-blank-line-quote-fence.md`](../debts/stamp-blank-line-quote-fence.md) |
| `stamp-html-comment-hides-file` | A fence inside an HTML comment hides the rest of the file. | [`debts/stamp-html-comment-hides-file.md`](../debts/stamp-html-comment-hides-file.md) |
| `stamp-list-fence-not-seen` | A blockquote fence inside a list item at 4 or more columns is not seen as a fence. | [`debts/stamp-list-fence-not-seen.md`](../debts/stamp-list-fence-not-seen.md) |
| `stamp-list-marker-column` | Some list markers that CommonMark does not open still set a content column. | [`debts/stamp-list-marker-column.md`](../debts/stamp-list-marker-column.md) |
| `stamp-quote-fence-closes-early` | A quoted fence line `>code`, with no space after `>`, closes the fence early. | [`debts/stamp-quote-fence-closes-early.md`](../debts/stamp-quote-fence-closes-early.md) |
| `stamp-scan-frontmatter-links` | The near-miss scan does not skip frontmatter or link targets. | [`debts/stamp-scan-frontmatter-links.md`](../debts/stamp-scan-frontmatter-links.md) |
| `stash-all-ignored-tree-passes` | `git stash -a` and `git stash --all` pass the guard over a tree that holds only ignored files. | [`debts/stash-all-ignored-tree-passes.md`](../debts/stash-all-ignored-tree-passes.md) |
| `stash-allow-any-linked-worktree` | The allow passes any linked worktree, not only the caller's own. | [`debts/stash-allow-any-linked-worktree.md`](../debts/stash-allow-any-linked-worktree.md) |
| `stash-create-false-refusal` | `git stash create` falls outside the stash tree actions, so it reads as a take. | [`debts/stash-create-false-refusal.md`](../debts/stash-create-false-refusal.md) |
| `stash-export-comment-stale` | The comment above the import and export rows in `hooks/test_guard.py` says `import` and `export` are not git subcommands. | [`debts/stash-export-comment-stale.md`](../debts/stash-export-comment-stale.md) |
| `stash-help-flag-refused-as-push` | `git stash -h` and `git stash --help` are refused over a dirty tree. | [`debts/stash-help-flag-refused-as-push.md`](../debts/stash-help-flag-refused-as-push.md) |
| `stash-read-to-run-race` | An empty tree or an empty stack still passes. | [`debts/stash-read-to-run-race.md`](../debts/stash-read-to-run-race.md) |
| `stash-reminder-text-outside-repo` | The harness worktree reminder still tells a worker to push a tagged entry. | [`debts/stash-reminder-text-outside-repo.md`](../debts/stash-reminder-text-outside-repo.md) |
| `stdin-python-read-as-code` | A quoted cap key or frozen path piped into an interpreter denies: `python hooks/guard.py`, `python run.py`, `python -`, and wrappers such as `head`, `tail`, `sort`, `VAR=x python`, `python3.12`, `py` or `verdict python`. | [`debts/stdin-python-read-as-code.md`](../debts/stdin-python-read-as-code.md) |
| `ste-autofix-tests-linux-only` | `lint/test_ste_autofix.py` runs on the Linux job only. | [`debts/ste-autofix-tests-linux-only.md`](../debts/ste-autofix-tests-linux-only.md) |
| `ste-comment-gt-mask-early` | A comment that holds `>` ends its mask early. | [`debts/ste-comment-gt-mask-early.md`](../debts/ste-comment-gt-mask-early.md) |
| `ste-edit-fence-blind` | The Edit and MultiEdit path tracks only plain fences and front matter. | [`debts/ste-edit-fence-blind.md`](../debts/ste-edit-fence-blind.md) |
| `ste-eg-in-fence-reported` | The lint still reports `e.g.` inside a blockquote fence or a pre block. | [`debts/ste-eg-in-fence-reported.md`](../debts/ste-eg-in-fence-reported.md) |
| `ste-eg-line-end-rewrite` | `e.g.` or `i.e.` at a line end becomes `for example.` or `that is.` with a full stop. | [`debts/ste-eg-line-end-rewrite.md`](../debts/ste-eg-line-end-rewrite.md) |
| `ste-exclude-star-crosses-dir` | After the git glob exclude, `run.sh` matches each file again with a bash pattern. | [`debts/ste-exclude-star-crosses-dir.md`](../debts/ste-exclude-star-crosses-dir.md) |
| `ste-fix-changes-meaning` | Some autofixes change meaning. | [`debts/ste-fix-changes-meaning.md`](../debts/ste-fix-changes-meaning.md) |
| `ste-gate-closed-pipe-no-log` | If the reader closes stdout early, the STE gate raises at its flush in `answer()`, before the log call. | [`debts/ste-gate-closed-pipe-no-log.md`](../debts/ste-gate-closed-pipe-no-log.md) |
| `ste-hook-timeout-fails-open` | The fixer limit (5 s) plus the lint timeout (15 s) equals the hook timeout (20 s). | [`debts/ste-hook-timeout-fails-open.md`](../debts/ste-hook-timeout-fails-open.md) |
| `ste-macos-child-route-unverified` | The child-process route for the STE autofix is not verified on macOS. | [`debts/ste-macos-child-route-unverified.md`](../debts/ste-macos-child-route-unverified.md) |
| `ste-rewrite-unchecked-lands` | The STE fixer rewrites the text, then the lint cannot run. | [`debts/ste-rewrite-unchecked-lands.md`](../debts/ste-rewrite-unchecked-lands.md) |
| `subagent-workflow-model-unasked` | The guard asks on a write of `CLAUDE_CODE_SUBAGENT_MODEL` or its `_FORCE` form only. | [`debts/subagent-workflow-model-unasked.md`](../debts/subagent-workflow-model-unasked.md) |
| `sweep-anchor-first-match` | `janitor/mutate_sweep.py` checks an anchor exactly once only in its scaffold. | [`debts/sweep-anchor-first-match.md`](../debts/sweep-anchor-first-match.md) |
| `sweep-no-deadline-many-trees` | The sweep checks each worktree in turn, with eight or more git calls per tree. | [`debts/sweep-no-deadline-many-trees.md`](../debts/sweep-no-deadline-many-trees.md) |
| `sweep-test-symlink-privilege` | On a Windows host with no symlink right, two tests in `janitor/test_sweep.py` stop with WinError 1314. | [`debts/sweep-test-symlink-privilege.md`](../debts/sweep-test-symlink-privilege.md) |
| `sweep-tests-sleep-bounds` | `_peak_concurrency` sleeps 0.2 s inside each wrapped call to widen a race. | [`debts/sweep-tests-sleep-bounds.md`](../debts/sweep-tests-sleep-bounds.md) |
| `symrun-link-gap-unmeasured` | The symrun case wants at least one mixed-id window during run 2. | [`debts/symrun-link-gap-unmeasured.md`](../debts/symrun-link-gap-unmeasured.md) |
| `test-guard-posix-gates-no-skip` | Two case blocks in the guard test suite run only on one platform: Windows (`os.name == "nt"`) and macOS (`sys.platform == "darwin"`). | [`debts/test-guard-posix-gates-no-skip.md`](../debts/test-guard-posix-gates-no-skip.md) |
| `timeout-moved-server-unchecked` | A foreground server that the harness moves to background at its 120 s timeout is not checked. | [`debts/timeout-moved-server-unchecked.md`](../debts/timeout-moved-server-unchecked.md) |
| `undo-scan-cr-nul-false-alarm` | The scan reads `git log -p` as text. | [`debts/undo-scan-cr-nul-false-alarm.md`](../debts/undo-scan-cr-nul-false-alarm.md) |
| `unknown-reads-nonbool-skips` | The check prints PASS for True, FAIL for False, and SKIP for any other answer. | [`debts/unknown-reads-nonbool-skips.md`](../debts/unknown-reads-nonbool-skips.md) |
| `unknown-stash-word-tree-only` | An unknown stash word is read as a push, so the guard judges it on the working tree only. | [`debts/unknown-stash-word-tree-only.md`](../debts/unknown-stash-word-tree-only.md) |
| `until-note-unjudged` | The `background-end` rule accepts any non-empty `until:` text, such as `until: n/a`. | [`debts/until-note-unjudged.md`](../debts/until-note-unjudged.md) |
| `verdict-skip-reads-pass` | If a run prints SKIP lines and exits 0, `bin/verdict` prints only PASS. | [`debts/verdict-skip-reads-pass.md`](../debts/verdict-skip-reads-pass.md) |
| `walk-curly-quotes-plain` | PowerShell can take the curly quotes U+2018 to U+201E as quote marks. | [`debts/walk-curly-quotes-plain.md`](../debts/walk-curly-quotes-plain.md) |
| `win-slice-hides-skip-rows` | Nine guard cases skip on Windows: 2 subject, 6 kill and 1 simulator. | [`debts/win-slice-hides-skip-rows.md`](../debts/win-slice-hides-skip-rows.md) |
| `win-split-min-jobs-untested` | Case `test_suites_spread_over_enough_jobs` was cut. | [`debts/win-split-min-jobs-untested.md`](../debts/win-split-min-jobs-untested.md) |
| `wsl-bare-bash-not-refused` | A bare `bash.exe -c` is not refused. | [`debts/wsl-bare-bash-not-refused.md`](../debts/wsl-bare-bash-not-refused.md) |
| `wsl-distro-exes-not-refused` | `debian.exe` and `kali.exe` are not refused. | [`debts/wsl-distro-exes-not-refused.md`](../debts/wsl-distro-exes-not-refused.md) |
| `wsl-env-path-form-untested` | No test pins the `env:` path form or the quoted-name form of WSLENV. | [`debts/wsl-env-path-form-untested.md`](../debts/wsl-env-path-form-untested.md) |
| `wsl-wslenv-false-alarms` | False alarms occur when the same command also runs wsl. | [`debts/wsl-wslenv-false-alarms.md`](../debts/wsl-wslenv-false-alarms.md) |
| `wsl-wslenv-no-equals-unrefused` | A WSLENV set with no `=` is not refused. | [`debts/wsl-wslenv-no-equals-unrefused.md`](../debts/wsl-wslenv-no-equals-unrefused.md) |

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
