"""The guard's shared code: stream encoding, shell segments, heredoc bodies, git call parsing,
command roots, the worktree rules, the config folder, and the log.

guard.py is the only entry point. It loads this module from its own folder.
Other files reach these names through `guard`. The git and session reads (`_git`, the primary
checkout, a tree's status, the default branch, a branch's proof, session liveness) live in
git_reads.py, shared with the janitor: a test or the janitor that patches one of them patches it
there, on the one object that every caller reads.
"""
import ast
import copy
import errno
import functools
import io
import json
import os
import re
import shlex
import sys
import time
import tokenize
from datetime import datetime

# No try/except: a guard copy without git_reads.py judges nothing, so it fails closed (guard.py).
from git_reads import (  # noqa: F401
    PROCESS_START_UNREADABLE, SESSION_LIVE_TOLERANCE_MS, _common_dir, _git, _inside_work_tree,
    _path_identity, _process_start_ms, _process_start_ms_windows, _under_by_identity,
    branch_cherry_empty, branch_is_ancestor, branch_is_empty, branch_on_remote, branch_proof,
    clone_checkouts, dirty_paths_are_pushed_copies, git_common_dir, is_worktree, porcelain,
    primary_checkout, read_default_base,
    resolve_default_base, session_is_live, session_records, stash_stack, worktree_live_session,
    worktree_locked,
)


def is_cloud() -> bool:
    """True in a Claude Code cloud session: CLAUDE_CODE_REMOTE is exactly "true". Read at each call. The one home of the
    cloud check; the load brake and its report stand down here, because the brake is local-only."""
    return os.environ.get("CLAUDE_CODE_REMOTE") == "true"


# ------------------------------------------------------------------ the stream encoding
#
# MEASURED 2026-09-09 in a Claude Code session on Windows: `sys.stderr.encoding` was `cp1252`, so
# an em dash in a refusal was written as the single byte 0x97. Claude Code decodes the stream as
# UTF-8, and 0x97 is not valid UTF-8, so it arrived as one replacement character.
#
# ONE replacement character per em dash is the whole measurement, and it names the direction. cp1252
# bytes read as UTF-8 give exactly that. UTF-8 bytes read as cp1252 would have given three mojibake
# characters instead. So the consumer was right and the writer was wrong.
#
# It is not cosmetic. A refusal exists to SAY what to do instead. A mangled dash is merely ugly, but
# the same corruption on a path or a flag would destroy the remedy the message carries.
#
# It never raises. `reconfigure` landed in Python 3.7 and a stream can be something other than a
# text wrapper, so a failure here leaves the old encoding rather than bricking the hook.
def _force_utf8_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


SHELL_TOOLS = ("Bash", "PowerShell")
READ_ONLY_TOOLS = ("Read", "Grep")
WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def norm(path: str) -> str:
    return path.replace("\\", "/")


# A subshell or substitution paren glued to the command word (`(git`, `$(git`): the word is git.
GLUED_OPEN = re.compile(r"^(?:\$?\()+(?=.)")
# An apostrophe inside a word (`don't`, `it's`) is text, never an opening quote. The suffix must
# end the word: `-e's/a/b/'` and `x'd'` are quoted arguments, so `/` and `'` after it fail.
CONTRACTION = re.compile(r"(?<=[A-Za-z])'(?:t|s|re|ll|ve|d|m)(?=[\s.,;:!?)]|$)")


def is_contraction(text: str, index: int, closes_after: bool = False) -> bool:
    """True when the `'` at `index` has a contraction's shape and bash never closes it: no `'`
    follows it in `text`, nor after `text` when `closes_after`. Bash ends a quote at the next `'`
    wherever it sits, so `echo a's b'; pkill foo` quotes `s b`. With no later `'`, bash runs
    nothing after the mark, so reading it as text hides nothing. Each find stops at the next `'`:
    one pass in all."""
    return (not closes_after and bool(CONTRACTION.match(text, index))
            and text.find("'", index + 1) < 0)


# What shlex and the PowerShell reader drop from a name: a quote inside it, a backslash, backtick
# or caret escape, a line continuation. A rule's quick test strips these from the command text,
# then looks for its names: a miss means no token can name them. It may over-match, never under,
# only when the rule's walk drops nothing more from a token before it reads a name. A walk that
# drops more (git-env: printf directives) needs its quick test to cover that step too. One known
# under-match: the walk's .upper() folds the ligature U+FB01 to FI and the quick test does not;
# Windows keeps such a name as its own variable, so no git variable is set.
QUOTE_MARKS = re.compile(r"""['"`\\^\s]""")


def basename(token: str) -> str:
    if token[:1] in ("(", "$"):   # only these open a glued paren; most tokens skip the regex
        token = GLUED_OPEN.sub("", token)
    return token.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()


class PowerShellScript(str):
    """Text that pwsh or `cmd /c` reads, not bash. Every reader of the text takes PowerShell's rules,
    where a backslash is a path character, so a path that ends in one hides no `;` or `&&`: the
    quote walk, `split_segments` and `segment_tokens`, all through `is_powershell`.
    `split_segments` hands back each segment of such a text with the same type, so the reading
    follows the text to the rule that judges it. Every producer of such text (`_pwsh_script`, a
    `cmd /c` tail, the iex arm of `nested_script`) returns this type."""


class PosixScript(str):
    """Text that `sh -c` or `bash -c` runs (`inline_script`): read with bash's rules, even in a
    PowerShell call. `split_segments` keeps the type on each segment, as for PowerShellScript."""


def is_powershell(text) -> bool:
    """True when `text` is read with PowerShell's rules: the tool is PowerShell, or the text is a
    script that pwsh or `cmd /c` runs. A PosixScript never is."""
    return not isinstance(text, PosixScript) and (
        POWERSHELL_CALL[0] or isinstance(text, PowerShellScript))


@functools.lru_cache(maxsize=8, typed=True)   # typed: a PosixScript is not its plain twin
def _split_segments_cached(cmd: str, powershell: bool):
    # powershell is part of the key: split_segments reads POWERSHELL_CALL[0] and the text's type
    return tuple(split_segments(cmd, []))


# ------------------------------------------------------------------ the quote walk
#
# ONE QUOTE WALK. `_split_reading` cuts segments with it and `walk_quotes` hands the same steps to
# a rule that must know whether a character sits inside quotes. `quote` is "", `'`, `"`, or `$'` (a
# bash ANSI-C string). A backslash escapes the next character outside quotes and inside `"..."` or
# `$'...'`, a backslash too, so `\"` neither opens nor closes a quote and `\\'` opens one; inside
# `'...'` it escapes nothing. PowerShell text takes PowerShell's rules: a backslash is a path
# character; a backtick escapes the next character outside quotes and inside `"..."`; `''` inside
# `'...'` and `""` inside `"..."` are one literal quote; `<# ... #>` is a comment (state `<#`) and
# `@"` or `@'` at a line's end opens a here-string that ends at `"@` or `'@` on a line's start
# (state `@"` or `@'`). Each opens only at a token start (`token_start`); mid-word it is text.
# Quotes inside either span open nothing. An opener with no closer is a parse PowerShell cannot
# finish, and the walk cannot tell where it ends: the rest reads BLIND, with no quote, escape or
# comment, so every redirect and `;` after it stays visible. A `sh -c` script is bash text in any
# call (PosixScript).
BLIND = "?"
HERE_OPEN = re.compile(r"@(['\"])[ \t]*\r?\n")
# PowerShell opens `<#` or `@'` only at a token's start: mid-word (`a<#`, `foo@'`) each is text.
# The characters after which a token starts, read off PowerShell's own parser (2026-10-15). `=`,
# `)`, `}` and `&` are left out: an opener after one reads as text, which shows more, never less.
TOKEN_BOUNDARY = " \t\r\n;|,({"


def token_start(text: str, index: int) -> bool:
    """True when a PowerShell token starts at `index`: the text's start, or after an unescaped
    TOKEN_BOUNDARY character (`` `; `` is text, so no token starts after it)."""
    return index == 0 or (text[index - 1] in TOKEN_BOUNDARY and text[index - 2:index - 1] != "`")


def quote_advance(text: str, index: int, quote: str):
    """Step the walk over `text[index]`: (width consumed, the quote open after it). An escaped
    pair is one step of width 2. A contraction is the caller's to skip (`is_contraction`)."""
    char = text[index]
    powershell = is_powershell(text)
    if quote == BLIND:
        return 1, BLIND
    if quote and powershell:
        if quote == "<#":
            return (2, "") if text.startswith("#>", index) else (1, quote)
        if quote[0] == "@":
            closer = "\n" + quote[1] + "@"
            return (len(closer), "") if text.startswith(closer, index) else (1, quote)
        if (char == "`" and quote == '"') or (char == quote and text[index + 1:index + 2] == quote):
            return 2, quote
        return 1, ("" if char == quote else quote)
    if quote:
        if char == "\\" and quote != "'":
            return 2, quote
        return 1, ("" if char == quote[-1] else quote)
    if powershell:
        if char == "`":
            return 2, ""
        opener = token_start(text, index) and HERE_OPEN.match(text, index)
        if token_start(text, index) and text.startswith("<#", index):
            return 2, ("<#" if text.find("#>", index + 2) >= 0 else BLIND)
        if opener:
            closer = "\n" + opener.group(1) + "@"
            return 2, ("@" + opener.group(1) if text.find(closer, index + 2) >= 0 else BLIND)
    if char == "\\" and not powershell:
        return 2, ""   # `\\` is one escaped backslash, so a quote after the pair opens
    if char == "$" and not powershell and text[index + 1:index + 2] == "'":
        return 2, "$'"   # read at the `$`, so an escaped `\$'` opens a plain quote
    if char in ("'", '"'):
        return 1, char
    return 1, ""


def walk_quotes(text: str):
    """Yield (index, char, quote open before it) over `text`, one step at a time. A contraction
    that bash never closes is text, as in `_split_reading`'s second reading. BLIND text yields as
    unquoted."""
    quote, index = "", 0
    while index < len(text):
        if not quote and text[index] == "'" and is_contraction(text, index):
            width, after = 1, ""
        else:
            width, after = quote_advance(text, index, quote)
        yield index, text[index], ("" if quote == BLIND else quote)
        quote, index = after, index + width


# ------------------------------------------------------------------ shell segments and command words
#
# ONE SHELL SEGMENT of the command. Each segment is judged on its own, so an allowed first half
# licenses nothing in the second half.
#
# QUOTE-AWARE, deliberately, and the only splitter left in the file. A blind split on `|` and
# `;` cuts a quoted argument that happens to hold one of those characters into a segment of its
# own, and whatever word lands first in that fragment then reads as a COMMAND. MEASURED: the
# owner's `grep -n -i "...|make reap|pkill..." CLAUDE.md` splits on the pipes INSIDE the quotes
# under a blind splitter, and one fragment starts with `pkill`. A rule that then judged the
# fragment's first word would deny a grep as if it were a kill.
def split_segments(cmd: str, ends=None):
    """Split into shell segments on unquoted `;`, `|`, `||`, `&&`, and newline.

    Quoted text, single or double, is copied whole into the current segment, so a delimiter
    inside a quote never starts a new one. An unterminated quote runs to the end of the string,
    which keeps the remainder inside it rather than guessing where it would have closed.

    THE COMMENT RULE, measured before it was written: without it, the `'` in `# the driver's
    shape` opens a quote that runs to the end of the text, and `guard-shell-selftest.sh`'s
    runaway-driver fixture — a script whose second line is exactly that comment — went from
    refused to ALLOWED once the parent's per-line reader was replaced by this function. An
    unquoted `#` that STARTS A WORD (index 0, or the previous character is space, tab,
    newline, `;`, `|`, `&`, or `(`) is a comment to the end of its line — the shell's own
    rule. `fix#3` and `'#300'` are not comments under it.

    `ends`, when a list, gets what closed each segment (`|`, `||`, `&&`, `;`, newline, or '' for
    the last), so a caller can tell a segment whose stdout is piped onward from the rest.
    """
    if ends is None:   # the same command is split by many rules: split it once
        return list(_split_segments_cached(cmd, is_powershell(cmd)))
    segments, open_quote, shaped = _split_reading(cmd, ends, False)
    if open_quote and shaped:   # bash leaves a quote open: read each contraction as text too
        segments += _split_reading(cmd, ends, True)[0]
    if isinstance(cmd, PosixScript):   # each segment keeps the reading of the text it was cut from
        segments = [PosixScript(segment) for segment in segments]
    elif is_powershell(cmd):
        segments = [PowerShellScript(segment) for segment in segments]
    return segments


def _split_reading(cmd: str, ends, contractions_are_text: bool):
    """One reading of split_segments: (segments, the quote open at the end, whether an unquoted
    `'` has a contraction's shape). The first reading is bash's own: every unquoted `'` opens a
    quote, so a call bash runs is always in a segment. When that reading ends inside a quote, bash
    runs nothing past the open mark, yet `echo don't; wsl --shutdown` must still show its call: a
    second reading takes each contraction-shaped `'` (CONTRACTION) as text, and its segments are
    judged too. Two linear passes; no `'` reads the rest of the command again."""
    segments = []
    current = []
    quote = ""
    shaped = False
    powershell = is_powershell(cmd)
    index = 0
    length = len(cmd)
    while index < length:
        char = cmd[index]
        if quote == BLIND:   # PowerShell text the walk cannot read: no quote, escape or comment
            if char in ("'", '"', "`", "#", "<", "@"):
                current.append(char)
                index += 1
                continue
        elif quote:
            width, after = quote_advance(cmd, index, quote)
            if quote != "<#":
                current.append(cmd[index:index + width])
            elif not after:
                current.append(" ")   # a block comment is dropped, and it ends a word
            quote = after
            index += width
            continue
        if char == "#" and (index == 0 or cmd[index - 1] in " \t\n;|&("):
            while index < length and cmd[index] != "\n":
                index += 1
            continue
        if char == "\\" and cmd[index + 1:index + 2] == "\n" and not powershell:
            index += 2   # a POSIX backslash-newline is a continuation; in PowerShell it ends a path
            continue
        if char == "'" and CONTRACTION.match(cmd, index):
            shaped = True
            if contractions_are_text:
                current.append(char)   # `don't` as text: it must not hide the rest of the command
                index += 1
                continue
        # The quote walk owns every escape, `$'`, and each PowerShell span, so `\;` and `` `; `` are
        # text and cut no segment.
        if char in ("'", '"') or (not powershell and (
                char == "\\" or cmd[index:index + 2] == "$'")) or (
                powershell and (char == "`" or token_start(cmd, index) and (
                    cmd.startswith("<#", index) or HERE_OPEN.match(cmd, index)))):
            width, quote = quote_advance(cmd, index, "")
            if quote != "<#":
                current.append(cmd[index:index + width])
            index += width
            # Escaped ampersand, then `&`: the pair is a literal `&`, and the second `&` is bash's
            # own background operator, which ends the command. `&&` and `&>` are read as they stand.
            if (cmd[index - 2:index] == "\\&" and cmd[index:index + 1] == "&"
                    and cmd[index + 1:index + 2] not in ("&", ">")):
                segments.append("".join(current))
                ends is None or ends.append("&")
                current = []
                index += 1
            continue
        if char == "&" and cmd[index:index + 2] == "&&":
            segments.append("".join(current))
            ends is None or ends.append("&&")
            current = []
            index += 2
            continue
        if char == "|" and cmd[index - 1:index] == ">":
            current.append(char)   # `>|` overrides noclobber: a redirect, no pipe
            index += 1
            continue
        if char == "|":
            width = 2 if cmd[index:index + 2] == "||" else 1
            ends is None or ends.append(cmd[index:index + width])
            index += width
            segments.append("".join(current))
            current = []
            continue
        if char in (";", "\n"):
            segments.append("".join(current))
            ends is None or ends.append(char)
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    segments.append("".join(current))
    ends is None or ends.append("")
    return segments, ("" if quote == BLIND else quote), shaped


# A leading `VAR=value` assignment, which is not a segment's command. Shared with the
# environment layer below, so the two never drift into judging an assignment two different ways.
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# PowerShell's own assignment, `$name = value`, is two tokens under shlex: `$sg` then `=`. MEASURED
# against a real launch, `$sg = Start-Process npx ... -PassThru`, the shape PowerShell's remedy for
# rule 2b recommends. `resolve_command` skips it: `$sg` as the command word matches no rule's tool
# name, so every command-word rule would miss the real command after it.
POWERSHELL_ASSIGNMENT = re.compile(r"^\$[A-Za-z_][A-Za-z0-9_]*$")

