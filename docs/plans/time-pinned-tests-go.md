# Time-pinned tests go: the plan

This plan turns the time-pinned tests into outcome checks. A time-pinned test passes or fails
on the speed of a clock or a runner. It is the working plan for roadmap step time-pinned-tests-go,
the step that ends the time-pinned tests and with them the stopgap job caps.

The finder and the per-repo counts are in `docs/plans/time-pinned-tests.md`. This file holds the
lanes.

Written 2026-11-18 08:47 CST. Base: `origin/main` at commit `6e6b498a35`. "Measured today" means
the finder ran on that base on this date.

## Rules that govern the lanes

- Owner item 345 (owner, 13:00 CST Nov 7): keep the hang guards. A timed test uses a synthetic clock.
- Decision `test-practices`, rule P5 (the same owner ruling, 13:00 CST Nov 7): a timed test is
  allowed only when it is needed. A hang guard sits well above the measured run. A date or a
  time-zone offset is a real clock too, so inject the clock.
- Decision `test-practices`, rule P6 (owner goal v6, 20:01 CST Nov 17): a flake is a defect report.
  An unfixable flaky test is deleted with its reason, never given a wider limit, a sleep or a retry.
  A deletion keeps the P9 proof or a debt.
- Decision `test-practices`, rule P9: delete or loosen a test only with proof that coverage holds.
  Each removed case gets a mutant that goes red.
- Decision `ci-job-caps` (CI job caps): the caps are stopgaps until the time-pinned tests are gone.

## Measured today

- Finder on main: 429 hits in 111 files. Sleep 33, elapsed-assert 4, test-cap 0, wait-cap 392.
  One file is unread: `merge/test_merge.py`, over 1,000,000 bytes.
- The finder misses `assertLess(<x>.elapsed, N)` in `lint/test_wait_pid.py`. That file has four
  such asserts. The finder lists none of them.
- Sleeps on main: 16 sit in the five files that lane 2 names. Seventeen more sit in other files.
  Lane 2 lists them.
- Stopgap hits: 72 in 17 files. The table is in lane 5.
- Branch `lane/timing-tests-guard`: the brief says 3 sleeps. A `git grep -c "time\.sleep\("` on that
  branch finds more lines, for example 34 in `janitor/test_sweep.py`. Unreconciled. Lane 2 runs the
  finder on that branch before it counts.

## Lanes

Five lanes, in this order. Lane 1 runs first. Lanes 2 and 3 follow it. Lane 4 needs lane 2. Lane 5
waits for lanes 2, 3 and 4.

| Lane | Work | Waits for | Done when |
|---|---|---|---|
| 1 | Finder fixes in claude-settings | none | Each fix goes red first, on the old finder. |
| 2 | claude-settings remainder | lane 1 | The gate mode prints sleep 0, elapsed-assert 0 and unread 0 on main. |
| 3 | Child repos: q_max, banchi, degen, joyous, mailaudit, ios-adblock, and home | lane 1 (gate mode) | Each repo's finder counts read zero for sleep, elapsed-assert and unread. Each conversion and deletion has its proof. |
| 4 | Keep it at zero: CI runs the gate mode | lane 2 | One shared check in claude-settings runs the gate in CI and goes red on a new sleep. |
| 5 | Caps: re-measure, drop the stopgaps, rewrite `ci-job-caps` | lanes 2, 3 and 4 | Each cap matches a measured figure. No stopgap remains. `ci-job-caps` is rewritten and a reviewer reads it. |

### Lane 1: finder fixes (claude-settings)

Work in this order. Each fix goes red first.

1. Merge PR 2975 first. It is the finder's keep marker.
2. Fold in step finder-deadline-poll. A poll inside a deadline loop lists as a wait-cap.
3. Do roadmap step time-pinned-helper-read. Its text is not in this checkout.
4. Do roadmap step finder-bare-date-cases. Its text is not in this checkout.
5. Make the finder read files over 1,000,000 bytes. `merge/test_merge.py` is the one unread file.
   The `main` function in `lint/find_time_pinned.py` prints the UNREAD lines.
6. Add a gate mode. It fails only on sleep, elapsed-assert or unread. It does not fail on wait-cap
   or test-cap. This plan proposes the flag `--gate`. The builder may choose another name.
7. Catch `assertLess(<x>.elapsed, N)`. The Python scanner is `scan_python`, which uses
   `assert_parts`. Today the finder misses this form in `lint/test_wait_pid.py`.

### Lane 2: claude-settings remainder

- The five named files hold 16 sleeps on main:
  - `janitor/test_sweep.py`: 8
  - `janitor/test_session_end_sweep.py`: 4
  - `merge/test_merge_beat.py`: 2
  - `hooks/test_mutate_shared.py`: 1
  - `hooks/test_sendmessage_state.py`: 1
