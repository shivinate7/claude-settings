# c95 step 2: judge it by escapes, not by green main runs (plan, no code)

Step c95, "CI at milestones". Step 2 is q_max's shape: quick checks per branch, the full suite on main only. Shiv rejected the green-main-run bar of plans/c95-step2-bar.md (waiting page item 34, Oct 28 02:36 CDT: "not the correct approach to judge off of"). This plan tests a new basis: escapes, the reds that only the full suite catches.

## Data and how it was read

- Read Oct 28 with `gh api repos/shivinate7/claude-settings/actions/runs` (workflow `gates`, created Oct 13 00:00 CDT to Oct 28), then `runs/{id}/jobs` for every run that was not skipped (551 runs), then `commits/{sha}/pulls` for each main head.
- A red run: a run with a failed step, or a job cancelled at its cap ("timeout"). A run cancelled by a newer push on its own branch is not red.
- The root cause of each main red comes from its job log (`FAIL` lines) and the commit that fixed it. Branch reds that cite "likely" share a suite and a failure pattern with a main red whose log was read; their own logs were not read.
- The scripts and raw JSON stay in the session's scratchpad. They are not tracked.

## The quick set (c95 did not define one; proposed)

- **Quick set (per branch):** the Linux jobs: `scope`, `gates` (lints and the Linux suites), `gates-guard`, `gates-shoot` and `gates-mutate-guard`, scoped by `ci-scope.sh` as they are now.
- **Full suite (main only):** the quick set plus every Windows and macOS job: `gates-windows*`, `pointer-windows`, `gates-macos` and `shell-macos`.
- **On demand:** a lane can dispatch one platform job (`workflow_dispatch`). Two lanes needed a Windows-only red proof (`3da7b57`, install-set test; `68f1b04`, install-no-gap test). The quick set cannot show that red.
- The step 2 shape already exists for two suites. The Windows guard and merge suites run a "Windows slice" on a PR and the full suite on push (gates.yml, `GUARD_TESTS` and `MERGE_TESTS`). Their escapes are measured below.

## Main: 161 full runs, 33 green

