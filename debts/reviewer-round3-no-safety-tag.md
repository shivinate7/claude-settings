# Round-3 reviewer does not tag safety holes

- **What.** Round 3 of the reviewer lists open findings as named limits. It does not tell the reviewer to list a safety hole under its own heading, so the orchestrator cannot read a hold from the report.
- **Where.** `agents/reviewer.md`, the Rounds paragraph.
- **Decision.** `hold-unsafe-after-round-3` (a change with a safety hole main lacks is held after round 3).
- **Retire.** Round 3 of `agents/reviewer.md` lists safety holes under their own heading, and the orchestrator reads that heading before it merges. A check that fails when a round-3 report puts a safety hole under another heading.
