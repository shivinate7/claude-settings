# The env-file rule looks through three wrappers

## The question

The `env-file` rule in `hooks/guard.py` allows `--env-file` only when the command word is a
runner (`ENV_LOADER_COMMANDS`). Which wrappers ahead of the runner may it look through?

## The ruling, 2026-10-12

Three shapes, each by exact form, and no other:

- `timeout <duration>`, after its own flags (`-k`/`--kill-after` and `-s`/`--signal` with their
  values, `--preserve-status`, `--foreground`). `timeout /t 5` is Windows `timeout.exe`, a
  sleep, and stays a `waiter` hit.
- `verdict`, and `python bin/verdict` or `python3 bin/verdict`: the repo's own runner.
- A `(` glued to an assignment, as in `(VERIFY_PORT=3001 node --env-file=.env app.js)`.

A flag's value never becomes the command word. `sudo`, `env`, `nohup` and the other general
wrappers stay outside the env-file rule, as before. The same unwrap serves every rule that
reads the command word through `resolve_command`, so `timeout 5 sleep 1` is now a `waiter`
hit and `timeout 5 pkill x` a `machine-wide-kill` hit.

## The incident

MEASURED in this Windows machine's `~/.claude/guard.log`, 30 days to 2026-10-11 (decision
guard-log-read-weekly). 296 of 766 `env-file` denies named `timeout` (160), `verdict` (78) or
a word glued to `(` (58) as the command. The rule's own remedy told the agent to use the form
it then refused.

The first build read the word through `resolve_command` as it stood. Review proved nine reads
of `.env` that main refused and the branch allowed. A wrapper flag's value posed as the
command word while the real command ran: `env -u ls cat .env`, `sudo -u ls cat .env`,
`echo x | xargs -I ls cat .env`, `env -u node cat -- --env-file .env`. A quoted glued
assignment hid the word: `(X='a ls' cat .env)`. Red cases first, then the narrowing.

## Named limits

- `node --env-file=.env -e 'console.log(process.env)'` prints the file through the runner.
  Main allowed it before this change; the runner allow-list is the limit.
- The log holds the command word, not its arguments, so the 160 `timeout` denies include any
  `timeout` form.

## What reopens it

A fourth wrapper shape with a measured deny count in the weekly table.
