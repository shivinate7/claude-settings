# The round-order rule counts every PR a brief cites

**What.** Rule `review-rounds-in-order` takes every pull request number in a brief as the PR under review. A `Round 2 of 3` brief for one PR that cites another PR is refused while the cited PR's first-round reviewer runs. Stacked PRs cite their base, so this false alarm is likely. Found by review round 1 of PR 2158, 2026-11-08.

**Where.** `hooks/guard.py` `round_order_hit`, `_PR_NUMBER`.

**Decision.** review-rounds-in-order (a later review round waits for the earlier round's reviewer).

**Retire.** Take the PR under review from the brief's first PR number, or from a `Review PR #<n>` form, and add a case for a brief that cites a second PR.
