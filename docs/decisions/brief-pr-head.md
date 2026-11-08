# A brief's PR and branch pair must name the PR's head ref

## The ruling

Rule `brief-pr-head` in `hooks/guard_merge.py` refuses a brief that pairs PR #N with a branch other than #N's head ref. Its home is `brief_pr_head_hit`, called from `hooks/guard.py` beside rule `brief-claim-has-probe` (decision `brief-claim-has-probe`). It was filed by roadmap step `brief-pr-branch-is-head-ref`.

- The mistake (lane notes-fix-large-3): reviewers and a Plan agent were briefed with branch `mcp-tools-in-guard-matcher`, a branch guessed from the lane name. The head ref was `mcp-safety-gaps`.
- The harm: two false review FAILs, a false debt and a duplicate step followed.
- The rule: a brief to any role that pairs PR #N with a branch other than #N's head ref is refused. A brief is an Agent or Task `prompt`, a remote send_message `message`, or a Workflow `agent()` prompt that reads as a literal. Backticks, `origin/` and `refs/heads/` are dropped before the match. The refusal names the shape and the read command, never a branch.
- A failed read, or a bare #N in a checkout with no readable repo, refuses as unknown. A 404 on the PR passes, since the number is no pull request.
- Cost: one `gh api` read of the head per distinct (repo, N) in a call, two at most for a short-name guess such as `q_max #12`. No pairing, no read. The repo comes from the checkout's files, so no git starts. The merge tool's `Host.gh` retries a network or rate error, so one read can take more calls.
- An override of another rule still meets this check first (`set_lift_check` in `hooks/guard_core.py`).
- Grammar, misses and the known false alarm: the `hooks/guard.py` header row, and `docs/debts/notes.md` (`brief-pr-head-diff-with`, `brief-pr-head-grammar-misses`).
- Protected by the `brief-pr-head:` cases in `hooks/test_guard.py`.

Kind: process
Plan: docs/decisions/brief-pr-head.md#the-ruling (all)
Home: hooks/guard_merge.py
