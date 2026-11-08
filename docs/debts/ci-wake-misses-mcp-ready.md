# The CI wake misses the cloud's ready route

- **What.** A cloud session marks a PR ready by MCP `update_pull_request`, since `gh pr ready` gets a GraphQL 403. The CI wake starts only on a Bash `gh pr ready`, so in cloud it never fires. The session waits on its PR subscription and a check-in instead.
- **Where.** `hooks/ci_wake.py` and its PostToolUse matcher in `settings.json` (Bash and PowerShell only).
- **Decision.** `auto-mode-owner-acts` (which acts auto mode allows with no ask), route pr-ready-mcp-cloud.
- **Retire.** The wake starts on the MCP ready call too, or the cloud wait is proved enough and the hook says cloud is out of its scope.
