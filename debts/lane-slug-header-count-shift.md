# An interpreter body or case shifts the heredoc header count

- **What.** An unquoted `<<word` in an interpreter-fed heredoc body, such as `x = 1 << y`, or a `case` `)` inside `$(`, shifts the header count.
- **Where.** `heredoc_heads` in `hooks/guard_core.py`.
- **Decision.** `lane-by-slug` (a lane is named by its branch slug, not a session number).
- **Retire.** Cases for `x = 1 << y` and for a `case` `)` inside `$(` keep the header count, and each case passes.
