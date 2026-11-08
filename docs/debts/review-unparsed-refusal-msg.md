# Unparsed review record gets a vague refusal

**What.** A review record comment with text added below the lines `merge --review-record` prints does not parse: `parse_review` returns None for it. `merge --fix-check` then refuses with "the reviewed head must be the Head of the newest earlier review record…" and does not say that record failed to parse, so a session had to call `parse_review` by hand to find the cause. The refusal caught the mistake. Seen in lane `judge-no-readable-verdict`, 2026-11-08.

**Where.** `merge/merge.py`, `main`, the `--fix-check` branch under `--review-record`. It parses each earlier body from `review_comments` with `parse_review` and takes the last. A None there gives the generic refusal. `merge --reviewed` already marks a newest record that does not parse as bad.

**Decision.** `pr-review-record`, review record rules.

**Retire.** Closed when a case in `merge/test_merge.py` puts text below the lines `--review-record` prints. The case runs `--fix-check` on that record and gets a refusal that names the review record that did not parse. That case is not written yet.
