"""The guard's shared code: stream encoding, shell segments, heredoc bodies, git call parsing,
command roots, the worktree rules, the config folder, and the log.

guard.py is the only entry point. It loads this module from its own folder.
Other files reach these names through `guard`. The git and session reads (`_git`, the primary
checkout, a tree's status, the default branch, a branch's proof, session liveness) live in
git_reads.py, shared with the janitor: a test or the janitor that patches one of them patches it
there, on the one object that every caller reads.
"""
import errno
import functools
import json
import os
import re
import shlex
import sys
import time
from datetime import datetime

# No try/except: a guard copy without git_reads.py judges nothing, so it fails closed (guard.py).
from git_reads import (  # noqa: F401
    PROCESS_START_UNREADABLE, SESSION_LIVE_TOLERANCE_MS, _common_dir, _git, _inside_work_tree,
    _path_identity, _process_start_ms, _process_start_ms_windows, _under_by_identity,
    branch_cherry_empty, branch_is_ancestor, branch_is_empty, branch_on_remote, branch_proof,
    clone_checkouts, clone_worktrees, dirty_paths_are_pushed_copies, git_common_dir, is_worktree, porcelain,
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


# PowerShell reads each of these as the ASCII quote beside it: the double family
# opens and ends a `"` string, the single family a `'` string. Bash reads them as ordinary characters.
PS_DOUBLE_QUOTES = "\u201c\u201d\u201e"
PS_SINGLE_QUOTES = "\u2018\u2019\u201a\u201b"
PS_STRAIGHT_QUOTES = str.maketrans({**dict.fromkeys(map(ord, PS_DOUBLE_QUOTES), '"'),
                                    **dict.fromkeys(map(ord, PS_SINGLE_QUOTES), "'")})


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
                    "timeout", "verdict", "python", "python3", "exec", "builtin", "!", "&"}
# The flags of a wrapper that take the NEXT word as their value: `nice -n 5 git` runs git, not `5`.
# Long flags are listed too: `sudo --user root git ...` runs git. A `--flag=value` is one token and
# needs no entry.
WRAPPER_VALUE_FLAGS = {
    "nice": {"-n", "--adjustment"},
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string", "-P"},
    "time": {"-f", "--format", "-o", "--output"}, "exec": {"-a"},
    "doas": {"-u", "-C"},
    "xargs": {"-n", "--max-args", "-P", "--max-procs", "-I", "-L", "--max-lines", "-s",
              "--max-chars", "-d", "--delimiter", "-E", "-a", "--arg-file"},
    "sudo": {"-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt", "-C",
             "--close-from", "-D", "--chdir", "-R", "--chroot", "-T", "--command-timeout",
             "-r", "--role", "-t", "--type", "-U", "--other-user"},
}
# Runners that start another command but are no `COMMAND_WRAPPERS` entry: `wrapped_commands` reads
# them. Their value flags sit here so `_wrapper_flags` skips the same way.
WRAPPER_VALUE_FLAGS.update({
    "stdbuf": {"-i", "-o", "-e"}, "caffeinate": {"-t", "-w"},
    "ionice": {"-c", "--class", "-n", "--classdata", "-p", "--pid", "-P", "--pgid", "-u", "--uid"},
    "flock": {"-w", "-E", "--timeout", "--conflict-exit-code"},
    "docker": {"-e", "--env", "-u", "--user", "-w", "--workdir", "--env-file", "--detach-keys"},
    "podman": {"-e", "--env", "-u", "--user", "-w", "--workdir", "--env-file", "--detach-keys"},
    "watch": {"-n", "--interval", "-q", "--equexit"},
})
# The flags of `docker|podman [compose] exec` that take no value. With WRAPPER_VALUE_FLAGS, they are every
# flag `wrapped_commands(strict=True)` knows before the container.
EXEC_BARE_FLAGS = {"-d", "-i", "-t", "-T", "--detach", "--interactive", "--tty", "--privileged"}
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


ANSI_C_SIMPLE = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r",
                 "t": "\t", "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?"}
ANSI_C_ESCAPE = re.compile(r"\\(?:([0-7]{1,3})|x([0-9a-fA-F]{1,2})|u([0-9a-fA-F]{1,4})|U([0-9a-fA-F]{1,8})"
                           r"|c(.)|(.))", re.DOTALL)


def _ansi_c_value(match) -> str:
    octal, hexa, short, wide, control, plain = match.groups()
    if octal or hexa or short or wide:
        try:
            return chr(int(octal or hexa or short or wide, 8 if octal else 16) & (0xFF if octal else 0x10FFFF))
        except (ValueError, OverflowError):
            return match.group(0)
    if control:
        return chr(ord(control) & 0x1F)
    return ANSI_C_SIMPLE.get(plain, match.group(0))


