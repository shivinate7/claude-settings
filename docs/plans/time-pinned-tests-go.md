# Time-pinned tests go: the plan

This plan turns the time-pinned tests into outcome checks. A time-pinned test passes or fails
on the speed of a clock or a runner. It is the working plan for roadmap step time-pinned-tests-go,
the step that ends the time-pinned tests and with them the stopgap job caps.

This file holds the lanes, the finder, and the per-repo record (counts and files as of 2026-11-02),
which sits at the end.

Status: Part 1 built the finder and ran it. Part 2 is the five lanes below.

Written 2026-11-18 08:47 CST. Base: `origin/main` at commit `6e6b498a35`. "Measured today" means
the finder ran on that base on this date.

## Rules that govern the lanes

- Owner item 345 (owner, 13:00 CST Nov 7): keep the hang guards. A timed test uses a synthetic clock.
- Decision `test-practices`, rule P5 (the same owner ruling, 13:00 CST Nov 7): a timed test is
  allowed only when it is needed. A hang guard sits well above the measured run. A date or a
  time-zone offset is a real clock too, so inject the clock.
- Decision `test-practices`, rule P6 (owner, 2026-11-17 20:01 CST, consultant goal v6): a flake is a defect report.
  An unfixable flaky test is deleted with its reason, never given a wider limit, a sleep or a retry.
  A deletion keeps the proof P9 asks for.
- Decision `test-practices`, rule P9: delete or loosen a test only with proof that coverage holds.
  Each removed case gets a mutant that goes red.
- Decision `ci-job-caps` (CI job caps): the caps are stopgaps until the time-pinned tests are gone.
- Decision `test-strategy-reset` (tests prove outcomes and never fail on runner speed): each
  finding becomes an outcome check or a debt.

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
- The counts from 2026-11-02 are in the per-repo record at the end of this file. They are unmeasured here.
  Each repo's lane runs the finder on its default branch first.
- degen: the assert in `tests/server/test_fetch_counter.py` changes to an injected clock (P5). The
  finder hit there reads a timestamp for its value, not for speed. So the change follows P5's rule
  on dates, not a speed fix.
- Each conversion gets a mutant that goes red. Each deletion gets the P9 proof.
- Home: its lane is held. The hold line sits in the counts section of the per-repo record. The
  owner decides whether that hold lifts.

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
- Lane 2 names 16 sleeps. Main has 33. The other 17 are listed in lane 2.
- The count on `lane/timing-tests-guard` is unreconciled (see Measured today).
- Home's lane is held (lane 3).

## Per-repo record (counts and files, dated 2026-11-02)

### The finder

`lint/find_time_pinned.py` lists lines in test files, in four kinds:

- sleep: a real wait in a test.
- elapsed-assert: an assert that reads a clock.
- test-cap: a per-test or per-suite time limit. A hang guard that decision test-practices P5 allows.
- wait-cap: a fixed bound on a wait for a condition or a child process. Most are hang guards, which can stay. Each repo's lane judges each one.

Each count is a candidate, not a verdict. A sample read found a false alarm in elapsed-assert: a timestamp checked for its value, not for speed (degen `tests/server/test_fetch_counter.py`). The repo lane decides each one.

### Counts

Each row comes from `python3 lint/find_time_pinned.py <clone> --json`, run on a shallow clone of the repo's default branch at the commit shown, on 2026-11-02. Re-run that command to check a number. The claude-settings row is this repo's main, not a clone: `python3 lint/find_time_pinned.py . | tail -1` on 2026-11-13, at the commit shown.

| Repo | Commit | sleep | elapsed-assert | test-cap | wait-cap | Total | Files | Unread | Target (sleep, elapsed, cap) |
|---|---|---|---|---|---|---|---|---|---|
| q_max | `e8f99027` | 64 | 20 | 127 | 115 | 326 | 57 | 1 | 0, 0, 0, each wait-cap judged |
| banchi | `2e46c112` | 119 | 2 | 0 | 236 | 357 | 54 | 0 | 0, 0, 0, each wait-cap judged |
| degen | `af1d95ac` | 251 | 20 | 0 | 1075 | 1346 | 219 | 0 | 0, 0, 0, each wait-cap judged |
| joyous | `de35e993` | 1 | 1 | 38 | 1 | 41 | 2 | 0 | 0, 0, 0, each wait-cap judged |
| mailaudit | `9efe1bb0` | 140 | 1 | 0 | 178 | 319 | 30 | 0 | 0, 0, 0, each wait-cap judged |
| ios-adblock | `4d265329` | 1 | 0 | 0 | 0 | 1 | 1 | 0 | 0, 0, 0, each wait-cap judged |
| claude-settings | `fccff95e` | 32 | 8 | 0 (hang guards) | 346 (hang guards; allowed only if each cap sits well above the run, P5) | 386 | 98 | 1 | 0, 0, no target for hang guards |

