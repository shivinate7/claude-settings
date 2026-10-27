# Docs-only pull requests skip the reviewer

## The ruling

Owner, 2026-09-26: a pull request that changes only prose or docs, and touches no rule, guard or product code, gets no reviewer pass. Report its PR and its CI verdict. A change that can move a verdict still gets a reviewer.

Why: a review of a change that simple is wasted. `roles-solo-reviews-logic-diffs-only` says the same for solo mode. This record extends it to orchestrate mode.

Kind: process
Home: rule:roles-solo-reviews-logic-diffs-only
