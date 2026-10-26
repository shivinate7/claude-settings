# One shared command takes every repo's screenshots

## The ruling

Owner, 2026-10-17: build one screenshot script in this repo. Adding it to each child repo is a later step.
Owner, 2026-10-20: one script, installed like the hooks. Each repo keeps only a config. The script is the check. A browser is for exploring.
Owner, 2026-10-26: cloud sessions ship Chromium and Playwright, so the script needs no MCP server.

The contract of `bin/shoot`:

- `shoot [--config F] [--out DIR]`. F defaults to `.claude/shoot.json` in the current folder.
- The config holds `baseUrl`, `routes`, `sizes` (widths, default 1440, 820 and 390), `themes` (light and dark, set by `prefers-color-scheme`) and an optional `simulator` UDID.
- A path in `baseUrl` is kept: base `http://h/app` and route `/a` take `http://h/app/a`. Two routes that write one file name are a config error.
- It writes one PNG for each route, width and theme to a folder, and prints one verdict line: the shot count, the fail count and the folder.
- A shot fails on a navigation error, a timeout, an HTTP status of 400 or more, or an image of one colour only.
- It uses the installed Playwright package only. If the package is missing, it prints one line that names it and exits 2. It never runs `playwright install`.
- It takes a simulator screenshot only when that device is already booted. It never boots a simulator, because the repos ration them. A device that is not booted is a skip, not a fail.
- Cost: one browser process for each run, closed at exit. No daemon and no watcher.

Why: each repo had its own way to take screenshots, and banchi's script had a fixed viewport. One command gives one place to fix the sizes, the themes and the blank-page check.

Protected by `lint/test_shoot.mjs` and the `gates-shoot` job of `.github/workflows/gates.yml`.

## Limits

- Unmeasured: a real simulator. The suite stubs `xcrun`.
- The blank check reads only the PNG form that Chromium writes. Any other form counts as not blank.

Kind: process
Home: bin/shoot
