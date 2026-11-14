"""The guard's push-delete family: a forced push and a wide delete.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import bisect
import os
import re
import stat

import guard_core
from guard_core import (
    CMD_EXE_NAMES, GIT_OPT_WITH_VALUE, _absolute, _segment_cd_move, _segment_cd_target,
    _segment_git_c_target, shell_abs, CONTRACTION, quote_advance, _git_subcommand_index,
    _SHELLS, _strip_heredoc_bodies_unconditionally, bare_words, basename, command_indexes, inner_commands,
    is_powershell, norm, resolve_command, segment_tokens, split_segments,
)


# `-o` is read in the short-flag loop, where its value may be glued on.
PUSH_VALUE_OPTS = {"--receive-pack", "--exec", "--push-option"}
DEFAULT_BRANCH_FALLBACK = ("main", "master")
# Rule push-agent-branch. push-stray-branch is silent on a branch with no upstream, and an agent-worktree
# branch (`claude/agent-<hex>`) has none. The three shapes the tools name a worktree branch by, with 8 or more
# lowercase hex characters after the prefix. Cost: a string match, and a bare push reads one more config key in
# the spawn it already makes.
AGENT_BRANCH = re.compile(r"(?:claude/|worktree-)?agent-[0-9a-f]{8,}")


def _push_config(cwd: str, key: str, overrides=None):
    """The config value, '' when the key is unset, None when git cannot answer.

    A `git -c key=value` override on the push call wins over the repository's own config.
    """
    if overrides and key.lower() in overrides:
        return overrides[key.lower()]
    answer = guard_core._git(cwd, "config", "--get", key) if cwd else None
    if answer is None or answer.returncode not in (0, 1):
        return None
    return answer.stdout.strip()


def _push_current_branch(cwd: str):
    answer = guard_core._git(cwd, "symbolic-ref", "-q", "HEAD") if cwd else None
    if answer is None or answer.returncode != 0 or not answer.stdout.strip():
        return None
    # no `--short`: it prints `heads/<name>` when a tag has the branch's name
    return answer.stdout.strip().removeprefix("refs/heads/")


def _push_bare_destination(cwd: str, overrides=None):
    """Where a push with no refspec goes, read through push.default, else None (unknown).

    `simple` and `current` push the current branch to its own name. `upstream` pushes to the
    branch's upstream ref. `matching`, `nothing`, an unset upstream or an unreadable config is
    unknown, and unknown is never safe.
    """
    current = _push_current_branch(cwd)
    mode = _push_config(cwd, "push.default", overrides)
    if current is None or mode is None:
        return None
    if mode in ("", "simple", "current"):
        return current
    if mode in ("upstream", "tracking"):
        merge = _push_config(cwd, "branch." + current + ".merge", overrides)
        return merge.removeprefix("refs/heads/") if merge else None
    return None


def _push_default_branches(cwd: str, remote: str):
    """The default branch names, or None when git cannot be read at all.

    `guard_core.read_default_base` answers for the PUSHED remote. A
    resolved `<remote>/HEAD` names the one branch. Any other answer (HEAD unset, dangling, or a
    read that did not answer) protects main AND master, plus the name HEAD holds. No readable
    repository is unknown, and unknown is never safe.
    """
    if not cwd or not os.path.isdir(cwd):
        return None
    repo = guard_core._git(cwd, "rev-parse", "--git-dir")
    if repo is None or repo.returncode != 0:
        return None
    base, head = guard_core.read_default_base(cwd, remote)
    named = (head[len(remote) + 1:],) if head else ()
    if base is not None and base == head:
        return named
    return DEFAULT_BRANCH_FALLBACK + named


# A quoted run with a space in it is text (a commit message, an echo), never a push. A quoted
# single word stays: it is a refspec or a remote, and the shell would unquote it.
PUSH_QUOTED = re.compile(r"\"[^\"\s]*\s[^\"]*\"|'[^'\s]*\s[^']*'")


def push_target(segment: str, cmd: str, cwd: str):
    """(directory, config overrides) a `git push` in this segment runs against.

    The directory is the segment's own `git -C <dir>`, else the command's last `cd`, else the
    session's cwd. A segment that cannot be read gives ('', {}): a directory that does not
    exist, which the verdict reads as unknown, and unknown asks.
    """
    tokens = segment_tokens(segment)
    if tokens is None:
        return "", {}
    # The last `cd` only: `_run_dir` would also take the first `git -C` of ANY segment.
    run_dir = cwd
    for other in split_segments(_strip_heredoc_bodies_unconditionally(cmd)):
        words = segment_tokens(other)
        cd = _segment_cd_target(words) if words else None
        if cd is not None:
            run_dir = _absolute(cd, run_dir)
    git_c = _segment_git_c_target(tokens)
    where = _absolute(git_c, run_dir) if git_c is not None else run_dir
    overrides = {}
    index = resolve_command(tokens)
    cursor = index + 1 if index is not None else len(tokens)
    while cursor < len(tokens) and tokens[cursor].startswith("-"):
        if tokens[cursor] == "-c" and cursor + 1 < len(tokens):
            key, _, value = tokens[cursor + 1].partition("=")
            overrides[key.lower()] = value
        cursor += 2 if tokens[cursor] in GIT_OPT_WITH_VALUE else 1
    return where, overrides


def _span_end(text: str, start: int, escapes: bool) -> int:
    """The index of the quote that closes the one at `start`, or -1 when none does. Inside double
    quotes (and `$'..'`) a backslash escapes the next character, so `\\"` closes nothing."""
    quote, index = text[start], start + 1
    while index < len(text):
        if escapes and text[index] == "\\":
            index += 2
        elif text[index] == quote:
            return index
        else:
            index += 1
    return -1


# The outer call hands its quoted script to a shell that runs it: `bash -c "..."`, `eval "..."`,
# `ssh host "..."`.
SCRIPT_RUNNER = re.compile(
    r"(?:^|[\s;&|(])(?:(?:(?:ba|z|da|k)?sh\s+(?:-\w+\s+)*-\w*c)|eval|ssh(?:\s+[^\s;&|]+)*)\s*$")
# ... or to an interpreter that runs it: `python3 -c "..."`, `node -e "..."`, `perl -e "..."`,
# `php -r "..."`, `deno eval -A "..."`. Deno's flags sit between `eval` and the script: `-A`,
# `--allow-run=git`, and a flag with its value as the next word (`--ext ts`, `--config x.json`);
# SCRIPT_RUNNER's `eval` reads only the bare `deno eval`. A flag starts with `-` and a value word
# never does, so each word has one parse and a failed match stays linear. The interpreter may be
# named by a path (`.venv/bin/python`, `/usr/bin/python3`), by a quoted path with a space in it, or by
# a variable (`$PYTHON`, `${VENV_PYTHON}`), and python takes `-W` and `-X` with a value word ahead of
# `-c` (`python3 -W ignore -c`). The word starts at a word start; `_interpreter` then checks that it is
# the command (see there). `php -r` and `deno eval` are checked against their own name there too.
_INTERPRETER_NAME = r"python[\d.]*|pypy[\d.]*|node(?:js)?|ruby|perl|php|deno|\$\{?\w*PYTHON\w*\}?"
INTERPRETER_RUNNER = re.compile(
    r"(?<![^\s;&|(`])(?:\"(?:[^\"]*/)?(?P<double>" + _INTERPRETER_NAME + r")\""
    r"|'(?:[^']*/)?(?P<single>" + _INTERPRETER_NAME + r")'"
    r"|(?:[^\s;&|()\"'`]*/)?(?P<bare>" + _INTERPRETER_NAME + r"))"
    r"(?:\s+(?:-\w+\s+|-[WX]\s+[^\s\"'-]\S*\s+)*-\w*(?P<flag>[cer])"
    r"|\s+(?:-\w+\s+)*(?P<eval>eval)(?:\s+-{1,2}\w[\w-]*(?:=\S*)?(?:\s+[^\s\"'-]\S*)?)*)\s*$")
# Where a command starts: the text after the last of these is the command's own words.
_COMMAND_START = re.compile(r"[;&|(\n`][^;&|(\n`]*$")
# How far back a runner is read ahead of a quote, so a long segment is read in linear time.
RUNNER_REACH = 512
# The text search tools: an interpreter-named word in their arguments is a path or a pattern.
TEXT_SEARCH_TOOLS = {"grep", "egrep", "fgrep", "zgrep", "rg", "ag", "ack", "ugrep"}
# The text between two strings of one argv call. Each part starts with its own character, so a
# failed fullmatch takes linear time.
ARGV_GAP = re.compile(r"[\s,]*(?:\{\s*args\s*:\s*\[[\s,]*)?")
# One argument as one shell word: each character the shell or shlex splits on is
# backslash-escaped, so an argument with a space stays one word. The word holds no quote:
# PUSH_QUOTED reads raw quotes and ignores backslashes, so a quote here could pair with a
# quote in a neighbouring word and blank the words between.
ARGV_UNSAFE = re.compile(r"[^\w@%+=:,./-]")
# The names of a call that runs its string argument as a command, even inside a print: the one list
# of run calls. RUN_NAME_ANYWHERE is read in any quoted text. RUN_NAME adds the bare names a script
# imports (`check_output`, `shell_exec`, `spawn`), which in a commit message or an echo are words.
RUN_NAME_ANYWHERE = (r"\bos\.(?:system|popen|exec\w*|spawn\w*)|\bsubprocess\.\w+|\bPopen|\bexec\w*|\bsystem"
                     r"|\bpopen")
RUN_NAME = RUN_NAME_ANYWHERE + r"|\bcheck_(?:output|call)|\bshell_exec|\bspawn\w*"
RUN_NAME_END = re.compile(r"(?:" + RUN_NAME + r")$")
RUN_CALL = r"(?:" + RUN_NAME + r")\s*\(\s*"
CALL_RUNNER = re.compile(RUN_CALL + r"\[?\s*$")
CALL_RUNNER_ANYWHERE = re.compile(r"(?:" + RUN_NAME_ANYWHERE + r")\s*\(\s*\[?\s*$")
# An argv call: `new Deno.Command("git", {args: ["push", "-f"]})` and a run call with a list
# (`subprocess.run(["git", "push", "-f"])`) name the program and its arguments as separate strings,
# so the pairs of one call are read as one command line.
ARGV_CALL = re.compile(r"\bDeno\.Command\s*\(\s*$|" + RUN_CALL + r"\[\s*$")
# The printers: the one place that names the calls and commands that show their string and run
# nothing. A pair inside a runner script is a command unless a printer holds it.
PRINT_NAME = (r"print\w*|console\.\w+|puts|say|logger\.\w+|System\.out\.print\w*"
              r"|sys\.std(?:out|err)\.write|Write-(?:Host|Output)")
PRINT_CALL_NAME = re.compile(r"\b(?:" + PRINT_NAME + r")$")
PRINT_COMMAND = re.compile(r"[\s\"'(]*(?:(?:sudo|command|builtin)\s+)?(?:echo|printf|print|puts)\b")
# The call name that ends the text ahead of an open `(`. Words that take a `(` and call nothing
# (`if (`, `return (`) are no call.
CALL_NAME = re.compile(r"([\w.-]+)\s*$")
NOT_A_CALL = {"if", "while", "for", "switch", "return", "and", "or", "not", "in", "is", "else", "elif",
              "await", "yield", "do"}
STATEMENT_END = re.compile(r"[;&|\n]")
# What a pipe feeds: a shell, which runs the printed text as a script.
PIPE_INTO_SHELL = re.compile(
    r"\s*(?:(?:sudo|exec|env)\s+)?(?:[^\s|;&]*/)?(?:" + _SHELLS + r")(?![\w.-])")


def _argv_word(arg: str) -> str:
    """One argument as one word of a command line (see ARGV_UNSAFE). Its quote characters are
    dropped, as _push_parse drops them from every push argument. An argument left empty is an
    escaped space, since the shell has no empty word without quotes. This is a bandaid: the push
    reader sees a one-space word, which keeps its place, so the words after it keep theirs."""
    arg = arg.replace("'", "").replace('"', "")
    escaped = ARGV_UNSAFE.sub(lambda m: "\\ " if m.group() == "\n" else "\\" + m.group(), arg)
    return escaped or "\\ "


def _interpreter(text: str, end: int = -1):
    """The name of the interpreter whose script starts at `end` in `text` (`python3`, `node`, `$PYTHON`),
    or None when no interpreter runner ends there. The interpreter is a runner where the shell runs it,
    after any assignments, keywords and wrappers that resolve_command skips (`FOO=1 sudo -u bob python3`).
    Words the shell cannot split are read as a runner."""
    end = len(text) if end < 0 else end
    reach = max(0, end - RUNNER_REACH)
    match = INTERPRETER_RUNNER.search(text, reach, end)
    if match is None:
        return None
    name = match.group("double") or match.group("single") or match.group("bare")
    if (match.group("flag") == "r" and name != "php") or (match.group("eval") and name != "deno"):
        return None
    start = _COMMAND_START.search(text, reach, match.start())
    words = text[start.start() + 1 if start else reach:match.start()]
    tokens = segment_tokens(words) if words.strip() else []
    if tokens is None or start is None and reach > 0:
        return name
    at = resolve_command(tokens + ["interpreter"])
    if at == len(tokens):
        return name
    # BANDAID: a launcher runs the interpreter too (`uv run python`, `strace -f python3`, `find -exec
    # python3`), and no list names them all, so the interpreter outside command position is a runner
    # unless the command is a text search tool, whose argument (`grep -rn src/python -e`) is a path.
    program = basename(tokens[at]) if at is not None else ""
    return None if program in TEXT_SEARCH_TOOLS else name


def _handed_on(words) -> list:
    """Every command line a list hands on, however deep: `sh -c` inside `docker exec` inside `flock`. Each
    text that inner_commands returns is read again, one segment at a time, until no new text turns up.
    A text already read is skipped, so the walk ends."""
    found, queue = [], [words]
    while queue:
        for text in inner_commands(queue.pop()):
            if text not in found:
                found.append(text)
                queue.extend(tokens for part in split_segments(text) if (tokens := segment_tokens(part)))
    return found


BRACKET = "["   # the calls entry of an open list or block


class _Statement:
    """The statement a script walk is in: where it starts and which calls are open in it. A pair is
    held as printed text when a printer holds it: the statement starts with a printer command
    (`echo`, `printf`), or an open call is a printer (`print(`, `console.log(`). Inside a printer a
    pair runs only when a run call (RUN_NAME) sits between it and the printer (`echo shell_exec(`,
    `print(check_output(`); any other call (`print(len(`, `echo json_encode(`) prints its result.
    With no printer, every pair runs, whatever call holds it."""

    def __init__(self, body: str, first: int = 0, quotes=(), hash_comments: bool = True, brackets: bool = False):
        self.body, self.start, self.calls, self.command = body, 0, [], None
        self.first = first     # where the script's text starts: a span's own quote sits ahead of it
        self.comment_end = 0   # a `#` comment runs to here: its text opens no call and ends no statement
        # The script's other string quotes, as they sit in its text (`'`, `\\"`, a backtick): inside one,
        # `#`, `;` and brackets are text. A `'` or `"` string ends at its line's end, so a lone apostrophe
        # hides no later line; a template literal may span lines.
        self.quotes, self.quote = quotes, ""
        self.hash_comments = hash_comments   # False for a language that reads `#` as text (node, deno)
        self.brackets = brackets   # `[` and `{` open a BRACKET entry, so a list element is no call argument

    def advance(self, index: int, width: int = 1):
        """Read the unquoted text at `index`, `width` characters (2 for a backslash pair): a statement
        end clears the state, a `(` opens a call or a group, a `)` closes one."""
        if index < self.comment_end:
            return
        token = self.body[index:index + width]
        if self.quote:
            if token == self.quote or (token == "\n" and not self.quote.endswith("`")):
                self.quote = ""
            return
        if token in self.quotes:
            self.quote = token
            return
        if width > 1:
            return
        char = token
        if char == "#" and self.hash_comments and (index == self.first or self.body[index - 1] in " \t\n;|&("):
            end = self.body.find("\n", index)
            self.comment_end = len(self.body) if end < 0 else end
            return
        if char == "\n" and any(name and name != BRACKET for name in self.calls):
            return   # a call split over lines (`print(` and its string) is still one statement
        if char in ";&|\n":
            self.start, self.calls, self.command = index + 1, [], None
        elif char == "(":
            name = CALL_NAME.search(self.body, max(0, index - 48), index)
            name = name.group(1) if name and name.group(1) not in NOT_A_CALL else ""
            self.calls.append(name)
        elif char == ")":
            while self.calls and self.calls[-1] == BRACKET:
                self.calls.pop()
            if self.calls:
                self.calls.pop()
        elif self.brackets and char in "[{":
            self.calls.append(BRACKET)
        elif self.brackets and char in "]}" and self.calls and self.calls[-1] == BRACKET:
            self.calls.pop()

    def runs(self) -> bool:
        """True when a run call (RUN_NAME) is open: the pair at the cursor is its argument or inside one."""
        return any(RUN_NAME_END.search(name) for name in self.calls)

    def printed(self, index: int) -> bool:
        # A run call named some other way (`sh = os.system; print(sh(...))`) reads as printed: only
        # a writer who means to hide the call takes that shape.
        for name in reversed(self.calls):
            if RUN_NAME_END.search(name):
                return False
            if PRINT_CALL_NAME.search(name):
                return True
        if self.command is None:
            self.command = PRINT_COMMAND.match(self.body, self.start, index) is not None
        return self.command


# The other string quotes of a script, by the quote its pairs use (see _Statement).
OTHER_QUOTES = {'\\"': ("'", "\\`", "`"), '"': ("'", "`"), "'": ('\\"', "\\`", "`")}


def _nested_commands(span: str, before: str = "", mark: str = '\\"', held_only: bool = False,
                     hash_comments=None) -> str:
    """A quoted span that holds quote marks is a script handed to an interpreter
    (`python3 -c "os.system(\\"git push\\")"`, `python3 -c 'os.system("git push")'`). `mark` is the
    pair's quote as it sits in the span: `\\"` in a double-quoted span, `"` in a single-quoted one. In a
    runner script (`bash -c`, `eval`, `ssh`, `python -c`, `node -e`) each pair is a command unless a
    printer holds it (`print`, `echo`, `printf`, `console.log`: see _Statement). The call may be named
    any way: an alias, a from-import, `shlex.split`, a variable. Printed text that a pipe feeds into a
    shell (`echo \\"git push\\" | sh`) is a script and runs. A CALL_RUNNER call runs its pair even inside
    a print. Outside a runner script only a CALL_RUNNER pair is read (`before` is the segment text
    ahead of the span). Give each command its own line, so the words that follow it in the script
    (`print(\\"+1\\")`) are not its arguments. `held_only` reads a pair as a command only when a run call
    holds it or a pipe feeds it to a shell: the single-quoted strings of a double-quoted script are
    assigned, written and asserted as often as they are run. `hash_comments` says whether `#` opens a
    comment; by default the runner ahead of the span tells: a shell, python, ruby, perl or php."""
    lines, piece, inner, run, index = ["\n"], [], False, False, 1
    words, argv, closed = [], False, 0
    shell = SCRIPT_RUNNER.search(before) is not None
    language = "" if shell else _interpreter(before)
    script = shell or language is not None
    body = span[:-1]
    if hash_comments is None:
        # Node and deno read `#` as text, so for them a ` #` hides nothing.
        hash_comments = basename(language or "") not in ("node", "nodejs", "deno")
    statement = _Statement(body, 1, OTHER_QUOTES[mark], hash_comments)
    # Each statement end, found once: a pair is fed to a shell when its statement ends in a pipe to one.
    ends = [match.start() for match in STATEMENT_END.finditer(body)] if script else []
    mark_width = len(mark)

    def emit():
        nonlocal words
        if words:
            # A list whose program runs an element as a command line (`sh -c`, `ssh`, `su -c`,
            # `watch`: inner_commands) hands that line on as it stands. Any other element is one word.
            handed = _handed_on(words)
            # A list of one string runs as a command line under shell=True, so it is read as one.
            lines.append("".join(text + "\n" for text in handed) if handed else words[0] + "\n"
                         if len(words) == 1 else " ".join(map(_argv_word, words)) + "\n")
            words = []

    def piped_into_shell(close: int) -> bool:
        """True when the statement of the pair that closes at `close` ends in a pipe into a shell."""
        at = bisect.bisect_left(ends, close + mark_width)
        return (at < len(ends) and body[ends[at]] == "|"
                and PIPE_INTO_SHELL.match(body, ends[at] + 1) is not None)

    while index < len(body):
        if not inner and index < statement.comment_end:
            index += 1
            continue
        if body.startswith(mark, index):
            if inner:
                if run:
                    # an argv call's pairs gather as words; any other pair is a line of its own
                    (words if argv else lines).append("".join(piece) if argv else "".join(piece) + "\n")
                piece = []
                closed = index + mark_width
            else:
                ahead = body[max(0, index - 256):index]
                if not (argv and ARGV_GAP.fullmatch(body[closed:index])):
                    emit()
                    run = (CALL_RUNNER if script else CALL_RUNNER_ANYWHERE).search(ahead) is not None
                    if script and not run:
                        close = body.find(mark, index + mark_width)
                        run = (statement.runs() if held_only else not statement.printed(index)) or (
                            close >= 0 and piped_into_shell(close))
                    argv = run and script and ARGV_CALL.search(ahead) is not None
            inner = not inner
            width = mark_width
        else:
            width = 2 if body[index] == "\\" else 1
            if inner:
                if run:
                    piece.append(body[index:index + width])
            else:
                statement.advance(index, width)
        index += width
    if inner and run:
        (words if argv else lines).append("".join(piece) if argv else "".join(piece) + "\n")
    emit()
    return "".join(lines)


def _joined_splices(segment: str, start: int, end: int):
    """(span, end) of the single-quoted span at `start`, with each `'\\''` splice that follows it joined in.
    The shell closes the quote, writes one apostrophe and reopens it, so the pieces are one script and
    the splice is an apostrophe in its text. `end` is where the last piece closes."""
    pieces = [segment[start + 1:end]]
    while segment.startswith("\\''", end + 1):
        more = _span_end(segment, end + 3, False)
        if more < 0:
            break
        pieces.append(segment[end + 4:more])
        end = more
    return "'" + "'".join(pieces) + "'", end


_RUN_LINES = {}   # script -> the lines that begin inside an open run call, for the life of one hook process


def _lines_in_run_call(script: str):
    """The stripped text of each line of `script` that begins inside an open run call (`os.system(` with
    its string on the next line). A list (`items = [`) and any other call (`print(`) hold text, and so
    does a list inside a run call (`subprocess.run([`): its element is no command line. The walk skips
    strings, template literals and `#` comments, and reads the script once however many lines ask."""
    found = _RUN_LINES.get(script)
    if found is None:
        found, statement, index, length = set(), _Statement(script, brackets=True), 0, len(script)
        while index < length:
            char = script[index]
            if char in "'\"`" and index >= statement.comment_end:
                end = _span_end(script, index, True)
                index = end + 1 if end >= 0 else index + 1
                continue
            statement.advance(index)
            index += 1
            if char == "\n" and index > statement.comment_end and statement.calls \
                    and RUN_NAME_END.search(statement.calls[-1]):
                end = script.find("\n", index)
                found.add(script[index:length if end < 0 else end].strip())
        _RUN_LINES[script] = found
    return found


def _push_scan(segment: str, script: str = "") -> str:
    """The segment read the way the shell reads its quotes, comments and escapes, so what the
    quote pattern sees is a whole span. A backslash pair is text (`it\\'s` opens no quote). A
    `#` that starts a word is a comment to the line's end. A quote the shell leaves open hides
    the rest of the line from it, so that rest, when it holds a space, is blanked. A
    double-quoted span with escaped quotes is read by _nested_commands. PowerShell escapes
    with a backtick, and a segment of it is left to the pattern. `script` is the text the segment is
    a line of, which tells a line that holds the string of a split run call from one that holds text."""
    if is_powershell(segment):
        return segment
    out, index, length = [], 0, len(segment)
    while index < length:
        char = segment[index]
        if char == "\\":
            out.append(segment[index:index + 2])
            index += 2
        elif char == "#" and (index == 0 or segment[index - 1] in " \t\n;|&("):
            while index < length and segment[index] != "\n":
                index += 1
        elif char in "'\"":
            end = _span_end(segment, index, char == '"' or segment[index - 1:index] == "$")
            if end < 0:
                tail = segment[index + 1:]
                out.append(" " if re.search(r"\s", tail) else char + tail)
                index = length
                continue
            span = segment[index:end + 1]
            ahead = segment[max(0, index - 512):index]
            if char == '"' and '\\"' in span:
                span = _nested_commands(span, segment[:index])
            elif char == "'" and _interpreter(segment, index) and '"' in (
                    joined := _joined_splices(segment, index, end))[0]:
                # The runner's script sits in single quotes, so its own strings are plain pairs.
                span, end = _nested_commands(joined[0], segment[:index], '"'), joined[1]
            elif char == '"' and "'" in span and _interpreter(segment, index):
                # The runner's script sits in double quotes, so its own strings are single-quoted pairs.
                span = _nested_commands(span, segment[:index], "'", True)
            elif char == '"' and ARGV_CALL.search(ahead[-256:]):
                # An argv call on a heredoc line (see below): the rest of the line is the call's
                # arguments, so its pairs join into one command line as in a deno eval script. The
                # heredoc's language is unknown, so `#` keeps its comment reading.
                out.append(_nested_commands("'" + segment[max(0, index - 256):] + "'", "deno eval ", '"',
                                            hash_comments=True))
                break
            elif CALL_RUNNER.search(ahead[-256:]) or (
                    not (ahead.strip() or segment[end + 1:].strip()) and segment.strip() in _lines_in_run_call(script)):
                # BANDAID: an interpreter heredoc body reaches this reader a line at a time, with
                # no runner word ahead of it. A string handed to a call that runs it is a command
                # wherever the call stands, and so is a line that is one string alone when a run
                # call is open ahead of it in `script` (the string of a call split over lines).
                # No shell line has either shape.
                span = "\n" + span[1:-1] + "\n"
            out.append(span)
            index = end + 1
        else:
            out.append(char)
            index += 1
    return "".join(out)


def push_text(segment: str, script: str = "") -> str:
    """The segment with quoted multi-word text blanked: a quoted `--force` is text, not a push.
    A script handed to an interpreter in a string with escaped quotes keeps its commands, one
    to a line; push_calls reads them line by line."""
    segment = _push_scan(segment, script)
    return PUSH_QUOTED.sub(" ", segment)


def push_calls(segment: str, script: str = ""):
    """(subcommand, arguments) of each `git` call in the live text of one segment: the one
    reader of git calls for a push. Each line of push_text is its own command."""
    for line in push_text(segment, script).split("\n"):
        yield from guard_core.git_calls(line)


def _push_parse(args):
    """The one reader of `git push` arguments: (force, mirror, every, includes, unpinned, leased,
    delete, upstream, remote, refspecs). `upstream` is a `-u` or `--set-upstream` push. `--branches` is
    git's alias of `--all`. The remote is '' when none is named."""
    force = mirror = every = includes = unpinned = leased = delete = upstream = False
    remote = ""
    plain = []
    skip = repo_next = False
    for arg in args:
        arg = arg.replace('"', "").replace("'", "")
        if repo_next:
            repo_next, remote = False, arg
        elif skip:
            skip = False
        elif arg in PUSH_VALUE_OPTS:
            skip = True
        elif arg.startswith("--"):
            name, _, value = arg.partition("=")
            if name == "--repo":
                remote, repo_next = value, not value
            elif name == "--force-if-includes" or (
                    len(name) >= 9 and "--force-if-includes".startswith(name)):
                includes = True
            elif name == "--no-force-if-includes":
                includes = False
            elif name == "--no-force-with-lease":
                leased = unpinned = False
            elif name == "--force-with-lease" or (
                    len(name) >= 9 and "--force-with-lease".startswith(name)):
                leased = True
                unpinned = unpinned or not value.partition(":")[2]
            elif name == "--mirror":
                mirror = True
            elif name in ("--all", "--branches"):
                every = True
            elif len(name) >= 6 and "--set-upstream".startswith(name):
                upstream = True
            elif name == "--delete":
                delete = True
            elif len(name) >= 4 and "--force".startswith(name):
                force = True
        elif arg.startswith("-") and len(arg) > 1:
            for index, letter in enumerate(arg[1:]):
                if letter == "o":  # a push option: the rest of the word, or the next word
                    skip = index == len(arg) - 2
                    break
                force = force or letter == "f"
                delete = delete or letter == "d"
                upstream = upstream or letter == "u"
        else:
            plain.append(arg)
    if not remote and plain:
        remote, plain = plain[0], plain[1:]
    return force, mirror, every, includes, unpinned, leased, delete, upstream, remote, plain


