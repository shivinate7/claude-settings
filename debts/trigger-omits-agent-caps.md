# The trigger omits the agent caps

- **What.** The trigger in decision `hold-unsafe-after-round-3` (net-value hold after round 3) omits the `settings.json` env caps `CLAUDE_CODE_SUBAGENT_MODEL` and `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, and the `model:` and `effort:` lines in `agents/*.md`. A change to them gets no net-value test.
- **Where.** The `settings.json` env block and the `agents/*.md` frontmatter. They enforce rule `roles-sonnet-is-the-ceiling` (Sonnet is the agent ceiling) and keep workers from spawning.
- **Decision.** `hold-unsafe-after-round-3` (net-value hold after round 3).
- **Retire.** The trigger names those keys and lines, and a check fails when a change edits one of them without the net-value test.
