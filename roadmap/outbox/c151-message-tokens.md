# c151-message-tokens

- c151 step 2 is ready: draft PR #751 (the message-token hand-off nudge), head fabd2dcb, branch c151-message-tokens. It needs a batch.
- Proof: test red first, then green. `ci-job gates --lint` passes. The silent-undo check is clean. Reviews: Opus in round 1, Sonnet in round 2, both merge.
- Pre-existing failures: two "failed pointer delete" checks in hooks/test_handoff_wave2.py fail on main too, because the container runs as root.
- Notes, not debts:
  - The zero-usage first-entry test case passes either way, so it is vacuous.
  - checkpoints() keeps the 200k floor, so a top between 200k and 275k can give two rewrites under 75k apart. That needs a limit of 250k to 325k or a huge overhead.
  - The first nudge now comes later by the overhead, so a model window smaller than autoCompactWindow can skip it. The hook's code comment marks this as a known gap (`ponytail`).
