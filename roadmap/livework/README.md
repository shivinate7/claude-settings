# Live-work file helpers

Build the `--live FILE` that main's skills/roadmap/build.py and `merge --idle-lanes --live FILE` read.
A live file goes stale 60 minutes after its readAt (build.py `STALE_LIVE_MINUTES`), so build a fresh one
each time; never commit one. Shape: build.py docstring of the live-file reader (`readAt`, `pulls`,
`sessions`, optional `threads` and `branches`).

1. Copy this folder to your scratchpad and run the scripts there; they write their JSON beside themselves.
2. Page `mcp__github__list_pull_requests` (state open, perPage 100) and save each page's output to a
   file. Run `python3 pulls_add.py <page file>` per page.
3. Page `mcp__claude-code-remote__list_sessions` (mine, limit 100, after_id = last_id) and save each page.
   Run `python3 sess_map.py <page file>` per page, until has_more is false.
4. Run `python3 make_live.py <readAt ISO with zone>`; it writes live.json.

Cost: one MCP read per page (about 8 PR pages and 12 session pages at 750 PRs and 1200 sessions), three
JSON files written, run on demand only.
