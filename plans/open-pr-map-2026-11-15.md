# Open PR map by live owner, claude-settings, 2026-11-15

Source: the consultant's open-pr-map TSV (524 open PRs, REST read about 23:15 CST Nov 15) and the live-work file (sessions read 23:15 CST; the session list is partial, 483 rows). Rewritten by triage 8 at 23:35 CST under the coordinator's owner rule of 23:30 CST Nov 15 (coordinator's pick, undoable, not owner-typed).

Owner rule, in order: (1) runner 10: its existing sections, and every ready PR (its lane lint and record at the live head are not read here: unmeasured). (2) The PR's own session when it is RUNNING in the live read. (3) Triage 8: stale drafts with no live session; triage closes one only when a fresh REST read proves it merged, superseded, duplicate or abandoned, naming the replacing PR or commit, never from the Nov 12 table. (4) The coordinator: everything else. Verdicts in the older plans are keywords from Nov 12 and are not acts. No PR is closed by this file.

## Summary, one section per owner

| Section | Session | PRs |
|---|---|---|
| Parked by the coordinator: no live session on it; draft; no hand-in | none (all 56 sessions re-read at 23:35 CST: 54 archived, 2 not found, none running) | 327 |
| Triage 8 (REST-proven stale drafts: close as replaced) | session_013NEJL2kLm8c5qDhosD6Nqb | 99 |
| Runner 10 (merge candidates) | session_013NEJL2f1YCYsvLdpFqtWP3 | 81 |
| Lane session session_013NEJKz5AWFJhGvmCUoi6wQ | session_013NEJKz5AWFJhGvmCUoi6wQ | 11 |
| Coordinator (decides per PR: resume, hand over, or park) | session_013NEJL1gw6EdrSyvHkTUEx6 | 5 |
| Lane session session_013NEJL3tMVa6d437aatxvYY | session_013NEJL3tMVa6d437aatxvYY | 1 |
| **Total** | | **524** |

Owners: 3 live lane sessions, plus runner 10, the coordinator and triage 8. PRs with no owner under the rule: none. Each coordinator row says why no live session holds it. A goal pointer is one line: "your PRs are section <name> of this file".

## Parked by the coordinator: no live session on it; draft; no hand-in (327)

| PR | Title | Draft | Why this owner | Older plan verdict |
|---|---|---|---|---|
| #3556 | Skip the Windows guard shards when no guard input changed | draft | no live session on it; draft; no hand-in | none |
| #3551 | Lane lint follows pinned trees through pin_tree; drop --pin… | draft | no live session on it; draft; no hand-in | none |
| #3550 | Cloud refresh switches a whole install generation by one li… | draft | no live session on it; draft; no hand-in | none |
| #3546 | Debt: a cloud session that clears or forks keeps stale hooks | draft | no live session on it; draft; no hand-in | none |
| #3541 | Add a shard switch and exactly-once test for the install.sh… | draft | no live session on it; draft; no hand-in | none |
| #3540 | Push runs only the Linux suites; the slow legs run once a d… | draft | no live session on it; draft; no hand-in | park: #3540 held for ite… |
| #3539 | Show progress in the lane-lint mutation stage | draft | no live session on it; draft; no hand-in | none |
| #3534 | Stop nudge re-arms after compaction; Stop refuses a handoff… | draft | no live session on it; draft; no hand-in | none |
| #3533 | Drop the Incident sentence from the Merge Tool Read Checks … | draft | no live session on it; draft; no hand-in | none |
| #3532 | Refuse a Checked never premise stamp in the handoff stamp r… | draft | no live session on it; draft; no hand-in | none |
| #3526 | aligned check reads agents/ and skills/ Markdown | draft | no live session on it; draft; no hand-in | none |
| #3525 | Check a record's Facts line against live PR and branch state | draft | no live session on it; draft; no hand-in | mentioned: state-line-li… |
| #3524 | Local sessions refresh a stale stable install mid-session | draft | no live session on it; draft; no hand-in | none |
| #3521 | project-ops: check every session role has text and a brief … | draft | no live session on it; draft; no hand-in | none |
| #3519 | Lane lint carries a claim or page commit made after a clean… | draft | no live session on it; draft; no hand-in | mentioned: pick 1, stdli… |
| #3517 | Recovered guard: refusal names both carry forms | draft | no live session on it; draft; no hand-in | mentioned: Item 860 b: p… |
| #3515 | Fix verifier record: unposted FAIL counts for nothing | draft | no live session on it; draft; no hand-in | none |
| #3511 | Delete three dead plans (keep trial-briefs) | draft | no live session on it; draft; no hand-in | none |
| #3509 | Record ruling own-mechanical-before-cleanup: a one-time cle… | draft | no live session on it; draft; no hand-in | none |
| #3504 | Rewrite per-lane merge text for the five repos named by rul… | draft | no live session on it; draft; no hand-in | park: HELD drafts (lanes… |
| #3491 | Note the findings from the review-carries lane | draft | no live session on it; draft; no hand-in | none |
| #3489 | Lane lint carries a generated page commit with no stamp kin… | draft | no live session on it; draft; no hand-in | mentioned: Lane review-c… |
| #3484 | message-time-from-clock: read header stamps with no separat… | draft | no live session on it; draft; no hand-in | none |
| #3481 | Carry the lane lint across a clean merge of main | draft | no live session on it; draft; no hand-in | none |
| #3476 | Search a question's Departs from line against filed rulings… | draft | no live session on it; draft; no hand-in | park: 869 a started lane… |
| #3475 | Three word guards read a text-only heredoc body as text (st… | draft | no live session on it; draft; no hand-in | none |
| #3473 | Guard rule pick-letter-matches-label: the label decides a p… | draft | no live session on it; draft; no hand-in | none |
| #3471 | Rewrite stale switch and stable claims to what is live | draft | no live session on it; draft; no hand-in | mentioned: #3471 (settin… |
| #3470 | The glossary check finds GLOSSARY.md from an installed copy | draft | no live session on it; draft; no hand-in | none |
| #3466 | CI's debt step skips its repeat run of the guard suite when… | draft | no live session on it; draft; no hand-in | none |
| #3465 | Small-edit review ruling (own-tiny-fixes-b) | draft | no live session on it; draft; no hand-in | mentioned: nothing acted… |
| #3463 | Past-ruling guard: a report that asks no question owes no B… | draft | no live session on it; draft; no hand-in | none |
| #3462 | Deviations names only a departure; unchecked claims go unde… | draft | no live session on it; draft; no hand-in | mentioned: its body list… |
| #3459 | Add lane check to the coordinator's wake recipe | draft | no live session on it; draft; no hand-in | none |
| #3458 | Combine docs notes: three lanes (2) | draft | no live session on it; draft; no hand-in | mentioned: Open PR #3458… |
| #3454 | Notes: two limits of the session-end sweep wording | draft | no live session on it; draft; no hand-in | none |
| #3453 | Notes: seven limits left by the Retire run moving into CI (… | draft | no live session on it; draft; no hand-in | none |
| #3452 | A draft's debt close defers its Retire test to the ready PR… | draft | no live session on it; draft; no hand-in | none |
| #3447 | Note: as-lane compares after strip | draft | no live session on it; draft; no hand-in | none |
| #3434 | Test: a fast-forwarded lane keeps its branch on merge | draft | no live session on it; draft; no hand-in | none |
| #3423 | Each ready check has its own time bound and fails by name | draft | no live session on it; draft; no hand-in | none |
| #3422 | Tell the question judges that one change for every repo is … | draft | no live session on it; draft; no hand-in | merged-already (PR still… |
| #3420 | A ready check the job lacks reads "not run" on its own line… | draft | no live session on it; draft; no hand-in | wave (rebuild/rebase): -… |
| #3417 | The lane lint no longer passes a lane whose selected macOS … | draft | no live session on it; draft; no hand-in | park: does not unblock `… |
| #3416 | Notes: stall-watch beat and phase-timing findings from the … | draft | no live session on it; draft; no hand-in | none |
| #3415 | The debt-close lint prints a heartbeat while a Retire test … | draft | no live session on it; draft; no hand-in | none |
| #3409 | ci: batch macOS jobs run on the owner's Mac, fall back to m… | draft | no live session on it; draft; no hand-in | park: #3409 held for ite… |
| #3385 | CI: 41 checks-job steps that read docs run only when their … | draft | no live session on it; draft; no hand-in | replaced, not rebased (coordinator pick 04:54 CST Nov 16, relayed): lane ci-skip-untouched-steps builds 3b from main 8d0b4cb75, opens the new draft, then closes #3385 with a pointer; closed as replaced (REST 05:39 CST Nov 16: #3385 closed 05:26 CST, not merged; replacement #3584 open draft, base main 8d0b4cb75) |
| #3384 | Red-main check judges only runs that ran the tests | draft | no live session on it; draft; no hand-in | none |
| #3383 | Every landed merge prints the idle-lane list; a stale live … | draft | no live session on it; draft; no hand-in | none |
| #3380 | Allow entries name [--priority-rows <file>] on the runner's… | draft | no live session on it; draft; no hand-in | none |
| #3379 | merge: a combined-PR marker line makes a cross-rule clash a… | draft | no live session on it; draft; no hand-in | none |
| #3378 | merge --priority-rows gates the merge order: no lower PR ah… | draft | no live session on it; draft; no hand-in | none |
| #3370 | Warn once when a cloud snapshot's settings.json still runs … | draft | no live session on it; draft; no hand-in | none |
| #3362 | After a compaction, refuse writes and replies until an Audi… | draft | no live session on it; draft; no hand-in | none |
| #3351 | Lane push-skip-test-gaps: pin actions: read and cover six p… | draft | no live session on it; draft; no hand-in | none |
| #3343 | Ask when a write adds an allow rule to a project settings.l… | draft | no live session on it; draft; no hand-in | none |
| #3339 | Spawn guard: a fenced Round or Try marker in a brief counts… | draft | no live session on it; draft; no hand-in | none |
| #3337 | merge --priority-rows reads each tracked-priority row's PR … | draft | no live session on it; draft; no hand-in | none |
| #3335 | Handoff template and lane brief: a hold line carries Ends: | draft | no live session on it; draft; no hand-in | mentioned: round 2 took … |
| #3334 | Coordinator-scope: no false alarm on input, mode and size w… | draft | no live session on it; draft; no hand-in | none |
| #3330 | A check refuses an owner-ruling claim with no record behind… | draft | no live session on it; draft; no hand-in | none |
| #3328 | Lane cards: update_trigger with ask_owner is refused in a l… | draft | no live session on it; draft; no hand-in | none |
| #3327 | Waiting page: a closed line older than a set age counts as … | draft | no live session on it; draft; no hand-in | none |
| #3326 | The widening label skips one global allow entry in claude-s… | draft | no live session on it; draft; no hand-in | none |
| #3321 | The lane lint reads a ready PR's draft run, not the skipped… | draft | no live session on it; draft; no hand-in | park [order row 5]: Held… |
| #3320 | A refused review restart names its real route, not a new br… | draft | no live session on it; draft; no hand-in | none |
| #3319 | Steps may carry done_check and ci_only; upkeep lists unread… | draft | no live session on it; draft; no hand-in | none |
| #3316 | Reviewer agent: the round-1 model line matches the round ro… | draft | no live session on it; draft; no hand-in | park [order row 5]: Held… |
| #3311 | Texts follow the R9 reading on round 3 | draft | no live session on it; draft; no hand-in | none |
| #3309 | Review rounds: a passed round or fix verifier ends review, … | draft | no live session on it; draft; no hand-in | none |
| #3308 | The Relayed Grant allow entry says a routed closed item cou… | draft | no live session on it; draft; no hand-in | wave (rebuild/rebase): L… |
| #3300 | Each agent's processes are recorded; only those end at Suba… | draft | no live session on it; draft; no hand-in | none |
| #3293 | A builder resolves a test merge conflict; a check proves no… | draft | no live session on it; draft; no hand-in | none |
| #3286 | Model layout: session rows by role and lane kind, builder a… | draft | no live session on it; draft; no hand-in | park [order row 5]: Held… |
| #3271 | Decision stall-watch drops its step count; the beat note na… | draft | no live session on it; draft; no hand-in | none |
| #3270 | Each Send wakes the page writer, which exports the git copy… | draft | no live session on it; draft; no hand-in | mentioned: #3270 retarge… |
| #3265 | Lane lint follows the pinned trees (rebuild of the pinned-l… | draft | no live session on it; draft; no hand-in | none |
| #3262 | A model-judged check reads a lane brief against the rulings… | draft | no live session on it; draft; no hand-in | park [order row 5]: Held… |
| #3260 | A batch PR body records lanes, drops, CI runs and CI minute… | draft | no live session on it; draft; no hand-in | none |
| #3258 | Report guard refuses a handoff-only "from now on" promise (… | draft | no live session on it; draft; no hand-in | none |
| #3254 | merge --clash: list files touched by more than one open PR … | draft | no live session on it; draft; no hand-in | none |
| #3253 | A reader of origin/roadmap fetches it before its verdict | draft | no live session on it; draft; no hand-in | mentioned: #3253's lane … |
| #3252 | merge --batch-label adds the batch label to an integration … | draft | no live session on it; draft; no hand-in | none |
| #3249 | Hold the coordinator's own writes, spawns and merges; read … | draft | no live session on it; draft; no hand-in | park: rebuild-2123 (#324… |
| #3248 | Resume guard: refuse a resume of a finished agent whose wor… | draft | no live session on it; draft; no hand-in | none |
| #3244 | Report guard: a pre-existing claim names a run on the base,… | draft | no live session on it; draft; no hand-in | none |
| #3242 | merge --reviewed reads comments since a stored cursor | draft | no live session on it; draft; no hand-in | park: Held or waiting: #… |
| #3240 | The release check also merge-trees each PR against the open… | draft | no live session on it; draft; no hand-in | none |
| #3235 | merge --review-record: read the record back, FAILED on a re… | draft | no live session on it; draft; no hand-in | none |
| #3234 | Stamp check reads bracketed, parenthesised and dated header… | draft | no live session on it; draft; no hand-in | none |
| #3231 | Lane lint refuses a PR whose commits name two sessions (ste… | draft | no live session on it; draft; no hand-in | none |
| #3230 | Silent-undo check reads the PR body from the CLI, the event… | draft | no live session on it; draft; no hand-in | none |
| #3229 | Lane lint refuses a review range that breaks the ancestry r… | draft | no live session on it; draft; no hand-in | none |
| #3223 | conflict-markers asks when a git read cannot run, instead o… | draft | no live session on it; draft; no hand-in | wave (rebuild/rebase): -… |
| #3219 | Stale flags: STALE007 flag reader on top of #3182 (rebuild … | draft | no live session on it; draft; no hand-in | none |
| #3216 | ci-cancel-on-close-v2: cancel a closed PR's unfinished CI r… | draft | no live session on it; draft; no hand-in | none |
| #3215 | Each batch merge mails every cloud session to refresh (merg… | draft | no live session on it; draft; no hand-in | none |
| #3211 | The feedback guard counts a mail send as a send (mail-guard… | draft | no live session on it; draft; no hand-in | none |
| #3209 | builder-diff judges an auto-committed strategy merge or pul… | draft | no live session on it; draft; no hand-in | none |
| #3200 | Lane lint follows the pinned trees, as the ready check does… | draft | no live session on it; draft; no hand-in | none |
| #3197 | Page writer label matched as a whole id token (replaces #17… | draft | no live session on it; draft; no hand-in | none |
| #3195 | Glossary: name the step statuses | draft | no live session on it; draft; no hand-in | none |
| #3190 | Carry the MCP guard line and the review-record stack onto m… | draft | no live session on it; draft; no hand-in | none |
| #3189 | Let merge --fix-check span a gap of record or notes commits | draft | no live session on it; draft; no hand-in | none |
| #3188 | A cloud session that compacts refreshes its hooks | draft | no live session on it; draft; no hand-in | wave (rebuild/rebase): t… |
| #3187 | Review rounds: round 1 model per diff, finding labels, and … | draft | no live session on it; draft; no hand-in | none |
| #3186 | STALE011: a line anchor whose sentence names a symbol its l… | draft | no live session on it; draft; no hand-in | wave (rebuild/rebase): t… |
| #3185 | Let a FAIL review record name a past head of the pull reque… | draft | no live session on it; draft; no hand-in | none |
| #3181 | ste-lint fails closed on an unread input and keeps its exit… | draft | no live session on it; draft; no hand-in | none |
| #3179 | Notes fix guard 2: SessionStart TMPDIR line, and a message-… | draft | no live session on it; draft; no hand-in | none |
| #3178 | ci-job gives each run step CLAUDE_SETTINGS_DIR: its pin's t… | draft | no live session on it; draft; no hand-in | none |
| #3175 | merge: a debt refusal of a batch PR stores its one lane as … | draft | no live session on it; draft; no hand-in | none |
| #3174 | Lane-lint refuses a debt close whose Retire names no test | draft | no live session on it; draft; no hand-in | none |
| #3169 | Carry #1632: linked node_modules reads npm aliases and work… | draft | no live session on it; draft; no hand-in | none |
| #3167 | Rebuild: P5 states the 2026-11-07 timed-test ruling; plan t… | draft | no live session on it; draft; no hand-in | none |
| #3166 | The live-stream refusal names the Monitor tool in its remedy | draft | no live session on it; draft; no hand-in | none |
| #3164 | Name the skipped repo in the home-check refusal | draft | no live session on it; draft; no hand-in | wave (rebuild/rebase): t… |
| #3160 | report guard: design-reviewer names are not reviewer claims… | draft | no live session on it; draft; no hand-in | none |
| #3159 | Decisions: batch runner closes superseded PRs with a pointe… | draft | no live session on it; draft; no hand-in | none |
| #3157 | Record ruling prose-batch-order | draft | no live session on it; draft; no hand-in | none |
| #3156 | merge --lane-lint: a dirty PR with no touched run reads "me… | draft | no live session on it; draft; no hand-in | none |
| #3147 | Live-file publisher gets a tracked home with a test | draft | no live session on it; draft; no hand-in | none |
| #3146 | stale-cites: a read path::name cite shows the named symbol | draft | no live session on it; draft; no hand-in | none |
| #3143 | Item 8 accepts an unmeasured-claim challenge; the denial ta… | draft | no live session on it; draft; no hand-in | none |
| #3141 | A session fast-forwards its own clean checkout to main at s… | draft | no live session on it; draft; no hand-in | none |
| #3139 | Decision lanes-run-no-full-ci-job states the lane-lint join… | draft | no live session on it; draft; no hand-in | none |
| #3137 | mail status: a sender reads whether its message was taken | draft | no live session on it; draft; no hand-in | none |
| #3136 | The lane-archive refusal names add_repo when it cannot read… | draft | no live session on it; draft; no hand-in | none |
| #3132 | A check lists open ruled entries whose step is done or has … | draft | no live session on it; draft; no hand-in | none |
| #3131 | A PASS fix verifier stands in for round 2 of a review recor… | draft | no live session on it; draft; no hand-in | none |
| #3130 | Cite merge.py by symbol in two decisions (merge-line-cites-… | draft | no live session on it; draft; no hand-in | none |
| #3124 | The page writer is found by its triage tag, not a fixed ses… | draft | no live session on it; draft; no hand-in | none |
| #3117 | Batch runner skips a lane whose get_session shows unarchive… | draft | no live session on it; draft; no hand-in | note: Close-list caveat:… |
| #3111 | Deny a lane start with no cs-step tag | draft | no live session on it; draft; no hand-in | none |
| #3110 | Add a late handoff checkpoint, 20k under the room | draft | no live session on it; draft; no hand-in | none |
| #3109 | A push after a moved head names the fresh-round route, and … | draft | no live session on it; draft; no hand-in | mentioned: round 2 took … |
| #3108 | merge --confirm prints the idle-lanes report, or says the p… | draft | no live session on it; draft; no hand-in | none |
| #3102 | A push of a clean merge of main to a fix-checked PR branch … | draft | no live session on it; draft; no hand-in | mentioned: round 2 took … |
| #3100 | session-messages: line 6 says the true status now | draft | no live session on it; draft; no hand-in | none |
| #3094 | Stale prose fixture suite runs on Python 3.9 | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #3092 | ios-apps starter: UI tests tap through one centre function … | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #3091 | The main-claim check flags only a branch-like use of main | draft | no live session on it; draft; no hand-in | none |
| #3090 | ios-apps: one build per session, another session's build do… | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #3084 | Consultant role is placed in the side-session list and role… | draft | no live session on it; draft; no hand-in | wave (rebuild/rebase): t… |
| #3082 | A builder may change only comments in a test file (step bui… | draft | no live session on it; draft; no hand-in | none |
| #3076 | The feedback inbox skips echoes of commands the owner ran | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #3074 | An owner override lifts the Explore model veto for a spawn … | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #3073 | Guards read repo config from the origin/main blob | draft | no live session on it; draft; no hand-in | none |
| #3072 | Lane-lint fails when merge --reviewed cannot parse the revi… | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #3071 | SessionStart logs each skip of the live pin update | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #3068 | A regression or no-regression claim cites a read of main (s… | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #3065 | Waiting page: splice.py --add-design puts mockup pictures o… | draft | no live session on it; draft; no hand-in | park: - Open step: #3065… |
| #3061 | Decision watch finds the transcript by session id | draft | no live session on it; draft; no hand-in | park: - Open step: #3065… |
| #3059 | guard: pointer-edit also judges a Bash write into the point… | draft | no live session on it; draft; no hand-in | park: - Open step: #3065… |
| #3058 | Record how far each child repo is from main (child-repo-gap… | draft | no live session on it; draft; no hand-in | park: - Open step: #3065… |
| #3056 | Guard cull docs: wrong refusals become notes, stale records… | draft | no live session on it; draft; no hand-in | park: - Guard-cull famil… |
| #3050 | Guard: refuse a builder's git apply onto a test path at wri… | draft | no live session on it; draft; no hand-in | park: - Open step: #3065… |
| #3047 | mutate-timeout-crashed: a hung mutant scores crashed, the r… | draft | no live session on it; draft; no hand-in | park: - Held, open step … |
| #3044 | brief-names-push-target: an agent pushes only to the branch… | draft | no live session on it; draft; no hand-in | park: - Held, open step … |
| #3043 | Debt check: a wrong refusal closes by a notes line, no test… | draft | no live session on it; draft; no hand-in | park: - Held, guard-cull… |
| #3040 | Debts from the relay-grant-words review (step page-wakes-an… | draft | no live session on it; draft; no hand-in | park: - Held, #3038 (the… |
| #3039 | Guard fixes: 13 small rows from the kept-notes re-check (st… | draft | no live session on it; draft; no hand-in | park: - Held, branch sta… |
| #3038 | A relayed grant carries the owner's exact words; the sender… | draft | no live session on it; draft; no hand-in | park: - Held, #3038 (the… |
| #3037 | Guard cull: the frozen-path guard stops refusing reads (fam… | draft | no live session on it; draft; no hand-in | park: - Held, the guard-… |
| #3035 | Guard cull: glossary rows keep seven record ids (family 10) | draft | no live session on it; draft; no hand-in | none |
| #3032 | Guard cull: text reads are not writes (family 8) | draft | no live session on it; draft; no hand-in | none |
| #3031 | Guard cull: ruling-kind check reads Home only after Kind (f… | draft | no live session on it; draft; no hand-in | none |
| #3030 | Guard cull: the test temp-run guard reads Python 3.9 code (… | draft | no live session on it; draft; no hand-in | none |
| #3029 | Guard cull: the question form's Departs-from dash check is … | draft | no live session on it; draft; no hand-in | none |
| #3028 | Guard cull: the Recovered report-line check is deleted (fam… | draft | no live session on it; draft; no hand-in | park: - Held, the guard-… |
| #3026 | Guard: an agent's hand-made-worktree refusal names its own … | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #3024 | GUARD_PATHS covers agents/ | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #3014 | merge-path-same-everywhere: one merge role proof, local and… | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #3008 | Brake raw API merges and pushes to main while a batch's CI … | draft | no live session on it; draft; no hand-in | none |
| #3006 | One home per answer: the Stop guard keeps options off chat … | draft | no live session on it; draft; no hand-in | park: - Held, held in th… |
| #3005 | Run the unknown-reads contract lint on Linux only | draft | no live session on it; draft; no hand-in | park: - Held or draft: #… |
| #3004 | ci-hygiene: run each suite once per batch (R61-R63) | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #3003 | Audit prose store tending; fix two tending entries | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #2997 | Item cites carry their short name (report and handoff guard… | draft | no live session on it; draft; no hand-in | none |
| #2996 | The feedback log closes, cleans and lists its own items | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #2989 | Check step notes' "owner picked" claims against the page's … | draft | no live session on it; draft; no hand-in | none |
| #2982 | Waiting page: Remove and Edit presses keep whole words at n… | draft | no live session on it; draft; no hand-in | none |
| #2981 | Closing a page item keeps the owner's saved answer | draft | no live session on it; draft; no hand-in | none |
| #2979 | A push after a review round asks until that round's record … | draft | no live session on it; draft; no hand-in | none |
| #2975 | Time-pinned finder: a keep marker with a reason keeps a sle… | draft | no live session on it; draft; no hand-in | none |
| #2974 | Plan: gather other repos' outbox findings into triage | draft | no live session on it; draft; no hand-in | none |
| #2972 | Busy files: refuse a batch build that holds two lanes on on… | draft | no live session on it; draft; no hand-in | none |
| #2971 | Guard: refuse a session's write to the waiting page's answe… | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #2967 | Guard: an agent's commit touches only the files its brief n… | draft | no live session on it; draft; no hand-in | none |
| #2962 | Silent-undo check: an in-place edit of a note the branch di… | draft | no live session on it; draft; no hand-in | none |
| #2959 | Mods and stamp tests: mock timers and yields instead of rea… | draft | no live session on it; draft; no hand-in | none |
| #2958 | Lint and merge tests: same-process ratio, try-count polls, … | draft | no live session on it; draft; no hand-in | none |
| #2957 | Repeat mark skips a same-thread follow-up within 30 minutes | draft | no live session on it; draft; no hand-in | none |
| #2955 | Each waiting-page item names who wakes (page-wakes-and-rela… | draft | no live session on it; draft; no hand-in | park: - Held, held in th… |
| #2953 | Only the page writer watches the waiting page (page-wakes-a… | draft | no live session on it; draft; no hand-in | park: - Held, held in th… |
| #2952 | Janitor tests: pinned clocks, start markers and condition w… | draft | no live session on it; draft; no hand-in | none |
| #2949 | Hook tests: stall-watch polls wait on conditions, blind-bri… | draft | no live session on it; draft; no hand-in | none |
| #2948 | Merge tool: a docs-only record may file a decision when the… | draft | no live session on it; draft; no hand-in | park: - Held, held in th… |
| #2946 | Agents: no retry of a refused hand-back call | draft | no live session on it; draft; no hand-in | park: - Held, held in th… |
| #2945 | install.sh: tree_hash skips generated __pycache__ bytecode | draft | no live session on it; draft; no hand-in | none |
| #2943 | The roadmap build lists started sessions that are waiting, … | draft | no live session on it; draft; no hand-in | wave (rebuild/rebase): t… |
| #2941 | Narration check: an example id in a history clause is still… | draft | no live session on it; draft; no hand-in | park: - Held, held in th… |
| #2940 | merge: --reviewed reads a fix check's round from the earlie… | draft | no live session on it; draft; no hand-in | mentioned: pick 1, stdli… |
| #2939 | Batch lanes merge in hand-in order; stacked check reads onc… | draft | no live session on it; draft; no hand-in | none |
| #2937 | Guard the Monitor tool's command like a shell command (lane… | draft | no live session on it; draft; no hand-in | mentioned: after #2937 i… |
| #2933 | Guard tests: fake clock for the page-item budget case, reas… | draft | no live session on it; draft; no hand-in | none |
| #2932 | A coordinator's pick cites a ruling before send_message car… | draft | no live session on it; draft; no hand-in | none |
| #2931 | Judge a wrapped commit -F of a scratchpad file (scratchpad-… | draft | no live session on it; draft; no hand-in | none |
| #2927 | Artifact guards 5/5: read Mac artifact calls in the feedbac… | draft | no live session on it; draft; no hand-in | park: - Held, branch sta… |
| #2926 | Artifact guards 4/5: read Mac artifact calls in the transcr… | draft | no live session on it; draft; no hand-in | none |
| #2925 | Artifact guards 3/5: route Mac artifact calls through the c… | draft | no live session on it; draft; no hand-in | none |
| #2924 | Artifact guards 2/5: judge Mac artifact calls in the guard | draft | no live session on it; draft; no hand-in | none |
| #2923 | Artifact guards 1/5: name the artifact tools in one constan… | draft | no live session on it; draft; no hand-in | park: - Held, branch sta… |
| #2920 | CI alarm: every cap end on main wakes the batch runner | draft | no live session on it; draft; no hand-in | mentioned: #2875 and #29… |
| #2918 | ask-alone: a plain chained git push is no forced push | draft | no live session on it; draft; no hand-in | park: - Held, branch sta… |
| #2915 | One shared tending contract and runner for prose stores | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #2914 | merge: refuse --fix-check with no --round | draft | no live session on it; draft; no hand-in | park: - Held, branch sta… |
| #2913 | Guard: message refs judge a PR word apart from its number | draft | no live session on it; draft; no hand-in | none |
| #2907 | Check that no tool reads the waiting copy as a live source;… | draft | no live session on it; draft; no hand-in | none |
| #2905 | The draft step claims record numbers before ready (one CI r… | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #2900 | Express pass: owner quotes that match the feedback log skip… | draft | no live session on it; draft; no hand-in | none |
| #2899 | sim-lease grants on the load brake's measure, not the load … | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #2895 | Run a repo-declared typecheck after each edit, from one cla… | draft | no live session on it; draft; no hand-in | park: - Held, branch sta… |
| #2894 | Deny an agent's start_session call (step both-session-start… | draft | no live session on it; draft; no hand-in | none |
| #2893 | A lane dropped from two batches leaves the queue for a fix … | draft | no live session on it; draft; no hand-in | note: Close-list caveat:… |
| #2886 | Fix the five debts of the brief-write guard, with the reade… | draft | no live session on it; draft; no hand-in | none |
| #2885 | The terse-line check reads HTML comments as CommonMark does | draft | no live session on it; draft; no hand-in | none |
| #2883 | check_debt_retire: a Retire test must fail on the debt's bi… | draft | no live session on it; draft; no hand-in | park: - Held, branch sta… |
| #2881 | A habit or brief line is no guard: a report's guard line na… | draft | no live session on it; draft; no hand-in | wave (rebuild/rebase): t… |
| #2879 | Add stale_pages.py --lag: answer read delay and unread age | draft | no live session on it; draft; no hand-in | none |
| #2878 | Roadmap upkeep lists blocked steps with no open blocker | draft | no live session on it; draft; no hand-in | none |
| #2875 | One wake for a CI alarm on a push to main | draft | no live session on it; draft; no hand-in | mentioned: #2875 and #29… |
| #2874 | Draft decision: what each review round catches (review-roun… | draft | no live session on it; draft; no hand-in | none |
| #2873 | Merge guard reads a quoted paren inside a $( ) span (merge-… | draft | no live session on it; draft; no hand-in | park: - Held, branch sta… |
| #2872 | A no-start agent lock whose pid was reused frees its tree (… | draft | no live session on it; draft; no hand-in | none |
| #2870 | Guard: a coordinator pick must reach the waiting page | draft | no live session on it; draft; no hand-in | none |
| #2869 | PR ledger: set round-age limits from measured ages | draft | no live session on it; draft; no hand-in | none |
| #2865 | Match a cloud-label page writer in the waiting export check | draft | no live session on it; draft; no hand-in | none |
| #2864 | Recovered guard refusal carries a draft of the missing line… | draft | no live session on it; draft; no hand-in | none |
| #2863 | CI limits from recent runs: script and records (S1 of time-… | draft | no live session on it; draft; no hand-in | park: Reopened after a p… |
| #2860 | Each failing job wakes the batch runner as it fails | draft | no live session on it; draft; no hand-in | wave (rebuild/rebase): f… |
| #2859 | A review record that does not parse is flagged by the lane … | draft | no live session on it; draft; no hand-in | park: - Held, branch sta… |
| #2858 | Warn-only one-term lint (STE022) | draft | no live session on it; draft; no hand-in | park: - Held, branch sta… |
| #2856 | Guard: refuse an agent's write to a session handoff; skip h… | draft | no live session on it; draft; no hand-in | park: - Held, branch sta… |
| #2852 | Move accepted CLAUDE.md sections to the files that need the… | draft | no live session on it; draft; no hand-in | none |
| #2851 | A pass claim cites its verdict line; a bare lint run is ref… | draft | no live session on it; draft; no hand-in | none |
| #2850 | One override route: length forms are timed on the fast path… | draft | no live session on it; draft; no hand-in | wave (rebuild/rebase): t… |
| #2845 | PR ledger: each open PR gets one next act, owner and age in… | draft | no live session on it; draft; no hand-in | close: . 594 none, "is t… |
| #2838 | merge: --blame takes a run still going once a job finished … | draft | no live session on it; draft; no hand-in | park: Runner 10 hold lis… |
| #2836 | Stop checks speak in one merged message (lane stop-checks-o… | draft | no live session on it; draft; no hand-in | none |
| #2832 | merge: count hooks/guard.py's import closure as guard paths | draft | no live session on it; draft; no hand-in | park: - Held, branch sta… |
| #2828 | Each plan ruling part cites its step; a check flags a missi… | draft | no live session on it; draft; no hand-in | none |
| #2801 | Guard tables per section: each family's rows live in its ow… | draft | no live session on it; draft; no hand-in | none |
| #2756 | Waiting page: Answered section starts closed (carries #2317) | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #2737 | Judge replay corpus: known allow and deny cases run in CI w… | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #2729 | Refuse a bare PR wait in a step write, flag a dead one in t… | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #2720 | Guard: a blank or non-ISO time in a page or step write is r… | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #2714 | Each agent role file and the lane start text carry one shor… | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #2700 | Guard: a background lane-lint call sets a timeout above the… | draft | no live session on it; draft; no hand-in | park: - Held, its branch… |
| #2696 | Known-defect replay: a load hook reads a fallback catcher U… | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #2684 | Refuse bare artifact links at a push to the record branch (… | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #2683 | One rule for an unknown read, carried from #1330 | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #2662 | Record the per-batch spend log ruling | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #2654 | File two round-2 review notes from the guard test split | draft | no live session on it; draft; no hand-in | close: Closed in Triage … |
| #2572 | Guard: an agent's start_session is refused, like create_ses… | draft | no live session on it; draft; no hand-in | park: Holds list 11:59 C… |
| #2562 | A lane starts with effort medium and its whole brief, openi… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #2527 | A page item cite carries its short name (report guard and h… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #2483 | Cloud allow rules for gh api PR close and PR comment | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #2440 | Review-record guard judges wrapper, GraphQL, full-URL, quot… | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #2347 | Stack the waiting page's presses under the text at narrow w… | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #2326 | Review records: a failed fix check counts as a round, FAIL … | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #2300 | ci-scope: pin the two test-helper routing arms and name eac… | draft | no live session on it; draft; no hand-in | park: Holds list 11:59 C… |
| #2234 | other-checkout: a quoted script argument or a kept heredoc … | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #2226 | fix(waiter): allow a Monitor wait, and read an escaped apos… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #2197 | worktree-home: allow a relative write after an absolute cd … | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #2171 | Env guard: close #2052's walk limits | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #2167 | Read a workflow's path filters toward a wait when their for… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #2160 | Lane hold ends when the pile-up cause is fixed | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #2146 | Notes: two gaps met in lane pr-review-range-check | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #2144 | Refuse a git push that follows a semicolon-joined command | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #2129 | Push report: first-push head, path filters, lagging PR, CI-… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #2099 | Guard: git-after-cd reads an exit only where it runs | draft | no live session on it; draft; no hand-in | park: Held back table: o… |
| #2097 | other-checkout: refuse a python write and an agent's git -C… | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #2083 | conflict-markers asks when a git read cannot run, instead o… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #2061 | Guard tests: a hold drive with no device list is refused | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #2052 | env guard follow-ups: hidden-search walks, wider ag regex r… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #2033 | Guard: drive rule allows a hold drive under the session's o… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #2030 | Keep override's notice tags when config_dir is missing, and… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #2024 | Question form: read a pipe before a newline, $( ) prefixes,… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1971 | Pin the open set of each GitHub MCP write call | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1964 | Merge guard: read every redirect form in the one redirect r… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1938 | Close the pinned-lint review notes | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1935 | Pre-existing guard: fewer false alarms | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1916 | Lane lint runs picked suites of other Linux jobs under thei… | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #1900 | Merge guard rules read every command form; a multi-repo run… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1897 | Lane lint refuses a stale or ambiguous mutant anchor | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1871 | merge --confirm refuses a lane tip with no done review reco… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1863 | Heredoc-keep reader: cases and mutants for its known gaps; … | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1849 | Guard: message-role-scope stops refusing ordinary orchestra… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1848 | Guard merge-roots-cover: a batch runner's --root set equals… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1836 | One YAML quote reader; test local ste-lint and zizmor under… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1811 | Batch runner follow-up: corrected stall cause, background l… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1805 | Guard: a message to a running agent stays inside its role | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1789 | Round 3 only when owed, labelled findings, and no review re… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1784 | Match the page writer label by its id, so the export check … | draft | no live session on it; draft; no hand-in | park: Held back table: o… |
| #1779 | roadmap: bake the record branch on a single-branch clone; f… | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #1771 | Refuse a handoff ruling line with no resolving home | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1760 | Run the lane lint before merge --review-record prints a rec… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1753 | Defer only a lane commit's cite, and read only the head's o… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1733 | Waiting page and roadmap: narrow bars draw one run per stat… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1732 | A builder cannot restore an old copy of a test file through… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1729 | One home each: the ls-remote reader (hooks/git_reads.py) an… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1714 | An agent's shell write into its session's handoff is refused | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1692 | Guard: refuse a drive of a booted phone with no lease of th… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1631 | draft-pr guard: a ready mark asks unless the PR is the inte… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1619 | A note counts its sightings and expires; each batch carries… | draft | no live session on it; draft; no hand-in | mentioned: the expiry wo… |
| #1618 | feedback guard: a bad rolled-out mark still reads the waiti… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1616 | Refuse a compare reply with no files list; run the lane lin… | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #1585 | push report: a failed branch read or an unnamed head reads … | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1561 | PR ledger: merge --reviewed gives each open PR one next act… | draft | no live session on it; draft; no hand-in | park: Held back table: s… |
| #1536 | Report guard: page links in any case or scheme form; more R… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1517 | Session start gives the session a TMPDIR when the container… | draft | no live session on it; draft; no hand-in | park: Holds list 11:59 C… |
| #1432 | One-home check: copies, rewords, child exceptions, paraphra… | draft | no live session on it; draft; no hand-in | close: To close table, p… |
| #1386 | Export check fires for a labelled page writer; promise guar… | draft | no live session on it; draft; no hand-in | park: Held back table: o… |
| #1377 | Give each page decision a blind refuter's case against its … | draft | no live session on it; draft; no hand-in | park: Holds list 11:59 C… |
| #1034 | Plan: one home per kind of prose, and shivpedia | draft | no live session on it; draft; no hand-in | close: To close table, p… |

## Triage 8 (REST-proven stale drafts: close as replaced) (99)

REST read at 00:09 CST Nov 16 (agent, sonnet; pull_request_read on all 99): all 99 are open drafts; none names a merged successor, so none is closed as replaced. 50 name a predecessor ("replaces", "carries", "rebuilds"); none of those predecessors is merged. Parked, one reason for all 99: no live session on it; draft; no hand-in; no successor merged. Eight wait on a base that closed unmerged: #2855 after #2826; #2808 after #2795; #2763 after #2762; #2717 and #2716 after #2715; and stacked on closed #3281, #2938, #2909 (under #3336, #2987, #2912). The coordinator decided at 00:10 CST (not owner-typed): close with the base named. Done at 00:12 CST after a REST read of each base: closed #2855, #2808, #2763, #3336, #2987, #2912 (no branch deleted; one comment each). Skipped #2717 and #2716: their base #2715 has a merged successor, #3214 (merged 2026-11-15 06:59 CST), so they need a retarget to main, not a close. The coordinator decided at 00:14 CST: they stay parked (a retarget needs a lane; none has a live session). Ruling: coordinator-close-drafts-on-closed-bases.

Read again at 14:00 to 14:06 CST Nov 16 (three Explore agents, sonnet, against main 107b66764 plus #3583; triage read the bodies of the PRs it closed). Closed as replaced, one comment each, REST-confirmed: #2661 (by #3138), #2680 (by commits 5bb365c18a and f159b311b4), #2721 (by #3468), #2820 (by #3049, which removed batch build). #2708 also closed, 03:56 CST, closer unknown. Final count: 7 closed before, 4 closed now, 88 open drafts. Of the 88, parked with the coordinator's reason (14:04 CST, not owner-typed, undoable; no live session owns them, none is named in the goal, the consultant's queue or a page item; each leaves the park when a lane, the consultant or the owner names it, resume by name first): 84 not replaced, including #2815 (overlaps merged #3535 but its mechanism is absent) and #2667 (partly covered by #3347; a reviewer reads #3347 first). Unknown, still parked: #2805 (prose only, no replacement found), #2798 (stacked on #2725), #2792 (tests only; main holds similar ask-phase-out tests from #2584), #2725 (main has TEST_CONFIG; its deny cases are unmeasured). A merge after 12:38 CST would not show in this read.

Session: session_013NEJL2kLm8c5qDhosD6Nqb (cs-build:triage cs-repo:shivinate7/claude-settings ui:pinned)

| PR | Title | Draft | Why this owner | Older plan verdict |
|---|---|---|---|---|
| #3336 | Red-main check: each red run since a group's last green nee… | draft | stale draft; REST re-read first | close: Strong 10, close … |
| #3019 | Refuse a lane push while a ready batch PR holds its tip (pu… | draft | stale draft; REST re-read first | close: Strong 10, close … |
| #2991 | Merge lock: read the ls-remote listing from stdout alone; a… | draft | stale draft; REST re-read first | close: Strong 10, close … |
| #2987 | The page card draws the case against the pick (part b) | draft | stale draft; REST re-read first | close: Strong 10, close … |
| #2963 | A past-ruling challenge passes on a new fact the ruling lef… | draft | stale draft; REST re-read first | close: Strong 10, close … |
| #2928 | One override route, part 2: the Opus keyword is gated, a no… | draft | stale draft; REST re-read first | close: Closed in Third p… |
| #2912 | Batch Build and Drop entry: also allow --blame --run, --on,… | draft | stale draft; REST re-read first | close: Strong 10, close … |
| #2910 | Log each past-ruling and judge model run (ms, chars, outcom… | draft | stale draft; REST re-read first | close: Closed in Third p… |
| #2901 | Reviewer file: the express pass skips the ruling-record rou… | draft | stale draft; REST re-read first | close: Closed in Third p… |
| #2867 | Departs-from check accepts a sentence-form line with no das… | draft | stale draft; REST re-read first | close: Closed in Third p… |
| #2855 | Pre-existing check: ref clause after a pronoun, split claim… | draft | stale draft; REST re-read first | close: Closed in Third p… |
| #2846 | ci_wake: a draft run never reads green | draft | stale draft; REST re-read first | close: Closed in Third p… |
| #2841 | The hook judge takes ANTHROPIC_API_KEY when no setup token … | draft | stale draft; REST re-read first | close: Closed in Third p… |
| #2831 | Frozen-path guard reads sed operands (flag clusters, w FILE… | draft | stale draft; REST re-read first | close: Closed in Third p… |
| #2827 | The writer's wake runs the open-asks end check on a fresh a… | draft | stale draft; REST re-read first | close: Closed in Third p… |
| #2824 | guard: end an unquoted heredoc body only on the end line ba… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2821 | Add the Keep sentence to roles-brief-contents | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2820 | A batch build keeps its log under state/ | draft | stale draft; REST re-read first | close: To close table, p… |
| #2815 | Lone lane merges its own PR in claude-settings (G2, G10) | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2813 | Guard reads a force push inside python -c bodies and a Powe… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2812 | Builders keep earlier lane work: builder.md paragraph and b… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2811 | File review round 3 findings as notes and two debts | draft | stale draft; REST re-read first | close: To close table, p… |
| #2808 | Keep a stalled job's log for 7 days | draft | stale draft; REST re-read first | wave (rebuild/rebase): t… |
| #2806 | docs: file low review findings from lane fan-code-handoffs … | draft | stale draft; REST re-read first | close: To close table, p… |
| #2805 | Stale cites: design notes and small debts (step stale-cites… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2804 | Stale cites: decision records (step stale-cites-tree-clean) | draft | stale draft; REST re-read first | close: To close table, p… |
| #2803 | Stale cites: plans folder (step stale-cites-tree-clean) | draft | stale draft; REST re-read first | close: To close table, p… |
| #2802 | Two wording fixes in the waiting-page SKILL.md (step waitin… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2799 | notes-name-their-fix: fixes stacked on #2735 | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2798 | A builder cannot edit an .xctestplan (step builder-xctestpl… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2797 | The past-ruling judge carries rules S1 to S4 and the record… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2792 | Pin the waiting page's routed lines and Mark read (step ask… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2791 | A new branch name never holds the word "git", and the guard… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2790 | Glossary renames in text: review log and feedback log (G4) | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2789 | other-checkout: a quoted python body that only quotes a pat… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2788 | Ruling-skip check: a pick taken under a ruling cites it, an… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2786 | Step replay-profile-parts: the load hook decides, static re… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2782 | Commit check: a ruling cite names its home and time | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2780 | Refuse a reviewer brief that holds a report or a prior verd… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2779 | Guard records-page-ready reads the repo the pull request is… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2777 | Notes: four open review findings from the prose-guard-2 lan… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2775 | The guard and sim-lease read machine load from one shared d… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2774 | Builder test-edit check: shell writes in folder roots, glob… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2772 | Debt windows-shards-outgrow-caps: merge cap 75, current sha… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2769 | Decision watch finds the transcript by session id when the … | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2768 | An archive refused for an out-of-scope repo names the repo … | draft | stale draft; REST re-read first | close: To close table, p… |
| #2767 | Status block lists each outbox ruling and whether its home … | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2766 | Stamp refuses a pending cite in a file it does not scan, an… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2763 | Silent-undo check reads the PR body in CI and the lane lint… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2759 | plain-push-asks cites its source as unverified, not page it… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2758 | One-worktree-per-branch check also refuses update-ref and b… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2757 | Two PR checks: a record's first cite has a gloss; a debt ke… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2755 | Guard: a lane session start whose model differs from the la… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2753 | PowerShell write detection: argument slots, groups, cp, lis… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2752 | The map's readers see aliased imports, shell strings and te… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2751 | A lane's plain acknowledgement is not an answer to its ques… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2750 | Draft-PR guard: heredoc bodies read as shell only when run,… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2749 | Lane lints wait for a CPU slot, so parallel lints finish (s… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2747 | Batch runner names each handed-over lane left out of a batc… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2744 | PowerShell write detection: comma lists, alias positions, s… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2742 | Waiting page: an option picture fills its card's width (car… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2740 | Past-ruling judge runs before an owner-question send and al… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2736 | merge --reviewed names each draft over 12 h old with a miss… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2735 | A note names its fix (carried forward from #1516) | draft | stale draft; REST re-read first | close: To close table, p… |
| #2734 | Silent-undo check: a lane commit that puts back its own ear… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2732 | Notes: three limits of the waiting-page guards (layout fail… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2728 | Model calls that cannot authenticate are no longer quiet (c… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2727 | A docs-only Kind claim is refused when the diff files a dec… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2726 | question-checked-with-repo takes a role or lane slug, never… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2725 | A builder cannot edit test config (carry of #2103) | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2724 | Force-push guard: remedy names the sha lease form | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2721 | Export the waiting page's receipts collection, from one lis… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2717 | bin/shoot: touchWidths config key (carries #2154) | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2716 | bin/shoot: stitched touch shots keep the pinned size (carri… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2709 | Lane brief check: Coordinator, Triage and Batch runner ids … | draft | stale draft; REST re-read first | close: Strong 10, close … |
| #2708 | check_layout: keep the two PR template copies byte-equal (s… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2704 | A page task's route cite must name a route row that covers … | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2702 | waiting-page SKILL.md: generate the item field table, state… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2699 | waiting-page: list asks with no reply at wake (carry of #22… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2697 | Stall watch: list an agent stuck in one Bash call past 900 … | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2695 | Waiting page: an answer names its session, and the page-not… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2693 | Guard: refuse a brief that tells a read-only agent to write… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2692 | Guard: an agent's commit names its own model in Co-Authored… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2691 | Guard: refuse a relative ../ write that leaves the agent's … | draft | stale draft; REST re-read first | close: To close table, p… |
| #2689 | Merge lock: take it by leased push on every host; delete Gh… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2681 | Read a page task with options for its Departs from line | draft | stale draft; REST re-read first | close: To close table, p… |
| #2680 | Stall watch: resolve a log after cd, count child CPU time a… | draft | stale draft; REST re-read first | close: Also (coordinator… |
| #2678 | Delete the branches the Oct 30 grant allows, from GitHub Ac… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2677 | Export check finds the real page writer; report guard refus… | draft | stale draft; REST re-read first | close: To close table, p… |
| #2676 | A lane brief's Done check is read blind against the step's … | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2675 | Known-defect replay: failed-install exposure by load hook, … | draft | stale draft; REST re-read first | close: To close table, p… |
| #2674 | Record the lane inflow hold (carries #1768) | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2672 | Decision watch finds the transcript by session id when the … | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2667 | merge --reviewed lists close-as-replaced, close-as-carried … | draft | stale draft; REST re-read first | close: To close table, p… |
| #2666 | A typed override takes even after the app's status block (c… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2665 | Report guard refuses an Input Needed item whose page item i… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2664 | Check a builder's reported files are in the pushed head bef… | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2663 | Record the usage brake ruling (R43) | draft | stale draft; REST re-read first | close: Closed in Triage … |
| #2661 | project-ops: the roster lives on the record branch, triage … | draft | stale draft; REST re-read first | close: Closed in Triage … |

## Runner 10 (merge candidates) (81)

Session: session_013NEJL2f1YCYsvLdpFqtWP3 (cs-build:batch-runner cs-repo:shivinate7/claude-settings ui:pinned)

| PR | Title | Draft | Why this owner | Older plan verdict |
|---|---|---|---|---|
| #3571 | Point page-writer at the new triage session | ready | ready for review (lane lint and record at head: u… | none |
| #3559 | Flag a Markdown file that cites a ruling and not the later … | draft | runner 10 section | close: #3505 and #3507 c… |
| #3554 | Debt: unknown-read lint check flake | draft | runner 10 section | close: #3505 and #3507 c… |
| #3552 | Lane lint merges main into a lane head behind it and pushes… | draft | runner 10 section | merge: Queued for lint: … |
| #3548 | Answered claims match the waiting page | ready | runner 10 section | merge: Queued for lint: … |
| #3543 | Waiting page: show each open decision's recommendation and … | draft | runner 10 section | merge: not read by triag… |
| #3538 | Back off a failed cloud reinstall; record the ls-remote cos… | draft | runner 10 section | merge: Lint PASS, unmark… |
| #3537 | Require a ruling ref in supersedes to name an exact older r… | draft | runner 10 section | merge: Lint PASS, unmark… |
| #3535 | A lane merges its own claude-settings PR | ready | runner 10 section | merge: rewritten from th… |
| #3530 | Export keeps all six waiting collections append-only | draft | runner 10 section | merge: Runner 10's queue… |
| #3529 | Match a cloud-label page writer in the waiting export check | draft | runner 10 section | merge: Runner 10's queue… |
| #3528 | Lost-work rows and ledger on main's per-lane merge | draft | runner 10 section | close: replaces #3516), … |
| #3523 | Stale-page remedy and ready-mark docs name merge --ready fi… | draft | runner 10 section | merge: Lint PASS, unmark… |
| #3520 | combine-train: --from-rest reads the queue from GitHub (ste… | draft | runner 10 section | close: replaces #3516), … |
| #3514 | Records: a claude-settings lane merges its own PR (replaces… | ready | runner 10 section | close: lanes-merge-own-p… |
| #3513 | Session start: say coordinator or lane, pin it to session-t… | draft | runner 10 section | merge: order #3482, #346… |
| #3497 | Own-lock walk: reject a recycled holder pid | draft | runner 10 section | merge: order #3482, #346… |
| #3490 | Refuse a push to a PR branch while its newest review log is… | draft | runner 10 section | merge: #3490 stays on ha… |
| #3482 | sim-lease, sim-test: a reuse takes a lease, two Duos at onc… | draft | runner 10 section | merge: order #3482, #346… |
| #3478 | A --base-red-ok merge must be the exact revert of the break… | draft | runner 10 section | merge: #3478 (base-red-o… |
| #3474 | Let a standing session merge its own small edit (merge-role… | draft | runner 10 section | merge: rewritten from th… |
| #3469 | The waiting-page writer prints the page link in chat (skill… | draft | runner 10 section | merge: Runner 10's queue… |
| #3468 | Export holds every receipt (sixth waiting collection, appen… | draft | runner 10 section | merge: Runner 10's queue… |
| #3467 | A merge that changes the page code says to republish the pa… | draft | runner 10 section | merge: Runner 10's queue… |
| #3457 | waiting-page: item number hover says it is the stable answe… | draft | runner 10 section | merge: Runner 10's queue… |
| #3449 | Writer lists comment threads awaiting its reply at each wake | draft | runner 10 section | merge: Runner 10's queue… |
| #3421 | Root clause roles-review-cap-three: done at a passing fix c… | draft | runner 10 section | close: Also (coordinator… |
| #3419 | push-skip text says child repos are ruled to follow the sta… | draft | runner 10 section | close: its lane squashed… |
| #3368 | Combine clear set 3: six lane PRs merged onto main bedbce7b… | draft | runner 10 section | merge: sent to runner 10… |
| #3359 | Keep the batch runner's state in one file on the record bra… | draft | runner 10 section | merge: Runner 10 files n… |
| #3358 | docs: back or cut the unbacked claims the prose judge named… | draft | runner 10 section | merge: - Older queue nam… |
| #3357 | Rolling combine train: pre-flight step while a batch's CI r… | draft | runner 10 section | merge: - Older queue nam… (replacement #3576 merged 06:04:25 CST Nov 16, alone, commit 115cbad47, REST read by triage 06:05 CST; #3357 close as replaced is runner 10's, REST proof owed) |
| #3354 | Apply six signed reply-style changes (29 rules to 25) | draft | runner 10 section | merge: - Older queue nam… |
| #3350 | Print the PR's own-run suite count when main is red or --ba… | draft | runner 10 section | merge: - Older queue nam… |
| #3346 | Warn on a ready mark with no PR subscription | draft | runner 10 section | merge: - Older queue nam… |
| #3341 | Batch runner standing duty: rolling combine train | draft | runner 10 section | merge: runner 10 set #33… |
| #3333 | Combine d2: 2 reviewed PRs (batch) | draft | its own live session | park: Holds list 11:59 C… |
| #3332 | Combine d1: 33 reviewed PRs (batch) | draft | its own live session | park: Holds list 11:59 C… |
| #3331 | Combine c1: 27 reviewed PRs (batch) | draft | its own live session | park: Holds list 11:59 C… |
| #3325 | Refuse a page task item that carries choice options (step t… | draft | runner 10 section | merge: - Older queue nam… |
| #3322 | State f of the lost-work check skips a named record branch | draft | runner 10 section | live: owned by lane lost-work-sweep, merges after #3528 (lane's word, 17:16 CST Nov 16: #3322 holds 5 own commits #3528 lacks; the lane merges origin/lost-work-rows into it once, then hands runner 10 the head) |
| #3312 | Decision merge-needs-current-base: a red main resumes when … | draft | runner 10 section | close: Also (coordinator… |
| #3304 | Rule git-red-main-reverts: merges resume when the revert me… | draft | runner 10 section | close: Also (coordinator… |
| #3299 | ci-hygiene step 8: recipe for a combined PR built by hand | draft | runner 10 section | close: left out by name:… |
| #3294 | CI alarm: a failed run a live revert on the branch clears o… | draft | runner 10 section | merge: Dry run (runner 1… |
| #3287 | check-tail reads any filter, a glued &, and merge flag forms | draft | its own live session | none |
| #3274 | CLAUDE.md: a PR merges alone and may combine several review… | draft | runner 10 section | close: left out by name:… |
| #3268 | Decision: merges resume when the revert merges (745 b, 746 … | draft | runner 10 section | merge: Dry run (runner 1… |
| #3264 | Close a page item in one batch: receipt, close, answer dele… | draft | runner 10 section | merge: triage read no la… |
| #3256 | Parse each state file a Bash or Edit call names (step state… | draft | runner 10 section | close: left out by name:… |
| #3236 | Lane : a lane never opens the question box or a trust card … | draft | runner 10 section | close: left out by name:… |
| #3227 | Guard: a progress claim cites a named live read (progress-c… | draft | runner 10 section | close: left out by name:… |
| #3222 | Run the lane lint before merge --review-record prints a rec… | draft | runner 10 section | close: left out by name:… |
| #3212 | Decision: git is the page's home, the database its live vie… | draft | runner 10 section | merge: - #3212 (git-home… |
| #3210 | Guard: read default-word config-dir forms and getcwd joins … | draft | runner 10 section | close: left out by name:… |
| #3206 | The past-ruling judge runs on owner-question sends and page… | draft | runner 10 section | merge: - Older queue nam… |
| #3204 | fix(waiter): read an escaped apostrophe in an interpreter h… | draft | runner 10 section | merge: Dry run (runner 1… |
| #3201 | Widening mark: per-repo exceptions only, worded as a guidel… | draft | runner 10 section | close: left out by name:… |
| #3176 | Carry the feedback guard and bad rolled-out mark stack onto… | draft | runner 10 section | merge: - Older queue nam… |
| #3170 | Batch review lists lost work: states a-f and the lost-PR le… | draft | runner 10 section | close: replaces #3148, #… |
| #3148 | A handed-in lane PR cannot fall off the batch (handin-canno… | draft | runner 10 section | close: replaces #3148, #… |
| #3126 | scratchpad-cp-keeps-writer: a cp of another agent's file ke… | draft | runner 10 section | park: List: main's build… |
| #3097 | Allow the merge tool with --confirm, --head and --base-red-… | ready | ready for review (lane lint and record at head: u… | park: Runner 10 hold lis… |
| #3011 | Simulator tool needs the caller's own lease (simulator-devi… | draft | runner 10 section | merge: sent to runner 10… |
| #2984 | Guard rule protected-path: a repo lists paths a session may… | draft | runner 10 section | merge: triage read no la… |
| #2954 | Builder bash test-write check (PostToolUse judge_shell_writ… | draft | its own live session | park: - Held, held in th… |
| #2922 | Archive refusals steer a lane to batch get_session calls | draft | runner 10 section | merge: order #2917, then… |
| #2919 | Page usage counters | draft | its own live session | park: - Held, branch sta… |
| #2917 | A lane may push its own handoff file to the record branch | draft | runner 10 section | merge: order #2917, then… |
| #2908 | Delete the 200-path cap in the pushed-copy proof (census ro… | draft | its own live session | close: Closed in Third p… |
| #2906 | Waiting page sorting | draft | runner 10 section | merge: triage read no la… |
| #2904 | Owner health tab: new check, CI step and page tab | draft | runner 10 section | merge: triage read no la… |
| #2884 | Retire the rule-audit count pins and the 8-word reason floo… | draft | its own live session | close: Closed in Third p… |
| #2861 | State why four hook bounds stay (census rows H4, H6, H7, H8) | draft | its own live session | close: Closed in Third p… |
| #2853 | Note: a merge-tool test needs pipx on the host | draft | its own live session | close: Closed in Third p… |
| #2848 | Archiving scope: whoever starts a session archives it; a la… | draft | runner 10 section | merge: order #2917, then… |
| #2837 | A stopped batch build pushes nothing (step batch-build-stop… | draft | its own live session | park: - Held, branch sta… |
| #2817 | merge --idle-lanes flags a lane whose handoff is not on the… | draft | runner 10 section | merge: order #2917, then… |
| #2778 | Waiting page: reply to Claude's reply on an item (carries #… | draft | runner 10 section | merge: triage read no la… |
| #2723 | PowerShell write detection: env -S, quoted text, copy sourc… | draft | runner 10 section | merge: Dry run (runner 1… |
| #2701 | A solo session with no parent and no cs-build tag may take … | draft | runner 10 section | merge: order #3482, #346… |

## Lane session session_013NEJKz5AWFJhGvmCUoi6wQ (11)

Session: session_013NEJKz5AWFJhGvmCUoi6wQ (cs-build:consultant cs-repo:shivinate7/claude-settings cs-topic:retrospective ui:pinned)

| PR | Title | Draft | Why this owner | Older plan verdict |
|---|---|---|---|---|
| #3568 | Pin the wider records-only CI skip: every job but the decis… | draft | its own live session | none |
| #3566 | Test the octopus-push guard on a merge the remote already h… | draft | its own live session | mentioned: #3566 lints o… |
| #3565 | Branch protection requires no status check (own-all-jobs-pa… | draft | its own live session | none |
| #3562 | Merge a lint-passed head without waiting for its CI run | draft | its own live session | none |
| #3561 | Refuse duplicate test section numbers | draft | its own live session | none |
| #3560 | Sessions get the roster at start | draft | its own live session | none |
| #3558 | Waiter and stall watch agree on a planned wait | draft | its own live session | none |
| #3557 | A fix check may chain from a descendant head | draft | its own live session | none |
| #3553 | A can't claim needs a probe | draft | its own live session | none |
| #3549 | Lane start in one pass | draft | its own live session | none |
| #3547 | Artifact links listed per account | draft | its own live session | none |

## Coordinator (decides per PR: resume, hand over, or park) (5)

Session: session_013NEJL1gw6EdrSyvHkTUEx6 (cs-build:coordinator cs-repo:shivinate7/claude-settings ui:pinned)

| PR | Title | Draft | Why this owner | Older plan verdict |
|---|---|---|---|---|
| #3569 | Freeze the old notes file; one file per new note | draft | resume by name when its stack head merges | none |
| #3536 | Saved comment: a cut owner ends in an ellipsis | draft | its own live session | none |
| #3228 | Question form: refuse bash-only forms in PowerShell blocks;… | closed | closed as replaced by #3583 (REST 03:17 CST Nov 16: #3228 closed, merged false, closed 09:05:33Z; #3583 open draft at a6d5945140, body "Replaces #3228"; #3583 carried to merge, handed to runner 10) | none |
| #2862 | Stall watch: never end a waiter or a lone pause (stacked on… | draft | PARKED (coordinator relay, stale-drafts lane): open; base #2680 is open and dirty; no replacing PR; last update Nov 13 17:54 CST | close: Closed in Third p… |
| #2771 | Resume guard: a finished agent whose worktree is gone is re… | draft | PARKED (coordinator relay, stale-drafts lane): open; replacement #3248 is open and based on guard-tables-per-section, contents not compared, so superseded is not proven | close: Closed in Triage … |

## Lane session session_013NEJL3tMVa6d437aatxvYY (1)

Session: session_013NEJL3tMVa6d437aatxvYY (cs-build:lane cs-repo:shivinate7/claude-settings cs-step:stale-row-reads-rest)

| PR | Title | Draft | Why this owner | Older plan verdict |
|---|---|---|---|---|
| #3570 | Stale-draft row reads open PRs from GitHub REST and branch … | draft | its own live session | none |

## Triage 9 reads of the four unknown drafts (REST, 16:36 CST Nov 16)

All four are open drafts with a stale base and no activity since Nov 12-13. No replacement PR found yet; not searched.

- #2725: carry of #2103, builder cannot edit test config. Head 8d53a3a50. Open: owner item 437 on the same rule. #2798 stacks on it.
- #2798: builder cannot edit an .xctestplan. Head 566cf5369. Needs #2725 to merge first. Parked on #2725.
- #2792: test-only pins for ask-phase-out; build already on main. Head 4b460f27f. No guard change. Parked: live step, no owner session named.
- #2805: prose-only stale-cites clean-up, one commit. Head ee9ad636c. Parked: lane lint passed at that head; no live lane named.

## Triage 9 REST reads of the other parked drafts (read-only agent, sonnet, 16:43 CST Nov 16)

95 PRs read on REST: 84 open drafts, 11 closed. 0 unreadable. 0 replaced (searched the last 800 main commits only; older history not searched). Class by REST base branch and updated time, taken at face value. 37 open PRs share one update at Nov 13 12:01-12:02 CST, cause unknown.

- STACKED, 11 (REST base is not main): #2928, #2867, #2841, #2824, #2821, #2812, #2799, #2774, #2757, #2753, #2744. Parked until the parent merges.
- LIVE, 4 (updated Nov 15 or later): #2963, #2751, #2742, #2681. These need their owning session named; none read.
- STALE-BASE, 69 (updated Nov 13 or earlier, base main): #3019, #2991, #2910, #2901, #2846, #2831, #2827, #2815, #2813, #2811, #2806, #2804, #2803, #2802, #2797, #2791, #2790, #2789, #2788, #2786, #2782, #2780, #2779, #2777, #2775, #2772, #2769, #2768, #2767, #2766, #2759, #2758, #2755, #2752, #2750, #2749, #2747, #2740, #2736, #2735, #2734, #2732, #2728, #2727, #2726, #2724, #2717, #2716, #2709, #2704, #2702, #2699, #2697, #2695, #2693, #2692, #2691, #2689, #2678, #2677, #2676, #2675, #2674, #2672, #2667, #2666, #2665, #2664, #2663.
- Closed, 11 (moot): #3336, #2987, #2912, #2855, #2808, #2763 (Nov 16 00:12 CST); #2721, #2820, #2680, #2661 (Nov 16 14:04 CST); #2708 (Nov 16 03:56 CST, closer unknown).
- Plan versus REST: the plan puts #2717 and #2716 on base #2715, but REST base is main for both.
