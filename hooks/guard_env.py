"""The guard's env family: any read or write of an environment file.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import fnmatch
import re
import shlex
import warnings

from guard_core import (
    ASSIGNMENT, DURATION, ENV_PATTERN_COMMANDS, FIND_EXEC_ACTIONS, INTERPRETER_HEREDOC, NODE_WORDS,
    POWERSHELL_CALL, PYTHON_WORDS, REDIRECT, SHELL_HEREDOC, TIMEOUT_FLAGS_BARE, TIMEOUT_FLAGS_WITH_VALUE,
    _interpreter_command, _split_heredocs, _walk_heredocs, _without_message_values, is_powershell, norm,
    script_language, segment_tokens, split_segments,
)


# ------------------------------------------------------------------ the environment file
#
# CLAUDE.md: the user manages the environment file, so its CONTENTS stay out of the session.
# Handing the file to a runner that loads it into its own environment prints nothing and puts
# nothing in the transcript, so this layer allows it by name.
#
# The check is a PATH TOKEN test and never a substring test. A substring test over the
# backslash-normalized command refuses both of these:
#
#   grep -n "dotenv|VERIFY_DATABASE_URL|process\.env" harness/browser/verify.mjs
#   ls -la .env
#
# The first is normalization doing it. `process\.env` became `process/.env`, so the ENVIRONMENT
# ACCESSOR that every source file uses read as a path. That command does NOT match before
# normalization, which is why this layer reads the command with its own separators intact. The
# second is a listing, and a listing reads no contents at all.
#
# The shape is a path token and then a NAMED allowance. The default is refusal, so a printer, a
# writer and a commit each need no enumeration: `cat`, `>`, `tee` and `git add` are simply not on
# the allow list, and neither is the next one nobody thought of.

ENV_ALLOWED = ".env.example"
ENV_PREFIX = ".env"


def names_env_file(name: str) -> bool:
    """The one predicate for an environment file's BASENAME, in every form of the guard.

    A name is held when it starts with `.env`: `.env`, `.env.local`, `.envrc`, `.environment`. The
    whole name `.env.example` is the one exception. It is checked in and is documentation. A variant
    is held, because it holds the same secrets. The Write and Edit form (`is_env`) and the shell form
    (`env_reference`, `_glob_could_name_env`) both call this, so no form reads a narrower name.
    """
    return name.startswith(ENV_PREFIX) and name != ENV_ALLOWED

# A word prefix that is a PATH, for deciding whether a backslash before `.env` is a separator or a
# regex escape. `.\.env` and `C:\Users\me\.env` are paths. The `process\.env` in a grep pattern is
# not. A separator is followed by a path segment, while `\.` and `\\` are regex escapes.
#
# Reading ANY backslash as a separator refuses `grep "import\.meta\.env"`, because the head
# `import\.meta` holds a backslash. One identifier deeper than the first case, and the same defect.
#
# The residue, stated rather than hidden: a RELATIVE Windows path whose every segment after the
# first begins with a dot, such as `foo\.config\.env`, is no longer read as a path. Text alone
# cannot tell it from a regex. The absolute form and the forward-slash form are unaffected.
ENV_PATH_PREFIX = re.compile(r"^(\.{1,2}|~|[A-Za-z]:|\S*(/|\\(?![.\\]))\S*)$")

# Runners that read the file into their own environment and echo nothing. `npm` and `npx` reach the
# flag through node, so `node --env-file=.env <npm-cli.js> run x` is the npm form.
ENV_LOADER_COMMANDS = (
    "node", "node.exe", "npm", "npm.cmd", "npm-cli.js", "npx", "npx.cmd", "npx-cli.js",
    "pnpm", "pnpm.cmd", "bun", "bun.exe", "deno", "deno.exe", "uv", "uv.exe",
    "docker", "docker.exe", "docker-compose", "docker-compose.exe", "podman", "podman.exe",
)
ENV_LOADER_FLAGS = ("--env-file", "--env-file-if-exists")

# A runner that runs inline code (`-e`, `-p`, a stdin script) has the file's variables in scope and
# can print them. Only these runners take inline code, and only the loader commands among them
# reach the check.
ENV_INLINE_RUNNERS = ("node", "node.exe", "bun", "bun.exe", "deno", "deno.exe")
# Runner options that take the next word as a value, so that word is no script. The `=` forms are one word.
ENV_RUNNER_VALUE_FLAGS = (
    "--env-file", "--env-file-if-exists", "-r", "--require", "--import", "--loader", "-C",
    "--conditions", "--input-type", "--experimental-loader", "--preload",
)
# A second copy of guard_frozen.py's `_NODE_EVAL_FLAG`, kept on purpose: this one also reads the
# `=` forms (`--eval=code`), which that one does not.
ENV_INLINE_FLAG = re.compile(r"^(?:-[ep]{1,2}|--eval|--print)(?:=.*)?$")

# Commands that ask whether the file is THERE. They read no contents.
ENV_EXISTENCE_COMMANDS = ("ls", "test", "[", "[[")

# `find` tests that take a name pattern, and the actions that act on a match. A pattern after one of
# those tests lists the file's name and reads no contents, as `ls` does, when the segment holds no
# action that runs a command, deletes, or writes the match list to a file, and its output goes to the
# terminal or a message value, straight or through a chain of filters that run no command
# (`ENV_FIND_FILTERS`). A redirect to a file, another substitution, or any other pipe stage hands the
# names to a command that may read them (`_find_output_on_screen`).
ENV_FIND_NAME_TESTS = (
    "-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename", "-regex", "-iregex")
ENV_FIND_ACTIONS = FIND_EXEC_ACTIONS + ("-delete", "-fprint", "-fprint0", "-fprintf", "-fls")
# Commands that read a pipe and run nothing and open no file named by it.
ENV_FIND_FILTERS = ("wc", "sort", "uniq", "head", "tail", "cut", "tr", "nl")

# Commands that only print their own arguments. An env name among the arguments is TEXT, printed to
# stdout or written to a file that is NOT an environment file (`echo <name> > .worktreeinclude`),
# and no environment file is read or written. A redirect onto an environment file is refused first. `cat <name> > x` is not on the list, so it stays held.
ENV_TEXT_COMMANDS = ("echo", "printf")


# How a search or script command reads its flags. A flag that takes the PATTERN or the program (`-e`,
# `--regexp`, `--expression`, `--source`) marks the word it carries as no path. A flag that names a
# FILE of patterns or of a program (`-f`, `--file`) marks nothing: that file is read, so it is
# judged. Once either one is met, every plain word is a file, and none is read as the pattern.
ENV_PATTERN_LONG = ("--regexp", "--expression", "--source")
ENV_FILE_LONG = ("--file", "--from-file")
# A flag's own value stands before the pattern and is never it: a count, a glob, a file filter.
ENV_VALUE_LONG = (
    "--max-count", "--context", "--after-context", "--before-context", "--include", "--exclude",
    "--exclude-dir", "--exclude-from", "--glob", "--max-depth", "--max-filesize", "--type",
    "--file-search-regex",
)
# The value of these flags is a glob that EXCLUDES files, so it reads nothing and is no path.
# `--include`, `-g`, `--glob` and `--exclude-from` are not here: each names a file or a file of
# names, or a glob that includes the file, and stays judged.
ENV_EXCLUDE_LONG = ("--exclude", "--exclude-dir")
ENV_VALUE_SHORT = "ABCmgd"
# `sed` and `awk` read a script, and its first plain word is a regex, never a path. `awk -F` and
# `-v` take a value of their own.
ENV_SCRIPT_COMMANDS = ("sed", "awk", "gawk", "mawk", "nawk")
ENV_SCRIPT_VALUE_SHORT = "Fv"
# Per-command flag letters, for the letters that differ between the search tools. `-f` takes a file
# of patterns in grep and rg, and is a plain switch in ag and ack. `-t` and `-T` take a file type in
# rg only: in ag `-t` is a switch, so a `t` in the shared letters would swallow a path.
ENV_BOOLEAN_F_COMMANDS = ("ag", "ack")
# `ag -G` takes a regex that picks the files to search, and `ag -p` a file of ignore patterns, which
# is judged as a path. In grep `-G` is a plain switch, so the letters are not shared.
ENV_VALUE_SHORT_BY_COMMAND = {"rg": "tT", "ag": "Gp"}
# The value of these letters is no path, so it is skipped: after rg `-t` or `-T` a file type name,
# after ag `-G` a file regex, judged by `_ag_hidden_regex_refusal` instead.
ENV_NO_PATH_SHORT_BY_COMMAND = {"rg": "tT", "ag": "G"}
# A hidden flag makes a search read dotfiles: `--hidden`, `--unrestricted`, `-u`, and rg `-.`. rg
# `-u` alone skips no hidden file, but it counts here: main refuses that form too.
ENV_HIDDEN_LONG = ("--hidden", "--unrestricted")
ENV_HIDDEN_SHORT = "u."
# rg `-T` excludes a file type, so with a hidden flag the search still reaches the env file, and a
# pattern that names one stays judged. `-t` searches only the named type, so its pattern is skipped.
ENV_RG_TYPE_NOT_SHORT = "T"
# With a hidden flag, ag searches dotfiles, so it reads each env file whose name its file regex
# (`-G`, `--file-search-regex`) matches. The regex is tried on a sample of env file names, bare and
# with the `./` that ag prefixes. Without a hidden flag ag skips dotfiles, so the regex is not judged.
ENV_AG_REGEX_LONG = "--file-search-regex"
ENV_SAMPLE_NAMES = tuple(ENV_PREFIX + suffix for suffix in (
    "", "rc", ".local", ".production", ".development", ".test", ".staging"))
# `jq`, `gojq` and `yq` take a program as the first plain word: a key path such as `.envs` is text.
# Their file arguments stay judged. Their `-e` is an exit-status switch, not a pattern flag, and
# `-f` / `--from-file` names a file of the program.
ENV_PROGRAM_COMMANDS = ("jq", "gojq", "yq")
# The program commands do not read flags as grep does: `-C` is a colour switch there, so a grep value
# letter would swallow the next word and leave a file read as the program. Only jq's and gojq's `-L`
# takes a value, a module directory, which is judged as a path. yq has no short value letter here.
ENV_PROGRAM_VALUE_SHORT = {"jq": "L", "gojq": "L", "yq": ""}
ENV_YQ_SUBCOMMANDS = ("e", "eval", "ea", "eval-all")
# `mkdir` makes a folder and reads no contents, so an env-prefixed folder name (`.envs`) is no read.
# `cd` and `pushd` stay refused: the shell keeps its folder between calls, so a later read in that
# folder cannot be tied to the move. `git add` and `cat` stay refused: they cannot tell a folder
# from a file. Not merged into ENV_EXISTENCE_COMMANDS, which ENV_RELAY_SAFE reuses.
ENV_FOLDER_COMMANDS = ("mkdir",)

# The message or body of a commit or a pull request is text. Its value is blanked before the words
# are read, so an env name in prose reads no contents. A substitution in the value is cut out
# and judged as a command first, by `_substitutions`.
ENV_MESSAGE_COMMAND = re.compile(r"\s*(git\s+commit|gh\s+pr\s+create)\b")
ENV_MESSAGE_ARG = re.compile(
    r"""(?P<flag>(?:-m|--message|--title|--body)(?:=|\s+))"""
    r"""(?P<value>"(?:[^"\\]|\\.)*"|'[^']*')""")