| Class | Runs | Would the quick set have caught it on the branch? |
|---|---|---|
| Timeout only (no red step): `gates-windows-merge` at 20 min in most of them, then `gates-windows-guard`, `-rest`, `gates-macos` | 94 | Not a defect. Step 1a (#715, no timeouts) and the shard jobs fixed these. |
| Red step, with the same job green on the batch PR | 29 | No. The PR's larger set missed it too. |
| Red step, with the job skipped on the batch PR by `ci-scope.sh` | 5 | No. Most fall inside an episode that was already red. |

The 34 red-step runs, by episode:

| Episode | Main runs | Failing job: test | Cause (from the log) | Kind |
|---|---|---|---|---|
| Oct 13 06:18 to Oct 14 21:49, heads 0f970f8 to 4ef686a | 14 | `gates-windows-guard` (full suite on push; the PR ran the slice), and `gates-macos` twice: guard suite | "session-log: 1 MB id sanitized in under 100 ms (took 102 ms)"; "rm-var: 64000 bindings judged in under 2 s CPU (2.18 s)" | timing assert |
| Oct 14, e50acdd and e30f174 | 2 | `gates-windows-rest`: SendMessage state | subprocess `TimeoutExpired` | timing |
| Oct 16 87663d9; Oct 18 0100418 | 2 | `gates-windows` and `shell-macos`: install.sh checkout detection | swap1sh and lock1sh: "install B landed its guard file 11 s before A exited" | timing |
| Oct 18 2ff288b (push and nightly) | 2 | `gates` (Linux): hook catalog check | Both batches were green alone. The merged pair was red. | merge interaction |
| Oct 19 960cc63 | 1 | `pointer-windows`: install-set test (skipped on the PR by scope) | Child output read while it was held open. Fixed Oct 27 (c6badc1). | real, Windows-only |
| Oct 23 ad6074f, cd638d7, d04a4cc | 3 | `gates-macos`: guard suite | "load-brake: read_load left cpu_pct unread on darwin" | unknown |
| Oct 26 bf084df | 1 | `gates` (Linux): records index; plus the Windows guard suite | "debts: link ../debts/merge-deletes-dropped-lane.md does not resolve" | merge interaction |
| Oct 26 b1e5a6d and 853b512 | 2 | `gates-windows-merge` shards 1 to 5: git-half suite (full on push; the PR ran the slice) | Git prints worktree paths with forward slashes. Fixed 9ade543. | real, Windows-only, **slice escape** |
| Oct 27 2ad85de to b031394 | 5 | `gates-macos`: stall watch | "23a. a log that grows each second: no". Fixed 53dc1bd (decide a stall on a fresh sample). | timing |
| Oct 27 835cde5 and 2ca8925 | 2 | `gates-windows-rest`: janitor triggers, janitor sweep | "parallel writers lose no row (writers=24)": lost one row | timing or race, unknown |

- On main: timing and load asserts 24 runs; unknown 4; real platform defects 3 (2 defects); merge interactions 3 (2 defects).
- The quick set would catch none of the 34. The current PR set caught none either. Only a run on the merged main head catches a merge interaction.
- The slice already escaped twice: the full Windows guard suite (14 runs, about 40 h red, timing asserts) and the merge git-half suite (2 runs, a real defect).
- Main red did not stop merges. The latest main run was not green for 311 of the 366 hours. A red step accounts for 55 of those hours; timeouts account for the rest.

## Branches: 390 runs, 131 with a red step

| Class | Runs | Quick set |
|---|---|---|
| Only Linux jobs red | 75 | caught |
| Windows or macOS red too, and the same suite red on Linux | 10 | caught |
| Linux red, and a different Windows- or macOS-only suite red too | 15 | Run red, but the platform defect hides behind the Linux red. It escapes if the fix lane fixes only the Linux suite. |
| **Only Windows or macOS red** (Linux green 22, Linux cancelled by a newer push 9) | **31** | **missed: these reach main under step 2** |

The 31 missed runs, by suite:

| Suite (job) | Runs | Heads | Cause | Kind |
|---|---|---|---|---|
| install.sh checkout detection (`gates-windows`, `shell-macos`) | 7 | 517ef25, 55902eb, 197ae92, 9aa6cc4, f900567, b592eb7, 2c24b0a | 2c24b0a: a `case` pattern inside `$( )` breaks bash 3.2, fixed 3c30594. The other 6 are likely main's swap1sh and lock1sh timing. | 1 real, 6 likely timing |
| Guard suite (`gates-windows-guard`, `gates-macos`) | 5 | 25e4671, 6daa741, a848b8f, 420b9e2, 2df2ca4 | 2df2ca4: the take() race of step c62, fixed 1cab940 (one-act pass is atomic on Windows). The other 4 are likely timing. | 1 real, 4 likely timing |
| Install-set and install-no-gap tests (`pointer-windows`) | 6 | 2b82b7c, 6ee2803, b344314, 247150d, 3da7b57, 68f1b04 | A child's output was read while it was held open. Fixed 42bde13 and c6badc1. 3da7b57 and 68f1b04 are deliberate red proofs. | 1 real (test harness) |
| SendMessage state, plus install-no-gap and janitor sweep (`gates-windows-rest`, `pointer-windows`) | 3 | 0d298c7, bb1e76f, 8e94a83 | likely main's subprocess timeout | likely timing |
| Stall watch, stall watch stop (`gates-macos`, `gates-windows-rest`) | 4 | 05ed05d, 8e65ee0, c57bdbb, 8945ef9 | main's stall-watch timing, fixed 53dc1bd | timing |
| Verdict runner (`gates-windows-rest`) | 2 | f1d6e63, decb6e2 | Swift Testing fixture marks broke under the Windows code page. Fixed c57bdbb. | real |
| Merge git-half (`gates-windows-merge`) | 1 | 9c52bb2 | cp1252 piped stdout, fixed 564d197 | real |
| Janitor sweep, CI wake-up, stop-hook gate (`gates-windows-rest`) | 3 | 63f2bdb, 2142a5b, 9f26c53 | logs not read | unknown |

- In 15.5 days, the quick set would have sent **5 real platform defects** from branches to main: bash 3.2, the c62 race, the read-while-open harness, verdict encoding and cp1252. The 15 masked runs hold at least one more: the Windows stamp-engine hang of step c158 (b2a90e8). The cp1252 defect in 9c52bb2 is another; its Linux job was cancelled.
- The quick set would also have sent about 20 timing reds to main. Most of them already fail on main today.
- Platform-only defects run at about **3 a week**. Each costs a red main and a repair lane.

## Minutes and wait that step 2 saves (last 7 days, Oct 21 to 28)

| | Linux | macOS | Windows | Total |
|---|---|---|---|---|
| Branch runs (PR and dispatch), runner-min | 5,161 | 5,585 | 7,184 | 17,930 |
| Main runs, runner-min | 1,972 | 2,157 | 5,292 | 9,421 |

- Step 2 removes the branch Windows and macOS minutes: **12,769 of 27,351 runner-min a week (47%).**
- Wait saved: almost none. The Linux `gates` job is the long pole. Across 118 green branch runs, the median time to the last job is 25.2 min with every job and 24.4 min with Linux alone (p90: 31.6 vs 29.4).
- macOS queue: the median wait is 0.1 min, but p90 is 3.0 min and the worst was 54 min. A macOS job waits for a free runner when too many run at once.
- Money: unmeasured. claude-settings is a public repo. GitHub bills standard-runner minutes on public repos at $0 (GitHub's published pricing; not checked against shiv's bill, because account endpoints return 403 from this session). If the bill shows claude-settings minutes, the pick below flips.

## Options for judging step 2

| Option | Basis | Gains | Loses |
|---|---|---|---|
| A. Raw escape count (the hypothesis as written) | Allow step 2 while reds that only the full suite catches stay under N per window | Measures the one risk step 2 adds; can be read from past runs now, with no streak to wait for | Timing flakes outnumber real defects about 4 to 1, so the count measures test noise more than risk |
| **B. Priced escapes (pick)** | Count only root-caused platform defects that reach main, read from the fix commit as above. Weigh them against what the cut saves: minutes × price, plus wait. Take step 2 only when savings exceed escapes × the cost of a repair lane. | Judges the trade itself; ports to every repo (c95's "port at each repo's visit") with that repo's own price; flakes can't move it | Needs a price for a repair lane (proposed: one lane, about 1 h of the session) and the real minute price per repo |
| C. Main red-hours | Step-failure hours on main per week, before and after the cut, with a brake: no batch merges onto a red main | Measures what shiv feels: a broken main and fix lanes. The brake stops a repeat of Oct 13 to 14 (14 runs red, merges kept landing). | A lagging measure: it shows harm only after the cut. It needs a new merge-gate rule. |
| D. No step 2 here; fix the timing tests first | Leave the branch set as it is. First make the timing and load asserts robust (24 of 34 main reds). Then judge by B. | Main goes green for real, so step 3's milestone runs mean something; no new escapes | The 47% of minutes stays, which costs nothing if the $0 price holds |

## Pick: B, which today says hold step 2 in claude-settings and do D's test fix

- The hypothesis holds in part. Escapes are the right risk. A raw count is wrong, because timing flakes are about 80% of platform-only reds.
- B with today's numbers: about 3 real defects a week reach main, to save about 12,800 runner-min a week (about $0 here, unmeasured) and under 1 min of wait. Step 2 loses here.
- In a private repo (q_max, or any repo where minutes cost money), B can pass. There, run this same read with that repo's price.
- Whatever shiv picks, two findings stand:
  1. The timing and load asserts (the 100 ms sanitize, 2 s CPU rm-var, 11 s install lock and stall-watch cases) cause most main reds. Fix them as tests. Never skip them.
  2. Main red does not stop merges, so an escape costs hours, not minutes. Option C's brake protects every step: 1, 2 and 3.
- Cost of B as a check: one `actions/runs` read, one jobs read per red run and one log read per new red, at each batch merge, on demand. No timer and no log written.

## Home and next

- Deferred, why: the basis is shiv's to pick (item 34). The question: B, which holds step 2 here and runs D's test fix (recommended); A; C; or D alone? Also: does shiv's GitHub bill show claude-settings minutes?
- Until then: no cut. The orchestrator moves the ruling into c95's `note` and the job-caps decision.
