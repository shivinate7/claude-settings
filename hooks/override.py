"""The owner override (decision owner-override): the one home of granting, spending and
reading it.

The owner starts a prompt with the word `override`. hooks/local_time.py, the prompt hook, calls grant().
refuse() in hooks/guard_core.py calls take() before it prints a deny or an ask, unless the veto that
judge() in hooks/guard.py registers finds an act no override lifts (decision owner-override).

An override is the file <config dir>/state/override/<session_id>.json, {"kind": "once"|"timed",
"until": ISO-8601 UTC}. It covers only the session that typed it. state/ is frozen against Claude's
writes, so a session cannot grant itself an override. It is valid only while now < until.
  once   `override`, or `override <reason>`: the next refused act, or 10 minutes. An agent's call
         never spends it. The reason, on one line, goes to guard.log.
  timed  `override 15m`, `override 2h`, `override 15` (minutes): every refused act until the end.
         It reaches agents. The owner picks the length, so there is no cap.
  `override off` ends any override at once. `override`, `override <n>[m|h]` and `override off` mean
  that only as the whole prompt: a word after the length or after `off` is ambiguous, so it grants
  nothing (an intended "off" must never become a grant). A later line starting with the word grants
  nothing.
An Opus override is the file <config dir>/state/override/opus/<session_id>.json, {"kind": "opus",
"until": ISO-8601 UTC, "role": null or one role}. It lives beside the override, so the two never
replace each other. It lifts only the Opus spawn refusal of guard rule agent-model-cap, never that
rule's settings-write ask, and it reaches agents.
  `opus 2h`, `opus 15m`: every Opus spawn until the end. The unit is required: `opus 4` may name a
         model. `opus builders 2h` (or `builder`): only spawns of that role, from OPUS_ROLES.
  `opus off` ends it. The same whole-prompt rule holds: any other text after `opus` grants nothing.
  A plain ask (`send opus judges`, `use opus reviewers for 30m`) writes the same file when a model judges the
  prompt to be the owner's own present request (grant_opus_ask, call_judge.opus_ask). Cost: one model call for an
  owner prompt that carries the whole word `opus` and starts with neither keyword; none for any other prompt, and
  none for a machine-tag prompt. It fails closed: an error or an odd answer grants nothing.
A step grant also lifts that ask, and nothing else: the owner's grant that triage writes on the lane's
roadmap step (decision agent-model-cap). take() reads it only on an Opus spawn refusal that no Opus override
lifted, from the local ref origin/roadmap in the call's cwd, never fetched: one git grep for the lane id,
one git show per hit. The lane id is session_<x> for env CLAUDE_CODE_REMOTE_SESSION_ID=cse_<x>, else the
payload's session id. Exactly one step must bind the lane, with status not done and a grant whose role
is null or the spawn's role. A record that names the lane and cannot be read logs STEP_UNREAD.
A file that is missing, unreadable or corrupt is no override. take() never raises into the guard: an
error means no override, so the refusal stands.

A one-act override is spent by creating its claim marker, <override file>.<digest>.claim, with O_EXCL: of
calls racing for one override, exactly one creates it. A rename is no claim on Windows, where it acts on
an open handle: two racers that opened the file both rename it, and both win (CI, run 40296652083).
The digest names the override's own bytes, and each grant writes a new id, so a marker spends only the
override it was made for. The spent override file stays until a grant replaces it: a delete would make it
unreadable to a Windows racer mid-delete (CI, run 40303298492). grant() deletes markers older
than CLAIM_KEEP.
"""
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

from shared_names import MACHINE_TAGS  # stdlib only: the one home of the machine-text tags