# A wrapper that runs another program in its place, so the CALLED program is a segment's real
# command word, not the wrapper. `xargs pkill foo` runs pkill, so `xargs` unwraps the same as
# the rest: the token after it, once its own flags are skipped, is what actually runs.
COMMAND_WRAPPERS = {"sudo", "env", "command", "nohup", "nice", "time", "doas", "xargs",
                    "timeout", "verdict", "python", "python3", "exec", "builtin", "!", "&",
                    "busybox", "stdbuf", "watch"}
# The flags of a wrapper that take the NEXT word as their value: `nice -n 5 git` runs git, not `5`.
# Long flags are listed too: `sudo --user root git ...` runs git. A `--flag=value` is one token and
# needs no entry.
WRAPPER_VALUE_FLAGS = {
    "nice": {"-n", "--adjustment"},
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string", "-P"},
    "time": {"-f", "--format", "-o", "--output"}, "exec": {"-a"},
    "watch": {"-n", "--interval", "-q", "--equexit"},
    "doas": {"-u", "-C"},
    "xargs": {"-n", "--max-args", "-P", "--max-procs", "-I", "-L", "--max-lines", "-s",
              "--max-chars", "-d", "--delimiter", "-E", "-a", "--arg-file"},
    "sudo": {"-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt", "-C",
             "--close-from", "-D", "--chdir", "-R", "--chroot", "-T", "--command-timeout",
             "-r", "--role", "-t", "--type", "-U", "--other-user"},
}
# Runners that `wrapped_commands` reads, and the value flags of `stdbuf` (also a wrapper above) and of
# the runners that are no `COMMAND_WRAPPERS` entry. They sit here so `_wrapper_flags` skips the same way.
WRAPPER_VALUE_FLAGS.update({
    "stdbuf": {"-i", "-o", "-e"}, "caffeinate": {"-t", "-w"},
    "flock": {"-w", "-E", "--timeout", "--conflict-exit-code"},
    "docker": {"-e", "--env", "-u", "--user", "-w", "--workdir", "--env-file", "--detach-keys"},
    "podman": {"-e", "--env", "-u", "--user", "-w", "--workdir", "--env-file", "--detach-keys"},
})
# `timeout` and `python` unwrap only in their wrapper shape: `timeout [flags] DURATION cmd` (Windows
# `timeout /t 5` is the waiter, not a wrapper) and `python bin/verdict cmd` (the repo's runner).
DURATION = re.compile(r"^\d+(\.\d+)?[smhd]?$")
TIMEOUT_FLAGS_WITH_VALUE = {"-k", "-s", "--kill-after", "--signal"}
TIMEOUT_FLAGS_BARE = {"--preserve-status", "--foreground"}
WRAPPER_VALUE_FLAGS["timeout"] = TIMEOUT_FLAGS_WITH_VALUE

# A leading shell keyword that opens or joins a control-flow block, never a command itself.
# `split_segments` cuts on `;`, so the segment after a loop's own semicolon starts with `do`, and
# the word after THAT is the command. MEASURED against the live guard: `while ! pgrep -f server;
# do sleep 1; done` allowed the sleep, because the segment `do sleep 1` resolved to `do` as its
# command word. Skip a keyword the same way a wrapper is skipped, so every rule that reads a
# command word sees the command inside the block, never the keyword that opens it.
LOOP_KEYWORDS = {"do", "then", "else", "elif", "while", "until", "if", "{", "(", "$("}


# What a PowerShell backtick escape stands for, outside quotes and inside `"..."` (parser, 2026-10-15).
BACKTICK_CHARS = {"n": "\n", "r": "\r", "t": "\t", "0": "\0", "a": "\a", "b": "\b", "e": "\x1b",
                  "f": "\f", "v": "\v"}
BACKTICK_UNICODE = re.compile(r"\{([0-9A-Fa-f]{1,6})\}")   # pwsh 6+: `u{3b} is `;`


def _powershell_values(segment: str) -> str:
    """PowerShell text spelled for posix shlex, so each token is the value PowerShell hands on. A
    backtick escape outside quotes or inside `"..."` is the character it stands for; `''` inside
    `'...'` and `""` inside `"..."` are one literal quote. Read as it stands, shlex keeps the
    backticks and drops the pairs, so the script a `pwsh -c` or `iex` hands on is read with escapes
    the outer string has already spent. The quote walk finds each pair (a width-2 step)."""
    segment = PowerShellScript(segment)
    out, quote, index = [], "", 0
    while index < len(segment):
        width, after = quote_advance(segment, index, quote)
        step = segment[index:index + width]
        if width == 2 and quote == "'":
            step = "'\\''"
        elif width == 2 and quote == '"' and step == '""':
            step = '\\"'
        elif len(step) == 2 and quote in ("", '"') and step[0] == "`":   # a last lone `` ` `` stays
            char = BACKTICK_CHARS.get(step[1], step[1])
            unicode = step[1] == "u" and BACKTICK_UNICODE.match(segment, index + 2)
            if unicode and int(unicode.group(1), 16) <= 0x10FFFF:
                char = chr(int(unicode.group(1), 16))
                width += len(unicode.group(0))
            if step[1] == "\\":
                step = "\\"   # the first half of a doubled backslash: the second half follows
            elif not quote:
                step = " " if step[1] in "\r\n" else "\\" + char   # `` `<newline> `` continues the line
            else:
                step = "\\" + char if char in '"\\' else char
        out.append(step)
        quote, index = after, index + width
    return "".join(out)


def segment_tokens(segment: str):
    """Tokenize one segment with shlex, or return None when it cannot be parsed.

    An unmatched quote or a stray backslash means the guard cannot tell what the segment would
    run. That must fail open, this file's existing stance: judge nothing rather than guess.
    """
    # PowerShell's escape is the backtick, so a backslash there is a path separator. Doubling it
    # keeps posix shlex from eating it (`C:\\repo` would read as `C:repo`).
    source = ""
    if is_powershell(segment):
        segment = segment.replace("\\", "\\\\")
        if "''" in segment or '""' in segment or "`" in segment:
            segment = _powershell_values(segment)
    elif "`" in segment:
        source = segment   # bash text: shlex keeps its backtick substitutions as they stand
    found = _segment_tokens(segment)
    if found is None:
        return None
    tokens, quoted = found
    if not quoted and not source:
        return list(tokens)   # no quoted opener to mark: a plain list, built once per call
    tokens = _Tokens(tokens)
    tokens.quoted = quoted
    tokens.bash_source = source
    return tokens


def _spent_by_bash(tokens):
    """`tokens` read again from their bash text with each backtick substitution outside single
    quotes cut to `x`: bash spends those backticks before pwsh or iex reads the script, so a
    `` `; `` there is no PowerShell escape. A backtick in single quotes reaches the script. Else
    `tokens` as they are."""
    source = getattr(tokens, "bash_source", "")
    if not source:
        return tokens
    marks = [index for index, char, quote in walk_quotes(source) if char == "`" and quote not in ("'", "$'")]
    out, last = [], 0
    for start, end in zip(marks[::2], marks[1::2]):
        out += [source[last:start], "x"]
        last = end + 1
    return segment_tokens(type(source)("".join(out) + source[last:])) or tokens


# A token that opens a subshell, a substitution, or a PowerShell block or group.
_GROUP_OPEN = re.compile(r"[&.$@]?[({]")


class _Tokens(list):
    """A segment's tokens, plus `quoted`: the indexes of tokens whose opening `(`, `$(` or `{` sat
    inside quotes, which makes it text, never a subshell or a script block. `command_indexes` and
    the git-env PowerShell reader read it. `bash_source` is the bash text, when it holds a
    backtick (`_spent_by_bash`)."""
    quoted = frozenset()
    bash_source = ""


def _quoted_opens(segment: str, count: int):
    """Indexes of the tokens that start inside quotes. Reads the segment again with quotes kept
    (non-POSIX shlex): a token that starts with `'`, or with `"` not followed by `$(`, is quoted
    text. When the two readings do not line up, state nothing: a paren then counts as a subshell."""
    try:
        raw = shlex.split(segment, posix=False)
    except ValueError:
        return frozenset()
    if len(raw) != count:
        return frozenset()
    return frozenset(i for i, t in enumerate(raw) if t[:1] == "'" or (t[:1] == '"' and t[1:3] != "$("))


@functools.lru_cache(maxsize=16384)   # holds every distinct segment of a 4000-rm command
def _segment_tokens(segment: str):
    """(the segment's tokens, `_Tokens.quoted` for them), or None when shlex cannot read it. Both
    come from one cache, so a call for a segment already read costs one lookup."""
    try:
        tokens = tuple(shlex.split(segment, posix=True))
    except ValueError:
        return None
    quoted = frozenset()
    if any(map(_GROUP_OPEN.search, tokens)):
        # A multi-line here-string (`@'`...`'@` or `@"`...`"@`) reads as one token `@...@` that
        # holds a newline. The non-POSIX reading cannot parse it, so its text is claimed here.
        here = frozenset(i for i, t in enumerate(tokens) if t[:1] == t[-1:] == "@" and "\n" in t)
        quoted = _quoted_opens(segment, len(tokens)) | here
    return tokens, quoted


POWERSHELL_CALL = [False]   # set per call by judge_shell: the tool being judged is PowerShell


def _skip_assignments_and_keywords(tokens, index=0):
    """Return the index of the first token that is neither an assignment (POSIX `VAR=value` or
    PowerShell `$name` `=`) nor a leading loop keyword, starting from `index`. Shared by
    `resolve_command`, which then unwraps wrappers from there, and by the detached-launch
    checks below, which must see a wrapper such as `nohup` BEFORE any unwrap, not after."""
    end = len(tokens)
    while index < end:
        if ASSIGNMENT.match(tokens[index]) or tokens[index] in LOOP_KEYWORDS:
            index += 1
            continue
        if tokens[index][:1] == "(" and ASSIGNMENT.match(tokens[index][1:]):
            index += 1   # `(VAR=x cmd`: a subshell paren glued to the first assignment
            continue
        if (POWERSHELL_ASSIGNMENT.match(tokens[index]) and index + 1 < end
                and tokens[index + 1] == "="):
            index += 2
            continue
        break
    return index


def resolve_command(tokens):
    """Return the index of the command word in a tokenized segment, or None when it names none.

    Skips leading `VAR=value` assignments and leading loop keywords (`do`, `then`, `else`,
    `elif`, `while`, `until`, `if`, `{`, `(`), then unwraps command wrappers (`sudo`, `env`,
    `command`, `nohup`, `nice`, `time`, `doas`, `xargs`) along with each wrapper's own flags and
    any assignment it takes ahead of the program name, so the index returned is the program that
    actually runs, never the keyword or the wrapper carrying it there.
    """
    return _walk_wrappers(tuple(tokens))[0]


def _wrapper_flags(word: str, tokens, index: int):
    """Read a wrapper's flags from `index`, getopt-style. Return (the index after them,
    [(flag, value)]). A short-flag cluster is read letter by letter: the first letter that takes a
    value (WRAPPER_VALUE_FLAGS) takes the rest of the cluster, or the next word when it is the last
    letter. So `sudo -Eu root cmd`, `xargs -rn 1 pkill` and `env -iS 'cmd'` each skip the value."""
    takes = WRAPPER_VALUE_FLAGS.get(word, ())
    end = len(tokens)
    found = []
    while index < end and tokens[index].startswith("-"):
        token = tokens[index]
        index += 1
        if token.startswith("--"):
            flag, glued, value = token.partition("=")
            if not glued and flag in takes:
                value = tokens[index] if index < end else ""
                index += 1
            found.append((flag, value))
            continue
        for at in range(1, len(token)):
            flag = "-" + token[at]
            if flag not in takes:
                found.append((flag, ""))
                continue
            value = token[at + 1:]
            if not value:
                value = tokens[index] if index < end else ""
                index += 1
            found.append((flag, value))
            break
    return index, found


@functools.lru_cache(maxsize=4096)   # every rule asks again for each segment of a long command
def _walk_wrappers(tokens):
    """Return (the command word's index or None, ((wrapper, its flags), ...)): the one walk
    `resolve_command` and `_env_split_string` both read."""
    end = len(tokens)
    index = _skip_assignments_and_keywords(tokens)
    chain = []
    while index < end and basename(tokens[index]) in COMMAND_WRAPPERS:
        word, start = basename(tokens[index]), index
        index, flags = _wrapper_flags(word, tokens, index + 1)
        chain.append((word, tuple(flags)))
        if word == "timeout" and not (index < end and DURATION.match(tokens[index])):
            return start, tuple(chain)
        if word == "timeout":
            index += 1
        if word in ("python", "python3"):
            if not (index < end and basename(tokens[index]) == "verdict"):
                return start, tuple(chain)
            index += 1
        while index < end and ASSIGNMENT.match(tokens[index]):
            index += 1
    return (index if index < end else None), tuple(chain)


# ------------------------------------------------------------------ heredoc bodies
#
# A heredoc body is DATA being written, not a command being run. A commit message that DISCUSSES a
# refused command must not trip the guard.
#
# The HEADER LINE is kept, so a redirect in the header still counts as a write:
# `cat <<'EOF' > .claude/settings.json` writes the settings file.
#
# EXCEPTION: a heredoc fed to an interpreter can be executed, so the body stays under inspection.
# The interpreter is a WORD of the header line: not a part of a file name (`node-notes.md`), and not
# the value of a message flag of a commit or a pull request (`gh pr create --title "node 20 bump"`).
# Other quoted text still counts: the shell word of `ssh host "bash -s" <<EOF` runs its body.
# SHELL_HEREDOC names the shells alone: a rule that reads shell lines keeps only a body a shell
# runs, never a Python or Node script.
# The delimiter is the whole shell word, read as bash reads it: a backslash, a single-quoted run or a
# double-quoted run inside it is dequoted, so `E\OF`, `E'OF'` and `"E"OF` all close at a line `EOF`
# (heredoc_delimiter). An unquoted word ends at a blank or a shell operator.
HEREDOC_HEADER = re.compile(
    r"""<<-?[ \t]*((?:\\.|'[^'\n]*'|"(?:\\.|[^"\\\n])*"|[A-Za-z_])(?:\\.|'[^'\n]*'|"(?:\\.|[^"\\\n])*"|[^\s'"\\|&;<>()])*)""")
_WORD_PART = re.compile(r"""\\(.)|'([^']*)'|"((?:\\.|[^"\\])*)"|(.)""", re.S)


def heredoc_delimiter(word: str):
    """Return (quote, delimiter): the delimiter as bash reads it. `quote` is "'" when the word STARTS
    with a quoted or escaped part (the body is then text), else ''. A quote later in the word
    (a backslash or a quote after the first character) still dequotes the delimiter but leaves `quote` empty, so the body stays
    code to every reader: the same reading main gives it. Bash itself reads such a body as text; a
    body written to a file and run (`> x.sh && sh x.sh`) is the act this keeps refused."""
    quote = ""
    out = []
    for position, (escaped, single, double, plain) in enumerate(_WORD_PART.findall(word)):
        if plain:
            out.append(plain)
            continue
        quote = "'" if position == 0 else quote
        if single or double:
            out.append(re.sub(r"\\([$`\"\\])", r"\1", double) if double else single)
        else:
            out.append(escaped)
    return quote, "".join(out)


_SEGMENT_BREAK = re.compile(r"(&&|\|\||[;|\n])")


def _without_message_values(cmd: str) -> str:
    """Blank each message value of a commit or a pull request, so prose naming a shell reads as
    text. The blanking is guard_env's own (imported late: guard_env imports this file)."""
    if "commit" not in cmd and "create" not in cmd:
        return cmd
    from guard_env import _blank_messages
    return "".join(_blank_messages(part) for part in _SEGMENT_BREAK.split(cmd))


def _interpreter_header(words: str):
    # The word stands alone or ends a path or a name (`/usr/bin/bash`, `ts-node`, `node.cmd`);
    # the lookahead alone keeps `node-notes.md` and `bash-tips.md` text.
    return re.compile(r"(?<!\w)(?:" + words + r")(?:\.exe|\.cmd)?(?![\w.-])[^\n]*<<").search


