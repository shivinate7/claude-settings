# A PR may merge onto a red main; UNKNOWN still refuses

## The ruling

Owner ruling Q5 v (chat, 10:42 CST Nov 20, 2026): "PRs may merge onto a red main. The red becomes the top lane at once (revert or fix). The merge tool prints main's red tests on each merge, so a new break shows as a new name. stable still moves only on green."

- A PR may merge onto a red main. Its own head still needs a green run (rule `git-never-merge-failing-ci`).
- A merge onto a known red prints one line, `red_line` in `merge/merge.py`. It names main's red checks, the run ids and the failing tests that the red jobs' logs name (read through `Host.failed_lines`). A new break shows as a new name. A log that cannot be read in full says so, and the tests that were read still print.
- The red becomes the top lane at once: a revert of the breaking merge, or a fix. Neither needs a flag on a known red. A fix merges like any PR.
- A reason flag beside a known red lifts nothing. The merge echoes it and writes no `Reason flag` line.
- A lane-lint PASS lifts no pending head while main is red.
- `stable` moves only on green (decision `stable-branch`).
- Cost of the line: on a red main only, one jobs read and one log read per failed job of each red run (unmeasured). Nothing on a green main.

## Rulings Q5 v replaces

Each ruling below stays on record. Q5 v replaces it.

- Owner ruling 2026-11-17 09:20 CST (approved option, relayed by the consultant): a fix also merges onto a red main when it touches the failing test or its code, and its own run is green on the red test (route `fix_proven`). The same day's case was a flaky test file the breaking merge did not touch. Q5 v replaces it: a fix merges like any PR.
- Owner ruling Q3 i (when the brake on a red main lifts), 2026-11-12 09:46 CST, relayed by the coordinator at 09:50 CST: "a red main stops merges only until the revert merges." Q5 v replaces it: a red main stops no merge.
- Owner ruling 745 b (`own-745-b-resume-at-revert`, page item 745, pick b), 2026-11-13 13:20 CST, against the triage recommendation (a): after a red main, merges resume when the revert merges, with the revert's own run still going. Q5 v replaces it: no merge waits on a revert.
- Ruling ow-29 (`ow-29-q-max-past-rates-a`, item 622 b, 2026-11-12 14:17 CST), which restated the 09:46 CST answer to Q3 i. Q5 v replaces it.
- Owner ruling 746 b (`own-746-b-off-blamed-paths`, page item 746, pick b), 2026-11-13 13:20 CST, against the triage recommendation (a): while main is red, a lane that touches none of the blamed paths may merge. Q5 v replaces it: any PR may merge onto a red main. The blame step (bisect) that the ruling named was not built when written. Unsettled: the ruling places that step in PR #3152, act 3, and History names PR 2889.

## UNKNOWN still refuses

Unknown never reads clear. The merge refuses while main reads UNKNOWN. UNKNOWN covers:

- a failed read of the workflow files, the runs or the jobs;
- a cancelled run with no red job, unless the cross-group clear below clears it;
- a re-run still going (`run_attempt` above 1, not completed);
- a cancelled or running run beside a red that a merged revert would lift.

The way out is `--base-red-ok "<reason>"`. It lifts an UNKNOWN read, and never a known red. It is a reason flag, like `--undo-check-unknown-ok`, not the owner's `override`. Claude may type it with no owner present (owner ruling, Cockpit item 178 a, 2026-11-03 22:31 CST: "Claude may type both, with a logged reason"). Use it for an unknown read whose cause the reason names. The tool prints the verdict and `--base-red-ok, reason: <reason>`, and writes `Reason flag: --base-red-ok: <reason>` to the merge commit message. A blank reason lifts nothing.

## Revert lift

A revert of the breaking merge lifts the red once its tree is proven. The tool then reads main green (`revert_proven`), so the red line stops. The lift holds for later merges that land above the revert. It stops when a red run sits on or above the revert's landing commit.

Owner ruling 823 b (`own-823-b-revert-merge-lifts-red`, page item 823, pick b), 2026-11-14 15:04 CST, with no note: a revert merged with its tree already proven lifts red main. The owner chose it knowingly, since the option widens the rule. Q5 v replaces its brake: no merge waits on the lift. Accepted cost (ruled): a revert that does not fix the failure reads clear until the next full run. Options a and c are not chosen.

Without the lift (a revert whose tree is not proven), the red clears when the revert's own push run on main is green and ran the suite. A green run with no suite is no verdict (the empty-run rule under the red-main check).

Design readings for the lift. The lane chose these. They are not rulings.

