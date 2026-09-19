#!/usr/bin/env python3
"""The PostToolUse and Stop watch on the subagent model cap.

Claude Code runs this file after every tool call that matches, and again when the turn ends:

  stdin  : one JSON object with tool_name, tool_input, cwd and session_id
  stdout : one JSON object with a systemMessage, or nothing
  exit   : always 0

WHY THIS FILE EXISTS, MEASURED 2026-09-19 against hooks/guard.py on main.

The guard runs at PreToolUse. Rule 8 asks before a write that lifts the subagent model cap. The
rule needs TWO readings of one tool call: the PATH it writes, and the CAP VALUE it writes there.
A write that hides either reading walks past the rule. Fed a cap lift to
`<project>/.claude/settings.local.json` in every shape, the guard answered:

  Write tool                        ask
  `>` redirect                      ask
  heredoc                           ask
  `tee`                             ask
  `jq ... > file`                   ask
  `cp /tmp/x.json <path>`           ALLOWED
  `mv /tmp/x.json <path>`           ALLOWED
  `sed -i '' s/a/b/ <path>`         ALLOWED
  `python3 -c "open(<path>,'w')"`   ALLOWED
  `python3 gen.py`                  ALLOWED
  `bash gen.sh`                     ALLOWED

The first five name the value on the command line. The last six carry it in another file, in a
script, or in a substitution, so the value is unreadable and rule 8 stays silent. `cp` is a
one-word bypass of the cap recorded in `decisions/subagent-model-cap.md`.

WHAT THIS FILE DOES NOT DO. It does not read shell text. A longer list of write commands cannot
close this hole, because `bash gen.sh` and `python3 gen.py` name no path at all, and
`f=.claude/settings.local.json; cp x "$f"` names no path either. An allow-list over command words
closes the command-word axis and leaves the path-visibility axis open.

This is the rule `decisions/predicate-is-the-act.md` records: judge a guard by the ACT it must
catch, never by the spelling of the act, and when a gate needs a list of shapes the predicate is
wrong. `lint/md_sweep.py` reached that rule first and dropped its own shape list, which had grown
to fourteen entries and still missed `python3 gen.py`. The same two shapes are in the table above.

WHERE THIS FILE DIFFERS FROM THE SWEEP, AND WHY. `md_sweep.py` runs at Stop and reads FILE MTIME.
This file reads a CONTENT HASH. Three reasons. A hash tells a write that changed nothing from a
write that lifted the cap, so an ordinary `touch` or a rewrite of identical bytes stays silent. A
hash needs no turn boundary, so it works at PostToolUse where there is no "since the last human
message" to compare against. And a hash carries the PREVIOUS CONTENT with it, which is what a
restore needs and an mtime cannot give.

WHAT THIS FILE DOES INSTEAD. It watches the FILE, not the command. After each matching tool call it
hashes the project settings files and compares each hash against a stored baseline. `cp`, `sed -i`,
a script file and a path held in a shell variable are all equally visible to a hash. On a cap
change that the guard did not ask about, this file puts the previous content back and prints a
systemMessage naming the file, the tool and the command.

THIS IS REVERT AND REPORT, NOT PREVENTION. The write lands and is then undone. That is acceptable
here and nowhere wider: the cap takes effect when a subagent is next spawned, and the restore
happens before the next tool call can spawn one.

DECISION 7 STILL HOLDS. A project's own `.claude` files are allowed and reported, never denied. So
an ordinary project config edit is re-baselined in silence. Only a change to a CAP VARIABLE is
reverted, and only when the guard did not ask about it.
"""

import base64
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# GUARD_UNDER_TEST points the suite at another copy of the guard, the same contract
# `hooks/test_guard.py` holds, so a mutation test needs no second copy of this file.
_GUARD_PATH = os.environ.get("GUARD_UNDER_TEST")
if _GUARD_PATH:
    import importlib.util
    _spec = importlib.util.spec_from_file_location("guard_under_test", _GUARD_PATH)
    guard = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(guard)
else:
    import guard


# ------------------------------------------------------------------ the watched set
#
# The project's own settings files, the pair `guard.PROJECT_FROZEN_FILES` already names. The
# config directory is NOT watched here. Rule 7 denies a write there, and `~/.claude/settings.json`
# is a symlink onto the clone of claude-settings, which is deliberately unfrozen so that the
# repository can edit its own source. A hash watch that followed that symlink would revert the
# repository's own work.
WATCHED_NAMES = tuple(name.lstrip("/") for name in guard.PROJECT_FROZEN_FILES)

