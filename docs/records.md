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
| `roles-sonnet-is-the-ceiling` | Sonnet is the ceiling, except Plan, the advisor, and a builder's third try (`roles-third-try-steps-up`), which run Opus. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-opus-shaped-say-so` | When a task is Opus-shaped (long-horizon, whole-codebase, or many-hour autonomous work), say so in one line before you dispatch, name why, and offer the switch. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-opus-override-guarded` | Only on my word, write the repo's `.claude/settings.local.json` with an `env` block that raises `CLAUDE_CODE_SUBAGENT_MODEL` to `opus`. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-brief-contents` | A brief carries the task, the files, governing rulings, failure classes from `outcomes-tests-are-claims`, and the check that proves the task done—in the fewest words. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-each-layer-proves-once` | Each layer proves a change once. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-review-cap-three` | A change gets at most three review rounds. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-holes-are-debts` | A known gap is a debt only if Claude is likely to hit it in normal work. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-third-try-steps-up` | Builders get two Sonnet tries; if review round 2 fails, the third (`Try 3 of 3`) runs on Opus by the owner's standing word. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-resume-by-name` | Resume a dead agent by name, never fresh. | [`CLAUDE.md`](../CLAUDE.md) |
| `parallelism-each-own-checkout` | Fan tasks out to workers now, each in its own checkout. | [`CLAUDE.md`](../CLAUDE.md) |
| `parallelism-own-lane-orchestrator` | A read-only workflow agent shares the caller's checkout. | [`CLAUDE.md`](../CLAUDE.md) |
| `parallelism-no-mid-task-talk` | Never let lanes talk mid-task. | [`CLAUDE.md`](../CLAUDE.md) |
| `parallelism-argue-max-parallelism` | Argue "at max parallelism" by naming the open lanes, never by assuming the claim. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-no-destructive-git` | No destructive git. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-no-machine-wide-kill` | Never kill a process you did not start. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-one-checkout-per-agent` | Give one checkout to each concurrent agent. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-own-ports-data` | A branch switch is a whole-tree act. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-confirm-before-write` | Confirm which checkout and branch you stand in before any git write or merge. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-reverify-after-incident` | Re-verify every edit after an incident. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-main-only-by-pr` | Move main only by pull request, merged only when I name the act, or under a repo grant. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-never-merge-failing-ci` | Never merge failing CI. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-never-discard-output` | Never discard a command's output. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-remedy-never-names-target` | A refusal's printed remedy never names the forbidden target. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-slug-then-claim-number` | Never allocate a numbered record on a branch. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-cite-by-id` | Cite by id, never by path. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-record-own-file-per-kind` | Give each record its own file, one folder per kind. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-one-entry-per-question` | One entry per question. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-integration-branch-merge` | Batch lane PRs that pass their local checks into one integration branch. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-screens-verdict` | If the repo has screens, check each screen at every size and theme it ships in. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-browser-login-only-needed` | Prefer a headless or isolated browser over my own, and use my login only when needed. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-announce-own-screen` | Before a window or a screen capture lands on my screen, say so in one line. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-trust-guard-after-red` | Trust a guard only once it goes red on the defect it guards. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-cry-wolf-guard-is-spent` | A guard that goes red when nothing is wrong is spent, because the reader learns to scroll past it. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-green-proves-only-its-fixtures` | A green check proves only its platform and the states its fixtures build. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-recovery-not-gated-on-own-state` | A recovery control must not depend on the state it recovers, or it fails on the one day it is needed. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-verify-against-repo` | Verify long work against the repo, not your status line. | [`CLAUDE.md`](../CLAUDE.md) |
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
| `building-memory-is-short-term` | Memory stays on, as short-term notes. | [`CLAUDE.md`](../CLAUDE.md) |
| `speak-cite-id-plus-gloss` | Cite a record by id plus a short gloss, like "D12, short titles for records". | [`CLAUDE.md`](../CLAUDE.md) |
| `speak-never-explain-in-paragraph` | Never explain a rule in a paragraph. | [`CLAUDE.md`](../CLAUDE.md) |
| `speak-rewrite-superseded-in-place` | Rewrite superseded text in place. | [`CLAUDE.md`](../CLAUDE.md) |
| `output-write-in-ste` | Write plainly: short sentences, one term per meaning, no filler. | [`CLAUDE.md`](../CLAUDE.md) |
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
| `a-branch-is-redundant-by-patch-not-by-ancestry` | The sweep (`the-janitor-is-one-machine-wide-sweep`, the janitor is one machine-wide sweep) keeps or reaps a local branch. | [`decisions/a-branch-is-redundant-by-patch-not-by-ancestry.md`](../decisions/a-branch-is-redundant-by-patch-not-by-ancestry.md) |
| `a-gates-allow-list-is-the-constant` | CLAUDE.md now names this rule: a gate's allow list must point at the constant the code emits, never a copy of it. | [`decisions/a-gates-allow-list-is-the-constant.md`](../decisions/a-gates-allow-list-is-the-constant.md) |
| `a-rule-with-no-gate-leaves-claude-md` | On 2026-09-28 the owner ruled that the semicolon line leaves `CLAUDE.md`. | [`decisions/a-rule-with-no-gate-leaves-claude-md.md`](../decisions/a-rule-with-no-gate-leaves-claude-md.md) |
| `agent-end-reap-stops-what-a-finished-agent-left` | Kind: process Home: janitor/agent_end_reap.py | [`decisions/agent-end-reap-stops-what-a-finished-agent-left.md`](../decisions/agent-end-reap-stops-what-a-finished-agent-left.md) |
| `agent-worktree-discard-is-noted` | The shared-tree rule asks the owner before a discarding git command runs. | [`decisions/agent-worktree-discard-is-noted.md`](../decisions/agent-worktree-discard-is-noted.md) |
| `agents-wait-with-monitor` | Which way may an agent wait for a condition? | [`decisions/agents-wait-with-monitor.md`](../decisions/agents-wait-with-monitor.md) |
| `ask-steps-run-alone` | Owner ruling, 2026-10-14. | [`decisions/ask-steps-run-alone.md`](../decisions/ask-steps-run-alone.md) |
| `audit-rework-order` | Owner ruling, 2026-10-16 10:50 CDT. | [`decisions/audit-rework-order.md`](../decisions/audit-rework-order.md) |
| `background-needs-end-note` | Owner ruling, 2026-10-13 23:41 CDT: "End condition at start." | [`decisions/background-needs-end-note.md`](../decisions/background-needs-end-note.md) |
| `build-dirs-reaped-at-agent-end` | Owner ruling, 2026-10-11, labeled "Agent-end hook + low-disk guard". | [`decisions/build-dirs-reaped-at-agent-end.md`](../decisions/build-dirs-reaped-at-agent-end.md) |
| `ci-unknown-is-red-and-dedup` | A lint that cannot read its input prints UNKNOWN. | [`decisions/ci-unknown-is-red-and-dedup.md`](../decisions/ci-unknown-is-red-and-dedup.md) |
| `cite-by-id-blocks-unread-file` | Owner, 2026-10-17 11:40 CDT (guard audit, finding 7): keep the block. | [`decisions/cite-by-id-blocks-unread-file.md`](../decisions/cite-by-id-blocks-unread-file.md) |
| `claude-md-shrink` | Owner ruling, 2026-10-16 23:53 CDT. | [`decisions/claude-md-shrink.md`](../decisions/claude-md-shrink.md) |
| `cull-rules` | Owner ruling, 2026-10-17 11:56 CDT. | [`decisions/cull-rules.md`](../decisions/cull-rules.md) |
| `debts-have-their-own-store` | A known gap that Claude is likely to hit in normal work is a debt. | [`decisions/debts-have-their-own-store.md`](../decisions/debts-have-their-own-store.md) |
| `decision-watch-mod-limits` | Yes. | [`decisions/decision-watch-mod-limits.md`](../decisions/decision-watch-mod-limits.md) |
| `default-branch-read-order` | Owner, 2026-10-16: read in this order. | [`decisions/default-branch-read-order.md`](../decisions/default-branch-read-order.md) |
| `dependabot-security-only` | Owner, 2026-10-16: security updates only. | [`decisions/dependabot-security-only.md`](../decisions/dependabot-security-only.md) |
| `design-skills` | Owner ruling, 2026-10-10. | [`decisions/design-skills.md`](../decisions/design-skills.md) |
| `draft-until-reviewed` | Owner rulings, 2026-10-10 and 2026-10-13. | [`decisions/draft-until-reviewed.md`](../decisions/draft-until-reviewed.md) |
| `drops-lines-trailer-exempt` | Owner, 2026-10-12: the `Drops-lines: <record path> -- <reason>` trailer is the one place a record path is allowed in a commit message. | [`decisions/drops-lines-trailer-exempt.md`](../decisions/drops-lines-trailer-exempt.md) |
| `env-file-wrappers` | The `env-file` rule allows `--env-file` only when the command word is a runner (`ENV_LOADER_COMMANDS`). | [`decisions/env-file-wrappers.md`](../decisions/env-file-wrappers.md) |
| `every-lint-rule-blocks-or-does-not-exist` | CLAUDE.md says: "Judge every rule, check, and design by the outcome for the person the software serves." The owner ruled that a rule either blocks or does not exist. | [`decisions/every-lint-rule-blocks-or-does-not-exist.md`](../decisions/every-lint-rule-blocks-or-does-not-exist.md) |
| `fewest-words-mandate` | On 2026-09-28 the owner asked for a verbiage mandate. | [`decisions/fewest-words-mandate.md`](../decisions/fewest-words-mandate.md) |
| `gate-hooks-fail-closed` | Owner, 2026-10-12: a gate whose script or python is missing refuses the call. | [`decisions/gate-hooks-fail-closed.md`](../decisions/gate-hooks-fail-closed.md) |
| `guard-audit-high` | Which guard refusals are false alarms or gaps? | [`decisions/guard-audit-high.md`](../decisions/guard-audit-high.md) |
| `guard-command-position` | One resolver finds the command word for every rule. | [`decisions/guard-command-position.md`](../decisions/guard-command-position.md) |
| `guard-guards-mistakes-only` | Owner ruling, 2026-10-17 09:07 CDT. | [`decisions/guard-guards-mistakes-only.md`](../decisions/guard-guards-mistakes-only.md) |
| `guard-log-read-weekly` | `hooks/guard_core.py:record()` appends one line per verdict to `~/.claude/guard.log`. | [`decisions/guard-log-read-weekly.md`](../decisions/guard-log-read-weekly.md) |
| `guard-that-cries-wolf-is-spent` | CLAUDE.md says: "Trust a guard only once it goes red on the defect it guards." This entry records the missing half, and the two false alarms that made the half worth writing down. | [`decisions/guard-that-cries-wolf-is-spent.md`](../decisions/guard-that-cries-wolf-is-spent.md) |
| `guard-trims-from-the-audit` | The owner approved these trims from an audit of `~/.claude/guard.log`: 2,713 lines, 2026-09-16 to 2026-10-02. | [`decisions/guard-trims-from-the-audit.md`](../decisions/guard-trims-from-the-audit.md) |
| `haiku-prompt-hooks` | Owner ruling, 2026-10-17 11:33 CDT, the trial review: the blocking judges stay. | [`decisions/haiku-prompt-hooks.md`](../decisions/haiku-prompt-hooks.md) |
| `hold-unsafe-after-round-3` | Owner ruling, 2026-10-15 12:00 CDT. | [`decisions/hold-unsafe-after-round-3.md`](../decisions/hold-unsafe-after-round-3.md) |
| `install-sh-mv-retries` | Kind: process Home: install.sh | [`decisions/install-sh-mv-retries.md`](../decisions/install-sh-mv-retries.md) |
| `janitor-dirty-test-stays` | Owner word, 2026-10-13 15:56 CDT: option A. | [`decisions/janitor-dirty-test-stays.md`](../decisions/janitor-dirty-test-stays.md) |
| `lane-by-slug` | Owner, 2026-10-13 14:13 CDT, relayed by the oversight session: | [`decisions/lane-by-slug.md`](../decisions/lane-by-slug.md) |
| `list-form-subprocess-ignores-a-path-shim-on-windows` | Three suites drive a blind `git` stand-in through a directory placed first on `PATH`. | [`decisions/list-form-subprocess-ignores-a-path-shim-on-windows.md`](../decisions/list-form-subprocess-ignores-a-path-shim-on-windows.md) |
| `local-time-central` | Owner, 2026-10-12: US Central (America/Chicago), DST-aware, 24-hour clock. | [`decisions/local-time-central.md`](../decisions/local-time-central.md) |
| `memory-is-never-a-rulings-only-home` | The owner's rulings must reach a tracked file. | [`decisions/memory-is-never-a-rulings-only-home.md`](../decisions/memory-is-never-a-rulings-only-home.md) |
| `merge-needs-a-proven-head` | Owner, 2026-10-12: "Fix both now, one lane." | [`decisions/merge-needs-a-proven-head.md`](../decisions/merge-needs-a-proven-head.md) |
| `mods-deferred-table` | Owner word, 2026-10-13 21:00 CDT: leave these as deferred recordings on the repo. | [`decisions/mods-deferred-table.md`](../decisions/mods-deferred-table.md) |
| `mods-install-via-marketplace` | The shared `settings.json` declares one marketplace, `claude-settings`. | [`decisions/mods-install-via-marketplace.md`](../decisions/mods-install-via-marketplace.md) |
| `mods-no-cli-key-headless` | No CLI API key for headless runs. | [`decisions/mods-no-cli-key-headless.md`](../decisions/mods-no-cli-key-headless.md) |
| `mods-tests-run-in-gates` | Merge session, 2026-10-13, 13:16 CDT. | [`decisions/mods-tests-run-in-gates.md`](../decisions/mods-tests-run-in-gates.md) |
| `mutant-cause-of-death` | CLAUDE.md says: "Trust a guard only once it goes red on the defect it guards." This entry is that sentence applied to the guard's own test harness. | [`decisions/mutant-cause-of-death.md`](../decisions/mutant-cause-of-death.md) |
| `one-shared-record-stamp` | CLAUDE.md: "Never allocate a numbered record on a branch. | [`decisions/one-shared-record-stamp.md`](../decisions/one-shared-record-stamp.md) |
| `opt-in-ci-templates-composite` | Owner approved six templates any repo can adopt. | [`decisions/opt-in-ci-templates-composite.md`](../decisions/opt-in-ci-templates-composite.md) |
| `plain-prose-lint` | Owner ruling, 2026-10-17 01:52 CDT: turn the STE lint into a plain-prose lint. | [`decisions/plain-prose-lint.md`](../decisions/plain-prose-lint.md) |
| `purge-keeps-younger-restore-ref` | The purge drops a restore ref only when both hold: | [`decisions/purge-keeps-younger-restore-ref.md`](../decisions/purge-keeps-younger-restore-ref.md) |
| `question-judge-reads-rulings` | Owner ruling, 2026-10-12 22:10 CDT: the question judge reads the repo's decision and deferred records and refuses a question the owner already settled. | [`decisions/question-judge-reads-rulings.md`](../decisions/question-judge-reads-rulings.md) |
| `question-outcome-check` | Owner ruling, 2026-10-13 19:48 CDT: the standard question format is a `Goal:` line first, then a `Problem:` sentence, then the options. | [`decisions/question-outcome-check.md`](../decisions/question-outcome-check.md) |
| `recovery-must-not-gate-on-its-own-state` | CLAUDE.md's Verification paragraph now states this rule. | [`decisions/recovery-must-not-gate-on-its-own-state.md`](../decisions/recovery-must-not-gate-on-its-own-state.md) |
| `review-cap-red-ci` | Owner ruling, 2026-10-13 14:50 CDT: "Split, then ask." | [`decisions/review-cap-red-ci.md`](../decisions/review-cap-red-ci.md) |
| `rulings-declare-kind` | Owner ruling, 2026-10-12. | [`decisions/rulings-declare-kind.md`](../decisions/rulings-declare-kind.md) |
| `silent-undo-check-design` | `lint/check_silent_undo.py` is the one home. | [`decisions/silent-undo-check-design.md`](../decisions/silent-undo-check-design.md) |
| `source-prose-lint-ships-dark` | CLAUDE.md says: "A guard that goes red when nothing is wrong is spent, because the reader learns to scroll past it." This entry names why `ste_lint.py`'s comment-and-docstring mode stays off by default. | [`decisions/source-prose-lint-ships-dark.md`](../decisions/source-prose-lint-ships-dark.md) |
| `stall-watch` | A background command can stop making progress. | [`decisions/stall-watch.md`](../decisions/stall-watch.md) |
| `stall-watch-stop-check` | A background shell can stay open after a turn ends. | [`decisions/stall-watch-stop-check.md`](../decisions/stall-watch-stop-check.md) |
| `stamp-cite-near-miss` | Where does the check for a wrongly wrapped cite live, and how does an agent learn the right form? | [`decisions/stamp-cite-near-miss.md`](../decisions/stamp-cite-near-miss.md) |
| `standing-merge-grant` | Owner ruling, 2026-10-10: the orchestrating session has standing merge authority in claude-settings. | [`decisions/standing-merge-grant.md`](../decisions/standing-merge-grant.md) |
| `stash-push-is-clone-wide` | CLAUDE.md says: "Set work aside with a commit on your own branch, never a stash." It also says: "A stash entry belongs to no branch. | [`decisions/stash-push-is-clone-wide.md`](../decisions/stash-push-is-clone-wide.md) |
| `ste-gate-fixes-not-nags` | The gate fixes first. | [`decisions/ste-gate-fixes-not-nags.md`](../decisions/ste-gate-fixes-not-nags.md) |
| `ste-lint-gloss-collapse` | `lint/ste_lint.py`'s `STE001` counts words per sentence. | [`decisions/ste-lint-gloss-collapse.md`](../decisions/ste-lint-gloss-collapse.md) |
| `stop-guardrail-became-a-command-hook` | The `type: agent` Stop hook in `settings.json` judged every turn for a silent change to a decision, gate, build-order, CLAUDE.md rule, or setting. | [`decisions/stop-guardrail-became-a-command-hook.md`](../decisions/stop-guardrail-became-a-command-hook.md) |
| `subagent-model-cap` | CLAUDE.md says: "Once ready, turn each rule below into a hook or check." This entry records how the worker-model rule is mechanized. | [`decisions/subagent-model-cap.md`](../decisions/subagent-model-cap.md) |
| `test-strategy-reset` | Owner ruling, 2026-10-14 17:14 CDT. | [`decisions/test-strategy-reset.md`](../decisions/test-strategy-reset.md) |
| `the-janitor-is-one-machine-wide-sweep` | Kind: process Home: janitor/sweep.py | [`decisions/the-janitor-is-one-machine-wide-sweep.md`](../decisions/the-janitor-is-one-machine-wide-sweep.md) |
| `unattended-sweep-stops-proven-orphans` | PR #132 added an orphaned-listener check to `janitor/sweep.py`. | [`decisions/unattended-sweep-stops-proven-orphans.md`](../decisions/unattended-sweep-stops-proven-orphans.md) |
| `wsl-allow-list` | Owner ruling, 2026-10-13 15:20: "fixed test list is fine; surf the web for a consensus first". | [`decisions/wsl-allow-list.md`](../decisions/wsl-allow-list.md) |