- R1, the proof uses no skipped run. It takes no push-skip or scope evidence. Ruling 812 a (`own-812-a-judge-suite-runs`, page item 812, pick a, 2026-11-13 23:38 CST) drops that cover signal.
- R2, the lift reads the commits from the blamed merge up to main's head, which already holds the revert. It lifts only when all of these hold:
  - The facts the red verdict leaves (`base_facts`, data, not the printed text) show exactly one red run. No cancelled, unknown or other red run sits beside it. They name one blamed breaking merge by its full sha, and main's head as the head of the newest run read.
  - The walk from the blamed sha to main's head, any parent, holds at most 200 commits (`REVERT_WALK_MAX`). A longer walk is not proven.
  - Exactly one commit in the walk says `This reverts commit <full blamed sha>`. That is the revert.
  - The landing commit is the oldest first-parent commit that is the revert or has it in its history. No commit in the walk reverts the revert or the landing commit.
  - The landing commit's subject names pull request N (`Merge pull request #N`, or `(#N)` at the end). Its tree equals N's head tree, and N's head checks are green, read through `Host.head_state`, the one home for check reads.
  - The red run sits on the blamed merge or between it and the landing commit. A red run on the landing commit or above it, or on a commit outside the walk, refuses the lift.
  - A missing, pending or red check, or no PR found, is not proven. The verdict stays red. A first run still going is not judged until it completes, so it does not make the verdict UNKNOWN.
  - The merge tool lands a merge commit by default (method `merge`, `MERGE_DEFAULTS` in `merge/merge.py`), so the revert sits on the second parent of its landing merge. The walk reads every parent for that reason.
- R3, a re-land (a revert of the revert) names the revert's sha, not the blamed one, so it gets no lift and main stays red. A first red that names no blamed merge gets no lift.
- R4, a failed or unreadable read is unknown. Unknown refuses. It never clears.
- R5, the preview line and `--confirm` print one verdict. The lift is made in one place, and both read it.

## Terms

- A breaking merge is a merge after which main's newest finished run is red.
- A revert PR is the lane PR that undoes the commit of a breaking merge. It merges as an ordinary lane PR. A known red needs no flag.
- Owner ruling Q4 g (how a revert merges), 2026-11-12 09:46 CST, relayed by the coordinator at 09:50 CST: a revert is an ordinary lane PR, merged with `--base-red-ok`. Q5 v replaces that flag part: a known red needs no flag. There is no `merge --revert`, and none is added.
- History: act 3 of R42 part 2 is pull request 2889, merged as commit f1b8031f.

## The red-main check

The merge tool reads main's latest completed run, job by job. A known red prints `red_line` and the merge goes on. An UNKNOWN verdict refuses. The preview prints the verdict on its `<base> run:` line, with the detail and `red_line`.

