# Three guards have no row in the rule map

- **What.** The rows that tied the `merge-checks`, `draft-pr` and `pointer-head` guard rules to a rule left with their rules. A guard deleted with its tests now passes `lint/rule_audit.py`.
- **Where.** `lint/rule_mechanisms.json`.
- **Decision.** `claude-md-shrink` (CLAUDE.md drops the prose of a rule that a guard or gate enforces).
- **Retire.** A check ties every guard rule name in `hooks/guard*.py` to a row or to a listed exemption.
