# Three dropped filler phrases pass with no note

- **What.** `in between`, `in terms of` and `it would appear that` left `BLOAT`. The lint no longer reports them, not even as a warning.
- **Where.** `BLOAT` in `lint/ste_lint.py`.
- **Decision.** `plain-prose-lint` (the STE lint becomes a plain-prose lint), hole 8.
- **Retire.** Add the three phrases back as advisory findings, or the owner accepts the loss.
