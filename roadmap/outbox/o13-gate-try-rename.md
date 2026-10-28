# o13 lane A: the gate/try rename (redo of PR #639)

- Status (Oct 28): the branch `o13-gate-try-rename` head ae0acd26 is pushed. The builder (opus) is done. Review round 1 (reviewer opus) passed with no blocking finding. The builder is now merging main b09aecee, which conflicts with main's step-up guard change (Workflow agent() calls, commits 72bfb8bc and de8741f4).
- Merge plan (round 1 finding, for the batch merge): merge.py reads stamp.json from origin/main, so it waits for the old gates* checks on this head. Switch branch protection and stamp.json in the merge act, or merge outside merge.py on shiv's grant.
- Transitional (step o13): briefs written before the merge say `bin/ci-job gates`. After the merge that command fails, and `checks` is the new name.
- Interpretation (step o13): the lane changes stamp.json only on its own branch. The PR body lists the old and new required check names.
- Resume: read the brief at origin/roadmap:briefs/o13-laneA-gate-try-rename.md, then the branch head.
