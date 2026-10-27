#!/usr/bin/env python3
"""The PostToolUse and Stop watch on the agent model cap.

Modes:
- PostToolUse: After a write or shell call, checks the agent model cap in each watched
  settings file. Reverts a cap change that the guard did not ask about, or a raise past its
  expiry time.
- Stop: At the end of the turn, checks the agent model cap in each watched settings file.
  Reverts a cap change that no tool call explains, or a raise past its expiry time.

Claude Code runs this file after every tool call that matches, and again when the turn ends:

  stdin  : one JSON object with tool_name, tool_input, cwd and session_id
  stdout : one JSON object with a systemMessage, or nothing
  exit   : always 0

It reads a content hash of the file, never the shell text (decision `predicate-is-the-act`).

WHAT THIS FILE DOES. It watches the FILE, not the command. After each matching tool call it
hashes the project settings files and compares each hash against a stored baseline. `cp`, `sed -i`,
a script file and a path held in a shell variable are all equally visible to a hash. On a cap
change that the guard did not ask about, this file puts the previous content back and prints a
systemMessage naming the file, the tool and the command.

THE SHELL ROUTE HAS TWO LAYERS. The guard asks about
the shell shapes that name the value, and this file reverts every shell cap change it did not
explain, in every shape. This file sees only the watched paths of the current directory, so the
guard's ask is the layer for a shell write from a subdirectory or another worktree. The guard's
ask is the first layer and this revert is the second.

THIS IS REVERT AND REPORT, NOT PREVENTION. The write lands and is then undone. That is acceptable
here and nowhere wider: the cap takes effect when an agent is next spawned, and the restore
happens before the next tool call can spawn one.

DECISION 7 STILL HOLDS. A project's own `.claude` files are allowed and reported, never denied. So
an ordinary project config edit is re-baselined in silence. Only a change to a CAP VARIABLE is
reverted, and only when the guard did not ask about it.

THE EXPIRY. An approved lift is revoked at its deadline (decision `opus-grant-expires`, an Opus grant expires within 24 hours).

The fix reads a second field the override file carries OUTSIDE its `env` block:
`_agentCapUntil`, an ISO-8601 instant. It sits outside `env` for two reasons. A key inside
`env` is exported into every agent's shell, which an expiry timestamp has no business being.
And a key inside `env` is read by `guard.AGENT_CAP_KEY`, which would turn a plain expiry write
into a second cap-change ask the field is not one. The guard's PreToolUse ask never sees this field,
and only this watch reads it. See decision `opus-grant-expires` (an Opus grant expires within 24 hours).

An override whose current reading sets the model above Sonnet is now judged on every sweep, not
only on the sweep that changed it, because a deadline passes with no write of its own: the file
never changes again and only the clock moves. The deadline is bad when `_agentCapUntil` is
missing, unparseable, already passed, or more than 24 hours ahead of now. A field written
INSIDE `env` by mistake reads as its own problem, not as "missing": the owner can see the
field, so the message says where it belongs instead of pretending it is absent. A bad
deadline is revoked the same way an unasked write is: the pre-lift content goes back, the
lifted content is kept beside the store, and a systemMessage names the file and what was
wrong with the expiry.

THE ONE HARD PART. `save_baseline` used to re-baseline an APPROVED cap change straight to the
lifted content, so the pre-lift bytes were gone by the time a deadline could be checked against
them. The baseline entry now carries a THIRD field, `prior`: the content last seen before the
lift began. It is computed once, when a lift first appears, and carried forward unchanged
through any later edit that keeps the reading lifted, so a chain of re-approvals still restores to
the one true pre-lift state. `load_baseline` treats a missing `prior` key, the shape every entry
written by the version on `main` carries, the same as an explicit `null`: no prior recorded. When
the expiry check finds no prior to restore to, it does not invent one and does not leave the
override running in silence. It reports UNKNOWN, the same as `judge_path` already does for a
first sight it cannot read.
"""

import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)



