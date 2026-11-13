# Plan: one direction for watches, wakes, sweeps, reaps and logs

Owner, 2026-11-04 06:50 CST, Cockpit item 180: "align all of these toward one uniform direction as its
currently a patchwork of lessons bugs and fixes and stale prose". The item covers every mechanism that
watches, wakes, sweeps, reaps or logs.

This record holds the model (section 1), the table of mechanisms (section 2), the merges (section 3),
the deletes (section 4), the lanes (section 5) and the owner questions (section 6). Section 6 has one open question, Q6.
This change changes no behaviour. It fixes stale prose in Markdown records and in code comments.

## Method

- **Source.** A read-only mapping named 30 mechanisms. A critic pass read that map and its plan against
  main at 446f2d3d. The critic's corrections are folded in below.
- **Checked on main.** Each row names its reader: a `settings.json` row, a file and line, or a record.
  A claim the check did not reach is marked "unchecked". Unchecked means unknown, not clear or broken.
- **Read on main, hooks.** `settings.json` gives every hook row and timeout. Also `hooks/stall_watch.py`,
  `hooks/ci_wake.py`, `hooks/guard_stream.py`, `hooks/guard_core.py`, `hooks/git_reads.py`,
  `hooks/sendmessage_state.py`, `hooks/question_form.py`, `hooks/mutate_shared.py`, `hooks/decision_watch.py`.
- **Read on main, lint and janitor.** `lint/report_guard.py`,
  `lint/check_hook_stubs.py`; `janitor/sweep.py`, `janitor/session_end_sweep.py`,
  `janitor/install_launchd.py`, `janitor/install_schtasks.py`, `janitor/GUIDE.md`.
- **Read on main, other.** `merge/merge.py`; `bin/ci-job`, `bin/verdict`; `mods/decision-watch/hooks/register.mjs`;
  `.github/workflows/checks.yml`. Also the decision and debt records named in the table.

## 1. The model

Eight rules. A rule becomes a check when a check exists. Until then it is a plain rule.

1. **Events.** A mechanism runs inside a hook or tool process that the harness started, or
   when a person asks. A timer is allowed only when its record shows it costs less than it saves (rule `outcomes-mechanize-rules`; timer ruling `timer-allowed-when-cheaper`). The hook events on main are PreToolUse, PostToolUse,
   PermissionRequest, PermissionDenied, Stop, SubagentStart, SubagentStop, SessionStart, SessionEnd,
   PreCompact, PostCompact and UserPromptSubmit (checked: `settings.json`). Three named exceptions may run on a timer or hold a process: the stall watcher, `ci_wake` and the daily job (Cockpit item 180, pick a, 2026-11-06 12:19 CST). Their home and status are in `.claude/rules/hooks.md`. The stall watcher and `ci_wake` are long-lived, which the root rule does not allow. That is open (step `watchers-plan-lanes`).
2. **Children.** A mechanism starts no process that outlives its hook. A child is short and bounded by the
   hook timeout, such as `git` or `ps`. A model call through `invoke_model` is such a child (Cockpit item 248, pick b; Q2). The stall watcher and `ci_wake` are the named exceptions (Q1a and Q3).
3. **Waiting.** A session waits through the harness's wake: an asyncRewake exit, a PR comment (`ci-done`),
   or `send_later`. It does not wait on a polling process we start. Two mechanisms break this rule today,
   the stall watcher and `ci_wake`. Q1a and Q3 name them as exceptions.
4. **Cost.** Each record states its cost: process starts, files written, and how often (rule `outcomes-mechanize-rules`). Decision `cost-line-pinned` and its checker check each file and count that a Cost line names.
5. **Proof.** One shared test helper proves the stated cost (`hooks/test_support/cost_probe.py`, on lane branch `lane/watcher-cost-tests-main`, not yet on main). It counts child processes, files written and
   sleep passes. The test is the proof. A cost claim with no test is not proven.
6. **Logs.** Each log names its reader in its record. Each log has a size cap. A cap rotates the file. It
   never trims the file, because a trim can remove rows a reader needs (the `crash` lines that
   `daily_note` reads). A log with no reader is not written. Rule `outcomes-mechanize-rules` (each rule
   becomes a hook or check) is the source.
7. **One record per mechanism.** A record holds its ruling, its reader, its test and its cost. It holds no
   history. Superseded text is rewritten in place (rule `speak-rewrite-superseded-in-place`).
8. **Record lint.** A new check fails a mechanism that is listed in `lint/rule_mechanisms.json` when its
   record lacks the lines that rules 4 to 7 need. No `check-records` script is on main (checked by grep).
   This check is new work. It comes last in section 5.

