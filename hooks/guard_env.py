"""The guard's env family: any read or write of an environment file.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import fnmatch
import glob
import os
import re
import warnings

from guard_core import (
    ASSIGNMENT, DURATION, ENV_PATTERN_COMMANDS, INTERPRETER_HEREDOC, REDIRECT, SHELL_HEREDOC,
    POWERSHELL_CALL, TIMEOUT_FLAGS_BARE, TIMEOUT_FLAGS_WITH_VALUE, _git, _split_heredocs,
    _without_message_values, is_powershell, norm, segment_tokens, split_segments,
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
# A second copy of guard_frozen.py's `_NODE_EVAL_FLAG`, kept on purpose: this module reads the
# `=` forms and the open rewrite of that one is not ours to touch.
ENV_INLINE_FLAG = re.compile(r"^(?:-[ep]{1,2}|--eval|--print)(?:=.*)?$")

# Commands that ask whether the file is THERE. They read no contents.
ENV_EXISTENCE_COMMANDS = ("ls", "test", "[", "[[")

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


def _substitutions(cmd: str, depth: int = 0, powershell: bool = False, heredoc: bool = False):
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
    """
    escape = "`" if powershell else "\\"
    if depth > ENV_MAX_DEPTH:
        return [], True
    done = []
    # a frame: [pieces of its text, open quote, paren depth, it is a message value, its open
    # quote holds a message value]
    stack = [[[], "", 0, False, False]]
    i, n = 0, len(cmd)

    def close():
        pieces, _, _, message, _ = stack.pop()
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
            inner, deep = _substitutions(cmd[i + 1:j].replace("\\`", "`"), depth + 1)
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
            stack.append([[], "", 0, message, False])
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
#   - `find -name '.env*'` refuses, and `ls` or `git ls-files` is the way to list;
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
    refusal = _env_walk(texts, cwd) if cwd else ("", "")
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
    PATTERN or a program, never a path, {index: the file name glued to a flag word}, whether a
    hidden flag is set, the indexes of the positional words, whether a flag turns the ignore rules off).

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
            unrestricted += name == ENV_UNRESTRICTED_LONG
            no_ignore = no_ignore or name.startswith(ENV_NO_IGNORE_LONG_PREFIX) or (
                command == "ag" and name in ENV_AG_NO_IGNORE_LONG)
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
                if not rest and letter in ENV_NO_PATH_SHORT_BY_COMMAND.get(command, ""):
                    skip.add(i + 1)  # a file type name or an ag file regex, never a path
                type_not = type_not or (command == "rg" and letter in ENV_RG_TYPE_NOT_SHORT)
                step = 1 if rest else 2
                break
        i += step
    hidden = hidden or unrestricted >= ENV_UNRESTRICTED_FOR_HIDDEN.get(command, 2)
    if program and not given and plain:
        # A yq subcommand leads the program, and is no path either. The program is skipped only
        # when a file word follows it: a lone word reads stdin or is the file, so it is judged.
        lead = 1 if command == "yq" and words[plain[0]] in ENV_YQ_SUBCOMMANDS else 0
        if len(plain) > lead + 1:
            skip.update(plain[:lead + 1])
    elif not given and plain and not (hidden and type_not):
        skip.add(plain[0])
    return skip, glued, hidden, plain, no_ignore or unrestricted > 0


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


def _env_words(segment: str):
    """Return (words, command word) of one segment, redirects spaced into words of their own."""
    words = _quoted_words(_blank_messages(segment))
    # The command is the first word that is not a `VAR=value` assignment.
    # A `(` glued to the first assignment is a subshell paren, not part of the name.
    if words and words[0][:1] == "(" and ASSIGNMENT.match(words[0][1:]):
        words[0] = words[0][1:]
    position = 0
    while position < len(words) and ASSIGNMENT.match(words[position]):
        position = _assignment_end(words, position)
    # Look through exactly these wrapper shapes, each by its exact form, so a flag value of some
    # other wrapper (`env -u ls cat .env`) can never pose as the command word.
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
        else:
            break
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
ENV_GREP_VALUE_SHORT = ENV_VALUE_SHORT + "ef"
ENV_WALK_LIMIT = 50000
ENV_TOO_LARGE = "<too large>"
ENV_WALK_REASON = ("this command would search a folder that holds an environment file, and a "
                   "hidden flag makes it read dotfiles")
ENV_WALK_LARGE_REASON = (
    "this command would search a folder too large to check, so it cannot be shown clean of "
    "environment files. Remedy: name a smaller folder")
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


def _env_file_in(folder: str, include=(), exclude=(), exclude_dir=(), ignored=frozenset()) -> str:
    """The first env file under `folder`, or ENV_TOO_LARGE past ENV_WALK_LIMIT entries, else ''. A symlink is not followed, as rg and ag do not.
    `.git` holds no env file and is skipped. The grep globs narrow it: a file is read only when it
    matches an `include` glob (when any is given) and no `exclude` glob, and a folder that matches an
    `exclude_dir` glob is not entered. `ignored` is `_ignored_paths`: a file or folder in it is skipped."""
    seen = 0
    for top, dirs, files in os.walk(folder):
        relative = os.path.relpath(top, folder).replace(os.sep, "/")
        prefix = "" if relative == "." else relative + "/"
        dirs[:] = [d for d in dirs if d != ".git"
                   and not any(fnmatch.fnmatchcase(d, g) for g in exclude_dir)
                   and prefix + d + "/" not in ignored]
        seen += len(dirs) + len(files)
        for name in files:
            if (names_env_file(name)
                    and (not include or any(fnmatch.fnmatchcase(name, g) for g in include))
                    and not any(fnmatch.fnmatchcase(name, g) for g in exclude)
                    and prefix + name not in ignored):
                return os.path.join(top, name)
        if seen > ENV_WALK_LIMIT:
            return ENV_TOO_LARGE
    return ""


