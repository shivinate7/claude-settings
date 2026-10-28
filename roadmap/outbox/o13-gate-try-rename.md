# o13 lane A: the gate/try rename (redo of PR #639)

- Status (Oct 28): draft PR #746 replaces #639. Head 587d7e01 is pushed and includes main b09aecee. Review round 1 (reviewer opus) passed, and round 2 (reviewer sonnet) on the main merge passed with no findings. The local checks are green, except four steps that are red on main too (the load-brake probe case, test_handoff_wave2, githooks main-ref, install_from_main case 8). It is waiting for its own batch after batch 3 (#735).
- Merge plan (round 1 finding, for the batch merge): merge.py reads stamp.json from origin/main, so it waits for the old gates* checks on this head. Switch branch protection and stamp.json in the merge act, or merge outside merge.py on shiv's grant. The PR body lists the old and new names.
- Sunset date: note try-marker-sunset says 2026-11-12, which is 14 days after a merge on Oct 29. Move the date if the merge slips.
- Transitional (step o13): briefs written before the merge say `bin/ci-job gates`. After the merge, the name is `checks`.
- Resume: read PR #746's body, then the branch head.
