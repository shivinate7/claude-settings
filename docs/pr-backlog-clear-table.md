# PR backlog: one next act and owner per open PR

Lane pr-backlog-clear, read 12:47 CST Nov 12. Acts for claude-settings come from the PR ledger of draft PR #2845 (`merge --reviewed`, run from that branch's code); that ledger stays the one home. This file is a snapshot, not a second ledger.

## Counts (claude-settings, 350 open at read; target for 'no next act' is 0)

| Next act | PRs | Target |
|---|---|---|
| merge in next batch | 124 | every PR has one |
| fix by lane (lane round N) | 89 | every PR has one |
| fix by lane (lane lint) | 88 | every PR has one |
| close as replaced (pending file check) | 19 | every PR has one |
| closed as replaced | 12 | every PR has one |
| fix by lane (fix check) | 8 | every PR has one |
| fix by lane (fresh full review) | 6 | every PR has one |
| blocked on stack base | 3 | every PR has one |
| batch run | 1 | every PR has one |

## claude-settings

| PR | Branch | Next act | Owner | Age and ledger state |
|---|---|---|---|---|
| #1034 | prose-homes-shivpedia | fix by lane prose-homes-shivpedia: lane round 1 | lane | 239.8h RED / ledger: no record |
| #1099 | no-undo-lane-commits | close as replaced by #2734, after a check that old-only files land there or are dropped | coordinator | 27.8h RED / ledger: done |
| #1147 | lane/timing-tests | fix by lane lane/timing-tests: lane lint | lane | 72.6h RED / ledger: no lint |
| #1314 | mcp-merge-unguarded | fix by lane mcp-merge-unguarded: lane lint | lane | 96.3h RED / ledger: no lint |
| #1315 | ste-lint-diff-fail-closed | fix by lane ste-lint-diff-fail-closed: lane round 1 | lane | 143.4h RED / ledger: no record |
| #1337 | widening-rule-guideline | close as replaced by #2705, after a check that old-only files land there or are dropped | coordinator | 142.9h RED / ledger: no record |
| #1349 | lane/watchers-one-rule | fix by lane lane/watchers-one-rule: lane round 1 | lane | 140.0h RED / ledger: no record |
| #1366 | reviewer-brief-blind-build | close as replaced by #2780, after a check that old-only files land there or are dropped | coordinator | 104.8h RED / ledger: no record |
| #1377 | challenger-page-against | fix by lane challenger-page-against: lane round 1 | lane | 139.5h RED / ledger: no record |
| #1382 | override-strips-status-block | closed as replaced by #2666 (done, comment posted, branch kept) | none |  |
| #1386 | export-after-page-write | fix by lane export-after-page-write: lane round 1 | lane | 136.9h RED / ledger: no record |
| #1417 | ready-checks-use-pinned-tools | fix by lane ready-checks-use-pinned-tools: lane lint | lane | 104.3h RED / ledger: no lint |
| #1432 | one-home-check | fix by lane one-home-check: lane round 3 | lane | 104.4h RED / ledger: open |
| #1443 | waiting-export-receipts | close as replaced by #2721, after a check that old-only files land there or are dropped | coordinator | 118.6h RED / ledger: no record |
| #1461 | lint-uses-pinned-tools | fix by lane lint-uses-pinned-tools: lane lint | lane | 103.8h RED / ledger: no lint |
| #1479 | notes-agent-shells-reap | closed as replaced by #2712 (done, comment posted, branch kept) | none |  |
| #1509 | script-file-test-write | fix by lane script-file-test-write: lane lint | lane | 116.8h RED / ledger: no lint |
| #1516 | notes-name-their-fix | close as replaced by #2735, after a check that old-only files land there or are dropped | coordinator | 96.6h RED / ledger: no record |
| #1517 | notes-guard2-tmpdir | fix by lane notes-guard2-tmpdir: lane lint | lane | 97.1h RED / ledger: no lint |
| #1520 | ruling-record-kind | fix by lane ruling-record-kind: lane lint | lane | 117.4h RED / ledger: no lint |
| #1536 | nfp-rg-forms | fix by lane nfp-rg-forms: lane lint | lane | 117.1h RED / ledger: no lint |
| #1552 | review-rounds-guard-marker | fix by lane review-rounds-guard-marker: lane lint | lane | 102.0h RED / ledger: no lint |
| #1554 | past-ruling-on-send | closed as replaced by #2740 (done, comment posted, branch kept) | none |  |
| #1555 | layout-rolled-out-bool | fix by lane layout-rolled-out-bool: lane lint | lane | 116.5h RED / ledger: no lint |
| #1561 | pr-state-is-on-the-pr | fix by lane pr-state-is-on-the-pr: fix check | lane | 104.4h RED / ledger: stale |
| #1585 | push-report-gaps | fix by lane push-report-gaps: lane round 3 | lane | 101.0h RED / ledger: open |
| #1598 | script-file-misses | fix by lane script-file-misses: lane lint | lane | 115.6h RED / ledger: no lint |
| #1616 | compare-files-missing-key | fix by lane compare-files-missing-key: fix check | lane | 80.0h RED / ledger: stale |
| #1618 | feedback-bad-mark | fix by lane feedback-bad-mark: lane round 3 | lane | 115.4h RED / ledger: open |
| #1619 | notes-sightings-expiry | fix by lane notes-sightings-expiry: lane round 1 | lane | 115.4h RED / ledger: no record |
| #1631 | pr-ready-guard-2 | fix by lane pr-ready-guard-2: lane round 3 | lane | 115.9h RED / ledger: open |
| #1632 | npm-alias-gaps-2 | fix by lane npm-alias-gaps-2: lane round 3 | lane | 115.7h RED / ledger: open |
| #1636 | guard-path-expand-forms | fix by lane guard-path-expand-forms: lane round 1 | lane | 113.6h RED / ledger: bad |
| #1642 | draft-pr-python-run-body | close as replaced by #2750, after a check that old-only files land there or are dropped | coordinator | 101.7h RED / ledger: stale |
| #1647 | script-glued-input | fix by lane script-glued-input: lane round 3 | lane | 114.9h RED / ledger: open |
| #1653 | replay-block-failed-imports | close as replaced by #2696, after a check that old-only files land there or are dropped | coordinator | 115.2h RED / ledger: no record |
| #1658 | fed-write-followups-2 | close as replaced by #2774, after a check that old-only files land there or are dropped | coordinator | 103.7h RED / ledger: stale |
| #1678 | record-after-each-round-build | closed as replaced by #2771 (done, comment posted, branch kept) | none |  |
| #1684 | fed-write-followups-3 | close as replaced by #2774, after a check that old-only files land there or are dropped | coordinator | 103.7h RED / ledger: stale |
| #1687 | mcp-safety-gaps | fix by lane mcp-safety-gaps: lane round 3 | lane | 94.0h RED / ledger: open |
| #1692 | claude/sim-drive-lease | fix by lane claude/sim-drive-lease: lane lint | lane | 101.2h RED / ledger: no lint |
| #1706 | record-post-parses-2 | fix by lane record-post-parses-2: lane lint | lane | 98.1h RED / ledger: no lint |
| #1707 | record-drop-edit-2 | fix by lane record-drop-edit-2: lane lint | lane | 56.4h / ledger: no lint |
| #1708 | lock-listed-stdout-only | fix by lane lock-listed-stdout-only: lane round 3 | lane | 96.1h RED / ledger: open |
| #1713 | draft-pr-backtick-span-dotall | close as replaced by #2750, after a check that old-only files land there or are dropped | coordinator | 101.7h RED / ledger: no lint |
| #1714 | lane/handoff-bash-redirect | fix by lane lane/handoff-bash-redirect: lane round 3 | lane | 108.2h RED / ledger: open |
| #1715 | claude/mutate-sweep-ctl | fix by lane claude/mutate-sweep-ctl: lane round 2 | lane | 104.6h RED / ledger: open |
| #1718 | stall-watch-open-call-cap | closed as replaced by #2697 (done, comment posted, branch kept) | none |  |
| #1722 | record-edit-judged-by-1687 | fix by lane record-edit-judged-by-1687: fresh full review | lane | 56.6h / ledger: stale |
| #1729 | sha-hex-one-home | fix by lane sha-hex-one-home: lane round 3 | lane | 96.1h RED / ledger: open |
| #1732 | lane/builder-checkout-test-path | fix by lane lane/builder-checkout-test-path: lane lint | lane | 112.5h RED / ledger: no lint |
| #1733 | nfp-narrow-paused-cell | fix by lane nfp-narrow-paused-cell: lane round 2 | lane | 102.1h RED / ledger: open |
| #1743 | retire-lines-to-batch-body | fix by lane retire-lines-to-batch-body: lane round 1 | lane | 104.6h RED / ledger: bad |
| #1748 | lane/lane-finds-triage | fix by lane lane/lane-finds-triage: lane lint | lane | 101.1h RED / ledger: no lint |
| #1751 | review-record-provenance | fix by lane review-record-provenance: lane lint | lane | 58.8h / ledger: no lint |
| #1753 | deferred-run-tighten | fix by lane deferred-run-tighten: lane round 1 | lane | 104.6h RED / ledger: bad |
| #1758 | review-cite-depth | fix by lane review-cite-depth: lane lint | lane | 97.7h RED / ledger: no lint |
| #1760 | record-post-runs-lane-lint | fix by lane record-post-runs-lane-lint: lane lint | lane | 109.8h RED / ledger: no lint |
| #1771 | claude/coord-pick-needs-record | fix by lane claude/coord-pick-needs-record: lane round 3 | lane | 104.3h RED / ledger: open |
| #1779 | roadmap-blank-pages | fix by lane roadmap-blank-pages: lane round 1 | lane | 109.5h RED / ledger: no record |
| #1784 | export-writer-label | fix by lane export-writer-label: lane round 3 | lane | 109.5h RED / ledger: open |
| #1789 | review-rounds-merge-2 | fix by lane review-rounds-merge-2: lane lint | lane | 102.1h RED / ledger: no lint |
| #1799 | notes-kd-install-false-red-2 | closed as replaced by #2675 (done, comment posted, branch kept) | none |  |
| #1805 | msg-role-scope-2 | fix by lane msg-role-scope-2: lane lint | lane | 40.5h / ledger: no lint |
| #1811 | reviewed-roots-cost-cases | fix by lane reviewed-roots-cost-cases: fresh full review | lane | 107.2h RED / ledger: stale |
| #1813 | merge-passes-settings-dir | fix by lane merge-passes-settings-dir: lane lint | lane | 107.8h RED / ledger: no lint |
| #1826 | notes-guard2-tmpdir2 | fix by lane notes-guard2-tmpdir2: lane round 1 | lane | 97.0h RED / ledger: open |
| #1829 | fix-check-chain-v3 | fix by lane fix-check-chain-v3: lane lint | lane | 102.1h RED / ledger: no lint |
| #1831 | lane-lint-unshallow-2 | fix by lane lane-lint-unshallow-2: lane round 1 | lane | 106.2h RED / ledger: no record |
| #1835 | stall-watch-round3-notes | fix by lane stall-watch-round3-notes: lane lint | lane | 97.2h RED / ledger: no lint |
| #1836 | quote-home-follow-up | fix by lane quote-home-follow-up: lane lint | lane | 103.7h RED / ledger: no lint |
| #1839 | fix-check-net-freeze | fix by lane fix-check-net-freeze: lane lint | lane | 104.9h RED / ledger: no lint |
| #1843 | lane-lint-parallel-cap | closed as replaced by #2749 (done, comment posted, branch kept) | none |  |
| #1844 | lane-lint-hook-suites | fix by lane lane-lint-hook-suites: lane lint | lane | 95.5h RED / ledger: no lint |
| #1848 | roots-cover-repo-tags | fix by lane roots-cover-repo-tags: lane lint | lane | 105.0h RED / ledger: no lint |
| #1849 | msg-role-fa | fix by lane msg-role-fa: lane lint | lane | 51.1h / ledger: no lint |
| #1858 | test-dirs-include-testing | close as replaced by #2686, after a check that old-only files land there or are dropped | coordinator | 105.5h RED / ledger: no record |
| #1861 | idle-lane-fu3 | fix by lane idle-lane-fu3: lane lint | lane | 97.3h RED / ledger: no lint |
| #1863 | heredoc-keep-gap-cases | fix by lane heredoc-keep-gap-cases: lane round 3 | lane | 103.8h RED / ledger: open |
| #1869 | silent-undo-checks-pr-base | fix by lane silent-undo-checks-pr-base: lane round 1 | lane | 96.1h RED / ledger: bad |
| #1871 | merge-unreviewed-final | fix by lane merge-unreviewed-final: lane lint | lane | 100.1h RED / ledger: no lint |
| #1872 | lease-remedy-fix | close as replaced by #2724, after a check that old-only files land there or are dropped | coordinator | 103.8h RED / ledger: no lint |
| #1873 | fix-check-freeze-label | fix by lane fix-check-freeze-label: lane lint | lane | 104.8h RED / ledger: no lint |
| #1881 | fix-check-remedy-text | fix by lane fix-check-remedy-text: lane round 3 | lane | 102.0h RED / ledger: open |
| #1892 | fix-check-round-lines | fix by lane fix-check-round-lines: lane lint | lane | 102.0h RED / ledger: no lint |
| #1897 | lane-lint-mutant-anchors | fix by lane lane-lint-mutant-anchors: lane lint | lane | 103.8h RED / ledger: no lint |
| #1900 | roots-guard-forms | fix by lane roots-guard-forms: lane lint | lane | 101.9h RED / ledger: no lint |
| #1906 | other-checkout-heredoc-text-v2 | close as replaced by #2789, after a check that old-only files land there or are dropped | coordinator | 82.3h RED / ledger: no lint |
| #1916 | lane-lint-other-jobs | fix by lane lane-lint-other-jobs: lane lint | lane | 100.6h RED / ledger: no lint |
| #1917 | resume-finished-reviewer | closed as replaced by #2771 (done, comment posted, branch kept) | none |  |
| #1935 | pe-guard-false-alarms-r3-build | fix by lane pe-guard-false-alarms-r3-build: lane round 1 | lane | 103.0h RED / ledger: bad |
| #1938 | pin-notes-follow-up | fix by lane pin-notes-follow-up: lane round 2 | lane | 103.0h RED / ledger: open |
| #1951 | fix-check-wording | fix by lane fix-check-wording: lane lint | lane | 102.1h RED / ledger: no lint |
| #1952 | stall-watch-live-run | closed as replaced by #2680 (done, comment posted, branch kept) | none |  |
| #1958 | lane/timing-tests-3 | fix by lane lane/timing-tests-3: lane lint | lane | 72.5h RED / ledger: no lint |
| #1964 | nfp-merge-records-print | fix by lane nfp-merge-records-print: lane round 2 | lane | 101.9h RED / ledger: open |
| #1971 | mcp-write-open-pin-2 | fix by lane mcp-write-open-pin-2: lane lint | lane | 57.1h / ledger: no lint |
| #1974 | resume-any-finished-agent | closed as replaced by #2771 (done, comment posted, branch kept) | none |  |
| #1975 | narrated-tee-tail | fix by lane narrated-tee-tail: lane lint | lane | 45.9h / ledger: no lint |
| #1981 | cost-line-pinned | fix by lane cost-line-pinned: lane lint | lane | 80.9h RED / ledger: no lint |
| #1984 | guard-relative-write-escape | close as replaced by #2691, after a check that old-only files land there or are dropped | coordinator | 98.0h RED / ledger: no record |
| #1987 | builder-amend-msg-only | fix by lane builder-amend-msg-only: lane lint | lane | 99.9h RED / ledger: no lint |
| #1992 | cost-pins-gaps | fix by lane cost-pins-gaps: lane lint | lane | 80.9h RED / ledger: no lint |
| #1993 | cmk-interp-body-git | close as replaced by #2813, after a check that old-only files land there or are dropped | coordinator | 84.9h RED / ledger: stale |
| #1995 | merge-glued-paren | blocked on #1900 (stacked) | lane | 99.8h RED / ledger: no record |
| #2001 | lane-lint-guard-suite-install | fix by lane lane-lint-guard-suite-install: lane round 1 | lane | 101.1h RED / ledger: no record |
| #2002 | lane/timing-tests-4 | fix by lane lane/timing-tests-4: lane lint | lane | 72.6h RED / ledger: no lint |
| #2015 | check-tail-any-filter | fix by lane check-tail-any-filter: lane lint | lane | 45.8h / ledger: no lint |
| #2017 | lane-lint-suites-picked | fix by lane lane-lint-suites-picked: lane lint | lane | 98.4h RED / ledger: no lint |
| #2024 | nfp-qform-ps-span-gaps | fix by lane nfp-qform-ps-span-gaps: fresh full review | lane | 59.4h / ledger: stale |
| #2026 | notes-fix-feedback-followup | fix by lane notes-fix-feedback-followup: lane lint | lane | 99.9h RED / ledger: no lint |
| #2030 | notes-fix-misc-followup | fix by lane notes-fix-misc-followup: lane round 3 | lane | 100.1h RED / ledger: open |
| #2033 | claude/sim-drive-limits | fix by lane claude/sim-drive-limits: lane round 3 | lane | 99.9h RED / ledger: open |
| #2049 | role-ids-on-1748 | fix by lane role-ids-on-1748: lane lint | lane | 99.5h RED / ledger: no lint |
| #2052 | env-folder-false-alarms | fix by lane env-folder-false-alarms: lane lint | lane | 59.0h / ledger: no lint |
| #2055 | export-check-writer-page | fix by lane export-check-writer-page: lane round 1 | lane | 99.4h RED / ledger: no record |
| #2061 | claude/sim-hold-nolist | fix by lane claude/sim-hold-nolist: lane round 2 | lane | 99.1h RED / ledger: open |
| #2063 | stale010-top-folder | fix by lane stale010-top-folder: lane lint | lane | 96.8h RED / ledger: no lint |
| #2067 | unreviewed-notes-wording | fix by lane unreviewed-notes-wording: lane round 2 | lane | 99.7h RED / ledger: open |
| #2071 | split-and-in-subst | blocked on #1995 (stacked) | lane | 96.1h RED / ledger: no record |
| #2081 | lane/time-pinned-plan-refresh | merge in the next batch | batch runner | 71.7h RED / ledger: done |
| #2083 | cmk-git-timeout-unread | fix by lane cmk-git-timeout-unread: lane lint | lane | 59.2h / ledger: no lint |
| #2087 | draft-pr-ps-herestring-r2 | close as replaced by #2750, after a check that old-only files land there or are dropped | coordinator | 97.8h RED / ledger: no lint |
| #2097 | guard-sibling-write-forms | fix by lane guard-sibling-write-forms: lane round 1 | lane | 99.3h RED / ledger: no record |
| #2099 | after-cd-errexit | fix by lane after-cd-errexit: fix check | lane | 96.8h RED / ledger: stale |
| #2115 | review-cite-followups | fix by lane review-cite-followups: lane lint | lane | 98.0h RED / ledger: no lint |
| #2119 | scratchpad-owner-follow-ups | close as replaced by #2830, after a check that old-only files land there or are dropped | coordinator | 59.0h / ledger: no lint |
| #2123 | coord-tier-self-tag | fix by lane coord-tier-self-tag: lane lint | lane | 56.3h / ledger: no lint |
| #2129 | push-report-followups | fix by lane push-report-followups: lane lint | lane | 97.8h RED / ledger: no lint |
| #2144 | push-after-check-semicolon | fix by lane push-after-check-semicolon: lane lint | lane | 58.3h / ledger: no lint |
| #2146 | range-lane-notes | fix by lane range-lane-notes: lane lint | lane | 97.9h RED / ledger: no lint |
| #2148 | lane-lows-followup | fix by lane lane-lows-followup: lane lint | lane | 90.0h RED / ledger: no lint |
| #2156 | check-tail-glued-amp | fix by lane check-tail-glued-amp: fix check | lane | 82.3h RED / ledger: stale |
| #2160 | lane-hold-ends-on-cause | fix by lane lane-hold-ends-on-cause: lane lint | lane | 97.7h RED / ledger: no lint |
| #2164 | pipe-exit-gap-forms-2 | fix by lane pipe-exit-gap-forms-2: lane lint | lane | 46.1h / ledger: no lint |
| #2167 | ci-wake-filter-gaps | fix by lane ci-wake-filter-gaps: lane lint | lane | 97.1h RED / ledger: no lint |
| #2171 | env-walk-limits | fix by lane env-walk-limits: lane lint | lane | 58.8h / ledger: no lint |
| #2173 | lane/option-tradeoff-pushback | fix by lane lane/option-tradeoff-pushback: lane round 1 | lane | 96.4h RED / ledger: no record |
| #2195 | past-ruling-owner-only | fix by lane past-ruling-owner-only: lane lint | lane | 92.7h RED / ledger: no lint |
| #2196 | cite-range-symbol-match | fix by lane cite-range-symbol-match: lane round 3 | lane | 94.5h RED / ledger: open |
| #2197 | relative-write-absolute-cd | fix by lane relative-write-absolute-cd: lane round 1 | lane | 96.7h RED / ledger: no record |
| #2200 | review-record-past-head | fix by lane review-record-past-head: lane lint | lane | 59.3h / ledger: no lint |
| #2226 | waiter-monitor-allowed | fix by lane waiter-monitor-allowed: lane lint | lane | 94.2h RED / ledger: no lint |
| #2230 | report-guard-spawn-model-fix | fix by lane report-guard-spawn-model-fix: lane round 3 | lane | 95.3h RED / ledger: open |
| #2234 | quoted-args-unresolved | fix by lane quoted-args-unresolved: lane lint | lane | 91.4h RED / ledger: no lint |
| #2262 | ste-lint-run-exit-codes | fix by lane ste-lint-run-exit-codes: lane lint | lane | 94.6h RED / ledger: no lint |
| #2265 | msg-ref-pr-forms | fix by lane msg-ref-pr-forms: lane lint | lane | 93.5h RED / ledger: no lint |
| #2268 | open-asks-at-wake-v3 | close as replaced by #2699, after a check that old-only files land there or are dropped | coordinator | 48.9h / ledger: stale |
| #2276 | guard-set-gap-pins-2 | fix by lane guard-set-gap-pins-2: lane lint | lane | 46.1h / ledger: no lint |
| #2277 | record-rounds-name-own-head | fix by lane record-rounds-name-own-head: lane lint | lane | 59.3h / ledger: no lint |
| #2297 | live-stream-monitor-remedy | fix by lane live-stream-monitor-remedy: lane round 1 | lane | 93.4h RED / ledger: no record |
| #2300 | nfp-ci-scope-cases | fix by lane nfp-ci-scope-cases: lane lint | lane | 93.0h RED / ledger: no lint |
| #2301 | guard-import-fails-closed-2 | fix by lane guard-import-fails-closed-2: lane lint | lane | 46.1h / ledger: no lint |
| #2317 | answered-section-folded | closed as replaced by #2756 (done, comment posted, branch kept) | none |  |
| #2321 | hooks-home-lookups | fix by lane hooks-home-lookups: lane lint | lane | 46.1h / ledger: no lint |
| #2322 | builder-diff-auto-merge-reflog-r2 | fix by lane builder-diff-auto-merge-reflog-r2: lane lint | lane | 90.6h RED / ledger: no lint |
| #2326 | review-record-stack | fix by lane review-record-stack: lane lint | lane | 51.0h / ledger: no lint |
| #2347 | nfp-ux-text-zoom | fix by lane nfp-ux-text-zoom: lane lint | lane | 51.3h / ledger: no lint |
| #2365 | fix-base-own-round-head | fix by lane fix-base-own-round-head: lane lint | lane | 59.2h / ledger: no lint |
| #2440 | record-guard-wrapper-forms | fix by lane record-guard-wrapper-forms: lane lint | lane | 71.7h / ledger: no lint |
| #2463 | lane/lane-push-frozen-in-batch | fix by lane lane/lane-push-frozen-in-batch: lane lint | lane | 51.6h / ledger: no lint |
| #2483 | cloud-allow-rules | fix by lane cloud-allow-rules: lane round 2 | lane | 41.7h / ledger: open |
| #2486 | agent-served-model-check-build-2 | close as replaced by #2722, after a check that old-only files land there or are dropped | coordinator | 59.2h / ledger: no lint |
| #2491 | worktree-merge-route-author-paths | fix by lane worktree-merge-route-author-paths: lane round 1 | lane | 63.6h / ledger: no record |
| #2500 | close-replaced-at-open | fix by lane close-replaced-at-open: lane lint | lane | 59.3h / ledger: no lint |
| #2520 | artifact-lane | closed as replaced by #2684 (done, comment posted, branch kept) | none |  |
| #2527 | item-cite-carries-name-build | fix by lane item-cite-carries-name-build: lane lint | lane | 55.2h / ledger: no lint |
| #2549 | ta4-artifact-guard-matcher-names | fix by lane ta4-artifact-guard-matcher-names: lane lint | lane | 50.7h / ledger: no lint |
| #2562 | lane-brief-cites-grant | fix by lane lane-brief-cites-grant: fresh full review | lane | 45.9h / ledger: stale |
| #2572 | both-session-starts-judged | fix by lane both-session-starts-judged: lane round 2 | lane | 42.0h / ledger: open |
| #2654 | lane/split-round2-notes | merge in the next batch | batch runner | 5.3h / ledger: done |
| #2655 | prose-back-flagged-3 | merge in the next batch | batch runner | 5.3h / ledger: done |
| #2656 | override-docstring-later-line | merge in the next batch | batch runner | 5.3h / ledger: done |
| #2658 | notes-fix-no-owner-line | merge in the next batch | batch runner | 5.1h / ledger: done |
| #2659 | silent-undo-session-url-line | merge in the next batch | batch runner | 4.8h / ledger: done |
| #2660 | glossary-page-row | merge in the next batch | batch runner | 5.0h / ledger: done |
| #2661 | roster-on-record-branch-prose | merge in the next batch | batch runner | 4.7h / ledger: done |
| #2662 | spend-log-batch-decision | merge in the next batch | batch runner | 4.8h / ledger: done |
| #2663 | usage-brake-decision | merge in the next batch | batch runner | 4.8h / ledger: done |
| #2664 | builder-report-in-head-3 | merge in the next batch | batch runner | 4.1h / ledger: done |
| #2665 | input-needed-reads-page-status-2 | merge in the next batch | batch runner | 3.8h / ledger: done |
| #2666 | override-strips-status-block-2 | merge in the next batch | batch runner | 4.1h / ledger: done |
| #2667 | close-replaced-at-open-2 | merge in the next batch | batch runner | 1.2h / ledger: done |
| #2669 | cost-pins-carry | merge in the next batch | batch runner | 4.1h / ledger: done |
| #2670 | consultant-and-queue | merge in the next batch | batch runner | 3.9h / ledger: done |
| #2671 | timer-rule-reason-only | merge in the next batch | batch runner | 3.9h / ledger: done |
| #2672 | watch-finds-transcript | merge in the next batch | batch runner | 3.0h / ledger: done |
| #2673 | outbox-home-check | merge in the next batch | batch runner | 4.1h / ledger: done |
| #2674 | lane-inflow-hold-carry | merge in the next batch | batch runner | 3.9h / ledger: done |
| #2675 | replay-1799-carry | merge in the next batch | batch runner | 2.8h / ledger: done |
| #2676 | check-line-reader-3 | merge in the next batch | batch runner | 4.1h / ledger: done |
| #2677 | export-after-page-write-2 | merge in the next batch | batch runner | 4.0h / ledger: done |
| #2678 | cloud-branch-delete | merge in the next batch | batch runner | 0.9h / ledger: done |
| #2679 | rule-mechanisms-style-count | fix by lane rule-mechanisms-style-count: lane round 1 | lane | 4.7h / ledger: no record |
| #2680 | stall-watch-live-run-2 | fix by lane stall-watch-live-run-2: lane round 3 | lane | 3.7h / ledger: open |
| #2681 | question-form-task-context | merge in the next batch | batch runner | 4.9h / ledger: done |
| #2682 | option-keys-carry | merge in the next batch | batch runner | 2.2h / ledger: done |
| #2683 | unknown-read-carry | merge in the next batch | batch runner | 0.4h / ledger: done |
| #2684 | artifact-lane-carry | merge in the next batch | batch runner | 2.7h / ledger: done |
| #2685 | handoff-keeps-owner-waits-2 | merge in the next batch | batch runner | 3.6h / ledger: done |
| #2686 | test-dirs-testing-folder | merge in the next batch | batch runner | 4.7h / ledger: done |
| #2687 | carry-dead-code-cite | merge in the next batch | batch runner | 3.8h / ledger: done |
| #2688 | trial-brief-triage-by-role | fix by lane trial-brief-triage-by-role: lane round 1 | lane | 4.7h / ledger: no record |
| #2689 | lock-delete-race-carry | merge in the next batch | batch runner | 3.1h / ledger: done |
| #2690 | reviewer-round-two-sonnet | merge in the next batch | batch runner | 4.3h / ledger: done |
| #2691 | lane/guard-relative-write-escape-carry | fix by lane lane/guard-relative-write-escape-carry: lane round 2 | lane | 2.9h / ledger: open |
| #2692 | lane/commit-trailer-model-carry | fix by lane lane/commit-trailer-model-carry: lane round 2 | lane | 3.0h / ledger: open |
| #2693 | lane/brief-write-needs-writer-tests | merge in the next batch | batch runner | 2.8h / ledger: done |
| #2694 | idle-lane-steps-unknown-2 | merge in the next batch | batch runner | 4.7h / ledger: done |
| #2695 | page-answer-session-field-2 | merge in the next batch | batch runner | 4.3h / ledger: done |
| #2696 | replay-block-failed-imports-4 | merge in the next batch | batch runner | 2.8h / ledger: done |
| #2697 | carry/stall-watch-open-call-cap | fix by lane carry/stall-watch-open-call-cap: lane lint | lane | 3.8h / ledger: no lint |
| #2698 | restart-plan-free-gate | merge in the next batch | batch runner | 4.6h / ledger: done |
| #2699 | carry/open-asks-at-wake | merge in the next batch | batch runner | 0.5h / ledger: done |
| #2700 | lane-lint-bg-timeout | merge in the next batch | batch runner | 3.4h / ledger: done |
| #2701 | solo-batch-hat | merge in the next batch | batch runner | 1.8h / ledger: done |
| #2702 | skill-text-once-v2 | merge in the next batch | batch runner | 4.6h / ledger: done |
| #2703 | page-thread-reply-refused | merge in the next batch | batch runner | 4.5h / ledger: done |
| #2704 | carry-why-cite-act | merge in the next batch | batch runner | 4.2h / ledger: done |
| #2705 | widening-rule-guideline-2 | merge in the next batch | batch runner | 3.7h / ledger: done |
| #2706 | pr-template-stays-guard | fix by lane pr-template-stays-guard: lane round 1 | lane | 4.4h / ledger: open |
| #2707 | find-copies-pr-template | merge in the next batch | batch runner | 4.6h / ledger: done |
| #2708 | pr-template-copies-equal | merge in the next batch | batch runner | 4.7h / ledger: done |
| #2709 | lane/lane-finds-triage-4 | fix by lane lane/lane-finds-triage-4: fresh full review | lane | 2.7h / ledger: stale |
| #2710 | catalog-model-per-event | merge in the next batch | batch runner | 4.5h / ledger: done |
| #2711 | carry-stale-flags-impl | merge in the next batch | batch runner | 3.5h / ledger: done |
| #2712 | agent-process-marker-carry | merge in the next batch | batch runner | 2.5h / ledger: done |
| #2714 | lane/agent-output-terse-line-stub | fix by lane lane/agent-output-terse-line-stub: lane round 3 | lane | 2.3h / ledger: open |
| #2715 | carry-shoot-touch-per-size | merge in the next batch | batch runner | 4.0h / ledger: done |
| #2716 | carry-shoot-stitch-pinned | merge in the next batch | batch runner | 3.9h / ledger: done |
| #2717 | carry-shoot-touch-widths | merge in the next batch | batch runner | 3.9h / ledger: done |
| #2718 | testing-folder-note | fix by lane testing-folder-note: lane round 1 | lane | 4.5h / ledger: no record |
| #2719 | lane-lint-time-carry | merge in the next batch | batch runner | 3.8h / ledger: done |
| #2720 | page-time-field-valid | merge in the next batch | batch runner | 4.4h / ledger: done |
| #2721 | carry/waiting-export-receipts | merge in the next batch | batch runner | 3.5h / ledger: done |
| #2722 | carry/builder-model-pin | fix by lane carry/builder-model-pin: lane lint | lane | 3.8h / ledger: no lint |
| #2723 | pwsh-followups-2 | merge in the next batch | batch runner | 2.0h / ledger: done |
| #2724 | lease-remedy-form-c | merge in the next batch | batch runner | 3.8h / ledger: done |
| #2725 | carry-builder-test-cfg | merge in the next batch | batch runner | 3.0h / ledger: done |
| #2726 | retarget-checked-with-role-build | merge in the next batch | batch runner | 3.6h / ledger: done |
| #2727 | merge-kind-diff-check | merge in the next batch | batch runner | 4.1h / ledger: done |
| #2728 | model-auth-build | merge in the next batch | batch runner | 3.4h / ledger: done |
| #2729 | dead-pr-waits | merge in the next batch | batch runner | 2.2h / ledger: done |
| #2731 | silent-undo-pr-base | fix by lane silent-undo-pr-base: lane round 1 | lane | 4.2h / ledger: no record |
| #2732 | page-lane-scope-notes | fix by lane page-lane-scope-notes: lane round 1 | lane | 4.2h / ledger: no record |
| #2733 | mutate-harness-change-timed-run-2 | merge in the next batch | batch runner | 3.0h / ledger: done |
| #2734 | lane-undo-check-3 | fix by lane lane-undo-check-3: lane round 1 | lane | 1.8h / ledger: bad |
| #2735 | carry-1516-names-fix | merge in the next batch | batch runner | 3.9h / ledger: done |
| #2736 | carry-reviewed-sends-back-build | merge in the next batch | batch runner | 3.3h / ledger: done |
| #2737 | judge-replay-corpus-2 | fix by lane judge-replay-corpus-2: lane round 2 | lane | 2.8h / ledger: open |
| #2739 | carry-lane-end-releases-steps | merge in the next batch | batch runner | 4.1h / ledger: done |
| #2740 | carry/past-ruling-on-send | merge in the next batch | batch runner | 2.8h / ledger: done |
| #2741 | shard-mutate-guard | merge in the next batch | batch runner | 3.9h / ledger: done |
| #2742 | carry/page-pics-fill-card | merge in the next batch | batch runner | 3.2h / ledger: done |
| #2743 | notes-dedup | merge in the next batch | batch runner | 4.1h / ledger: done |
| #2744 | pwsh-r3-2 | merge in the next batch | batch runner | 1.9h / ledger: done |
| #2745 | main-job-cap-alarm | fix by lane main-job-cap-alarm: fix check | lane | 0.3h / ledger: stale |
| #2747 | carry-runner-drops-handed-lane-build | merge in the next batch | batch runner | 2.1h / ledger: done |
| #2748 | carry-agent-report-shas-resolve-build | merge in the next batch | batch runner | 1.5h / ledger: done |
| #2749 | lane/lint-slot-carry-build | merge in the next batch | batch runner | 3.0h / ledger: done |
| #2750 | draft-pr-carry | merge in the next batch | batch runner | 2.5h / ledger: done |
| #2751 | lane-ack-question | merge in the next batch | batch runner | 3.4h / ledger: done |
| #2752 | map-reader-gaps | merge in the next batch | batch runner | 3.3h / ledger: done |
| #2753 | pwsh-r3-limits-2 | merge in the next batch | batch runner | 1.8h / ledger: done |
| #2755 | lane-session-model-check-e | merge in the next batch | batch runner | 3.8h / ledger: done |
| #2756 | answered-section-folded-2 | merge in the next batch | batch runner | 2.7h / ledger: done |
| #2757 | record-gloss-link-checks | merge in the next batch | batch runner | 2.3h / ledger: done |
| #2758 | lane/branch-force-worktree-build | merge in the next batch | batch runner | 3.8h / ledger: done |
| #2759 | plain-push-asks-cite | merge in the next batch | batch runner | 3.8h / ledger: done |
| #2761 | lane-title-slug-build | merge in the next batch | batch runner | 3.5h / ledger: done |
| #2762 | carry-qform-merge | merge in the next batch | batch runner | 0.4h / ledger: done |
| #2763 | carry-silent-undo-ci-body | merge in the next batch | batch runner | 0.2h / ledger: done |
| #2764 | carry-review-range-check | merge in the next batch | batch runner | 0.4h / ledger: done |
| #2765 | carry-pre-existing-needs-main-run | fix by lane carry-pre-existing-needs-main-run: lane round 1 | lane | 1.0h / ledger: no record |
| #2766 | stamp-unscanned-pending-cite | merge in the next batch | batch runner | 3.6h / ledger: done |
| #2767 | outbox-home-check-build | merge in the next batch | batch runner | 2.7h / ledger: done |
| #2768 | lane/child-repo-scope-fix | merge in the next batch | batch runner | 3.2h / ledger: done |
| #2769 | watch-transcript-fallback-build | merge in the next batch | batch runner | 2.8h / ledger: done |
| #2770 | no-ci-starter | fix by lane no-ci-starter: lane round 3 | lane | 2.2h / ledger: open |
| #2771 | resume-carry | fix by lane resume-carry: lane lint | lane | 3.1h / ledger: no lint |
| #2772 | debt-merge-shard-caps-prose | fix by lane debt-merge-shard-caps-prose: lane round 1 | lane | 3.4h / ledger: no record |
| #2774 | fed-write-carry | merge in the next batch | batch runner | 2.1h / ledger: done |
| #2775 | one-load-definition-f | merge in the next batch | batch runner | 2.0h / ledger: done |
| #2777 | notes-prose-guard-2 | fix by lane notes-prose-guard-2: lane round 1 | lane | 3.3h / ledger: no record |
| #2778 | item-reply-back-2 | fix by lane item-reply-back-2: lane round 3 | lane | 3.1h / ledger: open |
| #2779 | records-page-ready-reads-pr-repo | merge in the next batch | batch runner | 3.0h / ledger: done |
| #2780 | carry/reviewer-brief-blind | fix by lane carry/reviewer-brief-blind: lane lint | lane | 0.8h / ledger: no lint |
| #2781 | repeat-judge-never-blocks | merge in the next batch | batch runner | 2.6h / ledger: done |
| #2782 | carry-ruling-cite-in-commit-c | merge in the next batch | batch runner | 3.2h / ledger: done |
| #2783 | carry-1479-stack | merge in the next batch | batch runner | 3.1h / ledger: done |
| #2784 | lane-notes-prose-fanout | merge in the next batch | batch runner | 2.6h / ledger: done |
| #2786 | replay-profile-parts-3 | fix by lane replay-profile-parts-3: lane round 2 | lane | 1.5h / ledger: open |
| #2787 | carry-sim-lease-gaps | merge in the next batch | batch runner | 2.2h / ledger: done |
| #2788 | carry-ruling-skip-check | merge in the next batch | batch runner | 2.7h / ledger: done |
| #2789 | other-checkout-heredoc-text-6 | merge in the next batch | batch runner | 2.6h / ledger: done |
| #2790 | glossary-prose-renames | merge in the next batch | batch runner | 2.4h / ledger: done |
| #2791 | lane/branch-slug-rule-build | merge in the next batch | batch runner | 2.7h / ledger: done |
| #2792 | carry/ask-phase-out | fix by lane carry/ask-phase-out: lane round 1 | lane | 2.1h / ledger: no record |
| #2793 | lane-stable-mover | merge in the next batch | batch runner | 1.8h / ledger: done |
| #2795 | carry-stall-watch-quiet-lint-b | merge in the next batch | batch runner | 1.8h / ledger: done |
| #2796 | merge-commit-debt-retire | merge in the next batch | batch runner | 2.3h / ledger: done |
| #2797 | carry/past-ruling-s1-block | merge in the next batch | batch runner | 2.3h / ledger: done |
| #2798 | carry-xctestplan-config | merge in the next batch | batch runner | 1.4h / ledger: done |
| #2799 | notes-name-their-fix-stack | blocked on #2735 (stacked) | lane | 2.0h / ledger: bad |
| #2800 | stall-watch-round3-notes-3 | merge in the next batch | batch runner | 2.0h / ledger: done |
| #2801 | guard-tables-per-section | merge in the next batch | batch runner | 1.5h / ledger: done |
| #2802 | prose/waiting-page-skill-text-fixes | fix by lane prose/waiting-page-skill-text-fixes: lane round 1 | lane | 1.2h / ledger: no record |
| #2803 | stale-cites-plans | fix by lane stale-cites-plans: lane round 1 | lane | 1.9h / ledger: no record |
| #2804 | stale-cites-decisions | fix by lane stale-cites-decisions: lane round 1 | lane | 1.9h / ledger: no record |
| #2805 | stale-cites-design-debts | fix by lane stale-cites-design-debts: lane round 1 | lane | 1.9h / ledger: no record |
| #2806 | notes-code-handoffs | fix by lane notes-code-handoffs: lane round 1 | lane | 1.9h / ledger: no record |
| #2807 | stale-cites-janitor-skills | fix by lane stale-cites-janitor-skills: lane round 1 | lane | 1.9h / ledger: no record |
| #2808 | carry-stall-log-kept-b | merge in the next batch | batch runner | 1.5h / ledger: done |
| #2809 | notes-review-limits | merge in the next batch | batch runner | 1.0h / ledger: done |
| #2811 | prose-round3-notes | merge in the next batch | batch runner | 1.3h / ledger: done |
| #2812 | undo-keep-prose | merge in the next batch | batch runner | 1.2h / ledger: done |
| #2813 | lane/interp-body-carry | merge in the next batch | batch runner | 1.5h / ledger: done |
| #2814 | batch-104 | batch run: merge when its CI is all-jobs-passed green | batch runner | 0.5h RED / ledger: no record |
| #2815 | lone-lane-merge-path | fix by lane lone-lane-merge-path: fix check | lane | 0.5h / ledger: stale |
| #2816 | runner-start-idle-lanes | fix by lane runner-start-idle-lanes: lane lint | lane | 1.3h / ledger: no lint |
| #2817 | archive-flow-list-flag | fix by lane archive-flow-list-flag: lane lint | lane | 1.4h / ledger: no lint |
| #2818 | lane-ruleset-read | fix by lane lane-ruleset-read: lane round 1 | lane | 0.1h / ledger: no record |
| #2819 | lane-installers-stable | fix by lane lane-installers-stable: lane round 1 | lane | 0.0h / ledger: no record |
| #2820 | batch-build-log-kept-r2 | fix by lane batch-build-log-kept-r2: lane round 1 | lane | 1.0h / ledger: no record |
| #2821 | undo-brief-sentence | merge in the next batch | batch runner | 1.2h / ledger: done |
| #2822 | notes-tidy-r41 | fix by lane notes-tidy-r41: lane round 1 | lane | 1.2h / ledger: no record |
| #2823 | outbox-notes-land | fix by lane outbox-notes-land: lane round 1 | lane | 1.2h / ledger: no record |
| #2824 | draft-pr-unquoted-body-2 | fix by lane draft-pr-unquoted-body-2: fix check | lane | 1.1h / ledger: stale |
| #2825 | lane/upkeep-keys-live-status | fix by lane lane/upkeep-keys-live-status: fresh full review | lane | 0.6h / ledger: stale |
| #2826 | carry-pre-existing-uses-clause | merge in the next batch | batch runner | 0.5h / ledger: done |
| #2827 | fix/asks-wake-fresh-save | merge in the next batch | batch runner | 0.4h / ledger: done |
| #2828 | ruling-parts-cite-steps | merge in the next batch | batch runner | 0.1h / ledger: done |
| #2829 | page-data-one-store | fix by lane page-data-one-store: fix check | lane | 0.3h / ledger: stale |
| #2830 | scratchpad-owner-follow-ups-2 | merge in the next batch | batch runner | 0.5h / ledger: done |
| #2831 | sed-operand-reader | fix by lane sed-operand-reader: lane round 1 | lane | 0.6h / ledger: no record |
| #2832 | lint-config-guard-paths-2 | fix by lane lint-config-guard-paths-2: lane lint | lane | 0.0h / ledger: no lint |
| #2833 | carry-send-message-refs-build | fix by lane carry-send-message-refs-build: lane round 1 | lane | 0.0h / ledger: no record |
| #2836 | stop-checks-one-message | fix by lane stop-checks-one-message: lane round 1 | lane | 0.1h / ledger: no record |
| #2837 | batch-build-stop-group-fix | merge in the next batch | batch runner | 0.4h / ledger: done |
| #2838 | blame-on-finished-red-job-v2 | fix by lane blame-on-finished-red-job-v2: lane round 1 | lane | 0.1h / ledger: bad |
| #2839 | ci-wait-cap-55-fix-prose | fix by lane ci-wait-cap-55-fix-prose: lane round 1 | lane | 0.4h / ledger: no record |
| #2840 | one-term-warn-lint-r2 | fix by lane one-term-warn-lint-r2: lane round 1 | lane | 0.1h / ledger: no record |
| #2841 | model-auth-key-build | merge in the next batch | batch runner | 0.0h / ledger: done |
| #2842 | ste001-drop-cap | merge in the next batch | batch runner | 0.2h / ledger: done |
| #2844 | ruling-challenge-passes-lint-2 | fix by lane ruling-challenge-passes-lint-2: lane round 1 | lane | 0.3h / ledger: no record |
| #2845 | lane/pr-state-is-on-the-pr | fix by lane lane/pr-state-is-on-the-pr: lane round 1 | lane | 0.1h / ledger: no record |
| #2846 | green-hook-draft-run-2 | fix by lane green-hook-draft-run-2: lane round 1 | lane | 0.0h / ledger: no record |
| #2847 | lane-lint-once-fail-fast | fix by lane lane-lint-once-fail-fast: lane round 1 | lane | 0.2h / ledger: no record |
| #2848 | archive-flow-prose | fix by lane archive-flow-prose: lane round 1 | lane | 0.1h / ledger: no record |
| #2849 | lane/mailbox-repo-default | fix by lane lane/mailbox-repo-default: lane round 1 | lane | 0.1h / ledger: no record |

