# o13 lane A: the gate/try rename (redo of PR #639)

- Status (Oct 28 13:10 UTC, step o13): PR #746 head 345b300a (pushed, draft) includes main 26a539ff (batch 8). A fresh review of the batch 8 merge passed (reviewer sonnet). The local checks are green, except the pipx cases (no pipx in this container) and the load-brake probe case. All of them fail on main too.
- Next: the orchestrator takes #746 to shiv for the protection switch to checks* (waiting-page item 33) and marks it ready. If another batch lands first, merge main again.