def _push_dest(spec: str, bare: bool, cwd: str, overrides=None):
    """The branch one refspec writes: `HEAD` and a bare push read the checkout's current branch.
    None when that cannot be read."""
    source, colon, target = spec.lstrip("+").partition(":")
    target = target if colon else source
    if bare:
        return _push_bare_destination(cwd, overrides)
    if target in ("HEAD", "@"):
        return _push_current_branch(cwd)
    return target


_DESTINATIONS = {}   # (args, cwd, overrides) -> destinations, for the life of one hook process


def push_destinations(args, cwd: str, overrides=None):
    """The branch names a `git push` with these arguments writes, `refs/heads/` cut off, a deletion
    included. None stands for a destination it cannot resolve. One hook call is one process and reads
    each push's destinations once, so the record-branch check and the conflict-markers check share the
    reads (`git symbolic-ref`, `git config`) a HEAD or bare push needs."""
    key = (tuple(args), cwd, tuple(sorted((overrides or {}).items())))
    if key not in _DESTINATIONS:
        plain = _push_parse(args)[-1]
        found = [_push_dest(spec, not plain, cwd, overrides) for spec in plain or [""]]
        _DESTINATIONS[key] = [t.removeprefix("refs/heads/") if t else t for t in found]
    return _DESTINATIONS[key]