- home: not scanned. Its lane is held.
- claude-settings: step c95 (make the timing and load asserts robust) fixed this repo's guard, install lock, stall watch, SendMessage and janitor timing cases by hand. It left 12 notes in `docs/debts/notes.md`. It built no finder and scanned no other repo. On main at `fccff95e` (2026-11-13) the finder lists 386 here (sleep 32, elapsed-assert 8, test-cap 0, wait-cap 346, in 98 files, 1 unread: `merge/test_merge.py`, over 1 MB). Its test-cap and wait-cap are hang guards, allowed by P5 when each cap sits well above the run; the lane checks that. That list goes to a later claude-settings lane. Pending: finder keep marker, PR 2975.

### Files

#### q_max

- `harness/tests/ai-calls-picture.test.mjs`: wait-cap 1
- `harness/tests/ai-usage.test.mjs`: wait-cap 1
- `harness/tests/bid-leveling.test.mjs`: elapsed-assert 1
- `harness/tests/bid-package.test.mjs`: elapsed-assert 3
- `harness/tests/campus-import.test.mjs`: sleep 1, elapsed-assert 3, test-cap 19, wait-cap 9
- `harness/tests/ci-changes.test.mjs`: sleep 1
- `harness/tests/dashboard-outcome-sent.test.mjs`: sleep 5, wait-cap 5
- `harness/tests/decision-refs.test.mjs`: test-cap 9
- `harness/tests/deleted-chat-send.test.mjs`: sleep 1, wait-cap 31
- `harness/tests/escalate-to-date.test.mjs`: sleep 1
- `harness/tests/family-rates.test.mjs`: elapsed-assert 1
- `harness/tests/filter-model.test.mjs`: wait-cap 2
- `harness/tests/gap-estimates.test.mjs`: wait-cap 1
- `harness/tests/itb-bid-comparison.test.mjs`: sleep 3
- `harness/tests/job-cancellation.test.mjs`: sleep 5, elapsed-assert 2
- `harness/tests/job-resume.test.mjs`: sleep 1
- `harness/tests/job-store.test.mjs`: sleep 4
- `harness/tests/large-upload.test.mjs`: sleep 1
- `harness/tests/map-picture-page.test.mjs`: test-cap 33, wait-cap 7
- `harness/tests/map-picture.test.mjs`: test-cap 6
- `harness/tests/map-skill-check-cmd.test.mjs`: wait-cap 2
- `harness/tests/map-skill-coverage.test.mjs`: wait-cap 1
- `harness/tests/map-skill-vendored.test.mjs`: wait-cap 1
- `harness/tests/mapping-batch-resume.test.mjs`: sleep 3
- `harness/tests/meaning-real-run.test.mjs`: wait-cap 1
- `harness/tests/model-smoke.test.mjs`: wait-cap 2
- `harness/tests/name-on-write-screens.test.mjs`: sleep 1, wait-cap 14
- `harness/tests/object-store-s3.test.mjs`: sleep 9, elapsed-assert 1, test-cap 41
- `harness/tests/package-drop.test.mjs`: elapsed-assert 1
- `harness/tests/pdf-triage.test.mjs`: sleep 1
- `harness/tests/pick-split.test.mjs`: wait-cap 1
- `harness/tests/plain-english-map.test.mjs`: test-cap 3, wait-cap 3
- `harness/tests/plain-english-trace-limits.test.mjs`: elapsed-assert 1
- `harness/tests/pqq-round.test.mjs`: sleep 1
- `harness/tests/probe-exit-codes.test.mjs`: wait-cap 1
- `harness/tests/probe-exit-flush.test.mjs`: wait-cap 2
- `harness/tests/q-standin.test.mjs`: wait-cap 3
- `harness/tests/races-plant.test.mjs`: elapsed-assert 3
- `harness/tests/resilience.test.mjs`: sleep 1
- `harness/tests/rfp-direct-upload.test.mjs`: sleep 1
- `harness/tests/rfp-dropzone.test.mjs`: sleep 6, elapsed-assert 1
- `harness/tests/rfp-link.test.mjs`: sleep 1
- `harness/tests/rfp-poll-visibility.test.mjs`: sleep 1, wait-cap 6
- `harness/tests/rfp-route.test.mjs`: sleep 10, wait-cap 13
- `harness/tests/rfp-uppy-client.test.mjs`: sleep 1, elapsed-assert 1
- `harness/tests/run-tests.test.mjs`: wait-cap 1
- `harness/tests/same-outputs.test.mjs`: wait-cap 2
- `harness/tests/scratch-git-env.test.mjs`: test-cap 1, wait-cap 1
- `harness/tests/server-routes.test.mjs`: sleep 4
- `harness/tests/sqlWriteTools.test.mjs`: wait-cap 1
- `harness/tests/static-load-step.test.mjs`: test-cap 4
- `harness/tests/stop-budget.test.mjs`: test-cap 9
- `harness/tests/tests-for.test.mjs`: wait-cap 1
- `harness/tests/tests-off.test.mjs`: wait-cap 1
- `harness/tests/white-sheet-export-route.test.mjs`: elapsed-assert 2
- `harness/tests/worker-claim.test.mjs`: sleep 1, test-cap 2
- `harness/tests/worktree-reaper.test.mjs`: wait-cap 1
- UNREAD `harness/browser/verify.test.mjs`: over 1000000 bytes