_SHELLS = "bash|sh|zsh|dash|ksh|pwsh|powershell"
# A header whose heredoc pipes into a shell (`cat <<EOF | sh`, `... | ssh host bash -s`) or into xargs or source
# (`cat <<EOF | xargs sh -c`, `| source /dev/stdin`): the shell runs the body.
_PIPED_SHELL = re.compile(
    r"<<[^\n]*\|\s*(?:(?:sudo|env|exec)\s+)?(?:[^\s|;&]*[/\\])?(?:" + _SHELLS + r"|xargs|source)(?:\.exe|\.cmd)?(?![\w.-])"
    r"|<<[^\n]*\|\s*\.[ \t]"
    r"|<<[^\n]*\|\s*ssh\b[^\n|]*(?<!\w)(?:" + _SHELLS + r")(?![\w.-])").search
# A heredoc that eval, source or `.` runs: on its segment (`source /dev/stdin <<EOF`), or opened in a `$(`, `<(`
# or backtick that the word reads (`eval "$(cat <<EOF`, `. <(cat <<EOF`), on its line or a later one. The word
# stands in command position, so `cd .. && cat <<EOF` and `ls . <<EOF` stay text.
_FED_SHELL = re.compile(
    r"(?:^|[;&|(`{])[ \t]*(?:(?:builtin|command)[ \t]+)?(?:eval|source|\.)[ \t]"
    r"[^;&|\n]*?(?:(?:\$\(|<\(|`)[^;&|)`]*?)?<<", re.M).search
_SHELL_FIRST = _interpreter_header(_SHELLS)
_INTERPRETERS = _SHELLS + "|python[\\d.]*|perl|ruby|node"
_INTERPRETER_FIRST = _interpreter_header(_INTERPRETERS)


def SHELL_HEREDOC(text: str) -> bool:
    return bool(_SHELL_FIRST(text) or _PIPED_SHELL(text) or _FED_SHELL(text))


def INTERPRETER_HEREDOC(text: str) -> bool:
    return bool(_INTERPRETER_FIRST(text) or _PIPED_SHELL(text) or _FED_SHELL(text))


# The only characters heredoc_heads acts on when nothing is open.
_HEAD_MARKS = re.compile(r"""['"(#<]""")


def heredoc_heads(text: str, quote: str = "", closes_after: bool = False, legacy: bool = False):
    """Return ([(quote char, delimiter)], quote) for the heredoc headers in `text` that sit outside
    quotes and comments, in order, and what is still open at its end. `quote` is a stack of open
    quotes and parentheses. `echo "<<EOF"` and `<<<word` hold no header, but `-m "$(cat <<EOF` does:
    a `$(` inside double quotes is shell again. Quotes are read as bash reads them, with no escape:
    only a contraction bash never closes (is_contraction; `closes_after` says a `'` follows `text`)
    opens none. A mark read as text could show a header bash quotes, and drop a body bash runs.
    `legacy` reads each header with _MAIN_HEADER, as main did (the bandaid there)."""
    if not quote and not _HEAD_MARKS.search(text):
        return [], ""   # no quote, paren, comment or `<` to read: nothing opens, nothing is open
    heads = []
    index = 0
    while index < len(text):
        char = text[index]
        top = quote[-1:]
        if top == "'":
            quote = quote[:-1] if char == "'" else quote
        elif top == '"':
            if text.startswith("$(", index):
                quote += "("
                index += 1
            elif char == '"':
                quote = quote[:-1]
        elif char == "(":
            quote += "("
        elif char == ")" and top == "(":
            quote = quote[:-1]
        elif char == "#" and (index == 0 or text[index - 1] in " \t\n;|&("):
            while index < len(text) and text[index] != "\n":
                index += 1
            continue
        elif char == "'" and is_contraction(text, index, closes_after):
            pass
        elif char in "'\"":
            quote += char
        elif text.startswith("<<<", index):
            index += 3
            continue
        elif char == "<":
            header = (_MAIN_HEADER if legacy else HEREDOC_HEADER).match(text, index)
            if header:
                heads.append(header.groups() if legacy else heredoc_delimiter(header.group(1)))
                index = header.end()
                continue
        index += 1
    return heads, quote


def _split_heredocs(cmd: str, contractions_are_text: bool = False):
    """`_walk_heredocs` without its `unclosed` flag: (kept lines, [(quote, body, header)])."""
    kept, bodies, _ = _walk_heredocs(cmd, contractions_are_text)
    return kept, bodies


def _walk_heredocs(cmd: str, contractions_are_text: bool = False, legacy: bool = False,
                   kept_at: "list | None" = None):
    """Return (kept lines, [(quote, body, header)], unclosed): every header line kept, every body set apart,
    each body with the text of the header line that opened it (two headers share one line).
    The walk is bash's own reading, where a later `'` closes a contraction's mark. With
    `contractions_are_text` it is the second reading of split_segments: every contraction-shaped
    `'` is text, so `echo don't` then a `<<'B'` line shows its header. A caller that judges what
    bash runs walks both.
    The one walk `_drop_heredoc_bodies` and the environment layer both need. A header is read as
    heredoc_heads reads it, so one in quoted text, a comment or a here-string strips nothing.
    A caller that passes `kept_at` gets the line index of each kept line appended to it."""
    lines = cmd.split("\n")
    last = -1 if contractions_are_text else max(
        (i for i, line in enumerate(lines) if "'" in line), default=-1)
    kept = []
    bodies = []
    unclosed = False
    index = 0
    stack = ""
    while index < len(lines):
        kept.append(lines[index])
        if kept_at is not None:
            kept_at.append(index)
        header_line = lines[index]
        heads, stack = heredoc_heads(header_line, stack, index < last, legacy)   # a later line holds a `'`
        index += 1
        for quote, delimiter in heads:
            start = index
            while index < len(lines) and lines[index].strip() != delimiter:
                index += 1
            bodies.append((quote, "\n".join(lines[start:index]), header_line))
            if index < len(lines):
                index += 1  # drop the closing delimiter line too
            else:
                unclosed = True   # bash reads to the end of input, so a caller that judges runs reads on
    return kept, bodies, unclosed


def _drop_heredoc_bodies(cmd: str) -> str:
    """Drop the body of every heredoc, keeping every header line. The one loop
    `strip_heredoc_bodies` and `_strip_heredoc_bodies_unconditionally` both need: the first
    guards it with the interpreter exception, the second never does, and neither re-implements
    the walk itself."""
    lane_at, main_at = [], []
    _walk_heredocs(cmd, kept_at=lane_at)
    _walk_heredocs(cmd, legacy=True, kept_at=main_at)   # BANDAID: main's own walk, see _MAIN_HEADER
    if lane_at != main_at:
        keep = set(lane_at) | set(main_at)   # a line stays in view when either walk keeps it
        return "\n".join(line for at, line in enumerate(cmd.split("\n")) if at in keep)
    return "\n".join(_split_heredocs(cmd)[0])


# A file a heredoc header writes (`> f`, `>> f`, `>| f`, `&> f`, `tee -a f`), the words of the command, and a
# word that runs a file named after it. A quote or a comment hides no word from these readers: they can only
# keep more bodies in view, never fewer.
_WRITE_TARGET = re.compile(r"(?:>>?\|?(?!&)|(?<![\w-])tee(?:[ \t]+-[\w-]+)*[ \t])[ \t]*[\"']?([^\s;&|<>()\"'`]+)")
_WORDS = re.compile(r"[^\s;&|<>()\"'`]+").findall
_RUNNER = re.compile(r"(?:" + _INTERPRETERS + r"|source|\.|eval|exec|xargs|sudo|env|timeout|nohup|nice|command"
                     r"|time|ssh)(?:\.exe|\.cmd)?").fullmatch


def _plain_words(words):
    return [word[2:] if word.startswith("./") else word for word in words if not re.match(r"\w+=", word)]


def _runs_written_file(text: str, headers) -> bool:
    """True when a file a heredoc writes is run later: its pipeline holds a shell, an interpreter or a runner
    (`sh < f`, `cat f | sh`, `timeout 5 sh f`), or it is the command itself (`./f`). A read such as `wc -c f`
    runs nothing. The word is compared as written, so `$HOME/f` matches only itself."""
    written = {word for header in headers for word in _plain_words(_WRITE_TARGET.findall(header))}
    for pipeline in re.split(r"\n|;|&&|\|\||&", _WRITE_TARGET.sub(" ", text)) if written else ():
        stages = [_plain_words(_WORDS(stage)) for stage in pipeline.split("|")]
        runs = any(_RUNNER(word.rsplit("/", 1)[-1]) for words in stages for word in words)
        if any(word in written and (runs or at == 0) for words in stages for at, word in enumerate(words)):
            return True
    return False


def strip_heredoc_bodies(cmd: str, shells_only: bool = False) -> str:
    """Drop the body of every heredoc, and keep every header line. `shells_only` keeps a body
    only when a shell reads it, for a rule that judges shell lines."""
    if "<<" not in cmd:
        return cmd  # no heredoc: nothing to drop
    _, bodies, unclosed = _walk_heredocs(cmd)
    if unclosed:
        return cmd  # a body with no closer runs to the end of input: every line stays in view
    # bash runs each substitution of an unquoted body while it writes the body, so those stay in view as
    # lines of their own; the prose around them is data. A script body's header test below keeps it whole.
    runs = []
    for quote, body, header in bodies:
        if not quote and ("$(" in body or "`" in body) and not _INTERPRETER_FIRST(_without_message_values(header)):
            from guard_env import _substitutions   # imported late: guard_env imports this file
            texts, too_deep = _substitutions(body, heredoc=True)
            if too_deep:
                return cmd
            runs += [text for text, _ in texts[:-1]]   # the last text is the body around them
    dropped = _drop_heredoc_bodies(cmd)
    # The header test reads the command with its bodies gone: a `bash <<EOF` line inside a data body
    # is text, and no body line may make another body look run.
    text = _without_message_values(dropped)
    if (SHELL_HEREDOC if shells_only else INTERPRETER_HEREDOC)(text) or _runs_written_file(
            text, [header for _, _, header in bodies]):
        return cmd  # the body may be executed, so keep it under inspection
    return "\n".join([dropped] + runs)


# BANDAID (owner rule hold-unsafe-after-round-3: no safety hole that main lacks). This is main's header
# pattern. At a word such as `'EOF-1'` or `\EOF` it finds no header; at `EOF-1` or `"E"OF` it reads a shorter
# word and closes the body early at a line `EOF` or `E`. Main so kept body lines in view, and a run path no
# rule names (`cat <<'E-1' > x.sh && sh x.sh`, a pipe on the next line, `| python3 -`) still refused.
# heredoc_delimiter reads those words right, so _drop_heredoc_bodies walks the command as the lane reads it and
# as main read it, and keeps a line when either walk keeps it: every drop, the unconditional one too, sees what main saw,
# also for two heredocs where main's early close at a line of the second body leaves its payload outside every body.
# The cost: for those words an interpreter body counts each line, as on main (ruling ask-commands-run-alone).
# Retire it when each run path reads its body.
_MAIN_HEADER = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


# ------------------------------------------------------------------ git call parsing
#
# Judge the BEHAVIOUR of a git call, not the text beside it. `git checkout -b name` and
# `git checkout main` move a branch and keep every file, so they pass. `git checkout <path>`
# overwrites a file from the index, so it is refused.

# `git` reads these options before the subcommand, and each one takes a value.
GIT_OPT_WITH_VALUE = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
    "--super-prefix", "--config-env",
}

# `stash`, `reset`, and `restore` each cover both a read and a discard, so the SUBCOMMAND NAME
# alone never proves the act. MEASURED: `git stash list` only reads, yet it tripped this rule
# under the old name match. The predicates below read the ACT each one takes, never the spelling
# of the subcommand.

# These options are followed by a NEW branch name, which is never a path.
GIT_CHECKOUT_TAKES_NAME = {"-b", "-B", "--orphan"}

# An argument shaped like a file, not like a branch. A branch name may hold a slash
# (`claude/my-lane`), so a slash alone proves nothing. An extension, a leading `./`, a drive letter
# or a backslash does.
PATH_PREFIX = re.compile(r"^(?:\.{1,2}$|\.{1,2}[/\\]|[/~]|[A-Za-z]:[/\\])")
PATH_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,6}$")

# A shell redirection, dropped before a segment is tokenized for a git call. `2>&1` is a false
# positive, MEASURED in guard.log: `git checkout origin/claude/pass3-seam 2>&1` was refused as
# `git checkout origin/claude/pass3-seam` was not, because `2>&1` reached `git_calls` as one more
# plain word, and `checkout_names_a_path` reads two plain words as a start point plus a path.
#
# The redirect information itself is NOT lost. The frozen-path rule reads it from `writes_to`,
# against the raw command text, which this function never touches. This regex only shrinks the
# copy that decides what a `git` call's OWN arguments are.
#
# Order matters: `&>file` starts with a literal `&`, which the third branch would not reach on its
# own, so it is tried first. The other three shapes (`>file`, `>>file`, `<file`, and the fd forms
# `2>&1`, `>&2`, `1>&2`) all share one greedy `\S+` for the target, spaced or not.
REDIRECTION = re.compile(
    r"&>>?\s*\S+"       # &>file, &>>file
    r"|<\s*\S+"         # <file
    r"|\d?>>?\s*\S+"    # >file, >>file, 2>file, 2>>file, 2>&1, >&2, 1>&2
)


def _git_subcommand_index(tokens, index: int) -> int:
    """Return the index of the subcommand of the `git` word at `index`, past git's own options."""
    cursor = index + 1
    while cursor < len(tokens):
        token = tokens[cursor]
        if token in GIT_OPT_WITH_VALUE:
            cursor += 2
            continue
        if token.startswith("-"):
            cursor += 1
            continue
        break
    return cursor


def git_calls(segment: str):
    """Return (subcommand, arguments) for every `git` call in one segment."""
    text = REDIRECTION.sub(" ", segment)
    # shlex unquotes a pathspec (`'*.json'`, `"f.txt"`); a segment it cannot parse falls back to
    # a whitespace split, the old reader.
    tokens = segment_tokens(text)
    if tokens is None:
        tokens = text.split()
    calls = []
    index = 0
    while index < len(tokens):
        if basename(tokens[index]) in ("git", "git.exe"):
            cursor = _git_subcommand_index(tokens, index)
            if cursor < len(tokens):
                calls.append((tokens[cursor].lower(), tokens[cursor + 1:]))
            index = cursor + 1
            continue
        index += 1
    return calls


def long_flag_abbrev(arg: str, full: str, shortest: str) -> bool:
    """True when `arg` spells the long flag `full`, or a prefix of it at least as long as
    `shortest`. Git's parse-options accepts any unique prefix; `shortest` is the shortest one
    that no other option of the command shares. A `=value` tail is ignored."""
    name = arg.split("=", 1)[0]
    return len(name) >= len(shortest) and full.startswith(name)


def pathspec_from_file_flag(arg: str) -> bool:
    """True for `--pathspec-from-file` or any prefix of it git accepts (`--pathspec-from`, ...)."""
    return long_flag_abbrev(arg, "--pathspec-from-file", "--pathspec-f")


# ------------------------------------------------------------------ which tree the command runs in
#
# THE COMMAND IS JUDGED WHERE IT RUNS, NOT WHERE THE HOOK LIVES. A lane is built in a worktree and a
# discard there loses only that lane's own work, so a worktree earns an "ask". The shared checkout is
# the owner's editor and every other session, so a discard there earns a "deny".
#
# The directory is the last `cd <path>` in the command, or a `git -C <path>`, or the shell's own cwd.
# Reading the main checkout for every command would judge a worktree command against another branch.
#
# READ OFF PARSED TOKENS, NOT THE RAW STRING. A regex over the raw text cannot tell a real `cd`
# from one sitting inside a quoted argument or a `#` comment. MEASURED against this file before
# this fix: `bash -c 'true; cd /elsewhere; rm -rf x'; <destructive>` and `# note; cd
# /elsewhere\n<destructive>` both resolved to `/elsewhere`, because the old `CD_RE` only asked
# whether `cd` was preceded by `^`, `;`, `&`, or `|` in the raw text — true for both, despite the
# `cd` in each case never running. `split_segments` (quote- and comment-aware) plus
# `segment_tokens` (shlex) are the readers already used elsewhere in this file.
# `--work-tree` NAMES THE TREE THE FILES COME FROM, and it outranks `-C` and a `cd`, because git
# applies it after both. MEASURED 2026-09-19 with real git: from a CLEAN checkout A,
# `git --work-tree=B status --porcelain` reported B's modified file and B's untracked file. The
# files a call discards are B's, so B is the tree this rule must judge. Both the `=` and the
# spaced form are read, because git takes either. This one stays a raw-text regex: it is outside
# this fix's scope (the recorded debt named only `_run_dir`'s `cd`/`git -C` reading).
GIT_WORK_TREE_RE = re.compile(r"--work-tree(?:=|\s+)(['\"]?)([^'\";&|\s]+)\1")