def _add_guard_set_dir() -> None:
    """Put the installed guard set, guard.d/<id>/, on the path after this folder.

    The id is the INSTALL_ID stamped in the guard.py beside this file, the same key guard.py
    loads its set by, so the watch finds the set's shared_names.py when no flat copy is there.
    A repo copy has no stamp and no set.
    """
    try:
        with open(os.path.join(HERE, "guard.py"), encoding="utf-8") as handle:
            found = re.search(r'^INSTALL_ID = "([^"]*)"', handle.read(), re.MULTILINE)
    except Exception:
        return
    if found:
        set_dir = os.path.join(HERE, "guard.d", found.group(1))
        if os.path.isdir(set_dir) and set_dir not in sys.path:
            sys.path.insert(sys.path.index(HERE) + 1, set_dir)


_add_guard_set_dir()

from shared_names import PROJECT_FROZEN_FILES, config_dir  # noqa: E402  stdlib only

# The guard is imported lazily, by `_load_guard`, so a call where nothing changed exits on the
# stdlib alone (see `unchanged`). GUARD_UNDER_TEST points the suite at another copy of the guard,
# the same contract `hooks/test_guard.py` holds, so a mutation test needs no second copy of this
# file.
guard = None


def _load_guard() -> None:
    """Import the guard once and bind it, with the names derived from it."""
    global guard
    if guard is not None:
        return
    path = os.environ.get("GUARD_UNDER_TEST")
    if path:
        import importlib.util
        spec = importlib.util.spec_from_file_location("guard_under_test", path)
        loaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)
    else:
        import guard as loaded
    guard = loaded


# ------------------------------------------------------------------ the watched set
#
# The project's own settings files, the pair `shared_names.PROJECT_FROZEN_FILES` names. The
# config directory is NOT watched here. Rule 7 denies a write there, and `~/.claude/settings.json`
# is a symlink onto the clone of claude-settings, which is deliberately unfrozen so that the
# repository can edit its own source. A hash watch that followed that symlink would revert the
# repository's own work.
# `shared_names` is stdlib only, so the fast exit reads the names before the guard loads.
WATCHED_NAMES = tuple(name.lstrip("/") for name in PROJECT_FROZEN_FILES)

STORE_DIR_NAME = "state"
STORE_SUB = "config-watch"

REVERT_MESSAGE = (
    "Guard (agent-model-cap): an unasked write changed the agent model cap in {where}. "
    "Tool: {tool}. Command: {what}. Reading: {change}. "
    "The previous content is back in place and the rejected content is kept at {kept}. "
    "The PreToolUse guard could not read this write, so it asked nobody. "
    "To lift the cap, write the file with a tool that names the value, and approve the ask."
)

UNKNOWN_MESSAGE = (
    "Guard (agent-model-cap): {where} sets the agent model cap and this session holds no "
    "baseline for it, so the guard cannot tell a lift from the file's own starting state. "
    "Reading: {change}. Nothing was changed. Check the file by hand."
)

EXPIRE_MESSAGE = (
    "Guard (agent-model-cap): the agent model cap override in {where} expired. "
    "_agentCapUntil is {problem}. "
    "The pre-override content is back in place and the lifted content is kept at {kept}. "
    "To lift the cap again, set _agentCapUntil to an ISO-8601 time no more than 24 hours "
    "ahead, and approve the write."
)

EXPIRE_UNKNOWN_MESSAGE = (
    "Guard (agent-model-cap): {where} sets the agent model cap above Sonnet and "
    "_agentCapUntil is {problem}, but this session holds no pre-override content to restore. "
    "Reading: {change}. Nothing was changed. Check the file by hand."
)

# What a printed message may carry. The bounds are the guard's own, so a crafted path, value or
# command cannot fill the message or print a line that reads like an approval.
MAX_COMMAND = 200


def safe(text: str, limit: int) -> str:
    """Return text fit to print: control characters cleaned, length bounded, a cut MARKED."""
    return guard.cap_safe(guard.re.sub(r"\s+", " ", text or ""), limit)