def decode_ansi_c(text: str) -> str:
    """`text` with each bash ANSI-C string (`$'...'`) read as the shell reads it: the escapes
    (`\\NNN` octal, `\\xHH`, `\\n` and the rest) decode, a `\\0` ends the string, and the result
    stands as one single-quoted word. shlex has no such quoting and reads `$'g'it` as `$git`, so
    a command word spelled in pieces got past every rule that reads the word. A `$'` inside
    quotes or after a backslash is text and stays."""
    out, quote, index, last = [], "", 0, 0
    while index < len(text):
        if not quote and text[index] == "'" and is_contraction(text, index):
            width, after = 1, ""
        else:
            width, after = quote_advance(text, index, quote)
        if after == "$'" and not quote:
            end, scan = None, index + 2
            while scan < len(text):
                if text[scan] == "\\":
                    scan += 2
                elif text[scan] == "'":
                    end = scan
                    break
                else:
                    scan += 1
            if end is not None:
                body = ANSI_C_ESCAPE.sub(_ansi_c_value, text[index + 2:end]).split("\x00", 1)[0]
                out.append(text[last:index] + "'" + body.replace("'", "'\\''") + "'")
                last = index = end + 1
                continue
        quote, index = after, index + width
    return "".join(out) + text[last:] if out else text


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
        # A smart quote is a quote, so read the text with each as its ASCII twin. A text that then
        # fails shlex (a lone `\u2019` in `don\u2019t` that PowerShell would read as a quote too) is read as it stands.
        found = None
        for text in dict.fromkeys((segment.translate(PS_STRAIGHT_QUOTES), segment)):
            if "''" in text or '""' in text or "`" in text:
                text = _powershell_values(text)
            found = _segment_tokens(text)
            if found is not None:
                break
    else:
        if "`" in segment:
            source = segment   # bash text: shlex keeps its backtick substitutions as they stand
        if "$'" in segment:
            segment = decode_ansi_c(segment)
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


# A launcher starts another command, and that CHILD is what runs the heredoc body: `docker exec -i c python3 -`,
# `ssh host python3 -`, `uv run python -`. The child is read, never a later word of the launcher's line: a
# container, pod, host, `-w` path, file or `tee` argument named `node` is no interpreter. docker, podman,
# kubectl and ssh reuse `wrapped_commands` and `ssh_remote_script`. A launcher is read only when every flag
# before its child is known: a package runner takes no flag there, and docker and podman take only the flags
# of EXEC_BARE_FLAGS and WRAPPER_VALUE_FLAGS (`wrapped_commands(strict=True)`). An unknown flag may take a
# value, and a value read as the container would make a `tee` body read as that interpreter. An unread launcher
# costs a false alarm on prose and never lets a read through.
_RUN_LAUNCHERS = {
    "uv": "run", "poetry": "run", "pipenv": "run", "pdm": "run", "rye": "run", "hatch": "run",
    "conda": "run", "mamba": "run", "pipx": "run", "volta": "run", "pyenv": "exec", "fnm": "exec",
    "pnpm": "exec", "uvx": "", "npx": "", "bunx": ""}
_LAUNCHERS = frozenset(_RUN_LAUNCHERS) | {"ssh", "docker", "podman", "kubectl"}


def _launched_commands(tokens, at: int):
    """The command texts the launcher at `tokens[at]` starts, else []."""
    word = basename(tokens[at])
    if word == "ssh":
        return [text for text in [ssh_remote_script(tokens)] if text]
    if word not in _RUN_LAUNCHERS:
        return wrapped_commands(list(tokens), at, strict=True)   # it compares list slices
    index, sub = at + 1, _RUN_LAUNCHERS[word]
    if sub:
        if tokens[index:index + 1] != (sub,):
            return []
        index += 1
    if tokens[index:index + 1] == ("--",):
        index += 1
    elif tokens[index:index + 1] and tokens[index].startswith("-"):
        return []
    return [shlex.join(tokens[index:])] if index < len(tokens) else []


def _interpreter_command(words: str):
    """Like `_interpreter_header`, but the interpreter must be the COMMAND of the heredoc's segment (after
    assignments and wrappers such as `timeout 5` or `env X=1`), or the command a launcher starts
    (`_launched_commands`). The word as a redirect target (`cat > node <<EOF`, `cat >& node <<EOF`), a path
    part (`cat > node/go <<EOF`, `cd ~/node && cat > go <<EOF`) or an argument of another command is the
    name of a file, and the body is not that interpreter's.
    A segment the tokenizer cannot read is no match, so the caller keeps the body whole."""
    word = re.compile(r"(?:" + words + r")(?:\.exe|\.cmd)?").fullmatch

    def runs_interpreter(tokens) -> bool:
        index = _walk_wrappers(tokens)[0]
        if index is None:
            return False
        if word(basename(tokens[index])):
            return True
        if basename(tokens[index]) not in _LAUNCHERS:
            return False
        for child in _launched_commands(tokens, index):
            read = _segment_tokens(child)
            if read is not None and runs_interpreter(read[0]):
                return True
        return False

    def command_is_interpreter(header: str) -> bool:
        for segment in split_segments(header):
            if "<<" not in segment:
                continue
            read = _segment_tokens(segment)
            if read is None:
                continue
            tokens = []
            for token in read[0]:
                if "<<" in token:
                    break
                tokens.append(token)
            if runs_interpreter(tuple(tokens)):
                return True
        return False
    return command_is_interpreter


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
PYTHON_WORDS = "python[\\d.]*"
NODE_WORDS = "node"
_INTERPRETERS = _SHELLS + "|" + PYTHON_WORDS + "|perl|ruby|" + NODE_WORDS + "|deno"
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


def _own_headers(line: str, count: int):
    """For each of the `count` heredoc headers of one line, the text of the command that owns it: its
    segment, and the commands it pipes into when they hold no header (`cat <<A | sh`). Two commands on one
    line (`cat > go <<'A' && node - <<'B'`) so each body is classified by its own command. When the
    segments do not account for every header (an odd contraction quote doubles the segments), the line is
    read no further: every owner is '', and a caller that blanks prose keeps the body whole."""
    ends = []
    segments = split_segments(line, ends)
    owners = []
    for at, segment in enumerate(segments):
        found = len(heredoc_heads(segment)[0])
        if not found:
            continue
        text, last = segment, at
        while last + 1 < len(segments) and ends[last] == "|" and not heredoc_heads(segments[last + 1])[0]:
            last += 1
            text += "|" + segments[last]
        owners += [text] * found
    return owners if len(owners) == count else [""] * count