def _colon_delete(delete, plain):
    """True for a push that deletes: a delete flag, or a refspec with no source (`:ref`)."""
    return delete or any(spec.startswith(":") for spec in plain)


def push_refspecs(args):
    """(remote, refspecs) of a push that names the refs it sends, else None: `--all`, `--branches`,
    `--mirror`, a deletion and a tags-only push send no range this reader can name. The remote is ''
    when none is named, and the refspecs are empty for a bare push."""
    _force, mirror, every, _includes, _unpinned, _leased, delete, _upstream, remote, plain = _push_parse(args)
    delete = _colon_delete(delete, plain)
    if mirror or every or delete or (_push_tags_only(args) and not plain):
        return None
    return remote, plain


def push_verdict(args, cwd: str, overrides=None) -> str:
    """'' for an allowed push, else 'ask' or 'deny', for the `git push` arguments `args`.

    Not forced: ''. Forced or deleting at the default branch, or at a destination this cannot
    resolve: 'ask'. Forced by `--force`, `-f`, a `--fo...` prefix or a `+refspec`: 'deny'. Forced
    by a lease: '' when `--force-if-includes` rides with it, or every lease names its own sha;
    else 'deny'. A deletion off the default branch is ''.
    """
    force, mirror, every, includes, unpinned, leased, delete, _upstream, remote, plain = _push_parse(args)
    plus = any(spec.startswith("+") for spec in plain)
    delete = _colon_delete(delete, plain)
    if not (force or leased or plus or mirror or delete):
        return ""
    if not remote:
        remote = _push_config(
            cwd, "branch." + (_push_current_branch(cwd) or "") + ".remote", overrides)
    defaults = _push_default_branches(cwd, remote or "origin")
    reaches = mirror or every or defaults is None
    for spec in plain or [""]:
        target = _push_dest(spec, not plain, cwd, overrides)
        if target is None or "*" in target:
            reaches = True
        elif target.removeprefix("refs/heads/") in (defaults or ()):
            reaches = True
    if reaches:
        return "ask"
    if force or plus:
        return "deny"
    return "" if includes or not unpinned else "deny"


