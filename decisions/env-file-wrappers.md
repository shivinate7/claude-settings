# The env-file rule and its wrappers

## The ruling

Owner, 2026-10-13 14:40, rule 1 of `guard-audit-high`. The `env-file` rule allows `--env-file` only when the command word is a runner (`ENV_LOADER_COMMANDS`).

- It looks through `verdict`, `timeout`, `time` and `do` to the real command.
- It looks through `python`, `python3` and `py` only when the next word is a `verdict` path. Launcher flags such as `-3` or `-u` may come first.
- A grep, sed or awk pattern or program is never read as an env file. File-reading flags still refuse: `-f`, `--file`, `sed -f` and `awk -f`.
- It skips the pattern word of a search command (`grep`, `egrep`, `fgrep`, `rg`, `ag`, `ack`). `-e` and `--regexp` mark the pattern. Without them, the first plain word is the pattern, after the values of `-A`, `-B`, `-C` and `-m`. A path word is still judged, so `cat .*` denies. With `-f`, `--file` or `--file=`, nothing is skipped and the value is judged as a path.
- `timeout <duration>` is read after its flags. `timeout /t 5` is Windows `timeout.exe`, a sleep, and stays a waiter hit. `timeout 60 sleep 30` is refused by the waiter rule, `timeout 60 sleep 5` is allowed.
- A `(` glued to an assignment is looked through: `(VERIFY_PORT=3001 node --env-file=.env app.js)` is allowed, `(X='a ls' cat .env)` is refused. A quoted assignment value with a space is spanned by `_assignment_end`.
- A flag's value never becomes the command word. `env -u ls cat .env`, `sudo -u ls cat .env`, `command -p ls cat .env` and `echo x | xargs -I ls cat .env` are refused.
- `sudo`, `env`, `nohup` and the other general wrappers are not looked through. The code ends the unwrap at any other word. A reader behind `env`, `sudo`, `command` or `xargs` is refused.
- An unquoted heredoc body with no `$(...)` is judged and passes. The top-level crash handler of `guard.py` logs one `crash` line.

Why: the rule's own remedy told the agent to use forms it then refused (`timeout`, `verdict`, a word glued to `(`), and about 690 env-file denies a week were false alarms. A wrapper flag's value must not pose as the command word while the real command runs.

Protected by the env-family cases in `hooks/test_guard.py`. Unpinned: the bare flags `--preserve-status` and `--foreground`, `python3 bin/verdict`, and a runner behind `env`, `sudo`, `command` or `xargs`.

## Holes, named

Debts: `env-file-rule-false-alarms` (ag -f, ack -f, grep --exclude and rg -t are false refusals).

Limit: an `awk -v` value holding a glob is cleared as a search pattern. `hooks/test_guard.py` pins it as an allow.

Reopen on a wrapper shape this ruling does not name, with a counted number of denies in the weekly table (`guard-log-read-weekly`).

Kind: process
Home: hooks/guard_env.py