## q_max (11 open)

Review state unread: this session has no access to q_max (add_repo not attached). Acts are from titles only.

| PR | Title | Next act | Owner |
|---|---|---|---|
| #1164 | CI pin move | read its review record, then batch or fix lane | child-repo batch runner (no ledger read: q_max not attached) |
| #1163 | Batch fix-1 | merge when CI is green, or close if its lanes already merged | child-repo batch runner |
| #1162 | Past Rates 1440 re-point | read its review record, then batch or fix lane | child-repo batch runner |
| #1161 | Batch ci-1 (11 h idle) | merge when CI is green, or close if its lanes already merged | child-repo batch runner |
| #1160 | CI batch-* heads | read its review record, then batch or fix lane | child-repo batch runner |
| #1159 | Prose wave redo of #970 | read its review record, then batch or fix lane | child-repo batch runner |
| #1158 | Batch prose-1 | merge when CI is green, or close if its lanes already merged | child-repo batch runner |
| #1157 | Docs: four prose-judge lines | read its review record, then batch or fix lane | child-repo batch runner |
| #1156 | dependabot setup-python | merge in a batch, or close | child-repo batch runner |
| #1155 | dependabot zizmor | merge in a batch, or close | child-repo batch runner |
| #1011 | Batch: ci-hygiene (#1008), 10 days idle | owner question: close or revive (step lists it unclassed) | coordinator |
