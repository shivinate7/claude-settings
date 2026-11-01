# Records index

This page lists every record in this repo: the rules in `CLAUDE.md`, and the files in `docs/decisions/`, `docs/debts/` and `docs/plans/`. A script writes it. Do not edit it by hand.

The merge tool writes this page again when a pull request merges, so a pull request need not carry a fresh one. To write it by hand, run `python3 lint/hook_catalog.py` from the claude-settings checkout, with `--root` set to this repo. The check on the default branch fails when the page is stale.

Each row has the slug, the first sentence of the record, and a link to it. A record that a ruling overrules is rewritten in place, so no row holds old text.

## Mandates

| Slug | Gist | Link |
|---|---|---|
| `outcomes-judge-by-outcome` | Judge every rule, check, and design by the outcome for the person the software serves. | [`CLAUDE.md`](../CLAUDE.md) |
| `outcomes-decision-is-argument` | Treat a recorded decision as an argument, not a law. | [`CLAUDE.md`](../CLAUDE.md) |
| `outcomes-stale-decision-protocol` | When a decision looks stale, name the record and the sentence. | [`CLAUDE.md`](../CLAUDE.md) |
| `outcomes-tests-are-statements` | A failing test is a claim, not law. | [`CLAUDE.md`](../CLAUDE.md) |
| `outcomes-grant-covers-named-act` | My grant covers the act it names, never a variant. | [`CLAUDE.md`](../CLAUDE.md) |
| `outcomes-mechanize-rules` | Once ready, turn each rule below into a hook or check. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-pick-mode-from-request` | Pick the session's shape from my request: solo, one lane, or coordinator (`session-tiers`, the session shapes). | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-solo-builds-short-edit-list` | Solo: the request is a short list of edits with nothing to run in parallel. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-solo-reviews-logic-diffs-only` | In solo, a fresh reviewer reads the diff before merge only when it touches a rule's behaviour, a guard's or check's verdict, or program logic. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-solo-grows-switch-to-orchestrate` | A shape can grow: solo to one lane, one lane to coordinator. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-orchestrator-never-builds` | Every session that spawns agents is an orchestrator. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-one-role-per-agent` | Each agent is one role: builder, reviewer, designer, design reviewer, or Explore, never two. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-sonnet-is-the-default` | A workflow agent takes the builder or reviewer role through `agentType`. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-sonnet-is-the-ceiling` | Sonnet is the ceiling, except Plan, the built-in advisor (`advisorModel`), the designer, the design reviewer, and a builder's third try (`roles-third-round-steps-up`), which run Opus. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-opus-shaped-say-so` | When a task is Opus-shaped (long-horizon, whole-codebase, or many-hour autonomous work), say so in one line before you dispatch, name why, and offer the switch. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-opus-override-guarded` | Owner raises Opus. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-brief-contents` | A brief carries the task, the files, governing rulings, failure classes from `outcomes-tests-are-statements`, and the check that proves the task done—in the fewest words. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-each-layer-proves-once` | Each layer proves a change once. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-review-cap-three` | A change gets at most three review rounds. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-findings-are-debts-or-notes` | A known gap is a debt only if Claude is likely to hit it in normal work. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-third-round-steps-up` | Third try: Opus. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-resume-by-name` | Resume a dead agent by name, never fresh. | [`CLAUDE.md`](../CLAUDE.md) |
| `parallelism-each-own-checkout` | Fan tasks out to agents now, each in its own checkout. | [`CLAUDE.md`](../CLAUDE.md) |
| `parallelism-own-lane-orchestrator` | A read-only workflow agent shares the caller's checkout. | [`CLAUDE.md`](../CLAUDE.md) |
| `parallelism-no-mid-task-talk` | Never let lanes talk mid-task. | [`CLAUDE.md`](../CLAUDE.md) |
| `parallelism-argue-max-parallelism` | Argue "at max parallelism" by naming the open lanes, never by assuming the claim. | [`CLAUDE.md`](../CLAUDE.md) |
| `parallelism-no-guessed-lane-cap` | A brief or plan never caps lanes on its own, by a guessed number such as "one or two at a time" or "at most N lanes". | [`CLAUDE.md`](../CLAUDE.md) |
| `parallelism-keep-going` | When a lane ends, start in the same turn each queued item the owner asked for whose questions are all answered. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-no-destructive-git` | No destructive git. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-archive-then-delete` | Push an unmerged branch to `archive/<branch>` on origin, or a new archive name if taken. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-no-machine-wide-kill` | Kill only yours. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-one-checkout-per-agent` | Give one checkout to each concurrent agent. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-own-ports-data` | A branch switch is a whole-tree act. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-confirm-before-write` | Confirm which checkout and branch you stand in before any git write or merge. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-reverify-after-incident` | Re-verify every edit after an incident. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-delete-names-absolute-path` | A delete names its target as an absolute or quoted-variable path, never after a cd. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-main-only-by-pr` | Move main only by pull request, merged only when I name the act, or under a repo grant. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-never-merge-failing-ci` | Never merge failing CI. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-no-merge-during-batch-ci` | While a batch's integration PR has a CI run in progress, nothing merges to main, by any session or by me. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-ci-wait-checks-in` | A session that waits on CI sets a timed check-in when it starts to wait, and again after each red job, each wider apart. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-ci-done-comment-wakes` | A run that ends red posts one PR comment, which wakes the session that watches the PR (`ci-done-comment`). | [`CLAUDE.md`](../CLAUDE.md) |
| `git-never-discard-output` | Keep command output. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-remedy-never-names-target` | A refusal's printed remedy never names the forbidden target. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-slug-then-claim-number` | Never allocate a numbered record on a branch. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-cite-by-id` | Ids, not paths. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-record-own-file-per-kind` | Give each record its own file, one folder per kind. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-one-record-per-question` | One record per question. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-integration-branch-merge` | Batch lane PRs that pass their local checks into one integration branch. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-screens-verdict` | If the repo has screens, check each screen at every size and theme it ships in. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-browser-login-only-needed` | Prefer a headless or isolated browser over my own, and use my login only when needed. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-announce-own-screen` | Before a window or a screen capture lands on my screen, say so in one line. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-trust-guard-after-red` | Trust a guard only once it goes red on the defect it guards. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-cry-wolf-guard-is-spent` | A guard that goes red when nothing is wrong is spent, because the reader learns to scroll past it. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-green-proves-only-its-fixtures` | A green check proves only its platform and the states its fixtures build. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-recovery-independent-of-state` | A recovery control must not depend on the state it recovers, or it fails on the one day it is needed. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-verify-against-repo` | Verify long work against the repo, not your status line. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-never-dry-run-refusal-list` | Never dry-run a refusal list. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-newest-that-passes` | Take the newest version that passes its checks. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-checked-reader-for-numbers` | If this repo lints markdown, give every published number and path a checked reader. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-report-unknown-reads` | Verify a claim before you rely on it, a document's own claims too. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-never-load-whole-doc` | Never load a long document whole. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-verdict-not-stream` | A verification command's answer is its verdict, not its stream. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-run-through-verdict` | Run every verification command through `verdict <cmd>`, which prints the verdict and keeps the full output in a log. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-point-brief-at-files` | Point a brief at files. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-read-report-not-transcript` | Read an agent's report, never its transcript. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-compacting-keep-essentials` | When compacting, keep the files, the commands, each ruling's home, and the pid and port of each server still running. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-folder-rules-load-by-path` | Move a CLAUDE.md section that matters only under one folder to a path-scoped rule. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-read-map-first` | Before you answer how code in a repo works, read its `docs/map/`. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-never-guess-answer` | Never guess an answer the code should give you. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-port-keeps-behaviour` | A port or redesign keeps the existing app's behaviour as the default. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-surface-ambiguity` | Surface ambiguity instead of resolving it silently. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-never-drop-item-silently` | Never drop an item without saying so. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-one-home-per-capability` | Give each capability one home, and call it from everywhere. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-allow-list-is-the-constant` | A guard's or check's allow list must point at the constant the code emits, never a copy of it. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-guard-needs-incident` | Build a new guard or check rule only against a named incident, a measured risk, or a likely risk: one Claude is likely to hit in normal work. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-fix-cause-not-symptom` | Fix the cause, not the symptom. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-scanner-respects-strings` | Scan source code with the language's own parser or tokenizer when the repo has one. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-land-design-or-abandon` | A capability no user can reach is not built. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-memory-is-short-term` | Memory stays on, as short-term notes. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-comments-say-why` | Comment only what complex code does and why. | [`CLAUDE.md`](../CLAUDE.md) |
| `speak-cite-id-plus-gloss` | Give every id a short plain name the first time it appears, like "D12, short titles for records". | [`CLAUDE.md`](../CLAUDE.md) |
| `speak-one-name-per-thing` | `GLOSSARY.md`, beside this file, gives each workflow thing one name. | [`CLAUDE.md`](../CLAUDE.md) |
| `speak-never-explain-in-paragraph` | Never explain a rule in a paragraph. | [`CLAUDE.md`](../CLAUDE.md) |
| `speak-rewrite-superseded-in-place` | Rewrite superseded text in place. | [`CLAUDE.md`](../CLAUDE.md) |
| `output-write-in-ste` | Write plainly: short sentences, one term per meaning, no filler. | [`CLAUDE.md`](../CLAUDE.md) |
| `output-never-paste-passing-output` | Rules for replies to me, and not to agents, live in the `shiv-stylisms` output style. | [`CLAUDE.md`](../CLAUDE.md) |
| `output-bring-decisions-as-question` | Bring my choices as a question with options and a recommendation. | [`CLAUDE.md`](../CLAUDE.md) |
| `output-answer-has-a-home` | An answer to a question I bring is a ruling. | [`CLAUDE.md`](../CLAUDE.md) |
| `questions-go-to-owner` | Bring each question to me. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-order-of-labels` | Done, Deviations, Input Needed, Next. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-done-format` | Done: one line per item, BUILT, RECORDED, or OTHER. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-done-names-models` | A Done item that agents built or reviewed names each one's role and model, such as "(builder sonnet, reviewer sonnet)". | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-drop-unused-label` | Drop a label that does not apply. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-name-unstarted-items` | An orchestrator's report holds an `Unstarted:` line under Next: each queued item with every question answered that it left unstarted, with its reason, or `none`. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-no-report-when-nothing-landed` | No report when nothing landed. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-batch-pace-numbers` | At each batch merge, the report also gives four pace numbers, as OTHER items under Done. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-offer-sweep-after-merge` | When a session's last PR has merged and no lane is open, its final report offers one command under Next: `python3 ~/.claude/janitor/sweep.py --root <repo> --attended --fast`, preview first, then with `--confirm`. | [`CLAUDE.md`](../CLAUDE.md) |