def push_is_plain(args) -> bool:
    """True when the push carries no force, no lease of any form, no `--force-if-includes`, no `+` refspec,
    and no `--tags` or `--follow-tags` (or an unambiguous prefix of either): it moves only the branches
    it names, forward. A `--no-force-with-lease` that cancels a lease counts as none."""
    force, _mirror, _every, includes, _unpinned, leased, _delete, _upstream, _remote, plain = _push_parse(args)
    if force or leased or includes or any(spec.startswith("+") for spec in plain):
        return False
    for arg in args:
        name = arg.replace('"', "").replace("'", "").partition("=")[0]
        if name.startswith("--") and (
                (len(name) >= 4 and "--tags".startswith(name)) or (len(name) >= 5 and "--follow-tags".startswith(name))):
            return False
    return True


def _push_tags_only(args) -> bool:
    """True when the push carries `--tags` (or an unambiguous prefix): with no refspec it moves tags only."""
    for arg in args:
        name = arg.partition("=")[0]
        if name.startswith("--") and len(name) >= 4 and "--tags".startswith(name):
            return True
    return False


def _push_branch_config(cwd: str, current: str, with_default: bool, overrides=None):
    """(remote, merge, push.default, push.autoSetupRemote) of `current`: '' for a key that is unset, None for
    all four when git cannot answer. The last two are read only with `with_default`. One
    `git config --get-regexp` spawn answers all of them. A `git -c` override of either wins, as in
    `_push_config`."""
    pattern = r"^(branch\.|push\.(default|autosetupremote)$)" if with_default else r"^branch\."
    answer = guard_core._git(cwd, "config", "--get-regexp", pattern) if cwd else None
    if answer is None or answer.returncode not in (0, 1):
        return None, None, None, None
    found = {}
    for line in answer.stdout.splitlines():
        key, _, value = line.partition(" ")
        found.setdefault(key, value.strip())
    def key(name):
        return overrides[name] if overrides and name in overrides else found.get(name, "")

    return (found.get("branch." + current + ".remote", ""),
            found.get("branch." + current + ".merge", "").removeprefix("refs/heads/"),
            key("push.default"), key("push.autosetupremote"))


# Rule push-main judges the remote a push goes to. A URL is a network remote when it carries a scheme
# (`https://`, `ssh://`, `git://`) or is scp-like (`host:path`, `user@host:path`).
_PUSH_URL_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")
_PUSH_URL_SCP = re.compile(r"[^/:\\]+:")
# A remote token the shell expands at run time: a variable, a `$( )` or a backtick substitution.
_PUSH_SHELL_EXPANSION = re.compile(r"[$`]")
_PUSH_LOCAL_PATH = re.compile(r"(?:/|\.{1,2}(?:[/\\]|$)|~|[A-Za-z]:[/\\]|file://)", re.I)
_PUSH_REMOTE_KEYS = (r"^(branch\..+\.(remote|pushremote)|remote\.pushdefault"
                     r"|remote\.[^ ]+\.(url|pushurl))$")


def _is_local_path(url: str) -> bool:
    """True for a path on this machine: absolute, `./` or `../` relative, `~`, a Windows drive path or `file://`."""
    return bool(_PUSH_LOCAL_PATH.match(url))


def _push_url_is_network(url: str) -> bool:
    """True when a remote URL reaches the network. An empty URL and a local path do not."""
    if not url:
        return False
    if _is_local_path(url):
        return False
    return bool(_PUSH_URL_SCHEME.match(url) or _PUSH_URL_SCP.match(url))


def _push_goes_to_network(remote: str, cwd: str, current, overrides=None, resolved=None) -> bool:
    """True when a push to `remote` ('' for a bare push) writes to a network remote.

    A remote argument that is itself a URL or path is judged directly. A name is resolved to
    `remote.<name>.pushurl`, else `remote.<name>.url`. A bare push names `branch.<cur>.pushRemote`, else
    `remote.pushDefault`, else `branch.<cur>.remote`, else origin. A name with no URL is no remote at all, and
    git refuses that push itself. Unreadable config is unknown, and unknown is never safe. A `git -c` override wins.
    A remote the shell has not expanded (`$`, a backtick, `$(`) cannot be resolved, so it is unknown too.
    A dict passed as `resolved` receives `name`, the remote's name, when the push names a remote by name or its
    config does (a URL or path has none): the caller reads that remote's tracking refs without a second config read.
    """
    if _PUSH_SHELL_EXPANSION.search(remote):
        return True
    if remote and (_is_local_path(remote) or ":" in remote):
        return _push_url_is_network(remote)
    answer = guard_core._git(cwd, "config", "--get-regexp", _PUSH_REMOTE_KEYS) if cwd else None
    if answer is None or answer.returncode not in (0, 1):
        return True
    found = {}
    for line in answer.stdout.splitlines():
        key, _, value = line.partition(" ")
        found.setdefault(key, value.strip())

    def get(key):
        return overrides[key.lower()] if overrides and key.lower() in overrides else found.get(key, "")

    if not remote:
        cur = current() or ""
        remote = (get("branch." + cur + ".pushremote") or get("remote.pushdefault")
                  or get("branch." + cur + ".remote") or "origin")
    if resolved is not None:
        resolved["name"] = remote
    return _push_url_is_network(get("remote." + remote + ".pushurl") or get("remote." + remote + ".url"))


def _glob_reach(spec: str):
    """[(source ref, default branch)] a glob refspec sends to main or master, [] when it sends none, None when the
    pattern is not one `*` on each side. A side that is not a full ref name is read under `refs/heads/`."""
    source, colon, target = spec.partition(":")
    target = target if colon else source
    if source.count("*") != 1 or target.count("*") != 1:
        return None
    source_pre, _, source_suf = _qualified(source).partition("*")
    target_pre, _, target_suf = _qualified(target).partition("*")
    found = []
    for name in DEFAULT_BRANCH_FALLBACK:
        full = "refs/heads/" + name
        # `*` may match an empty string, so a name equal to prefix + suffix is reached. The length check only rejects a
        # prefix and suffix that overlap inside the name.
        if (full.startswith(target_pre) and full.endswith(target_suf)
                and len(full) >= len(target_pre) + len(target_suf)):
            middle = full[len(target_pre):len(full) - len(target_suf)]
            found.append((source_pre + middle + source_suf, name))
    return found


