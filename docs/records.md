# Records index

This page lists every record in this repo: the rules in `CLAUDE.md`, and the files in `decisions/`, `debts/` and `plans/`. A script writes it. Do not edit it by hand.

The merge tool writes this page again when a pull request merges, so a pull request need not carry a fresh one. To write it by hand, run `python3 lint/hook_catalog.py` from the claude-settings checkout, with `--root` set to this repo. The check on the default branch fails when the page is stale.

Each row has the slug, the first sentence of the record, and a link to it. A record that a ruling overrules is rewritten in place, so no row holds old text.

## Mandates

| Slug | Gist | Link |
|---|---|---|
| `outcomes-judge-by-outcome` | Judge every rule, check, and design by the outcome for the person the software serves. | [`CLAUDE.md`](../CLAUDE.md) |
| `outcomes-decision-is-argument` | Treat a recorded decision as an argument, not a law. | [`CLAUDE.md`](../CLAUDE.md) |
| `outcomes-stale-decision-protocol` | When a decision looks stale, name the entry and the sentence. | [`CLAUDE.md`](../CLAUDE.md) |
| `outcomes-tests-are-claims` | A failing test is a claim, not law. | [`CLAUDE.md`](../CLAUDE.md) |
| `outcomes-word-covers-named-act` | My word covers the act it names, never a variant. | [`CLAUDE.md`](../CLAUDE.md) |
| `outcomes-mechanize-rules` | Once ready, turn each rule below into a hook or check. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-pick-mode-from-request` | Pick solo or orchestrate from my request. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-solo-builds-short-edit-list` | Solo: the request is a short list of edits with nothing to run in parallel. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-solo-reviews-logic-diffs-only` | In solo, a fresh reviewer reads the diff before merge only when it touches a rule's behaviour, a gate's verdict, or program logic. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-solo-grows-switch-to-orchestrate` | If a solo job grows, switch to orchestrate and say so in one line. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-orchestrator-never-builds` | Orchestrate: every other job. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-one-role-per-worker` | Each worker is one role: builder, reviewer, or Explore, never two. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-sonnet-is-the-default` | A workflow agent takes the builder or reviewer role through `agentType`. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-sonnet-is-the-ceiling` | Sonnet is the ceiling, except Plan, the built-in advisor (`advisorModel`), and a builder's third try (`roles-third-try-steps-up`), which run Opus. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-opus-shaped-say-so` | When a task is Opus-shaped (long-horizon, whole-codebase, or many-hour autonomous work), say so in one line before you dispatch, name why, and offer the switch. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-opus-override-guarded` | Owner raises Opus. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-brief-contents` | A brief carries the task, the files, governing rulings, failure classes from `outcomes-tests-are-claims`, and the check that proves the task done—in the fewest words. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-each-layer-proves-once` | Each layer proves a change once. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-review-cap-three` | A change gets at most three review rounds. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-holes-are-debts` | A known gap is a debt only if Claude is likely to hit it in normal work. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-third-try-steps-up` | Third try: Opus. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-resume-by-name` | Resume a dead agent by name, never fresh. | [`CLAUDE.md`](../CLAUDE.md) |
| `parallelism-each-own-checkout` | Fan tasks out to workers now, each in its own checkout. | [`CLAUDE.md`](../CLAUDE.md) |
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
| `git-main-only-by-pr` | Move main only by pull request, merged only when I name the act, or under a repo grant. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-never-merge-failing-ci` | Never merge failing CI. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-ci-wait-checks-in` | A session that waits on CI sets a timed check-in when it starts to wait, and again after each red job, each wider apart. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-ci-done-comment-wakes` | A run that ends red posts one PR comment, which wakes the session that watches the PR (`ci-done-comment`). | [`CLAUDE.md`](../CLAUDE.md) |
| `git-never-discard-output` | Keep command output. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-remedy-never-names-target` | A refusal's printed remedy never names the forbidden target. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-slug-then-claim-number` | Never allocate a numbered record on a branch. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-cite-by-id` | Ids, not paths. | [`CLAUDE.md`](../CLAUDE.md) |
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
| `verification-newest-that-passes` | Take the newest version that passes its checks. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-checked-reader-for-numbers` | If this repo lints markdown, give every published number and path a checked reader. | [`CLAUDE.md`](../CLAUDE.md) |
| `verification-report-unknown-reads` | Verify a claim before you rely on it, a document's own claims too. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-never-load-whole-doc` | Never load a long document whole. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-verdict-not-stream` | A verification command's answer is its verdict, not its stream. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-run-through-verdict` | Run every verification command through `verdict <cmd>`, which prints the verdict and keeps the full output in a log. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-point-brief-at-files` | Point a brief at files. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-read-report-not-transcript` | Read a sub-agent's report, never its transcript. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-compacting-keep-essentials` | When compacting, keep the files, the commands, each ruling's home, and the pid and port of each server still running. | [`CLAUDE.md`](../CLAUDE.md) |
| `tokens-folder-rules-load-by-path` | Move a CLAUDE.md section that matters only under one folder to a path-scoped rule. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-never-guess-answer` | Never guess an answer the code should give you. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-surface-ambiguity` | Surface ambiguity instead of resolving it silently. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-never-drop-item-silently` | Never drop an item without saying so. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-one-home-per-capability` | Give each capability one home, and call it from everywhere. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-allow-list-is-the-constant` | A gate's allow list must point at the constant the code emits, never a copy of it. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-guard-needs-incident` | Build a new guard or gate rule only against a named incident, a measured risk, or a likely risk: one Claude is likely to hit in normal work. | [`CLAUDE.md`](../CLAUDE.md) |
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
| `output-bring-decisions-as-question` | Bring my decisions as a question with options and a recommendation. | [`CLAUDE.md`](../CLAUDE.md) |
| `output-answer-has-a-home` | An answer to a question I bring is a ruling. | [`CLAUDE.md`](../CLAUDE.md) |
| `questions-go-to-owner` | Bring each question to me. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-order-of-labels` | Done, Deviations, Input Needed, Next. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-done-format` | Done: one line per item, BUILT, RECORDED, or OTHER. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-done-names-models` | A Done item that subagents built or reviewed names each one's role and model, such as "(builder sonnet, reviewer sonnet)". | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-drop-unused-label` | Drop a label that does not apply. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-name-unstarted-items` | An orchestrator's report holds an `Unstarted:` line under Next: each queued item with every question answered that it left unstarted, with its reason, or `none`. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-no-report-when-nothing-landed` | No report when nothing landed. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-batch-pace-numbers` | At each batch merge, the report also gives four pace numbers, as OTHER items under Done. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-offer-sweep-after-merge` | When a session's last PR has merged and no lane is open, its final report offers one command under Next: `python3 ~/.claude/janitor/sweep.py --root <repo> --attended --fast`, preview first, then with `--confirm`. | [`CLAUDE.md`](../CLAUDE.md) |

