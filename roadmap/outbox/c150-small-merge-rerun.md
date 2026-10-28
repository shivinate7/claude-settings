# c150-small-merge-rerun

Step c150, a small unrelated merge to main does not force a full CI re-run of the batch.

- Branch: c150-small-merge-rerun, from origin/main e0f9e2d.
- Design: option (a). merge.py accepts the old green run only when main's new paths share no path with the batch, turn on no CI job per .github/scripts/ci-scope.sh, and the `gates` lint steps (`bin/ci-job gates --lint`) pass on the merge result. Anything else keeps today's refusal.
- State: builder (Opus) writing red tests, then the fix. Reviewer (Opus) next.
- Resume: read the branch log; if no fix commit, re-brief a builder from this note.
