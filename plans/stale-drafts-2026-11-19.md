# Stale-draft ledger, 16:08 CST Nov 19

Owner goal item 8 (14:40 CST Nov 19) and pick a (16:03 CST Nov 19): write this ledger before the rest of the stale drafts are closed.

Sort rule: a draft whose last commit is before 2026-11-16 14:45 CST, that is not on the keep list, and has no owner ruling id missing from main. Patch tests found none of the 482 open PRs landed on main (merge-base, merge-tree, per-file blob, reverse apply, git cherry).

Not closed: the 18 owner-ruled PRs and the 43 kept PRs. A closed PR reopens from its page. Its branch stays.

Rows: 421 (123 owner-cited, 298 other). Closed 2026-11-19: 50. To close: 371. Conflicts with main: 334 yes, 87 no.

Reason key: stale = the sort rule holds. owner-cited = the body cites an owner ruling, pick or page item. replaced by = another open PR says it replaces this one. stacked on = its base is another PR on this list. stacked on branch = its base is a branch, not a PR.

Check before closing: 12 rows name a replacement that is also to close. Closing both leaves the work with no open PR. Each pair is old PR, then new PR: #1386, #2677; #1784, #3197; #1789, #3187; #1938, #3265; #2083, #3223; #2226, #3204; #2677, #3258; #2681, #3582; #2699, #3578; #2724, #3580; #2751, #3581; #2771, #3248. The replaced row #1760 names #3222, which is kept as owner-ruled.

Dates: 12 rows are dated 2026-11-16. Each head commit time was checked. All are before 14:45 CST that day. The latest, #3575, is 09:41 CST.

Titles: 222 titles are exactly 70 characters, so the stale list cut them there. A cut title stops mid-phrase. Row #3420 also stops early, at an ellipsis, to pass the plain-writing lint. Open the PR for its full title.

Sources: the stale list (its owner-cited and other sections, 421 lines). Branch names: origin's PR head refs matched to branch refs by commit (406), and GitHub's PR head refs where two branches shared a commit (15). State: the closed-today list (50 numbers).

## Ledger (421 rows, by PR number)

