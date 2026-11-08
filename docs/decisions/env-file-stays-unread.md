# The environment file stays unread

## The ruling

No session reads, writes or commits the contents of an environment file. The user manages that file, and its values stay out of the session. The guard refuses a shell command that would do any of those, and a write tool call that names the file. The settings deny list refuses a Read or Edit call on it. A runner may load the file into its own process with its loader flag. The guard stops node, bun and deno given the file when they run inline code (`-e`, `-p`, `--eval`, `--print`, deno's `eval`) or a script read from stdin (`-`, a pipe, a heredoc, a here-string or a `<` file), since that code can print the variables. It does not catch deno's `run -`, which reads stdin after the word `run`. The guard also stops uv, docker, podman, npm, npx and pnpm given the file when the child command they start prints its environment. Those children are `env`, `printenv`, `python -c`, and inline node, bun or deno code. A python or shell child with no script word and stdin fed is also stopped. Stdin is fed by a pipe, a heredoc, a here-string or a `<` file. A shell string is `sh`, `bash`, `zsh` or `dash` with `-c "<s>"`, or npm, npx or pnpm with `-c "<s>"`. It is refused when, with its quote marks removed, it starts with `env` or `printenv`. It is also refused when it holds a `$` expansion. Any other string is allowed, so `docker run … sh -c "npm start"` runs. A docker or podman child is the `--entrypoint` program, else the word after the image. An `npm exec -c` child is its string. Quote marks on a child word are ignored. Gaps remain: a value flag not on a runner's short list, and `docker container run`. Perl or ruby `-e` is a gap. So is a string that prints later (`sh -c "cd x && env"`). A nested `sh -c "python -c …"` is a gap too. The guard does not read a script file, so a script the session wrote can still print the variables.

One scope covers every form: a write tool call, a shell command and a Read call. A name is any basename that starts with `.env`, except `.env.example`. The guard's forms read one shared basename matcher in guard_env (`names_env_file`).

Ruling: owner, Queue item 159 answer a, 2026-11-02 00:56 CST. Reason: `.envrc` often holds exported secrets. That is the likely risk named below.

Shell form. `judge_shell` calls `env_refusal` and `env_heredoc_refusal`. A name is a word whose basename is in the scope above. A glob that could match a name counts as the name (`_glob_could_name_env`).

- Refused: a redirect onto the file. A shell variable that holds its path, because the guard cannot follow a variable to its use. The file given to a command that is not a runner. Any other command that would read, write or commit it.
- Allowed: an existence check (`ls`, `test`, `[`, `[[`). `echo` and `printf`, where the name is text. The message or body value of `git commit` and `gh pr create`. A runner in `ENV_LOADER_COMMANDS` (node, npm, npx, pnpm, bun, deno, uv, docker, podman, and their variants) given `--env-file` or `--env-file-if-exists`, except that node, bun and deno given the file must run a script file, not inline code or a stdin script. A runner that starts a child command (uv, docker, podman, npm, npx, pnpm) must not start one that prints its environment, or a shell string that does (`ENV_CHILD_REASON`).
- Substitutions (`$(...)`, backticks, `<(...)`) are judged as commands of their own, at any depth up to `ENV_MAX_DEPTH` (64). A deeper nest is refused. The substitutions in an unquoted heredoc body are judged (`env_heredoc_refusal`). A quoted heredoc body is text.

Write form. In `judge`, a write tool call (Write, Edit, MultiEdit or NotebookEdit) whose target name is in the scope is refused (`is_env`). It reads the same matcher as the shell form.

Read form. The guard does not judge Read. It returns early for Read and Grep. The settings deny list refuses a Read call on a name that starts with `.env`, at any depth. It refuses an Edit call on the same names. Its `!` carve-outs keep `.env.example` readable and editable. That reading of the `!` carve-outs comes from Claude Code's permission docs. It is not measured.

The printed refusal names no file. It names the shape of the access (`ENV_REDIRECT_REASON`, `ENV_VARIABLE_REASON`, `ENV_RUNNER_REASON`, `ENV_INLINE_REASON`, `ENV_CHILD_REASON`, `ENV_CONTENTS_REASON`, `ENV_DEPTH_REASON`, `ENV_TOOL_REASON`) and a remedy (`ENV_ADVICE`). The log holds the file name, for a person to read.

Known false alarms: debt `env-file-rule-false-alarms` (the env-file false-alarm debt). The guard refuses `ag -f` and `ack -f`, where `-f` is a boolean flag, `grep -r --exclude=.env`, and `rg -t py .env`. All four are safe. None reads a file's contents.

Why: the user's own secrets must not enter the session. `.envrc` is in the scope for the same reason. The guard stops Claude's mistakes, not an attacker's form (`guard-guards-mistakes-only`, a guard stops mistakes, not an attacker).

Risk: likely risk (`building-guard-needs-incident`: a guard or check needs a mistake Claude has made or is likely to make in normal work). A session would likely read a `.env` or `.envrc` file while it debugs. No incident is on record. Landed 2026-09-16, the env-file rule. The guard_env module has held the rule since 2026-10-13.

Kind: process
Home: hooks/guard_env.py
Home: hooks/guard.py
