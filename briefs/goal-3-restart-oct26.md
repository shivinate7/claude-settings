# Goal 3, fresh session: add-on to the handoff

Paste this below the `/goal` block from the old session. Written by the advisor, Oct 26, against
claude-settings main 149f4bc5 (#574). It changes three things in briefs/cleanup-goal-3-oct25.md;
everything else stands.

1. Batch 1, lane 2 (the stop guard on live tasks, branch stop-blocks-live-tasks) gets one more
   try with an exit line. The first try would have blocked 248 of 1,787 real agent stops by
   mistake. Build the new cases from those real transcript shapes, red then green. Then replay
   the same 1,787 stops: ship only if it blocks none of them by mistake and still catches the
   advisor's probe (a subagent that leaves a Monitor and a background Bash running). If it
   misses that bar, drop the lane, keep the agent-file sentence from #574, and leave a note on
   the c43 debt. A guard that cries wolf is spent (verification-cry-wolf-guard-is-spent).
2. Lanes ready at the same time join one integration PR. Oct 25 merged #575, #576 and #574 as
   three lone PRs within 20 minutes; each merge made the next branch out of date, so CI ran
   again (46 of #575's 46 minutes were CI). This follows git-integration-branch-merge. The
   advisor's goal-3 brief said "each batch is its own integration PR"; that line is withdrawn.
3. Batch 4 (kill guard, c27) runs in its own session on the Mac, beside this one. On Windows,
   skip it; do not wait for it.

Batch 3: the owner did not see whether the Oct 25 18:05 question alerted them (not watching).
Rerun the check on purpose: tell the owner in your first report that a test question comes in
5 minutes, with the app minimized and the phone nearby, then ask one AskUserQuestion test. The
owner says what fired: desktop banner, phone push, or nothing. Park batch 3 only until then.
