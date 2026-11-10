# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKzk1MsAcMP53yRaVu1

## Reply at 2026-11-10T17:24:05Z UTC

IDLE (B)
Goal: step lane-lint-unshallow. `merge --lane-lint` on a shallow cloud clone read the silent-undo check as UNKNOWN, and --strict turned that into FAIL (incident #1585 at 96f4fcc4f). Fix: fetch the full history first, or stop as unknown.
State: all 3 PRs are open, unmerged and handed to batch runner 8. Merge them in this order, each after the one before:
- #1818 (lane lint unshallows a shallow clone first), branch lane-lint-unshallow, head 7f90f9168. Lane lint PASS. Review round 2 PASS.
- #1831 (fetch bound at 600 s, stop text names both causes, GIT_TRACE reads), branch lane-lint-unshallow-2, head 936092ed5, Merge after: #1818. Lane lint PASS. Review round 3 PASS, net value positive.
- #1857 (git_env() drops trace paths that name stdout or stderr, or sit in an unwritable folder), branch lane-lint-unshallow-3, head 2fe2e0320, Merge after: #1831. Lane lint PASS. Review round 1 FAIL, then the fixes got a fix check.
Files: merge/merge.py (unshallow_for_lint, git_env, STD_STREAMS, repo_root, UNSHALLOW_SECONDS), merge/test_lane_lint.py, merge/test_merge.py (4 merge.sh stubs take **kw), testing/shallow_clone.py (origin()), docs/decisions/lanes-run-no-full-ci-job.md, docs/debts/notes.md.
Left: the merges, by the runner. CI is the first full-suite run of #1857's last 7-line git_env change. Triage step: guard test-author-scope's TEST_DIRS lacks testing/ (a possible false alarm). Nothing is unpushed.

