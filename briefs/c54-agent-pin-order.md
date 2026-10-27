# c54 next part: does an agents/*.md model pin beat the env var in a cloud thread?

Cloud build thread brief. Build advisor (10), Oct 27, against claude-settings main 6a3e842.
Measurement lane. It lands a decision record by PR; send the head to the build advisor.

## Why
Known (measured Oct 26, cloud): a spawn's own `model` field wins, then a built-in definition's
model, then CLAUDE_CODE_SUBAGENT_MODEL. Unknown: where a pin in claude-settings'
`agents/*.md` frontmatter sits in that order. Local sessions rely on those pins for the
model-per-role table.

## Task
1. Copy claude-settings `agents/*.md` into `~/.claude/agents/` in this container.
2. Set CLAUDE_CODE_SUBAGENT_MODEL to a model different from one pin (for example a pin of
   opus, env sonnet), and the reverse. Spawn each agent type with no `model` field and record
   the model it ran (from the agent's own report of its model id or the session API).
3. Also record whether a cloud thread loads `~/.claude/agents` written mid-session, or only at start.
4. Write the order into the decision record that holds the model-per-role table
   (find it with `grep -rl agent-model-cap docs/decisions`), rewritten in place.

## Done when
The record states the full order with "measured Oct 27, cloud" and each case's observed model.
Any case you cannot measure is written as unknown. Review: one fresh Sonnet reviewer.
Report cap 15 lines. Port: no; the order is a Claude Code fact, recorded once here.