def _glob_sends(spec: str, refs) -> list:
    """The refs among `refs` that the source side of the one-`*` glob refspec `spec` matches."""
    pre, _, suf = _qualified(spec.partition(":")[0]).partition("*")
    return [ref for ref in refs if ref.startswith(pre) and ref.endswith(suf) and len(ref) >= len(pre) + len(suf)]


def _local_agent_branches(cwd: str):
    """The full names of the local branches named like an agent worktree, None when the read fails. One
    `git for-each-ref`; a push of every branch sends them, so a failed read is unknown and unknown is never safe."""
    answer = guard_core._git(cwd, "for-each-ref", "--format=%(refname)", "refs/heads/") if cwd else None
    if answer is None or answer.returncode != 0:
        return None
    return [ref for ref in answer.stdout.split() if AGENT_BRANCH.fullmatch(ref.removeprefix("refs/heads/"))]


def _qualified(ref: str) -> str:
    return ref if ref.startswith("refs/") else "refs/heads/" + ref


def _push_updates_default(cwd: str, remote: str, reach) -> bool:
    """True when a push may update main or master on `remote`, for `reach`, the (local source ref, default branch)
    pairs the push sends. A source that does not exist sends nothing. A source whose sha equals the sha of the tracking
    ref `refs/remotes/<remote>/<name>` is trusted to match the remote: nothing is fetched. A missing tracking ref, a different one, or a failed read
    is an update, since unknown is never safe. One `git for-each-ref` reads every ref the pairs name."""
    if not reach:
        return False
    names = sorted({source for source, _name in reach}
                   | {"refs/remotes/" + remote + "/" + name for _source, name in reach})
    answer = guard_core._git(cwd, "for-each-ref", "--format=%(refname) %(objectname)", *names) if cwd else None
    if answer is None or answer.returncode != 0:
        return True
    shas = {}
    for line in answer.stdout.splitlines():
        ref, _, sha = line.partition(" ")
        shas[ref] = sha.strip()
    for source, name in reach:
        if source in shas and shas.get("refs/remotes/" + remote + "/" + name) != shas[source]:
            return True
    return False


def push_ask_hit(args, cwd: str, overrides=None) -> str:
    """'main', 'all', 'all-agent', 'agent', 'stray' or '' for the `git push` arguments `args`, a push `push_verdict`
    let through.

    'all' (rule push-all-main, which refuses and never asks): `--all`, `--branches`, or a glob refspec that sends
    main or master to a name it reaches (`refs/heads/*:refs/heads/*`), to a network remote, when local main or master
    exists and the remote-tracking ref (`refs/remotes/<remote>/<name>`) is missing or differs from it. A matching ref is
    trusted: the remote is never contacted. The verdict is the same from a main, lane, detached or agent checkout, except
    that `--all` from an agent checkout is 'agent'. Reads on this path: the one `git config --get-regexp` for the
    remote, one `git symbolic-ref` for `--all` (the agent test), and one `git for-each-ref` of the tracking refs.

    'all-agent' (rule push-all-main, same refusal, another reason): the same push, when main is not updated, but a local
    branch named like an agent worktree exists that the push sends: every branch for `--all` and `--branches`, the
    branches its source side matches for a glob, whatever name its target has. One more `git for-each-ref`, of
    `refs/heads/`, once the tracking-ref read has found no update. A failed read of it is 'all'.

    'agent' (rule push-agent-branch, which refuses where the other two kinds ask): a push whose destination name is an agent-worktree branch name
    (`AGENT_BRANCH`), with or without `-u`, checked before 'stray'. An implied destination is the current
    branch (a bare push with no upstream too, under push.autoSetupRemote); an explicit one is the part
    after `:`, `refs/heads/` stripped; a colon-less refspec is its own name. A destination after `:` adds
    no read. A colon-less refspec other than `main` or `master` reads the current branch once
    (`symbolic-ref`), to tell an implied destination from a literal one.

    'main' (rule push-main): a non-forced push whose destination is literally `main` or `master`
    to a network remote (`_push_goes_to_network`): a push to a path, a `file://` URL or a remote
    with no URL is silent. The remote's HEAD is never read. 'stray' (rule push-stray-branch): a push with an implied
    destination (a bare push, `HEAD`, `@`, or a colon-less refspec naming the current branch) that writes a
    name other than the branch's upstream. It needs an upstream, the pushed remote equal to
    branch.<cur>.remote, and an upstream that is not main or master. A `-u` push is silent here: its
    implied destination is the local name, which becomes the new upstream. A bare push under push.default
    simple writes the current branch only when the upstream carries its name, else git refuses it. A
    deletion, a forced push, a mirror, and a push of tags alone are never judged here. A destination that
    cannot be read is allowed. A 'stray' is silent when the implied destination already exists as
    `refs/remotes/<pushed remote>/<name>`: that push updates the branch's own ref. A failed ref read keeps
    the ask. Reads: none for a destination after `:`; one `symbolic-ref` for the current
    branch for a bare push or a colon-less refspec; one `git config --get-regexp` when the upstream is
    needed; one `git rev-parse --verify -q` of the destination's remote-tracking ref, on the stray path only;
    one more `git config --get-regexp` on the main path only, for the remote's URL (none when the
    remote argument is itself a URL or path).
    """
    force, mirror, every, includes, unpinned, leased, delete, upstream, remote, plain = _push_parse(args)
    if force or leased or mirror or delete or any(spec.startswith(("+", ":")) for spec in plain):
        return ""
    state = {"remote": {}}

    def current():
        if "cur" not in state:
            state["cur"] = _push_current_branch(cwd)
        return state["cur"]

    def main():
        if "main" not in state:
            state["main"] = "main" if _push_goes_to_network(remote, cwd, current, overrides, state["remote"]) else ""
        return state["main"]

    def updates_default(reach):
        return _push_updates_default(cwd, state["remote"].get("name", ""), reach)

    if every:
        # --all sends main and the checkout's own branch together, so an agent checkout's push is the agent rule's.
        if not main():
            return ""
        if current() and AGENT_BRANCH.fullmatch(current()):
            return "agent"
        if updates_default([("refs/heads/" + name, name) for name in DEFAULT_BRANCH_FALLBACK]):
            return "all"
        sent = _local_agent_branches(cwd)
        return "all" if sent is None else "all-agent" if sent else ""
    if not plain and _push_tags_only(args):
        return ""

    def config():
        if "cfg" not in state:
            state["cfg"] = _push_branch_config(cwd, current(), not plain, overrides)
        return state["cfg"]

    implied = False
    if not plain:
        cur = current()
        merge, mode, auto = config()[1:] if cur else (None, None, None)
        if cur is None or mode is None:
            return ""
        if mode in ("", "simple"):
            # With no upstream, autoSetupRemote makes git push the current name and set it as the upstream.
            dest = cur if merge == cur or (not merge and auto.lower() in ("true", "yes", "on", "1")) else None
        elif mode == "current":
            dest = cur
            implied = True
        elif mode in ("upstream", "tracking"):
            dest = merge or None
        else:
            dest = None
        if dest in DEFAULT_BRANCH_FALLBACK:
            return main()
        agent = bool(dest and AGENT_BRANCH.fullmatch(dest))
    else:
        agent = False
        to_main = False
        reach, unreadable, globs = [], False, []
        for spec in plain:
            source, colon, target = spec.partition(":")
            if "*" in spec:
                # A glob refspec is --all's own form: it sends every branch it matches, main among them.
                glob = _glob_reach(spec)
                unreadable = unreadable or glob is None
                reach += glob or []
                if glob is not None:
                    globs.append(spec)
            elif colon:
                # A main destination does not end the scan: an agent name later in the push is refused, not asked.
                if target.removeprefix("refs/heads/") in DEFAULT_BRANCH_FALLBACK and main():
                    to_main = True
                agent = agent or bool(AGENT_BRANCH.fullmatch(target.removeprefix("refs/heads/")))
            elif source.removeprefix("refs/heads/") in DEFAULT_BRANCH_FALLBACK:
                # A local origin makes main() empty; the other refspecs are still read for agent and stray.
                if main():
                    to_main = True
            elif source in ("HEAD", "@") or (current() is not None and source == current()):
                implied = True
                agent = agent or bool(current() and AGENT_BRANCH.fullmatch(current()))
            else:
                agent = agent or bool(AGENT_BRANCH.fullmatch(source.removeprefix("refs/heads/")))
        # A glob this cannot read may send main, and unknown is never safe.
        if not agent and (unreadable or reach or globs) and main():
            if unreadable or updates_default(reach):
                return "all"
            # A glob reaches a local agent-named branch whatever name its target has, so it is judged by its source.
            if globs:
                local = _local_agent_branches(cwd)
                if local is None:
                    return "all"
                if any(_glob_sends(spec, local) for spec in globs):
                    return "all-agent"
        if not agent and (to_main or (implied and current() in DEFAULT_BRANCH_FALLBACK and main())):
            return "main"
    if agent:
        return "agent"
    if not implied or current() is None:
        return ""
    remote_cfg, merge = config()[:2]
    pushed = remote or remote_cfg
    if not merge or not remote_cfg or pushed != remote_cfg or merge in DEFAULT_BRANCH_FALLBACK:
        return ""
    # A -u push of the local name sets that name as the new upstream on purpose (a lane stacked on a lane).
    if merge == current() or upstream:
        return ""
    # A destination already on the pushed remote is that branch's own ref, so the push is no stray. A read that
    # fails (git unavailable, an error other than "no such ref") keeps the ask.
    seen = guard_core._git(cwd, "rev-parse", "--verify", "-q", "refs/remotes/" + pushed + "/" + current())
    return "" if seen is not None and seen.returncode == 0 else "stray"


