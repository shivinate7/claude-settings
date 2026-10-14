# A > inside a comment ends the mask early

- **What.** A comment that holds `>` ends its mask early. Example: `<!-- a > b -->`. The rest of the comment is then read as text.
- **Where.** The comment mask in `lint/ste_gate.py`.
- **Decision.** `ste-gate-fixes-not-nags` (the STE gate fixes text, not nags).
- **Retire.** Mask the comment up to its closing `-->`. A test with `<!-- a > b -->` keeps the whole comment masked.
