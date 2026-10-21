# Source

- Repo: https://github.com/centminmod/claude-plugins
- Path: plugins/desktop-statusline
- Commit: 5239dd5c241ca5537f4737c25321399734d0c0bc
- Licence: MIT (LICENSE is the plugin-folder file)
- Vendored on 2026-10-12.

Copied from the commit above; markdown docs and unused screenshots omitted.

Local changes (owner ruling 2026-10-14: token-weather is the one context bar):

- hooks/register.tsx: removed the Context meter and its `used`, `contextRoomPx`, `contextBar` values. Also removed the unread `contextPercent`, `contextTokens` and `contextWindow` snapshot fields (and their types) and the `breakdown: 'summary'` option on `session.usage()`. The rest of the status line stays.

- hooks/register.tsx: the band reads its source on session start, on attach, at each turn end, and after 5 idle minutes, not on the 60 s timer. A failed read is never stored: the band keeps the last good values. After a first failure the next tick reads again; after a second, reads wait 5 minutes. Outside a turn, the band can trail the repository by up to about 6 minutes. That is an accepted cost of the 5-minute idle back-off (owner ruling 2026-10-21).