def _walk_heredocs(cmd: str, contractions_are_text: bool = False, legacy: bool = False,
                   kept_at: "list | None" = None, spans: "list | None" = None,
                   own_heads: "list | None" = None):
    """Return (kept lines, [(quote, body, header)], unclosed): every header line kept, every body set apart,
    each body with the text of the header line that opened it (two headers share one line).
    The walk is bash's own reading, where a later `'` closes a contraction's mark. With
    `contractions_are_text` it is the second reading of split_segments: every contraction-shaped
    `'` is text, so `echo don't` then a `<<'B'` line shows its header. A caller that judges what
    bash runs walks both.
    The one walk `_drop_heredoc_bodies` and the environment layer both need. A header is read as
    heredoc_heads reads it, so one in quoted text, a comment or a here-string strips nothing.
    A caller that passes `kept_at` gets the line index of each kept line appended to it, and one that
    passes `spans` gets the (first, end) line indexes of each body, and one that passes `own_heads` gets, for
    each body, the text of the command that owns its header (_own_headers)."""
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
        if own_heads is not None and heads:
            own_heads.extend(_own_headers(header_line, len(heads)))
        for quote, delimiter in heads:
            start = index
            while index < len(lines) and lines[index].strip() != delimiter:
                index += 1
            bodies.append((quote, "\n".join(lines[start:index]), header_line))
            if spans is not None:
                spans.append((start, index))
            if index < len(lines):
                index += 1  # drop the closing delimiter line too
            else:
                unclosed = True   # bash reads to the end of input, so a caller that judges runs reads on
    return kept, bodies, unclosed


def _heredoc_walks(cmd: str):
    """((line indexes the lane's walk keeps, line indexes main's walk keeps, the line span of each body),
    the bodies of the lane's walk, whether its last body is unclosed)."""
    lane_at, main_at, spans = [], [], []
    _, bodies, unclosed = _walk_heredocs(cmd, kept_at=lane_at, spans=spans)
    _walk_heredocs(cmd, legacy=True, kept_at=main_at)   # BANDAID: main's own walk, see _MAIN_HEADER
    return (lane_at, main_at, spans), bodies, unclosed


def _drop_heredoc_bodies(cmd: str, keep=(), walks=None) -> str:
    """Drop the body of every heredoc, keeping every header line, and the bodies numbered in `keep`. The one
    loop `strip_heredoc_bodies` and `_strip_heredoc_bodies_unconditionally` both need: the first
    guards it with the interpreter exception, the second never does, and neither re-implements
    the walk itself."""
    lane_at, main_at, spans = walks or _heredoc_walks(cmd)[0]
    # a line stays in view when either walk keeps it, or when its body is one in `keep`
    show = set(lane_at) | set(main_at) | {at for number in keep for at in range(*spans[number])}
    return "\n".join(line for at, line in enumerate(cmd.split("\n")) if at in show)


# A file a heredoc header writes (`> f`, `>> f`, `>| f`, `&> f`, `tee -a f`), the words of the command, and a
# word that runs a file named after it. A quote or a comment hides no word from these readers: they can only
# keep more bodies in view, never fewer.
_WRITE_TARGET = re.compile(r"(?:>>?\|?(?!&)|(?<![\w-])tee(?:[ \t]+-[\w-]+)*[ \t])[ \t]*[\"']?([^\s;&|<>()\"'`]+)")
_WORDS = re.compile(r"[^\s;&|<>()\"'`]+").findall
# The commands that print their heredoc body or write it to a file, and run nothing in it.
_DATA_SINKS = {"cat", "tee"}
_WRAPPERS = r"source|\.|eval|exec|xargs|sudo|env|timeout|nohup|nice|command|time|ssh"
_RUNNER = re.compile(r"(?:" + _INTERPRETERS + "|" + _WRAPPERS + r")(?:\.exe|\.cmd)?").fullmatch
# The runners that read a file as shell lines: a shell or a wrapper, never a python, perl, ruby or node.
_SHELL_RUNNER = re.compile(r"(?:" + _SHELLS + "|" + _WRAPPERS + r")(?:\.exe|\.cmd)?").fullmatch
# The runners that read a file as a script of their own.
_SCRIPT_RUNNER = re.compile(r"(?:python[\d.]*|perl|ruby|node|nodejs|bun|deno)(?:\.exe|\.cmd)?").fullmatch


def _plain_words(words):
    return [word[2:] if word.startswith("./") else word for word in words if not re.match(r"\w+=", word)]


def _runs_written_file(text: str, headers, runner=_RUNNER) -> str:
    """The word that runs a file a heredoc writes, else '': the first `runner` word of its pipeline (by default a
    shell, an interpreter or a wrapper: `sh < f`, `cat f | sh`, `timeout 5 sh f`), or the file itself when it is
    the command (`./f`). A read such as `wc -c f` runs nothing. The word is compared as written, so `$HOME/f`
    matches only itself."""
    written = {word for header in headers for word in _plain_words(_WRITE_TARGET.findall(header))}
    for pipeline in re.split(r"\n|;|&&|\|\||&", _WRITE_TARGET.sub(" ", text)) if written else ():
        stages = [_plain_words(_WORDS(stage)) for stage in pipeline.split("|")]
        runs = next((word.rsplit("/", 1)[-1] for words in stages for word in words
                     if runner(word.rsplit("/", 1)[-1])), "")
        for words in stages:
            for at, word in enumerate(words):
                if word in written and (runs or at == 0):
                    return runs or word
    return ""


