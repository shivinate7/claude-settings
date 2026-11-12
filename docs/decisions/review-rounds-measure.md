# What each review round catches

## The ruling

None yet. This is a measured draft for the owner. It changes no rule. Any change to rule `roles-review-cap-three` or decision `agent-model-cap` waits for the owner's word (step `review-rounds-rework`).

## The measure

Source: review records (`<!-- review-record -->` PR comments) read by REST, one page at a time, never GraphQL. Window: comments created 2026-10-26 to 2026-11-11 00:45 UTC, 4000 comments of which 3387 are records. The read stopped at the 4000th comment, so newer records are not read. Sample: 992 PRs, 3096 record heads (the newest record per PR and head). Model names are grouped (`claude-haiku-5-5`, `haiku-5-5` and `haiku` count as haiku; the same for sonnet).

Not measured: how many findings were real, and how many findings each round raised. A record holds only a verdict per round, not finding text or counts. Proxy used: a FAIL that is followed by a new head on the same PR (1739 of 2469 round-1 FAIL heads, 70%).

| Round, model | Heads | FAIL | FAIL rate | What good looks like |
|---|---|---|---|---|
| 1, haiku (guard or check: yes) | 2665 | 2243 | 84% | a FAIL rate near the real defect rate; unmeasured |
| 1, haiku (guard or check: no) | 325 | 226 | 70% | same |
| 1, sonnet (all) | 43 | 19 | 44% | small sample, not comparable |
| 2, sonnet (guard or check: yes) | 2093 | 1035 | 49% | same |
| 2, sonnet after a round-1 PASS | 259 | 71 | 27% | near 0 if round 1 caught it all |
| 3, sonnet (guard or check: yes) | 1490 | 124 | 8% | same |
| 3, sonnet after a round-2 PASS | 675 | 29 | 4.3% | same |
| 3, sonnet after round 1 and 2 both PASS | 155 | 4 | 2.6% | same |

Net value at round 3 (guard or check: yes): after a round-2 PASS, 0 negative in 646 records with a net value, 119 zero. After a round-2 FAIL, 9 negative in 695, 110 zero. Guard or check: no changes: 423 heads, round 3 reached by 73.

Reading: haiku round 1 FAILs most guard changes, and sonnet round 2 still FAILs 27% of those haiku passed, so haiku misses real defects. Round 3 after a round-2 PASS catches 4% and held back nothing (0 negative net value). All 9 negative net values follow a round-2 FAIL.

## The proposal, for the owner

- a. Round 1 on sonnet for every guard or check change (haiku stays for the rest). Owner item 359 a already says so; only 43 round-1 records show sonnet, so check that the spawn applies it.
- b. Round 3 and its net-value test only after a round-2 FAIL. After a round-2 PASS, skip it. Loses: 29 catches in 675 and a net-value line on those. Gains: one fewer sonnet round on about 675 heads.
- c. Add a `Findings:` line to the record (blocker, should-fix, wording counts), so the next measure can say how many findings were real. Item 359 c labels findings but the record keeps none.

Kind: process
Home: CLAUDE.md rule `roles-review-cap-three`, and decision `agent-model-cap`, once the owner rules.
