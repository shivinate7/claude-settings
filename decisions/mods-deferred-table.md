# Mods on the deferred list, with status and reason

## The question

Which community mods and mod ideas wait for a later decision, and why?

## The ruling

Owner word, 2026-10-13 21:00 CDT: leave these as deferred recordings on the repo.

A row with the status "Unvetted" needs the same vetting as the first eight mods. No row authorizes an install.

| Item | Status | Reason |
| --- | --- | --- |
| Robot Workers | Try later | Owner wants a trial. It adds files touched per agent. |
| claude-flightdeck | Reference only | Per-session depth. The session board builds its own per-session view (session-board-mod-limits). Its README claims no network calls, processes, file writes, or model calls. Verify in code. Lowest reach. |
| hamzafer/claude-code-mods | Consider later. Owner ruling: do not touch it now. | A toolkit of about 24 separate mods in one marketplace. The owner picks each one. |
| claude-pokemon-mod | Later, optional | Fun only. A pixel pet. It fetches sprites from the network and states no license. Skip unless the sprites are copied into the repo and the license is clear. |
| glowup | Skip | Poor fit. Haiku writes the pet lines, which spends usage. The Spotify tab does not run on Windows. Themes can load from web addresses. The side pane repeats the board and the built-in diff. |
| Visible Compact | Skip | precompact_handoff covers the need. |
| replay-theater | Skip | The plain-English diff covers the need (plain-diff-mod-limits). |
| blast-radius | Skip | The guard hook covers it. |
| fleet | Skip | It wraps `claude agents`. |
| LeakStop | Pass | Owner decision. |
| Secret-warning mod | Pass for now | No real key in 25 sessions. |

## Unvetted candidates

Vetting uses the same rule as the first eight mods. Desktop support is the first check.

| Item | Status | Reason |
| --- | --- | --- |
| claude-skins (hellosverre) | Unvetted, vet before any install | MIT. The README says the desktop app works. Adds 15 themes, styled tool rows, diff cards, a usage band, and a spinner. Fits the complaint that diffs look ugly. Compare it with the plain-diff mod. Makes one network GET per day for a plugin.json file, and sends no data. |
| project-sentinel (Arjun0014) | Unvetted, take only with its policies off | MIT. Highest reach. The README says desktop works for local sessions. Shows context, cost, CPU, and memory. Can ask or deny tool calls by category. The Windows method for machine stats is undocumented. |
| hamzafer picks: mission-control, where-am-i, usage-meter, cache-clock, merge-gate, switchboard, session-saver, rulebook-guard | Unvetted, vet before any install | Worth reading. Desktop support is not stated for these mods. |
| prismantis, claude-show-your-work | Skip for now | Desktop support is unverified or absent. |

## Parked ideas

- An `agent.spawn` hook sets a subagent's model. It is the clean home for the merge session's step-up rule: reviewer rounds 2 and 3 on Sonnet, and builder try 3 on Opus. Today that rule is a guard deny. A mod would replace refusals with correct spawns. Not built. Flag to the owner as a later item.
- A sound from `$.audio`. No community mod uses `$.audio`. The session board would play a sound when a session starts waiting on the owner. Not built.

Source: the owner's mods plan, untracked. Research date 2026-10-12.

Kind: process
Home: decisions/mods-deferred-table.md
