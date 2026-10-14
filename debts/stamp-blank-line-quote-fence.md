# A blank line does not end a quoted fence

- **What.** A blank line with no `>` inside a quoted fence does not end the quote.
- **Where.** The quote scan in `actions/stamp/stamp.mjs`.
- **Decision.** `stamp-cite-near-miss` (the stamp cite near-miss check).
- **Retire.** End the quote at a blank line with no `>`. A test with that blank line closes the quote.
