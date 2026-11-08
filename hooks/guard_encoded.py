"""The guard's encoded-retry family: a refused command is not sent again in another form.

guard.py is the only entry point. A Bash call that decodes text and runs it, or whose command word is
built from `$'...'` escapes, is the usual second form of a call the harness or a guard just refused. It is
refused when its own session had a refusal in the last ten minutes (decision encoded-retry-after-refusal).
The call's shape is read first and costs nothing on an ordinary command. The refusal state is read only
when the shape matches.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta

import local_time
import shared_names
from guard_core import (basename, nested_script, resolve_command, segment_tokens, session_log_field, split_segments,
                        walk_quotes)

ENCODED_RETRY_REASON = (
    "a refusal is final, and this call is the refused act in another form: it decodes text and runs it, or "
    "builds its command word from escapes, within ten minutes of a refusal in this session. "
    "Remedy: do not send the act again in any form. Stop, and report the refusal and what you needed to your "
    "orchestrator or the owner. "
    "(decision encoded-retry-after-refusal, a refusal is final)"
)

WINDOW = timedelta(minutes=10)
SKEW = timedelta(minutes=1)        # a row stamped slightly ahead of this hook's clock still counts
LOG_TAIL_BYTES = 256 * 1024        # guard.log is read from its end, never whole
LINT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lint")
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
# An escape that builds a byte: hex, octal, or a code point.
ESCAPE = re.compile(r"\\(?:x[0-9a-fA-F]|[0-7]{1,3}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8})")
BASE64_DECODE = re.compile(r"--decode|-[A-Za-z0-9]*[dD][A-Za-z0-9]*")
ECHO_E = re.compile(r"-[neE]*e[neE]*")
DEPTH = 3   # script text handed to `sh -c`, read as a command of its own, this many levels down


MARK = re.compile("\x00(\\d+)\x00")
ASSIGN = re.compile(r"[A-Za-z_]\w*=")
DECLARERS = {"export", "declare", "local", "readonly", "typeset"}   # their arguments are assignments too


def _clean(tokens):
    """The tokens with the glued `(` of a subshell and `)` that closes it taken off the first and last word."""
    out = list(tokens)
    if out and len(out[0]) > 1 and out[0].startswith("("):
        out[0] = out[0].lstrip("(")
    if out and len(out[-1]) > 1 and out[-1].endswith(")"):
        out[-1] = out[-1].rstrip(")")
    return out


def _closers(text: str, states) -> dict:
    """{index of each `(` outside single quotes: index of the `)` that closes it}, in one pass. It counts as a walk
    from each opener would count, so an opener closes where that walk would stop, and an unclosed one is absent."""
    closes, stack = {}, []
    for index, char in enumerate(text):
        if states.get(index) in ("'", "$'"):
            continue
        if char == "(":
            stack.append(index)
        elif char == ")" and stack:
            closes[stack.pop()] = index
    return closes


def _mark(text: str, table: list):
    """(marked text, indices of its new spans). Each outermost `$(...)`, `<(...)`, `>(...)` or backtick pair outside
    single quotes becomes one marker word, and table[n] holds (the text inside it, the text as written). A pipe or a
    space inside a substitution then cuts no segment. One table serves a whole call, so a script cut from marked text
    keeps the meaning of its markers. Linear: parens are matched in one pass, and the first backtick that never closes
    ends the backtick search (bash runs no part of an unclosed substitution)."""
    states = {index: quote for index, _, quote in walk_quotes(text)}
    closes_at = _closers(text, states)
    out, first, i, n, backticks = [], len(table), 0, len(text), True
    while i < n:
        quote = states.get(i)
        closes = -1
        if quote not in ("'", "$'"):
            if text.startswith("$(", i) or (quote in ("", None) and text.startswith(("<(", ">("), i)):
                closes = closes_at.get(i + 1, -1)
                inner = text[i + 2:closes]
            elif text[i] == "`" and backticks:
                j = i + 1
                while j < n and text[j] != "`":
                    j += 2 if text[j] == "\\" else 1
                closes, inner = (j if j < n else -1), text[i + 1:j].replace("\\`", "`")
                backticks = closes >= 0
        if closes < 0:
            out.append(text[i])
            i += 1
            continue
        out.append("\x00%d\x00" % len(table))
        table.append((inner, text[i:closes + 1]))
        i = closes + 1
    return "".join(out), range(first, len(table))


def _unmark(text: str, table: list) -> str:
    """The text with each marker put back as written, and no NUL left: a matched text goes to guard.log."""
    def written(match):
        number = int(match.group(1))
        return table[number][1] if number < len(table) else " "
    for _ in range(len(table) + 1):   # a span cut from a nested script can hold an outer marker
        if not MARK.search(text):
            break
        text = MARK.sub(written, text)
    return text.replace("\x00", " ")


def _command(tokens):
    """(command word without its path, its index), or ("", None)."""
    at = resolve_command(tokens) if tokens else None
    return ("", None) if at is None else (basename(tokens[at]), at)


def _raw_words(segment: str):
    """The segment's shell words as written, quotes kept, split on unquoted white space."""
    words, start = [], None
    for index, char, quote in walk_quotes(segment):
        if not quote and char in " \t\r\n":
            if start is not None:
                words.append(segment[start:index])
            start = None
            continue
        start = index if start is None else start
    if start is not None:
        words.append(segment[start:])
    return words


