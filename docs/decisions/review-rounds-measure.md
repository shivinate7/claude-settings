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

Reading: haiku round 1 FAILs most guard heads, and sonnet round 2 still FAILs 27% of those haiku passed, so haiku misses some defects. Round 3 after a round-2 PASS caught 4% and held back nothing.

## The proposal, for the owner

Already ruled, not re-asked: round 1 on Sonnet for a guard or check change (item 359 a); round 3 only for a change fixed under a fix check, and a change that passes round 1 is done (owner, R9, 2026-11-10 15:44 CST, corrected 16:07 CST, relayed; step `rounds-rules-one-record`; item 471 a, 2026-11-09 23:39 CST). The 675 round-3 heads after a round-2 PASS above predate that ruling. Their 4.3% FAIL rate and 0 negative net value are the measure of what the ruling drops.

Open, from the step's deferred note: should round 1 run Sonnet for every logic change, not only guard and check changes? Measure: haiku round 1 FAILs 84% of guard or check heads, sonnet 44% (43 records, a small sample). The share of haiku FAILs that were noise is unmeasured.

- c. Add a `Findings:` line to the record (blocker, should-fix, wording counts), so the next measure can say how many findings were real. Item 359 c labels findings but the record keeps none.

Kind: process
Home: CLAUDE.md rule `roles-review-cap-three`, and decision `agent-model-cap`, once the owner rules.