## Build designs

| Slug | Gist | Link |
|---|---|---|
| `agents-get-standing-rules` | Owner, 2026-10-12: a SubagentStart hook injects them. | [`decisions/agents-get-standing-rules.md`](../decisions/agents-get-standing-rules.md) |
| `an-agent-outside-its-home-tree-must-stop` | An agent outside its home tree must stop | [`decisions/an-agent-outside-its-home-tree-must-stop.md`](../decisions/an-agent-outside-its-home-tree-must-stop.md) |
| `bare-merge-asks` | Orchestrator call, lane bare-gh-merge-ask. | [`decisions/bare-merge-asks.md`](../decisions/bare-merge-asks.md) |
| `ci-wait-reads-run-status` | Owner, 2026-10-16 01:47 CDT: "Status read only." Neither program runs `gh run watch`. | [`decisions/ci-wait-reads-run-status.md`](../decisions/ci-wait-reads-run-status.md) |
| `claude-md-change-is-flagged` | Owner, 2026-10-16 03:27 CDT: "Report only." (Feedback item fb-claude-md-flag: "how can i confirm an agent does not just edit claude.md without asking me first".) | [`decisions/claude-md-change-is-flagged.md`](../decisions/claude-md-change-is-flagged.md) |
| `deleted-record-keeps-its-number` | Settled by the owner. | [`decisions/deleted-record-keeps-its-number.md`](../decisions/deleted-record-keeps-its-number.md) |
| `git-env-set-denied` | No. | [`decisions/git-env-set-denied.md`](../decisions/git-env-set-denied.md) |
| `guard-reads-wrapped-commands` | Kind: build Plan: decisions/guard-reads-wrapped-commands.md#the-change (all) Home: hooks/guard_core.py | [`decisions/guard-reads-wrapped-commands.md`](../decisions/guard-reads-wrapped-commands.md) |
| `guard-split-by-family` | Owner, 2026-10-12 and 2026-10-13: | [`decisions/guard-split-by-family.md`](../decisions/guard-split-by-family.md) |
| `handoff-hooks-wave-2` | Owner ruling, 2026-10-13 11:20 CDT: build all three in claude-settings. | [`decisions/handoff-hooks-wave-2.md`](../decisions/handoff-hooks-wave-2.md) |
| `install-hooks-whole` | The installer writes each non-guard file to a temp name in the same folder, then renames it over the target. | [`decisions/install-hooks-whole.md`](../decisions/install-hooks-whole.md) |
| `liveness-read-is-platform-specific-and-unreadable-is-not-death` | `hooks/guard.py`'s liveness oracle (`_process_start_ms`, `session_is_live`, `worktree_live_session`) folded two different facts into one answer. | [`decisions/liveness-read-is-platform-specific-and-unreadable-is-not-death.md`](../decisions/liveness-read-is-platform-specific-and-unreadable-is-not-death.md) |
| `merge-follows-the-prs-base` | Settled by the owner, written down 2026-10-07. | [`decisions/merge-follows-the-prs-base.md`](../decisions/merge-follows-the-prs-base.md) |
| `merge-lock-names-its-holder` | Settled by the owner. | [`decisions/merge-lock-names-its-holder.md`](../decisions/merge-lock-names-its-holder.md) |
| `merge-net-retry` | Owner, 2026-10-13, about 16:25 CDT: "Retry 3 times." | [`decisions/merge-net-retry.md`](../decisions/merge-net-retry.md) |
| `merge-notice-checks-the-report` | CLAUDE.md: "A guard that goes red when nothing is wrong is spent, because the reader learns to scroll past it." And: trust a guard only once it goes red on the defect it guards. | [`decisions/merge-notice-checks-the-report.md`](../decisions/merge-notice-checks-the-report.md) |
| `merge-reinstalls-from-main` | Owner, 2026-10-11, owner, 2026-10-15 (the pinned checkout), and owner, 2026-10-15 17:40 CDT (the install switch): | [`decisions/merge-reinstalls-from-main.md`](../decisions/merge-reinstalls-from-main.md) |
| `merge-waits-on-every-check` | Settled by the owner, written down 2026-10-01. | [`decisions/merge-waits-on-every-check.md`](../decisions/merge-waits-on-every-check.md) |
| `owner-feedback-inbox` | Owner ruling, 2026-10-13, from an interview in the claude-settings audit session. | [`decisions/owner-feedback-inbox.md`](../decisions/owner-feedback-inbox.md) |
| `plain-diff-mod-limits` | The mod sends a diff to `$.model.complete` only for a file that passes the secret filter. | [`decisions/plain-diff-mod-limits.md`](../decisions/plain-diff-mod-limits.md) |
| `prune-cases-skip-without-symlink-privilege` | Prune cases skip when this account cannot make a real symlink | [`decisions/prune-cases-skip-without-symlink-privilege.md`](../decisions/prune-cases-skip-without-symlink-privilege.md) |
| `records-index-at-merge` | Owner ruling, 2026-10-14 10:59 and 13:18 CDT. | [`decisions/records-index-at-merge.md`](../decisions/records-index-at-merge.md) |
| `rm-path-wrapper` | Owner, 2026-10-11 ("Yes, only for Claude sessions"): `bin/rm` sits ahead of the real `rm` on PATH. | [`decisions/rm-path-wrapper.md`](../decisions/rm-path-wrapper.md) |
| `session-board-mod-limits` | Owner intent: stop typing "status?" into many sessions. | [`decisions/session-board-mod-limits.md`](../decisions/session-board-mod-limits.md) |
| `split-segments-comment-rule` | `hooks/guard.py:split_segments` tracked single and double quotes. | [`decisions/split-segments-comment-rule.md`](../decisions/split-segments-comment-rule.md) |
| `stash-stack-is-a-shared-subject` | CLAUDE.md says: "Never run `git stash` ... | [`decisions/stash-stack-is-a-shared-subject.md`](../decisions/stash-stack-is-a-shared-subject.md) |
| `sweep-shuts-down-idle-simulators` | Owner rulings, 2026-10-10. | [`decisions/sweep-shuts-down-idle-simulators.md`](../decisions/sweep-shuts-down-idle-simulators.md) |

