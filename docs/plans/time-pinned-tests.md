# Time-pinned tests: per-repo list

Working plan for roadmap step time-pinned-tests-go (tests that pass or fail on clock speed become outcome checks). Part 1 built the finder and ran it. Part 2 goes to each repo's own lane: replace each finding with an outcome check, or record it as a debt, per decision test-strategy-reset (tests prove outcomes and never fail on runner speed). Then each repo's job caps go back to measured figures.

## The finder

`lint/find_time_pinned.py` lists lines in test files, in four kinds:

- sleep: a real wait in a test.
- elapsed-assert: an assert that reads a clock.
- test-cap: a per-test or per-suite time limit.
- wait-cap: a fixed bound on a wait for a condition or a child process. Most are hang guards, which can stay. Each repo's lane judges each one.

Each count is a candidate, not a verdict. A sample read found false alarms in elapsed-assert: a timestamp checked for its value, not for speed (degen `tests/server/test_fetch_counter.py`), and a name taken for a clock reading (q_max `harness/tests/deleted-chat-send.test.mjs`). The repo lane decides each one.

## Counts

Each row comes from `python3 lint/find_time_pinned.py <clone> --json`, run on a shallow clone of the repo's default branch at the commit shown, on 2026-11-02. Re-run that command to check a number.

| Repo | Commit | sleep | elapsed-assert | test-cap | wait-cap | Total | Files | Unread | Target (sleep, elapsed, cap) |
|---|---|---|---|---|---|---|---|---|---|
| q_max | `e8f99027` | 64 | 18 | 127 | 115 | 324 | 57 | 1 | 0, 0, 0, each wait-cap judged |
| banchi | `2e46c112` | 119 | 2 | 0 | 236 | 357 | 54 | 0 | 0, 0, 0, each wait-cap judged |
| degen | `af1d95ac` | 251 | 15 | 0 | 1075 | 1341 | 218 | 0 | 0, 0, 0, each wait-cap judged |
| joyous | `de35e993` | 1 | 1 | 38 | 1 | 41 | 2 | 0 | 0, 0, 0, each wait-cap judged |
| mailaudit | `9efe1bb0` | 140 | 1 | 0 | 178 | 319 | 30 | 0 | 0, 0, 0, each wait-cap judged |
| ios-adblock | `4d265329` | 1 | 0 | 0 | 0 | 1 | 1 | 0 | 0, 0, 0, each wait-cap judged |

- home: not scanned. Its lane is held.
- claude-settings: step c95 (make the timing and load asserts robust) fixed this repo's guard, install lock, stall watch, SendMessage and janitor timing cases by hand. It left 12 notes in `docs/debts/notes.md`. It built no finder and scanned no other repo. On main at 84a56038 the finder lists 207 here (sleep 51, elapsed-assert 7, test-cap 0, wait-cap 149, in 49 files, 1 unread). That list goes to a later claude-settings lane.

## Files

### q_max

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
- `harness/tests/races-plant.test.mjs`: elapsed-assert 1
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

### banchi

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

### degen

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
- `native/DegenKit/Tests/DegenKitTests/GridToggleModelTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/IgDmReadClientTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/IgDmRulesModelTests.swift`: sleep 1, wait-cap 1
- `native/DegenKit/Tests/DegenKitTests/ImageTimingEntryTests.swift`: wait-cap 1
- `native/DegenKit/Tests/DegenKitTests/ImageTimingInFlightTests.swift`: wait-cap 2
- `native/DegenKit/Tests/DegenKitTests/ImageTimingSupport.swift`: wait-cap 1
- `native/DegenKit/Tests/DegenKitTests/ItemListModelTests.swift`: sleep 4
- `native/DegenKit/Tests/DegenKitTests/JdHubSendTests.swift`: sleep 2
- `native/DegenKit/Tests/DegenKitTests/JdQueueCancelTests.swift`: sleep 2
- `native/DegenKit/Tests/DegenKitTests/JdQueueRefreshTests.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/JdSendOutboxTests.swift`: sleep 2
- `native/DegenKit/Tests/DegenKitTests/LaunchScansSupport.swift`: sleep 1
- `native/DegenKit/Tests/DegenKitTests/LaunchScansTests.swift`: sleep 2, elapsed-assert 2
- `native/DegenKit/Tests/DegenKitTests/LaunchTraceBufferTests.swift`: sleep 2
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

### joyous

- `tests/leads/score.test.ts`: elapsed-assert 1, test-cap 2
- `tests/tour-pages.test.mjs`: sleep 1, test-cap 36, wait-cap 1

### mailaudit

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

### ios-adblock

- `ios/Tests/ListUpdateTests.swift`: sleep 1
