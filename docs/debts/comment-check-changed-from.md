# Comment check flags change-detection comments

- **What.** The comment check flags "changed from the previous/original/old …" as history. A why-comment on change-detection code uses the same words, such as "true if the hash changed from the previous snapshot". Claude writes such comments in normal work, and each hit turns code-check red in every pinning repo until the comment is reworded.
- **Where.** The "history phrase" pattern in `lint/check_comment_narration.py`, the `changed from the (old|previous|original|former)` form.
- **Decision.** None. Rule `building-comments-say-why` (a comment says what and why, never history).
- **Retire.** The pattern tells a history line from a change-detection line, or a suppression marker exists, and a CLEAN case pins "changed from the previous snapshot".
