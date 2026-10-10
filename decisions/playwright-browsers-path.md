# A command may not set the Playwright browser path

## Question

May a command set PLAYWRIGHT_BROWSERS_PATH to work around a missing browser build?

## Ruling

No. The guard rule `playwright-browsers-path` refuses a Bash or PowerShell command that sets
the variable. A read, a grep, and `unset` stay allowed. The refusal sends the reader to the
two measured causes. One is a stale `__dirlock` in the Playwright cache: the reader runs
`pgrep -fl playwright` to confirm that no install is running, then removes the lock. The other
is an install that hangs while it unpacks under Node 26.11 with Playwright 1.58. Under Node 22
it unpacks in 0.75 s, through `npx -y node@22 node_modules/playwright/cli.js install`.

Home: `playwright_path_hit` in hooks/guard.py, called from `judge_shell` at step 3c.

## Incident

On 2026-10-10 a feed-build session set the variable to a scratch directory. It wanted to work
around a missing chromium_headless_shell-1208. The real cause was a stale `__dirlock`, left at
16:11 by an install that stopped halfway, and the install hung under Node 26.11. The install
waited 73 minutes. The workaround hid both causes. The feed-build session has since resolved
both.