# ------------------------------------------------------------------ the baseline store
#
# WHERE THE BASELINE LIVES, AND WHY.
#
# The store sits under `<config dir>/state/config-watch/`, and `state` is on the guard's
# CONFIG_FROZEN_DIRS list. So rule 7 DENIES a session write to the store in every shape PreToolUse
# can read, which is a wider set than rule 8 reads: rule 7 needs only the path, never the value, so
# `cp`, `mv`, `sed -i`, a redirect and `tee` onto the store are all refused.
#
# THE HONEST LIMIT. The two shapes that hide the path from PreToolUse, `python3 -c` and a script
# file, hide it for the store as well. Nothing a session can write to is beyond a session that
# writes without naming its target. So the store is not a vault. What it is instead is a place
# where tampering is visible: a missing or unreadable baseline is reported as UNKNOWN and never as
# clear. A file whose baseline was destroyed says so, and the reader checks it by hand.
#
# The store is NOT put beside the watched file, under the project's own `.claude`, because that is
# the folder the bypass already writes to.


def store_dir() -> str:
    return os.path.join(config_dir(), STORE_DIR_NAME, STORE_SUB)


def store_key(path: str) -> str:
    """The store file name for one watched path. A hash, so no path depth or character escapes."""
    return hashlib.sha256(path.encode("utf-8", "replace")).hexdigest() + ".json"


def digest(content) -> str:
    """The content hash of a watched file, or '' when the file is absent.

    An absent file has its own reading, distinct from an empty one, because a cap lift that CREATES
    `settings.local.json` must read as a change and its restore must remove the file again.
    """
    if content is None:
        return ""
    return hashlib.sha256(content).hexdigest()


def read_file(path: str):
    """Return the file's bytes, or None when it is absent or unreadable."""
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except Exception:
        return None


def load_baseline(path: str):
    """Return the stored baseline for one path, or None when there is none to read.

    An unreadable or malformed entry reads as None, the same as no entry. A baseline that cannot be
    trusted is not a baseline.

    The result carries a third field, `prior`: the content last seen before the current lift
    began, or None when no lift is in effect or none was ever recorded. An entry written by the
    version on `main` carries no `prior` key at all, and `entry.get("prior")` reads that the same
    as an explicit `null` -- no prior recorded, never a crash. A `prior` that fails to decode is
    dropped the same way, rather than invalidating the whole entry: `prior` is supplementary, and
    an unreadable one must never be trusted, only treated as absent.
    """
    try:
        with open(os.path.join(store_dir(), store_key(path)), "r", encoding="utf-8") as handle:
            entry = json.load(handle)
    except Exception:
        return None
    if not isinstance(entry, dict) or entry.get("path") != path:
        return None
    blob = entry.get("content")
    if blob is None:
        result = {"digest": "", "content": None}
    else:
        if not isinstance(blob, str):
            return None
        try:
            content = base64.b64decode(blob.encode("ascii"), validate=True)
        except Exception:
            return None
        if digest(content) != entry.get("digest"):
            return None
        result = {"digest": entry.get("digest"), "content": content}

    prior = None
    prior_blob = entry.get("prior")
    if isinstance(prior_blob, str):
        try:
            prior = base64.b64decode(prior_blob.encode("ascii"), validate=True)
        except Exception:
            prior = None
    result["prior"] = prior
    return result


def save_baseline(path: str, content, prior=None) -> None:
    """Record one path's content as the baseline, with its pre-lift `prior` beside it.

    A failure here never changes a decision.
    """
    try:
        os.makedirs(store_dir(), exist_ok=True)
        entry = {
            "path": path,
            "digest": digest(content),
            "content": None if content is None else base64.b64encode(content).decode("ascii"),
            "prior": None if prior is None else base64.b64encode(prior).decode("ascii"),
        }
        target = os.path.join(store_dir(), store_key(path))
        with open(target + ".tmp", "w", encoding="utf-8") as handle:
            json.dump(entry, handle)
        os.replace(target + ".tmp", target)
    except Exception:
        pass


def keep_rejected(path: str, content) -> str:
    """Put the rejected content beside the store and return where it went, or ''.

    NOTHING IS DESTROYED BY A REVERT. The write that this file undoes may hold work worth reading,
    and a revert that dropped it would be a second kind of loss. The kept copy is named in the
    message.
    """
    if content is None:
        return ""
    try:
        os.makedirs(store_dir(), exist_ok=True)
        target = os.path.join(store_dir(), store_key(path) + ".rejected")
        with open(target, "wb") as handle:
            handle.write(content)
        return target
    except Exception:
        return ""


