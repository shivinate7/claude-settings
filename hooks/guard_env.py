"""The guard's env family: any read or write of an environment file.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import fnmatch
import glob
import itertools
import os
import re
import warnings

from guard_core import (
    ASSIGNMENT, DURATION, ENV_PATTERN_COMMANDS, FIND_EXEC_ACTIONS, INTERPRETER_HEREDOC, POWERSHELL_CALL,
    REDIRECT, SHELL_HEREDOC, TIMEOUT_FLAGS_BARE, TIMEOUT_FLAGS_WITH_VALUE, _git, _segment_cd_move,
    _split_heredocs, _without_message_values, _wrapper_flags, dir_before_segment, is_powershell, norm,
    resolve_command, segment_tokens, split_segments,
)

# The wrappers `_env_words` looks through for a folder search, beyond its own list: each runs the program
# after its flags, and `xargs` also hands that program the paths it reads from stdin.
ENV_RUNNER_WRAPPERS = ("sudo", "doas", "nohup", "exec", "xargs")


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
# The long flags that take a value in one tool only. `ag --depth 3` and `ag --ignore PAT` own the next word, as
# grep's `--devices ACTION` and `--directories ACTION` do. The word is no pattern and no path.
ENV_VALUE_LONG_BY_COMMAND = {
    "ag": ("--depth", "--ignore", "--ignore-dir", "--workers", "--width", "--pager", "--path-to-ignore",
           "--color-line-number", "--color-match", "--color-path"),
    "grep": ("--devices", "--directories", "--binary-files", "--label", "--group-separator"),
}
# rg reads its flags by its own table, kept whole so a flag outside it can be told from one inside:
# the flags that take a value (a word after them is no pattern and no path), and the plain switches.
# A `--no-...` flag is always a switch. A flag in neither table might take a value, so the search is
# read as if it might have swallowed a path word (`_env_walk`, "fails closed").
ENV_RG_VALUE_LONG = (
    "--after-context", "--before-context", "--color", "--colors", "--context", "--context-separator",
    "--dfa-size-limit", "--encoding", "--engine", "--field-context-separator",
    "--field-match-separator", "--generate", "--glob", "--hostname-bin", "--hyperlink-format",
    "--iglob", "--ignore-file", "--max-columns", "--max-count", "--max-depth", "--maxdepth",
    "--max-filesize", "--path-separator", "--pre", "--pre-glob", "--regex-size-limit", "--replace",
    "--sort", "--sortr", "--threads", "--type", "--type-add", "--type-clear", "--type-not",
)
ENV_RG_SWITCH_LONG = (
    "--auto-hybrid-regex", "--binary", "--block-buffered", "--byte-offset", "--case-sensitive",
    "--column", "--count", "--count-matches", "--crlf", "--debug", "--files", "--files-with-matches",
    "--files-without-match", "--fixed-strings", "--follow", "--glob-case-insensitive", "--heading",
    "--help", "--hidden", "--ignore-case", "--ignore-file-case-insensitive", "--include-zero",
    "--invert-match", "--json", "--line-buffered", "--line-number", "--line-regexp",
    "--max-columns-preview", "--mmap", "--multiline", "--multiline-dotall", "--null", "--null-data",
    "--one-file-system", "--only-matching", "--passthru", "--pcre2", "--pcre2-version", "--pretty",
    "--quiet", "--search-zip", "--smart-case", "--sort-files", "--stats", "--stop-on-nonmatch",
    "--text", "--trace", "--trim", "--type-list", "--unicode", "--unrestricted", "--version",
    "--vimgrep", "--with-filename", "--word-regexp",
)
ENV_RG_SWITCH_SHORT = ".0FHILNPSUVabchilnopqsuvwxz"
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
ENV_VALUE_SHORT_BY_COMMAND = {"rg": "tTjrEM", "ag": "GpW", "grep": "D"}
# The value of these letters is no path, so it is skipped: after rg `-t` or `-T` a file type name,
# after ag `-G` a file regex, judged by `_ag_hidden_regex_refusal` instead.
ENV_NO_PATH_SHORT_BY_COMMAND = {"rg": "tT", "ag": "G"}
# A hidden flag makes a search read dotfiles: `--hidden`, rg `-.`, and `-u` (`--unrestricted`) as often
# as the tool needs. ag reads dotfiles at one `-u`. rg `-u` turns off the ignore rules and no more;
# `-uu` and `-uuu` (or `-u` twice) also read dotfiles. Any `-u` turns the ignore rules off.
ENV_HIDDEN_LONG = ("--hidden",)
ENV_UNRESTRICTED_LONG = "--unrestricted"
ENV_UNRESTRICTED_FOR_HIDDEN = {"rg": 2, "ag": 1}
# Flags that turn the ignore rules (.gitignore and the like) off, apart from `-u`. rg: `--no-ignore`
# and each `--no-ignore-...` (kept whole, so a partial one counts too). ag: `-U`, `-a` and their long forms.
ENV_NO_IGNORE_LONG_PREFIX = "--no-ignore"
ENV_AG_NO_IGNORE_LONG = ("--skip-vcs-ignores", "--all-types")
ENV_AG_NO_IGNORE_SHORT = "Ua"
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


# The deepest nest of substitutions the guard reads. A command nested deeper is REFUSED: a nest that
# no honest command needs is a way to make the reader give up, and giving up must not allow it.
ENV_MAX_DEPTH = 64
ENV_DEPTH_REASON = "substitutions are nested too deep for the guard to read"


def _substitutions(cmd: str, depth: int = 0, powershell: bool = False, heredoc: bool = False,
                   places=None):
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

    `places`, when a list, is filled with one (parent, offset) per text, in step with the texts:
    the index of the text that holds this one, and where its placeholder starts in that text (-1
    and 0 for the command itself). A parent comes after its children, so the walk can read the
    folder of each text from its parent's (`_env_walk`).
    """
    escape = "`" if powershell else "\\"
    if depth > ENV_MAX_DEPTH:
        return [], True
    done = []
    # a frame: [pieces of its text, open quote, paren depth, it is a message value, its open
    # quote holds a message value, (pieces counted, their length), (child index, offset) of each
    # child, where its placeholder starts in its parent]
    stack = [[[], "", 0, False, False, [0, 0], [], 0]]
    i, n = 0, len(cmd)

    def length(frame):
        """The length of the text a frame holds so far, counting each piece once."""
        seen = frame[5]
        for piece in frame[0][seen[0]:]:
            seen[1] += len(piece)
        seen[0] = len(frame[0])
        return seen[1]

    def close():
        frame = stack.pop()
        done.append(("".join(frame[0]), frame[3]))
        if places is not None:
            for child, offset in frame[6]:
                places[child] = (len(done) - 1, offset)
            places.append((-1, 0))
            if stack:
                stack[-1][6].append((len(done) - 1, frame[7]))

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
            inner_places = [] if places is not None else None
            inner, deep = _substitutions(cmd[i + 1:j].replace("\\`", "`"), depth + 1,
                                         places=inner_places)
            if deep:
                return [], True
            if places is not None:
                places.extend((parent + len(done) if parent >= 0 else -1, offset)
                              for parent, offset in inner_places)
                frame[6].append((len(done) + len(inner) - 1, length(frame)))
            done.extend(inner)
            pieces.append("`x`")
            i = j + 1
            continue
        elif cmd[i:i + 2] == "$(" or (quote == "" and cmd[i:i + 2] in ("<(", ">(")):
            if len(stack) + depth > ENV_MAX_DEPTH:
                return [], True
            message = quote == '"' and frame[4]
            offset = length(frame)
            pieces.append("x")
            stack.append([[], "", 0, message, False, [0, 0], [], offset])
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
        pieces.append(char)
        i += 1
    while stack:
        close()
    # the outermost text closed last, so it is last
    return done, False


def substitution_commands(raw: str, stripped: str, outer: bool = False):
    """The texts a shell runs INSIDE the command, each a command of its own: every `$(...)`, backtick
    and process substitution in `stripped`, plus those in an unquoted heredoc body of `raw`. A quoted
    shell heredoc body runs nothing and is gone from `stripped`; an interpreter heredoc body stays in
    `stripped` and is read as shell text, so a `$( )` in it can be a false alarm. With `outer`, the command itself is last, its substitutions read as `x`
    (`stripped` as it stands when the nest is too deep). A nest too deep to read gives no inner text:
    the env-file rule refuses it. The one home of this cut: judge_shell and git_env_command_hit call it.
    """
    found, too_deep = _substitutions(stripped, powershell=POWERSHELL_CALL[0])
    inner = [text for text, _in_message in found[:-1]]
    for quote, body, _ in _split_heredocs(raw)[1]:
        if not quote:
            body_found, body_deep = _substitutions(body, heredoc=True)
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


def _glob_could_name_env(word: str, fold: bool = False, by_path: bool = False) -> bool:
    """True when the glob `word` could match the name of an env file. The glob is tried on the
    sample names (`ENV_SAMPLE_NAMES`, and `.env.x`), and each of its parts is filled in as the shortest
    and a one letter match. `fold` reads the glob without case. The glob is read as grep and rg read it
    (`_glob_unescaped`): `\\.` is a dot and `[^a]` a negated class. With `by_path` the glob is a search
    flag's, so a `/` in it is a folder in front of the name, which can be any folder: only the last
    part is judged, and a glob that ends in `/` picks every file under a folder."""
    if by_path:
        word = word.rpartition("/")[2]
        if not word:
            return True
    if fold:
        word = word.lower()
    word = _glob_unescaped(word)
    if any(fnmatch.fnmatchcase(name, word) for name in ENV_SAMPLE_NAMES + (ENV_PREFIX + ".x",)):
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


def _plain_escaped_quotes(cmd: str) -> str:
    """Write a backslash-escaped quote in the body of a python, node, perl or ruby heredoc as a plain
    character. Those languages read the backslash as an escape, but the word reader below does not:
    a `\\'` would flip its quote state, and the prose after it would read as bare shell words."""
    if "<<" not in cmd or "\\" not in cmd:
        return cmd
    for _, body, header in _split_heredocs(cmd)[1]:
        header = _without_message_values(header)
        if body and INTERPRETER_HEREDOC(header) and not SHELL_HEREDOC(header):
            cmd = cmd.replace(body, _ESCAPED_QUOTE.sub(lambda m: m.group(0) if m.group(0) == "\\\\" else "_", body), 1)
    return cmd


