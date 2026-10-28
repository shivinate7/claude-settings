# c154-cloud-handoff-hooks

Step c154: cloud installs keep the hand-off start-up hooks.

- Finding: install.sh cloud branch replaced `.hooks.SessionStart` with the refresh hook alone. No decision record covered it; its "stays hook-free" comment was stale. Ruled a defect.
- Done: refresh hook now appended after the repo's SessionStart hooks; comment rewritten. Head 9f5ab95. Draft PR #726 (cloud installs keep the hand-off start-up hooks).
- Tests: cloud_settings1 red on old install.sh, green now; `verdict bash hooks/test_install_src.sh` PASS; `verdict ste-changed origin/main` PASS.
- Review: opus reviewer, round 1, CLEAR. Builder opus.
- Note (not a debt): cloud_settings1 false-reds if settings.json ever has no SessionStart key (`null` vs `[]`); fix is `.hooks.SessionStart // []` in its `want`.
- State: waiting on the orchestrator's integration batch.