def restore(path: str, content) -> bool:
    """Put the baseline content back. Remove the file when the baseline was an absent file."""
    try:
        if content is None:
            if os.path.exists(path):
                os.remove(path)
            return True
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(content)
        return True
    except Exception:
        return False


# ------------------------------------------------------------------ the cap reading
#
# The reading is the guard's own, so the watch and the ask agree on what a cap setting is. A change
# of the READING is what matters, never a change of the bytes: reformatting a settings file, adding
# a permission or renaming a key that is not the cap leaves the reading equal and passes in silence,
# which is what Decision 7 asks for.


def cap_reading(content):
    """Return {key: value} for the cap variables a file's content sets, or {} for none."""
    if content is None:
        return {}
    try:
        text = content.decode("utf-8", "replace")
    except Exception:
        return {}
    return guard._cap_reading(text)


def reading_text(reading) -> str:
    """Return one short printable line for a cap reading."""
    if not reading:
        return "(no cap setting)"
    parts = [key + " = " + (guard.cap_safe(value, guard.CAP_MAX_VALUE) or "(value unread)")
             for key, value in reading.items()]
    return guard.cap_safe(", ".join(parts), guard.CAP_MAX_CHANGE)


# ------------------------------------------------------------------ the expiry
#
# `_agentCapUntil` is a REPO-OWNED field, read from the parsed JSON document only, never from a
# text scan. That keeps it out of `env` (see the module docstring: an `env` key is exported into
# every agent's shell, and a key inside `env` is what `guard.AGENT_CAP_KEY` reads). It also
# keeps this watch the ONLY reader of it, so the PreToolUse ask never fires on this field alone.

_MODEL_KEYS = ("CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL")
EXPIRY_FIELD = "_agentCapUntil"
# The field's old name, read too until OLD_NAME_ENDS, so a deadline written before the rename still
# counts. Delete both lines and the old name's reader on that day.
OLD_EXPIRY_FIELD = "_subagentCapUntil"
OLD_NAME_ENDS = "2026-11-09"
EXPIRY_MAX_AHEAD_HOURS = 24


# A `_FORCE` key is an on/off flag (decision `agent-model-cap`), so these values set no model.
_FORCE_FLAGS = ("0", "1", "true", "false")


def first_sight_silent(reading) -> bool:
    """True when a first-sight reading may pass in silence: every cap key reads Sonnet, or a
    `_FORCE` key holds a plain flag. Any other value, a model name on a `_FORCE` key too, is
    reported unknown."""
    for key, value in reading.items():
        text = str(value or "").strip().lower()
        if text != "sonnet" and not (key.endswith("_FORCE") and text in _FORCE_FLAGS):
            return False
    return True


def cap_lift_value(reading) -> bool:
    """True when a cap reading sets the model above Sonnet, the state the expiry rule watches.

    A value this file's own reading cannot read (the bare-key match, printed as "(value
    unread)") counts as a lift too. The expiry rule would rather ask for a deadline that turns
    out unneeded than stay silent on a value it cannot confirm is Sonnet.
    """
    return any((reading.get(key) or "").strip().lower() != "sonnet"
               for key in _MODEL_KEYS if key in reading)


def next_prior(reading, was, baseline):
    """Return the pre-lift bytes to carry forward as the new `prior`, or None.

    None when the new reading is not a lift: nothing needs protecting. The last-seen baseline
    content when the lift is FRESH (the old reading was not a lift). The EXISTING prior, carried
    forward untouched, when the lift CONTINUES a lift already in effect, so a chain of
    re-approvals still restores to the one true pre-lift state, never to the most recent lifted
    content.
    """
    if not cap_lift_value(reading):
        return None
    if cap_lift_value(was):
        return baseline.get("prior")
    return baseline["content"]


EXPIRY_WRONG_PLACE = (
    "inside the env block, not at the top level -- env keys are exported into every "
    "agent's shell"
)


