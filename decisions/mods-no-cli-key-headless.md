# Mods make model calls with `$.model.complete`, with no CLI key

## The ruling

- No CLI API key for headless runs. Headless `claude -p` is retired for mods only. The Stop hook keeps its `claude -p` path (decision-watch-mod-limits).
- A mod calls `$.model.complete`. It uses the app's own connection, which is separate from the CLI login that expires between a Mac and a PC. It returns `{isAnswered, text, usage}`. Read `.text`.
- A stored API token is the fallback, only if the mod route fails. It bills per token on top of the plan and adds a secret to protect.
- A model call spends usage, so cap it.

Unverified: whether the call works during a compaction.

Kind: process
Home: mods/decision-watch/README.md