- Judged: per workflow file and per event group, on the base branch. The groups are in one file, `actions/ci-alarm/events.json`, which the CI alarm reads too. Its keys are the judged events. Its values are the groups. `push` and `workflow_dispatch` (`gh workflow run`, the tool's own remedy) form one group. `schedule` is its own group. For each file and group, the newest completed run decides, except an empty run (the next bullet). So a green push or dispatch run that ran a check clears an older red push or dispatch run. A newer schedule run clears an older red schedule run. A newer first run still in progress waits its turn. A re-run in flight is not: GitHub keeps the run id and sets `run_attempt` above 1, and the run under it may be red. So when the newest run of a file and group is a re-run not yet completed, that group is UNKNOWN, never green. The UNKNOWN refusal says to wait for the re-run to finish, then run again. A run of any other event, such as a Pages build, is not judged. Runs are keyed by workflow file, not by name, so a rename inside the file keeps one verdict. A run whose workflow file is gone from the base is not judged, because no new run will ever replace it. One page of 50 runs is read. A group with no run on that page is not judged.
  - An empty run with no evidence is no verdict. A completed `success` run of the push group (push or dispatch) is empty when no job of it concluded `success` except the bookkeeping jobs `scope`, `push-skip` and `nightly-skip`. A push can run no check: `push-skip` skips the whole run. `ci-scope.sh` sets every scope flag on for a push with no proven base, and for a schedule or a dispatch. A push whose base is proven (a full sha that is an ancestor of its head) reads its diff like a pull request, so its flags can go off (decision `push-skip-on-proven-tree`). So a push run can have every flag off. An empty run with no evidence says nothing about an older red run. An empty run counts as a verdict only with evidence: its `push-skip` job is `success` and its `scope` job is `skipped`. That is the path where `push-skip.py` found the push tree equal to a `batch-*` pull request head whose `all-jobs-passed` passed. Until the step that builds ruling `own-812-a-judge-suite-runs` (a skipped push run reads green only with a green pull request run of its tree behind it) lands, `clear_rule.py` still counts such a run as a verdict. Only a push run can carry it; a dispatch runs no `push-skip` job. An empty run with no evidence is skipped, and the group's newest run that is not empty decides, so an older red run stays red. A group with no such run on the page keeps its newest run. A schedule run is judged as it is. The one home of the test is `actions/ci-alarm/clear_rule.py` (`empty_without_evidence`), which the CI alarm calls too. A failed jobs read of a candidate is UNKNOWN. Ruling: owner, 2026-11-12 21:44 CST, relayed by the coordinator at 21:46 CST.
  - A failed run R with at least one red job is cleared by a run N of another group of the same workflow file. All of these must hold:
    - N is newer than R.
    - N is the verdict run of its own group: its newest completed run, or when that run is empty with no evidence, the newest run that is not.
    - N's conclusion is `success`.
    - Every job name in R that may run in N appears in N, compared exactly, with conclusion `success`. A skipped job in N is not a pass. A job of R that is not red in R may be left out. It is left out when its job-level `if:` has a top-level `&&` conjunct `github.event_name == 'X'`, X not N's event, so it cannot run in N. The one home of this rule is `actions/ci-alarm/clear_rule.py`, which the CI alarm calls too. So a newer green push run that ran those jobs clears a red nightly, because `all-jobs-passed` and `ci-done` are pull_request-only. An empty push run clears nothing. A red job is never left out. A test inside `||`, a `!=`, an `if:` that cannot be parsed, or a job name that maps to no job keeps the job needed. A name that maps to two jobs maps to none. The file is read at N's head, one read per candidate N, and only when N passed every red job of R. A red job that N lacks or did not pass is red with no read. A failed read is UNKNOWN. Ruling: owner, 2026-11-04 15:21 and 15:27 CST, in chat to the coordinator.
  - Otherwise the groups stay separate. A green run of one group never hides a failed run of another. Reason (roadmap step `ci-alarm-reads-by-event`): two events can run different job sets, so a green nightly must not clear a red push whose jobs it did not run.
  - A cancelled R with no red job is cleared by such an N too, when R's commit is older than main's head. That reads as: N's `head_sha` differs from R's. Runs on main start at its head, and N is newer, so R's commit is no longer the head. No extra read is made. Here each job R ran (conclusion not `skipped`) must be in N, compared exactly, with conclusion `success`. Each job R skipped must be in N by exact name, with any conclusion. A cancelled R with no jobs stays UNKNOWN. A cancelled R on main's head stays UNKNOWN, unless a re-run of it passes.
  - No other run is cleared across groups. A run that ended `failure` with no red job stays red, as the "did not succeed" bullet below says: no jobs (`startup_failure`), jobs that all passed, or only cancelled or skipped jobs. A cancelled N, or one in progress, clears nothing.
  - The CI alarm (`actions/ci-alarm/alarm.sh`) follows the same rule for a red run, so it opens no issue for a run the merge tool calls clear. It never alarms on a cancelled run.
- Red: a job whose conclusion is `failure`, or any value GitHub adds later (`Host.classify`). A job cancelled at its cap (timed out), a cancelled job and a skipped job are not red.
- A run that did not succeed and has no red job: a timed-out job explains it, so it is not red. A cancelled run is UNKNOWN, unless the cross-group clear above clears it. The UNKNOWN refusal, the unknown detail and the preview line name the run. They name its own re-run, `gh run rerun <id>`, only when its `head_sha` is the head_sha of the newest run on the page read (any status, any judged event). Runs on the base start at its head, and a re-run tests the run's own commit. A cancelled run on an older commit keeps its line with no remedy. A red verdict names a cancelled run beside it the same way. A run with a red job and a re-run in flight get no remedy. It is never swapped for an older run: on the base, `judge_runs`'s twin rule would reach across commits. Any other conclusion is red, such as `startup_failure` from a broken workflow file that runs no job. The tool sees a failed run and no reason for it, so it treats the run as red.
- The preview's detail, and a refusal beside a red, name each red job, the run id, its head and its URL.
- Unknown: a read of the workflow files, the runs or the jobs that fails is UNKNOWN, never green or red. Unknown refuses, as the silent-undo check does.

Why: Oct 13 to 14, 14 main runs in a row were red, and batch merges kept landing on top. Main's latest run was not green for 311 of 366 hours. The refusal that followed was written so that each merge onto a red main would stop hiding the next defect and lengthening the repair lane (roadmap step c166, from plan c95-step2-escapes, option C's brake). Ruling Q5 v replaced that refusal. The red line now names each new break.

