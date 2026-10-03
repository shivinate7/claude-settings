# Docs-only pull requests skip the reviewer

## The ruling, 2026-09-26

The owner said there is no need for a review on a change that is so simple. The case was
the README rewrite in PR 142.

A pull request that changes only prose or docs, and touches no rule, gate, or product
code, gets no reviewer pass. Report its PR and its CI verdict. A change that can move a
verdict still gets a reviewer. `rule:roles-solo-reviews-logic-diffs-only` says the same for
solo mode. This entry extends it to orchestrate mode.