CD_WORDS = ("cd", "chdir", "pushd", "set-location", "push-location")
POP_WORDS = ("popd", "pop-location")
CD_UNKNOWN = object()   # a move whose destination is not tracked (popd)


def _segment_cd_move(tokens):
    """None when the segment moves no directory. Else where it goes: a path, "-" (the directory
    before the last move), "" (a bare cd: home), or CD_UNKNOWN. `cd`, `chdir`, `pushd` and
    PowerShell's `Set-Location`, `Push-Location` and `sl` all move; `popd` goes somewhere not
    tracked."""
    index = resolve_command(tokens)
    if index is None:
        return None
    word = basename(tokens[index])
    if word in POP_WORDS:
        return CD_UNKNOWN
    if not (word in CD_WORDS or (word == "sl" and POWERSHELL_CALL[0])):
        return None
    if word == "pushd":
        operands = [t for t in tokens[index + 1:] if not (t[:1] in "<>" or REDIRECTION.match(t))]
        # `pushd -n` only adds to the stack: the shell stays. `pushd` alone swaps the top two
        # folders, and `pushd +N` / `-N` rotates the stack: neither names a folder.
        if "-n" in operands:
            return None
        if not operands or re.fullmatch(r"[+-]\d+", operands[0]):
            return CD_UNKNOWN
    for token in tokens[index + 1:]:
        if token == "-":
            return "-"
        if token.startswith("-") or token[:1] in "<>" or REDIRECTION.match(token):
            continue
        return token
    return ""


def _segment_cd_target(tokens, words=("cd", "set-location")):
    """Return the path a tokenized segment's `cd` or PowerShell `Set-Location` would take, or None
    when it names none, or when the segment's command word is neither. The aliases `sl`, `chdir`
    and `Push-Location` are not read (owner ruling 2026-10-15 names only `Set-Location`). The push
    and delete rules and `_run_dir` read this; `_segment_cd_move` (the silent-write rule) reads the
    rest. WORDS widens the command words read: rule other-checkout adds `pushd`."""
    move = _segment_cd_move(tokens)
    index = resolve_command(tokens)
    if index is None or basename(tokens[index]) not in words:
        return None
    return move if isinstance(move, str) and move not in ("", "-") else None


def shell_abs(path: str, base):
    """A path a command names, made absolute against `base` (the directory the shell is in, or
    None when that is not known). Git Bash's `/tmp` is the Windows temp folder. No variable is
    expanded: the shell's variables are not this hook's. None when it cannot be made absolute."""
    if os.name == "nt" and (path == "/tmp" or path.startswith("/tmp/")):
        import tempfile   # lazy: only a path under /tmp needs it
        path = tempfile.gettempdir() + path[4:]
    path = os.path.expanduser(path)
    if re.match(r"^/[a-zA-Z]/", path):
        path = path[1].upper() + ":" + path[2:]
    if not os.path.isabs(path):
        return os.path.join(base, path) if base else None
    return path


def dir_before_segment(segments, number: int, shell_cwd: str, ends=()):
    """The directory the shell is in when `segments[number]` runs, or None when it cannot be told.

    Walks the segments ahead of it in order, the way `_run_dir` reads them, but keeps the state a
    real shell keeps: `cd`, `pushd`, `Set-Location` move it, a bare `cd` goes home, `cd -` goes
    back, a `cd` inside `( ... )` ends with the parenthesis, `popd` or a path that holds a variable
    is not tracked, and a `cd` into a folder that does not exist is not trusted (the shell stays
    where it was, and a `;` runs the next command there). `ends` is what `split_segments` gave:
    in bash each part of a pipe runs in a subshell, so its `cd` moves nothing after the pipe."""
    where = shell_cwd if shell_cwd and os.path.isabs(shell_cwd) else None
    prev, stack = None, []
    for at, segment in enumerate(segments[:number + 1]):
        marks = [char for _, char, quote in walk_quotes(segment) if not quote and char in "()"]
        stack.extend([(where, prev)] * marks.count("("))
        if at == number:
            return where
        tokens = segment_tokens(segment)
        move = _segment_cd_move(tokens) if tokens else None
        if move is not None and not is_powershell(segment) and "|" in (
                ends[at] if at < len(ends) else "", ends[at - 1] if 0 < at <= len(ends) else ""):
            move = None   # a bash pipe's part: a subshell, so the shell stays where it was
        if tokens is None:
            where = None
        elif move is not None:
            old = where
            if move is CD_UNKNOWN:
                where = None
            elif move == "-":
                where = prev
            elif any(mark in move for mark in "$%`"):
                where = None
            else:
                where = shell_abs(move or "~", where)
                where = where if where and os.path.isdir(where) else None
            prev = old
        for _ in range(marks.count(")")):
            if stack:
                where, prev = stack.pop()
    return where


def _segment_git_c_target(tokens):
    """Return a tokenized segment's `git -C <path>` target, or None when it names none, or
    when the segment's command word is not `git`.

    ONLY THE SPACED FORM, `-C <path>`, IS READ. MEASURED against the real binary: `git
    -C/some/path status` and `git -C=/some/path status` both fail with `unknown option:
    -C/some/path` (or `-C=...`) and never run. An earlier version of this function also
    accepted an attached `-C<path>` as if it named a tree, which let a command text attach any
    path it liked to `-C` and have `_run_dir` read that path as though it were real, even
    though git itself refused the call and the command ran wherever the shell's own cwd (or an
    earlier, real `cd`) put it. Found in review of PR #75, reproduced against real git and
    against the live guard: the attached form ALLOWED a `git reset --hard HEAD` that ran in a
    real dirty checkout, because the fake `-C<path>` pointed the subject read at an unrelated
    clean one.
    """
    index = resolve_command(tokens)
    if index is None or basename(tokens[index]) not in ("git", "git.exe"):
        return None
    cursor = index + 1
    found = None
    while cursor < len(tokens):
        token = tokens[cursor]
        if token == "-C":
            if cursor + 1 >= len(tokens):
                return None
            value = tokens[cursor + 1]
            # git chains every `-C`: a relative one joins onto the one before it
            found = os.path.join(found, value) if found and value else (value or found)
            cursor += 2
            continue
        if token in GIT_OPT_WITH_VALUE:
            cursor += 2
            continue
        if token.startswith("-"):
            cursor += 1
            continue
        break
    return found


def _absolute(where: str, shell_cwd: str) -> str:
    """Expand and absolutize one directory taken from a command."""
    where = os.path.expandvars(os.path.expanduser(where))
    if re.match(r"^/[a-zA-Z]/", where):  # Git Bash `/c/Users/...` to `C:/Users/...`
        where = where[1].upper() + ":" + where[2:]
    # Python 3.13 and later on Windows: a bare `/x` is not absolute, so test the converted
    # form, and only then join a relative path onto the cwd.
    if not os.path.isabs(where) and shell_cwd:
        where = os.path.join(shell_cwd, where)
    return where


def _strip_heredoc_bodies_unconditionally(cmd: str) -> str:
    """Drop the body of every heredoc, header line kept, even one fed to an interpreter.

    `strip_heredoc_bodies` keeps an INTERPRETER heredoc's body under inspection, on purpose,
    because that body may be executed. But "may be executed" means the INTERPRETER runs it, not
    the outer shell: a `cd` inside a `python3 <<'EOF'` body changes python's notion of a
    directory, never the outer shell's cwd, so `_run_dir` must never read it as a live segment.
    Found in review of PR #75, reproduced against the live guard: a `cd <clean checkout>` line
    inside such a body ALLOWED a `git reset --hard HEAD` that actually ran in a real dirty
    checkout named by the command's own cwd, because `_run_dir` read the heredoc body's `cd` as
    though the outer shell had run it. `_run_dir` is the only caller that wants the interpreter
    body dropped this way; every other caller of `strip_heredoc_bodies` still needs that body
    kept for its OWN question, which is what a write or a refused command might say, not where
    the shell sits. The walk itself is `_drop_heredoc_bodies`, shared with that function.
    """
    return _drop_heredoc_bodies(cmd)


def _run_dir(cmd: str, shell_cwd: str) -> str:
    """Return the directory the command RUNS in: a `git -C`, else the last `cd`, else the cwd.

    This is the part both roots share. Neither `--work-tree` nor `--git-dir` is read here,
    because each answers a different question and each belongs to one caller.

    READ OFF TOKENS, PER SEGMENT, not a regex over the raw string: a `cd` or `git -C` sitting
    inside a quoted argument or a `#` comment is text, not a command, and only a segment that
    tokenizes to `cd`/`git` as its OWN command word (via `resolve_command`, which already steps
    over wrappers and loop keywords) counts. A segment that fails to tokenize (an unmatched
    quote) is skipped, the same fail-open stance `segment_tokens` documents elsewhere. The FIRST
    `git -C` found, across all segments in order, still wins over every `cd`, matching this
    function's behaviour before this fix; failing that, the LAST `cd` found wins.

    HEREDOC BODIES ARE STRIPPED FIRST, unconditionally, even an interpreter body that
    `strip_heredoc_bodies` keeps for other callers: a `cd` line inside one never moves the
    OUTER shell, which is the tree this function answers about.
    """
    cmd = _strip_heredoc_bodies_unconditionally(cmd)
    where = None
    last_cd = None
    for segment in split_segments(cmd):
        tokens = segment_tokens(segment)
        if tokens is None:
            continue
        if where is None:
            git_c = _segment_git_c_target(tokens)
            if git_c is not None:
                where = git_c
        cd = _segment_cd_target(tokens)
        if cd is not None:
            last_cd = cd
    if where is None:
        where = last_cd
    if where:
        where = _absolute(where, shell_cwd)
    return where or shell_cwd or ""


def command_root(cmd: str, shell_cwd: str) -> str:
    """Return the WORKING TREE the command acts on.

    This answers "whose files does this call write or discard". It is NOT the answer to "whose
    HEAD does this call move": a git directory and a work tree are set separately and can name
    two different checkouts. `head_root` answers that second question.
    """
    match = GIT_WORK_TREE_RE.search(cmd)
    if match:
        return _absolute(match.group(2), _run_dir(cmd, shell_cwd))
    return _run_dir(cmd, shell_cwd)


# ------------------------------------------------------------------ a removed or pruned worktree
#
# `git worktree remove <path>` throws away one worktree's own files. Its subject lives at PATH,
# never at `where` (the checkout the command RUNS in): removing a worktree is ordinarily typed
# from the primary checkout or from any other worktree of the same clone, never from inside the
# tree it deletes.
#
# THREE THINGS MAKE THE SUBJECT NON-EMPTY, so the call refuses: uncommitted or untracked work in
# that tree (`git status --porcelain`), a lock (`git worktree list --porcelain` naming it
# `locked`), or a LIVE SESSION still standing in it. None of the three is a guess: each is read
# straight off git or off the session record git-worktree-remove would run past.
def worktree_remove_target(args, where: str) -> str:
    """Return the absolute path a `git worktree remove` call would delete, or '' when it names
    none (`git worktree remove` with no path is not a call this rule can happen upon; the
    matcher already required at least the subcommand)."""
    for arg in args:
        if arg.startswith("-"):
            continue
        return _absolute(arg, where)
    return ""


def worktree_remove_subject(args, where: str):
    """The subject of `git worktree remove <path>` is PATH's own uncommitted and untracked work,
    widened by whether it is locked and whether a live session still stands in it."""
    target = worktree_remove_target(args, where)
    if not target:
        return None
    lines = porcelain(target)
    if lines is None:
        return None
    # An untracked symlink is not work: removing it deletes the link, never its target.
    # A path git quotes (core.quotePath) keeps its quotes here, is no link, and still counts.
    lines = [l for l in lines
             if not (l.startswith("?? ") and os.path.islink(os.path.join(target, l[3:].rstrip("/"))))]
    if lines and not dirty_paths_are_pushed_copies(target, lines):
        # False and None both keep today's refusal: a dirty tree whose copies cannot be proven
        # pushed is never read as unreadable-and-allowed.
        return False
    locked = worktree_locked(where, target)
    if locked is None:
        return None
    if locked:
        return False
    live = worktree_live_session(target)
    if live is None:
        return None
    if live:
        return False
    return True


# `git worktree prune` deletes no files at all: it drops the ADMINISTRATIVE RECORD of a worktree
# whose directory is already gone. `-n` is the read git itself offers for exactly this question,
# the same shape `git status --porcelain` is for a working tree elsewhere in this file: it is not
# a dry run of a block list (CLAUDE.md: never dry-run a block list), because nothing here compares
# the answer against a list of names. An empty answer means nothing would be pruned, so the call
# passes; any line named means a record would go, and the caller turns that into an ASK, never a
# deny, because the record is not a file and the loss is the record alone.
def worktree_prune_subject(args, where: str):
    """True when `git worktree prune -n` names nothing to prune, False when it names something,
    None when the dry run could not be read.

    MEASURED: git prints each worktree it would remove to STDERR, not stdout (`Removing
    worktrees/<name>: <reason>`), so both streams are read. A non-empty stderr from a `-n` call
    that still exits 0 is this message, never an error: an error exits non-zero, which the
    caller above already turns into `None`.
    """
    answer = _git(where, "worktree", "prune", "-n")
    if answer is None or answer.returncode != 0:
        return None
    return not (answer.stdout.strip() or answer.stderr.strip())


from shared_names import config_dir  # noqa: E402  the one home, shared with the config watch


def _expanded(path: str, cwd: str) -> str:
    """`~`, env vars, a Git-Bash drive spelling and a relative path resolved against `cwd`. No
    symlink is followed here, and nothing is realpath'd: see `_resolved` and `_literal_resolved`.
    """
    target = os.path.expandvars(os.path.expanduser(path.strip("'\"")))
    if re.match(r"^/[a-zA-Z]/", target):  # Git Bash `/c/Users/...` to `C:/Users/...`
        target = target[1].upper() + ":" + target[2:]
    if not os.path.isabs(target) and cwd:
        target = os.path.join(cwd, target)
    return target


def _resolved(path: str, cwd: str) -> str:
    return os.path.normcase(os.path.realpath(_expanded(path, cwd)))

# What the printed reason may carry. A reason is read by a person under time pressure, and it is the
# one reason in this file built from tool-supplied text, so the text is bounded and cleaned first.
CAP_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
CAP_CUT_MARK = " [cut]"


def cap_safe(text: str, limit: int) -> str:
    """Return text fit to print inside a reason: cleaned, bounded, and a cut MARKED.

    A control character becomes a space, so a crafted value or path cannot print a line of its own
    that reads like an approval. A text over the limit is cut and the cut is marked, so a shortened
    value is never read as the whole value.
    """
    clean = CAP_CONTROL.sub(" ", text or "")
    if len(clean) > limit:
        return clean[:limit] + CAP_CUT_MARK
    return clean


# ------------------------------------------------------------------ the log
#
# One line for each refusal, and nothing for an allow. An allow is the ordinary case, so logging it
# would bury the refusals. A failure to write the log never changes the decision.
#
# THE MATCHED FIELD IS BOUNDED, so a crafted command or a deep path cannot fill the log file. The
# bound cuts from the TAIL, which is right for a command, because a command says what it is in its
# first words. A CUT IS MARKED, the same contract `cap_safe` holds for the printed reason: a
# shortened field must never read as a whole one. An unmarked cut is what hid the defect below.
LOG_MAX_MATCHED = 120
LOG_CUT_MARK = " [cut]"

# A PATH IS SHORTENED FROM ITS HEAD, never from its tail. The tail of a path names the project, the
# folder and the file, which is what a reader needs. The head names only the machine's temporary or
# home root, which no reader needs.
LOG_PATH_MARK = "..."

