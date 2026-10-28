# c54 part 3: every cloud container installs claude-settings

Lane session session_013NEJL2U2yybhzheLMVTVC6, Oct 28, against main 3bebbd3. No claude-settings code change, so no PR.

## Cause

- The cloud install has one home: the cloud environment's setup script, which runs `install.sh --cloud` (README, "Cloud sessions"; install.sh line 5). claude-settings carries no repo `.claude/settings.json` and no repo SessionStart hook. Nothing in a repo's own checkout installs it.
- A setup script belongs to a cloud environment, not to a repo. So the install depends on the environment a session runs in, not on its repo.
- Red, measured Oct 28 in this lane: this session runs on claude-settings itself, in environment "Siberia" (env_01RGfPzEB3iusXZwCZw5q5or, made Oct 28 03:39 UTC). It has no `~/.claude/settings.json`, no `~/.claude/hooks/guard.py`, and no `CLAUDE_CODE_SUBAGENT_MODEL`. So the starting fact ("claude-settings sessions install at start") holds only for an environment whose setup script runs the install. It is not a property of the repo.
- The account has three environments: Siberia, Q_Env, Default. Which of them have the setup script: unknown. No tool here reads an environment's setup script. Any of them without it installs nothing, in any repo.

## Green, measured Oct 28 in this lane

The README setup line, run in an isolated home, from a non-claude-settings git repo (origin shivinate7/degen), with no claude-settings checkout reachable:

- It fetched main and wrote `CLAUDE.md` (pointer), `settings.json` (repo settings + cloud refresh hook), hooks, agents, lint and skills. Exit 0.
- settings.json holds the PreToolUse guard, the SessionStart refresh hook, the precompact hand-off hooks (c154 keeps them), and env `CLAUDE_CODE_SUBAGENT_MODEL=sonnet`.
- The guard's shared-tree family passes against the installed copy (`GUARD_UNDER_TEST=<installed guard.py> GUARD_FAMILY=shared-tree`, verdict PASS).

## Setup text for shiv

Set this as the setup script on each cloud environment (Siberia, Q_Env, Default): the cloud environment menu in the session's title bar, then Edit, then Setup script. New sessions run it.

```bash
#!/bin/bash
set -o pipefail
curl -fsSL https://raw.githubusercontent.com/shivinate7/claude-settings/main/install.sh | bash -s -- --cloud
```

- `set -o pipefail`: a failed download fails the setup script, so it shows in the session's start-up output. Without it, bash reads an empty script, exits 0, and the session starts with no guard and no sign.
- Network: Trusted, or a Custom list with `raw.githubusercontent.com`, `github.com`, `codeload.github.com`.
- After that, each new or resumed session also re-runs the install through the refresh hook the script writes.
- Check: in a new cloud session on any repo, `ls ~/.claude/hooks/guard.py` and `echo $CLAUDE_CODE_SUBAGENT_MODEL` (expect `sonnet`).

## Why not a SessionStart hook in each child repo

- It needs one change per child repo (degen, banchi and others), and a new repo starts with no guard until someone adds it.
- It runs after the session loads its settings. Whether a running cloud session loads hooks from a `~/.claude/settings.json` written by its own SessionStart hook: unknown. c54 measured that a running cloud thread does not load `~/.claude/agents` written mid-session, so the first session would likely start unguarded.
- The setup script runs before the session starts, in every repo, with one setting per environment. Recommended. Child-repo plan: none needed.

## Open

- Whether a failed setup script stops the session from starting: unknown. If it does, `pipefail` trades "start with no guard" for "no start while GitHub is down". Drop the `set -o pipefail` line to prefer the first.
- Note, not a debt: README's setup line has no `pipefail`. A one-line README change can add it in a later lane.
