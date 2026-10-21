# A lane agent in a hand-made worktree can write into the main clone

- **What.** On 2026-10-20 at 16:53 CDT, two lane agents wrote into the main clone `C:\Users\ShivamSemwal\Clones\claude-settings` through relative paths. One script truncated `decisions/haiku-prompt-hooks.md` there (restored from the lane's copy). Another created an empty `hooks/test_prose_judge.py`.
- **Cause.** On 2026-10-19, at 100% CPU, the Agent tool's `isolation: 'worktree'` refused its own worktrees. Whether the harness or this repo's guard refused is unknown. The orchestrator then made lane worktrees by hand in its scratchpad, and spawned agents without isolation, briefed to use them. Such an agent starts in the main clone, and no hook payload field ties it to the hand-made tree.
- **Where.** The guard rule `worktree-home` in `hooks/guard.py` knows an agent's home only at the harness path `<primary>/.claude/worktrees/agent-<agent_id>`. A hand-made worktree cannot take that path, because the id does not exist before the spawn. So "pin hand-made worktrees to `.claude/worktrees/`" fences nothing.
- **Decision.** `an-agent-outside-its-home-tree-must-stop` (an agent outside its home tree must stop).
- **Ruling (owner 2026-10-21).** Block the workaround fully, and diagnose the isolation failure:
  - Block: the guard refuses a hand-made lane worktree, so a lane starts only through the tool's isolation. Cost: when isolation fails, the lane fails. Only the claude-settings orchestrator session paces spawns by CPU (process-only ruling), so in other repos no rule makes a session wait for load to drop.
  - Diagnose: on the next isolation refusal, record which layer refused (harness or guard) and its message. If the guard refused, fix the guard.
- **Retire.** A red case shows the guard refusing a hand-made lane worktree. The isolation failure's cause is named, and fixed if it is this repo's.
