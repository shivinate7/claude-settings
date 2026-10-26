# Goal 3: close the cleanup phase of claude-settings

Paste this whole file to one fresh claude-settings session with `/goal finish this end to end`.
Written by the advisor, Oct 25, against main f463787 (#572). Goal 2 (briefs/cleanup-goal-2-oct23.md)
is done except its two Mac batches; this goal finishes those and the last cleanup steps. Each batch
is its own integration PR, under the usual rules (git-integration-branch-merge,
roles-review-cap-three).

## 0. First, before any work

1. Save this file as `~/.claude/handoffs/goal-cleanup-3.md`. Put that path on the Goal line of
   your handoff. After every compaction, read it again before you act.
2. Check each "checked at" fact against current main. A fact that no longer holds: re-plan that
   lane and say so in the report. A lane whose work is already on main: skip it, say so.
3. Open PRs at writing time: #571 (bin/ios-ship, one shared tool to ship iOS apps) and the guard
   cull lane (branch guard-cull-gh-api: delete gh-api-method, owner's word Oct 25, typed as the
   override for the hole review round 1 found). The owner said both are merging. Confirm with
   `gh pr list --state open`; take over any that are not merged and drive them to green.
4. Confirm the live settings match main on this machine: `git -C <pin> rev-parse HEAD` against
   `git rev-parse origin/main`, read right after this session started. Equal: the session-start
   auto-pull (#568) works here; say so. Behind: say so with both commits, then reinstall with
   `bash merge/install_from_main.sh` from the clone, and treat the auto-pull as a red finding for
   batch 1.

## Pace (from goal 2, unchanged)

No fixed lane cap: start every ready lane that touches no other open lane's files; the load brake
decides. Never idle: while CI runs, build the next batch's lanes as drafts. Questions go to the
advisor first (rule questions-ask-advisor-first); only the owner's calls wait for the owner, and an
unanswered question parks only its item. At each batch merge, report four numbers from git and
GitHub (no new log): wall-clock from first lane commit to merge; lanes run and the most at once;
minutes with no lane running and why; brake refusals with their readings.

## Handoff rules

As in goal 2: the handoff holds Goal, State (each open lane and PR with its plain name, branch, last
CI head and verdict), owner rulings with their record, open questions and what you do meanwhile,
the next action, and working premises with sources. Update it on events. After a compaction: this
file, then the handoff, then `git fetch` and `gh pr list --state open`. Trust GitHub over the
handoff.

## Stop points (the only places you wait for the owner)

- Batch 3, part 1: whether to add an alert at all, after the first check below.
- Batch 4: the kill guard needs the owner's Mac. On Windows, park it and say so.
Merges run under decision standing-merge-grant.

## Batch 1. Agents stop their watchers before they report (c43)

Full brief: briefs/c43-agents-stop-their-watchers.md in the advisor repo (owner pastes it, or read
the copy in step c43's Ask). Short form: the defect is verified (a subagent that leaves a Monitor
or a background Bash running after its report wakes once per task end, and the parent gets a new
notification each time; advisor probe, Oct 25: 3 notifications from one agent). Lane 1: one
sentence in each agent file: before the final report, stop every Monitor and background task you
started with TaskStop, and start none after it. Lane 2: extend judge_stop in hooks/guard.py (it
already runs on SubagentStop) to read the agent's transcript and block the stop once while a task
it started is live; never block twice; fail open. Red then green, then one live run.

## Batch 2. A goal run shows its pace, and no brief caps lanes by guess (c37, parts 2 and 3)

Goal 2 used both; neither is in claude-settings yet (checked at f463787).
1. One rule, in its one home (find it: the orchestrator's roles or parallelism rules in CLAUDE.md,
   or the skill that plans batches; extend it, add no second home): a brief or plan never caps
   lanes by a guessed number; the load brake decides when the machine is too loaded.
2. The batch report rule (reports-order-of-labels and its home) gains the four pace numbers above,
   read from git and GitHub at report time. No new log, no watcher, no timer.
3. If a lint already checks report or rule format, extend it so a brief that writes "one or two at
   a time" or "at most N lanes" is flagged; otherwise prose only, and say so.
Proof: the rule text lands with its rule anchor; any lint case is red then green.

## Batch 3. A question waiting on the owner reaches the owner (c31)

1. First check, before any code: does the Claude desktop app already alert the owner (a desktop or
   phone notification) when a session stops on a question? Read the Claude Code docs for the
   Notification hook and the desktop app's own notifications, and test it once on this machine.
   Report what fires. Stop point: bring the owner one question: (a) the app already alerts, close
   c31 with no code (pick, if true); (b) add a Notification hook that sends one desktop alert,
   costing nothing per tool call; (c) also a phone push, with the channel named.
2. The question rule already says a session keeps working on what does not depend on the answer
   (questions-ask-advisor-first). Check it also says the question names what the session does
   meanwhile; if not, add those words in place.

## Batch 4. Kill guard knows a lane's left-behind server (c27). Mac only.

Full brief: briefs/c27-kill-guard-session-tag.md in the advisor repo (step c27's Ask). Its first
check runs on the Mac before any code and stops the batch if the session tag is not in the
server's environment. On Windows, park it and say so.

## Batch 5. Delete the two STE stub scripts (debt ste-stubs-delete)

lint/ste_gate.py and lint/md_sweep.py exit 0 and exist only for old installs whose settings.json
still calls them. Check the install log on this machine and ask the owner for the other machine's
pin commit: every install at or past #566 (batch-oct23a, where the STE hooks left settings.json)
means delete both files, their stub cases in lint/test_settings_matcher.py, and the debt. Any
install older, or unknown: keep them and say why.

## Batch 6. Merged work leaves no worktrees or branches behind (c44). Added Oct 26.

Full brief: briefs/c44-merged-work-cleans-up.md in the advisor repo (step c44's Ask). Owner agreed
Oct 25. Its lane 3 (the report offers the fast cleanup command) edits the same report rule as batch 2:
if batch 2 has not merged, carry lane 3 in batch 2; otherwise it rides here. Lanes 1 and 2 touch the
merge tool and the sweep, which no other batch touches, so they may start as drafts at once.

## Not in this goal

- c33 (home gets a small CI) and c42 (home-app names its merge checks): each is a short session in
  its own repo, from its own brief in the advisor repo.
- c41 (Opus for one session without lifting other guards): owner's word, Oct 25, brief it later.
- c40 (idle desktop sessions burn a core each): the owner's action in the app.

## When the goal is done

Report per the report rules, plus the four pace numbers per batch and in total. List anything
parked and why. Then the advisor re-measures the cull numbers and reviews the roadmap for the move
to the Organize phase, which starts with o2 (one layout for every repo; its brief and plan are in
the advisor repo).