# The tail of the path that survives whatever else shares the field. MEASURED: the widest ORDINARY
# reading rule 8 writes is both cap variables with a full model id,
# `CLAUDE_CODE_SUBAGENT_MODEL = claude-sonnet-5, CLAUDE_CODE_SUBAGENT_MODEL_FORCE = 1`, at 82
# characters. LOG_MAX_MATCHED less that reading and the one space between the parts leaves 37, so
# the ordinary reading and a path tail of 37 both fit whole, at any path depth.
LOG_MIN_PATH = LOG_MAX_MATCHED - 1 - 82


def log_cut(text: str, limit: int) -> str:
    """Return one log field, whitespace folded to spaces, no longer than `limit`, cut MARKED.

    The mark is inside the limit, never added past it, so a caller can budget a field by adding up
    the parts and trust the sum.
    """
    text = re.sub(r"\s+", " ", text or "")
    if len(text) <= limit:
        return text
    return (text[:max(limit - len(LOG_CUT_MARK), 0)] + LOG_CUT_MARK)[:limit]


def log_path(path: str, limit: int) -> str:
    """Return a path as a log field of at most `limit` characters, shortened from the HEAD."""
    path = re.sub(r"\s+", " ", path or "")
    if len(path) <= limit:
        return path
    keep = max(limit - len(LOG_PATH_MARK), 0)
    return (LOG_PATH_MARK + path[len(path) - keep:])[:limit]


def log_path_and_text(where: str, text: str) -> str:
    """Compose a log field out of a PATH and a TEXT so that BOTH survive the field's bound.

    THE DEFECT THIS FIXES, MEASURED 2026-09-19 on macOS: rule 8 handed `record` the path and the
    cap reading joined into one string, and `record` cut the join at LOG_MAX_MATCHED from the tail.
    A macOS temporary root is long (`/var/folders/nv/mtfv7k2n11g3m1zvzw6bffym0000gn/T/...`), so the
    path alone ate the field and the line ended `... CLAUDE_CODE_SUBAG`: the variable cut mid-token
    and the MODEL GONE. The model is the part that says how far the cap was lifted, so the log line
    lost the one thing it is written for. Ubuntu passed only because `/tmp` is short, which is the
    platform reading a green check proves and nothing more.

    THE FIX IS A BUDGET, not a bigger bound. A bigger bound moves the cliff to a deeper path. Here
    the text takes the room it needs, the path takes the rest and never less than LOG_MIN_PATH
    characters of its tail, and each part marks its own cut. A path of any depth now leaves the
    ordinary reading whole, and a crafted text of any length still leaves the path readable.
    """
    text = re.sub(r"\s+", " ", text or "")
    room = LOG_MAX_MATCHED - 1  # the one space between the two parts
    for_path = min(len(re.sub(r"\s+", " ", where or "")),
                   max(LOG_MIN_PATH, room - len(text)))
    for_path = max(0, min(for_path, room))
    short = log_path(where, for_path)
    return short + " " + log_cut(text, room - len(short))


SESSION_LOG_PLACEHOLDER = "-"
SESSION_LOG_MAX = 64
# Controls and line separators go before the cut. A lone surrogate cannot be encoded as UTF-8, so
# one in the id would lose the whole log line at the write. It goes after the cut, so the cut
# never leaves one at the end.
_SESSION_LOG_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")
_SESSION_LOG_SURROGATE = re.compile(r"[\ud800-\udfff]")
_log_session = SESSION_LOG_PLACEHOLDER


def session_log_field(value) -> str:
    """Return the guard.log session column: the id without control characters, cut at 64, else "-".

    A guard.log line ends in this field. It reads the hook input's id only, never the environment
    (an environment id can belong to a parent session), so it is not session_id_of. It never raises.
    """
    try:
        if not isinstance(value, str):
            return SESSION_LOG_PLACEHOLDER
        text = _SESSION_LOG_CONTROL.sub("", value).strip()[:SESSION_LOG_MAX]
        text = _SESSION_LOG_SURROGATE.sub("", text).strip()
        return text or SESSION_LOG_PLACEHOLDER
    except Exception:
        return SESSION_LOG_PLACEHOLDER


def set_log_session(value) -> None:
    """Name the session whose hook call this process judges. Each `record` line carries it.

    A hook process judges one call, so the entry point sets it once instead of every rule passing it
    down to every `record` and `refuse` call.
    """
    global _log_session
    _log_session = session_log_field(value)


def record(tool: str, decision: str, rule: str, matched: str) -> None:
    try:
        folder = config_dir()
        os.makedirs(folder, exist_ok=True)
        fields = [
            datetime.now().astimezone().isoformat(timespec="seconds"),  # with the UTC offset: a reader on another clock reads the true instant
            tool or "",
            decision,
            rule,
            log_cut(matched, LOG_MAX_MATCHED),
        ]
        session = globals().get("_log_session")  # absent: a five-field line, never a lost one
        if session is not None:
            fields.append(session)
        line = "\t".join(fields)
        with open(os.path.join(folder, "guard.log"), "a", encoding="utf-8") as handle:
            locked = _log_lock(handle)
            try:
                handle.write(line + "\n")
                handle.flush()  # the line leaves while the lock is held
            finally:
                if locked:
                    _log_unlock(handle)
    except Exception:
        pass


LOG_LOCK_WAIT = 2.0  # seconds; then the line is written unlocked, never dropped
LOG_LOCK_OFFSET = 1 << 40  # a byte past any log data, so a reader never meets the lock


def _log_lock(handle) -> bool:
    """Take a short exclusive lock on the open log. False if it cannot: the caller writes anyway.

    Two processes appending to one file can lose lines on Windows, where an append seeks and then
    writes. The lock makes each line land whole. Stdlib only: msvcrt on Windows, fcntl elsewhere.
    """
    try:
        fd = handle.fileno()
        deadline = time.monotonic() + LOG_LOCK_WAIT
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(fd, LOG_LOCK_OFFSET, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except OSError as exc:
                # Only contention is worth a retry: msvcrt gives EACCES or EDEADLK, flock gives
                # BlockingIOError (EAGAIN) or EACCES. Any other error returns at once.
                busy = isinstance(exc, BlockingIOError) or exc.errno in (
                    errno.EACCES, errno.EAGAIN, errno.EDEADLK)
                if not busy or time.monotonic() >= deadline:
                    return False
                time.sleep(0.001)
    except Exception:
        return False


def _log_unlock(handle) -> None:
    try:
        fd = handle.fileno()
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, LOG_LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    except Exception:
        pass


_override_who = ("", None)  # (session id, agent id) of the call this process judges
_override_cwd = ""  # the call's directory, where the step grant is read


def set_override_context(session_id, agent_id, cwd=None) -> None:
    """Name the session and agent whose call this process judges, and its directory, for the owner
    override."""
    global _override_who, _override_cwd
    _override_who = (session_id, agent_id or None)
    _override_cwd = cwd if isinstance(cwd, str) else ""


def set_override_veto(veto) -> None:
    """Register the test judge() builds for this call: veto() is true when the call holds an act no
    override lifts. Until it is set, no refusal is liftable."""
    global _override_veto
    _override_veto = veto


_override_veto = lambda: True  # noqa: E731 - fail closed until judge() registers its own


def _vetoed() -> bool:
    try:
        return bool(_override_veto())
    except Exception:
        return True  # a veto that cannot be read is a veto: the refusal stands


def refuse(tool: str, decision: str, rule: str, reason: str, matched: str, spawn_role=None) -> None:
    """Print a deny or an ask and exit, unless an owner override lifts it (decision
    owner-override). A lifted act prints nothing, so the normal permission flow runs. The
    veto runs before the override is taken, so a call that also holds a never-lifted act spends no override.
    spawn_role is set only on the Opus spawn refusal, the one refusal an Opus override may lift."""
    vetoed = _vetoed()
    if not vetoed:
        try:  # an import or read failure is no override: the refusal stands
            import override
            lifted = override.take(_override_who[0], _override_who[1], override.now(), rule, spawn_role,
                                   _override_cwd)
            step = override.step_read() if lifted in (override.STEP_LIFTED, override.STEP_UNREAD) else None
        except Exception:
            lifted = step = None
        if lifted:
            record(tool, lifted, rule, matched + " step " + step if step else matched)
            if lifted in override.LIFTS:
                sys.exit(0)
    record(tool, decision, rule, matched)
    try:  # the line the owner types to lift this refusal, or the words that none does; last in the reason
        import override
        line = override.NO_OVERRIDE if vetoed else override.offer(rule, spawn_role, _override_who[1])
        reason = reason.rstrip() + " " + line
    except Exception:
        pass
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": rule + ": " + reason,
        }
    }))
    sys.exit(0)


# ------------------------------------------------------------------ builders do not edit tests
#
# A builder that cannot pass a test may otherwise delete it, skip it, or rewrite it to pass.
#
# THE RULE JUDGES THE RESULT, NOT THE COMMANDS (docs/decisions/predicate-is-the-act.md). The act is a
# test path in the diff, not a shell command. So the diff is judged, at three
# points: a Write/Edit tool call (the early warning, by path), the builder's own `git commit` and
# `git push`, and its SubagentStop. Each reads the SAME change: what the agent wrote itself
# (`own_changes` in guard.py: its own commits HEAD still holds, against their first parent or git's
# own merge, and the working tree against HEAD), plus untracked files, with every path normalised
# for backslashes and resolved through symlinks.
#
# THE ROLE is read from the payload: it carries an `agent_id` (an agent) and an `agent_type`.
# The main session, a reviewer, an Explore agent, and a session started with `--agent builder` (no
# `agent_id`; unmeasured, so it stays allowed) pass untouched. `test-author` is the inverse: it may
# change ONLY test paths and test config, never product code (agents/test-author.md).
# `record-writer` may change ONLY `*.md` files (case-insensitive
# extension; agents/*.md and CLAUDE.md included), never anything else (agents/record-writer.md).
# `designer` may change ONLY paths under the repo's design folder (agents/designer.md, decision
# design-agents).
#
# A TEST PATH is read from the path's own parts, never from a substring: a basename shape
# (`test_*.py`, `*_test.py`, `*_test.go`, `*.test.{ts,js,tsx,jsx}`, `*.spec.*`, `conftest.py`) or a
# directory part named tests, test, __tests__ or spec. Parts count from the repository root, so a
# clone that lives under a folder named `tests` is not all test files. TEST CONFIG (pytest.ini,
# pyproject.toml, jest.config.*, ...) is a test path for a builder only when the change ADDS a line
# that disables tests (`--deselect`, `testpaths`, `testPathIgnorePatterns`, ...), so a new
# dependency in pyproject.toml stays allowed. For a test-author, test config is always its own.
# `contest.py` and `latest_results.md` match no shape.
# WORKFLOWS (`.github/workflows/*.yml|*.yaml`) have one classifier (`is_workflow_rel`, `workflow_test_steps_only`,
# `workflow_disables_tests` in guard.py). A test-author may add, remove or move whole test-run steps, so a new
# suite gets its CI step. A builder may change any workflow line, except an added one that disables tests.
# Xcode/SPM: a part `^[A-Z]\w*Tests$` (`DegenUITests`) and a basename `^\w+Tests\.swift$`, case-sensitive.
# The decisions: predicate-is-the-act, guard-that-cries-wolf-is-spent, builders-cannot-edit-tests.
BUILDER_ROLE = "builder"
AUTHOR_ROLE = "test-author"
WRITER_ROLE = "record-writer"
DESIGNER_ROLE = "designer"


def agent_role(payload) -> str:
    """BUILDER_ROLE, AUTHOR_ROLE, WRITER_ROLE or DESIGNER_ROLE for an agent of that type, else ''."""
    role = payload.get("agent_type")
    if not payload.get("agent_id") or not isinstance(role, str):
        return ""
    role = role.strip().lower()
    return role if role in (BUILDER_ROLE, AUTHOR_ROLE, WRITER_ROLE, DESIGNER_ROLE) else ""


# ------------------------------------------------------------------ helpers several families share
# A null-device target, on either stream, in the three shells this guard reads a command from:
# POSIX (`/dev/null`), Windows cmd (`NUL`), and PowerShell (`$null`). `2>&1` duplicates one stream
# onto another file descriptor and is not this: the line still reaches a stream the session reads.
SILENT_WRITE_REDIRECT = re.compile(
    r"(?:&>>?|\d?>>?&?)\s*(['\"]?)(?:/dev/null|NUL|\$null)\1(?=$|[\s;&|])"
    r"|\d?>&-(?=$|[\s;&|])",   # a closed descriptor
    re.IGNORECASE,
)


def _norm_dir(path: str):
    """A resolved, case-folded form of `path` for a prefix compare, or None when it cannot be
    read. `os.path.realpath` needs no existing file, so a removed worktree's path still
    normalizes: the home record must still compare correctly once the folder is gone."""
    if not path or not isinstance(path, str):
        return None
    try:
        return os.path.normcase(os.path.realpath(path))
    except Exception:
        return None


def path_is_inside(path: str, root: str):
    """True when `path` sits at or under `root`, False when it plainly does not, None when
    either could not be resolved. Existence of either is never required."""
    p, r = _norm_dir(path), _norm_dir(root)
    if p is None or r is None:
        return None
    if p == r:
        return True
    return (p + os.sep).startswith(r + os.sep)


# A directory change that is the WHOLE call, as a recovery step: an agent whose shell cwd has left
# its home must still be able to `cd` back, or it is stuck (the PowerShell tool keeps its cwd
# between calls). Rule verification-recovery-independent-of-state. Any other word, any chained
# step, or a target not plainly inside `home` is no recovery, and stays refused.
# `sl`, `chdir` and `set-location` are PowerShell names. In Bash they move nothing, so they are no
# recovery step there.
_MOVE_WORDS = {"cd", "chdir", "set-location", "sl"}
_BASH_MOVE_WORDS = {"cd"}
# A `;`, `&`, `|`, CR or LF anywhere in the raw text. A backslash before a quote hides the separator
# from the splitter, which reads the quote as an opener, while the shell still runs the step after it.
_MOVE_SEPARATOR = re.compile(r"[;&|\r\n]")
_MOVE_FLAGS = {"-path", "-literalpath"}
_MOVE_TARGET_UNSAFE = re.compile(r"[$`()&<>|*?{}]")


def is_move_into(tool: str, command: str, cwd: str, home: str) -> bool:
    """True when `command` is one `cd` or `Set-Location` whose target is inside `home`."""
    POWERSHELL_CALL[0] = tool == "PowerShell"
    if _MOVE_SEPARATOR.search(command):
        return False
    segments = [s for s in split_segments(command) if s.strip()]
    if len(segments) != 1:
        return False
    try:   # a backslash is a Windows path separator here, never an escape
        tokens = shlex.split(segments[0].replace("\\", "\\\\"), posix=True)
    except ValueError:
        return False
    if len(tokens) == 3 and tokens[1].lower() in _MOVE_FLAGS:
        del tokens[1]
    if len(tokens) != 2 or tokens[0].lower() not in (_MOVE_WORDS if tool == "PowerShell" else _BASH_MOVE_WORDS) \
            or _MOVE_TARGET_UNSAFE.search(tokens[1]):
        return False
    return path_is_inside(_expanded(tokens[1], cwd), home) is True


# A shell that runs its `-c` argument as a script. The script is judged by this same rule.
# The `&` in `sh -c 'cmd &'` sits inside one quoted token, where no per-segment read above can see it.
INLINE_SCRIPT_SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "sh.exe", "bash.exe"}
_C_FLAG = re.compile(r"^-[A-Za-z]*c[A-Za-z]*$")


def inline_script(tokens) -> str:
    """Return the script a `sh -c SCRIPT` segment runs, else ''."""
    index = resolve_command(tokens)
    if index is None or basename(tokens[index]) not in INLINE_SCRIPT_SHELLS:
        return ""
    has_c, rest = False, iter(tokens[index + 1:])
    for tok in rest:
        if tok in ("-o", "+o", "-O", "+O"):
            next(rest, None)   # a shell option's name (`bash -o pipefail -c`), never the script
            continue
        if tok.startswith("-"):
            has_c = has_c or bool(_C_FLAG.match(tok))
            continue
        return PosixScript(tok) if has_c else ""
    return ""


# A redirect operator, spaced into a word of its own before the words are read.
REDIRECT = re.compile(r"(\d?>>?)")


# A search command's pattern is a regex, never a path: a lone dot-star pattern reads no
# environment file.
ENV_PATTERN_COMMANDS = ("grep", "egrep", "fgrep", "rg", "ag", "ack")


PLAYWRIGHT_PS_SHELLS = ("pwsh", "powershell", "pwsh.exe", "powershell.exe")


