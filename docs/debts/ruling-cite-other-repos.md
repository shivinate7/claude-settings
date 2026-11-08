# Ruling cites go unchecked in other repos

**What.** The commit check judges a ruling claim only when the commit's parent tracks `lint/check_red_run.py`. In another repo, a test-author runs the installed copy, and an unsourced ruling claim there passes. The Red-run rule judges each commit in such a repo, but the ruling rule does not.

**Where.** `lint/check_red_run.py`, the rollout gate of the ruling rule.

**Decision.** red-run-trailer-on-test-commits (a commit that adds test lines carries a red-run trailer; item 5 judges every commit in a repo that does not track the check)

**Retire.** In a repo that does not track the check, a claim with no cite fails, and the commits in a batch rebuilt from main are still not re-judged. A case in `lint/test_check_red_run.py` shows this.