def _grep_recursive(words, position: int) -> bool:
    """True when a grep command line asks for a recursive search: `-r`, `-R` (alone or in a
    cluster such as `-rn`), `-d recurse`, or a long form. A cluster ends at a letter that takes a
    value, as in `_pattern_words`."""
    i = position + 1
    while i < len(words):
        word = words[i]
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
    """The (include, exclude, exclude-dir) globs of a grep command line, as the shell passes them."""
    found = {"--include": [], "--exclude": [], "--exclude-dir": []}
    for i in range(position + 1, len(words)):
        name, attached, value = words[i].partition("=")
        if name in found:
            if not attached and i + 1 < len(words):
                value = words[i + 1]
            found[name].append(re.sub(r"[\"']", "", value))
    return found["--include"], found["--exclude"], found["--exclude-dir"]


def _env_walk(texts, cwd: str):
    """Return (reason, log) when `rg` or `ag` with a hidden flag, or a recursive grep, walks a
    folder that holds an env file on disk. The folder is each path word that is a folder, or `cwd`
    when no path is named. For rg and ag no pipe or `<` may feed the search either; a recursive
    grep walks `cwd` whatever feeds it. `rg --files` lists names and reads no contents. A grep
    `--include`, `--exclude` or `--exclude-dir` glob that skips the env file clears it.

    A glob word is expanded against `cwd` as the shell does (no dotfile). For rg and ag with no flag
    that turns the ignore rules off, a file or folder that the checkout ignores is not read, so it is
    skipped (`_ignored_paths`, one call, made only when the first walk found a file or ran past the cap).

    ACCEPTED LIMITS: a word that holds a variable or a substitution is not resolved, a `cd` earlier
    in the command is not followed (a path reads against `cwd`), a search in the body of a heredoc is
    not walked, and a `-g '!...'` or an ignore file other than the checkout's own that skips the file
    is not read, so such a search of a folder with an env file is refused.
    """
    for text, _ in texts:
        ends = []
        for number, piece in enumerate(split_segments(text, ends)):
            fed = number > 0 and ends[number - 1] == "|"
            for part, segment in enumerate(_env_parts(piece)):
                words, position, command = _env_words(segment)
                grep = command in ENV_GREP_COMMANDS + (ENV_GREP_RECURSIVE_COMMAND,)
                if not (command in ENV_WALK_COMMANDS or grep) or "--files" in words:
                    continue
                skip, _, hidden, plain, no_ignore = _pattern_words(
                    words, position, "grep" if grep else command)
                if grep:
                    if command != ENV_GREP_RECURSIVE_COMMAND and not _grep_recursive(words, position):
                        continue
                elif not hidden:
                    continue
                paths = [re.sub(r"[\\\"']", "", words[i]) for i in plain if i not in skip]
                folders = []
                for i in (i for i in plain if i not in skip):
                    word = re.sub(r"[\\\"']", "", words[i])
                    if re.search(r"[$`]", word):
                        continue
                    target = os.path.join(cwd, os.path.expanduser(word))
                    # A quoted glob is no glob to the shell, so it is not expanded.
                    expand = re.search(r"[*?\[]", word) and words[i] == word
                    folders += [f for f in (glob.glob(target) if expand else [target])
                                if os.path.isdir(f) and f not in folders]
                if not paths and (grep or not ((fed and part == 0) or "<" in words)):
                    folders = [cwd]
                globs = _grep_globs(words, position) if grep else ((), (), ())
                for folder in folders:
                    found = _env_file_in(folder, *globs)
                    if found and not grep and not no_ignore:
                        found = _env_file_in(folder, *globs, ignored=_ignored_paths(folder))
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


def _runner_inline_code(words, position: int, command: str, stdin_fed: bool = False) -> bool:
    """True when a node, bun or deno command runs inline code: an eval or print flag, a stdin
    script (`-`, or no script word with stdin fed by a pipe or a heredoc), or deno's `eval`.
    The option words after the runner are read up to the first positional word or `--`, so the
    `-e` of a script's own arguments (`node app.js -e x`) is not inline code."""
    if command.lower() not in ENV_INLINE_RUNNERS:
        return False
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
        elif ENV_INLINE_FLAG.match(word) or word == "-":
            return True
        elif word.startswith("-"):
            i += 1
        else:
            if command.lower().startswith("deno") and word == "eval":
                return True
            script = True
            break
    return fed and not script


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
                loaded = flag in ENV_LOADER_FLAGS or previous in ENV_LOADER_FLAGS
                if loaded and command.lower() in ENV_LOADER_COMMANDS:
                    if _runner_inline_code(words, position, command, stdin_piped):
                        return (ENV_INLINE_REASON,
                                "'%s' runs inline code with '%s' loaded" % (command, named))
                    continue  # a runner loading it into its own environment prints nothing
                if loaded:
                    return (ENV_RUNNER_REASON,
                            "only a runner may be handed '%s' with %s, and '%s' is not one" % (
                                named, flag or previous, command))
                if names_only or text_to_file:
                    continue  # the name is data, and no contents are read or written
                if command in ENV_EXISTENCE_COMMANDS:
                    continue  # asking whether the file is there reads none of it
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