def cap_expiry_location(content):
    """Return (where, value) for `_agentCapUntil`, read from the PARSED document only.

    `where` is "top" when the field sits where it belongs, "env" when it sits inside the
    `env` block instead -- a mistake, not an absence, and the message must say so rather than
    read as "missing" -- or None when the field is nowhere in the file. Content that is not a
    JSON object reads the same as a file with no expiry at all: (None, None).
    """
    if content is None:
        return (None, None)
    try:
        parsed = json.loads(content.decode("utf-8", "replace"))
    except Exception:
        return (None, None)
    if not isinstance(parsed, dict):
        return (None, None)
    env = parsed.get("env")
    for field in (EXPIRY_FIELD, OLD_EXPIRY_FIELD):
        value = parsed.get(field)
        if isinstance(value, str):
            return ("top", value)
        value = env.get(field) if isinstance(env, dict) else None
        if isinstance(value, str):
            return ("env", value)
    return (None, None)


def expiry_problem(content, clock=None) -> str:
    """Return why `_agentCapUntil` fails, or '' when it names a valid, current deadline.

    `clock` lets a caller inject the instant this check reads as "now". It defaults to None,
    and a None reads the real clock, `datetime.now(timezone.utc)`, AT CALL TIME. Production
    never passes anything else, so production always reads the live clock, exactly as before
    this parameter existed. Only a test pins `clock` to a fixed instant, which is the only way
    a fixture can sit exactly on the 24-hour boundary: `datetime.now()` called once to build
    the fixture and once more, later, inside this function, are never the same instant, so no
    fixture could otherwise land ON the boundary rather than near it.
    """
    where, raw = cap_expiry_location(content)
    if where is None:
        return "missing"
    if where == "env":
        return EXPIRY_WRONG_PLACE
    text = raw.strip()
    if text[-1:] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    try:
        deadline = datetime.fromisoformat(text)
    except Exception:
        return "not a parseable ISO-8601 time"
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if clock is None:
        clock = datetime.now(timezone.utc)
    ahead = (deadline - clock).total_seconds()
    if ahead < 0:
        return "already passed"
    if ahead > EXPIRY_MAX_AHEAD_HOURS * 3600:
        return "more than 24 hours ahead"
    return ""


# ------------------------------------------------------------------ the explained test
#
# A write is EXPLAINED when the PreToolUse guard's rule 8 already asked about that exact path. The
# test here is rule 8's own condition, re-run against the same tool call, so the two cannot drift.
#
# NO TOKEN IS PASSED BETWEEN THE HOOKS, and the design brief's one-shot token is deliberately not
# built. A token has to survive a DENIED ask: PreToolUse asks, the owner says no, the tool never
# runs, PostToolUse never fires and the token is left behind for the next write to spend. Closing
# that needs a time to live, which is a window. Re-running the condition needs no window at all.
# PostToolUse fires only for a call that SUCCEEDED, and rule 8's answer is `ask`, so a successful
# call that rule 8 would ask about is a call the owner approved.
#
# THE LIMIT, STATED PLAINLY: an owner who puts a blanket `allow` for these writes in their own
# permissions never sees the ask, and this file then reads the write as explained. That is the
# owner's setting overriding the owner's guard, which is the owner's to do.


def explained_path(tool: str, tool_input, cwd: str) -> str:
    """Return the resolved path rule 8 asked about for this tool call, or ''.

    Stop time passes no tool call, so nothing is explained there and every outstanding cap change
    is judged on its own.
    """
    if not tool or not isinstance(tool_input, dict):
        return ""
    if tool in guard.WRITE_TOOLS:
        target = (tool_input.get("file_path", "")
                  or tool_input.get("path", "")
                  or tool_input.get("notebook_path", "")
                  or "")
        if not isinstance(target, str) or not target:
            return ""
        if not guard.is_settings_file(target, cwd):
            return ""
        if not guard.cap_change_parts(guard.write_content_parts(tool_input)):
            return ""
        return resolve(target, cwd)
    if tool in guard.SHELL_TOOLS:
        raw = tool_input.get("command", "") or ""
        if not isinstance(raw, str) or not raw.strip():
            return ""
        stripped = guard.strip_heredoc_bodies(raw)
        hit = guard._shell_write_hit(stripped, cwd, guard.is_settings_file)
        if not hit:
            return ""
        if not guard.cap_change(raw):
            return ""
        return resolve(hit, cwd)
    return ""


def resolve(path: str, cwd: str) -> str:
    """The guard's own path resolution, so the watch and the ask compare the same spellings."""
    try:
        return guard._resolved(path, cwd)
    except Exception:
        return ""


# ------------------------------------------------------------------ the sweep


