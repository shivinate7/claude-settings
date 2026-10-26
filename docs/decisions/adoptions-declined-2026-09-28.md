# Adoptions declined on 2026-09-28

## Ruling

The owner declined each candidate below. A session that proposes one again first names what changed.

| Candidate | Why declined | What would reopen it |
| --- | --- | --- |
| Package this repo as a plugin | Cloud sessions load no plugins from local settings. A plugin cannot ship CLAUDE.md or permissions. The SessionStart hook already installs. | Cloud sessions load user plugins. |
| Sandbox mode | Every network host and tool needs an allow entry. The guard, deny rules and frozen paths give most of the gain. | A guard bypass that deny rules and frozen paths do not cover. |
| destructive_command_guard (dcg) | Too broad for one developer: a second binary, over 50 rule packs mostly for unused tools, open bypass issues, fails open. | Regular use of Docker, Kubernetes, cloud or database CLIs. Copy those few patterns into the guard. |
| Status line | It renders in the terminal. The owner works in the desktop app. | Daily terminal use. |
| Public agent collections (wshobson/agents, VoltAgent) | Persona prompts with generic checklists, no gating checks. Each agent description costs context in every session. | Evidence that a specialist beats a briefed builder or reviewer. |
| adr-tools | It numbers records at creation, so branches collide. | None. |
| Log4brains | It serves human browsing, which is rare here. Agents read decisions by grep. | The owner browses decisions often enough to want a site. |
| An AI README generator | Generic prose breaks the fewest-words rule. The fresh-prose skill holds the README procedure. | None. |
| A per-tool cost-logging hook | A hook sees tool calls, not token counts. Transcripts hold the per-reply usage. | A question the transcripts cannot answer. |

Kind: process
Home: rule:outcomes-decision-is-argument
