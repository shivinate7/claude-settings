# Brief: c133, a report rewritten after a missing-report block is still checked

Repo: shivinate7/claude-settings, from main 43d9af20. One lane: builder (sonnet), then reviewer (sonnet). This changes a check's verdict, so it gets up to three review rounds and, after round 3, the net-value test.

## Task
lint/report_gate.py stays quiet whenever stop_hook_active is set (see its main and the comment on the correction tail). So the report a session writes after a missing-report block is never checked for model names (reports-done-names-models) or the `Unstarted:` line (reports-name-unstarted-items).
On a stop_hook_active run whose previous block was the missing-report block, run those two checks once on the rewrite. Keep one correction tail and no loop: a second block on the same rewrite never happens. Every other stop_hook_active run stays quiet as today.

## Failure classes
- A loop: the gate blocks the rewrite, then blocks the rewrite of the rewrite.
- A false alarm on a rewrite that names its models and Unstarted line correctly.

## Check that proves it done
Cases in the report gate's tests: red on main (a rewrite after a missing-report block that drops the Unstarted line passes), green on the branch; a second rewrite stays quiet; a correct rewrite passes. `python3 bin/ci-job gates --lint --base origin/main` and `bin/ste-changed origin/main` pass (the silent-undo gitlink fixture is red on main 43d9af2 too; batch #700 fixes it).

## Report
At most 12 lines: PR (draft), head, red run, green run, each review round's verdict. Send the green, reviewed head to the build advisor thread "Advise the claude-settings build (9)". Do not rebase onto main and do not merge.
