"""The guard's env family: any read or write of an environment file.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import fnmatch
import re

from guard_core import (
    ASSIGNMENT, DURATION, ENV_PATTERN_COMMANDS, INTERPRETER_HEREDOC, POWERSHELL_PATTERN_COMMANDS,
    REDIRECT, SHELL_HEREDOC, SMART_QUOTES, SMART_SINGLE, closes_quote, smart_quote_span, token_start,
    TIMEOUT_FLAGS_BARE, TIMEOUT_FLAGS_WITH_VALUE, _split_heredocs, _without_message_values,
    is_powershell, norm, split_segments,
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
# A head holds no space, except in a quote that sits inside the word (`C:\"My Dir"\.env`) or in a
# quoted word that is a rooted path from its first character (`"C:\My Dir\.env"`). Prose before the
# backslash (`"see C:\MyDir\.env"`) and a regex (`"\d+ \.env"`) have no root, so they stay text.
# In PowerShell text every other argument is a path (`path_arg`): none of this applies to it.
#
# The residue, stated rather than hidden: a RELATIVE Windows path whose every segment after the
# first begins with a dot, such as `foo\.config\.env`, is no longer read as a path. Text alone
# cannot tell it from a regex. The absolute form and the forward-slash form are unaffected.
ENV_PATH_PREFIX = re.compile(r"^(\.{1,2}|~|[A-Za-z]:|\S*(/|\\(?![.\\]))\S*)$")
ENV_QUOTED_ROOT = re.compile(r"^([A-Za-z]:[\\/]|\\\\|~[\\/]|\.{1,2}[\\/]|/)")
ENV_QUOTED_SPAN = re.compile(r"\"[^\"]*\"|'[^']*'")

# In PowerShell text an argument is a path unless it is a pattern or text. A path's backslash is a
# separator. A pattern's is a regex escape, and a text command's arguments are text. The pattern
# commands are POWERSHELL_PATTERN_COMMANDS, apart from ENV_PATTERN_COMMANDS, since PowerShell names
# its pattern flag `-Pattern`, which `_pattern_words` would misread as the short flag `-e`. Its
# print cmdlets and `throw` are not `echo` or `printf`. Lower case.
ENV_POWERSHELL_TEXT_COMMANDS = (
    "write-host", "write-output", "write-error", "write-warning", "write-verbose", "write-debug",
    "write-information", "throw")
# A quoted word that holds a space is text, such as an Add-Content value, unless it is the command's
# path argument: its first plain word, or the value of a `-Path`, `-LiteralPath` or `-FilePath`
# flag. So `Get-Content "My Dir\.env"` reads a path, and `Add-Content log "see C:\app\.env"` writes
# text. A rooted quoted path (`"C:\My Dir\.env"`) stays a path anywhere (ENV_QUOTED_ROOT).
ENV_PATH_FLAG = re.compile(r"-\w*path", re.IGNORECASE)
# A .NET regex call: every word from it to the segment end is a regex argument.
ENV_REGEX_CALL = re.compile(r"\[(?:system\.text\.regularexpressions\.)?regex\]::", re.IGNORECASE)
# `-Path` and the like take a value that is never the pattern.
ENV_SELECT_STRING_VALUES = (
    "-path", "-literalpath", "-include", "-exclude", "-encoding", "-context", "-inputobject")
# The operators whose right-hand word is a regex.
ENV_REGEX_OPERATOR = re.compile(r"-[ic]?(not)?match|-[ic]?replace|-[ic]?split", re.IGNORECASE)

# Runners that read the file into their own environment and echo nothing. `npm` and `npx` reach the
# flag through node, so `node --env-file=.env <npm-cli.js> run x` is the npm form.
ENV_LOADER_COMMANDS = (
    "node", "node.exe", "npm", "npm.cmd", "npm-cli.js", "npx", "npx.cmd", "npx-cli.js",
    "pnpm", "pnpm.cmd", "bun", "bun.exe", "deno", "deno.exe", "uv", "uv.exe",
    "docker", "docker.exe", "docker-compose", "docker-compose.exe", "podman", "podman.exe",
)
ENV_LOADER_FLAGS = ("--env-file", "--env-file-if-exists")

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
# rg only: in ag `-t` is a switch, so a `t` in the shared letters would swallow a path. The word
# after rg `-t` or `-T` is a type name and no path, so it is skipped.
ENV_BOOLEAN_F_COMMANDS = ("ag", "ack")
# `ag -G` takes a regex that picks the files to search, and `ag -p` a file of ignore patterns. Each
# value is judged as a path. In grep `-G` is a plain switch, so the letters are not shared.
ENV_VALUE_SHORT_BY_COMMAND = {"rg": "tT", "ag": "Gp"}
ENV_TYPE_SHORT_BY_COMMAND = {"rg": "tT"}
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
# The flag may close a short cluster (`-am`, `-sm`), and the value may be a PowerShell here-string.
ENV_MESSAGE_COMMAND = re.compile(r"\s*(git\s+(commit|tag)|gh\s+pr\s+create)\b")
ENV_MESSAGE_FLAG = r"(?<![\w-])(?:-[A-Za-z]*m|--message|--title|--body)(?:=|\s+)"
ENV_MESSAGE_ARG = re.compile(
    r"(?P<flag>" + ENV_MESSAGE_FLAG + r")"
    r"""(?P<value>@(?P<here>["'])\r?\n[\s\S]*?\n(?P=here)@|"(?:[^"\\]|\\.)*"|'[^']*')""")


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
                   groups: bool = False):
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
    `groups` reads a PowerShell `( ... )` or `@( ... )` at a token start as a substitution too: it
    runs a command of its own, and its output is an argument of the command around it.
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
        if not re.search(ENV_MESSAGE_FLAG + "$", "".join(pieces[-12:])):
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
        elif cmd[i:i + 2] == "$(" or (quote == "" and cmd[i:i + 2] in ("<(", ">(")) or (
                groups and quote == "" and char == "(" and (token_start(cmd, i) or cmd[i - 1] == "@")):
            if len(stack) + depth > ENV_MAX_DEPTH:
                return [], True
            message = quote == '"' and frame[4]
            pieces.append("x")
            stack.append([[], "", 0, message, False])
            i += 1 if char == "(" else 2
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


def _joined_spaces(word: str, path_arg: bool = False) -> str:
    """Write each space that belongs to a quoted path as NUL, so the head test, which reads `\\S*`,
    keeps the path in one word. Those are the spaces inside a quote within the word, and every space
    of a quoted word that is a rooted path from its first character, or any quoted word that is a
    path argument. A quoted word with prose or a regex before the backslash keeps its spaces, and
    the head test then reads it as text."""
    if len(word) > 1 and word[0] in "\"'" and word[-1] == word[0] and word.count(word[0]) == 2:
        inner = word[1:-1]
        return inner.replace(" ", "\0") if path_arg or ENV_QUOTED_ROOT.match(inner) else inner
    return ENV_QUOTED_SPAN.sub(lambda m: m.group(0).replace(" ", "\0"), word)


def env_reference(word: str, path_arg: bool = False) -> str:
    """Return the environment file that one shell word names as a path, else ''.

    `path_arg` is set for a PowerShell argument that is a path: any one but a pattern or text (see
    ENV_POWERSHELL_TEXT_COMMANDS). There a backslash is always a separator and a quoted word is
    one path, so `sub\\.env` and `"My Dir\\.env"` name the file. In a pattern a backslash may be a
    regex escape.

    A reference is the WHOLE BASENAME of the word and never a substring of it. That one property
    keeps `process.env`, `import.meta.env` and `dotenv` out, because in none of them does `.env`
    end a path segment.

    The word is normalized first, the way the shell reads it: inner quotes go, so `.e""nv` and
    `'.e'nv` are `.env`, and so does a backslash that is not an escaped dot, so `.e\\nv` is. A
    glob that starts with a dot and could match a name, such as `.en?` or `.env*`, is the name.
    """
    word = re.sub(r"[\"'`]", "", _joined_spaces(word, path_arg)).strip("()")
    for separator in ("/", "\\"):
        head, found, tail = word.rpartition(separator)
        if not found:
            continue
        if separator == "\\" and not path_arg and not ENV_PATH_PREFIX.match(head):
            break  # `process\.env` is an escaped dot, not a Windows separator
        # A file inside an env folder (`.envs/x`, `.envs\x`) is a read of that folder.
        folders = re.split(r"[\\/]" if path_arg or separator == "\\" else "/", head)
        folder = next((part for part in folders if names_env_file(part.replace("\0", " "))), "")
        if folder:
            return folder.replace("\0", " ")
        word = tail
        break
    word = re.sub(r"\\(?!\.)", "", word.replace("\0", " "))
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
    cmd = _plain_escaped_quotes(cmd)
    texts, too_deep = _substitutions(cmd, powershell=is_powershell(cmd), heredoc=heredoc,
                                     groups=is_powershell(cmd))
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
            if name in ENV_PATTERN_LONG:
                given = True
                skip.update({i} if attached else {i + 1})
            elif name in ENV_FILE_LONG:
                given = True
            elif name in ENV_EXCLUDE_LONG:
                skip.update({i} if attached else {i + 1})
            i += 1 if attached or name not in ENV_PATTERN_LONG + ENV_FILE_LONG + ENV_VALUE_LONG else 2
            continue
        step = 1
        for k, letter in enumerate(word[1:], 1):
            rest = word[k + 1:]
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
                if not rest and letter in ENV_TYPE_SHORT_BY_COMMAND.get(command, ""):
                    skip.add(i + 1)  # a file type name, never a path
                step = 1 if rest else 2
                break
        i += step
    if program and not given and plain:
        # A yq subcommand leads the program, and is no path either. The program is skipped only
        # when a file word follows it: a lone word reads stdin or is the file, so it is judged.
        lead = 1 if command == "yq" and words[plain[0]] in ENV_YQ_SUBCOMMANDS else 0
        if len(plain) > lead + 1:
            skip.update(plain[:lead + 1])
    elif not given and plain:
        skip.add(plain[0])
    return skip, glued


def _powershell_regex_words(words, position: int, command: str):
    """The indexes of the words in a PowerShell segment that are a regex and no path: the word
    after a `-match`, `-replace` or `-split` operator, each word from a `[regex]::` call on, a
    `git grep` pattern, a `git log --grep` value, the first plain word of `findstr`, and a
    Select-String pattern (`-Pattern x`, `-Pattern:x`, or the first plain word when no flag gives
    it)."""
    found = {i for i in range(1, len(words)) if ENV_REGEX_OPERATOR.fullmatch(words[i - 1])}
    call = next((i for i, word in enumerate(words) if ENV_REGEX_CALL.search(word)), len(words))
    found |= set(range(call, len(words)))
    name = command.lower()
    subcommand = words[position + 1:position + 2]
    if name == "git" and subcommand == ["grep"]:
        found |= _pattern_words(words, position + 1, "grep")[0]
    elif name == "git" and subcommand == ["log"]:
        for i in range(position + 2, len(words)):
            flag, glued, _ = words[i].partition("=")
            if flag == "--grep":
                found.add(i if glued else i + 1)
    elif name == "findstr":   # its flags start with `/`, and its first plain word is the pattern
        found |= set(next(([i] for i in range(position + 1, len(words))
                           if not words[i].startswith("/") and not REDIRECT.fullmatch(words[i])
                           and not REDIRECT.fullmatch(words[i - 1])), []))
    elif name in POWERSHELL_PATTERN_COMMANDS:
        plain, explicit, i = [], False, position + 1
        while i < len(words):
            word = words[i]
            if REDIRECT.fullmatch(word):
                i += 2
                continue
            flag, colon, _ = word.partition(":")
            low = flag.lower()
            if len(word) > 1 and word.startswith("-"):
                if len(low) >= 5 and "-pattern".startswith(low):
                    explicit = True
                    found.add(i if colon else i + 1)
                    i += 1
                elif not colon and len(low) >= 3 and any(
                        v.startswith(low) for v in ENV_SELECT_STRING_VALUES):
                    i += 2
                else:
                    i += 1
                continue
            plain.append(i)
            i += 1
        if not explicit and plain:
            found.add(plain[0])
    return found


def _powershell_text_words(words, position: int, text_command: bool):
    """The indexes of the quoted words in a PowerShell segment that hold a space and are text, not
    the command's path argument (ENV_PATH_FLAG). A text command has no path argument. A redirect's
    target is never text."""
    slot = set()
    if not text_command:
        plain = [i for i in range(position + 1, len(words))
                 if not words[i].startswith("-") and not REDIRECT.fullmatch(words[i])
                 and not REDIRECT.fullmatch(words[i - 1])]
        slot = set(plain[:1]) | {i for i in range(position + 1, len(words))
                                 if ENV_PATH_FLAG.fullmatch(words[i - 1])}
    return {i for i in range(position + 1, len(words))
            if i not in slot and not REDIRECT.fullmatch(words[i - 1]) and " " in words[i]
            and (words[i][:2] in ('@"', "@'") or len(words[i]) > 1 and words[i][0] in "\"'"
                 and words[i][-1] == words[i][0])}


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


def _quoted_words(segment: str):
    """Split a segment into words the way the shell does: a quoted string with a space is ONE word.
    The redirects are spaced into words of their own outside the quotes only. A quote with no
    closing mate is a plain character, so a lone quote in text still leaves the words after it. In
    PowerShell a smart quote opens a string too."""
    chunks, plain, i, n = [], [], 0, len(segment)

    def flush():
        text = "".join(plain)
        chunks.append(READ_REDIRECT.sub(" < ", REDIRECT.sub(r" \1 ", text)))
        plain.clear()

    while i < n:
        char = segment[i]
        if char == "\\" and i + 1 < n and not is_powershell(segment):   # PowerShell: a path character
            plain.append(segment[i:i + 2])
            i += 2
            continue
        span_end = smart_quote_span(segment, i) if char in SMART_QUOTES else 0
        if span_end:   # PowerShell: the marks become ASCII ones, so the word reads as any quoted path
            flush()
            ascii_mark = "'" if char in SMART_SINGLE else '"'
            chunks.append(re.sub(r"\s", "\0", ascii_mark + segment[i + 1:span_end - 1] + ascii_mark))
            i = span_end
            continue
        if char in "'\"":
            powershell = is_powershell(segment)
            j = i + 1
            while j < n and not closes_quote(segment[j], char, powershell):
                j += 2 if char == '"' and segment[j] == "\\" and not powershell else 1
            if j < n:   # a smart close becomes the straight mark that opened the string
                flush()
                chunks.append(re.sub(r"\s", "\0", char + segment[i + 1:j] + char))
                i = j + 1
                continue
        plain.append(char)
        i += 1
    flush()
    return [w.replace("\0", " ") for w in "".join(chunks).split()]


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


def _env_flat(cmd: str, text_ok: bool = False):
    """The segment rules over one text whose substitutions are already cut out."""
    ends = []
    pieces = split_segments(cmd, ends)
    for piece, end in zip(pieces, ends):
        parts = _env_parts(piece)
        for number, segment in enumerate(parts):
            words, position, command = _env_words(segment)
            if not words:
                continue
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
            # In PowerShell a text command's words are text unless it pipes onward, and then a word
            # with no space may be a path the next command reads.
            powershell = is_powershell(segment)
            text_command = command.lower() in ENV_TEXT_COMMANDS + ENV_POWERSHELL_TEXT_COMMANDS
            not_paths = set()
            if powershell and text_command and not piped:
                not_paths = {i for i in range(len(words)) if not (i and REDIRECT.fullmatch(words[i - 1]))}
            elif powershell:
                not_paths = (_powershell_regex_words(words, position, command)
                             | _powershell_text_words(words, position, text_command))
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
                named = env_reference(glued[index] if index in glued else rest if assigned else word,
                                      powershell and index not in not_paths)
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