def _ansi_c_escape(word: str) -> bool:
    """True when a raw word holds an ANSI-C `$'...'` span and an escape."""
    return any(quote == "$'" for _, _, quote in walk_quotes(word)) and bool(ESCAPE.search(word))


def _ansi_args(words, tokens, at: int) -> bool:
    """True when an argument of the command at `at` is written as an ANSI-C escape word."""
    return any(map(_ansi_c_escape, words[at + 1:] if len(words) == len(tokens) else words[1:]))


def _decodes(tokens, words) -> bool:
    """True when one segment turns text into other text: `base64 -d`, `printf` or `echo -e` with an escape, or
    `echo` or `printf` of an ANSI-C escape word."""
    word, at = _command(tokens)
    if at is None:
        return False
    args = tokens[at + 1:]
    if word == "base64":
        return any(BASE64_DECODE.fullmatch(arg) for arg in args)
    if word == "printf":
        return any(ESCAPE.search(arg) for arg in args)
    if word == "echo":
        return (any(ECHO_E.fullmatch(arg) for arg in args) and any(ESCAPE.search(arg) for arg in args)
                or _ansi_args(words, tokens, at))
    return False


def _text_decodes(text: str, table: list, depth: int = 0) -> bool:
    """True when a command text, a substitution's inside, has a segment that decodes, at any substitution depth."""
    marked, _ = _mark(text, table)
    for segment in split_segments(marked):
        tokens = segment_tokens(segment) if segment.strip() else None
        if tokens and _decodes(_clean(tokens), _raw_words(segment)):
            return True
    return depth < DEPTH and any(_text_decodes(_span(table, n), table, depth + 1) for n in MARK.findall(marked))


def _span(table: list, number) -> str:
    """The text inside marker `number`, or '' for a number the table never gave out."""
    number = int(number)
    return table[number][0] if number < len(table) else ""


def _stdin_shell(tokens) -> bool:
    """True for a shell that runs what a pipe hands it: no `-c`."""
    word, at = _command(tokens)
    if word not in SHELLS:
        return False
    flags = []
    for arg in tokens[at + 1:]:
        if not arg.startswith("-") or arg == "--":
            break
        flags.append(arg)
    return not any(not flag.startswith("--") and "c" in flag for flag in flags)


def _shell_sinks(tokens, at: int):
    """The words a shell takes as a script: the word after `-c`, else the first non-flag word, a herestring's, and
    the file its stdin reads (`sh < <(...)`)."""
    args, sinks, flags, skip = tokens[at + 1:], [], True, False
    for index, arg in enumerate(args):
        following = args[index + 1] if index + 1 < len(args) else ""
        if skip:
            skip = False
        elif arg.startswith("<<<"):
            sinks.append(arg[3:] or following)
        elif arg.startswith("<") and not arg.startswith("<<"):
            sinks.append(arg[1:] or following)
            skip = not arg[1:]
        elif flags and arg.startswith("-") and arg != "--":
            if not arg.startswith("--") and "c" in arg and index + 1 < len(args):
                sinks.append(args[index + 1])
                flags = False
        elif flags:
            sinks.append(arg)
            flags = False
    return sinks


