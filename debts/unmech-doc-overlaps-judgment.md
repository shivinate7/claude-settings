# The unmechanized docstring in rule_audit overlaps the judgment kind

- **What.** The module docstring of `lint/rule_audit.py` says an `unmechanized` rule "genuinely cannot be checked by a machine". The new `judgment` kind holds that case. A reader cannot tell the two kinds apart.
- **Where.** The `unmechanized` bullet in the docstring of `lint/rule_audit.py`.
- **Decision.** `claude-md-shrink` (CLAUDE.md drops the prose of a rule that a guard or gate enforces).
- **Retire.** The bullet says `unmechanized` is a rule that a check could still cover, and only `judgment` says "cannot be checked". The text "genuinely cannot be checked by a machine" no longer appears under `unmechanized`.
