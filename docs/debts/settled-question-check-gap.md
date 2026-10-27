# No hook checks for a question that a record settles

- **What.** A question that a decision or a debt already settles can reach the owner. No check runs.
- **Where.** The AskUserQuestion agent hook in `settings.json`. It judges the box alone and has no Read allow rule, so it cannot read `docs/decisions/` or `docs/debts/`.
- **Decision.** `questions-go-to-owner` (questions go to the owner).
- **Retire.** A hook checks each question against `docs/decisions/` and `docs/debts/`, shown by a test that sends back a question a decision settles. Then delete this file.
