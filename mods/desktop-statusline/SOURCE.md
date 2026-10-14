# Source

- Repo: https://github.com/centminmod/claude-plugins
- Path: plugins/desktop-statusline
- Commit: 5239dd5c241ca5537f4737c25321399734d0c0bc
- Licence: MIT (LICENSE is the plugin-folder file)
- Vendored on 2026-10-12.

Copied from the commit above; markdown docs and unused screenshots omitted.

Local changes (owner ruling 2026-10-14: token-weather is the one context bar):

- hooks/register.tsx: removed the Context meter and its `used`, `contextRoomPx`, `contextBar` values. Also removed the unread `contextPercent`, `contextTokens` and `contextWindow` snapshot fields (and their types) and the `breakdown: 'summary'` option on `session.usage()`. The rest of the status line stays.
