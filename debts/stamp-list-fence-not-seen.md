# A blockquote fence in a list item is not seen

- **What.** A blockquote fence inside a list item at 4 or more columns is not seen as a fence.
- **Where.** The fence scan in `actions/stamp/stamp.mjs`.
- **Decision.** `stamp-cite-near-miss` (the stamp cite near-miss check).
- **Retire.** Read list-indented fences at 4 or more columns. A test with such a fence finds it.