## 2. The table

Columns: the mechanism, what main does (checked), the change, the owner question (Q), and the size (S
small, M medium, L large).

| Mechanism | On main | Change | Q | Size |
|---|---|---|---|---|
| Stall watcher (`hooks/stall_watch.py --watch-pid`) | The hook rewrites each background Bash call to start one python watcher. The watcher loops every 0.2 s (line 278) and runs `ps` about once a second. It exits 3 after a stall (hook command, line 17). | Replace, cap or keep. Do not delete before Q1 is ruled. | 1 | L |
| Stall temp files | The hook exits 3 before `rm -f LOG BEAT`. A stalled job leaves `.log` and `.beat` files (line 17). | Remove them on every exit path. | no | S |
| Stall Stop check (`--stop`) | Lists each quiet job once per crossing: at the first Stop after its stall crossed, against the previous Stop (`stop()`, `scan_jobs`). A job that goes quiet again after new output is listed again. | None. Test `each_stale_job_is_listed_once` holds it. | no | - |
| `wait-pid` (`bin/wait-pid`) | One process per wait. Ownership reads run at start (record `stall-watch`; code unchecked). | Add the cost test. | no | S |
| `ci_wake` (PostToolUse, Bash and PowerShell) | One python per `gh pr ready`. Timeout 3600 s. Reads runs every 30 s, then gaps up to 120 s (checked: `settings.json`; `hooks/ci_wake.py` header). | Keep as a named exception with its cost stated (Q3, decided). Long-lived: open (step `watchers-plan-lanes`). | 3 | M |
| `merge/merge.py` poll loops | Two loops of its own. `retry_net` (line 223) pauses between network retries. `wait_checks` (line 967) pauses through `block` (lines 1223 to 1229): 30 s when a check has an Actions run, else a minute. It also pauses 30 s for a settle read (lines 1017 to 1021). | Share the `gh` call and the pause seam with `ci_wake`. Do not share the loop. | no | M |
| Config watch (`hooks/config_watch.py`, PostToolUse 20 s, Stop 20 s) | Hashes the two watched settings files on each matching call (record `config-watch-fast-exit`). | Add a test that a clean call starts no process. Fix the docstring. | no | S |
| Decision watch | No Stop row runs `decision_watch.py` (checked: `settings.json`). The mod runs in the app (checked: `register.mjs`). Its model call is used by `hooks/reply_judge.py` and `lint/report_guard.py` (checked). | Make the log append-only. Keep the `STOP seen` line: `/dw` reads it. | 5 | M |
| Model-call judges | `call_judge` (PreToolUse on Agent, AskUserQuestion, ArtifactData; 70 s). `prose_judge` (PreToolUse on Edit and Write; 45 s). `reply_judge` (Stop; 25 s). `feedback_guard` (Stop; 60 s). `report_guard` (Stop; 80 s; calls `decision_watch.invoke_model` in its past-ruling check). `local_time` (UserPromptSubmit; 30 s) calls a model for a prompt with the whole word `override` or `opus` (`override.grant_override_ask`, `override.grant_opus_ask`, `hooks/override.py`). Each judge calls a model. `invoke_model` is at `hooks/decision_watch.py` line 678. | One home (`invoke_model`). Costs are in decision `haiku-prompt-hooks` (Q2, decided). | 2 | M |
| Other hooks with no row | `ruling_home` (Stop; 20 s). `reread_check` (Stop 10 s, PreToolUse Read 10 s, PostCompact 10 s). `blind_brief` (PreToolUse on Agent or Task; 10 s). `rm_prompt_answer` (PermissionRequest on Bash; 20 s). `sendmessage_state` (PreToolUse on SendMessage; 50 s; starts a node reader child at line 91 with `start_new_session`). `agent_brief` (SubagentStart; 20 s). `local_time` (SubagentStart 10 s; PostToolUse on ArtifactData 10 s). `refusal_note` (PermissionDenied; 10 s). `precompact_handoff` (PreCompact and Stop, 30 s each; SessionStart and SessionEnd rows, 10 s each). `guard.py` (SubagentStop 20 s; PreToolUse 60 s). `sim_boot_record` (PreToolUse Bash 20 s; PostToolUse 600 s). All checked in `settings.json`. | Add each row to the table. Record each cost in the form of rule 4. | no | M |
| `question_form.py` git child | Starts one long-lived `git cat-file --batch` process (line 1422). | Bound it to the hook timeout, or close it when the call ends. | no | S |
| `bin/ci-job` verdict run | Starts one `verdict` process per job (line 351). | Record it. | no | S |
| `hooks/mutate_shared.py` child | Starts a child with `start_new_session` on POSIX (line 483). The critic found it. The map read this file as CI tooling. | Record its cost. Bound it by time. | no | S |
| `bin/verdict` | Writes a per-run log. Deletes `verdict-*.log` files older than 7 days (lines 8 and 16). No decision record. | Write the record: cost, reader and test. | no | S |
| SessionStart refresh child | Inline SessionStart row (startup and resume; 20 s) starts a detached child. `hooks/session_start.sh` (10 s) runs too (checked: `settings.json`). The lock gap is in debt `refresh-lock-untested`. | Move its cost into record `merge-reinstalls-from-main`. Add the lock test. | no | S |
| `daily_note` (SessionStart, startup; 10 s) | One python per startup. The record names no cost test. Rule 5 needs one. | Add a "no process" test. Keep the slug. | no | S |
| Waiter guard (`hooks/guard_stream.py`) | In-process. Starts no child. Its remedy names the CI-wake notice or Monitor (checked: `WAITER_REASON`, line 248). | Record its cost. | no | S |
| SessionEnd sweep | `janitor/session_end_sweep.py` runs `sweep.py <root> --confirm` on one repository. Timeout 55 s. Its output goes to DEVNULL (checked: lines 255 to 257). The record says the hook sweeps one repository. The run also scans every process (`sweep.py` line 1436) and lists simulators (line 1787). | Q4. | 4 | M |
| Daily job (launchd and schtasks) | A timer by design. The installers write the job and load nothing (checked: `install_launchd.py` prints the load command; it calls no `launchctl`). Logs go to `launchd-sweep.log` and `launchd-sweep.err.log`. `hooks/daily_note.py` reads the error log. | Q4. | 4 | S |
| Idle simulator tier | Lists devices and runs `xcrun simctl shutdown` under `--confirm` (checked: `sweep.py` lines 1787 and 1906). The guard `simulator-boot-cap` refuses at two booted devices (record `sweep-shuts-down-idle-simulators`; code unchecked). | Q4. | 4 | S |
| Agent-end reap | Runs on SubagentStop, timeout 60 s (checked: `settings.json`). Its build pass deletes trash in a detached child. That child has no time bound (record `build-dirs-reaped-at-agent-end`; the bound is unchecked). | Bound the child by time. State the cost. Split the record by stage. | no | M |
| Agent-end payload log | Written under a lock file, capped at 200 rows. Its reader is `hooks/daily_note.py` (`agent_end_failures`) (record `agent-end-reap-stops-what-a-finished-agent-left`). | None. | no | none |
| Repo reaper (npm `reap:worktrees`) | Removed. The sweep ignores a repository's `reap:worktrees` script (`janitor/test_sweep.py`). | None. Q7 is decided. | no | none |
| `install_schtasks.resolve_primary_checkout` | `janitor/install_schtasks.py` keeps a local copy. `install_launchd.py` calls `guard.primary_checkout`. | Both installers call `guard.primary_checkout`. This is code work for a builder. | no | S |
| `sim-lease` (`bin/sim-lease`) | A 2 s poll inside `take` (from the map; unchecked). | Keep it. Add a cost test. Fix the docstring. | no | S |
| `sim_boot_record` | Its cost is not stated (rows are in the table above). | Record the cost. | no | S |
| `guard.log` writer | `hooks/guard_core.py` `record()` writes one line per refusal, ask or note. It is called from `refuse()` (checked). No file cap is found by grep. `daily_note` reads its `crash` lines. | Add a rotating cap, never a trim. Record the cost. | no | S |
| `machine-load-brake` | Its record states the cost, names the test and lists the zero children and zero files (checked: record `machine-load-brake`). | None. Copy its form for the other records. | no | none |
| Guard import wait | A 5 s sleep on import failure only (from the map; unchecked). | None. | no | none |

