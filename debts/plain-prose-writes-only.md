# The plain-prose rule is checked on file writes only

- **What.** The gate and the sweep judge file writes. Replies, briefs and agent messages are unchecked.
- **Where.** Rule `output-write-in-ste`, root `CLAUDE.md`. `lint/ste_gate.py` and `lint/md_sweep.py`.
- **Decision.** `plain-prose-lint` (the STE lint becomes a plain-prose lint).
- **Retire.** The writing standard moves into agent briefs (deferred item `ste-into-agent-briefs`) and the owner rules the rule's row. Or a check reads replies and briefs.