def watched_paths(cwd: str):
    """Return the absolute watched paths for one working directory."""
    if not cwd or not isinstance(cwd, str):
        return []
    found = []
    for name in WATCHED_NAMES:
        path = os.path.join(cwd, *name.split("/"))
        if path not in found:
            found.append(path)
    return found


def command_text(tool: str, tool_input) -> str:
    """One short printing of what the tool call was, for the message."""
    if not isinstance(tool_input, dict):
        return "(none)"
    if tool in guard.SHELL_TOOLS:
        return safe(tool_input.get("command", "") or "(none)", MAX_COMMAND)
    target = (tool_input.get("file_path", "") or tool_input.get("path", "")
              or tool_input.get("notebook_path", "") or "")
    return safe(str(target) or "(none)", MAX_COMMAND) if target else "(none)"


def judge_path(path: str, tool: str, tool_input, cwd: str, explained: str, clock=None):
    """Judge one watched path. Return a message to print, or ''.

    Five answers, in order:

      no baseline  : record it. Report UNKNOWN when the file already sets the cap above Sonnet,
                     because a first sight cannot tell a lift from a starting state, and silence
                     there would read as clear. A cap at Sonnet is no lift, so it stays silent.
      unchanged    : fall through to the expiry check below, unchanged or not.
      cap unchanged: Decision 7. Re-baseline, carry `prior` forward, and say nothing yet.
      cap changed,
        explained  : re-baseline, carry `prior` forward, and say nothing yet.
      cap changed,
        unasked    : restore and report. The expiry rule never runs here: the write itself was
                     never authorized, so its deadline is beside the point.

    THE EXPIRY RULE runs last, on every path that did not just get reverted as an unasked write,
    changed this sweep or not. A deadline passes with no write of its own: the file that set it
    never changes again, and only the clock moves, so the check must run whether or not `now`
    differs from the baseline digest.
    """
    current = read_file(path)
    now = digest(current)
    baseline = load_baseline(path)

    if baseline is None:
        save_baseline(path, current)
        reading = cap_reading(current)
        if not first_sight_silent(reading):
            return UNKNOWN_MESSAGE.format(
                where=safe(path, guard.CAP_MAX_PATH), change=reading_text(reading))
        return ""

    if now != baseline["digest"]:
        was = cap_reading(baseline["content"])
        reading = cap_reading(current)

        if reading != was and not (explained and explained == resolve(path, cwd)):
            kept = keep_rejected(path, current)
            if not restore(path, baseline["content"]):
                return UNKNOWN_MESSAGE.format(
                    where=safe(path, guard.CAP_MAX_PATH), change=reading_text(reading))
            save_baseline(path, baseline["content"], baseline.get("prior"))
            guard.record(tool or "Stop", "reverted", "agent-model-cap",
                         guard.log_path_and_text(path, reading_text(reading)))
            return REVERT_MESSAGE.format(
                where=safe(path, guard.CAP_MAX_PATH),
                tool=safe(tool or "(turn end)", 40),
                what=command_text(tool, tool_input),
                change=reading_text(reading),
                kept=safe(kept or "(not kept)", guard.CAP_MAX_PATH))

        prior = next_prior(reading, was, baseline)
        save_baseline(path, current, prior)
        baseline = {"digest": now, "content": current, "prior": prior}

    reading = cap_reading(baseline["content"])
    if not cap_lift_value(reading):
        return ""
    problem = expiry_problem(baseline["content"], clock)
    if not problem:
        return ""

    if baseline.get("prior") is None:
        return EXPIRE_UNKNOWN_MESSAGE.format(
            where=safe(path, guard.CAP_MAX_PATH), problem=problem,
            change=reading_text(reading))

    kept = keep_rejected(path, baseline["content"])
    if not restore(path, baseline["prior"]):
        return EXPIRE_UNKNOWN_MESSAGE.format(
            where=safe(path, guard.CAP_MAX_PATH), problem=problem,
            change=reading_text(reading))
    save_baseline(path, baseline["prior"], None)
    guard.record(tool or "Stop", "reverted", "agent-model-cap",
                 guard.log_path_and_text(path, "expired: " + problem))
    return EXPIRE_MESSAGE.format(
        where=safe(path, guard.CAP_MAX_PATH), problem=problem,
        kept=safe(kept or "(not kept)", guard.CAP_MAX_PATH))