ONCE_WINDOW = timedelta(minutes=10)  # how long a one-act override waits for its act
CLAIM_KEEP = 2 * ONCE_WINDOW.total_seconds()  # seconds; past it, a marker's override has ended
# The first word, then one mark (`,` `.` `!` `;` or a dash) that is dropped, then the rest. A mark counts
# only with whitespace or the end after it, so `override.py` and `override-15m` grant nothing. A bare
# `:` counts as on main (`override:reason`).
PROMPT = re.compile(
    r"\s*override(?:(?=\s|$)\s*(?::|[,.!;\-\u2013\u2014](?=\s|$))?|:|[,.!;\-\u2013\u2014](?=\s|$))\s*(.*)",
    re.I | re.S)
WORD = re.compile(r"(?:(off)|(\d+)([mh])?)", re.I)  # `off` or a length, as the whole rest
OPUS_PROMPT = re.compile(r"\s*opus(?=\s|$)(.*)", re.I | re.S)  # the Opus word, then the rest
OPUS_LENGTH = re.compile(r"(\d+)([mh])", re.I)  # an Opus override needs its unit
# The plain ask (grant_opus_ask): the whole word, a pasted block, a word that may name a role, a length anywhere in the
# words (bounded by non-word characters, so `12 mhz` is none), and the length when the words give none.
OPUS_WORD = re.compile(r"\bopus\b", re.I)
PASTED = re.compile(r"<pasted_content\b[^>]*>.*?</pasted_content>", re.I | re.S)
ROLE_WORDS = re.compile(r"[A-Za-z][\w-]*")
ASK_LENGTH = re.compile(r"(?<![\w-])" + OPUS_LENGTH.pattern + r"(?![\w-])", re.I)
DEFAULT_ASK_LENGTH = ("2", "h")
OPUS_RULE = "agent-model-cap"  # the one rule an Opus override lifts, and only its spawn refusal
# The roles an Opus spawn can ask for: the agents/ roles and the built-in ones, less Plan, which runs Opus by standing
# grant (OPUS_STANDING_ROLES in hooks/guard.py). Explore is not in it either: an Explore on Opus with no Audit: marker is
# refused, and `opus 2h` or `override` lifts it. No scoped `opus explore` form exists (decision agent-model-cap).
OPUS_ROLES = ("builder", "reviewer", "test-author", "record-writer", "claude-code-guide",
              "general-purpose", "claude")
LOG_REASON_MAX = 300
SESSION_ID = re.compile(r"[\w.-]{1,128}")  # the id names a file: no separator, no leading dot
LIFTED = "override"  # the log decision of a lifted act
UNREAD = "override-unread"  # the log decision when an override file cannot be read
OPUS_LIFTED = "opus-override"  # the log decision of an Opus spawn an Opus override lifted
OPUS_UNREAD = "opus-unread"  # the log decision when an Opus override file cannot be read
STEP_LIFTED = "step-grant"  # the log decision of an Opus spawn a grant on the lane's roadmap step lifted
STEP_UNREAD = "step-grant-unread"  # the log decision when a step record that names the lane cannot be read
LIFTS = (LIFTED, OPUS_LIFTED, STEP_LIFTED)  # the take() results that let the act through
STEP_REF = "refs/remotes/origin/roadmap"  # the record branch as the lane last fetched it; never fetched here
STEP_DIR = "roadmap/data/steps/"
LANE_ENV, LANE_ENV_PREFIX, LANE_PREFIX = "CLAUDE_CODE_REMOTE_SESSION_ID", "cse_", "session_"
_step_read = None  # the step id the last take() read for its step decision, for the log line
# What a refusal prints so the owner can copy the word that lifts it (step c80). The line names the
# typed word and never the refused target. A model or an agent only offers the line; text from an
# agent grants nothing, because the grant file lives in frozen state.
NO_OVERRIDE = "No override lifts this refusal."


def offer(rule, spawn_role=None, agent_id=None):
    """The line an owner types to lift a refusal of this rule, for the call that was refused."""
    if rule == OPUS_RULE and spawn_role is not None:
        role = opus_role(str(spawn_role))
        by_role = " or `opus %ss 2h` for this role" % role if role else ""
        return "To allow this Opus spawn, type `opus 2h` for every Opus spawn%s, or `override` for this one act." % by_role
    if agent_id:
        return ("To allow this act, type `override 15m`. A one-act `override` does not reach an agent's call.")
    return ("To allow this act, type `override` for this one act, or `override 15m` for every refused act "
            "for 15 minutes.")


