# Step audit: 303 doing steps owned by triage

Read by REST by 8 read-only agents, finished 21:19 CST Nov 18 (file written 2026-11-18T21:23:43-06:00). Triage proposes; the coordinator decides.

Proposal: 44 steps done (every PR merged), 3 steps todo (PR closed unmerged, lane archived), the rest unchanged. Merge shas are rechecked before any status is set.

| step | PRs (state, sha) | lane | proposal |
|---|---|---|---|
| agent-git-reset-refused | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| agent-output-terse-line | #2714 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| agent-owned-processes | #3300 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| agent-worktree-add-in-tool-dir | #3026 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| all-jobs-passed-docs-only-red | #3292 merged 2a388ccd92 | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| answer-finding-needs-step | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| answer-kept-on-close | #2981 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| answered-claims-match-page | #3548 merged 48646c9dff | none/none | done |
| answered-lines-age-out | #3327 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| answers-session-write-guard | #2971 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| archive-reads-unarchived-epoch | #3117 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| archive-refusal-names-add-repo | #3136 merged 62b515246b | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | done |
| archive-sweep-runs-per-merge | #3667 open | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| backlog-drain | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| base-hash-on-base | #3244 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| batch-build-log-kept | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| batch-build-names-left-out | #3148 closed unmerged | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | todo |
| batch-build-stop-group | #2837 open draft | none/none | wait |
| batch-drop-refusal-blame | #3175 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| batch-label-setter | #3252 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| batch-order-by-pr-number | #2939 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| blame-on-finished-red-job | #2838 open draft | none/none | wait |
| both-session-starts-judged | #2894 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| brake-same-everywhere | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| brief-from-step | #3319 open draft | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| brief-names-push-target | #3044 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| brief-says-owner-unread | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| builder-bash-test-write | #2954 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| builder-report-in-head | #2664 open draft | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| builder-test-comment-edit | #3082 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| busy-file-stacked-batches | #2972 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| challenge-followups | #3143 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| child-ci-once-per-batch | - | SESSION_STATUS_IDLE; SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_BLOCKED; SESSION_STATUS_BUCKET_COMPLETED | wait |
| child-repo-archive-scope | #2768 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| ci-alarm-reads-reverts | #3294 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| ci-batch-mac-runner | #3409 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| ci-cancel-on-close | #3216 merged 908e15ad86 | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | done |
| ci-hygiene-once-per-batch | #3004 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| ci-hygiene-upkeep | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| ci-mac-once-per-batch | #3005 open draft | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| ci-skip-untouched-steps | #3584 merged fae9721503 | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| ci-split-checks-family | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| ci-wait-subscribes-first | #3346 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| claim-vs-main-needs-read | #3068 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| claude-md-load-once | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| claude-md-merge-alone-or-combined | #3274 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| cloud-hooks-stale-copy | #3487 merged f191df768b | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | done |
| cloud-precompact-handoff-stale | #3110 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| combine-first-three | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| combine-tournament | - | unknown (invalid session ID format)/unknown | wait |
| combine-train-tool | #3520 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| combined-pr-recipe | #3299 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| commit-trailer-model | #2692 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| compact-pct-override | #3060 merged 150169752f | none/none | done |
| compaction-audit-before-reply | - | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| consultant-role-placement | #3084 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| consultant-role-record | #3057 closed unmerged | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| consultant-tag-owner-facing | #3310 merged af70a86328 | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| coordinator-scope-false-alarms | #3334 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| coordinator-session-board | #2943 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| dead-host-lock-form-off-linux | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_BLOCKED | wait |
| dead-pr-states-filled | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| dead-pr-waits | #2729 open draft | none/none | wait |
| debt-retire-names-test | #3174 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| decision-watch-finds-transcript | #2769 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| degen-harness-flake-archiver-stop | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| deviations-means-departure | #3462 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| draft-pr-unquoted-body-sq-subst | #2824 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| draft-push-starts-touched-run | #3156 open draft | none/none | wait |
| export-scan-key-followups | #1827 merged a5aefcf1f8 | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | done |
| express-pass-owner-quotes | #2900 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| fast-forward-clean-start | #3141 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| feedback-log-tends-itself | #2996 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| fetch-head-shared-race | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| filing-check-reads-page | #2907 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| first-fix-check-net-value | - | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| fix-branch-merge-main-deny | #3102 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| fix-check-reads-red-job-wakes | #2860 merged 46f98900f6; #2940 closed unmerged | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| fix-check-records-carry | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| fix-verifier-stands-for-round-2 | #3131 open draft | none/none | wait |
| force-advice-needs-real-run | #3350 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| gate-skipped-push-run | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| git-apply-test-path-write | #3050 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| global-claude-md-scope-audit | #2852 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| glossary-one-page-row | - | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| glossary-orchestrator-sweep | - | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| glossary-page-row | #2660 merged 3ef0480fcd | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| glossary-renames-in-code | - | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| glossary-same-local-cloud | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| green-hook-skips-draft-run | - | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| guard-false-alarm-cull | #3056 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| guard-interpreter-body-git | #2813 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| guard-paths-agents | #3024 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| guard-relative-write-escape | #2691 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| guard-run-slow-long-command | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| guard-tables-per-section | #2801 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| guards-read-origin-main-config | #3073 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| hand-in-merges-main-first | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_BLOCKED | wait |
| handin-cannot-drop | #3148 closed unmerged | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| handoff-agent-write | #2856 open draft | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| handoff-audit-after-compact | #3062 merged 7364c3f7e6 | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | done |
| handoff-written-by-hook | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| hold-names-its-end | #3335 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| inbox-dup-heading-merge | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| install-hash-skips-pycache | #2945 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| install-src-shard-by-function | #3541 merged 8a17c21393 | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | done |
| ios-apps-test-shapes | #3092 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| judge-flags-batch101 | #2743 merged c4071963af | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | done |
| judge-flags-batch102 | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| judge-replay-page-cases | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| lane-brief-cites-grant | #2562 open draft | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| lane-draft-pr-grant | #3048 merged 9eb6dd72c0 | none/none | done |
| lane-idle-shows | #3459 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| lane-lint-allow-words | - | not-found/not-found | wait |
| lane-lint-merges-main | #3552 open draft | not-found/not-found | wait |
| lane-lint-once-fail-fast | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| lane-lint-parallel-cap | #2749 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| lane-lint-unknown-on-ready-pr | #3321 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| lane-no-popup | #3236 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| lane-reply-past-ruling | #3099 merged 1915165684 | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| lane-start-checks-open-pr | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| lane-start-one-pass | #3549 merged 28d4752adb | none/none | done |
| lane-start-tags-cs-step | #3111 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| lanes-no-ci-record-claims | #3139 open draft | none/none | wait |
| lease-remedy-form | #3580 open draft | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| lint-fixtures-at-python-floor | #3094 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| live-file-refresh-one-command | - | none/none | wait |
| local-allow-goes-global | #3343 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| local-autonomy-equals-cloud | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| local-page-publish-route | #3065 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| macos-only-fail-passes-lane-lint | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| macos-runner-queue-wait | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| mail-guards-read-send-message | #3211 open draft | none/none | wait |
| mail-read-receipt | #3137 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| main-claim-branch-only | #3091 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| main-job-cap-alarm | #2920 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| main-push-wakes-runner | #2875 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| merge-claim-only-head-skips-run | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| merge-flow-after-anthropic | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| merge-line-cites-to-symbols | #3130 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| merge-lint-fix-no-round-3 | #3269 merged 22231dd779 | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| merge-lock-ttl-waits | #3377 merged 9f44f200bb | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | done |
| merge-passes-settings-dir | #3178 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| merge-path-same-everywhere | #3014 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| merge-r3-reviewer-sonnet-only | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| merge-reads-newest-check-run | #3317 merged 82469ae589 | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| merge-red-base-resume-on-merge | #3312 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| merge-reviewed-cursor | #3242 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| merge-runs-idle-lanes | #3108 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| merge-skips-lint-on-green-ci | #3025 merged 5c7243e846 | SESSION_STATUS_RUNNING/SESSION_STATUS_BUCKET_WORKING | done |
| merge-stale-cites-to-ids | #3377 merged 9f44f200bb | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | done |
| merge-tool-beats-every-phase | #3404 merged 0806bf59d2 | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| mistake-prose-files-guard | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| model-layout-to-table | #3286 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| msg-claims-vs-git | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| mutate-timeout-crashed | #3047 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| mutation-tests-for-cost | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| no-ci-starter | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| notes-1796-fix-lines | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| notes-204-ponytail-drop | - | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| notes-fix-no-owner-line | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| one-build-per-session-wording | #3090 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| one-term-warn-lint | #2858 open draft | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| operating-model-role-handoffs | #3259 merged 42c5dbe9b1 | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | done |
| opus-ask-grants-one-spawn | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| other-checkout-heredoc-text | #2789 open draft | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| outbox-aggregate-plan | #2974 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| outbox-ruling-home-check | #2767 open draft | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| owner-credit-guard | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| owner-health-tab | #2904 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| owner-override-one-route | #2850 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| page-answered-not-closed | - | none/none | wait |
| page-data-one-store | #3212 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| page-one-store-fixes | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| page-open-item-staleness | - | none/none | wait |
| page-republish-at-merge | #3467 merged b6263e3d4a | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| page-taken-picks-area | - | none/none | wait |
| page-time-url-scope | #2732 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| page-wakes-and-relays | #2870 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_BLOCKED | wait |
| page-writer-key-follows-tag | #3124 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| past-ruling-before-post | #3206 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| past-ruling-s1-block | #2797 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| pe-guard-false-alarms | #1935 open draft | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| pick-reaches-page | #2870 open draft | none/none | wait |
| plain-push-asks-source-fix | #3083 merged 98db63e2c8 | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| pr-3578-revive-open-asks-at-wake | #3578 open draft | none/none | wait |
| pr-3579-pr-template-copies-equal | #3579 open draft | none/none | wait |
| pr-3580-lease-remedy-form | #3580 open draft | none/none | wait |
| pr-3581-lane-ack-question-revive | #3581 open draft | none/none | wait |
| pr-3582-task-options-departs | #3582 open draft | none/none | wait |
| pr-ledger-round-ages | #2869 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| pr-template-copies-equal | #2708 closed unmerged | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| pre-existing-needs-main-run | #3244 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| pre-existing-uses-clause | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| priority-table-reads-pr | #3337 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| priority-vs-merge-order | #3378 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| progress-claims-cite-live-read | #3227 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| project-ops-roles | #3521 merged 67d200f0ab | not-found/not-found | done |
| prose-tending-contract | #2915 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| prose-tending-move-stores | #3003 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| push-skip-proven-tree | - | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| push-skip-text-says-stable | #3419 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| pwsh-followups | #2723 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| qmax-1011-carry | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| qmax-ci-batch-heads | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| question-form-task-context | #2681 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| question-form-widens-false-alarm | #3422 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| question-form-widens-label | #3326 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| r13-lane-never-stalls-on-popup | #3236 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| r16-mistake-is-missing-guard | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| r2-merge-checks-run-in-ci | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| r31-builder-test-conflicts | #3293 merged 72220a23af | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| r65-express-batch | #3213 merged aadc6cbbd3 | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| ready-step-hang-no-timeout | #3415 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| rebuild-2123 | #3249 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| rec-and-waiting-line | - | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| record-before-next-push | #3109 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| records-page-guard-derived-rows | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| records-page-ready-reads-pr-repo | #2779 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| red-chain-needs-revert-each | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| red-gate-reads-suite-run | - | not-found/not-found | wait |
| red-main-owner-two-picks | #3268 open draft; #3304 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| refused-start-queues-turn | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| release-check-vs-batch-head | #3240 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| repeat-judge-never-blocks | #2957 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| repeat-mark-skips-followups | #2957 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| restart-plan-free-gate | #2698 merged 42c61f7248 | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | done |
| resume-guard-subagent-sends | #2771 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| resume-guard-workflow-agents | #2771 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| retire-check-whole-suite | - | none/none | wait |
| retire-missing-deps-unknown | - | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| retry-net-method-safe | #2964 merged d58d7843e0 | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| revert-then-resume-merges | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| review-carries-live-head | #3519 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| review-record-fix-check-reads | #2940 closed unmerged | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | todo |
| review-record-merge-main-line | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| review-record-parses-at-handin | #3072 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| review-record-restart-on-doc-nit | #3320 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| review-record-usage-line | #2940 closed unmerged | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | todo |
| roadmap-ref-fresh-before-verdict | #3253 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| role-md-no-override-opus | #3286 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| role-model-explore-veto-offer | #3074 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| role-texts-match-rulings | #3138 merged 06a65cbc58 | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | done |
| rollup-skipped-reads-pending | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| round-one-model-prose-matches-table | #3316 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| round1-sonnet-guard-table | #3010 merged 05f32bca8c | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| rounds-rules-one-record | #3311 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| ruled-entry-open-too-long | #3132 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| ruled-store-one-home | #2992 merged 3125c65e8e | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| ruling-challenge-passes | #2963 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| ruling-claim-cites-record | #3330 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| ruling-parts-cite-steps | #2828 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| scratch-rm-other-agent | #3013 merged b92ac4791f | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| scratchpad-cp-keeps-writer | #3126 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| scratchpad-owner-follow-ups | #2830 merged 95cbb50d44 | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| send-message-refs-resolve | #2913 open draft | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| session-messages-status-line | #3100 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| session-roster-at-start | #3560 merged 721144d71f | none/none | done |
| session-start-pin-skip-log | #3071 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| shared-job-finder | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| sim-lease-load-brake | #2899 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| solo-batch-hat | #2701 open draft | not-found/not-found | wait |
| sort281-merge-main-list | - | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| spawn-guard-marker-any-line | #3339 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| spend-line-format | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| spend-log-per-batch | #2662 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| stable-refresh-local | #3524 open draft | not-found/not-found | wait |
| stack-check-scales-open-prs | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| stale-cites-tree-clean | #2804 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| stale-draft-joint-pass | #3142 merged unknown (n | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| stale-draft-reads-runner-holds | #3147 open draft | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| stale-flags-test-gaps | - | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| stall-watch-clock-pins | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| stall-watch-ends-quiet-jobs | #2862 open draft | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| stall-watch-live-run | #2862 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| stall-watch-quiet-lint | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| stall-watch-round3-notes | #3271 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| stamp-clock-check-everywhere | #3234 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| stamp-guard-send-message | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| standing-role-model-rows | #3023 merged unknown (n | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | done |
| standing-sessions-add-repo | - | none/none | wait |
| step-done-check-field | #3319 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| stood-pick-needs-review | #3479 merged unknown (n | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | done |
| stop-checks-one-message | #2836 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| stylisms-apply-six-changes | #3354 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| stylisms-rules-table | #3340 merged unknown (n | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| subagent-handback-skipped | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| sweep-lock-age | #2872 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| sweep-mutants-windows-skip | #3303 merged unknown (n | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| task-item-with-options | #3325 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| tier-boundaries-carry | #2831 open draft | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| time-limits-end-hangs-only | #2863 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| time-pinned-keep-marker | #2975 merged unknown (n | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | done |
| trial-brief-triage-by-role | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| two-drop-leaves-queue | #2893 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| unknown-reads-lint-linux-only | #3005 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| upkeep-keys-live-status | #2878 open draft | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | wait |
| usage-brake | #2663 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| waiting-copy-backup-only | #2907 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| waiting-export-miss-cloud | #3529 merged unknown (n | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
| waiting-lag-read | #2879 open draft | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_REVIEW_READY | wait |
| wave-88-rebuilds | - | SESSION_STATUS_IDLE/SESSION_STATUS_BUCKET_COMPLETED | wait |
| windows-fixture-git-timeout | #3345 merged unknown (n | SESSION_STATUS_ARCHIVED/SESSION_STATUS_BUCKET_COMPLETED | done |