# ------------------------------------------------------------------ a rewrite and a wide delete
#
# A force push rewrites a branch other people have pulled. It is sometimes right, so it asks rather
# than refuses.
#
# The recursive delete keeps the SAME SHAPE in both shells, deliberately. `rm -rf node_modules` is
# allowed, so `Remove-Item -Recurse -Force node_modules` must be allowed too. A guard that answers
# differently for the same act teaches which tool to reach for. PowerShell folds case and
# abbreviates parameter names, so `-r`, `-rec` and `-recurse` are one flag. The command text is
# read with backslashes already turned into forward slashes, which is why a drive root reads
# as `C:/`.
WIDE_TARGET = (
    r"(?:/\*?|(?:~|\.|\$HOME|\$\{HOME\}|%USERPROFILE%|\$env:USERPROFILE)(?:/\*?)?|\*|[A-Za-z]:/?\*?)"
)
# The POSIX `rm -rf` form is read by TOKENS (`rm_delete_hit`), not by a pattern: a quoted `rm -rf /`
# in an echo or a commit message is text. `RM_RAW` reads raw text only for a segment shlex cannot
# parse. There a match inside quotes is text too, and a quote the shell leaves open hides what
# follows it, as it does from the shell. An escaped quote (`it\'s`, kept by `delete_text`) and a
# contraction open no quote.
_ESCAPED = re.compile(r"\\(.?)", re.S)


def delete_text(segment):
    """`segment` with its backslashes turned into slashes, as `norm` does, so `C:\\` reads as `C:/`.
    In bash a backslash before a quote stays: `it\\'s` and `"a\\"b"` open no quote, and `it/'s`
    would. Each pair is read whole, so `\\\\'` is an escaped backslash and then an open quote."""
    if is_powershell(segment):
        return type(segment)(norm(segment))
    return type(segment)(_ESCAPED.sub(
        lambda m: m.group(0) if m.group(1) in ("'", '"') else "/" + norm(m.group(1)), segment))


def _substitution_end(text, index):
    """Where the command substitution that opens at `text[index]` ends, else -1. `$(` ends at its
    matching `)` and a backtick at the next one; an unclosed one runs to the end of the text.
    PowerShell has `$( )` only, as a backtick is its escape."""
    if text.startswith("$(", index):
        depth = 0
        for at in range(index + 1, len(text)):
            depth += (text[at] == "(") - (text[at] == ")")
            if depth == 0:
                return at
        return len(text)
    if text[index] == "`" and not is_powershell(text):
        close = text.find("`", index + 1)
        return len(text) if close < 0 else close
    return -1


_TEXT_COMMANDS = ("echo", "printf", "write-host", "write-output")
_LIVE_UNQUOTED = re.compile(r"\$\(|`|[<>]\(")


def _quotes_are_text(segment):
    """True when a segment only prints its quoted words or stores them as a commit message: its
    command is a printer or `git commit`, with no substitution outside single quotes. Any other
    command may run a quoted word (`parallel`, `script -c`, `watch`, `runuser -c`)."""
    if _LIVE_UNQUOTED.search(re.sub(r"'[^']*'", "", segment)):
        return False
    words = [word for word in segment_tokens(segment) or () if not re.match(r"[A-Za-z_]\w*=", word)]
    if not words:
        return False
    if words[0].lower() in _TEXT_COMMANDS:
        return True
    return words[0] in ("git", "git.exe") and words[_git_subcommand_index(words, 0):][:1] == ["commit"]


class UnquotedStart:
    """A compiled pattern whose `search` skips a match that starts inside quotes. It has a
    pattern's own `search`, so a caller loops over it without knowing the difference. An
    apostrophe shaped like a contraction is text, as in split_segments' second reading: a lone
    `don't` must not turn the rest of the line into one quote. `printers_only` skips quotes only in
    a segment whose quoted words are text (`_quotes_are_text`) and not piped on; elsewhere it reads
    the raw text."""

    def __init__(self, pattern, nested=False, printers_only=False):
        self.pattern = pattern
        self.nested = nested
        self.printers_only = printers_only

    def search(self, text):
        if self.printers_only:
            ends = []
            for segment, end in zip(split_segments(text, ends), ends):
                text_only = end != "|" and _quotes_are_text(segment)
                found = self._search_unquoted(segment) if text_only else self.pattern.search(segment)
                if found:
                    return found
            return None
        found = self._search_unquoted(text)
        if found or not self.nested:
            return found
        # The script a shell, `eval` or `pwsh -Command` runs is quoted text, so it is read again as a command.
        for segment in split_segments(text):
            for script in inner_commands(segment_tokens(segment) or []):
                found = self.search(script)
                if found:
                    return found
        return None

    def _search_unquoted(self, text):
        inside, quote, index, live_to = set(), "", 0, -1
        while index < len(text):
            if quote == '"' and index > live_to:
                live_to = max(live_to, _substitution_end(text, index))   # `$( )` and backticks run in double quotes
            if not quote and text[index] == "'" and CONTRACTION.match(text, index):
                width, after = 1, ""
            else:
                width, after = quote_advance(text, index, quote)
            if quote and index >= live_to:
                inside.update(range(index, index + width))
            quote, index = after, index + width
        return next((m for m in self.pattern.finditer(text) if m.start() not in inside), None)


RM_RAW = UnquotedStart(re.compile(
    r"\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*\s+['\"]?" + WIDE_TARGET + r"['\"]?(?:\s|\)|$)"
))


DESTRUCTIVE_DELETE = (
    UnquotedStart(re.compile(
        r"(?i)\b(?:remove-item|ri|rd|rmdir|del|erase|rm)\b"
        r"(?![^\n;|&]*\s--cached\b)"   # the index-only form of `git rm`
        r"(?=[^\n;|&]*\s-r(?:ec(?:urse)?)?\b)"
        r"(?=[^\n;|&]*\s-f(?:o(?:rce)?)?\b)"
        r"[^\n;|&]*\s['\"]?" + WIDE_TARGET + r"['\"]?(?:\s|\)|$)"
    ), printers_only=True),
    # Recursion alone is enough for the PowerShell names. `rm` is read by tokens, not here. A match
    # that starts inside quotes is text (an echo, a commit message), so it is not read.
    UnquotedStart(re.compile(
        r"(?i)\b(?:remove-item|ri|rd|rmdir|del|erase)\b"
        r"(?=[^\n;|&]*\s-r(?:ec(?:urse)?)?\b)"
        r"[^\n;|&]*\s['\"]?" + WIDE_TARGET + r"['\"]?(?:\s|\)|$)"
    ), nested=True),
)
# The one set of wide targets, read by the pattern fallbacks and, by tokens, by `rm -rf`: a root, a
# home, the working directory or a glob of one, with an optional trailing slash and `*`. `.*` and
# `..` are not here: they were allowed before.
RM_WIDE_TARGET = re.compile(WIDE_TARGET)


def _rm_args_wide(args) -> str:
    """The first wide target of `rm`'s arguments when they hold a recursive flag, else ''. Long
    flags count, `--` ends the flags, and one letter cluster may hold R or r. Force is no part of it."""
    recursive = after_dashes = False
    targets = []
    for arg in args:
        if after_dashes or not arg.startswith("-") or arg == "-":
            targets.append(arg)
        elif arg == "--":
            after_dashes = True
        elif arg.startswith("--"):
            recursive = recursive or arg == "--recursive"
        else:
            recursive = recursive or "r" in arg or "R" in arg
    if recursive:
        return next((t for t in targets if RM_WIDE_TARGET.fullmatch(t)), "")
    return ""


# A substitution glued to an assignment or a backtick (`x=$(rm`, `` `rm ``): the command follows it.
SUBST_OPEN = re.compile(r"^(?:[A-Za-z_]\w*=)?(\$\(|`)(?=.)")


def _in_group(args, tick=False):
    """`args` up to the `)` (or, with `tick`, the backtick) that closes a group opened before them,
    with that mark cut off its token: `(rm -rf .)` hands rm `.)`, and rm's target is `.`. A `)` that
    closes a `$(` inside `args` stays."""
    depth, out = 0, []
    for arg in args:
        if tick:
            cut = arg.find("`")
            if cut >= 0:
                out += [arg[:cut]] if cut else []
                break
        else:
            depth += arg.count("(")
            extra = arg.count(")") - depth
            if extra > 0:
                out += [arg[:-extra]] if arg[:-extra] else []
                break
            depth -= arg.count(")")
        out.append(arg)
    return out


def _git_subcommands(words):
    """The indexes of the words that name a git subcommand, such as the `rm` of `git rm -r .`. Such
    a word is no command word. A force flag keeps the word read: `git rm` without one refuses to drop an edited
    file, so git can restore what it removes, and `git rm -f` discards the edits. `--cached` removes from the
    index only, so it names the subcommand whatever the other flags say."""
    found = set()
    for at, word in enumerate(words):
        if basename(word) in ("git", "git.exe"):
            sub = _git_subcommand_index(words, at)
            args = words[sub + 1:]
            args = args[:args.index("--")] if "--" in args else args
            if "--cached" in args or not any(
                    a == "--force" or (a[:1] == "-" and a[1:2] != "-" and "f" in a) for a in args):
                found.add(sub)
    return found