- Seventeen more sleeps on main sit in other files. The done test covers them too:
  - `hooks/test_stall_watch.py`: 5
  - `tests/guard/s05163-kill.py`: 3
  - `mods/plain-diff/plain-diff.test.mjs`: 3
  - `tests/guard/s25798-page-item-design.py`: 1
  - `mods/session-board/session-board.test.mjs`: 1
  - `mods/desktop-statusline/desktop-statusline.test.mjs`: 1
  - `merge/test_lane_lint.py`: 1
  - `lint/test_wait_pid.py`: 1
  - `lint/test_sim_lease.py`: 1
- The three sleeps on branch `lane/timing-tests-guard` come from the brief. They are unmeasured
  here. Run the finder on that branch first.
- Elapsed-asserts: every one the gate lists. That includes the four in `lint/test_wait_pid.py`
  once lane 1 catches them.
- Each conversion waits on a marker file or a condition, never a fixed sleep. Each timed assert
  reads an injected clock (P5). Each conversion gets a mutant that goes red.
- Done when the gate prints sleep 0, elapsed-assert 0 and unread 0 on main.

### Lane 3: child repos

- Six child repos run in parallel, each under its own coordinator: q_max, banchi, degen, joyous,
  mailaudit and ios-adblock. Home runs in its own lane.
- The counts from 2026-11-02 are in `docs/plans/time-pinned-tests.md`. They are unmeasured here.
  Each repo's lane runs the finder on its default branch first.
- degen: the assert in `tests/server/test_fetch_counter.py` changes to an injected clock (P5). The
  finder hit there reads a timestamp for its value, not for speed. So the change follows P5's rule
  on dates, not a speed fix.
- Each conversion gets a mutant that goes red. Each deletion gets the P9 proof.
- Home: the per-repo list does not scan home, and it holds home's lane. Input Needed asks whether
  that hold lifts.

### Lane 4: keep at zero

- Re-scope step test-no-fixed-sleep (no fixed sleeps in tests) first. Its "wall-clock wait bound"
  conflicts with owner item 345, which keeps the hang guards. The re-scoped step keeps a wall-clock
  bound only as a hang guard, with a cap well above the run.
- Then add one shared check in claude-settings. CI runs the gate mode through it.
- The check goes red on a new sleep, elapsed-assert or unread. Prove it with a mutant that adds one
  sleep.

### Lane 5: caps

1. Re-measure each job per decision `ci-job-caps`, section "How to measure again". The steps:
   - Take the newest 30 green runs per job.
   - Read `job_minutes` and `job_caps` in `merge/merge.py`. Do not write a second reader.
   - Count a cap end as a run that reached its cap, ended cancelled or failed, with no failed test step.
   - Read per-step times from the GitHub API.
   - A new job takes a provisional 60 min until it has 5 green runs.
   - `merge.deadlineMinutes` in `.github/stamp.json` stays at least the largest cap plus 5.
2. Drop each stopgap. The table below holds every hit. A code hit needs a builder. A debt or record
   hit changes with the decision it cites.
3. Rewrite decision `ci-job-caps` in place. A reviewer reads the rewrite.

Stopgap hits, from `grep -rn -i stopgap` over the repo, measured today: 72 hits in 17 files.

| Path | Hits |
|---|---|
| `docs/decisions/ci-job-caps.md` | 29 |
| `.github/workflows/checks.yml` | 28 |
| `docs/records.md` | 1 |
| `docs/debts/lane-lint-hub-cost.md` | 1 |
| `docs/debts/mutate-guard-split.md` | 1 |
| `docs/debts/windows-shards-outgrow-caps.md` | 1 |
| `docs/decisions/mutation-ci-report-and-replay.md` | 1 |
| `docs/plans/restart-plan.md` | 1 |
| `docs/plans/shared-merge-tool.md` | 1 |
| `.github/workflows/lane-touched-tests.yml` | 1 |
| `hooks/mutate_guard.py` | 1 |
| `hooks/test_call_judge.py` | 1 |
| `janitor/mutate_sweep.py` | 1 |
| `lint/check_debt_retire.py` | 1 |
| `lint/check_python_floor.py` | 1 |
| `merge/merge.py` | 1 |
| `skills/ci-hygiene/SKILL.md` | 1 |

Done when every cap cites a measured figure, every hit above is gone or rewritten, and
`ci-job-caps` is rewritten.

## Open points

- The brief says six lanes and names five. This plan holds five. Lane 3 covers six child repos
  and home.
- `docs/plans/time-pinned-tests.md` is the earlier working plan for the same step. It holds the
  finder and the per-repo counts. This file holds the lanes. The owner decides whether to fold one
  into the other.
- Lane 2 names 16 sleeps. Main has 33. The other 17 are listed in lane 2.
- The count on `lane/timing-tests-guard` is unreconciled (see Measured today).
- The per-repo list holds home's lane (lane 3).
