# Build advisor outbox

- c91 (one iOS standard): the c91 part 1 lane (PR #666) found that the standard's "slow tests once per batch on the Mac through bin/sim-test" contradicts home-app's CLAUDE.md rule that iPhone tests run in GitHub CI only. The c91 repo visit must settle it with shiv. Note for the step; no new step.
- c88 (a CI wait never sleeps): measured Oct 27, a red batch run's ci-done comment on PR #663 woke the watching build advisor (queued 02:13:23Z, arrived 02:15:10Z), about 3 minutes after the check_run event. Note for the step.