## Rulings

| Slug | Gist | Link |
|---|---|---|
| `a-branch-is-redundant-by-patch-not-by-ancestry` | The sweep (`the-janitor-is-one-machine-wide-sweep`, the janitor is one machine-wide sweep) reaps a local branch when the branch is an ancestor of the base, or when `git cherry <base> <branch>` prints no `+`. | [`docs/decisions/a-branch-is-redundant-by-patch-not-by-ancestry.md`](../docs/decisions/a-branch-is-redundant-by-patch-not-by-ancestry.md) |
| `a-kill-by-pid-needs-an-owned-pid` | Rule `shared-trees-no-machine-wide-kill` says to kill only your own processes. | [`docs/decisions/a-kill-by-pid-needs-an-owned-pid.md`](../docs/decisions/a-kill-by-pid-needs-an-owned-pid.md) |
| `act-in-place` | Owner, 2026-10-28 13:01 CDT (waiting-page gripe on item 47): when an item asks the owner to act, everything he needs sits on the item. | [`docs/decisions/act-in-place.md`](../docs/decisions/act-in-place.md) |
| `action-pins-follow-sessions` | Owner, 2026-10-26 (gripe on the degen Duo batch): "doesn't this just mean CI is old? | [`docs/decisions/action-pins-follow-sessions.md`](../docs/decisions/action-pins-follow-sessions.md) |
| `adoptions-declined-2026-09-28` | The owner declined each candidate below. | [`docs/decisions/adoptions-declined-2026-09-28.md`](../docs/decisions/adoptions-declined-2026-09-28.md) |
| `agent-end-reap-stops-what-a-finished-agent-left` | The goal: when an agent ends, each process it left under its own worktree stops. | [`docs/decisions/agent-end-reap-stops-what-a-finished-agent-left.md`](../docs/decisions/agent-end-reap-stops-what-a-finished-agent-left.md) |
| `agent-model-cap` | Each agent role has its own model and effort, in the table below. | [`docs/decisions/agent-model-cap.md`](../docs/decisions/agent-model-cap.md) |
| `agent-powershell-tool` | With Claude Code's PowerShell tool. | [`docs/decisions/agent-powershell-tool.md`](../docs/decisions/agent-powershell-tool.md) |
| `agent-worktree-discard-is-noted` | Owner rulings: 2026-10-03 (the agent-owned worktree), 2026-10-11 ("Allow per-file", the untracked link), 2026-10-17 11:40 CDT (the per-file allow outside `.claude/worktrees/` stands). | [`docs/decisions/agent-worktree-discard-is-noted.md`](../docs/decisions/agent-worktree-discard-is-noted.md) |
| `agents-wait-with-monitor` | Owner, 2026-10-11 and 2026-10-12: the `Monitor` tool, Claude Code's own wait-once tool, is allowed. | [`docs/decisions/agents-wait-with-monitor.md`](../docs/decisions/agents-wait-with-monitor.md) |
| `ask-commands-run-alone` | An agent never chains a command that needs the owner's answer onto other commands in one shell call (owner, 2026-10-14). | [`docs/decisions/ask-commands-run-alone.md`](../docs/decisions/ask-commands-run-alone.md) |
| `audit-rework-order` | Owner, 2026-10-16 10:50 CDT. | [`docs/decisions/audit-rework-order.md`](../docs/decisions/audit-rework-order.md) |
| `auto-mode-owner-acts` | Owner, 2026-10-30 16:24 CDT, relayed by the coordinator session: the auto-mode classifier keeps refusing the coordinator's routine acts, which the owner always grants. | [`docs/decisions/auto-mode-owner-acts.md`](../docs/decisions/auto-mode-owner-acts.md) |
| `background-needs-end-note` | Owner, 2026-10-13 23:41 CDT: "End condition at start." | [`docs/decisions/background-needs-end-note.md`](../docs/decisions/background-needs-end-note.md) |
| `bare-bash-on-windows-can-resolve-to-the-wsl-stub` | Python code on Windows never hands `subprocess.run` a bare `"bash"` or `"gh"`. | [`docs/decisions/bare-bash-on-windows-can-resolve-to-the-wsl-stub.md`](../docs/decisions/bare-bash-on-windows-can-resolve-to-the-wsl-stub.md) |
| `blind-briefs-use-a-template` | Owner, 2026-10-26 22:58 CDT, on the mailaudit Duo mockups: "not a single one of them tried to break the mold". | [`docs/decisions/blind-briefs-use-a-template.md`](../docs/decisions/blind-briefs-use-a-template.md) |
| `browser-prompts-are-the-apps` | Owner, 2026-10-11: claude-settings cannot disable the built-in browser pane's approval prompts on outside sites. | [`docs/decisions/browser-prompts-are-the-apps.md`](../docs/decisions/browser-prompts-are-the-apps.md) |
| `build-dirs-reaped-at-agent-end` | Owner, 2026-10-11: the agent-end reap also deletes build folders. | [`docs/decisions/build-dirs-reaped-at-agent-end.md`](../docs/decisions/build-dirs-reaped-at-agent-end.md) |
| `builders-cannot-edit-tests` | A builder that cannot pass a test must not delete, skip or rewrite it. | [`docs/decisions/builders-cannot-edit-tests.md`](../docs/decisions/builders-cannot-edit-tests.md) |
| `ci-job-caps` | Owner, 2026-10-27, roadmap step c95: a full CI run must be red only when something is broken, never because a job ran out of time. | [`docs/decisions/ci-job-caps.md`](../docs/decisions/ci-job-caps.md) |
| `ci-unknown-is-red` | A lint that cannot read its input prints UNKNOWN. | [`docs/decisions/ci-unknown-is-red.md`](../docs/decisions/ci-unknown-is-red.md) |
| `cite-by-id-refuses-unread-file` | Owner, 2026-10-17 11:40 CDT (guard audit, finding 7): the guard refuses `git commit -F <file>` when it cannot read the file at hook time. | [`docs/decisions/cite-by-id-refuses-unread-file.md`](../docs/decisions/cite-by-id-refuses-unread-file.md) |
| `claude-md-shrink` | Owner, 2026-10-16 23:53 CDT and 2026-10-17 00:40 CDT: | [`docs/decisions/claude-md-shrink.md`](../docs/decisions/claude-md-shrink.md) |
| `config-watch-fast-exit` | Owner, 2026-10-20. | [`docs/decisions/config-watch-fast-exit.md`](../docs/decisions/config-watch-fast-exit.md) |
| `copy-mode-overwrites-no-backup` | Owner: in copy mode, an installer overwrites its own old copy and keeps no backup. | [`docs/decisions/copy-mode-overwrites-no-backup.md`](../docs/decisions/copy-mode-overwrites-no-backup.md) |
| `cull-rules` | Owner ruling, 2026-10-17 11:56 CDT. | [`docs/decisions/cull-rules.md`](../docs/decisions/cull-rules.md) |
| `decision-watch-mod-limits` | The decision watch runs as a mod on the app's own login, so an expired CLI login no longer silences it. | [`docs/decisions/decision-watch-mod-limits.md`](../docs/decisions/decision-watch-mod-limits.md) |
| `decisions-reach-a-clickable-pick` | Roadmap step c118, 2026-10-27. | [`docs/decisions/decisions-reach-a-clickable-pick.md`](../docs/decisions/decisions-reach-a-clickable-pick.md) |
| `default-branch-read-order` | Owner, 2026-10-16: the branch-delete rule, the janitor sweep and the push guard read the default branch in this order. | [`docs/decisions/default-branch-read-order.md`](../docs/decisions/default-branch-read-order.md) |
| `dependabot-security-only` | Owner, 2026-10-16: security updates only. | [`docs/decisions/dependabot-security-only.md`](../docs/decisions/dependabot-security-only.md) |
| `design-agents` | Owner, 2026-10-26 (waiting-page item 15, answer b): a lane that touches a screen gets two design agents, and both run Opus. | [`docs/decisions/design-agents.md`](../docs/decisions/design-agents.md) |
| `design-skills` | Owner, 2026-10-10: three third-party skills apply to any repo with screens. | [`docs/decisions/design-skills.md`](../docs/decisions/design-skills.md) |
| `detached-launch-refused` | The `detached-launch` rule in `hooks/guard.py` refuses a command that starts a process and detaches it from the session. | [`docs/decisions/detached-launch-refused.md`](../docs/decisions/detached-launch-refused.md) |
| `docs-only-prs-skip-review` | Owner, 2026-09-26: a pull request that changes only prose or docs, and touches no rule, guard, check or product code, gets no reviewer pass. | [`docs/decisions/docs-only-prs-skip-review.md`](../docs/decisions/docs-only-prs-skip-review.md) |
| `draft-until-reviewed` | Owner, 2026-10-10 and 2026-10-13: every PR opens as a draft, and CI skips draft PRs. | [`docs/decisions/draft-until-reviewed.md`](../docs/decisions/draft-until-reviewed.md) |
| `fewest-words-mandate` | Fewest words, most of all in front-end copy | [`docs/decisions/fewest-words-mandate.md`](../docs/decisions/fewest-words-mandate.md) |
| `frozen-path-resolves-shell-vars` | Before rule 7 (frozen-path) matches the target of a shell write, it reads the command left to right. | [`docs/decisions/frozen-path-resolves-shell-vars.md`](../docs/decisions/frozen-path-resolves-shell-vars.md) |
| `git-env-set-refused` | No agent command may set `GIT_DIR`, `GIT_WORK_TREE` or `GIT_INDEX_FILE`. | [`docs/decisions/git-env-set-refused.md`](../docs/decisions/git-env-set-refused.md) |
| `guard-command-position` | One resolver in `hooks/guard_core.py` finds the command word for every rule. | [`docs/decisions/guard-command-position.md`](../docs/decisions/guard-command-position.md) |
| `guard-guards-mistakes-only` | Owner, 2026-10-17 09:07 CDT, "widen": every guard and check stops Claude's mistakes, never an attacker. | [`docs/decisions/guard-guards-mistakes-only.md`](../docs/decisions/guard-guards-mistakes-only.md) |
| `guard-hooks-fail-closed` | Owner, 2026-10-12: a guard whose script or python is missing refuses the call. | [`docs/decisions/guard-hooks-fail-closed.md`](../docs/decisions/guard-hooks-fail-closed.md) |
| `guard-linked-node-modules` | Yes. | [`docs/decisions/guard-linked-node-modules.md`](../docs/decisions/guard-linked-node-modules.md) |
| `guard-log-read-weekly` | Owner, 2026-10-13. | [`docs/decisions/guard-log-read-weekly.md`](../docs/decisions/guard-log-read-weekly.md) |
| `guard-that-cries-wolf-is-spent` | CLAUDE.md: "Trust a guard only once it goes red on the defect it guards." The other half: a guard that goes red when nothing is wrong is spent, because the reader stops reading it. | [`docs/decisions/guard-that-cries-wolf-is-spent.md`](../docs/decisions/guard-that-cries-wolf-is-spent.md) |
| `haiku-prompt-hooks` | **Prompt hooks judge rules that no script can parse.** Each refuses the call when it finds a breach (owner ruling 2026-10-07). | [`docs/decisions/haiku-prompt-hooks.md`](../docs/decisions/haiku-prompt-hooks.md) |
| `hold-unsafe-after-round-3` | Owner, 2026-10-15 12:00 CDT. | [`docs/decisions/hold-unsafe-after-round-3.md`](../docs/decisions/hold-unsafe-after-round-3.md) |
| `hook-if-filters` | Owner, 2026-10-21. | [`docs/decisions/hook-if-filters.md`](../docs/decisions/hook-if-filters.md) |
| `hook-inputs-carry-token-counts` | c151 is the plan item "compaction timing reads message tokens, not total context". | [`docs/decisions/hook-inputs-carry-token-counts.md`](../docs/decisions/hook-inputs-carry-token-counts.md) |
| `hooks-share-the-transcript-reader` | The Stop hooks read the transcript through one module, `lint/_transcript.py`. | [`docs/decisions/hooks-share-the-transcript-reader.md`](../docs/decisions/hooks-share-the-transcript-reader.md) |
| `install-hooks-whole` | No running session judges a call with a missing, short or mixed set of hook files. | [`docs/decisions/install-hooks-whole.md`](../docs/decisions/install-hooks-whole.md) |
| `ios-mac-install-first` | Owner, 2026-10-22 19:40 CDT, for every app: when the phone is on Wi-Fi and the Mac can install, install from the Mac. | [`docs/decisions/ios-mac-install-first.md`](../docs/decisions/ios-mac-install-first.md) |
| `ios-ship-is-one-shared-tool` | Owner, 2026-10-25: one tool, `bin/ios-ship`, builds and ships the owner's iOS apps from the Mac. | [`docs/decisions/ios-ship-is-one-shared-tool.md`](../docs/decisions/ios-ship-is-one-shared-tool.md) |
| `item-field-rendered` | A field on a waiting item is for the owner to read. | [`docs/decisions/item-field-rendered.md`](../docs/decisions/item-field-rendered.md) |
| `lane-by-slug` | Owner, 2026-10-13 14:13 CDT, relayed by the oversight session: the guard refuses a session number that names a lane, such as `N20` or `(N16)`. | [`docs/decisions/lane-by-slug.md`](../docs/decisions/lane-by-slug.md) |
| `lanes-run-no-full-ci-job` | Owner, 2026-10-27 (waiting page item 27, option a): a lane runs only the suites its change touches. | [`docs/decisions/lanes-run-no-full-ci-job.md`](../docs/decisions/lanes-run-no-full-ci-job.md) |
| `lanes-start-as-agents` | Roadmap step c107 (an orchestrator starts its lanes with no click from the owner), 2026-10-27: an orchestrator starts each lane as a background agent. | [`docs/decisions/lanes-start-as-agents.md`](../docs/decisions/lanes-start-as-agents.md) |
| `list-form-subprocess-ignores-a-path-shim-on-windows` | A blind-command fixture cannot shadow a real executable for a list-form subprocess call on Windows. | [`docs/decisions/list-form-subprocess-ignores-a-path-shim-on-windows.md`](../docs/decisions/list-form-subprocess-ignores-a-path-shim-on-windows.md) |
| `local-time-central` | Owner, 2026-10-12: a session tells the owner times in US Central (America/Chicago), DST-aware, 24-hour clock. | [`docs/decisions/local-time-central.md`](../docs/decisions/local-time-central.md) |
| `main-branch-protection` | `main` of shivinate7/claude-settings requires one check: `all-jobs-passed`, the job in `.github/workflows/checks.yml` that runs the shared action `actions/all-jobs-passed`. | [`docs/decisions/main-branch-protection.md`](../docs/decisions/main-branch-protection.md) |
| `map-facts-are-checked` | Owner, 2026-10-30 16:09 CDT. | [`docs/decisions/map-facts-are-checked.md`](../docs/decisions/map-facts-are-checked.md) |
| `map-skill-lives-here` | Owner, 2026-10-16: `skills/plain-english-map/` in claude-settings is the one home of the skill. | [`docs/decisions/map-skill-lives-here.md`](../docs/decisions/map-skill-lives-here.md) |
| `memory-is-never-a-rulings-only-home` | The owner's rulings must reach a tracked file. | [`docs/decisions/memory-is-never-a-rulings-only-home.md`](../docs/decisions/memory-is-never-a-rulings-only-home.md) |
| `merge-deletes-batch-lanes` | Owner, 2026-10-19 12:14 CDT: each merge deletes the lane branches its batch took in. | [`docs/decisions/merge-deletes-batch-lanes.md`](../docs/decisions/merge-deletes-batch-lanes.md) |
| `merge-needs-current-base` | Roadmap step c97, filed 2026-10-27; step c150, 2026-10-28: a batch merges only after a green run that holds for the current main. | [`docs/decisions/merge-needs-current-base.md`](../docs/decisions/merge-needs-current-base.md) |
| `mods-deferred-table` | These mods stay deferred recordings on the repo. | [`docs/decisions/mods-deferred-table.md`](../docs/decisions/mods-deferred-table.md) |
| `mods-install-via-marketplace` | The shared `settings.json` declares one marketplace, `claude-settings`, from the GitHub repo `shivinate7/claude-settings`, with `autoUpdate` set to true. | [`docs/decisions/mods-install-via-marketplace.md`](../docs/decisions/mods-install-via-marketplace.md) |
| `mods-no-cli-key-headless` | No CLI API key for headless runs. | [`docs/decisions/mods-no-cli-key-headless.md`](../docs/decisions/mods-no-cli-key-headless.md) |
| `mutation-report-scores-suites` | `hooks/mutate_guard.py --report` scores the suites of other verdict-deciding files with mechanical mutants, on demand. | [`docs/decisions/mutation-report-scores-suites.md`](../docs/decisions/mutation-report-scores-suites.md) |
| `no-merge-during-batch-ci` | The owner ruled on Oct 28 at 13:36 CDT: no one merges to main while a batch's CI runs. | [`docs/decisions/no-merge-during-batch-ci.md`](../docs/decisions/no-merge-during-batch-ci.md) |
| `no-merge-onto-red-main` | The red-main check: the merge tool refuses `merge <pr> --confirm` while the base branch's latest completed run has a red job. | [`docs/decisions/no-merge-onto-red-main.md`](../docs/decisions/no-merge-onto-red-main.md) |
| `notes-merge-union` | `.gitattributes` gives `docs/debts/notes.md` git's built-in `merge=union` driver. | [`docs/decisions/notes-merge-union.md`](../docs/decisions/notes-merge-union.md) |
| `one-layout-every-repo` | Every repo keeps each kind of file in the same place. | [`docs/decisions/one-layout-every-repo.md`](../docs/decisions/one-layout-every-repo.md) |
| `one-shared-record-stamp` | One shared parser in claude-settings handles every repo's record format. | [`docs/decisions/one-shared-record-stamp.md`](../docs/decisions/one-shared-record-stamp.md) |
| `opt-in-ci-templates-composite` | Seven templates any repo can adopt live in one home and one shape: a composite action under `actions/<name>/`, or a plain file where the template is no CI step. | [`docs/decisions/opt-in-ci-templates-composite.md`](../docs/decisions/opt-in-ci-templates-composite.md) |
| `option-keys-are-letters` | The waiting page shows an option by its position, as a letter: the first option is A, the second B (`skills/waiting-page/page.html`, symbol `letterOf`). | [`docs/decisions/option-keys-are-letters.md`](../docs/decisions/option-keys-are-letters.md) |
| `opus-grant-expires` | An Opus agent is enabled for one repository, on the owner's grant in chat (`roles-opus-override-guarded`). | [`docs/decisions/opus-grant-expires.md`](../docs/decisions/opus-grant-expires.md) |
| `owner-feedback-inbox` | A hook writes every owner message to a per-session inbox. | [`docs/decisions/owner-feedback-inbox.md`](../docs/decisions/owner-feedback-inbox.md) |
| `owner-judge-test` | A session asks the owner a decision only when he can judge it from what he already knows. | [`docs/decisions/owner-judge-test.md`](../docs/decisions/owner-judge-test.md) |
| `plain-prose-lint` | The STE lint is a plain-prose lint. | [`docs/decisions/plain-prose-lint.md`](../docs/decisions/plain-prose-lint.md) |
| `playwright-browsers-path` | No command sets PLAYWRIGHT_BROWSERS_PATH to work around a missing browser build. | [`docs/decisions/playwright-browsers-path.md`](../docs/decisions/playwright-browsers-path.md) |
| `playwright-install-once` | Rule `playwright-install` in `hooks/guard.py`: | [`docs/decisions/playwright-install-once.md`](../docs/decisions/playwright-install-once.md) |
| `port-keeps-behaviour` | Owner, 2026-10-27 15:32 CDT: when a session ports or redesigns an existing app, the working app already answers most questions. | [`docs/decisions/port-keeps-behaviour.md`](../docs/decisions/port-keeps-behaviour.md) |
| `precompact-handoff` | Auto-compact drops detail. | [`docs/decisions/precompact-handoff.md`](../docs/decisions/precompact-handoff.md) |
| `predicate-is-the-act` | Judge a guard by the act it must catch, never by the spelling of the act. | [`docs/decisions/predicate-is-the-act.md`](../docs/decisions/predicate-is-the-act.md) |
| `premise-format` | A premise is a statement, not a fact. | [`docs/decisions/premise-format.md`](../docs/decisions/premise-format.md) |
| `question-form` | Owner steer, 2026-10-30 12:50 CDT: a question to the owner has one form and one guard, for the chat question box (`AskUserQuestion`) and for a waiting-page item write. | [`docs/decisions/question-form.md`](../docs/decisions/question-form.md) |
| `question-reviewer-agent-hook` | Owner rulings, 2026-10-22 10:18 CDT: | [`docs/decisions/question-reviewer-agent-hook.md`](../docs/decisions/question-reviewer-agent-hook.md) |
| `questions-go-to-owner` | Owner, 2026-10-26: a session with a question brings it to the owner. | [`docs/decisions/questions-go-to-owner.md`](../docs/decisions/questions-go-to-owner.md) |
| `recovery-independent-of-state` | A recovery control exists for the moment its own precondition is false. | [`docs/decisions/recovery-independent-of-state.md`](../docs/decisions/recovery-independent-of-state.md) |
| `reply-judge-samples-never-refuses` | The Stop reply judge is `hooks/reply_judge.py`, a command hook (owner ruling 2026-10-12), because a prompt hook cannot exit on a field in code. | [`docs/decisions/reply-judge-samples-never-refuses.md`](../docs/decisions/reply-judge-samples-never-refuses.md) |
| `repo-kind-and-caution` | Owner, 2026-10-27 00:30 and 00:31 CDT, roadmap step c115: about 1 in 5 home sessions refuse to log in to the owner's own Home Assistant or KEF speakers. | [`docs/decisions/repo-kind-and-caution.md`](../docs/decisions/repo-kind-and-caution.md) |
| `reuse-needs-checkout-proof` | Lanes run in separate worktrees of one clone. | [`docs/decisions/reuse-needs-checkout-proof.md`](../docs/decisions/reuse-needs-checkout-proof.md) |
| `rework-leaves-page` | An open item on the waiting page is one the owner can answer now. | [`docs/decisions/rework-leaves-page.md`](../docs/decisions/rework-leaves-page.md) |
| `rm-after-cd-names-absolute-path` | Rule `rm-after-cd` in `hooks/guard.py` refuses a recursive `rm` (`-r`, `-R`, `--recursive`) with a relative target, when a `cd` joined by `;`, `&&` or a newline came before it in the same command. | [`docs/decisions/rm-after-cd-names-absolute-path.md`](../docs/decisions/rm-after-cd-names-absolute-path.md) |
| `rm-on-a-variable-needs-a-guard` | Bypass-mode sessions must not wait on the owner for Claude Code's critical-path `rm` prompt (owner ruling 2026-10-11). | [`docs/decisions/rm-on-a-variable-needs-a-guard.md`](../docs/decisions/rm-on-a-variable-needs-a-guard.md) |
| `rulings-declare-kind` | A decision record that a pull request adds or changes must say what kind each ruling is: a build task, or a process change. | [`docs/decisions/rulings-declare-kind.md`](../docs/decisions/rulings-declare-kind.md) |
| `safe-stop-queues-one-prompt` | `/safe-stop` is a command of the session-board mod (`session-board-mod-limits`, session-board keeps small records). | [`docs/decisions/safe-stop-queues-one-prompt.md`](../docs/decisions/safe-stop-queues-one-prompt.md) |
| `same-check-kinds` | Owner, 2026-10-30 15:03 CDT, waiting item 87: every owner repo runs the same kinds of checks, judged by the same outcomes. | [`docs/decisions/same-check-kinds.md`](../docs/decisions/same-check-kinds.md) |
| `session-board-mod-limits` | The session-board mod (`mods/session-board`, commands `/board` and `/safe-stop`) gives one view of all sessions and a safe stopping point, with no typing of "status?" into each one. | [`docs/decisions/session-board-mod-limits.md`](../docs/decisions/session-board-mod-limits.md) |
| `session-end-sweep-is-disarmed-until-liveness-is-proven` | The `SessionEnd` hook in `settings.json` runs `janitor/session_end_sweep.py`. | [`docs/decisions/session-end-sweep-is-disarmed-until-liveness-is-proven.md`](../docs/decisions/session-end-sweep-is-disarmed-until-liveness-is-proven.md) |
| `session-tiers` | Owner rulings, 2026-10-28 CDT unless dated. | [`docs/decisions/session-tiers.md`](../docs/decisions/session-tiers.md) |
| `shared-resource-owner` | Owner, 2026-10-27 13:22 CDT (cmsg_01DoF7thf3iq2Srr1UsfXgh2FS8R88VGL2A75ER5mnDyai), roadmap step c140: the HA Green box (4 GB) is loaded by home, degen and mailaudit. | [`docs/decisions/shared-resource-owner.md`](../docs/decisions/shared-resource-owner.md) |
| `shoot-is-one-shared-command` | Owner, 2026-10-17: build one screenshot script in this repo. | [`docs/decisions/shoot-is-one-shared-command.md`](../docs/decisions/shoot-is-one-shared-command.md) |
| `silent-undo-check-design` | `lint/check_silent_undo.py` is the one home. | [`docs/decisions/silent-undo-check-design.md`](../docs/decisions/silent-undo-check-design.md) |
| `sim-boot-is-verified` | The record hook of `sweep-shuts-down-idle-simulators` (ruling 1) checks each device that a `simctl boot` or an MCP `launch` took from `Shutdown` to `Booted`. | [`docs/decisions/sim-boot-is-verified.md`](../docs/decisions/sim-boot-is-verified.md) |
| `source-prose-lint-ships-dark` | The comment-and-docstring mode of `ste_lint.py` stays off by default (`--source-prose` and `check_source`). | [`docs/decisions/source-prose-lint-ships-dark.md`](../docs/decisions/source-prose-lint-ships-dark.md) |
| `spawns-use-no-window` | Owner, 2026-10-19 16:20 CDT: helper programs that hooks, mods and tools start use the "no window" option. | [`docs/decisions/spawns-use-no-window.md`](../docs/decisions/spawns-use-no-window.md) |
| `stale-safe-force-push` | The owner gets no prompt for a safe push, and no push overwrites newer remote work with a stale copy. | [`docs/decisions/stale-safe-force-push.md`](../docs/decisions/stale-safe-force-push.md) |
| `stall-watch` | The session learns within minutes that a background command stalled, and diagnoses the cause. | [`docs/decisions/stall-watch.md`](../docs/decisions/stall-watch.md) |
| `standing-merge-grant` | Owner rulings, 2026-10-10, 2026-10-29 16:47 CDT, 2026-10-29 20:33 CDT and 2026-10-30 15:06 CDT: the coordinator holds a standing merge grant in claude-settings and in the owner's other repos. | [`docs/decisions/standing-merge-grant.md`](../docs/decisions/standing-merge-grant.md) |
| `stash-stack-is-a-shared-subject` | CLAUDE.md says: "A stash entry belongs to no branch." The guard reads `git stash` against the whole stack, not only the working tree. | [`docs/decisions/stash-stack-is-a-shared-subject.md`](../docs/decisions/stash-stack-is-a-shared-subject.md) |
| `ste-guard-fixes-not-nags` | Owner, 2026-10-22 10:10 CDT: `settings.json` wires no STE write guard (`ste_gate.py`) and no markdown sweep (`md_sweep.py`). | [`docs/decisions/ste-guard-fixes-not-nags.md`](../docs/decisions/ste-guard-fixes-not-nags.md) |
| `stop-guardrail-became-a-command-hook` | The Stop guardrail is never a `type: agent` hook. | [`docs/decisions/stop-guardrail-became-a-command-hook.md`](../docs/decisions/stop-guardrail-became-a-command-hook.md) |
| `sweep-shuts-down-idle-simulators` | Sessions boot simulators. The sweep stops idle ones. | [`docs/decisions/sweep-shuts-down-idle-simulators.md`](../docs/decisions/sweep-shuts-down-idle-simulators.md) |
| `task-names-its-check` | A session never hands the owner an act that a session can do. | [`docs/decisions/task-names-its-check.md`](../docs/decisions/task-names-its-check.md) |
| `test-strategy-reset` | A test must not fail on runner speed. | [`docs/decisions/test-strategy-reset.md`](../docs/decisions/test-strategy-reset.md) |
| `test-temp-standard` | Each test run writes temp files only in its own run folder, under one temp root per repo, and removes that folder at teardown. | [`docs/decisions/test-temp-standard.md`](../docs/decisions/test-temp-standard.md) |
| `the-janitor-is-one-machine-wide-sweep` | The sweep deletes a local branch that holds no unique work. | [`docs/decisions/the-janitor-is-one-machine-wide-sweep.md`](../docs/decisions/the-janitor-is-one-machine-wide-sweep.md) |
| `unattended-sweep-stops-proven-orphans` | **What an unattended run can stop.** A `--confirm` run, run by the SessionEnd hook or the scheduled task, can send one signal to one process. | [`docs/decisions/unattended-sweep-stops-proven-orphans.md`](../docs/decisions/unattended-sweep-stops-proven-orphans.md) |
| `uniform-over-variants` | Owner, 2026-10-27 12:51 CDT, topic t18 (one home, then variants): when a repo differs from a shared format, the repo changes to match it. | [`docs/decisions/uniform-over-variants.md`](../docs/decisions/uniform-over-variants.md) |
| `ux-house-rules` | The UX rules that every repo with screens shares, beyond the three third-party sets, live in `docs/design/`. | [`docs/decisions/ux-house-rules.md`](../docs/decisions/ux-house-rules.md) |
| `when-a-worktree-may-be-removed` | Four idle limits. | [`docs/decisions/when-a-worktree-may-be-removed.md`](../docs/decisions/when-a-worktree-may-be-removed.md) |
| `windows-temp-sweep` | A session's temp folder goes after its transcript is idle 24 hours | [`docs/decisions/windows-temp-sweep.md`](../docs/decisions/windows-temp-sweep.md) |
| `worktree-setup-is-per-repo` | Each repo sets up the untracked state (node_modules, venv, caches) of a worktree itself. | [`docs/decisions/worktree-setup-is-per-repo.md`](../docs/decisions/worktree-setup-is-per-repo.md) |
| `wsl-allow-list` | The guard allows a WSL command only when every condition holds: | [`docs/decisions/wsl-allow-list.md`](../docs/decisions/wsl-allow-list.md) |