def _pwsh_script(tokens) -> str:
    """The script text after `-c` or `-Command` of a pwsh launch, else ''. Read after the outer
    shell's escapes: `segment_tokens` spends PowerShell's, `_spent_by_bash` bash's backticks."""
    tokens = _spent_by_bash(tokens)
    for at, tok in enumerate(tokens[:-1]):
        if re.fullmatch(r"-c(?:ommand)?", tok, re.I):
            return PowerShellScript(" ".join(tokens[at + 1:]))
    return ""


CMD_EXE_NAMES = {"cmd", "cmd.exe"}


def _env_split_string(tokens) -> str:
    """The command string `env -S STRING` (or `--split-string`, `-iS STRING`) runs, else ''. Only
    an `env` the segment runs as a wrapper counts, at its start or after a `(` or `$(`:
    `echo env -S x` runs echo."""
    for start in _command_starts(tokens):
        for word, flags in _walk_wrappers(tuple(tokens[start:]))[1]:
            for flag, value in flags if word == "env" else ():
                if flag in ("-S", "--split-string"):
                    return value
    return ""


def nested_script(tokens) -> str:
    """The script text a segment hands to another interpreter: `sh -c`, `cmd /c`, `pwsh -c`,
    `env -S`, PowerShell's `iex`, or `eval`. Else ''. A rule that judges a command reads this text as one more command."""
    script = inline_script(tokens) or _env_split_string(tokens)
    at = resolve_command(tokens)
    if script or at is None:
        return script
    word, rest = basename(tokens[at]), tokens[at + 1:]
    if word in CMD_EXE_NAMES:
        flag = next((i for i, t in enumerate(rest) if t.lower() in ("/c", "/k")), None)
        return "" if flag is None else PowerShellScript(" ".join(rest[flag + 1:]))
    if word in ("iex", "invoke-expression"):   # PowerShell text, whatever shell holds the call
        spent = _spent_by_bash(tokens)
        return PowerShellScript(" ".join(spent[(resolve_command(spent) or at) + 1:]))
    if word == "eval":
        return " ".join(rest)
    return _pwsh_script(tokens) if word in PLAYWRIGHT_PS_SHELLS else ""


# The ssh options that take a value: `-p 22`, `-i key`, `-o X=y`. The value is never the host.
SSH_VALUE_LETTERS = "BbcDEeFIiJLlmOopQRSWw"


def ssh_remote_script(tokens) -> str:
    """The command `ssh [options] host COMMAND...` runs on the far side, else ''. Not part of
    `nested_script`: that one also feeds the step count of an ask, which this must not move."""
    at = resolve_command(tokens)
    if at is None or basename(tokens[at]) != "ssh":
        return ""
    index = at + 1
    while index < len(tokens) and tokens[index].startswith("-"):
        flag, index = tokens[index], index + 1
        for pos, letter in enumerate(flag[1:], 1):
            if letter in SSH_VALUE_LETTERS:
                index += pos == len(flag) - 1   # the value is the next word, else glued on
                break
    return " ".join(tokens[index + 1:])   # tokens[index] is the host


def wrapped_commands(tokens, at: int):
    """The command texts the runner at `tokens[at]` starts, else []. Read: `docker|podman exec`,
    `kubectl exec ... --`, `find -exec ... ;`, `su -c`, `flock FILE`, `stdbuf`, `unbuffer`,
    `caffeinate`. A text keeps its quoting, so `docker exec c sh -c 'x y'` still reads as `sh -c`."""
    word, rest = basename(tokens[at]), tokens[at + 1:]
    if word == "kubectl" and "exec" in rest and "--" in rest:
        return [shlex.join(rest[rest.index("--") + 1:])]
    if word == "find":
        found = []
        for i, token in enumerate(rest):
            if token in ("-exec", "-execdir", "-ok", "-okdir"):
                end = next((j for j in range(i + 1, len(rest)) if rest[j] in (";", "+")), len(rest))
                found.append(shlex.join(rest[i + 1:end]))
        return found
    if word == "su":
        return [rest[i + 1] for i, t in enumerate(rest[:-1]) if t in ("-c", "--command")][:1]
    skip = 0
    if word in ("docker", "podman"):
        if rest[:1] in (["container"], ["compose"]):
            rest = rest[1:]
        if rest[:1] != ["exec"]:
            return []
        rest, skip = rest[1:], 1   # the container
    elif word == "flock":
        skip = 1   # the lock file
    elif word not in ("stdbuf", "unbuffer", "caffeinate"):
        return []
    index, _ = _wrapper_flags(word, rest, 0)
    inner = rest[index + skip:]
    return [shlex.join(inner)] if inner else []


def bare_words(segment: str):
    """(words, bare): one segment's shell words, dequoted, and the indexes of the words that hold
    no quote at all. A rule that reads a danger word at ANY bare position keeps main's breadth, so
    a runner no reader names (`docker run`, `watch`, `uv run`) still shows its inner command, and
    quoted text (`echo 'tail -f x'`, a commit message) still reads as text. A search command's
    words are patterns and paths, never a command (ENV_PATTERN_COMMANDS): `grep -rn tail -F x`
    has no bare word."""
    tokens = segment_tokens(segment)
    at = resolve_command(tokens) if tokens else None
    if at is not None and basename(tokens[at]) in ENV_PATTERN_COMMANDS:
        return [], set()
    spans, start, bare = [], None, True
    for index, char, quote in walk_quotes(segment):
        if not quote and char in " \t\r\n":
            if start is not None:
                spans.append((segment[start:index], bare))
            start, bare = None, True
            continue
        start = index if start is None else start
        bare = bare and not quote and char not in "'\"\\"
    if start is not None:
        spans.append((segment[start:], bare))
    words = []
    for text, _ in spans:
        try:
            words.append("".join(shlex.split(text)))
        except ValueError:
            words.append(text)
    return words, {i for i, (_, b) in enumerate(spans) if b}


def inner_commands(tokens):
    """Every command text one segment hands on, for a rule that judges the command word: what a
    shell, `eval` or `ssh` gets (nested_script, ssh_remote_script) and what a runner starts
    (wrapped_commands), at each command in the segment. The one reader of these wrappers."""
    found = [nested_script(tokens), ssh_remote_script(tokens)]
    for at in command_indexes(tokens):
        found.extend(wrapped_commands(tokens, at))
    return [text for text in found if text]


def _command_starts(tokens):
    """The token indexes where a command may start: 0, and each unquoted `(` or `$(`."""
    quoted = getattr(tokens, "quoted", ())
    return [0] + [i for i, t in enumerate(tokens)
                  if i and i not in quoted and (t in ("(", "$(") or GLUED_OPEN.match(t))]


def command_indexes(tokens):
    """Every index where a command runs in one segment: its own command word, and the one after
    each `(` or `$(` (a subshell or substitution, glued or spaced), such as `echo $(wsl ...)`."""
    found = []
    for start in _command_starts(tokens):
        at = resolve_command(tokens[start:])
        if at is not None and start + at not in found:
            found.append(start + at)
    return found


# ------------------------------------------------------------------ the code an interpreter runs
#
# `python -c`, `node -e` and a python or node heredoc run code that opens files as the interpreter
# does. These helpers are the one reader of that code, for every rule that judges a path in it (the
# env-file rule, and any rule that judges a write). They are stdlib only.

CODE_EXISTS_CALLS = frozenset({"exists", "lexists", "isfile", "isdir", "islink", "access"})
CODE_EXISTS_METHODS = frozenset({"exists", "is_file", "is_dir", "is_symlink"})
# What `code_paths(..., frozen=True)` reads as "exists" besides the calls above: a call that asks about a
# path's metadata or the names in it and never reads its content. The env-file rule does not read them
# so (decision env-file-stays-unread: a getsize of the file is refused); the frozen rule does.
CODE_METADATA_CALLS = frozenset({"stat", "lstat", "getsize", "getmtime", "getatime", "getctime", "samefile",
                                 "glob", "iglob", "listdir", "scandir", "walk", "readlink"})
CODE_METADATA_METHODS = frozenset({"stat", "lstat", "glob", "rglob", "iterdir", "samefile", "readlink"})
# A string a call or an attribute takes from a path: `Path(p).name`, `os.path.basename(p)`. Frozen reading only.
PY_PATH_STRING_PARTS = frozenset({"name", "stem", "suffix", "suffixes", "parts"})
# An attribute that names the folder around a path. Frozen reading only: `print(p.parent)` prints it;
# the use of `p.parent` judges the path, as the use of `p` does.
PY_PATH_PARENT_PARTS = frozenset({"parent", "parents"})
PY_PATH_STRING_CALLS = frozenset({"basename", "splitext", "relpath"})
# Calls that only read the paths in their first two arguments (a file compare, a module spec). Frozen reading only.
CODE_READ_PAIR_CALLS = frozenset({"cmp", "spec_from_file_location"})
# A program a subprocess runs with a path as its argument: the path is run or read, never written by the
# script that names it. A list that starts with another program (`cp`, `rm`, `cat`) is judged as before.
PY_RUN_CALLS = frozenset({"run", "call", "check_call", "check_output", "Popen"})
PY_RUN_PROGRAMS = re.compile(r"^(?:python[\d.]*|node|nodejs|bun|deno|bash|sh)(?:\.exe)?$")
# Programs that read the files they are given. A subprocess list that starts with one reads the paths after
# it, unless a write flag is in the list (`PY_READ_ONLY_WRITE_FLAGS`: `less -o` copies its input to a file,
# `file -C` writes a magic database). Frozen reading only.
PY_READ_ONLY_PROGRAMS = frozenset({"cat", "diff", "cmp", "head", "tail", "less", "more", "wc", "ls", "stat",
                                   "file", "grep", "md5sum", "sha1sum", "sha256sum"})
# The write flags of a program in `PY_READ_ONLY_PROGRAMS`: short flag letters (they may be bundled, `-io`) and
# long flag names (`--log-file=x`). A call that holds one is not a read.
PY_READ_ONLY_WRITE_FLAGS = {"less": ("oO", ("--log-file", "--LOG-FILE")), "file": ("C", ("--compile",))}
# A shell run with `-c` (`sh -c "cat x > p"`): the next argument is a shell script. Frozen reading only.
PY_SHELL_PROGRAMS = re.compile(r"^(?:bash|sh)(?:\.exe)?$")

# `py_compile.compile(src)` reads src. It writes a `.pyc` of that same source into the `__pycache__` beside
# it: under a frozen folder that cache is frozen too, but it holds only the compiled source the file
# already has. The cache path (`cfile`, `dfile`) is a later argument, judged as before. Frozen reading only.
PY_COMPILE_READ_CALLS = {"compile": "py_compile"}
# Python calls by the mode they give the path in their first argument. The destination is judged
# apart: `shutil.copy(src, dst)` reads src and writes dst, and a move or rename changes both.
PY_READ_METHODS = frozenset({"read_text", "read_bytes"})
PY_WRITE_CALLS = frozenset({"remove", "unlink", "rmdir", "rmtree", "mkdir", "makedirs", "removedirs",
                            "truncate", "chmod", "chown", "utime", "touch", "write_text", "write_bytes",
                            "symlink_to", "hardlink_to", "rename", "replace", "move"})
PY_COPY_CALLS = frozenset({"copy", "copy2", "copyfile", "copytree", "copymode", "copystat"})
PY_MOVE_CALLS = frozenset({"rename", "replace", "move"})
# A call whose argument is only printed, written as content, or compared: the string is text, as an
# `echo` argument is in the shell. `write(x)` takes x as the CONTENT, never the path.
PY_TEXT_CALLS = frozenset({"print", "pprint", "write", "writelines", "write_text", "write_bytes",
                           "dumps", "dump"})
# A call that returns its one path argument in another spelling: the mode passes on to the call around
# it, as it does through a join. `open(os.path.expanduser(p))` opens p; `print(expanduser(p))` prints it.
# This is the one home of the list: guard_frozen's own path reader (`_py_paths`) reads it too.
PY_PATH_SPELLINGS = frozenset({"expanduser", "expandvars", "abspath", "realpath", "normpath", "normcase",
                               "fspath", "resolve", "absolute", "dirname"})
PY_TEXT_COMPARES = (ast.In, ast.NotIn, ast.Eq, ast.NotEq)
# Nodes that carry a string on to the call around them: a list, a dict, an f-string, a sum.
PY_CARRIERS = (ast.Dict, ast.List, ast.Tuple, ast.Set, ast.JoinedStr, ast.FormattedValue, ast.BinOp,
               ast.Starred, ast.keyword, ast.IfExp, ast.BoolOp)
# Node calls (fs, fs.promises) by the mode they give the path at an argument index.
JS_READ_CALLS = frozenset({"readFileSync", "readFile", "createReadStream", "readdirSync", "readdir"})
JS_WRITE_CALLS = frozenset({"writeFileSync", "writeFile", "appendFileSync", "appendFile",
                            "createWriteStream", "unlinkSync", "unlink", "rmSync", "rm", "rmdirSync",
                            "rmdir", "mkdirSync", "mkdir", "truncateSync", "truncate", "chmodSync",
                            "chmod", "utimesSync", "utimes"})
JS_COPY_CALLS = frozenset({"copyFileSync", "copyFile", "cpSync", "cp"})   # read, then write
JS_MOVE_CALLS = frozenset({"renameSync", "rename"})                       # write, then write
JS_CONTENT_CALLS = frozenset({"writeFileSync", "writeFile", "appendFileSync", "appendFile"})
JS_EXISTS_CALLS = frozenset({"exists", "existsSync", "access", "accessSync"})
JS_METADATA_CALLS = frozenset({"stat", "statSync", "lstat", "lstatSync"})   # frozen reading only
JS_JOIN_CALLS = frozenset({"join", "resolve", "normalize"})
JS_TEXT_CALLS = frozenset({"write", "writeln", "stringify", "includes", "indexOf"})
JS_CONSOLE_CALLS = frozenset({"log", "error", "warn", "info", "debug"})
JS_CALLEE = re.compile(r"([\w$.?]+)\s*$")
JS_COMPARE_BEFORE = re.compile(r"[!=]==?\s*$")
JS_COMPARE_AFTER = re.compile(r"\s*[!=]==?")
JS_EVAL_FLAGS = ("-e", "-p", "--eval", "--print")
# After one of these a `/` opens a regex, and after anything else it divides.
JS_REGEX_AFTER = frozenset("(,=:[!&|?{};+-*%<>~^}")
JS_REGEX_WORDS = frozenset({"return", "typeof", "case", "in", "of", "delete", "void", "throw", "new",
                            "else", "do", "yield", "await"})
JS_DEPTH = 64
# `uv run`, `poetry run` and `pipenv run` start the command after them. The reader unwraps them
# itself: `wrapped_commands` and `resolve_command` are read by other rules, which test `uv run` as
# a runner with no skip rule, so a change there would move their verdicts.
CODE_RUNNERS = frozenset({"uv", "poetry", "pipenv"})
CODE_RUNNER_VALUE_FLAGS = frozenset({"--with", "--python", "-p", "--project", "--directory", "--extra",
                                     "--group", "--package", "--with-requirements", "--env-file",
                                     "--index", "--from", "--python-version"})


def _call_name(call) -> str:
    func = call.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def _stdlib_call(call) -> bool:
    """True for a bare call (`open(p)`) and a call on os, shutil, io or a `.path` (`os.path.exists`).
    A method of some other object (`names.remove(x)`, `text.replace(a, b)`) is no file call."""
    func = call.func
    if isinstance(func, ast.Name):
        return True
    owner = func.value if isinstance(func, ast.Attribute) else None
    return (isinstance(owner, ast.Name) and owner.id in ("os", "shutil", "io", "path", "glob")) or (
        isinstance(owner, ast.Attribute) and owner.attr == "path")


def _read_pair_call(call) -> bool:
    """True for `filecmp.cmp(...)` and `importlib.util.spec_from_file_location(...)`: the module is the
    one that reads, not some other object's method of the same name."""
    owner = call.func.value if isinstance(call.func, ast.Attribute) else None
    return (isinstance(owner, ast.Name) and owner.id == "filecmp") or (
        isinstance(owner, ast.Attribute) and owner.attr == "util")


