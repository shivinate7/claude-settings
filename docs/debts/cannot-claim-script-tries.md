# A failed merge tool or script call is not a try of its act

**What.** The cannot-claim check counts a try only for gh calls, git push, fetch, ls-remote and merge, curl, wget or httpie to github.com, and any `mcp__github__` tool. A failed call to the repo's merge tool (`merge 12`, exit 1) or to a repo script (`./open-pr.sh`, exit 1) is not seen as a try of pr-merge or pr-open. So a claim backed by that failure blocks as no try, such as "I can't merge PR 12, `merge 12` exited 1."

**Where.** `lint/report_guard.py`, `_segment_tries` (:1709), which lists the routes one shell segment is a try of, and `_text_acts` (:1743).

**Decision.** `claims-carry-backing`, a definitive prose claim carries its backing or a route row. Its Part (vi), What a try is, lists the routes that count.

**Retire.** Add a case to `lint/test_report_guard_cannot.py`: a failed `merge 12` call is a try of pr-merge, and a failed `./open-pr.sh` call is a try of pr-open. A claim backed by either then passes. The case goes red on the current check and green after the fix.
