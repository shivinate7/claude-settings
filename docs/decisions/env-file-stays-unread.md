# The environment file stays unread

## The ruling

No session reads, writes or commits the contents of an environment file, a `.env` file. The user
manages that file, and its values stay out of the session. The guard refuses a shell command that would
do any of those, and a write tool call that names the file. A runner may load the file into its own
process with its loader flag. A runner prints nothing, so no value reaches the session.

Shell form. `judge_shell` in `hooks/guard.py` calls `env_refusal` and `env_heredoc_refusal` in
`hooks/guard_env.py`. A name is a word whose whole basename is `.env` or `.env.<suffix>`
(`ENV_BASENAME`). `.env.example` is exempt (`ENV_ALLOWED`). A glob that could match a name counts as
the name (`_glob_could_name_env`).

- Refused: a redirect onto the file. A shell variable that holds its path, because the guard cannot
  follow a variable to its use. The file given to a command that is not a runner. Any other command
  that would read, write or commit it.
- Allowed: an existence check (`ls`, `test`, `[`, `[[`). `echo` and `printf`, where the name is text. The
  message or body value of `git commit` and `gh pr create`. A runner in `ENV_LOADER_COMMANDS` (node, npm,
  npx, pnpm, bun, deno, uv, docker, podman, and their variants) given `--env-file` or
  `--env-file-if-exists`.
- Substitutions (`$(...)`, backticks, `<(...)`) are judged as commands of their own, at any depth up to
  `ENV_MAX_DEPTH` (64). A deeper nest is refused. The substitutions in an unquoted heredoc body are judged
  (`env_heredoc_refusal`). A quoted heredoc body is text.

Write-tool form. In `judge` in `hooks/guard.py`, a write tool call whose target basename starts with
`.env`, and is not `.env.example`, is refused (`is_env` in `hooks/guard_env.py`). This form is wider than
the shell form: `.envrc` is refused as a write and is not a name in the shell form.

Read tool. The guard does not judge the Read tool. The settings deny list holds `Read(.env)` and
`Read(.env.*)` (`settings.json`).

The printed refusal names no file. It names the shape of the access (`ENV_REDIRECT_REASON`,
`ENV_VARIABLE_REASON`, `ENV_RUNNER_REASON`, `ENV_CONTENTS_REASON`, `ENV_DEPTH_REASON`, `ENV_TOOL_REASON`)
and a remedy (`ENV_ADVICE`). The log holds the file name, for a person to read.

Known false alarms: note `env-file-rule-false-alarms`, a line in `docs/debts/notes.md`. The guard refuses
`ag -f` and `ack -f`, where `-f` is a boolean flag, `grep -r --exclude=.env`, and `rg -t py .env`. All four
are safe. None reads a file's contents.

Why: the user's own secrets must not enter the session. The guard stops Claude's mistakes, not an
attacker's form (`guard-guards-mistakes-only`, a guard stops mistakes, not an attacker).

Risk: likely risk (`building-guard-needs-incident`: a rule needs a named incident, a measured risk or a
likely risk). A session would likely read a `.env` file while it debugs. No incident is on record.
Landed 2026-09-16, the `env-file` rule in `hooks/guard.py`. `hooks/guard_env.py` has held the rule since
2026-10-13.

Kind: process
Home: hooks/guard_env.py
Home: hooks/guard.py
