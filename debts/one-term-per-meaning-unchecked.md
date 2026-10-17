# No check reads "one term per meaning"

- **What.** Rule `output-write-in-ste` says "one term per meaning". The gate covers sentence length and filler only. The rule STE019 (terminology drift) was deleted, so nothing reads that clause.
- **Where.** Rule `output-write-in-ste`, root `CLAUDE.md`. Its row in `lint/rule_mechanisms.json`.
- **Decision.** `plain-prose-lint` (the STE lint becomes a plain-prose lint).
- **Retire.** A check reads the clause, or the owner rules that the clause is a judgment and the row changes kind.
