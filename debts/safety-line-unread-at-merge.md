# Round-3 safety line is not read before a merge

- **What.** No check makes the orchestrator read the round-3 line `Safety hole vs main:` before a merge.
- **Where.** The round-3 line in `agents/reviewer.md`, and the merge step the orchestrator runs under rule `roles-review-cap-three` in `CLAUDE.md`.
- **Decision.** `hold-unsafe-after-round-3` (a change with a safety hole main lacks is held after round 3).
- **Retire.** A check that goes red when a merge follows a round-3 report whose safety line was not read. Or a check that reads the line before the merge.
