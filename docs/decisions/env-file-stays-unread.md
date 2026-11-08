# The environment file stays unread

## The ruling

No session reads, writes or commits the contents of an environment file. The user manages that file, and its values stay out of the session.

The guard refuses a write tool call that names the file. The settings deny list refuses a Read or Edit call on it. In a shell command the guard refuses only the forms it reads. A runner is read for its child (below). The script a shell hands on is read too (`bash -c "cat .env"`, `sh -c "source .env && npm test"`, `eval "cat .env"`), as the Substitutions bullet below says. An awk program that reads `ENVIRON` is a gap too: the guard does not read awk's script for the variables.

A runner may load the file into its own process with its loader flag. The guard stops node, bun and deno given the file when they run inline code (`-e`, `-p`, `--eval`, `--print`, deno's `eval`) or a script read from stdin (`-`, a pipe, a heredoc, a here-string or a `<` file). That code can print the variables. It does not catch deno's `run -`, which reads stdin after the word `run`.

The guard also stops uv, docker, podman, npm, npx and pnpm given the file when the child command they start prints its environment. It reads these children: `env`, `printenv`, any `python -c`, and inline node, bun or deno code. A python or shell child with no script word and stdin fed is also stopped. Stdin is fed by a pipe, a heredoc, a here-string or a `<` file. `npx`, `npm exec`, `npm x`, `pnpm exec`, `pnpm dlx` and `bun x` children are read the same way: `npx node -e "…"` is inline code. One reader, `_child_starts`, finds the children. One judge, `_child_prints`, reads each.

A wrapper before the child is read through to the command it runs: `timeout <n>`, `nice [-n x]`, `sudo [-E] [-u x]`, `time`, `stdbuf …`, `env VAR=x`, and `exec`, `command`, `builtin` and `nohup`. `uv run timeout 5 env` is the child `env`. `env VAR=x` with no command prints, so it is the child.

A shell string is `sh`, `bash`, `zsh` or `dash` with `-c "<s>"`, or npm, npx or pnpm with `-c "<s>"`. The guard judges it segment by segment, with the same reader as the shell form (`_env_flat`). A segment is refused in three cases. It names an environment file as the shell form refuses. Its command is a printing child: `env` or `printenv` (also after a wrapper), a nested `sh -c` that prints, or any nested `python -c`. Or its command is `echo` or `printf` and it expands a `$` variable. A `$` in any other segment is an ordinary argument, so `docker run … sh -c "cd $APP_DIR && npm start"` runs. Any other string is allowed too, so `docker run … sh -c "npm start"` runs.

A docker or podman child is the `--entrypoint` program, else the word after the image. An empty `--entrypoint ""` is no program. An option off a runner's value-flag list may own the next word. So the guard tries that word as the image or child. It then goes on past each option and its possible value, to the next word that follows no unlisted option (`--pull always --rm alpine env`, `--cap-add X --cap-add Y img env`, `pnpm exec --recursive env`). The child of npx, `pnpm dlx`, `npm exec` and `npm x` is found the same way (`npx env`, `pnpm -r exec env`). pnpm's `-r` and `-w` are bools there. `--` ends a runner's options, so the word after it is the child (`pnpm exec -- env`). A program's own arguments are not tried (`uv run -q pytest -k env`, `uv run --exact pytest -k env`), except after an option the guard does not know (below) and npm's `-c`. An `npm exec -c` child is its string. Quote marks on a child word are ignored.

Gaps remain. `docker container run` allows. A shell string misses a backtick, a `<(env)` and nested escaped quotes. It misses a `$(env)` in a segment whose command does not print (`cd $(env)`). Other printers are not read under a runner: `export -p`, `set`, `cat /proc/self/environ`, and `env` in a spaced `{ env; }`, `( env )`, `! env` or `if …; then env; fi` (debt note `env-child-printer-forms`). Perl or ruby `-e` is a gap. The guard does not read a script file, so a script the session wrote can still print the variables.

Two false alarms remain. An option that is neither on the runner's value-flag list nor on its bool list may own the next word. After it, `env` or `printenv` right after the program word, or after the program's own option, is tried as the child and denies (`uv run --foo pytest env`, `uv run --foo pytest -k env`). The guard cannot tell a bool from a value flag. An `echo` or `printf` segment that expands any `$` variable refuses, even one that holds no secret (`sh -c 'echo $PORT'`).

One scope covers every form: a write tool call, a shell command and a Read call. A name is any basename that starts with `.env`, except `.env.example`. The guard's forms read one shared basename matcher in guard_env (`names_env_file`).

Ruling: owner, Queue item 159 answer a, 2026-11-02 00:56 CST. Reason: `.envrc` often holds exported secrets. That is the likely risk named below.

Shell form. `judge_shell` calls `env_refusal` and `env_heredoc_refusal`. A name is a word whose basename is in the scope above. A glob that could match a name counts as the name (`_glob_could_name_env`).

- Refused: a redirect onto the file. A shell variable that holds its path, because the guard cannot follow a variable to its use. The file given to a command that is not a runner. Any other command that the guard reads as one that would read, write or commit it.
- Allowed: an existence check (`ls`, `test`, `[`, `[[`). `echo` and `printf`, where the name is text. The message or body value of `git commit` and `gh pr create`. A runner in `ENV_LOADER_COMMANDS` (node, npm, npx, pnpm, bun, deno, uv, docker, podman, and their variants) given `--env-file` or `--env-file-if-exists`, except that node, bun and deno given the file must run a script file, not inline code or a stdin script. A runner that starts a child command (uv, docker, podman, npm, npx, pnpm) must not start one that prints its environment, or a shell string that does (`ENV_CHILD_REASON`).
- Interpreter code (`python -c`, `node -e`, python and node heredoc bodies, quoted or not) is judged by its string literals, one path each, read by guard_core `code_paths`. Text uses (printed, written as content, dumped as JSON, compared) and existence checks (`os.path.exists`, `Path(p).is_file()`, `fs.existsSync`, also through a join) are allowed, as `echo` and `ls` are. Every other use of the file, or a literal whose use is unknown, is refused (`ENV_CODE_REASON`). Code behind `uv run`, `poetry run` and `pipenv run` is judged too, and so is a heredoc written to a file that the same command runs with python or node. Comments are never read. Ruling: item 399 a, owner, 2026-11-08 06:08 CST.
- Substitutions (`$(...)`, backticks, `<(...)`) are judged as commands of their own, at any depth up to `ENV_MAX_DEPTH` (64). A deeper nest is refused. Each script that `inner_commands` returns (`sh -c`, `eval`, `env -S`, `docker exec`, `su -c`, `find -exec`, ssh) is judged as a command of its own by a recursive `env_refusal`, under the same cap. Not read: `docker run`, `watch`, and `bash --rcfile F -c`. The substitutions in an unquoted heredoc body are judged (`env_heredoc_refusal`). A quoted heredoc body is text for bash, except a python or node body, which is code (above).

Write form. In `judge`, a write tool call (Write, Edit, MultiEdit or NotebookEdit) whose target name is in the scope is refused (`is_env`). It reads the same matcher as the shell form.

Read form. The guard does not judge Read. It returns early for Read and Grep. The settings deny list refuses a Read call on a name that starts with `.env`, at any depth. It refuses an Edit call on the same names. Its `!` carve-outs keep `.env.example` readable and editable. That reading of the `!` carve-outs comes from Claude Code's permission docs. It is not measured.

The printed refusal names no file. It names the shape of the access (`ENV_REDIRECT_REASON`, `ENV_VARIABLE_REASON`, `ENV_RUNNER_REASON`, `ENV_INLINE_REASON`, `ENV_CHILD_REASON`, `ENV_CONTENTS_REASON`, `ENV_DEPTH_REASON`, `ENV_CODE_REASON`, `ENV_TOOL_REASON`) and a remedy (`ENV_ADVICE`). The log holds the file name, for a person to read.

Known false alarms: debt `env-file-rule-false-alarms` (the env-file false-alarm debt). The guard refuses `ag -f` and `ack -f`, where `-f` is a boolean flag, `grep -r --exclude=.env`, and `rg -t py .env`. All four are safe. None reads a file's contents.

Why: the user's own secrets must not enter the session. `.envrc` is in the scope for the same reason. The guard stops Claude's mistakes, not an attacker's form (`guard-guards-mistakes-only`, a guard stops mistakes, not an attacker).

Risk: likely risk (`building-guard-needs-incident`: a guard or check needs a mistake Claude has made or is likely to make in normal work). A session would likely read a `.env` or `.envrc` file while it debugs. No incident is on record. Landed 2026-09-16, the env-file rule. The guard_env module has held the rule since 2026-10-13.

Kind: process
Home: hooks/guard_env.py
Home: hooks/guard.py
