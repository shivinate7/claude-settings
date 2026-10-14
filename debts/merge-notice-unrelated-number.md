# A digit in the reply can suppress a real merge notice

- **What.** A reply's blockquote can hold digits that match a merged PR's number for an unrelated reason. A commit SHA fragment, a port number or another PR's number nearby can supply them. `already_named` requires the number to follow `#` or `PR`. A `PR 75` elsewhere in the block still suppresses a real, unnamed merge of PR 75. Nothing checks that the mention refers to the merge the hook names.
- **Where.** `already_named` and `block_text` in the merge notice path of `hooks/decision_watch.py`.
- **Decision.** `merge-notice-checks-the-report` (the merge notice is a check, not a reminder).
- **Retire.** The notice matches a mention to the merge's own PR. A case with `PR 75` elsewhere still fires for a real merge of PR 75.
