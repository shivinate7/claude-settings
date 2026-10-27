# Scorecard can put an item under the wrong group

- **What.** The probes print item lines before their group line, and the skill writes them after it. `scorecard` holds the items and gives them to the next group line only when that name is a lower-case probe key. So skill-order input with a lower-case group name, such as `layout: partial - x (a:1)`, then `  - extras: gap - none (f)`, then `design: out - bad (c)`, gives the row `design: extras`, and layout gets no item.
- **Where.** `scorecard` in `lint/compliance_probes.py`, and section 4 of `skills/compliance-check/SKILL.md`.
- **Decision.** none
- **Retire.** The code finds the input order, or one order is the only order the skill writes. A test that feeds the input above gets the row `layout: extras`.
