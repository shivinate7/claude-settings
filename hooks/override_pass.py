"""The owner override pass (decision owner-override-pass): the one home of granting, spending and
reading it.

The owner types `override` as a whole prompt. hooks/local_time.py, the prompt hook, calls grant().
refuse() in hooks/guard_core.py calls take() before it prints a deny or an ask.

A pass is the file <config dir>/state/override/<session_id>.json, {"kind": "once"|"timed",
"until": ISO-8601 UTC}. It covers only the session that typed it. state/ is frozen against Claude's
writes, so a session cannot grant itself a pass. It is valid only while now < until.
  once   `override`: the next refused act, or 10 minutes. A subagent's call never spends it.
  timed  `override 15m`, `override 2h`, `override 15` (minutes): every refused act until the end.
         It reaches subagents. The owner picks the length, so there is no cap.
  `override off` ends any pass at once.
A file that is missing, unreadable or corrupt is no pass. take() never raises into the guard: an
error means no pass, so the refusal stands.
"""
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

ONCE_WINDOW = timedelta(minutes=10)  # how long a one-act pass waits for its act
PROMPT = re.compile(r"override(?:\s+(?:(off)|(\d+)([mh])?))?", re.I)  # the whole stripped prompt
SESSION_ID = re.compile(r"[\w.-]{1,128}")  # the id names a file: no separator, no leading dot
# Rules no pass lifts (owner rulings 2026-10-18): the guard files and the pass file, and a git
# location variable. A kill of pid 0, 1 or -1 shares its rule with other kills, so refuse() marks it.
NEVER = frozenset({"frozen-path", "git-env-set"})
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
    said = PROMPT.fullmatch(prompt.strip()) if isinstance(prompt, str) else None
    path = _path(session_id)
    if not said or path is None:
        return None
    off, number, unit = said.groups()
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
    scratch = "%s.%s.tmp" % (path, uuid.uuid4().hex)  # a new file always replaces the old, unread
    with open(scratch, "w", encoding="utf-8") as handle:
        json.dump({"kind": kind, "until": until.astimezone(timezone.utc).isoformat()}, handle)
    os.replace(scratch, path)
    return kind, until


def take(session_id, agent_id, rule, at):
    """PASSED when the pass lifts this refusal (a one-act pass is spent), UNREAD when the file exists
    but cannot be read, else None. A one-act pass is spent by a rename to a unique name, so of two
    calls racing for it only one wins."""
    path = _path(session_id)
    if path is None or rule in NEVER:
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
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
    spent = "%s.%s.used" % (path, uuid.uuid4().hex)
    try:
        os.rename(path, spent)
    except OSError:
        return None  # another call spent it first
    try:
        os.remove(spent)
    except OSError:
        pass
    return PASSED