#### banchi

- `app/tests/boxmap.spec.ts`: sleep 1, wait-cap 1
- `app/tests/brand.spec.ts`: sleep 1
- `app/tests/button-stack.spec.ts`: wait-cap 1
- `app/tests/capture-claims.spec.ts`: wait-cap 2
- `app/tests/capture-freeze.spec.ts`: sleep 2, wait-cap 19
- `app/tests/capture-section.spec.ts`: wait-cap 14
- `app/tests/capture-undo.spec.ts`: wait-cap 4
- `app/tests/card-variants.spec.ts`: sleep 1
- `app/tests/copy-checks.spec.ts`: sleep 1
- `app/tests/cursor.spec.ts`: wait-cap 1
- `app/tests/demo-coverage.spec.ts`: wait-cap 3
- `app/tests/dispenser.spec.ts`: sleep 11, wait-cap 42
- `app/tests/dispenserRig.ts`: sleep 1, wait-cap 5
- `app/tests/empty-section.spec.ts`: wait-cap 2
- `app/tests/fulfillment.spec.ts`: sleep 1, wait-cap 7
- `app/tests/gallery.spec.ts`: wait-cap 1
- `app/tests/icon-button.spec.ts`: sleep 2
- `app/tests/inventory.spec.ts`: sleep 12, wait-cap 8
- `app/tests/live-reconcile.spec.ts`: sleep 1
- `app/tests/match.spec.ts`: elapsed-assert 2
- `app/tests/motion-live.spec.ts`: wait-cap 6
- `app/tests/motion-theme-flash.spec.ts`: sleep 1
- `app/tests/motionSettled.ts`: sleep 1
- `app/tests/nav.spec.ts`: sleep 1
- `app/tests/order-walk.spec.ts`: sleep 1
- `app/tests/orders.spec.ts`: sleep 5, wait-cap 3
- `app/tests/pricing-markdown.spec.ts`: sleep 2, wait-cap 1
- `app/tests/pricing.spec.ts`: sleep 4, wait-cap 4
- `app/tests/product-history.spec.ts`: sleep 2
- `app/tests/request-budget.spec.ts`: wait-cap 1
- `app/tests/revenue.spec.ts`: sleep 8
- `app/tests/review.spec.ts`: sleep 17, wait-cap 7
- `app/tests/run-panel.spec.ts`: sleep 3, wait-cap 2
- `app/tests/scaffold.spec.ts`: sleep 1, wait-cap 1
- `app/tests/section-ruler.spec.ts`: wait-cap 1
- `app/tests/slabs.spec.ts`: sleep 1, wait-cap 6
- `app/tests/stability.spec.ts`: sleep 11, wait-cap 8
- `harness/tests/t7/backup.py`: wait-cap 1
- `harness/tests/t7/common.py`: wait-cap 1
- `harness/tests/t7/emit_pricing.py`: wait-cap 5
- `harness/tests/t7/engine_pick.py`: sleep 1
- `harness/tests/t7/engine_sweep.py`: wait-cap 6
- `harness/tests/t7/inventory_routes.py`: wait-cap 2
- `harness/tests/t7/manifest_merge.py`: wait-cap 3
- `harness/tests/t7/photo_recheck.py`: wait-cap 1
- `harness/tests/t7/pipeline_fetch.py`: wait-cap 3
- `harness/tests/t7/price_fresh.py`: sleep 6, wait-cap 1
- `harness/tests/t7/read_budget.py`: wait-cap 4
- `harness/tests/t7/send_markdown.py`: sleep 3, wait-cap 8
- `harness/tests/t7/server_hardening.py`: wait-cap 9
- `harness/tests/t7/server_lanes.py`: sleep 10, wait-cap 25
- `harness/tests/t7/sets_stock.py`: sleep 5, wait-cap 12
- `harness/tests/t7/undo_built_on.py`: sleep 2, wait-cap 4
- `harness/tests/t7_box_map.py`: wait-cap 1