## Rulings

| Slug | Gist | Link |
|---|---|---|
| `a-branch-is-redundant-by-patch-not-by-ancestry` | The sweep (`the-janitor-is-one-machine-wide-sweep`, the janitor is one machine-wide sweep) reaps a local branch when the branch is an ancestor of the base, or when `git cherry <base> <branch>` prints no `+`. | [`decisions/a-branch-is-redundant-by-patch-not-by-ancestry.md`](../decisions/a-branch-is-redundant-by-patch-not-by-ancestry.md) |
| `a-kill-by-pid-needs-an-owned-pid` | Rule `shared-trees-no-machine-wide-kill` says to kill only your own processes. | [`decisions/a-kill-by-pid-needs-an-owned-pid.md`](../decisions/a-kill-by-pid-needs-an-owned-pid.md) |
| `adoptions-declined-2026-09-28` | The owner declined each candidate below. | [`decisions/adoptions-declined-2026-09-28.md`](../decisions/adoptions-declined-2026-09-28.md) |
| `agent-end-reap-stops-what-a-finished-agent-left` | The goal: when a subagent ends, each process it left under its own worktree stops. | [`decisions/agent-end-reap-stops-what-a-finished-agent-left.md`](../decisions/agent-end-reap-stops-what-a-finished-agent-left.md) |
| `agent-worktree-discard-is-noted` | Owner rulings: 2026-10-03 (the agent-owned worktree), 2026-10-11 ("Allow per-file", the untracked link), 2026-10-17 11:40 CDT (the per-file allow outside `.claude/worktrees/` stands). | [`decisions/agent-worktree-discard-is-noted.md`](../decisions/agent-worktree-discard-is-noted.md) |
| `agents-wait-with-monitor` | Owner, 2026-10-11 and 2026-10-12: the `Monitor` tool, Claude Code's own wait-once tool, is allowed. | [`decisions/agents-wait-with-monitor.md`](../decisions/agents-wait-with-monitor.md) |
| `ask-steps-run-alone` | An agent never chains a step that needs the owner's answer onto other steps in one command (owner, 2026-10-14). | [`decisions/ask-steps-run-alone.md`](../decisions/ask-steps-run-alone.md) |
| `audit-rework-order` | Owner, 2026-10-16 10:50 CDT. | [`decisions/audit-rework-order.md`](../decisions/audit-rework-order.md) |
| `background-needs-end-note` | Owner, 2026-10-13 23:41 CDT: "End condition at start." | [`decisions/background-needs-end-note.md`](../decisions/background-needs-end-note.md) |
| `bare-bash-on-windows-can-resolve-to-the-wsl-stub` | Python code on Windows never hands `subprocess.run` a bare `"bash"` or `"gh"`. | [`decisions/bare-bash-on-windows-can-resolve-to-the-wsl-stub.md`](../decisions/bare-bash-on-windows-can-resolve-to-the-wsl-stub.md) |
| `browser-prompts-are-the-apps` | Owner, 2026-10-11: claude-settings cannot disable the built-in browser pane's approval prompts on outside sites. | [`decisions/browser-prompts-are-the-apps.md`](../decisions/browser-prompts-are-the-apps.md) |
| `build-dirs-reaped-at-agent-end` | Owner, 2026-10-11: the agent-end reap also deletes build folders. | [`decisions/build-dirs-reaped-at-agent-end.md`](../decisions/build-dirs-reaped-at-agent-end.md) |
| `builders-cannot-edit-tests` | A builder that cannot pass a test must not delete, skip or rewrite it. | [`decisions/builders-cannot-edit-tests.md`](../decisions/builders-cannot-edit-tests.md) |
| `ci-unknown-is-red` | A lint that cannot read its input prints UNKNOWN. | [`decisions/ci-unknown-is-red.md`](../decisions/ci-unknown-is-red.md) |
| `cite-by-id-blocks-unread-file` | Owner, 2026-10-17 11:40 CDT (guard audit, finding 7): the guard blocks `git commit -F <file>` when it cannot read the file at hook time. | [`decisions/cite-by-id-blocks-unread-file.md`](../decisions/cite-by-id-blocks-unread-file.md) |
| `claude-md-shrink` | Owner, 2026-10-16 23:53 CDT and 2026-10-17 00:40 CDT: | [`decisions/claude-md-shrink.md`](../decisions/claude-md-shrink.md) |
| `config-watch-fast-exit` | Owner, 2026-10-20. | [`decisions/config-watch-fast-exit.md`](../decisions/config-watch-fast-exit.md) |
| `copy-mode-overwrites-no-backup` | Owner: in copy mode, an installer overwrites its own old copy and keeps no backup. | [`decisions/copy-mode-overwrites-no-backup.md`](../decisions/copy-mode-overwrites-no-backup.md) |
| `cull-rules` | Owner ruling, 2026-10-17 11:56 CDT. | [`decisions/cull-rules.md`](../decisions/cull-rules.md) |
| `decision-watch-mod-limits` | The decision watch runs as a mod on the app's own login, so an expired CLI login no longer silences it. | [`decisions/decision-watch-mod-limits.md`](../decisions/decision-watch-mod-limits.md) |
| `default-branch-read-order` | Owner, 2026-10-16: the branch-delete rule, the janitor sweep and the push guard read the default branch in this order. | [`decisions/default-branch-read-order.md`](../decisions/default-branch-read-order.md) |
| `dependabot-security-only` | Owner, 2026-10-16: security updates only. | [`decisions/dependabot-security-only.md`](../decisions/dependabot-security-only.md) |
| `design-skills` | Owner, 2026-10-10: three third-party skills apply to any repo with screens. | [`decisions/design-skills.md`](../decisions/design-skills.md) |
| `detached-launch-refused` | The `detached-launch` rule in `hooks/guard.py` refuses a command that starts a process and detaches it from the session. | [`decisions/detached-launch-refused.md`](../decisions/detached-launch-refused.md) |
| `docs-only-prs-skip-review` | Owner, 2026-09-26: a pull request that changes only prose or docs, and touches no rule, gate or product code, gets no reviewer pass. | [`decisions/docs-only-prs-skip-review.md`](../decisions/docs-only-prs-skip-review.md) |
| `draft-until-reviewed` | Owner, 2026-10-10 and 2026-10-13: every PR opens as a draft, and CI skips draft PRs. | [`decisions/draft-until-reviewed.md`](../decisions/draft-until-reviewed.md) |
| `fewest-words-mandate` | Fewest words, most of all in front-end copy | [`decisions/fewest-words-mandate.md`](../decisions/fewest-words-mandate.md) |
| `frozen-path-resolves-shell-vars` | Before rule 7 (frozen-path) matches the target of a shell write, it reads the command left to right. | [`decisions/frozen-path-resolves-shell-vars.md`](../decisions/frozen-path-resolves-shell-vars.md) |
| `gate-hooks-fail-closed` | Owner, 2026-10-12: a gate whose script or python is missing refuses the call. | [`decisions/gate-hooks-fail-closed.md`](../decisions/gate-hooks-fail-closed.md) |
| `git-env-set-denied` | No agent command may set `GIT_DIR`, `GIT_WORK_TREE` or `GIT_INDEX_FILE`. | [`decisions/git-env-set-denied.md`](../decisions/git-env-set-denied.md) |
| `guard-command-position` | One resolver in `hooks/guard_core.py` finds the command word for every rule. | [`decisions/guard-command-position.md`](../decisions/guard-command-position.md) |
| `guard-guards-mistakes-only` | Owner, 2026-10-17 09:07 CDT, "widen": every guard, gate and check stops Claude's mistakes, never an attacker. | [`decisions/guard-guards-mistakes-only.md`](../decisions/guard-guards-mistakes-only.md) |
| `guard-linked-node-modules` | Yes. | [`decisions/guard-linked-node-modules.md`](../decisions/guard-linked-node-modules.md) |
| `guard-log-read-weekly` | Owner, 2026-10-13. | [`decisions/guard-log-read-weekly.md`](../decisions/guard-log-read-weekly.md) |
| `guard-that-cries-wolf-is-spent` | CLAUDE.md: "Trust a guard only once it goes red on the defect it guards." The other half: a guard that goes red when nothing is wrong is spent, because the reader stops reading it. | [`decisions/guard-that-cries-wolf-is-spent.md`](../decisions/guard-that-cries-wolf-is-spent.md) |
| `haiku-prompt-hooks` | **Prompt hooks judge rules that no script can parse.** Each blocks the call when it finds a breach (owner ruling 2026-10-07). | [`decisions/haiku-prompt-hooks.md`](../decisions/haiku-prompt-hooks.md) |
| `hold-unsafe-after-round-3` | Owner, 2026-10-15 12:00 CDT. | [`decisions/hold-unsafe-after-round-3.md`](../decisions/hold-unsafe-after-round-3.md) |
| `hook-if-filters` | Owner, 2026-10-21. | [`decisions/hook-if-filters.md`](../decisions/hook-if-filters.md) |
| `hooks-share-the-transcript-reader` | The Stop hooks read the transcript through one module, `lint/_transcript.py`. | [`decisions/hooks-share-the-transcript-reader.md`](../decisions/hooks-share-the-transcript-reader.md) |
| `install-hooks-whole` | No running session judges a call with a missing, short or mixed set of hook files. | [`decisions/install-hooks-whole.md`](../decisions/install-hooks-whole.md) |
| `ios-ship-is-one-shared-tool` | Owner, 2026-10-25: one tool, `bin/ios-ship`, builds and ships the owner's iOS apps from the Mac. | [`decisions/ios-ship-is-one-shared-tool.md`](../decisions/ios-ship-is-one-shared-tool.md) |
| `lane-by-slug` | Owner, 2026-10-13 14:13 CDT, relayed by the oversight session: the guard refuses a session number that names a lane, such as `N20` or `(N16)`. | [`decisions/lane-by-slug.md`](../decisions/lane-by-slug.md) |
| `list-form-subprocess-ignores-a-path-shim-on-windows` | A blind-command fixture cannot shadow a real executable for a list-form subprocess call on Windows. | [`decisions/list-form-subprocess-ignores-a-path-shim-on-windows.md`](../decisions/list-form-subprocess-ignores-a-path-shim-on-windows.md) |
| `local-time-central` | Owner, 2026-10-12: a session tells the owner times in US Central (America/Chicago), DST-aware, 24-hour clock. | [`decisions/local-time-central.md`](../decisions/local-time-central.md) |
| `main-branch-protection` | `main` of shivinate7/claude-settings requires the eleven checks that `.github/stamp.json` `merge.requiredChecks` names: scope, gates, gates-windows, gates-windows-guard, gates-mutate-guard, gates-windows-merge, gates-windows-rest, gates-macos, shell-macos, pointer-windows, gates-shoot. | [`decisions/main-branch-protection.md`](../decisions/main-branch-protection.md) |
| `map-skill-lives-here` | Owner, 2026-10-16: `skills/plain-english-map/` in claude-settings is the one home of the skill. | [`decisions/map-skill-lives-here.md`](../decisions/map-skill-lives-here.md) |
| `memory-is-never-a-rulings-only-home` | The owner's rulings must reach a tracked file. | [`decisions/memory-is-never-a-rulings-only-home.md`](../decisions/memory-is-never-a-rulings-only-home.md) |
| `merge-deletes-batch-lanes` | Owner, 2026-10-19 12:14 CDT: each merge deletes the lane branches its batch took in. | [`decisions/merge-deletes-batch-lanes.md`](../decisions/merge-deletes-batch-lanes.md) |
| `mods-deferred-table` | These mods stay deferred recordings on the repo. | [`decisions/mods-deferred-table.md`](../decisions/mods-deferred-table.md) |
| `mods-install-via-marketplace` | The shared `settings.json` declares one marketplace, `claude-settings`, from the GitHub repo `shivinate7/claude-settings`, with `autoUpdate` set to true. | [`decisions/mods-install-via-marketplace.md`](../decisions/mods-install-via-marketplace.md) |
| `mods-no-cli-key-headless` | No CLI API key for headless runs. | [`decisions/mods-no-cli-key-headless.md`](../decisions/mods-no-cli-key-headless.md) |
| `one-layout-every-repo` | Every repo keeps each kind of file in the same place. | [`decisions/one-layout-every-repo.md`](../decisions/one-layout-every-repo.md) |
| `one-shared-record-stamp` | One shared parser in claude-settings handles every repo's record format. | [`decisions/one-shared-record-stamp.md`](../decisions/one-shared-record-stamp.md) |
| `opt-in-ci-templates-composite` | Seven templates any repo can adopt live in one home and one shape: a composite action under `actions/<name>/`, or a plain file where the template is no workflow step. | [`decisions/opt-in-ci-templates-composite.md`](../decisions/opt-in-ci-templates-composite.md) |
| `opus-grant-expires` | An Opus worker is enabled for one repository, on the owner's word in chat (`roles-opus-override-guarded`). | [`decisions/opus-grant-expires.md`](../decisions/opus-grant-expires.md) |
| `owner-feedback-inbox` | When the owner opens a feedback burst, a hook writes each message to a per-session inbox. | [`decisions/owner-feedback-inbox.md`](../decisions/owner-feedback-inbox.md) |
| `plain-prose-lint` | The STE lint is a plain-prose lint. | [`decisions/plain-prose-lint.md`](../decisions/plain-prose-lint.md) |
| `playwright-browsers-path` | No command sets PLAYWRIGHT_BROWSERS_PATH to work around a missing browser build. | [`decisions/playwright-browsers-path.md`](../decisions/playwright-browsers-path.md) |
| `playwright-install-once` | Rule `playwright-install` in `hooks/guard.py`: | [`decisions/playwright-install-once.md`](../decisions/playwright-install-once.md) |
| `precompact-handoff` | Auto-compact drops detail. | [`decisions/precompact-handoff.md`](../decisions/precompact-handoff.md) |
| `predicate-is-the-act` | Judge a guard by the act it must catch, never by the spelling of the act. | [`decisions/predicate-is-the-act.md`](../decisions/predicate-is-the-act.md) |
| `premise-format` | A premise is a claim, not a fact. | [`decisions/premise-format.md`](../decisions/premise-format.md) |
| `question-reviewer-agent-hook` | Owner rulings, 2026-10-22 10:18 CDT: | [`decisions/question-reviewer-agent-hook.md`](../decisions/question-reviewer-agent-hook.md) |
| `questions-go-to-owner` | Owner, 2026-10-26: a session with a question brings it to the owner. | [`decisions/questions-go-to-owner.md`](../decisions/questions-go-to-owner.md) |
| `recovery-must-not-gate-on-its-own-state` | A recovery control exists for the moment its own precondition is false. | [`decisions/recovery-must-not-gate-on-its-own-state.md`](../decisions/recovery-must-not-gate-on-its-own-state.md) |
| `reply-judge-samples-never-blocks` | The Stop reply judge is `hooks/reply_judge.py`, a command hook (owner ruling 2026-10-12), because a prompt hook cannot exit on a field in code. | [`decisions/reply-judge-samples-never-blocks.md`](../decisions/reply-judge-samples-never-blocks.md) |
| `reuse-needs-checkout-proof` | Lanes run in separate worktrees of one clone. | [`decisions/reuse-needs-checkout-proof.md`](../decisions/reuse-needs-checkout-proof.md) |
| `rm-on-a-variable-needs-a-guard` | Bypass-mode sessions must not wait on the owner for Claude Code's critical-path `rm` prompt (owner ruling 2026-10-11). | [`decisions/rm-on-a-variable-needs-a-guard.md`](../decisions/rm-on-a-variable-needs-a-guard.md) |
| `rulings-declare-kind` | A decision record that a pull request adds or changes must say what kind each ruling is: a build task, or a process change. | [`decisions/rulings-declare-kind.md`](../decisions/rulings-declare-kind.md) |
| `safe-stop-queues-one-prompt` | `/safe-stop` is a command of the session-board mod (`session-board-mod-limits`, session-board keeps small records). | [`decisions/safe-stop-queues-one-prompt.md`](../decisions/safe-stop-queues-one-prompt.md) |
| `session-board-mod-limits` | The session-board mod (`mods/session-board`, commands `/board` and `/safe-stop`) gives one view of all sessions and a safe stopping point, with no typing of "status?" into each one. | [`decisions/session-board-mod-limits.md`](../decisions/session-board-mod-limits.md) |
| `session-end-sweep-is-disarmed-until-liveness-is-proven` | The `SessionEnd` hook in `settings.json` runs `janitor/session_end_sweep.py`. | [`decisions/session-end-sweep-is-disarmed-until-liveness-is-proven.md`](../decisions/session-end-sweep-is-disarmed-until-liveness-is-proven.md) |
| `shoot-is-one-shared-command` | Owner, 2026-10-17: build one screenshot script in this repo. | [`decisions/shoot-is-one-shared-command.md`](../decisions/shoot-is-one-shared-command.md) |
| `silent-undo-check-design` | `lint/check_silent_undo.py` is the one home. | [`decisions/silent-undo-check-design.md`](../decisions/silent-undo-check-design.md) |
| `sim-boot-is-verified` | The record hook of `sweep-shuts-down-idle-simulators` (ruling 1) checks each device that a `simctl boot` or an MCP `launch` took from `Shutdown` to `Booted`. | [`decisions/sim-boot-is-verified.md`](../decisions/sim-boot-is-verified.md) |
| `source-prose-lint-ships-dark` | The comment-and-docstring mode of `ste_lint.py` stays off by default (`--source-prose` and `check_source`). | [`decisions/source-prose-lint-ships-dark.md`](../decisions/source-prose-lint-ships-dark.md) |
| `spawns-use-no-window` | Owner, 2026-10-19 16:20 CDT: helper programs that hooks, mods and tools start use the "no window" option. | [`decisions/spawns-use-no-window.md`](../decisions/spawns-use-no-window.md) |
| `stale-safe-force-push` | The owner gets no prompt for a safe push, and no push overwrites newer remote work with a stale copy. | [`decisions/stale-safe-force-push.md`](../decisions/stale-safe-force-push.md) |
| `stall-watch` | The session learns within minutes that a background command stalled, and diagnoses the cause. | [`decisions/stall-watch.md`](../decisions/stall-watch.md) |
| `standing-merge-grant` | Owner ruling, 2026-10-10: the orchestrating session has standing merge authority in claude-settings. | [`decisions/standing-merge-grant.md`](../decisions/standing-merge-grant.md) |
| `stash-stack-is-a-shared-subject` | CLAUDE.md says: "A stash entry belongs to no branch." The guard reads `git stash` against the whole stack, not only the working tree. | [`decisions/stash-stack-is-a-shared-subject.md`](../decisions/stash-stack-is-a-shared-subject.md) |
| `ste-gate-fixes-not-nags` | Owner, 2026-10-22 10:10 CDT: `settings.json` wires no STE write gate (`ste_gate.py`) and no markdown sweep (`md_sweep.py`). | [`decisions/ste-gate-fixes-not-nags.md`](../decisions/ste-gate-fixes-not-nags.md) |
| `stop-guardrail-became-a-command-hook` | The Stop guardrail is never a `type: agent` hook. | [`decisions/stop-guardrail-became-a-command-hook.md`](../decisions/stop-guardrail-became-a-command-hook.md) |
| `subagent-model-cap` | Each agent role has its own model and effort, in the table below. | [`decisions/subagent-model-cap.md`](../decisions/subagent-model-cap.md) |
| `subagent-powershell-tool` | With Claude Code's PowerShell tool. | [`decisions/subagent-powershell-tool.md`](../decisions/subagent-powershell-tool.md) |
| `sweep-shuts-down-idle-simulators` | Sessions boot simulators. The sweep stops idle ones. | [`decisions/sweep-shuts-down-idle-simulators.md`](../decisions/sweep-shuts-down-idle-simulators.md) |
| `test-strategy-reset` | A test must not fail on runner speed. | [`decisions/test-strategy-reset.md`](../decisions/test-strategy-reset.md) |
| `test-temp-standard` | Each test run writes temp files only in its own run folder, under one temp root per repo, and removes that folder at teardown. | [`decisions/test-temp-standard.md`](../decisions/test-temp-standard.md) |
| `the-janitor-is-one-machine-wide-sweep` | The sweep deletes a local branch that holds no unique work. | [`decisions/the-janitor-is-one-machine-wide-sweep.md`](../decisions/the-janitor-is-one-machine-wide-sweep.md) |
| `unattended-sweep-stops-proven-orphans` | **What an unattended run can stop.** A `--confirm` run, run by the SessionEnd hook or the scheduled task, can send one signal to one process. | [`decisions/unattended-sweep-stops-proven-orphans.md`](../decisions/unattended-sweep-stops-proven-orphans.md) |
| `ux-house-rules` | The UX rules that every repo with screens shares, beyond the three third-party sets, live in `ux/`. | [`decisions/ux-house-rules.md`](../decisions/ux-house-rules.md) |
| `when-a-worktree-may-be-removed` | Four idle limits. | [`decisions/when-a-worktree-may-be-removed.md`](../decisions/when-a-worktree-may-be-removed.md) |
| `windows-temp-sweep` | A session's temp folder goes after its transcript is idle 24 hours | [`decisions/windows-temp-sweep.md`](../decisions/windows-temp-sweep.md) |
| `worktree-setup-is-per-repo` | Each repo sets up the untracked state (node_modules, venv, caches) of a worktree itself. | [`decisions/worktree-setup-is-per-repo.md`](../decisions/worktree-setup-is-per-repo.md) |
| `wsl-allow-list` | The guard allows a WSL command only when every condition holds: | [`decisions/wsl-allow-list.md`](../decisions/wsl-allow-list.md) |

