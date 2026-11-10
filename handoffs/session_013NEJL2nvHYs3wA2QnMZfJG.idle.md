# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL2nvHYs3wA2QnMZfJG

## Reply at 2026-11-10T17:27:32Z UTC

IDLE (B). Handoff, lane builder-brief-code-check (step builder-brief-names-code-check):
- Goal: a guard rule, `builder-brief-code-check`, that refuses a builder brief whose done check names no code check (`merge --lane-lint`, `ci-job checks --lint` or `code_check.py`), in a repo whose checks.yml defines a `checks` job.
- PR #2204, branch builder-brief-code-check-2, head 64011deed1b03dec0760a587a8b2e3213c0fb5fc, open. It is handed to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) with `Merge after: #2118, #2109`.
- State: reviewed rounds 1-3 (haiku FAIL, then sonnet PASS, sonnet PASS), net value positive. The review record is posted on the PR, and `merge --lane-lint 2204` gave PASS. It replaces #2192, which is closed: the same tree minus a Red-run trailer.
- Files: hooks/guard.py (builder_code_check_hit, step 9f), hooks/test_guard.py (29 builder-code-check: cases), hooks/mutate_guard.py (23 mutants), docs/decisions/builder-brief-code-check.md, docs/debts/builder-done-label-blank-line.md, docs/debts/notes.md.
- Left:
  - The runner merges #2204.
  - Triage files a step for debt builder-done-label-blank-line (a false alarm on a done-check label followed by a blank line; one fix try was reverted after its fix check found two fence bypasses).
  - Triage re-points steps brief-builder-no-test-grant and builder-runs-comment-check from hooks/agent_brief.py to hooks/guard.py.
  - Branches builder-brief-code-check and builder-brief-code-check-2 are on origin. Nothing is unpushed.