def _feeds_data(header: str, scripts: bool) -> bool:
    """True when each heredoc on the header line feeds a command that only holds its body as data: a data
    sink (`_DATA_SINKS`: `cat > n.md <<EOF`, `sudo tee n.md <<EOF`), or with `scripts` a python, node, perl or
    ruby whose script `interpreter_bodies` reads. The command word is read at command position, as
    `resolve_command` reads it. A heredoc piped onward, fed through xargs, or on a segment that cannot be
    read feeds no data sink."""
    ends = []
    fed = False
    for segment, end in zip(split_segments(header, ends), ends):
        if not heredoc_heads(segment)[0]:
            continue
        tokens = segment_tokens(segment)
        if end == "|" or not tokens:
            return False
        at, chain = _walk_wrappers(tuple(tokens))
        word = basename(tokens[at]) if at is not None else ""
        if any(wrapper == "xargs" for wrapper, _ in chain) or not (
                word in _DATA_SINKS or (scripts and script_language(word))):
            return False
        fed = True
    return fed


def strip_heredoc_bodies(cmd: str, shells_only: bool = False, per_body: bool = False) -> str:
    """Drop the body of every heredoc, and keep every header line. `shells_only` keeps a body
    only when a shell reads it, for a rule that judges shell lines. One body that runs keeps every body in
    view. With `per_body` that reading drops a body whose own header only feeds it to a data sink
    (`_feeds_data`), unless the header names a shell or an interpreter, pipes it to a shell, or writes a file
    that a later segment runs. Under `shells_only` a python, node, perl or ruby body drops too: it holds a
    script, which `interpreter_bodies` gives to a rule that reads its shell spots. A caller that maps the
    returned lines back to the command (`heredoc_offsets`) takes the default."""
    if "<<" not in cmd:
        return cmd  # no heredoc: nothing to drop
    walks, bodies, unclosed = _heredoc_walks(cmd)
    if unclosed:
        return cmd  # a body with no closer runs to the end of input: every line stays in view
    # The header test reads the command with its bodies gone: a `bash <<EOF` line inside a data body
    # is text, and no body line may make another body look run.
    text = _without_message_values(_drop_heredoc_bodies(cmd, walks=walks))
    headers = [_without_message_values(header) for _, _, header in bodies]
    keep = []
    # The per-body reading starts from main's whole-command test, which both its callers read before.
    if (SHELL_HEREDOC if shells_only and not per_body else INTERPRETER_HEREDOC)(text) or _runs_written_file(
            text, headers):
        # The body may be executed, so keep it under inspection. With the two walks reading these headers
        # differently, no body can be told apart from another; a heredoc that eval or source runs may open
        # on a line before its header.
        if not per_body or walks[0] != walks[1] or _FED_SHELL(text):
            return cmd
        first = _SHELL_FIRST if shells_only else _INTERPRETER_FIRST
        runner = _SHELL_RUNNER if shells_only else _RUNNER
        keep = [number for number, header in enumerate(headers)
                if first(header) or _PIPED_SHELL(header) or _runs_written_file(text, [header], runner)
                or not _feeds_data(header, shells_only)]
    # bash runs each substitution of an unquoted body while it writes the body, so those stay in view as
    # lines of their own; the prose around them is data. A script body is the interpreter's own text, one
    # command (`interpreter_bodies` gives it to a rule that reads its shell spots).
    runs = []
    for number, (quote, body, _header) in enumerate(bodies):
        if (not quote and number not in keep and ("$(" in body or "`" in body)
                and not _INTERPRETER_FIRST(headers[number])):
            from guard_env import _substitutions   # imported late: guard_env imports this file
            texts, too_deep = _substitutions(body, heredoc=True)
            if too_deep:
                return cmd
            runs += [t for t, _ in texts[:-1]]   # the last text is the body around them
    if len(keep) == len(bodies):
        return cmd
    return "\n".join([_drop_heredoc_bodies(cmd, keep, walks)] + runs)


# The language a header names, by the header's own word.
SCRIPT_HEADERS = {
    "py": re.compile(r"(?<![\w.-])python[\d.]*(?:\.exe)?(?![\w.-])"),
    "js": re.compile(r"(?<![\w.-])(?:node|nodejs|bun|deno)(?:\.exe)?(?![\w.-])"),
    "perl": re.compile(r"(?<![\w.-])perl(?:\.exe)?(?![\w.-])"),
    "ruby": re.compile(r"(?<![\w.-])ruby(?:\.exe)?(?![\w.-])"),
}


def script_language(header: str) -> str:
    """"py", "js", "perl" or "ruby" for a header line that names that interpreter, else ''."""
    return next((lang for lang, found in SCRIPT_HEADERS.items() if found.search(header)), "")


