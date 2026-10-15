# Two real-timer margins in the session-board test are unproven on a slow runner

- **What.** `mods/session-board/session-board.test.mjs` has two real-timer margins, about lines 709-718 and 928-940. Each is `within(200)` against a 100 ms grace. Both margins are unproven on a slow runner.
- **Where.** `mods/session-board/session-board.test.mjs`, lines 709-718 and 928-940.
- **Decision.** `mods-tests-run-in-gates` (mod tests run as the last step of the gates job).
- **Retire.** The margins use fake timers, or a slow-runner run proves them. The decision records the result.
