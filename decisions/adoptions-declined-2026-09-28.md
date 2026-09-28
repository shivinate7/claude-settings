# Adoptions declined on 2026-09-28

A review of public Claude Code configs and native features proposed these. The owner
declined each one. A session that proposes one again first names what changed since this
entry.

| Candidate | Why declined | What would reopen it |
| --- | --- | --- |
| Package this repo as a plugin | A cloud session does not load plugins from local settings, and a plugin cannot ship CLAUDE.md or permissions. The SessionStart hook already pulls and installs. | Cloud sessions load user plugins. |
| Sandbox mode | Upkeep: every network host and tool needs an allow entry, for a gain the guard, the deny rules, and the frozen paths now mostly give. | A guard bypass that the deny rules and frozen paths do not cover. |
| destructive_command_guard (dcg) | Too broad for one developer: a second binary and TOML config, over 50 rule packs mostly for tools not in use. Its open issues are bypasses, and it also fails open. | Regular use of Docker, Kubernetes, cloud, or database CLIs. Copy those few patterns into the guard. |
| Status line | It renders in the terminal, and the owner works in the desktop app. | Daily terminal use. |
| Public subagent collections (wshobson/agents, VoltAgent) | Persona prompts with generic checklists, no gating checks, no evidence of better outcomes. Each installed agent's description costs context in every session. Three useful reviewer checks were taken instead (PR #156). | Evidence that a specialist beats a briefed builder or reviewer. |
| adr-tools | It numbers records at creation, so branches collide. No commits since 2020. | None. |
| Log4brains | It serves human browsing, which is rare here. Agents read decisions by grep. Last release December 2024. | The owner browses decisions often enough to want a site. |
| An AI README generator | Generic prose that breaks the fewest-words rule. The fresh-prose skill holds the README procedure instead. | None. |
| A per-tool cost-logging hook | A hook sees tool calls, not token counts. The transcripts already hold the per-reply usage. | A question the transcripts cannot answer. |