## Build designs

| Slug | Gist | Link |
|---|---|---|
| `agents-get-standing-rules` | Owner, 2026-10-12: a SubagentStart hook injects the standing rules, so a brief need not retype them. | [`docs/decisions/agents-get-standing-rules.md`](../docs/decisions/agents-get-standing-rules.md) |
| `an-agent-outside-its-home-tree-must-stop` | Each session writes only inside its own checkout. | [`docs/decisions/an-agent-outside-its-home-tree-must-stop.md`](../docs/decisions/an-agent-outside-its-home-tree-must-stop.md) |
| `bare-merge-asks` | Orchestrator call (lane bare-gh-merge-ask); the owner may rule otherwise. | [`docs/decisions/bare-merge-asks.md`](../docs/decisions/bare-merge-asks.md) |
| `catalog-cells-never-cut` | The cell cap in `docs/catalog.md` sits above the longest cell, so no cell is cut. | [`docs/decisions/catalog-cells-never-cut.md`](../docs/decisions/catalog-cells-never-cut.md) |
| `ci-wait-reads-run-status` | Owner, 2026-10-16 01:47 CDT ("Status read only") and 03:00 CDT ("Change them too"): no program and no agent runs `gh run watch`, in the foreground or the background. | [`docs/decisions/ci-wait-reads-run-status.md`](../docs/decisions/ci-wait-reads-run-status.md) |
| `claude-md-change-is-flagged` | Owner, 2026-10-16: report only, no hold. | [`docs/decisions/claude-md-change-is-flagged.md`](../docs/decisions/claude-md-change-is-flagged.md) |
| `compliance-defined` | Owner, 2026-10-31 15:04 CDT, waiting-page item 104: a claude-settings rule wins over a child repo's text on the same question, unless that text names the rule as a known exemption. | [`docs/decisions/compliance-defined.md`](../docs/decisions/compliance-defined.md) |
| `guard-reads-wrapped-commands` | The guards judge the command a wrapper runs, not the raw text. | [`docs/decisions/guard-reads-wrapped-commands.md`](../docs/decisions/guard-reads-wrapped-commands.md) |
| `hook-catalog-page` | `docs/catalog.md` lists every hook, judge, mod and skill. | [`docs/decisions/hook-catalog-page.md`](../docs/decisions/hook-catalog-page.md) |
| `install-refuses-linked-tree` | The installer refuses a linked worktree. | [`docs/decisions/install-refuses-linked-tree.md`](../docs/decisions/install-refuses-linked-tree.md) |
| `install-sh-stays-off-windows` | `install.sh` does nothing on Windows. | [`docs/decisions/install-sh-stays-off-windows.md`](../docs/decisions/install-sh-stays-off-windows.md) |
| `lanes-start-in-tool-worktrees` | Owner, 2026-10-21: refuse the hand-made lane worktree fully, and record which layer refused isolation. | [`docs/decisions/lanes-start-in-tool-worktrees.md`](../docs/decisions/lanes-start-in-tool-worktrees.md) |
| `machine-load-brake` | Owner, 2026-10-21 (spec), 2026-10-22 (foreground), 2026-10-23 (disk) and 2026-10-25 (CPU dropped: a 200 ms sample is noise; memory and disk are what stall a machine): a lane-start call reads the machine's load, and a busy or full machine refuses new lanes (disk is the smaller of a share and a GB cap). | [`docs/decisions/machine-load-brake.md`](../docs/decisions/machine-load-brake.md) |
| `merge-reinstalls-from-main` | The links in `~/.claude` point at one pinned checkout. | [`docs/decisions/merge-reinstalls-from-main.md`](../docs/decisions/merge-reinstalls-from-main.md) |
| `one-browser-setup-no-apt` | Roadmap step c78 (one shared browser-test setup), 2026-10-26: one composite action installs the browser-test setup for every repo, so a CI fix lands once. | [`docs/decisions/one-browser-setup-no-apt.md`](../docs/decisions/one-browser-setup-no-apt.md) |
| `owner-override` | The owner starts a prompt with the word `override`. | [`docs/decisions/owner-override.md`](../docs/decisions/owner-override.md) |
| `plain-diff-mod-limits` | The plain-diff mod (`mods/plain-diff`, command `/plain-diff`) sends a diff to `$.model.complete` only for a file that passes the secret filter. | [`docs/decisions/plain-diff-mod-limits.md`](../docs/decisions/plain-diff-mod-limits.md) |
| `post-merge-hook-is-a-fallback` | Owner, 2026-10-22: `install.ps1` writes its git post-merge hook only when it installs a copy, not a link. | [`docs/decisions/post-merge-hook-is-a-fallback.md`](../docs/decisions/post-merge-hook-is-a-fallback.md) |
| `records-index-at-merge` | Each repo that keeps records has one generated index page, `docs/records.md`. | [`docs/decisions/records-index-at-merge.md`](../docs/decisions/records-index-at-merge.md) |
| `rm-path-wrapper` | `bin/rm` sits ahead of the real `rm` on PATH, for Claude sessions only. | [`docs/decisions/rm-path-wrapper.md`](../docs/decisions/rm-path-wrapper.md) |
| `shell-scripts-check-out-lf` | Owner, 2026-10-21: `.gitattributes` forces LF on checkout for every file under `bin/` and `githooks/`, every `*.sh`, and `skills/impeccable/scripts/impeccable`. | [`docs/decisions/shell-scripts-check-out-lf.md`](../docs/decisions/shell-scripts-check-out-lf.md) |

