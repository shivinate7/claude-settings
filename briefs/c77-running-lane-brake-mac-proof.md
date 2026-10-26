# c77: prove the running-lane brake on the Mac

Goal: prove that a background agent's own Bash call reaches the guard with its `agent_id`, so the running-lane brake (PR 642, "brake a running lane at a full machine") can stop it.

Steps, on the Mac, after PR 642 is installed (`sh install.sh` from a checkout of its branch, or after it merges):
1. In any repo, start one Agent with `run_in_background: true` whose only job is to run `echo probe` in Bash.
2. Read the last lines of `~/.claude/guard.log` (or the payload trace, if one is on). Report whether the Bash call's payload carried an `agent_id`.
3. Do not fill the disk to test the refusal. The fixture suite proves the refusal; this brief proves only the live payload.

Report (5 lines max): the commit installed, whether the background Bash payload carried `agent_id`, and anything unexpected.
