# One Playwright install, never from an agent

## The ruling

Rule `playwright-install` in `hooks/guard.py`:

1. An agent never runs a Playwright browser install, in any form. The browsers are shared in
   `~/Library/Caches/ms-playwright`. The orchestrator installs once.
2. A main session installs only under Node 22, through
   `npx -y node@22 node_modules/playwright/cli.js install <browser>`.
3. `settings.json` sets `PLAYWRIGHT_SKIP_BROWSER_GC=1` for every session, so an install never removes
   another project's browser build. The guard does not check this.

Reason: parallel agent installs under Node 26.11 hung, fought over the shared `__dirlock` and
blocked other projects. The Node 26 hang is measured in playwright-browsers-path.

Kind: process
Home: hooks/guard.py

## Named limits

- An install inside a script, such as `npm run e2e:setup`, is not seen.
- These rarer forms are not seen: a Windows `.cmd` or `.exe` suffix, a heredoc piped into `sh`, a
  `( ... )` subshell, `timeout`, `env -S`, `pnpx`, `yarnpkg`, `corepack pnpm dlx`, `npx --call=`,
  `npm exec -c`, and `pwsh -com`.
- When a Playwright release fixes the Node 26 hang, rule 2 is stale. Measure it again then.
