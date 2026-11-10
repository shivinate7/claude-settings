"""The guard's process-args family: a command that prints other processes' full arguments.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import re
import shlex

from guard_core import (
    basename, command_indexes, inner_commands, segment_tokens, split_segments, walk_quotes,
)
from guard_env import substitution_commands


# ------------------------------------------------------------------ process arguments
#
# A process's full arguments can hold a secret, such as an auth key in a flag, and a session that
# prints them puts the secret in its transcript. Three acts print them:
#   - `ps` with an args column: `ps aux`, `ps -ef`, `ps -f`, `ps -o args|command|cmd`.
#   - `pgrep` with `-a`, or with `-l` and `-f` together.
#   - a read of `/proc/<pid>/cmdline`: `cat` of the file, or any command fed it with `<`.
# A pid, a name, a parent id and a start time stay allowed (`ps -o pid,comm`, `pgrep -l x`).
#
# Judged per command word, read from the shell's own segments, so quoted text, a comment and a
# commit message never fire it (rule building-scanner-respects-strings). The wrappers are read by
# guard_core's `command_indexes` and `inner_commands` (`sudo`, `env`, `xargs`, `bash -c`, `$(...)`),
# the one home of that unwrapping.
#
# ACCEPTED LIMITS: `ps` and `pgrep` flags are read as procps reads them, so a `ps` of another
# family (BSD, busybox) may read a flag differently. A `ps` whose format comes from the
# environment (`PS_FORMAT`) is not read. `/proc/<pid>/environ`, `head`, `strings` or `xargs -a` on
# a cmdline file, and a script that reads the file, are not covered. `ps -aux` is read as the BSD
# `aux`, which it prints as.

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
PGREP_VALUE_SHORT = "dFgGJPstuUr"
PGREP_VALUE_LONG = {"--delimiter", "--pidfile", "--pgroup", "--group", "--parent", "--session",
                    "--terminal", "--euid", "--uid", "--runstates", "--ns", "--nslist", "--signal"}

CMDLINE_PATH = re.compile(r"^/proc/([^/]+)/cmdline$")
# A path that reads no other process: the shell's own pid, and `self`.
OWN_PROCESS = {"self", "thread-self", "$$"}
CMDLINE_READERS = {"cat", "tac"}
REDIRECT_TARGET_OPEN = " \t"


def _field_names(value: str):
    return [re.split(r"[=:]", field, maxsplit=1)[0].lower() for field in re.split(r"[,\s]+", value) if field]


def _ps_prints_args(args) -> bool:
    """True when the arguments of a `ps` ask for a column of full arguments. An explicit format
    (`-o`) decides alone. Without one, `-f` or `-F`, or a BSD operand (`aux`, `ax`, a pid list),
    prints them."""
    fields, full, bsd_operand, skip = [], False, False, False
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
    return full or bsd_operand


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


def _cmdline_word(word: str) -> bool:
    """True when `word` is `/proc/<pid>/cmdline` of another process: a number, a glob or a variable."""
    found = CMDLINE_PATH.match(word)
    if not found or found.group(1) in OWN_PROCESS:
        return False
    middle = found.group(1)
    return bool(re.fullmatch(r"[0-9]+", middle) or re.search(r"[*?\[]", middle) or middle.startswith("$"))


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
        if tool in CMDLINE_READERS:
            for word in args:
                if _cmdline_word(word):
                    return tool + " " + word
    for text in inner_commands(tokens):
        for part in split_segments(text):
            matched = _segment_hit(part)
            if matched:
                return matched
    return ""


def process_args_hit(raw: str, stripped: str) -> str:
    """Return the matched text when the command prints other processes' full arguments, else ''.
    Reads the command and each substitution in it as commands of their own (`substitution_commands`)."""
    for text in [stripped, *substitution_commands(raw, stripped)]:
        for segment in split_segments(text):
            matched = _segment_hit(segment)
            if matched:
                return matched
    return ""

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
