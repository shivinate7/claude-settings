# Mods make model calls with `$.model.complete`, with no CLI key

## The question

How does a mod get a model answer when the CLI login is missing or has expired?

## The ruling

- No CLI API key for headless runs.
- Headless `claude -p` is being retired for mods. This covers mods only. The Stop hook keeps its `claude -p` path (decision-watch-mod-limits, shadow-mode judge).
- A mod calls `$.model.complete` instead. It uses the app's own connection.
- A stored API token is the fallback, and only if the mod route fails. It bills per token on top of the plan. It adds one more secret to protect.

## Why

- The owner sees the CLI login expire when switching between a Mac and a PC. The app's own connection is separate from that login.
- The header of precompact_handoff says it makes no model call, because `claude -p` needs a login that the desktop app lacks.
- Spike, 2026-10-13 12:09 CDT: `$.model.complete` ran in the desktop app with no CLI login. A haiku ping took about 0.9 s. A full decision-watch judgment took about 5 s. The call returns `{isAnswered, text, usage}`. Read `.text`.
- A model call spends usage, so cap it.

## Unverified

- Whether the call works during a compaction.

Kind: process
Home: mods/decision-watch/README.md
