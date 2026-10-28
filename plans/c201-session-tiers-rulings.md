# c201: session tiers, rulings so far (shiv, Oct 28 2026, CDT)

Home until docs/decisions/session-tiers.md (c201 part L0) merges; then cut this file and point c201 there.

Rulings by shiv, Oct 28 (chat; full text in docs/decisions/session-tiers.md, L0): 14:59: one coordinator per repo; coordinators may message each other to share a resource (a simulator, a loaded machine) and may touch other repos, but mainly run their own repo's lanes; claude-settings touches every repo a little.

15:01: no coded guard or file-ownership record for clashing lanes (a good brief and merging overlapping edits are enough); his want is better file splitting, no lane filed yet; false done is already covered by merge.py and rule verification-verify-against-repo.

15:03: triage is always a standing session, and each coordinator spawns it first, before any lane session.

15:04: revise the solo-versus-orchestrate rules to match the tiers; he wants an Opus review and is open to being interviewed.

15:11 ("B for sure actually"): a third standing role, the batch runner. It owns the integration batch, the CI waits, the merge tool runs and archiving lanes, so the coordinator holds only lane state and talks with him.

15:12: when he names the wrong tier or brings work to the wrong session, that session pushes back in one line (its tier, the right one, why), then still handles or routes it; into session-tiers.md, and lane L1 puts it in the output style or rules.

15:18, the planner's four questions, answered in chat: (1) session shape is picked dynamically from his request: solo, one lane with its own subagents, or coordinator, and a session may grow from one shape to the next; (2) "orchestrator" stays the catch-all tier (coordinator, triage, batch runner and lane session are kinds of it); (3) a coordinator may work in another repo by hand-off or its own PR, no hard block; it first checks for an active coordinator there and, if none, proceeds; (4) only the coordinator starts sessions, and it starts triage and the batch runner together as a trio before any lane.

15:23 want: rotate standing sessions before they go stale. Triage and the batch runner each report a tally of their own use (turns or context) to the coordinator; near the limit the coordinator has the session write its handoff, archives it and starts a fresh one.

Open: coordinator succession (a new coordinator takes over every child session, each told its id); into session-tiers.md and lane L1 or its own lane. Name: he said "branch manager" for the batch runner; the coordinator is telling him the name in use.

Lanes L1 (rules, glossary), L2 (skills), L3 (session-start guard) start after batch 13 merges.

Open: item 50 (lane sessions Sonnet or Opus, pick a recommended); whether he answers triage directly more often; a per-tier context limit (Oct 28 15:08): local launches and agent files can set their own window, cloud has no documented per-session setting, so waiting-page item 53 asks whether to test one cloud environment per tier.

Placed after c200 (triage 12, Oct 28).
