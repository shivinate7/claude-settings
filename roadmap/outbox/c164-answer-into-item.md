# c164-answer-into-item (a waiting-page answer is written into its item)

- PR #759 (draft), head 076de1f, branch c164-answer-into-item from main 646d23c.
- Gates on 076de1f: ci-job gates --lint --base origin/main PASS; check_silent_undo --strict rc 0; test_reply_judge PASS; page.test.mjs 118/0.
- Red first: test_reply_judge 2 of 51 cases red on main; page.test new case red on main.
- Review: round 1 APPROVE with two fixes (judge example names the waiting-page thread, plus a PR-review carve-out; SKILL.md points to Route-and-close steps 3/4 instead of restating them). Round 2 APPROVE. Builder opus, reviewers opus then sonnet.
- Note, not fixed (predates this lane): a non-writer owner that rewrites an item may republish a design, which only the writer should do (SKILL.md "The writer").
- No conflict with #753: its SKILL.md hunks are at lines 40/105/207/218, this one at 146-156.
- Status: ready for batch. Nothing open.