## Debts

| Slug | Gist | Link |
|---|---|---|
| `agent-end-log-loses-row` | On Windows, test_parallel_writers_lose_no_row lost one of 24 rows (run 39086341296) though the same tree passed before. | [`docs/debts/agent-end-log-loses-row.md`](../docs/debts/agent-end-log-loses-row.md) |
| `agent-reports-with-live-watcher` | No check stops an agent that sends its final report while a Monitor or background task it started is still running. | [`docs/debts/agent-reports-with-live-watcher.md`](../docs/debts/agent-reports-with-live-watcher.md) |
| `banchi-build-steps` | A pending Banchi step is a line `` 0. `step <slug>` `` in a file in `docs/gates/steps/`. | [`docs/debts/banchi-build-steps.md`](../docs/debts/banchi-build-steps.md) |
| `bg-end-false-alarms` | The rule splits script names on `:` and `-`, so `build:dev` and `test-watch-ci` read as servers. | [`docs/debts/bg-end-false-alarms.md`](../docs/debts/bg-end-false-alarms.md) |
| `build-disk-guard` | Part 2 of `build-dirs-reaped-at-agent-end`, the low-disk build guard, is not built. | [`docs/debts/build-disk-guard.md`](../docs/debts/build-disk-guard.md) |
| `checks-job-near-timeout` | The checks job took 30.4 min slowest over 30 runs (median 22.1), 84% of its 36 min cap, on 2026-10-27. | [`docs/debts/checks-job-near-timeout.md`](../docs/debts/checks-job-near-timeout.md) |
| `ci-wake-export-gh-repo-unread` | ci_wake reads GH_REPO only as a command prefix. | [`docs/debts/ci-wake-export-gh-repo-unread.md`](../docs/debts/ci-wake-export-gh-repo-unread.md) |
| `ci-wake-gh-host-bare-repo` | For a github.com PR, ci_wake passes a bare -R owner/repo. | [`docs/debts/ci-wake-gh-host-bare-repo.md`](../docs/debts/ci-wake-gh-host-bare-repo.md) |
| `ci-wake-lists-runs-once` | `ci_wake.wait_for` lists the head's CI runs again until a run that ran is judged. | [`docs/debts/ci-wake-lists-runs-once.md`](../docs/debts/ci-wake-lists-runs-once.md) |
| `cloud-merge-moves-live-pin` | In a cloud session, `merge/install_from_main.sh` runs `bash "$pin/install.sh"` without a pipe, after each coordinator merge. | [`docs/debts/cloud-merge-moves-live-pin.md`](../docs/debts/cloud-merge-moves-live-pin.md) |
| `departs-word-list-limits` | `question-departs` reads a no-change word in the first clause of the change side. | [`docs/debts/departs-word-list-limits.md`](../docs/debts/departs-word-list-limits.md) |
| `exit-worktree-hook-unmeasured` | The guard clears a session-home record on an ExitWorktree call. | [`docs/debts/exit-worktree-hook-unmeasured.md`](../docs/debts/exit-worktree-hook-unmeasured.md) |
| `explain-accessvbom` | The owner wants to be talked through AccessVBOM, the Office setting "Trust access to the VBA project object model": what it does, its risk, and whether to turn it on. | [`docs/debts/explain-accessvbom.md`](../docs/debts/explain-accessvbom.md) |
| `ff-first-lane-not-a-tip` | `lane_tips` reads merge commits only. | [`docs/debts/ff-first-lane-not-a-tip.md`](../docs/debts/ff-first-lane-not-a-tip.md) |
| `finished-agent-shells-keep-tree` | A finished agent's own shells, such as a dev server, have the live host as parent. | [`docs/debts/finished-agent-shells-keep-tree.md`](../docs/debts/finished-agent-shells-keep-tree.md) |
| `fork-step-grants-read-roadmap` | In a fork worktree, the Opus step-grant lookup reads `origin/roadmap`, main's record branch. | [`docs/debts/fork-step-grants-read-roadmap.md`](../docs/debts/fork-step-grants-read-roadmap.md) |
| `frozen-dup-in-subshell` | From a frozen working folder (the live pin `<clone>-live`, or `~/.claude/hooks`), the frozen-path rule still refuses `x=$(ls 2>&1)`, `(ls 2>&1)`, a backtick form, and `ls 2>&1&`. | [`docs/debts/frozen-dup-in-subshell.md`](../docs/debts/frozen-dup-in-subshell.md) |
| `gitignore-skips-map-tests` | `ci-scope.sh` turns on only `code` for a `.gitignore` change. | [`docs/debts/gitignore-skips-map-tests.md`](../docs/debts/gitignore-skips-map-tests.md) |
| `guard-stdin-not-utf8` | `_force_utf8_streams` reconfigures stdout and stderr only. | [`docs/debts/guard-stdin-not-utf8.md`](../docs/debts/guard-stdin-not-utf8.md) |
| `hooks-to-mods-judges` | Plan step E has four parts. | [`docs/debts/hooks-to-mods-judges.md`](../docs/debts/hooks-to-mods-judges.md) |
| `inplace-edit-under-0-9-flagged` | A branch can edit a line that main only added. | [`docs/debts/inplace-edit-under-0-9-flagged.md`](../docs/debts/inplace-edit-under-0-9-flagged.md) |
| `install-checkout-flake` | On Windows CI two session-start freshness cases failed, then passed on rerun, twice on 2026-10-20: caseF1 in the morning (#527), and caseG1 at 23:00 (#533, run 39528566602; "expected ... | [`docs/debts/install-checkout-flake.md`](../docs/debts/install-checkout-flake.md) |
| `install-set-reads-held-file` | On Windows the install-set test reads a hook run's output file while another process still holds it, so the job fails with an IOException though the install is correct. | [`docs/debts/install-set-reads-held-file.md`](../docs/debts/install-set-reads-held-file.md) |
| `lane-cycle-delete-order` | `cut_lanes` deletes dependents first. | [`docs/debts/lane-cycle-delete-order.md`](../docs/debts/lane-cycle-delete-order.md) |
| `layout-legacy-repos` | The layout's `legacy-repos` map lets two named repos keep their `todo` kind in a place of their own: q_max at `specs/todo.md`, home at `records`. | [`docs/debts/layout-legacy-repos.md`](../docs/debts/layout-legacy-repos.md) |
| `linked-nm-prefix-workspace` | `-w`, `--workspace` and `--prefix` change the folder npm works in. | [`docs/debts/linked-nm-prefix-workspace.md`](../docs/debts/linked-nm-prefix-workspace.md) |
| `long-lived-head-lost-in-batch` | `cut_lanes` deletes any origin head whose sha is a lane tip. | [`docs/debts/long-lived-head-lost-in-batch.md`](../docs/debts/long-lived-head-lost-in-batch.md) |
| `measured-time-table` | `bin/verdict` logs no kind, seconds and exit per run, and no table keeps measured times. | [`docs/debts/measured-time-table.md`](../docs/debts/measured-time-table.md) |
| `merge-head-race-remains` | The race between a push and `gh pr ready` remains. | [`docs/debts/merge-head-race-remains.md`](../docs/debts/merge-head-race-remains.md) |
| `merge-records-stale-base` | `bin/merge` rebuilds the records page after the CI wait. | [`docs/debts/merge-records-stale-base.md`](../docs/debts/merge-records-stale-base.md) |
| `merge-silent-exit` | Twice on 2026-10-20 (#527 in the afternoon, #538 at 00:08 CDT on 10-21), the background shell that ran `bin/merge <pr> --confirm` exited rc 1 mid-wait and printed no reason. | [`docs/debts/merge-silent-exit.md`](../docs/debts/merge-silent-exit.md) |
| `nowindow-bin-no-fallback` | bin/verdict, bin/ste-changed, bin/ci-job and merge/launch.py import hooks/_nowindow.py with no fallback, so a copy-mode install that lands bin/ before hooks/ makes them fail. | [`docs/debts/nowindow-bin-no-fallback.md`](../docs/debts/nowindow-bin-no-fallback.md) |
| `nowindow-ctrl-c-orphans` | With CREATE_NO_WINDOW the child gets its own hidden console, so Ctrl-C may not reach grandchildren. | [`docs/debts/nowindow-ctrl-c-orphans.md`](../docs/debts/nowindow-ctrl-c-orphans.md) |
| `nowindow-fallback-silent` | A hook that falls back to plain subprocess says nothing, so the popups return unseen. | [`docs/debts/nowindow-fallback-silent.md`](../docs/debts/nowindow-fallback-silent.md) |
| `nowindow-git-prompt-hangs` | A git credential prompt on the terminal, from merge/merge.py sh(), has no console to show in, so it would wait with no end. | [`docs/debts/nowindow-git-prompt-hangs.md`](../docs/debts/nowindow-git-prompt-hangs.md) |
| `nowindow-scan-misses-os-system` | lint/test_no_window_spawn.py reads subprocess and Node child_process calls only. | [`docs/debts/nowindow-scan-misses-os-system.md`](../docs/debts/nowindow-scan-misses-os-system.md) |
| `npm-audit-fix-linked` | The rule judges only npm install, i, ci, update, uninstall and their aliases. | [`docs/debts/npm-audit-fix-linked.md`](../docs/debts/npm-audit-fix-linked.md) |
| `old-merge-tool-refuses-stamp` | A merge tool older than this change refuses main's `stamp.json`, which has the unknown field `keepBranches`. | [`docs/debts/old-merge-tool-refuses-stamp.md`](../docs/debts/old-merge-tool-refuses-stamp.md) |
| `pin-missing-files-no-install` | `merge/install_from_main.sh` treats a pin at main that has only missing tracked files as dirty: it exits 1 and installs nothing. | [`docs/debts/pin-missing-files-no-install.md`](../docs/debts/pin-missing-files-no-install.md) |
| `pinoff1-freshness-flaky` | Case pinoff1 expected one freshness line and got none, on a commit that changed only the records page (run 39080117103). | [`docs/debts/pinoff1-freshness-flaky.md`](../docs/debts/pinoff1-freshness-flaky.md) |
| `playwright-rows-measure` | Unmeasured: whether the Playwright rows in `hooks/test_guard.py` still stop a real mistake. | [`docs/debts/playwright-rows-measure.md`](../docs/debts/playwright-rows-measure.md) |
| `pr-ready-unguarded` | The `draft-pr` guard rule reads only the create command and the MCP create tool. | [`docs/debts/pr-ready-unguarded.md`](../docs/debts/pr-ready-unguarded.md) |
| `ps-command-misses-bash` | Guard rule `command-in-item` refuses a `powershell` string only for `&&`, `\|\|`, `<<`, `<<<`, `/dev/null` and `export`. | [`docs/debts/ps-command-misses-bash.md`](../docs/debts/ps-command-misses-bash.md) |
| `push-head-mismatch-trap` | `git push <remote> HEAD`, when the current branch tracks a branch of another name on that remote, pushes under the local branch's own name. | [`docs/debts/push-head-mismatch-trap.md`](../docs/debts/push-head-mismatch-trap.md) |
| `push-report-before-checks` | A session can report a push as done before its checks finish. | [`docs/debts/push-report-before-checks.md`](../docs/debts/push-report-before-checks.md) |
| `refresh-lock-untested` | The SessionStart refresh holds a lock directory in the config dir. | [`docs/debts/refresh-lock-untested.md`](../docs/debts/refresh-lock-untested.md) |
| `refusal-route-around-guard` | A hook refuses an Edit of a path, then the same agent writes the file with Bash and Python. | [`docs/debts/refusal-route-around-guard.md`](../docs/debts/refusal-route-around-guard.md) |
| `ruling-kind-vacuous-local-pass` | `lint/check_ruling_kind.py` checks only the committed diff against `origin/main`, so a run before the commit checks zero files and prints PASS. | [`docs/debts/ruling-kind-vacuous-local-pass.md`](../docs/debts/ruling-kind-vacuous-local-pass.md) |
| `session-home-lane-visit` | A top-level session whose `cwd` enters a non-agent lane tree gets a session-home record naming it, and a return to the primary does not clear it. | [`docs/debts/session-home-lane-visit.md`](../docs/debts/session-home-lane-visit.md) |
| `settled-question-unchecked` | A question that a decision or a debt already settles can reach the owner. | [`docs/debts/settled-question-unchecked.md`](../docs/debts/settled-question-unchecked.md) |
| `sharables-adopts-the-stamp` | claude-sharables claims record ids with its own `scripts/check_records.py --claim-ids --apply`. | [`docs/debts/sharables-adopts-the-stamp.md`](../docs/debts/sharables-adopts-the-stamp.md) |
| `skill-copy-no-typescript` | A copy of the skill folder outside the clone finds no `node_modules`, so `map-check.mjs` and `map-picture.mjs` cannot load `typescript` there. | [`docs/debts/skill-copy-no-typescript.md`](../docs/debts/skill-copy-no-typescript.md) |
| `squash-lane-branch-kept` | A squash-merged lane has no merge commit parent. | [`docs/debts/squash-lane-branch-kept.md`](../docs/debts/squash-lane-branch-kept.md) |
| `stale-step-blocked-lane` | The roadmap's stale-step row counts a session as live only when its status is RUNNING or IDLE. | [`docs/debts/stale-step-blocked-lane.md`](../docs/debts/stale-step-blocked-lane.md) |
| `stall-message-repeats-every-stop` | There is no dedupe. | [`docs/debts/stall-message-repeats-every-stop.md`](../docs/debts/stall-message-repeats-every-stop.md) |
| `stamp-shallow-depth-two` | `stamp.mjs --check` off the default branch needs `fetch-depth: 0`. | [`docs/debts/stamp-shallow-depth-two.md`](../docs/debts/stamp-shallow-depth-two.md) |
| `start-detached-not-main` | hooks/session_start.sh counts a detached checkout as on main only when HEAD equals local `refs/heads/main`. | [`docs/debts/start-detached-not-main.md`](../docs/debts/start-detached-not-main.md) |
| `step-shell-programs-partial` | Guard rule `command-in-item` reads a backtick span in a step as a shell line only when its first word is in a fixed program list. | [`docs/debts/step-shell-programs-partial.md`](../docs/debts/step-shell-programs-partial.md) |
| `test-guard-no-progress-line` | `hooks/test_guard.py` prints nothing for minutes, so the stall watch cuts off a healthy full run. | [`docs/debts/test-guard-no-progress-line.md`](../docs/debts/test-guard-no-progress-line.md) |
| `upgrade-strips-name-port` | The version 1 to 2 upgrade removes `:N` after a name whose extension is in `codeExtensions`. | [`docs/debts/upgrade-strips-name-port.md`](../docs/debts/upgrade-strips-name-port.md) |
| `verdict-pipe-drops-line` | `verdict <cmd> \| tail` keeps only the last lines, and a wrapper watching the pipe can read a stalled or false exit. | [`docs/debts/verdict-pipe-drops-line.md`](../docs/debts/verdict-pipe-drops-line.md) |
| `verdict-skip-reads-pass` | If a run prints SKIP lines and exits 0, `bin/verdict` prints only PASS. | [`docs/debts/verdict-skip-reads-pass.md`](../docs/debts/verdict-skip-reads-pass.md) |
| `wp-batch-reads-installed-copy` | `stale_pages.py` batch mode (no `--page`) compares each live page with the `page.html` installed at session start, not with claude-settings main. | [`docs/debts/wp-batch-reads-installed-copy.md`](../docs/debts/wp-batch-reads-installed-copy.md) |

## Plans

| Slug | Gist | Link |
|---|---|---|
| `o10-session-questions-page` | Plan: a page per session for questions waiting on the owner | [`docs/plans/o10-session-questions-page.md`](../docs/plans/o10-session-questions-page.md) |
| `shared-merge-tool` | Plan: the shared merge tool | [`docs/plans/shared-merge-tool.md`](../docs/plans/shared-merge-tool.md) |
