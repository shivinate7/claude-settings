Lane brief: watchers-prose-and-plan. Topic: watchers-prose-and-plan.

Repo shivinate7/claude-settings, from origin/main. Your parent is the coordinator (session_013NEJL2hB1pLZPDpzas7VgB). One lane, one topic. Roles: record-writer (sonnet) writes, reviewer (sonnet) reads. Owner Cockpit item 180 (owner, 2026-11-04 06:50 CST): "align all of these toward one uniform direction as its currently a patchwork of lessons bugs and fixes and stale prose". A read-only Sonnet workflow mapped 30 watch, wake, sweep, reap and log mechanisms. Its plan, its critic, and the stale-prose list are pasted below.

Task:
1. Land the plan as docs/plans/align-watchers.md (rule building-land-design-or-abandon). It holds the model, the table, merges, deletes, lanes and the critic's corrections, all in STE. Mark section 6 (owner questions) as open: items 180, plus new items on model-call hooks, unread logs and SessionEnd sweep scope, are on the Cockpit. Fold in the critic's corrections. The critic found that only the stall watcher wakes an idle session, and it listed the missed hooks.
2. Fix the stale prose below, in records, docs, GUIDE.md and code comments only. Verify each claim against main first (rule verification-report-unknown-reads). Drop a claim that main does not show, and name it in your report. Change no behaviour, no guard or check verdict, and no test.
3. Do not rename record slugs (a slug never changes). Fix a title or body only.
4. Leave out "Cost:" lines. They wait on item 180.

