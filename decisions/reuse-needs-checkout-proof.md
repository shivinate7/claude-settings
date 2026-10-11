# A test server is reused only with proof of its checkout

## The question

Lanes run in separate worktrees of one clone. How does a lane avoid a test pass or fail on
another lane's server?

## The ruling

Owner, 2026-10-11:

1. In each repo, a Playwright `webServer` sets `reuseExistingServer: false`. Or it reuses a
   server only after the server proves its checkout, as banchi's `app/checkoutIdentity.ts`
   does.
2. The dev server binds its port strictly, so a clash fails loudly with "port in use".
3. A port taken from a hash of the worktree path is not enough by itself. banchi D261 measured
   an 87% chance of a collision with 35 worktrees in 300 slots.
4. The check: the compliance-check probe "Shared trees" reads each repo's Playwright config.
   There is no guard. A guard can read only a port on the command line, and the silent
   failures came from ports set in config files.

## Incidents

- banchi, 2026-08-29: worktrees shared port 5173 with reuse on. A lane passed on another
  lane's server.
- banchi, 2026-09-24: two path-hash ports collided, with the same result (banchi D261).
- feed-build, 2026-10-11: two lanes met on port 5397. Reuse was already off, so the second
  lane failed loudly. No wrong pass happened.

## Rejected

- A guard that refuses a command when another checkout holds the port it names. It sees only
  a port on the command line, which already fails loudly when reuse is off.
- A port lease. A lease cannot make a server bind its port, and a stale lease refuses falsely.