STORE_DIR_NAME = "state"
STORE_SUB = "config-watch"

REVERT_MESSAGE = (
    "Guard (subagent-model-cap): an unasked write changed the subagent model cap in {where}. "
    "Tool: {tool}. Command: {what}. Reading: {change}. "
    "The previous content is back in place and the rejected content is kept at {kept}. "
    "The PreToolUse guard could not read this write, so it asked nobody. "
    "To lift the cap, write the file with a tool that names the value, and approve the ask."
)

UNKNOWN_MESSAGE = (
    "Guard (subagent-model-cap): {where} sets the subagent model cap and this session holds no "
    "baseline for it, so the guard cannot tell a lift from the file's own starting state. "
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
    return os.path.join(guard.config_dir(), STORE_DIR_NAME, STORE_SUB)


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
        return {"digest": "", "content": None}
    if not isinstance(blob, str):
        return None
    try:
        content = base64.b64decode(blob.encode("ascii"), validate=True)
    except Exception:
        return None
    if digest(content) != entry.get("digest"):
        return None
    return {"digest": entry.get("digest"), "content": content}


def save_baseline(path: str, content) -> None:
    """Record one path's content as the baseline. A failure here never changes a decision."""
    try:
        os.makedirs(store_dir(), exist_ok=True)
        entry = {
            "path": path,
            "digest": digest(content),
            "content": None if content is None else base64.b64encode(content).decode("ascii"),
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


def judge_path(path: str, tool: str, tool_input, cwd: str, explained: str):
    """Judge one watched path. Return a message to print, or ''.

    Four answers, in order:

      no baseline  : record it. Report UNKNOWN when the file already sets the cap, because a first
                     sight cannot tell a lift from a starting state, and silence there would read
                     as clear.
      unchanged    : nothing.
      cap unchanged: Decision 7. Re-baseline and say nothing.
      cap changed  : explained, so re-baseline and pass. Otherwise restore and report.
    """
    current = read_file(path)
    now = digest(current)
    baseline = load_baseline(path)

    if baseline is None:
        save_baseline(path, current)
        reading = cap_reading(current)
        if reading:
            return UNKNOWN_MESSAGE.format(
                where=safe(path, guard.CAP_MAX_PATH), change=reading_text(reading))
        return ""

    if now == baseline["digest"]:
        return ""

    was = cap_reading(baseline["content"])
    reading = cap_reading(current)
    if reading == was:
        save_baseline(path, current)
        return ""

    if explained and explained == resolve(path, cwd):
        save_baseline(path, current)
        return ""

    kept = keep_rejected(path, current)
    if not restore(path, baseline["content"]):
        return UNKNOWN_MESSAGE.format(
            where=safe(path, guard.CAP_MAX_PATH), change=reading_text(reading))
    save_baseline(path, baseline["content"])
    guard.record(tool or "Stop", "reverted", "subagent-model-cap",
                 guard.log_path_and_text(path, reading_text(reading)))
    return REVERT_MESSAGE.format(
        where=safe(path, guard.CAP_MAX_PATH),
        tool=safe(tool or "(turn end)", 40),
        what=command_text(tool, tool_input),
        change=reading_text(reading),
        kept=safe(kept or "(not kept)", guard.CAP_MAX_PATH))


def sweep(payload):
    """Judge every watched path for this payload. Return the messages, in path order."""
    tool = payload.get("tool_name", "") or ""
    tool_input = payload.get("tool_input", {}) or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    cwd = payload.get("cwd", "") or os.getcwd() or ""
    if not isinstance(cwd, str):
        cwd = ""
    explained = explained_path(tool, tool_input, cwd)
    messages = []
    for path in watched_paths(cwd):
        message = judge_path(path, tool, tool_input, cwd, explained)
        if message:
            messages.append(message)
    return messages


def main() -> None:
    guard._force_utf8_streams()
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # fail open on unreadable input
    if not isinstance(payload, dict):
        sys.exit(0)  # fail open on a payload that is not an object
    try:
        messages = sweep(payload)
    except Exception:
        sys.exit(0)  # fail open on a watch defect
    if messages:
        print(json.dumps({"systemMessage": " ".join(messages)}))
    sys.exit(0)


if __name__ == "__main__":
    main()
