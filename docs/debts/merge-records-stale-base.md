# Merge reports a stale base too late

**What.** `bin/merge` rebuilds the records page after the CI wait. On a lane based on an old main, that rebuild clashes with main. It then reports "went DIRTY during the wait". Claude is likely to hit this, because lanes often sit on an older main. The report should say "merge main first", and it should say it before the push.

**Where.** `merge/merge.py`, the records-page rebuild and the DIRTY report after the wait.

**Decision.** none.

**Retire.** Before it pushes, `bin/merge` checks that the lane holds main's tip, or merges cleanly with it. If not, it stops and says "merge main first". A merge test adds a lane on an old main. It is red now, and green when the stop comes before the push.
