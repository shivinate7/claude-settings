# One Playwright install, never from a subagent

## The question

Who may run a Playwright browser install, and how?

## The ruling

Owner, 2026-10-11 (rule `playwright-install` in `hooks/guard.py`):

1. A subagent never runs a Playwright browser install, in any form. The browsers are shared
   in `~/Library/Caches/ms-playwright`. The orchestrator installs once.
2. A main session installs only under Node 22, through
   `npx -y node@22 node_modules/playwright/cli.js install <browser>`.
3. `settings.json` sets `PLAYWRIGHT_SKIP_BROWSER_GC=1` for every session, so an install never
   removes another project's browser build. The guard does not check this.

## The incident

2026-10-11, feed-build: three test-author subagents ran `npx playwright install chromium` at
the same time, under the Mac's default Node 26.11. One hung for 20 minutes. They fought over
the shared `__dirlock` and blocked other projects' installs. The browsers they wanted were
already in the cache. The sessions had started before `settings.json` set the GC variable,
and an earlier install removed another project's build.

The Node 26 hang is measured in decision playwright-browsers-path.

## Named limits

- An install inside a script, such as `npm run e2e:setup`, is not seen.
- These rarer forms are not seen: a Windows `.cmd` or `.exe` suffix, a heredoc piped into
  `sh`, a `( ... )` subshell, `timeout`, `env -S`, `pnpx`, `yarnpkg`, `corepack pnpm dlx`,
  `npx --call=`, `npm exec -c`, and `pwsh -com`.
- When a Playwright release fixes the Node 26 hang, rule 2 is stale. Measure it again then.
