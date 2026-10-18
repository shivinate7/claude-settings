# An Opus grant expires within 24 hours

## The ruling

An Opus worker is enabled for one repository, on the owner's word in chat (`roles-opus-override-guarded`). The grant raises the fallback and does not pin. For one Opus lane, the orchestrator passes the model on that one call, on the owner's word: narrower and cheaper. The grant is for several lanes in a row, and it needs a fresh session: a running session keeps the old value.

A write that sets the fallback is always an ask (guard rule `subagent-model-cap`). `hooks/config_watch.py` expires it, because a clock protects better than memory.

The raise outlives the turn that wrote it. Two parts guard it. Both key on `CLAUDE_CODE_SUBAGENT_MODEL` and `CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL` alone.

- Guard rule `subagent-model-cap` asks on the write. It matches `_FORCE` too, so the ask still fires on a stale file, or another repository, that sets the flag.
- `hooks/config_watch.py` lifts the cap for any value of either model key other than `sonnet`. The deadline `_subagentCapUntil` is a top-level key of `.claude/settings.local.json`, outside `env`, at most 24 hours ahead. Only the watch reads it. A deadline that is missing, unparseable, passed or too far out gets the file reverted to the `prior` content the watch holds. With no `prior` on record the watch reports UNKNOWN and asks the owner to read the file by hand.

The model per role, the default and the ceiling are in `subagent-model-cap`.

Kind: process
Home: hooks/config_watch.py
