---
id: pending
slug: review-record-hand-form
---

# A review log comment must be one the merge tool reads, and name a commit that exists

## The ruling

Coordinator brief for the lane that builds PR #3634, 2026-11-18. The guard judges the two GitHub comment tools, add and update, when the body's first line is exactly the review log marker.

- Rule `review-record-form`: refused when `parse_review` in `merge/merge.py` returns None for the body. The reason names `merge N --review-record --head SHA ...` as the one source of review log text. <!-- glossary-ok: the rule id is fixed by its cases -->
- Rule `review-record-sha`: refused when a 40-hex sha on a `Head:` or `Fix check:` line does not resolve with `git cat-file -e <sha>^{commit}` in the call's checkout. <!-- glossary-ok: the rule id is fixed by its cases -->
- A check that cannot run allows: no git on PATH, no git tree at the call's folder, or a merge tool that does not load.
- A body with no marker is no review log. Neither rule judges it.

The form has one home, `merge/merge.py` (decision `pr-review-record`, a pull request carries its review log). The guard imports `parse_review`, `REVIEW_MARKER` and `REVIEW_SHA` from it and copies none of them.

Mistake: a session typed a review log by hand, in a form `parse_review` refuses (a Kind in free text, a round with no role, a rounds summary line, a free-text Fix check line, or the marker alone). Another session wrote a sha it had made up from the first ten characters of a real one.

Harm: the merge tool reads no review log from the PR, so the merge stops on a PR that was reviewed. A made-up sha records a review of a head that never existed, which is a false record.

Cost: the merge tool loads once per guard process, and only for a call to one of the two comment tools. A body with no marker runs no git. A body with the marker runs one `git rev-parse` and one `git cat-file` per distinct sha. No file is written and no process stays running.

Why: the merge tool already prints a review log in the one readable form, so a hand-typed body adds only the chance of error. The guard refuses at the post, where the session can still fix it, not at the merge.

Kind: process
Home: hooks/guard_review_log.py
