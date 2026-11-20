# A reuse of a booted phone takes no lease

**What.** The sim-test reuse path takes no lease for a phone that is already booted. Two runs can then drive one phone at once. Roadmap step sim-lease-gaps (close the sim-lease and sim-test gaps) notes two runs on Duo 1 on 7 Nov. The rate is unmeasured here. Owner waiting item 336 (pick a, 12:31 CST Nov 7) rules that a reuse takes the booted phone's lease. Main still says the opposite in four places. Checked on main 2026-11-20 16:29 CST.

**Where.**
- The sim-test reuse note, `bin/sim-test` lines 8-9: "Reuse takes no lease and shuts nothing down."
- `lint/test_sim_test.sh`, case 50, lines 783-787: pins the gap.
- `skills/ios-apps/SKILL.md`, line 79 ("Boot path"): describes the gap. Line 72 on main has no reuse text. Open PR 3704 changes only that line, and is not on main.

**Decision.** `sim-lease-tool`, the one simulator queue and lease on a Mac. Its ruling 4, line 10, says the reuse path takes no lease. The fix rewrites ruling 4 in place.

**Retire.** Case 50 of `lint/test_sim_test.sh` passes on the gap today. The fix changes case 50 to expect a lease on a reuse. It goes red on main first, then green on the fix. Closed when `lint/test_sim_test.sh` passes on the fix's head.

## Ruling

Owner waiting item 336, pick a, 12:31 CST Nov 7: rewrite ruling 4 of decision `sim-lease-tool` so that a reuse takes the booted phone's lease. The waiting item is the home of this ruling, on the roadmap branch. This debt holds the ruling. It does not reopen it.
