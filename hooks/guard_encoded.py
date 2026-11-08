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
from datetime import datetime, timedelta, timezone

import local_time
import shared_names
from guard_core import (basename, resolve_command, segment_tokens, session_log_field, split_segments,
                        walk_quotes, nested_script)
from guard_env import substitution_commands

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


def _decodes(tokens) -> bool:
    """True when one segment turns text into other text: `base64 -d`, or `printf` or `echo -e` with an escape."""
    at = resolve_command(tokens) if tokens else None
    if at is None:
        return False
    word, args = basename(tokens[at]), tokens[at + 1:]
    if word == "base64":
        return any(BASE64_DECODE.fullmatch(arg) for arg in args)
    if word == "printf":
        return any(ESCAPE.search(arg) for arg in args)
    if word == "echo":
        return any(ECHO_E.fullmatch(arg) for arg in args) and any(ESCAPE.search(arg) for arg in args)
    return False


def _reads_stdin_as_script(tokens) -> bool:
    """True for a shell with no `-c`: it runs what a pipe hands it."""
    at = resolve_command(tokens) if tokens else None
    if at is None or basename(tokens[at]) not in SHELLS:
        return False
    flags = []
    for arg in tokens[at + 1:]:
        if not arg.startswith("-") or arg == "--":
            break
        flags.append(arg)
    return not any(not flag.startswith("--") and "c" in flag for flag in flags)


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


def _scan_text(text: str, inner_decodes, depth: int) -> str:
    """The matched text of one command text, else ''. `inner_decodes` is a function that says whether any
    command substitution of the whole call decodes."""
    ends = []
    segments = split_segments(text, ends)
    parsed = [segment_tokens(segment) for segment in segments]
    for number, segment in enumerate(segments):
        tokens = parsed[number]
        if tokens is None:
            continue
        # a pipeline that decodes into a shell
        if _reads_stdin_as_script(tokens):
            back = number - 1
            while back >= 0 and back < len(ends) and ends[back] == "|":
                if parsed[back] and _decodes(parsed[back]):
                    return segment.strip()
                back -= 1
        at = resolve_command(tokens)
        if at is None:
            continue
        # a command word spelled as an ANSI-C escape word
        words = _raw_words(segment)
        spelled = words[at] if len(words) == len(tokens) else (words[0] if words else "")
        if _ansi_c_escape(spelled):
            return spelled
        # a command word that is a substitution which decodes, or eval or source of one
        word, args = tokens[at], tokens[at + 1:]
        if word.startswith(("$(", "`")) and inner_decodes():
            return segment.strip()
        if basename(word) in ("eval", "source", ".") and any(
                "$(" in arg or "`" in arg or "<(" in arg for arg in args) and inner_decodes():
            return segment.strip()
        if depth < DEPTH:
            script = nested_script(tokens)
            if script and not script.isspace():
                found = _scan_text(script, lambda: False, depth + 1)
                if found:
                    return found
    return ""


def encoded_form_hit(raw: str, stripped: str) -> str:
    """The matched text when the call decodes text and runs it, or has an ANSI-C escape command word, else ''.
    Reads the text only. `raw` and `stripped` are the command with and without its heredoc bodies."""
    if "base64" not in stripped and "\\" not in stripped and "$'" not in stripped:
        return ""   # none of the three shapes can be here
    inners = substitution_commands(raw, stripped)
    state = []

    def inner_decodes() -> bool:
        if not state:
            state.append(any(_decodes(segment_tokens(segment))
                             for text in inners for segment in split_segments(text)
                             if segment.strip() and segment_tokens(segment) is not None))
        return state[0]

    for text in [stripped, *inners]:
        found = _scan_text(text, inner_decodes, 0)
        if found:
            return found
    return ""


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


def encoded_retry_hit(raw: str, stripped: str, session_id: str, agent_id: str = "") -> str:
    """The matched text of an encoded retry, else ''. The refusal state is read only once the shape matches."""
    matched = encoded_form_hit(raw, stripped)
    if matched and recent_refusal(session_id, agent_id):
        return matched
    return ""

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
