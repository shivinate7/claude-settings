# A process record keeps a Plan line that no check reads

- **What.** The record mods-tests-run-in-gates is `Kind: process`, but it also holds a `Plan:` line. The Kind check ignores a Plan line on a process record, so the line is dead text that reads like a build plan. The Edit judge refused to delete it under the rule that a ruling declares its kind.
- **Where.** `decisions/mods-tests-run-in-gates.md`, lines 51-53; `lint/check_ruling_kind.py`, lines 125-130.
- **Decision.** `mods-tests-run-in-gates` (mod tests run in the gates job).
- **Retire.** Delete the Plan line, or make the Kind check refuse a Plan line on a process record. A record with both then fails the check.