## 3. Merges

- **One cost statement per record, and one test helper.** Today the cost sits in code docstrings, READMEs
  and records. Item 180 fixes the form. Then one helper proves it (rule 5).
- **Stall watch is one mechanism.** The wrapper and the watcher share one record, `stall-watch`. The map
  listed them twice.
- **`ci_wake` and `merge/merge.py` share the `gh` call and the pause seam.** They do not share the loop.
  `merge.py` has two loops of its own.
- **Process scans.** One process scan per session end, not two (inferred from the map; unchecked). Q4
  decides where the scan runs.
- **Agent-end reap.** One record for the reap and its payload log. The process tiers keep their own record,
  `unattended-sweep-stops-proven-orphans`.
- **Load definitions.** The guard reads memory and disk. `sim-lease` reads `vm.loadavg`. Q6 is open. Owner items 304 and 309 picked one shared definition, memory and disk only (rulings `load-def-shared-304a` and `load-def-memory-disk-309a`). `hooks/guard_load.py` is not on main.

## 4. Deletes

Nothing here is deleted before its owner question is ruled. Each delete names its reader check.

- **`STOP seen` line in `shadow.log`.** `mods/decision-watch/hooks/register.mjs` line 81 writes it. Line 358
  counts it for `/dw`. It is the only live evidence that the mod fires, and the record says no live read
  has happened. Kept: `/dw` reads it, so it has a reader (Q5, ruling `watchers-log-reader-249b`).
