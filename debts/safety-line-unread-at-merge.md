# Round-3 net-value line is not read before a merge

- **What.** No check makes the orchestrator read the round-3 line `Net safety value:` before a merge.
- **Where.** The round-3 lines in `agents/reviewer.md`, and the merge step the orchestrator runs under rule `roles-review-cap-three` in `CLAUDE.md`.
- **Decision.** `hold-unsafe-after-round-3` (after round 3, a change with zero or negative net safety value is held).
- **Retire.** A check that goes red when a merge follows a round-3 report whose net-value line was not read. Or a check that reads the line before the merge.
