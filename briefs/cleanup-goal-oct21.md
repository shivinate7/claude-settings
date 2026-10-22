# Goal: finish the cleanup phase of claude-settings, batch by batch

Paste this whole file to one claude-settings session with `/goal finish this end to end`.
Written by the advisor, Oct 21, against main 73ed71a and batch #552 (still running).
Work in plain order. Each batch below is its own integration PR, under the usual rules
(git-integration-branch-merge, roles-review-cap-three). Expect about 20 hours of work.

## 0. First, before any work

1. Save this file as `~/.claude/handoffs/goal-cleanup-oct21.md`. Put that path on the
   Goal line of your handoff. After every compaction, read it again before you act.
2. Check each "checked at" fact below against current main. Other work merges in between.
   A fact that no longer holds: re-plan that lane, and say so in the report.
3. One integration PR at a time, but never wait idle. While a batch's CI runs, build and
   review the next batch's lanes as drafts (drafts skip CI). When the batch merges, open the
   next integration PR at once. Run lanes one or two at a time, since the Windows machine is
   short on memory. Once batch 4 (load brake) lands, its reading sets how many lanes may run.
   CI runs once per batch, on the integration PR; do not add runs, and do not skip one.

## Handoff rules for this goal (it will compact many times)

Your handoff (`~/.claude/handoffs/<session_id>.md`) must always hold these, current, not as a log:

- **Goal:** the path above, and the batch you are in, by number and plain name.
- **State:** each open lane and PR with its plain name (for example "#560, decision watch
  on turn.complete"), its branch, its last CI head and verdict.
- **Owner rulings this goal received:** one line each, with the record it now lives in.
- **Open questions to the owner,** and what you do meanwhile.
- **Next action:** the one command or step you take next.
- **Working premises,** each with its source: ruling, measured, read (file and commit),
  or notes. Before you act on a "notes" premise after a compaction, check it.

Update the handoff on events, not only at the token nudges: a lane done, a PR merged,
a CI verdict, an owner ruling, a premise that turned out wrong. Small edits.

After a compaction: read this file, then the handoff, then run `git fetch` and
`gh pr list --state open`, and confirm the handoff's State against what GitHub shows.
Trust GitHub over the handoff, and fix the handoff when they differ.

## Stop points (the only places you wait for the owner)

Bring each as one question with options and a pick. While you wait, carry on with the
next batch that does not depend on the answer.

- Batch 6, lane 1: if agent hooks do not work, stop before the other lanes.
- Batch 8 (guard cull): the list of rules to delete, before any deletion.
- Batch 9 (STE draft): the draft itself, before any build.
- Batch 10 (kill guard): needs the owner's Mac. On Windows, park it and say so.

## Batch 0. Finish what is running

- #552 (hook imports, fewer process starts, Windows installer and rm shim: c18, c19, c22)
  merges on green. Then each lane PR it replaced closes as replaced.
- Then the c22 cleanup the owner's brief listed: delete ~/.claude/bin/rm and the
  "# claude-settings: ~/.claude/bin on PATH" block in ~/.bashrc on Windows; check
  ~/.claude/claude-settings-install.log for install.sh runs; report anything install.sh
  replaced that install.ps1 would not have made. Give the owner one PowerShell block to
  re-run the memory monitor (tools/mem-monitor.ps1); do not run it yourself.

## Batch 1. The decision watch runs again (c29), plus #549

Found Oct 21: the app's own sec-default mod sends every classic.* event past user-tier
mods (its hooks/register.ts line 24), so decision-watch, which listens only on
classic.Stop, has never run on Windows. No shadow.log exists.

- Lane: #549 (decision-watch finds Python once, version 0.0.6) joins first.
- Lane: move decision-watch from classic.Stop to turn.complete. Skip turns with
  e.agentId set (subagent turns), as session-board does. Use the session id the mod keeps
  from session.start, and find the transcript the way /dw does, since turn.complete has no
  transcript path. One judge at a time, never block the turn. Drop the stop_hook_active
  skip. Tests: a main turn starts a judge; a subagent turn does not; classic.Stop no longer
  does. Bump the mod version again.
- Live proof on Windows: a "seen" line lands in shadow.log after one real turn.
- Rewrite decision decision-watch-mod-limits in place. Close debt dw-stop-row-unproven
  with the sec-default finding. No Stop hook row comes back.

## Batch 2. Rule text (c10, l1, c26, c28, c30, c20)

All edit CLAUDE.md, the output style, docs/records.md or lint/. One batch, one lane each.

- **c10 and l1:** paste-in brief A below (the guard-rule brief), lanes 1 and 2. Do not
  delete any guard rule in this batch.
- **c26, watching costs less than what it watches.** Amend an existing CLAUDE.md rule in
  place if one fits: any tracking, logging, monitoring or measuring must read on demand
  inside a process that is already running (never on a timer or on every tool call), start
  no new long-lived process, state its cost in its record (process starts, files written,
  how often), and carry a test that proves that cost. A log needs a named reader or it is
  not written.
- **c28, a step left to the owner comes as a command the owner can run.** Amend
  output-never-hand-off-doable-step in output-styles/shiv-stylisms.md in place: each
  command left to the owner is its own fenced block, ready to run as is (starts with its cd,
  no blanks, no admin). On Windows a block to paste into a terminal is PowerShell (5.1-safe);
  a Git Bash block says "open Git Bash" on its first line; a Mac block is bash or zsh;
  never mix shells in one block. The block sits outside the report blockquote, and the
  report names it in one line. Add a check to reply_judge.py (already runs at Stop): a reply
  that hands the owner a step with no code block is flagged. Test, red on main.
- **c30, a red batch run gets its fix or drop pushed at once.** In git-integration-branch-merge
  (CLAUDE.md line 56 at 73ed71a), make two changes in place, no new rule.
  (1) Replace "Never push to a ready PR while its CI runs" with: "Never push to a ready PR
  while its CI run can still go green. Once a job is red, push the lane drop or the lane fix
  at once; the push cancels the old run, and the new run is the re-run."
  (2) Add: a red check is fixed in its lane and the lane re-merged, instead of dropped, when
  all hold: the fix is a few lines in the failing lane's own files; the failing check is about
  form (record format, version bump, lint), not a behaviour test; it is the lane's first such
  fix in this batch (a second red drops it); the fix goes on the lane branch, never in the
  batch branch. A lane red on a behaviour test is dropped as today, with any lane that
  depends on it. Reasons: a red run cannot merge, so waiting only delays the re-run; dropping
  a chain of lanes for a one-line form fix costs a batch cycle for nothing (owner, Oct 21).
  No guard.
- **c20, every id comes with a plain name.** Rewrite speak-cite-id-plus-gloss (CLAUDE.md
  line 89 at 5553dc6) in place so it covers every id the owner would have to look up:
  decision and debt ids, roadmap step ids, lane numbers, PR and issue numbers, commit
  hashes, rule anchors, hook and script names. Each gets a short plain name the first time
  it appears. Add: a numbered id carries no order, so state the work order in words. Update
  its row in lint/rule_mechanisms.json and the compliance-check probe ("Speak plainly" in
  skills/compliance-check/probes.md). Also delete branch batch-map on origin (adds nothing
  over main; check first).
- Report the before and after text of each rule, and the word change for CLAUDE.md.

## Batch 3. Standard lint in CI only (c21)

Add a [tool.ruff] config with select = ["F", "E9"], skills/impeccable excluded. Fix the
findings (12 at 5553dc6: 11 unused imports, 1 f-string; recount). Add ruff check and
ShellCheck (severity warning, on every *.sh) as failing steps in gates.yml. Fix or suppress
each ShellCheck finding with a one-line reason. No format step, no pre-commit hook, no
Claude Code hook.

## Batch 4. Machine-load brake (c14)

Owner rulings, Oct 21: it applies on every device that installs claude-settings, covers
storage as well as CPU and memory, must judge accurately, and must cost less than the
problem: no watcher, no timer, no per-tool-call reading, no log of its own.

- Where: inside guard.py, which already runs on Agent, Task, Workflow and start_session
  calls. Only those calls read the load.
- What: memory (Windows GlobalMemoryStatusEx; Mac kern.memorystatus_level), disk
  (shutil.disk_usage on the home drive), CPU (Mac os.getloadavg; Windows two
  GetSystemTimes reads 200 ms apart). No claude process count (owner ruling, Oct 22: no
  fixed count; 31 ran on Windows, 14 app helpers and 17 CLI). All through ctypes, no child
  process, no file written. Memory and disk decide, as shares of the machine's own capacity;
  CPU is secondary.
- Levels (placeholders): busy when memory is over 85%, disk free under 15%, or CPU over 85%;
  full when memory is over 95% or disk free under 5%. The refusal names the reading and
  says to run the lane in the foreground. Any read error counts as normal.
- Busy keeps no lane count (Oct 22): it refuses a background spawn (an Agent or Task call
  with run_in_background true, or one that omits it if background is the default; check that
  default in this version) and any Workflow, and allows a foreground spawn. A foreground
  spawn makes the session wait, so lanes run one at a time. Full refuses every new lane.
- Tests: on the Windows and Mac runners each reading matches the OS's own tool within a
  tolerance; the lane-start path starts zero child processes and takes under about 300 ms;
  busy refuses a background Agent, an Agent that omits the setting, and a Workflow; busy
  allows a foreground Agent; normal allows all; full refuses all; each red on main.
- Record it as a decision with its cost, per c26.

## Batch 5. Opus on the owner's word, and override takes words (c17, lanes 1 and 3)

Paste-in brief B below. Lane 2 is done (#544). First check lanes 1 and 3 against main.

## Batch 6. Premises batch (c7, c24, c25)

Paste-in brief C below, with the plan in Appendix 1. Lane 1 (probe agent hooks) runs first
and alone; it is a stop point if agent hooks fail.

## Batch 7. Janitor sweep fast on big repos (c16)

janitor/sweep.py and session_end_sweep.py import the whole guard family at start; each
worktree is proven safe by up to three separate git calls. Batch the git calls (one
for-each-ref and one merged-into-main list for all branches; cherry only for what the
batch cannot prove), drop the guard import (move the few helpers into a small module),
and add a fast mode that only reaps worktrees whose branch is already in main. A worktree it
cannot prove safe is kept: less checking must fail toward keeping, never toward deleting.
No timing step (owner: no measuring steps); prove it with tests, including a count of git
calls per sweep, before and after, from the code path.

## Batch 8. Cull the guard (c23)

Run `lint/guard_log_report.py --all-rules --days all` (from batch 2) on this machine.
List each guard rule that never fired since it landed and whose record names no incident,
with its code and tests. Stop point: bring that list to the owner. Delete only what the
owner approves, with code and tests, under the net-value review. Also list the
remember-guards that filing a ruling at once (o5b) would replace, as candidates only.

## Batch 9. STE rules become outcomes (c15), draft only

Draft, do not build: for each of the five blocking STE codes (STE001 sentence over 30 words,
STE011 bloat, STE013 double negative, STE020 label over 4 words, STE021 UI escape comment),
the outcome it was for, whether a CI check on changed files, a judge, or nothing should
carry it, and what ste_gate becomes. Direction the owner agreed Oct 20: stop blocking at edit
time. Include the word and line change. Stop point: bring the draft.

## Batch 10. Kill guard knows a lane's left-behind server (c27), Mac only

Paste-in brief D below. Its first check needs the owner's Mac. On Windows, park it and say so.

## When the goal is done

Report per batch, in the usual format. Then list: each owner ruling with its home; each debt
opened or closed; anything parked and why; and the four size numbers on main (decisions,
debt files, hook lines, CLAUDE.md words) before and after.

## Paste-in brief A: guard rule and fire counts (c10, l1)

Guard rule amendment and fire counts, claude-settings. Roadmap: c10 (the guard rule, amended) and l1 (track guard refusals per session). This prepares c23 (cull the guard itself), which is not part of this brief. Make it its own small batch after the one running now (the hook import, process-start and Windows lanes), because it touches CLAUDE.md and lint/, and those lanes are already editing files near them. No measuring step; prove each change with a test.

Owner's ruling, Oct 21: let the guard grow while things change, then cull what never proved itself. No freeze was ever in force. The current rule stays and gets wider.

Lane 1, amend building-guard-needs-incident in place. CLAUDE.md, around line 82: "Build a new guard or gate rule only against a named incident or a measured risk. Cite it in the rule's record." Rewrite it in place, as one rule with no new section, to say:
- A new guard or gate rule may land for a named incident, a measured risk, or a likely risk (likely to hit in normal work, the same bar debts use).
- Its record says which of the three it is, and the date the rule landed.
- At each cull, a guard rule that never fired in guard.log since it landed, and whose record names no incident, is deleted with its code and tests.
Update the rule's row in docs/records.md (line 77) and in lint/rule_mechanisms.json, whose reason text names only "a named incident or measured risk". Record the ruling in place under decisions/ if a decision holds this rule; otherwise in the rule's record. One-line reason: "grow while things change, then cull what never fired (owner, Oct 21)". Report the rule text before and after, and the word change.

Lane 2, rules that never fired show up. lint/guard_log_report.py already prints deny, ask and noted counts per rule from guard.log, and guard.log is never pruned. The gap: a rule that never fired has no line, so it never appears, and those are exactly the rules a cull is looking for. Add a flag (for example --all-rules) that lists every rule id the guard and the gates can emit, each with its counts, including 0, plus the date of the rule's first guard.log line (or "never"). Take the rule ids from their one home in the code, not a copied list (rule building-allow-list-is-the-constant). Let --days take "all" for the whole log. Tests: a rule with no lines shows 0 and "never"; a rule with lines shows its counts and first date; the list matches the constant, red on main and green on the fix.

Do not delete any guard rule in this batch. That is c23, the guard cull, after this lands.

Report: per lane, what changed and the test that proves it; the rule text before and after; and one run of the new report on this machine with --all-rules --days all, pasted in full, so the cull can start from it.

## Paste-in brief B: Opus on the owner's word (c17)

Opus on your word, claude-settings. Goal: when the owner wants Opus for a spawn, it runs, with no magic words; Claude never picks Opus on its own; no new model calls.

Today: the type: prompt PreToolUse judge on Agent refuses an audit Explore spawn unless model is sonnet, so it refuses Opus too, against decision subagent-model-cap ("any other spawn runs Opus only when the owner names it"). It sees only the tool call, so the owner's word and the override pass can never reach it.

Lane 1, the ceiling moves to the guard. guard.py already runs on Agent and Task calls. When a spawn sets model opus and no standing word covers it (Plan; builder try 3; reviewer round 3 is not standing), the guard answers "ask" under rule subagent-model-cap, the same way it already asks on a settings write. The owner approves or declines in the prompt. An override pass lifts it like any other ask. Test: a spawn with model opus gets an ask; Plan with opus and a spawn with sonnet or haiku pass; red on main, green on the fix.

Lane 2, the judge keeps only the floor. DONE Oct 21 in PR #544 (the Agent judge accepts Opus); do not redo it, check lanes 1 and 3 against main first. In the Agent prompt judge, the Explore clause blocks only an audit or judging brief that sets model haiku or no model. Opus and Sonnet pass the judge; the guard owns the ceiling.

Lane 3, override takes words. In hooks/override_pass.py, a prompt that starts with the word override grants the pass, and the rest of the prompt is the reason, written to guard.log. So "override: use opus for that one review agent" grants a once pass. "override 15m", "override 2h" and "override off" keep their meaning when they are the whole prompt. A prompt that only mentions override later in a sentence grants nothing. Update the decision owner-override-pass in place.

First check: does a hook "ask" show a prompt to the owner in bypass mode? The guard already relies on it for settings writes, so confirm with that existing case. Report the before and after judge text and the tests.

## Paste-in brief C: premises batch (c7, c24, c25)

Premises batch, claude-settings. Roadmap: c7 (fix the reply-style conflict: one question reviewer), c24 (planners check their brief's premises), c25 (handoffs list premises with sources, evidence lives in its record). Attach plans/premise-handoffs-plan.md with this brief; it is the design, with file and line references checked at 73ed71a7. Re-check each reference against current main before editing, since other batches have merged since.

Order: after the guard-rule batch (c10, let the guard grow then cull what never fired; l1, rules that never fired show up) lands. Fixes and tests only; no measuring step.

Owner's rulings, Oct 21 (all four open questions in the plan, answered A):
1. Premises show inside the question box: one to three short "Based on:" lines in plain words, each with its source kind.
2. Drop the code check for the Goal and Problem lines; the question reviewer judges form too.
3. The question reviewer runs on Opus by a standing class-level word, recorded in decision subagent-model-cap (like the audit Explore word of 2026-10-21).
4. Raw evidence lives inside the decision or debt that uses it, in an Evidence section of about 10 lines, deleted with that record. Add that one clause to decision cull-rules in place.

Lanes, as in the plan's section 5:
1. Probe agent hooks first, alone. Report which of the plan's checks hold. If agent hooks do not work, stop and report before any other lane; the fallback (the session spawns the reviewer itself) costs about five processes per question on Windows and needs the owner's word.
2 and 3. The premise section in the handoff and the premise format's one home (same files: one builder, or 3 after 2).
4. The question reviewer: agents/question-reviewer.md with model opus pinned, one agent hook on AskUserQuestion.
5. Delete the old judges (the AskUserQuestion prompt hook and hooks/question_outcome.py, with their tests, decisions and references). Needs 4 merged.
6. The planner duty in agents/plan.md: premises first, checked against decisions/ and recent rulings. Can run beside 2 to 4.
7. The evidence clause in cull-rules (wording only).
8. Handoff cadence (owner's ruling, Oct 21). (a) The Stop nudges to rewrite the handoff move from fixed token counts (200k, 350k, 450k, precompact_handoff.py) to fractions of autoCompactWindow, about 40, 70 and 90 percent, so they still fire if the window is lowered. Test: with the window set to 250k, all three nudges fire; red on main. (b) hooks/precompact_handoff_prompt.md gains a rule: also update the handoff with a small edit when something happens (an owner ruling, a finished step, a test result that changes what fails); the token nudges stay as the backstop. Shares files with lane 2: same builder, or after it. (c) The PreCompact digest (precompact_handoff.py, state/handoff/<sid>.digest.md) keeps every owner message word for word, not only the last 60,000 characters, with long pastes cut to their first lines and marked as cut. Digest file only; nothing new loads into context. Test: an owner message from early in a long transcript is in the digest verbatim, and a long paste is cut; red on main.

Each lane: a test red on main and green on the fix, as the plan lists. Record each ruling in place under decisions/.

Report: per lane, what changed and the test that proves it; lane 1's findings in full; the net hook processes per question on Windows, before and after, counted from settings.json; and the four size numbers on main.

## Paste-in brief D: kill guard (c27)

Kill guard knows a lane's left-behind server, claude-settings. Goal: a session can stop, by pid, a test server that one of its own lane agents started, after that agent ended, on Mac. A process this session did not start stays refused. No new per-call cost.

Today, checked at 73ed71a: hooks/guard_kill.py foreign_pid_kill allows a kill by pid only when the parent chain reaches this session's claude process. When an agent ends, macOS hands its server to init (PPID 1), so the guard calls it foreign. The one exception, in_own_agent_worktree, needs the cwd inside .claude/worktrees/agent-<id> AND <session>/subagents/agent-<id>.jsonl. Lane agents work in scratchpad folders, and workflow agents keep their records under subagents/workflows/, so it never matches them. Decision a-kill-by-pid-needs-an-owned-pid lists this as a known limit.

First check, before any code: on the owner's Mac, start `sleep 600 &` from a Bash call inside a subagent, let the subagent end, and confirm three things. (1) The sleep's PPID is 1. (2) Its environment holds CLAUDE_CODE_SESSION_ID equal to the hook payload's session_id. Read it the way lane 1 will. (3) Where the subagent's record landed under subagents/. If (2) fails, stop and report; do not fall back to path rules.

Lane 1, ownership by inherited tag. In guard_kill.py add one check beside in_own_agent_worktree: a pid is owned when its PPID is 1 and its environment holds CLAUDE_CODE_SESSION_ID exactly equal to this session's id (session_id_of, from the payload). Read the environment without a child process where you can: Linux /proc/<pid>/environ; Mac sysctl KERN_PROCARGS2 through ctypes, which returns argv and env separately, so a matching string in argv does not count. Match a whole NAME=value entry, never a substring. Any read failure means foreign. Read it only on the path that already found the pid foreign, so an allowed kill costs nothing new. Keep the worktree exception. Windows stays as today (unknown, allowed).

Lane 2, the reaper uses the same test. janitor/agent_end_reap.py only looks under .claude/worktrees/agent-<id>, so a scratchpad lane's server runs until a full sweep. On SubagentStop, also stop each orphaned process whose environment holds this session's id and whose cwd sits in this session's scratchpad, with the reaper's other reads unchanged. If one shared helper serves both files, give it one home (shared module) and import it from both.

Lane 3, one brief line. Wherever the lane brief template lives, add: a lane stops each server it started before it ends, by $! from the same call or through the harness.

Tests, red on main and green on the fix: a PPID-1 process carrying this session's id is allowed; the same process carrying another session's id is denied; one with no tag is denied; one whose argv, not env, holds the id is denied; pids 0, 1, -1 stay denied. Add a mutant in hooks/mutate_guard.py that drops the exact-match check, and show a test kills it. Update the decision a-kill-by-pid-needs-an-owned-pid in place: one dated owner line, Oct 21, and fix the Limits list.

Overlap: PR #557 (refuse a recursive delete of a parent folder) edits hooks/guard.py, delete section only. This work should not need guard.py; if it does, rebase on #557 first.

Report: the first-check results, the diff size per file, test names, and the decision's before and after text.

## Appendix 1: premise handoffs plan (for brief C)

# Plan: premises that travel with their sources

Repo: shivinate7/claude-settings, main at 73ed71a7 (after PR #544). Planning only. Nothing in the repo was changed.
Roadmap steps covered:
- **c25, "premises in the handoff"**: handoffs carry the facts a session leans on, each with its source, plus one home for raw evidence.
- **c7, "fix the reply-style conflict"**: here, the part that decides who reviews a question before the owner sees it.
- **c24, "planners check their premises"**: the Plan agent and the orchestrator check a brief's premises before they plan.

c24 and c25 are not in the roadmap backup of 2026-10-21 (`/mnt/project-files/roadmap-backup-2026-10-21/steps/`). Their wording here comes from the brief only.

**What the plan does.** It sets one way to write down a "premise": a fact the work assumes, with where it came from. Handoffs, questions and plans all use it. A fact is trusted only as far as its source. A weak source is re-checked before anyone acts on it.

---

## 1. What exists today (checked at 73ed71a7)

### Handoffs and compaction

| Piece | Where | What it does |
|---|---|---|
| Auto-compaction | `settings.json:463` `"autoCompactWindow": 500000` | Compacts at 500k tokens. |
| Nudge at checkpoints | `settings.json:89` (Stop, `precompact_handoff.py --nudge`); code `hooks/precompact_handoff.py:461-509` | Blocks a turn end once at 200k, 350k and 450k tokens. Tells the session to rewrite its handoff. The section list is copied into the reason text (`:501-506`). |
| Digest before compaction | `settings.json:128` (PreCompact); `precompact_handoff.py:166-195` | Saves the last 60,000 chars of user and assistant text to `state/handoff/<sid>.digest.md`. No model call. |
| Reorient after compaction | `settings.json:140` (SessionStart `compact`); `precompact_handoff.py:408-435` | Prints: follow the prompt file, rewrite the handoff whole, use the summary, the digest and the old handoff. Adds open feedback ids (`:371-395`). |
| Reorient after /clear or fork | `settings.json:150`, `:201`; `precompact_handoff.py:245-265`, `:337-368` | Names the earlier session's handoff for the same folder. |
| Re-read check | `settings.json:416` (PostCompact), `:329` (PreToolUse Read), `:117` (Stop); `hooks/reread_check.py:55-68` | Sets a flag after compaction. A Read of the handoff clears it. While the flag is set, Stop blocks once per turn. |
| Feedback gate | `settings.json:108`; `hooks/feedback_gate.py:75-90` | Blocks a turn end when an open feedback id (`fb-...`) is missing from the handoff. It matches whole tokens, so a new section does not break it. |
| The prompt the session follows | `hooks/precompact_handoff_prompt.md:28-45` | Step 4 lists the sections: rulings with NO HOME YET, where things stand, rulings with homes, work in flight, next steps, files and commands. **It has no section for facts or their sources.** |
| The ruling | `decisions/precompact-handoff.md` items 1-9 | Handoff is per session, outside git (`~/.claude/handoffs/<sid>.md`), rewritten whole, never appended. No hook calls a model (item 4). |
| CLAUDE.md | `CLAUDE.md:75-76` (`tokens-compacting-keep-essentials`), `:103-106` (Compact instructions) | Keep files, commands, ruling homes, server pid and port. The handoff contents live in prompt step 4. |
| Tests | `hooks/test_precompact_handoff.py` (17 cases, e.g. `case_reorient_ok_names_prompt_and_digest` at :282, `case_nudge` at :418); `hooks/test_handoff_wave2.py` (24 cases, reorient after clear/fork and the re-read check) | Plain Python, no runner. |

**The gap.** After a compaction the session gets the summary, the digest and the old handoff. All three hold beliefs with no source. Nothing tells the session which beliefs are measured and which are guesses. The summary is itself an unchecked source.

### Questions to the owner

| Piece | Where | What it does |
|---|---|---|
| Prompt judge | `settings.json:258-267` (`type: prompt`, model `claude-sonnet-5-5`, `continueOnBlock`) | Sees only the question. Judges three form rules. |
| Outcome judge | `settings.json:268-272` (command, timeout 105); `hooks/question_outcome.py` (558 lines); `hooks/test_question_outcome.py` (2,894 lines) | Code check for `Goal:` and `Problem:` lines, then one `claude -p` child at Haiku xhigh (`MODEL_TIMEOUT = 90`, `:34`). Reads the last 3 owner messages and every ruling in `decisions/` and `debts/` (up to 95,000 chars, `:68`). Needs a token from `claude setup-token` in `state/hook-token`. Has a code loop guard: after a deny, the next question passes. |
| Rulings | `decisions/question-outcome-check.md`, `decisions/question-judge-reads-rulings.md` | The judge's spec. Note: the first says Haiku, `subagent-model-cap.md:54` also says Haiku. |
| Other places that name it | `decisions/gate-hooks-fail-closed.md:7`, `decisions/owner-override-pass.md:35`, `decisions/decision-watch-mod-limits.md:16`, `decisions/subagent-model-cap.md:50,54`, `lint/rule_mechanisms.json:539-545`, `lint/test_settings_matcher.py:184-189` (`test_ask_user_question_rows_stay`), `lint/test_windows_split.py:39`, `hooks/test_wrappers.py:61`, `hooks/test_shared_names.py:160-164`, `.github/workflows/gates.yml:128,525,850`, `docs/catalog.md:43`, `debts/notes.md` lines 144-149, 236-238, 358, 461, 491, 499. | |

On Windows each question starts today: one `bash.exe` and one `python.exe` (the command hook), plus a `git` child and a `claude` child from inside the hook. The prompt judge starts no process.

### Planners

`agents/plan.md` (22 lines): Opus, high, read-only. It reads code and gives steps, files, risks and checks. It has no duty to list or check the brief's premises. `CLAUDE.md:28-31` (`roles-brief-contents`): a brief carries task, files, rulings, failure classes and the proving check. No premises.

### Evidence

- `decisions/cull-rules.md:11`: "No history in the tree. A decision holds only a ruling in force, plus a one-line reason."
- Precedent the other way: `decisions/subagent-powershell-tool.md:41-50` keeps an `## Evidence` section with a dated measurement inside the decision.
- `debts/measured-time-table.md`: no table keeps measured times.
- Roadmap c13 note, 2026-10-21 16:27: the owner ruled "no more measuring" for that batch. Fixes are proven by tests.
- No decision rules on a `measurements/` folder. None exists.

### Constraints checked

- **Model cap** (`decisions/subagent-model-cap.md:5-10`): Opus runs only for Plan, the advisor, builder try 3, a reviewer's round 3 on the owner's word, and an audit Explore (class-level word, 2026-10-21, PR #544). **Any other Opus use needs the owner's word.** A question-reviewer on Opus is a new Opus use.
- **PR #544** changed only the Agent prompt judge and the table: an audit Explore now passes on `sonnet` or `opus`; Haiku or no model blocks (`settings.json:280`, `subagent-model-cap.md:24,61-65`). The guard denies Haiku below the floor only (`hooks/guard.py:1536-1577`). Nothing in the guard denies Opus. Prose alone holds the ceiling.
- **Judge row test** (`lint/test_settings_matcher.py:208-255`): every `prompt` or `agent` hook needs a row in the model table whose first cell contains "prompt-hook judges" and names the matcher, with the same model. Model ids must start with `claude-` (`:105-139`).
- **building-guard-needs-incident** (`CLAUDE.md:82-83`): today "a named incident or a measured risk". Brief `c10-c23-guard-grows-then-proves.md` widens it to "or a likely risk". Plan below adds no new guard rule except optional lane 7.
- **Fewer hook processes**: a goal, not a rule. Prefer no new command hooks.
- **Plain words**: `output-styles/shiv-stylisms.md:29-37` (`style-plain-words`, `style-question-restates-goal`, `style-question-states-problem`, `style-question-inside-box`, `style-option-says-effect`).

### Facts from the Claude Code hooks page (code.claude.com/docs/en/hooks, read today)

- Agent hooks exist: `type: "agent"` "spawn a subagent that can use tools like Read, Grep, and Glob to verify conditions before returning a decision. Agent hooks are experimental and may change." Fields: `prompt` (with `$ARGUMENTS`), `model`, `timeout` (default 60 s).
- `onFailure: "block"` is for command and HTTP hooks only. So a failed agent hook lets the call through.
- "The transcript file is written asynchronously and may lag ... it may not yet include the current turn's most recent messages." So a judge cannot count on seeing the text just before the question.
- Hook input carries `agent_id` and `agent_type` when the hook fires inside a subagent.
- **Unknown**: the agent hook's return format (assumed `{"ok", "reason"}` like prompt hooks), whether `continueOnBlock` applies, whether hooks such as `reread_check --pre-read` fire for the agent hook's own Read calls, and whether it can name an `agents/*.md` file. The docs section on agent hooks did not load in full. Lane 1 proves these first.

---

## 2. The shared premise format

One line per premise. The same line works in a handoff, a brief, a plan and (in short form) a question.

```
## Working premises
- P1 [ruling] An audit Explore may run Opus. Source: owner 2026-10-21, decisions/subagent-model-cap.md. Checked 2026-10-21.
- P2 [read] The guard denies only a Haiku model below the floor. Source: hooks/guard.py:1577 at 73ed71a7. Checked 2026-10-21.
- P3 [measured] test_handoff_wave2 passes on this branch. Source: verdict run 2026-10-21 14:02 CDT, log <temp>/verdict-123.log, at 9f1c2ab. Checked 2026-10-21.
- P4 [notes] Lane A of c13 merged the config_watch fast exit. Source: roadmap c13 note. Checked never.
- P5 [assumed] Agent hooks accept a full model id. Source: none. Checked never.
```

The five source kinds, strongest first:

| Kind | Means | Strong or weak |
|---|---|---|
| `ruling` | The owner said it. Names the date and the home (decision, debt, or NO HOME YET). | Strong |
| `measured` | A command ran and showed it. Names the command, the time, the commit, and the log if one is kept. | Strong while the commit is current for the files it covers |
| `read` | Read in a file. Names `path:line` and the commit. | Strong while that file has not changed since the commit |
| `notes` | From a handoff, a summary, a digest, memory, a brief, a roadmap note, or an agent's report not yet checked. | Weak |
| `assumed` | No source. | Weak |

Rules of the format:
- **A premise is a claim, not a fact.** Act on a weak one only after a check upgrades it.
- A `read` or `measured` premise goes stale when its files change. The cheap check: `git log <commit>..HEAD -- <path>` prints nothing.
- **The handoff is a current record, not a log.** When a check confirms a premise, rewrite its line with the new source and date. When a check shows it wrong, delete the line, or replace it with the true fact and its source. Keep no "was wrong" note. If the wrong fact also sits in a brief, a decision, memory or a plan, fix it there too. If work already rested on it, say so under Deviations in the next report.
- A premise that becomes a ruling moves to its ruling's home. The premise line then cites that home as `ruling`.
- Every compaction summary fact counts as `notes` until checked.

In a question box, the same premise gets one plain line, kind in plain words:
`Based on: the guard only blocks Haiku below the floor (I read it in guard.py today).`

---

## 3. Design per place

### 3a. Handoffs (c25)

**Change the prompt, not the hooks' number.**

1. `hooks/precompact_handoff_prompt.md` step 4 gains a section, second in order (right after rulings with NO HOME YET):
   - **Goal**: one line, the owner's goal in the owner's words, with its source (owner message date).
   - **Working premises**: the lines in the format above. Only premises the next steps lean on. At most about 15.
   It also gains a short step "Check premises": after a compaction or a /clear, treat every premise as a claim. Before you act on a weak or stale premise, check it, then rewrite its line.
2. `hooks/precompact_handoff.py --reorient` (already runs once at SessionStart compact, clear and fork) reads the handoff and lists the premise ids to re-check before acting: every `notes` and `assumed` id, and every `read` or `measured` id (the session runs the `git log` check, the hook runs no git). After /clear or a fork, it lists every premise of the old handoff, because they came from another session. If the section is missing or does not parse, the message says: "Your handoff has no Working premises section. Add it per step 4." The message also says: "Facts in the compaction summary are notes until checked." No new process. Fails open like the rest of the file.
3. The nudge reason (`precompact_handoff.py:501-506`) stops copying the section list. It points at step 4 only, so the list has one home.
4. `CLAUDE.md:105-106` (Compact instructions) gains: keep the Goal and the Working premises with their sources.
5. `decisions/precompact-handoff.md` gains item 10: the premise section, the check after compaction, and the rewrite rule for a wrong premise.

No change to `reread_check.py` for handoffs. One fix rides with lane 1 if the probe shows hooks fire inside the question-reviewer: `--pre-read` must ignore a Read whose payload has `agent_id`, so a subagent reading the handoff does not clear the main session's flag (`reread_check.py:59-62`).

### 3b. Questions to the owner (c7)

**One reviewer, run as an agent hook, replaces both judges.**

- New file `agents/question-reviewer.md`: frontmatter like `agents/plan.md` (`model: opus`, `effort: high`, `disallowedTools: Edit, Write, NotebookEdit`). It is the one home of the reviewer's instructions.
- `settings.json`: the AskUserQuestion entry (`:258-273`) holds one hook only:
  `{"type": "agent", "model": "claude-opus-5-5", "timeout": 120, "continueOnBlock": true, "prompt": "You are the question reviewer. Read ~/.claude/agents/question-reviewer.md and follow it. Hook input: $ARGUMENTS"}`.
  The `model` field is the pin the hook actually uses. The frontmatter `model: opus` covers a manual spawn. Both are rows of the model table.

**Why an agent hook, not the session spawning the reviewer.**
- A hook runs on every question with no prose to obey. A session that spawns the reviewer itself needs a gate to prove it did.
- An agent hook starts no `bash.exe` or `python.exe`. A session spawn of a subagent fires the Agent hooks: `guard.py` (PreToolUse), `agent_brief.py` and `local_time.py` (SubagentStart, `settings.json:347-365`), `agent_end_reap.py` and `guard.py` (SubagentStop, `:207-225`). That is five command hooks, five `bash.exe` plus five `python.exe` per question on Windows.
- An agent hook uses the app's own login. The `claude -p` child and its `state/hook-token` go away for this check.
- Fallback if lane 1 shows agent hooks do not work here: the session spawns `question-reviewer` before each question, and the reviewer file is unchanged. That fallback needs a gate and costs the five processes above. Lane 1 reports which one holds before any other lane starts.

**What the reviewer gets.** A fresh context. The hook input (`session_id`, `transcript_path`, `cwd`, the question and options). With Read, Grep and Glob it reads:
- the goal: the question's `Goal:` line, the handoff's Goal line (`~/.claude/handoffs/<session_id>.md`), and the owner's last messages in the transcript (Grep from the end; the transcript may lag, so it never relies on text from the current turn);
- the premises: the question's `Based on:` lines, matched to the handoff's Working premises;
- the raw evidence: every file, line, log or record a premise names;
- the owner's rulings: `decisions/*.md` and `debts/*.md` under `cwd`, Grep first, then only the records the question touches. This also closes debt note `judge-reads-related-only` and the 800-char cut (`debts/notes.md:145,491,499`).

**What it checks, in order.**
1. Does a ruling already answer the question?
2. Does each premise hold? A `notes` or `assumed` premise that the choice turns on, and that the session could check itself, counts as failed (`output-never-hand-off-doable-step`). A strong premise it cannot verify passes.
3. Is there an option that beats the listed ones for the goal?
4. Form: `Goal:` first, then `Problem:`, each option says what the owner gains and loses, every id or name explained in the box. A question with no options or one option passes at once.

**What it returns** (the hook's `{"ok", "reason"}`; the reason goes back to the session, the owner sees nothing):

| Verdict | Reply | The session then |
|---|---|---|
| Pass | `{"ok": true}` | The owner sees the question. |
| Answered | `{"ok": false, "reason": "ANSWERED by decisions/<id> (<title>): \"<quoted ruling>\". Do not ask. Act on it, cite it, and add it to Working premises as [ruling]."}` | Acts on the ruling. **The owner never sees the question.** |
| Premise fails | `{"ok": false, "reason": "PREMISE P<n> fails: <claim>. Fact: <what holds>, source <path:line at commit, or record id>."}` | Fixes the premise line in the handoff. Asks again only if the question still stands. |
| Better option | `{"ok": false, "reason": "OPTION missing: <option>, because <reason>."}` | Adds the option, or states in the box why it loses. |
| Form | `{"ok": false, "reason": "FORM <rule id>: <fix>."}` | Fixes the wording. |

**Loop guard.** No code holds state any more, so the reviewer file says: if the transcript shows you already blocked this question and the new one answers your objection, pass it. The session side: after two blocks on the same question, ask the owner in plain reply text and name the reviewer's objection. A wrong reviewer then costs two turns, never a stuck session.

**Fail open.** An agent hook that fails or times out lets the question through (no `onFailure` for agent hooks). That matches `question-outcome-check`'s stance: a question is not a destructive act.

**What the session writes.** Each question with two or more options adds, inside the box after `Problem:`, one to three `Based on:` lines in plain words (see Open question 1). The style file gains that rule.

### 3c. Planners (c24)

- `agents/plan.md` gains one paragraph, before "Read the code the task touches first":
  "Premises first. List the brief's premises in the premise format, each with its source. Check each against `decisions/`, `debts/`, the owner's recent rulings named in the brief, and the code. Mark each holds, fails, or unknown. Name every premise that fails, and any simpler route the facts open. Put this list at the top of the plan."
- `CLAUDE.md:28-31` (`roles-brief-contents`): a brief also carries its premises, each with a source. When the orchestrator writes a batch's briefs, it lists the batch's premises once across all lanes, checks each once, and puts the checked lines in each brief that leans on them (`Checked <date> by the orchestrator`). A Plan or builder re-checks only weak ones. This is a CLAUDE.md change, so `bin/merge` flags it (`decisions/claude-md-change-is-flagged.md`).
- Optional (lane 7): the Agent prompt judge (`settings.json:280`) also checks that a builder, reviewer or test-author brief carries a premise list. No new process. It is a new gate rule, so it needs a "likely risk" record once c10's amendment lands.

### 3d. Raw evidence (c25)

- **No `measurements/` folder.** Evidence lives with the record that uses it:
  - a measurement a standing decision leans on: an `## Evidence` section in that decision, at most about 10 lines (date, command, commit, result), like `decisions/subagent-powershell-tool.md:41-50`;
  - a measurement an open step leans on: the same section in its debt file;
  - raw logs stay outside git (the verdict log in temp, pruned after 7 days). A record keeps only the summary line and may name the log path while it exists.
- When the decision or debt is deleted, its evidence goes with it. No sweep is needed, and no history stays in the tree.
- `decisions/cull-rules.md:11` needs one added clause: "plus an Evidence section of the measurements the ruling leans on". That is a rewrite of a ruling, so it needs the owner's word (Open question 4).
- A handoff `measured` premise names the log path. A pruned log turns the premise stale, and the reorient list catches it.

---

## 4. What gets deleted or replaced

| Removed | Replaced by |
|---|---|
| `settings.json:259-267`, the AskUserQuestion prompt hook and its prompt text | the agent hook |
| `settings.json:268-272`, the `question_outcome.py` command hook | the agent hook |
| `hooks/question_outcome.py` (558 lines) and `hooks/test_question_outcome.py` (2,894 lines) | `agents/question-reviewer.md` plus settings pins |
| `decisions/question-outcome-check.md`, `decisions/question-judge-reads-rulings.md` | one new entry, slug `question-reviewer` |
| Rows in `subagent-model-cap.md:50` (AskUserQuestion leaves the prompt-judge row) and `:54` | a new row: "prompt-hook judges (agent type): AskUserQuestion, question reviewer, claude-opus-5-5" and a row for `agents/question-reviewer.md`, opus, high |
| `gate-hooks-fail-closed.md:7` "four command gates" | three (`question_outcome.py` leaves) |
| `owner-override-pass.md:35`, `decision-watch-mod-limits.md:16` mentions | name the reviewer, or drop the name |
| `lint/rule_mechanisms.json:539-545` (`style-question-restates-goal`, kind gate, test `case_1`) and `:546-550` | kind judgment, ref `agents/question-reviewer.md`. **This turns a code check into a model check** (Open question 2). |
| `gates.yml:128,525,850`, `lint/test_windows_split.py:39`, `hooks/test_wrappers.py:61`, `hooks/test_shared_names.py:15,35,160-164`, comments in `test_local_time.py:407`, `test_feedback_inbox.py:35`, `test_decision_watch.py:1169`, `docs/catalog.md:43` | updated; `docs/catalog.md` is rebuilt by `lint/hook_catalog.py` |
| `debts/notes.md` lines 144-149, 236-238, 358, 461 (question part), 491, 499 | deleted: their subject is gone |

Stays: `decision_watch.invoke_model` and `state/hook-token` (`reply_judge`, `prose_judge`, `sendmessage_state`, `feedback_judge` still use them). `shared_names.MACHINE_TAGS` stays.

**Net change in hook processes on Windows, per event:**

| Event | Today | After | Change |
|---|---|---|---|
| PreToolUse AskUserQuestion | 1 command hook (1 `bash.exe` + 1 `python.exe`, plus a `git` and a `claude` child) and 1 prompt hook | 1 agent hook, no shell, no python | **-1 bash, -1 python, -1 git, -1 claude child per question** |
| SessionStart compact / clear / fork | 1 command hook | same hook, more text | 0 |
| Stop | 9 command hooks | 9 | 0 |
| PostCompact, PreToolUse Read, PreCompact, SessionEnd | unchanged | unchanged | 0 |
| Agent spawn (planner, briefs) | unchanged | prose only; lane 7 adds text to an existing prompt hook | 0 |

The agent hook still costs one Opus run per question. Unknown: whether the reviewer's own Read calls fire `reread_check --pre-read` (a command hook). If they do, each reviewer Read costs one `bash.exe` + `python.exe`. Lane 1 measures nothing, but it checks whether the hook fires at all.

---

## 5. Lanes for a later build batch

Each lane: a test-author writes the case red on main, the builder turns it green. All tests are plain Python, standard library, the repo's own style.

| # | Lane | Files | Test, red on main, green on the fix |
|---|---|---|---|
| 1 | **Probe agent hooks** (a feature check, no timing) | scratch config only; then `hooks/reread_check.py` if needed | A throwaway session with an agent hook on AskUserQuestion: does it accept `claude-opus-5-5`, return `{"ok","reason"}`, apply `continueOnBlock`, read `~/.claude/agents/...`, and do hooks fire for its Read calls? Report each as yes, no or unknown. If Read hooks fire: `test_handoff_wave2.py` new case `case_subagent_read_keeps_flag` (a `--pre-read` payload with `agent_id` keeps the flag): red on main. **Gate: lanes 4-5 wait for this report.** |
| 2 | **Premise section in the handoff** | `hooks/precompact_handoff_prompt.md`, `hooks/precompact_handoff.py` (nudge reason, reorient), `decisions/precompact-handoff.md` (item 10), `CLAUDE.md:105-106` | In `test_precompact_handoff.py`: `case_prompt_lists_working_premises` (step 4 names Goal and Working premises), `case_reorient_lists_weak_premises` (a handoff with P1 `ruling`, P4 `notes`, P5 `assumed` prints P4 and P5 and not P1), `case_reorient_flags_missing_premises`, `case_nudge_points_at_step4` (reason has no copied section list). In `test_handoff_wave2.py`: `case_cleared_reorient_lists_every_old_premise`. All red on main. |
| 3 | **Premise format home** | new section in `decisions/precompact-handoff.md` or a small new entry, slug `premise-format` (the table of kinds) | Lint-style case in lane 2's test file: the five kinds the reorient parser accepts equal the kinds the record lists (one home, `building-allow-list-is-the-constant`). Red on main. |
| 4 | **Question reviewer** | new `agents/question-reviewer.md`; `settings.json:258-273`; `decisions/subagent-model-cap.md` rows; new entry `question-reviewer`; `lint/test_settings_matcher.py` (re-point `test_ask_user_question_rows_stay` to "one agent hook, model claude-opus-5-5, names agents/question-reviewer.md"; widen `JUDGE_ROW` to match the agent-type row) ; `output-styles/shiv-stylisms.md` (`Based on:` rule) | `test_settings_matcher.py`: `test_ask_user_question_is_one_agent_hook`, `test_reviewer_file_exists_and_pins_opus`, judge-row test still red when the AskUserQuestion row is removed (mutation like `lint/test_settings_matcher.py:251-255`). `lint/check_agent_models.py` passes the new file. Red on main. |
| 5 | **Delete the old judges** | `hooks/question_outcome.py`, `hooks/test_question_outcome.py`, the two decisions, `gates.yml`, `lint/test_windows_split.py`, `hooks/test_wrappers.py`, `hooks/test_shared_names.py`, comments in three tests, `lint/rule_mechanisms.json`, `gate-hooks-fail-closed.md`, `owner-override-pass.md`, `decision-watch-mod-limits.md`, `debts/notes.md`, `docs/catalog.md` | Delete-only lane: one review round. Proof: `lint/test_settings_matcher.py` from lane 4 green, `lint/rule_audit.py` and `lint/hook_catalog.py` checks green with the rows moved. Red on main: a new case `test_no_hook_runs_question_outcome`. |
| 6 | **Planner duty** | `agents/plan.md`, `CLAUDE.md:28-31` | `lint/` case: `agents/plan.md` body names "Premises first" and the five kinds by reading the premise-format record, not a copy. Red on main. Prose otherwise; the rule stays `unmechanized` in `lint/rule_mechanisms.json` with a reason. |
| 7 | **Evidence home** (after Open question 4) | `decisions/cull-rules.md:11` | Wording only, no test (a ruling text). Optional: the Agent prompt judge checks briefs for premises (`settings.json:280`), with a pin case in `test_settings_matcher.py` and its record citing a likely risk. |

**Order.** 1 first, alone. Then 2 and 3 together (same files: lane 3's record sits beside lane 2's item 10; give both to one builder or run 3 after 2). Then 4. Then 5 (needs 4 merged, since both edit `settings.json`, `subagent-model-cap.md` and `lint/test_settings_matcher.py`). 6 can run beside 2-4, but it edits `CLAUDE.md` like lane 2, so it joins the batch after lane 2. 7 last.

**Shared files:** `settings.json` (4, 5, 7), `decisions/subagent-model-cap.md` (4, 5), `lint/test_settings_matcher.py` (4, 5, 7), `CLAUDE.md` (2, 6), `decisions/precompact-handoff.md` (2, 3), `hooks/test_handoff_wave2.py` (1, 2).

Model use: Plan for this design is Opus by standing rule. Builders Sonnet, reviewers per the table. The question-reviewer's Opus needs Open question 3.

---

## 6. Open questions for the owner

1. **Should the premises show inside the question box?**
   - A: yes, one to three short `Based on:` lines in plain words. You see what the question rests on and can spot a wrong fact. The box gets a little longer.
   - B: no, only ids that point at the handoff. Shorter box, but the ids mean nothing to you, and the reviewer must find the handoff.
   - **My pick: A.** The transcript can lag, so the reviewer can only count on what is in the box.

2. **Keep a code check for the `Goal:` and `Problem:` lines?**
   - A: drop it. The reviewer judges form too. Saves one bash and one python start per question. The rule moves from a code check to a model check.
   - B: keep a small Python check, with no model call. It never misses a missing line, but it keeps the bash and python start.
   - **My pick: A.** A missing label is easy for Opus to see, and the start cost is the point of the change.

3. **Give the question reviewer a standing Opus word?** The model cap allows Opus only for named roles. The reviewer would run Opus on every question with two or more options.
   - A: yes, a class-level word like the audit Explore of 2026-10-21. Best judgment where a wrong question costs you the most time.
   - B: Sonnet. Cheaper per question, weaker at spotting a better option.
   - **My pick: A.**

4. **Where does raw evidence live?**
   - A: inside the decision or debt that uses it, in an Evidence section of about 10 lines. It is deleted with that record. Needs one clause added to `cull-rules` ("no history in the tree").
   - B: a `measurements/` folder. One place to look, but it needs its own cleanup rule and drifts from the records.
   - **My pick: A.**

## Unknown (not checked)

- The agent hook's return format, `continueOnBlock` support, Read access to `~/.claude/agents/`, and whether hooks fire inside it (lane 1).
- Whether the session or a subagent can call AskUserQuestion at all; assumed main session only.
- Roadmap text of c24 and c25 (not in the 2026-10-21 backup).
- Timings: not measured, by the owner's ruling of 2026-10-21.
