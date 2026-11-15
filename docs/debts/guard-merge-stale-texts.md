# Guard texts name the removed wait and the bare merge run

**What.** Two texts in `hooks/guard_merge.py` are stale. The header (line 38) says the merge tool runs its own `gh pr merge` as a subprocess. The tool now sends `PUT pulls/<n>/merge` with the head sha as its guard. The `merge-checks` remedy (about line 217) says `--confirm` "waits on the required checks". `confirm` has no wait under the lock.

**Where.** `hooks/guard_merge.py`, the header comment (lines 37 to 39) and the `merge-checks` remedy (about lines 215 to 218).

**Decision.** `merge-needs-current-base` (the head is green on its own base and merges cleanly with the base tip).

**Retire.** Reword both texts to the one-read green check and the `PUT`. Check: a case in `hooks/test_guard.py` that reads the remedy and finds no "waits on the required checks". Red on the current text, green after the fix.