- Risk: named incident, the Oct 13 to 14 red episode. Landed 2026-10-28.
- Risk: named incident, 2026-11-02, joyous #68. Joyous `links.yml` schedule run 40323547948 (Oct 26, on old main `eb7800528`, job `readme-links`: failure) blocked every joyous merge, although dispatch run 41397308885 on current main `53b50465e` ran the same job, `readme-links`, and passed.
- Risk: named incident, 2026-11-02 06:18 CST, batch 65 (PR #1090). Schedule run 41434991174 on old main `4477f7e3` was cancelled with no red job. Main read UNKNOWN, although push run 41437045856 on main's head `07f855dc` passed every job it ran. A re-run cleared it. The cancelled-R clear above fixes this shape.
- Risk: named incident, 2026-11-01 20:28 CST, q_max PR #1011. Dispatch run 41377928751 of `browser.yml` at `5ab167f2f` was cancelled with no red job. Its commit is older than main's head, but no newer completed run of that file exists. So main stays UNKNOWN by this rule: a re-run, or `--base-red-ok`, is the way out.
- The owner's `override` prompt does not reach the red-main check. The override check has one home, `refuse()` in `hooks/guard_core.py`. The merge tool runs after the guard, and decision owner-override lists the `bin/merge` shim as outside every override. The tool also cannot tell a session's run from its agent's, and a one-act override must not reach an agent.
- Check: `merge/test_merge.py`, class `RedMainBrake` (its empty-run cases too) and `GhHalf.test_a_red_main_run_read_through_gh_merges_the_merge`. The CI alarm's groups and its empty-run cases: `actions/ci-alarm/test_action.sh`. The empty-run test: `actions/ci-alarm/test_clear_rule.py`.
- Cost of the revert lift: on a red verdict naming one blamed merge, one `git diff`, one pull request files read, two fetches (one in the base read, one in `fetch_pr_head`) and one `merge-base`, one `Host.check_state` read for each red job of the run (each a checks read, `Host.checks`), and one `Host.head_state` read (unmeasured). The lift (`revert_proven`) makes at most 9 git calls on a full pass, fewer on an early refusal (unmeasured): the head, the ancestor check, the message walk, the first-parent list, two ancestry lists, the subject and two trees. It makes at most 7 GitHub calls on a full pass, at one page per list (unmeasured), fewer when a check fails early. The GitHub calls are `Host.pr`, the check runs and commit statuses that `Host.head_state` reads (one call per page each, unmeasured), and two workflow run lists: one that drops a superseded run, one for the head's own runs. Unless `merge.requiredChecks` is a list, the ruleset read is added, and the classic branch protection read when no ruleset names a check. Each call starts one short process (unmeasured). No long-lived process starts, no file written, no timer.
- Cost: at each `--confirm` and each preview, one `git ls-tree` of the base, one `actions/runs` read (one page of 50), and one jobs read for each judged run that did not succeed (unmeasured). A newest green run of the push group costs one jobs read, and each empty run with no evidence above an older run costs one more (unmeasured). A cross-group clear adds one jobs read for N, made only when R has a red job or is cancelled, and a candidate N exists (unmeasured). The CI alarm adds one jobs read each for R and N per failed group that has a candidate N, and the same empty-run reads of the push group (unmeasured).

## Main's run verdict for a merge

A session reads the verdict of main's run for its merge with `merge --main-run <sha>`. `<sha>` is the commit its merge put on main. The tool prints one line, `main run <sha9>: <outcome>. <detail>`. It stands alone, takes no lock and writes nothing.

- A red is blamed only on a re-run. A first-attempt red is a first red. A red again on its re-run is a new break, and the line names that run's commit and pull request.
- A red run on an earlier red: only a check name or failing test the earlier red lacked is new. Nothing new reads carried.
- The run before is the newest earlier push run of the same workflow file and event group that is not cancelled, skipped, neutral or empty. A run before still going reads unknown.
- green: the run ran its suite and passed. Nothing is asked.
- no verdict: the run ran no suite. The line reads emptiness alone, with no push-skip evidence, and says nothing about main.
- carried: the red is not this merge's. A carried line marks `not re-run` each red job the run before had and this run skipped.
- first red: the red becomes the top lane at once, a revert or a fix, the session's pick. Nothing is blamed yet. The line names the command that re-runs the failed jobs.
- new break: the red becomes the top lane at once, a revert or a fix, the session's pick.
- cleared: the revert's run is green and re-ran every job that was red in the run before. The red is lifted. A revert line counts only at a line start (`REVERT_OF_LINE`); `read_lanes` takes it anywhere in a message (`REVERT_OF_ANYWHERE`).
- did not clear: the revert's run is red, or green with a red job not re-run. The base stays red.
- unknown: a failed read, a run still going or cancelled, no push run of the commit on the newest page, or a red run with no earlier run to compare (a green run with none reads green). The tool exits 1. Run it again. Unknown never reads green, first red or carried.
- Cost: one runs read, a jobs read for each run judged, and a log read per failed job of each red run read (unmeasured). No file, process or timer.

Check: `merge/test_merge.py`, class `MainRunVerdict`.

Kind: process
Home: merge/merge.py
