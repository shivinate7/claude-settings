# Some list markers set a content column wrongly

- **What.** Some list markers that CommonMark does not open still set a content column. Examples: `* * *`, and `2.` after a paragraph line.
- **Where.** The list-marker check in `actions/stamp/stamp.mjs`.
- **Decision.** `stamp-cite-near-miss` (the stamp cite near-miss check).
- **Retire.** Match the CommonMark list-opening rule. A test per example sets no content column.
