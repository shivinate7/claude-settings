---
id: pending
slug: review-log-hand-form
---

# A review log comment must be one the merge tool reads, and name a commit that exists

## The ruling

Coordinator brief for the lane that builds PR #3634, 2026-11-18. The guard judges three paths that post a comment, when the body's first line starts with the review log marker (a one-line body that holds a literal backslash and n is judged too): the two GitHub comment tools (add and update), a Bash `gh pr comment` (`--body` or `-b`), and a Bash `gh api` call (a `body=` field). A Bash body is read when the command line holds it as a plain word or as a quoted heredoc (`--body "$(cat <<'EOF'` or `-F body=@-` fed by a heredoc). A body in a variable, another `$(...)` or a file (`--body-file`) is not read: a recorded limit.

- Rule `review-log-form`: refused when `parse_review` in `merge/merge.py` returns None for the body. The reason names `merge N --review-record --head SHA ...` as the one source of review log text.
- Rule `review-log-sha`: refused when a 40-hex sha on a `Head:` or `Fix check:` line does not resolve with `git cat-file -e <sha>^{commit}` in the call's checkout. The reason tells the reader to fetch the branch, since the commit may be on origin.
- Rule `review-log-sha` judges the sha only when the call's owner and repo are the checkout's origin repo, or either is unknown. A post to another repo skips the sha rule, since its commits are not in this checkout. The form rule still applies.
- A check that cannot run allows: no git on PATH, no git tree at the call's folder, or a merge tool that does not load.
- A body with no marker is no review log. Neither rule judges it.

The form has one home, `merge/merge.py` (decision `pr-review-record`, a pull request carries its review log). The guard imports `parse_review`, `REVIEW_MARKER` and `REVIEW_SHA` from it and copies none of them.

Mistake: a session typed a review log by hand, in a form `parse_review` refuses (a Kind in free text, a round with no role, a rounds summary line, a free-text Fix check line, or the marker alone). Another session wrote a sha it had made up from the first ten characters of a real one.

Harm: the merge tool reads no review log from the PR, so the merge stops on a PR that was reviewed. A made-up sha records a review of a head that never existed, which is a false record.

Cost: the merge tool loads at most once per guard process, and only for a call that posts a comment body. A body with no marker runs no git. A body with the marker runs at most one `git rev-parse`, at most one `git remote get-url` (only when the call names its repo) and at most one `git cat-file` per distinct sha. No file is written and no process stays running.

Why: the merge tool already prints a review log in the one readable form, so a hand-typed body adds only the chance of error. The guard refuses at the post, where the session can still fix it, not at the merge.

Kind: process
Home: hooks/guard_review_log.py
