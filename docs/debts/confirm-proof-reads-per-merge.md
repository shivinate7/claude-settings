# A confirm under "first-proof" reads the head's checks on every merge

- **What.** A confirm under merge.requiredChecks "first-proof" reads the head's check runs, commit statuses and workflow runs: 3 GitHub reads per head read (one page each), or 6 when the proof is carried from a page or clean-merge commit (4 measured in the fake, 6 by code). "none" reads none (measured by the builder: 0). Claude meets it on every merge.
- **Where.** `merge/merge.py` `confirm`, the head-checks block (`needs_proof`).
- **Decision.** `merge-needs-current-base` (the proof rule under "first-proof", and its Cost line).
- **Retire.** Close when the reads are cut, or measured and the decision's Cost line states the count. Test: `merge/test_merge.py`.