#### degen

- `app/tests/add-sheet-reddit-pending.spec.ts`: wait-cap 1
- `app/tests/archive-delete.spec.ts`: wait-cap 1
- `app/tests/design-review.spec.ts`: wait-cap 2
- `app/tests/edge-back.spec.ts`: wait-cap 7
- `app/tests/fast-scroll-bar.spec.ts`: sleep 1, wait-cap 1
- `app/tests/grid-cells.spec.ts`: sleep 2
- `app/tests/item-list.spec.ts`: wait-cap 1
- `app/tests/l2.spec.ts`: sleep 3, wait-cap 2
- `app/tests/l3.spec.ts`: sleep 1, wait-cap 3
- `app/tests/l4.spec.ts`: sleep 1, wait-cap 1
- `app/tests/l5.spec.ts`: wait-cap 2
- `app/tests/media-sweep.spec.ts`: sleep 1
- `app/tests/media.spec.ts`: sleep 2, wait-cap 2
- `app/tests/offline-label-screens.spec.ts`: sleep 1
- `app/tests/offline/gated-lists-cache.spec.ts`: sleep 1
- `app/tests/offline/offline-fallback.spec.ts`: sleep 1, wait-cap 2
- `app/tests/offline/offline-icon.spec.ts`: sleep 1
- `app/tests/offline/offline.config.ts`: wait-cap 3
- `app/tests/pull-refresh.spec.ts`: sleep 6, wait-cap 1
- `app/tests/pwa-update.spec.ts`: sleep 1, wait-cap 2
- `app/tests/quote-popover-drag.spec.ts`: sleep 1, wait-cap 3
- `app/tests/seen.spec.ts`: sleep 1, wait-cap 3
- `app/tests/served/served-build.spec.ts`: wait-cap 2
- `app/tests/served/served.config.ts`: wait-cap 3
- `app/tests/settings-disk-low.spec.ts`: wait-cap 1
- `app/tests/settings-viewing.spec.ts`: sleep 1
- `app/tests/sheet-swipe.spec.ts`: wait-cap 3
- `app/tests/thread-pending-controls.spec.ts`: wait-cap 6
- `app/tests/viewer-retry.spec.ts`: wait-cap 6
- `app/tests/viewer.spec.ts`: sleep 19, wait-cap 1
- `native/DegenKit/Tests/DegenKitTests/ArchiveRuleRulesFirstTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/ArchiveRuleStatusTests.swift`: sleep 2
- `native/DegenKit/Tests/DegenKitTests/BothPullReviewTests.swift`: sleep 2
- `native/DegenKit/Tests/DegenKitTests/CacheablePicture.swift`: sleep 2
- `native/DegenKit/Tests/DegenKitTests/ClientLastSyncTests.swift`: sleep 1, elapsed-assert 2
- `native/DegenKit/Tests/DegenKitTests/DownloadQueueTests.swift`: wait-cap 1
- `native/DegenKit/Tests/DegenKitTests/DownloadsControlPhoneTests.swift`: sleep 3, wait-cap 2
- `native/DegenKit/Tests/DegenKitTests/DownloadsControlPullTests.swift`: wait-cap 1
- `native/DegenKit/Tests/DegenKitTests/FeedCancelledFillTests.swift`: sleep 6, wait-cap 1
- `native/DegenKit/Tests/DegenKitTests/FeedOnlyNewPagingTests.swift`: sleep 2
- `native/DegenKit/Tests/DegenKitTests/FeedTgChatTopicTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/FreeSpaceCountSafetyTests.swift`: elapsed-assert 1
- `native/DegenKit/Tests/DegenKitTests/GridToggleModelTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/IgDmReadClientTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/IgDmRulesModelTests.swift`: sleep 1, wait-cap 1
- `native/DegenKit/Tests/DegenKitTests/ImageTimingEntryTests.swift`: wait-cap 1
- `native/DegenKit/Tests/DegenKitTests/ImageTimingInFlightTests.swift`: wait-cap 2
- `native/DegenKit/Tests/DegenKitTests/ImageTimingSupport.swift`: elapsed-assert 2, wait-cap 1
- `native/DegenKit/Tests/DegenKitTests/ItemListModelTests.swift`: sleep 4
- `native/DegenKit/Tests/DegenKitTests/JdHubSendTests.swift`: sleep 2
- `native/DegenKit/Tests/DegenKitTests/JdQueueCancelTests.swift`: sleep 2
- `native/DegenKit/Tests/DegenKitTests/JdQueueRefreshTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/JdSendOutboxTests.swift`: sleep 2
- `native/DegenKit/Tests/DegenKitTests/LaunchScansSupport.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/LaunchScansTests.swift`: sleep 2, elapsed-assert 2
- `native/DegenKit/Tests/DegenKitTests/LaunchTraceBufferTests.swift`: sleep 2, elapsed-assert 2
- `native/DegenKit/Tests/DegenKitTests/MediaDownloadSessionFakeTests.swift`: sleep 6
- `native/DegenKit/Tests/DegenKitTests/MediaDownloadSessionHandChunkTests.swift`: sleep 3
- `native/DegenKit/Tests/DegenKitTests/MediaDownloadSessionSupport.swift`: sleep 2
- `native/DegenKit/Tests/DegenKitTests/MediaUploadMemoryTests.swift`: sleep 5
- `native/DegenKit/Tests/DegenKitTests/NBBrowserTests.swift`: wait-cap 1
- `native/DegenKit/Tests/DegenKitTests/OfflineFallbackTests.swift`: elapsed-assert 2
- `native/DegenKit/Tests/DegenKitTests/OpenInstantGateTests.swift`: sleep 4
- `native/DegenKit/Tests/DegenKitTests/OpenInstantPassTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/PartlyRecheckIndexTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/PhoneDrainBacklogTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/PhoneDrainRouteTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/PhoneDrainSupport.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/PhoneDrainTraceTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/PhoneRefreshTests.swift`: sleep 1, elapsed-assert 1
- `native/DegenKit/Tests/DegenKitTests/PhoneRollOffLagTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/PhoneRollOffSupport.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/PhoneStoreTests.swift`: wait-cap 1
- `native/DegenKit/Tests/DegenKitTests/PlayFailureLogTests.swift`: sleep 7
- `native/DegenKit/Tests/DegenKitTests/QueueLagFlushTests.swift`: sleep 3
- `native/DegenKit/Tests/DegenKitTests/QueueLagLateFailureTests.swift`: wait-cap 1
- `native/DegenKit/Tests/DegenKitTests/QueueLagPerfTests.swift`: sleep 2, wait-cap 1
- `native/DegenKit/Tests/DegenKitTests/QueueLagRateTests.swift`: sleep 2
- `native/DegenKit/Tests/DegenKitTests/QueueMissingStatTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/RouteRulesStallTests.swift`: sleep 1, elapsed-assert 1
- `native/DegenKit/Tests/DegenKitTests/RouteRulesSyncTests.swift`: sleep 2
- `native/DegenKit/Tests/DegenKitTests/SaveFailureReasonTests.swift`: wait-cap 2
- `native/DegenKit/Tests/DegenKitTests/SaveReasonKeptTests.swift`: wait-cap 3
- `native/DegenKit/Tests/DegenKitTests/SavedThreadReadLagTests.swift`: sleep 2
- `native/DegenKit/Tests/DegenKitTests/SavesStatusCancelPauseTests.swift`: sleep 2
- `native/DegenKit/Tests/DegenKitTests/SavesStatusRateTests.swift`: sleep 13
- `native/DegenKit/Tests/DegenKitTests/ServerPullSupport.swift`: sleep 3
- `native/DegenKit/Tests/DegenKitTests/ServerStepAnswerTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/SettingsCardReadsTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/SettingsFeedRetryShownTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/SettingsFeedSaveStateTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/ShareFileFixGuardTests.swift`: wait-cap 1
- `native/DegenKit/Tests/DegenKitTests/ShareUploadEventsTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/SourcesGridMoveFixTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/StepOwnLineTests.swift`: sleep 3
- `native/DegenKit/Tests/DegenKitTests/StepsNoWaitTests.swift`: sleep 3
- `native/DegenKit/Tests/DegenKitTests/StoreFilesSupport.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/StoreFoldSupport.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/StoreJournalDamageTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/StoreJournalKillTests.swift`: sleep 2
- `native/DegenKit/Tests/DegenKitTests/StoreWriteBatchTests.swift`: sleep 2
- `native/DegenKit/Tests/DegenKitTests/StoreWriteFailureTests.swift`: wait-cap 1
- `native/DegenKit/Tests/DegenKitTests/StoreWriteFoldTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/StoreWriteLateFailureTests.swift`: wait-cap 1
- `native/DegenKit/Tests/DegenKitTests/StoreWriteSlotTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/StoreWriteSupport.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/TelegramChatPickerTests.swift`: sleep 2
- `native/DegenKit/Tests/DegenKitTests/ThreadModelCancelTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/ThreadModelReloadTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/ViewerPlayerFeedTests.swift`: sleep 5
- `native/DegenKit/Tests/DegenKitTests/ViewerPlayerVLCSoundTests.swift`: sleep 9
- `native/DegenKit/Tests/DegenKitTests/ViewerPlayerWaitingTests.swift`: sleep 12
- `native/DegenUITests/AddSourceCombinedUITests.swift`: wait-cap 5
- `native/DegenUITests/ArchivePillUITests.swift`: wait-cap 12
- `native/DegenUITests/ArchivePillWidthUITests.swift`: wait-cap 1
- `native/DegenUITests/ArchiveRefreshUITests.swift`: wait-cap 7
- `native/DegenUITests/ArchiveRulesUITests.swift`: wait-cap 6
- `native/DegenUITests/BoardBackListUITests.swift`: wait-cap 4
- `native/DegenUITests/BoardBackUITests.swift`: wait-cap 4
- `native/DegenUITests/BoardTilesUITests.swift`: wait-cap 21
- `native/DegenUITests/BookmarksPillUITests.swift`: wait-cap 12
- `native/DegenUITests/BookmarksRefreshUITests.swift`: wait-cap 2
- `native/DegenUITests/BrowserExitsUITests.swift`: wait-cap 7
- `native/DegenUITests/ChatLinksSpreadUITests.swift`: wait-cap 9
- `native/DegenUITests/ColumnsPickerUITests.swift`: wait-cap 4
- `native/DegenUITests/DownloadsButtonClearUITests.swift`: wait-cap 5
- `native/DegenUITests/EdgeBackUITests.swift`: sleep 1, wait-cap 17
- `native/DegenUITests/FeedDownloadsIconUITests.swift`: wait-cap 16
- `native/DegenUITests/FeedPillUITests.swift`: wait-cap 39
- `native/DegenUITests/HideWordsUITests.swift`: wait-cap 10
- `native/DegenUITests/InfiniteFeedUITests.swift`: wait-cap 29
- `native/DegenUITests/ItemListLayoutSupport.swift`: wait-cap 2
- `native/DegenUITests/ItemListUITests.swift`: wait-cap 10
- `native/DegenUITests/JdDeferredScreenUITests.swift`: wait-cap 24
- `native/DegenUITests/KeepHandClaimUITests.swift`: wait-cap 18
- `native/DegenUITests/KeepPlaceUITests.swift`: wait-cap 11
- `native/DegenUITests/KeepScrollUITests.swift`: sleep 3, wait-cap 9
- `native/DegenUITests/LaunchTests.swift`: wait-cap 1
- `native/DegenUITests/MediaBarUITests.swift`: sleep 1, wait-cap 12
- `native/DegenUITests/MediaFeedUITests.swift`: wait-cap 16
- `native/DegenUITests/MediaGridEdgeBackUITests.swift`: wait-cap 6
- `native/DegenUITests/MediaPillLayoutUITests.swift`: wait-cap 3
- `native/DegenUITests/MediaScreenFastScrollUITests.swift`: wait-cap 4
- `native/DegenUITests/MediaViewerUITests.swift`: sleep 2, wait-cap 30
- `native/DegenUITests/NativeScreensUITests.swift`: wait-cap 22
- `native/DegenUITests/OfflineIconUITests.swift`: wait-cap 13
- `native/DegenUITests/OneTouchSaveUITests.swift`: wait-cap 11
- `native/DegenUITests/OtherScreensUITests.swift`: wait-cap 5
- `native/DegenUITests/PillMenuSupport.swift`: wait-cap 3
- `native/DegenUITests/PillThreadItemsUITests.swift`: wait-cap 26
- `native/DegenUITests/RowHoldMenuUITests.swift`: wait-cap 9
- `native/DegenUITests/SaveToastUITests.swift`: wait-cap 3
- `native/DegenUITests/SaveTwoUITests.swift`: wait-cap 35
- `native/DegenUITests/SavedBoardsUITests.swift`: wait-cap 10
- `native/DegenUITests/SavedSelectUITests.swift`: wait-cap 6
- `native/DegenUITests/SavedSetsUITests.swift`: wait-cap 57
- `native/DegenUITests/SelectReworkUITests.swift`: wait-cap 13
- `native/DegenUITests/SettingsCardsUITests.swift`: wait-cap 18
- `native/DegenUITests/SettingsDiskNoteUITests.swift`: wait-cap 3
- `native/DegenUITests/SettingsInnerPagesUITests.swift`: wait-cap 7
- `native/DegenUITests/SettingsPagesSupport.swift`: wait-cap 6
- `native/DegenUITests/SettingsPagesUITests.swift`: wait-cap 22
- `native/DegenUITests/SettingsRoundTwoUITests.swift`: wait-cap 11
- `native/DegenUITests/SettingsStorageAboutUITests.swift`: wait-cap 25
- `native/DegenUITests/ShellTabsUITests.swift`: wait-cap 14
- `native/DegenUITests/SourceIconUITests.swift`: wait-cap 14
- `native/DegenUITests/SourceLogoUITests.swift`: wait-cap 13
- `native/DegenUITests/SourceTileCropUITests.swift`: wait-cap 2
- `native/DegenUITests/SourcesGridDragUITests.swift`: wait-cap 4
- `native/DegenUITests/SourcesGridMenuUITests.swift`: wait-cap 7
- `native/DegenUITests/SourcesGridMoveModeUITests.swift`: wait-cap 29
- `native/DegenUITests/SourcesGridPillAfterDragUITests.swift`: sleep 1, wait-cap 9
- `native/DegenUITests/SourcesGridPillUITests.swift`: wait-cap 20
- `native/DegenUITests/SourcesGridUITests.swift`: wait-cap 3
- `native/DegenUITests/ThreadActionsPillUITests.swift`: wait-cap 12
- `native/DegenUITests/ThreadLinksUITests.swift`: sleep 1, wait-cap 26
- `native/DegenUITests/ThreadMediaGridUITests.swift`: wait-cap 20
- `native/DegenUITests/ThreadPillPopoverUITests.swift`: wait-cap 12
- `native/DegenUITests/ThreadPillSupport.swift`: wait-cap 6
- `native/DegenUITests/ThreadSwipeUITests.swift`: wait-cap 15
- `native/DegenUITests/ThreadUITests.swift`: wait-cap 17
- `native/DegenUITests/TopWindowSelectedUITests.swift`: wait-cap 8
- `native/DegenUITests/ViewerMuteCircleUITests.swift`: wait-cap 12
- `native/DegenUITests/ViewerOriginalTapAreaUITests.swift`: wait-cap 8
- `native/DegenUITests/ViewerSaveUITests.swift`: wait-cap 22
- `native/DegenUITests/ViewerStripLazyUITests.swift`: sleep 1, wait-cap 8
- `native/DegenUITests/ViewerStripSwipeUITests.swift`: wait-cap 6
- `native/DegenUITests/WhereSavesGoUITests.swift`: wait-cap 17
- `native/DegenUITests/WindowSupport.swift`: sleep 2, wait-cap 1
- `tests/addon/test_jd_folderwatch.py`: wait-cap 3
- `tests/addon/test_jd_guard.py`: wait-cap 2
- `tests/addon/test_jd_heal.py`: sleep 2, wait-cap 3
- `tests/addon/test_jd_update_settings.py`: sleep 1
- `tests/server/jd_rig.py`: wait-cap 1
- `tests/server/stills_rig.py`: wait-cap 3
- `tests/server/test_api_fixtures.py`: wait-cap 1
- `tests/server/test_disk_floor.py`: wait-cap 2
- `tests/server/test_fetch_counter.py`: sleep 5, elapsed-assert 1, wait-cap 1
- `tests/server/test_file_speed_test.py`: sleep 1, wait-cap 1
- `tests/server/test_hostkit.py`: wait-cap 4
- `tests/server/test_icon_pacing.py`: sleep 3
- `tests/server/test_ig_dm.py`: sleep 7
- `tests/server/test_ig_refusal_log.py`: elapsed-assert 1
- `tests/server/test_media_cache_repair.py`: wait-cap 1
- `tests/server/test_media_queue.py`: elapsed-assert 2
- `tests/server/test_media_save_upload.py`: sleep 3
- `tests/server/test_service_edges.py`: elapsed-assert 1
- `tests/server/test_share_lanes.py`: sleep 3
- `tests/server/test_share_media.py`: sleep 1
- `tests/server/test_sigterm.py`: wait-cap 1
- `tests/server/test_tg_api.py`: sleep 1
- `tests/server/test_tg_chat_follow.py`: sleep 1
- `tests/server/test_tg_file.py`: sleep 1, wait-cap 1
- `tests/server/test_tg_file_link.py`: elapsed-assert 2
- `tests/server/test_tg_file_stream.py`: sleep 4
- `tests/server/test_tg_session.py`: sleep 1
- `tests/server/test_tg_thumb_route.py`: wait-cap 1
- `tests/server/test_tls.py`: wait-cap 2
- `tests/server/tg_thumb_rig.py`: sleep 3, wait-cap 1