- **`janitor-runs.jsonl`.** `janitor/sweep.py` line 2238 writes it. A reader exists: `read_last_runs` in the same file (Q5, ruling `watchers-log-reader-249b`).
- **Loose-process tier in the hook run.** It reports only. The hook sends its output to DEVNULL (line 257).
  So the run has no reader for it. The SessionEnd run skips it (decision `the-janitor-is-one-machine-wide-sweep`). Its scan cost is unchecked. Q4 is decided.
- **Stall watcher.** Kept (Q1a, decided). Not a delete.

## 5. Lanes, smallest first

1. **Text only (this change).** Fix stale prose in the decision records, debts, `docs/*.md` and
   `janitor/GUIDE.md`. Size S. It needs no owner answer.
2. **Cost tests for the cheap mechanisms.** One shared helper, `hooks/test_support/cost_probe.py`, on lane branch `lane/watcher-cost-tests-main`. Size S.
3. **Stall defects.** Remove the temp files on every exit path. Dedupe the Stop message. Size S. The
   watcher stays until Q1 is ruled.
4. **Log readers.** Name a reader for each log, with no delete (Q5, ruling `watchers-log-reader-249b`). Size S.
5. **SessionEnd scope.** The SessionEnd half of Q4 (ruling `watchers-sessionend-250a`). Size M.
6. **Decision watch log.** Append-only. Any skip on a quiet turn uses the same protected-path set as
   `--emit-prompt`, so a protected change is still judged. Size M.
7. **Agent-end reap.** Bound the delete child by time. One process scan per session end. Size M.
8. **Record lint.** The check for rules 4 to 8. Size M.
9. **Stall watcher and `ci_wake`.** Replace or cap, per Q1 and Q3. Size L.

Lane 1 needs no answer. A lane that waits on a question says so in its report.

## 6. Owner questions

**Status: Q1a to Q5 decided, Q6 open, Q7 decided.** Q1a, Q1b, Q3 and the daily-timer half of Q4 decide on Cockpit item 180, pick a (2026-11-06 12:19 CST). Q2 decides on item 248, pick b (same time). The SessionEnd half of Q4 and Q5 decide on rulings `watchers-sessionend-250a` and `watchers-log-reader-249b`, whose answer times are not on record. Open, not decided: whether a long-lived watch fits the root rule (rule 1; step `watchers-plan-lanes`). Q7 (repo reaper) is decided by an earlier ruling, and the reaper is removed.

**Q1a. Stall watcher. Decided:** keep it as a named exception, with its cost stated and pinned by `hooks/test_stall_watch.py` (class `CostTests`). Its lifetime is open (rule 1).

**Q1b. A wake for an idle session. Decided:** keep the watcher's wake (Cockpit item 180, pick a). For a stalled background job, only the watcher's exit-3 report wakes an idle session. The Stop check runs at the end of a turn and repeats at every Stop. An idle session has no Stop. `ci_wake` also wakes an idle session, but only for CI results.

**Q2. Model-call hooks under the no-new-process rule. Decided:** they count under rule 2, as children inside a hook budget. All six stay command hooks, each with its cost stated. The move to a prompt hook is re-checked on three triggers (Cockpit item 248, pick b, 2026-11-06 12:19 CST). Home: decision `haiku-prompt-hooks`.

**Q3. `ci_wake`. Decided:** a named exception, with its cost stated (Cockpit item 180, pick a). Its lifetime is open (rule 1). Home: decision `ci-wait-reads-run-status`.

**Q4. SessionEnd scope and the daily timer. Decided.** The daily timer is a named exception, with its cost stated (Cockpit item 180, pick a). The SessionEnd half is ruling `watchers-sessionend-250a`: one repository at SessionEnd, machine-wide only in the daily job (Cockpit item 250, pick a). The answer time is not on record. Home: decision `the-janitor-is-one-machine-wide-sweep`. Lane 5 carries the change. The record says the hook sweeps one repository, and the code also scans every process and lists simulators.

