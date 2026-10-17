# A re-kind to judgment leaves the waiting list

- **What.** An `unmechanized` rule waits for a check. A move to `judgment` takes it off that list. Only the 8-word reason floor and a change to both pins in one commit stand in the way.
- **Where.** `lint/rule_audit.py`, the reason check and the two pins.
- **Decision.** `claude-md-shrink` (CLAUDE.md drops the prose of a rule that a guard or gate enforces).
- **Retire.** A check refuses a move to `judgment` without one of two things. The reason says why no check can judge the rule, or the commit cites the owner's word.