def now():
    """The clock of the prompt hook (LOCAL_TIME_NOW in tests), so grant and take agree."""
    import local_time
    return local_time.clock()


def _path(session_id, *folder):
    """The session's override file, or with folder "opus" its Opus override file. None when the id
    cannot name a file."""
    if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id) or session_id[0] == ".":
        return None
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "state", "override", *folder, session_id + ".json")


def _write(path, data):
    """Write an override file whole: a new file always replaces the old, unread."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    scratch = "%s.%s.tmp" % (path, uuid.uuid4().hex)
    with open(scratch, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    os.replace(scratch, path)


def opus_role(word):
    """The role a word names, singular or plural, from OPUS_ROLES, else None."""
    word = word.lower()
    for role in OPUS_ROLES:
        if word in (role, role + "s"):
            return role
    return None


def _grant_opus(session_id, rest, at):
    """`opus <n>[m|h]`, `opus <role> <n>[m|h]` or `opus off` as the whole prompt. Returns ("opus",
    until, role) for a new override, ("opus-off", None) when one was removed, else None."""
    path = _path(session_id, "opus")
    words = rest.split()
    if path is None or not words or (rest[:1] and not rest[:1].isspace()):
        return None
    if [w.lower() for w in words] == ["off"]:
        try:
            os.remove(path)
        except FileNotFoundError:
            return None
        _log(session_id, "opus-off", "")
        return "opus-off", None
    role = opus_role(words[0]) if len(words) == 2 else None
    length = OPUS_LENGTH.fullmatch(words[-1])
    if not length or len(words) > 2 or (len(words) == 2 and role is None):
        return None  # ambiguous: grants nothing
    return _write_opus(session_id, path, at, length.groups(), role)


def _write_opus(session_id, path, at, length, role, said=None):
    """Write the Opus override file for `length` = (number, unit) from `at` and log it: the one home of the file's
    shape, for the keyword grant and the plain ask. `said` is the owner's words, for the log. Returns ("opus", until,
    role)."""
    number, unit = length
    until = at + (timedelta(hours=int(number)) if unit.lower() == "h" else timedelta(minutes=int(number)))
    stamp = until.astimezone(timezone.utc).isoformat()
    _write(path, {"kind": "opus", "until": stamp, "role": role})
    detail = "%s until %s" % (role or "every role", stamp)
    if said:
        detail += ": " + said[:LOG_REASON_MAX].encode("utf-8", "replace").decode("utf-8")
    _log(session_id, "opus-grant", detail)
    return "opus", until, role


def _strip_pasted(prompt):
    """The prompt with each pasted block replaced by a marker: pasted text is not the owner's own words."""
    return PASTED.sub("[pasted text]", prompt)


def grant_opus_ask(session_id, prompt, at, judge=None):
    """The owner's plain Opus ask (`send opus judges`): an Opus override written when the model says the prompt is the
    owner's own present request to run Opus agents (decision owner-override). `judge` is call_judge.opus_ask unless a
    caller passes another. Returns ("opus", until, role) for a new override, else None.

    The judge is not called, and nothing is granted, when: the prompt is no string; the session id cannot name a
    file; the prompt starts with a machine tag (an agent's text, a notice); its first word is `opus` or `override`
    (the keyword forms keep the whole-prompt rule of grant()); or no whole word `opus` stays once the pasted blocks
    are removed. Cost: one model call for an owner prompt that carries the word, none for any other.
    The role is the one OPUS_ROLES role the words name (none or several: every role). The length is the first
    `<n>m` or `<n>h` in the words, else DEFAULT_ASK_LENGTH. The guard.log line `opus-grant` holds the owner's words."""
    if not isinstance(prompt, str):
        return None
    path = _path(session_id, "opus")
    if path is None or prompt.lstrip().startswith(MACHINE_TAGS):
        return None
    if OPUS_PROMPT.match(prompt) or PROMPT.match(prompt):
        return None
    text = _strip_pasted(prompt)
    if not OPUS_WORD.search(text):
        return None
    if judge is None:
        from call_judge import opus_ask as judge
    if judge(text) is not True:
        return None
    roles = {opus_role(word) for word in ROLE_WORDS.findall(text)} - {None}
    found = ASK_LENGTH.search(text)
    return _write_opus(session_id, path, at, found.groups() if found else DEFAULT_ASK_LENGTH,
                       roles.pop() if len(roles) == 1 else None, " ".join(text.split()))