**Q5. Logs with no reader. Decided** by ruling `watchers-log-reader-249b` (Cockpit item 249, pick b: "Name a reader for each"). The answer time is not on record. Each log gets a named reader in its record, and none is deleted. `hooks/daily_note.py` reads the agent-end payload log and the launchd error log. Keep `guard.log`, with a rotating cap.

**Q6. Load definition. Open.** Owner items 304 and 309 picked a: "One shared definition" (ruling `load-def-shared-304a`, 2026-11-06 15:24 CST) and "Memory and disk only" (ruling `load-def-memory-disk-309a`, 2026-11-06 15:45 CST). Ruling `sims-load-brake-only` (2026-11-12 21:59 CST) does not supersede 309a as written. Its supersedes field names only the 2026-11-02 ruling on the 18 Pro. It names the load brake as the only limit on simulator count, so it leans on the load definition without changing it. 309a stays open. `sim-lease` already states its own definition.

**Q7. Repo reaper. Decided and done.** The rule says the sweep never runs code a repository supplies.
Decision uniform-over-variants (a shared tool never grows a per-repo exception; owner, 2026-10-27 12:51
CDT) rules out the npm reaper as a per-repo exception. The reaper is removed, and the rule has no
exception.

## 7. Stale prose left open

One line each, with the reason the text stays.

- stall-watch: "no test pins the cost" (wait-pid). An honest admission. True now.
- stall-watch: "a builder's choice, not measured" (300 s age). Unmeasured, not false.
- stall-watch: the heading premise "the watcher does the waiting" and the waiter-rule argument. Item 180 keeps the watcher, so they stay true.
- stall-watch: incident 2026-10-31 and ruling 2026-10-18 15:15 CDT inside the ruling. The reasons still hold. Not superseded.
- stall-watch (wait-pid): the subreaper "reads foreign" line. An open question, unmeasured.
- stall-watch (wait-pid): the inline statement "one process per wait". True as written. Unmeasured: no test pins its cost.
- ci-wait: the cost line is written, under "The CI wake-up".
- ci-wait: "owner, 2026-10-21, back-off" is date-only. The code cannot re-derive it. Not false.
- ci-wait: `ci_wake.py` header matches the record. No stale text.
- agents-wait: remedy names the CI-wake notice or Monitor. Checked true (`WAITER_REASON`, `hooks/guard_stream.py` line 248).
- decision-watch: marketplace copy of sec-default. Unchecked, unmeasured.
- decision-watch.py docstring ("Replaces the type: agent guardrail", "old markdown sweep"). Fixed in this change.
- config-watch.py docstring (history words: "used to", "now", "version on main"). Fixed in this change.
- daily_note.py docstring: volume figure dropped in this change. The weekly id stays, because a slug never changes.
- daily_note: precompact-handoff item 12. Not read.
- agent-end reap: "The sweep takes the deepest checkout" names `sweep.py`. True. The Home is the reaper by design.
- janitor: "Banchi keeps its own tier 2". A child repo. Not checkable here.
- janitor: "Each new rule gets a row in rule_mechanisms.json". Unmeasured.
- GUIDE: "runs against every repository" omits roots detail. The GUIDE covers roots later.
- idle simulators, ruling 3 (simulator-boot-cap). Lives in `hooks/guard.py`. Unverified here.
- session-end record: "owner ask, undated" constant. An undated owner ask. Cannot be dated.
- session-end record title: already says armed. The file name keeps "disarmed" by design. No change.
- `session_end_sweep.py` comment on the Windows job. Checked true (`checks-windows-sweep` runs the sweep and mutation suites).
- `install_schtasks.py` docstring named a missing `install_launchd` function. Fixed in this change.
- daily installers: "the job is loaded on any machine". Unmeasured.
- machine-load-brake: "the memory level is a placeholder" (85 and 95 %). Unmeasured.
- machine-load-brake: the opening paragraph lists five dated rulings. These are citations the outcomes rule needs. Kept.
- verdict: no decision record. Nothing stale to fix.
- sim-lease: a debt pointer inside the ruling. A pointer, not false.
- sim_boot_record: "none verified". No stale claim found.
- SessionStart refresh child: cost text in README and the catalog. Unchecked here.
- Mutation test and end-to-end scripts: no dedicated record. A gap, not stale text.
- guard.py import-failure wait: no stale text in the input list.
