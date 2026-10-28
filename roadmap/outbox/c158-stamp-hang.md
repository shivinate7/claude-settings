# c158-stamp-hang (cloud lane, Oct 28)

- c158: built and reviewed. Branch `c158-stamp-hang` head f7ec968, draft PR #735 (stamp suite watchdog), based on batch-oct28a. Builder opus (3 tries); reviewers opus, sonnet, opus; round 3 clear, net value positive.
- Fix: test_stamp.mjs re-runs itself under an out-of-process 240 s watchdog with piped stdio. On a hang it names the test, kills the tree, lists leftovers and exits 1. Every call the suite spawns has a 60 s timeout. Proof tests are red on the old code; 144 of 144 green on Linux. timeout-minutes: 5 stays as the backstop.
- Cause of the hang: unknown, does not reproduce on Linux. Candidates (unmeasured): stamp.mjs `bash -c` regenerate with inherited stdio inside the suite process; shallow `git clone --no-local file://`; git maintenance or a credential prompt. The next hang prints the test and the process tree.
- Cause of the cap miss (unmeasured): the Windows runner waited on a descendant holding the step's output pipe. Job 122632514525's log blob is gone (404), so it cannot be read.
- Not yet proven: the Windows paths (PowerShell walk, taskkill) have never run. The first windows-latest batch run is their proof. Watch gates-windows-rest on that batch.
- Notes (not debts, per round 3):
  - The proof test sets STAMP_SUITE_SWEEP=1, so on a Windows dev machine the sweep runs for a few seconds. It is limited to orphans that carry `<tmp>\stamp-test-`.
  - Worst case on a hang is 290 s against the 300 s step cap.
  - The proof's `secs < 30` includes a cold PowerShell walk (up to 20 s).
  - killOrphansOf trusts that a parent pid is not reused.
- Deviation: round 2's reviewer ran sonnet (the CLAUDE.md round-2 rule) where the lane brief said opus; round 3 ran opus.
