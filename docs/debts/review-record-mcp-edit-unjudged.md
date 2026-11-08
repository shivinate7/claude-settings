# The MCP edit tool can rewrite a review record unjudged

- **What.** `mcp__github__update_issue_comment` can rewrite a posted review record with a hand-typed head or a malformed form, and no guard judges it. This PR drops the edit-tool branch from the review-record guard (coordinator ruling 2026-11-07 18:59 CST gave the tool to lane `mcp-tools-in-guard-matcher`), and that lane's PR #1687 does not judge the tool either (its record says "is not judged").
- **Where.** `hooks/guard.py` `review_post_hit` and the `settings.json` PreToolUse matcher, which lists no `mcp__github__update_issue_comment`.
- **Decision.** `pr-review-record` (each PR carries a review record for its live head).
- **Retire.** The guard judges an MCP edit of a review record for form and head, and the matcher lists the tool. Shown closed by a refuse case and an allow control in `hooks/test_guard.py` (GUARD_FAMILY=review-record).
