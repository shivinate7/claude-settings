# A check that turns red after the head read still merges

**What.** `confirm` reads the head's checks, then sends `PUT pulls/<n>/merge` with the head sha as its guard. A required check that turns red between the read and the PUT still merges. The design names this as a known limit, in the same window as main. Whether the admin-bypass PUT refuses a pending or red check is unknown.

**Where.** `merge/merge.py`, the head read in `confirm`, and the merge call `pulls/<n>/merge` (the `Host` merge method).

**Decision.** `standing-merge-grant` (the required checks must pass on the head that merges).

**Retire.** Re-read the checks after the head read and before the PUT, and refuse a red one. Or prove that the PUT refuses a red check. Check: a case in `merge/test_merge.py` where a check turns red between the reads. Red on the current code, green after the fix.
