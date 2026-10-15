# The heredoc header reader has thin tests and no mutant

- **What.** No test pins a `#` inside a string, a lone apostrophe in a comment, or multi-line quoted text before a header. The code handles them. No mutant covers `heredoc_heads` or the gh flag value roles.
- **Where.** `heredoc_heads` in `hooks/guard_core.py`, and the cases in `hooks/test_guard.py`.
- **Decision.** `lane-by-slug` (a lane is named by its branch slug, not a session number).
- **Retire.** A case for each form passes, and a mutant of `heredoc_heads` and a mutant of the gh flag roles each go red.
