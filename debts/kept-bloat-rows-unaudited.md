# 97 kept fix rows are not read against a corpus

- **What.** The lane read five `BLOAT` rows for meaning and removed their fix. The other 97 fixable rows were not read against a corpus. Unmeasured: how often a kept swap changes meaning. Example row: `not possible` becomes `impossible`.
- **Where.** `FIXABLE`, built from `BLOAT`, in `lint/ste_lint.py`.
- **Decision.** `plain-prose-lint` (the STE lint becomes a plain-prose lint).
- **Retire.** The fixer runs over the tracked Markdown files of this repo and one other. Each swap is read. A row that changes meaning loses its fix. The count of swaps read is recorded.
