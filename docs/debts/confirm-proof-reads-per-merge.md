# A confirm under "none" reads the head's checks on every merge

- **What.** A confirm under merge.requiredChecks "none" on a base with a CI workflow reads the head's checks, statuses and runs: 3 GitHub reads (one page each), or 6 when the proof is carried from a page or clean-merge commit. It read none before. Claude meets it on every merge.
- **Where.** `merge/merge.py` `confirm`, the head-checks block (`needs_proof`).
- **Decision.** `merge-needs-current-base` (the proof rule under "none" with a workflow, and its Cost line).
- **Retire.** Close when the reads are cut, or measured and the decision's Cost line states the count. Test: `merge/test_merge.py`.
