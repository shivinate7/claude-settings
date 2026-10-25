# c42. home-app: the merge tool finds its checks

Brief for a home-app session (paste all of it):

Goal: the claude-settings merge tool runs in home-app, and a PR whose draft run skipped gets a real run without an empty commit.
1. Add .github/stamp.json with merge.requiredChecks naming the jobs in .github/workflows/test.yml: scope, test, addon, ios. Copy the shape from claude-settings .github/stamp.json. Set merge.deadlineMinutes to the largest job timeout-minutes plus 5. The merge tool already passes a skipped job, and goes red only when no job ran on the head (merge/merge.py judge_runs).
2. Proof: run the merge tool's dry read on an open PR (or the next one) and show it lists the four checks instead of stopping on "no branch protection".
3. Add one line to home-app CLAUDE.md's CI rule: when a PR's run skipped because it was a draft, mark it ready (gh pr ready), which starts the PR run on the same head; never push an empty commit to start CI.
Report: Done, Deviations, Input Needed, Next.
