# Orchestrator hand-off, claude-settings build (Oct 28, 01:25 CDT)

Orchestrator session: session_013NEJL1XXYYo8v15nsrgKv7 (cloud, shiv's fresh account).
After a compaction: re-read this note, the roadmap, then act.

## Main
- b09aecee (#737, batch 2: #720 #726 #727 #728 #729 #730 #731 #732 #733 #734), merged 01:19 CDT.
- #735 (c158) was dropped from batch 2 (Windows tests red); it is batch 3 after it merges main.

## Rulings
- Oct 27 ~23:20 CDT: freeze (c155) lifted; operating model (lanes, triage, design sessions; 6+ lanes; one batch open).
- Oct 27 23:40 CDT: d9 (a) every option on a look-question shows a picture.
- Oct 27 23:48 CDT (waiting page): c108 (a), c40 (c), c121 (b), c82 done pending guard.log lines.

## Pages
- Roadmap: https://claude.ai/artifact/JGqfvgXBuLqWUm1CX6Bv5h
- Waiting page: https://claude.ai/artifact/RddcgXbB6SvTrFZHPmsvFx
- d4 picks: https://claude.ai/artifact/F2pNQsrFg6fDSqFQzKpasU

## Running sessions
| Session | Job | Branch |
|---|---|---|
| session_013NEJL1P54NSHPy9rhJ1ogU | Triage (9) | roadmap |
| session_013NEJL2u86hPSv13Jrg8KjL | d4 design: waits on shiv (items 13-21) | roadmap designs/ |
| session_013NEJL2gbHfRAmd2xZJb7ua | c158 stamp hang; merging main for batch 3 | c158-stamp-hang (#735) |
| session_013NEJL3ViieU3SfFGLVAtHg | o13 lane A rename; own batch after batch 3 | o13-gate-try-rename |
| session_013NEJKzCxa1AvvBqcazZNgY | c150 small merges skip full re-run (try 3) | c150-small-merge-rerun |
| session_013NEJKzp9tnKWNvu73kHNzN | c156 one guard for writes outside the checkout | c156-outside-write-guard |
| session_013NEJL3o8Tgq6rRbR1LbHK4 | c160 main-ref stale origin on git 2.43 | c160-main-ref-git243 |
| session_013NEJL4SMaoDMq9MrZy2bay | c148 a port keeps behaviour | c148-port-keeps-behaviour |
| session_013NEJL1Mdjts8EKVNhDB2u3 | c140 shared resource names its owner (part 1) | c140-shared-resource-owner |
| session_013NEJKzm47fniebG3qSZwaB | o2 layout-extras waiting-page key | o2-layout-waiting-page |
| session_013NEJL3wZULApnLiRyPqycj | o4 scorecard wrong-group debt | o4-scorecard-group |

## Held
- c161 after c156 (both hooks/guard.py). c152 (branch deletes) needs a watched run. Waiting-page steps c122/c135/c136/c139/c145/c147: order asked of triage.

## Owed to shiv
- Add gates-guard and gates-windows-sweep to main's required checks.
- Waiting page items: d4 picks, c146 plan picks, c151 step 2, child-repo plan check.

## Next 3 actions
1. #735 head with main: batch 3, lint, silent-undo, PR, ready, subscribe, 55-min check-in.
2. Lanes report green heads: batch 4 (o13 alone first, then the rest).
3. Start c161 once c156 merges; start the first waiting-page step in triage's order.
