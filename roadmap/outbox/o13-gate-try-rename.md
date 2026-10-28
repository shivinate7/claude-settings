# o13 lane A: the gate/try rename (redo of PR #639)

- Status (Oct 28 08:50 UTC, step o13): draft PR #746 (replaces #639) has head 9d634c75, which includes main 4e913588 (batch 4).
  - Three review rounds passed: round 1 reviewer opus, rounds 2 and 3 reviewer sonnet. Round 3's net-value test is positive: one act is newly refused and no safety hole is opened.
  - The local checks are green, except the load-brake probe case, which is red on main too.
  - Batch 4 brought `gates` names into merge/merge.py. They are renamed to `checks` (commit 77a5993e).
  - The PR merges alone after batch 5, with shiv's protection switch (waiting-page item 33).
