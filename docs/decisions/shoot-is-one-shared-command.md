# One shared command takes every repo's screenshots

## The ruling

Owner, 2026-10-17: build one screenshot script in this repo. Adding it to each child repo is a later step.
Owner, 2026-10-20: one script, installed like the hooks. Each repo keeps only a config. The script is the check. A browser is for exploring.
Owner, 2026-10-26: cloud sessions ship Chromium and Playwright, so the script needs no MCP server.

The contract of `bin/shoot`:

- `shoot [--config F] [--out DIR]`. F defaults to `.claude/shoot.json` in the current folder.
- The config holds `baseUrl`, `routes`, `sizes` (widths, default 1440, 820 and 390), `themes` (light and dark, set by `prefers-color-scheme`), an optional `simulator` UDID and an optional `ignoreHTTPSErrors` boolean (default false, for an app with a self-signed certificate). A bad value is a config error: exit 2 and a `shoot: config` line that names the key. Other keys, on the config or on a route, are ignored.
- A route may carry `steps` (the route steps): a non-empty list that runs after the page loads and its HTTP status passes, before the screenshot. A route step is `{click: css}` or `{wait: css, state: "visible" | "hidden"}` (state defaults to visible), bounded by `timeoutMs`. A route step that errors fails the shot. A `state: "hidden"` wait passes at once when nothing matches, so a disappear-wait alone proves nothing: pair it with a wait for real content.
- A route may carry `localStorage`: an object of string values, set before the page's scripts run, in the top frame only. A route with route steps or `localStorage` runs in its own browser context, with `ignoreHTTPSErrors` carried into it. The context is closed after the shot, so the route starts clean and leaves nothing behind (localStorage, cookies) for another route. A click can write that state, which is why route steps count too.
- A path in `baseUrl` is kept: base `http://h/app` and route `/a` take `http://h/app/a`. Two routes that write one file name are a config error.
- Touch per size (coordinator pick, 2026-11-08 08:27 CST; process only): a width under 1024 gets `hasTouch`, so `(pointer: coarse)` matches. 1024 and wider has none. No config key. Chromium drops the coarse match in a full-page capture, so a touch shot with `fullPage` joins viewport tiles in a canvas. The tiles cover the root element's scroll width and height. A page that scrolls its body, not its root, gets a smaller PNG than a plain full-page capture. Tiles after the first hide fixed elements, fixed pseudo-elements and the images of fixed backgrounds (the colour stays), so each shows once, at its first-tile place. An element mixing fixed and scroll layers loses its scroll layers on those tiles. For the whole stitch, sticky elements sit in the flow and the root does not scroll-snap. The cost is one screenshot per viewport tile. A canvas Chromium cannot read back fails that shot.
- It writes one PNG for each route, width and theme to a folder, and prints one verdict line: the shot count, the fail count and the folder.
- A shot fails on a navigation error, a timeout, an HTTP status of 400 or more, or an image of one colour only.
- It uses the installed Playwright package only. If the package is missing, it prints one line that names it and exits 2. It never runs `playwright install`.
- It takes a simulator screenshot only when that device is already booted. It never boots a simulator, because the repos ration them. A device that is not booted is a skip, not a fail.
- Cost: one browser process for each run, closed at exit (unmeasured). No daemon and no watcher.

Why: each repo had its own way to take screenshots, and banchi's script had a fixed viewport. One command gives one place to fix the sizes, the themes and the blank-page check.

Protected by `lint/test_shoot.mjs` and the `checks-shoot` job of `.github/workflows/checks.yml`.

## Limits

- Unmeasured: a real simulator. The suite stubs `xcrun`.
- The blank check reads only the PNG form that Chromium writes. Any other form counts as not blank.

Kind: process
Home: bin/shoot
