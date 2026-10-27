# Build advisor outbox

- c91 (one iOS standard): the c91 part 1 lane (PR #666) found that the standard's "slow tests once per batch on the Mac through bin/sim-test" contradicts home-app's CLAUDE.md rule that iPhone tests run in GitHub CI only. The c91 repo visit must settle it with shiv. Note for the step; no new step.
- c88 (a CI wait never sleeps): measured Oct 27, a red batch run's ci-done comment on PR #663 woke the watching build advisor (queued 02:13:23Z, arrived 02:15:10Z), about 3 minutes after the check_run event. Note for the step.
- Close or update, batch #663 merged Oct 27 03:09 UTC as main 1733dac (ten lanes): o13 lane B (#640), c89 part 1 sim-test (#653), c69 follow-up no lane full CI (#654), c93 gold column (#655), o17 todo kind (#656), o2 cite guard (#657), o18 ux/ to docs/design/ (#658), c97 merge needs current main (#659), c98 fewer messages (#660), d10 designer lane kinds (#661). Lane PRs closed as replaced.
- c88 (#651) was dropped from #663 after run 3 (its test imported PyYAML, which CI lacks); its lane fixed it and joins the next batch. o13 lane C (#638) left out (30 conflicts); it re-merges main 1733dac.
- Batch #667 (c86 #665, c91 part 1 #666, c99 #662) is in CI on main 1733dac.
- Finding for the batch rules (git-integration-branch-merge): dropping a lane with `git revert -m 1` of its merge leaves the revert on main, so the lane's later merge of main silently deletes the lane's files (c88, Oct 27: only 2 of 13 files showed as conflicts). The c88 lane re-applied its diff (acd0882). A drop should rebuild the batch without the lane, or the lane must re-apply after merging main. Candidate step: the merge tool or a rule names the safe drop.
- Close or update, batch #667 merged Oct 27 03:38 UTC as main 835cde5: c86 question-box check (#665), c91 part 1 iOS standard (#666; c91 parts after 1 stay), c99 waiting-page save wake (#662).
- Batch #668 (c88 alone, #651) is in CI on main 835cde5.
