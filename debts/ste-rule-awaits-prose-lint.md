# The STE rule waits for the plain-prose lint

- **What.** Its gate judges only file writes. Replies, briefs and agent messages are unchecked. The owner moved the rule to its own lane.
- **Where.** Rule `output-write-in-ste`, root `CLAUDE.md`.
- **Decision.** `claude-md-shrink` (CLAUDE.md drops the prose of a rule that a guard or gate enforces).
- **Retire.** The plain-prose lint lane merges and rewrites the rule.
