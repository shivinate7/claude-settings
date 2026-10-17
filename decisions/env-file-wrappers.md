# The env-file rule and its wrappers

## The question

The `env-file` rule allows `--env-file` only when the command word is a runner
(`ENV_LOADER_COMMANDS`). Which wrappers ahead of the runner may it look through, and which
words does it read as paths?

## The ruling, 2026-10-13

Owner, 2026-10-13 14:40, rule 1 of guard-audit-high (the audit ruling of the same day):

- The rule looks through `verdict`, `timeout`, `time` and `do` to the real command.
- The rule looks through `python`, `python3` and `py` only when the next word is a `verdict`
  path. Optional launcher flags such as `-3` or `-u` may come first.
- A grep, sed or awk pattern or program is never read as an env file.
- File-reading flags still refuse: `-f`, `--file`, `sed -f` and `awk -f`.

## Exact forms

A pinned form has a case in `hooks/test_guard.py`. On 2026-10-13 the env family passed 327 of
327 cases, and the fail-closed family passed 13 of 13.

- `timeout <duration>`, after its flags. Allowed: `timeout 60 node --env-file=.env app.js`,
  `timeout --signal=TERM 5 node --env-file=.env app.js`, `timeout --kill-after=2 5 node
  --env-file=.env app.js`. Refused: `timeout 60 cat --env-file=.env`. Pinned. The bare flags
  `--preserve-status` and `--foreground` are in the code, but no case pins them.
- `timeout /t 5` is Windows `timeout.exe`, a sleep. It stays a waiter hit. Pinned.
- `verdict`. Allowed: `verdict npm --env-file=.env test`. Refused: `verdict pytest
  --env-file=.env`. Pinned.
- `python bin/verdict` and `py -3 bin/verdict`. Allowed with a runner after them. Pinned.
  `python3 bin/verdict` shares the code path, but no case pins it.
- `time`. Allowed: `time node --env-file=.env app.js` and `time -p node --env-file=.env app.js`.
  Refused: `time cat .env`. Pinned.
- `do`. Allowed: `for f in a; do node --env-file=.env app.js; done`. Refused:
  `for f in a; do cat .env; done`. Pinned.
- A `(` glued to an assignment. Allowed: `(VERIFY_PORT=3001 node --env-file=.env app.js)`.
  Refused: `(X='a ls' cat .env)`. Pinned.
- A flag's value never becomes the command word. Refused: `env -u ls cat .env`,
  `sudo -u ls cat .env`, `command -p ls cat .env`, `echo x | xargs -I ls cat .env`. Pinned.
- `sudo`, `env`, `nohup` and the other general wrappers are not looked through. The code ends
  the unwrap at any other word. A reader behind `env`, `sudo`, `command` or `xargs` is refused,
  pinned. No case pins a runner behind them.
- The same unwrap feeds the waiter rule. `timeout 60 sleep 30` is refused. `timeout 60 sleep 5`
  is allowed. Pinned.

## Patterns and flags

Allowed, pinned: `grep '.*' README.md`, `grep -e '.*' src/`, `sed -n '/.env/p' file`,
`awk '/.*/' file`, `grep --max-count 5 '.*' file`.

Refused, pinned: a real path after a pattern or a value flag, as in `grep -n "def .*" .env`
and `grep -e foo .env`. File-reading flags, as in `grep -f .env x`, `rg -f .env x`,
`grep --file .env x`, `grep --file=.env x`, `sed -f.env x`, `awk -f.env x` and
`time grep -f .env x`.

The rule skips the pattern word of a search command (`grep`, `egrep`, `fgrep`, `rg`, `ag`, `ack`).
`-e` and `--regexp` mark the pattern. Without them, the first plain word is the pattern, after the
values of `-A`, `-B`, `-C` and `-m`. A path word is still judged, so `cat .*` denies. With `-f`,
`--file` or `--file=`, the patterns come from a file: nothing is skipped, and the value is judged as
a path.

## Holes, named

Debts: `env-grep-long-abbrev-unpinned` (grep --regex= style abbreviations are not pinned), `env-file-rule-false-alarms` (ag -f, ack -f, grep --exclude and rg -t are false refusals), `env-flat-crash-allows` (a crash in `_env_flat` allows the call), `env-node-env-file-prints` (node --env-file with -e prints the file through the runner).

## Named limits

- An `awk -v` value holding a glob is cleared as a search pattern. `hooks/test_guard.py` pins it as an allow.

## Incident

Counted in guard.log (a lower bound, one machine), this Windows machine's `~/.claude/guard.log`, 30 days to 2026-10-11 (decision
guard-log-read-weekly, the weekly table). 296 of 766 env-file denies named `timeout` (160),
`verdict` (78) or a word glued to `(` (58) as the command. The log holds the command word, not
its arguments, so the 160 `timeout` denies include any timeout form. The rule's own remedy told
the agent to use the form it then refused.

Measured by the oversight session's audit, 2026-10-13 (guard-audit-high): about 690
env-file denies a week. Since 2026-10-12, 25 were for `grep '.*'` and 7 for `do`. Rule 1 covers
these shapes.

The first build read the word through the unwrap as it stood. Review proved nine reads of `.env`
that main refused and the branch allowed. A wrapper flag's value posed as the command word while
the real command ran: `env -u ls cat .env`, `sudo -u ls cat .env`,
`echo x | xargs -I ls cat .env`, `env -u node cat -- --env-file .env`. A quoted glued assignment
hid the word: `(X='a ls' cat .env)`. Red cases were committed first, then the narrowing.

Two more defects, found in review of the guard trims (decision guard-trims-from-the-audit):

- 29 `env-file` denies read "only a runner may be handed '.env' with --env-file, and 'Semwal' is
  not one". The cause was a quoted assignment value with a space, as in
  `ADMINS='Shivam Semwal' node --env-file=.env server.ts`. The guard split words on spaces, so the
  tail of the value read as the command word. `_assignment_end` now spans the quoted value.
- An unquoted heredoc body with no `$(...)` made `env_heredoc_refusal` raise an IndexError. The
  guard failed open, so every rule after the env check was skipped. The body is now judged and
  passes. The top-level crash handler of `guard.py` now logs one `crash` line, so the next hidden
  crash shows in `guard.log`.

## What reopens it

A wrapper shape this ruling does not name, with a counted number of denies in the weekly table.

Kind: process
Home: hooks/guard_env.py