def _command_hit(segment: str, names, judge, raw=None, by_word=False, flagged=False) -> str:
    """The first text `judge` returns for the arguments of a command named in `names`, in one parsed
    segment, else ''. The command word sits behind its wrappers or a
    subshell, or inside the script a shell, `eval` or `ssh` hands on. The one reader of these forms.
    A group's closing `)` is no part of the last argument. A segment shlex cannot parse is read as
    raw text with the pattern `raw`, when there is one. With `by_word`, `judge` also gets the
    command word it judges. With `flagged`, `judge` is known to answer '' for arguments that hold no
    word starting with `-` or `/`, so a command word with no such word after it is not judged: a
    chain of command words (`echo rm rm rm ...`) then costs one pass, not one pass per word. This is a
    bandaid: a chain with a flag at its end is still judged word by word."""
    tokens = segment_tokens(segment)
    if tokens is None:
        found = raw.search(segment) if raw else None
        return found.group(0) if found else ""
    quoted = getattr(tokens, "quoted", ())
    views = [(tokens, False)]
    for at, token in enumerate(tokens):
        opened = SUBST_OPEN.match(token) if at not in quoted else None
        if opened:
            views.append(([token[opened.end():]] + tokens[at + 1:], opened.group(1) == "`"))
    for view, tick in views:
        for start in command_indexes(view):
            if basename(view[start]) in names:
                args = _in_group(view[start + 1:], tick)
                found = judge(args, basename(view[start])) if by_word else judge(args)
                if found:
                    return found
    words, bare = bare_words(segment)
    last_flag = max((i for i, w in enumerate(words) if w[:1] in ("-", "/")), default=-1) if flagged else len(words)
    for at in sorted(bare - _git_subcommands(words)):
        opened = SUBST_OPEN.match(words[at])
        word = words[at][opened.end():] if opened else words[at]
        if basename(word) not in names or at >= last_flag:
            continue   # reading the group only for a named command keeps the loop linear in the words
        args = _in_group(words[at + 1:], bool(opened) and opened.group(1) == "`")
        found = judge(args, basename(word)) if by_word else judge(args)
        if found:
            return found
    for script in inner_commands(tokens):
        for inner in split_segments(script):
            found = _command_hit(inner, names, judge, raw, by_word, flagged)
            if found:
                return found
    return ""


def _rm_wide_text(args) -> str:
    target = _rm_args_wide(args)
    return "rm -rf " + target if target else ""


def rm_delete_hit(segment: str) -> str:
    """Return the matched text when one segment runs `rm -rf` at a root, a home, the working
    directory or a glob, else ''. A segment shlex cannot parse is read as raw text."""
    return _command_hit(segment, ("rm",), _rm_wide_text, RM_RAW, flagged=True)


# ------------------------------------------------------------ `.`, a parent, the working folder
#
# A recursive delete, forced or not, of `.`, a relative parent, the working folder or a folder above
# it (decision rm-path-wrapper). The rm shim holds the same line on Mac and Linux, at run time; on
# Windows this reader is the only one. It reads the command text, and resolves a named folder through
# links already on disk, so it misses a link made earlier in the same command. One reader serves
# `rm`, the PowerShell delete verbs and the cmd.exe verbs, in either shell. `.`, `..` and a relative
# parent deny by their text, so a folder change ahead of them needs no tracking. Any other relative name is
# resolved against the shell's own folder only when no folder change comes first.
REL_PARENT = re.compile(r"(?:\.{1,2}/)*\.{1,2}(?:/\*?)?")
CMD_FLAG = re.compile(r"/[A-Za-z?]")
RM_PARENT_RAW = UnquotedStart(re.compile(
    r"\brm\s+(?:-\S+\s+)*?-(?:[a-zA-Z]*[rR][a-zA-Z]*|-recursive)\s+(?:-\S+\s+)*['\"]?"
    + REL_PARENT.pattern + r"['\"]?(?:\s|\)|$)"
))


def _pwd_as_dot(target: str) -> str:
    """`target` with a leading `$(pwd)` read as `.`, the working folder the substitution names, so
    `$(pwd)/*` is judged as `./*` and `$(pwd)/build` as `./build`. Quotes are already gone from a
    parsed token. `$PWD` is left alone: the variable rule (rm-var-unguarded) refuses it."""
    return "." + target[len("$(pwd)"):] if target.startswith("$(pwd)") else target


def _parent_target(target: str, cwd: str, moved: bool) -> bool:
    """True when `target` is `.`, a relative parent, or the working folder or a folder above it,
    or a glob of one."""
    target = _pwd_as_dot(target)
    if REL_PARENT.fullmatch(target):
        return True
    if not cwd or not target or RM_WIDE_TARGET.fullmatch(target):
        return False   # a root, a home or a drive root is the wide readers' to judge, not this one's
    path = shell_abs(target[:-2] if target.endswith("/*") else target, None if moved else cwd)
    if not path:
        return False
    try:
        here, there = (os.path.normcase(os.path.realpath(p)) for p in (cwd, path))
    except (OSError, ValueError):
        return False
    return here == there or here.startswith(there.rstrip(os.sep) + os.sep)


def _parent_delete_text(args, word: str, cwd: str, moved: bool) -> str:
    """`word -r <target>` for the first target of a recursive delete that is `.`, a parent or the
    working folder, else ''. Recursion is `/s` for the cmd.exe verbs, a prefix of `-Recurse` for the
    PowerShell verbs, and `-r`, `-R` or `--recursive` for `rm`."""
    cmd_verb = word in CMD_EXE_DELETE_WORDS
    recursive = after_dashes = False
    targets = []
    for arg in args:
        low = arg.lower()
        if cmd_verb and not after_dashes and CMD_FLAG.fullmatch(arg):
            recursive = recursive or low == "/s"
        elif after_dashes or not arg.startswith("-") or arg == "-":
            targets.append(arg)
        elif arg == "--":
            after_dashes = True
        elif arg.startswith("--"):
            recursive = recursive or "recursive".startswith(low[2:])
        else:
            body = low[1:]
            recursive = recursive or "recurse".startswith(body) or (
                word == "rm" and "r" in body and not "force".startswith(body))
    if not recursive:
        return ""
    for target in targets:
        if _parent_target(target, cwd, moved):
            return "%s %s %s" % (word, "/s" if cmd_verb else "-r", target)
    return ""


PARENT_DELETE_REASON = (
    "Rule (shared trees): this deletes the working folder, a folder above it, or everything in one "
    "of them. The loss reaches files that no session here can see. "
    "Remedy: name the one directory you mean, below the working folder, such as build."
)
PARENT_MOVED_REASON = (
    "Rule (shared trees): this deletes `.` or a parent of it after a folder change, and this hook "
    "does not follow the folder change, so it cannot tell which folder that is. "
    "Remedy: %s"
)
PARENT_MOVED_REMEDY = {
    False: "`rm -rf ./build/*` empties a folder, and `rm -rf build` deletes it by name.",
    True: "`Remove-Item -Recurse build` deletes a folder by name.",
}


def parent_delete_hit(segments, number: int, cwd: str):
    """(matched text, reason) when `segments[number]` runs a recursive delete of `.`, a relative
    parent, the working folder or a folder above it, else ('', ''). Any folder-change command in an
    earlier segment makes the reason name the rewrite that passes."""
    moved = any(
        tokens and _segment_cd_move(tokens) is not None
        for tokens in map(segment_tokens, segments[:number]))
    segment = segments[number]
    matched = _command_hit(
        segment, DELETE_WORDS, lambda args, word: _parent_delete_text(args, word, cwd, moved),
        RM_PARENT_RAW, by_word=True, flagged=True)
    if not matched:
        return "", ""
    if moved and REL_PARENT.fullmatch(_pwd_as_dot(matched.split()[-1].strip("'\""))):
        return matched, PARENT_MOVED_REASON % PARENT_MOVED_REMEDY[is_powershell(segment)]
    return matched, PARENT_DELETE_REASON


# ------------------------------------------------------------------ a link to another install
#
# Some worktrees link their node_modules to another checkout's install with a junction or a symlink.
# Through that link a hand-run `npm ci`, or a recursive delete of what is inside it, empties the
# other checkout's install. The rule reads the filesystem: a real folder, or none, is judged as it
# always was. A bare `rm node_modules` removes only the link, so it stays allowed.
# `--prefix` is read (npm_prefix_flag): its folder is the one judged. A workspace flag is read for
# `npm version` only (NPM_WORKSPACE_FLAGS).
# THE READ-ONLY LIST: every npm subcommand and alias that never rewrites node_modules, by the npm 10.9.9
# list in lib/utils/cmd-list.js. A subcommand off this list is refused in a linked folder, so a new npm
# command, a typo and an abbreviation fail closed. The list is a curated copy because the guard cannot
# read npm's own at hook time.
NPM_READ_ONLY = {
    "access", "adduser", "add-user", "login", "logout", "audit", "bugs", "issues", "cache",  # glossary-ok: "bugs" is npm's own subcommand name
    "completion", "config", "c", "get", "set", "deprecate", "diff", "dist-tag", "dist-tags", "docs",
    "home", "doctor", "exec", "x", "explain", "why", "find-dupes", "fund", "help", "hlep",
    "help-search", "hook", "ll", "la", "ls", "list", "org", "ogr", "outdated", "owner", "author",
    "pack", "ping", "pkg", "prefix", "profile", "publish", "query", "repo", "root", "run-script",
    "run", "rum", "urn", "sbom", "search", "s", "se", "find", "star", "stars", "unstar", "start",
    "stop", "restart", "test", "t", "tst", "team", "token", "unpublish", "version", "verison", "view",
    "v", "info", "show", "whoami",
}
# Global options that take the next word as their value, so that word is not the subcommand.
NPM_VALUE_FLAGS = {
    "--loglevel", "--prefix", "--cache", "--registry", "--userconfig", "--globalconfig",
    "--workspace", "-w", "--tag", "--otp", "--scope", "--before", "--omit", "--include",
    "--install-strategy", "--logs-dir", "-C", "-L", "--location", "-c", "--call", "-m", "--message",
    "--reg",
}
# Options after which the command changes nothing in the working folder's install.
NPM_NO_CHANGE = {"-g", "--global", "--location=global", "--help", "-h", "--dry-run"}
# Subcommands that run install scripts even with --dry-run, so a dry run is no exemption for them.
NPM_DRY_RUN_WRITERS = {"rebuild", "rb", "edit"}
# With one of these, `npm version` reifies the linked root, so it changes the install. Without one it
# only rewrites package.json.
NPM_WORKSPACE_FLAGS = {"-w", "-ws"}
DELETE_WORDS = ("rm", "remove-item", "ri", "del", "erase", "rd", "rmdir")


