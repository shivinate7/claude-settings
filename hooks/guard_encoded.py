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
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
# An escape that builds a byte: hex, octal, or a code point.
ESCAPE = re.compile(r"\\(?:x[0-9a-fA-F]|[0-7]{1,3}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8})")
BASE64_DECODE = re.compile(r"--decode|-[A-Za-z0-9]*[dD][A-Za-z0-9]*")
ECHO_E = re.compile(r"-[neE]*e[neE]*")
DEPTH = 3   # script text handed to `sh -c`, read as a command of its own, this many levels down


MARK = re.compile("\x00(\\d+)\x00")
ASSIGN = re.compile(r"[A-Za-z_]\w*=")


def _clean(tokens):
    """The tokens with the glued `(` of a subshell and `)` that closes it taken off the first and last word."""
    out = list(tokens)
    if out and len(out[0]) > 1 and out[0].startswith("("):
        out[0] = out[0].lstrip("(")
    if out and len(out[-1]) > 1 and out[-1].endswith(")"):
        out[-1] = out[-1].rstrip(")")
    return out


def _mark(text: str):
    """(text, spans): each outermost `$(...)`, `<(...)`, `>(...)` or backtick pair outside single quotes becomes one
    marker word, and spans[n] holds the text inside it. A pipe or a space inside a substitution then cuts no segment."""
    states = {index: quote for index, _, quote in walk_quotes(text)}
    out, spans, i, n = [], [], 0, len(text)
    while i < n:
        quote = states.get(i)
        closes = -1
        if quote not in ("'", "$'"):
            if text.startswith("$(", i) or (quote in ("", None) and text.startswith(("<(", ">("), i)):
                depth, j = 1, i + 2
                while j < n:
                    if states.get(j) not in ("'", "$'"):
                        depth += text[j] == "("
                        depth -= text[j] == ")"
                        if not depth:
                            break
                    j += 1
                closes, inner = (j if j < n else -1), text[i + 2:j]
            elif text[i] == "`":
                j = i + 1
                while j < n and text[j] != "`":
                    j += 2 if text[j] == "\\" else 1
                closes, inner = (j if j < n else -1), text[i + 1:j].replace("\\`", "`")
        if closes < 0:
            out.append(text[i])
            i += 1
            continue
        out.append("\x00%d\x00" % len(spans))
        spans.append(inner)
        i = closes + 1
    return "".join(out), spans


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


def _text_decodes(text: str, depth: int = 0) -> bool:
    """True when a command text, a substitution's inside, has a segment that decodes, at any substitution depth."""
    marked, spans = _mark(text)
    for segment in split_segments(marked):
        tokens = segment_tokens(segment) if segment.strip() else None
        if tokens and _decodes(_clean(tokens), _raw_words(segment)):
            return True
    return depth < DEPTH and any(_text_decodes(inner, depth + 1) for inner in spans)


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
    """The words a shell takes as a script: the word after `-c`, else the first non-flag word, and a herestring's."""
    args, sinks, flags = tokens[at + 1:], [], True
    for index, arg in enumerate(args):
        if arg.startswith("<<<"):
            sinks.append(arg[3:] or (args[index + 1] if index + 1 < len(args) else ""))
        elif flags and arg.startswith("-") and arg != "--":
            if not arg.startswith("--") and "c" in arg and index + 1 < len(args):
                sinks.append(args[index + 1])
                flags = False
        elif flags:
            sinks.append(arg)
            flags = False
    return sinks


def _scan_text(text: str, depth: int = 0) -> str:
    """The matched text of one command text, else ''."""
    marked, spans = _mark(text)
    tainted = set()   # names assigned from a substitution that decodes

    def decoded(word: str) -> bool:
        if any(_text_decodes(spans[int(n)], 1) for n in MARK.findall(word)):
            return True
        return any(re.search(r"\$\{?%s\b" % name, word) for name in tainted)

    ends = []
    segments = split_segments(marked, ends)
    parsed = [segment_tokens(segment) if segment.strip() else None for segment in segments]
    for number, segment in enumerate(segments):
        tokens = parsed[number]
        if not tokens:
            continue
        tokens = _clean(tokens)
        for token in tokens:   # `NAME=$(... decode ...)` taints NAME for the rest of the call
            if not ASSIGN.match(token):
                break
            if decoded(token):
                tainted.add(token.split("=", 1)[0])
        word, at = _command(tokens)
        if at is None:
            continue
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
        if tokens[at].startswith("\x00") and decoded(tokens[at]):
            return segment.strip()
        if word in ("eval", "source", ".") and any(decoded(arg) for arg in tokens[at + 1:]):
            return segment.strip()
        if depth < DEPTH:
            script = nested_script(tokens)
            if script and not script.isspace():
                found = _scan_text(script, depth + 1)
                if found:
                    return found
    return ""


def encoded_form_hit(stripped: str) -> str:
    """The matched text when the call decodes text and runs it, or has an ANSI-C escape command word, else ''.
    Reads the text only. `stripped` is the command without its heredoc bodies."""
    if "base64" not in stripped and "\\" not in stripped and "$'" not in stripped:
        return ""   # none of the shapes can be here
    return _scan_text(stripped)


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
    """A guard.log deny row of this session inside the window. A row names no agent, so it counts for the session."""
    path = os.path.join(shared_names.config_dir(), "guard.log")
    names = {session_id, session_log_field(session_id)}
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - LOG_TAIL_BYTES))
            tail = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return False
    for line in tail.split("\n"):
        fields = line.split("\t")
        if len(fields) >= 6 and fields[2] == "deny" and fields[5] in names and _fresh(_stamp(fields[0]), now):
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
    """The matched text of an encoded retry, else ''. The refusal state is read only once the shape matches."""
    matched = encoded_form_hit(stripped)
    if matched and recent_refusal(session_id, agent_id):
        return matched
    return ""

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
