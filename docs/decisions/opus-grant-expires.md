# An Opus grant ends at the deadline the owner approves

## The ruling

An Opus agent is enabled for one repository, on the owner's grant in chat (`roles-opus-override-guarded`). The grant raises the fallback and does not pin. For one Opus lane, the orchestrator passes the model on that one call, on the owner's grant: narrower and cheaper. The grant is for several lanes in a row, and it needs a fresh session: a running session keeps the old value.

A write that sets the fallback is always an ask (guard rule `agent-model-cap`). `hooks/config_watch.py` expires it, because a clock protects better than memory.

The deadline has no length cap. Owner, 2026-11-12 12:54 CST (page item 602, pick a): the end time joins the existing ask and shows its end in US Central, 24-hour clock with the zone, and it allows any length. The ask is the check on the length, and the owner reads the end before he approves.

The raise outlives the turn that wrote it. Two parts guard it. Both key on `CLAUDE_CODE_SUBAGENT_MODEL` and `CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL` alone.

- Guard rule `agent-model-cap` asks on the write. It matches `_FORCE` too, so the ask still fires on a stale file, or another repository, that sets the flag. A write that sets a current `_agentCapUntil`, with or without a model key, asks too, and the ask prints `cap lift ends HH:MM CST` or `CDT`, with no date. An Edit, a MultiEdit or a `sed` shows the end the file arrives at, read from the file on disk with the change applied. A deadline that is passed, malformed or missing adds no ask. The watch handles it.
- `hooks/config_watch.py` lifts the cap for any value of either model key other than `sonnet`. The deadline `_agentCapUntil` is a top-level key of `.claude/settings.local.json`, outside `env`, at any length ahead. The watch revokes on it, and the guard reads it only to show the end in the ask. A deadline that is missing, unparseable or passed gets the file reverted to the `prior` content the watch holds. With no `prior` on record the watch reports UNKNOWN and asks the owner to read the file by hand.

The model per role, the default and the ceiling are in `agent-model-cap`.

Kind: process
Home: hooks/config_watch.py
