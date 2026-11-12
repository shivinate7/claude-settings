# The agent-write rule judges only file-tool writes

**What.** The rule `handoff-agent-write` judges only Write, Edit and MultiEdit to a session handoff, the same scope as `handoff-sections` (item 14). An agent's `cat >`, `tee` or `Set-Content` on the handoff of the session that spawned it passes it. The incident's own shell try (17:21:03) was stopped only by the worktree-isolation check, which refused it as too complex to verify. Mistake: an agent writes the spawner's handoff through a shell command after the file tool is refused. Harm: that handoff is replaced. The root fix (item 16) is the skip in the handoff hooks. The cwd skip covers an agent with a worktree. The `agent_id` skip covers the rest, if real payloads carry `agent_id` (unmeasured). Where neither holds, only this rule catches the agent, and not for the shell form.

**Where.** `hooks/guard.py`, rule `handoff-agent-write`, the tool check that takes only Write, Edit and MultiEdit.

**Decision.** `precompact-handoff` (checkpoints keep the handoff current), item 16 (an agent never writes a session handoff).

**Retire.** A red case per form, an agent's `cat >`, `tee` and `Set-Content` to the handoff path, expects a refusal naming `handoff-agent-write`. Test file: `hooks/test_guard.py`.
