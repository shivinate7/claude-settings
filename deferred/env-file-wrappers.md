# The env-file rule looks through wrappers

**What waits.** The `env-file` rule in `hooks/guard.py` allows `--env-file` only when the
command word is a runner (`ENV_LOADER_COMMANDS`). It reads the command word with
`resolve_command`, which unwraps `sudo`, `env`, `nohup`, `time` and a few more, but not
`timeout N`, not `verdict`, and not a `(VAR=x` token glued to a subshell paren.

**What it must do.** `timeout 60 node --env-file=.env app.js`, `verdict npm --env-file=.env
test` and `(VERIFY_PORT=3001 node --env-file=.env app.js)` run with no refusal. `timeout /t 5`
stays a `waiter` hit, so the `timeout` unwrap applies only when a duration follows. Red cases
first, in `hooks/test_guard.py`.

**Why it waits.** MEASURED in this Windows machine's `~/.claude/guard.log`, 30 days to
2026-10-11: 303 of 766 `env-file` denies name one of those three shapes as the command
(`timeout` 160, `verdict` 78, a word glued to `(` 65). The
rule's own remedy tells the agent to use the form it then refuses. See decision
guard-log-read-weekly.