def _scan_text(text: str, table: list, depth: int = 0, tainted=None) -> str:
    """The matched text of one command text, else ''. It may hold markers of `table`; the match may too."""
    marked, made = _mark(text, table)
    tainted = set() if tainted is None else tainted   # names assigned from a substitution that decodes

    def decoded(word: str) -> bool:
        if any(_text_decodes(_span(table, n), table, 1) for n in MARK.findall(word)):
            return True
        return any(re.search(r"\$\{?%s\b" % re.escape(name), word) for name in tainted)

    def taint(assignments):
        for token in assignments:
            if ASSIGN.match(token) and decoded(token):
                tainted.add(token.split("=", 1)[0])

    ends = []
    segments = split_segments(marked, ends)
    parsed = [segment_tokens(segment) if segment.strip() else None for segment in segments]
    for number, segment in enumerate(segments):
        tokens = parsed[number]
        if not tokens:
            continue
        tokens = _clean(tokens)
        # `NAME=$(... decode ...)`, alone or after `export`, taints NAME for the rest of the call
        leading = next((index for index, token in enumerate(tokens) if not ASSIGN.match(token)), len(tokens))
        taint(tokens[:leading])
        word, at = _command(tokens)
        if at is None:
            continue
        if word in DECLARERS:
            taint(tokens[at + 1:])
        if decoded(tokens[at]):   # the command word is a substitution that decodes, or a decoded variable
            return segment.strip()
        words = _raw_words(segment)
        if word in SHELLS:
            if _stdin_shell(tokens):   # a pipeline that decodes into a shell
                back = number - 1
                while back >= 0 and back < len(ends) and ends[back] == "|":
                    if parsed[back] and _decodes(_clean(parsed[back]), _raw_words(segments[back])):
                        return segment.strip()
                    back -= 1
            if any(decoded(sink) for sink in _shell_sinks(tokens, at)):
                return segment.strip()
            if "<<<" in tokens[:-1] and _ansi_args(words, tokens, at):
                return segment.strip()
        # a command word spelled as an ANSI-C escape word, or a substitution that decodes
        spelled = words[at] if len(words) == len(tokens) else (words[0] if words else "")
        if _ansi_c_escape(spelled):
            return spelled
        if word in ("eval", "source", ".") and any(decoded(arg) for arg in tokens[at + 1:]):
            return segment.strip()
        if depth < DEPTH:
            script = nested_script(tokens)
            if script and not script.isspace():
                found = _scan_text(script, table, depth + 1, set(tainted))
                if found:
                    return found
    if depth < DEPTH:   # each substitution's inside is a command text of its own: `OUT=$(... | base64 -d | sh)`
        for number in made:
            found = _scan_text(table[number][0], table, depth + 1, set(tainted))
            if found:
                return found
    return ""


def encoded_form_hit(stripped: str) -> str:
    """The matched text when the call decodes text and runs it, or has an ANSI-C escape command word, else ''.
    Reads the text only. `stripped` is the command without its heredoc bodies. The match holds no NUL."""
    if "base64" not in stripped and "\\" not in stripped and "$'" not in stripped:
        return ""   # none of the shapes can be here
    table = []
    # A NUL is the marker's own byte, and bash cannot carry one in a command, so a NUL in the call is a space.
    return _unmark(_scan_text(stripped.replace("\x00", " "), table), table)


def _stamp(text):
    """A row's time as an aware datetime, or None when it does not read."""
    try:
        when = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo else when.astimezone()


def _fresh(when, now) -> bool:
    return when is not None and -SKEW <= now - when <= WINDOW


def _state_row_counts(row, agent_id: str, now) -> bool:
    """A refusal state row counts when it is fresh and names no agent, or names the calling agent."""
    if not isinstance(row, dict) or not _fresh(_stamp(row.get("ts")), now):
        return False
    named = row.get("agent_id")
    return not (isinstance(named, str) and named) or named == agent_id


def _state_refusal(session_id: str, agent_id: str, now) -> bool:
    path = shared_names.refusals_path(session_id)
    if path is None:
        return False
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:   # a truncated line is skipped, as refusal_note.py skips it
                    row = json.loads(line)
                except ValueError:
                    continue
                if _state_row_counts(row, agent_id, now):
                    return True
    except OSError:
        pass
    return False


def _log_refusal(session_id: str, now) -> bool:
    """A guard.log deny row of this session inside the window. A row names no agent, so it counts for the session.
    Rows are read through lint/guard_log_report.py, the one reader of guard.log lines. An unimportable reader is no
    refusal: this rule fails open."""
    path = os.path.join(shared_names.config_dir(), "guard.log")
    names = {session_id, session_log_field(session_id)}
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - LOG_TAIL_BYTES))
            tail = handle.read().decode("utf-8", errors="replace")
        if LINT_DIR not in sys.path:
            sys.path.insert(0, LINT_DIR)
        import guard_log_report  # lint/guard_log_report.py, the one reader of guard.log lines
    except Exception:
        return False
    for line in tail.split("\n"):
        row = guard_log_report.parse_line(line)
        if row is None or row.decision != "deny" or row.session not in names:
            continue
        when = row.at or row.when   # an offset time is one instant; a zone-less one reads as local time
        if _fresh(when if when.tzinfo else when.astimezone(), now):
            return True
    return False


def recent_refusal(session_id: str, agent_id: str = "") -> bool:
    """True when the session had a refusal in the last ten minutes. An unreadable state is no refusal."""
    if not session_id:
        return False
    try:
        now = local_time.clock()
        return _state_refusal(session_id, agent_id, now) or _log_refusal(session_id, now)
    except Exception:
        return False


def encoded_retry_hit(stripped: str, session_id: str, agent_id: str = "") -> str:
    """The matched text of an encoded retry, else ''. The refusal state is read only once the shape matches. A fault in
    the scan fails this rule open and no other: the rules after it in judge_shell still run."""
    try:
        matched = encoded_form_hit(stripped)
    except Exception:
        return ""
    if matched and recent_refusal(session_id, agent_id):
        return matched
    return ""

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