def env_refusal(cmd: str, subs_only: bool = False, heredoc: bool = False, cwd: str = ""):
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
    around them, for the body of a heredoc. `cwd` is the folder the command runs in, for the search
    that walks a folder (`_env_walk`); with none, that check is skipped.
    """
    cmd = _plain_escaped_quotes(cmd)
    places = []
    texts, too_deep = _substitutions(cmd, powershell=is_powershell(cmd), heredoc=heredoc, places=places)
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
    refusal = _env_walk(texts, cwd, places=places) if cwd else ("", "")
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


def _flag_word(word: str) -> str:
    """A word that is one whole quoted string and starts with `-` is a flag to the shell, whatever its
    quotes: `'--exclude=GLOB'` is `--exclude=GLOB`. Any other word is returned as it stands."""
    if len(word) > 2 and word[0] in "'\"" and word[-1] == word[0] and word[1] == "-":
        return word[1:-1]
    return word


def _pattern_words(words, position: int, command: str):
    """Read the flags of a search or script command. Return (the indexes of the words that are a
    PATTERN or a program, never a path, {index: the file name glued to a flag word}, whether a
    hidden flag is set, the indexes of the positional words, whether a flag turns the ignore rules off,
    and a dict of what `_env_walk` also needs). In that dict, "pattern" is the index of the plain
    word read as the pattern, skipped or not. For rg, "unknown" counts the flags in neither rg
    table, each of which might have taken a word; "globs" holds the `-g` and `--iglob` values as
    (glob, ignores case); "types" holds the `-t` type names; "types_open" is set when `--type-add` or
    `--type-clear` changes the stock types, so a type narrows nothing; "lists_files" is set when rg
    gets the `--files` flag itself, never a word that is the value of `-e` or another flag.

    The words after the command go flag by flag. A short cluster is read letter by letter, so `-nf`
    and `-ex` are seen. `-e` and the long pattern flags take the pattern (the word itself when it
    is attached, else the next word). `-f` and `--file` take a FILE: attached, it goes in the
    second result to be judged as a path, and otherwise the next word is left to be judged. Either
    kind of flag settles where the pattern comes from, so every plain word after it is a file.
    Else the first plain word is the pattern. A value flag (`-A 3`, `--include x`) skips its value,
    which stays judged as a path, so an error here only ever judges a word and never hides one.
    """
    skip, glued, plain, given, ended = set(), {}, [], False, False
    hidden, type_not, unrestricted, no_ignore = False, False, 0, False
    extras = {"pattern": None, "unknown": 0, "globs": [], "types": [], "types_open": False,
              "lists_files": False}
    rg = command == "rg"
    fold = rg and "--glob-case-insensitive" in words
    program = command in ENV_PROGRAM_COMMANDS
    value_short = (ENV_PROGRAM_VALUE_SHORT[command] if program
                   else ENV_VALUE_SHORT + ENV_VALUE_SHORT_BY_COMMAND.get(command, "")
                   + (ENV_SCRIPT_VALUE_SHORT if command in ENV_SCRIPT_COMMANDS else ""))
    i = position + 1
    while i < len(words):
        word = _flag_word(words[i])
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
            name, attached, glued_value = word.partition("=")
            hidden = hidden or name in ENV_HIDDEN_LONG
            unrestricted += name == ENV_UNRESTRICTED_LONG
            extras["lists_files"] = extras["lists_files"] or (rg and name == "--files")
            no_ignore = no_ignore or name.startswith(ENV_NO_IGNORE_LONG_PREFIX) or (
                command == "ag" and name in ENV_AG_NO_IGNORE_LONG)
            if name in ENV_PATTERN_LONG:
                given = True
                skip.update({i} if attached else {i + 1})
            elif name in ENV_FILE_LONG:
                given = True
            elif name in ENV_EXCLUDE_LONG or (command == "ag" and name == ENV_AG_REGEX_LONG):
                skip.update({i} if attached else {i + 1})
            takes = rg and name in ENV_RG_VALUE_LONG
            if rg:
                if takes:
                    value = glued_value if attached else (words[i + 1] if i + 1 < len(words) else "")
                    _rg_value(extras, name, value, fold)
                elif not (name in ENV_RG_SWITCH_LONG or name.startswith("--no-") or "=" in word
                          or name in ENV_PATTERN_LONG + ENV_FILE_LONG + ENV_EXCLUDE_LONG):
                    extras["unknown"] += 1
            i += 1 if attached or not (takes or name in ENV_PATTERN_LONG + ENV_FILE_LONG + ENV_VALUE_LONG
                                       + ENV_VALUE_LONG_BY_COMMAND.get(command, ())) else 2
            continue
        step = 1
        for k, letter in enumerate(word[1:], 1):
            rest = word[k + 1:]
            hidden = hidden or letter == "."
            unrestricted += letter == "u"
            no_ignore = no_ignore or (command == "ag" and letter in ENV_AG_NO_IGNORE_SHORT)
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
                if rg:
                    _rg_value(extras, "-" + letter, rest or (words[i + 1] if i + 1 < len(words) else ""),
                              fold)
                if not rest and letter in ENV_NO_PATH_SHORT_BY_COMMAND.get(command, ""):
                    skip.add(i + 1)  # a file type name or an ag file regex, never a path
                type_not = type_not or (command == "rg" and letter in ENV_RG_TYPE_NOT_SHORT)
                step = 1 if rest else 2
                break
            if rg and letter not in ENV_RG_SWITCH_SHORT:
                extras["unknown"] += 1
        i += step
    hidden = hidden or unrestricted >= ENV_UNRESTRICTED_FOR_HIDDEN.get(command, 2)
    if program and not given and plain:
        # A yq subcommand leads the program, and is no path either. The program is skipped only
        # when a file word follows it: a lone word reads stdin or is the file, so it is judged.
        lead = 1 if command == "yq" and words[plain[0]] in ENV_YQ_SUBCOMMANDS else 0
        if len(plain) > lead + 1:
            skip.update(plain[:lead + 1])
    elif not given and plain:
        extras["pattern"] = plain[0]
        if not (hidden and type_not):
            skip.add(plain[0])
    return skip, glued, hidden, plain, no_ignore or unrestricted > 0, extras


def _rg_value(extras, flag: str, value: str, fold: bool):
    """Record what an rg flag's value says about the files read: a `-g` or `--iglob` glob (a glob
    that starts with `!` is a negative one and narrows nothing, and a brace list is expanded), a
    `-t` type, or a changed type table."""
    value = _shell_value(value)
    if flag in ("-g", "--glob", "--iglob") and value and not value.startswith("!"):
        # rg expands a brace list in a glob itself, whatever the shell did with the word.
        extras["globs"] += [(g, fold or flag == "--iglob") for g in _brace_list(value)]
    elif flag in ("-t", "--type"):
        extras["types"].append(value)
    elif flag in ("--type-add", "--type-clear"):
        extras["types_open"] = True


def _git_grep_at(words, position: int, command: str) -> int:
    """The index of the `grep` word in `git grep ...`, else 0. `git grep` is read as `grep` is:
    its first plain word is a pattern, so an env name inside it is text. Only the plain form counts
    (`git grep`, with no flag before the subcommand), as `git check-ignore` does."""
    rest = [i for i in range(position + 1, len(words)) if not words[i].startswith("-")]
    return rest[0] if command == "git" and rest and words[rest[0]] == "grep" else 0


def _shell_value(word: str) -> str:
    """The value a command gets from one shell word, after the shell's quote removal. Bash reads
    it by `segment_tokens`. PowerShell does not: a single quote holds every character as it stands
    (`'\\.env'` keeps its backslash) and a backtick escapes the next character, so the bash reader
    would double each backslash and change what a regex means."""
    if not is_powershell(word):
        tokens = segment_tokens(word)
        return "".join(tokens) if tokens else word.strip("\"'")
    out, quote, i = [], "", 0
    while i < len(word):
        char = word[i]
        if quote:
            if char == quote and word[i + 1:i + 2] == quote:
                out.append(quote)   # a doubled quote is one literal quote
                i += 2
                continue
            if char == quote:
                quote = ""
            elif char == "`" and quote == '"' and i + 1 < len(word):
                out.append(word[i + 1])
                i += 1
            else:
                out.append(char)
        elif char in "'\"":
            quote = char
        elif char == "`" and i + 1 < len(word):
            out.append(word[i + 1])
            i += 1
        else:
            out.append(char)
        i += 1
    return "".join(out)


# A POSIX class inside a bracket expression, as PCRE (the regex ag runs) reads it. Python's `re`
# reads `[[:alpha:]]` as a set of the characters `[`, `:`, `a`, `l`, `p`, `h`, then a literal `]`,
# so the guard writes each class out as the ranges it stands for. A negated class is written as the
# ASCII characters outside the class, then every character past ASCII. An unknown class is not
# translated, and the regex is refused: the guard cannot tell what it matches.
POSIX_CLASS = re.compile(r"\[:(\^?)([a-z]+):\]")
POSIX_CLASS_RANGES = {
    "alpha": "a-zA-Z", "digit": "0-9", "alnum": "a-zA-Z0-9", "upper": "A-Z", "lower": "a-z",
    "xdigit": "0-9A-Fa-f", "space": r"\s", "blank": r" \t", "word": r"\w",
    "punct": r"!-/:-@\[-`{-~", "cntrl": r"\x00-\x1f\x7f", "print": r"\x20-\x7e",
    "graph": r"\x21-\x7e", "ascii": r"\x00-\x7f",
}


def _posix_classes_to_python(regex: str) -> str:
    def ranges(match):
        if match.group(2) not in POSIX_CLASS_RANGES:
            raise ValueError("a POSIX class the guard does not translate")
        body = POSIX_CLASS_RANGES[match.group(2)]
        if not match.group(1):
            return body
        member = re.compile("[%s]" % body)
        return "".join("\\x%02x" % code for code in range(128) if not member.match(chr(code))) + \
            "\\x80-\\U0010ffff"
    return POSIX_CLASS.sub(ranges, regex)


# The names a file regex could pick, built from the regex itself, so a suffix outside
# ENV_SAMPLE_NAMES (`\.env\.prod$`) is still seen. Every literal is kept, a repeat runs its least
# count and one more, and a class or a dot offers the letters of `.env` it holds, then one other
# letter. A built string counts only when the regex really matches it (the caller searches), so a
# name is never claimed that the regex would not pick. A regex with too many shapes is read again
# in the lean form: each repeat runs its least count only and each class or dot offers one letter. ACCEPTED LIMIT: a regex that names no env
# prefix of its own (`prod$`) is judged on ENV_SAMPLE_NAMES only. Rewriting `\.py$` as the names it
# could pick would refuse every extension filter.
try:
    from re import _parser as _sre_parse
except ImportError:   # Python before 3.11
    import sre_parse as _sre_parse
SAMPLE_PICK_FROM = ".env"
SAMPLE_PICK_OTHER = "abcdefghijklmnopqrstuvwxyz0123456789_-/ABCDEFGHIJKLMNOPQRSTUVWXYZ"
SAMPLE_LIMIT = 2048
SAMPLE_REPEATS = ("MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT")
SAMPLE_CATEGORIES = {
    "CATEGORY_DIGIT": str.isdigit, "CATEGORY_NOT_DIGIT": lambda c: not c.isdigit(),
    "CATEGORY_SPACE": str.isspace, "CATEGORY_NOT_SPACE": lambda c: not c.isspace(),
    "CATEGORY_WORD": lambda c: c.isalnum() or c == "_",
    "CATEGORY_NOT_WORD": lambda c: not (c.isalnum() or c == "_"),
}


def _sample_pick(test, lean=False):
    """The letters a class or a dot offers: those of `.env` it holds, then the first other one.
    The lean form offers the first of them only."""
    picks = [c for c in SAMPLE_PICK_FROM if test(c)]
    other = next((c for c in SAMPLE_PICK_OTHER if test(c)), "")
    picks += [other] if other and other not in picks else []
    return picks[:1] if lean else picks


def _sample_class(items):
    tests, negate = [], False
    for op, value in items:
        name = str(op)
        if name == "NEGATE":
            negate = True
        elif name == "LITERAL":
            tests.append(lambda c, v=value: ord(c) == v)
        elif name == "RANGE":
            tests.append(lambda c, lo=value[0], hi=value[1]: lo <= ord(c) <= hi)
        elif name == "CATEGORY":
            tests.append(SAMPLE_CATEGORIES.get(str(value), lambda c: False))
    return lambda c: any(test(c) for test in tests) != negate


def _sample_seq(items, lean=False):
    out = [""]
    for op, value in items:
        options = _sample_node(str(op), value, lean)
        out = list(dict.fromkeys(a + b for a in out for b in options))
        if len(out) > SAMPLE_LIMIT:
            raise OverflowError("a file regex with too many shapes")
    return out


def _sample_node(name, value, lean=False):
    if name == "LITERAL":
        return [chr(value)]
    if name == "NOT_LITERAL":
        return _sample_pick(lambda c: ord(c) != value, lean)
    if name == "ANY":
        return _sample_pick(lambda c: True, lean)
    if name == "IN":
        return _sample_pick(_sample_class(value), lean)
    if name == "CATEGORY":
        return _sample_pick(SAMPLE_CATEGORIES.get(str(value), lambda c: False), lean)
    if name == "BRANCH":
        return list(dict.fromkeys(s for branch in value[1] for s in _sample_seq(branch, lean)))
    if name == "SUBPATTERN":
        return _sample_seq(value[-1], lean)
    if name == "ATOMIC_GROUP":
        return _sample_seq(value, lean)
    if name in SAMPLE_REPEATS:
        low, high, body = value
        if low > 64:
            raise OverflowError("a file regex with a long repeat")
        counts = {low} | ({low + 1} if high > low and not lean else set())
        # A repeat that runs zero times adds the empty string, even when its body offers no letter.
        shapes = _sample_seq(body, lean) if counts - {0} else []
        return list(dict.fromkeys(s * k for k in sorted(counts) for s in (shapes if k else [""])))
    if name == "GROUPREF_EXISTS":
        return _sample_seq(value[1], lean) + _sample_seq(value[2] or [], lean)
    return [""]   # an anchor, a look-around or a back reference adds no characters


def _regex_names(regex: str, lean=False):
    return _sample_seq(_sre_parse.parse(regex), lean)


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
            hidden = hidden or name in ENV_HIDDEN_LONG or name == ENV_UNRESTRICTED_LONG
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
        try:
            regex = _posix_classes_to_python(_shell_value(regex))
            with warnings.catch_warnings():
                # A bracket set such as `[[a]` warns on stderr (nested set). The verdict stands.
                warnings.simplefilter("ignore", FutureWarning)
                compiled = re.compile(regex)
            try:
                names = _regex_names(regex)
            except OverflowError:
                names = _regex_names(regex, lean=True)
            names = list(ENV_SAMPLE_NAMES) + names
        except (re.error, ValueError, RecursionError, OverflowError):
            return "a file regex the guard cannot read"
        for name in names:
            # A built name may lack the leading dot that the regex itself leaves to the file name
            # (`env\.prod$` picks `.env.prod`), so the dotted form is tried as well.
            base = name.rsplit("/", 1)[-1]
            for held in (name, name[:len(name) - len(base)] + "." + base):
                if names_env_file(held.rsplit("/", 1)[-1]) and (
                        compiled.search(held) or compiled.search("./" + held)):
                    return "the file regex matches the name '%s'" % held
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
    "setsid": (),
    "env": ("-u", "--unset", "-C", "--chdir", "-S"),
}
# `env -C DIR` and `env --chdir=DIR` run the program in DIR, and the value may be glued to the flag.
ENV_CHDIR_GLUED = re.compile(r"-C\S+|--chdir=\S*")
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


def _skip_wrappers(words, position: int, runner_child: bool = False, walk: bool = False) -> int:
    """Return the index of the command that the wrappers at `position` run. Looks through exactly
    these wrapper shapes, each by its exact form, so a flag value of some other wrapper
    (`env -u ls cat .env`) can never pose as the command word. `runner_child` adds the wrappers
    that a runner's child or a shell-string segment may lead with (`nice`, `sudo`, `stdbuf`,
    `env VAR=x`, and `exec`, `command`, `builtin`, `nohup`); the parent shell form leaves them.
    `walk` adds the wrappers a folder search hides behind: `command [-p]`,
    `env [-i] [-u NAME] [-C DIR] [--] [VAR=value]...`, `stdbuf` and `setsid` with their flags, and
    `nice [-n N | -nN | -N | --adjustment N | --adjustment=N] [--]`."""
    while position < len(words):
        if walk and (REDIRECT.fullmatch(words[position]) or words[position] == "<"):
            position += 2   # a redirect in front of the program: the operator and its target
            continue
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
        elif walk and word == "command":
            position = after + (after < len(words) and words[after] == "-p")
        elif walk and word == "nice":
            if after < len(words) and words[after] in ("-n", "--adjustment"):
                after += 2
            elif after < len(words) and re.fullmatch(r"-n-?\d+|-\d+|--adjustment=\S+", words[after]):
                after += 1
            position = after + (after < len(words) and words[after] == "--")
        elif walk and word == "env":
            while after < len(words):
                if ASSIGNMENT.match(words[after]):
                    after = _assignment_end(words, after)
                elif words[after] in ("-i", "-0", "--ignore-environment"):
                    after += 1
                elif words[after] in ("-u", "--unset", "-C", "--chdir"):
                    after += 2
                elif ENV_CHDIR_GLUED.fullmatch(words[after]):
                    after += 1
                elif words[after] == "--":
                    # After `--` env takes no flag: only assignments, then the command.
                    after += 1
                    while after < len(words) and ASSIGNMENT.match(words[after]):
                        after = _assignment_end(words, after)
                    break
                else:
                    break
            position = after
        elif walk and word in ENV_RUNNER_WRAPPERS:
            # The program behind `sudo`, `nohup`, `exec` and `xargs` is read by guard_core's wrapper walk,
            # which knows each one's value flags (`sudo -u root`, `xargs -n 1`).
            kept, at = [], position
            while at < len(words):
                if REDIRECT.fullmatch(words[at]) or words[at] == "<":
                    at += 2   # a redirect and its target are no part of the program
                    continue
                kept.append(at)
                at += 1
            behind = resolve_command(tuple(words[i] for i in kept))
            if not behind:
                break
            position = kept[behind]
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
        elif (runner_child or walk) and word in ENV_WRAPPER_VALUE_FLAGS:
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


def _env_chdirs(words, position: int):
    """The folders that each `env -C DIR` or `env --chdir=DIR` before the command word at `position` moves
    to, in order, as typed. The command runs in the last one, each relative to the one before."""
    found = []
    for at, word in enumerate(words[:position]):
        if _base(word) != "env":
            continue
        i = at + 1
        while i < position:
            flag = words[i]
            if flag in ("-C", "--chdir") and i + 1 < position:
                found.append(_shell_value(words[i + 1]))
                i += 2
            elif ENV_CHDIR_GLUED.fullmatch(flag):
                found.append(_shell_value(flag[2:] if flag[:2] == "-C" else flag.partition("=")[2]))
                i += 1
            elif flag in ("-u", "--unset"):
                i += 2
            elif flag.startswith("-") or ASSIGNMENT.match(flag):
                i += 1
            else:
                break   # the next wrapper: its flags are not env's
    return found


def _env_words(segment: str, walk: bool = False):
    """Return (words, index of the command word, command word) of one segment, redirects spaced
    into words of their own. `walk` also looks through the wrappers a folder search hides behind:
    a subshell paren, a `{` brace group, and the `_skip_wrappers` walk wrappers. The other
    callers read each of those as the command itself."""
    words = _quoted_words(_blank_messages(segment), keep_newlines=True)
    if walk and words:
        # A lone `{` opens a brace group. A `{` glued to a word is part of the command name to bash.
        while words and (words[0] == "{" or words[0].startswith("(")):
            words[0] = "" if words[0] == "{" else words[0].lstrip("(")
            if not words[0]:
                words.pop(0)
        # A `)` after a backslash is find's escaped paren, a word of the command, and not a subshell's close.
        if (words and words[-1].endswith(")") and not words[-1].endswith("\\)")
                and not words[-1].startswith(("'", '"'))):
            words[-1] = words[-1].rstrip(")")
            if not words[-1]:
                words.pop()
    # The command is the first word that is not a `VAR=value` assignment.
    # A `(` glued to the first assignment is a subshell paren, not part of the name.
    if words and words[0][:1] == "(" and ASSIGNMENT.match(words[0][1:]):
        words[0] = words[0][1:]
    position = 0
    while position < len(words) and ASSIGNMENT.match(words[position]):
        position = _assignment_end(words, position)
    position = _skip_wrappers(words, position, walk=walk)
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


# A search that reads dotfiles and walks a folder reaches each env file in it, whatever its name.
# ENV_WALK_COMMANDS read a folder when no path is named, and need a hidden flag to reach dotfiles.
# ENV_GREP_COMMANDS reach them with a recursive flag, and `rgrep` is always recursive. The walk
# stops at ENV_WALK_LIMIT entries and the search is then refused: a folder that large cannot be
# shown clean. A folder that the ignore rules skip is not walked
# for rg and ag, which skip it too.
ENV_WALK_COMMANDS = ("rg", "ag")
ENV_GREP_COMMANDS = ("grep", "egrep", "fgrep")
ENV_GREP_RECURSIVE_COMMAND = "rgrep"
ENV_GREP_RECURSIVE_LONG = ("--recursive", "--dereference-recursive")
# Letters of a grep flag cluster that take a value, and so end the cluster: `-A 3`, `-e pat`, `-f file`.
ENV_GREP_VALUE_SHORT = ENV_VALUE_SHORT + "ef" + ENV_VALUE_SHORT_BY_COMMAND["grep"]
ENV_WALK_LIMIT = 50000
ENV_TOO_LARGE = "<too large>"
ENV_WALK_REASON = ("this command would search a folder that holds an environment file, and a "
                   "hidden flag makes it read dotfiles")
ENV_WALK_LARGE_REASON = (
    "this command would search a folder too large to check, so it cannot be shown clean of "
    "environment files. Remedy: name a smaller folder, or skip the large one with --exclude-dir=node_modules")
ENV_GREP_WALK_REASON = (
    "this command would search a folder that holds an environment file, and a recursive grep "
    "reads dotfiles. Remedy: add --exclude with a glob that covers the environment file names, "
    "or --exclude-dir for the folder that holds it")


def _ignored_paths(folder: str):
    """The paths under `folder` that the ignore rules skip, as the checkout's own tool prints them:
    relative to `folder`, with `/` as the separator, an ignored folder as one name that ends in `/`.
    A tracked file is never in it. Empty when `folder` is in no checkout or the call failed, so
    nothing is then skipped."""
    answer = _git(folder, "ls-files", "--others", "--ignored", "--exclude-standard", "--directory", "-z")
    if answer is None or answer.returncode != 0:
        return frozenset()
    return frozenset(p for p in answer.stdout.split("\0") if p)


# The file types of rg that a `-t` flag can name here, each with its globs as `rg --type-list` prints
# them (rg 14.1.0), a bare name such as `Gemfile` included. A type outside this table (or a type table
# changed by `--type-add`) may pick any file, so it narrows nothing.
_MD_GLOBS = ("*.markdown", "*.md", "*.mdown", "*.mdwn", "*.mdx", "*.mkd", "*.mkdn")
ENV_RG_TYPE_GLOBS = {
    "py": ("*.py", "*.pyi"), "js": ("*.cjs", "*.js", "*.jsx", "*.mjs", "*.vue"),
    "ts": ("*.cts", "*.mts", "*.ts", "*.tsx"), "rust": ("*.rs",), "go": ("*.go",),
    "md": _MD_GLOBS, "markdown": _MD_GLOBS,
    "json": ("*.json", "*.sarif", "composer.lock"), "yaml": ("*.yaml", "*.yml"),
    "toml": ("*.toml", "Cargo.lock"), "html": ("*.ejs", "*.htm", "*.html"),
    "css": ("*.css", "*.scss"), "java": ("*.java", "*.jsp", "*.jspx", "*.properties"),
    "ruby": ("*.gemspec", "*.rb", "*.rbw", ".irbrc", "Gemfile", "Rakefile", "config.ru"),
    "php": ("*.php", "*.php3", "*.php4", "*.php5", "*.php7", "*.php8", "*.pht", "*.phtml"),
    "sql": ("*.psql", "*.sql"),
    "xml": ("*.dtd", "*.rng", "*.sch", "*.xhtml", "*.xjb", "*.xml", "*.xml.dist", "*.xsd", "*.xsl",
            "*.xslt"),
    "c": ("*.[chH]", "*.[chH].in", "*.cats"),
    "cpp": ("*.[ChH]", "*.[ChH].in", "*.[ch]pp", "*.[ch]pp.in", "*.[ch]xx", "*.[ch]xx.in", "*.cc",
            "*.cc.in", "*.hh", "*.hh.in", "*.inl"),
    "lua": ("*.lua",), "swift": ("*.swift",), "kotlin": ("*.kt", "*.kts"),
}


def _brace_list(word: str):
    """The words that one brace list stands for: `{a,b}x` is `ax` and `bx`, nested lists too. A word
    with no list, or a brace pair with no comma, is returned as it stands."""
    open_at = word.find("{")
    while open_at != -1:
        depth, parts, last = 0, [], open_at + 1
        for j in range(open_at, len(word)):
            if word[j] == "{":
                depth += 1
            elif word[j] == "}":
                depth -= 1
                if depth == 0:
                    if parts:
                        parts.append(word[last:j])
                        return [e for part in parts
                                for e in _brace_list(word[:open_at] + part + word[j + 1:])]
                    break
            elif word[j] == "," and depth == 1:
                parts.append(word[last:j])
                last = j + 1
        open_at = word.find("{", open_at + 1)
    return [word]


def _brace_expand(word: str):
    """The words bash makes of one word with a brace list: `--exclude-dir={a,b}` is `--exclude-dir=a
    --exclude-dir=b`, and `"su"b/{x,y}` is `"su"b/x "su"b/y`. Only an unquoted brace or comma counts, so
    a list inside quotes, after a backslash or inside `${...}` or `$(...)` stays literal. The quotes stay
    in each word for the reader that removes them."""
    if not any(c in word for c in "{,}"):
        return [word]
    hidden = {"{": "", "}": "", ",": ""}
    masked, i, quote = [], 0, ""
    while i < len(word):
        char = word[i]
        if quote:
            if char == "\\" and quote == '"' and i + 1 < len(word):
                masked.append(char + hidden.get(word[i + 1], word[i + 1]))
                i += 1
            else:
                masked.append(hidden.get(char, char))
                quote = "" if char == quote else quote
        elif char in "\"'":
            quote = char
            masked.append(char)
        elif char == "\\" and i + 1 < len(word):
            masked.append(char + hidden.get(word[i + 1], word[i + 1]))
            i += 1
        elif char == "$" and word[i + 1:i + 2] in ("{", "("):
            end = word.find("}" if word[i + 1] == "{" else ")", i + 2)
            end = len(word) - 1 if end == -1 else end
            masked.append("".join(hidden.get(c, c) for c in word[i:end + 1]))
            i = end
        else:
            masked.append(char)
        i += 1
    back = {v: k for k, v in hidden.items()}
    return ["".join(back.get(c, c) for c in e) for e in _brace_list("".join(masked))]


def _zero_folder_forms(glob: str):
    """`glob` and the forms of it where each mid-glob `/**/` stands for a bare `/`, because `**/`
    also matches zero folders: `sub/**/*` names `sub/.env`."""
    forms = [glob]
    for form in forms:
        if "/**/" in form and (shorter := form.replace("/**/", "/", 1)) not in forms:
            forms.append(shorter)
    return forms


# The ASCII members of a POSIX class in a glob bracket, as glibc fnmatch reads it.
GLOB_POSIX_CLASS_MEMBERS = {
    "alpha": "a-zA-Z", "digit": "0-9", "alnum": "a-zA-Z0-9", "upper": "A-Z", "lower": "a-z",
    "xdigit": "0-9A-Fa-f", "space": " \t\n\r\f\v", "blank": " \t", "punct": "!-/:-@[-`{-~",
    "cntrl": "\x00-\x1f\x7f", "print": " -~", "graph": "!-~",
}


def _class_chars(spec: str):
    """The characters that a list of members stands for: each `x-y` is a range, any other char itself."""
    chars = set()
    for low, high, single in re.findall(r"(.)-(.)|(.)", spec, flags=re.DOTALL):
        if single:
            chars.add(single)
        else:
            chars.update(chr(code) for code in range(ord(low), min(ord(high), ord(low) + 4096) + 1))
    return chars


def _bracket_member(glob: str, i: int):
    """(the char of the bracket member at `glob[i]`, the index after it). A backslash escapes the next char."""
    if glob[i] == "\\" and i + 1 < len(glob):
        return glob[i + 1], i + 2
    return glob[i], i + 1


def _glob_bracket(glob: str, at: int):
    """(the fnmatch class for the bracket expression that opens at `glob[at]`, the index after it), or
    None when it never closes, so the `[` is a literal. glibc and rg negate with `^` as well as `!`,
    and glibc reads `[:alpha:]` inside a bracket as a class. Python's fnmatch reads neither, so the
    class is written out as its members: a range, a POSIX class, or a char after a backslash."""
    i = at + 1
    negated = glob[i:i + 1] in ("!", "^")
    i += negated
    chars, first = set(), True
    while i < len(glob) and (glob[i] != "]" or first):
        first = False
        end = glob.find(":]", i + 2) if glob.startswith("[:", i) else -1
        if end != -1 and glob[i + 2:end] in GLOB_POSIX_CLASS_MEMBERS:
            chars |= _class_chars(GLOB_POSIX_CLASS_MEMBERS[glob[i + 2:end]])
            i = end + 2
            continue
        low, i = _bracket_member(glob, i)
        high = low
        if glob[i:i + 1] == "-" and glob[i + 1:i + 2] not in ("", "]"):
            high, i = _bracket_member(glob, i + 1)
        chars |= _class_chars(low + "-" + high) if high != low else {low}
    if i >= len(glob):
        return None
    # `]` goes first and `-` last, and `!` and `^` are never first, so every fnmatch reads the set the same
    # way. Only a leading `!` or `^` in the glob negates; a `!` elsewhere is a member.
    body = "".join(sorted(chars - set("]!^-")))
    text = ("]" if "]" in chars else "") + body + "".join(c for c in "!^-" if c in chars)
    if text[:1] in ("!", "^") and len(text) > 1:
        text = text[1:] + text[0]
    if not negated and text == "!":
        return "!", i + 1
    return "[%s%s]" % ("!" if negated else "", text), i + 1


def _glob_unescaped(glob: str) -> str:
    """`glob` as fnmatch reads it, with each `\\x` that rg and grep read as the literal x written out: a
    wildcard becomes a one-letter class (`\\*` is `[*]`), any other letter stands for itself. A bracket
    expression is written out by `_glob_bracket`. A trailing lone backslash stays."""
    out, i = [], 0
    while i < len(glob):
        char = glob[i]
        if char == "\\" and i + 1 < len(glob):
            letter = glob[i + 1]
            out.append("[%s]" % letter if letter in "*?[" else letter)
            i += 2
        elif char == "[":
            made = _glob_bracket(glob, i)
            out.append(made[0] if made else "[[]")
            i = made[1] if made else i + 1
        else:
            out.append(char)
            i += 1
    return "".join(out)


def _glob_picks(name: str, relative: str, glob: str, fold: bool, by_name: bool = False, named: bool = False) -> bool:
    """True when a file named `name`, at path `relative` (`_glob_anchor`), matches `glob`. With
    `named` (grep's `--include` and `--exclude` on a file it is named) the glob is matched on the
    whole path and on each tail of it after a `/`, so `sub/*` picks `./sub/a`. With `by_name` (grep's
    rules on a file it finds in a folder) the glob is matched on the name alone, so a glob
    with a `/` picks no file. Otherwise a glob with no `/` is matched on the name, and one with a `/`
    on the relative path, where a leading `**/` also matches at the top and a mid-glob `**/` matches
    zero folders. `*` crosses a `/`, so a doubtful glob picks more, never less."""
    if fold:
        name, relative, glob = name.lower(), relative.lower(), glob.lower()
    if named:
        glob = _glob_unescaped(glob)
        tails = [relative] + [relative[at + 1:] for at, letter in enumerate(relative)
                              if letter == "/" and relative[at + 1:at + 2] != "/"]
        return any(fnmatch.fnmatchcase(tail, glob) for tail in tails)
    # rg anchors a glob that leads with `/` at the folder it searches. grep and find match a name, which holds no
    # `/`, so a leading `/` there makes a glob that picks nothing.
    glob = _glob_unescaped(glob if by_name else glob.lstrip("/"))
    if by_name or "/" not in glob:
        return fnmatch.fnmatchcase(name, glob)
    return any(fnmatch.fnmatchcase(relative, g) or (
        g.startswith("**/") and fnmatch.fnmatchcase(relative, g[3:])) for g in _zero_folder_forms(glob))


def _glob_picked(name: str, relative: str, rules, by_name: bool = False, named: bool = False) -> tuple:
    """(whether a file is read, whether the rule that read it overrides the ignore rules), by the
    include and exclude `rules` as grep applies them: the LAST rule whose glob matches the file
    decides (`_glob_picks` reads `by_name` and `named`). With no match, a file is read unless the
    first rule is an include."""
    for kind, pattern, fold, overrides in reversed(rules):
        if _glob_picks(name, relative, pattern, fold, by_name, named):
            return kind == "include", kind == "include" and overrides
    return not rules or rules[0][0] != "include", False


def _glob_anchor(folder: str, cwd: str) -> str:
    """The path from `cwd` to the searched `folder`, with `/` separators and a trailing `/`, or '' for
    `cwd` itself. rg matches a glob with a `/` against the path from cwd, so `-g 'sub/*' K sub` reads
    each file in sub. A folder outside cwd gives its absolute path, which rg matches as it stands."""
    try:
        relative = os.path.relpath(folder, cwd).replace(os.sep, "/")
    except ValueError:  # another drive
        relative = ".."
    if relative == ".":
        return ""
    if relative == ".." or relative.startswith("../"):
        return os.path.abspath(folder).replace(os.sep, "/").rstrip("/") + "/"
    return relative + "/"


def _env_file_in(folder: str, rules=(), exclude_dir=(), ignored=frozenset(), by_name=False,
                 anchor="", min_depth: int = 0, max_depth=None, named=False, prune=None) -> str:
    """The first env file under `folder`, or ENV_TOO_LARGE past ENV_WALK_LIMIT entries, else ''. A symlink is not followed, as rg and ag do not.
    `.git` holds no env file and is skipped. `rules` narrow it, as `_glob_picked` reads them (`by_name` and `named` are grep's), on
    each path with `anchor` (`_glob_anchor`) in front, and a
    folder that matches an `exclude_dir` glob is not entered. `ignored` is `_ignored_paths`: a file
    or folder in it is skipped, except a file that a rule with `overrides` set picks. An ignored folder
    that such a rule's glob picks by itself is entered, as rg enters it: `-g '*'` picks every folder.
    `min_depth` and `max_depth` (None for no limit) bound the depth of a file as find counts it: a file in
    `folder` is at depth 1, and a file in a folder under it at depth 2. `prune(path, name)` (`_find_pruned`)
    says find does not enter the folder `name`, which find prints as `path`: it is not walked, so its entries
    do not count toward the cap."""
    seen = 0
    overriding = [rule for rule in rules if rule[3]]
    for top, dirs, files in os.walk(folder):
        relative = os.path.relpath(top, folder).replace(os.sep, "/")
        prefix = "" if relative == "." else relative + "/"
        dirs[:] = [d for d in dirs if d != ".git"
                   and not (prune and prune(anchor + prefix + d, d))
                   and not any(_glob_picks(d, d, g, False, by_name=True) for g in exclude_dir)
                   and (prefix + d + "/" not in ignored
                        or any(_glob_picks(d, anchor + prefix + d, glob_text, fold)
                               for _, glob_text, fold, _ in overriding))]
        level = 0 if relative == "." else relative.count("/") + 1
        if max_depth is not None and level + 1 >= max_depth:
            dirs[:] = []
        seen += len(dirs) + len(files)
        for name in files:
            if not names_env_file(name) or level + 1 < min_depth or (max_depth is not None and level + 1 > max_depth):
                continue
            read, overrides = _glob_picked(name, anchor + prefix + name, rules, by_name, named)
            if read and (overrides or prefix + name not in ignored):
                return os.path.join(top, name)
        if seen > ENV_WALK_LIMIT:
            return ENV_TOO_LARGE
    return ""


def _exclude_dir_skips(typed, exclude_dir) -> bool:
    """True when grep skips the folder operand `typed`, as grep receives it, because an `exclude_dir` glob
    matches it. grep 3.11 matches the operand on its whole text and on each tail after a `/`, as typed, and
    skips no folder when no operand is typed (`typed` is None). A `.` or `..` last part or a trailing `/`
    is never skipped: the guard is not sure of grep there, and walking is the safe side."""
    if typed is None or typed.endswith("/") or typed.rsplit("/", 1)[-1] in (".", ".."):
        return False
    return any(_glob_picks(typed, typed, g, False, named=True) for g in exclude_dir)


def _search_walk(folder: str, here: str, rules, exclude_dir, grep: bool, no_ignore: bool, typed=None) -> str:
    """The first env file a search reads in `folder` that it is given, as `_env_file_in` returns it. The
    search's include `rules` and `exclude_dir` globs narrow it, with the path from `here` (`_glob_anchor`) in
    front. `typed` is the folder operand as grep receives it, or None for a folder no operand names; grep
    skips it when `_exclude_dir_skips` says so. For rg and ag with the ignore rules on, a file the checkout
    ignores is skipped (`_ignored_paths`, read only when the first walk found a file or ran past the cap)."""
    anchor = _glob_anchor(folder, here)
    if _exclude_dir_skips(typed, exclude_dir):
        return ""
    found = _env_file_in(folder, rules, exclude_dir, by_name=grep, anchor=anchor)
    if found and not grep and not no_ignore:
        found = _env_file_in(folder, rules, exclude_dir, ignored=_ignored_paths(folder), anchor=anchor)
    return found


def _grep_recursive(words, position: int) -> bool:
    """True when a grep command line asks for a recursive search: `-r`, `-R` (alone or in a
    cluster such as `-rn`), `-d recurse`, or a long form. A cluster ends at a letter that takes a
    value, as in `_pattern_words`."""
    i = position + 1
    while i < len(words):
        word = _flag_word(words[i])
        i += 1
        if word == "--":
            return False
        if word.startswith("--"):
            name, _, value = word.partition("=")
            if name in ENV_GREP_RECURSIVE_LONG or (name == "--directories" and value == "recurse"):
                return True
            continue
        if not word.startswith("-") or word == "-":
            continue
        for k, letter in enumerate(word[1:], 1):
            rest = word[k + 1:]
            if letter in "rR":
                return True
            if letter == "d" and (rest or (words[i] if i < len(words) else "")) == "recurse":
                return True
            if letter in ENV_GREP_VALUE_SHORT:
                i += 0 if rest else 1
                break
    return False


def _grep_globs(words, position: int):
    """The (rules, exclude-dir globs) of a grep command line, as the shell passes them. A rule is
    (`include` or `exclude`, glob, False, False), in command-line order. An unquoted brace list is
    expanded, and a whole quoted flag word is read as the flag."""
    raw = [e for word in words[position + 1:] for e in _brace_expand(word)]
    shaped = [_flag_word(e) for e in raw]
    rules, exclude_dir = [], []
    for i, word in enumerate(shaped):
        name, attached, value = word.partition("=")
        if name in ("--include", "--exclude", "--exclude-dir"):
            at = i
            if not attached and i + 1 < len(shaped):
                at, value = i + 1, shaped[i + 1]
            # The shell removes the quotes, and the backslash of an unquoted `\*`, before grep reads the glob.
            # A flag that was one whole quoted word keeps its backslashes.
            value = re.sub(r"[\"']", "", value) if raw[at] != shaped[at] else _shell_value(value)
            if name == "--exclude-dir":
                exclude_dir.append(value.rstrip("/"))
            else:
                rules.append((name[2:], value, False, False))
    return rules, exclude_dir


def _rg_rules(extras):
    """The include rules an rg command line makes: each positive `-g` or `--iglob` glob, which
    overrides the ignore rules, and each `-t` type's globs. A type outside `ENV_RG_TYPE_GLOBS` may
    pick any file, so it is one catch-all rule. No rule when no glob and no type is given."""
    rules = [("include", glob, fold, True) for glob, fold in extras["globs"]]
    types = extras["types"]
    if extras["types_open"] or any(t not in ENV_RG_TYPE_GLOBS for t in types):
        return rules + [("include", "*", False, bool(rules))]
    return rules + [("include", g, False, False) for t in types for g in ENV_RG_TYPE_GLOBS[t]]


def _pwd_rest(word: str, pwd_text: bool):
    """The rest of a path word after `$PWD`, `${PWD}` or a `pwd` substitution (`x` in the text around
    it, from `_substitutions`), or None when the word starts with none of them."""
    found = re.fullmatch(r"(?:\$PWD|\$\{PWD\}%s)(/.*)?" % ("|x|`x`" if pwd_text else ""), word)
    return None if found is None else (found.group(1) or "")


def _rules_skip_env(rules) -> bool:
    """True when no sample env name could be read by the glob rules (grep's, or rg's include rules):
    the first rule is an include, so a file that no rule matches is not read, and no include glob
    could name an env file (`_glob_could_name_env`). With no rule, or a first rule that excludes, a
    file no rule matches is read. Only the cap reads this: a folder past the cap cannot be walked, so
    such a glob clears the refusal as too large to check. A folder under the cap is always walked,
    because an env file with a suffix a glob picks (`.yaml`) is not a sample name."""
    return bool(rules) and rules[0][0] == "include" and not any(
        kind == "include" and _glob_could_name_env(glob, fold, by_path=True)
        for kind, glob, fold, _ in rules)


# The shell commands that run a string as a command of their own.
ENV_SHELL_STRING_COMMANDS = ("bash", "sh", "zsh", "dash", "ksh", "eval", "su")
# The long options of bash and sh that take a value word, so the word is no script.
ENV_SHELL_VALUE_LONG = ("--rcfile", "--init-file")


def _su_string(words, position: int) -> str:
    """The text `su -c STRING`, `su --command=STRING` or `su -cSTRING` runs, else ''. A user name may come before
    the flag, and `-s`, `-g` and `-G` take a value word of their own."""
    i = position + 1
    while i < len(words):
        word = _flag_word(words[i])
        i += 1
        if word.startswith("--"):
            name, attached, value = word.partition("=")
            if name == "--command":
                return _shell_value(value if attached else (words[i] if i < len(words) else ""))
            i += not attached and name in ("--shell", "--group", "--supp-group")
        elif word.startswith("-") and word != "-":
            for k, letter in enumerate(word[1:], 1):
                rest = word[k + 1:]
                if letter == "c":
                    return _shell_value(rest or (words[i] if i < len(words) else ""))
                if letter in "sgG":
                    i += not rest
                    break
    return ""


def _shell_string(words, position: int, command: str) -> str:
    """The text a shell runs from a string, else ''. `bash -c STRING` and `sh -c STRING` (the `-c` may
    sit in a cluster such as `-lc`) run the first word after their options. `su -c STRING` runs it too
    (`_su_string`). `eval` runs its words joined by spaces. Each word is read by `_shell_value`, the
    tokenizer's quote removal."""
    if command == "eval":
        return " ".join(_shell_value(word) for word in words[position + 1:])
    if command == "su":
        return _su_string(words, position)
    run, i = False, position + 1
    while i < len(words):
        word = _flag_word(words[i])
        if word == "--":   # the options end here, and the next word is the string
            return _shell_value(words[i + 1]) if run and i + 1 < len(words) else ""
        if word in ("-", "+") or not word.startswith(("-", "+")):
            return _shell_value(words[i]) if run else ""
        long_option = word.startswith("--")
        run = run or (word[0] == "-" and not long_option and "c" in word)
        i += 2 if word in ENV_SHELL_VALUE_LONG or (not long_option and word[-1] in "oO") else 1
    return ""


# Stands in the text around a substitution, to find the segment that holds it (`_text_folders`).
ENV_PLACE_MARK = "\ue000"


# Past this many cds that might not run, every combination is not tried: all run, all skipped and each
# skipped alone are.
ENV_SKIP_LIMIT = 6


def _branch_bodies(pieces):
    """The branch bodies each segment sits in, one tuple of body numbers per segment, outermost first.
    A body opens at a segment that starts `then`, `do` or `else`, and closes at one that starts `fi`,
    `done`, `else` or `elif`, so a `cd` after `echo x;` in a `then` branch, or on a line of its own, is in
    the body as well. ACCEPTED LIMIT: a `case` branch is not read as a body."""
    paths, stack, opened = [], [], 0
    for piece in pieces:
        first = piece.split(None, 1)[:1]
        word = first[0] if first else ""
        if word in ("fi", "done", "elif", "else") and stack:
            stack.pop()
        if word in ("then", "do", "else"):
            opened += 1
            stack.append(opened)
        paths.append(tuple(stack))
    return paths


def _folders_at(pieces, number: int, bases, ends):
    """The folders the shell may be in when `pieces[number]` runs, started from each folder in `bases`
    (`dir_before_segment`, which falls back to the base when it cannot tell). A `cd` after `&&` or `||`,
    or in a branch body of an `if` or a loop that closes before the segment (`_branch_bodies`), might not
    run, so the segment is judged with each combination of those `cd`s run and skipped. With more than
    ENV_SKIP_LIMIT of them, only all run, all skipped and each skipped alone are tried. The combinations
    run through `dir_before_segment`, the one place that reads `cd -`, a subshell paren and a failed `cd`.

    A skipped `cd` after `&&` is judged only when the segment can still run without it: a connector
    from the `cd` up to the segment is not `&&` or `|`. After `&&` with only `&&` up to the
    segment (`test -d D && cd D && rg K`), the `&&` before the `cd` failed, so the chain stops there
    and the segment never runs in the folder before the `cd`. A pipe up to the segment does not break the
    chain: `cd D && echo | rg K` runs the whole pipe or none of it. A `cd` after `||` is always judged
    skipped. A `cd` in a body that does not hold the segment is always judged skipped, since the body may
    not run."""
    bodies = _branch_bodies(pieces)

    def conditional_cd(at):
        if at > len(ends) or not (tokens := segment_tokens(pieces[at])) or _segment_cd_move(tokens) is None:
            return False
        if ends[at - 1] == "||" or (bodies[at] and bodies[number][:len(bodies[at])] != bodies[at]):
            return True
        return ends[at - 1] == "&&" and any(end not in ("&&", "|") for end in ends[at:number])

    conditional = [at for at in range(1, number) if conditional_cd(at)]
    skips = [[]]
    if len(conditional) <= ENV_SKIP_LIMIT:
        skips = [[at for at, bit in zip(conditional, bits) if bit]
                 for bits in itertools.product((False, True), repeat=len(conditional))]
    elif conditional:
        skips += [conditional] + [[at] for at in conditional]
    variants = [[":" if at in skipped else piece for at, piece in enumerate(pieces)] for skipped in skips]
    found = []
    for base in bases:
        for variant in variants:
            folder = dir_before_segment(variant, number, base, ends) or base
            if folder not in found:
                found.append(folder)
    return found


def _text_folders(texts, cwd, places):
    """The folders each text of `_substitutions` may run in, one list per text. The command itself runs
    in `cwd` (a folder, or a list of them). A substitution runs where the segment that holds it runs, so a
    `cd` earlier in that command moves it too: `cd D && x=$(rg --hidden K)` searches D. A parent comes
    after its children, so the texts are read from the last. A text whose place cannot be found in its
    parent keeps the parent's folders."""
    folders = [[cwd] if isinstance(cwd, str) else list(cwd)] * len(texts)
    for child in range(len(texts) - 2, -1, -1):
        parent, offset = places[child]
        text = texts[parent][0]
        ends = []
        pieces = split_segments(text[:offset] + ENV_PLACE_MARK + text[offset:], ends)
        number = next((at for at, piece in enumerate(pieces) if ENV_PLACE_MARK in piece), None)
        folders[child] = folders[parent] if number is None else _folders_at(
            pieces, number, folders[parent], ends)
    return folders


def _every_folder(texts, cwd):
    """Every folder a segment of any text may run in, started from `cwd` (a folder, or a list of them).
    It fails closed when the place of each substitution is not known (`places` out of step with the
    texts): each text is judged in every folder a `cd` in any text reaches. A `cd` in a nested
    substitution moves from the folders found before it, so the search repeats until it finds no new
    folder, once per text at most."""
    found = [cwd] if isinstance(cwd, str) else list(cwd)
    for _round in range(len(texts)):
        new = []
        for text, _in_message in texts:
            ends = []
            pieces = split_segments(text, ends)
            for number in range(1, len(pieces)):
                new += [f for f in _folders_at(pieces, number, found, ends) if f not in found + new]
        if not new:
            break
        found += new
    return found


ENV_FIND_EXPRESSION = ("(", "!", "-not", "-o", "-or")
# The options find reads before its start folders, and the ones of them that take a value word.
ENV_FIND_LEAD = ("-H", "-L", "-P", "-D")
# The find actions that print other text than the name a test matched, such as the folder (`-printf '%h'`) or a
# program's output (`-exec`), so a `-name` test does not bound what the search is handed.
ENV_FIND_OTHER_OUTPUT = ("-printf", "-fprintf", "-fprint", "-fprint0", "-fls", "-ls", "-exec", "-execdir", "-ok",
                         "-okdir")
ENV_WALK_REASON_FED = ("this command would search a name that a lister hands to xargs, and the name is an "
                       "environment file")
ENV_WALK_REASON_EXEC = ("this command would search a name that find hands to its -exec program, and the name is "
                        "an environment file")


def _find_group_end(expression, start: int) -> int:
    """The index of the `)` that closes the `(` at `expression[start]`, or -1 when none does."""
    level = 0
    for at in range(start, len(expression)):
        if expression[at] == "(":
            level += 1
        elif expression[at] == ")":
            level -= 1
            if level == 0:
                return at
    return -1


def _find_names_no_env(expression, runners: bool = False) -> bool:
    """True when each name a find expression prints matches a `-name` or `-iname` glob that no env file name
    fits. The words are dequoted. Without a paren, find's `-a` binds tighter than `-o`, so each part between
    two top-level `-o` is one alternative. Each alternative needs a `-name` or `-iname` test that no `!` or
    `-not` turns round. Any other test in it, negated or not, only narrows the names. When an explicit
    `-print` or `-print0` sits in the expression, only an alternative that holds one prints (a `-prune`
    branch with none prints nothing), and only its tests before the first print narrow what it prints. A
    paren group is one test: it narrows the names when each alternative inside it does (`\\( -name '*.py' -o
    -name '*.md' \\)`), and narrows nothing otherwise. A group that holds a print or a program, an unmatched
    paren, or an action that prints other text than the name, is not read, and the answer is False. With
    `runners` set, the names are the ones find hands to its `-exec` programs (`{}`), not the ones it prints: a
    runner and its program words, up to the `;` or `+` that ends them, then count as a `-print` in its
    alternative, so only the tests before it narrow the names it gets."""
    alternatives, current, at = [], [], 0
    printing = []
    printed = False
    while at < len(expression):
        word = expression[at]
        if runners and word in ENV_FIND_RUNNERS:
            printed = True
            while at < len(expression) and expression[at] not in ENV_FIND_RUNNER_ENDS:
                at += 1
        elif word == "(":
            end = _find_group_end(expression, at)
            group = expression[at + 1:end] if end > at else []
            if end < 0 or any(w in ("-print", "-print0") or w in ENV_FIND_OTHER_OUTPUT for w in group):
                return False
            negated = at > 0 and expression[at - 1] in ("!", "-not")
            if not negated and not printed:
                current.append(_find_names_no_env(group))
            at = end
        elif word == ")" or word in ENV_FIND_OTHER_OUTPUT:
            return False
        elif word in ("-o", "-or"):
            alternatives.append(current)
            printing.append(printed)
            current, printed = [], False
        elif word in ("-print", "-print0"):
            printed = True
        elif word in ("-name", "-iname") and at + 1 < len(expression):
            negated = at > 0 and expression[at - 1] in ("!", "-not")
            if not negated and not printed:
                current.append(not _glob_could_name_env(expression[at + 1], word == "-iname"))
            at += 1
        at += 1
    alternatives.append(current)
    printing.append(printed)
    if any(printing):
        alternatives = [names for names, prints in zip(alternatives, printing) if prints]
    return all(any(names) for names in alternatives)


def _find_type_d_bounds_all(expression, runners: bool = False) -> bool:
    """True when an unnegated `-type d` bounds every alternative of a find expression that reaches what the
    search is handed, so find hands over folders alone. Alternatives are the parts between two top-level `-o`.
    With `runners` set, the ones that count hold a `-exec`, `-execdir`, `-ok` or `-okdir`, and its `-type d`
    must come before the runner. Otherwise the ones that count hold no `-prune` (a prune branch prints only the
    folder it stops at, which a `-type d` branch of its own prints too). The `-type d` must stand in the
    alternative itself, not in a paren group: a group, or a runner inside one, is not read, so the answer is
    False. One `-type d` in one alternative of an `-o` chain then does not decide the others (`-type d -o
    -type f -exec grep K {} +` hands over files)."""
    alternatives, current = [], []
    for word in expression:
        if word in ("-o", "-or"):
            alternatives.append(current)
            current = []
        else:
            current.append(word)
    alternatives.append(current)
    found = False
    for words in alternatives:
        folders, runs, level, at = False, False, 0, 0
        while at < len(words):
            word = words[at]
            if word == "(":
                level += 1
            elif word == ")":
                level -= 1
            elif word in ENV_FIND_RUNNERS:
                if level:
                    return False
                runs = True
                while at < len(words) and words[at] not in ENV_FIND_RUNNER_ENDS:
                    at += 1
            elif word == "-type" and words[at + 1:at + 2] == ["d"] and not level and not runs:
                folders = folders or not (at > 0 and words[at - 1] in ("!", "-not"))
            at += 1
        reaches = runs if runners else "-prune" not in words
        if reaches and not folders:
            return False
        found = found or (reaches and folders)
    return found


def _find_depth_limits(expression):
    """(min depth, max depth) that find's `-mindepth N` and `-maxdepth N` set, the max None for no limit. A
    value that is not a number, or a missing one, sets no limit. With a repeat, the wider limit stands."""
    low, high = None, None
    for at, word in enumerate(expression[:-1]):
        value = expression[at + 1]
        if word not in ("-mindepth", "-maxdepth") or not value.isdigit():
            continue
        if word == "-mindepth":
            low = int(value) if low is None else min(low, int(value))
        else:
            high = int(value) if high is None else max(high, int(value))
    return low or 0, high


# The find tests that tell which folder a `-prune` alternative stops at: `-path` and `-name`, each with its
# `i` form that ignores case, and `-type d`.
ENV_FIND_GLOB_PATH_TESTS = {"-path": False, "-wholename": False, "-ipath": True, "-iwholename": True}
ENV_FIND_GLOB_NAME_TESTS = {"-name": False, "-iname": True}


def _find_pruned(expression):
    """A function `(path, name) -> bool` that says find does not enter the folder `name`, printed as `path`, or
    None when no folder is pruned that the guard can tell. An alternative (between two top-level `-o`) that holds
    `-prune` prunes the folders that pass the tests before it, when those are `-path`, `-name` and `-type d`
    tests only. An alternative with any other test before its `-prune`, a `!`, or a paren in the expression is
    not read: find then prunes at most what the guard walks, and the folder is counted. With `-depth` or
    `-delete`, find ignores `-prune`, so nothing is pruned."""
    if "(" in expression or "-depth" in expression or "-delete" in expression:
        return None
    alternatives, current = [], []
    for word in expression:
        if word in ("-o", "-or"):
            alternatives.append(current)
            current = []
        else:
            current.append(word)
    alternatives.append(current)
    def read_tests(words, stop: int):
        """The `-path` and `-name` tests in `words[:stop]` as (kind, glob, ignores case), or None when any other
        test or a `!` stands there. A `-type d` test is read as no test: it only narrows."""
        tests, at = [], 0
        while at < stop:
            word = words[at]
            if word in ("-a", "-and"):
                at += 1
            elif (word in ENV_FIND_GLOB_PATH_TESTS or word in ENV_FIND_GLOB_NAME_TESTS) and at + 1 < len(words):
                kind = "path" if word in ENV_FIND_GLOB_PATH_TESTS else "name"
                tests.append((kind, words[at + 1], {**ENV_FIND_GLOB_PATH_TESTS, **ENV_FIND_GLOB_NAME_TESTS}[word]))
                at += 2
            elif word == "-type" and words[at + 1:at + 2] == ["d"]:
                at += 2
            else:
                return None
        return tests

    # Find reaches an alternative only when each one before it is false for the entry. An earlier alternative with
    # no `-prune` (`-name '*.py'`, or `-print` with no test) holds for the entries its tests pick, and find stops
    # there: it neither prunes nor enters differently for them. Such an alternative shadows the prunes after it for
    # those entries (`shadows`). One whose tests are not `-path` or `-name` tests, with at most a closing print,
    # ends the reading, so no prune after it is counted.
    prunes, shadows = [], []
    for words in alternatives:
        if "-prune" not in words:
            end = len(words) - (1 if words[-1:] in (["-print"], ["-print0"]) else 0)
            shadow = read_tests(words, end)
            if shadow is None or any(w in ("-prune", "-print", "-print0") for w in words[:end]):
                break
            shadows.append(shadow)
            continue
        tests = read_tests(words, words.index("-prune"))
        if tests:
            prunes.append((tests, list(shadows)))
    if not prunes:
        return None

    def pruned(path: str, name: str) -> bool:
        def holds(kind, glob_text, fold):
            if kind == "name":
                return _glob_picks(name, name, glob_text, fold, by_name=True)
            shown = path.lower() if fold else path
            return fnmatch.fnmatchcase(shown, _glob_unescaped(glob_text.lower() if fold else glob_text))
        return any(all(holds(*test) for test in tests) and not any(all(holds(*test) for test in shadow)
                                                                    for shadow in earlier)
                   for tests, earlier in prunes)
    return pruned


def _find_prints_nothing(starts, here: str, expression, low: int, high) -> bool:
    """True when no entry under the start folders of a find has a name that one of its `-name` or `-iname` globs
    picks, within the depth limits, so the find prints nothing and a xargs behind it runs on no names. A find with
    no such glob, a start word with a variable, or a tree past ENV_WALK_LIMIT entries is not known to print
    nothing. A negated test picks no name here."""
    globs = [(expression[at + 1], word == "-iname") for at, word in enumerate(expression[:-1])
             if word in ENV_FIND_GLOB_NAME_TESTS and expression[at - 1:at] not in (["!"], ["-not"])]
    if not globs:
        return False

    def picked(name: str, level: int) -> bool:
        return level >= low and (high is None or level <= high) and any(
            _glob_picks(name, name, pattern, fold, by_name=True) for pattern, fold in globs)

    seen = 0
    for word, start in starts:
        if re.search(r"[$`]", start):
            return False
        target = os.path.join(here, os.path.expanduser(start))
        expand = re.search(r"[*?\[]", start) and word == start
        for folder in glob.glob(target) if expand else [target]:
            if not os.path.exists(folder):
                continue
            if picked(os.path.basename(start.rstrip("/")) or start, 0):
                return False
            for top, dirs, files in os.walk(folder):
                relative = os.path.relpath(top, folder).replace(os.sep, "/")
                level = 0 if relative == "." else relative.count("/") + 1
                if any(picked(name, level + 1) for name in dirs + files):
                    return False
                seen += len(dirs) + len(files)
                if seen > ENV_WALK_LIMIT:
                    return False
                if high is not None and level + 1 >= high:
                    dirs[:] = []
    return True


def _find_folder_names(expression):
    """(whether a find expression may print a folder, the (glob, ignores case) of the `-name` and `-iname` tests
    on the alternatives that may). An alternative prints only files when an unnegated `-type f` comes before
    its first `-print`. Alternatives are read as in `_find_names_no_env`. `-printf` prints a file's folder. With
    a paren the expression is not split: it prints only files when no `-o` or negation is in it and a
    `-type f` is."""
    def glob_at(at):
        negated = at > 0 and expression[at - 1] in ("!", "-not")
        return None if negated or at + 1 >= len(expression) else (expression[at + 1], expression[at] == "-iname")
    every = [g for at, word in enumerate(expression) if word in ("-name", "-iname") and (g := glob_at(at))]
    if "-printf" in expression:
        return True, every
    if "(" in expression:
        files_only = (not any(w in ("-o", "-or", "!", "-not") for w in expression)
                      and any(w == "-type" and expression[i + 1:i + 2] == ["f"] for i, w in enumerate(expression)))
        return not files_only, every
    alternatives, files_only, printed, globs = [], False, False, []
    for at, word in enumerate(expression):
        if word in ("-o", "-or"):
            alternatives.append((files_only, printed, globs))
            files_only, printed, globs = False, False, []
        elif word in ("-print", "-print0"):
            printed = True
        elif word == "-type" and not printed and expression[at + 1:at + 2] == ["f"]:
            files_only = files_only or not (at > 0 and expression[at - 1] in ("!", "-not"))
        elif word in ("-name", "-iname") and not printed and glob_at(at):
            globs.append(glob_at(at))
    alternatives.append((files_only, printed, globs))
    if any(prints for _, prints, _ in alternatives):
        alternatives = [a for a in alternatives if a[1]]
    folders = [a for a in alternatives if not a[0]]
    return bool(folders), [g for a in folders for g in a[2]]


def _find_folder_env(folder: str, globs, base: str, low: int, high, walk=_env_file_in, prune=None,
                     shown: str = "") -> str:
    """The first env file below a folder that find would print because a `-name` glob in `globs` matches it, or
    '' for none. `folder` is depth 0 and takes the name `base`, as find names a start word. A folder at depth
    `low` to `high` (None for no limit) that matches is read whole by the program that gets its name, so
    `walk(path)` (`_env_file_in` by default) judges it, each under its own cap. A folder is judged when its
    parent lists it, so one that sits in a parent past ENV_WALK_LIMIT entries is still judged. Past the cap, a
    folder that is not listed in the part of the tree walked is not seen, and so ENV_TOO_LARGE is returned,
    for the walk or for a printed folder that is too large to judge. `prune(path, name)` (`_find_pruned`) says find
    prints the folder `name` as `path` (the start `shown`, then the way down) but does not enter it: its name is
    judged and its entries are not walked, so they do not count toward the cap."""
    def printed(path: str, name: str, level: int) -> str:
        if level >= low and (high is None or level <= high) and any(
                _glob_picks(name, name, pattern, fold, by_name=True) for pattern, fold in globs):
            return walk(path)
        return ""

    found = printed(folder, base, 0)
    if found:
        return found
    seen = 0
    for top, dirs, files in os.walk(folder):
        relative = os.path.relpath(top, folder).replace(os.sep, "/")
        level = 0 if relative == "." else relative.count("/") + 1
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in dirs:
            found = printed(os.path.join(top, name), name, level + 1)
            if found:
                return found
        if prune:
            dirs[:] = [d for d in dirs if not prune("%s/%s" % (
                (shown or base).rstrip("/"), os.path.relpath(os.path.join(top, d), folder).replace(os.sep, "/")), d)]
        if high is not None and level >= high:
            dirs[:] = []
        seen += len(dirs) + len(files)
        if seen > ENV_WALK_LIMIT:
            return ENV_TOO_LARGE
    return ""


def _xargs_source(pieces, ends, number: int, part: int, here: str, reads_folders: bool = True,
                  narrowing=((), (), False, False), runs_empty: bool = False):
    """What the segment before an `xargs` puts on its stdin (`_feed_source`). `runs_empty` is set when xargs
    runs its command once with no names for an empty stdin, as GNU xargs does without `-r`. Any other source,
    or a pipe that is not directly before the xargs, names paths the guard cannot see, so `here` is walked."""
    unknown = ("", True, [])
    if not (part == 0 and number > 0 and ends[number - 1] == "|"):
        return unknown
    words, position, command = _env_words(_env_parts(pieces[number - 1])[-1], walk=True)
    return _feed_source(command, words[position + 1:], here, reads_folders, narrowing, runs_empty)


def _feed_source(command: str, rest, here: str, reads_folders: bool = True,
                 narrowing=((), (), False, False), runs_empty: bool = False, exec_feed: bool = False):
    """What the lister `command` (its argument words are `rest`) hands to a search as names, from xargs or as
    the `{}` of its own `-exec`: (the env file it names, whether the search may walk `here`, the folders it
    names). The env file is '' for none, a path, or ENV_TOO_LARGE. With `runs_empty` the search runs once on
    `here` when the lister names nothing, so `here` is walked then.

    `find` names every file under each folder it is given (default `.`), and `ls -a` or `ls -A` names each
    entry of the folder, dotfiles too. Each file name reaches the search as a path. rg reads it whatever its
    globs, and grep reads it when its include and exclude rules pick the path (`_glob_picks` with `named`). A folder find prints is read whole only when `reads_folders` is set: the search
    walks a folder and reads the dotfiles in it (`_env_walk`). A `find` whose every alternative has a
    `-name` or `-iname` glob that no env file name fits (`*.py`) names none (`_find_names_no_env`). Each
    folder find prints is walked as the search walks a folder it is given (`_search_walk`), narrowed by
    the search's include rules and ignore set (`narrowing`: rules, exclude-dir globs, whether grep's, whether
    the ignore rules are off). With a `-name` glob, each such folder has its own cap, and only a folder too
    large to walk is judged by its names alone. A file find names is judged by grep's include and exclude rules
    alone, and for rg whatever the narrowing. `-type d`
    names folders alone. A start word
    with a variable names folders the guard cannot see. A plain `ls` names no dotfile, so only the folders it names are
    walked. `ls -a` also names `.` and `..`, so `here` and its parent are walked. Any other source
    names paths the guard cannot see, so `here` is walked."""
    unknown = ("", True, [])
    flags = [w for w in rest if w.startswith("-")]
    paths = [w for w in rest if not w.startswith("-")]
    if command == "ls":
        letters = "".join(w[1:] for w in flags if not w.startswith("--"))
        if paths or "R" in letters or "--recursive" in flags:
            return unknown
        dotfiles = "a" in letters or "A" in letters or "--all" in flags or "--almost-all" in flags
        try:
            entries = sorted(os.listdir(here))
        except OSError:
            return unknown
        folders = [os.path.join(here, n) for n in entries
                   if (dotfiles or not n.startswith(".")) and os.path.isdir(os.path.join(here, n))]
        # grep skips a name that its include and exclude rules leave out. rg reads each name it is given.
        named = next((os.path.join(here, n) for n in entries if dotfiles and names_env_file(n)
                      and (not narrowing[2] or _glob_picked(n, n, narrowing[0], named=True)[0])), "")
        every = "a" in letters or "--all" in flags
        # `ls -a` names `.` and `..` as well, which listdir leaves out: `.` is `here`, and `..` its parent.
        parent = os.path.dirname(os.path.normpath(here))
        if every and parent and parent != os.path.normpath(here):
            folders.append(parent)
        return named, every, folders
    if command == "find":
        # Bash expands an unquoted brace list in a word before find sees it: `sub/{a,b}` is two start paths.
        rest = [e for w in rest for e in _brace_expand(w)]
        # find sees each word after the shell's quote removal: `"."` is the folder `.`, and `\(` a paren.
        bare = [_shell_value(w) for w in rest]
        at = 0
        while at < len(bare) and bare[at] in ENV_FIND_LEAD:
            at += 2 if bare[at] == "-D" else 1
        starts = []
        while at < len(bare) and not (bare[at].startswith("-") or bare[at] in ENV_FIND_EXPRESSION):
            starts.append((rest[at], bare[at]))
            at += 1
        if _find_type_d_bounds_all(bare[at:], exec_feed):
            # A `-exec` program gets each folder find prints, and a search that reads folders reads each whole. Every
            # folder find prints is the start folder or lies below it, so the start folders hold what is read.
            if not exec_feed:
                return unknown
            folders = []
            for word, start in starts or [(".", ".")]:
                if re.search(r"[$`]", start):
                    return unknown
                target = os.path.join(here, os.path.expanduser(start))
                expand = re.search(r"[*?\[]", start) and word == start
                folders += [f for f in (glob.glob(target) if expand else [target]) if os.path.isdir(f)]
            return "", False, folders
        names_no_env = _find_names_no_env(bare[at:], exec_feed)
        prints_folder, globs = _find_folder_names(bare[at:])
        # A search that reads no folder it is given reads only the files find prints.
        prints_folder = prints_folder and reads_folders
        low, high = _find_depth_limits(bare[at:])

        def names_nothing():
            # Run on no names, xargs runs its search once on `here`: a find that prints nothing leaves it there.
            return ("", runs_empty and _find_prints_nothing(starts or [(".", ".")], here, bare[at:], low, high), [])

        if names_no_env and not prints_folder:
            return names_nothing()
        pruned = _find_pruned(bare[at:])
        rules, exclude_dir, by_name, no_ignore = narrowing

        def narrowed_walk(path: str) -> str:
            # A printed folder is read as the search reads a folder it is given: by its include rules and its ignore set.
            return _search_walk(path, here, rules, exclude_dir, by_name, no_ignore)

        for word, start in starts or [(".", ".")]:
            if re.search(r"[$`]", start):
                return unknown
            target = os.path.join(here, os.path.expanduser(start))
            # A quoted glob is no glob to the shell, so it is not expanded.
            expand = re.search(r"[*?\[]", start) and word == start
            for folder in glob.glob(target) if expand else [target]:
                # The path find prints for the start, as the shell handed it: relative to `here` unless absolute.
                head = os.path.join(here, "")
                shown = (folder[len(head):] if folder.startswith(head) and not os.path.isabs(os.path.expanduser(start))
                         else folder).replace(os.sep, "/")
                if names_no_env:
                    found = (_find_folder_env(folder, globs, os.path.basename(start.rstrip("/")) or start, low, high,
                                              narrowed_walk, pruned, shown)
                             if os.path.isdir(folder) else "")
                    # A folder or tree too large to judge is judged by its names alone, and they name no env file.
                    found = "" if found == ENV_TOO_LARGE else found
                elif os.path.isdir(folder):
                    # rg reads a file it is named whatever its globs. grep reads one only when its include and
                    # exclude rules pick the path find prints. A folder find prints is walked whole by the
                    # search, which reads only the files its rules pick.
                    found = (_env_file_in(folder, rules, anchor=shown.rstrip("/") + "/", min_depth=low,
                                          max_depth=high, named=True, prune=pruned) if by_name
                             else _env_file_in(folder, anchor=shown.rstrip("/") + "/", min_depth=low,
                                               max_depth=high, prune=pruned))
                    if not found and prints_folder:
                        found = _find_folder_env(folder, [("*", False)], os.path.basename(start.rstrip("/")) or start,
                                                 low, high, narrowed_walk, pruned, shown)
                else:
                    base = os.path.basename(folder)
                    found = folder if names_env_file(base) and not low and (
                        not by_name or _glob_picked(base, shown, rules, named=True)[0]) else ""
                if found:
                    return found, False, []
        return names_nothing()
    return unknown


# The find actions that run a program, and the words that end its argument list.
ENV_FIND_RUNNERS = ("-exec", "-execdir", "-ok", "-okdir")
ENV_FIND_RUNNER_ENDS = (";", "+")
# The xargs flags after which it runs nothing for an empty stdin. A plain xargs runs its command once.
ENV_XARGS_NO_EMPTY_RUN = ("-r", "--no-run-if-empty", "-I", "-i", "--replace")


def _find_runners(words, position: int):
    """The programs a find at `words[position]` runs with `-exec`, `-execdir`, `-ok` and `-okdir`, each as
    (its words, the index of its command word past its wrappers, its command name), and the words of the find
    after its name. A program's words run up to the first `;` or `+` word, as find reads them. A `{}` among
    them is a name that find hands over."""
    rest = words[position + 1:]
    found, at = [], 0
    while at < len(rest):
        if _shell_value(rest[at]) in ENV_FIND_RUNNERS:
            end = at + 1
            while end < len(rest) and _shell_value(rest[end]) not in ENV_FIND_RUNNER_ENDS:
                end += 1
            child = rest[at + 1:end]
            start = _skip_wrappers(child, 0, walk=True)
            if start < len(child):
                found.append((child, start, _base(child[start])))
            at = end
        at += 1
    return found, rest


def _xargs_runs_empty(words, position: int) -> bool:
    """True when the xargs before the command word at `position` runs it once with no names for an empty stdin:
    GNU xargs does, unless it has `-r`, or `-I` or `-i`, which make a run per input line."""
    for at, word in enumerate(words[:position]):
        if _wrapper_name(_base(word)) == "xargs":
            flags = _wrapper_flags("xargs", words[:position], at + 1)[1]
            return not any(flag in ENV_XARGS_NO_EMPTY_RUN for flag, _ in flags)
    return False


def _env_walk(texts, cwd, depth: int = 0, places=None):
    """Return (reason, log) when `rg` or `ag` with a hidden flag, `rg` with a positive glob, or a
    recursive grep, walks a folder that holds an env file on disk. The
    folder is each path word that is a folder, or the folder the command runs in when no path is
    named. For rg and ag no pipe or `<` may feed the search either; a recursive grep walks that
    folder whatever feeds it. `rg --files` lists names and reads no contents.

    The folder the command runs in is `cwd`, moved by each literal `cd <dir>` earlier in the command
    (`dir_before_segment`). A `cd` the guard cannot resolve (a variable, `popd`, a folder that does
    not exist) leaves the search at `cwd`. A `cd` after `&&` or `||`, or in a `then`, `else` or `do`
    branch, might not run, so the search is walked in each folder the combinations of those `cd`s reach
    when it can run without them (`_folders_at`). A search in a command substitution runs where the segment
    that holds it runs (`_text_folders`, from `places`), so `cd D && x=$(rg --hidden K)` walks D.
    `cwd` is a folder, or a list of them for a string that a conditional `cd` may run in.

    The search is found behind a subshell paren, a brace group, `command`, `env`, `nice`, `sudo`, `doas`, `nohup`,
    `exec`, `stdbuf`, `setsid` and `xargs` (`_env_words`), and past a redirect in front of the program. `env -C DIR`
    starts the walk in DIR (`_env_chdirs`). Under `xargs` stdin feeds xargs, so a `<`, a pipe, a path or `{}` in the
    command does not spare the folder, and with no names on stdin xargs runs the search once on the folder it is in
    (`_xargs_runs_empty`). A `find` or `ls -a` before the xargs names each env file under the folder it lists, and
    the search is refused over it (`_xargs_source`). The program that a `find -exec`, `-execdir`, `-ok` or `-okdir`
    runs is a search that gets each name find prints, and it is judged the same way (`_find_runners`). A string
    that `bash -c`, `sh -c`, `zsh -c`, `dash -c`, `ksh -c`, `su -c` or `eval` runs is a command of its own: it is cut
    by `_substitutions` and walked from the folder the shell command runs in. An unquoted comma brace
    list in a word (`{a,b}`) is expanded as bash expands it. A path word that starts with `$PWD`,
    `${PWD}` or a `pwd` substitution is that folder. A glob word is expanded against it as the shell
    does (no dotfile).

    The files read are narrowed as the tool narrows them. A grep `--include` and `--exclude` glob
    decides each file by the last of them that matches, on the file's base name alone. An rg positive
    `-g` or `--iglob` glob picks the files read, and reads a file that is hidden or ignored too. A glob
    with a `/` matches the path from that folder (`_glob_anchor`). With no hidden flag, rg reads only
    the dotfiles a glob picks. An rg `-t` type picks by its globs, and a type the guard does not list
    picks every file. A folder is always walked, and an env file that an include glob picks is refused
    at any folder size, whatever its suffix (`--include='*.yaml'` picks one that ends .yaml). Only the
    cap reads the glob: past it, when no include glob (rg `-g` or `--iglob`, grep `--include`) could
    match a sample env file name (`_rules_skip_env`), the search is allowed, and otherwise it is refused
    as too large to check. A search with an rg `-t` type past the cap is refused. For rg and ag with no flag that turns the ignore rules off, a file or folder
    that the checkout ignores is not read, so it is skipped (`_ignored_paths`, one call, made only
    when the first walk found a file or ran past the cap). An ignored folder that a positive glob
    picks is entered, as rg enters it.

    FAILS CLOSED: an rg flag that is in neither of the guard's flag tables might take a word, so the
    search is walked as if it took one, and the folder is walked when the words left could all be that
    flag's value.

    ACCEPTED LIMITS: a path word with any other variable or substitution is not resolved, a wrapper
    that changes folder (`sudo -D`) is looked through but the search is walked in the folder the command
    runs in, any other wrapper, or a shell given a script file is not looked through, a program other than a search that xargs feeds an env file name is not judged
    here, a `cd` in a `case` branch is not read, a search in the body of a heredoc is not walked, an rg `!` glob is not read,
    a brace sequence (`{a..c}`) is not expanded, past the cap a glob that no sample name matches
    (`*.py`) is allowed though a name with an env stem and a `.py` suffix would match it, a `cd` that
    only one of two chained commands needs is judged in both folders, more than ENV_SKIP_LIMIT cds that
    might not run are tried only as all run, all skipped and each skipped alone, and an ignore file other than
    the checkout's own that skips the file is not read, so such a search of a folder with an env file
    is refused.
    """
    if depth > ENV_MAX_DEPTH:
        return ENV_DEPTH_REASON, "shell strings nested past %d levels" % ENV_MAX_DEPTH
    pwd_text = any(text.strip() in ("pwd", "pwd -P", "pwd -L") for text, _ in texts[:-1])
    text_folders = _text_folders(texts, cwd, places) if places and len(places) == len(texts) else [
        _every_folder(texts, cwd)] * len(texts)
    for index, (text, _) in enumerate(texts):
        ends = []
        pieces = split_segments(text, ends)
        for number, piece in enumerate(pieces):
            fed = number > 0 and ends[number - 1] == "|"
            for part, segment in enumerate(_env_parts(piece)):
                words, position, command = _env_words(segment, walk=True)
                if command in ENV_SHELL_STRING_COMMANDS:
                    # The string is one word with its newlines kept (`_env_words`), and each ends a command in it.
                    inner = _shell_string(words, position, command)
                    inner_places = []
                    inner_texts, too_deep = (_substitutions(inner, places=inner_places) if inner
                                             else ([], False))
                    if too_deep:
                        return ENV_DEPTH_REASON, "substitutions nested past %d levels" % ENV_MAX_DEPTH
                    if inner_texts:
                        here = _folders_at(pieces, number, text_folders[index], ends)
                        refusal = _env_walk(inner_texts, here, depth + 1, inner_places)
                        if refusal[0]:
                            return refusal
                    continue
                # A find that runs a program with `-exec` hands it each name it prints: that program is the search,
                # fed as xargs feeds one (`_feed_source`). Any other command is the search itself.
                feed = None
                searches = [(words, position, command)]
                if command == "find":
                    searches, feed = _find_runners(words, position)
                for words, position, command in searches:
                    grep = command in ENV_GREP_COMMANDS + (ENV_GREP_RECURSIVE_COMMAND,)
                    if not (command in ENV_WALK_COMMANDS or grep):
                        continue
                    # Bash expands an unquoted brace list before the search sees its words.
                    words = words[:position + 1] + [e for w in words[position + 1:] for e in _brace_expand(w)]
                    skip, _, hidden, plain, no_ignore, extras = _pattern_words(
                        words, position, "grep" if grep else command)
                    if extras["lists_files"]:
                        continue
                    heres = _folders_at(pieces, number, text_folders[index], ends)
                    for moved in _env_chdirs(words, position):
                        # `env -C DIR` runs the search in DIR, which a `$` or a backtick leaves unresolved.
                        heres = [here if re.search(r"[$`]", moved)
                                 else os.path.normpath(os.path.join(here, os.path.expanduser(moved)))
                                 for here in heres]
                    via_xargs = "xargs" in (_wrapper_name(w.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
                                            for w in words[:position])
                    # Whether the search reads env files inside a folder it is given. grep does only with -r.
                    # With no hidden flag, rg reads a dotfile only when a positive glob picks it, and the walk
                    # judges each glob against the env files it finds. Every env file name is a dotfile.
                    reads_folders = ((command == ENV_GREP_RECURSIVE_COMMAND or _grep_recursive(words, position))
                                     if grep else bool(hidden or extras["globs"] or extras["types"]))
                    if grep:
                        rules, exclude_dir = _grep_globs(words, position)
                    else:
                        rules, exclude_dir = (_rg_rules(extras) if command == "rg" else []), ()
                    # Under xargs, stdin feeds xargs and not the search, and the names it reads are appended
                    # as paths, so a path or `{}` in the command does not spare the folder. Under `find -exec`
                    # the search gets each name find prints as a path of its own, as `{}`.
                    narrowing = (rules, exclude_dir, grep, no_ignore)
                    if via_xargs:
                        empty = _xargs_runs_empty(words, position)
                        sources = {here: _xargs_source(pieces, ends, number, part, here, reads_folders, narrowing,
                                                       empty) for here in heres}
                    elif feed is not None:
                        sources = {here: _feed_source("find", feed, here, reads_folders, narrowing, exec_feed=True)
                                   for here in heres}
                    else:
                        sources = {}
                    lister = "xargs is fed" if via_xargs else "find -exec is fed"
                    for here, (listed, _, _) in sources.items():
                        if listed == ENV_TOO_LARGE:
                            return (ENV_WALK_LARGE_REASON,
                                    "%s names from '%s', which is past the walk cap" % (lister, here))
                        if listed:
                            return (ENV_WALK_REASON_FED if via_xargs else ENV_WALK_REASON_EXEC,
                                    "%s the env file '%s'" % (lister, listed))
                    if not reads_folders:
                        continue
                    # Past the cap an rg type is refused: its globs name a suffix, which an env stem can carry.
                    cap_clear = (grep or not extras["types"]) and _rules_skip_env(rules)
                    for here in heres:
                        # A `<` and the word after it are stdin, not a path the search reads.
                        paths = [i for i in plain if i not in skip and i != extras["pattern"]
                                 and words[i] != "<" and words[i - 1] != "<"]
                        # Each (folder, operand as grep receives it). A folder no operand names, such as the
                        # cwd a grep with no path walks or one xargs feeds, has None (`_exclude_dir_skips`).
                        folders = []
                        head = os.path.join(here, "")
                        for i in paths:
                            word = re.sub(r"[\\\"']", "", words[i])
                            rest = None if words[i].startswith("'") else _pwd_rest(word, pwd_text)
                            if rest is not None:
                                # grep receives the cwd's full path, which the guard does not match: None walks it.
                                word, typed = "." + rest, None
                            elif re.search(r"[$`]", word):
                                continue
                            else:
                                typed = os.path.expanduser(word)
                            target = os.path.join(here, os.path.expanduser(word))
                            # A quoted glob is no glob to the shell, so it is not expanded.
                            expand = re.search(r"[*?\[]", word) and words[i] == word
                            for f in glob.glob(target) if expand else [target]:
                                # The shell hands grep each match as the glob was typed: relative unless absolute.
                                given = typed
                                if expand and typed is not None:
                                    given = f[len(head):] if not os.path.isabs(typed) and f.startswith(head) else f
                                if os.path.isdir(f) and (f, given) not in folders:
                                    folders.append((f, given))
                        if sources:
                            _, walks_here, named = sources[here]
                            folders += [(d, None) for d in named if (d, None) not in folders]
                            folders += [(here, None)] * (walks_here and (here, None) not in folders)
                        if not via_xargs and len(paths) <= extras["unknown"] and (
                                grep or not ((fed and part == 0) or "<" in words)):
                            folders += [(here, None)] * ((here, None) not in folders)
                        for folder, given in folders:
                            found = _search_walk(folder, here, rules, exclude_dir, grep, no_ignore, given)
                            if found == ENV_TOO_LARGE and cap_clear:
                                continue
                            if found == ENV_TOO_LARGE:
                                return (ENV_WALK_LARGE_REASON,
                                        "'%s' %s walks '%s', which is past the walk cap"
                                        % (command, "recursive" if grep else "with a hidden flag", folder))
                            if found:
                                return (ENV_GREP_WALK_REASON if grep else ENV_WALK_REASON,
                                        "'%s' %s walks '%s', which holds '%s'"
                                        % (command, "recursive" if grep else "with a hidden flag", folder,
                                           found))
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
            # The string is one quoted word, and it runs as a command line of its own. The shell is found
            # behind the same wrappers and subshell paren the walk looks through (`nohup bash -c`), so the
            # two readers agree on which word runs the string.
            shell_words, shell_at, shell = _env_words(segment, walk=True)
            if shell in ENV_SHELL_STRING_COMMANDS:
                inner = _shell_string(shell_words, shell_at, shell)
                refusal = env_refusal(inner) if inner else ("", "")
                if refusal[0]:
                    return refusal
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
            grep_at = _git_grep_at(words, position, command)
            patterns, glued = (
                _pattern_words(words, grep_at, "grep")[:2] if grep_at
                else _pattern_words(words, position, command)[:2]
                if command in (ENV_PATTERN_COMMANDS + ENV_SCRIPT_COMMANDS + ENV_PROGRAM_COMMANDS)
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
