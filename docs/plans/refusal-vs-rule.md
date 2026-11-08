# Plan: each refusal matches its rule

This record holds the sweep for roadmap step refusal-matches-rule (each guard and merge refusal
matches its rule's outcome, no stricter or looser). It compares every guard rule id and every merge
tool refusal with the rule or decision text it claims to hold.

Owner, 2026-11-01 20:57 CST: "a lot of what this repo is is just self improvement best practices so
that my next project comes in faster, better than the last". The incident: the merge tool refused a
merge while another ready PR ran CI, stricter than rule git-no-merge-during-batch-ci (no merge to main
while a batch's integration PR runs CI). Step overlapping-batches (a batch can run CI on top of the
batch ahead of it) holds that fix. This sweep cites it and does not redo it.

## Method

- **Ids.** The guard ids are every literal rule name passed to `refuse()` or `record()` in
  `hooks/guard*.py`, read with Python's own parser, plus the ids passed through a variable: the four
  role-diff notes, the four role-scope refusals, and the `bare-merge` ask. The merge rows are every
  stop in `merge/merge.py`. Stops of one function with one cause share a row, with their lines.
- **Readers.** Six read-only Explore agents (Sonnet, `Audit:` marker), one per area below.
- **Rule text.** First the decision the guard index names, then the CLAUDE.md or style anchor that
  `lint/rule_mechanisms.json` maps, then the comment above the code. No home was invented.
- **Calibration.** Decision guard-guards-mistakes-only (guards stop Claude's mistakes, not an
  attacker's): a bypass only an attacker would write counts as exact. A limit that its own decision
  accepts counts as exact.

## Verdicts

- **exact:** the refusal holds what the rule says, no more and no less. This is the gold.
- **stricter:** the code refuses or asks about an act the rule allows.
- **looser:** the code lets through an act the rule refuses, or only notes it.
- **uncited:** no rule or decision holds the refusal. Most are fail-closed stops on a failed read.
- **unverified:** no rule sentence could be quoted.

143 rows: exact 89, looser 10, stricter 11, uncited 32, unverified 1. The Gold column is the target for every row. A row whose Verdict is not
exact has a gap.


## A. Destructive git and file acts

| Refusal | Rule it cites | Rule sentence | Verdict | Gold | Showing case | Proposed fix |
|---|---|---|---|---|---|---|
| `git-env-set` | git-env-set-refused | "No agent command may set `GIT_DIR`, `GIT_WORK_TREE` or `GIT_INDEX_FILE`." | exact | exact | an export of GIT_DIR is denied; unset and echo pass | - |
| `shared-tree` | shared-trees-no-destructive-git | "No destructive git. Destructive git loses another agent's work in a shared tree." | looser | exact | `git switch -f main` and `git switch --discard-changes main` pass, though `git checkout -f` is refused | tool fix: add switch -f, --force and --discard-changes to shared_tree_match |
| `subject-unread` | verification-report-unknown-reads | "Report a read that could not run as unknown, never as clear or broken." | exact | exact | when git cannot answer, `git reset --hard` passes with one note; cite-by-id also logs this id for an unread record folder | - |
| `pointer-head` | recovery-independent-of-state | "The rule refuses a command that moves HEAD off `main` in the pointer checkout." | stricter | exact | `git switch -C main origin/main` is refused, though HEAD stays on main | tool fix: pass -C and -B when the target branch is main |
| `silent-write` | git-never-discard-output | "Keep git write output. Discarded output hides failures from the reader." | looser | exact | `git branch -D x >/dev/null` and `git update-ref -d refs/heads/x >/dev/null` pass. The guard reads seven git subcommands (commit, push, merge, tag, rebase, cherry-pick, pull), a `fetch` with a `src:dst` refspec to a branch, `gh pr merge` and `make merge`; a bare `fetch` is a read. A silenced non-git command passes, as the rule allows (owner, item 177 a, 2026-11-03 22:31 CST: "Narrow the rule to git writes") | tool fix: read every git write that moves a ref, such as `branch -D` |
| `hand-made-worktree` | lanes-start-in-tool-worktrees | "A worktree comes only from the Agent tool's `isolation: 'worktree'` or the EnterWorktree tool." | exact | exact | `git worktree add ../x` is denied; `.claude/worktrees/x` passes | - |
| `force-push` | stale-safe-force-push | "Any forced push whose destination is the default branch: ask" | exact | exact | `--force` is denied; a lease with --force-if-includes passes | - |
| `rm-var-unguarded` | rm-on-a-variable-needs-a-guard | "refuses a recursive `rm` only in the shape Claude Code prompts on" | exact | exact | a recursive delete of `"$D"/*` is denied; `"$ROOT/dist"` passes | rule rewrite: the CLAUDE.md line still says "quoted-variable path"; say "a guarded variable path" |
| `rm-after-cd` | shared-trees-delete-names-absolute-path | "A delete names its target as an absolute or quoted-variable path, never after a cd." | exact | exact | a cd, then a recursive delete of a relative folder, is denied | - |
| `ln-over-directory` | none | - | uncited | exact | `ln -sf /tmp/x existing_dir` is denied; the comment says only "ported from banchi" and names no risk kind | rule rewrite: land a decision with its risk kind and date, or cull it (building-guard-needs-incident) |
| `destructive-delete` | rm-path-wrapper | "Also a root, a home, or a glob of one (`rm -r /`, `rm -r ~/*`, `rm -r ../*`)." | looser | exact | a recursive delete of `$(pwd)/*` passes, though the same delete of `./*` is denied. So do a delete inside `$(...)` in an unquoted heredoc and a python heredoc that calls shutil.rmtree (step refusal-looser-fixes) | tool fix: read `$(pwd)` and `$PWD` as `.`; read command substitutions in an unquoted heredoc |
| `linked-node-modules` | guard-linked-node-modules | "A recursive delete into a linked `node_modules` is refused." | exact | exact | `npm ci` in a linked folder is denied; the open holes are the decision's debts | - |
| `env-file` | none | - | uncited | exact | `cat .env` is denied; `grep -r --exclude=.env foo .` is denied too (debt env-file-rule-false-alarms) | rule rewrite: write an env-file decision; tool fix: skip --exclude and -t values |
| `frozen-path` | frozen-path-resolves-shell-vars | "A write whose resolved target is frozen is refused." | exact | exact | a write to the settings file under `$HOME/.claude` through a variable is denied | rule rewrite: the guard index lists 3 frozen kinds; the code freezes 11 |
| `config-edit` | none | - | uncited | exact | a write to `.claude/settings.local.json` is allowed and noted; the code cites "Decision 7", which has no file | rule rewrite: land the "project config edits: allow and report" decision |
| `records-page` | records-index-at-merge | "refuses a lane commit whose staged `docs/records.md` differs from the page on the lane's base." | exact | exact | `python3 lint/hook_catalog.py && git add -A && git commit` is denied even when the page would be unchanged. An accepted limit: the guard runs before the generator, so it cannot read the page the command will stage (triage, step refusal-stricter-fixes) | - |
| `ask-alone` | ask-commands-run-alone | "An agent never chains a command that needs the owner's answer onto other commands in one shell call" | exact | exact | `git worktree prune; echo done` is denied | - |
| `bare-merge` | bare-merge-asks | "The rule fires on a `gh pr merge` segment when the stamp config of the working tree holds a `merge` key." | exact | exact | a green `gh pr merge 5` in a merge-tool repo asks | - |

Notes: the shared-tree gaps `git update-ref -d`, `git rm -rf .` and `git read-tree --reset -u` are unread; low odds in normal work.

## B. Processes, streams and other shell acts

| Refusal | Rule it cites | Rule sentence | Verdict | Gold | Showing case | Proposed fix |
|---|---|---|---|---|---|---|
| `machine-wide-kill` | shared-trees-no-machine-wide-kill | "Kill only yours. Others' servers and processes are not yours to stop" | stricter | exact | `lsof -ti :3000` (a list only) and `pkill -P <own pid>` are denied | tool fix: refuse `lsof -t` only when its output reaches kill; pass `pkill -P` on an owned pid |
| `detached-launch` | detached-launch-refused | "refuses a command that starts a process and detaches it from the session" | stricter | exact | `nohup make test` and `setsid -w make test` run in the foreground and are denied | tool fix: refuse nohup or setsid only with a trailing `&` or without `-w` |
| `wsl-allow-list` | wsl-allow-list | "The guard allows a WSL command only when every condition holds" | exact | exact | `wsl -e bash -c id` is denied; `wsl -e python3 tests/test_x.py` passes | - |
| `live-stream` | none | - | uncited | exact | `tail -f x` is denied, and so is `timeout 5 tail -f x`, which the remedy itself suggests | tool fix: pass a `timeout N` wrapper; rule rewrite: write a live-stream decision |
| `waiter` | agents-wait-with-monitor | "refuses only real waste: a loop that pauses... two or more pauses... one pause of 25 s or more" | exact | exact | `sleep 30` is denied; `sleep 3` passes | - |
| `background-end` | background-needs-end-note | "refuses the call when the note is missing or its condition is empty" | exact | exact | `npm run dev` with no end note is denied | - |
| `check-tail` | background-check-through-verdict | "A pipeline that holds a named check and any later stage but a lone `tee`, `tee.exe`, `Tee-Object` or `Out-File` is refused" | exact | exact | `merge --lane-lint 7 \| tail -3` is denied, foreground or background; the same call through `verdict` with no pipe after it passes (`verdict <cmd> \| tail` is denied by verdict-pipe-refused), as does a `tee`, `tee.exe`, `Tee-Object` or `Out-File` with no filter after it (`tee x | tail` is denied); `ci-job` is denied in the background only. | - |
| `playwright-browsers-path` | playwright-browsers-path | "refuses a Bash or PowerShell command that sets the variable." | exact | exact | an export is denied; echo and unset pass | - |
| `playwright-install` | playwright-install-once | "An agent never runs a Playwright browser install, in any form." | exact | exact | `npx playwright install` is denied | - |
| `simulator-boot-cap` | sweep-shuts-down-idle-simulators | "refuses a session's boot when 2 devices are already booted, and names them" | exact | exact | a third boot is denied | - |
| `simulator-boot-twin` | sweep-shuts-down-idle-simulators | "refuses a boot when an idle booted device of the same type and runtime exists" | exact | exact | a twin boot is denied, with the idle device named | - |
| `simulator-boot-route` | sim-test-is-the-one-boot-path | "An `xcodebuild -destination` that names a shut-down device still boots outside the lock." | looser | exact | a test of a shut-down device is denied, with `sim-test` as the remedy; a destination held in a variable (`-destination "$D"`) passes, because the rule reads command text only | - |
| `simulator-boot-lease` | sim-test-is-the-one-boot-path | "refuses an MCP `launch` that names a shut-down device, unless the held-lease allow applies." | exact | exact | a launch of a shut-down device is denied, lock or no lock, whatever its case or outer spaces, with `sim-test` as the remedy; it passes only when the session's live lease holds that device; a launch of a booted device passes | - |
| `impeccable-review-only` | design-skills | "the Skill tool loads impeccable only for `audit` or `critique`" | stricter | exact | Skill args "audit the page; focus on a11y" are denied for the `;` | tool fix: apply the chain check to the shell form only |
| `cite-by-id` | git-cite-by-id | "Ids, not paths. A path breaks when its file moves." | exact | exact | a commit message "see docs/decisions/foo.md" is denied | - |
| `lane-by-slug` | lane-by-slug | "the guard refuses a session number that names a lane, such as `N20` or `(N16)`" | exact | exact | `N20` in a commit message is denied | - |
| `draft-pr` | draft-until-reviewed | "refuses `gh pr create` without `--draft` or `-d`." | exact | exact | `gh pr create --fill` is denied | - |
| `load-brake` | machine-load-brake | "a call that starts a lane or an agent reads the machine's load. A busy or full machine refuses new lanes and agents" | exact | exact | a busy machine refuses a background Agent | - |
| `guard-crash` | guard-hooks-fail-closed | "a guard that times out or crashes does not ... except a missing guard module, which refuses" | exact | exact | a raise is allowed and logged; a missing module is denied | rule rewrite: the guard index line says only "allowed"; add the missing-module deny |

Notes: create_session is not a start tool for load-brake, so a lane session starts on a full machine; the decision names start_session only (owner question). `narrated-tail` logs as live-stream with no index line.

## C. Agents, models, roles and worktrees

| Refusal | Rule it cites | Rule sentence | Verdict | Gold | Showing case | Proposed fix |
|---|---|---|---|---|---|---|
| `worktree-home` | an-agent-outside-its-home-tree-must-stop | "An agent whose worktree is gone must stop and report." | exact | exact | an agent's write outside its recorded worktree is denied | - |
| `other-checkout` | an-agent-outside-its-home-tree-must-stop | "A write whose resolved target sits in a checkout of the clone other than the checkout that holds cwd." | exact | exact | `.git`, no-checkout targets and unread git pass, as the decision says | - |
| `session-home` | an-agent-outside-its-home-tree-must-stop | "The owner's ask is 'refuse writes in the primary checkout', and these write it." | looser | exact | a session whose home is gone runs `git clean -fd` in the primary: clean is not in the write verb list | tool fix: add clean to SESSION_HOME_GIT_VERBS |
| `agent-role-model` | agent-model-cap | "A spawn that names a model above its role's row is denied." | exact | exact | a round-1 reviewer on sonnet is denied | - |
| `agent-role-model-unread` | agent-model-cap | "A table or agents folder in the pointer checkout that cannot be read passes the spawn and logs one line." | exact | exact | an unread table passes and is noted | - |
| `agent-model-floor` | agent-model-cap | "Guard rule `agent-model-floor` refuses an Agent, Task, Workflow agent() or start_session call whose model holds haiku." | looser | exact | create_session with model haiku passes: the floor reads start_session only | tool fix: read create_session in floor_hit too |
| `roles-third-round-steps-up` | roles-third-round-steps-up | "Third try: Opus. A builder's third try ... its brief carries `Round 3 of 3`." | exact | exact | a builder's round 3 on sonnet is denied | - |
| `agent-model-cap` | agent-model-cap | "Any other spawn runs Opus only when the owner names it." | looser | exact | Explore with model opus and no `Audit:` marker passes unasked; the table gives plain Explore haiku | tool fix: exempt Explore only with the `Audit:` marker |
| `lane-effort-pin` | agent-model-cap | "A lane session runs at medium effort" | exact | exact | a lane create_session whose prompt is not `/effort medium` is denied | - |
| `builder-test-edit` | builders-cannot-edit-tests | "A builder that cannot pass a test must not delete, skip or rewrite it." | stricter | exact | a builder Write to `<scratchpad>/test_probe.py` or `docs/spec/api.md` is denied: the test-path check reads paths outside the repo, and `spec` counts as a test folder | tool fix: skip paths outside the repo; count `spec` only for code files |
| `test-author-scope` | builders-cannot-edit-tests | "`test-author`: the inverse." | exact | exact | a test-author write to product code is denied; scratchpad passes | - |
| `record-writer-scope` | builders-cannot-edit-tests | "`record-writer`: may change only `*.md` files" | exact | exact | a .txt note in its own scratchpad is denied; the literal rule holds | - |
| `designer-scope` | design-agents | "refuses a designer's Edit or Write on a repo path outside the design folder." | exact | exact | a designer write to hooks/ is denied | - |
| `builder-diff` | builders-cannot-edit-tests | "`builder`: logged when the diff holds a test path." | exact | exact | noted at commit, push and stop; never refuses | - |
| `author-diff` | builders-cannot-edit-tests | "Logged when the diff holds anything but a test path, test config or a dev dependency list." | exact | exact | a test-author diff with product code is noted | - |
| `writer-diff` | builders-cannot-edit-tests | "A diff that holds one is logged at commit, push or stop" | exact | exact | a record-writer diff with a .py file is noted | - |
| `designer-diff` | design-agents | "logs a designer's diff at commit and stop the same way" | exact | exact | a designer diff outside the design folder is noted | - |
| `role-diff-main-checkout` | none | - | uncited | exact | a SubagentStop with cwd in the main checkout is noted and the diff skipped | rule rewrite: one line in builders-cannot-edit-tests |
| `role-diff-unresolved` | none | - | uncited | exact | it is also logged when the diff is unread (None is not "") | tool fix: log it only for a read diff; rule rewrite: name it in builders-cannot-edit-tests |
| `role-diff-unread` | builders-cannot-edit-tests | "An unreadable diff logs `role-diff-unread`." | exact | exact | an unread diff is noted, never blocks | - |

Notes: lint/rule_mechanisms.json calls roles-sonnet-is-the-ceiling unmechanized, but agent-role-model and agent-model-floor now enforce it.

## D. Question form and waiting page

| Refusal | Rule it cites | Rule sentence | Verdict | Gold | Showing case | Proposed fix |
|---|---|---|---|---|---|---|
| `port-question` | port-keeps-behaviour | "It says so in a 'Departs from: <file>:<symbol> — <what changes>' line." | looser | exact | a port task with "Departs from: none" or no file:symbol passes | tool fix: run the departs check on port task context; require file:symbol on the main side |
| `uniform-pick` | uniform-over-variants | "It carries 'Goes against your ruling…' and is never the recommended option." | exact | exact | an unmarked widening option passes; the decision accepts that limit | - |
| `press-link` | act-in-place | "An option or step that asks him to press in a web app carries a link to that exact page." | stricter | exact | option "Merge PR #374" with no link is refused, though the session does the merge after the pick | rule rewrite: a press the session runs needs no link, or tool fix: skip it when the option's how says the session does it |
| `command-in-item` | act-in-place | "A step never sends him to a file for a command, and never holds one." | stricter | exact | step "Search for `foo\|bar` in the page" is refused: any semicolon or pipe in a code span counts as a shell line | tool fix: count a span only when it starts with a shell program or cmdlet |
| `question-form` | question-form | "Goal, Problem, Based on lines in this order; each option's description says Gain: and Lose:." | looser | exact | the copied template "Goal: <the goal>" passes; only Departs from is checked for placeholders | tool fix: apply the placeholder check to Goal, Problem and Based on |
| `owner-judge` | owner-judge-test | "The stake is one of goal, money, risk, rule, cannot undo." | exact | exact | a false stake passes; the decision accepts that limit | - |
| `task-names-check` | task-names-its-check | "A waiting-page task carries a line in `context` that starts `Why yours:`." | exact | exact | false check text passes; the decision accepts that limit | - |
| `option-letter-keys` | option-keys-are-letters | "The key of each option is that letter in lowercase." | exact | exact | only the decision says it; no CLAUDE.md or style line does | rule rewrite: add one key-letter line to the waiting-page skill |
| `rework-off-page` | rework-leaves-page | "A session never writes an open item that says it is being reworked." | exact | exact | the stricter cases (history text) are limits the decision accepts | - |
| `question-departs` | port-keeps-behaviour | "It also refuses a no-change word in the first clause of the change side." | exact | exact | "Departs from: main — adds a guard so nothing merges" is refused for "nothing", as the decision's word list says; the style rule names only three words | - |
| `item-field-rendered` | item-field-rendered | "refuses an ArtifactData write to items that names a top-level field outside the list." | exact | exact | the list is read from page.html itemFields | - |
| `page-stale` | page-stale-publish | "Every republish of a waiting page is main's page.html with the live designData and roadmap blocks kept." | looser | exact | a republish of main's raw page with empty designData and roadmap blocks passes, and the live data is lost | tool fix: deny a republish whose designData block equals main's empty template, unless it is a first publish |
| `gh-login-switch` | act-in-place | "A gh command block opens, after its `cd`, with `gh auth switch -u shivinate7`" | stricter | exact | a str_replace of "gh pr view 3" to "gh pr view 4" is refused, though the stored command keeps its switch | tool fix: on str_replace, judge the whole command after the edit |

Notes: owner-judge also fires on prose "Problem statement:" (wrong id only). gh-login-switch and command-in-item judge waiting-page tasks only; chat is the reply judge's.

## E. Merge tool, first half: locks, reads, waits, the merge call

| Refusal | Rule it cites | Rule sentence | Verdict | Gold | Showing case | Proposed fix |
|---|---|---|---|---|---|---|
| `merge:records-generator-unloadable` | none | - | uncited | exact | the records generator cannot be imported (lines 35-36); the tool stops | rule rewrite: none needed, operational |
| `merge:undo-check-unknown` | silent-undo-check-design | "merge.py refuses on unknown, because its merge cannot be taken back." | exact | exact | unreadable history (241); --undo-check-unknown-ok lifts it | - |
| `merge:undo-check-dropped` | silent-undo-check-design | "a real flag stops the merge." | exact | exact | the branch drops base lines with no trailer (246) | - |
| `merge:rate-wait-unextendable` | none | - | uncited | exact | a rate-limit wait needs the lock extended first (194) | rule rewrite: merge-lock decision |
| `merge:lock-held` | none | - | uncited | exact | a live or old-name lock stops the run (278, 381, 486, 585) | rule rewrite: write a merge-lock decision (holder, time limit, take-over) |
| `merge:lock-acquire-unreadable` | none | - | uncited | exact | the lock ref, commit or base cannot be read or made (461, 480, 553-584) | rule rewrite: merge-lock decision |
| `merge:lock-extend-failed` | none | - | uncited | exact | the lock expired, passed its max hold, or its push failed (423-433, 495, 499, 595-602) | rule rewrite: merge-lock decision |
| `merge:unlock-failed` | none | - | uncited | exact | `merge --unlock` cannot expire the ref (530, 619, 621) | rule rewrite: merge-lock decision |
| `merge:host-read-failed` | no-merge-during-batch-ci | "A failed read refuses. Unknown is red" | exact | exact | a page, PR, protection or run read fails (670, 703, 766, 918) | - |
| `merge:gh-network-failed` | none | - | uncited | exact | a network error outlasts the retries (645); no claim revert | - |
| `merge:pr-unnamed-or-ambiguous` | none | - | uncited | exact | no PR named and the branch unreadable (692), or 0 or 2+ open PRs on one head (696) | - |
| `merge:required-none-named` | no-merge-during-batch-ci | "The tool refuses a base with no protection and no pinned list." | exact | exact | no protection (776) or an empty list (782) | - |
| `merge:ignore-clash` | git-never-merge-failing-ci | "Never merge failing CI." | exact | exact | merge.ignoreChecks names a required check (780) | - |
| `merge:pinned-mismatch` | main-branch-protection (nearest) | "so the merge tool reads the name from the protection." | uncited | exact | a pinned check list differs from a non-empty protection list (800) | rule rewrite: add "the pin equals the protection" to main-branch-protection |
| `merge:wait-deadline` | standing-merge-grant | "The required checks must pass on the head that merges" | exact | exact | the head is still pending at the deadline (907), or GitHub shows the old head (871) | - |
| `merge:wait-head-moved` | standing-merge-grant | "The required checks must pass on the head that merges" | exact | exact | the head differs from the waited commit (877) | - |
| `merge:wait-base-changed` | merge-needs-current-base (nearest) | "The head and the base tip merge cleanly." | uncited | exact | the PR base changed (875) or the PR went conflicting (879) during the wait | rule rewrite: add both cases to merge-needs-current-base |
| `merge:wait-red` | git-never-merge-failing-ci | "Never merge failing CI." | exact | exact | any red check or run (884) | - |
| `merge:wait-required-unreported` | ci-unknown-is-red | "a green exit on an unread input hides a defect." | exact | exact | a required check no run reports (891) | - |
| `merge:base-red-or-unknown` | no-merge-onto-red-main | "Unknown refuses, as the silent-undo check does." | exact | exact | the newest base run is red, or cancelled with no red job (947-980) | - |
| `merge:head-read-verdict` | git-never-merge-failing-ci | "Never merge failing CI." | exact | exact | red, pending, no check yet, or unknown is not green (1025-1057) | - |
| `merge:ready-never-sent` | records-index-at-merge | "so the batch runner marks the PR ready" | exact | exact | the tool never marks a PR ready (1073) | - |
| `merge:blocked-or-behind` | none | - | uncited | exact | a PR GitHub reads BLOCKED (for example, by a missing review) or BEHIND gets no merge call (1085) | rule rewrite: add to standing-merge-grant that a BLOCKED PR never merges |
| `merge:merged-other-head` | standing-merge-grant | "Only a proven refusal reverts the claim" | exact | exact | the PR merged at another head (1103); no revert | - |
| `merge:outcome-unproven` | standing-merge-grant | "Only a proven refusal reverts the claim" | exact | exact | state unread (1098), network loss (1105), or exit 0 still open (1107); after the claim push, a read that could not run (a failed wait read, the wait deadline with a check pending, a base read, a small-move read such as the lint listing, the workflow, a suite file or a merge that names no conflict, a debt check with only unknown findings) | - |
| `merge:refused-reply` | standing-merge-grant | "a refusal reply with the pull request still OPEN" | exact | exact | GitHub refuses the merge call (1111); the claim reverts | - |
| `merge:claim-refused` | records-index-at-merge (nearest) | "claims record numbers under the merge lock" | uncited | exact | the claim exits non-zero (1173) or prints two claim lines (1176) | - |
| `merge:stamp-config-unreadable` | standing-merge-grant (nearest) | "reads the switch from the base branch on origin" | uncited | exact | the base config cannot be read or parsed (1135, 1141, 1144) | - |
| `merge:records-commit-failed` | records-index-at-merge | "Only the merge tool rebuilds the page." | unverified | exact | the generator or its commit fails (1189, 1202, 1226) | - |
| `merge:records-conflict-beyond-page` | merge-needs-current-base | "The head and the base tip merge cleanly." | exact | exact | the base conflicts on a file other than the records page (1215) | - |
| `merge:records-no-page-to-heal` | records-index-at-merge | "The heal stops when the generator writes no page for a conflicted page." | exact | exact | (1221) | - |
| `merge:small-move-unproved` | merge-needs-current-base | "A small move is the one exception: ... any read that fails refuses." | exact | exact | a suite or lint read fails, so the base move is not proved small (1422-1556); after the claim push it is `merge:outcome-unproven`: the claim stays | - |
| `merge:holds-base-behind` | merge-needs-current-base | "The merge tool refuses a head that does not hold the base tip." | exact | exact | the head lacks the base tip with no small-move proof (1577-1579) | - |
| `merge:push-refused` | none | - | uncited | exact | the plain push of the PR branch is refused (1584) | - |
| `merge:ff-main-skipped` | shared-trees-no-destructive-git | "No destructive git." | exact | exact | the local main is not moved when a fetch, ancestry or ff-only fails (1617-1631) | - |
| `merge:cleanup-keeps` | merge-deletes-batch-lanes | "Its worktree goes when the sweep's `--fast` judgment says reap." | exact | exact | a held tree or an unmerged tip is kept (1650-1699); never blocks the merge | - |

Notes: batch_running (726-753) computes the blockers; area F rows its refusal. The merge lock has no decision record: 5 lock rows uncited. BEHIND needs strict protection, off here, so BLOCKED is the live case.

## F. Merge tool, second half, and the guard's merge rules

| Refusal | Rule it cites | Rule sentence | Verdict | Gold | Showing case | Proposed fix |
|---|---|---|---|---|---|---|
| `merge-checks` | git-never-merge-failing-ci | "Never merge failing CI." | exact | exact | `gh pr merge 5` on a red or pending head is denied | rule rewrite: add the decision slug no-merge-during-batch-ci to the guard index line |
| `merge-checks:batch` | git-no-merge-during-batch-ci | "While a batch's integration PR has a CI run in progress, nothing merges to main" | stricter | exact | `gh pr merge 63` is denied while ready PR #65, which holds #63, runs CI | tool fix: step overlapping-batches; the guard reads the same Host.head_read, so the fix reaches it; add a guard test |
| `merge-role-proof` | session-tiers | "allows `merge --role T` only when the session's own newest `get_session` result ... lists the tag `cs-build:T`" | exact | exact | a lane runs `merge --role coordinator`: denied | - |
| `trust-card-in-build` | session-tiers | "allows the calls only when the session's own newest `get_session` record shows no `cs-build:` tag" | exact | exact | a cs-build session opens the trust card: denied | - |
| `merge:dropped-lane-unread` | silent-undo-check-design | "`merge.py` refuses on unknown, because its merge cannot be taken back." | exact | exact | git log fails; --undo-check-unknown-ok lifts it (1761) | - |
| `merge:dropped-lane-reverted` | `ci-hygiene` step 8 | "Rebuild the branch from main without them. Never revert." | exact | exact | a batch holds a net-reverted lane (1764) | - |
| `merge:default-branch-unread` | verification-report-unknown-reads | "Report a read that could not run as unknown, never as clear or broken." | exact | exact | the repo read fails (1921, 1924) | - |
| `merge:base-workflows-unread` | none | - | uncited | exact | the base workflow files cannot be read (1970, 1979) | - |
| `merge:config-unread` | none | - | uncited | exact | the base stamp.json cannot be read or is not an object (1989-2005) | - |
| `merge:config-field-invalid` | standing-merge-grant (standingGrant only) | "A value that is not `true` or `false` stops the merge tool as a broken config." | uncited | exact | `merge.deadlineMinutes: 0` or an unknown field stops (2009-2037); only standingGrant has a sentence | - |
| `merge:ignore-entry-invalid` | none | - | uncited | exact | an ignoreChecks entry with no reason (2083) | - |
| `merge:pr-closed-or-conflicting` | none | - | uncited | exact | the PR is closed or conflicting (2051, 2053) | - |
| `merge:worktree-open-failed` | none | - | uncited | exact | origin's head differs from the one gh named, or the tree cannot be added (2060-2069) | - |
| `merge:red-base` | no-merge-onto-red-main | "the merge tool refuses `merge <pr> --confirm` while the base branch's latest completed run has a red job." | exact | exact | a red or unread main run (2105); --base-red-ok lifts it | - |
| `merge:batch-refusal` | git-no-merge-during-batch-ci | "nothing merges to main, by any session or by me." | stricter (known) | exact | PR #63 is refused while ready PR #65, which holds #63, runs CI (batch_running 726-753, batch_refusal 2107, confirm 2224 and 2359-2363, preview 2149-2151) | tool fix: step overlapping-batches |
| `merge:preview-base-stale` | merge-needs-current-base | "The preview prints a `base:` line that says whether the head ... is BEHIND." | exact | exact | a BEHIND head gets "--confirm refuses it" (2129, 2132) | - |
| `merge:preview-base-run` | no-merge-onto-red-main | "The preview prints the same verdict on its `<base> run:` line." | stricter (wording) | exact | a red main says "--confirm refuses it", though --base-red-ok lifts it (2156) | tool fix: add "unless --base-red-ok" to the line |
| `merge:draft-holds-claim` | records-index-at-merge | "refuses ... a head that carries a claim" | exact | exact | a draft head with a claim line (2177) | - |
| `merge:draft-base-stale` | records-index-at-merge | "refuses a head that does not hold the base tip" | exact | exact | a BEHIND or unknown draft head (2182) | - |
| `merge:base-changed-under-lock` | none | - | uncited | exact | the PR is retargeted during the lock wait (2217) | - |
| `merge:confirm-stale-base` | merge-needs-current-base | "The merge tool refuses a head that does not hold the base tip." | exact | exact | the head is behind main and the move is not small (2231) | - |
| `merge:claim-off-default-base` | one-shared-record-stamp (nearest) | "The claim runs before the merge, on the pull request branch" | uncited | exact | a claimed head on a base that is not the default (2239) | rule rewrite: one line in one-shared-record-stamp |
| `merge:confirm-head-not-green` | git-never-merge-failing-ci | "Never merge failing CI." | exact | exact | the head checks are red before the claim (2258) | - |
| `merge:confirm-required-names` | no-merge-during-batch-ci | "The tool refuses a base with no protection and no pinned list." | exact | exact | no protection and no pin (2210, 2220) | - |
| `merge:confirm-wait-not-green` | git-never-merge-failing-ci | "Never merge failing CI." | exact | exact | a check goes red; the claim reverts (2287). The deadline with a check pending is `merge:outcome-unproven`: the claim stays | - |
| `merge:claim-proof-stale` | merge-needs-current-base | "A base that moved during the wait, and is not a small move, reverts the claim." | exact | exact | the claimed number is now taken (2295-2310). A base fetch that fails, or an UNKNOWN stamp or undo read, is `merge:outcome-unproven`: the claim stays | - |
| `merge:records-stale` | records-index-at-merge | "A stale page ... gets the rebuild commit" | exact | exact | the base gained a record outside the tool (2317, 2321) | - |
| `merge:base-moved-in-wait` | merge-needs-current-base | "a batch merges only after a green run that holds for the current main." | exact | exact | main moved during the wait, not small (2324) | - |
| `merge:heal-push-failed` | records-index-at-merge | "When only the page conflicts with the base, the tool rebuilds it on the merged tree." | exact | exact | the heal commit push fails; the claim reverts (2334) | - |
| `merge:heal-not-green` | merge-needs-current-base | "A heal merge commit ... Its own checks wait before the merge." | exact | exact | the heal commit is red, or the base moved again (2343-2349) | - |
| `merge:host-refused` | none | - | uncited | exact | the merge call is refused, for example the head moved; the claim reverts (2366) | - |
| `merge:confirm-unexpected-error` | none | - | uncited | exact | an error after the claim push that is no read (not a timeout, OS or value error); the claim reverts (2266-2277, 2370) | - |
| `merge:role-write-failed` | session-tiers | "Local sessions: unchanged." | uncited | exact | `--role` outside the cloud, with no session id, or on an unwritable file (2422, 2424, 2436) | - |
| `merge:role-tier-invalid` | session-tiers | "The merge tool refuses any other tier, and the refusal lists no tier." | exact | exact | `--role lane` (2426) | - |
| `merge:no-merge-role` | session-tiers | "Only a coordinator or batch runner gains a way to merge" | exact | exact | a cloud --confirm with no role file (2461, 2403-2415) | - |
| `merge:standing-grant-off` | standing-merge-grant | "`false`: in a cloud session, the merge tool refuses `merge <pr> --confirm` for both merge roles" | exact | exact | standingGrant false on the base (2478) | - |
| `merge:arg-errors` | none | - | uncited | exact | `merge --role 3`, or a run outside git (2452, 2454, 2464) | - |

Notes: every Stop ends "No override lifts this refusal" (2488), false for red-base and dropped-lane, which name a reason flag; tool fix: append it only where no flag lifts. The guard reads pinned and ignored checks from the cwd's stamp.json, the tool from the base; debt batch-guard-config-from-cwd covers it.
## Cross-cutting findings

- **False "no override" text.** Every merge tool stop ends "No override lifts this refusal". Two
  stops, red-base and dropped-lane-unread, are lifted by a reason flag. The text is stricter than the
  tool. Tool fix: add the line only where no flag lifts the stop.
- **No merge-lock decision.** Five merge rows (lock held, lock unread, lock extend failed, unlock
  failed, rate wait) refuse with no record behind them. Rule rewrite: write one merge-lock decision:
  who holds it, for how long, and who may take it over.
- **Stale rule map.** `lint/rule_mechanisms.json` calls rule roles-sonnet-is-the-ceiling (Sonnet is
  the agent model cap) unmechanized. Guard rules agent-role-model and agent-model-floor enforce it now.

## Follow-up steps

Each stricter or looser row becomes one step. Triage owns the steps. This record changes no guard.

- **Stricter, tool fix:** `merge-checks:batch` and `merge:batch-refusal` (step overlapping-batches),
  `pointer-head`, `command-in-item`, `gh-login-switch`, `machine-wide-kill`, `detached-launch`,
  `impeccable-review-only`, `builder-test-edit`, `merge:preview-base-run`, the "no override" text.
- **Looser, tool fix:** `shared-tree`, `destructive-delete` (`$(pwd)`, heredoc forms), `session-home`,
  `agent-model-floor`, `port-question`, `question-form`, `page-stale`.
- **Fit the tool to the rule** (process-only, coordinator 2026-11-01 21:14 CST). The rule stays,
  and the tool moves to fit it:
  - `agent-model-cap`: a fix step (refusal-looser-fixes). The owner's waiting-page item 137, pick a
    (2026-11-01 18:38 CST), rules it: an Explore whose brief carries `Audit:` may run Sonnet or Opus.
    An Explore on Opus with no `Audit:` mark is refused, unless the owner's override lifts it.
  - `press-link`: a fix step. The rule covers a press the owner makes. The check stops asking for a
    link on a press the session makes.
  - `silent-write`: no step. The guard holds part of its rule, and CLAUDE.md holds the rest. See note
    silent-write-ref-gaps.
  - `load-brake` and `create_session`: no step. A cloud session adds no load to this machine. See note
    load-brake-skips-create-session.
- **Uncited, rule rewrite:** the merge-lock decision, `env-file`, `config-edit`,
  `ln-over-directory`, `role-diff-main-checkout`, `role-diff-unresolved`, `merge:pinned-mismatch`,
  `merge:wait-base-changed`, `merge:blocked-or-behind`, `merge:claim-off-default-base`.