| PR | Branch | Title | Last commit | Conflicts with main | Reason | State |
|---|---|---|---|---|---|---|
| #1034 | prose-homes-shivpedia | Plan: one home per kind of prose, and shivpedia | 2026-11-02 | no | stale | to close |
| #1377 | challenger-page-against | Give each page decision a blind refuter's case against its pick | 2026-11-06 | yes | stale, owner-cited | closed 2026-11-19 |
| #1386 | export-after-page-write | Export check fires for a labelled page writer; promise guard for hando | 2026-11-07 | yes | stale, owner-cited, replaced by #2677 (also to close) | closed 2026-11-19 |
| #1432 | one-home-check | One-home check: copies, rewords, child exceptions, paraphrase pass | 2026-11-12 | yes | stale | to close |
| #1517 | notes-guard2-tmpdir | Session start gives the session a TMPDIR when the container has none | 2026-11-08 | yes | stale | to close |
| #1536 | nfp-rg-forms | Report guard: page links in any case or scheme form; more Recovered so | 2026-11-07 | yes | stale | to close |
| #1585 | push-report-gaps | push report: a failed branch read or an unnamed head reads unknown | 2026-11-08 | yes | stale, stacked on branch push-report-checks | to close |
| #1616 | compare-files-missing-key | Refuse a compare reply with no files list; run the lane lint before th | 2026-11-10 | yes | stale, stacked on #2326 | to close |
| #1618 | feedback-bad-mark | feedback guard: a bad rolled-out mark still reads the waiting folder a | 2026-11-07 | yes | stale, owner-cited, stacked on branch layout-rolled-out-bool | closed 2026-11-19 |
| #1619 | notes-sightings-expiry | A note counts its sightings and expires; each batch carries one debt-f | 2026-11-07 | yes | stale, owner-cited | closed 2026-11-19 |
| #1631 | pr-ready-guard-2 | draft-pr guard: a ready mark asks unless the PR is the integration PR | 2026-11-07 | yes | stale, owner-cited, stacked on branch mcp-merge-unguarded | closed 2026-11-19 |
| #1692 | claude/sim-drive-lease | Guard: refuse a drive of a booted phone with no lease of the session's | 2026-11-08 | yes | stale, stacked on branch claude/sim-lease-gaps | to close |
| #1714 | lane/handoff-bash-redirect | An agent's shell write into its session's handoff is refused | 2026-11-08 | yes | stale | to close |
| #1729 | sha-hex-one-home | One home each: the ls-remote reader (hooks/git_reads.py) and the sha p | 2026-11-08 | yes | stale | to close |
| #1732 | lane/builder-checkout-test-path | A builder cannot restore an old copy of a test file through git | 2026-11-08 | yes | stale | to close |
| #1733 | nfp-narrow-paused-cell | Waiting page and roadmap: narrow bars draw one run per state; paused i | 2026-11-08 | yes | stale, owner-cited | closed 2026-11-19 |
| #1753 | deferred-run-tighten | Defer only a lane commit's cite, and read only the head's own checks r | 2026-11-08 | yes | stale | to close |
| #1760 | record-post-runs-lane-lint | Run the lane lint before merge --review-record prints a record | 2026-11-08 | yes | stale, replaced by #3222 (not on this list) | to close |
| #1771 | claude/coord-pick-needs-record | Refuse a handoff ruling line with no resolving home | 2026-11-08 | yes | stale | to close |
| #1784 | export-writer-label | Match the page writer label by its id, so the export check fires for t | 2026-11-08 | yes | stale, replaced by #3197 (also to close) | to close |
| #1789 | review-rounds-merge-2 | Round 3 only when owed, labelled findings, and no review record with m | 2026-11-08 | yes | stale, owner-cited, replaced by #3187 (also to close), stacked on branch review-fix-check-round-2 | closed 2026-11-19 |
| #1805 | msg-role-scope-2 | Guard: a message to a running agent stays inside its role | 2026-11-11 | yes | stale | to close |
| #1811 | reviewed-roots-cost-cases | Batch runner follow-up: corrected stall cause, background long command | 2026-11-08 | yes | stale | to close |
| #1836 | quote-home-follow-up | One YAML quote reader; test local ste-lint and zizmor under pins | 2026-11-08 | yes | stale, stacked on branch pin-gaps-follow-up | to close |
| #1848 | roots-cover-repo-tags | Guard merge-roots-cover: a batch runner's --root set equals its cs-rep | 2026-11-08 | yes | stale, stacked on #1811 | to close |
| #1849 | msg-role-fa | Guard: message-role-scope stops refusing ordinary orchestrator message | 2026-11-10 | yes | stale | to close |
| #1863 | heredoc-keep-gap-cases | Heredoc-keep reader: cases and mutants for its known gaps; `$(< f)` re | 2026-11-08 | yes | stale | to close |
| #1871 | merge-unreviewed-final | merge --confirm refuses a lane tip with no done review record (single | 2026-11-08 | yes | stale, owner-cited, stacked on branch merge-guard-round3-r | closed 2026-11-19 |
| #1897 | lane-lint-mutant-anchors | Lane lint refuses a stale or ambiguous mutant anchor | 2026-11-08 | yes | stale | to close |
| #1900 | roots-guard-forms | Merge guard rules read every command form; a multi-repo runner cannot | 2026-11-08 | yes | stale, stacked on #1848 | to close |
| #1916 | lane-lint-other-jobs | Lane lint runs picked suites of other Linux jobs under their own limit | 2026-11-08 | yes | stale | to close |
| #1935 | pe-guard-false-alarms-r3-build | Pre-existing guard: fewer false alarms | 2026-11-08 | yes | stale, owner-cited | closed 2026-11-19 |
| #1938 | pin-notes-follow-up | Close the pinned-lint review notes | 2026-11-13 | yes | stale, replaced by #3265 (also to close), stacked on #1836 | to close |
| #1964 | nfp-merge-records-print | Merge guard: read every redirect form in the one redirect reader | 2026-11-08 | yes | stale, owner-cited | closed 2026-11-19 |
| #1971 | mcp-write-open-pin-2 | Pin the open set of each GitHub MCP write call | 2026-11-10 | yes | stale, owner-cited | closed 2026-11-19 |
| #2024 | nfp-qform-ps-span-gaps | Question form: read a pipe before a newline, $( ) prefixes, wrapped at | 2026-11-10 | yes | stale, owner-cited | closed 2026-11-19 |
| #2030 | notes-fix-misc-followup | Keep override's notice tags when config_dir is missing, and close the | 2026-11-08 | yes | stale | to close |
| #2033 | claude/sim-drive-limits | Guard: drive rule allows a hold drive under the session's own lease | 2026-11-08 | yes | stale, owner-cited, stacked on #1692 | closed 2026-11-19 |
| #2052 | env-folder-false-alarms | env guard follow-ups: hidden-search walks, wider ag regex reading, git | 2026-11-10 | yes | stale, owner-cited | closed 2026-11-19 |
| #2061 | claude/sim-hold-nolist | Guard tests: a hold drive with no device list is refused | 2026-11-08 | yes | stale, stacked on #2033 | to close |
| #2083 | cmk-git-timeout-unread | conflict-markers asks when a git read cannot run, instead of allowing | 2026-11-10 | yes | stale, replaced by #3223 (also to close) | to close |
| #2097 | guard-sibling-write-forms | other-checkout: refuse a python write and an agent's git -C write into | 2026-11-08 | yes | stale, owner-cited | closed 2026-11-19 |
| #2099 | after-cd-errexit | Guard: git-after-cd reads an exit only where it runs | 2026-11-10 | yes | stale | to close |
| #2129 | push-report-followups | Push report: first-push head, path filters, lagging PR, CI-only rewrit | 2026-11-08 | yes | stale, stacked on #1585 | to close |
| #2144 | push-after-check-semicolon | Refuse a git push that follows a semicolon-joined command | 2026-11-10 | yes | stale, stacked on #2099 | to close |
| #2146 | range-lane-notes | Notes: two gaps met in lane pr-review-range-check | 2026-11-08 | no | stale | to close |
| #2160 | lane-hold-ends-on-cause | Lane hold ends when the pile-up cause is fixed | 2026-11-08 | no | stale, owner-cited, stacked on branch claude/clever-planck-oynpfh | closed 2026-11-19 |
| #2167 | ci-wake-filter-gaps | Read a workflow's path filters toward a wait when their form is unclea | 2026-11-08 | yes | stale, stacked on #2129 | to close |
| #2171 | env-walk-limits | Env guard: close #2052's walk limits | 2026-11-10 | yes | stale, stacked on #2052 | to close |
| #2197 | relative-write-absolute-cd | worktree-home: allow a relative write after an absolute cd out of the | 2026-11-08 | yes | stale | to close |
| #2226 | waiter-monitor-allowed | fix(waiter): allow a Monitor wait, and read an escaped apostrophe in a | 2026-11-08 | yes | stale, replaced by #3204 (also to close) | to close |
| #2234 | quoted-args-unresolved | other-checkout: a quoted script argument or a kept heredoc body is dat | 2026-11-08 | yes | stale, owner-cited | closed 2026-11-19 |
| #2300 | nfp-ci-scope-cases | ci-scope: pin the two test-helper routing arms and name each importer' | 2026-11-08 | yes | stale, owner-cited | closed 2026-11-19 |
| #2326 | review-record-stack | Review records: a failed fix check counts as a round, FAIL on an ances | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2347 | nfp-ux-text-zoom | Stack the waiting page's presses under the text at narrow widths and l | 2026-11-10 | yes | stale, owner-cited | closed 2026-11-19 |
| #2440 | record-guard-wrapper-forms | Review-record guard judges wrapper, GraphQL, full-URL, quoted-paren an | 2026-11-09 | yes | stale, stacked on branch review-cutover-shallow-deepen | to close |
| #2483 | cloud-allow-rules | Cloud allow rules for gh api PR close and PR comment | 2026-11-11 | yes | stale, owner-cited | closed 2026-11-19 |
| #2527 | item-cite-carries-name-build | A page item cite carries its short name (report guard and handoff prom | 2026-11-10 | yes | stale | to close |
| #2562 | lane-brief-cites-grant | A lane starts with effort medium and its whole brief, opening with a G | 2026-11-11 | yes | stale, owner-cited | closed 2026-11-19 |
| #2572 | both-session-starts-judged | Guard: an agent's start_session is refused, like create_session | 2026-11-11 | yes | stale, owner-cited | closed 2026-11-19 |
| #2654 | lane/split-round2-notes | File two round-2 review notes from the guard test split | 2026-11-12 | no | stale | to close |
| #2662 | spend-log-batch-decision | Record the per-batch spend log ruling | 2026-11-13 | no | stale, owner-cited | closed 2026-11-19 |
| #2663 | usage-brake-decision | Record the usage brake ruling (R43) | 2026-11-12 | no | stale | to close |
| #2664 | builder-report-in-head-3 | Check a builder's reported files are in the pushed head before review | 2026-11-12 | yes | stale | to close |
| #2665 | input-needed-reads-page-status-2 | Report guard refuses an Input Needed item whose page item is closed (c | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2666 | override-strips-status-block-2 | A typed override takes even after the app's status block (carries #138 | 2026-11-12 | yes | stale | to close |
| #2667 | close-replaced-at-open-2 | merge --reviewed lists close-as-replaced, close-as-carried and reopen | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2672 | watch-finds-transcript | Decision watch finds the transcript by session id when the given path | 2026-11-12 | no | stale, owner-cited | closed 2026-11-19 |
| #2674 | lane-inflow-hold-carry | Record the lane inflow hold (carries #1768) | 2026-11-12 | no | stale, owner-cited | closed 2026-11-19 |
| #2675 | replay-1799-carry | Known-defect replay: failed-install exposure by load hook, base (carri | 2026-11-12 | yes | stale | to close |
| #2676 | check-line-reader-3 | A lane brief's Done check is read blind against the step's ask (carrie | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2677 | export-after-page-write-2 | Export check finds the real page writer; report guard refuses a handof | 2026-11-13 | yes | stale, replaced by #3258 (also to close) | to close |
| #2678 | cloud-branch-delete | Delete the branches the Oct 30 grant allows, from GitHub Actions | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2681 | question-form-task-context | Read a page task with options for its Departs from line | 2026-11-15 | no | stale, replaced by #3582 (also to close) | to close |
| #2683 | unknown-read-carry | One rule for an unknown read, carried from #1330 | 2026-11-12 | yes | stale | to close |
| #2684 | artifact-lane-carry | Refuse bare artifact links at a push to the record branch (carries #25 | 2026-11-12 | yes | stale | to close |
| #2689 | lock-delete-race-carry | Merge lock: take it by leased push on every host; delete GhLock (carri | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2691 | lane/guard-relative-write-escape-carry | Guard: refuse a relative ../ write that leaves the agent's worktree; a | 2026-11-13 | yes | stale, owner-cited | closed 2026-11-19 |
| #2692 | lane/commit-trailer-model-carry | Guard: an agent's commit names its own model in Co-Authored-By (carrie | 2026-11-12 | yes | stale | to close |
| #2693 | lane/brief-write-needs-writer-tests | Guard: refuse a brief that tells a read-only agent to write a file | 2026-11-12 | no | stale | to close |
| #2695 | page-answer-session-field-2 | Waiting page: an answer names its session, and the page-note capture r | 2026-11-12 | yes | stale | to close |
| #2696 | replay-block-failed-imports-4 | Known-defect replay: a load hook reads a fallback catcher UNKNOWN afte | 2026-11-12 | yes | stale | to close |
| #2697 | carry/stall-watch-open-call-cap | Stall watch: list an agent stuck in one Bash call past 900 s (carried | 2026-11-12 | yes | stale | to close |
| #2699 | carry/open-asks-at-wake | waiting-page: list asks with no reply at wake (carry of #2268) | 2026-11-12 | yes | stale, replaced by #3578 (also to close) | to close |
| #2700 | lane-lint-bg-timeout | Guard: a background lane-lint call sets a timeout above the lint's own | 2026-11-13 | yes | stale | to close |
| #2701 | solo-batch-hat | A solo session with no parent and no cs-build tag may take the batch-r | 2026-11-15 | yes | stale | to close |
| #2702 | skill-text-once-v2 | waiting-page SKILL.md: generate the item field table, state each rule | 2026-11-12 | yes | stale | to close |
| #2704 | carry-why-cite-act | A page task's route cite must name a route row that covers its act (ca | 2026-11-12 | yes | stale | to close |
| #2709 | lane/lane-finds-triage-4 | Lane brief check: Coordinator, Triage and Batch runner ids (step lane- | 2026-11-12 | yes | stale | to close |
| #2714 | lane/agent-output-terse-line-stub | Each agent role file and the lane start text carry one short-output li | 2026-11-12 | yes | stale | to close |
| #2716 | carry-shoot-stitch-pinned | bin/shoot: stitched touch shots keep the pinned size (carries #2116) | 2026-11-12 | no | stale | to close |
| #2717 | carry-shoot-touch-widths | bin/shoot: touchWidths config key (carries #2154) | 2026-11-12 | no | stale, owner-cited | closed 2026-11-19 |
| #2720 | page-time-field-valid | Guard: a blank or non-ISO time in a page or step write is refused | 2026-11-13 | yes | stale | to close |
| #2723 | pwsh-followups-2 | PowerShell write detection: env -S, quoted text, copy sources, aliases | 2026-11-12 | yes | stale | to close |
| #2724 | lease-remedy-form-c | Force-push guard: remedy names the sha lease form | 2026-11-12 | no | stale, replaced by #3580 (also to close) | to close |
| #2725 | carry-builder-test-cfg | A builder cannot edit test config (carry of #2103) | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2726 | retarget-checked-with-role-build | question-checked-with-repo takes a role or lane slug, never a session | 2026-11-12 | yes | stale | to close |
| #2727 | merge-kind-diff-check | A docs-only Kind claim is refused when the diff files a decision recor | 2026-11-12 | yes | stale | to close |
| #2728 | model-auth-build | Model calls that cannot authenticate are no longer quiet (carries #131 | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2729 | dead-pr-waits | Refuse a bare PR wait in a step write, flag a dead one in the roadmap | 2026-11-12 | yes | stale | to close |
| #2732 | page-lane-scope-notes | Notes: three limits of the waiting-page guards (layout fail-open, thre | 2026-11-12 | no | stale | to close |
| #2734 | lane-undo-check-3 | Silent-undo check: a lane commit that puts back its own earlier work r | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2735 | carry-1516-names-fix | A note names its fix (carried forward from #1516) | 2026-11-12 | yes | stale | to close |
| #2736 | carry-reviewed-sends-back-build | merge --reviewed names each draft over 12 h old with a missing, stale | 2026-11-12 | yes | stale | to close |
| #2737 | judge-replay-corpus-2 | Judge replay corpus: known allow and deny cases run in CI when a judge | 2026-11-14 | yes | stale | to close |
| #2740 | carry/past-ruling-on-send | Past-ruling judge runs before an owner-question send and alone on a pa | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2742 | carry/page-pics-fill-card | Waiting page: an option picture fills its card's width (carry of #2495 | 2026-11-15 | no | stale, owner-cited | closed 2026-11-19 |
| #2744 | pwsh-r3-2 | PowerShell write detection: comma lists, alias positions, scriptblocks | 2026-11-12 | yes | stale, stacked on #2723 | to close |
| #2747 | carry-runner-drops-handed-lane-build | Batch runner names each handed-over lane left out of a batch (carries | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2749 | lane/lint-slot-carry-build | Lane lints wait for a CPU slot, so parallel lints finish (step lane-li | 2026-11-12 | yes | stale | to close |
| #2750 | draft-pr-carry | Draft-PR guard: heredoc bodies read as shell only when run, backtick s | 2026-11-12 | yes | stale | to close |
| #2751 | lane-ack-question | A lane's plain acknowledgement is not an answer to its question | 2026-11-15 | yes | stale, replaced by #3581 (also to close) | to close |
| #2752 | map-reader-gaps | The map's readers see aliased imports, shell strings and test joins | 2026-11-12 | no | stale | to close |
| #2753 | pwsh-r3-limits-2 | PowerShell write detection: argument slots, groups, cp, listed targets | 2026-11-12 | yes | stale, stacked on #2744 | to close |
| #2755 | lane-session-model-check-e | Guard: a lane session start whose model differs from the lane row is r | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2756 | answered-section-folded-2 | Waiting page: Answered section starts closed (carries #2317) | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2757 | record-gloss-link-checks | Two PR checks: a record's first cite has a gloss; a debt keeps its Dec | 2026-11-12 | yes | stale, stacked on #2735 | to close |
| #2758 | lane/branch-force-worktree-build | One-worktree-per-branch check also refuses update-ref and branch -f of | 2026-11-12 | no | stale | to close |
| #2759 | plain-push-asks-cite | plain-push-asks cites its source as unverified, not page item 410 | 2026-11-12 | no | stale, owner-cited | closed 2026-11-19 |
| #2766 | stamp-unscanned-pending-cite | Stamp refuses a pending cite in a file it does not scan, and names the | 2026-11-12 | no | stale | to close |
| #2767 | outbox-home-check-build | Status block lists each outbox ruling and whether its home on main hol | 2026-11-12 | yes | stale | to close |
| #2768 | lane/child-repo-scope-fix | An archive refused for an out-of-scope repo names the repo and routes | 2026-11-12 | yes | stale | to close |
| #2769 | watch-transcript-fallback-build | Decision watch finds the transcript by session id when the given path | 2026-11-12 | yes | stale | to close |
| #2771 | resume-carry | Resume guard: a finished agent whose worktree is gone is refused a res | 2026-11-12 | yes | stale, owner-cited, replaced by #3248 (also to close) | closed 2026-11-19 |
| #2772 | debt-merge-shard-caps-prose | Debt windows-shards-outgrow-caps: merge cap 75, current shard times | 2026-11-12 | yes | stale | to close |
| #2774 | fed-write-carry | Builder test-edit check: shell writes in folder roots, globs and sed f | 2026-11-12 | yes | stale, stacked on #2750 | to close |
| #2775 | one-load-definition-f | The guard and sim-lease read machine load from one shared definition | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2777 | notes-prose-guard-2 | Notes: four open review findings from the prose-guard-2 lane PRs | 2026-11-12 | no | stale | to close |
| #2778 | item-reply-back-2 | Waiting page: reply to Claude's reply on an item (carries #1425) | 2026-11-15 | yes | stale | to close |
| #2779 | records-page-ready-reads-pr-repo | Guard records-page-ready reads the repo the pull request is in | 2026-11-12 | yes | stale | to close |
| #2780 | carry/reviewer-brief-blind | Refuse a reviewer brief that holds a report or a prior verdict (carrie | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2782 | carry-ruling-cite-in-commit-c | Commit check: a ruling cite names its home and time | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2786 | replay-profile-parts-3 | Step replay-profile-parts: the load hook decides, static regex parts a | 2026-11-12 | yes | stale | to close |
| #2788 | carry-ruling-skip-check | Ruling-skip check: a pick taken under a ruling cites it, and a Sonnet | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2789 | other-checkout-heredoc-text-6 | other-checkout: a quoted python body that only quotes a path is text; | 2026-11-12 | yes | stale | to close |
| #2790 | glossary-prose-renames | Glossary renames in text: review log and feedback log (G4) | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2791 | lane/branch-slug-rule-build | A new branch name never holds the word "git", and the guard refuses on | 2026-11-12 | no | stale | to close |
| #2792 | carry/ask-phase-out | Pin the waiting page's routed lines and Mark read (step ask-phase-out) | 2026-11-12 | yes | stale | to close |
| #2797 | carry/past-ruling-s1-block | The past-ruling judge carries rules S1 to S4 and the record-kind sente | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2798 | carry-xctestplan-config | A builder cannot edit an .xctestplan (step builder-xctestplan-config) | 2026-11-12 | yes | stale, owner-cited | closed 2026-11-19 |
| #2799 | notes-name-their-fix-stack | notes-name-their-fix: fixes stacked on #2735 | 2026-11-12 | yes | stale, stacked on #2735 | to close |
| #2801 | guard-tables-per-section | Guard tables per section: each family's rows live in its own section f | 2026-11-13 | yes | stale | to close |
| #2802 | prose/waiting-page-skill-text-fixes | Two wording fixes in the waiting-page SKILL.md (step waiting-page-skil | 2026-11-12 | yes | stale | to close |
| #2803 | stale-cites-plans | Stale cites: plans folder (step stale-cites-tree-clean) | 2026-11-12 | yes | stale | to close |
| #2804 | stale-cites-decisions | Stale cites: decision records (step stale-cites-tree-clean) | 2026-11-12 | yes | stale | to close |
| #2805 | stale-cites-design-debts | Stale cites: design notes and small debts (step stale-cites-tree-clean | 2026-11-12 | no | stale | to close |
| #2806 | notes-code-handoffs | docs: file low review findings from lane fan-code-handoffs as notes an | 2026-11-13 | no | stale | to close |
| #2811 | prose-round3-notes | File review round 3 findings as notes and two debts | 2026-11-12 | no | stale | to close |
| #2812 | undo-keep-prose | Builders keep earlier lane work: builder.md paragraph and brief Keep l | 2026-11-12 | yes | stale, owner-cited, stacked on #2734 | to close |
| #2813 | lane/interp-body-carry | Guard reads a force push inside python -c bodies and a PowerShell call | 2026-11-12 | yes | stale | to close |
| #2815 | lone-lane-merge-path | Lone lane merges its own PR in claude-settings (G2, G10) | 2026-11-12 | yes | stale | to close |
| #2821 | undo-brief-sentence | Add the Keep sentence to roles-brief-contents | 2026-11-12 | yes | stale, stacked on #2812 | to close |
| #2824 | draft-pr-unquoted-body-2 | guard: end an unquoted heredoc body only on the end line bash accepts | 2026-11-12 | yes | stale, stacked on #2750 | to close |
| #2827 | fix/asks-wake-fresh-save | The writer's wake runs the open-asks end check on a fresh asks save (s | 2026-11-12 | yes | stale | to close |
| #2828 | ruling-parts-cite-steps | Each plan ruling part cites its step; a check flags a missing or gone | 2026-11-12 | yes | stale | to close |
| #2831 | sed-operand-reader | Frozen-path guard reads sed operands (flag clusters, w FILE, wrappers) | 2026-11-12 | yes | stale | to close |
| #2832 | lint-config-guard-paths-2 | merge: count hooks/guard.py's import closure as guard paths | 2026-11-12 | yes | stale | to close |
| #2836 | stop-checks-one-message | Stop checks speak in one merged message (lane stop-checks-one-message) | 2026-11-12 | yes | stale | to close |
| #2837 | batch-build-stop-group-fix | A stopped batch build pushes nothing (step batch-build-stop-group) | 2026-11-12 | yes | stale | to close |
| #2838 | blame-on-finished-red-job-v2 | merge: --blame takes a run still going once a job finished red | 2026-11-13 | yes | stale | to close |
| #2841 | model-auth-key-build | The hook judge takes ANTHROPIC_API_KEY when no setup token exists | 2026-11-12 | yes | stale, owner-cited, stacked on #2728 | to close |
| #2846 | green-hook-draft-run-2 | ci_wake: a draft run never reads green | 2026-11-12 | yes | stale | to close |
| #2850 | owner-override-one-route | One override route: length forms are timed on the fast path, one recei | 2026-11-15 | yes | stale | to close |
| #2852 | claude-md-section-moves | Move accepted CLAUDE.md sections to the files that need them (step 3, | 2026-11-15 | yes | stale, owner-cited | to close |
| #2853 | note-pipx-host-dep | Note: a merge-tool test needs pipx on the host | 2026-11-12 | no | stale | to close |
| #2856 | handoff-agent-write-r3 | Guard: refuse an agent's write to a session handoff; skip handoff hook | 2026-11-12 | yes | stale | to close |
| #2858 | one-term-warn-lint-r3 | Warn-only one-term lint (STE022) | 2026-11-12 | yes | stale, owner-cited | to close |
| #2859 | review-record-parse-warn-3 | A review record that does not parse is flagged by the lane lint and by | 2026-11-12 | yes | stale | to close |
| #2861 | hook-bounds-reasons-census | State why four hook bounds stay (census rows H4, H6, H7, H8) | 2026-11-16 | no | stale, owner-cited | to close |
| #2862 | stall-watch-quiet-ab | Stall watch: never end a waiter or a lone pause (stacked on #2680) | 2026-11-12 | yes | stale, stacked on branch stall-watch-live-run-2 | to close |
| #2863 | ci-limits-from-green-runs | CI limits from recent runs: script and records (S1 of time-limits-end- | 2026-11-12 | yes | stale, owner-cited | to close |
| #2864 | stop-checks-draft-carry | Recovered guard refusal carries a draft of the missing lines (stacked | 2026-11-12 | yes | stale, stacked on #2836 | to close |
| #2867 | stop-checks-departs-fix | Departs-from check accepts a sentence-form line with no dash (stacked | 2026-11-12 | yes | stale, stacked on #2836 | to close |
| #2869 | pr-ledger-round-ages | PR ledger: set round-age limits from measured ages | 2026-11-12 | yes | stale | to close |
| #2870 | pick-reaches-page | Guard: a coordinator pick must reach the waiting page | 2026-11-15 | yes | stale | to close |
| #2872 | sweep-lock-age | A no-start agent lock whose pid was reused frees its tree (on #2783) | 2026-11-12 | yes | stale, owner-cited | to close |
| #2873 | merge-subst-paren-v4 | Merge guard reads a quoted paren inside a $( ) span (merge-subst-paren | 2026-11-12 | yes | stale | to close |
| #2874 | review-rounds-rework | Draft decision: what each review round catches (review-rounds-rework) | 2026-11-12 | no | stale | to close |
| #2875 | main-push-wakes-runner | One wake for a CI alarm on a push to main | 2026-11-14 | yes | stale | to close |
| #2878 | lane/upkeep-blocked-no-blocker | Roadmap upkeep lists blocked steps with no open blocker | 2026-11-15 | yes | stale | to close |
| #2879 | waiting-lag-read | Add stale_pages.py --lag: answer read delay and unread age | 2026-11-12 | yes | stale, owner-cited | to close |
| #2881 | habit-is-not-a-guard-r2 | A habit or brief line is no guard: a report's guard line names a PR, c | 2026-11-15 | no | stale, owner-cited | to close |
| #2883 | debt-retire-red-on-birth-v2 | check_debt_retire: a Retire test must fail on the debt's birth commit | 2026-11-12 | yes | stale | to close |
| #2884 | lint-counts-census | Retire the rule-audit count pins and the 8-word reason floor; add a mo | 2026-11-16 | no | stale, owner-cited | to close |
| #2885 | lane/md-midline-comment-gap | The terse-line check reads HTML comments as CommonMark does | 2026-11-12 | yes | stale, stacked on #2714 | to close |
| #2886 | lane/pr-2693-debt-fixes | Fix the five debts of the brief-write guard, with the readers bounded | 2026-11-12 | no | stale, stacked on #2693 | to close |
| #2893 | two-drop-leaves-queue | A lane dropped from two batches leaves the queue for a fix lane | 2026-11-12 | yes | stale | to close |
| #2894 | lane/both-session-starts-judged | Deny an agent's start_session call (step both-session-starts-judged) | 2026-11-12 | yes | stale | to close |
| #2895 | repo-typecheck-hook-r2 | Run a repo-declared typecheck after each edit, from one claude-setting | 2026-11-12 | yes | stale | to close |
| #2899 | sim-lease-load-brake | sim-lease grants on the load brake's measure, not the load average | 2026-11-13 | yes | stale, owner-cited | to close |
| #2900 | express-pass-owner-quotes | Express pass: owner quotes that match the feedback log skip the ruling | 2026-11-12 | no | stale, owner-cited | to close |
| #2901 | express-pass-reviewer-line | Reviewer file: the express pass skips the ruling-record round when quo | 2026-11-12 | no | stale | to close |
| #2904 | owner-health-tab | Owner health tab: new check, CI step and page tab | 2026-11-15 | yes | stale | to close |
| #2905 | records-page-before-ready-2 | The draft step claims record numbers before ready (one CI run per merg | 2026-11-12 | yes | stale | to close |
| #2907 | waiting-copy-backup-only | Check that no tool reads the waiting copy as a live source; name the c | 2026-11-12 | yes | stale, owner-cited | to close |
| #2910 | past-ruling-run-log | Log each past-ruling and judge model run (ms, chars, outcome) and read | 2026-11-12 | yes | stale | to close |
| #2913 | carry-msg-ref-pr-forms-build | Guard: message refs judge a PR word apart from its number | 2026-11-12 | yes | stale | to close |
| #2914 | review-fix-check-round-5 | merge: refuse --fix-check with no --round | 2026-11-12 | yes | stale | to close |
| #2915 | prose-tending-contract | One shared tending contract and runner for prose stores | 2026-11-13 | yes | stale, owner-cited | to close |
| #2918 | ask-alone-push-not-force-r2 | ask-alone: a plain chained git push is no forced push | 2026-11-12 | yes | stale, owner-cited | to close |
| #2919 | page-usage-counters-r2 | Page usage counters | 2026-11-12 | yes | stale | to close |
| #2920 | main-job-cap-alarm-2 | CI alarm: every cap end on main wakes the batch runner | 2026-11-14 | yes | stale, owner-cited | to close |
| #2923 | artifact-guard-matcher-names-1-normalizer | Artifact guards 1/5: name the artifact tools in one constant, map Mac | 2026-11-12 | yes | stale, owner-cited | to close |
| #2924 | artifact-guard-matcher-names-2-guard | Artifact guards 2/5: judge Mac artifact calls in the guard | 2026-11-12 | yes | stale, stacked on #2923 | to close |
| #2925 | artifact-guard-matcher-names-3-call-judge | Artifact guards 3/5: route Mac artifact calls through the call judge | 2026-11-12 | yes | stale, stacked on #2924 | to close |
| #2926 | artifact-guard-matcher-names-4-transcript | Artifact guards 4/5: read Mac artifact calls in the transcript readers | 2026-11-12 | yes | stale, stacked on #2925 | to close |
| #2927 | artifact-guard-matcher-names-5-inbox | Artifact guards 5/5: read Mac artifact calls in the feedback guard and | 2026-11-12 | yes | stale, stacked on #2926 | to close |
| #2931 | scratchpad-commit-msg-owner | Judge a wrapped commit -F of a scratchpad file (scratchpad-commit-msg- | 2026-11-12 | no | stale | to close |
| #2932 | pick-ack-ruling-2 | A coordinator's pick cites a ruling before send_message carries it | 2026-11-15 | yes | stale, owner-cited | to close |
| #2937 | lane-sim-hold-path-3 | Guard the Monitor tool's command like a shell command (lane-sim-hold-p | 2026-11-12 | yes | stale | to close |
| #2939 | batch-order-by-pr-number | Batch lanes merge in hand-in order; stacked check reads once per head | 2026-11-12 | yes | stale | to close |
| #2941 | cull-narration-hex-id-fix | Narration check: an example id in a history clause is still flagged | 2026-11-12 | yes | stale, owner-cited | to close |
| #2943 | coordinator-session-board-2 | The roadmap build lists started sessions that are waiting, done, faile | 2026-11-15 | yes | stale, owner-cited | to close |
| #2945 | install-hash-skips-pycache | install.sh: tree_hash skips generated __pycache__ bytecode | 2026-11-12 | yes | stale, owner-cited | to close |
| #2946 | subagent-handback-bypass-v2 | Agents: no retry of a refused hand-back call | 2026-11-12 | no | stale | to close |
| #2948 | express-pass-merge-stamp | Merge tool: a docs-only record may file a decision when the session st | 2026-11-12 | yes | stale, owner-cited, stacked on #2727 | to close |
| #2953 | pwr-only-triage-watches | Only the page writer watches the waiting page (page-wakes-and-relays, | 2026-11-12 | yes | stale | to close |
| #2954 | worktree-builder-bash-test-write | Builder bash test-write check (PostToolUse judge_shell_write) | 2026-11-12 | yes | stale | to close |
| #2955 | pwr-item-names-wakers-b | Each waiting-page item names who wakes (page-wakes-and-relays, item 2) | 2026-11-12 | yes | stale, owner-cited | to close |
| #2957 | repeat-mark-skips-followups | Repeat mark skips a same-thread follow-up within 30 minutes | 2026-11-15 | yes | stale | to close |
| #2962 | notes-scope-own-lines-2 | Silent-undo check: an in-place edit of a note the branch did not add i | 2026-11-12 | yes | stale | to close |
| #2963 | ruling-challenge-passes-5 | A past-ruling challenge passes on a new fact the ruling left unweighed | 2026-11-15 | yes | stale, owner-cited | to close |
| #2967 | agent-commit-file-scope-2 | Guard: an agent's commit touches only the files its brief names (carri | 2026-11-12 | yes | stale | to close |
| #2971 | answers-session-write-guard | Guard: refuse a session's write to the waiting page's answers | 2026-11-13 | yes | stale, owner-cited | to close |
| #2972 | busy-file-stacked-batches | Busy files: refuse a batch build that holds two lanes on one busy file | 2026-11-12 | yes | stale | to close |
| #2974 | outbox-aggregate-plan | Plan: gather other repos' outbox findings into triage | 2026-11-13 | no | stale, owner-cited | to close |
| #2979 | record-before-fix-push-v3 | A push after a review round asks until that round's record is posted a | 2026-11-13 | no | stale | to close |
| #2981 | lane/answer-kept-on-close | Closing a page item keeps the owner's saved answer | 2026-11-14 | yes | stale | to close |
| #2982 | page-narrow-word-breaks | Waiting page: Remove and Edit presses keep whole words at narrow width | 2026-11-12 | yes | stale, stacked on #2347 | to close |
| #2989 | pick-claims-match-page | Check step notes' "owner picked" claims against the page's answers | 2026-11-12 | yes | stale, owner-cited | to close |
| #2991 | lock-stdout-only | Merge lock: read the ls-remote listing from stdout alone; accept only | 2026-11-12 | yes | stale | to close |
| #2996 | feedback-log-tends-itself | The feedback log closes, cleans and lists its own items | 2026-11-13 | yes | stale, owner-cited, stacked on #2915 | to close |
| #2997 | item-cite-carries-name-2 | Item cites carry their short name (report and handoff guards) | 2026-11-12 | yes | stale, owner-cited | to close |
| #3003 | prose-tending-move-stores | Audit prose store tending; fix two tending entries | 2026-11-13 | yes | stale, owner-cited, stacked on #2996 | to close |
| #3004 | ci-hygiene-once-per-batch | ci-hygiene: run each suite once per batch (R61-R63) | 2026-11-14 | yes | stale | to close |
| #3005 | unknown-reads-lint-linux-only | Run the unknown-reads contract lint on Linux only | 2026-11-14 | yes | stale | to close |
| #3006 | pwr-one-home-answer | One home per answer: the Stop guard keeps options off chat once the pa | 2026-11-12 | yes | stale | to close |
| #3008 | batch-ci-merge-guard-3 | Brake raw API merges and pushes to main while a batch's CI runs | 2026-11-12 | yes | stale, owner-cited | to close |
| #3011 | sim-tool-lease-check-3 | Simulator tool needs the caller's own lease (simulator-device-lease) | 2026-11-14 | yes | stale, owner-cited | to close |
| #3014 | worktree-merge-path-same-everywhere | merge-path-same-everywhere: one merge role proof, local and cloud | 2026-11-13 | yes | stale | to close |
| #3019 | lane-push-frozen-in-batch | Refuse a lane push while a ready batch PR holds its tip (push-batch-he | 2026-11-12 | yes | stale | to close |
| #3024 | guard-paths-agents | GUARD_PATHS covers agents/ | 2026-11-13 | yes | stale | to close |
| #3026 | agent-worktree-add-in-tool-dir | Guard: an agent's hand-made-worktree refusal names its own red-run fol | 2026-11-13 | no | stale | to close |
| #3028 | cull-report-guard | Guard cull: the Recovered report-line check is deleted (family 1) | 2026-11-13 | yes | stale | to close |
| #3029 | cull-question-form | Guard cull: the question form's Departs-from dash check is deleted (fa | 2026-11-13 | no | stale | to close |
| #3030 | cull-test-temp-run | Guard cull: the test temp-run guard reads Python 3.9 code (family 8b) | 2026-11-12 | no | stale | to close |
| #3031 | cull-ruling-kind-home | Guard cull: ruling-kind check reads Home only after Kind (family 7) | 2026-11-13 | no | stale | to close |
| #3032 | cull-text-reads | Guard cull: text reads are not writes (family 8) | 2026-11-13 | yes | stale | to close |
| #3035 | cull-glossary-decision-id | Guard cull: glossary rows keep seven record ids (family 10) | 2026-11-12 | yes | stale | to close |
| #3037 | cull-frozen-reads | Guard cull: the frozen-path guard stops refusing reads (family 4) | 2026-11-12 | yes | stale | to close |
| #3038 | pwr-grant-carries-words | A relayed grant carries the owner's exact words; the sender's guard ch | 2026-11-13 | yes | stale | to close |
| #3039 | notes-fix-reverify-small-code | Guard fixes: 13 small rows from the kept-notes re-check (step notes-fi | 2026-11-13 | yes | stale, owner-cited | to close |
| #3040 | pwr-grant-debts | Debts from the relay-grant-words review (step page-wakes-and-relays, i | 2026-11-13 | no | stale | to close |
| #3043 | cull-debt-retire-note | Debt check: a wrong refusal closes by a notes line, no test (guard cul | 2026-11-13 | yes | stale, owner-cited | to close |
| #3044 | brief-names-push-target | brief-names-push-target: an agent pushes only to the branch its brief | 2026-11-13 | yes | stale | to close |
| #3047 | mutate-timeout-crashed | mutate-timeout-crashed: a hung mutant scores crashed, the run goes on | 2026-11-13 | yes | stale | to close |
| #3050 | git-apply-test-path-write | Guard: refuse a builder's git apply onto a test path at write time | 2026-11-13 | yes | stale | to close |
| #3056 | cull-docs-notes | Guard cull docs: wrong refusals become notes, stale records fixed | 2026-11-13 | yes | stale, owner-cited | to close |
| #3058 | child-repo-gap | Record how far each child repo is from main (child-repo-gap, part 1) | 2026-11-13 | no | stale | to close |
| #3059 | pointer-checkout-edit | guard: pointer-edit also judges a Bash write into the pointer checkout | 2026-11-13 | yes | stale | to close |
| #3061 | decision-watch-finds-transcript-2 | Decision watch finds the transcript by session id | 2026-11-13 | yes | stale | to close |
| #3065 | local-page-publish-route | Waiting page: splice.py --add-design puts mockup pictures on the page | 2026-11-13 | no | stale | to close |
| #3068 | claim-vs-main-needs-read | A regression or no-regression claim cites a read of main (step claim-v | 2026-11-13 | no | stale | to close |
| #3071 | session-start-pin-skip-log | SessionStart logs each skip of the live pin update | 2026-11-13 | yes | stale | to close |
| #3072 | review-record-parses-at-handin | Lane-lint fails when merge --reviewed cannot parse the review record | 2026-11-13 | yes | stale | to close |
| #3073 | guards-read-origin-main-config | Guards read repo config from the origin/main blob | 2026-11-13 | yes | stale | to close |
| #3074 | explore-veto-offer | An owner override lifts the Explore model veto for a spawn he names | 2026-11-13 | yes | stale | to close |
| #3076 | inbox-skip-bash-echo | The feedback inbox skips echoes of commands the owner ran | 2026-11-13 | no | stale, owner-cited | to close |
| #3082 | builder-test-comment-edit | A builder may change only comments in a test file (step builder-test-c | 2026-11-13 | yes | stale, owner-cited | to close |
| #3084 | consultant-role-placement | Consultant role is placed in the side-session list and role lists (ste | 2026-11-15 | yes | stale | to close |
| #3090 | one-build-per-session-wording | ios-apps: one build per session, another session's build does not bloc | 2026-11-13 | yes | stale | to close |
| #3091 | main-claim-branch-only | The main-claim check flags only a branch-like use of main | 2026-11-13 | no | stale, stacked on #3068 | to close |
| #3092 | ios-apps-test-shapes-starter-2 | ios-apps starter: UI tests tap through one centre function (starter co | 2026-11-13 | no | stale | to close |
| #3094 | lint-fixtures-py39 | Stale prose fixture suite runs on Python 3.9 | 2026-11-13 | no | stale | to close |
| #3100 | lane/session-messages-status-line | session-messages: line 6 says the true status now | 2026-11-13 | no | stale | to close |
| #3102 | fix-branch-merge-main-deny-2 | A push of a clean merge of main to a fix-checked PR branch passes the | 2026-11-13 | yes | stale, owner-cited, stacked on #2979 | to close |
| #3108 | lane/merge-runs-idle-lanes | merge --confirm prints the idle-lanes report, or says the pass is owed | 2026-11-13 | yes | stale | to close |
| #3109 | record-before-next-push-v2 | A push after a moved head names the fresh-round route, and a descendan | 2026-11-13 | no | stale, stacked on #2979 | to close |
| #3110 | cloud-precompact-handoff-stale | Add a late handoff checkpoint, 20k under the room | 2026-11-13 | no | stale | to close |
| #3111 | lane-start-tags-cs-step | Deny a lane start with no cs-step tag | 2026-11-13 | yes | stale | to close |
| #3117 | lane/archive-reads-unarchived-epoch | Batch runner skips a lane whose get_session shows unarchived_epoch abo | 2026-11-13 | yes | stale, stacked on #3108 | to close |
| #3124 | worktree-page-writer-key-follows-tag | The page writer is found by its triage tag, not a fixed session id | 2026-11-13 | yes | stale | to close |
| #3126 | scratchpad-cp-keeps-writer-2 | scratchpad-cp-keeps-writer: a cp of another agent's file keeps that ag | 2026-11-13 | no | stale | to close |
| #3130 | merge-line-cites-to-symbols | Cite merge.py by symbol in two decisions (merge-line-cites-to-symbols) | 2026-11-13 | yes | stale | to close |
| #3131 | fix-verifier-r2-build | A PASS fix verifier stands in for round 2 of a review record (fix-veri | 2026-11-13 | yes | stale, owner-cited | to close |
| #3132 | ruled-entry-open-too-long | A check lists open ruled entries whose step is done or has no lane (ru | 2026-11-13 | yes | stale | to close |
| #3137 | mail-read-receipt | mail status: a sender reads whether its message was taken | 2026-11-13 | yes | stale | to close |
| #3139 | lanes-no-ci-record-claims | Decision lanes-run-no-full-ci-job states the lane-lint join as main do | 2026-11-13 | yes | stale, stacked on #3130 | to close |
| #3141 | fast-forward-clean-start | A session fast-forwards its own clean checkout to main at start | 2026-11-15 | yes | stale | to close |
| #3143 | challenge-followups-3 | Item 8 accepts an unmeasured-claim challenge; the denial tail carries | 2026-11-13 | yes | stale, stacked on #2963 | to close |
| #3146 | stale-cites-read-symbol-2 | stale-cites: a read path::name cite shows the named symbol | 2026-11-13 | no | stale | to close |
| #3147 | live-publisher-tracked-r2 | Live-file publisher gets a tracked home with a test | 2026-11-13 | yes | stale, owner-cited | to close |
| #3156 | draft-run-dirty-pr-reason | merge --lane-lint: a dirty PR with no touched run reads "merge main in | 2026-11-13 | yes | stale | to close |
| #3157 | worktree-prose-batch-order-record | Record ruling prose-batch-order | 2026-11-13 | no | stale, owner-cited | to close |
| #3159 | pr-close-by-batch-runner | Decisions: batch runner closes superseded PRs with a pointer (pr-close | 2026-11-13 | yes | stale, owner-cited | to close |
| #3160 | report-guard-design-reviewer-re | report guard: design-reviewer names are not reviewer claims in Done | 2026-11-13 | no | stale | to close |
| #3164 | notes-fix-report-rebuild | Name the skipped repo in the home-check refusal | 2026-11-15 | yes | stale | to close |
| #3166 | live-stream-monitor-remedy-2 | The live-stream refusal names the Monitor tool in its remedy | 2026-11-13 | no | stale | to close |
| #3169 | nfl3-1632-carry | Carry #1632: linked node_modules reads npm aliases and workspaces | 2026-11-14 | no | stale | to close |
| #3174 | debt-retire-names-test | Lane-lint refuses a debt close whose Retire names no test | 2026-11-13 | yes | stale | to close |
| #3175 | batch-drop-refusal-blame | merge: a debt refusal of a batch PR stores its one lane as blamed | 2026-11-13 | yes | stale | to close |
| #3176 | nfl3-1618-carry | Carry the feedback guard and bad rolled-out mark stack onto main | 2026-11-14 | yes | stale | to close |
| #3178 | merge-sets-settings-dir | ci-job gives each run step CLAUDE_SETTINGS_DIR: its pin's tree, else t | 2026-11-13 | yes | stale, owner-cited | to close |
| #3179 | notes-fix-guard-2-rebuild | Notes fix guard 2: SessionStart TMPDIR line, and a message-only amend | 2026-11-13 | yes | stale | to close |
| #3185 | review-record-past-head-core | Let a FAIL review record name a past head of the pull request | 2026-11-13 | yes | stale | to close |
| #3186 | cite-range-symbol-match-r2 | STALE011: a line anchor whose sentence names a symbol its lines do not | 2026-11-15 | yes | stale | to close |
| #3187 | round-1-sonnet-labels | Review rounds: round 1 model per diff, finding labels, and the review | 2026-11-13 | yes | stale, owner-cited | to close |
| #3188 | compact-refreshes-hooks | A cloud session that compacts refreshes its hooks | 2026-11-16 | yes | stale | to close |
| #3189 | fix-check-notes-commit | Let merge --fix-check span a gap of record or notes commits | 2026-11-13 | yes | stale | to close |
| #3190 | nfl3-2115-1687-carry | Carry the MCP guard line and the review-record stack onto main | 2026-11-14 | yes | stale | to close |
| #3197 | export-label-token | Page writer label matched as a whole id token (replaces #1784) | 2026-11-13 | yes | stale, stacked on #3258 | to close |
| #3200 | lane-lint-pinned-trees | Lane lint follows the pinned trees, as the ready check does (step lane | 2026-11-13 | yes | stale | to close |
| #3201 | rebuild-2705 | Widening mark: per-repo exceptions only, worded as a guideline (rebuil | 2026-11-14 | yes | stale, owner-cited | to close |
| #3204 | draft-pr-guard-text-false-alarm | fix(waiter): read an escaped apostrophe in an interpreter heredoc, nam | 2026-11-13 | no | stale, owner-cited | to close |
| #3206 | rebuild/past-ruling-on-send | The past-ruling judge runs on owner-question sends and page item write | 2026-11-14 | yes | stale, owner-cited | to close |
| #3209 | builder-diff-auto-merge-reflog-r3 | builder-diff judges an auto-committed strategy merge or pull (rebuild) | 2026-11-13 | yes | stale, owner-cited | to close |
| #3210 | guard-path-expand-forms-2 | Guard: read default-word config-dir forms and getcwd joins (step guard | 2026-11-14 | yes | stale | to close |
| #3211 | mail-guards-read-send-message | The feedback guard counts a mail send as a send (mail-guards-read-send | 2026-11-13 | yes | stale | to close |
| #3212 | page-one-store-final | Decision: git is the page's home, the database its live view (prose) | 2026-11-15 | yes | stale, owner-cited | to close |
| #3215 | merge-mail-refreshes | Each batch merge mails every cloud session to refresh (merge-mail-refr | 2026-11-13 | yes | stale | to close |
| #3219 | rebuild-2711 | Stale flags: STALE007 flag reader on top of #3182 (rebuild of #2711) | 2026-11-14 | yes | stale | to close |
| #3223 | cmk-unread-git-read-rebuild | conflict-markers asks when a git read cannot run, instead of allowing | 2026-11-14 | yes | stale | to close |
| #3227 | progress-claims-live-read | Guard: a progress claim cites a named live read (progress-claims-cite- | 2026-11-14 | yes | stale | to close |
| #3229 | review-range-ancestry-check | Lane lint refuses a review range that breaks the ancestry rule (replac | 2026-11-13 | yes | stale | to close |
| #3230 | silent-undo-reads-pr-body | Silent-undo check reads the PR body from the CLI, the event file and l | 2026-11-13 | yes | stale, owner-cited | to close |
| #3234 | stamp-clock-check-everywhere | Stamp check reads bracketed, parenthesised and dated header forms (ste | 2026-11-13 | yes | stale | to close |
| #3235 | review-record-readback | merge --review-record: read the record back, FAILED on a refused post | 2026-11-13 | yes | stale | to close |
| #3236 | lane-no-popup | Lane : a lane never opens the question box or a trust card (step lane- | 2026-11-13 | yes | stale | to close |
| #3240 | lane/release-check-vs-batch-head | The release check also merge-trees each PR against the open batch head | 2026-11-13 | yes | stale | to close |
| #3242 | merge-reviewed-cursor | merge --reviewed reads comments since a stored cursor | 2026-11-15 | yes | stale | to close |
| #3244 | pre-existing-reads-clause | Report guard: a pre-existing claim names a run on the base, read on th | 2026-11-15 | yes | stale | to close |
| #3248 | resume-recut | Resume guard: refuse a resume of a finished agent whose worktree is go | 2026-11-13 | yes | stale, stacked on #2801 | to close |
| #3249 | rebuild-2123-coord-scope | Hold the coordinator's own writes, spawns and merges; read loop and br | 2026-11-14 | yes | stale, owner-cited | to close |
| #3252 | lane/batch-label-write | merge --batch-label adds the batch label to an integration PR | 2026-11-14 | yes | stale, owner-cited | to close |
| #3253 | roadmap-ref-fresh | A reader of origin/roadmap fetches it before its verdict | 2026-11-14 | yes | stale | to close |
| #3254 | lane/role-gaps-clash-tool | merge --clash: list files touched by more than one open PR (step role- | 2026-11-15 | yes | stale | to close |
| #3256 | lane/state-file-parse-check | Parse each state file a Bash or Edit call names (step state-file-parse | 2026-11-14 | yes | stale | to close |
| #3258 | export-promise-guard | Report guard refuses a handoff-only "from now on" promise (replaces #2 | 2026-11-13 | yes | stale | to close |
| #3260 | drain-batch-measure | A batch PR body records lanes, drops, CI runs and CI minutes (step dra | 2026-11-13 | yes | stale | to close |
| #3262 | brief-matches-rulings-tests | A model-judged check reads a lane brief against the rulings store and | 2026-11-14 | yes | stale, stacked on #3206 | to close |
| #3265 | pin-lint-pins-2 | Lane lint follows the pinned trees (rebuild of the pinned-lint chain t | 2026-11-13 | yes | stale, owner-cited, stacked on #1836 | to close |
| #3268 | red-main-resume-records | Decision: merges resume when the revert merges (745 b, 746 b) | 2026-11-13 | yes | stale | to close |
| #3271 | stall-watch-round3-notes-4 | Decision stall-watch drops its step count; the beat note names the fet | 2026-11-13 | yes | stale, owner-cited, stacked on branch carry-stall-log-kept-b | to close |
| #3274 | claude-md-merge-alone-combined | CLAUDE.md: a PR merges alone and may combine several reviewed lanes | 2026-11-14 | yes | stale | to close |
| #3287 | bg-tail-verdict-rebuild | check-tail reads any filter, a glued &, and merge flag forms | 2026-11-14 | yes | stale | to close |
| #3294 | ci-alarm-reads-reverts-c | CI alarm: a failed run a live revert on the branch clears opens no ala | 2026-11-13 | yes | stale | to close |
| #3299 | combined-pr-recipe | ci-hygiene step 8: recipe for a combined PR built by hand | 2026-11-14 | yes | stale, stacked on #3274 | to close |
| #3300 | agent-owned-processes | Each agent's processes are recorded; only those end at SubagentStop (s | 2026-11-14 | yes | stale | to close |
| #3309 | rounds-done-first-pass | Review rounds: a passed round or fix verifier ends review, guard or ch | 2026-11-14 | yes | stale, owner-cited | to close |
| #3311 | r9-texts-follow-up | Texts follow the R9 reading on round 3 | 2026-11-14 | yes | stale, owner-cited | to close |
| #3312 | merge-needs-base-revert-line | Decision merge-needs-current-base: a red main resumes when the revert | 2026-11-14 | yes | stale, owner-cited | to close |
| #3319 | worktree-step-done-check-field | Steps may carry done_check and ci_only; upkeep lists unreadable ones ( | 2026-11-16 | yes | stale | to close |
| #3320 | review-record-restart-on-doc-nit | A refused review restart names its real route, not a new branch (step | 2026-11-14 | yes | stale | to close |
| #3321 | worktree-lane-lint-unknown-ready | The lane lint reads a ready PR's draft run, not the skipped run beside | 2026-11-14 | no | stale | to close |
| #3325 | worktree-task-item-with-options | Refuse a page task item that carries choice options (step task-item-wi | 2026-11-14 | yes | stale | to close |
| #3326 | question-form-widens-label | The widening label skips one global allow entry in claude-settings its | 2026-11-14 | yes | stale | to close |
| #3327 | answered-lines-age-out | Waiting page: a closed line older than a set age counts as read at loa | 2026-11-15 | yes | stale | to close |
| #3330 | ruling-claim-cites-record | A check refuses an owner-ruling claim with no record behind it (step r | 2026-11-14 | yes | stale, owner-cited, stacked on #3206 | to close |
| #3331 | combine-c1 | Combine c1: 27 reviewed PRs (batch) | 2026-11-14 | yes | stale | to close |
| #3332 | combine-d1 | Combine d1: 33 reviewed PRs (batch) | 2026-11-14 | yes | stale | to close |
| #3333 | combine-d2 | Combine d2: 2 reviewed PRs (batch) | 2026-11-14 | no | stale | to close |
| #3334 | lane/coord-scope-false-alarms | Coordinator-scope: no false alarm on input, mode and size words (step | 2026-11-14 | yes | stale, stacked on #3249 | to close |
| #3335 | worktree-hold-names-its-end | Handoff template and lane brief: a hold line carries Ends: | 2026-11-15 | no | stale | to close |
| #3337 | priority-rows-read-pr | merge --priority-rows reads each tracked-priority row's PR by REST (st | 2026-11-14 | yes | stale | to close |
| #3343 | local-allow-ask | Ask when a write adds an allow rule to a project settings.local.json | 2026-11-14 | yes | stale | to close |
| #3346 | ci-wait-subscribes-first | Warn on a ready mark with no PR subscription | 2026-11-14 | yes | stale | to close |
| #3350 | force-advice-own-run | Print the PR's own-run suite count when main is red or --base-red-ok l | 2026-11-14 | yes | stale | to close |
| #3351 | push-skip-test-gaps | Lane push-skip-test-gaps: pin actions: read and cover six push-skip ru | 2026-11-14 | no | stale, owner-cited | to close |
| #3354 | stylisms-apply-six-changes | Apply six signed reply-style changes (29 rules to 25) | 2026-11-14 | yes | stale | to close |
| #3358 | docs-back-unbacked-claims | docs: back or cut the unbacked claims the prose judge named after 3317 | 2026-11-14 | yes | stale | to close |
| #3368 | combine-clear3 | Combine clear set 3: six lane PRs merged onto main bedbce7b5c80 | 2026-11-14 | yes | stale | to close |
| #3370 | cloud-snapshot-age-check-v4 | Warn once when a cloud snapshot's settings.json still runs stale start | 2026-11-15 | yes | stale, owner-cited | to close |
| #3378 | priority-vs-merge-order | merge --priority-rows gates the merge order: no lower PR ahead of a re | 2026-11-14 | yes | stale, owner-cited | to close |
| #3384 | gate-reads-suite-run | Red-main check judges only runs that ran the tests | 2026-11-15 | yes | stale | to close |
| #3409 | ci-batch-mac-runner-3 | ci: batch macOS jobs run on the owner's Mac, fall back to macos-latest | 2026-11-16 | yes | stale, owner-cited | to close |
| #3415 | debt-retire-heartbeat | The debt-close lint prints a heartbeat while a Retire test runs | 2026-11-15 | yes | stale | to close |
| #3416 | lane-notes-stall-phase | Notes: stall-watch beat and phase-timing findings from the review roun | 2026-11-14 | no | stale | to close |
| #3417 | macos-only-fail-lane-lint | The lane lint no longer passes a lane whose selected macOS leg has no | 2026-11-14 | no | stale | to close |
| #3419 | push-skip-text-says-stable-3 | push-skip text says child repos are ruled to follow the stable branch | 2026-11-14 | yes | stale | to close |
| #3420 | tool-reads-config-at-own-ref | A ready check the job lacks reads "not run" on its own line, … | 2026-11-14 | yes | stale | to close |
| #3422 | widens-false-alarm | Tell the question judges that one change for every repo is not a widen | 2026-11-14 | yes | stale | to close |
| #3423 | ready-checks-time-bound | Each ready check has its own time bound and fails by name | 2026-11-14 | yes | stale | to close |
| #3434 | ff-first-lane-test | Test: a fast-forwarded lane keeps its branch on merge | 2026-11-15 | yes | stale | to close |
| #3447 | note-as-lane-strip | Note: as-lane compares after strip | 2026-11-15 | no | stale | to close |
| #3452 | debt-close-defers-draft | A draft's debt close defers its Retire test to the ready PR's CI | 2026-11-15 | no | stale | to close |
| #3453 | notes-r2-slice1-leftovers | Notes: seven limits left by the Retire run moving into CI (PR 3251) | 2026-11-15 | no | stale | to close |
| #3454 | lane/notes-sessionend-limits | Notes: two limits of the session-end sweep wording | 2026-11-15 | no | stale | to close |
| #3459 | lane-idle-shows | Add lane check to the coordinator's wake recipe | 2026-11-15 | no | stale | to close |
| #3462 | lane/deviations-means-departure | Deviations names only a departure; unchecked claims go under Next | 2026-11-15 | no | stale | to close |
| #3463 | qform-no-question-no-basedon | Past-ruling guard: a report that asks no question owes no Based-on lin | 2026-11-15 | no | stale | to close |
| #3465 | tiny-fixes-b | Small-edit review ruling (own-tiny-fixes-b) | 2026-11-15 | yes | stale | to close |
| #3470 | check-glossary-installed-root | The glossary check finds GLOSSARY.md from an installed copy | 2026-11-15 | no | stale | to close |
| #3473 | option-keys-match-chat-2 | Guard rule pick-letter-matches-label: the label decides a pick | 2026-11-15 | yes | stale | to close |
| #3475 | heredoc-text-guards | Three word guards read a text-only heredoc body as text (steps gh-writ | 2026-11-15 | no | stale | to close |
| #3476 | question-checks-rulings-first | Search a question's Departs from line against filed rulings (HELD: net | 2026-11-15 | yes | stale | to close |
| #3482 | sim-lease-gaps-fresh | sim-lease, sim-test: a reuse takes a lease, two Duos at once, a run re | 2026-11-15 | yes | stale, owner-cited | to close |
| #3484 | lane/message-time-from-clock | message-time-from-clock: read header stamps with no separator | 2026-11-15 | yes | stale | to close |
| #3490 | lane/handed-in-push-needs-record | Refuse a push to a PR branch while its newest review log is stale | 2026-11-15 | yes | stale | to close |
| #3491 | rct-notes-review-carries | Note the findings from the review-carries lane | 2026-11-15 | no | stale, owner-cited | to close |
| #3497 | lock-holder-pid-reuse | Own-lock walk: reject a recycled holder pid | 2026-11-15 | no | stale | to close |
| #3504 | five-repos-per-lane-text | Rewrite per-lane merge text for the five repos named by ruling own-820 | 2026-11-15 | yes | stale, owner-cited | to close |
| #3509 | mechanical-before-cleanup | Record ruling own-mechanical-before-cleanup: a one-time cleanup waits | 2026-11-15 | no | stale | to close |
| #3515 | fix-fail-unposted-stands | Fix verifier record: unposted FAIL counts for nothing | 2026-11-15 | yes | stale, owner-cited | to close |
| #3517 | recovered-label-first | Recovered guard: refusal names both carry forms | 2026-11-15 | no | stale, owner-cited | to close |
| #3520 | lane/combine-train-rest | combine-train: --from-rest reads the queue from GitHub (step combine-t | 2026-11-15 | no | stale | to close |
| #3523 | ready-remedy-names-ready | Stale-page remedy and ready-mark docs name merge --ready first | 2026-11-15 | yes | stale | to close |
| #3524 | local-stable-refresh | Local sessions refresh a stale stable install mid-session | 2026-11-15 | yes | stale, owner-cited | to close |
| #3526 | aligned-agents-skills-scope | aligned check reads agents/ and skills/ Markdown | 2026-11-15 | no | stale, owner-cited | to close |
| #3532 | never-stamp-no-escape | Refuse a Checked never premise stamp in the handoff stamp rule | 2026-11-15 | yes | stale, owner-cited | to close |
| #3534 | nudge-rearm-handoff-lag | Stop nudge re-arms after compaction; Stop refuses a handoff that lags | 2026-11-15 | yes | stale | to close |
| #3546 | debt-cloud-refresh-clear-fork | Debt: a cloud session that clears or forks keeps stale hooks | 2026-11-15 | no | stale, owner-cited | to close |
| #3554 | unknown-read-lint-flake-2 | Debt: unknown-read lint check flake | 2026-11-15 | no | stale | to close |
| #3559 | ruling-overtakes-record-2 | Flag a Markdown file that cites a ruling and not the later ruling that | 2026-11-15 | yes | stale | to close |
| #3572 | h17-path-cap-census-2 | Delete the 200-path cap in the pushed-copy proof; bound it by the hook | 2026-11-16 | no | stale, owner-cited | to close |
| #3575 | h12-deadline-ask-census-3 | The cap-lift end joins the model-cap ask; the 24 h limit is gone (cens | 2026-11-16 | no | stale, owner-cited | to close |
| #3578 | revive-open-asks-at-wake | waiting-page: list asks with no reply at wake (revives #2699) | 2026-11-16 | yes | stale | to close |
| #3579 | pr-tmpl-copies-equal-2 | check_layout: keep the two PR template copies byte-equal (revives #270 | 2026-11-16 | no | stale | to close |
| #3580 | lease-remedy-form-d | Force-push guard: remedy names the sha lease form (replaces #2724) | 2026-11-16 | no | stale | to close |
| #3581 | lane-ack-question-revive | A lane's plain acknowledgement is not an answer to its question (reviv | 2026-11-16 | yes | stale | to close |
| #3582 | task-options-departs | Read a page task with options for its Departs from line | 2026-11-16 | no | stale | to close |
| #3693 | allow-lane-lint-perm | Allow the lane lint command in permissions | 2026-11-15 | no | stale | to close |