def _compile_read_call(call) -> bool:
    """True for `py_compile.compile(...)` (`PY_COMPILE_READ_CALLS`): the module's call, not another
    object's method of the same name."""
    owner = call.func.value if isinstance(call.func, ast.Attribute) else None
    return isinstance(owner, ast.Name) and PY_COMPILE_READ_CALLS.get(_call_name(call)) == owner.id


def _run_list(call):
    """(program name, the constant strings after it) of a subprocess call whose first argument is a list
    that starts with a string, else None."""
    first = call.args[0] if call.args else None
    head = first.elts[0] if isinstance(first, (ast.List, ast.Tuple)) and first.elts else None
    if not (isinstance(head, ast.Constant) and isinstance(head.value, str)):
        return None
    rest = [arg.value for arg in first.elts[1:] if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]
    return os.path.basename(head.value), rest


def _has_write_flag(program: str, words) -> bool:
    letters, longs = PY_READ_ONLY_WRITE_FLAGS.get(program, ("", ()))
    return any((word.startswith("--") and word.startswith(longs)) or (
        word.startswith("-") and not word.startswith("--") and any(char in letters for char in word[1:]))
        for word in words)


def _runs_program(call) -> bool:
    """True for a subprocess call whose argument list starts with an interpreter, a shell or a read-only
    program (`PY_READ_ONLY_PROGRAMS`) that holds no write flag: a path in that list is the script it runs
    or an argument it reads."""
    spelled = _run_list(call)
    if spelled is None:
        return False
    program, words = spelled
    if PY_RUN_PROGRAMS.match(program) is not None:
        return True
    return program in PY_READ_ONLY_PROGRAMS and not _has_write_flag(program, words)


def _shell_script_call(call) -> bool:
    """True for a subprocess call that runs a shell with `-c`: `["sh", "-c", script]`."""
    spelled = _run_list(call)
    return spelled is not None and PY_SHELL_PROGRAMS.match(spelled[0]) is not None and any(
        re.match(r"^-[A-Za-z]*c$", word) for word in spelled[1])


def _open_mode(call, mode_at: int) -> str:
    """"write" for an `open` call whose mode string holds w, a, x or +, "read" when it holds none
    (the default too), "unknown" when the mode is not a string literal."""
    mode = call.args[mode_at] if len(call.args) > mode_at else next(
        (k.value for k in call.keywords if k.arg == "mode"), None)
    if mode is None:
        return "read"
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return "write" if set(mode.value) & set("wax+") else "read"
    return "unknown"


def _spelled_path_call(expr, parents):
    """The call `expr.expanduser()` (or another PY_PATH_SPELLINGS method, no arguments) when `expr`
    is the object it is called on, else None. It returns the same path in another spelling."""
    method = parents.get(expr)
    outer = parents.get(method)
    if (isinstance(method, ast.Attribute) and method.value is expr and method.attr in PY_PATH_SPELLINGS
            and isinstance(outer, ast.Call) and outer.func is method and not outer.args
            and not outer.keywords):
        return outer
    return None


def _path_method_mode(call, parents, frozen=False) -> str:
    """The mode a `Path(...)` call gives its path, from the method called on it."""
    method = parents.get(call)
    outer = parents.get(method)
    if frozen and isinstance(method, ast.Attribute) and method.value is call \
            and method.attr in PY_PATH_STRING_PARTS:
        return "text"
    if frozen and isinstance(method, ast.Attribute) and method.value is call \
            and method.attr in PY_PATH_PARENT_PARTS:
        return _python_mode(method, parents, True, frozen=True)
    if not (isinstance(method, ast.Attribute) and isinstance(outer, ast.Call) and outer.func is method):
        return "unknown"
    if method.attr in CODE_EXISTS_METHODS or (frozen and method.attr in CODE_METADATA_METHODS):
        return "exists"
    if method.attr in PY_READ_METHODS:
        return "read"
    if method.attr == "open":
        return _open_mode(outer, 0)
    return "write" if method.attr in PY_WRITE_CALLS else "unknown"


PY_MODE_RANK = ("text", "exists", "read", "shell", "unknown", "write")   # the riskiest use of a name wins


def _outer_loop(node, parents):
    """The outermost `for` or `while` that holds `node` (not past a function), else None."""
    loop = None
    while node is not None and not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        node = parents.get(node)
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            loop = node
    return loop


def _straight_uses(assign, uses, bound):
    """The uses of a name after this binding and before the next binding of the name (the first binding
    also takes the uses before it, as `_py_bound_value` does)."""
    ends = [end for end, _ in bound.get(_assign_target(assign).id, ())]
    mine = (assign.end_lineno, assign.end_col_offset)
    if mine not in ends:
        return uses
    later = next((end for end in ends if end > mine), None)
    first = ends[0] == mine
    return [use for use in uses if ((use.lineno, use.col_offset) >= mine or first)
            and (later is None or (use.lineno, use.col_offset) < later)]


def _live_uses(assign, uses, bound, parents):
    """The uses of a name that read this binding: those after it and before the next binding of the
    name. A binding the table does not hold keeps every use. Inside a loop a use can run under any
    binding the loop assigns, on a later pass, so the uses of every binding of the name in the loop,
    and every use inside the loop, count for each of them."""
    live = _straight_uses(assign, uses, bound)
    loop = _outer_loop(assign, parents)
    if loop is None:
        return live
    start, end = (loop.lineno, loop.col_offset), (loop.end_lineno, loop.end_col_offset)
    pooled = {id(use): use for use in live}
    for use in uses:
        if start <= (use.lineno, use.col_offset) < end:
            pooled[id(use)] = use
    for _, value in bound.get(_assign_target(assign).id, ()):
        other = parents.get(value)
        if other is not None and other is not assign and start <= (other.lineno, other.col_offset) < end:
            for use in _straight_uses(other, uses, bound):
                pooled[id(use)] = use
    return list(pooled.values())


def _assign_target(assign):
    return assign.targets[0] if isinstance(assign, ast.Assign) and len(assign.targets) == 1 \
        else getattr(assign, "target", None)


def _bound_mode(assign, path_object, parents, names, seen, frozen, bound=None) -> str:
    """The mode a value bound to a name (`p = Path(x).expanduser()`) gives its path, from the uses of
    that name in the code (`p.read_text()`, `open(p, "w")`). The riskiest use wins. A name with no use
    the reader can see, or a target that is not one plain name, reads "unknown". Frozen reading judges
    only the uses the binding is live at (`_live_uses`); the env reading pools every use."""
    target = _assign_target(assign)
    uses = names.get(target.id) if isinstance(target, ast.Name) and names is not None else None
    if uses and frozen and bound is not None:
        uses = _live_uses(assign, uses, bound, parents)
    if not uses:
        return "unknown"
    modes = [_python_mode(use, parents, path_object, names, seen | {assign}, frozen, bound) for use in uses]
    return max(modes, key=PY_MODE_RANK.index)


def _python_mode(node, parents, path_object=False, names=None, seen=frozenset(), frozen=False,
                 bound=None) -> str:
    """The mode a python string constant gives its path, from the call that holds it. A join
    (`os.path.join(a, p)`) passes the mode of its result on; a list, a dict, an f-string or a sum
    carries the string to the call around it, where only a text call reads it (`direct` is then off).
    A bare `Path(p)` argument is p as a path object. A value bound to a name takes the mode of the
    name's uses when `names` (the name to its load nodes) is given (`_bound_mode`; `bound` is the table
    of bindings `_python_paths` builds, which frozen reading uses to judge each use at its own binding)."""
    value, direct = node, True
    while True:
        parent = parents.get(value)
        spelled = None
        if direct and isinstance(parent, ast.Call) and _call_name(parent).endswith("Path") \
                and value in parent.args:
            spelled = _spelled_path_call(parent, parents)
            if spelled is None and not isinstance(parents.get(parent), ast.Attribute):
                value, path_object = parent, True    # `open(Path(p))`: the call around it judges p
                continue
        elif path_object:
            spelled = _spelled_path_call(value, parents)
        if spelled is not None:
            value, path_object = spelled, True
            continue
        if isinstance(parent, ast.Compare):
            return "text" if all(isinstance(op, PY_TEXT_COMPARES) for op in parent.ops) else "unknown"
        if (direct and isinstance(parent, ast.Call) and _stdlib_call(parent) and value in parent.args
                and (_call_name(parent) == "join"
                     or (_call_name(parent) in PY_PATH_SPELLINGS and parent.args[0] is value))):
            value = parent
        elif isinstance(parent, PY_CARRIERS):
            value, direct = parent, False
        else:
            break
    call = parent
    if path_object and isinstance(call, ast.Attribute):
        return _path_method_mode(value, parents, frozen)    # `Path(p).expanduser().exists()` checks p
    if direct and names is not None and (isinstance(call, (ast.Assign, ast.AnnAssign))
                                         or (frozen and isinstance(call, ast.AugAssign))):
        return "text" if call in seen else _bound_mode(call, path_object, parents, names, seen, frozen, bound)
    if not isinstance(call, ast.Call):
        return "unknown"
    name = _call_name(call)
    if direct and name.endswith("Path") and value in call.args:
        return _path_method_mode(call, parents, frozen)
    if name in PY_TEXT_CALLS or (frozen and name in PY_PATH_STRING_CALLS):
        return "text"
    if frozen and name in PY_RUN_CALLS and _shell_script_call(call):
        return "shell"   # the script is read by the shell write scan (`_code_literal_hit`)
    if frozen and name in PY_RUN_CALLS and _runs_program(call):
        return "text"
    position = call.args.index(value) if direct and value in call.args else -1
    if frozen and 0 <= position <= 1 and name in CODE_READ_PAIR_CALLS and _read_pair_call(call):
        return "read"
    if frozen and position == 0 and _compile_read_call(call):
        return "read"
    if position < 0 or position > 1 or not _stdlib_call(call):
        return "unknown"
    if name in CODE_EXISTS_CALLS or (frozen and name in CODE_METADATA_CALLS):
        return "exists" if position == 0 else "unknown"
    if name == "open":
        return _open_mode(call, 1) if position == 0 else "unknown"
    if name in PY_COPY_CALLS:
        return "read" if position == 0 else "write"
    if name in PY_MOVE_CALLS:
        return "write"
    return "write" if position == 0 and name in PY_WRITE_CALLS else "unknown"


PY_HOME_ENV = ("HOME", "USERPROFILE")


def _join_text(head: str, tail: str) -> str:
    """`os.path.join(head, tail)` on text: an absolute tail replaces the head."""
    if tail.startswith("/") or not head:
        return tail
    return head.rstrip("/") + "/" + tail


def _py_is_format(node) -> bool:
    """True for `"...%s..." % value`: a %-format of a string literal."""
    return (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Constant)
            and isinstance(node.left.value, str))


def _py_is_str_join(node) -> bool:
    """True for `"/".join([a, b])`: a join of a list or tuple literal on a string literal."""
    return (isinstance(node, ast.Call) and _call_name(node) == "join" and len(node.args) == 1
            and isinstance(node.args[0], (ast.List, ast.Tuple)) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Constant) and isinstance(node.func.value.value, str))


def _py_is_str_format(node) -> bool:
    """True for `"{}/x".format(a)`: a `.format` call on a string literal."""
    return (isinstance(node, ast.Call) and _call_name(node) == "format" and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Constant) and isinstance(node.func.value.value, str)
            and bool(node.args or node.keywords))


def _py_join_parts(call):
    """The arguments of `os.path.join(a, b)` or `Path(a, b)`, with a `*[a, b]` of list literals spread."""
    parts = []
    for arg in call.args:
        if isinstance(arg, ast.Starred) and isinstance(arg.value, (ast.List, ast.Tuple)):
            parts.extend(arg.value.elts)
        else:
            parts.append(arg)
    return parts


def _py_format_text(call, bound, depth) -> str:
    """`"{}/x/{0}/{name}".format(a, b, name=c)` with each hole read as its argument; `_` for a hole it
    cannot tell: a slot with no argument, a keyword the call does not name, and every positional slot at
    or after a star argument that is not a list or tuple literal (a `*[a, b]` is spread)."""
    args, unknown_from = [], None
    for arg in call.args:
        if isinstance(arg, ast.Starred):
            if unknown_from is not None:
                continue
            if isinstance(arg.value, (ast.List, ast.Tuple)):
                args.extend(_py_composed_text(item, bound, depth) for item in arg.value.elts)
            else:
                unknown_from = len(args)
        elif unknown_from is None:
            args.append(_py_composed_text(arg, bound, depth))
    named = {key.arg: _py_composed_text(key.value, bound, depth) for key in call.keywords if key.arg}
    auto = iter(range(len(args) + 1))

    def hole(match):
        if match.group(0) in ("{{", "}}"):
            return match.group(0)[0]
        key = match.group(1)
        if key == "":
            key = next(auto, None)
            if key is None:
                return "_"
            key = str(key)
        if key.isdigit():
            return args[int(key)] if int(key) < len(args) else "_"
        return named.get(key, "_")

    return re.sub(r"\{\{|\}\}|\{(\w*)(?:[!:][^}]*)?\}", hole, call.func.value.value)


def _py_bound_value(name, bound):
    """The expression a name holds where `name` is read: the last `name = ...` that ends before it, so
    `p = p / "x"` reads the p before it. A name read before every assignment takes the first one."""
    values = bound.get(name.id)
    if not values:
        return None
    here = (name.lineno, name.col_offset)
    return next((value for end, value in reversed(values) if end <= here), values[0][1])


def _py_composed_text(node, bound, depth=0) -> str:
    """The path an expression builds, as text: literals joined as `os.path.join`, `Path(a, b)` and
    `a / b` join them, `a + b` joins them as is, a name reads as the value last bound before it,
    `str(p)` and `p.joinpath(a)` read as `p` and a join, `"%s/x" % p` as an f-string, the home
    directory reads as `~`. `_` stands for a part it cannot tell (a call, a name never bound), so a
    frozen folder followed by an unknown child reads `<frozen folder>/_`."""
    if depth > 8:
        return "_"
    step = depth + 1
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else "_"
    if isinstance(node, ast.Name):
        value = _py_bound_value(node, bound)
        return _py_composed_text(value, bound, step) if value is not None else "_"
    if isinstance(node, ast.JoinedStr):
        return "".join(_py_composed_text(part.value if isinstance(part, ast.FormattedValue) else part,
                                         bound, step) for part in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.Add)):
        left, right = _py_composed_text(node.left, bound, step), _py_composed_text(node.right, bound, step)
        return _join_text(left, right) if isinstance(node.op, ast.Div) else left + right
    if _py_is_format(node):
        holes = node.right.elts if isinstance(node.right, ast.Tuple) else [node.right]
        texts = iter(_py_composed_text(hole, bound, step) for hole in holes)
        return re.sub(r"%[sdr]", lambda _match: next(texts, "_"), node.left.value)
    if isinstance(node, ast.Subscript):
        key = node.slice
        return "~" if isinstance(key, ast.Constant) and key.value in PY_HOME_ENV else "_"
    if isinstance(node, ast.Call):
        name = _call_name(node)
        first = node.args[0] if node.args else None
        if name == "home" or (name in ("getenv", "get") and isinstance(first, ast.Constant)
                              and first.value in PY_HOME_ENV):
            return "~"
        if name == "str" and first is not None:
            return _py_composed_text(first, bound, step)   # `str(p)` is p in another spelling
        if _py_is_str_join(node):
            sep, parts = node.func.value.value, node.args[0].elts
            return sep.join(_py_composed_text(part, bound, step) for part in parts) or "_"
        if _py_is_str_format(node):
            return _py_format_text(node, bound, step)
        if name == "join" or name.endswith("Path") or (name == "joinpath" and isinstance(node.func, ast.Attribute)):
            text = _py_composed_text(node.func.value, bound, step) if name == "joinpath" else ""
            for arg in _py_join_parts(node):
                text = _join_text(text, _py_composed_text(arg, bound, step))
            return text or "_"
        if name in PY_PATH_SPELLINGS:
            owner = first if first is not None else node.func.value if isinstance(node.func, ast.Attribute) else None
            return _py_composed_text(owner, bound, step) if owner is not None else "_"
    return "_"


