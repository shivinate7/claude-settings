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
| `roles-pick-mode-from-request` | Pick the session's role from my request: coordinator for a standing build, else lane (`session-tiers`, the session roles). | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-solo-reviews-logic-diffs-only` | In a run with one lane, a fresh reviewer reads the diff before merge only when it touches a rule's behaviour, a guard's or check's verdict, or program logic. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-solo-grows-switch-to-orchestrate` | A lane may grow to a coordinator. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-orchestrator-never-builds` | A lane builds a short list of edits itself when nothing can run in parallel, whoever started it. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-one-role-per-agent` | Each agent is one role: builder, reviewer, designer, design reviewer, refuter, or Explore, never two. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-model-per-role-table` | A workflow agent takes the builder or reviewer role through `agentType`. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-sonnet-is-the-ceiling` | Sonnet is the ceiling, except Plan, the built-in advisor (`advisorModel`), the designer, the design reviewer, the refuter, and a builder's third try (`roles-third-round-steps-up`), which run Opus. | [`CLAUDE.md`](../CLAUDE.md) |
| `roles-plan-gets-refuter` | After a Plan agent returns, a refuter gets the task brief and the plan, word for word, and nothing else. | [`CLAUDE.md`](../CLAUDE.md) |
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
| `shared-trees-own-ports-data` | A branch switch is a whole-tree act. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-confirm-before-write` | Confirm which checkout and branch you stand in before any git write or merge. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-reverify-after-incident` | Re-verify every edit after an incident. | [`CLAUDE.md`](../CLAUDE.md) |
| `shared-trees-delete-names-absolute-path` | A delete names its target as an absolute or quoted-variable path, never after a cd. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-main-only-by-pr` | Move main only by pull request, merged only when I name the act, or under a repo grant. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-never-merge-failing-ci` | Never merge a PR whose own run is red, or onto a red main, except its revert. | [`CLAUDE.md`](../CLAUDE.md) |
| `gh-write-cloud` | In a cloud session, a `gh` pr, issue or `gh api` write is refused: write through the GitHub MCP tools or the merge tool. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-red-main-reverts` | While main's newest finished run is red, only the revert of the blamed commit merges, with `--base-red-ok "<reason>"`, until the revert's run on main is green. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-ci-wait-checks-in` | A session that waits on CI sets a one-time check-in when it starts to wait, and again after each red job, each wider apart. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-ci-done-comment-wakes` | A run that ends red posts one PR comment, which wakes the session that watches the PR (decision `ci-wait-reads-run-status`). | [`CLAUDE.md`](../CLAUDE.md) |
| `git-never-discard-output` | Keep git write output. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-remedy-never-names-target` | A refusal's printed remedy never names the forbidden target. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-slug-then-claim-number` | Never allocate a numbered record on a branch. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-cite-by-id` | Ids, not paths. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-record-own-file-per-kind` | Give each record its own file, one folder per kind. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-one-record-per-question` | One record per question. | [`CLAUDE.md`](../CLAUDE.md) |
| `git-integration-branch-merge` | Each lane PR merges alone through the merge tool, on its own green run and the review its risk needs. | [`CLAUDE.md`](../CLAUDE.md) |
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
| `verification-counts-from-rest` | Counts and states (open, closed, merged, CI status) come from the GitHub REST API, not a search. | [`CLAUDE.md`](../CLAUDE.md) |
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
| `building-guard-needs-incident` | Build a guard or check against a mistake Claude has made or is likely to make in normal work. | [`CLAUDE.md`](../CLAUDE.md) |
| `building-mistake-names-its-guard` | A mistake you made is a strong sign that a guard or check is missing, since the way we work should make accidents hard. | [`CLAUDE.md`](../CLAUDE.md) |
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
| `reports-name-unstarted-items` | A report from a spawner holds an `Unstarted:` line under Next: each queued item with every question answered that it left unstarted, with its reason, or `none`. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-no-report-when-nothing-landed` | No report when nothing landed. | [`CLAUDE.md`](../CLAUDE.md) |
| `reports-batch-pace-numbers` | After each merge, the report also gives four pace numbers, as OTHER items under Done. | [`CLAUDE.md`](../CLAUDE.md) |
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
| `agent-model-cap` | Each agent role runs the model and effort of its row in the table below. | [`docs/decisions/agent-model-cap.md`](../docs/decisions/agent-model-cap.md) |
| `agent-no-remote-tools` | An agent never starts, messages, tags or archives a session. | [`docs/decisions/agent-no-remote-tools.md`](../docs/decisions/agent-no-remote-tools.md) |
| `agent-powershell-tool` | With Claude Code's PowerShell tool. | [`docs/decisions/agent-powershell-tool.md`](../docs/decisions/agent-powershell-tool.md) |
| `agent-worktree-discard-is-noted` | Owner rulings: 2026-10-03 (the agent-owned worktree), 2026-10-11 ("Allow per-file", the untracked link), 2026-10-17 11:40 CDT (the per-file allow outside `.claude/worktrees/` stands). | [`docs/decisions/agent-worktree-discard-is-noted.md`](../docs/decisions/agent-worktree-discard-is-noted.md) |
| `agents-wait-with-monitor` | Owner, 2026-10-11 and 2026-10-12: the `Monitor` tool, Claude Code's own wait-once tool, is allowed. | [`docs/decisions/agents-wait-with-monitor.md`](../docs/decisions/agents-wait-with-monitor.md) |
| `all-repos-switch-together` | Owner ruling Q1 a (the cutover), 2026-11-12 09:42 CST, relayed by the coordinator at 09:50 CST: the per-lane merge target of R42 part 2 (`docs/plans/restart-plan.md`, entry R42) takes effect together. | [`docs/decisions/all-repos-switch-together.md`](../docs/decisions/all-repos-switch-together.md) |
| `answered-needs-source` | The answered-source check, in the Stop hook `lint/report_guard.py` (rule `answered-needs-source`), refuses a reply when a line of it says "answered" and cites no source on that line. | [`docs/decisions/answered-needs-source.md`](../docs/decisions/answered-needs-source.md) |
| `ask-commands-run-alone` | An agent never chains a command that needs the owner's answer onto other commands in one shell call (owner, 2026-10-14). | [`docs/decisions/ask-commands-run-alone.md`](../docs/decisions/ask-commands-run-alone.md) |
| `audit-rework-order` | Owner, 2026-10-16 10:50 CDT. | [`docs/decisions/audit-rework-order.md`](../docs/decisions/audit-rework-order.md) |
| `auto-mode-owner-acts` | Owner, 2026-10-30 16:24 CDT, relayed by the coordinator session: the auto-mode classifier keeps refusing the coordinator's routine acts, which the owner always grants. | [`docs/decisions/auto-mode-owner-acts.md`](../docs/decisions/auto-mode-owner-acts.md) |
| `background-check-through-verdict` | No owner ruling yet. | [`docs/decisions/background-check-through-verdict.md`](../docs/decisions/background-check-through-verdict.md) |
| `background-needs-end-note` | Owner, 2026-10-13 23:41 CDT: "End condition at start." | [`docs/decisions/background-needs-end-note.md`](../docs/decisions/background-needs-end-note.md) |
| `bare-bash-on-windows-can-resolve-to-the-wsl-stub` | Python code on Windows never hands `subprocess.run` a bare `"bash"` or `"gh"`. | [`docs/decisions/bare-bash-on-windows-can-resolve-to-the-wsl-stub.md`](../docs/decisions/bare-bash-on-windows-can-resolve-to-the-wsl-stub.md) |
| `batch-freeze-lane-set` | The batch runner freezes a batch's lane set when the build starts. | [`docs/decisions/batch-freeze-lane-set.md`](../docs/decisions/batch-freeze-lane-set.md) |
| `blind-briefs-use-a-template` | Owner, 2026-10-26 22:58 CDT, on the mailaudit Duo mockups: "not a single one of them tried to break the mold". | [`docs/decisions/blind-briefs-use-a-template.md`](../docs/decisions/blind-briefs-use-a-template.md) |
| `brief-claim-has-probe` | Rule `brief-claim-has-probe` in `hooks/guard.py` refuses an Agent or Task brief to a builder or a test-author that claims what main passes or refuses for an input. | [`docs/decisions/brief-claim-has-probe.md`](../docs/decisions/brief-claim-has-probe.md) |
| `brief-destructive-git` | Rule `brief-destructive-git` in `hooks/guard.py` refuses an Agent, Task or Workflow spawn to a writing role whose brief orders a working-tree discard (rule `shared-trees-no-destructive-git`). | [`docs/decisions/brief-destructive-git.md`](../docs/decisions/brief-destructive-git.md) |
| `browser-prompts-are-the-apps` | Owner, 2026-10-11: claude-settings cannot disable the built-in browser pane's approval prompts on outside sites. | [`docs/decisions/browser-prompts-are-the-apps.md`](../docs/decisions/browser-prompts-are-the-apps.md) |
| `build-dirs-reaped-at-agent-end` | Owner, 2026-10-11: the agent-end reap also deletes build folders. | [`docs/decisions/build-dirs-reaped-at-agent-end.md`](../docs/decisions/build-dirs-reaped-at-agent-end.md) |
| `builders-cannot-edit-tests` | A builder that cannot pass a test must not delete, skip or rewrite it. | [`docs/decisions/builders-cannot-edit-tests.md`](../docs/decisions/builders-cannot-edit-tests.md) |
| `checks-share-the-clause-parser` | The checks that read prose by sentence and clause use one module, `lint/_clause.py`. | [`docs/decisions/checks-share-the-clause-parser.md`](../docs/decisions/checks-share-the-clause-parser.md) |
| `child-cites-not-copies` | Owner, 2026-11-02 10:41 CST, ruling fb-1041-2 ("Stop rule churn and drift in the other repos"): | [`docs/decisions/child-cites-not-copies.md`](../docs/decisions/child-cites-not-copies.md) |
| `ci-cut-in-steps` | Owner, 2026-10-27 12:07 CDT (waiting page item 31, pick e), roadmap step c95: trust first, then cut CI in steps. | [`docs/decisions/ci-cut-in-steps.md`](../docs/decisions/ci-cut-in-steps.md) |
| `ci-job-caps` | Owner, 2026-11-01 18:44 CST: each owner repo raises its job caps generously, as a stopgap, until its time-pinned tests are gone. | [`docs/decisions/ci-job-caps.md`](../docs/decisions/ci-job-caps.md) |
| `ci-step2-bar` | Owner, 2026-10-28 13:40 CDT (waiting page item 34, pick b), roadmap step c95, step 2: count the real Windows or Mac bugs that reach main, and weigh that count against what step 2 saves. | [`docs/decisions/ci-step2-bar.md`](../docs/decisions/ci-step2-bar.md) |
| `ci-unknown-is-red` | A lint that cannot read its input prints UNKNOWN. | [`docs/decisions/ci-unknown-is-red.md`](../docs/decisions/ci-unknown-is-red.md) |
| `cite-by-id-refuses-unread-file` | Owner, 2026-10-17 11:40 CDT (guard audit, finding 7): the guard refuses `git commit -F <file>` when it cannot read the file at hook time. | [`docs/decisions/cite-by-id-refuses-unread-file.md`](../docs/decisions/cite-by-id-refuses-unread-file.md) |
| `claude-md-shrink` | Owner, 2026-10-16 23:53 CDT and 2026-10-17 00:40 CDT: | [`docs/decisions/claude-md-shrink.md`](../docs/decisions/claude-md-shrink.md) |
| `commit-hook-bypass-refused` | The guard refuses a `git commit`, `git merge` or `git push` that skips git hooks (rule `hook-bypass`). | [`docs/decisions/commit-hook-bypass-refused.md`](../docs/decisions/commit-hook-bypass-refused.md) |
| `commit-refuses-conflict-markers` | Rule `conflict-markers` in `hooks/guard.py` refuses a commit or a push that would carry git conflict markers. | [`docs/decisions/commit-refuses-conflict-markers.md`](../docs/decisions/commit-refuses-conflict-markers.md) |
| `config-watch-fast-exit` | Owner, 2026-10-20. | [`docs/decisions/config-watch-fast-exit.md`](../docs/decisions/config-watch-fast-exit.md) |
| `copy-mode-overwrites-no-backup` | Owner: in copy mode, an installer overwrites its own old copy and keeps no backup. | [`docs/decisions/copy-mode-overwrites-no-backup.md`](../docs/decisions/copy-mode-overwrites-no-backup.md) |
| `cost-line-pinned` | A Cost sentence may name a file or state a count only when the same sentence backs it: | [`docs/decisions/cost-line-pinned.md`](../docs/decisions/cost-line-pinned.md) |
| `cross-repo-question-checked` | An open decision or task on a repo's waiting page names the repo it is about. | [`docs/decisions/cross-repo-question-checked.md`](../docs/decisions/cross-repo-question-checked.md) |
| `cull-guard-wrong-refusals` | It sits beside decision `cull-rules` (how a cull runs, owner ruling 2026-10-17). | [`docs/decisions/cull-guard-wrong-refusals.md`](../docs/decisions/cull-guard-wrong-refusals.md) |
| `cull-rules` | Owner ruling, 2026-10-17 11:56 CDT. | [`docs/decisions/cull-rules.md`](../docs/decisions/cull-rules.md) |
| `debt-close-runs-retire` | A PR closes a debt when it deletes the debt file, or renames it out of `docs/debts/`. | [`docs/decisions/debt-close-runs-retire.md`](../docs/decisions/debt-close-runs-retire.md) |
| `decision-watch-mod-limits` | The decision watch runs as a mod on the app's own login, so an expired CLI login no longer silences it. | [`docs/decisions/decision-watch-mod-limits.md`](../docs/decisions/decision-watch-mod-limits.md) |
| `decisions-reach-a-clickable-pick` | Roadmap step c118, 2026-10-27, rewritten under owner ruling 2026-11-01 23:31 CST (decision `questions-go-to-owner`, "Same turn to the page"). | [`docs/decisions/decisions-reach-a-clickable-pick.md`](../docs/decisions/decisions-reach-a-clickable-pick.md) |
| `default-branch-read-order` | Owner, 2026-10-16: the branch-delete rule, the janitor sweep and the push guard read the default branch in this order. | [`docs/decisions/default-branch-read-order.md`](../docs/decisions/default-branch-read-order.md) |
| `dependabot-security-only` | Owner, 2026-10-16: security updates only. | [`docs/decisions/dependabot-security-only.md`](../docs/decisions/dependabot-security-only.md) |
| `design-agents` | Owner, 2026-11-04 07:56 CST (Cockpit item 204 a): the design reviewer runs beside review round 1, on the first built head, so design fixes ride the normal review rounds. | [`docs/decisions/design-agents.md`](../docs/decisions/design-agents.md) |
| `design-skills` | Owner, 2026-10-10: three third-party skills apply to any repo with screens. | [`docs/decisions/design-skills.md`](../docs/decisions/design-skills.md) |
| `detached-launch-refused` | The `detached-launch` rule in `hooks/guard.py` refuses a command that starts a process and detaches it from the session. | [`docs/decisions/detached-launch-refused.md`](../docs/decisions/detached-launch-refused.md) |
| `docs-only-prs-skip-review` | A pull request that changes only prose or docs, and touches no rule, guard, check or product code, gets no full review. | [`docs/decisions/docs-only-prs-skip-review.md`](../docs/decisions/docs-only-prs-skip-review.md) |
| `draft-until-reviewed` | Owner, 2026-10-10 and 2026-10-13: every PR opens as a draft, and CI skips draft PRs. | [`docs/decisions/draft-until-reviewed.md`](../docs/decisions/draft-until-reviewed.md) |
| `duo-fold-tool` | bin/duo-fold is the one fold for the iPhone Duo simulator | [`docs/decisions/duo-fold-tool.md`](../docs/decisions/duo-fold-tool.md) |
| `env-file-stays-unread` | No session reads, writes or commits the contents of an environment file. | [`docs/decisions/env-file-stays-unread.md`](../docs/decisions/env-file-stays-unread.md) |
| `express-batch-per-act` | Owner ruling R55 (how each act of R42 part 2, a merge-flow step, merges), 2026-11-12 13:21 CST. | [`docs/decisions/express-batch-per-act.md`](../docs/decisions/express-batch-per-act.md) |
| `feel-fix-waits-device-check` | A feel-fix is a change to how a screen feels: its motion, touch, timing or scroll. | [`docs/decisions/feel-fix-waits-device-check.md`](../docs/decisions/feel-fix-waits-device-check.md) |
| `fewest-words-mandate` | Fewest words, most of all in front-end copy | [`docs/decisions/fewest-words-mandate.md`](../docs/decisions/fewest-words-mandate.md) |
| `frozen-path-resolves-shell-vars` | Before rule 7 (frozen-path) matches the target of a shell write, it reads the command left to right. | [`docs/decisions/frozen-path-resolves-shell-vars.md`](../docs/decisions/frozen-path-resolves-shell-vars.md) |
| `git-env-set-refused` | No agent command may set `GIT_DIR`, `GIT_WORK_TREE` or `GIT_INDEX_FILE`. | [`docs/decisions/git-env-set-refused.md`](../docs/decisions/git-env-set-refused.md) |
| `github-apps-keep-access` | Owner, 2026-10-28 14:40 CDT (waiting page item 9, roadmap step c153): keep the access that Renovate, Cloudflare and Render have to claude-settings as it is. | [`docs/decisions/github-apps-keep-access.md`](../docs/decisions/github-apps-keep-access.md) |
| `glossary-meets-owner-halfway` | Owner, 2026-11-01 18:46 CST: a session reads what the owner types by meaning, and the glossary keeps one name per thing. | [`docs/decisions/glossary-meets-owner-halfway.md`](../docs/decisions/glossary-meets-owner-halfway.md) |
| `guard-command-position` | One resolver in `hooks/guard_core.py` finds the command word for every rule. | [`docs/decisions/guard-command-position.md`](../docs/decisions/guard-command-position.md) |
| `guard-guards-mistakes-only` | Owner, 2026-10-17 09:07 CDT, "widen": every guard and check stops Claude's mistakes, never an attacker. | [`docs/decisions/guard-guards-mistakes-only.md`](../docs/decisions/guard-guards-mistakes-only.md) |
| `guard-hooks-fail-closed` | Owner, 2026-10-12: a guard whose script or python is missing refuses the call. | [`docs/decisions/guard-hooks-fail-closed.md`](../docs/decisions/guard-hooks-fail-closed.md) |
| `guard-linked-node-modules` | Yes. | [`docs/decisions/guard-linked-node-modules.md`](../docs/decisions/guard-linked-node-modules.md) |
| `guard-log-read-weekly` | Owner, 2026-10-13. | [`docs/decisions/guard-log-read-weekly.md`](../docs/decisions/guard-log-read-weekly.md) |
| `guard-remedy-not-to-owner` | Question: where does a Stop refusal's remedy live when the owner sees the refusal in chat? | [`docs/decisions/guard-remedy-not-to-owner.md`](../docs/decisions/guard-remedy-not-to-owner.md) |
| `guard-that-cries-wolf-is-spent` | CLAUDE.md: "Trust a guard only once it goes red on the defect it guards." The other half: a guard that goes red when nothing is wrong is spent, because the reader stops reading it. | [`docs/decisions/guard-that-cries-wolf-is-spent.md`](../docs/decisions/guard-that-cries-wolf-is-spent.md) |
| `haiku-prompt-hooks` | **Prompt hooks judge rules that no script can parse.** Each refuses the call when it finds a breach (owner ruling 2026-10-07). | [`docs/decisions/haiku-prompt-hooks.md`](../docs/decisions/haiku-prompt-hooks.md) |
| `hold-unsafe-after-round-3` | Owner, 2026-10-15 12:00 CDT. | [`docs/decisions/hold-unsafe-after-round-3.md`](../docs/decisions/hold-unsafe-after-round-3.md) |
| `hook-if-filters` | Owner, 2026-10-21. | [`docs/decisions/hook-if-filters.md`](../docs/decisions/hook-if-filters.md) |
| `hook-inputs-carry-token-counts` | c151 is the plan item "compaction timing reads message tokens, not total context". | [`docs/decisions/hook-inputs-carry-token-counts.md`](../docs/decisions/hook-inputs-carry-token-counts.md) |
| `hooks-share-the-transcript-reader` | The Stop hooks read the transcript through one module, `lint/_transcript.py`. | [`docs/decisions/hooks-share-the-transcript-reader.md`](../docs/decisions/hooks-share-the-transcript-reader.md) |
| `idle-resume-compacts` | The owner reported (2026-11-01 17:54 CST): after a session sits idle for a couple of hours, the first thing it does on his reply is compact, whatever the context size. | [`docs/decisions/idle-resume-compacts.md`](../docs/decisions/idle-resume-compacts.md) |
| `install-hooks-whole` | No running session judges a call with a missing, short or mixed set of hook files. | [`docs/decisions/install-hooks-whole.md`](../docs/decisions/install-hooks-whole.md) |
| `ios-mac-install-first` | Owner, 2026-11-08 17:09 CST (Degen page item 157, pick b), confirmed 2026-11-09 03:35 CST (item 164, pick a): a Degen build reaches the phone by a box-served install first. | [`docs/decisions/ios-mac-install-first.md`](../docs/decisions/ios-mac-install-first.md) |
| `ios-ship-is-one-shared-tool` | Owner, 2026-10-25: one tool, `bin/ios-ship`, builds and ships the owner's iOS apps from the Mac. | [`docs/decisions/ios-ship-is-one-shared-tool.md`](../docs/decisions/ios-ship-is-one-shared-tool.md) |
| `item-field-rendered` | A field on a waiting item is for the owner to read. | [`docs/decisions/item-field-rendered.md`](../docs/decisions/item-field-rendered.md) |
| `lane-by-slug` | Owner, 2026-10-13 14:13 CDT, relayed by the oversight session: the guard refuses a session number that names a lane, such as `N20` or `(N16)`. | [`docs/decisions/lane-by-slug.md`](../docs/decisions/lane-by-slug.md) |
| `lanes-run-no-full-ci-job` | Owner, 2026-10-27 (waiting page item 27, option a): a lane runs only the suites its change touches. | [`docs/decisions/lanes-run-no-full-ci-job.md`](../docs/decisions/lanes-run-no-full-ci-job.md) |
| `lanes-start-as-agents` | Owner, 2026-11-04 07:56 CST, waiting-page item 168 (what a lane is), pick a: a lane is a session everywhere. | [`docs/decisions/lanes-start-as-agents.md`](../docs/decisions/lanes-start-as-agents.md) |
| `list-form-subprocess-ignores-a-path-shim-on-windows` | A blind-command fixture cannot shadow a real executable for a list-form subprocess call on Windows. | [`docs/decisions/list-form-subprocess-ignores-a-path-shim-on-windows.md`](../docs/decisions/list-form-subprocess-ignores-a-path-shim-on-windows.md) |
| `local-time-central` | Owner, 2026-10-12: a session tells the owner times in US Central (America/Chicago), DST-aware, 24-hour clock. | [`docs/decisions/local-time-central.md`](../docs/decisions/local-time-central.md) |
| `main-branch-protection` | `main` of shivinate7/claude-settings requires one check: `all-jobs-passed`, the job in `.github/workflows/checks.yml` that runs the shared action `actions/all-jobs-passed`. | [`docs/decisions/main-branch-protection.md`](../docs/decisions/main-branch-protection.md) |
| `map-facts-are-checked` | Owner, 2026-10-30 16:09 CDT. | [`docs/decisions/map-facts-are-checked.md`](../docs/decisions/map-facts-are-checked.md) |
| `map-lists-record-named` | Owner, Cockpit item 268 (`banchi-map-binary-hints`), choice a, 2026-11-06 13:08 CST: "Yes: list every file a decision or debt names." Not picked: "banchi only: map its 8 files", and "Accept the loss". | [`docs/decisions/map-lists-record-named.md`](../docs/decisions/map-lists-record-named.md) |
| `map-skill-lives-here` | Owner, 2026-10-16: `skills/plain-english-map/` in claude-settings is the one home of the skill. | [`docs/decisions/map-skill-lives-here.md`](../docs/decisions/map-skill-lives-here.md) |
| `map-tested-by-line` | Lane `map-tested-by-line`, 2026-11-05. | [`docs/decisions/map-tested-by-line.md`](../docs/decisions/map-tested-by-line.md) |
| `memory-is-never-a-rulings-only-home` | The owner's rulings must reach a tracked file. | [`docs/decisions/memory-is-never-a-rulings-only-home.md`](../docs/decisions/memory-is-never-a-rulings-only-home.md) |
| `merge-deletes-batch-lanes` | Owner pick A for R42 part 2 (per-lane merge). | [`docs/decisions/merge-deletes-batch-lanes.md`](../docs/decisions/merge-deletes-batch-lanes.md) |
| `merge-lock` | One lock holds each base branch while a merge run works on it. | [`docs/decisions/merge-lock.md`](../docs/decisions/merge-lock.md) |
| `merge-needs-current-base` | Owner pick A for R42 part 2 (per-lane merge). | [`docs/decisions/merge-needs-current-base.md`](../docs/decisions/merge-needs-current-base.md) |
| `merge-practices` | Owner, page item 150, pick a, 2026-11-06 12:58 CST ("Build the small proof"): decision `test-practices` stays the testing chapter. | [`docs/decisions/merge-practices.md`](../docs/decisions/merge-practices.md) |
| `mistake-means-missing-guard` | Owner, 2026-11-06 11:38 CST: AI sometimes assumes it broke something by accident. | [`docs/decisions/mistake-means-missing-guard.md`](../docs/decisions/mistake-means-missing-guard.md) |
| `mockup-home` | Git is each artifact's home (owner ruling fb-1458-1, 2026-11-02 14:58 CST, option A). | [`docs/decisions/mockup-home.md`](../docs/decisions/mockup-home.md) |
| `mods-deferred-table` | These mods stay deferred recordings on the repo. | [`docs/decisions/mods-deferred-table.md`](../docs/decisions/mods-deferred-table.md) |
| `mods-install-via-marketplace` | The shared `settings.json` declares one marketplace, `claude-settings`, from the GitHub repo `shivinate7/claude-settings`, with `autoUpdate` set to true. | [`docs/decisions/mods-install-via-marketplace.md`](../docs/decisions/mods-install-via-marketplace.md) |
| `mods-no-cli-key-headless` | No CLI API key for headless runs. | [`docs/decisions/mods-no-cli-key-headless.md`](../docs/decisions/mods-no-cli-key-headless.md) |
| `mutation-ci-report-and-replay` | Owner, 2026-11-05 07:41 CST (waiting-page item 163, Cockpit item `mutation-ci-job`, pick d): "Report only, plus known-bug replay". | [`docs/decisions/mutation-ci-report-and-replay.md`](../docs/decisions/mutation-ci-report-and-replay.md) |
| `mutation-report-scores-suites` | `hooks/mutate_guard.py --report` scores the suites of other verdict-deciding files with mechanical mutants, on demand. | [`docs/decisions/mutation-report-scores-suites.md`](../docs/decisions/mutation-report-scores-suites.md) |
| `no-merge-during-batch-ci` | State: live until the cutover (decision `all-repos-switch-together`). | [`docs/decisions/no-merge-during-batch-ci.md`](../docs/decisions/no-merge-during-batch-ci.md) |
| `no-merge-onto-red-main` | Owner ruling Q4 g (how a revert merges), 2026-11-12 09:46 CST, relayed by the coordinator at 09:50 CST: a revert is an ordinary lane PR, merged with `--base-red-ok`. | [`docs/decisions/no-merge-onto-red-main.md`](../docs/decisions/no-merge-onto-red-main.md) |
| `notes-merge-union` | `.gitattributes` gives `docs/debts/notes.md` git's built-in `merge=union` driver. | [`docs/decisions/notes-merge-union.md`](../docs/decisions/notes-merge-union.md) |
| `octopus-push-refused` | Rule `octopus-push` in `hooks/guard.py` refuses a `git push` whose new commits hold a merge with more than two parents. | [`docs/decisions/octopus-push-refused.md`](../docs/decisions/octopus-push-refused.md) |
| `one-layout-every-repo` | Every repo keeps each kind of file in the same place. | [`docs/decisions/one-layout-every-repo.md`](../docs/decisions/one-layout-every-repo.md) |
| `one-shared-record-stamp` | One shared parser in claude-settings handles every repo's record format. | [`docs/decisions/one-shared-record-stamp.md`](../docs/decisions/one-shared-record-stamp.md) |
| `opt-in-ci-templates-composite` | Eight templates any repo can adopt live in one home and one shape: a composite action under `actions/<name>/`, or a plain file where the template is no CI step. | [`docs/decisions/opt-in-ci-templates-composite.md`](../docs/decisions/opt-in-ci-templates-composite.md) |
| `option-keys-are-letters` | The waiting page shows an option by its position, as a letter: the first option is A, the second B (`skills/waiting-page/page.html`, symbol `letterOf`). | [`docs/decisions/option-keys-are-letters.md`](../docs/decisions/option-keys-are-letters.md) |
| `opus-grant-expires` | An Opus agent is enabled for one repository, on the owner's grant in chat (`roles-opus-override-guarded`). | [`docs/decisions/opus-grant-expires.md`](../docs/decisions/opus-grant-expires.md) |
| `owner-feedback-inbox` | A hook writes every owner message to a per-session inbox. | [`docs/decisions/owner-feedback-inbox.md`](../docs/decisions/owner-feedback-inbox.md) |
| `owner-judge-test` | A session asks the owner a decision only when he can judge it from what he already knows. | [`docs/decisions/owner-judge-test.md`](../docs/decisions/owner-judge-test.md) |
| `page-check-at-export` | Owner ruling, item 298 (14:17 CST Nov 6 2026): build both the check at export and the `--check` mode. | [`docs/decisions/page-check-at-export.md`](../docs/decisions/page-check-at-export.md) |
| `page-item-design` | An item write whose picture the page would refuse, or would draw as a thin strip, is refused at write, with the page's own sentence. | [`docs/decisions/page-item-design.md`](../docs/decisions/page-item-design.md) |
| `page-stale-publish` | Every republish of a waiting page is main's `skills/waiting-page/page.html` with the live `designData` and roadmap blocks kept, never the live page's own code (decision `questions-go-to-owner`, skill `waiting-page`, "Keep the page on main's code"). | [`docs/decisions/page-stale-publish.md`](../docs/decisions/page-stale-publish.md) |
| `plain-prose-lint` | The STE lint is a plain-prose lint. | [`docs/decisions/plain-prose-lint.md`](../docs/decisions/plain-prose-lint.md) |
| `plain-push-asks` | Two kinds of push that are not forced ask. | [`docs/decisions/plain-push-asks.md`](../docs/decisions/plain-push-asks.md) |
| `plan-refuter` | Owner, 2026-11-06 12:43 CST, waiting-page item 279, pick d. | [`docs/decisions/plan-refuter.md`](../docs/decisions/plan-refuter.md) |
| `playwright-browsers-path` | No command sets PLAYWRIGHT_BROWSERS_PATH to work around a missing browser build. | [`docs/decisions/playwright-browsers-path.md`](../docs/decisions/playwright-browsers-path.md) |
| `playwright-install-once` | Rule `playwright-install` in `hooks/guard.py`: | [`docs/decisions/playwright-install-once.md`](../docs/decisions/playwright-install-once.md) |
| `port-keeps-behaviour` | Owner, 2026-10-27 15:32 CDT: when a session ports or redesigns an existing app, the working app already answers most questions. | [`docs/decisions/port-keeps-behaviour.md`](../docs/decisions/port-keeps-behaviour.md) |
| `pr-review-record` | Owner, 2026-11-01 04:26 CST, waiting-page item 113 a. | [`docs/decisions/pr-review-record.md`](../docs/decisions/pr-review-record.md) |
| `precompact-handoff` | Auto-compact drops detail. | [`docs/decisions/precompact-handoff.md`](../docs/decisions/precompact-handoff.md) |
| `predicate-is-the-act` | Judge a guard by the act it must catch, never by the spelling of the act. | [`docs/decisions/predicate-is-the-act.md`](../docs/decisions/predicate-is-the-act.md) |
| `premise-format` | A premise is a statement, not a fact. | [`docs/decisions/premise-format.md`](../docs/decisions/premise-format.md) |
| `process-args-guard` | The guard refuses a shell command that prints the full arguments of other processes (rule `process-args`): | [`docs/decisions/process-args-guard.md`](../docs/decisions/process-args-guard.md) |
| `push-skip-on-proven-tree` | Owner, item 729 a (relayed by the coordinator, 2026-11-13 12:29 CST), extended by ruling `own-769-a-narrowed-pr-push` (owner, 16:03 CST, "main skips the whole run after a passing PR run"): the `push-skip` job skips a push to main in one case. | [`docs/decisions/push-skip-on-proven-tree.md`](../docs/decisions/push-skip-on-proven-tree.md) |
| `question-form` | Owner steer, 2026-10-30 12:50 CDT: a question to the owner has one form and one guard, for the chat question box (`AskUserQuestion`) and for a waiting-page item write. | [`docs/decisions/question-form.md`](../docs/decisions/question-form.md) |
| `question-reviewer-agent-hook` | Owner rulings, 2026-10-22 10:18 CDT: | [`docs/decisions/question-reviewer-agent-hook.md`](../docs/decisions/question-reviewer-agent-hook.md) |
| `questions-go-to-owner` | Owner, 2026-10-26: a session with a question brings it to the owner. | [`docs/decisions/questions-go-to-owner.md`](../docs/decisions/questions-go-to-owner.md) |
| `recovery-independent-of-state` | A recovery control exists for the moment its own precondition is false. | [`docs/decisions/recovery-independent-of-state.md`](../docs/decisions/recovery-independent-of-state.md) |
| `red-run-trailer-on-test-commits` | `lint/check_red_run.py` is the one home. | [`docs/decisions/red-run-trailer-on-test-commits.md`](../docs/decisions/red-run-trailer-on-test-commits.md) |
| `refusals-reach-the-owner` | Owner-side goal: when the auto-mode classifier refuses a tool call, the owner hears of it in the session's reply. | [`docs/decisions/refusals-reach-the-owner.md`](../docs/decisions/refusals-reach-the-owner.md) |
| `relayed-grant-read-from-page` | Owner ask ask-mw3lqb8bwx, 2026-11-05 07:49 CST, verbatim: "i need sessions to be able to relay my word to other cloud sessions and it be trust worthy add in auto mode". | [`docs/decisions/relayed-grant-read-from-page.md`](../docs/decisions/relayed-grant-read-from-page.md) |
| `reply-judge-samples-never-refuses` | The Stop reply judge is `hooks/reply_judge.py`, a command hook (owner ruling 2026-10-12), because a prompt hook cannot exit on a field in code. | [`docs/decisions/reply-judge-samples-never-refuses.md`](../docs/decisions/reply-judge-samples-never-refuses.md) |
| `repo-kind-and-caution` | Owner, 2026-10-27 00:30 and 00:31 CDT, roadmap step c115: about 1 in 5 home sessions refuse to log in to the owner's own Home Assistant or KEF speakers. | [`docs/decisions/repo-kind-and-caution.md`](../docs/decisions/repo-kind-and-caution.md) |
| `reuse-needs-checkout-proof` | Lanes run in separate worktrees of one clone. | [`docs/decisions/reuse-needs-checkout-proof.md`](../docs/decisions/reuse-needs-checkout-proof.md) |
| `rework-leaves-page` | An open item on the waiting page is one the owner can answer now. | [`docs/decisions/rework-leaves-page.md`](../docs/decisions/rework-leaves-page.md) |
| `rewrite-cite-predates-ruling` | The report guard (`lint/report_guard.py`) checks each landed turn's reply. | [`docs/decisions/rewrite-cite-predates-ruling.md`](../docs/decisions/rewrite-cite-predates-ruling.md) |
| `rm-after-cd-names-absolute-path` | Rule `rm-after-cd` in `hooks/guard.py` refuses a recursive `rm` (`-r`, `-R`, `--recursive`) with a relative target, when a `cd` joined by `;`, `&&` or a newline came before it in the same command. | [`docs/decisions/rm-after-cd-names-absolute-path.md`](../docs/decisions/rm-after-cd-names-absolute-path.md) |
| `rm-on-a-variable-needs-a-guard` | Bypass-mode sessions must not wait on the owner for Claude Code's critical-path `rm` prompt (owner ruling 2026-10-11). | [`docs/decisions/rm-on-a-variable-needs-a-guard.md`](../docs/decisions/rm-on-a-variable-needs-a-guard.md) |
| `rulings-declare-kind` | A decision record that a pull request adds or changes must say what kind each ruling is: a build task, or a process change. | [`docs/decisions/rulings-declare-kind.md`](../docs/decisions/rulings-declare-kind.md) |
| `rulings-land-once-per-sitting` | Owner, 2026-11-02 10:41 CST, ruling fb-1041-2 ("Stop rule churn and drift in the other repos"): | [`docs/decisions/rulings-land-once-per-sitting.md`](../docs/decisions/rulings-land-once-per-sitting.md) |
| `safe-stop-queues-one-prompt` | `/safe-stop` is a command of the session-board mod (`session-board-mod-limits`, session-board keeps small records). | [`docs/decisions/safe-stop-queues-one-prompt.md`](../docs/decisions/safe-stop-queues-one-prompt.md) |
| `same-check-kinds` | Owner, 2026-10-30 15:03 CDT, waiting item 87: every owner repo runs the same kinds of checks, judged by the same outcomes. | [`docs/decisions/same-check-kinds.md`](../docs/decisions/same-check-kinds.md) |
| `scratchpad-commit-msg-owner` | The guard refuses a `git commit` from an agent's call when a `-F` or `--file` message file (not `-`) resolves, by real path, into any session's scratchpad. | [`docs/decisions/scratchpad-commit-msg-owner.md`](../docs/decisions/scratchpad-commit-msg-owner.md) |
| `scratchpad-owner` | The rule `scratchpad-owner` in `hooks/guard.py` refuses when an agent runs or overwrites a scratchpad file that another agent of its session wrote. | [`docs/decisions/scratchpad-owner.md`](../docs/decisions/scratchpad-owner.md) |
| `sendmessage-session-id-refused` | Rule `sendmessage-session-id` in `hooks/guard.py` refuses a `SendMessage` call whose `to` is a string that starts `session_`. | [`docs/decisions/sendmessage-session-id-refused.md`](../docs/decisions/sendmessage-session-id-refused.md) |
| `session-board-mod-limits` | The session-board mod (`mods/session-board`, commands `/board` and `/safe-stop`) gives one view of all sessions and a safe stopping point, with no typing of "status?" into each one. | [`docs/decisions/session-board-mod-limits.md`](../docs/decisions/session-board-mod-limits.md) |
| `session-end-sweep-is-disarmed-until-liveness-is-proven` | The `SessionEnd` hook in `settings.json` runs `janitor/session_end_sweep.py`. | [`docs/decisions/session-end-sweep-is-disarmed-until-liveness-is-proven.md`](../docs/decisions/session-end-sweep-is-disarmed-until-liveness-is-proven.md) |
| `session-tiers` | Owner rulings, 2026-10-28 CDT unless dated. | [`docs/decisions/session-tiers.md`](../docs/decisions/session-tiers.md) |
| `shared-resource-owner` | Owner, 2026-10-27 13:22 CDT (cmsg_01DoF7thf3iq2Srr1UsfXgh2FS8R88VGL2A75ER5mnDyai), roadmap step c140: the HA Green box (4 GB) is loaded by home, degen and mailaudit. | [`docs/decisions/shared-resource-owner.md`](../docs/decisions/shared-resource-owner.md) |
| `shoot-is-one-shared-command` | Owner, 2026-10-17: build one screenshot script in this repo. | [`docs/decisions/shoot-is-one-shared-command.md`](../docs/decisions/shoot-is-one-shared-command.md) |
| `silent-undo-check-design` | `lint/check_silent_undo.py` is the one home. | [`docs/decisions/silent-undo-check-design.md`](../docs/decisions/silent-undo-check-design.md) |
| `sim-boot-is-verified` | The record hook of `sweep-shuts-down-idle-simulators` (ruling 1) checks each device that an MCP `launch` took from `Shutdown` to `Booted`, and each device that an overridden `simctl boot` took the same way. | [`docs/decisions/sim-boot-is-verified.md`](../docs/decisions/sim-boot-is-verified.md) |
| `sim-lease-tool` | bin/sim-lease is the one simulator queue and lease on a Mac | [`docs/decisions/sim-lease-tool.md`](../docs/decisions/sim-lease-tool.md) |
| `sim-test-is-the-one-boot-path` | One lock makes sim-test the one boot path on a Mac | [`docs/decisions/sim-test-is-the-one-boot-path.md`](../docs/decisions/sim-test-is-the-one-boot-path.md) |
| `sim-test-stops-a-crash-loop` | sim-test stops a simulator that crash-loops | [`docs/decisions/sim-test-stops-a-crash-loop.md`](../docs/decisions/sim-test-stops-a-crash-loop.md) |
| `source-prose-lint-ships-dark` | The comment-and-docstring mode of `ste_lint.py` stays off by default (`--source-prose` and `check_source`). | [`docs/decisions/source-prose-lint-ships-dark.md`](../docs/decisions/source-prose-lint-ships-dark.md) |
| `spawns-use-no-window` | Owner, 2026-10-19 16:20 CDT: helper programs that hooks, mods and tools start use the "no window" option. | [`docs/decisions/spawns-use-no-window.md`](../docs/decisions/spawns-use-no-window.md) |
| `stable-branch` | Owner approved the design with the refuter's changes, 2026-11-12 09:48 CST, relayed by the coordinator at 09:50 CST. | [`docs/decisions/stable-branch.md`](../docs/decisions/stable-branch.md) |
| `stable-fallback-warn` | Orchestrator pick, not an owner ruling, recorded 2026-11-12 15:27 CST under R42 part 2. | [`docs/decisions/stable-fallback-warn.md`](../docs/decisions/stable-fallback-warn.md) |
| `stale-safe-force-push` | The owner gets no prompt for a safe push, and no push overwrites newer remote work with a stale copy. | [`docs/decisions/stale-safe-force-push.md`](../docs/decisions/stale-safe-force-push.md) |
| `stall-watch` | The session learns within minutes that a background command stalled, and diagnoses the cause. | [`docs/decisions/stall-watch.md`](../docs/decisions/stall-watch.md) |
| `standing-merge-grant` | Owner rulings, 2026-10-10, 2026-10-29 16:47 CDT, 2026-10-29 20:33 CDT, 2026-10-30 15:06 CDT, 2026-11-01 17:37 CST, 2026-11-01 19:23 CST, 2026-11-02 14:02 CST, 2026-11-02 15:14 CST and 2026-11-02 15:38 CST. | [`docs/decisions/standing-merge-grant.md`](../docs/decisions/standing-merge-grant.md) |
| `stash-stack-is-a-shared-subject` | CLAUDE.md says: "A stash entry belongs to no branch." The guard reads `git stash` against the whole stack, not only the working tree. | [`docs/decisions/stash-stack-is-a-shared-subject.md`](../docs/decisions/stash-stack-is-a-shared-subject.md) |
| `ste-guard-fixes-not-nags` | Owner, 2026-10-22 10:10 CDT: `settings.json` wires no STE write guard (`ste_gate.py`) and no markdown sweep (`md_sweep.py`). | [`docs/decisions/ste-guard-fixes-not-nags.md`](../docs/decisions/ste-guard-fixes-not-nags.md) |
| `stop-guardrail-became-a-command-hook` | The Stop guardrail is never a `type: agent` hook. | [`docs/decisions/stop-guardrail-became-a-command-hook.md`](../docs/decisions/stop-guardrail-became-a-command-hook.md) |
| `sweep-shuts-down-idle-simulators` | Sessions boot simulators. The sweep stops idle ones. | [`docs/decisions/sweep-shuts-down-idle-simulators.md`](../docs/decisions/sweep-shuts-down-idle-simulators.md) |
| `swift-tests-at-milestones` | Owner, 2026-10-27 12:07 CDT, roadmap step c95 (decision `ci-cut-in-steps`, step 3, milestone runs): full-scale test runs happen at milestones, not on every merge. | [`docs/decisions/swift-tests-at-milestones.md`](../docs/decisions/swift-tests-at-milestones.md) |
| `task-names-its-check` | A session never hands the owner an act that a session can do. | [`docs/decisions/task-names-its-check.md`](../docs/decisions/task-names-its-check.md) |
| `test-practices` | A test must catch a real defect before the person meets it; a test that misses it, or fails with no defect, costs time and trust and catches nothing. | [`docs/decisions/test-practices.md`](../docs/decisions/test-practices.md) |
| `test-strategy-reset` | A test must not fail on runner speed. | [`docs/decisions/test-strategy-reset.md`](../docs/decisions/test-strategy-reset.md) |
| `test-temp-standard` | Each test run writes temp files only in its own run folder, under one temp root per repo, and removes that folder at teardown. | [`docs/decisions/test-temp-standard.md`](../docs/decisions/test-temp-standard.md) |
| `the-janitor-is-one-machine-wide-sweep` | The sweep deletes a local branch that holds no unique work. | [`docs/decisions/the-janitor-is-one-machine-wide-sweep.md`](../docs/decisions/the-janitor-is-one-machine-wide-sweep.md) |
| `trust-error-docs-silent` | Written 2026-11-11 22:52 CST. | [`docs/decisions/trust-error-docs-silent.md`](../docs/decisions/trust-error-docs-silent.md) |
| `unattended-sweep-stops-proven-orphans` | **What an unattended run can stop.** A `--confirm` run, run by the SessionEnd hook or the scheduled task, can send one signal to one process. | [`docs/decisions/unattended-sweep-stops-proven-orphans.md`](../docs/decisions/unattended-sweep-stops-proven-orphans.md) |
| `uniform-over-variants` | Owner, 2026-10-27 12:51 CDT, topic t18 (one home, then variants): when a repo differs from a shared format, the repo changes to match it. | [`docs/decisions/uniform-over-variants.md`](../docs/decisions/uniform-over-variants.md) |
| `ux-house-rules` | The UX rules that every repo with screens shares, beyond the three third-party sets, live in `docs/design/`. | [`docs/decisions/ux-house-rules.md`](../docs/decisions/ux-house-rules.md) |
| `verdict-pipe-refused` | The `verdict-pipe` rule in `hooks/guard.py` refuses a shell command (Bash or PowerShell) that pipes the output of `verdict` into another command, such as `verdict <cmd> \| tail`. | [`docs/decisions/verdict-pipe-refused.md`](../docs/decisions/verdict-pipe-refused.md) |
| `waiting-data-in-repo` | Git is each artifact's home. | [`docs/decisions/waiting-data-in-repo.md`](../docs/decisions/waiting-data-in-repo.md) |
| `when-a-worktree-may-be-removed` | Four idle limits. | [`docs/decisions/when-a-worktree-may-be-removed.md`](../docs/decisions/when-a-worktree-may-be-removed.md) |
| `windows-temp-sweep` | A session's temp folder goes after its transcript is idle 24 hours | [`docs/decisions/windows-temp-sweep.md`](../docs/decisions/windows-temp-sweep.md) |
| `workflow-args-shape-check` | The guard refuses a `Workflow` call whose `args` is a placeholder (rule `workflow-args-shape-check`). | [`docs/decisions/workflow-args-shape-check.md`](../docs/decisions/workflow-args-shape-check.md) |
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
| `claims-carry-backing` | Owner goal, 2026-11-06 11:36 CST: every definitive prose claim is backed and verifiable. | [`docs/decisions/claims-carry-backing.md`](../docs/decisions/claims-carry-backing.md) |
| `claude-md-change-is-flagged` | Owner, 2026-10-16: report only, no hold. | [`docs/decisions/claude-md-change-is-flagged.md`](../docs/decisions/claude-md-change-is-flagged.md) |
| `cloud-start-hooks-run-fresh` | In a cloud session, `install.sh --cloud` runs the repo's startup hooks itself, after it has copied them into `~/.claude`. | [`docs/decisions/cloud-start-hooks-run-fresh.md`](../docs/decisions/cloud-start-hooks-run-fresh.md) |
| `compliance-defined` | Owner, 2026-10-31 15:04 CDT, waiting-page item 104: a claude-settings rule wins over a child repo's text on the same question, unless that text names the rule as a known exemption. | [`docs/decisions/compliance-defined.md`](../docs/decisions/compliance-defined.md) |
| `grant-reaches-lanes` | Owner, Cockpit item 152 (grant-plan-signoff), saved 2026-11-03 18:21 CST: pick a, sign off the plan `docs/plans/grant-reaches-lanes.md` as written. | [`docs/decisions/grant-reaches-lanes.md`](../docs/decisions/grant-reaches-lanes.md) |
| `guard-reads-wrapped-commands` | The guards judge the command a wrapper runs, not the raw text. | [`docs/decisions/guard-reads-wrapped-commands.md`](../docs/decisions/guard-reads-wrapped-commands.md) |
| `hook-catalog-page` | `docs/catalog.md` lists every hook, judge, mod and skill. | [`docs/decisions/hook-catalog-page.md`](../docs/decisions/hook-catalog-page.md) |
| `install-manifest-prunes` | Coordinator brief, lane install-drops-retired-files (2026-11-01): each install removes a file it landed earlier that main no longer ships. | [`docs/decisions/install-manifest-prunes.md`](../docs/decisions/install-manifest-prunes.md) |
| `install-refuses-linked-tree` | The installer refuses a linked worktree. | [`docs/decisions/install-refuses-linked-tree.md`](../docs/decisions/install-refuses-linked-tree.md) |
| `install-sh-stays-off-windows` | `install.sh` does nothing on Windows. | [`docs/decisions/install-sh-stays-off-windows.md`](../docs/decisions/install-sh-stays-off-windows.md) |
| `lanes-start-in-tool-worktrees` | Owner, 2026-10-21: refuse the hand-made worktree fully, and record which layer refused isolation. | [`docs/decisions/lanes-start-in-tool-worktrees.md`](../docs/decisions/lanes-start-in-tool-worktrees.md) |
| `machine-load-brake` | Owner, 2026-10-21 (spec), 2026-10-22 (foreground), 2026-10-23 (disk) and 2026-10-25 (CPU dropped: a 200 ms sample is noise; memory and disk are what stall a machine). | [`docs/decisions/machine-load-brake.md`](../docs/decisions/machine-load-brake.md) |
| `merge-confirm-repo` | Orchestrator call (lane merge-repo-dir-flag); the owner may rule otherwise. | [`docs/decisions/merge-confirm-repo.md`](../docs/decisions/merge-confirm-repo.md) |
| `merge-reinstalls-from-main` | The links in `~/.claude` point at one pinned checkout. | [`docs/decisions/merge-reinstalls-from-main.md`](../docs/decisions/merge-reinstalls-from-main.md) |
| `one-browser-setup-no-apt` | Roadmap step c78 (one shared browser-test setup), 2026-10-26: one composite action installs the browser-test setup for every repo, so a CI fix lands once. | [`docs/decisions/one-browser-setup-no-apt.md`](../docs/decisions/one-browser-setup-no-apt.md) |
| `owner-override` | The owner starts a prompt with the word `override`. | [`docs/decisions/owner-override.md`](../docs/decisions/owner-override.md) |
| `plain-diff-mod-limits` | The plain-diff mod (`mods/plain-diff`, command `/plain-diff`) sends a diff to `$.model.complete` only for a file that passes the secret filter. | [`docs/decisions/plain-diff-mod-limits.md`](../docs/decisions/plain-diff-mod-limits.md) |
| `plan-needs-refuter` | Ruling: coordinator, 2026-11-06 12:37 CST, pick a. | [`docs/decisions/plan-needs-refuter.md`](../docs/decisions/plan-needs-refuter.md) |
| `pointer-edit` | The guard refuses a Write, Edit, MultiEdit or NotebookEdit whose target is one of the pointer checkout's own files. | [`docs/decisions/pointer-edit.md`](../docs/decisions/pointer-edit.md) |
| `post-merge-hook-is-a-fallback` | Owner, 2026-10-22: `install.ps1` writes its git post-merge hook only when it installs a copy, not a link. | [`docs/decisions/post-merge-hook-is-a-fallback.md`](../docs/decisions/post-merge-hook-is-a-fallback.md) |
| `pr-ledger` | Owner, 2026-11-07 12:22 CST, in chat to the coordinator. | [`docs/decisions/pr-ledger.md`](../docs/decisions/pr-ledger.md) |
| `records-index-at-merge` | Each repo that keeps records has one generated index page, `docs/records.md`. | [`docs/decisions/records-index-at-merge.md`](../docs/decisions/records-index-at-merge.md) |
| `rm-path-wrapper` | `bin/rm` sits ahead of the real `rm` on PATH, for Claude sessions only. | [`docs/decisions/rm-path-wrapper.md`](../docs/decisions/rm-path-wrapper.md) |
| `ruled-store-one-home` | The owner's rulings that main has not taken in sit in one store: `roadmap/rulings/<slug>.json` on `origin/roadmap`, one file per ruling. | [`docs/decisions/ruled-store-one-home.md`](../docs/decisions/ruled-store-one-home.md) |
| `session-messages` | Owner asks ask-mw5b3m9hl0 (2026-11-06 12:27 CST) and ask-mw5a0ekdlv (11:56 CST). | [`docs/decisions/session-messages.md`](../docs/decisions/session-messages.md) |
| `shell-scripts-check-out-lf` | Owner, 2026-10-21: `.gitattributes` forces LF on checkout for every file under `bin/` and `githooks/`, every `*.sh`, and `skills/impeccable/scripts/impeccable`. | [`docs/decisions/shell-scripts-check-out-lf.md`](../docs/decisions/shell-scripts-check-out-lf.md) |
| `stale-cites-at-merge` | The ste-lint CI step refuses a pull request that leaves stale prose of one kind. | [`docs/decisions/stale-cites-at-merge.md`](../docs/decisions/stale-cites-at-merge.md) |
| `stale-cites-whole-tree` | `lint/stale_cites.py --tree [REV]` reads every tracked Markdown file at REV. | [`docs/decisions/stale-cites-whole-tree.md`](../docs/decisions/stale-cites-whole-tree.md) |
| `stalled-steps` | Nobody types a step's `doing` status. | [`docs/decisions/stalled-steps.md`](../docs/decisions/stalled-steps.md) |
| `two-worktrees-one-branch` | Coordinator, 2026-11-07 14:29 CST, under lane override-plain-ask: the incident below gets its guard now. | [`docs/decisions/two-worktrees-one-branch.md`](../docs/decisions/two-worktrees-one-branch.md) |

