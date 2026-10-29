# c194 cloud refusal goes to a session on the owner's computer

- Draft PR #811, branch c194-cloud-refusal-to-pc, head 347e8aa7.
- Guard rule task-names-check: a waiting-page task needs a "Why yours:" line in context. Decision task-names-its-check.
- Review: round 1 FAIL (str_replace bypass, bare line), fixed; round 2 PASS. Round-2 notes filed in docs/debts/notes.md.
- Gates on head: ste-changed PASS; check_silent_undo --strict PASS; ci-job checks --lint PASS. test_guard PASS on bd0a759f (head adds notes only).
- Overlap: c190 (not merged) also edits skills/waiting-page/SKILL.md; this lane added lines only. The second to land merges.
- State: done, waiting on the coordinator's batch.
