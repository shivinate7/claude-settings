# A one-shot owner approval is asked for a home like a standing grant

- **What.** A one-shot approval, such as "go ahead and merge PR 12" or "approved, push it", counts as a grant, so the guard asks for a home. The only exits are a ruling file, which is heavy for one merge, or `not-a-grant`, which is a false label. Claude hits this in normal work. The frequency is unmeasured.
- **Where.** `grant_problem` and `GRANT_HOMES` in `hooks/feedback_guard.py`.
- **Decision.** `none`.
- **Retire.** Add a one-shot home, such as `once:<act>` or the page item. A case with "go ahead and merge PR 12" and that home passes, and the same text with no home still blocks.