def lift_candidate(content) -> bool:
    """True when a file's cap might be lifted, or cannot be read with the stdlib alone.

    Any doubt reads as True, so the guard's own reading decides.
    """
    try:
        text = content.decode("utf-8")
        parsed = json.loads(text)
    except Exception:
        return True
    if not isinstance(parsed, dict):
        return True
    env = parsed.get("env")
    env = env if isinstance(env, dict) else {}
    named = re.findall(r"CLAUDE_CODE_(?:WORKFLOW_)?SUBAGENT_MODEL(?:_FORCE)?", text)
    if len(named) != sum(1 for key in env if key in named):
        return True  # a cap name outside the env block: the guard's text scan reads it
    return any(not isinstance(env.get(key), str) or env[key].strip().lower() != "sonnet"
               for key in _MODEL_KEYS if key in env)


def unchanged(payload, clock=None) -> bool:
    """True when this call needs no guard: every watched file matches its stored baseline.

    The hash is the only test of "unchanged", never mtime or size. A missing or unreadable
    record, or a recorded lift whose deadline is not valid now, reads as False, because an
    expiry is a clock event that no write marks.
    """
    cwd = payload.get("cwd", "") or os.getcwd() or ""
    if not isinstance(cwd, str):
        return False
    for path in watched_paths(cwd):
        baseline = load_baseline(path)
        if baseline is None or baseline["digest"] != digest(read_file(path)):
            return False
        content = baseline["content"]
        if content is not None and lift_candidate(content) and expiry_problem(content, clock):
            return False
    return True


def sweep(payload, clock=None):
    """Judge every watched path for this payload. Return the messages, in path order."""
    _load_guard()
    tool = payload.get("tool_name", "") or ""
    try:
        guard.set_log_session(payload.get("session_id"))  # the last column of a revert's log line
    except Exception:
        pass  # a guard without the setter still reverts: its line has no session cell (unknown session)
    tool_input = payload.get("tool_input", {}) or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    cwd = payload.get("cwd", "") or os.getcwd() or ""
    if not isinstance(cwd, str):
        cwd = ""
    explained = explained_path(tool, tool_input, cwd)
    messages = []
    for path in watched_paths(cwd):
        message = judge_path(path, tool, tool_input, cwd, explained, clock)
        if message:
            messages.append(message)
    return messages


# TEST_CLOCK_ENV lets `hooks/test_config_watch.py` pin the expiry rule's clock to a fixed
# instant, the only way a fixture can sit exactly on the 24-hour boundary (see
# `expiry_problem`'s own docstring). Production never sets this variable, so `main` always
# passes `clock=None` there, and `expiry_problem` always reads the live clock: the injection
# cannot drift from what runs, because it IS what runs, absent the variable.
TEST_CLOCK_ENV = "CONFIG_WATCH_TEST_CLOCK"


def _test_clock():
    """Return the instant `TEST_CLOCK_ENV` pins, or None when it is unset or unreadable."""
    raw = os.environ.get(TEST_CLOCK_ENV)
    if not raw:
        return None
    try:
        text = raw.strip()
        if text[-1:] in ("Z", "z"):
            text = text[:-1] + "+00:00"
        clock = datetime.fromisoformat(text)
    except Exception:
        return None
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    return clock


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # fail open on unreadable input
    if not isinstance(payload, dict):
        sys.exit(0)  # fail open on a payload that is not an object
    try:
        fast_exit = unchanged(payload, _test_clock())
    except Exception:
        fast_exit = False  # a fault in the fast check runs the full check, never a silent exit
    if fast_exit:
        sys.exit(0)
    try:
        _load_guard()
        guard._force_utf8_streams()
        messages = sweep(payload, _test_clock())
    except Exception:
        sys.exit(0)  # fail open on a watch defect
    if messages:
        print(json.dumps({"systemMessage": " ".join(messages)}))
    sys.exit(0)


# An importer, such as a test calling `sweep`, finds the guard bound at once. Only the hook run
# keeps it lazy.
if __name__ != "__main__":
    _load_guard()

if __name__ == "__main__":
    main()
