# A command may not set the Playwright browser path

## Question

May a command set PLAYWRIGHT_BROWSERS_PATH to work around a missing browser build?

## Ruling

No. The guard rule `playwright-browsers-path` refuses a Bash or PowerShell command that sets
the variable. A read, a grep, and `unset` stay allowed. The refusal sends the reader to the
real cause: a stale `__dirlock` in the Playwright cache. The reader runs `pgrep -fl playwright`
to confirm that no install is running, then removes the lock.

## Incident

On 2026-10-10 a feed-build session set the variable to a scratch directory. It wanted to work
around a missing chromium_headless_shell-1208. The real cause was a stale `__dirlock`, left at
16:11 by an install that stopped halfway. The install waited 73 minutes. The workaround hid
the cause.
