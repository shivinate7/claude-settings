# A follow-up PR check passes any open PR

**What.** A `N, follow-up #<pr>` Findings line passes when each named PR exists and is open or merged. The check does not read whether that PR files the finding. So a follow-up that names any other open or merged PR passes, including a stacked base PR. A wrong number is a normal slip.

**Where.** `merge/merge.py`, `findings_read`.

**Decision.** `pr-review-record` (the review record form and its Findings check).

**Retire.** The follow-up check passes a named PR only when that PR files a finding of this record. Check: `merge/test_merge.py`, with a case that names an open PR which files no finding. Red on the current code, green after the fix.