## Build designs

| Slug | Gist | Link |
|---|---|---|
| `agents-get-standing-rules` | Owner, 2026-10-12: a SubagentStart hook injects the standing rules, so a brief need not retype them. | [`decisions/agents-get-standing-rules.md`](../decisions/agents-get-standing-rules.md) |
| `an-agent-outside-its-home-tree-must-stop` | An agent whose worktree is gone must stop and report. | [`decisions/an-agent-outside-its-home-tree-must-stop.md`](../decisions/an-agent-outside-its-home-tree-must-stop.md) |
| `bare-merge-asks` | Orchestrator call (lane bare-gh-merge-ask); the owner may rule otherwise. | [`decisions/bare-merge-asks.md`](../decisions/bare-merge-asks.md) |
| `catalog-cells-never-cut` | The cell cap in `docs/catalog.md` sits above the longest cell, so no cell is cut. | [`decisions/catalog-cells-never-cut.md`](../decisions/catalog-cells-never-cut.md) |
| `ci-wait-reads-run-status` | Owner, 2026-10-16 01:47 CDT ("Status read only") and 03:00 CDT ("Change them too"): no program and no agent runs `gh run watch`, in the foreground or the background. | [`decisions/ci-wait-reads-run-status.md`](../decisions/ci-wait-reads-run-status.md) |
| `claude-md-change-is-flagged` | Owner, 2026-10-16: report only, no hold. | [`decisions/claude-md-change-is-flagged.md`](../decisions/claude-md-change-is-flagged.md) |
| `guard-reads-wrapped-commands` | The guards judge the command a wrapper runs, not the raw text. | [`decisions/guard-reads-wrapped-commands.md`](../decisions/guard-reads-wrapped-commands.md) |
| `hook-catalog-page` | `docs/catalog.md` lists every hook, judge, mod and skill. | [`decisions/hook-catalog-page.md`](../decisions/hook-catalog-page.md) |
| `install-refuses-linked-tree` | The installer refuses a linked worktree. | [`decisions/install-refuses-linked-tree.md`](../decisions/install-refuses-linked-tree.md) |
| `install-sh-stays-off-windows` | `install.sh` does nothing on Windows. | [`decisions/install-sh-stays-off-windows.md`](../decisions/install-sh-stays-off-windows.md) |
| `lanes-start-in-tool-worktrees` | Owner, 2026-10-21: block the hand-made lane worktree fully, and record which layer refused isolation. | [`decisions/lanes-start-in-tool-worktrees.md`](../decisions/lanes-start-in-tool-worktrees.md) |
| `machine-load-brake` | Owner, 2026-10-21 (spec), 2026-10-22 (foreground), 2026-10-23 (disk) and 2026-10-25 (CPU dropped: a 200 ms sample is noise; memory and disk are what stall a machine): a lane-start call reads the machine's load, and a busy or full machine refuses new lanes (disk is the smaller of a share and a GB cap). | [`decisions/machine-load-brake.md`](../decisions/machine-load-brake.md) |
| `merge-reinstalls-from-main` | The links in `~/.claude` point at one pinned checkout. | [`decisions/merge-reinstalls-from-main.md`](../decisions/merge-reinstalls-from-main.md) |
| `owner-override-pass` | The owner starts a prompt with the word `override`. | [`decisions/owner-override-pass.md`](../decisions/owner-override-pass.md) |
| `plain-diff-mod-limits` | The plain-diff mod (`mods/plain-diff`, command `/plain-diff`) sends a diff to `$.model.complete` only for a file that passes the secret filter. | [`decisions/plain-diff-mod-limits.md`](../decisions/plain-diff-mod-limits.md) |
| `post-merge-hook-is-a-fallback` | Owner, 2026-10-22: `install.ps1` writes its git post-merge hook only when it installs a copy, not a link. | [`decisions/post-merge-hook-is-a-fallback.md`](../decisions/post-merge-hook-is-a-fallback.md) |
| `records-index-at-merge` | Each repo that keeps records has one generated index page, `docs/records.md`. | [`decisions/records-index-at-merge.md`](../decisions/records-index-at-merge.md) |
| `rm-path-wrapper` | `bin/rm` sits ahead of the real `rm` on PATH, for Claude sessions only. | [`decisions/rm-path-wrapper.md`](../decisions/rm-path-wrapper.md) |
| `shell-scripts-check-out-lf` | Owner, 2026-10-21: `.gitattributes` forces LF on checkout for every file under `bin/` and `githooks/`, every `*.sh`, and `skills/impeccable/scripts/impeccable`. | [`decisions/shell-scripts-check-out-lf.md`](../decisions/shell-scripts-check-out-lf.md) |

