# The comment rule is unmeasured on quoting shapes

- **What.** The comment rule is unmeasured against every quoting shape a real shell accepts. This gap predates the fix that closed the two found bypasses.
- **Where.** `split_segments` in `hooks/guard.py`.
- **Decision.** `split-segments-comment-rule` (split_segments needs the shell's comment rule).
- **Retire.** Run a list of quoting shapes through the real shell. Pin each shape that the reader must match.
