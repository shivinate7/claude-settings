# Outbox: c140-shared-resource-owner

- c140 part 1 (a shared machine names one owning repo): draft PR #743, head c1aecd35. The local gates pass, and the round-2 review approved. Batch 5: it is held out of batch 4 because it conflicts with #740 (step c160) in docs/debts/notes.md. When the orchestrator says batch 4 merged:
  1. Merge origin/main INTO the branch with a merge commit, and keep both sides' notes lines.
  2. Re-run `bin/verdict ci-job gates --lint` and check_silent_undo.
  3. Push, and send the orchestrator the head.
- c141 (the roll-out to other repos): each repo adds a `shared-resources` entry to `.claude/layout-extras.json`. The HA Green entry names owner shivinate7/home-app and the preflight path in that repo. Each repo then runs `lint/check_shared_resources.py` in its CI. The decision `shared-resource-owner` holds the convention.
