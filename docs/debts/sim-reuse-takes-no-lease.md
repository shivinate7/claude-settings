# A reuse of a booted phone takes no lease

**What.** The sim-test reuse path takes no lease for a phone that is already booted. Two runs can then drive one phone at once. Roadmap step sim-lease-gaps (close the sim-lease and sim-test gaps) notes two runs on Duo 1 on 7 Nov. The rate is unmeasured here. Owner waiting item 336 (pick a, 12:31 CST Nov 7) rules that a reuse takes the booted phone's lease. Main still says the opposite in four places. Checked on main 2026-11-20 16:29 CST.

**Where.**
- The sim-test reuse note, `bin/sim-test` lines 8-9: "Reuse takes no lease and shuts nothing down."
- `lint/test_sim_test.sh`, case 50, lines 783-787: pins the gap.
- `skills/ios-apps/SKILL.md`, line 79 ("Boot path"): describes the gap. Line 72 on main has no reuse text. Open PR 3704 (ios-apps skill: a reuse takes its lease) changes only that line, and is not on main.

**Decision.** `sim-lease-tool`, the one simulator queue and lease on a Mac. Its ruling 4, line 10, says the reuse path takes no lease. The fix rewrites ruling 4 in place.

**Retire.** Case 50 of `lint/test_sim_test.sh` passes on the gap today. The fix rewrites case 50 to expect a lease on a reuse. The rewritten case goes red on the gap first, then green on the fix. Until then, this Retire test passes with the gap in place. Closed when `lint/test_sim_test.sh` passes on the fix's head.

## Ruling

Owner waiting item 336, pick a, 12:31 CST Nov 7: rewrite ruling 4 of decision `sim-lease-tool` so that a reuse takes the booted phone's lease. This debt is the deferred home of this ruling until ruling 4 of `sim-lease-tool` is rewritten. The waiting item, on the roadmap branch, names step sim-lease-gaps as its home. This debt holds the ruling. It does not reopen it.
