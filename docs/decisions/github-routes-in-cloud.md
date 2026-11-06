# Which GitHub route works in a cloud session

## Ruling

One table says which route does a GitHub act from a cloud session. A record, skill or tool that says
an act "cannot" be done, or names one route for it, cites this table and states no claim of its own.
A row is a measurement with its date. A route nobody measured is "unknown", never "cannot".

Kind: process
Home: docs/decisions/github-routes-in-cloud.md

## Route table

Measured on PR #1294 (this record's own draft PR), Claude Code 2.1.319, cloud session, 2026-11-06.

| Act | Route | Result | When (CST) |
|---|---|---|---|
| Mark a draft ready | MCP `update_pull_request` `draft: false` | Works. The ready run started. | 11:38 |
| Return a PR to draft | MCP `update_pull_request` `draft: true` | Works. | 11:38 |
| Mark ready or return to draft | `gh pr ready`, `gh pr ready --undo` | HTTP 403: the proxy refuses all GraphQL. | 11:39 |
| Any GraphQL read | `gh api graphql` | HTTP 403, same text. | 11:39 |
| Mark ready, return to draft | REST `POST pulls/<n>/ccr/ready_for_review`, `.../ccr/convert_to_draft` (named by the 403 text) | Unknown. Auto mode refused the Bash call ("Unrequested Commit in a Connected App"). | 11:39 |
| Cancel a run of the session's own PR | MCP `actions_run_trigger` `cancel_workflow_run` | Works. HTTP 202; run 42263498384 ended `cancelled`. Auto mode did not refuse it. | 11:38 |
| Cancel a run | `gh api -X POST .../actions/runs/<id>/cancel` | Auto mode refused it on Nov 1 (note `auto-mode-refuses-run-cancel`). GitHub's answer is unknown. | Nov 1 |

A cancel of a run that another session started stays that session's act (`shared-trees-no-machine-wide-kill`).

The CI wake (`hooks/ci_wake.py`) starts only on a Bash `gh pr ready`, which the cloud refuses. So the MCP
route sends no wake (debt `ci-wake-misses-mcp-ready`).

## Unknown, not measured

- Whether a cloud session loads plugins from local settings (decision `adoptions-declined-2026-09-28`).
  This session loaded the claude.ai organization's plugins, which is another source.
- The two `ccr/` REST routes above.

## Other cloud fact measured here

- `CLAUDE_CODE_EXECPATH` on 2.1.319: unset in the SessionStart hook, set in the Bash tool
  (`/opt/claude-code/bin/claude`). Home: decision `precompact-handoff`, item 12.
