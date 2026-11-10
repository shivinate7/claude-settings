"""The guard's process-args family: a command that prints other processes' full arguments.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import re
import shlex

from guard_core import (
    ENV_PATTERN_COMMANDS, basename, command_indexes, inner_commands, is_powershell, segment_tokens,
    split_segments, walk_quotes, wrapped_commands,
)
from guard_env import _pattern_words, substitution_commands


# ------------------------------------------------------------------ process arguments
#
# A process's full arguments can hold a secret, such as an auth key in a flag, and a session that
# prints them puts the secret in its transcript. Three acts print them:
#   - `ps` with an args column: `ps aux`, `ps -ef`, `ps -f`, `ps -o args|command|cmd`.
#   - `pgrep` with `-a`, or with `-l` and `-f` together.
#   - `ps -x` (BSD: no terminal, full arguments), `pstree -a`, `top -c`.
#   - a read of `/proc/<pid>/cmdline`: any command that takes the file as an argument, or is fed it
#     with `<`, except one that only names or measures it (`NOT_READERS`). The pattern word of a
#     search command (`grep /proc/1/cmdline docs`) is no file. `find` names the file and passes,
#     unless `-exec`, `-execdir`, `-ok` or `-okdir` hands it to a reader.
#   - PowerShell and `wmic`: a `Win32_Process` or `Get-Process` read that selects `CommandLine`.
# A pid, a name, a parent id and a start time stay allowed (`ps -o pid,comm`, `pgrep -l x`).
#
# Judged per command word, read from the shell's own segments, so quoted text, a comment and a
# commit message never fire it (rule building-scanner-respects-strings). The wrappers are read by
# guard_core's `command_indexes` and `inner_commands` (`sudo`, `env`, `xargs`, `bash -c`, `$(...)`),
# the one home of that unwrapping.
#
# ACCEPTED LIMITS: `ps` and `pgrep` flags are read as procps reads them, so a `ps` of another
# family (busybox) may read a flag differently. `ps -aux` is read as the BSD `aux`, which it
# prints as. What is still unread is listed in the ruling, under "Not read".

PROCESS_ARGS_REASON = (
    "this prints other processes' full arguments, and an argument can hold a secret, such as an "
    "auth key in a flag, which then sits in the transcript. "
    "Remedy: list processes by pid and name. Run `ps -o pid,comm`, or `pgrep -l x` for a "
    "name. `pgrep -f x` matches the full command line and prints pids only. "
    "`ps -o ppid= -p <pid>` gives a parent, and `ps -o lstart= -p <pid>` a start time. "
    "(decision process-args-guard, a session never prints process arguments)"
)

# `ps -o` fields that hold the full argument list. `comm` is the executable name and stays allowed.
PS_ARGS_FIELDS = {"args", "cmd", "command", "uargs"}
# `ps` short options that take a value: the rest of the cluster, or the next word.
PS_VALUE_SHORT = "oOpqCGgUutsn"
PS_FORMAT_SHORT = "oO"
PS_VALUE_LONG = {
    "--sort", "--pid", "--ppid", "--sid", "--tty", "--user", "--User", "--group", "--Group", "--cols",
    "--columns", "--lines", "--rows", "--width", "--quick-pid", "--format",
}
PSTREE_VALUE_SHORT = "CHN"
TOP_VALUE_SHORT = "dEenopUuw"
PGREP_VALUE_SHORT = "dFgGJPstuUr"
PGREP_VALUE_LONG = {"--delimiter", "--pidfile", "--pgroup", "--group", "--parent", "--session",
                    "--terminal", "--euid", "--uid", "--runstates", "--ns", "--nslist", "--signal"}

CMDLINE_PATH = re.compile(r"^/proc/([^/]+)(?:/task/[^/]+)?/cmdline$")
# A path that reads no other process: the shell's own pid, and `self`.
OWN_PROCESS = {"self", "thread-self", "$$"}
# Commands that take a cmdline path and print no content from it: text, names, sizes, tests. Every
# other command word that takes the path is a reader. `xargs` is never exempt: it feeds the file on.
NOT_READERS = {"echo", "printf", "ls", "stat", "test", "[", "[[", "wc", "file", "readlink", "realpath",
               "basename", "dirname", "find", "cd"}
# PowerShell reads of the process table. `Win32_Process` goes with the CIM and WMI readers; the
# process cmdlets stand alone. `ps` is Get-Process only under PowerShell's reading.
PS_CIM_READERS = {"get-ciminstance", "gcim", "get-wmiobject", "gwmi"}
PS_PROCESS_READERS = {"get-process", "gps", "ps"}
PS_PART_SPLIT = re.compile(r"[,.(){}|;@]")
REDIRECT_TARGET_OPEN = " \t"


def _field_names(value: str):
    return [re.split(r"[=:]", field, maxsplit=1)[0].lower() for field in re.split(r"[,\s]+", value) if field]


def _ps_prints_args(args) -> bool:
    """True when the arguments of a `ps` ask for a column of full arguments. An explicit format
    (`-o`) decides alone. Without one, `-f` or `-F`, the BSD `x` flag, or a BSD operand (`aux`, `ax`,
    a pid list), prints them."""
    fields, full, bsd_operand, bsd_x, skip = [], False, False, False, False
    args = list(args)
    if args:
        args[-1] = args[-1].rstrip(")")   # a subshell's closing paren glued to the last word
    for index, arg in enumerate(args):
        if skip:
            skip = False
            continue
        if arg.startswith("--"):
            flag, glued, value = arg.partition("=")
            if flag == "--format":
                if not glued and index + 1 < len(args):
                    value, skip = args[index + 1], True
                fields += _field_names(value)
            elif not glued and flag in PS_VALUE_LONG:
                skip = True
            continue
        if not arg.startswith("-") or arg == "-":
            bsd_operand = True
            continue
        cluster = arg[1:]
        if {"a", "u", "x"} <= set(cluster):
            return True   # `ps -aux` is read as the BSD `aux`
        for at, letter in enumerate(cluster):
            if letter in "fF":
                full = True
            if letter == "x":
                bsd_x = True   # BSD `x`: the processes with no terminal, listed with full arguments
            if letter not in PS_VALUE_SHORT:
                continue
            value = cluster[at + 1:].lstrip("=")
            if not value and index + 1 < len(args):
                value, skip = args[index + 1], True
            if letter == "O":
                return True   # `-O` adds columns to the default format, which holds the arguments
            if letter in PS_FORMAT_SHORT:
                fields += _field_names(value)
            break
    if fields:
        return any(field in PS_ARGS_FIELDS for field in fields)
    return full or bsd_operand or bsd_x


def _pgrep_prints_args(args) -> bool:
    """True when `pgrep` lists full arguments: `-a`, or `-l` together with `-f`."""
    list_full = list_name = match_full = skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg.startswith("--"):
            flag, glued, _ = arg.partition("=")
            list_full = list_full or flag == "--list-full"
            list_name = list_name or flag == "--list-name"
            match_full = match_full or flag == "--full"
            skip = not glued and flag in PGREP_VALUE_LONG
            continue
        if not arg.startswith("-") or arg == "-":
            continue
        cluster = arg[1:]
        for at, letter in enumerate(cluster):
            list_full = list_full or letter == "a"
            list_name = list_name or letter == "l"
            match_full = match_full or letter == "f"
            if letter in PGREP_VALUE_SHORT:
                skip = not cluster[at + 1:]
                break
    return list_full or (list_name and match_full)


def _cluster_has(args, letter: str, value_short: str, long_flag: str) -> bool:
    """True when `pstree` or `top` is given an option: `letter` in a short cluster, read up to the
    first option that takes a value (`top -bn1` is `b`, `n` and the value `1`), or `long_flag`."""
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg.startswith("--"):
            if long_flag and arg.partition("=")[0] == long_flag:
                return True
            continue
        if not arg.startswith("-") or arg == "-":
            continue
        cluster = arg[1:].rstrip(")")
        for at, char in enumerate(cluster):
            if char == letter:
                return True
            if char in value_short:
                skip = not cluster[at + 1:]
                break
    return False


def _cmdline_word(word: str) -> bool:
    """True when `word` is `/proc/<pid>/cmdline` of another process: a number, a glob or a variable."""
    found = CMDLINE_PATH.match(word)
    if not found or found.group(1) in OWN_PROCESS:
        return False
    middle = found.group(1)
    return bool(re.fullmatch(r"[0-9]+", middle) or re.search(r"[*?\[]", middle) or middle.startswith("$"))


def _find_exec_reads(tokens) -> bool:
    """True when a `find` in the segment hands its paths to a command that reads them: the command
    after `-exec`, `-execdir`, `-ok` or `-okdir` is no `NOT_READERS` word."""
    for at in command_indexes(tokens):
        if basename(tokens[at]) != "find":
            continue
        for text in wrapped_commands(tokens, at):
            inner = segment_tokens(text) if text.strip() else None
            starts = command_indexes(inner) if inner else []
            if starts and basename(inner[starts[0]]) not in NOT_READERS:
                return True
    return False


def _cmdline_read(tokens) -> str:
    """The cmdline path a segment hands to a command that reads it, else ''. A segment whose every
    command word only names or measures the file passes, unless `xargs` feeds the file on or a
    `find` runs a reader on it. The pattern word of a search command is no file."""
    pattern_at = set()
    for at in command_indexes(tokens):
        if basename(tokens[at]) in ENV_PATTERN_COMMANDS:
            pattern_at |= _pattern_words(tokens, at, basename(tokens[at]))[0]
    paths = [word for at, word in enumerate(tokens) if at and at not in pattern_at and _cmdline_word(word)]
    if not paths:
        return ""
    tools = [basename(tokens[at]) for at in command_indexes(tokens)]
    if "find" in tools and _find_exec_reads(tokens):
        return "find " + paths[0]
    if tools and all(tool in NOT_READERS for tool in tools) and "xargs" not in map(basename, tokens):
        return ""
    return (tools[0] + " " if tools else "") + paths[0]


def _parts(token: str):
    """The lower-case names inside one token: `Name,CommandLine` and `$_.CommandLine` split into words.
    A quoted sentence stays one part, so a filter that only mentions a property is no selection."""
    return [part.strip().lower() for part in PS_PART_SPLIT.split(token)]


def _wmic_reads_command_line(args) -> bool:
    """True for `wmic process ... get ...commandline`: the process alias and a CommandLine word."""
    parts = [part for arg in args for part in _parts(arg)]
    return "process" in parts and "commandline" in parts


def _powershell_hit(text: str) -> str:
    """The matched text when PowerShell text reads a process's `CommandLine`: a pipeline (segments
    joined by `|`) that starts from a process reader and names the property, however it selects it.
    `Get-CimInstance Win32_Process | Select CommandLine`, `(Get-WmiObject Win32_Process).CommandLine`
    and `Get-Process | Select Name,CommandLine` all match. A pid-and-name selection and text pass."""
    if not is_powershell(text):
        return ""
    ends = []
    segments = split_segments(text, ends)
    if len(ends) != len(segments):
        ends = [""] * len(segments)
    pipeline, parts, sources = [], [], set()
    for segment, end in zip(segments, ends):
        tokens = segment_tokens(segment) if segment.strip() else None
        for at in command_indexes(tokens) if tokens else ():
            sources.add(basename(tokens[at]))
        for token in tokens or ():
            parts += _parts(token)
        pipeline.append(segment.strip())
        if end == "|":
            continue
        reads_table = sources & PS_PROCESS_READERS or (sources & PS_CIM_READERS and "win32_process" in parts)
        if reads_table and "commandline" in parts:
            return " | ".join(pipeline)
        pipeline, parts, sources = [], [], set()
    return ""


def _redirect_sources(segment: str):
    """The word after each unquoted `<` of one segment (a file read as stdin), dequoted. A heredoc
    (`<<`), a here-string (`<<<`), a process substitution (`<(`) and a descriptor copy (`<&`) are
    no file."""
    for index, char, quote in walk_quotes(segment):
        if char != "<" or quote:
            continue
        after = segment[index + 1:index + 2]
        if after in ("<", "(", "&") or (index and segment[index - 1] == "<"):
            continue
        rest = segment[index + 1:].lstrip(REDIRECT_TARGET_OPEN)
        end = len(rest)
        for at, mark, open_quote in walk_quotes(rest):
            if not open_quote and mark in " \t\r\n;|&<>()":
                end = at
                break
        try:
            words = shlex.split(rest[:end])
        except ValueError:
            continue
        if words:
            yield words[0]


def _segment_hit(segment: str) -> str:
    """The matched text when one segment, or a command it hands on, prints process arguments."""
    tokens = segment_tokens(segment) if segment.strip() else None
    if not tokens:
        return ""
    for word in _redirect_sources(segment):
        if _cmdline_word(word):
            return "< " + word
    for start in command_indexes(tokens):
        tool, args = basename(tokens[start]), tokens[start + 1:]
        if tool == "ps" and _ps_prints_args(args):
            return "ps " + " ".join(args)
        if tool == "pgrep" and _pgrep_prints_args(args):
            return "pgrep " + " ".join(args)
        if tool == "pstree" and _cluster_has(args, "a", PSTREE_VALUE_SHORT, "--arguments"):
            return "pstree " + " ".join(args)
        if tool == "top" and _cluster_has(args, "c", TOP_VALUE_SHORT, ""):
            return "top " + " ".join(args)
        if tool in ("wmic", "wmic.exe") and _wmic_reads_command_line(args):
            return "wmic " + " ".join(args)
    matched = _cmdline_read(tokens)
    if matched:
        return matched
    for text in inner_commands(tokens):
        matched = _text_hit(text)
        if matched:
            return matched
    return ""


def _text_hit(text: str) -> str:
    """The matched text when one command text prints process arguments: judged per segment, then as
    PowerShell pipelines."""
    for segment in split_segments(text):
        matched = _segment_hit(segment)
        if matched:
            return matched
    return _powershell_hit(text)


def process_args_hit(raw: str, stripped: str) -> str:
    """Return the matched text when the command prints other processes' full arguments, else ''.
    Reads the command and each substitution in it as commands of their own (`substitution_commands`)."""
    for text in [stripped, *substitution_commands(raw, stripped)]:
        matched = _text_hit(text)
        if matched:
            return matched
    return ""

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