#### joyous

- `tests/leads/score.test.ts`: elapsed-assert 1, test-cap 2
- `tests/tour-pages.test.mjs`: sleep 1, test-cap 36, wait-cap 1

#### mailaudit

- `native/ManifestKit/Tests/ManifestKitTests/HandModelTests.swift`: sleep 1
- `native/ManifestKit/Tests/ManifestKitTests/N4bSupport.swift`: sleep 1
- `native/ManifestKit/Tests/ManifestKitTests/PhotoSyncTests.swift`: sleep 2, wait-cap 2
- `native/ManifestKit/Tests/ManifestKitTests/PressGateTests.swift`: sleep 1
- `native/ManifestKit/Tests/ManifestKitTests/StubNetTests.swift`: sleep 2
- `native/ManifestKit/Tests/ManifestKitTests/StubURLProtocol.swift`: sleep 1
- `native/ManifestKit/Tests/ManifestKitTests/SyncPanelTests.swift`: sleep 1
- `native/ManifestKit/Tests/ManifestKitTests/SyncTestCase.swift`: sleep 1
- `native/ManifestUITests/AuditSkippingTabBarUITests.swift`: sleep 1, wait-cap 6
- `native/ManifestUITests/DuoHandUITests.swift`: sleep 1, wait-cap 10
- `native/ManifestUITests/DuoShellUITests.swift`: sleep 1, wait-cap 11
- `native/ManifestUITests/DuoSpreadUITests.swift`: sleep 6, elapsed-assert 1, wait-cap 12
- `native/ManifestUITests/DuoWindowSupport.swift`: sleep 2, wait-cap 1
- `native/ManifestUITests/LedgerSyncUITests.swift`: wait-cap 4
- `native/ManifestUITests/MastheadBackupUITests.swift`: sleep 2, wait-cap 9
- `native/ManifestUITests/MastheadPaintUITests.swift`: wait-cap 2
- `native/ManifestUITests/MastheadRefreshUITests.swift`: sleep 1, wait-cap 1
- `native/ManifestUITests/OrphanedRecordSupport.swift`: wait-cap 4
- `native/ManifestUITests/OrphanedUITests.swift`: sleep 2, wait-cap 26
- `native/ManifestUITests/PackageCardUITests.swift`: wait-cap 15
- `native/ManifestUITests/PackageStampUITests.swift`: wait-cap 21
- `native/ManifestUITests/PackagesShellUITests.swift`: wait-cap 2
- `native/ManifestUITests/SyncAdvisoryUITests.swift`: wait-cap 3
- `native/ManifestUITests/TallyCopyStepperUITests.swift`: wait-cap 9
- `native/ManifestUITests/TallyUITests.swift`: wait-cap 15
- `native/ManifestUITests/VersionsUITests.swift`: wait-cap 4
- `test/app.test.mjs`: sleep 80
- `test/harness.mjs`: sleep 1
- `test/screens.mjs`: sleep 32, wait-cap 20
- `test/send-key.test.mjs`: sleep 1, wait-cap 1

#### ios-adblock

- `ios/Tests/ListUpdateTests.swift`: sleep 1
