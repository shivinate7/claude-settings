# o13 lane A: the gate/try rename (redo of PR #639)

- Status (Oct 28 08:50 UTC, step o13): draft PR #746 (replaces #639) has head 9d634c75, which includes main 4e913588 (batch 4).
  - Three review rounds passed: round 1 reviewer opus, rounds 2 and 3 reviewer sonnet. Round 3's net-value test is positive: one act is newly refused and no safety hole is opened.
  - The local checks are green, except the load-brake probe case, which is red on main too.
  - Batch 4 brought `gates` names into merge/merge.py. They are renamed to `checks` (commit 77a5993e).
  - The PR merges alone after batch 5, with shiv's protection switch (waiting-page item 33).
  - Paused (Oct 28 09:00 UTC): batch 5 (#754) carries step c162, which also edits merge.py and test_merge.py. After #754 lands, merge main again (merge commit), rename any new `gates` names, re-run the checks, push, then message the orchestrator.