## Unsorted decisions

| Slug | Gist | Link |
|---|---|---|
| `a-kill-by-pid-needs-an-owned-pid` | CLAUDE.md says: "Never kill a process you did not start." The guard denied a kill by name or by pattern. | [`decisions/a-kill-by-pid-needs-an-owned-pid.md`](../decisions/a-kill-by-pid-needs-an-owned-pid.md) |
| `adoptions-declined-2026-09-28` | A review of public Claude Code configs and native features proposed these. | [`decisions/adoptions-declined-2026-09-28.md`](../decisions/adoptions-declined-2026-09-28.md) |
| `bare-bash-on-windows-can-resolve-to-the-wsl-stub` | `hooks/test_config_watch.py`'s bypass cases handed `subprocess.run(["bash", "-c", command], ...)` a bare command name. | [`decisions/bare-bash-on-windows-can-resolve-to-the-wsl-stub.md`](../decisions/bare-bash-on-windows-can-resolve-to-the-wsl-stub.md) |
| `bash-path-breaks-only-when-the-snapshot-breaks` | The Bash tool's PATH breaks only when its shell snapshot breaks | [`decisions/bash-path-breaks-only-when-the-snapshot-breaks.md`](../decisions/bash-path-breaks-only-when-the-snapshot-breaks.md) |
| `branch-delete-wrong-cause-was-a-filename-collision` | `decisions/branch-delete-wrong-cause-on-windows-unexplained.md` named a real defect and said its cause stayed unexplained. | [`decisions/branch-delete-wrong-cause-was-a-filename-collision.md`](../decisions/branch-delete-wrong-cause-was-a-filename-collision.md) |
| `browser-prompts-are-the-apps` | Owner, 2026-10-11: no. | [`decisions/browser-prompts-are-the-apps.md`](../decisions/browser-prompts-are-the-apps.md) |
| `builders-cannot-edit-tests` | Builders cannot edit tests | [`decisions/builders-cannot-edit-tests.md`](../decisions/builders-cannot-edit-tests.md) |
| `ci-spend-rules` | Skill steps 1 and 11 to 14 hold these rules. | [`decisions/ci-spend-rules.md`](../decisions/ci-spend-rules.md) |
| `ci-wall-time-cuts` | The owner chose cuts A to D on 2026-10-07. | [`decisions/ci-wall-time-cuts.md`](../decisions/ci-wall-time-cuts.md) |
| `copy-mode-overwrites-no-backup` | Owner, 2026-10-03: in copy mode, an installer overwrites its own old copy. | [`decisions/copy-mode-overwrites-no-backup.md`](../decisions/copy-mode-overwrites-no-backup.md) |
| `docs-only-prs-skip-code-suites` | `hooks/test_install_src.sh` takes case names as arguments and runs only those. | [`decisions/docs-only-prs-skip-code-suites.md`](../decisions/docs-only-prs-skip-code-suites.md) |
| `docs-only-prs-skip-review` | Docs-only pull requests skip the reviewer | [`decisions/docs-only-prs-skip-review.md`](../decisions/docs-only-prs-skip-review.md) |
| `frozen-path-resolves-shell-vars` | Rule 7 resolves shell variables before it matches a write target | [`decisions/frozen-path-resolves-shell-vars.md`](../decisions/frozen-path-resolves-shell-vars.md) |
| `hooks-share-the-transcript-reader` | Four hooks each carried their own copy of the same transcript readers. | [`decisions/hooks-share-the-transcript-reader.md`](../decisions/hooks-share-the-transcript-reader.md) |
| `known-bad-input-proves-the-gate` | A `gate` row cites a `test` id (`path::name`, `path::Class.name`) or a `setting` value. | [`decisions/known-bad-input-proves-the-gate.md`](../decisions/known-bad-input-proves-the-gate.md) |
| `main-branch-protection` | main branch protection | [`decisions/main-branch-protection.md`](../decisions/main-branch-protection.md) |
| `merge-config-defaults` | Must a repo have `.github/stamp.json` before the merge tool works in it? | [`decisions/merge-config-defaults.md`](../decisions/merge-config-defaults.md) |
| `one-entry-per-question` | On 2026-09-29 the owner ruled that a decision entry answers one question, and a changed ruling rewrites that entry. | [`decisions/one-entry-per-question.md`](../decisions/one-entry-per-question.md) |
| `playwright-browsers-path` | No. | [`decisions/playwright-browsers-path.md`](../decisions/playwright-browsers-path.md) |
| `playwright-install-once` | Owner, 2026-10-11 (rule `playwright-install` in `hooks/guard.py`): | [`decisions/playwright-install-once.md`](../decisions/playwright-install-once.md) |
| `precompact-handoff` | Auto-compact drops detail. | [`decisions/precompact-handoff.md`](../decisions/precompact-handoff.md) |
| `predicate-is-the-act` | CLAUDE.md says: "Fix the cause, not the symptom." It also says: "Check whether the primitive exists before building a workaround." This entry records why the markdown sweep stopped reading command text, and what that rule means for the next gate. | [`decisions/predicate-is-the-act.md`](../decisions/predicate-is-the-act.md) |
| `repeal-the-no-prefix-report-rule` | CLAUDE.md's Reports paragraph said: | [`decisions/repeal-the-no-prefix-report-rule.md`](../decisions/repeal-the-no-prefix-report-rule.md) |
| `reuse-needs-checkout-proof` | Lanes run in separate worktrees of one clone. | [`decisions/reuse-needs-checkout-proof.md`](../decisions/reuse-needs-checkout-proof.md) |
| `rm-on-a-variable-needs-a-guard` | Owner, 2026-10-11 ("Ship guard now, hook later"): | [`decisions/rm-on-a-variable-needs-a-guard.md`](../decisions/rm-on-a-variable-needs-a-guard.md) |
| `session-end-sweep-is-disarmed-until-liveness-is-proven` | The `SessionEnd` hook in `settings.json` runs `janitor/session_end_sweep.py`. | [`decisions/session-end-sweep-is-disarmed-until-liveness-is-proven.md`](../decisions/session-end-sweep-is-disarmed-until-liveness-is-proven.md) |
| `stale-safe-force-push` | CLAUDE.md says: "Judge every rule, check, and design by the outcome for the person the software serves." The outcome here: the owner gets no prompt for a safe push, and no push overwrites newer remote work with a stale copy. | [`decisions/stale-safe-force-push.md`](../decisions/stale-safe-force-push.md) |
| `ux-house-rules` | Owner ruling, 2026-10-11: "build a ux folder". | [`decisions/ux-house-rules.md`](../decisions/ux-house-rules.md) |
| `verdict-reads-runner-markers` | Owner, 2026-10-11 ("start the verdict lane"): | [`decisions/verdict-reads-runner-markers.md`](../decisions/verdict-reads-runner-markers.md) |
| `which-start-shapes-outlive-the-agent-on-windows` | This entry is step 1 of a plan. | [`decisions/which-start-shapes-outlive-the-agent-on-windows.md`](../decisions/which-start-shapes-outlive-the-agent-on-windows.md) |
| `worktree-setup-is-per-repo` | Owner, 2026-10-10: no. | [`decisions/worktree-setup-is-per-repo.md`](../decisions/worktree-setup-is-per-repo.md) |