def grant(session_id, prompt, at):
    """Write, replace or remove the session's override for one owner prompt. Returns (kind, until) for a
    new override, ("off", None) when `override off` removed one, the _grant_opus result for the Opus word,
    else None: the prompt is not a word."""
    opus = OPUS_PROMPT.match(prompt) if isinstance(prompt, str) else None
    if opus:
        return _grant_opus(session_id, opus.group(1), at)
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
    _write(path, {"kind": kind, "until": until.astimezone(timezone.utc).isoformat(),
                  "id": uuid.uuid4().hex})  # the id gives each override its own claim marker
    if reason and kind == "once":
        _log_reason(session_id, reason, at)
    return kind, until


def _sweep_claims(folder):
    """Delete claim markers older than CLAIM_KEEP. A newer one may still stop a racer that read its
    override before the override was spent."""
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
    """True for the one call that creates this override's claim marker, else False."""
    marker = "%s.%s.claim" % (path, hashlib.sha256(raw).hexdigest()[:32])
    try:
        os.close(os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except OSError:
        return False  # another call claimed it first, or the marker cannot be made: no override
    return True


def _log_reason(session_id, reason, at):
    """Write the owner's reason as one guard.log line through the guard's own locked writer. A lone
    surrogate cannot be encoded, so it becomes `?` before the write rather than losing the line."""
    _log(session_id, "override-reason", reason[:LOG_REASON_MAX].encode("utf-8", "replace").decode("utf-8"),
         "owner-override")


def _log(session_id, decision, detail, rule=OPUS_RULE):
    import guard_core  # lazy: only a grant that logs needs it
    guard_core.set_log_session(session_id)
    guard_core.record("UserPromptSubmit", decision, rule, detail)


def _take_opus(session_id, spawn_role, at):
    """OPUS_LIFTED when the session's Opus override covers a spawn of spawn_role now, OPUS_UNREAD when the
    file exists but cannot be read, else None."""
    path = _path(session_id, "opus")
    if path is None:
        return None
    try:
        with open(path, "rb") as handle:
            data = json.loads(handle.read().decode("utf-8"))
        until, role = datetime.fromisoformat(data["until"]), data["role"]
        if data["kind"] != "opus" or until.tzinfo is None or (role is not None and opus_role(role) != role):
            return OPUS_UNREAD
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return OPUS_UNREAD
    if at >= until or (role is not None and role != str(spawn_role).lower()):
        return None
    return OPUS_LIFTED


def remote_session_id():
    """The session record id (session_<x>) the env names as cse_<x>, or None when the env is unset or of another shape."""
    remote = os.environ.get(LANE_ENV) or ""
    rest = remote[len(LANE_ENV_PREFIX):] if remote.startswith(LANE_ENV_PREFIX) else ""
    return LANE_PREFIX + rest if rest else None


def _lane_id(session_id):
    """The lane's id as a step's `lane` field names it, or None. A set env value of another shape is no id."""
    if os.environ.get(LANE_ENV):
        lane = remote_session_id()
    else:
        lane = session_id
    if not isinstance(lane, str) or not SESSION_ID.fullmatch(lane) or lane[0] == ".":
        return None
    return lane


def _grant_role(grant):
    """The role a well-formed grant covers: None for every role, else one role from OPUS_ROLES. Raises
    ValueError for a grant of the wrong shape or an unknown role."""
    if (not isinstance(grant, dict) or "role" not in grant or grant.get("by") != "triage"
            or not isinstance(grant.get("words"), str) or not grant["words"].strip()):
        raise ValueError("grant shape")
    if datetime.fromisoformat(grant["at"]).tzinfo is None:
        raise ValueError("grant time has no offset")
    role = grant["role"]
    if role is not None and (not isinstance(role, str) or opus_role(role) != role):
        raise ValueError("unknown role")
    return role


def _take_step(session_id, spawn_role, cwd):
    """STEP_LIFTED when the one step bound to this lane grants an Opus spawn of spawn_role, STEP_UNREAD
    when a record that names the lane cannot be read or has the wrong shape, else None. Sets _step_read
    to the step the decision names."""
    global _step_read
    _step_read = None
    lane = _lane_id(session_id)
    if lane is None or not isinstance(cwd, str) or not cwd:
        return None
    import git_reads  # lazy: only an Opus spawn refusal that no Opus override lifted needs it
    hits = git_reads._git(cwd, "grep", "-l", "-F", "-e", lane, STEP_REF, "--", STEP_DIR)
    if hits is None or hits.returncode != 0:
        return None  # no ref, no repository, no hit or a git error: no lift
    bound = []
    for name in hits.stdout.splitlines():
        if not name.strip():
            continue
        _step_read = name.rsplit("/", 1)[-1]
        shown = git_reads._git(cwd, "show", name)
        try:
            if shown is None or shown.returncode != 0:
                raise ValueError("unread")
            step = json.loads(shown.stdout)
            if not isinstance(step, dict):
                raise ValueError("not a record")
            if step.get("lane") != lane:
                continue  # the id appears in another field or as part of a longer id
            grants = step.get("grants", [])
            if not isinstance(grants, list) or not isinstance(step.get("status"), str):
                raise ValueError("record shape")
            roles = [_grant_role(grant) for grant in grants]
        except (ValueError, KeyError, TypeError, AttributeError):
            return STEP_UNREAD
        bound.append((str(step.get("id") or _step_read), step["status"], roles))
    _step_read = None
    if len(bound) != 1:
        return None  # no step or two steps bind the lane: no lift
    step_id, status, roles = bound[0]
    role = str(spawn_role).lower()
    if status == "done" or not any(r is None or r == role for r in roles):
        return None
    _step_read = step_id
    return STEP_LIFTED


def step_read():
    """The step the last take() named for a step decision, or None."""
    return _step_read


def take(session_id, agent_id, at, rule=None, spawn_role=None, cwd=None):
    """LIFTED when the override lifts this refusal (a one-act override is spent), UNREAD when its file
    exists but cannot be read, else None. Of calls racing for one one-act override, only the one that
    creates its claim marker wins. For the Opus spawn refusal (rule OPUS_RULE with a spawn_role) the Opus
    override is read first, then the step grant (STEP_LIFTED or STEP_UNREAD), so a lift either one covers
    spends no one-act override. `cwd` is the call's directory, where the step grant is read."""
    opus = _take_opus(session_id, spawn_role, at) if rule == OPUS_RULE and spawn_role is not None else None
    if opus == OPUS_LIFTED:
        return opus
    step = None
    if rule == OPUS_RULE and spawn_role is not None:
        try:  # an error in the step read is no lift, and it never stops the override read below
            step = _take_step(session_id, spawn_role, cwd)
        except Exception:
            step = None
        if step == STEP_LIFTED:
            return step
    return _take_override(session_id, agent_id, at) or opus or step


def _take_override(session_id, agent_id, at):
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
        return LIFTED
    if not _claim(path, raw):
        return None
    return LIFTED
