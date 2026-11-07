# The posted check reads a comment someone else left as Claude's own post

**What.** The posted-comment check reads "left" as Claude's own post, so a line about a reviewer's comment refuses: "Fixed the comment the reviewer left on #1500.", "The owner left a comment on #1500; fixed in abc1234." A session that fixes PR review comments can write such a line. Each hit costs one reword.

**Where.** `_claims_posted` in `lint/report_guard.py`, the `left` branch (rule `posted-needs-comment-url`).

**Decision.** `posted-needs-comment-url` (a reply line that claims a posted PR comment cites its URL).

**Retire.** `left` counts only when no other actor is its subject, shown by a case in `lint/test_report_guard.py` where "The owner left a comment on #1500" passes.
