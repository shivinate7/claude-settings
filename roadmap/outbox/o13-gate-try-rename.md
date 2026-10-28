# o13 lane A: the gate/try rename (redo of PR #639)

- Status (Oct 28): branch `o13-gate-try-rename` starts at main 0fb91de. An Opus builder runs. The reviewer has not started.
- Interpretation (step o13): the brief says "do not change stamp.json's required list on main". The failure class says to rename the required checks in stamp.json too. So the lane changes stamp.json only on its own branch, as #639 did, and the PR body lists the old and new names so the batch merge can switch protection.
- Resume: read the brief at origin/roadmap:briefs/o13-laneA-gate-try-rename.md, then the branch head.