def interpreter_bodies(cmd: str):
    """[(language, body, quote)] for each heredoc body that python, node, perl or ruby reads as a script: the body
    of a header that names one, and the body written to a file that a later segment runs with one, in the
    language of the word that runs it (language '' for a file run as the command itself, `./f`).
    `quote` is "'" for a quoted delimiter. A rule that judges shell lines reads these only at their shell spots
    (guard_env.script_spots), and an unquoted body also at the substitutions bash runs in it."""
    if "<<" not in cmd:
        return []
    walks, bodies, _ = _heredoc_walks(cmd)
    text = _without_message_values(_drop_heredoc_bodies(cmd, walks=walks))
    out = []
    for quote, body, header in bodies:
        header = _without_message_values(header)
        runs = _runs_written_file(text, [header], _SCRIPT_RUNNER)
        lang = script_language(header) or script_language(runs)
        if lang or runs:
            out.append((lang, body, quote))
    return out


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


# The operator of a redirection, read at a word's start or after one: `&>`, `<`, `>`, `>>`, `2>`, with the space before its target.
_REDIRECT_OPERATOR = re.compile(r"&>>?\s*|<\s*|\d?>>?\s*")


def strip_redirections(segment: str) -> str:
    """`segment` with each UNQUOTED redirection (REDIRECTION's shapes) cut to one space; a `>` or `<` inside quotes is text and stays.
    The target is one shell word: a quoted target (`> "run log"`) goes whole, an unquoted one up to the next space, as REDIRECTION
    reads it. Quote state comes from walk_quotes, the one quote walk. A quote left open stays open, so segment_tokens returns None
    for the result and its caller can refuse.

    One walk step can span several characters (an escape `\\x`, a `$'` opener), so each character takes the quote state of the step
    it falls in, and only a step's first character can start a redirection or end a target word: an escaped `>` or space is text."""
    size = len(segment)
    quotes, step_starts = [""] * size, [False] * size
    steps = [(at, quote) for at, _char, quote in walk_quotes(segment)]
    for (at, quote), (after, _next) in zip(steps, steps[1:] + [(size, "")]):
        step_starts[at] = True
        for inside in range(at, min(after, size)):
            quotes[inside] = quote

    def unquoted_space(at: int) -> bool:
        return step_starts[at] and not quotes[at] and segment[at].isspace()

    out, index = [], 0
    while index < size:
        char, quote = segment[index], quotes[index]
        word_start = index == 0 or unquoted_space(index - 1)
        starts = not quote and step_starts[index] and (char in "<>&" or (char.isdigit() and word_start))
        operator = REDIRECTION.match(segment, index) and _REDIRECT_OPERATOR.match(segment, index) if starts else None
        if not operator:
            out.append(char)
            index += 1
            continue
        end = operator.end()
        fd = re.compile(r"&(?:\d+|-)").match(segment, end)
        if fd:
            end = fd.end()
        else:
            while end < size and not unquoted_space(end):
                end += 1
        out.append(" ")
        index = max(end, index + 1)
    return "".join(out)


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


# Commands that cannot set a variable of the shell they run in. A segment whose command is not here
# (unset, read, printf -v, export, a loop, eval, a function, `R+=x`) may, so the walk forgets every
# variable after it.
_VARIABLE_SAFE_WORDS = frozenset(CD_WORDS + POP_WORDS + (
    "echo", "true", "false", "git", "gh", "ls", "cat", "pwd", "mkdir", "rm", "grep", "test", "[", "sleep",
    "python", "python3"))
_VARIABLE_SET_IN_ARGS = re.compile(r"\$\(\(|\$\{[^}]*=")   # `$((R=1))` and `${R:=x}` set R from an argument


def _variable_text(known, text: str) -> str:
    """`text` with each `$VAR` read as the value in `known`. The values go through `_resolve_vars`, the
    one resolver, as assignments written ahead of the text; it is imported late (guard_frozen imports
    this file). A variable not in `known` stays as written."""
    from guard_frozen import _resolve_vars
    mark = " ;\x00; "
    given = "".join('%s="%s"%s' % (name, value, mark) for name, value in known.items())
    return _resolve_vars(given + text).split(mark)[-1]


def _track_variables(known, segment: str, tokens, ran: bool) -> bool:
    """Update `known`, the variables the shell holds, for one segment the walk passes. Only a segment of
    plain `NAME=value` words that surely ran here (`ran`: not in a pipe, not after `||`, not after an `&&`
    whose left side may fail) sets a variable. A value holding a substitution, a quote, a backslash or an
    unread variable, an empty value, and a quoted `~` (bash does not expand it) leave the variable unknown.
    Only a `~` that starts the value or follows a `:` is a tilde: one inside a name (the Windows
    `RUNNER~1` temp folder) is a plain character.
    A segment that is not an assignment keeps `known` only when its command cannot set a variable.
    True when the segment is plain assignments with no substitution: its exit status is 0, so an `&&`
    after it runs."""
    if tokens and all(ASSIGNMENT.match(token) for token in tokens):
        for token in tokens:
            name, value = token.split("=", 1)
            read = None
            if (ran and value and not set(value) & set("`'\"(\\")
                    and not ((value.startswith("~") or ":~" in value) and "%s=~" % name not in segment)):
                read = _variable_text(known, value)
                if not read or "$" in read:
                    read = None
            if read is None:
                known.pop(name, None)
            else:
                known[name] = read
        return not any("$(" in token or "`" in token for token in tokens)
    index = resolve_command(tokens) if tokens else None
    if (index is None or basename(tokens[index]) not in _VARIABLE_SAFE_WORDS
            or _VARIABLE_SET_IN_ARGS.search(segment)):
        known.clear()
    return False


