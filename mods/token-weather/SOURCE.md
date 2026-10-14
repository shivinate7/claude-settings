# Source

- Repo: https://github.com/anthropics/claude-code-playground
- Path: claude-code/mods/token-weather
- Commit: 569c5283d9a0a7ee7938df85bb32e4f48cbb8c86
- Licence: Apache-2.0 (LICENSE is the repo-root file)
- Vendored on 2026-10-12.

Copied from the commit above; markdown docs and unused screenshots omitted.

Local changes (owner ruling 2026-10-14: this band is the one context bar, measured against the auto-compact window):

- hooks/token-weather.mjs: asks `session.usage({ breakdown: "summary" })` and measures against the auto-compact window when enabled, ignoring host `context.percent`. The host window is the model window, so a 500000 autoCompactWindow read low.
