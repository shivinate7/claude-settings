# A record that files an owner ruling is not checked for its Kind

- **What.** The merge tool takes the lane's Kind claim. A PR that adds or edits a record that files an owner ruling, posted as `Kind: docs-only` with zero rounds, reads done with no review round. Lanes pick docs-only for prose PRs under the 2026-09-26 ruling. How often a ruling PR gets that kind is unmeasured.
- **Where.** The Kind field of the review record, read by `merge/merge.py` (`review_state`). No check reads the diff's paths against Kind.
- **Decision.** `docs-only-prs-skip-review` (docs-only PRs skip the reviewer, except a record that files an owner ruling).
- **Retire.** A check that fails a `Kind: docs-only` review record when the diff files a record that files an owner ruling. Its test shows the case red on the current merge tool, then green.