## Debts

| Slug | Gist | Link |
|---|---|---|
| `bg-end-false-alarms` | The rule splits script names on `:` and `-`, so `build:dev` and `test-watch-ci` read as servers. | [`debts/bg-end-false-alarms.md`](../debts/bg-end-false-alarms.md) |
| `bg-end-roster-gaps` | The roster is a closed list. | [`debts/bg-end-roster-gaps.md`](../debts/bg-end-roster-gaps.md) |
| `ci-wake-lists-runs-once` | `ci_wake.wait_for` lists the head's CI runs again until a run that ran is judged. | [`debts/ci-wake-lists-runs-once.md`](../debts/ci-wake-lists-runs-once.md) |
| `cmd-c-script-skips-kill` | `cmd /c taskkill /F /IM node.exe` is allowed. | [`debts/cmd-c-script-skips-kill.md`](../debts/cmd-c-script-skips-kill.md) |
| `cp-into-frozen-dir` | Measured on main: `cp /tmp/x <config>/hooks/`, `cp -t <config>/hooks /tmp/x`, `cp -t<config>/hooks /tmp/x` and `cp --target-directory=<config>/hooks /tmp/x` are allowed. | [`debts/cp-into-frozen-dir.md`](../debts/cp-into-frozen-dir.md) |
| `dead-run-extended-lock-blocks` | A run that dies after a lock extension leaves a lock that expires up to 1200 s (a 900 s wait plus the 300 s margin) after the extension. | [`debts/dead-run-extended-lock-blocks.md`](../debts/dead-run-extended-lock-blocks.md) |
| `env-file-rule-false-alarms` | `ag -f` and `ack -f` refuse now, though `-f` is a boolean in those tools. | [`debts/env-file-rule-false-alarms.md`](../debts/env-file-rule-false-alarms.md) |
| `finished-agent-lock-holds-tree` | A finished agent's worktree can hold the lock `claude agent agent-<id> (pid N)`, with no start time. | [`debts/finished-agent-lock-holds-tree.md`](../debts/finished-agent-lock-holds-tree.md) |
| `finished-agent-shells-keep-tree` | A finished agent's own shells, such as a dev server, have the live host as parent. | [`debts/finished-agent-shells-keep-tree.md`](../debts/finished-agent-shells-keep-tree.md) |
| `git-rm-cached-false-alarm` | `git rm -rf --cached .` denies. | [`debts/git-rm-cached-false-alarm.md`](../debts/git-rm-cached-false-alarm.md) |
| `guard-timeout-fails-open` | If the PreToolUse guard times out or crashes, Claude Code lets the call run. | [`debts/guard-timeout-fails-open.md`](../debts/guard-timeout-fails-open.md) |
| `inplace-edit-under-0-9-flagged` | A branch can edit a line that main only added. | [`debts/inplace-edit-under-0-9-flagged.md`](../debts/inplace-edit-under-0-9-flagged.md) |
| `judge-cap-drops-old-rulings` | Measured 2026-10-14 (review round 1): 87 rulings, 100,887 chars uncapped. | [`debts/judge-cap-drops-old-rulings.md`](../debts/judge-cap-drops-old-rulings.md) |
| `merge-head-race-remains` | The race between a push and `gh pr ready` remains. | [`debts/merge-head-race-remains.md`](../debts/merge-head-race-remains.md) |
| `node-file-server-unchecked` | `node <file>` under `run_in_background` is not refused without an `until:` note. | [`debts/node-file-server-unchecked.md`](../debts/node-file-server-unchecked.md) |
| `pr-ready-unguarded` | The `draft-pr` guard rule reads only the create command and the MCP create tool. | [`debts/pr-ready-unguarded.md`](../debts/pr-ready-unguarded.md) |
| `prompt-hooks-fail-open` | Prompt hooks (Agent, AskUserQuestion, Edit and Write under `decisions/`, SendMessage) can deny, but the docs give them no `onFailure`. | [`debts/prompt-hooks-fail-open.md`](../debts/prompt-hooks-fail-open.md) |
| `push-report-before-checks` | A session can report a push as done before its checks finish. | [`debts/push-report-before-checks.md`](../debts/push-report-before-checks.md) |
| `records-page-gen-false-alarm` | One call can run the generator and then a `git commit` that holds the page. | [`debts/records-page-gen-false-alarm.md`](../debts/records-page-gen-false-alarm.md) |
| `report-on-empty-turn-unchecked` | The report gate returns early when nothing landed, so it cannot see a report written on such a turn. | [`debts/report-on-empty-turn-unchecked.md`](../debts/report-on-empty-turn-unchecked.md) |
| `sb-auto-approve-unseen` | An auto-approve mode can answer an "ask" with no person present. | [`debts/sb-auto-approve-unseen.md`](../debts/sb-auto-approve-unseen.md) |
| `sb-command-turn-unknown` | It is unknown whether a prompt sent from a command starts a turn in the app. | [`debts/sb-command-turn-unknown.md`](../debts/sb-command-turn-unknown.md) |
| `sb-pane-untested` | The pane draw is untested in the desktop app. | [`debts/sb-pane-untested.md`](../debts/sb-pane-untested.md) |
| `sb-process-desktop-unknown` | The API notes `$.process` as CLI only. | [`debts/sb-process-desktop-unknown.md`](../debts/sb-process-desktop-unknown.md) |
| `sb-store-not-shared` | The store is per plugin and per config folder. | [`debts/sb-store-not-shared.md`](../debts/sb-store-not-shared.md) |
| `sendmessage-judge-blind-recvs` | The busy-state layer reads an agent id, a `uds:` address, `main` and `*` as unseen, so it allows. | [`debts/sendmessage-judge-blind-recvs.md`](../debts/sendmessage-judge-blind-recvs.md) |
| `server-wrappers-unread` | The `background-end` rule does not read some wrappers and forms, so a background server behind them is not refused without an `until:` note. | [`debts/server-wrappers-unread.md`](../debts/server-wrappers-unread.md) |
| `shell-write-miss-spaced-target` | `cat > "dir with space/.claude/settings.json"` writes the settings file, but the reader splits the quoted path on its space, and no fragment of it follows the `>`. | [`debts/shell-write-miss-spaced-target.md`](../debts/shell-write-miss-spaced-target.md) |
| `silent-undo-oracle-hides-cause` | When the records page generator fails, is missing, or reports a problem, the silent-undo check reports only "hunk reversed" for `docs/records.md` and discards the generator's stderr. | [`debts/silent-undo-oracle-hides-cause.md`](../debts/silent-undo-oracle-hides-cause.md) |
| `slug-cite-gloss-unchecked` | The report gate checks only `D<n>`-style ids for a short gloss. | [`debts/slug-cite-gloss-unchecked.md`](../debts/slug-cite-gloss-unchecked.md) |
| `split-reader-misses-cd-forms` | `split_segments` does not model `$'...'` ANSI-C quoting, `$(...)`, or backtick substitution. | [`debts/split-reader-misses-cd-forms.md`](../debts/split-reader-misses-cd-forms.md) |
| `stall-message-delivery-unproven` | No run shows that a Stop systemMessage reaches the model. | [`debts/stall-message-delivery-unproven.md`](../debts/stall-message-delivery-unproven.md) |
| `stall-message-repeats-every-stop` | There is no dedupe. | [`debts/stall-message-repeats-every-stop.md`](../debts/stall-message-repeats-every-stop.md) |
| `stall-open-job-no-age-ceiling` | Open jobs have no age ceiling. | [`debts/stall-open-job-no-age-ceiling.md`](../debts/stall-open-job-no-age-ceiling.md) |
| `stamp-scan-frontmatter-links` | The near-miss scan does not skip frontmatter or link targets. | [`debts/stamp-scan-frontmatter-links.md`](../debts/stamp-scan-frontmatter-links.md) |
| `stash-reminder-text-outside-repo` | The harness worktree reminder still tells a worker to push a tagged entry. | [`debts/stash-reminder-text-outside-repo.md`](../debts/stash-reminder-text-outside-repo.md) |
| `stdin-python-read-as-code` | A quoted cap key or frozen path piped into an interpreter denies: `python hooks/guard.py`, `python run.py`, `python -`, and wrappers such as `head`, `tail`, `sort`, `VAR=x python`, `python3.12`, `py` or `verdict python`. | [`debts/stdin-python-read-as-code.md`](../debts/stdin-python-read-as-code.md) |
| `ste-comment-gt-mask-early` | A comment that holds `>` ends its mask early. | [`debts/ste-comment-gt-mask-early.md`](../debts/ste-comment-gt-mask-early.md) |
| `ste-edit-fence-blind` | The Edit and MultiEdit path tracks only plain fences and front matter. | [`debts/ste-edit-fence-blind.md`](../debts/ste-edit-fence-blind.md) |
| `timeout-moved-server-unchecked` | A foreground server that the harness moves to background at its 120 s timeout is not checked. | [`debts/timeout-moved-server-unchecked.md`](../debts/timeout-moved-server-unchecked.md) |
| `verdict-skip-reads-pass` | If a run prints SKIP lines and exits 0, `bin/verdict` prints only PASS. | [`debts/verdict-skip-reads-pass.md`](../debts/verdict-skip-reads-pass.md) |

