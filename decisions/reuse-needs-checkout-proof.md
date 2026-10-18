# A test server is reused only with proof of its checkout

## The ruling

Lanes run in separate worktrees of one clone. A lane must not pass or fail on another lane's server.

1. In each repo, a Playwright `webServer` sets `reuseExistingServer: false`. Or it reuses a server only
   after the server proves its checkout, as banchi's `app/checkoutIdentity.ts` does.
2. The dev server binds its port strictly, so a clash fails loudly with "port in use".
3. A port taken from a hash of the worktree path is not enough by itself. banchi D261 measured an 87%
   chance of a collision with 35 worktrees in 300 slots.
4. The check: the compliance-check probe "Shared trees" reads each repo's Playwright config. There is no
   guard. A guard can read only a port on the command line, and the silent failures came from ports set
   in config files.

Rejected: a guard that refuses a command when another checkout holds the port it names (a port on the
command line already fails loudly when reuse is off), and a port lease (a lease cannot make a server
bind its port, and a stale lease refuses falsely).

Reason: worktrees shared port 5173 with reuse on, and a lane passed on another lane's server.

Kind: process
Home: skills/compliance-check/probes.md