## Debts

| Slug | Gist | Link |
|---|---|---|
| `agent-end-log-loses-row` | On Windows, test_parallel_writers_lose_no_row lost one of 24 rows (run 39086341296) though the same tree passed before. | [`debts/agent-end-log-loses-row.md`](../debts/agent-end-log-loses-row.md) |
| `agent-reports-with-live-watcher` | No check stops an agent that sends its final report while a Monitor or background task it started is still running. | [`debts/agent-reports-with-live-watcher.md`](../debts/agent-reports-with-live-watcher.md) |
| `banchi-build-steps` | A pending Banchi step is a line `` 0. `step <slug>` `` in a file in `docs/gates/steps/`. | [`debts/banchi-build-steps.md`](../debts/banchi-build-steps.md) |
| `bg-end-false-alarms` | The rule splits script names on `:` and `-`, so `build:dev` and `test-watch-ci` read as servers. | [`debts/bg-end-false-alarms.md`](../debts/bg-end-false-alarms.md) |
| `build-disk-guard` | Part 2 of `build-dirs-reaped-at-agent-end`, the low-disk build guard, is not built. | [`debts/build-disk-guard.md`](../debts/build-disk-guard.md) |
| `ci-wake-export-gh-repo-unread` | ci_wake reads GH_REPO only as a command prefix. | [`debts/ci-wake-export-gh-repo-unread.md`](../debts/ci-wake-export-gh-repo-unread.md) |
| `ci-wake-gh-host-bare-repo` | For a github.com PR, ci_wake passes a bare -R owner/repo. | [`debts/ci-wake-gh-host-bare-repo.md`](../debts/ci-wake-gh-host-bare-repo.md) |
| `ci-wake-lists-runs-once` | `ci_wake.wait_for` lists the head's CI runs again until a run that ran is judged. | [`debts/ci-wake-lists-runs-once.md`](../debts/ci-wake-lists-runs-once.md) |
| `explain-accessvbom` | The owner wants to be talked through AccessVBOM, the Office setting "Trust access to the VBA project object model": what it does, its risk, and whether to turn it on. | [`debts/explain-accessvbom.md`](../debts/explain-accessvbom.md) |
| `ff-first-lane-not-a-tip` | `lane_tips` reads merge commits only. | [`debts/ff-first-lane-not-a-tip.md`](../debts/ff-first-lane-not-a-tip.md) |
| `finished-agent-shells-keep-tree` | A finished agent's own shells, such as a dev server, have the live host as parent. | [`debts/finished-agent-shells-keep-tree.md`](../debts/finished-agent-shells-keep-tree.md) |
| `gates-job-near-timeout` | The gates job took 13.7-17.8 min over 12 green runs on 2026-10-17. | [`debts/gates-job-near-timeout.md`](../debts/gates-job-near-timeout.md) |
| `gitignore-skips-map-tests` | `harness-scope.sh` turns on only `code` for a `.gitignore` change. | [`debts/gitignore-skips-map-tests.md`](../debts/gitignore-skips-map-tests.md) |
| `guard-stdin-not-utf8` | `_force_utf8_streams` reconfigures stdout and stderr only. | [`debts/guard-stdin-not-utf8.md`](../debts/guard-stdin-not-utf8.md) |
| `hooks-to-mods-judges` | Plan step E has four parts. | [`debts/hooks-to-mods-judges.md`](../debts/hooks-to-mods-judges.md) |
| `inplace-edit-under-0-9-flagged` | A branch can edit a line that main only added. | [`debts/inplace-edit-under-0-9-flagged.md`](../debts/inplace-edit-under-0-9-flagged.md) |
| `install-checkout-flake` | On Windows CI two session-start freshness cases failed, then passed on rerun, twice on 2026-10-20: caseF1 in the morning (#527), and caseG1 at 23:00 (#533, run 39528566602; "expected ... | [`debts/install-checkout-flake.md`](../debts/install-checkout-flake.md) |
| `install-set-reads-held-file` | On Windows the install-set test reads a hook run's output file while another process still holds it, so the job fails with an IOException though the install is correct. | [`debts/install-set-reads-held-file.md`](../debts/install-set-reads-held-file.md) |
| `lane-cycle-delete-order` | `cut_lanes` deletes dependents first. | [`debts/lane-cycle-delete-order.md`](../debts/lane-cycle-delete-order.md) |
| `linked-nm-prefix-workspace` | `-w`, `--workspace` and `--prefix` change the folder npm works in. | [`debts/linked-nm-prefix-workspace.md`](../debts/linked-nm-prefix-workspace.md) |
| `long-lived-head-lost-in-batch` | `cut_lanes` deletes any origin head whose sha is a lane tip. | [`debts/long-lived-head-lost-in-batch.md`](../debts/long-lived-head-lost-in-batch.md) |
| `measured-time-table` | `bin/verdict` logs no kind, seconds and exit per run, and no table keeps measured times. | [`debts/measured-time-table.md`](../debts/measured-time-table.md) |
| `merge-head-race-remains` | The race between a push and `gh pr ready` remains. | [`debts/merge-head-race-remains.md`](../debts/merge-head-race-remains.md) |
| `merge-records-stale-base` | `bin/merge` rebuilds the records page after the CI wait. | [`debts/merge-records-stale-base.md`](../debts/merge-records-stale-base.md) |
| `merge-silent-exit` | Twice on 2026-10-20 (#527 in the afternoon, #538 at 00:08 CDT on 10-21), the background shell that ran `bin/merge <pr> --confirm` exited rc 1 mid-wait and printed no reason. | [`debts/merge-silent-exit.md`](../debts/merge-silent-exit.md) |
| `nowindow-bin-no-fallback` | bin/verdict, bin/ste-changed, bin/ci-job and merge/launch.py import hooks/_nowindow.py with no fallback, so a copy-mode install that lands bin/ before hooks/ makes them fail. | [`debts/nowindow-bin-no-fallback.md`](../debts/nowindow-bin-no-fallback.md) |
| `nowindow-ctrl-c-orphans` | With CREATE_NO_WINDOW the child gets its own hidden console, so Ctrl-C may not reach grandchildren. | [`debts/nowindow-ctrl-c-orphans.md`](../debts/nowindow-ctrl-c-orphans.md) |
| `nowindow-fallback-silent` | A hook that falls back to plain subprocess says nothing, so the popups return unseen. | [`debts/nowindow-fallback-silent.md`](../debts/nowindow-fallback-silent.md) |
| `nowindow-git-prompt-hangs` | A git credential prompt on the terminal, from merge/merge.py sh(), has no console to show in, so it would wait with no end. | [`debts/nowindow-git-prompt-hangs.md`](../debts/nowindow-git-prompt-hangs.md) |
| `nowindow-scan-misses-os-system` | lint/test_no_window_spawn.py reads subprocess and Node child_process calls only. | [`debts/nowindow-scan-misses-os-system.md`](../debts/nowindow-scan-misses-os-system.md) |
| `npm-audit-fix-linked` | The rule judges only npm install, i, ci, update, uninstall and their aliases. | [`debts/npm-audit-fix-linked.md`](../debts/npm-audit-fix-linked.md) |
| `old-merge-tool-refuses-stamp` | A merge tool older than this change refuses main's `stamp.json`, which has the unknown field `keepBranches`. | [`debts/old-merge-tool-refuses-stamp.md`](../debts/old-merge-tool-refuses-stamp.md) |
| `pin-missing-files-no-install` | `merge/install_from_main.sh` treats a pin at main that has only missing tracked files as dirty: it exits 1 and installs nothing. | [`debts/pin-missing-files-no-install.md`](../debts/pin-missing-files-no-install.md) |
| `pinoff1-freshness-flaky` | Case pinoff1 expected one freshness line and got none, on a commit that changed only the records page (run 39080117103). | [`debts/pinoff1-freshness-flaky.md`](../debts/pinoff1-freshness-flaky.md) |
| `playwright-rows-measure` | Unmeasured: whether the Playwright rows in `hooks/test_guard.py` still stop a real mistake. | [`debts/playwright-rows-measure.md`](../debts/playwright-rows-measure.md) |
| `pr-ready-unguarded` | The `draft-pr` guard rule reads only the create command and the MCP create tool. | [`debts/pr-ready-unguarded.md`](../debts/pr-ready-unguarded.md) |
| `push-head-mismatch-trap` | `git push <remote> HEAD`, when the current branch tracks a branch of another name on that remote, pushes under the local branch's own name. | [`debts/push-head-mismatch-trap.md`](../debts/push-head-mismatch-trap.md) |
| `push-report-before-checks` | A session can report a push as done before its checks finish. | [`debts/push-report-before-checks.md`](../debts/push-report-before-checks.md) |
| `refresh-lock-untested` | The SessionStart refresh holds a lock directory in the config dir. | [`debts/refresh-lock-untested.md`](../debts/refresh-lock-untested.md) |
| `refusal-route-around-guard` | A hook refuses an Edit of a path, then the same agent writes the file with Bash and Python. | [`debts/refusal-route-around-guard.md`](../debts/refusal-route-around-guard.md) |
| `ruling-kind-vacuous-local-pass` | `lint/check_ruling_kind.py` checks only the committed diff against `origin/main`, so a run before the commit checks zero files and prints PASS. | [`debts/ruling-kind-vacuous-local-pass.md`](../debts/ruling-kind-vacuous-local-pass.md) |
| `settled-question-check-gap` | A question that a decision or a debt already settles can reach the owner. | [`debts/settled-question-check-gap.md`](../debts/settled-question-check-gap.md) |
| `sharables-adopts-the-stamp` | claude-sharables claims record ids with its own `scripts/check_records.py --claim-ids --apply`. | [`debts/sharables-adopts-the-stamp.md`](../debts/sharables-adopts-the-stamp.md) |
| `skill-copy-no-typescript` | A copy of the skill folder outside the clone finds no `node_modules`, so `map-check.mjs` and `map-picture.mjs` cannot load `typescript` there. | [`debts/skill-copy-no-typescript.md`](../debts/skill-copy-no-typescript.md) |
| `squash-lane-branch-kept` | A squash-merged lane has no merge commit parent. | [`debts/squash-lane-branch-kept.md`](../debts/squash-lane-branch-kept.md) |
| `stall-message-repeats-every-stop` | There is no dedupe. | [`debts/stall-message-repeats-every-stop.md`](../debts/stall-message-repeats-every-stop.md) |
| `stamp-shallow-depth-two` | `stamp.mjs --check` off the default branch needs `fetch-depth: 0`. | [`debts/stamp-shallow-depth-two.md`](../debts/stamp-shallow-depth-two.md) |
| `test-guard-no-progress-line` | `hooks/test_guard.py` prints nothing for minutes, so the stall watch cuts off a healthy full run. | [`debts/test-guard-no-progress-line.md`](../debts/test-guard-no-progress-line.md) |
| `upgrade-strips-name-port` | The version 1 to 2 upgrade removes `:N` after a name whose extension is in `codeExtensions`. | [`debts/upgrade-strips-name-port.md`](../debts/upgrade-strips-name-port.md) |
| `verdict-pipe-drops-line` | `verdict <cmd> \| tail` keeps only the last lines, and a wrapper watching the pipe can read a stalled or false exit. | [`debts/verdict-pipe-drops-line.md`](../debts/verdict-pipe-drops-line.md) |
| `verdict-skip-reads-pass` | If a run prints SKIP lines and exits 0, `bin/verdict` prints only PASS. | [`debts/verdict-skip-reads-pass.md`](../debts/verdict-skip-reads-pass.md) |

## Plans

| Slug | Gist | Link |
|---|---|---|
| `o10-session-questions-page` | Plan: a page per session for questions waiting on the owner | [`plans/o10-session-questions-page.md`](../plans/o10-session-questions-page.md) |
| `shared-merge-tool` | Plan: the shared merge tool | [`plans/shared-merge-tool.md`](../plans/shared-merge-tool.md) |
