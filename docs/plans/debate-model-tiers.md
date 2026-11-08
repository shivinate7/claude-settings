# Plan: which refuters run Opus

id: pending

Critic: pending, the refuter role (lane blind-plan-refuter) is not on main yet

This record holds roadmap step debate-model-tiers (the model each refuter runs). Owner note on page item
284 (more places for a refuter), 2026-11-06 13:08 CST: "some challengers should run Opus, not all Sonnet,
and there are probably more places to use them". The word is "refuter" (item 282, pick b).

## Method

- **Sort test.** A refuter runs Opus when a wrong "it holds" verdict does real harm, no other reader sees
  the verdict, and the call count is low. It runs Sonnet when another reader sees the same verdict, or when
  the call count is high.
- **Counts.** Read from git on origin/main and origin/roadmap, 2026-11-06. A count marked "proxy" stands in
  for the real count. A count marked "assumed" has no measure.
- **Precedent.** The question reviewer already makes one Opus call per page question (decision
  `agent-model-cap`, its row; class-level grant of 2026-10-21).

## 1. Refuters built or in flight

| Lane | Model call | Who else sees the verdict | Calls per day | Pick | Gold |
|---|---|---|---|---|---|
| blind-plan-refuter | one per plan | nobody before the build | plan records added: 2 to 17 a day, 10-30 to 11-04 (proxy; most Plan output is no record) | Opus, ruled (item 279, pick d). Not in the question. | Opus |
| reviewer-brief-blind | none: a guard check on the brief | n/a | 0 | n/a, no model call. The reviewer keeps its row: haiku round 1, sonnet rounds 2 and 3. Item 279 option c (guard fix check on sonnet) was not picked. | 0 calls |
| judge-replay-corpus | CI only, per judge change | CI | only on a PR that changes a judge | n/a. Each judge replays on its own production row, or the replay proves nothing. | each judge's own row |
| step-done-needs-check | none: a lint | n/a | 0 | n/a, no model call. Its `Critic:` line names the refuter role, which is Opus. | 0 calls |
| challenger-page-against | one per decision item | the owner reads the case; the Opus question reviewer reads the question | decision items added: 6 to 51 a day, 10-31 to 11-06, median 22 (measured) | Sonnet | a strong case against, read by the owner |
| ruling-skip-check | one per skip | nobody: the owner never sees a skip | unmeasured. Stood picks (13, all 10-27 and 10-28) do not match the meaning. Assumed: under 10 a day | Opus | each skip confirmed against the ruling's own words |
| check-line-reader, brief read | one per lane brief | the builder and reviewer, later | lane sessions started: 25 to 104 a day, 10-28 to 11-05, median 58 (measured, session list) | Sonnet | a weak done-check flagged before the build |
| check-line-reader, close read | one per step close | nobody: it decides "done" | steps closed: 4 to 33 a day, 10-29 to 11-05 (proxy: the commit that first set done; 11-06 is a bulk rewrite and is left out) | Opus | done only on a check that proves the ask |

Why the split on check-line-reader: the brief read is early and seen again by the builder and the reviewer,
and its count is the highest. The close read is the last reader before "done", and its count is lower.

## 2. More places a refuter catches a normal-work mistake

Item 279 options c and e (guard fix check on sonnet; a second blind reviewer on guard PRs) were offered and
not picked. This list does not repeat them.

| Place | Mistake Claude makes | Harm | Calls per day | Model | Gold |
|---|---|---|---|---|---|
| Coordinator rulings | A coordinator rules on a question that stakes a rule, and files it ("Ruling: coordinator ... The owner may rule otherwise", decision `plan-needs-critic`). | A rule changes with no owner word, and every repo copies it. | 14 such rulings in 9 decision files on main (measured), so under 2 a day | Opus: nobody reads it | each coordinator ruling checked: owner's call or not |
| Test re-point | A builder re-points a failing test to the new behaviour, but the test had found a defect (`outcomes-tests-are-statements`). | The defect ships under a green check. | commits that say "re-point": 2 to 43 a day, 11-01 to 11-06 (proxy) | Sonnet: the reviewer also reads the diff | each re-point shown to hide no defect |
| False-alarm claim | A session reads a refusal as a false alarm and routes around it (`verification-cry-wolf-guard-is-spent`). | The guarded act happens. | commits that say "false alarm": 1 to 14 a day, 11-01 to 11-05 (proxy) | Opus: the act is past the guard | each route-around argued against the guard's record |
| Stale-decision claim | A session calls a decision stale to get past it (`outcomes-stale-decision-protocol`). | The owner grants the removal of a live protection on a one-sided case. | covered by challenger-page-against when the proposal goes on the page | none new | the case for the decision on the page |

Each new place needs its own owner pick. This record proposes them. It adopts none.

## 3. The owner question

**Ruling.** Owner, 2026-11-06 13:59 CST, waiting-page item 289 (which refuters run Opus): "none of these
(for now let's do sonnet for all)". The owner picked none of options a, b and c. For now, the three item-284
agents that argue back (case against the pick, ruling-skip check, done-check read) run Sonnet, at brief time and
at step close. Each takes its own Sonnet row in decision `agent-model-cap` when its lane lands. The `refuter` row
on Opus stays the plan refuter's alone (item 279, pick d).
The coordinator relayed the answer at 14:00 CST. The answer file was not yet on the record branch.
The picks in section 1 stand as the case argued, not as the ruling. The places in section 2 stay proposed only.

The question as sent, 2026-11-06:

Goal: each refuter runs the model its stakes need (your note on item 284).
Problem (money): Opus costs more per call, and decision agent-model-cap lets only its named roles run Opus, so a refuter on Opus needs your word.
Based on (measured): page decision items 6 to 51 a day (median 22); steps closed 4 to 33 a day; ruling skips unmeasured.
Based on (ruling): item 279 pick d put the plan refuter on Opus; Sonnet is the ceiling for every other role.
Based on (read): the Opus question reviewer already reads every page question.
Departs from: main agent-model-cap has no row for the three item-284 refuters — adds a row for each, on the model you pick.

- **a. Opus where nobody else reads the verdict (recommended).** The ruling-skip check and the done-check
  read at step close run Opus. The case against the pick and the done-check read at brief time run Sonnet.
  Gain: the two verdicts that no one else sees get the strongest read. Lose: about 4 to 43 Opus calls a day
  (closes measured, skips assumed under 10).
- **b. Opus for all three.** Gain: the strongest read at every place. Lose: the case against each page
  question (6 to 51 a day) and each lane brief (25 to 104 a day) also run Opus.
- **c. Sonnet for all three, as item 284 was written.** Gain: the lowest cost. Lose: a stretched ruling or a
  weak done-check passes on one Sonnet read, with no other reader.

## Risks

- Name drift: `plan-needs-critic` on lane step-done-needs-check cites `CHALLENGER_ROLE`. Lane
  blind-plan-refuter renamed it `REFUTER_ROLE`. Lane reviewer-brief-blind still says `challenger`. Merged out
  of order, the check reads a name that is gone.
- The `Critic:` line here names no refuter. It fails `lint/check_plan_critic.py` once that check requires
  the refuter role (coordinator, 2026-11-06 12:56 CST), unless a refuter reads this plan first.

Kind: process
Home: docs/decisions/agent-model-cap.md
