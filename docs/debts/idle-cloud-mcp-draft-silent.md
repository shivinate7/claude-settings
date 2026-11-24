# A cloud session's MCP draft posts no comment, so the watching session is not woken

**What.** On a cloud session the merge tool cannot draft an idle red PR. It prints the MCP route, `update_pull_request` with `draft` true. A draft by that route posts no comment, so the session that watches the PR is not woken, and the author does not learn why the PR went to draft.

**Where.** `merge/merge.py`, `Host.to_draft`: the cloud branch sends nothing and returns the route. `merge/idle_prs.py`, `draft_one`: the comment is posted only after a draft by the local route.

**Decision.** `idle-red-pr-returns-to-draft` (the rule for an idle red PR, and its comment as the wake).

**Retire.** A case in `merge/test_idle_prs.py` shows the cloud route posting the same comment after its draft, so the watching session is woken as on the local route.
