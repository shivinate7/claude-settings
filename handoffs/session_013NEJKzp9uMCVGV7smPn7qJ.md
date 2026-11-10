# push-calls-substitution-mutant (session_013NEJKzp9uMCVGV7smPn7qJ), received 09:50 CST 2026-11-10, kind B

(B) handoff, lane push-calls-substitution-mutant (session_013NEJKzp9uMCVGV7smPn7qJ):
1. Work: a mutant in hooks/mutate_guard.py that drops only the substitution read in guard_merge._push_calls; debt line retired; one note added.
2. claude-settings, branch worktree-push-calls-substitution-mutant, PR #2526 (draft), head 4bd1e4f2f9ffcf270f73f40afadba35bc907bf39. All commits pushed; nothing local.
3. State: mutant KILLED by the required case on the first commit's full mutate run. Round 1 PASS on the live head (reviewer claude-haiku-5-5), review record posted on #2526 (comment 6766434757), merge --lane-lint PASS. Base is old main 0e6509a96; PR is draft and not given to a batch runner.
4. Left: batch runner marks it ready and merges (rebase on current main first, then re-check the head against the record); mutate run not re-run on the final head (only a note line follows the run).
