# Coordinator picks filed by triage 8, Nov 16 (his words relayed; none owner-typed; each undoable)

Source: coordinator session_013NEJL1gw6EdrSyvHkTUEx6 by send_message. Triage verified none of the facts in them unless a line says so.

| Time CST | Pick | Home |
|---|---|---|
| 01:47 | Close #3357 as "Replaced by #3576"; runner 10 closes it, then lints #3576. Banchi #1107 merged 01:44 CST (d56b512e8), per runner 12. | Step batch-runner-rolling-train (note, f1dfc1bd27) |
| 01:53 | #3579 (replaces #2708): keep the byte-equal rule, never exempt a repo-only line (decision uniform-over-variants); put template line 18 in both copies. | Draft PR #3579, head 4174ac375c; fix check passed |
| 01:53 | #3581 (replaces #2751): let past-tense claims look back across an answer; add tests for the retry case and the bare claim; drop the unsourced "2026-11-07 14:12 CST" cite; remove the resolved notes line. | Draft PR #3581, head b8f25fd656; tests and fix check pending |
| 02:00 | (consultant) debt fix-check-refuses-review-prose: the refusal names the prose; the parser route is not taken. | Debt in draft PR #3577, head ff503cb6d7 |
| 02:01 | Runner 12 decides each of its 27 other child-repo PRs under its standing merge authority; closes only on a REST-named replacement; parks with one reason line; ios-adblock #169 and any close with no replacement wait for the owner; one table of at most 25 lines to the coordinator. | None needed unless the table shows an owner close |
| 02:06 | #3474 at 37da28c16: lane lint reads UNKNOWN because the `touched` job of lane-touched-tests skipped on the ready head (run 43828189510, REST 02:05 CST, runner 10's lint log). The lane converts #3474 to draft so a draft run runs `touched`; runner 10 re-lints, marks ready on PASS, merges on green; no `--lint-unknown-ok`. Possible debt (unmeasured): a ready head with no draft run reads UNKNOWN for lane lint; note it on step lint-step-hang if it recurs. | Draft PR #3474; step lint-step-hang |
| 02:02 | #3474 lane lint fails at 555f75f14 (silent-undo, merge 607ad0fff replaced lines of #3535 in hooks/guard.py, merge/merge.py, merge/test_merge.py): the lane checks each line by diff, pushes one commit with three `Drops-lines:` trailers, posts the record and fix-check chain, re-lints, hands runner 10 the new head. A truly lost line returns to the coordinator. Still owed after merge: consultant in STANDING_HOLDERS, close of item 867. | Draft PR #3474; step merge-role-proof-follows-b |
