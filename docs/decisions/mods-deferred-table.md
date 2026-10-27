# Mods on the deferred list, with status and reason

## The ruling

These mods stay deferred recordings on the repo. A row with the status "Unvetted" needs the
same vetting as the first eight mods (desktop support first). No row authorizes an install.

| Item | Status | Reason |
| --- | --- | --- |
| Robot Workers | Try later | Owner wants a trial. It adds files touched per agent. |
| claude-flightdeck | Reference only | Per-session depth. The session board builds its own (session-board-mod-limits). Verify its README claims in code. Lowest reach. |
| hamzafer/claude-code-mods | Consider later. Do not touch it now. | About 24 separate mods in one marketplace. The owner picks each one. |
| claude-pokemon-mod | Later, optional | Fun only. It fetches sprites from the network and states no license. Skip unless the sprites are copied in and the license is clear. |
| glowup | Skip | Poor fit. Haiku writes the pet lines, which spends usage. The Spotify tab does not run on Windows. Themes can load from web addresses. The side pane repeats the board and the built-in diff. |
| Visible Compact | Skip | precompact_handoff covers the need. |
| replay-theater | Skip | The plain-English diff covers the need (plain-diff-mod-limits). |
| blast-radius | Skip | The guard hook covers it. |
| fleet | Skip | It wraps `claude agents`. |
| LeakStop | Pass | Owner decision. |
| Secret-warning mod | Pass for now | No real key in 25 sessions. |

Parked, not built, flag to the owner as later items:

- An `agent.spawn` hook sets an agent's model. It would replace the guard refusal for the step-up rule (reviewer rounds 2 and 3 on Sonnet, builder try 3 on Opus) with correct spawns.
- A `$.audio` sound when a session starts waiting on the owner. No community mod uses `$.audio`.

## Unvetted candidates

| Item | Status | Reason |
| --- | --- | --- |
| claude-skins (hellosverre) | Unvetted, vet before any install | MIT. README says desktop works. 15 themes, diff cards, usage band. Compare with the plain-diff mod. One network GET per day, no data sent. |
| project-sentinel (Arjun0014) | Unvetted, take only with its policies off | MIT. Highest reach. README says desktop works for local sessions. Can ask or deny tool calls by category. Windows method for machine stats is undocumented. |
| hamzafer picks: mission-control, where-am-i, usage-meter, cache-clock, merge-gate, switchboard, session-saver, rulebook-guard | Unvetted, vet before any install | Desktop support is not stated. |
| prismantis, claude-show-your-work | Skip for now | Desktop support is unverified or absent. |

Kind: process
Home: docs/decisions/mods-deferred-table.md
