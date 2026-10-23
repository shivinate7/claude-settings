# Goal 2: finish the cleanup phase of claude-settings, fast and measured

Paste this whole file to one fresh claude-settings session with `/goal finish this end to end`.
Written by the advisor, Oct 23, against main 1842e56 and #564 (batch-oct22d, CI running).
It replaces briefs/cleanup-goal-oct21.md. Each batch is its own integration PR, under the usual
rules (git-integration-branch-merge, roles-review-cap-three).

## 0. First, before any work

1. Save this file as `~/.claude/handoffs/goal-cleanup-2.md`. Put that path on the Goal line of
   your handoff. After every compaction, read it again before you act.
2. Check each "checked at" fact against current main. A fact that no longer holds: re-plan
   that lane and say so in the report. A lane whose work is already on main: skip it, say so.
3. Take over #564 (the last goal-1 batch, branch batch-oct22d). The goal-1 session stopped
   on Oct 23 and handed it off. Its handoff: C:\Users\ShivamSemwal\.claude\handoffs\
   c5d76e85-6c75-4e9a-a61d-bb3938b4991b.md; read it first. State then: red at 54a99bf, only the
   `gates` job failing (a duplicate question-hook row in the hook catalog). Cause per that
   session: the question-reviewer lane; the STE-removal lane carries that lane's work. It left
   four local reverts in the batch checkout, not pushed: three drop STE removal, one drops the
   question reviewer; with them the duplicate-row test passed locally. The generated records page
   was still stale, cause not found.
   - Confirm the cause from the failing job's log, not from the handoff.
   - Follow the red-run rule: push the drop of the failing lane and the lanes that depend on it,
     run CI once, and merge the rest on green (owner's word, Oct 23: merge #564 when its CI is
     green). Find and fix the stale records page cause, or say why it is not a lane's.
   - The dropped lanes are fixed in their own lanes and join batch 3. The janitor lane's test
     fix at 599de54 still needs review; it also joins batch 3.
   - Meanwhile build batch 2 and batch 3 lanes as drafts. Batch 1 branches from main only
     after #564 merges.
   - #556 (manual memory monitor, ready at f585fff): owner's word, Oct 23: merge it. Do it
     after #564 merges, with the merge tool, on green CI against the new main.
4. Confirm the live settings match main: `git -C <pin> rev-parse HEAD` against
   `git rev-parse origin/main`. If they differ, the session-start auto-pull is still broken
   (batch 2 fixes it): run `git -C <clone> fetch origin main:main`, then
   `bash merge/install_from_main.sh` from the clone, and check again.

## Pace: measure, never guess (owner gripe, Oct 22: goal 1 measured compute badly and ran slowly)

Goal 1 ran slowly for three causes: the brief capped lanes at "one or two at a time" by guess;
the load brake read the machine wrong (CPU from one 200 ms spike, disk as a percent, Mac CPU
from the load average) and refused lanes the machine could run; and "run in the foreground"
was a remedy this app cannot use, since every Agent lane here runs in the background.

- No fixed lane cap. Start every lane that is ready and does not touch another open lane's
  files. The brake decides when the machine is too loaded; when it refuses, start the next lane
  once one finishes, and say which reading tripped it.
- Batch 1 (brake reads right) goes first, because every later batch paces on it.
- Never idle. While CI runs, build and review the next batch's lanes as drafts. A question goes
  to the advisor first (rule from #564), and you keep working on anything that does not depend
  on the answer.
- Measure each batch, at its merge, from what git and GitHub already hold (no new log, no
  watcher): wall-clock from first lane commit to merge; lanes run, and the most at once; minutes
  with no lane running, and why (CI, a question, a brake refusal, a red run); the brake readings
  of each refusal. Put these four numbers in the batch report. A batch with more idle minutes
  than working minutes names the cause and the fix in its report.

## Handoff rules (it will compact many times)

Your handoff (`~/.claude/handoffs/<session_id>.md`) always holds, current, not as a log:
Goal (this path and the batch, by number and plain name); State (each open lane and PR with its
plain name, branch, last CI head and verdict); owner rulings this goal received, one line each
with the record they now live in; open questions and what you do meanwhile; the next action;
working premises, each with its source (ruling, measured, read with file and commit, or notes).
Update it on events: a lane done, a merge, a CI verdict, a ruling, a premise found wrong.
After a compaction: read this file, then the handoff, then `git fetch` and
`gh pr list --state open`. Trust GitHub over the handoff, and fix the handoff when they differ.

## Stop points (the only places you wait for the owner)

Bring each as one question with options and a pick, and keep working meanwhile.

Owner's word, Oct 23: every question in this run goes to the advisor session (ListAgents, then
SendMessage to the session named "advisor-" plus a short suffix; advisor-1b on Oct 23; a restart
gives it a new suffix), from the start, before #564 lands its asking rule. No advisor session
listed: wait 10 minutes, look again, and if still none, treat the question as unanswered. Ask the
owner nothing during the run. When the advisor replies "ask the owner", treat it as unanswered
(below). Merges run under decision standing-merge-grant; they need no question.

