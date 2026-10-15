# The near-miss scan reads frontmatter and link targets

- **What.** The near-miss scan does not skip frontmatter or link targets.
- **Where.** The near-miss scan in `actions/stamp/stamp.mjs`.
- **Decision.** `stamp-cite-near-miss` (the stamp cite near-miss check).
- **Retire.** Skip frontmatter and link targets in the scan. A test with a near miss in each gives no report.
