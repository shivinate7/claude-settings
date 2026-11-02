# Terminology review: roles and units

Opus review, 2026-11-02 13:50 CST. Read claude-settings origin/main 5a5f081e and each child's origin/main (q_max, banchi, degen, joyous, mailaudit). The home and ios-adblock repos were not in the container. No child has a GLOSSARY.md.

## Point

The role words are not conflict-free: 9 real conflicts. Five are word clashes. Four are stale merge rulings in child repos that let the coordinator or an "orchestrator" merge; main says only a batch runner merges (standing-merge-grant.md:7; session-tiers.md:63; owner 2026-11-01 21:34 CST).

## Terms

| Term | GLOSSARY.md | Differing use | Verdict |
| --- | --- | --- | --- |
| lane | :25 one isolated piece of work, with its own branch, worktree and lane PR | lanes-start-as-agents.md:7 "A lane is an Agent spawn"; GLOSSARY:70-72 blind/informed/directed lane = a designer spawn with no lane PR | CONFLICT |
| orchestrator | :49 any session that spawns agents; lists triage and batch runner as kinds | session-tiers.md:13 makes them kinds by tier even when they spawn nothing; solo missing from the kinds | CONFLICT (minor) |
| coordinator | :50 starts triage, batch runner, lane sessions | it also starts the arbiter (:53), which :50 omits; child merge lines below | CONFLICT |
| triage / page writer / gatekeeper | :51 only writer of the roadmap and the waiting page | waiting-page SKILL.md:168 "the orchestrating session ... owns the page"; operating-model.md:17 "The gatekeeper of the roadmap"; four spellings of page writer | CONFLICT + SYNONYM |
| builder | :56 agent | roadmap README.md.tmpl:13 and operating-model.md:23 mean build.py; joyous CLAUDE.md:30,42,51,59 mean the owner | CONFLICT |
| batch | :26 | degen CLAUDE.md:39 "A batch is one release, cut at a milestone" | CONFLICT |
| integration branch | :27, Not "batch branch" | CLAUDE.md:58 "never the batch branch" | CONFLICT |
| arbiter | :53, batch checks go to the batch runner | q_max CLAUDE.md:132 the arbiter marks the batch ready; q_max browser-checks-once-per-batch.md:19 | CONFLICT |
| agent roles | builder, test-author, reviewer, designer, design reviewer | CLAUDE.md:21-22 lists 5 and omits test-author; agents/ holds 9 files | CONFLICT (incomplete) |

Clear: batch runner, integration PR, session, agent, subagent (platform names only), reviewer, test-author, designer, design reviewer, lane session; worker as a domain word.

No glossary row: solo, one lane, shape, tier, standing session, Explore, Plan, advisor, record-writer, workflow, fan-out, workstream (CLAUDE.md:43), oversight session, bridge session, helper, point guard (mailaudit), primary orchestrator (q_max).

## Lane: agent or session

lanes-start-as-agents.md (2026-10-27) says a lane is an Agent spawn and a separate session needs the owner's words (:7-8). session-tiers.md:15,51 (2026-10-28) says the coordinator starts lane sessions. agent-model-cap.md:17 pins subagent spawn depth at 1, so an agent lane cannot run "with its own agents" (CLAUDE.md:14). lanes-start-as-agents looks stale for tiered repos: a stale-decision candidate, no ruling made. "One lane" (a shape) and "lane session" (a tier) name one thing two ways.

## Children: stale merge lines

- banchi CLAUDE.md:346-347: the coordinator holds the standing merge grant and merges.
- degen CLAUDE.md:7: the coordinator may merge; :23,35 "the orchestrator" names no tier.
- mailaudit orchestrator-may-merge.md:5: the coordinator also merges.
- q_max D-705 and CLAUDE.md:88: the "primary orchestrator" holds the grant; "arbiter" used since 2026-10-12, before the parent role (2026-10-29).
- joyous CLAUDE.md:30: "Claude merges a PR"; "builder" means the owner.
- banchi CLAUDE.md:369, :343 restate agent-model-cap and session-tiers instead of pointing.

These are rulings, not wording: they go to the owner through the stale-decision protocol.

## Questions for the owner (recommendations)

- Is a lane an agent or a session? Recommend: a lane is the unit of work; a lane session runs it. Rewrite lanes-start-as-agents to cover solo and one-lane sessions only.
- Who writes the page? Recommend: triage where tiers run, else the coordinator.

## Proposed fix (proposals only)

- GLOSSARY: rows for shape, tier (the 5 cs-build values), standing session, page writer (one spelling), Explore, Plan, advisor, record-writer, fan-out. Add the arbiter to the coordinator row. Define orchestrator by tier or by spawning. Rename the blind/informed/directed "lane" to "designer spawn".
- Retire: gatekeeper, oversight session, primary orchestrator, point guard, helper, workstream, bridge session (or define it). Add "builder (this sense)" for the script. Fix "batch branch" at CLAUDE.md:58.
- CLAUDE.md:21-22: list all agent roles, or point at GLOSSARY.
- Children: each merge line becomes a one-line pointer to session-tiers and standing-merge-grant. degen:39 batch points at the parent term and keeps only the milestone cadence. joyous: "builder" becomes "owner". q_max: the batch runner, not the arbiter, marks a batch ready; retire "primary orchestrator".