def _blank_messages(segment: str) -> str:
    if not ENV_MESSAGE_COMMAND.match(segment):
        return segment

    def blank(match):
        value = match.group("value")
        return match.group("flag") + value[0] + "x" + value[0]

    return ENV_MESSAGE_ARG.sub(blank, segment)

ENV_ADVICE = (
    "(decision env-file-stays-unread, a session never reads an environment file). "
    "Remedy: ask the user for the value and never read the file. "
    "To RUN something that needs those variables, hand the file to the runner with the "
    "--env-file flag ahead of node, npm, npx or a container command. "
    "That loads it into one process's own environment and prints nothing. "
    "A runner given the file runs a script file: put the code in a script file, not inline. "
    "A listing and a test for existence are allowed."
)

# Runners that start a child command. Per runner, the options that take the next word as a value
# and the options that take none, each read from the tool's own help. DESIGN: a flag in neither
# list may be either, so `_child_starts` reads it both ways (a false alarm at most); every `--no-*`
# flag is a bool unless the value list names it. Only the node scan keeps a closed list, in
# `_first_positional`. `-c` of npm and pnpm is the child's shell string, so it is in neither list.
ENV_NPM_RUNNERS = tuple(c for c in ENV_LOADER_COMMANDS if c.startswith(("npm", "npx", "pnpm")))
ENV_CHILD_VALUE_FLAGS = {
    "node": ENV_RUNNER_VALUE_FLAGS,
    # `npm exec --help`, plus npm's own config options that most often precede the child.
    "npm": (
        "--env-file", "-w", "--workspace", "-p", "--package", "--prefix", "--loglevel", "--registry",
        "--cache", "--userconfig", "--node-options", "--script-shell"),
    # `pnpm help exec` and `pnpm help dlx`.
    "pnpm": (
        "--env-file", "-C", "--dir", "--loglevel", "--resume-from", "--workspace-concurrency",
        "--reporter", "-F", "--filter", "--filter-prod", "--test-pattern",
        "--changed-files-ignore-pattern", "--package", "--allow-build"),
    # `bun x --help`.
    "bun": (
        "--env-file", "-p", "--package", "--cwd", "--minimum-release-age", "--registry", "--ca",
        "--cafile"),
    # `uv run --help`.
    "uv": (
        "--env-file", "--extra", "--no-extra", "--group", "--no-group", "--only-group",
        "--no-editable-package", "-w", "--with", "--with-editable", "--with-requirements",
        "--package", "--python-platform", "--index", "--default-index", "-i", "--index-url",
        "--extra-index-url", "-f", "--find-links", "--index-strategy", "--keyring-provider", "-P",
        "--upgrade-package", "--upgrade-group", "--resolution", "--prerelease", "--fork-strategy",
        "--exclude-newer", "--exclude-newer-package", "--no-sources-package", "--reinstall-package",
        "--link-mode", "-C", "--config-setting", "--config-settings-package",
        "--no-build-isolation-package", "--no-build-package", "--no-binary-package", "--cache-dir",
        "--refresh-package", "-p", "--python", "--color", "--allow-insecure-host", "--directory",
        "--project", "--config-file"),
    # `docker run --help`, which `docker container run`, `podman run` and `exec` share (`exec` takes
    # a subset), and `docker compose`'s global `-f`, `--file`, `--project-name` and `--profile`.
    "docker": (
        "--add-host", "--annotation", "-a", "--attach", "--blkio-weight", "--blkio-weight-device",
        "--cap-add", "--cap-drop", "--cgroup-parent", "--cgroupns", "--cidfile", "--cpu-count",
        "--cpu-percent", "--cpu-period", "--cpu-quota", "--cpu-rt-period", "--cpu-rt-runtime", "-c",
        "--cpu-shares", "--cpus", "--cpuset-cpus", "--cpuset-mems", "--detach-keys", "--device",
        "--device-cgroup-rule", "--device-read-bps", "--device-read-iops", "--device-write-bps",
        "--device-write-iops", "--dns", "--dns-option", "--dns-search", "--domainname",
        "--entrypoint", "-e", "--env", "--env-file", "--expose", "--gpus", "--group-add",
        "--health-cmd", "--health-interval", "--health-retries", "--health-start-interval",
        "--health-start-period", "--health-timeout", "-h", "--hostname", "--io-maxbandwidth",
        "--io-maxiops", "--ip", "--ip6", "--ipc", "--isolation", "-l", "--label", "--label-file",
        "--link", "--link-local-ip", "--log-driver", "--log-opt", "--mac-address", "-m", "--memory",
        "--memory-reservation", "--memory-swap", "--memory-swappiness", "--mount", "--name",
        "--network", "--net", "--network-alias", "--oom-score-adj", "--pid", "--pids-limit",
        "--platform", "-p", "--publish", "--pull", "--restart", "--runtime", "--security-opt",
        "--shm-size", "--stop-signal", "--stop-timeout", "--storage-opt", "--sysctl", "--tmpfs",
        "--ulimit", "--umask", "-u", "--user", "--userns", "--uts", "-v", "--volume",
        "--volume-driver", "--volumes-from", "-w", "--workdir", "-f", "--file", "--project-name",
        "--profile"),
}
ENV_CHILD_BOOL_FLAGS = {
    "npm": (
        "-y", "--yes", "-q", "--quiet", "-s", "--silent", "-f", "--force", "-g", "--global",
        "--verbose", "--offline", "--prefer-offline", "--prefer-online", "--ignore-scripts",
        "--json", "--dry-run", "--foreground-scripts", "-ws", "--ws", "--workspaces",
        "--include-workspace-root", "--fund", "--audit", "--no", "--color"),
    "pnpm": (
        "-r", "--recursive", "-w", "--workspace-root", "-s", "--silent", "--stream", "--parallel",
        "--aggregate-output", "--report-summary", "--use-stderr", "--fail-if-no-match", "--color"),
    "bun": ("--bun", "--no-install", "--trust", "--ignore-scripts", "--verbose", "--silent"),
    "uv": (
        "--all-extras", "--no-dev", "--no-default-groups", "--all-groups", "-m", "--module",
        "--only-dev", "--dev", "--no-editable", "--exact", "--no-env-file", "--isolated", "--active",
        "--no-sync", "--locked", "--frozen", "-s", "--script", "--gui-script", "--all-packages",
        "--no-project", "--no-index", "-U", "--upgrade", "--no-sources", "--reinstall",
        "--compile-bytecode", "--no-build-isolation", "--no-build", "--no-binary", "-n",
        "--no-cache", "--refresh", "--managed-python", "--no-managed-python",
        "--no-python-downloads", "--system-certs", "--offline", "--no-progress", "--no-config",
        "-q", "--quiet", "-v", "--verbose", "--help"),
    "docker": (
        "-d", "--detach", "-i", "--interactive", "-t", "--tty", "-P", "--publish-all", "-q",
        "--quiet", "--privileged", "--init", "--read-only", "--rm", "--sig-proxy",
        "--oom-kill-disable", "--use-api-socket", "--help"),
}
ENV_SHELL_C_FLAG = re.compile(r"^-[A-Za-z]*c[A-Za-z]*$")
ENV_PRINT_PROGRAMS = ("env", "env.exe", "printenv", "printenv.exe")
# Words that open a group or a clause and run the command after them: `{ env; }`, `( env )`,
# `! env`, `if true; then env; fi`. `_shell_string_prints` reads the command past them.
ENV_GROUP_WORDS = ("(", "{", "!", "if", "then", "else", "elif", "do", "while", "until")
# The process environment as a file: `cat /proc/self/environ`, `/proc/<pid>/environ`, `/proc/$$/environ`.
# A pid may be a glob: `/proc/*/environ`, `/proc/[0-9]*/environ`.
ENV_PROC_ENVIRON = re.compile(r"/proc/(?:self|thread-self|[\d*?\[\]!^-]+|\$\$|\$\{?\w+\}?)/environ(?!\w)")
# An inline script that names the environment: perl `%ENV` and `$ENV{`, ruby `ENV[` and `ENV.`, awk
# `ENVIRON`. A bare word ENV is text (`perl -pe 's/ENV/prod/'`), except ruby's own `p ENV`: there it
# is the constant, when no slash, quote, bar or brace sits against it and it is outside a string
# literal (`puts "the ENV var"` is text). Only the code is read (`_script_code`), never a script
# name, its arguments or a file name (`ruby script.rb ENV`, `awk '{print}' ENV.txt`).
ENV_SCRIPT_PROGRAM = re.compile(r"(?:perl|ruby|[gmn]?awk)[\d.]*(?:\.exe)?")
ENV_SCRIPT_ENV_WORD = re.compile(r"[%$@]ENV\b|\bENVIRON\b|\bENV(?=[\[.])")
ENV_RUBY_ENV_WORD = re.compile(r"(?<![\w/'\"|{}])ENV(?![\w/'\"|{}])")
# A ruby string literal, `"..."` or `'...'`, with its backslash escapes. A quote with no mate is
# no literal. A `#{...}` in a double-quoted one is code, so its text stays.
ENV_RUBY_STRING = re.compile(r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'""", re.S)
ENV_RUBY_INTERPOLATION = re.compile(r"#\{([^{}]*)\}")
# The perl and ruby option letters whose value is code (`-e`, `-ne`, `-E`), and the letters whose
# value is the rest of the word (`-Mstrict`, `-i.bak`, `-rjson`), so an `e` in that rest is no `-e`.
ENV_SCRIPT_CODE_LETTERS = {"perl": "eE", "ruby": "e"}
ENV_SCRIPT_VALUE_LETTERS = {"perl": "CDFIMdimx", "ruby": "CEFIKTWirx"}
# awk options that take a value. `-f` and `-E` name a program file; `-e` and `--source` hold code.
ENV_AWK_VALUE_FLAGS = (
    "-F", "-v", "-f", "-E", "-e", "-i", "-l", "--field-separator", "--assign", "--file", "--exec",
    "--source", "--include", "--load")
ENV_AWK_PROGRAM_FLAGS = ("-f", "--file", "-E", "--exec", "-e", "--source")
# The shell strings that perl and ruby code runs: `system("env")`, `exec 'env'`, a backtick pair,
# `qx(env)`, `%x(env)`. Each is judged by `_shell_string_prints`.
ENV_SCRIPT_SHELL_STRING = re.compile(
    r"""(?:system|exec|spawn|popen)\s*\(?\s*(["'])((?:(?!\1).)*)\1|`([^`]*)`"""
    r"""|(?:qx|%x)\s*(?:\(([^)]*)\)|\{([^}]*)\}|\[([^\]]*)\]|\|([^|]*)\||/([^/]*)/)""")
# `docker compose config` prints each service's resolved environment, the file's values among them.
# With one of the listing flags it prints names, hashes or nothing, glued `=` forms too (`--hash="*"`).
ENV_COMPOSE_PRINTERS = ("config", "convert")
ENV_COMPOSE_LISTING_FLAGS = (
    "--services", "--volumes", "--profiles", "--images", "--hash", "-q", "--quiet")
# THE PRINTED REASONS, AND NONE OF THEM NAMES A FILE. Each one says which shape of access fired,
# so the reader knows what to change, and the log carries the file name for a person to read.
ENV_REDIRECT_REASON = "a redirect would overwrite an environment file"
ENV_VARIABLE_REASON = (
    "a shell variable holds the path of an environment file, and the guard cannot follow "
    "a variable to where it is used"
)
ENV_RUNNER_REASON = (
    "only a runner may be handed an environment file with the loader flag, and this command "
    "is not a runner"
)
ENV_INLINE_REASON = (
    "a runner given an environment file may run a script file, not inline code"
)
ENV_CHILD_REASON = (
    "a runner given an environment file may run a program, not a command that prints "
    "its environment"
)
ENV_CONTENTS_REASON = (
    "this command would read, write or commit the contents of an environment file"
)
ENV_TOOL_REASON = (
    "an environment file holds the user's own secrets, and this tool would put the contents "
    "in the session"
)


# A `<` redirect (not `<<` or `<<<`), spaced into a word of its own. The word after it is READ.
READ_REDIRECT = re.compile(r"(?<![<])<(?![<(])")
# ASSIGNMENT (a leading `VAR=value`) is defined once, above, and shared with `resolve_command`.


def _ampersand_split(segment: str):
    """Split one `split_segments` segment further, on a bare, unquoted `&`.

    `split_segments` cuts on `;`, `|`, `||`, `&&` and newline, but not on a LONE `&`, because
    that splitter serves callers for whom a backgrounded command is still one segment. The
    environment layer needs the opposite: a background job is its own command, so `cat .env &`
    must not let the backgrounding operator hide the read behind an empty tail. This is the one
    genuinely different rule env_refusal needs on top of `split_segments`, kept small and
    quote-aware the same way: text inside a quote is never split, whatever character it holds.
    """
    parts = []
    current = []
    quote = ""
    for char in segment:
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            continue
        if char in ("'", '"'):
            quote = char
            current.append(char)
            continue
        if char == "&":
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


# The deepest nest of substitutions the guard reads. A command nested deeper is REFUSED: a nest this
# deep is far more likely a runaway than a command Claude writes, and an unbounded read would hit
# Python's recursion limit. A crash fails open, so past the bound the guard refuses instead.
ENV_MAX_DEPTH = 64
ENV_DEPTH_REASON = "substitutions are nested too deep for the guard to read"


def _substitutions(cmd: str, depth: int = 0, powershell: bool = False, heredoc: bool = False,
                   arithmetic: bool = True):
    """Return ([(text, in a message)], too_deep). The last text is the command itself.

    One pass, no recursion. Each command substitution `$(...)`, backtick pair or process
    substitution `<(...)` `>(...)` met OUTSIDE single quotes is its own text, and its place in the
    text around it is `x`. Every text is then judged as a command of its own, at any depth. The
    work is linear: a text holds only its own characters and one `x` per child.

    ponytail: a backtick body is read again by a recursive call. A nested backtick needs a
    backslash per level, so honest input never nests them, and past ENV_MAX_DEPTH it is refused.

    `powershell` reads PowerShell's escape: a backtick escapes the next character, as a backslash
    does in bash, and opens no substitution. A backslash is then a plain character. `heredoc`
    reads an unquoted heredoc body: there a quote mark is text, until a substitution opens.

    An unquoted `#` at a word start is a comment to the end of the line: its text stays in the
    text around it, and opens no quote and no substitution. A heredoc body has no comments.

    With `arithmetic` False, the text of a `$(( ))` arithmetic expansion is left out: it runs no
    command. Bash reads `$((` as arithmetic only when the paren after `$(` closes right before the
    last `)`; `$((a) )` and `$((a); (b))` are command substitutions and stay in. A substitution
    inside the arithmetic is a text of its own and stays in.
    """
    escape = "`" if powershell else "\\"
    if depth > ENV_MAX_DEPTH:
        return [], True
    done = []
    # a frame: [pieces of its text, open quote, paren depth, it is a message value, its open
    # quote holds a message value, it is still a `$(( ))` arithmetic expansion]
    stack = [[[], "", 0, False, False, False]]
    i, n = 0, len(cmd)

    def close():
        pieces, _, _, message, _, arith = stack.pop()
        if arithmetic or not arith:
            done.append(("".join(pieces), message))

    def opens_message(pieces):
        """True when a `"` opened now is the value of a message flag of a commit or a PR."""
        if not re.search(r"(?:-m|--message|--title|--body)(?:=|\s+)$", "".join(pieces[-12:])):
            return False
        tail = []
        for piece in reversed(pieces):
            if piece in ";|&\n":
                break
            tail.append(piece)
        return bool(ENV_MESSAGE_COMMAND.match("".join(reversed(tail))))

    while i < n:
        char = cmd[i]
        frame = stack[-1]
        pieces, quote = frame[0], frame[1]
        if char == escape and quote != "'":
            pieces.append(cmd[i:i + 2])
            i += 2
            continue
        if char == "#" and quote == "" and not (heredoc and len(stack) == 1) and (
                not pieces or pieces[-1] in (" ", "\t", "\n", ";", "|", "&", "(")):   # an escape pair is no boundary
            end = cmd.find("\n", i)
            end = n if end < 0 else end
            pieces.append(cmd[i:end])
            i = end
            continue
        if heredoc and len(stack) == 1 and char in "'\"":
            pass   # a quote mark in a heredoc body is text
        elif quote == "'":
            frame[1] = "" if char == "'" else quote
        elif char == "'" and quote == "":
            frame[1] = "'"
        elif char == '"':
            frame[1] = "" if quote == '"' else '"'
            frame[4] = quote == "" and opens_message(pieces)
        elif char == "`" and not powershell:
            j = i + 1
            while j < n and cmd[j] != "`":
                j += 2 if cmd[j] == "\\" else 1
            inner, deep = _substitutions(cmd[i + 1:j].replace("\\`", "`"), depth + 1, arithmetic=arithmetic)
            if deep:
                return [], True
            done.extend(inner)
            pieces.append("`x`")
            i = j + 1
            continue
        elif cmd[i:i + 2] == "$(" or (quote == "" and cmd[i:i + 2] in ("<(", ">(")):
            if len(stack) + depth > ENV_MAX_DEPTH:
                return [], True
            message = quote == '"' and frame[4]
            pieces.append("x")
            stack.append([[], "", 0, message, False, cmd[i:i + 3] == "$(("])
            i += 2
            continue
        elif quote == "" and len(stack) > 1 and char == "(":
            frame[2] += 1
        elif quote == "" and len(stack) > 1 and char == ")":
            if frame[2] == 0:
                close()
                i += 1
                continue
            frame[2] -= 1
            if frame[2] == 0 and cmd[i + 1:i + 2] != ")":
                frame[5] = False   # the paren after `$(` closed before the end: a subshell, not arithmetic
        pieces.append(char)
        i += 1
    while stack:
        close()
    # the outermost text closed last, so it is last
    return done, False


# ------------------------------------------------------------------ a script's shell spots
#
# A python, node, perl or ruby script is text to the shell that starts it. It reaches a shell only where it
# hands a string to one: a call such as os.system or subprocess.run, and in perl and ruby a backtick span,
# `qx(...)` or `%x(...)`. `script_spots` gives the shell text of those spots. Every other string of the
# script is data, so a `$(...)` or a backtick in it runs nothing.
_SPOT_CALLS = {
    "py": r"(?<![\w.])(?:os\s*\.\s*(?:system|popen|exec\w*|spawn\w*|posix_spawn\w*)|subprocess\s*\.\s*\w+"
          r"|Popen|check_output|check_call|getoutput|getstatusoutput)",
    "js": r"(?:(?<![\w$.])|(?<=\)\.)|(?<=\w\.))(?:execSync|execFileSync|spawnSync|execFile|spawn)"
          r"|(?:(?<![\w$.])|(?<=child_process\.)|(?<=cp\.)|(?<=\)\.))exec",
    "ruby": r"(?<![\w.$@:])(?:system|exec|spawn)(?!\w)"
            r"|(?<![\w.])(?:IO\s*\.\s*popen|Open3\s*\.\s*\w+|Kernel\s*\.\s*(?:system|exec|spawn))",
    "perl": r"(?<![\w.$@:>])(?:system|exec)(?!\w)",
}
# A call's name, then its open paren; perl and ruby also take a quote after a space (`system "cmd"`).
_SPOT_PAREN = r"\s*\("
_SPOT_BARE = r"|[ \t]+(?=['\"])"
_KEYWORD_ARG = re.compile(r"\s*(?:\*\*)?[A-Za-z_]\w*\s*(?:=(?!=)|:(?!:))")
_BRACKETS = {"(": ")", "{": "}", "[": "]", "<": ">"}
_COMMAND_OPEN = re.compile(r"(?:\bqx|%x)[ \t]*([^\w\s])")
# An argument whose shell text can be told: one string, or a bracket list of strings, with no interpolation.
_STRING = r"""'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`"""
_STRINGS = re.compile(r"\[\s*(?:(?:" + _STRING + r")\s*(?:,\s*(?:" + _STRING + r")\s*)*,?\s*)?\]|" + _STRING)
_INTERPOLATION = {"js": r"\$\{", "perl": r"[$@]", "ruby": r"#\{"}
# Node reaches a shell through child_process. A name bound to it is read only as `name.call(`.
_JS_CALLS = r"(?:execSync|execFileSync|spawnSync|execFile|spawn|exec)"
_JS_MODULE = r"""require\s*\(\s*(?P<quote>['"`])(?:node:)?child_process(?P=quote)\s*\)"""
_JS_BIND = re.compile(r"(?<![\w$.])(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*" + _JS_MODULE + r"\s*(?=[;\n]|$)")
_JS_DIRECT = re.compile(_JS_MODULE + r"\." + _JS_CALLS + r"\s*\(")


def _call_args(script: str, at: int, parens: bool):
    """The arguments of the call that starts at `at`, split at the commas outside quotes and brackets. A call
    with parens ends at its own close paren, one without at the end of its statement."""
    args, depth, quote, start, i = [], 0, "", at, at
    while i < len(script):
        char = script[i]
        if quote:
            if char == "\\":
                i += 2
                continue
            quote = "" if char == quote else quote
        elif char in "'\"`":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif char == "," and depth == 0:
            args.append(script[start:i])
            start = i + 1
        elif not parens and depth == 0 and char in ";\n":
            break
        i += 1
    return args + [script[start:i]]


def _command_spans(script: str):
    """The commands inside the backtick pairs, `qx(...)` and `%x(...)` of a perl or ruby script. The span
    of `qx` and `%x` ends at the bracket that closes the opener (nested pairs count), or at the same
    character again for a delimiter that is no bracket."""
    out = [found.group(1) for found in re.finditer(r"`([^`]*)`", script)]
    at = 0
    for opener in _COMMAND_OPEN.finditer(script):
        if opener.start() < at:
            continue   # inside the span of an earlier one
        open_char = opener.group(1)
        close_char = _BRACKETS.get(open_char, open_char)
        depth, end = 1, opener.end()
        while end < len(script) and depth:
            depth += (script[end] == open_char != close_char) - (script[end] == close_char)
            end += 1
        if depth == 0:
            out.append(script[opener.end():end - 1])
        at = end
    return out


def _literal_arg(arg: str, lang: str) -> bool:
    """True when the argument is one string or a bracket list of strings whose text the language does not fill
    in: a js template with `${`, a perl string in double quotes or backticks with `$` or `@`, or a ruby one
    with `#{`. A variable, a concatenation or a call is no literal."""
    if not _STRINGS.fullmatch(arg):
        return False
    return not any(each[0] != "'" and (lang != "js" or each[0] == "`") and re.search(_INTERPOLATION[lang], each)
                   for each in re.findall(_STRING, arg))


def _js_module_names(script: str):
    """The names a node script binds to child_process (`const cp = require('child_process')`), or None when it
    names the module any other way: a destructured or imported name, a call held in a variable or handed on,
    or a name used other than as `name.call(`. Those calls cannot be told."""
    names, told = [], [found.span() for found in _JS_DIRECT.finditer(script)]
    for bind in _JS_BIND.finditer(script):
        names.append(bind.group(1))
        told.append(bind.span())
    for name in names:
        for use in re.finditer(r"(?<![\w$.])" + re.escape(name) + r"(?![\w$])", script):
            if any(start <= use.start() < end for start, end in told):
                continue
            call = re.compile(re.escape(name) + r"\." + _JS_CALLS + r"\s*\(").match(script, use.start())
            if not call:
                return None
            told.append(call.span())
    for mention in re.finditer("child_process", script):
        if not any(start <= mention.start() < end for start, end in told):
            return None
    return names


def script_spots(script: str, lang: str = ""):
    """The shell text of each spot of a script where it hands a string to a shell: the call text of each shell
    call, and the command of each perl or ruby backtick span, `qx` and `%x`. `lang` is "py", "js", "perl" or
    "ruby", or '' for a script of unknown language (every language is tried). Python is read with `ast`
    (`guard_frozen.py_spots`): an alias resolves, a comment and a plain string are text, and a script it cannot
    tell reads whole. In the other languages, a call whose arguments hold no quote, a variable handed to a
    shell, reads the whole script: the string it holds cannot be told. So does a node script that names
    child_process other than as `name.call(` (`_js_module_names`)."""
    langs = [lang] if lang else list(_SPOT_CALLS)
    out = []
    if lang in ("", "py"):
        from guard_frozen import py_spots   # the home of the ast reading; it imports this module
        try:
            found = py_spots(script)
        except (SyntaxError, ValueError):
            pass   # python runs no line of it, so the pattern reader below only tries a literal name
        else:
            if found is None:
                return [script]
            out += found
            langs = [each for each in langs if each != "py"]
    for each in langs:
        calls = _SPOT_CALLS[each]
        if each == "js":
            names = _js_module_names(script)
            if names is None:
                return _whole_script(script, each)
            calls += "".join(r"|(?<=(?<![\w$.])" + re.escape(name) + r"\.)exec" for name in names)
        tail = _SPOT_PAREN + (_SPOT_BARE if each in ("perl", "ruby") else "")
        for call in re.finditer("(?:" + calls + ")(?:" + tail + ")", script):
            parens = call.group(0).rstrip().endswith("(")
            args = [arg.strip() for arg in _call_args(script, call.end(), parens)
                    if arg.strip() and not _KEYWORD_ARG.match(arg) and not arg.lstrip().startswith("{")]
            if not any(mark in arg for arg in args for mark in "'\"`") or (
                    each != "py" and not all(_literal_arg(arg, each) for arg in args)):
                return _whole_script(script, each)
            out.append(re.sub(r"\s*\($", "", call.group(0).rstrip()) + "(" + ", ".join(args) + ")")
    if lang in ("", "perl", "ruby"):
        out += _command_spans(script)
    return out


def _whole_script(script: str, lang: str):
    """The shell texts that stand for a script whose shell spots cannot be told: the script, and for js each
    of its string literals as the target of a write (`tee`). A node script joins a path into a command with
    `+`, so the path sits in a literal beside the call, and the script as shell text names it nowhere a write
    reads. This refuses more, never less."""
    if lang != "js":
        return [script]
    return [script] + ["tee " + shlex.quote(text) for text in (
        found.group(0)[1:-1] for found in re.finditer(_STRING, script)) if text.strip()]


def _elide_substitutions(text: str) -> str:
    """The text with each closed `$(...)` and backtick pair written as `x`. In the string of a script they are
    data. An unclosed one stays, so the words after it are still read."""
    out, i = [], 0
    while i < len(text):
        if text.startswith("$(", i):
            depth, end = 1, i + 2
            while end < len(text) and depth:
                depth += (text[end] == "(") - (text[end] == ")")
                end += 1
            if depth == 0:
                out.append("x")
                i = end
                continue
        elif text[i] == "`" and text.find("`", i + 1) >= 0:
            out.append("x")
            i = text.find("`", i + 1) + 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def substitution_commands(raw: str, stripped: str, outer: bool = False, arithmetic: bool = True):
    """The texts a shell runs INSIDE the command, each a command of its own: every `$(...)`, backtick
    and process substitution in `stripped`, plus those in an unquoted heredoc body of `raw`. A quoted
    shell heredoc body runs nothing and is gone from `stripped`; an interpreter heredoc body stays in
    `stripped` and is read as shell text, so a `$( )` in it can be a false alarm. With `outer`, the command itself is last, its substitutions read as `x`
    (`stripped` as it stands when the nest is too deep). A nest too deep to read gives no inner text:
    the env-file rule refuses it. With `arithmetic` False, a `$(( ))` arithmetic text is left out
    (`_substitutions`). The one home of this cut: judge_shell and git_env_command_hit call it.
    """
    found, too_deep = _substitutions(stripped, powershell=POWERSHELL_CALL[0], arithmetic=arithmetic)
    inner = [text for text, _in_message in found[:-1]]
    for quote, body, _ in _split_heredocs(raw)[1]:
        if not quote:
            body_found, body_deep = _substitutions(body, heredoc=True, arithmetic=arithmetic)
            too_deep = too_deep or body_deep
            inner = [text for text, _in_message in body_found[:-1]] + inner
    if too_deep:
        inner = []
    if outer:
        return inner + [stripped if too_deep else found[-1][0]]
    return inner


# A word that holds a glob. It is an environment word when it could match any name that
# `names_env_file` holds: a name that starts with `.env`, other than exactly `.env.example`. The test
# is a sample of the pattern itself (each glob filled in as the shortest and a one letter match), run
# through that same predicate, so `.env.s*`, `.envr*` and `.env.bak*` count with no list of suffixes
# to keep. No prefix of the example name is exempt: `.env.example*` could match `.env.example.bak`,
# which holds the same secrets, so it is refused.
#
# ACCEPTED LIMITS, each named so nobody trusts this layer past them:
#   - a brace or variable split (`.env{,.x}`, `.e$Xnv`) cannot be read statically;
#   - a dot glob such as `cat .*` or `tar .*` refuses, on purpose, as it sweeps in `.env`;
#   - `find -name '.env*'` lists names and is allowed, as `ls` is, while its output goes to the
#     terminal or a message value, straight or through filters that run no command
#     (`ENV_FIND_FILTERS`); a redirect to a file, another substitution, or any other pipe stage
#     refuses. `find .env -print` is judged as a name word and refuses;
#   - a relay split across two separate tool calls (write the name to a file in one, read the file
#     in the next) cannot be seen by a per-command guard;
#   - the relay check matches the literal path, so another spelling of the same file (`./f`, or
#     `~/f` against `$HOME/f`) is not caught. The guard does not resolve paths.
ENV_GLOB = re.compile(r"[?*\[]")
ENV_GLOB_PART = re.compile(r"\[[!^]?([^\]])[^\]]*\]|\?|\*")


def _glob_could_name_env(word: str) -> bool:
    if any(fnmatch.fnmatchcase(name, word) for name in (".env", ".env.x", ".envrc")):
        return True
    for fill in ("", "x"):
        sample = ENV_GLOB_PART.sub(
            lambda m: (m.group(1) or "a") if m.group(0) != "*" else fill, word)
        if names_env_file(sample):
            return True
    return False


def env_reference(word: str) -> str:
    """Return the environment file that one shell word names as a path, else ''.

    A reference is the WHOLE BASENAME of the word and never a substring of it. That one property
    keeps `process.env`, `import.meta.env` and `dotenv` out, because in none of them does `.env`
    end a path segment.

    The word is normalized first, the way the shell reads it: inner quotes go, so `.e""nv` and
    `'.e'nv` are `.env`, and so does a backslash that is not an escaped dot, so `.e\\nv` is. A
    glob that starts with a dot and could match a name, such as `.en?` or `.env*`, is the name.
    """
    word = re.sub(r"[\"'`]", "", word).strip("()")
    for separator in ("/", "\\"):
        head, found, tail = word.rpartition(separator)
        if not found:
            continue
        if separator == "\\" and not ENV_PATH_PREFIX.match(head):
            break  # `process\.env` is an escaped dot, not a Windows separator
        word = tail
        break
    word = re.sub(r"\\(?!\.)", "", word)
    if ENV_GLOB.search(word) and word.startswith("."):
        return word if _glob_could_name_env(word) else ""
    return word if names_env_file(word) else ""


# Read left to right, a `\\` pair is one escaped backslash, so the quote after it is real.
_ESCAPED_QUOTE = re.compile(r"""\\\\|\\['"]""")


def _rewrite_interpreter_bodies(cmd: str, rewrite) -> str:
    """Replace each python, node, perl or ruby heredoc body (no shell reads it) with
    `rewrite(body, header, quoted)`. `quoted` is true for a quoted delimiter, where the shell expands nothing."""
    own = []
    bodies = _walk_heredocs(cmd, own_heads=own)[1]
    for (quote, body, _), header in zip(bodies, own):   # each body is read by its own command
        header = _without_message_values(header)
        if body and INTERPRETER_HEREDOC(header) and not SHELL_HEREDOC(header):
            cmd = cmd.replace(body, rewrite(body, header, bool(quote)), 1)
    return cmd


def _plain_escaped_quotes(cmd: str) -> str:
    """Write a backslash-escaped quote in the body of a python, node, perl or ruby heredoc as a plain
    character. Those languages read the backslash as an escape, but the word reader below does not:
    a `\\'` would flip its quote state, and the prose after it would read as bare shell words."""
    if "<<" not in cmd or "\\" not in cmd:
        return cmd
    return _rewrite_interpreter_bodies(
        cmd, lambda body, _header, _quoted: _ESCAPED_QUOTE.sub(
            lambda m: m.group(0) if m.group(0) == "\\\\" else "_", body))


_PYTHON_HEADER = _interpreter_command(PYTHON_WORDS)
_NODE_HEADER = _interpreter_command(NODE_WORDS)
# A `//` line of a template literal ends at its line end, or sooner at the backtick or `${` that goes back to code.
_TEMPLATE_PROSE_END = re.compile(r"\n|`|\$\{|\Z")


def _is_prose_string(body: str, start: int, end: int) -> bool:
    """True when the python triple-quoted string body[start:end] is prose and not a value code can use."""
    text = body[start:end]
    if " " in text or "\n" in text:
        return True
    line_start = body.rfind("\n", 0, start) + 1
    line_end = body.find("\n", end)
    line_end = len(body) if line_end < 0 else line_end
    return not body[line_start:start].strip() and not body[end:line_end].strip()


def _template_end(body: str, start: int) -> int:
    """The index of the backtick that closes the template literal opened at body[start], or len(body)."""
    j, n = start + 1, len(body)
    while j < n and body[j] != "`":
        if body.startswith("${", j):
            j = _expression_end(body, j + 2)
        else:
            j += 2 if body[j] == "\\" else 1
    return j


def _expression_end(body: str, start: int) -> int:
    """The index just past the `}` that closes the `${` expression whose text starts at `start`, or len(body).
    A brace nests, a quote opens a string up to its mate on the line, and a backtick opens a nested template."""
    j, n, depth = start, len(body), 1
    while j < n:
        char = body[j]
        if char == "`":
            j = _template_end(body, j) + 1
            continue
        if char in "'\"":
            j += 1
            while j < n and body[j] not in (char, "\n"):
                j += 2 if body[j] == "\\" else 1
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if not depth:
                return j + 1
        j += 1
    return n


def _blank_code_prose(body: str, python: bool) -> str:
    """Cut the comments, and the prose triple-quoted strings, out of a python or node body.

    The word reader below reads a body as shell words. A comment or a docstring that names an env file
    in prose then reads as a bare word, and an odd apostrophe in it flips the quote state for the code
    after it. This reads the body with the language's own rules: a quote opens a string up to its
    mate (a newline ends a single-line one), and a comment is found only outside a string.
    A python triple-quoted string is cut only when it is prose: it stands alone on its line, as a
    docstring does, or it holds a space or a newline. One with neither, such as `p = '''.env'''`, may
    be a path that code goes on to open, so it stays as written. Every other string stays as
    written, so a read of an env file there is still judged. A node template literal is left whole
    except for a line that starts with `//`, which the prose case needs and which the reader can
    only read as shell words. In node a `//` or `/*` right after a backslash is the end of an
    escaped slash in a regex literal, not a comment, so it opens nothing.
    """
    out, i, n = [], 0, len(body)
    while i < n:
        char = body[i]
        pair = body[i:i + 2]
        if python and char == "#":
            end = body.find("\n", i)
            i = n if end < 0 else end
        elif not python and pair == "//" and body[i - 1:i] != "\\":
            end = body.find("\n", i)
            i = n if end < 0 else end
        elif not python and pair == "/*" and body[i - 1:i] != "\\":
            end = body.find("*/", i + 2)
            end = n if end < 0 else end + 2
            out.append("\n" * body.count("\n", i, end))
            i = end
        elif python and body[i:i + 3] in ("'''", '"""'):
            end = body.find(body[i:i + 3], i + 3)
            end = n if end < 0 else end + 3
            if _is_prose_string(body, i, end):
                out.append("\n" * body.count("\n", i, end))
                out.append('""')
            else:
                out.append(body[i:end])
            i = end
        elif char in "'\"" or (char == "`" and not python):
            j = i + 1
            while j < n and body[j] != char and (char == "`" or body[j] != "\n"):
                if char == "`" and body.startswith("//", j) and not body[body.rfind("\n", i, j) + 1:j].strip():
                    k = _TEMPLATE_PROSE_END.search(body, j).start()
                    out.append(body[i:j])
                    i, j = k, k
                    continue
                if char == "`" and body.startswith("${", j):
                    j = _expression_end(body, j + 2)
                    continue
                j += 2 if body[j] == "\\" else 1
            out.append(body[i:j + 1])
            i = j + 1
        else:
            out.append(char)
            i += 1
    return "".join(out)


def _blank_interpreter_prose(cmd: str) -> str:
    """`_blank_code_prose` over each QUOTED-delimiter python or node heredoc body. An unquoted body is
    expanded by the shell first, so a `$(...)` in what looks like a comment still runs: it stays whole."""
    if "<<" not in cmd:
        return cmd

    def blank(body, header, quoted):
        python = bool(_PYTHON_HEADER(header))
        if not quoted or not (python or _NODE_HEADER(header)):
            return body
        return _blank_code_prose(body, python)
    return _rewrite_interpreter_bodies(cmd, blank)


def _script_bodies_as_text(cmd: str) -> str:
    """Write the body of each QUOTED python, node, perl or ruby heredoc as the script it is: bash expands
    nothing in it, so a `$(...)` or a backtick in one of its strings is data, and the body stands with those
    spans written as `x`. Its shell spots (`script_spots`) follow as lines of their own, where a substitution
    runs. Every other word of the body is still read as a shell word."""
    if "<<" not in cmd:
        return cmd
    for quote, body, header in _split_heredocs(cmd)[1]:
        header = _without_message_values(header)
        lang = script_language(header)
        if quote and body and lang and not SHELL_HEREDOC(header):
            cmd = cmd.replace(body, "\n".join([_elide_substitutions(body)] + script_spots(body, lang)), 1)
    return cmd


def env_refusal(cmd: str, subs_only: bool = False, heredoc: bool = False):
    """Return (printed reason, logged text) when the command touches an environment file.

    Both are the empty string when the command is clean.

    THE PRINTED REASON NAMES NO FILE. CLAUDE.md: "A refusal's printed remedy never names the
    forbidden target." The whole printed reason is covered, not the last sentence of it, so the
    reason says that an environment file was named and nothing more. The file name, the flag and
    the command word go to the log, where a person can read them and a session cannot.

    The command arrives with its own separators intact. Normalizing them is what made a search for
    the environment accessor read as a path.

    Every substitution is cut out and judged as a command of its own, at any depth. `text_ok` is
    set for one that sits in a commit or pull request message: an `echo` or `printf` there only
    prints text, so its arguments are data. `subs_only` judges the substitutions and not the text
    around them, for the body of a heredoc.
    """
    cmd = _script_bodies_as_text(_blank_interpreter_prose(_plain_escaped_quotes(cmd)))
    texts, too_deep = _substitutions(cmd, powershell=is_powershell(cmd), heredoc=heredoc)
    if too_deep:
        return ENV_DEPTH_REASON, "substitutions nested past %d levels" % ENV_MAX_DEPTH
    if subs_only:
        texts = texts[:-1]
        if not texts:
            return "", ""  # a body with no substitution is text: nothing to judge, and no crash
    for index, (text, in_message) in enumerate(texts):
        # The command itself is last. Its `echo` or `printf` prints to stdout or a file, and an env
        # name among the arguments is text. A substitution's output is an ARGUMENT of the command
        # around it, so only a message value may treat it as text.
        refusal = _env_flat(text, in_message or index == len(texts) - 1)
        if refusal[0]:
            return refusal
    return _env_relay(texts)


def env_heredoc_refusal(raw: str):
    """`env_refusal` for the substitutions in the body of each UNQUOTED heredoc.

    `strip_heredoc_bodies` drops a body before the layers run, and that is right for text. An
    unquoted body still runs its `$(...)`, backticks and `<(...)`, so those are judged. A quoted
    delimiter (`<<'EOF'`) makes the body text, and it stays dropped.
    """
    for quote, body, _ in _split_heredocs(raw)[1]:
        if not quote:
            refusal = env_refusal(body, subs_only=True, heredoc=True)
            if refusal[0]:
                return refusal
    return "", ""


def _env_parts(piece: str):
    """`_ampersand_split` of one segment, with an fd duplication (`2>&1`, `>&2`) taken out first.
    Its `&` is no background operator, and left in, it cut the text command from the pipe after it.
    `&>` and `>&file` are a plain redirect."""
    piece = re.sub(r"\d*>&(\d+|-)", " ", piece)
    piece = re.sub(r"&>>?|>&(?![\d-])", lambda m: m.group(0).replace("&", ""), piece)
    return _ampersand_split(piece)


def _pattern_words(words, position: int, command: str):
    """Read the flags of a search or script command. Return (the indexes of the words that are a
    PATTERN or a program, never a path, {index: the file name glued to a flag word}).

    The words after the command go flag by flag. A short cluster is read letter by letter, so `-nf`
    and `-ex` are seen. `-e` and the long pattern flags take the pattern (the word itself when it
    is attached, else the next word). `-f` and `--file` take a FILE: attached, it goes in the
    second result to be judged as a path, and otherwise the next word is left to be judged. Either
    kind of flag settles where the pattern comes from, so every plain word after it is a file.
    Else the first plain word is the pattern. A value flag (`-A 3`, `--include x`) skips its value,
    which stays judged as a path, so an error here only ever judges a word and never hides one.
    """
    skip, glued, plain, given, ended = set(), {}, [], False, False
    hidden, type_not = False, False
    program = command in ENV_PROGRAM_COMMANDS
    value_short = (ENV_PROGRAM_VALUE_SHORT[command] if program
                   else ENV_VALUE_SHORT + ENV_VALUE_SHORT_BY_COMMAND.get(command, "")
                   + (ENV_SCRIPT_VALUE_SHORT if command in ENV_SCRIPT_COMMANDS else ""))
    i = position + 1
    while i < len(words):
        word = words[i]
        if REDIRECT.fullmatch(word):
            i += 2
            continue
        if ended or not word.startswith("-") or word == "-":
            plain.append(i)
            i += 1
            continue
        if word == "--":
            ended = True
            i += 1
            continue
        if word.startswith("--"):
            name, attached, _ = word.partition("=")
            hidden = hidden or name in ENV_HIDDEN_LONG
            if name in ENV_PATTERN_LONG:
                given = True
                skip.update({i} if attached else {i + 1})
            elif name in ENV_FILE_LONG:
                given = True
            elif name in ENV_EXCLUDE_LONG or (command == "ag" and name == ENV_AG_REGEX_LONG):
                skip.update({i} if attached else {i + 1})
            i += 1 if attached or name not in ENV_PATTERN_LONG + ENV_FILE_LONG + ENV_VALUE_LONG else 2
            continue
        step = 1
        for k, letter in enumerate(word[1:], 1):
            rest = word[k + 1:]
            hidden = hidden or letter in ENV_HIDDEN_SHORT
            if letter == "e" and not program:
                given = True
                skip.update({i} if rest else {i + 1})
                step = 1 if rest else 2
                break
            if letter == "f" and command in ENV_BOOLEAN_F_COMMANDS:
                continue  # a switch: the cluster goes on, and no pattern file is named
            if letter == "f":
                given = True
                if rest:
                    glued[i] = rest
                step = 1 if rest else 2
                break
            if letter in value_short:
                if not rest and letter in ENV_NO_PATH_SHORT_BY_COMMAND.get(command, ""):
                    skip.add(i + 1)  # a file type name or an ag file regex, never a path
                type_not = type_not or (command == "rg" and letter in ENV_RG_TYPE_NOT_SHORT)
                step = 1 if rest else 2
                break
        i += step
    if program and not given and plain:
        # A yq subcommand leads the program, and is no path either. The program is skipped only
        # when a file word follows it: a lone word reads stdin or is the file, so it is judged.
        lead = 1 if command == "yq" and words[plain[0]] in ENV_YQ_SUBCOMMANDS else 0
        if len(plain) > lead + 1:
            skip.update(plain[:lead + 1])
    elif not given and plain and not (hidden and type_not):
        skip.add(plain[0])
    return skip, glued


def _ag_hidden_regex_refusal(words, position: int) -> str:
    """Return a description of what an `ag` file regex picks while a hidden flag is set, else ''.

    The regex is tried on sample env file names. One that will not compile as Python is refused:
    the guard cannot tell what it matches. Only `-G` and `--file-search-regex` take a file regex;
    `-p` names a file of ignore patterns.
    """
    hidden, regexes, i = False, [], position + 1
    while i < len(words):
        word = words[i]
        i += 1
        if word == "--":
            break
        if word.startswith("--"):
            name, attached, value = word.partition("=")
            hidden = hidden or name in ENV_HIDDEN_LONG
            if name == ENV_AG_REGEX_LONG:
                if attached:
                    regexes.append(value)
                elif i < len(words):
                    regexes.append(words[i])
                    i += 1
            continue
        if not word.startswith("-") or word == "-":
            continue
        for k, letter in enumerate(word[1:], 1):
            if letter == "u":
                hidden = True
            elif letter == "G":
                rest = word[k + 1:]
                if rest:
                    regexes.append(rest)
                elif i < len(words):
                    regexes.append(words[i])
                    i += 1
                break
            elif letter in ENV_VALUE_SHORT + "p":
                i += 0 if word[k + 1:] else 1
                break
    if not hidden:
        return ""
    for regex in regexes:
        tokens = segment_tokens(regex)   # the value ag gets, after the shell's quote removal
        regex = "".join(tokens) if tokens else regex.strip("\"'")
        try:
            with warnings.catch_warnings():
                # A POSIX class such as `[[:alpha:]]` warns of a nested set on stderr. The verdict stands.
                warnings.simplefilter("ignore", FutureWarning)
                compiled = re.compile(regex)
        except re.error:
            return "a file regex the guard cannot compile"
        for name in ENV_SAMPLE_NAMES:
            if names_env_file(name) and (compiled.search(name) or compiled.search("./" + name)):
                return "the file regex matches the name '%s'" % name
    return ""


def _assignment_end(words, position: int) -> int:
    """Return the index after the `VAR=value` assignment that starts at `position`. A quoted value
    with a space (`ADMINS='Shivam Semwal'`) spans several words, and its tail must not read as the
    command word: read as one, an author's surname gave 29 false `env-file` refusals."""
    quote = next((c for c in "'\"" if words[position].partition("=")[2].count(c) % 2), "")
    end = position
    while quote and end + 1 < len(words):
        end += 1
        if quote in words[end]:
            break
    return end + 1


# Words that run the next word as a command and are no command themselves.
ENV_COMMAND_PREFIXES = ("exec", "command", "builtin", "nohup")
# Wrappers that take options and run the rest as a command, with the option words that own the next word.
ENV_WRAPPER_VALUE_FLAGS = {
    "nice": ("-n", "--adjustment"),
    "sudo": ("-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U", "--user", "--group", "--host"),
    "stdbuf": ("-i", "-o", "-e"),
    "env": ("-u", "--unset", "-C", "--chdir", "-S"),
}
TIMEOUT_FLAG_GLUED = re.compile(r"^(--(kill-after|signal)=\S+|-[ks]\S+)$")
PY_LAUNCHER_FLAG = re.compile(r"^-(\d(\.\d+)?(-\d+)?|u)$")  # `py -3`, `py -3.12`, `python -u`


def _wrapper_name(word: str) -> str:
    """A wrapper's name without its Windows extension: `verdict.cmd` is `verdict`."""
    return re.sub(r"\.(cmd|exe|bat|py)$", "", word)


def _quoted_words(segment: str, keep_newlines=False):
    """Split a segment into words the way the shell does: a quoted string with a space is ONE word.
    A newline inside a quote reads as a space, or stays a newline with `keep_newlines`, for a caller that
    reads the quoted text as a script (a `bash -c` string with two lines runs two commands). The redirects
    are spaced into words of their own outside the quotes only. A quote with no
    closing mate is a plain character, so a lone quote in text still leaves the words after it."""
    chunks, plain, i, n = [], [], 0, len(segment)

    def flush():
        text = "".join(plain)
        chunks.append(READ_REDIRECT.sub(" < ", REDIRECT.sub(r" \1 ", text)))
        plain.clear()

    while i < n:
        char = segment[i]
        if char == "\\" and i + 1 < n:
            plain.append(segment[i:i + 2])
            i += 2
            continue
        if char in "'\"":
            j = i + 1
            while j < n and segment[j] != char:
                j += 2 if char == '"' and segment[j] == "\\" else 1
            if j < n:
                flush()
                chunks.append(re.sub(r"\s", lambda m: "\1" if keep_newlines and m.group() == "\n" else "\0",
                                     segment[i:j + 1]))
                i = j + 1
                continue
        plain.append(char)
        i += 1
    flush()
    return [w.replace("\0", " ").replace("\1", "\n") for w in "".join(chunks).split()]


def _is_redirect(word: str) -> bool:
    """True when a word is a redirect operator (`>`, `2>>`, `<`, `<<`, `<<EOF`)."""
    return bool(REDIRECT.fullmatch(word)) or word.lstrip("0123456789").startswith("<")


def _operands(words):
    """The words of a command's arguments, with each redirect and its target taken out."""
    out, i = [], 0
    while i < len(words):
        if _is_redirect(words[i]):
            i += 2 if REDIRECT.fullmatch(words[i]) or words[i].lstrip("0123456789") in ("<", "<<", "<<-", "<<<") else 1
            continue
        out.append(words[i])
        i += 1
    return out


def _skip_wrappers(words, position: int, runner_child: bool = False) -> int:
    """Return the index of the command that the wrappers at `position` run. Looks through exactly
    these wrapper shapes, each by its exact form, so a flag value of some other wrapper
    (`env -u ls cat .env`) can never pose as the command word. `runner_child` adds the wrappers
    that a runner's child or a shell-string segment may lead with (`nice`, `sudo`, `stdbuf`,
    `env VAR=x`, and `exec`, `command`, `builtin`, `nohup`); the parent shell form leaves them."""
    while position < len(words):
        word = words[position].rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        after = position + 1
        if word == "timeout":
            while after < len(words) and (words[after] in TIMEOUT_FLAGS_WITH_VALUE
                                          or words[after] in TIMEOUT_FLAGS_BARE
                                          or TIMEOUT_FLAG_GLUED.match(words[after])):
                after += 2 if words[after] in TIMEOUT_FLAGS_WITH_VALUE else 1
            if not (after < len(words) and DURATION.match(words[after])):
                break
            position = after + 1
        elif word == "do" or _wrapper_name(word) == "verdict":
            position = after
        elif word == "time":
            position = after + (after < len(words) and words[after] == "-p")
        elif _wrapper_name(word) in ("python", "python3", "py"):
            while after < len(words) and PY_LAUNCHER_FLAG.match(words[after]):
                after += 1
            if not (after < len(words) and _wrapper_name(
                    words[after].rsplit("/", 1)[-1].rsplit("\\", 1)[-1]) == "verdict"):
                break
            position = after + 1
        elif runner_child and word in ENV_COMMAND_PREFIXES:
            position = after
        elif runner_child and word in ENV_WRAPPER_VALUE_FLAGS:
            while after < len(words) and (words[after] in ENV_WRAPPER_VALUE_FLAGS[word]
                                          or words[after].startswith("-")
                                          or (word != "stdbuf" and ASSIGNMENT.match(words[after]))):
                after += 2 if words[after] in ENV_WRAPPER_VALUE_FLAGS[word] else 1
            if word == "env" and (after >= len(words) or _is_redirect(words[after])):
                break  # `env VAR=x` alone, or `env > f`, prints the environment, so env is the command
            position = after
        else:
            break
    return position


def _env_words(segment: str):
    """Return (words, command word) of one segment, redirects spaced into words of their own."""
    words = _quoted_words(_blank_messages(segment), keep_newlines=True)
    # The command is the first word that is not a `VAR=value` assignment.
    # A `(` glued to the first assignment is a subshell paren, not part of the name.
    if words and words[0][:1] == "(" and ASSIGNMENT.match(words[0][1:]):
        words[0] = words[0][1:]
    position = 0
    while position < len(words) and ASSIGNMENT.match(words[position]):
        position = _assignment_end(words, position)
    position = _skip_wrappers(words, position)
    head = words[position] if position < len(words) else ""
    command = head.strip("'\"").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if command in ENV_TEXT_COMMANDS:
        # `printf '<name>\n'` prints the name and a newline: the escape ends the word.
        words = re.sub(r"\\[ntr]", " ", " ".join(words)).split()
    return words, position, command


# Commands that take a file name and read none of its contents to run it: they ask, list or record.
ENV_RELAY_SAFE = ENV_EXISTENCE_COMMANDS + ENV_TEXT_COMMANDS + ("git",)


def _env_relay(texts):
    """Return (reason, log) when a text command writes an env name into a file that another
    segment of the SAME command reads. `echo <name> > f; cat $(cat f)` prints the name to a file
    and then reads the file the name points at. A relay split across two separate tool calls
    cannot be seen by a per-command guard, and that is an accepted limit.
    """
    segments = [[_env_words(seg) for piece in split_segments(text) for seg in _env_parts(piece)]
                for text, _ in texts]

    def gives_a_name(words, command):
        return command in ENV_TEXT_COMMANDS and any(
            env_reference(w) for i, w in enumerate(words)
            if i and not REDIRECT.fullmatch(words[i - 1]))

    def targets(words):
        return {w for i, w in enumerate(words) if i and REDIRECT.fullmatch(words[i - 1])}

    def reads(words, command, files):
        return command not in ENV_RELAY_SAFE and any(
            w in files and not (i and REDIRECT.fullmatch(words[i - 1]))
            for i, w in enumerate(words))

    # The command itself is the last text, and its segments run in order: a read before the write
    # is the check-then-write setup, and is no relay. A substitution runs at a place this scan
    # does not track, so a read inside one counts against every write.
    written = set()
    for text in segments:
        for words, _, command in text:
            if gives_a_name(words, command):
                written |= targets(words)
    for text in segments[:-1]:
        if any(reads(words, command, written) for words, _, command in text):
            return ENV_CONTENTS_REASON, "a substitution reads a file that was given an environment name"
    written = set()
    for words, _, command in segments[-1]:
        if reads(words, command, written):
            return (ENV_CONTENTS_REASON,
                    "'%s' would read a file that was just given an environment name" % command)
        if gives_a_name(words, command):
            written |= targets(words)
    return "", ""


def _runner_scan(words, position: int, stdin_fed: bool, is_flag, eval_word: bool = False):
    """Read the option words after a runner, up to the first positional word or `--`. Returns
    (index of the first flag that `is_flag` accepts, a `-` stdin word, or deno's `eval`; else -1,
    whether stdin feeds a script: fed with no script word). A script's own `-e` is no hit."""
    fed = stdin_fed
    script = False
    i = position + 1
    while i < len(words):
        word = words[i]
        if REDIRECT.fullmatch(word):
            i += 2
        elif word.lstrip("0123456789").startswith("<"):
            # A heredoc, here-string or `<` file feeds stdin. A spaced operator (`<<`, `<<-`, `<<<`,
            # `<`) owns the next word, which is the delimiter, the string or the file.
            fed = True
            i += 2 if word.lstrip("0123456789") in ("<", "<<", "<<-", "<<<") else 1
        elif word.isdigit() and words[i + 1:i + 2] and words[i + 1].startswith("<"):
            i += 1  # the fd of `0< file`
        elif word == "--":
            script = i + 1 < len(words)
            break
        elif word in ENV_RUNNER_VALUE_FLAGS:
            i += 2
        elif is_flag(word) or word == "-":
            return i, True
        elif word.startswith("-"):
            i += 1
        else:
            if eval_word and word == "eval":
                return i, True
            script = True
            break
    return -1, fed and not script


def _runner_inline_code(words, position: int, command: str, stdin_fed: bool = False) -> bool:
    """True when a node, bun or deno command runs inline code: an eval or print flag, a stdin
    script (`-`, or no script word with stdin fed by a pipe or a heredoc), or deno's `eval`.
    The option words after the runner are read up to the first positional word or `--`, so the
    `-e` of a script's own arguments (`node app.js -e x`) is not inline code."""
    if command.lower() not in ENV_INLINE_RUNNERS:
        return False
    hit, stdin = _runner_scan(words, position, stdin_fed, ENV_INLINE_FLAG.match,
                              command.lower().startswith("deno"))
    return hit >= 0 or stdin


def _base(word: str) -> str:
    """The program name of a word: no quote marks, no directory, lower case."""
    return re.split(r"[\\/]", word.replace('"', "").replace("'", ""))[-1].lower()


def _first_positional(words, i: int, flags) -> int:
    """The index of the first word from `i` that is no option. An option that takes a value owns
    the next word."""
    while i < len(words):
        if words[i] in flags:
            i += 2
        elif words[i].startswith("-"):
            i += 1
        else:
            break
    return min(i, len(words))


def _shell_word(word: str) -> str:
    r"""The text the shell hands a program for one word (`sh -c <word>`, `ruby -e <word>`). Pieces
    quoted apart join: `'it'"'"'s'` and `'it'\''s'` are both `it's`. In single quotes every
    character is text. In double quotes the shell drops the backslash of `\$`, `` \` ``, `\"` and
    `\\`, and a backslash and newline. Out of quotes a backslash escapes the next character. A quote
    with no mate is a plain character, as `_quoted_words` reads it. An unescaped `$( )` stays: the
    parent's `_substitutions` judges it. Not shlex: it keeps the backslash of `\$` in double quotes
    and raises on a quote with no mate."""
    out, i, n = [], 0, len(word)
    while i < n:
        char = word[i]
        close = word.find("'", i + 1) if char == "'" else -1
        if close > 0:
            out.append(word[i + 1:close])
            i = close + 1
        elif char == '"':
            j, piece = i + 1, []
            while j < n and word[j] != '"':
                if word[j] == "\\" and j + 1 < n and word[j + 1] in '$`"\\\n':
                    piece.append("" if word[j + 1] == "\n" else word[j + 1])
                    j += 2
                else:
                    piece.append(word[j])
                    j += 1
            if j >= n:  # no mate: a plain character
                out.append(char)
                i += 1
            else:
                out.append("".join(piece))
                i = j + 1
        elif char == "\\" and i + 1 < n:
            out.append(word[i + 1])
            i += 2
        else:
            out.append(char)
            i += 1
    return "".join(out)


def _shell_string_prints(text: str, depth: int = 0) -> bool:
    """A shell string (`sh -c "<s>"`, `npm exec -c "<s>"`) is judged segment by segment, the way the
    parent shell form reads a command. `text` is the string the child shell gets: a caller that holds
    the shell word passes its `_shell_word`. A perl or ruby shell string is that text already.
    `_env_flat` is its one reader of a file name, and `_substitutions` cuts out each `$(...)`,
    backtick pair and `<(...)`, so each body is judged as a command of its own (`_segments_print`). A segment prints the environment when its command is a
    printing child (`_child_prints`), `set` or `export` with no variable to name, or `echo` or
    `printf` over a `$` variable that is no substitution. A `$` in any other segment is an ordinary
    argument (`cd $APP_DIR && npm start`). A string nested past ENV_MAX_DEPTH counts as printing."""
    if depth > ENV_MAX_DEPTH:
        return True
    if _env_flat(text, True)[0]:
        return True
    for piece in split_segments(text):
        for segment in _env_parts(piece):
            texts, too_deep = _substitutions(segment)
            if too_deep:
                return True
            for number, (body, in_message) in enumerate(texts):
                # Each text has its own substitutions cut to `x`, so a `$` in it is a variable. The
                # child shell runs each body, so a file name in one is read as `cat .env` reads it.
                # The segment itself is last: its text is data to an `echo`. A body is an argument of
                # the command around it, as in `env_refusal`.
                if _env_flat(body, in_message or number == len(texts) - 1)[0]:
                    return True
                if _segments_print(body, depth):
                    return True
    return False


def _lists_variables(name: str, args) -> bool:
    """True when the shell builtin `name` over `args` (redirects taken out) lists the shell's
    variables: `set`, `export`, `declare` and `typeset` with no name to set, `export -p`,
    `declare -p` and `declare -x`. With `-f` or `-F`, `declare` prints functions only. `compgen`
    prints names, not values."""
    clusters = "".join(a[1:] for a in args if a.startswith("-") and not a.startswith("--"))
    names = [a for a in args if not a.startswith("-")]
    if name == "set":
        return not args
    if name == "export":
        return not args or "p" in clusters
    if name in ("declare", "typeset"):
        if "f" in clusters or "F" in clusters:
            return False
        return "p" in clusters or (not names and (not args or "x" in clusters))
    return False


def _segments_print(text: str, depth: int) -> bool:
    """`_shell_string_prints` for one text whose substitutions are already cut out, so a `$` in it
    is a variable: after `echo` or `printf` it is a printed variable."""
    for piece in split_segments(text):
        for segment in _env_parts(piece):
            words, position, _ = _env_words(segment)
            while words and words[-1] in (")", "}"):
                words.pop()  # the closer of a spaced group is no argument: `( env )`, `{ env; }`
            while position < len(words):  # a group or a clause word runs the command after it
                head = words[position].lstrip("({")
                if head and head not in ENV_GROUP_WORDS:
                    words[position] = head.rstrip(")};")  # glued `(env)`
                    break
                position += 1
            if position >= len(words):
                continue
            at = _skip_wrappers(words, position, True)
            if at < len(words):
                name = _base(words[at])
                if "$" in segment and name in ENV_TEXT_COMMANDS:
                    return True
                if _lists_variables(name, _operands(words[at + 1:])):
                    return True
            if _child_prints(words, position, False, depth + 1):
                return True
    return False


def _script_code(words, program: str):
    """The code words of a perl, ruby or awk command (`words` past the program name), as the shell
    hands them on (`_shell_word`). perl and ruby: the value of each option word with a code letter
    (`-e`, `-ne`, `-lane`), glued (`-e'code'`) or the next word. awk: each `-e` or `--source` value,
    else the first word that is no option, unless `-f` names a program file. A here-string
    (`ruby <<< 'p ENV'`) is code too. A word that may be code is read as code: reading too much
    costs a false alarm, too little a hole."""
    perl = program.startswith("perl")
    awk = not perl and not program.startswith("ruby")
    letters = ENV_SCRIPT_CODE_LETTERS["perl" if perl else "ruby"]
    stops = ENV_SCRIPT_VALUE_LETTERS["perl" if perl else "ruby"]
    code = [words[k + 1] for k in range(len(words) - 1) if words[k] == "<<<"]
    words = _operands(words)
    i, n, options, has_program = 0, len(words), True, False
    while i < n:
        word = words[i]
        if awk and options and word.startswith("-") and word != "-":
            flag, _, glued = word.partition("=") if word.startswith("--") else (word[:2], "", word[2:])
            options = word != "--"
            if flag in ENV_AWK_VALUE_FLAGS:
                if flag in ("-e", "--source"):
                    code.append(glued if glued else (words[i + 1] if i + 1 < n else ""))
                has_program = has_program or flag in ENV_AWK_PROGRAM_FLAGS
                i += 1 if glued else 2
            else:
                i += 1
        elif awk:  # the first word that is no option is the program, unless a flag gave it
            if not has_program:
                code.append(word)
            options, has_program = False, True
            i += 1
        elif word.startswith("-") and not word.startswith("--"):
            for at, letter in enumerate(word[1:], 1):
                if letter in stops:
                    break
                if letter in letters:
                    if word[at + 1:]:
                        code.append(word[at + 1:])
                    elif i + 1 < n:
                        code.append(words[i + 1])
                        i += 1
                    break
            i += 1
        else:
            i += 1
    return [_shell_word(w) for w in code]


def _script_prints(code: str, program: str, depth: int) -> bool:
    """True when the code of a perl, ruby or awk command (`_script_code`) names the environment, or
    holds a shell string that prints it (`system("env")`, backticks, `qx(env)`). A ruby bare `ENV`
    in a string literal is text, and one in a `#{...}` is code."""
    if ENV_SCRIPT_ENV_WORD.search(code):
        return True
    if program.startswith("ruby") and ENV_RUBY_ENV_WORD.search(ENV_RUBY_STRING.sub(
            lambda m: " %s " % " ".join(ENV_RUBY_INTERPOLATION.findall(m.group()))
            if m.group()[0] == '"' else " ", code)):
        return True
    for match in ENV_SCRIPT_SHELL_STRING.finditer(code.replace("\\`", "`")):
        body = match.group(2) if match.group(2) is not None else next(g for g in match.groups()[2:] if g is not None)
        if _shell_string_prints(body, depth + 1):
            return True
    return False


def _child_prints(words, at: int, fed: bool = False, depth: int = 0) -> bool:
    """True when the child command at words[at], past its wrappers (`_skip_wrappers`), prints its
    environment: env or printenv; a shell string that does (`sh -c`); python `-c`; python or a shell
    with no script word and stdin fed; or node, bun or deno inline code."""
    at = _skip_wrappers(words, at, True)
    if at >= len(words):
        return False
    name = _base(words[at])
    if name in ENV_PRINT_PROGRAMS:
        return True
    shell = re.fullmatch(r"(ba|z|da)?sh", name)
    # `cat /proc/self/environ`. A shell's string is judged below, command by command.
    if not shell and name not in ENV_EXISTENCE_COMMANDS + ENV_TEXT_COMMANDS and any(
            ENV_PROC_ENVIRON.search(w) for w in words[at + 1:]):
        return True
    if ENV_SCRIPT_PROGRAM.fullmatch(name):  # perl `%ENV`, ruby `ENV`, awk `ENVIRON`
        return any(_script_prints(c, name, depth) for c in _script_code(words[at + 1:], name))
    if shell or re.fullmatch(r"python[\d.]*(\.exe)?", name):
        hit, stdin = _runner_scan(words, at, fed, ENV_SHELL_C_FLAG.match)
        if hit < 0 or not shell or words[hit] == "-":
            return hit >= 0 or stdin
        return hit + 1 >= len(words) or _shell_string_prints(_shell_word(words[hit + 1]), depth)
    return _runner_inline_code(words, at, name, fed)


def _is_bool_flag(word: str, runner: str) -> bool:
    """True when `word` is a flag of the runner that takes no value: one in its bool list, a
    `--no-*` flag, or a cluster of short bools such as `-it`."""
    bools = ENV_CHILD_BOOL_FLAGS[runner]
    if word in bools:
        return True
    if word.startswith("--"):
        return word.startswith("--no-")
    return len(word) > 1 and all("-" + c in bools for c in word[1:])


def _owns_literal(words, i: int, runner: str) -> bool:
    """True when words[i] is a bool flag of npm or pnpm and the next word is exactly `true` or
    `false`, or `always` after `--color`: nopt reads that word as the flag's own value, so it is not
    the child."""
    return (runner in ("npm", "pnpm") and i + 1 < len(words)
            and (words[i + 1] in ("true", "false") or (words[i] == "--color" and words[i + 1] == "always"))
            and _is_bool_flag(words[i], runner))


def _may_own_value(word: str, runner: str) -> bool:
    """True when an option word that is not in the runner's value-flag list may still own the next
    word: it has no `=`, is not `--` and is not a known bool flag."""
    return (word.startswith("-") and word != "--" and "=" not in word
            and not _is_bool_flag(word, runner))


def _child_starts(words, i: int, runner: str):
    """The indexes from `i` where a child command may start, past the runner's options. An option
    in the runner's value list owns the next word, and one in its bool list owns none, except that
    an npm or pnpm bool owns a next word that is exactly `true` or `false` (`--color` also `always`). Each
    positional word is a start. When it sits right after an option in neither list it may be that
    option's value, so the scan goes on past every option to the next positional word, which is a
    start too: `--foo X --bar always alpine env` starts at `X`, `always` and `alpine`. A positional
    word that follows no such option ends the scan, so a program's own arguments
    (`docker run --rm myimage serve env`, `uv run -q pytest -k env`) are never starts. FEWEST FALSE
    ALARMS: a start that is no child costs nothing, since `_child_prints` reads only env, printenv,
    shells, python and inline runners. One false alarm stays: an option in neither list before a
    program, then `env` or `printenv` as the program's first word or after its own option
    (`uv run --foo pytest env` has starts `pytest` and `env`).
    `--` ends the runner's options, so the word after it is the one start."""
    flags = ENV_CHILD_VALUE_FLAGS[runner]
    while i < len(words):
        word = words[i]
        if word == "--":
            if i + 1 < len(words):
                yield i + 1
            return
        if word in flags:
            i += 2
        elif word.startswith("-"):
            i += 2 if _owns_literal(words, i, runner) else 1
        else:
            yield i
            if not (i and _may_own_value(words[i - 1], runner)):
                return
            i += 1


def _compose_prints(words, at: int) -> bool:
    """True when words[at] is a compose `config` or `convert` that prints resolved values: none of
    its listing flags (`--services`, `-q`) follows it."""
    return words[at] in ENV_COMPOSE_PRINTERS and not any(
        w.split("=", 1)[0] in ENV_COMPOSE_LISTING_FLAGS for w in words[at + 1:])


def _container_child_prints(words, at: int, fed: bool) -> bool:
    """words[at] is `run` or `exec`. The child is the `--entrypoint` program with the words after
    the image, or just the words after the image or container word. Each start that `_child_starts`
    finds is tried as the image."""
    starts = list(_child_starts(words, at + 1, "docker"))
    entry = ""
    for i in range(at + 1, starts[-1] if starts else len(words)):
        if words[i] == "--entrypoint" and i + 1 < len(words):
            entry = words[i + 1]
        elif words[i].startswith("--entrypoint="):
            entry = words[i][13:]
    entry = entry.strip("'\"")  # `--entrypoint ""` is the image's own command
    return any(_child_prints(([entry] if entry else []) + words[c + 1:], 0, fed) for c in starts)


def _runner_child_prints(words, position: int, command: str, fed: bool = False) -> bool:
    """True when a runner given the file starts a child command that prints it: `uv run`,
    `docker`/`podman` `run`, `compose run` and `exec` (the child follows the image word), and
    `npm exec -c`, `npx -c` and `pnpm exec`. The npm walk reads `-c` up to `--` or the child; the
    child of `exec`, `x`, `dlx` and `npx` is found by `_child_starts`."""
    name = _base(command)
    flags = ENV_CHILD_VALUE_FLAGS["node"]
    if name in ENV_INLINE_RUNNERS:  # `node --env-file=F npm-cli.js exec -c env`
        at = _first_positional(words, position + 1, flags)
        if at >= len(words):
            return False
        if name.startswith("bun") and words[at].strip("'\"") == "x":  # bun's `x` is the npx form, `./x` is not
            return any(_child_prints(words, c, fed) for c in _child_starts(words, at + 1, "bun"))
        if _base(words[at]) not in ENV_NPM_RUNNERS:
            return False
        position, name = at, _base(words[at])
    if name in ENV_NPM_RUNNERS:
        pnpm = name.startswith("pnpm")
        runner = "pnpm" if pnpm else "npm"  # pnpm's -r and -w are bools, npm's -w takes a value
        flags = ENV_CHILD_VALUE_FLAGS[runner]
        exec_at = position if name.startswith("npx") else -1  # npx's child is its first word
        i = position + 1

        def child_prints() -> bool:
            return exec_at >= 0 and any(
                _child_prints(words, c, fed) for c in _child_starts(words, exec_at + 1, runner))

        while i < len(words):
            word = words[i]
            if word == "--" and exec_at >= 0:  # the rest is the child's
                break
            if word in ("-c", "--call"):  # past `pnpm exec`, `-c` may be the child's own flag
                return child_prints() or (
                    i + 1 < len(words) and _shell_string_prints(_shell_word(words[i + 1])))
            if word.startswith("--call="):
                return child_prints() or _shell_string_prints(_shell_word(word[7:]))
            if word in flags:
                i += 2
            elif word.startswith("-"):
                i += 2 if _owns_literal(words, i, runner) else 1
            elif not name.startswith("npx") and (word in ("exec", "x") or (pnpm and word == "dlx")):
                exec_at = i  # `x` may be an option value, so it never ends the walk
                i += 1
            elif _may_own_value(words[i - 1], runner):  # may be an unlisted option's value
                i += 1
            else:
                break
        return child_prints()
    if name.startswith("uv"):
        return any(
            words[at] == "run" and any(_child_prints(words, c, fed)
                                       for c in _child_starts(words, at + 1, "uv"))
            for at in _child_starts(words, position + 1, "uv"))
    if name.startswith(("docker", "podman")):
        for at in _child_starts(words, position + 1, "docker"):
            if words[at] in ("compose", "container"):  # `container run` is `run`
                return any(_compose_prints(words, c) or (
                    words[c] in ("run", "exec") and _container_child_prints(words, c, fed))
                    for c in _child_starts(words, at + 1, "docker"))
            if name.startswith("docker-compose") and _compose_prints(words, at):
                return True
            if words[at] in ("run", "exec"):
                return _container_child_prints(words, at, fed)
    return False


# A redirect of stdout. `2>` sends errors only; `&>` reaches here as `>` (`_env_parts`). guard_core
# `REDIRECT` is not used here: it matches `2>` too, and a find name test with `2>/dev/null` lists to the screen.
ENV_STDOUT_REDIRECTS = (">", ">>", "1>", "1>>")


def _find_output_on_screen(words, piped: bool, pieces, ends, at: int) -> bool:
    """True when a find segment's output reaches only the screen: no stdout redirect to a file,
    and, when `piped`, each stage of the pipe that the piece `at` opens is a filter
    (`ENV_FIND_FILTERS`) with no such redirect."""
    if any(w in ENV_STDOUT_REDIRECTS for w in words):
        return False
    while piped and ends[at] == "|":
        at += 1
        # A piece follows each `|` (`split_segments`), and `_env_parts` returns at least one part.
        parts = _env_parts(pieces[at])
        stage, _, command = _env_words(parts[0])
        if command not in ENV_FIND_FILTERS or any(w in ENV_STDOUT_REDIRECTS for w in stage):
            return False
        if len(parts) > 1:
            return True  # the filter is sent to the background, and its output goes to the screen
    return True


def _env_flat(cmd: str, text_ok: bool = False):
    """The segment rules over one text whose substitutions are already cut out."""
    ends = []
    pieces = split_segments(cmd, ends)
    for at, (piece, end) in enumerate(zip(pieces, ends)):
        previous_end = ends[at - 1] if at else ""
        parts = _env_parts(piece)
        for number, segment in enumerate(parts):
            words, position, command = _env_words(segment)
            if not words:
                continue
            # The first segment of a piece reads the pipe that the piece before it closed with.
            stdin_piped = number == 0 and previous_end == "|"
            # A segment that pipes onward hands its output to another command, which may read it
            # as a path. Only its stdout to the terminal or to a file keeps the text allowance.
            piped = end == "|" and number == len(parts) - 1
            # `git check-ignore <path>` asks git whether a path is ignored. It reads no contents.
            rest_words = [w for w in words[position + 1:] if not w.startswith("-")]
            # Only positional paths. `--stdin`, `-z` and a `<` redirect feed it contents to print.
            names_only = (
                command == "git" and rest_words[:1] == ["check-ignore"] and "<" not in segment
                and not any(w == "--stdin" or re.fullmatch(r"-[A-Za-z]*z[A-Za-z]*", w)
                            for w in words))
            # A text command's arguments are data. A redirect onto an environment file is refused
            # below, first.
            text_to_file = command in ENV_TEXT_COMMANDS and text_ok and not piped
            if command == "ag":
                hit = _ag_hidden_regex_refusal(words, position)
                if hit:
                    return (ENV_CONTENTS_REASON,
                            "'ag' with a hidden flag would read an environment file: %s" % hit)
            patterns, glued = (_pattern_words(words, position, command)
                               if command in (ENV_PATTERN_COMMANDS + ENV_SCRIPT_COMMANDS
                                              + ENV_PROGRAM_COMMANDS)
                               else (set(), {}))
            # An awk `-v name=value` value that holds a glob is a regex, as a pattern is. A plain
            # env name there stays judged: awk can open it. ACCEPTED LIMIT: a glob value that
            # could name an env file is cleared.
            if command in ENV_SCRIPT_COMMANDS[1:]:
                patterns = set(patterns) | {
                    i for i, w in enumerate(words)
                    if i and words[i - 1] == "-v" and ENV_GLOB.search(w)}
            for index, word in enumerate(words):
                if index in patterns:
                    continue
                prefix, assigned, rest = word.partition("=")
                flag = prefix if assigned and prefix.startswith("-") else ""
                named = env_reference(glued[index] if index in glued else rest if assigned else word)
                if not named:
                    continue
                previous = words[index - 1] if index else ""
                loaded = flag in ENV_LOADER_FLAGS or previous in ENV_LOADER_FLAGS
                # A redirect onto the file overwrites it, whatever the command turns out to be.
                if REDIRECT.fullmatch(previous):
                    return (ENV_REDIRECT_REASON,
                            "a redirect onto '%s' would overwrite the file" % named)
                # A shell variable holding the path. The assignment reads nothing, but the guard
                # cannot follow the variable to its use, so `E=.env; cat $E` would be a one-line
                # way past this whole layer.
                if assigned and not flag:
                    return (ENV_VARIABLE_REASON,
                            "a shell variable holds '%s'" % named)
                if loaded and command.lower() in ENV_LOADER_COMMANDS:
                    if _runner_inline_code(words, position, command, stdin_piped):
                        return (ENV_INLINE_REASON,
                                "'%s' runs inline code with '%s' loaded" % (command, named))
                    if _runner_child_prints(words, position, command, stdin_piped):
                        return (ENV_CHILD_REASON,
                                "'%s' runs a child command that prints its environment with "
                                "'%s' loaded" % (command, named))
                    continue  # a runner loading it into its own environment prints nothing
                if loaded:
                    return (ENV_RUNNER_REASON,
                            "only a runner may be handed '%s' with %s, and '%s' is not one" % (
                                named, flag or previous, command))
                if names_only or text_to_file:
                    continue  # the name is data, and no contents are read or written
                if command in ENV_EXISTENCE_COMMANDS:
                    continue  # asking whether the file is there reads none of it
                # `text_ok` is false for a substitution that is not a message value: its output is an
                # argument of the command around it. Every pipe stage must be a filter, not a runner.
                if (command == "find" and previous in ENV_FIND_NAME_TESTS and text_ok
                        and not any(w in ENV_FIND_ACTIONS for w in words)
                        and _find_output_on_screen(words, piped, pieces, ends, at)):
                    continue  # a name test lists the name, as ls does
                if command in ENV_FOLDER_COMMANDS:
                    continue  # a folder is made, and none of it is read
                actor = "'%s'" % command if command else "this command"
                return (ENV_CONTENTS_REASON,
                        "%s would read, write or commit the contents of '%s'" % (actor, named))
    return "", ""


def is_env(path: str) -> bool:
    name = norm(path).rsplit("/", 1)[-1]
    return names_env_file(name)

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