def _command_text(segment: str, tokens) -> str:
    """`segment` from its command word on, or None when that word cannot be found unquoted. Bash expands
    a command's words before its prefix assignments (`R=A cd "$R"`) take effect, so the resolver must not
    see them."""
    index = resolve_command(tokens)
    if index is None or not any(ASSIGNMENT.match(token) for token in tokens[:index]):
        return segment
    word = tokens[index]
    for at, _, quote in walk_quotes(segment):
        if (not quote and segment.startswith(word, at) and (at == 0 or segment[at - 1].isspace())
                and (at + len(word) == len(segment) or segment[at + len(word)].isspace())):
            return segment[at:]
    return None


def _subshell_opens(segment: str, marks):
    """The indexes of the `(` in `marks` that open a subshell group: the first word of the segment, or
    inside another such group. A `$(`, `<(`, `((` or a group after a keyword is not read as one, so its
    `)` keeps what the segment itself did to a variable (`R=$(cmd)` leaves R unknown)."""
    opens = set()
    for at, char in marks:
        if char != "(" or segment[at + 1:at + 2] == "(":
            continue
        before = segment[:at].rstrip()
        if not before or (before[-1] == "(" and len(before) - 1 in opens):
            opens.add(at)
    return opens


def _close_paren(stack, known):
    """Pop one `( ... )` level: the folder state comes back, and so does `known` after a subshell group.
    After any other paren (a substitution, arithmetic), only the variables the segment left unchanged
    stay known: the snapshot is from before the segment, so restoring it would undo the segment's own
    clear."""
    where, prev, saved, group, anchor = stack.pop()
    if group:
        return where, prev, dict(saved), anchor
    return where, prev, {name: value for name, value in known.items() if saved.get(name) == value}, anchor


def _read_cd_variable(known, segment: str, move: str, ran: bool) -> str:
    """The folder a `cd` names with each variable read from `known`, or `move` unchanged when it cannot be
    read: a `cd` that may not run (`ran` False), a command word not found in the text, or a result that is
    empty, which would be taken for home. A prefix assignment on the cd is not read (`_command_text`)."""
    text = _command_text(segment, segment_tokens(segment)) if ran else None
    if text is None:
        return move
    tokens = segment_tokens(_variable_text(known, text))
    read = _segment_cd_move(tokens) if tokens else None
    return read if isinstance(read, str) and read else move


def dir_before_segment(segments, number: int, shell_cwd: str, ends=(), failed_cd_stays=False, origin=False):
    """The directory the shell is in when `segments[number]` runs, or None when it cannot be told.

    Walks the segments ahead of it in order, the way `_run_dir` reads them, but keeps the state a
    real shell keeps: `cd`, `pushd`, `Set-Location` move it, a bare `cd` goes home, `cd -` goes
    back, a `cd` inside `( ... )` ends with the parenthesis, and `popd` is not tracked. A `cd` to
    `$VAR`, `"$VAR"` or `"${VAR}"` is read as the value a plain `NAME=value` segment set in this shell
    (`_track_variables`); a prefix assignment, one in a pipe, a subshell, after `||` or after an `&&` whose
    left side may fail, and any step that may set a variable (`unset`, `read`, a loop, `$(...)`) leave it
    unknown. A path that still holds `$` after that
    (unassigned, a substitution), or holds `%` or a backtick, is not tracked. A `cd` into a folder that does not exist is not trusted (the
    shell stays where it was, and a `;` runs the next command there). `ends` is what `split_segments` gave:
    in bash each part of a pipe runs in a subshell, so its `cd` moves nothing after the pipe.
    `failed_cd_stays` reads a `cd` to a folder that does not exist the way the shell does: it
    leaves the shell where it was, and `cd -` still goes to the folder before the last `cd` that
    worked. After `&&` the rest of that chain does not run, up to the next `;`, newline or `||`:
    a segment in it gets None, and its own `cd` moves nothing. Off by default, so a rule that
    fails closed on an untrusted `cd` keeps doing so. `origin` returns `(folder, anchor)` instead: `anchor`
    is the folder the last absolute or `~` `cd` landed in, else None. A relative `cd` after it keeps it. A
    variable `cd` (read or not), a bare `cd`, `cd -`, `popd`, a `cd` that cannot be followed, and a segment
    the tokenizer cannot read leave none."""
    where = shell_cwd if shell_cwd and os.path.isabs(shell_cwd) else None
    prev, stack = None, []
    anchor = None      # the folder the last absolute or `~` cd landed in (`origin`)
    known = {}         # the variables the shell holds: plain assignments that ran here (`_track_variables`)
    doubt = False      # the last cd may have failed in an `&&` chain: a segment after it may not run
    unsure = False     # the last segment may have failed or not run: an assignment after its `&&` may not run
    skipping = False   # a failed cd ended in `&&`: the rest of the chain does not run
    last_end = ""      # the operator that ended the last non-empty segment
    for at, segment in enumerate(segments[:number + 1]):
        marks = [(index, char) for index, char, quote in walk_quotes(segment) if not quote and char in "()"]
        groups = _subshell_opens(segment, marks)
        stack.extend((where, prev, dict(known), index in groups, anchor) for index, char in marks if char == "(")
        closes = sum(1 for _, char in marks if char == ")")
        end = ends[at] if at < len(ends) else ""
        if at == number:
            if skipping:
                where, anchor = None, None
            return (where, anchor) if origin else where
        if not segment.strip():
            continue   # an operator at end of line then the newline leaves an empty part: it changes nothing
        if skipping:
            last_end = end
            skipping = end in ("&&", "|")
            unsure = True
            for _ in range(closes):
                if stack:
                    where, prev, known, anchor = _close_paren(stack, known)
                    skipping = False
            continue
        tokens = segment_tokens(segment)
        move = _segment_cd_move(tokens) if tokens else None
        before = last_end
        last_end = end
        piped = "|" in (end, before)
        if move is not None and not is_powershell(segment) and piped:
            move = None   # a bash pipe's part: a subshell, so the shell stays where it was
        ran = not (doubt or piped or before == "||")   # this segment runs in the shell, as itself
        sure = ran and not (unsure and before == "&&")
        assigned = _track_variables(known, segment, tokens, sure)
        doubt = doubt and end == "&&"
        if tokens is None:
            where, anchor = None, None
        elif move is not None:
            old = where
            variable = move is not CD_UNKNOWN and "$" in move
            if variable:
                move = _read_cd_variable(known, segment, move, sure)
            if move is CD_UNKNOWN:
                where, anchor = None, None
            elif move == "-":
                where, anchor = prev, None
            elif any(mark in move for mark in "$%`"):
                where, anchor = None, None
            else:
                target = shell_abs(move or "~", where)
                if target and os.path.isdir(target):
                    where = target
                    if variable or not move:
                        anchor = None
                    elif move.startswith("~") or shell_abs(move, None) is not None:
                        anchor = target
                elif target and failed_cd_stays:
                    skipping = end == "&&"   # the cd failed: the shell stays, and an `&&` chain stops
                    old = prev   # a failed cd leaves the folder `cd -` goes back to alone
                else:
                    where, anchor = None, None
            doubt = doubt or (where is None and end == "&&")
            prev = old
        # Only a plain assignment or a cd into a folder the walk trusts surely succeeds.
        unsure = not (sure and (assigned or (move is not None and move is not CD_UNKNOWN and where is not None
                                                  and not skipping)))
        for _ in range(closes):
            if stack:
                where, prev, known, anchor = _close_paren(stack, known)
    return (where, anchor) if origin else where


