# Outcomes review of the next-coordinator plan

Opus review, 2026-11-02 13:50 CST, of branch handoff/next-coordinator (baaa19dd) against the owner's outcomes. Read: the three handoff files, the coordinator handoff and its inbox owner blocks, 4 of 25 lane handoffs. The waiting page was not read.

## Point

10 of the 15 lanes serve an owner ask; parts of 3 stray. The churn has three causes: agent-drafted text lands as the owner's ruling; each owner message lands as its own PR; child repos copy rule text instead of citing it.

## Premise corrections

- #1061 is already closed as replaced (13:38 CST); lane 15's step is moot.
- #1104 and #1105 exist; their round-1 reviewer ran Haiku, below the role's model. Re-review on Sonnet before a batch.
- fb-1338-1 (13:38 CST, mechanize one-home-per-capability both ways) is in no lane: add it (roadmap step one-home-check).
- Unknown from these sources: the source of the waiting-data-in-repo hold (owner, 11:00 CST, typed to runner 7), tci-1's source, item 153's answer.

## Lanes (ON = on outcome, SUP = support, STRAY = straying)

1. report-guard: ON (owner Nov 1 23:26 CST "this problem needs to be solved"; 18:48 CST vetting).
2. other-clone refusal: SUP (banchi #1003 waits on it); cites no owner ruling.
3. branch cleanup: ON (Nov 2 10:41 CST items 3.1, 3.3, 3.4).
4. tier boundaries: ON (Oct 31 15:32 CDT; Nov 1 21:34 CST). Width of #1042 unknown.
5. red-main merge fix: SUP, gated on item 166; lane and coordinator recommend opposite answers.
6. lane undo check: ON (10:41 item 1; 10:52 "One excuse line"). STRAY part: the pending "two shapes" narrowing departs from the owner's words.
7. prose records: ON (13:10 time zone; 13:22 drop STE; item 109 rotation text).
8. child repos cite records: ON (10:41 item 2), plus decision rulings-land-once-per-sitting (item 2.2), which the plan's goal line omits.
9. survive an account switch: ON, owner hold (11:49 CST).
10. Cockpit title: ON (11:12 CST).
11. child-repo merges: ON. STRAY part: "one runner per two repos at most" is a guessed cap (rule parallelism-no-guessed-lane-cap).
12. pins and tci-1: SUP for pins (Nov 1 17:26 CST "go ahead"); tci-1 has no source.
13. session reach: ON as one probe (Nov 1 18:19, 22:52 CST); merge the two plans (O7).
14. waiting plans: ON as parked plans (shivpedia sign-off first, Nov 1 21:07 CST; plugin assessment 21:32 CST). No session.
15. close and clean: SUP; only item 170 is left.

## Findings, by class

- Fact fixes, keep: C1-C6, O6, O8, S8, A7, A8 (C2 already done).
- Ordering, keep: O1, S1, O2, S2, O4, O5, O7, S5, S6, S9, S3 (S3 merges three owner items into one).
- Already ruled; cite, do not ask: A1 (item 109, Nov 1 17:56 CST), A4 (fb-1231-1 "a point that loses no work"), A5 (a template line).
- STRAY: O3, S4, S7, A3, A6 (A6 adds a merge refusal with no incident: rule building-guard-needs-incident). A2 re-argues the owner's 12:42 CST "or just do the triaging yourself". C7 is a fair owner item.

## Reversals and their causes

1. Merge grant rewritten three times, Nov 1 19:19-21:34 CST (commits 0c64f505, 4fe5c2c1, 74484807, bb9091b4). banchi and degen CLAUDE.md still say the coordinator merges. Causes: one PR per message; copied text.
2. Idle compaction off, on, off within an hour (owner, 10:41). Cause: per-message landing.
3. Agent text in the owner's voice: the trust-card guard in the Oct 31 seed brief ("what's this? I don't remember", 14:49 CDT); `Removes:` ("the advisor's word, not mine", 10:52 CST).
4. The advisor retired, then demanded back (Nov 1 18:45, 18:48 CST). Cause: the outcome it protected was dropped with no replacement.
5. Rotation: item 109 says compact in place, but sessions still respawned (12:29 CST). Cause: a ruling with no check.
6. The inbox fix lane started without the owner (Oct 31 15:16 CDT "You didn't even ask me"). Cause: an agent took the owner's choice.
7. The coordinator did other tiers' work (Oct 31 15:31 CDT; Nov 1 21:34 CST). Cause: a prose ruling with no check.
8. Overlapping batches (Nov 1 20:54 CST); STE dropped but not carried to the roots (13:35 CST).
9. Two sessions on one question: item 161; item 153; #1070 and trial tz built the same check; the sim-lease plan reversed itself 3 times in 18 minutes (13:28-13:46 CST).
10. At 12:31 CST ten lanes stopped before their work landed (A4).

## For the next coordinator

- Freeze: no new rule, guard or process record until lanes 8, 1 and 6 merge, except owner rulings. Land each sitting's rulings as one rewrite. Label agent-drafted text as agent text.
- Cut: the two-repo cap; A2 and A6; lane 15's #1061 step; the trials as build sources; tci-1 until it has a source.
- Lane 6's narrowing: bring it to the owner once, with the measured sweep (16 of 31 batches red), under outcomes-stale-decision-protocol.
- Merge lanes 5, 11 and 12 into one chain behind item 166. Lanes 13 and 14 become plans with no session. The surviving owner-ruling findings (O3, S4, A3, C7) go on one page item.
- Before any lane: restart triage, then the batch runner.
- First lanes, in order: lane 8 (#1098) with fb-1338-1; batch 70 (#1100, then #1104 and #1105 after re-review); lane 1 slice 1a (#1070); lane 6 at the owner's wording; lane 2, then lane 3a.