## Debts

| Slug | Gist | Link |
|---|---|---|
| `agent-reports-with-live-watcher` | No check stops an agent that sends its final report while a Monitor or background task it started is still running. | [`docs/debts/agent-reports-with-live-watcher.md`](../docs/debts/agent-reports-with-live-watcher.md) |
| `agent-resume-reads-closed` | A TaskStop or a terminal notice closes an agent id for the whole transcript, so the Stop check drops every later launch under that id. | [`docs/debts/agent-resume-reads-closed.md`](../docs/debts/agent-resume-reads-closed.md) |
| `agent-session-tools` | On 2026-11-07 an agent called session tools by mistake. | [`docs/debts/agent-session-tools.md`](../docs/debts/agent-session-tools.md) |
| `banchi-build-steps` | A pending Banchi step is a line `` 0. `step <slug>` `` in a file in `docs/gates/steps/`. | [`docs/debts/banchi-build-steps.md`](../docs/debts/banchi-build-steps.md) |
| `bg-end-false-alarms` | The rule splits script names on `:` and `-`, so `build:dev` and `test-watch-ci` read as servers. | [`docs/debts/bg-end-false-alarms.md`](../docs/debts/bg-end-false-alarms.md) |
| `bold-option-keys-missed` | In `OPTION_KEY` of `hooks/question_form.py` and `LABEL_RE` of `lint/report_guard.py`, a bold key at line start (`**a)** x`, `**a** x`) ends the Input Needed section. | [`docs/debts/bold-option-keys-missed.md`](../docs/debts/bold-option-keys-missed.md) |
| `brief-no-topic-wrong-steer` | Rule `lane-one-topic` (refuses a lane brief for another topic) refuses a marker brief whose `Topic:` it cannot read, such as a missing `Topic:`, a topic in backticks, or no dot after it. | [`docs/debts/brief-no-topic-wrong-steer.md`](../docs/debts/brief-no-topic-wrong-steer.md) |
| `build-disk-guard` | Part 2 of `build-dirs-reaped-at-agent-end`, the low-disk build guard, is not built. | [`docs/debts/build-disk-guard.md`](../docs/debts/build-disk-guard.md) |
| `builder-diff-auto-merge-reflog` | A builder's merge that git commits with a strategy option is not judged. | [`docs/debts/builder-diff-auto-merge-reflog.md`](../docs/debts/builder-diff-auto-merge-reflog.md) |
| `cannot-claim-object-past-comma` | On PR #2058 (branch cannot-claim-follow-up-4; main does not have this code yet), `_non_pr_object` reads the object from a 6-word window that runs past a comma, a parenthesis, "and" or "so". | [`docs/debts/cannot-claim-object-past-comma.md`](../docs/debts/cannot-claim-object-past-comma.md) |
| `carry-source-words` | `SOURCE_RE` accepts only the words git, page and digest as the source of a Recovered item. | [`docs/debts/carry-source-words.md`](../docs/debts/carry-source-words.md) |
| `ci-wake-cloud-unproven` | No live cloud run shows the CI-done wake firing after an MCP ready call. | [`docs/debts/ci-wake-cloud-unproven.md`](../docs/debts/ci-wake-cloud-unproven.md) |
| `ci-wake-gh-host-bare-repo` | For a github.com PR, ci_wake passes a bare -R owner/repo. | [`docs/debts/ci-wake-gh-host-bare-repo.md`](../docs/debts/ci-wake-gh-host-bare-repo.md) |
| `ci-wake-lists-runs-once` | `ci_wake.wait_for` lists the head's CI runs once more, at once, after the first judged run, and judges any run that shows there. | [`docs/debts/ci-wake-lists-runs-once.md`](../docs/debts/ci-wake-lists-runs-once.md) |
| `classic-readers-miss-rulesets` | Three prose and audit readers look only at classic branch protection. | [`docs/debts/classic-readers-miss-rulesets.md`](../docs/debts/classic-readers-miss-rulesets.md) |
| `clause-adverb-exp-backtrack` | On PR #2058 (branch cannot-claim-follow-up-4; main does not have this code yet), `ADVERB_PATTERN` in `lint/_clause.py` lists adverbs ending in -ly (really, simply, actually, currently, directly, unfortunately), and `[a-z]{3,}ly` in the same alternation matches them too. | [`docs/debts/clause-adverb-exp-backtrack.md`](../docs/debts/clause-adverb-exp-backtrack.md) |
| `cloud-hook-bakes-stable-url` | The cloud SessionStart refresh hook is a fixed command that fetches `${RAW}/install.sh`, the URL built when the install ran. | [`docs/debts/cloud-hook-bakes-stable-url.md`](../docs/debts/cloud-hook-bakes-stable-url.md) |
| `code-check-pin-drift` | `bin/ste-changed` warns when CI pins the ste-lint or zizmor action at a commit whose files differ from the session's copy. | [`docs/debts/code-check-pin-drift.md`](../docs/debts/code-check-pin-drift.md) |
| `comment-narration-limits` | The check has no suppression marker. | [`docs/debts/comment-narration-limits.md`](../docs/debts/comment-narration-limits.md) |
| `confirm-red-between-read-and-put` | `confirm` reads the head's checks, then sends `PUT pulls/<n>/merge` with the head sha as its guard. | [`docs/debts/confirm-red-between-read-and-put.md`](../docs/debts/confirm-red-between-read-and-put.md) |
| `cost-pins-line-range-suffix` | `LINE_SUFFIX` drops only a trailing `:digits`. | [`docs/debts/cost-pins-line-range-suffix.md`](../docs/debts/cost-pins-line-range-suffix.md) |
| `cost-pins-time-noun-missing` | `COST_NOUN` has `times` but not `time`, so a count before the singular noun passes unflagged. | [`docs/debts/cost-pins-time-noun-missing.md`](../docs/debts/cost-pins-time-noun-missing.md) |
| `cost-pins-verb-past-tense` | `WORK_VERB` has no past tense, so a count after a past verb passes unflagged. | [`docs/debts/cost-pins-verb-past-tense.md`](../docs/debts/cost-pins-verb-past-tense.md) |
| `departs-word-list-limits` | `question-departs` reads a no-change word in the first clause of the change side. | [`docs/debts/departs-word-list-limits.md`](../docs/debts/departs-word-list-limits.md) |
| `design-branch-deleted-unmerged` | An unmerged design branch was deleted, and its mockup is on no ref. | [`docs/debts/design-branch-deleted-unmerged.md`](../docs/debts/design-branch-deleted-unmerged.md) |
| `duo-fold-pin-bump-stale-clone` | `duo_fold_fetch_hinge` skips the clone when `$work/hinge/.git` exists, then runs `git checkout` of the pinned sha. | [`docs/debts/duo-fold-pin-bump-stale-clone.md`](../docs/debts/duo-fold-pin-bump-stale-clone.md) |
| `env-guard-reads-basenames-only` | The guard passes these forms, which read or open an env file: `cat .envs/x`, `cat .env/x/secret`, `grep --incl .env K .` (a shortened long flag), `yq -n 'load(".env")'` and `cd .envs/x && cat config.json`. | [`docs/debts/env-guard-reads-basenames-only.md`](../docs/debts/env-guard-reads-basenames-only.md) |
| `exit-worktree-hook-unmeasured` | The guard clears a session-home record on an ExitWorktree call. | [`docs/debts/exit-worktree-hook-unmeasured.md`](../docs/debts/exit-worktree-hook-unmeasured.md) |
| `explain-accessvbom` | The owner wants to be talked through AccessVBOM, the Office setting "Trust access to the VBA project object model": what it does, its risk, and whether to turn it on. | [`docs/debts/explain-accessvbom.md`](../docs/debts/explain-accessvbom.md) |
| `ff-first-lane-not-a-tip` | The old tip reader read merge commits only, so a lane that fast-forwarded onto the base had its tip unread and its branch never cut. | [`docs/debts/ff-first-lane-not-a-tip.md`](../docs/debts/ff-first-lane-not-a-tip.md) |
| `find-xargs-test-write` | A builder can write a test by mistake through a path that a shell command supplies. | [`docs/debts/find-xargs-test-write.md`](../docs/debts/find-xargs-test-write.md) |
| `fork-step-grants-read-roadmap` | In a fork worktree, the Opus step-grant lookup reads `origin/roadmap`, main's record branch. | [`docs/debts/fork-step-grants-read-roadmap.md`](../docs/debts/fork-step-grants-read-roadmap.md) |
| `frozen-dup-in-subshell` | From a frozen working folder (the live pin `<clone>-live`, or `~/.claude/hooks`), the frozen-path rule still refuses `x=$(ls 2>&1)`, `(ls 2>&1)`, a backtick form, and `ls 2>&1&`. | [`docs/debts/frozen-dup-in-subshell.md`](../docs/debts/frozen-dup-in-subshell.md) |
| `granted-round-4-briefs` | The review record now accepts a granted round 4, which is the final round. | [`docs/debts/granted-round-4-briefs.md`](../docs/debts/granted-round-4-briefs.md) |
| `guard-merge-stale-texts` | Two texts in `hooks/guard_merge.py` are stale. | [`docs/debts/guard-merge-stale-texts.md`](../docs/debts/guard-merge-stale-texts.md) |
| `guard-split-f821-lint-gap` | After the guard split, `ruff` reads each section file alone. | [`docs/debts/guard-split-f821-lint-gap.md`](../docs/debts/guard-split-f821-lint-gap.md) |
| `guard-stdin-not-utf8` | `_force_utf8_streams` reconfigures stdout and stderr only. | [`docs/debts/guard-stdin-not-utf8.md`](../docs/debts/guard-stdin-not-utf8.md) |
| `guard-summary-names-batch-ci` | The `merge-checks` summary in `hooks/guard.py` (about lines 151 to 152) says a merge is denied "while another ready PR on the base runs CI". | [`docs/debts/guard-summary-names-batch-ci.md`](../docs/debts/guard-summary-names-batch-ci.md) |
| `handoff-choice-exempts-line` | "your call" exempts the whole "Why yours" line, so a false "can't" on that line passes with no cite. | [`docs/debts/handoff-choice-exempts-line.md`](../docs/debts/handoff-choice-exempts-line.md) |
| `handoff-verb-list-closed` | A capability line in these words passes with no cite: "do not have access", "no permission", "not able to", "only the owner can", "cant", "can not". | [`docs/debts/handoff-verb-list-closed.md`](../docs/debts/handoff-verb-list-closed.md) |
| `heredoc-written-run-false-alarm` | The guard keeps a heredoc body in view when the file the body writes shares a pipeline with any runner word, even as a plain argument. | [`docs/debts/heredoc-written-run-false-alarm.md`](../docs/debts/heredoc-written-run-false-alarm.md) |
| `hooks-to-mods-judges` | Plan step E has four parts. | [`docs/debts/hooks-to-mods-judges.md`](../docs/debts/hooks-to-mods-judges.md) |
| `inbox-saves-other-notices` | The feedback inbox saves some prompts the owner did not type. | [`docs/debts/inbox-saves-other-notices.md`](../docs/debts/inbox-saves-other-notices.md) |
| `inbox-send-window-unbounded` | The feedback Stop guard accepts any matching send after the owner's message, in any later turn. | [`docs/debts/inbox-send-window-unbounded.md`](../docs/debts/inbox-send-window-unbounded.md) |
| `inplace-edit-under-0-9-flagged` | A branch can edit a line that main only added. | [`docs/debts/inplace-edit-under-0-9-flagged.md`](../docs/debts/inplace-edit-under-0-9-flagged.md) |
| `jobs-over-80pct-of-cap` | In the window of 2026-11-05 (decision `ci-job-caps`, each job's cap leaves its slowest run under 80%), nine jobs had a green run past 80% of the cap. | [`docs/debts/jobs-over-80pct-of-cap.md`](../docs/debts/jobs-over-80pct-of-cap.md) |
| `js-layout-reader` | The map skill reads the debts folder from `lint/layout.json` in JS. | [`docs/debts/js-layout-reader.md`](../docs/debts/js-layout-reader.md) |
| `judge-dash-order-passes` | `session_wording` does not flag an order that follows an em dash, or one joined with no mark, so a past-ruling judge reason can still reach the owner with it. | [`docs/debts/judge-dash-order-passes.md`](../docs/debts/judge-dash-order-passes.md) |
| `judge-modal-drops-ruling` | A past-ruling judge reason that only states a ruling, such as "decision x (2026-11-01) says replies must end with the report.", is dropped whole, because `_MODAL` flags "must" and "should" in it. | [`docs/debts/judge-modal-drops-ruling.md`](../docs/debts/judge-modal-drops-ruling.md) |
| `judge-passes-475-read-flags` | Page item 475 (doc id `merge-read-flags-allow`) asked the owner whether six read-only merge-tool flags may run without a prompt, up from three. | [`docs/debts/judge-passes-475-read-flags.md`](../docs/debts/judge-passes-475-read-flags.md) |
| `kept-claim-goes-stale` | A merge keeps its claim after a read that could not run. | [`docs/debts/kept-claim-goes-stale.md`](../docs/debts/kept-claim-goes-stale.md) |
| `lane-ack-skips-every-reply` | In `last_incoming_index`, a send's first reply from its target is its ack, so a new question in that reply passes with no send. | [`docs/debts/lane-ack-skips-every-reply.md`](../docs/debts/lane-ack-skips-every-reply.md) |
| `lane-cycle-delete-order` | A cycle of lanes (A based on B, and B based on A) had no first lane to delete, so a failed delete could close a pull request whose base was gone. | [`docs/debts/lane-cycle-delete-order.md`](../docs/debts/lane-cycle-delete-order.md) |
| `lane-lint-hub-cost` | A change to a widely imported module makes lane lint pick most of the suites, and each picked CI step runs whole. | [`docs/debts/lane-lint-hub-cost.md`](../docs/debts/lane-lint-hub-cost.md) |
| `lane-model-recheck` | Lane sessions run Sonnet for now. | [`docs/debts/lane-model-recheck.md`](../docs/debts/lane-model-recheck.md) |
| `layout-kind-repeats-extras` | When `lint/layout.json` gains a kind that a rolled-out repo already lists in its `.claude/layout-extras.json`, `layout.kinds()` refuses that repo's extras file and ste_lint exits 2 on every lane there. | [`docs/debts/layout-kind-repeats-extras.md`](../docs/debts/layout-kind-repeats-extras.md) |
| `layout-legacy-repos` | The layout's `legacy-repos` map lets two named repos keep their `todo` kind in a place of their own: q_max at `specs/todo.md`, home at `records`. | [`docs/debts/layout-legacy-repos.md`](../docs/debts/layout-legacy-repos.md) |
| `layout-writer-key-stale` | The extras key `page-writer` holds the page writer's session id. | [`docs/debts/layout-writer-key-stale.md`](../docs/debts/layout-writer-key-stale.md) |
| `linked-nm-prefix-workspace` | `npm ci -w sub`, and a plain `npm ci` run inside a workspace member, write the root's `node_modules` (npm 10). | [`docs/debts/linked-nm-prefix-workspace.md`](../docs/debts/linked-nm-prefix-workspace.md) |
| `lint-past-bash-cap` | Cloud `./bin/verdict ./bin/ci-job checks --lint` took 630-649 s over 2 runs on 2026-11-07 (514-547 s over 4 runs on 2026-11-06). | [`docs/debts/lint-past-bash-cap.md`](../docs/debts/lint-past-bash-cap.md) |
| `local-triage-tier-proof` | The guard takes a session's tier only from its cloud tags, read from its own get_session record. | [`docs/debts/local-triage-tier-proof.md`](../docs/debts/local-triage-tier-proof.md) |
| `lock-ttl-sized-for-gone-waits` | `confirm` takes the merge lock for `(WAITS * deadlineMinutes + 10) * 60` seconds. | [`docs/debts/lock-ttl-sized-for-gone-waits.md`](../docs/debts/lock-ttl-sized-for-gone-waits.md) |
| `long-lived-head-lost-in-batch` | `cut_branch` deletes the merged pull request's own origin branch. | [`docs/debts/long-lived-head-lost-in-batch.md`](../docs/debts/long-lived-head-lost-in-batch.md) |
| `mail-windows-timeout-hang` | On Windows, `subprocess.run` calls `communicate()` after a timeout, which waits for any helper child that still holds the pipe. | [`docs/debts/mail-windows-timeout-hang.md`](../docs/debts/mail-windows-timeout-hang.md) |
| `map-import-alias-unread` | The import reader skips a specifier that does not start with `.`. | [`docs/debts/map-import-alias-unread.md`](../docs/debts/map-import-alias-unread.md) |
| `map-py-base-name-match` | `py-facts.py` resolves an import by the module's last name. | [`docs/debts/map-py-base-name-match.md`](../docs/debts/map-py-base-name-match.md) |
| `map-tested-by-no-shell` | MAP11 has no reader for a shell test. | [`docs/debts/map-tested-by-no-shell.md`](../docs/debts/map-tested-by-no-shell.md) |
| `map-tested-by-path-pieces` | MAP11 counts only a whole path string. | [`docs/debts/map-tested-by-path-pieces.md`](../docs/debts/map-tested-by-path-pieces.md) |
| `mcp-merge-no-repo-tag` | `mcp__github__merge_pull_request` has one merge test, the `MERGE_TOOLS` clause in `judge` (read `hooks/guard.py` `judge`). | [`docs/debts/mcp-merge-no-repo-tag.md`](../docs/debts/mcp-merge-no-repo-tag.md) |
| `measured-time-table` | `bin/verdict` logs no kind, seconds and exit per run, and no table keeps measured times. | [`docs/debts/measured-time-table.md`](../docs/debts/measured-time-table.md) |
| `merge-commit-skips-review` | While it resolved a merge of main into a lane branch, a builder pushed a logic change to `lint/report_guard.py`. | [`docs/debts/merge-commit-skips-review.md`](../docs/debts/merge-commit-skips-review.md) |
| `merge-head-race-remains` | The race between a push and `gh pr ready` remains. | [`docs/debts/merge-head-race-remains.md`](../docs/debts/merge-head-race-remains.md) |
| `merge-reason-paren-cuts-args` | The merge-confirm-repo clause stops reading a merge's arguments at the first token that ends in `)` or `&`. | [`docs/debts/merge-reason-paren-cuts-args.md`](../docs/debts/merge-reason-paren-cuts-args.md) |
| `merge-records-stale-base` | `bin/merge` rebuilds the records page after the CI wait. | [`docs/debts/merge-records-stale-base.md`](../docs/debts/merge-records-stale-base.md) |
| `merge-remedy-hits-role-refusal` | The remedy text for `merge <pr> --confirm` now sends a cloud lane into the merge role refusal. | [`docs/debts/merge-remedy-hits-role-refusal.md`](../docs/debts/merge-remedy-hits-role-refusal.md) |
| `merge-silent-exit` | Twice on 2026-10-20 (#527 in the afternoon, #538 at 00:08 CDT on 10-21), the background shell that ran `bin/merge <pr> --confirm` exited rc 1 mid-wait and printed no reason. | [`docs/debts/merge-silent-exit.md`](../docs/debts/merge-silent-exit.md) |
| `merge-stale-texts-and-cites` | `merge/merge.py` still cites and prints removed things. | [`docs/debts/merge-stale-texts-and-cites.md`](../docs/debts/merge-stale-texts-and-cites.md) |
| `mutate-guard-split` | `checks-mutate-guard` runs every guard mutant in one job, 4 at a time. | [`docs/debts/mutate-guard-split.md`](../docs/debts/mutate-guard-split.md) |
| `nowindow-bin-no-fallback` | bin/verdict, bin/ste-changed, bin/ci-job and merge/launch.py import hooks/_nowindow.py with no fallback, so a copy-mode install that lands bin/ before hooks/ makes them fail. | [`docs/debts/nowindow-bin-no-fallback.md`](../docs/debts/nowindow-bin-no-fallback.md) |
| `nowindow-ctrl-c-orphans` | With CREATE_NO_WINDOW the child gets its own hidden console, so Ctrl-C may not reach grandchildren. | [`docs/debts/nowindow-ctrl-c-orphans.md`](../docs/debts/nowindow-ctrl-c-orphans.md) |
| `nowindow-fallback-silent` | A hook that falls back to plain subprocess says nothing, so the popups return unseen. | [`docs/debts/nowindow-fallback-silent.md`](../docs/debts/nowindow-fallback-silent.md) |
| `nowindow-git-prompt-hangs` | A git credential prompt on the terminal, from merge/merge.py sh(), has no console to show in, so it would wait with no end. | [`docs/debts/nowindow-git-prompt-hangs.md`](../docs/debts/nowindow-git-prompt-hangs.md) |
| `nowindow-scan-misses-os-system` | lint/test_no_window_spawn.py reads subprocess and Node child_process calls only. | [`docs/debts/nowindow-scan-misses-os-system.md`](../docs/debts/nowindow-scan-misses-os-system.md) |
| `old-merge-tool-refuses-stamp` | A merge tool older than this change refuses main's `stamp.json`, which has the unknown field `keepBranches`. | [`docs/debts/old-merge-tool-refuses-stamp.md`](../docs/debts/old-merge-tool-refuses-stamp.md) |
| `option-freeze-no-backfill` | Guard rule `option-letters-frozen` refuses every write of an open decision that carries `options` but no `shown` and no option ids. | [`docs/debts/option-freeze-no-backfill.md`](../docs/debts/option-freeze-no-backfill.md) |
| `opus-ask-exclusion-words` | A plain Opus ask that names two or more roles, joined to an exclusion the scope read does not list, grants exactly the excluded roles for 2h. | [`docs/debts/opus-ask-exclusion-words.md`](../docs/debts/opus-ask-exclusion-words.md) |
| `opus-ask-scheduled-text` | A plain Opus ask is refused when the UserPromptSubmit payload's `source` names a non-owner origin, such as `loop_wakeup`. | [`docs/debts/opus-ask-scheduled-text.md`](../docs/debts/opus-ask-scheduled-text.md) |
| `other-checkout-cwd-outside` | `other_checkout_hit` returns `""` when the call's `cwd` is in no checkout of the clone. | [`docs/debts/other-checkout-cwd-outside.md`](../docs/debts/other-checkout-cwd-outside.md) |
| `other-clone-unread-writers` | Into a separate clone, as into another checkout, these forms pass the write scan: `touch`, `mkdir`, `rsync -a src/ <dir>/`, `curl -o`, `tar -C`, `make -C`, `env -C`, `bash -c 'cd X && touch f'`, and `cd $HOME/...`. | [`docs/debts/other-clone-unread-writers.md`](../docs/debts/other-clone-unread-writers.md) |
| `page-answer-second-click` | One waiting-page answer needed a second approval. | [`docs/debts/page-answer-second-click.md`](../docs/debts/page-answer-second-click.md) |
| `page-only-copy-of-mockup` | A mockup lives only inside the `designData` block of the waiting page. | [`docs/debts/page-only-copy-of-mockup.md`](../docs/debts/page-only-copy-of-mockup.md) |
| `pin-missing-files-no-install` | `merge/install_from_main.sh` treats a pin at main that has only missing tracked files as dirty: it exits 1 and installs nothing. | [`docs/debts/pin-missing-files-no-install.md`](../docs/debts/pin-missing-files-no-install.md) |
| `pinoff1-freshness-flaky` | Case pinoff1 expected one freshness line and got none, on a commit that changed only the records page (run 39080117103). | [`docs/debts/pinoff1-freshness-flaky.md`](../docs/debts/pinoff1-freshness-flaky.md) |
| `playwright-rows-measure` | Unmeasured: whether the Playwright rows in the guard suite (family `kill`, `tests/guard/`) still stop a real mistake. | [`docs/debts/playwright-rows-measure.md`](../docs/debts/playwright-rows-measure.md) |
| `pr-ready-unguarded` | The `draft-pr` guard rule reads only the create command and the MCP create tool. | [`docs/debts/pr-ready-unguarded.md`](../docs/debts/pr-ready-unguarded.md) |
| `press-clause-hides-owner-press` | The press-link check excuses a session-subject clause when it holds no `you` and no owner's name as subject of a present or future press or act verb. | [`docs/debts/press-clause-hides-owner-press.md`](../docs/debts/press-clause-hides-owner-press.md) |
| `ps-assign-in-braces` | A PowerShell assignment inside braces is not read, so a write to a frozen path `T` through that variable is allowed. | [`docs/debts/ps-assign-in-braces.md`](../docs/debts/ps-assign-in-braces.md) |
| `ps-command-misses-bash` | Guard rule `command-in-item` refuses a `powershell` string only for `&&`, `\|\|`, `<<`, `<<<`, `/dev/null` and `export`. | [`docs/debts/ps-command-misses-bash.md`](../docs/debts/ps-command-misses-bash.md) |
| `ps-read-with-bash-quotes` | In PowerShell text the resolver pairs double quotes by bash rules: a `\` before `"` or a newline escapes it. | [`docs/debts/ps-read-with-bash-quotes.md`](../docs/debts/ps-read-with-bash-quotes.md) |
| `ps-typed-var-assign` | `[string]$D = 'T'; Set-Content $D x`, `[string]$D='T'` and `[System.IO.FileInfo]$D = 'T'` set `$D` in PowerShell, but the resolver reads only a bare `$D` word, so the write to the frozen path `T` is allowed. | [`docs/debts/ps-typed-var-assign.md`](../docs/debts/ps-typed-var-assign.md) |
| `push-report-before-checks` | A session can report a push as done before its checks finish. | [`docs/debts/push-report-before-checks.md`](../docs/debts/push-report-before-checks.md) |
| `pycache-rm-false-alarm` | `rm -rf tests/__pycache__` and `rm -rf tests/.pytest_cache` are refused for a builder, because the path sits in a test folder. | [`docs/debts/pycache-rm-false-alarm.md`](../docs/debts/pycache-rm-false-alarm.md) |
| `readonly-write-paren-redirect` | A read-only agent's shell call (a reviewer or Explore, for example) is refused though it writes nothing when a `)` follows a descriptor duplicate, as in `x=$(git status 2>&1)`, `out=$(python3 -c "print(1)" 2>&1)`, `(ls 2>&1)` and `(cd /tmp && ls >&2)`. | [`docs/debts/readonly-write-paren-redirect.md`](../docs/debts/readonly-write-paren-redirect.md) |
| `ready-checks-skipped-by-mcp` | A session that marks a draft ready by MCP `update_pull_request draft=false` or by `gh pr ready`, without running `merge <pr> --confirm` on the draft, skips `merge.readyChecks`. | [`docs/debts/ready-checks-skipped-by-mcp.md`](../docs/debts/ready-checks-skipped-by-mcp.md) |
| `record-code-spans-unindexed` | The restates check strips code spans from the record side too, so owner words that a record keeps in backticks are never indexed. | [`docs/debts/record-code-spans-unindexed.md`](../docs/debts/record-code-spans-unindexed.md) |
| `red-base-head-order-untested` | No test pins that `base_state` walks the push and dispatch group (the head group) first. | [`docs/debts/red-base-head-order-untested.md`](../docs/debts/red-base-head-order-untested.md) |
| `red-run-amend-push-unconditional` | Any `git commit --amend` followed by a push in the same call is refused as a red-run chain, even when the amend is docs-only. | [`docs/debts/red-run-amend-push-unconditional.md`](../docs/debts/red-run-amend-push-unconditional.md) |
| `red-run-chain-ignores-trailer` | The push-chain refusal ignores a valid Red-run trailer in the chained commit's own `-m`. | [`docs/debts/red-run-chain-ignores-trailer.md`](../docs/debts/red-run-chain-ignores-trailer.md) |
| `red-run-chain-merge-main-tests` | After a conflicted merge of main, the index holds main's incoming test lines. | [`docs/debts/red-run-chain-merge-main-tests.md`](../docs/debts/red-run-chain-merge-main-tests.md) |
| `refresh-lock-untested` | The SessionStart refresh holds a lock directory in the config dir. | [`docs/debts/refresh-lock-untested.md`](../docs/debts/refresh-lock-untested.md) |
| `refresh-no-main-fallback` | When origin has no `stable` branch, an existing cloud clone or mirror keeps its old files with a WARN, and the own-checkout fetch leaves the checkout as it is. | [`docs/debts/refresh-no-main-fallback.md`](../docs/debts/refresh-no-main-fallback.md) |
| `refusal-route-around-guard` | A test-author gets a refusal on an Edit of a path, then writes the same file with Bash and Python. | [`docs/debts/refusal-route-around-guard.md`](../docs/debts/refusal-route-around-guard.md) |
| `refusal-settle-reads` | When the refusals file holds a row with a `tool_use_id`, each Stop reads the whole transcript and every `<session>/subagents/*.jsonl` file, to tell an agent's refused call from the orchestrator's. | [`docs/debts/refusal-settle-reads.md`](../docs/debts/refusal-settle-reads.md) |
| `retire-run-footer-refused` | `lint/check_debt_retire.py` reads `Retire-run:` only from the PR body's last paragraph. | [`docs/debts/retire-run-footer-refused.md`](../docs/debts/retire-run-footer-refused.md) |
| `review-record-model-not-served` | `merge --review-record` refuses a non-Sonnet fix check or round 2/3 line, but only reads the model as typed. | [`docs/debts/review-record-model-not-served.md`](../docs/debts/review-record-model-not-served.md) |
| `route-flag-stop-untested` | No test feeds a refusal row that carries `route_flag` through the Stop read, so that path has no test. | [`docs/debts/route-flag-stop-untested.md`](../docs/debts/route-flag-stop-untested.md) |
| `ruling-pr-kind-unchecked` | The merge tool takes the lane's Kind claim. | [`docs/debts/ruling-pr-kind-unchecked.md`](../docs/debts/ruling-pr-kind-unchecked.md) |
| `scan-key-and-root-ip` | In the 2026-11-08 export of the personal accounts' pages, the scan refused two pages for shapes that held no secret. | [`docs/debts/scan-key-and-root-ip.md`](../docs/debts/scan-key-and-root-ip.md) |
| `scan-quote-led-password-host` | Two accepted limits of PR 2372 (branch `export-scan-key-false-alarms`, head `f71e12a0463e89bdcad6124e531fcb2cb870b0c4`). | [`docs/debts/scan-quote-led-password-host.md`](../docs/debts/scan-quote-led-password-host.md) |
| `session-home-lane-visit` | A top-level session whose `cwd` enters a non-agent lane tree gets a session-home record naming it, and a return to the primary does not clear it. | [`docs/debts/session-home-lane-visit.md`](../docs/debts/session-home-lane-visit.md) |
| `session-start-bare-fetch` | The `SessionStart` hook in `settings.json` runs a bare `git fetch -q origin`, which fetches every branch (2,715 remote-tracking refs counted on 2026-11-12). | [`docs/debts/session-start-bare-fetch.md`](../docs/debts/session-start-bare-fetch.md) |
| `session-start-handoff-text` | `hooks/session_start.sh` line 18 tells a session that wants a merge to hand the branch, head and PR to the batch runner. | [`docs/debts/session-start-handoff-text.md`](../docs/debts/session-start-handoff-text.md) |
| `sharables-adopts-the-stamp` | claude-sharables claims record ids with its own `scripts/check_records.py --claim-ids --apply`. | [`docs/debts/sharables-adopts-the-stamp.md`](../docs/debts/sharables-adopts-the-stamp.md) |
| `short-copy-passes` | A child line that copies a claude-settings grant in under 12 words passes the restates group. | [`docs/debts/short-copy-passes.md`](../docs/debts/short-copy-passes.md) |
| `silent-undo-rebase-no-merge` | `revived_notes` replays the branch's own commits and flags a note that a merge put back. | [`docs/debts/silent-undo-rebase-no-merge.md`](../docs/debts/silent-undo-rebase-no-merge.md) |
| `skill-copy-no-typescript` | A copy of the skill folder outside the clone finds no `node_modules`, so `map-check.mjs` and `map-picture.mjs` cannot load `typescript` there. | [`docs/debts/skill-copy-no-typescript.md`](../docs/debts/skill-copy-no-typescript.md) |
| `squash-lane-branch-kept` | `cut_local` deletes a local branch only when its tip is an ancestor of the merged head. | [`docs/debts/squash-lane-branch-kept.md`](../docs/debts/squash-lane-branch-kept.md) |
| `stable-has-no-ruleset` | `stable` has no ruleset, so nothing blocks a delete or a force-push of it. | [`docs/debts/stable-has-no-ruleset.md`](../docs/debts/stable-has-no-ruleset.md) |
| `stamp-read-false-alarms` | The stamp rule counts three read-only shell calls as no evidence. | [`docs/debts/stamp-read-false-alarms.md`](../docs/debts/stamp-read-false-alarms.md) |
| `stamp-shallow-depth-two` | `stamp.mjs --check` off the default branch needs `fetch-depth: 0`. | [`docs/debts/stamp-shallow-depth-two.md`](../docs/debts/stamp-shallow-depth-two.md) |
| `stamp-shell-write-counts-read` | `_shell_reads` is a deny list of write forms, so an unlisted write counts as a read when its text holds a premise's Source token. | [`docs/debts/stamp-shell-write-counts-read.md`](../docs/debts/stamp-shell-write-counts-read.md) |
| `stamp-shell-write-not-judged` | The stamp rule judges only Write, Edit and MultiEdit to a session handoff, the same scope as `handoff-sections` (item 14). | [`docs/debts/stamp-shell-write-not-judged.md`](../docs/debts/stamp-shell-write-not-judged.md) |
| `start-fetch-leaves-refs-stale` | The session start fetches only origin's main and its HEAD target, so refs such as `origin/roadmap` age until a session runs `git fetch origin <branch>`. | [`docs/debts/start-fetch-leaves-refs-stale.md`](../docs/debts/start-fetch-leaves-refs-stale.md) |
| `step-shell-programs-partial` | Guard rule `command-in-item` reads a backtick span in a step as a shell line only when its first word is in a fixed program list. | [`docs/debts/step-shell-programs-partial.md`](../docs/debts/step-shell-programs-partial.md) |
| `sweep-reaps-local-stable` | The sweep reaps a local `stable` on main, because its work is on the base. | [`docs/debts/sweep-reaps-local-stable.md`](../docs/debts/sweep-reaps-local-stable.md) |
| `two-worktrees-unexpanded-target` | A `cd` or `git -C` target the guard cannot expand, such as `"$(git rev-parse --show-toplevel)"`, `$REPO` or `"$(pwd)"`, names a folder that does not exist. | [`docs/debts/two-worktrees-unexpanded-target.md`](../docs/debts/two-worktrees-unexpanded-target.md) |
| `unlock-delete-no-check` | After retry-net-method-safe, a 5xx on the lock-release DELETE stops the unlock with a network stop, and the lock stays until it expires. | [`docs/debts/unlock-delete-no-check.md`](../docs/debts/unlock-delete-no-check.md) |
| `unstarted-guard-held` | No check refuses a coordinator report whose `Unstarted:` line omits a step that is ready and not started (rule `reports-name-unstarted-items`). | [`docs/debts/unstarted-guard-held.md`](../docs/debts/unstarted-guard-held.md) |
| `upgrade-strips-name-port` | The version 1 to 2 upgrade removes `:N` after a name whose extension is in `codeExtensions`. | [`docs/debts/upgrade-strips-name-port.md`](../docs/debts/upgrade-strips-name-port.md) |
| `verdict-rewritten-xcode-output` | `verdict` needs a sign of a test run to fail a run with no test count. | [`docs/debts/verdict-rewritten-xcode-output.md`](../docs/debts/verdict-rewritten-xcode-output.md) |
| `windows-main-run-flakes` | Two main push runs went red on Windows only, and each blocked the next batch until a rerun went green. | [`docs/debts/windows-main-run-flakes.md`](../docs/debts/windows-main-run-flakes.md) |
| `windows-shards-outgrow-caps` | The guard suite runs in 3 Windows shards (on push, and on a ready pull_request since R62) (read .github/workflows/checks.yml:1453) and the merge git-half suite in 5 (read .github/workflows/checks.yml:1661). | [`docs/debts/windows-shards-outgrow-caps.md`](../docs/debts/windows-shards-outgrow-caps.md) |
| `wp-batch-reads-installed-copy` | `stale_pages.py` batch mode (no `--page`) compares each live page with the `page.html` installed at session start, not with claude-settings main. | [`docs/debts/wp-batch-reads-installed-copy.md`](../docs/debts/wp-batch-reads-installed-copy.md) |

## Plans

| Slug | Gist | Link |
|---|---|---|
| `3d-tools-survey` | Plan: 3D tools, what to think about as 3D work grows | [`docs/plans/3d-tools-survey.md`](../docs/plans/3d-tools-survey.md) |
| `align-watchers` | Plan: one direction for watches, wakes, sweeps, reaps and logs | [`docs/plans/align-watchers.md`](../docs/plans/align-watchers.md) |
| `builtin-hook-survey` | Plan: which model-call hooks can move to the built-in prompt hook | [`docs/plans/builtin-hook-survey.md`](../docs/plans/builtin-hook-survey.md) |
| `child-guard-promotion` | Plan: child guards go up or out | [`docs/plans/child-guard-promotion.md`](../docs/plans/child-guard-promotion.md) |
| `claude-md-scope-audit` | Plan: Global CLAUDE.md scope audit | [`docs/plans/claude-md-scope-audit.md`](../docs/plans/claude-md-scope-audit.md) |
| `debate-model-tiers` | Plan: which refuters run Opus | [`docs/plans/debate-model-tiers.md`](../docs/plans/debate-model-tiers.md) |
| `grant-reaches-lanes` | Plan: an owner grant typed in one session reaches the session it names | [`docs/plans/grant-reaches-lanes.md`](../docs/plans/grant-reaches-lanes.md) |
| `local-session-reach` | Plan: reach between local and cloud sessions | [`docs/plans/local-session-reach.md`](../docs/plans/local-session-reach.md) |
| `o10-session-questions-page` | Plan: a page per session for questions waiting on the owner | [`docs/plans/o10-session-questions-page.md`](../docs/plans/o10-session-questions-page.md) |
| `plugin-assess-three` | Plan: three catalog plugins, add or skip | [`docs/plans/plugin-assess-three.md`](../docs/plans/plugin-assess-three.md) |
| `pointer-system` | Plan: the pointer system | [`docs/plans/pointer-system.md`](../docs/plans/pointer-system.md) |
| `r42-part2-design` | R42 part 2: per-lane merges, test after merge, stable branch | [`docs/plans/r42-part2-design.md`](../docs/plans/r42-part2-design.md) |
| `refusal-vs-rule` | Plan: each refusal matches its rule | [`docs/plans/refusal-vs-rule.md`](../docs/plans/refusal-vs-rule.md) |
| `restart-plan` | Restart plan: how claude-settings lands work after the freeze | [`docs/plans/restart-plan.md`](../docs/plans/restart-plan.md) |
| `shared-merge-tool` | Plan: the shared merge tool | [`docs/plans/shared-merge-tool.md`](../docs/plans/shared-merge-tool.md) |
| `stalled-steps` | Plan: stalled steps (lane doing-needs-live-lane) | [`docs/plans/stalled-steps.md`](../docs/plans/stalled-steps.md) |
| `test-ci-standard` | Plan: how good tests and CI are made, how far the repos are, and how to close the gap | [`docs/plans/test-ci-standard.md`](../docs/plans/test-ci-standard.md) |
| `time-pinned-tests` | Time-pinned tests: per-repo list | [`docs/plans/time-pinned-tests.md`](../docs/plans/time-pinned-tests.md) |
| `trial-results` | Trial results: Ambition Lenses, blind grade | [`docs/plans/trial-results.md`](../docs/plans/trial-results.md) |