# The value flags of a wrapper that move the program it runs into another folder first, so `env
# -C <dir> git ...` runs git in <dir>. `_wrapper_flags` already reads each flag's value with
# `WRAPPER_VALUE_FLAGS`; this names which of them are a folder.
WRAPPER_CHDIR_FLAGS = {"env": ("-C", "--chdir")}


def _chain_chdir(base, value):
    """One folder step: a relative VALUE joins onto BASE, as `env -C a env -C b` and `git -C a -C b` do,
    and an empty one leaves BASE alone."""
    return os.path.join(base, value) if base and value else (value or base)


def _wrapper_chdir(tokens):
    """Return the folder the command wrappers in front of a segment's command word move it into, or
    None when none does. Each `env -C` or `env --chdir` is read through `_walk_wrappers`, the walk
    that finds the command word, so the folder and the program come from one reading. A relative
    folder joins onto the one before it, as `env -C a env -C b` does."""
    found = None
    for word, flags in _walk_wrappers(tuple(tokens))[1]:
        for flag, value in flags:
            if flag in WRAPPER_CHDIR_FLAGS.get(word, ()) and value:
                found = _chain_chdir(found, value)
    return found


def _segment_git_c_parts(tokens):
    """Return `(env folder, git -C folder)` of a tokenized segment, each None when the segment names none,
    or None when the segment's command word is not `git` or a `-C` has no value. The env folder is the one
    an `env -C <dir>` or `env --chdir <dir>` in front of the `git` moves it into (`_wrapper_chdir`). The
    git -C folder is every `-C` after the `git`, chained. The two stay apart because `_run_dir` reads them
    differently: an env folder moves only the segment's own program, and a git -C folder reads first-wins.
    `_segment_git_c_target` joins them for every other caller.

    ONLY THE SPACED FORM, `-C <path>`, IS READ. MEASURED against the real binary: `git
    -C/some/path status` and `git -C=/some/path status` both fail with `unknown option:
    -C/some/path` (or `-C=...`) and never run. Reading an attached `-C<path>` as a tree would
    let a command text attach any path it liked to `-C` and have `_run_dir` read that path as
    though it were real, even though git itself refuses the call and the command runs wherever
    the shell's own cwd (or a real `cd`) puts it. A `git reset --hard HEAD` that runs in a real
    dirty checkout would then be allowed, because the fake `-C<path>` points the subject read at
    an unrelated clean one.
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
            # git chains every `-C`: a relative one joins onto the one before it
            found = _chain_chdir(found, tokens[cursor + 1])
            cursor += 2
            continue
        if token in GIT_OPT_WITH_VALUE:
            cursor += 2
            continue
        if token.startswith("-"):
            cursor += 1
            continue
        break
    return _wrapper_chdir(tokens), found


def _segment_git_c_target(tokens):
    """Return a tokenized segment's `git -C <path>` target, or None when it names none, or
    when the segment's command word is not `git`. An `env -C <dir>` or `env --chdir <dir>` in
    front of the `git` moves it first, so a `git -C` after it joins onto that folder, and with
    no `git -C` the `env` folder alone is the target. `_segment_git_c_parts` holds the reading
    and its measured limits; this is its joined form, the one every caller but `_run_dir` shares."""
    parts = _segment_git_c_parts(tokens)
    if parts is None:
        return None
    return _chain_chdir(*parts)


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
    """Return the directory the command RUNS in: a `git -C`, else the env folder when every git segment
    has one, else the last `cd`, else the cwd.

    This is the part both roots share. Neither `--work-tree` nor `--git-dir` is read here,
    because each answers a different question and each belongs to one caller.

    READ OFF TOKENS, PER SEGMENT, not a regex over the raw string: a `cd` or `git -C` sitting
    inside a quoted argument or a `#` comment is text, not a command, and only a segment that
    tokenizes to `cd`/`git` as its OWN command word (via `resolve_command`, which already steps
    over wrappers and loop keywords) counts. A segment that fails to tokenize (an unmatched
    quote) is skipped, the same fail-open stance `segment_tokens` documents elsewhere. The FIRST
    segment with a `git -C` wins over every `cd` and over an env folder (only an env folder in its
    own segment is kept, as its base), and its relative folder reads against the shell cwd, not
    against the folder an earlier `cd` left. Without a `git -C`, an env folder is used only when
    every git segment carries one (below); otherwise the last `cd`, else the cwd. That first-wins
    reading of `git -C` is kept as the owner ruled.

    AN `env -C` FOLDER MOVES ONLY ITS OWN PROGRAM, NOT THE SHELL: a later bare `git` in the command
    still runs in the shell's folder. So the env folder is read only when EVERY git segment carries
    one; the last of them wins, and a relative one joins onto the folder the last `cd` before it left.
    Any bare git segment makes the shell's folder (the last `cd`, else the cwd) the answer, and so
    does a command with no git segment. With a `git -C` in the same segment, the `git -C` joins onto
    that env folder.

    HEREDOC BODIES ARE STRIPPED FIRST, unconditionally, even an interpreter body that
    `strip_heredoc_bodies` keeps for other callers: a `cd` line inside one never moves the
    OUTER shell, which is the tree this function answers about.
    """
    cmd = _strip_heredoc_bodies_unconditionally(cmd)
    where = None
    moved = None   # the folder the last `cd` left
    env_moved = None   # the env folder of the last git segment that carries one
    bare_git = False   # a git segment without an env folder runs in the shell's folder
    for segment in split_segments(cmd):
        tokens = segment_tokens(segment)
        if tokens is None:
            continue
        parts = _segment_git_c_parts(tokens)
        if parts is not None:
            env_dir, git_c = parts
            if env_dir and moved:
                env_dir = shell_abs(env_dir, moved) or env_dir
            if git_c is not None:
                if where is None:
                    where = _chain_chdir(env_dir, git_c)
            elif env_dir:
                env_moved = env_dir
            else:
                bare_git = True
        cd = _segment_cd_target(tokens)
        if cd is not None:
            moved = cd
    if where is None:
        where = env_moved if env_moved and not bare_git else moved
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


def refuse(tool: str, decision: str, rule: str, reason: str, matched: str, spawn_role=None, on_lift=None) -> None:
    """Print a deny or an ask and exit, unless an owner override lifts it (decision
    owner-override). A lifted act prints nothing, so the normal permission flow runs. The
    veto runs before the override is taken, so a call that also holds a never-lifted act spends no override.
    spawn_role is set only on the Opus spawn refusal, the one refusal an Opus override may lift.
    on_lift, when set, runs once when an override lifts the act, so a rule may keep state only for an act that lands."""
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
                if on_lift:
                    on_lift()
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
# The read-only Opus role that argues against a plan (decision plan-refuter). The one home of its name: the guard, the
# brief hook and the tests import it, and none types it.
REFUTER_ROLE = "refuter"


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


# The `find` actions that run a command on a match. `guard_env` builds its own find list on this.
FIND_EXEC_ACTIONS = ("-exec", "-execdir", "-ok", "-okdir")


def wrapped_commands(tokens, at: int, strict: bool = False):
    """The command texts the runner at `tokens[at]` starts, else []. Read: `docker|podman exec`,
    `kubectl exec ... --`, `find -exec ... ;`, `su -c`, `flock FILE`, `stdbuf`, `ionice`, `unbuffer`,
    `caffeinate`, `watch`. A text keeps its quoting, so `docker exec c sh -c 'x y'` still reads as
    `sh -c`. `watch` joins its words with spaces and hands the line to `sh -c`, so its text is that
    line.
    With `strict`, a `docker|podman exec` that has a flag before the container the tables do not list reads
    as no child: the flag may take a value, and the container is then misplaced."""
    word, rest = basename(tokens[at]), tokens[at + 1:]
    if word == "watch":
        index, _ = _wrapper_flags(word, rest, 0)
        return [" ".join(rest[index:])] if rest[index:] else []
    if word == "kubectl" and "exec" in rest and "--" in rest:
        return [shlex.join(rest[rest.index("--") + 1:])]
    if word == "find":
        found = []
        for i, token in enumerate(rest):
            if token in FIND_EXEC_ACTIONS:
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
    elif word not in ("stdbuf", "ionice", "unbuffer", "caffeinate"):
        return []
    index, flags = _wrapper_flags(word, rest, 0)
    if strict and word in ("docker", "podman"):
        known = WRAPPER_VALUE_FLAGS[word] | EXEC_BARE_FLAGS
        if any(flag not in known for flag, _ in flags):
            return []
    inner = rest[index + skip:]
    return [shlex.join(inner)] if inner else []


def bare_words(segment: str):
    """(words, bare): one segment's shell words, dequoted, and the indexes of the words that hold
    no quote at all. A rule that reads a danger word at ANY bare position keeps main's breadth, so
    a runner no reader names (`docker run`, `uv run`) still shows its inner command, and
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

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
