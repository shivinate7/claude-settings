# Goal 3, fresh session: the whole /goal prompt

Paste the block below, whole, into one fresh claude-settings session. Written by the advisor, Oct 26,
against claude-settings main 149f4bc5 (#574).

```
/goal Complete this end to end. Read C:\Users\ShivamSemwal\.claude\handoffs\goal-cleanup-3.md, then the prior session's handoff C:\Users\ShivamSemwal\.claude\handoffs\bab053f2-9550-436d-b482-c8e80dd26b1b.md, then git fetch and gh pr list --state open. Continue from its "Next steps", with these changes from the advisor (Oct 26, main 149f4bc5):

1. Batch 1, lane 2 (stop guard on live tasks, branch stop-blocks-live-tasks): one more try. The first try would have blocked 248 of 1,787 real agent stops by mistake. Build new cases from those real transcript shapes, red then green. Then replay the same 1,787 stops. Ship only if it blocks none by mistake and still catches a subagent that leaves a Monitor and a background Bash running. Otherwise drop the lane, keep the agent-file sentence from #574, and note it on the c43 debt.
2. Lanes ready at the same time join one integration PR (git-integration-branch-merge). Three lone PRs on Oct 25 each re-ran CI after the one before merged. The goal file's line "each batch is its own integration PR" is withdrawn.
3. Batch 4 (kill guard) runs in its own Mac session. On Windows, skip it; do not wait.
4. Batch 3: the owner did not see whether the Oct 25 18:05 question alerted them. In your first report, say a test question comes in 5 minutes, then ask one AskUserQuestion test. The owner says what fired: desktop banner, phone push, or nothing. Park only batch 3 until then.
```