Check: `./bin/verdict ./bin/ci-job checks --lint` (lane lint may false-FAIL on missing node_modules; #1219 fixes it, so name it in the hand-off). Then give the coordinator the branch, head sha and a draft PR number. Do not mark it ready. Report cap: 20 lines.

# Plan

Sources: everything below comes from the supplied map. I did not re-read the repo; the working directory is not a git checkout. "read" means stated in the map or the prompt, "inferred" means my reasoning from it.

**1. The model (8 lines)**
1. Events: a mechanism runs only inside a hook or tool process the harness already started (PreToolUse, PostToolUse, Stop, SessionStart, SubagentStop, SessionEnd), or when a person asks. Never on a timer. (read: outcomes-mechanize-rules)
2. It may start nothing that outlives its hook, and only short, bounded children (`git`, `ps`) inside the hook budget. (read: same rule)
3. Waiting is done by the harness's own wake (task notification, PR `ci-done` comment, `send_later`), not by our polling process. Departs from stall-watch and ci-wait-reads-run-status. (read: cloud wake in the CI record)
4. Each record has one Cost line: process starts, files written, how often. (read: the rule)
5. One shared test helper proves that line: child count, files written, sleep passes. The test is the proof, not prose. (read: the rule says "a test proves")
6. Every log names its reader in its record and has a size cap. If it has no reader, it is not written. (read: the rule; the cap is my addition)
7. One record per mechanism. It holds the ruling, Cost, Reader and Test lines, and no history paragraphs. (read: speak-rewrite-superseded-in-place, git-one-record-per-question)
8. `check-records` fails a mechanism listed in `lint/rule_mechanisms.json` whose record lacks those lines. (inferred: the checker's home exists; extending it is the change)

**2. Table**
| mechanism | today | change | owner ruling? | size |
|---|---|---|---|---|
| stall-watch watcher | one python per background job, 0.2 s loop, 1 s `ps`; record says "no new process or timer" (read) | drop the watcher; the Stop check and `wait-pid` stay; or cap, state cost, add test | yes, changes the ruling | L |
| stall-watch temp files | `.log`/`.beat` left after a stall (read) | remove them on every exit path | no, defect | S |
| stall Stop check | repeats the message at every Stop (debt, read) | dedupe per job; add Cost line | no | S |
| ci_wake | 55 min polling python per `gh pr ready` (read) | keep until the harness can wake on PR events; write the Cost line and a process-count test; remove lock files | yes, because it is a standing exception | M |
| config_watch | one python per matching call, fast path (read) | add Cost line and "writes nothing" test; fix "every call" wording | no | S |
| decision_watch / mod | 1–3 pythons per turn; 3+ rewrites of `shadow.log` per turn (read) | skip python unless a protected path changed; append, don't rewrite; drop the "STOP seen" line | yes for the log drop | M |
| daily_note | one python per startup (read) | add Cost line and a "no process" test; rename the slug | no | S |
| waiter guard | in-process, free (read) | add Cost line; fix the three false-alarm debts | no | S |
| sweep (machine-wide) | the hook run does machine-wide tiers, contradicting its record (read) | make the hook run one repo only (a flag); machine-wide tiers stay in the daily job | yes, the record's claim and the code differ | M |
| process tiers / sim tier / temp tier | report goes to DEVNULL in the hook (read) | run only in the daily job; add Cost lines | no | S |
| agent-end reap | detached delete child, no bound (read) | give the child a time cap; add Cost line; split the record by stage | no | M |
| agent-end payload log | no named reader (read) | delete (section 4) | yes | S |
| daily job installers | timer by design, logs unread (read) | keep the timer; name the reader or drop the logs | yes, the timer is a standing exception | S |
| sim-lease | 2 s poll inside `take` (read) | keep; add a cost test; fix the docstring | no | S |
| sim_boot_record | no cost line (read) | add Cost line and test | no | S |
| SessionStart refresh child | one detached child per start (read) | move its cost into the decision record | no | S |
| machine-load-brake | cost stated and proven (read) | this is the model; copy it | no | none |
| guard.log writer | no cost line, no size cap (read) | add cap and Cost line | no | S |
| verdict | per-run file plus 7-day prune, no record (read) | write the record | no | S |
| guard.py import wait | 5 s sleep on failure only (read) | none | no | none |

**3. Merges (building-one-home-per-capability)**
- Every "state my cost" statement moves to one Cost line per record, plus one test helper. Today the cost sits in code docstrings, README and records. (read)
- stall-watch's two entries in the map (the same code twice) become one record. (read)
- ci_wake has two map entries; its `gh` wait should be one helper shared with `merge/merge.py` (inferred).
- One load definition: guard (memory, disk) and sim-lease (`vm.loadavg`) differ (read). Ask the owner whether they should differ.
- `install_schtasks.resolve_primary_checkout` becomes a call to `guard.primary_checkout` (read).
- One process scan per session end, not two (scratchpad reap, then sweep) (inferred).
- Agent-end reap and its payload log into one record with the sweep's process tiers (inferred).

**4. Deletes (building-guard-needs-incident)**
- The agent-end payload log: it exists to measure unknown fields, its only reader is a manual proof script, and the fields are still logged (read).
- The "STOP seen" line in `shadow.log`: its only reader is the `/dw` count that checks the mod fires, and the record admits no live read (read).
- `janitor-runs.jsonl`: no reader found by `git grep` (read).
- `launchd-sweep.log` and `.err.log`: no reader (read). Report stays on stdout for a person.
- The loose-process tier inside the hook run: it is report-only, and the hook sends it to DEVNULL, so cost is O(all pids) for no reader (read; the cost is inferred).
- The `md_sweep.py` stub: delete 14 days after `check_hook_stubs` allows (read).
- The stall watcher: harm stopped is the 2026-10-31 incident, whose size is unmeasured. The Stop check and `wait-pid` cover most of it (inferred). Do not delete before the owner rules.

**5. Lanes, smallest first**
1. Text only: fix stale prose (slugs, `guard.worktree_live_session`, "both scripts deleted", the stale schtasks debt, unread-doc claims). S.
2. Cost lines and one test helper for the already-cheap mechanisms (config_watch, daily_note, waiter, sim_boot_record, guard.log, verdict, refresh child). S.
3. Stall defects: temp file cleanup after a stall, Stop-message dedupe. S.
4. Log cull: payload log, STOP seen, janitor-runs, launchd logs, a guard.log cap. S, after owner rules.
5. Hook-run sweep scope: one repo only, plus record rewrite. M.
6. decision_watch: no python on a quiet turn, append-only log. M.
7. Agent-end reap: bounded delete child, one process scan. M.
8. `check-records` rule for Cost, Reader and Test lines. M.
9. Stall watcher and ci_wake: replace or cap, per owner ruling. L.

**6. Owner questions**
- Stall watcher: (a) delete it and keep the Stop check plus `wait-pid`; (b) keep it with a cost cap and test; (c) leave it. I recommend (a) if the 2026-10-31 incident is covered by the Stop check, which is unmeasured.
- ci_wake: (a) keep as a standing exception with its cost stated; (b) replace with PR subscription locally too. I recommend (a) for now.
- Daily timer: (a) keep as a standing exception; (b) run the sweep only at SessionEnd. I recommend (a).
- Sweep hook run: (a) one repo only; (b) keep machine-wide. I recommend (a).
- Logs without a reader: (a) delete now; (b) name a reader. I recommend (a).
- Load definition: (a) one shared; (b) keep two. I recommend (b), with one record that says why.

# Critique

Review of the map and plan, against origin/main (446f2d3d). Searched `hooks/`, `bin/`, `janitor/`, `lint/`, `merge/`, `settings.json`. I did not read every hit in full.

**1. Mechanisms the map missed**
- Model-call judges. Each hook below makes a `claude -p` call through `decision_watch.invoke_model`, which is a process of up to 120 s. The map covers the call only inside decision_watch.
  - `call_judge.py`: PreToolUse on Agent|AskUserQuestion|ArtifactData, timeout 70.
  - `prose_judge.py`: Edit|Write, timeout 45.
  - `reply_judge.py`: Stop, timeout 25.
  - `feedback_guard.py`: Stop, timeout 60.
  - `lint/report_guard.py`: Stop, timeout 35, a model call at line 1267.
  - `local_time.py`: UserPromptSubmit and SubagentStart, timeout 30 (an Opus call, per its comment).
- Other hooks with no map row and no cost line:
  - Stop: `ruling_home.py` (20 s) and `reread_check.py` (10 s).
  - PreToolUse: `blind_brief.py` (10 s) and `rm_prompt_answer.py` (20 s).
  - PostToolUse: `sendmessage_state.py` (50 s).
  - SubagentStart: `agent_brief.py`.
  - PreCompact and SessionStart compact, clear and fork: `precompact_handoff.py` (the map only has its `cc_version_check`).
  - A second guard.py Stop row (timeout 20), which the map also omits.
- `sendmessage_state.py:91` starts a node reader child (`start_new_session`, bounded by `READER_TIMEOUT`).
- `question_form.py:1422` starts a long-lived `git cat-file --batch` child.
- `bin/ci-job` Popens `verdict` per job.
- `merge/merge.py` has standing wait loops at lines 228 (`retry_net`, rate-limit waits) and 988 (waiting for the head to appear). The plan's "one gh wait helper shared with merge" ignores that it is a second poll loop with its own pause seam.
- `bin/ios-ship` has a `setsid` escape comment at line 270. `bin/shoot` and `merge/launch.py` came up in the search; I did not read them.
- The map reads `mutate_guard.py` and `mutate_shared.py` as CI tooling, but `mutate_shared.py:483` starts sessions with `start_new_session`.

**2. Claims in the plan that are wrong**
- Section 4 says the Stop check covers most of the stall watcher's job. A Stop check fires once at turn end. A session idle on a silent background job gets no further Stop until a wake, so a job that stalls later is never reported. Only the watcher's exit-3 wake does that. The plan's recommendation (a), delete the watcher, rests on this error.
- Table row "daily_note: add a 'no process' test". The map says `cc_version_check` already claims it starts no process, so the gap is a missing test, not an unstated cost. Minor.
- "Cost lines for the already-cheap mechanisms" lists 7 items. The model judges (item 1 above) cost far more, and the plan never mentions them.

**3. Safety holes the plan would open**
- Deleting the stall watcher with only the Stop check left removes the one wake for a stranded job. The `kill -0` and polling guards stay on, so agents will wait blind. This is a possible hole, not a guard refusal: it only strands agents.
- Moving the process tiers and sim shutdown out of the SessionEnd run leaves orphaned servers and booted simulators until the daily job runs. The `simulator-boot-cap` guard refuses at 2 booted devices, so a sweep that runs less often means more refusals (false alarms), not a hole.
- "Skip python on a quiet turn" in decision_watch: the skip test must use the same protected-path set as the current `--emit-prompt`, or a protected change goes unjudged. I found no refusal in this path (it never refuses).
- "Drop the `STOP seen` line" removes the only live evidence that the mod fires. The record already admits it was never read live. Land a different fire-check first.
- A `guard.log` cap that truncates removes the `crash` lines `daily_note` reads. Cap by rotating, not trimming.
- No change in the plan turns a main refusal into an ask.

**4. Owner questions**
- Missing: whether model-call hooks (the 25 to 70 s judge processes) count under the "no new process" rule. Today `invoke_model` is the one home, so one decision covers all six.
- Missing: a wake that fires while the session is idle. This decides the stall-watcher question, and the plan leaves it out.
- Mis-stated: "Daily timer (a) keep, (b) run at SessionEnd only". The sweep also runs in SessionEnd, so the real choice is whether the hook run stays machine-wide.
- Mis-stated: the load-definition question is lower value than the two above, and sim-lease already states its own definition.

# Stale prose found by the mappers

## stall-watch wrapper and watcher (stall_watch.py --hook, --watch-pid)
Record: docs/decisions/stall-watch.md
- stall-watch.md 'Unmeasured: ... no test pins the cost.' (wait-pid bullet): it is true now, but it concedes that the rule's required cost test is missing.
- stall-watch.md 'a builder's choice, not measured' for the 300 s age: an unmeasured figure, still marked as such.
- Record heading list says the watcher 'does the waiting' to avoid a polling timer in the session: the timer moved into the watcher process rather than disappearing. The 'A polling timer in the session is refused by the waiter guard rule' argument protects the session, not the machine.

## stall-watch Stop check (stall_watch.py --stop)
Record: docs/decisions/stall-watch.md (section 'The Stop-time check'); docs/debts/stall-message-repeats-every-stop.md
- The record's 'The Stop-time check' says it 'lists stalled shells' once a turn ends; the debt says it repeats. The record does not mention the repeat.

## ci_wake (PostToolUse asyncRewake watcher)
Record: docs/decisions/ci-wait-reads-run-status.md (sections 'The ruling', 'The CI wake-up'); debts ci-wake-export-gh-repo-unread, ci-wake-gh-host-bare-repo, ci-wake-lists-runs-once
- Record title 'CI waits read the run status' and its section 'The CI wake-up' both lack any cost statement of process starts and files, which rule outcomes-mechanize-rules requires.
- ci_wake.py header says 'It lists runs, and reads a run's status, 30 s apart for the first 4 minutes, then at gaps that grow to 120 s'. It matches the record. The record's 'owner, 2026-10-21, back-off' ruling is date-only and the date cannot be re-derived from code. (not stale, but unverifiable)
- agents-wait-with-monitor.md says the guard remedy 'names the CI-wake notice that follows `gh pr ready`, or Monitor'. WAITER_REASON in hooks/guard_stream.py should be re-read to confirm it still does (inferred: not read in full).

## config_watch (PostToolUse and Stop revert of the agent model cap)
Record: docs/decisions/config-watch-fast-exit.md (also opus-grant-expires, predicate-is-the-act referenced)
- Docstring paragraph 'THE ONE HARD PART. `save_baseline` used to re-baseline ... The baseline entry now carries a THIRD field' and 'the shape every entry written by the version on `main` carries': narrates history ('used to', 'now', 'the version on main'), which rule building-comments-say-why and speak-rewrite-superseded-in-place forbid.
- Record sentence 'A missing shared module. ... The stall check prints nothing on Stop' still holds for stall_watch.py (TASK_NOTIFICATION_TAG fallback None), but it lives in config-watch-fast-exit.md, not stall-watch.md. The record points the wrong way (the ruling for the stall check's fallback sits in a record about the config watch).

## decision_watch (script, now driven by the decision-watch mod)
Record: docs/decisions/decision-watch-mod-limits.md
- decision-watch-mod-limits.md 'Owner, 22:00 CDT ("Fix, then swap")' has no date, so no reader can place it.
- '## Unverified ... Live: no "seen" line has been read in shadow.log after a real Windows turn. It is pending until the move lands.' Stale or unresolved: the move has landed (enabledPlugins true) and the record has not been closed with a result or an owner choice.
- 'This is a read of the marketplace copy of sec-default. The installed app's copy is unchecked' is an unmeasured claim left open.
- hooks/decision_watch.py docstring 'Replaces the `type: agent` guardrail' narrates history; and 'old markdown sweep' ('scoped by mtime ... the same way the old markdown sweep did'). Both are history (rule building-comments-say-why).

## daily_note (SessionStart startup note and cc_version_check)
Record: docs/decisions/guard-log-read-weekly.md (file name says weekly, title says daily). cc_version_check: docs/decisions/precompact-handoff.md item 12 (named in the docstring, not read here)
- guard-log-read-weekly.md slug says 'weekly'; the ruling is a daily note with a 7-day window. The title was rewritten and the id was not (rule git-one-record-per-question: rewrite in place; a slug never changes, so the mismatch stays).
- guard-log-read-weekly.md: 'The STE write guard and the markdown sweep wrote `STE-fallback` and `STE-unchecked` lines. Both are removed ... Old rows stay in guard.log' is a history paragraph (rule speak-rewrite-superseded-in-place).
- daily_note.py docstring: 'There is no volume check: refusals grew with use, and a count check fired on 6 of 14 real days.' states a measurement with no re-run command (rule verification-checked-reader-for-numbers).

## waiter guard rule and Monitor allowance (agents-wait-with-monitor)
Record: docs/decisions/agents-wait-with-monitor.md
- 'Almost none of the refusals were real loops' is a count with no stated source or re-run command; it is unmeasured.
- docs/debts/notes.md 'waiter-monitor-failures-unmeasured: Unmeasured whether Monitor still errors' means the record's reason ('the guard once refused Monitor... an agent lost a turn') has no current measurement.

## machine-wide sweep: branches, worktrees, husks, trash, tombstones, run log, fetch throttle, repo reaper
Record: the-janitor-is-one-machine-wide-sweep
- 'The parent ships branches and worktrees: pure git plus the oracle.' (record) and GUIDE.md 'branches and worktrees, which are pure git plus a liveness read': the sweep also runs npm, ps, lsof, ss, simctl and network fetch.
- GUIDE.md 'The sweep never runs code that your repository supplies. It reads one file from your repository, and it reads that file as data.': contradicted by run_repo_reaper.
- Record: 'the installers ... refuse to run from a linked worktree, except the live pin (install-refuses-linked-tree ...)': neither installer has an exception branch; both refuse when guard.is_worktree is not False (inferred: the live pinned checkout reads as not a linked worktree).
- Record: 'Banchi keeps its own tier 2 until the owner names its removal': not checkable from this repo (unmeasured).
- Record says the oracle reads `~/.claude/sessions`; the code calls git_reads.worktree_live_session (other records cite guard.worktree_live_session; guard.py has no def of it, inferred re-export or stale name).
- Record and GUIDE.md never mention the Windows temp tier, the scratchpad reap or agent_end_reap.py; GUIDE.md 'It runs against every repository on this machine' omits janitor.roots / opt-out interplay only partly (GUIDE covers roots later).
- Record: 'Each new rule gets a row in lint/rule_mechanisms.json': not checked here (unmeasured).

## process tiers of the sweep: orphaned listeners, dead-rooted servers, loose processes
Record: unattended-sweep-stops-proven-orphans
- Record cites `guard.worktree_live_session` as the oracle; code uses git_reads.worktree_live_session (inferred rename).
- Record: 'Both unattended paths may stop a proven orphan': the code now also stops dead-rooted pids from the same hook run; consistent, but 'both unattended paths' = SessionEnd and scheduled task, and the agent-end reaper is a third unattended path with its own reads (see agent_end_reap rows).

## idle simulator shutdown tier
Record: sweep-shuts-down-idle-simulators
- Ruling 3 'Guard rule simulator-boot-cap refuses ... when 2 devices are already booted' lives in hooks/guard.py, outside this area; not verified here (unmeasured).

## Windows session temp-folder sweep
Record: windows-temp-sweep
- None found. GUIDE.md omits this tier entirely (stale by omission).

## SessionEnd hook: scratchpad reap then repo sweep
Record: session-end-sweep-is-disarmed-until-liveness-is-proven (scratchpad reap is in agent-end-reap-stops-what-a-finished-agent-left, owner ruling 2026-10-26)
- File name and title 'is-disarmed-until-liveness-is-proven' vs the body 'The hook is armed on every platform'; also '(owner ask, undated)' on the no-inspect constant.
- session_end_sweep.py comment 'Windows job in checks.yml runs the guard and sweep suites' is a CI claim not re-verified here (unmeasured).

## agent-end reap: orphaned processes in the ending agent's worktree
Record: agent-end-reap-stops-what-a-finished-agent-left
- Owner ruling 2026-09-27 and 2026-10-10 sentences are history in the record body (dated rulings appended in place); outcomes say 'rewrite superseded text in place' (speak-rewrite-superseded-in-place): the record keeps four dated 'Owner ruling' paragraphs, including one that moves scratchpad reaping elsewhere ('stays as above').
- Record paragraph 'The sweep takes the deepest checkout' describes sweep.py _matching_checkout, a different file than its Home.

## agent-end reap: build folders and other idle agent worktrees
Record: build-dirs-reaped-at-agent-end (worktree removal rules: when-a-worktree-may-be-removed, outside my area)
- Record 'Reason: ... The daily janitor skips registered worktrees and the agent-end reap stopped only processes' is a pre-change narrative sentence (history), against rewrite-superseded-in-place.
- Record bullet 'An agent lock does not keep build folders (owner, 2026-10-28, waiting-page item 35 a)' duplicates item 3 of the numbered list (same ruling stated twice).
- Record cites `guard.worktree_live_session`; code uses git_reads.worktree_live_session.

## agent-end payload log
Record: agent-end-reap-stops-what-a-finished-agent-left (last paragraph only); debt agent-end-log-loses-row
- Docstring: 'Every run appends the raw payload and the decisions ... so the payload fields the docs leave unmeasured get measured.' If the fields are now measured, the log's reason is spent; the record does not say whether they are.
- Record: 'Measured on b0c87cb (PR 322 review)' is a one-time measurement pinned to a commit, kept in a standing-choice record (decision records should hold only standing choices).

## daily job installers (launchd plist, schtasks XML)
Record: the-janitor-is-one-machine-wide-sweep ('Two triggers' bullet); install-refuses-linked-tree (outside my area); janitor/GUIDE.md 'How you run it every day'
- install_schtasks.resolve_primary_checkout docstring: 'Same read `install_launchd.py.resolve_primary_checkout` makes': install_launchd.py has no such function (it calls guard.primary_checkout).
- Record: 'except the live pin (install-refuses-linked-tree)': neither installer has that branch.
- GUIDE.md 'Two installers write a scheduled job ... Neither one runs that job itself': true, but whether the job is loaded on any machine is unmeasured.

## mutation test and end-to-end proof scripts
Record: none dedicated (mutation-report-scores-suites and the-janitor-is-one-machine-wide-sweep 'Proof' bullet name the practice); GLOSSARY entry 'mutation test'
- None found in the files; the record corpus names mutation proof only in a one-line 'Proof' bullet inside the-janitor-is-one-machine-wide-sweep.

## machine-load-brake
Record: docs/decisions/machine-load-brake.md (also docs/plans/refusal-vs-rule.md row for load-brake; docs/records.md row)
- 'The memory level is a placeholder for the owner to tune' (85/95 thresholds unmeasured).
- 'Risk kind: ... running lanes, incident, landed with this change' ('this change' has no referent).
- Ruling opener says 'a busy or full machine refuses new lanes' while later bullets say busy no longer slows Agent lanes in the desktop app; docs/plans/refusal-vs-rule.md row quotes the opener.
- 'Full only.' bullet repeats the 'Running lanes' bullet; the opening paragraph strings five dated rulings (history narration, speak-rewrite-superseded-in-place).
- 'Not covered' says start_session only; debt load-brake-skips-create-session holds the create_session case; the record does not point to it.

## guard.log writers
Record: docs/decisions/guard-log-read-weekly.md (first paragraph of The ruling); no separate cost record
- '`hooks/guard_core.py:record()` appends one line per verdict' uses a path-and-symbol with a colon form; fine, but 'one line per verdict' is untrue for allowed calls (nothing logged).
- 'The STE write guard and the markdown sweep wrote STE-fallback and STE-unchecked lines. Both are removed' is history narration for dead rows.

## guard_log_report + daily_note (the guard.log reader)
Record: docs/decisions/guard-log-read-weekly.md
- Record id and Home say 'weekly' (guard-log-read-weekly) while the title says 'read daily, by a note'; docstring of daily_note.py cites the weekly id for a daily note.
- 'There is no volume check: refusals grew with use, and a count check fired on 6 of 14 real days' sits in the code docstring, not the record (record silent on why).

## md_sweep.py (markdown sweep, retired stub)
Record: docs/decisions/ste-guard-fixes-not-nags.md; mentioned in guard-log-read-weekly.md and predicate-is-the-act.md
- 'Both scripts are deleted' (md_sweep.py is a stub).
- guard-log-read-weekly: the paragraph on STE-fallback/STE-unchecked rows is history for a mechanism that no longer runs.

## stall_watch (background-job watcher and Stop check)
Record: docs/decisions/stall-watch.md (also background-needs-end-note.md, agents-wait-with-monitor.md)
- 'Cost: no new process or timer' (see conflicts).
- 'A polling timer in the session is refused by the waiter guard rule, so the watcher does the waiting' justifies the design with a premise the item 180 now questions.
- wait-pid paragraph: 'Unmeasured: no test pins the cost' and 'three short ps reads per ancestor level ... (unmeasured count)' are admitted gaps against the cost-test requirement.
- 'Incident, 2026-10-31' and 'owner ruling, 2026-10-18 15:15 CDT' history narration inside the ruling.

## wait-pid
Record: docs/decisions/stall-watch.md (bullet 'The one allowed wait on a stranded job')
- 'Unmeasured: a stub adopted by a subreaper ... reads foreign' is an open question inside a ruling.

## verdict (heartbeat and temp logs)
Record: No decision record found for bin/verdict itself; its cost sits in the file header and in docs/decisions/stall-watch.md ('Tools that are quiet by design')
- none found (no record to go stale)

## ci_wake (CI wake after gh pr ready)
Record: docs/decisions/ci-wait-reads-run-status.md (section The CI wake-up)
- 'Batch 649's macOS job went red ...' and 'Measured on batch 663 (2026-10-27)' are incident history inside the ruling.
- '`merge/merge.py`, `block`: no watch. It pauses 30 s.' not re-verified here (inferred still true).

## sim-lease
Record: docs/decisions/sim-lease-tool.md; docstring header of bin/sim-lease
- 'Landed: 2026-11-04' / 'Not covered: a SIGKILL of sim-test ... (debt note sim-test-sigkill-leaves-pro-booted)' is a debt inside a ruling.

## sim_boot_record (PreToolUse snapshot, PostToolUse boot check and record)
Record: docs/decisions/sweep-shuts-down-idle-simulators.md (ruling 1) and sim-boot-is-verified.md
- none verified

## SessionStart refresh child (detached git fetch and pin install)
Record: docs/decisions/merge-reinstalls-from-main.md; cost is stated in README.md (section on the refresh), docs/catalog.md; debt docs/debts/refresh-lock-untested.md
- Debt refresh-lock-untested says a child outliving 10 minutes can remove a newer lock; the record is silent.

## janitor triggers (SessionEnd sweep, SubagentStop reap, daily launchd/schtasks job)
Record: docs/decisions/the-janitor-is-one-machine-wide-sweep.md (Two triggers); janitor/GUIDE.md
- Debt note schtasks-test-not-in-ci is stale (the test runs in three CI jobs).
- 'Banchi keeps its own tier 2 until the owner names its removal' is an open dependency inside the ruling.

## guard.py import-failure wait
Record: docs/decisions/install-hooks-whole.md
- none verified