def _py_builds_path(node) -> bool:
    """True for an expression that builds one path from parts: `a / b`, `a + b`, `os.path.join(a, b)`,
    `Path(a, b)`, `p.joinpath(a)`, a %-format of a string, an f-string with a hole, `"/".join([a, b])`
    and `"{}/x".format(a)`."""
    if isinstance(node, ast.BinOp):
        return isinstance(node.op, (ast.Div, ast.Add)) or _py_is_format(node)
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(part, ast.FormattedValue) for part in node.values)
    if isinstance(node, ast.Call) and node.args and _call_name(node) == "joinpath":
        return isinstance(node.func, ast.Attribute)
    if _py_is_str_join(node) or _py_is_str_format(node):
        return True
    return isinstance(node, ast.Call) and len(_py_join_parts(node)) > 1 and (
        _call_name(node) == "join" or _call_name(node).endswith("Path"))


def _py_composed_paths(tree, parents, names, bound):
    """[(path, mode)] for each expression that builds a path from parts, once for the whole chain. The
    parts of `os.path.join(a, b, c)` are string literals the reader names one by one, and none of them
    is a frozen file; the built path is."""
    found = []
    augmented = [value for values in bound.values() for _, value in values
                 if isinstance(parents.get(value), ast.AugAssign)]
    for node in [*ast.walk(tree), *augmented]:
        if not _py_builds_path(node):
            continue
        parent = parents.get(node)
        if _py_builds_path(parent) and (not isinstance(parent, ast.Call) or node in parent.args):
            continue   # a part of a longer chain: the chain is read whole
        path_object = isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) or (
            isinstance(node, ast.Call) and (_call_name(node).endswith("Path") or _call_name(node) == "joinpath"))
        texts = [_py_composed_text(node, bound)]
        loop = _outer_loop(node, parents)
        if loop is not None:
            # On a later pass a name in the loop holds the value the loop last bound: read the path again
            # with each name in it taken at the end of the loop.
            later = copy.deepcopy(node)
            for name in ast.walk(later):
                if isinstance(name, ast.Name):
                    name.lineno, name.col_offset = loop.end_lineno, loop.end_col_offset
            texts.append(_py_composed_text(later, bound))
        texts = [text for index, text in enumerate(texts) if text != "_" and text not in texts[:index]]
        if texts:
            mode = _python_mode(node, parents, path_object, names, frozen=True, bound=bound)
            found.extend((text, mode) for text in texts)
    return found


def _python_paths(code: str, frozen=False):
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return [(text, "unknown") for text in _python_token_strings(code)]
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    names, bound = {}, {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            names.setdefault(node.id, []).append(node)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            bound.setdefault(node.targets[0].id, []).append(((node.end_lineno, node.end_col_offset), node.value))
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) \
                and isinstance(node.op, (ast.Add, ast.Div)):
            # `p += x` binds p to `p + x`: the value built from the one before it
            left = ast.copy_location(ast.Name(id=node.target.id, ctx=ast.Load()), node.target)
            value = ast.copy_location(ast.BinOp(left=left, op=node.op, right=node.value), node)
            parents[value] = node
            bound.setdefault(node.target.id, []).append(((node.end_lineno, node.end_col_offset), value))
    for values in bound.values():
        values.sort(key=lambda item: item[0])
    found = [(node.value, _python_mode(node, parents, names=names, frozen=frozen, bound=bound)) for node in ast.walk(tree)
             if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    return found + _py_composed_paths(tree, parents, names, bound) if frozen else found


def _python_token_strings(code: str):
    found = []
    middle = getattr(tokenize, "FSTRING_MIDDLE", None)
    try:
        for token in tokenize.generate_tokens(io.StringIO(code).readline):
            if token.type == tokenize.STRING:
                text = token.string.lstrip("rRbBuUfF")
                for quote in ('"""', "'''", '"', "'"):
                    if text.startswith(quote) and text.endswith(quote) and len(text) >= 2 * len(quote):
                        text = text[len(quote):-len(quote)]
                        break
                found.append(text)
            elif middle is not None and token.type == middle:
                found.append(token.string)
    except (tokenize.TokenError, SyntaxError):
        pass  # what was read before the break still counts
    return found


def _js_file_mode(name: str, index: int, frozen=False) -> str:
    if name in JS_EXISTS_CALLS or (frozen and name in JS_METADATA_CALLS):
        return "exists" if index == 0 else "unknown"
    if name in JS_CONTENT_CALLS and index >= 1:
        return "text"   # the content, never the path
    if index == 0:
        return "read" if name in JS_READ_CALLS or name in JS_COPY_CALLS else (
            "write" if name in JS_WRITE_CALLS or name in JS_MOVE_CALLS else "unknown")
    if index == 1 and (name in JS_COPY_CALLS or name in JS_MOVE_CALLS):
        return "write"
    return "unknown"


def _js_mode(frames, code: str, start: int, end: int, whole: bool, frozen=False) -> str:
    """The mode a node string at code[start:end] gives its path. `frames` are the open brackets,
    `[kind, callee, argument index]`. `whole` is true when the string is a whole argument (a
    quote or comma before it, a comma or paren after it): only then does a file call read it as its
    path. A text call (console.log, JSON.stringify, a `write` content) reads it at any depth. A
    join passes the mode of its result on to the call around it."""
    if JS_COMPARE_BEFORE.search(code[max(0, start - 8):start]) or JS_COMPARE_AFTER.match(code, end):
        return "text"
    direct = whole
    for kind, callee, index, *_ in reversed(frames):
        if kind != "(":
            direct = False
            continue
        base = callee.rsplit(".", 1)[-1]
        if base in JS_TEXT_CALLS or (base in JS_CONSOLE_CALLS and callee.startswith("console.")):
            return "text"
        if base in JS_JOIN_CALLS:
            continue
        return _js_file_mode(base, index, frozen) if direct else "unknown"
    return "unknown"


JS_HOME = (r"\bhomedir\s*\(|\bprocess\s*\.\s*env\s*\.\s*(?:HOME|USERPROFILE)\b"
           r"|\benv\s*\[\s*['\"](?:HOME|USERPROFILE)['\"]")
JS_HOME_BOUND = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=[^;\n]*?(?:" + JS_HOME + ")")


def _js_paths(code: str, frozen=False):
    """`frozen` is the reading the frozen rule judges by (`code_paths`). It also gives the path a string
    is a part of when the home directory heads it (`path.join(os.homedir(), ".claude/hooks", f)`,
    `os.homedir() + "/.claude/x"`): that path as `~/...`, and again with `/_` (an unknown child) after
    it. A string joined to another with `+` is then a whole argument too, and `stat` asks only."""
    found, stack, frames, prev = [], [], [], ""
    i, n = 0, len(code)
    home = re.compile("|".join([JS_HOME] + [r"\b%s\b" % re.escape(name)
                                            for name in JS_HOME_BOUND.findall(code)])) if frozen else None

    def whole_arg(start: int, end: int) -> bool:
        before = code[:start].rstrip()[-1:]
        after = code[end:].lstrip()[:1]
        ends = ("(", ",", "+") if frozen else ("(", ",")
        return bool(frames) and frames[-1][0] == "(" and before in ends and after in (
            (",", ")", "+") if frozen else (",", ")"))

    def add(text: str, mode: str, start: int, whole: bool):
        found.append((text, mode))
        if not frozen:
            return
        frame = frames[-1] if frames else None
        joined = bool(whole and frame and frame[0] == "(" and frame[1].rsplit(".", 1)[-1] in JS_JOIN_CALLS)
        if joined:
            frame[4].append(text.strip("/"))
        brace = max((at for at, other in enumerate(frames) if other[0] == "{"), default=-1)
        scope = frames[brace + 1][3] if brace + 1 < len(frames) else max(
            code.rfind(";", 0, start), code.rfind("\n", 0, start)) + 1
        if home.search(code, scope, start):
            built = "~/" + "/".join(part for part in frame[4] if part) if joined else "~/" + text.lstrip("/")
            found.append((built, mode))
            found.append((built + "/_", mode))

    def close(kind: str):
        while frames and frames[-1][0] != kind and frames[-1][0] != "{":
            frames.pop()   # an unbalanced bracket never reaches past a brace
        if frames and frames[-1][0] == kind:
            frames.pop()

    while i < n:
        if len(stack) > JS_DEPTH or len(frames) > JS_DEPTH:
            raise ValueError("nest")
        if stack and stack[-1] == "`":
            first = i > 0 and code[i - 1] == "`"
            j, part = i, []
            while j < n and code[j] != "`" and not code.startswith("${", j):
                step = 2 if code[j] == "\\" else 1
                part.append(code[j:j + step])
                j += step
            closed = j < n and code[j] == "`"
            whole = first and closed and whole_arg(i - 1, j + 1)
            at = i - 1 if first else i
            add("".join(part), _js_mode(frames, code, at, j + closed, whole, frozen), at, whole)
            if closed:
                stack.pop()
                prev, i = "a", j + 1
            elif j < n:
                stack.append("${")
                frames.append(["{", "", 0, i, []])
                prev, i = "{", j + 2
            else:
                i = n
            continue
        char = code[i]
        if code.startswith("//", i):
            end = code.find("\n", i)
            i = n if end < 0 else end
        elif code.startswith("/*", i):
            end = code.find("*/", i + 2)
            i = n if end < 0 else end + 2
        elif char in "'\"":
            j = i + 1
            while j < n and code[j] != char and code[j] != "\n":
                j += 2 if code[j] == "\\" else 1
            whole = whole_arg(i, j + 1)
            add(code[i + 1:j], _js_mode(frames, code, i, j + 1, whole, frozen), i, whole)
            prev, i = "a", j + 1
        elif char == "`":
            stack.append("`")
            i += 1
        elif char == "/" and (not prev or prev in JS_REGEX_AFTER or prev == "kw"):
            j, in_class = i + 1, False
            while j < n and code[j] != "\n" and (in_class or code[j] != "/"):
                if code[j] == "[":
                    in_class = True
                elif code[j] == "]":
                    in_class = False
                j += 2 if code[j] == "\\" else 1
            prev, i = "a", j + 1
        elif char in "{}":
            if char == "{":
                stack.append("{")
                frames.append(["{", "", 0, i, []])
            else:
                if stack:
                    stack.pop()
                close("{")
            prev, i = char, i + 1
        elif char in "([":
            callee = JS_CALLEE.search(code[max(0, i - 120):i]) if char == "(" else None
            frames.append([char, callee.group(1) if callee else "", 0, i, []])
            prev, i = char, i + 1
        elif char in ")]":
            close("(" if char == ")" else "[")
            prev, i = char, i + 1
        elif char == ",":
            if frames and frames[-1][0] == "(":
                frames[-1][2] += 1
            prev, i = char, i + 1
        elif char.isalnum() or char in "_$":
            j = i
            while j < n and (code[j].isalnum() or code[j] in "_$"):
                j += 1
            prev, i = ("kw" if code[i:j] in JS_REGEX_WORDS else "a"), j
        else:
            if not char.isspace():
                prev = char
            i += 1
    return found


def code_paths(code: str, language: str, frozen=False):
    """[(string literal, mode)] for each string literal of the code that could be a path.

    `language` is "python" or "node". Python is read with `ast` (the literal parts of an f-string
    too) and, when the code does not parse, with `tokenize`; node is read by one left-to-right
    scan that skips comments and regex literals and reads each template literal's literal parts
    and the code in its `${...}`. A comment is never read. The mode comes from the call the
    literal is an argument of: "read" (`open(p)`, `Path(p).read_text()`, `shutil.copy(p, d)`,
    `fs.readFileSync(p)`), "write" (`open(p, 'w')`, the destination of a copy, a move, a rename,
    `fs.writeFileSync(p)`), "exists" (`os.path.exists(p)`, `Path(p).is_file()`, `fs.existsSync(p)`,
    also through `os.path.join`, `os.path.expanduser` and its kin, and `Path(a, b)`), "text" (printed, written as content, dumped as
    JSON, or compared: `print(s)`, `f.write(s)`, `console.log(s)`, `s in names`), and "unknown" for
    any other literal: a name handed to some other call, bound to a variable (judged by the uses of
    the name, python), or built from parts.
    A caller that refuses a path must refuse "unknown" as well as the modes it names. Raises
    ValueError for a nest deeper than JS_DEPTH.

    `frozen=True` is the reading the frozen rule judges by. It also gives each path built from parts
    (`os.path.join(a, b)`, `a / b`, `a + b`, `Path(a, b)`, an f-string, node's `path.join` and `+`
    behind the home directory) as one more entry with the mode of the whole, `_` standing for a part
    it cannot tell, and reads a metadata call (`os.stat`, `getsize`, `glob`, `fs.statSync`) and a
    string taken from a path (`Path(p).name`, `os.path.basename(p)`) as no write."""
    return _python_paths(code, frozen) if language == "python" else _js_paths(code, frozen)


def code_language(word: str) -> str:
    """"python" for `python`, `python3.12` and `py`, "node" for `node`, `nodejs` and `bun`, else ''."""
    name = re.sub(r"\.exe$", "", word.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
    if re.fullmatch(r"python[\d.]*|py", name):
        return "python"
    return "node" if name in ("node", "nodejs", "bun") else ""


def _interpreter_calls(tokens):
    """[(language, the tokens after the interpreter word)] for each python, node, bun or deno
    command of one segment, looking through `uv run`, `poetry run` and `pipenv run` and their
    flags. "node" is also the language of `deno eval`."""
    found = []
    for at in command_indexes(tokens):
        rest = tokens[at:]
        while len(rest) > 1 and basename(rest[0]) in CODE_RUNNERS and rest[1] == "run":
            rest = rest[2:]
            while rest and rest[0].startswith("-"):
                rest = rest[2:] if rest[0] in CODE_RUNNER_VALUE_FLAGS else rest[1:]
            if rest and (at2 := resolve_command(rest)) is not None:
                rest = rest[at2:]
        if not rest:
            continue
        language = code_language(rest[0])
        if language:
            found.append((language, rest[1:]))
        elif re.sub(r"\.exe$", "", rest[0].rsplit("/", 1)[-1]) == "deno" and rest[1:2] == ["eval"]:
            found.append(("deno", rest[1:]))
    return found


def inline_code(tokens):
    """[(code, language)] for the code one segment hands to python or node by flag: `python -c`,
    `node -e` or `-p`, `bun --eval`, and `deno eval`, also behind `uv run`, `poetry run` and
    `pipenv run`. `tokens` are the segment's `segment_tokens`, so the quotes and wrappers around
    the code are already read. A segment with no such code gives []. The heredoc form is
    `heredoc_code`."""
    found = []
    for language, rest in _interpreter_calls(tokens):
        if language == "python":
            for k, token in enumerate(rest[:-1]):
                if re.fullmatch(r"-[A-Za-z]*c", token):
                    found.append((rest[k + 1], "python"))
                    break
        elif language == "node":
            for k, token in enumerate(rest):
                if token.startswith(("--eval=", "--print=")):
                    found.append((token.partition("=")[2], "node"))
                elif (token in JS_EVAL_FLAGS or re.fullmatch(r"-[pe]{2}", token)) and k + 1 < len(rest):
                    found.append((rest[k + 1], "node"))
        else:
            found.extend((code, "node") for code in [t for t in rest[1:] if not t.startswith("-")][:1])
    return found


def heredoc_code(cmd: str):
    """[(quote, body, language)] for each heredoc of the command that holds python or node code.
    `quote` is the delimiter's quote character, '' when unquoted. Two shapes hold code. The header
    runs the interpreter (INTERPRETER_HEREDOC and not SHELL_HEREDOC, the test
    `_plain_escaped_quotes` uses; also behind `uv run` and its kin), and the language is that of the
    header's command word. Or the header writes a file (`cat > dbg.py <<'PY'`) that another
    segment of the same command runs with python or node (`_runs_written_file`'s reading of the
    written name), and the language is that runner's."""
    if "<<" not in cmd:
        return []
    found = []
    bodies = _split_heredocs(cmd)[1]
    rest = None
    for quote, body, header in bodies:
        header = _without_message_values(header)
        if not body:
            continue
        if INTERPRETER_HEREDOC(header) and not SHELL_HEREDOC(header):
            languages = [language for piece in split_segments(header)
                         for language, _ in _interpreter_calls(segment_tokens(piece) or [])]
        else:
            written = {word for word in _plain_words(_WRITE_TARGET.findall(header))}
            if not written:
                continue
            if rest is None:
                rest = _without_message_values(_drop_heredoc_bodies(cmd))
            languages = [language for piece in split_segments(rest)
                         for language, args in _interpreter_calls(segment_tokens(piece) or [])
                         if written & set(_plain_words(args))]
        found.extend((quote, body, "python" if language == "python" else "node")
                     for language in dict.fromkeys(languages))
    return found

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