## Deferred

| Slug | Gist | Link |
|---|---|---|
| `banchi-build-steps` | Banchi build steps are not claimed by the shared stamp | [`deferred/banchi-build-steps.md`](../deferred/banchi-build-steps.md) |
| `build-disk-guard` | Low-disk guard refuses builds below 20 GB | [`deferred/build-disk-guard.md`](../deferred/build-disk-guard.md) |
| `measured-time-table` | A measured-time table for machine steps | [`deferred/measured-time-table.md`](../deferred/measured-time-table.md) |
| `merge-retarget-before-merge` | A base change just before the merge command is not caught | [`deferred/merge-retarget-before-merge.md`](../deferred/merge-retarget-before-merge.md) |
| `playwright-rows-measure` | A measure of the Playwright guard rows | [`deferred/playwright-rows-measure.md`](../deferred/playwright-rows-measure.md) |
| `push-head-mismatch-trap` | A push of HEAD to a branch of another name is not guarded yet | [`deferred/push-head-mismatch-trap.md`](../deferred/push-head-mismatch-trap.md) |
| `refusal-route-around-guard` | No guard stops an agent that routes around a refusal | [`deferred/refusal-route-around-guard.md`](../deferred/refusal-route-around-guard.md) |
| `sharables-adopts-the-stamp` | claude-sharables adopts the stamp, not a claim-command setting | [`deferred/sharables-adopts-the-stamp.md`](../deferred/sharables-adopts-the-stamp.md) |
| `stamp-shallow-depth-two` | The stamp check does not read a shallow checkout | [`deferred/stamp-shallow-depth-two.md`](../deferred/stamp-shallow-depth-two.md) |
| `ste-into-agent-briefs` | The STE writing standard moves into agent briefs | [`deferred/ste-into-agent-briefs.md`](../deferred/ste-into-agent-briefs.md) |
| `three-skill-findings` | The compliance-check skill has two findings that wait | [`deferred/three-skill-findings.md`](../deferred/three-skill-findings.md) |
| `undo-check-rename-alarm` | The silent-undo check flags a rename that main edited | [`deferred/undo-check-rename-alarm.md`](../deferred/undo-check-rename-alarm.md) |
| `windows-temp-sweep` | A sweep of idle session temp folders on Windows | [`deferred/windows-temp-sweep.md`](../deferred/windows-temp-sweep.md) |

## Plans

| Slug | Gist | Link |
|---|---|---|
| `shared-merge-tool` | Plan: the shared merge tool | [`plans/shared-merge-tool.md`](../plans/shared-merge-tool.md) |
