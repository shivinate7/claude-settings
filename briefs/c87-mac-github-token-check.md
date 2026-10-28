# c87: find which GitHub connection fails on the Mac (read-only)

Step c87, "Local sessions stop failing on the GitHub plugin's empty token". Ruling: shiv, Oct 28 02:43 CDT, waiting page item 7, (a): a Mac session finds the cause and changes nothing; the fix follows from the cause.

## Why

shiv says GitHub access fails on the Mac too, and asks whether a personal access token expired. On Oct 27 the local liaison found no GitHub plugin installed on the Mac (plugin list, MCP list, every repo's settings). So the failing piece may be another GitHub connection.

One fact from the cloud (orchestrator, Oct 28): the GitHub plugin there fails with "Authorization header is badly formatted", while `gh` with its own login works. That error usually means a bad, empty or expired token.

## Do (read-only; change nothing)

1. List every GitHub connection on the Mac: `claude plugin list`, `claude mcp list`, `~/.claude/settings.json` and each repo's `.claude/settings*.json` (enabledPlugins, mcpServers), and any env var or env file that holds a GitHub token (names only, never values).
2. For each one, check its token without printing it: `gh auth status`; for an env token, whether it is set and empty; for a fine-grained or classic token, its expiry if `gh api` can read it (`gh api user -i` with that token, reading only the status line and the expiry header).
3. Reproduce the failure once: name the exact tool or command that fails and its error text.

## Report (to the orchestrator; 5 lines at most)

- Which connection fails, the error text, and the cause (expired, empty, wrong scope, malformed header, or not installed).
- The smallest fix and where it lands (claude-settings, so every machine gets it, unless the cause is a token only shiv can make).
- Never paste a token value, even partly.
