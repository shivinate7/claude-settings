# c77: prove the running-lane brake on the Mac

Goal: prove that a background agent's own Bash call reaches the guard with its `agent_id`, so the running-lane brake (PR 642, "brake a running lane at a full machine") can stop it.

Steps, on the Mac, after PR 642 is installed (`sh install.sh` from a checkout of its branch, or after it merges):
1. In any git repo, note the files in `$(git rev-parse --git-common-dir)/agent-homes/` (it may not exist).
2. Start one Agent with `run_in_background: true` and `isolation: "worktree"` whose only job is to run `echo probe` in Bash. Wait for it to finish.
   The guard writes `agent-homes/<agent_id>` only when the call's payload carries an `agent_id`. Report whether a new file appeared.
3. Do not fill the disk to test the refusal. The fixture suite proves the refusal; this brief proves only the live payload.

Report (5 lines max): the commit installed, whether the background Bash payload carried `agent_id`, and anything unexpected.