When the owner does not answer (owner's word, Oct 23): never wait. Park only the item that needs
the answer, and keep going with every other lane and batch, in order. Ask the advisor first for
anything it may answer (rule from #564); only the owner's calls wait for the owner. Each parked
item goes in the handoff under "Open questions" with what it blocks. When nothing is left that
does not depend on an answer, write the report with each parked item and its question, then stop.
The goal is not done until those items are answered or the owner drops them.
- Batch 4, guard cull part 2: the list of rules to delete, before any deletion. Needs the Mac.
- Batch 5, kill guard: needs the owner's Mac. On Windows, park it and say so.

## Batch 1. The brake reads the machine right (c14)

Branch from main after #564 merges. Decision machine-load-brake.

1. Disk: the smaller of a share and a GB cap, so big drives are not penalized. Today
   `_read_disk` returns 100 * free / total, against 15 (busy) and 5 (full). On the owner's 926 GB
   Mac disk, busy fires under about 139 GB free; it held lanes back at 119 GB free. Owner ruling,
   Oct 23: busy when free space is under the smaller of 10% of the disk and 15 GB; full when it
   is under the smaller of 5% and 5 GB. (926 GB disk: busy under 15 GB, full under 5 GB. 100 GB
   disk: busy under 10 GB, full under 5 GB.) Memory stays a share. Read free bytes and total from
   `shutil.disk_usage(home)`. Refusal text "disk %.1f GB free of %.0f GB". Replace the
   `disk_free_pct` key with `disk_free_gb` and `disk_total_gb` and update every reader.
   read_load clamps every reading to 0-100: do not clamp the GB values.
2. CPU from ticks on Mac and Linux, not the load average. Today darwin uses
   os.getloadavg()[0] / cpu_count. Measured on the owner's Mac: Spotlight indexing gave load 107
   on 15 cores (reads 100% busy) while top showed 49-53% idle. Read Mach CPU ticks twice, 200 ms
   apart, like the Windows GetSystemTimes branch: ctypes on /usr/lib/libSystem.dylib,
   host_statistics(mach_host_self(), HOST_CPU_LOAD_INFO=3, uint32[4] {user, system, idle, nice},
   count 4). Busy share = (delta total - delta idle) / delta total. Linux: /proc/stat read twice
   the same way. No child process on any platform.
3. CPU sample window: 2 seconds on every platform (Windows, Mac, Linux), one constant. Owner's
   word, Oct 23. Why: a 200 ms sample catches bursts, such as a lane's own local CI filling the
   cores for a moment; on the Mac a lane read 100% busy while top showed 24% idle. With 2 s the
   owner's Mac read about 14% busy against top's 27%. Cost: a 2-second pause per lane start
   only; no other call reads CPU. The owner's Mac has this as an uncommitted patch too.
4. Keep from #564: a spawn that leaves run_in_background out or sets it false passes busy; CPU
   counts only with memory over 75%. The refusal text says plainly that in this app busy slows
   only Workflows and explicit background calls, and full stops every lane.
- Reference only: the owner's Mac has an uncommitted version of fixes 1 and 2 in its
  claude-settings-live-<hash>/hooks/guard.py (`git -C <that checkout> diff`). Build fresh.
- Proof: a test-author writes cases red on today's code: 926 GB disk with 119 GB free is not
  busy; 926 GB with 10 GB free is busy and with 3 GB free is full; 100 GB with 9 GB free is busy
  and with 12 GB free is not; a darwin reading with high load average and low
  tick use is not busy; ticks at 90% busy with memory over 75% is busy; a 0.3 s burst at 100% in
  an otherwise idle 2 s window reads about 15%, not busy. The lane-start path takes about 2 s, not 300 ms. The builder makes them
  green. Update test_guard_load_os.py and test_guard.py where they assert percent disk or load
  average; show each red, then green. The Mac runner checks ticks against `top -l 2`.
- Rewrite the machine-load-brake decision in place: disk as the smaller of a share and a GB cap,
  CPU from ticks on Mac and Linux.

## Batch 2. Local sessions pick up merged settings on their own (live-pin-autopull)

Checked at 1842e56: the SessionStart hook in settings.json reads the @ path from
~/.claude/CLAUDE.md, tests `[ -d "$d/.git" ]`, then pulls and runs install.sh. That path is
<clone>-live, a worktree (or a link to <clone>-live-<commit>), so .git is a file and the test
fails. The pull never runs, and could not work anyway: the pin is a detached HEAD. install.sh
then reinstalls whatever local main holds, nothing moves local main, and all output goes to
/dev/null. Incident, Oct 22: the owner's Mac pin was 174 commits behind origin/main.

- Find the clone from the pin with `git rev-parse --git-common-dir`.
- Fetch origin main and move local main fast-forward only, never force. Advisor ruling, Oct 23
  (replaces "if main is checked out in any worktree, skip"; read literally it skipped on every
  normal clone, since the clone's own checkout holds main): do what merge.py's ff_main and
  launch.py already do. No worktree holds main: `git fetch origin main:main`. A worktree holds
  main (the clone's own checkout or a linked one): fast-forward it there with
  `git -C <that tree> merge --ff-only origin/main`, only when it is on main and has no tracked
  changes (`git status --porcelain --untracked-files=no` is empty). Untracked files do not block
  it; git itself refuses the fast-forward when one would be overwritten. Tracked changes, or a
  refused fast-forward: leave that tree as it is and write one line to the install log. Never
  stash, reset, switch or force. The pin still follows local main
  (decision merge-reinstalls-from-main, unchanged).
- Run merge/install_from_main.sh from the clone (decision merge-reinstalls-from-main: only that
  script moves the pin).
- Keep: exit at once when CLAUDE_CODE_REMOTE is set; never block the session; a failed step never
  fails the session. Windows: read install.ps1 and the hook's MINGW branch, say what Windows
  does today, and change it only if it has the same fault.
- A failed step writes one line to the install log install.sh writes. Nothing else is logged.
- Files: settings.json (SessionStart hook), merge/install_from_main.sh, install.sh (pin logic
  near merge-reinstalls-from-main), README.md ("Why local sessions never run stale": rewrite in
  place), lint/test_hook_catalog.py (re-point the pinned hook text), hooks/test_guard.py (the
  guard allows the new commands).
- Windows has the same fault (the hook's MINGW branch runs nothing, and the .git test fails on
  the pin), so this lane fixes Windows too; install_from_main.sh already runs install.ps1 there.
- Proof: test first, red on today's hook: a temp clone with a -live worktree, origin ahead; after
  the hook runs, the pin is at origin/main. Second case: main checked out in the clone, no tracked
  changes, an untracked file present, origin ahead; the hook fast-forwards it and the pin is at
  origin/main. Third case: main checked out with a tracked change; the hook leaves that tree and
  its change as they were, logs one line, and the pin stays at local main. Builder makes all
  green. Reviewer reads the diff.

## Batch 3. Small lanes (each a few lines; one integration PR)

- janitor-fast-sweep (c16): dropped from #564, red on test_decision_watch judge_isolation,
  fixed in its own lane. Check the fix, then join.
- ci-time-caps (c34 and c39 on the roadmap). Owner gripe, Oct 23: CI that is new, or that just
  gained tests, keeps timing out and failing. Cause, checked at 1842e56: skill ci-hygiene step 5
  sets each job's cap at about 2x its slowest green run, but a new job has no green run, and a
  growing suite outgrows its cap with no warning. The only signal is a timeout that looks like a
  test failure (Oct 17: two gates runs cancelled at 18 min with every step green; Oct 22: the macOS
  cap raised from 25 to 50 min, and #562's merge wait ran out while CI was green).
  1. New job: skill ci-hygiene says a job with fewer than 5 green runs takes a provisional cap of
     60 minutes, marked "provisional" in a comment; after 5 green runs, set it to about 2x the
     slowest, from the measured times.
  2. Warn before the cap fires: when the merge tool reads a run, it prints one line for each job
     whose time was over 70% of its cap ("job X: 31 of 36 min; raise the cap from measured runs,
     or split its slowest suite"). It reads the run it already reads; no new call on any other
     path, no log. Advisor ruling, Oct 23: add startedAt and completedAt to the fields of the
     `gh pr checks` call merge.py already makes; read each job's cap from the workflow files on
     disk. No `gh run view` call.
  3. A timeout is not a test failure: when a job ends by its cap, the merge tool says so in its
     verdict, and the red-run rule treats it as "re-cap or split", not as a reason to drop the
     lane. Advisor ruling, Oct 23: a job ended by its cap is one whose check is cancelled and
     whose completedAt minus startedAt is at least its cap (a concurrency cancel ends sooner).
     Step data is not read: on the Oct 17 timed-out gates job (run 39074284633) every step reads
     success, so "every finished step green" adds nothing.
  4. The merge wait follows the caps: merge.deadlineMinutes in .github/stamp.json is the largest
     job timeout-minutes plus 5; extend the check that validates stamp.json so it fails when the
     wait is below the largest cap (red on main, green after).
  5. Run the report-gate timing test that failed once 20 times on main; fix the cause if it
     fails, never add a retry. Advisor ruling, Oct 23: no record names the test, so run all six
     wall-clock bounds in lint/test_gates.py (the report-gate fixture file): test_114 in
     UICopyRoundTwoTests, test_27 and test_28 in SteGateLogTests, test_09 in MdSweepLogTests,
     and the two lock-error tests in GuardLogAppendRaceTests. Run the whole file 20 times, under
     load, since the failure came in a full run and not alone. If none fails, say so and change
     nothing.
  Tests: a fixture run with a job at 80% of its cap prints the line, at 50% prints nothing; a
  job cancelled at its cap gets the timeout verdict, one cancelled sooner does not; red on main. The ci-hygiene skill
  is used by every repo, so this reaches banchi, q_max, home-app and home too.
- ste-lint-import-path (c35): actions/ste-lint/run.sh line 131 runs `python3 -c` in the linted
  repo's root, so a json.py or ste_emit.py there runs as code. Move that summary into a script
  file in $EMIT_DIR, like HUNK_MAP_PY and SPLIT_PY. No -I, no -P. Test in
  actions/ste-lint/test_action.py with fixture json.py, json/__init__.py and ste_emit.py that
  write a marker; SCOPE all and changed; no marker, summary still prints. Red then green.
- ste-stubs-delete: delete the exit-0 ste_gate and md_sweep stubs #564 left, per that debt, once
  every install has run past #564 (check the install logs on both machines; on doubt, keep them
  and say why).
- test-temp-standard (new, from the Degen Swift session, Oct 22): test temp folders filled the
  Mac disk. Make this the standard for every repo, in its one home (agents/test-author.md and a
  decision; find the existing home first): one temp root per repo; one run folder per test run,
  named <pid>-<UUID>; every helper takes its folder from the run folder, never the system temp
  dir directly; teardown removes the run folder; the first request of a run removes sibling run
  folders older than one day (crashed runs), and leaves newer ones (parallel runs). A test proves
  the sweep: an old sibling goes, a new one stays. Rule only; each repo's helper stays in that
  repo (Degen: TempDirSupport.swift). Do not copy code across repos.
- windows-temp-sweep (debt, ruled Oct 16, never built): the janitor removes a session's
  %LOCALAPPDATA%\Temp\claude<project><session id>\ folder once its transcript has been idle 24
  hours; no transcript found means keep. Red cases are in the debt. 17 GB was found on Oct 16.

## Batch 4. Cull the guard, part 2 (c23). Needs the Mac.

On the Mac: `python3 lint/guard_log_report.py --all-rules --days all`. Join that count with the
Windows count of Oct 22. Bring the list for gh-api-method and ln-over-directory to the owner
(stop point). Delete only what the owner names, with code and tests. On Windows: park it.

## Batch 5. Kill guard knows a lane's left-behind server (c27). Mac only.

Its brief (c27, kill guard session tag) comes from the owner when this batch starts on the Mac.
On Windows, park it and say so.

## When the goal is done

Report per the report rules, plus the four pace numbers per batch, and the total. List anything
parked and why.
