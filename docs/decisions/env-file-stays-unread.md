# The environment file stays unread

## The ruling

No session reads, writes or commits the contents of an environment file. The user manages that file, and its values stay out of the session. The guard refuses a shell command that would do any of those, and a write tool call that names the file. The settings deny list refuses a Read or Edit call on it. A runner may load the file into its own process with its loader flag. The guard stops node, bun and deno given the file when they run inline code (`-e`, `-p`, `--eval`, `--print`, deno's `eval`) or a script read from stdin (`-`, a pipe, a heredoc, a here-string or a `<` file), since that code can print the variables. It does not catch deno's `run -`, which reads stdin after the word `run`. It does not read a script file: a script the session wrote can still print them.

One scope covers every form: a write tool call, a shell command and a Read call. A name is any basename that starts with `.env`, except `.env.example`. The guard's forms read one shared basename matcher in guard_env (`names_env_file`).

Ruling: owner, Queue item 159 answer a, 2026-11-02 00:56 CST. Reason: `.envrc` often holds exported secrets. That is the likely risk named below.

Shell form. `judge_shell` calls `env_refusal` and `env_heredoc_refusal`. A name is a word whose basename is in the scope above. A glob that could match a name counts as the name (`_glob_could_name_env`).

- Refused: a redirect onto the file. A shell variable that holds its path, because the guard cannot follow a variable to its use. The file given to a command that is not a runner. Any other command that would read, write or commit it.
- Allowed: an existence check (`ls`, `test`, `[`, `[[`). `echo` and `printf`, where the name is text. The message or body value of `git commit` and `gh pr create`. A runner in `ENV_LOADER_COMMANDS` (node, npm, npx, pnpm, bun, deno, uv, docker, podman, and their variants) given `--env-file` or `--env-file-if-exists`, except that node, bun and deno given the file must run a script file, not inline code or a stdin script.
- Substitutions (`$(...)`, backticks, `<(...)`) are judged as commands of their own, at any depth up to `ENV_MAX_DEPTH` (64). A deeper nest is refused. The substitutions in an unquoted heredoc body are judged (`env_heredoc_refusal`). A quoted heredoc body is text.

Write form. In `judge`, a write tool call (Write, Edit, MultiEdit or NotebookEdit) whose target name is in the scope is refused (`is_env`). It reads the same matcher as the shell form.

Read form. The guard does not judge Read. It returns early for Read and Grep. The settings deny list refuses a Read call on a name that starts with `.env`, at any depth. It refuses an Edit call on the same names. Its `!` carve-outs keep `.env.example` readable and editable. That reading of the `!` carve-outs comes from Claude Code's permission docs. It is not measured.

The printed refusal names no file. It names the shape of the access (`ENV_REDIRECT_REASON`, `ENV_VARIABLE_REASON`, `ENV_RUNNER_REASON`, `ENV_INLINE_REASON`, `ENV_CONTENTS_REASON`, `ENV_DEPTH_REASON`, `ENV_TOOL_REASON`) and a remedy (`ENV_ADVICE`). The log holds the file name, for a person to read.

Known false alarms: two open notes in the debt notes. Both hold at this head. Main: code read, not probed.

- Note `env-cwd-prose-false-alarm` (printed text read as a variable): `echo "(cwd=.envs)"` and `python3 -c "print('x (cwd=.envs):')"` are refused. The guard reads `(cwd=.envs)` as a shell variable that holds an env path.
- Note `jq-lone-word-false-alarm` (a lone program word): `jq .envs` and `cat f | jq .environment` are refused. A lone word may be the file, so the guard judges it.
- Note `jq-lone-word-false-alarm` (a value flag before the program word): `jq --arg k v .environment f.json`, `jq --indent 2 .envs f.json` and `yq -o json .envs f.yaml` are refused. The guard does not know that `--arg`, `--indent` and yq's `-o` take a value. So the value is read as the program word, and the real one is judged.

Allowed forms:

- `ag -f` and `ack -f` are boolean flags. They name no pattern file.
- The values of `grep --exclude` and `--exclude-dir`, and of `rg -t` and `-T`.
- A `jq`, `gojq` or `yq` program word, when a file word follows it. A switch such as `-C` does not hide that file word.
- `mkdir` on an env-prefixed folder, such as `mkdir .envs`, reads no contents.
- `cd` and `pushd` into such a folder are refused. The shell keeps its folder between calls.
- `git add` and `cat` on such a folder are refused. The guard cannot tell a folder from a file.
- In each allowed form, the env name is a pattern, an excluding glob, a type name, a program or a folder name. It is never a file that is read.

ag regex:

- Without a hidden flag, ag skips dotfiles, so its file regex is not judged.
- With a hidden flag, the guard judges the regex from `-G` or `--file-search-regex`. `-p` names an ignore-pattern file, judged as a path.
- The guard reads the regex as the shell gives it to ag, in bash or PowerShell. A PowerShell single quote keeps its backslashes.
- The guard tries the regex, bare and with a `./` prefix, on `.env`, `.envrc`, `.env.local`, `.env.production`, `.env.development`, `.env.test` and `.env.staging` (`ENV_SAMPLE_NAMES`).
- It also tries the names the regex could pick, built from its parse tree, with and without the leading dot. A regex that matches one is refused. Examples: `\.env\.prod$`, `env\.prod$`, and `\.env[A-Z]*\.md$`, whose empty repeat picks `.env.md`.
- A POSIX class such as `[[:alpha:]]` or `[[:^alpha:]]` is first written out as ranges.
- A regex with too many shapes is read again in a lean form. Each repeat takes its least count, and each class or dot offers one letter. So `.*a.*b.*c.*d.*e.*f` is judged by the names it can pick.
- A regex is refused when it does not compile, holds an unknown POSIX class, or still has too many shapes in the lean form.

Folder walk:

- With a hidden flag, rg and ag reach each env file in a folder they walk, whatever its name. The hidden flags are `--hidden`, rg's `-.`, and `-u` (`--unrestricted`). ag needs one `-u`. rg needs two.
- rg also walks for any positive `-g` or `--iglob` glob, even with no hidden flag. The walk judges the glob against each env file it finds. Such a glob overrides the ignore rules, and rg enters an ignored folder that the glob picks.
- rg matches a glob with a `/` against the path from the working folder. So `rg -g 'sub/*' K sub` reads each file in `sub`.
- A recursive grep reaches them with no flag. `grep`, `egrep` and `fgrep` recurse with `-r`, `-R`, `-d recurse`, `--directories=recurse`, `--recursive` or `--dereference-recursive`. `rgrep` always recurses.
- The guard refuses a search when a path word is a folder that holds an env file on disk. It also refuses when no path is named, because the working folder is walked.
- For rg and ag, a pipe or `<` into the search clears the no-path case. For grep it does not.
- A folder with no env file stays allowed. So does `rg --files`, which lists names and reads nothing.
- Grep decides each file by its last matching `--include` or `--exclude` glob, so an exclude before an include re-includes the env file. An exclude glob or `--exclude-dir` that skips the env file clears the search. The refusal names `--exclude` and `--exclude-dir` as the remedy, and prints no file name.
- `--include`, `-g`, `--glob` and `--exclude-from` stay judged, since each can name the file.
- The walk is `_env_walk`. It expands an unquoted comma brace list, such as `{a,b}`, in each word, as bash does. It expands a glob in a path word as the shell does, with no dotfile match. A path word that starts with `$PWD`, `${PWD}` or a `pwd` substitution is the working folder.
- For rg and ag with no flag that turns the ignore rules off, an ignored file or folder is not read or counted. The walk does not enter an ignored folder. The list is git's own, read once per walk. grep reads ignored files, so they count for grep.
- The ignore rules are off with `-u` (any count), `--no-ignore` and its variants. For ag, `-U`, `-a`, `--skip-vcs-ignores` and `--all-types` also turn them off. A tracked file is never ignored.
- The walk stops at 50000 entries, `node_modules` included. It then refuses with a reason that says the folder is too large to check, never that it holds an env file.
- A folder is always walked, and an env file that an include glob picks is refused at any folder size, whatever its suffix: `--include='*.yaml'` picks an env file that ends `.yaml`. The glob decides only the cap. Past it, a glob that no sample env file name matches, such as `*.py`, is allowed, and any other include glob is refused as too large to check. An rg `-t` type past the cap is refused. The sample-name test is `_glob_could_name_env`, the one home of the question.
- A `cd` after `&&` or `||` might not run, so the search is judged in the folder before it and the folder after it. A search in a command substitution runs where the segment that holds it runs, so `cd D && x=$(rg --hidden K)` is judged in D.
- `bash -c -- 'STRING'` runs the string after the `--`, as `bash -c 'STRING'` does.
- `git grep` reads its first plain word as a pattern, so an env name in it is text. A path after it stays judged.
- With a hidden flag, rg `-T` excludes only a type. The search still reaches the env file, so a pattern or a path that names one is refused. With `-t`, only a path that names one is refused.

Known limits:

- rg fails closed. An rg flag in neither of its flag tables might take a value, so the guard may walk the working folder too.
- ag and grep do not fail closed. An unknown flag there is read as a switch, so the walk can miss a folder the search reads.
- An rg `!` glob is not read.
- A brace sequence, such as `{a..c}`, is not expanded.
- A literal `cd <dir>` earlier in the command is followed, so the search is judged in the folder it runs in. A `cd` the guard cannot resolve (a variable, `popd`, a folder that does not exist) leaves the walk at the starting folder. Other variables and substitutions in a path word are not resolved. A search that runs only when its conditional `cd` ran (`test -d D && cd D && rg K`) is judged in the folder before the `cd` too, so a start folder with an env file refuses it. Only the all-run, all-skipped and each-one-skipped cases are tried when several `cd` are conditional.
- A string that `bash -c`, `sh -c` or `eval` runs is walked as a command of its own. `zsh`, `dash`, `ksh` and `bash` with a script file are not looked into.
- Accepted limit: past the cap, an rg `-g` or `--iglob` glob, or a grep `--include` glob, that matches none of the sample env file names, such as `*.py`, is allowed. A name with an env stem and a `.py` suffix would match that glob and is read, out of the walk's sight. Under the cap the walk sees it.
- A search in a heredoc body is not walked.
- The walk sees a search behind a subshell paren, a `{ ...; }` group, `command`, `env` (with `--` too) or `nice` (with any form of its adjustment flag). A search behind `sudo`, `xargs` or `env -C` is not walked.
- An ignore file other than the checkout's own is not read. So a search of a folder with an env file is refused, even when such a file skips it.
- Accepted limit: a regex with no `.env` prefix of its own, such as `prod$`, is judged on the sample names only. Rewriting `\.py$` as the names it could pick would refuse every extension filter.

Why: the user's own secrets must not enter the session. `.envrc` is in the scope for the same reason. The guard stops Claude's mistakes, not an attacker's form (`guard-guards-mistakes-only`, a guard stops mistakes, not an attacker).

Risk: likely risk (`building-guard-needs-incident`: a guard or check needs a mistake Claude has made or is likely to make in normal work). A session would likely read a `.env` or `.envrc` file while it debugs. No incident is on record. Landed 2026-09-16, the env-file rule. The guard_env module has held the rule since 2026-10-13.

Kind: process
Home: hooks/guard_env.py
Home: hooks/guard.py
