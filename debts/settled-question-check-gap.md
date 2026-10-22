# No hook checks for a question that a record settles

- **What.** A question that a decision or a debt already settles can reach the owner. The advisor session holds this check. With no advisor running, no check runs.
- **Where.** The AskUserQuestion agent hook in `settings.json`. It judges the box alone and has no Read allow rule, so it cannot read `decisions/` or `debts/`.
- **Decision.** `advisor-answers-questions` (sessions ask the advisor first).
- **Retire.** A hook checks each question against `decisions/` and `debts/`, shown by a test that sends back a question a decision settles. Or the owner rules the advisor's check enough. Then delete this file.
