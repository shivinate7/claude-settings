"""The owner override pass (decision owner-override-pass): the one home of granting, spending and
reading it.

The owner starts a prompt with the word `override`. hooks/local_time.py, the prompt hook, calls grant().
refuse() in hooks/guard_core.py calls take() before it prints a deny or an ask, unless the veto that
judge() in hooks/guard.py registers finds an act no pass lifts (decision owner-override-pass).

A pass is the file <config dir>/state/override/<session_id>.json, {"kind": "once"|"timed",
"until": ISO-8601 UTC}. It covers only the session that typed it. state/ is frozen against Claude's
writes, so a session cannot grant itself a pass. It is valid only while now < until.
  once   `override`, or `override <reason>`: the next refused act, or 10 minutes. A subagent's call
         never spends it. The reason, on one line, goes to guard.log.
  timed  `override 15m`, `override 2h`, `override 15` (minutes): every refused act until the end.
         It reaches subagents. The owner picks the length, so there is no cap.
  `override off` ends any pass at once. `override`, `override <n>[m|h]` and `override off` mean
  that only as the whole prompt: a word after the length or after `off` is ambiguous, so it grants
  nothing (an intended "off" must never become a grant). A later line starting with the word grants
  nothing.
A file that is missing, unreadable or corrupt is no pass. take() never raises into the guard: an
error means no pass, so the refusal stands.

A one-act pass is spent by creating its claim marker, <pass file>.<digest>.claim, with O_EXCL: of
calls racing for one pass, exactly one creates it. A rename is no claim on Windows, where it acts on
an open handle: two racers that opened the file both rename it, and both win (CI, run 40296652083).
The digest names the pass's own bytes, and each grant writes a new id, so a marker spends only the
pass it was made for. The spent pass file stays until a grant replaces it: a delete would make it
unreadable to a Windows racer mid-delete (CI, run 40303298492). grant() deletes markers older
than CLAIM_KEEP.
"""
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

ONCE_WINDOW = timedelta(minutes=10)  # how long a one-act pass waits for its act
CLAIM_KEEP = 2 * ONCE_WINDOW.total_seconds()  # seconds; past it, a marker's pass has ended
PROMPT = re.compile(r"\s*override(?=[\s:]|$)\s*:?\s*(.*)", re.I | re.S)  # the first word, then the rest
WORD = re.compile(r"(?:(off)|(\d+)([mh])?)", re.I)  # `off` or a length, as the whole rest
LOG_REASON_MAX = 300
SESSION_ID = re.compile(r"[\w.-]{1,128}")  # the id names a file: no separator, no leading dot
PASSED = "override"  # the log decision of a lifted act
UNREAD = "override-unread"  # the log decision when a pass file cannot be read


def now():
    """The clock of the prompt hook (LOCAL_TIME_NOW in tests), so grant and take agree."""
    import local_time
    return local_time.clock()


def _path(session_id):
    if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id) or session_id[0] == ".":
        return None
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "state", "override", session_id + ".json")


def grant(session_id, prompt, at):
    """Write, replace or remove the session's pass for one owner prompt. Returns (kind, until) for a
    new pass, ("off", None) when `override off` removed one, else None: the prompt is not the word."""
    said = PROMPT.match(prompt) if isinstance(prompt, str) else None
    path = _path(session_id)
    if not said or path is None:
        return None
    reason = " ".join(said.group(1).split())  # one log line: newlines and tabs fold to spaces
    word = WORD.fullmatch(reason)
    if not word and WORD.fullmatch(reason.split(" ")[0]):
        return None  # a word after `off` or a length: ambiguous, grants nothing
    off, number, unit = word.groups() if word else (None, None, None)
    if off:
        try:
            os.remove(path)
        except FileNotFoundError:
            return None
        return "off", None
    if number is None:
        kind, until = "once", at + ONCE_WINDOW
    else:
        kind = "timed"
        until = at + (timedelta(hours=int(number)) if unit and unit.lower() == "h"
                      else timedelta(minutes=int(number)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _sweep_claims(os.path.dirname(path))
    scratch = "%s.%s.tmp" % (path, uuid.uuid4().hex)  # a new file always replaces the old, unread
    with open(scratch, "w", encoding="utf-8") as handle:
        json.dump({"kind": kind, "until": until.astimezone(timezone.utc).isoformat(),
                   "id": uuid.uuid4().hex}, handle)  # the id gives each pass its own claim marker
    os.replace(scratch, path)
    if reason and kind == "once":
        _log_reason(session_id, reason, at)
    return kind, until


def _sweep_claims(folder):
    """Delete claim markers older than CLAIM_KEEP. A newer one may still stop a racer that read its
    pass before the pass was spent."""
    import time
    try:
        names = os.listdir(folder)
    except OSError:
        return
    for name in names:
        if name.endswith(".claim"):
            marker = os.path.join(folder, name)
            try:
                if time.time() - os.path.getmtime(marker) > CLAIM_KEEP:
                    os.remove(marker)
            except OSError:
                pass


def _claim(path, raw):
    """True for the one call that creates this pass's claim marker, else False."""
    marker = "%s.%s.claim" % (path, hashlib.sha256(raw).hexdigest()[:32])
    try:
        os.close(os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except OSError:
        return False  # another call claimed it first, or the marker cannot be made: no pass
    return True


def _log_reason(session_id, reason, at):
    """Write the owner's reason as one guard.log line through the guard's own locked writer. A lone
    surrogate cannot be encoded, so it becomes `?` before the write rather than losing the line."""
    import guard_core  # lazy: only a grant that has a reason needs it
    guard_core.set_log_session(session_id)
    guard_core.record("UserPromptSubmit", "override-reason", "owner-override-pass",
                      reason[:LOG_REASON_MAX].encode("utf-8", "replace").decode("utf-8"))


def take(session_id, agent_id, at):
    """PASSED when the pass lifts this refusal (a one-act pass is spent), UNREAD when the file exists
    but cannot be read, else None. Of calls racing for one one-act pass, only the one that creates
    its claim marker wins."""
    path = _path(session_id)
    if path is None:
        return None
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        data = json.loads(raw.decode("utf-8"))
        kind = data["kind"]
        until = datetime.fromisoformat(data["until"])
        if kind not in ("once", "timed") or until.tzinfo is None:
            return UNREAD
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return UNREAD
    if at >= until or (kind == "once" and agent_id):
        return None
    if kind == "timed":
        return PASSED
    if not _claim(path, raw):
        return None
    return PASSED