def _nm_recursive_delete(args) -> bool:
    """True when the delete arguments hold a recursive flag: `-r`, `-R`, `-rf`, `--recursive`, or
    a PowerShell `-Recurse` spelled in full or in part."""
    for arg in args:
        flag = arg.lower()
        if flag == "--recursive" or (len(flag) > 1 and "-recurse".startswith(flag)) or (
                re.fullmatch(r"-[rfivd]*r[rfivd]*", flag)):
            return True
    return False


def is_link(path: str) -> bool:
    """True for a symlink, or a junction. A junction is a reparse point: `os.path.isjunction` reads
    it only from Python 3.12, so the file attribute is read instead."""
    if os.path.islink(path):
        return True
    if os.name != "nt":
        return False
    try:
        return bool(os.stat(path, follow_symlinks=False).st_file_attributes
                    & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return False


def _nm_inside(arg: str, where: str) -> str:
    """The folder whose `node_modules` this path reaches into, or '' when it names no file inside
    one. `node_modules` alone is the link itself, so it names none."""
    parts = arg.replace("\\", "/").split("/")
    for at, part in enumerate(parts):
        if part.lower() == "node_modules":
            return _absolute("/".join(parts[:at]) or ".", where) if at + 1 < len(parts) else ""
    return ""


def npm_prefix(where: str) -> str:
    """The folder npm installs into, as `npm prefix` finds it: the first folder from `where` upward
    that holds a package.json or a node_modules. With none up to the drive root, npm uses `where`."""
    folder = where
    while True:
        if any(os.path.lexists(os.path.join(folder, name)) for name in ("package.json", "node_modules")):
            return folder
        parent = os.path.dirname(folder)
        if parent == folder:
            return where
        folder = parent


def npm_prefix_flag(words, where: str) -> str:
    """The folder `--prefix <dir>` or `--prefix=<dir>` names, from `where` when relative, else ''. npm uses
    that folder as the prefix as it stands, with no walk upward. The last flag wins, as in npm."""
    value = ""
    for at, word in enumerate(words):
        if word == "--prefix" and at + 1 < len(words):
            value = words[at + 1]
        elif word.startswith("--prefix="):
            value = word[len("--prefix="):]
    value = value.strip("\"'")
    if "$" in value or "`" in value or value.startswith("~"):
        return ""  # the shell fills these in, so the guard cannot name the folder: the walk from `where` decides
    return os.path.join(where, value) if value else ""


def linked_nm_hit(segment: str, where: str) -> str:
    """Return the matched text when one segment runs a dependency install in `where`, or a
    recursive delete of what is inside a `node_modules`, and that `node_modules` is a link, else ''."""
    def delete(args):
        if _nm_recursive_delete(args) and any(
                (folder := _nm_inside(arg, where)) and is_link(os.path.join(folder, "node_modules"))
                for arg in args):
            return "recursive delete inside a linked node_modules"
        return ""

    def install(args):
        # A `)` glued to the last word closes the subshell or substitution the command sits in.
        words = [arg.rstrip(")") for arg in args]
        subcommand, at = "", 0
        while at < len(words):
            if words[at] in NPM_VALUE_FLAGS:
                at += 2
            elif words[at].startswith("-"):
                at += 1
            else:
                word = words[at].lower()
                version_in_workspace = word == "version" and any(
                    flag in NPM_WORKSPACE_FLAGS or flag.startswith("--workspace") for flag in words)
                # `audit` rewrites the install when `fix` follows it, after any flag.
                if word not in NPM_READ_ONLY or (word == "audit" and "fix" in words[at + 1:]) or (
                        version_in_workspace):
                    subcommand = word
                if word in NPM_DRY_RUN_WRITERS:
                    words = [flag for flag in words if flag != "--dry-run"]
                break
        if subcommand and not NPM_NO_CHANGE.intersection(words) and is_link(
                os.path.join(npm_prefix_flag(words, where) or npm_prefix(where), "node_modules")):
            return "npm " + subcommand + " in a folder whose node_modules is a link"
        return ""

    return (_command_hit(segment, DELETE_WORDS, delete, flagged=True)
            or _command_hit(segment, ("npm", "npm.cmd"), install))


LINKED_NM_REASON = (
    "node_modules here is a link to another checkout's install, and this command would change that "
    "install through the link, for every checkout that shares it. "
    "Remedy: replace the link with a real folder first, for example with the repo's setup script "
    "(npm run setup where it exists), then run the command again. "
    "(decision guard-linked-node-modules, a command that would change another checkout's install through a link is refused)"
)


DELETE_REASON = (
    "Rule (shared trees): this deletes a whole root, a home directory or everything a "
    "glob matches. The loss reaches files that no session here can see. "
    "Remedy: name the one directory you mean, under the project or under the scratchpad."
)

# THE CMD.EXE VERBS. `rd`/`rmdir` and `del`/`erase` take slash flags, never `rm`'s or
# `Remove-Item`'s dash flags, so neither pattern above ever reads them: `/s` is the recurse
# switch, and `/q` (optional, never required) only silences the confirmation prompt.
# `rd /s /q C:\Users\x`, `cmd /c rd /s /q %USERPROFILE%` and `del /s /q C:\*` deny, as their twins do.
#
# Checked by TOKENS, not by a whole-string search like the two patterns above, so a name sitting
# inside a quoted argument or a grep pattern never reads as a command: `echo "rd /s /q"` and
# `grep "del /s" notes.md` are text, and neither segment's own command word is `rd` or `del`.
# `segment_tokens` is quote-aware for the same reason `split_segments` is (see its own comment),
# and this reads `cmd`, the backslash-normalized text, same as the patterns above, so a token can
# be compared to `WIDE_TARGET` with no backslash left to confuse it.
#
# `cmd /c` and `cmd.exe /c` are unwrapped IN PLACE, deliberately, rather than folded into the
# shared `COMMAND_WRAPPERS` every rule reads: that set feeds `resolve_command`, which rules 2 and
# 3 also call, and widening it here would change what THEY skip past too.
CMD_EXE_DELETE_WORDS = {"rd", "rmdir", "del", "erase"}


def cmd_exe_delete_hit(segment: str) -> str:
    """Return the matched text when one segment runs a cmd.exe recursive delete at a
    root, a home or a glob, else ''.

    Reached directly, or through a `cmd /c`/`cmd.exe /c` prefix, from either shell.
    """
    tokens = segment_tokens(segment)
    if not tokens:
        return ""
    index = 0
    if (len(tokens) >= 2 and basename(tokens[0]) in CMD_EXE_NAMES
            and tokens[1].lower() == "/c"):
        index = 2
    if index >= len(tokens):
        return ""
    word = tokens[index]
    if basename(word) not in CMD_EXE_DELETE_WORDS:
        return ""
    rest = tokens[index + 1:]
    if not any(arg.lower() == "/s" for arg in rest):
        return ""
    for arg in rest:
        if re.fullmatch("(?i)" + WIDE_TARGET, arg):
            return word + " /s " + arg
    return ""


PUSH_REASON = (
    "Rule (Git): a forced push can overwrite newer remote work with a stale copy. "
    "The sha is the tip your own last push left, so record it when you push; never one read after a "
    "fetch, which accepts whatever the fetch brought in. "
    "Remedy: retry with --force-with-lease=<branch>:<sha>."
)
PUSH_MAIN_REASON = (
    "Rule (Git): this push writes the default branch, main or master. Main moves only by pull request "
    "(rule git-main-only-by-pr, decision plain-push-asks). Approving the prompt lets this one push through; it is not a grant."
)
PUSH_STRAY_REASON = (
    "Rule (Git): this push writes a branch name other than the one this branch tracks (its upstream), "
    "so it may land on a stray branch, and no such branch exists on the remote yet (rule push-stray-branch, "
    "decision plain-push-asks). Name the destination: `git push origin HEAD:<branch>`. "
    "Approving the prompt lets this one push through; it is not a grant."
)
PUSH_ALL_REASON = (
    "Rule (Git): this push sends every branch, and it may update the default branch on the remote: the "
    "remote-tracking ref for it is missing or differs from the local one (rule push-all-main, decision plain-push-asks). "
    "Remedy: push the lane's own branch by name: `git push origin HEAD:<lane-branch>`."
)
PUSH_ALL_AGENT_REASON = (
    "Rule (Git): this push sends every branch it matches, and a local branch named like an agent worktree "
    "(agent-<hex>, claude/agent-<hex> or worktree-agent-<hex>) is among them (rule push-all-main, decision "
    "plain-push-asks). Remedy: push the lane's own branch by name: `git push origin HEAD:<lane-branch>`."
)
PUSH_AGENT_REASON = (
    "Rule (Git): this push writes a branch named like an agent worktree (agent-<hex>, "
    "claude/agent-<hex> or worktree-agent-<hex>), not a lane branch (decision plain-push-asks). "
    "Remedy: push the lane's own branch by name: `git push origin HEAD:<lane-branch>`."
)
PUSH_ASK_REASON = (
    "Rule (Git): this forced push may rewrite the default branch, or its target is unreadable. "
    "The click in this prompt is the grant."
)

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
