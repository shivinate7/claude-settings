# A command may not set the Playwright browser path

## Ruling

No command sets PLAYWRIGHT_BROWSERS_PATH to work around a missing browser build. The guard rule
`playwright-browsers-path` refuses a Bash or PowerShell command that sets the variable. A read, a grep
and `unset` stay allowed. The refusal sends the reader to the two measured causes:

- A stale `__dirlock` in the Playwright cache. The reader runs `pgrep -fl playwright` to confirm that no
  install is running, then removes the lock.
- An install that hangs while it unpacks under Node 26.11 with Playwright 1.58. Under Node 22 it unpacks
  in 0.75 s, through `npx -y node@22 node_modules/playwright/cli.js install`.

The rule refuses `cross-env`. Named limits, rare in docs and guides: `setx`, `timeout N env`, a `<<<`
here-string, a PowerShell block, a CI yaml `env:` key, and `node -e` or `python -c`. An export on a later
line of a multi-line `printf` format is a limit too.

Owner, 2026-10-16: the Playwright rows in `hooks/test_guard.py` (this rule's set forms and the `PLAYWRIGHT_INSTALL_DENY` table of `playwright-install-once`) stay until a session runs Playwright on a Mac. Then measure whether they still stop a real mistake. The incidents were on a Mac, so a Windows measure cannot show it. Not measured yet.

Reason: a session set the variable to a scratch directory and hid both causes. The install then waited 73 minutes.

Kind: process
Home: hooks/guard.py
