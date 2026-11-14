#!/usr/bin/env python3
"""The launcher's role file: the one home of how a local session's tier is written and read (decision session-tiers).

bin/claude-role starts `claude` with CS_SESSION_ROLE set. The session-start hook runs `session_role.py write`, which records
that role in <config dir>/state/session-roles/<session id>.json as {"session", "role", "repo"}. The guard and the merge tool read
it with `own_record` / `own_role` where a cloud session reads its get_session tags. Claude cannot write the folder: the
configuration rule and settings.json's Edit deny refuse a write under the config directory.

Every read fails closed: a failure is None, never a role. pathlib only, so the same code runs on Windows; an os.replace that
raises (a reader holds the file open there) leaves the old file or none, which no reader trusts.
Cost: `write` is one small file write or delete per session start, plus the prune below; a reader is one file read.
"""
import contextlib
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guard_shared_tree import SESSION_ID_RE  # noqa: E402  the one home of the session id's shape

SESSION_ROLES = ("coordinator", "triage", "batch-runner")  # what bin/claude-role may start; a lane is never launched
STALE_SECONDS = 7 * 24 * 3600  # a role file this old belongs to a session that ended; `write` removes it


def roles_dir():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return pathlib.Path(base) / "state" / "session-roles"


def valid_id(sid):
    return isinstance(sid, str) and bool(SESSION_ID_RE.match(sid))


def own_record(sid):
    """The role file of session `sid` as a dict {"session", "role", "repo"}, or None: no id, an id outside the id shape, no file,
    unreadable or malformed, a file that names another session, or a role outside SESSION_ROLES. The one reader."""
    if not valid_id(sid):
        return None
    try:
        data = json.loads((roles_dir() / (sid + ".json")).read_text(encoding="utf-8"))
    except (OSError, ValueError):  # UnicodeDecodeError and JSONDecodeError are ValueErrors
        return None
    if not isinstance(data, dict) or data.get("session") != sid:
        return None
    role = data.get("role")
    if not isinstance(role, str) or role not in SESSION_ROLES:  # a list is unhashable: test the type first
        return None
    return data


def own_role(sid):
    """The role the launcher recorded for session `sid`, or None (see own_record)."""
    record = own_record(sid)
    return record["role"] if record else None


def own_file_exists(sid):
    """True when session `sid` has a role file, valid or not; False with no id, an id outside the id shape or no file. A path that cannot be
    tested for any reason but being absent counts as present, so the caller judges it (fails closed)."""
    if not valid_id(sid):
        return False
    try:
        (roles_dir() / (sid + ".json")).stat()
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:
        return True
    return True


def local_judgement(sid):
    """How a local `merge --confirm` judges session `sid`: (judged, record). The session is judged by its OWN file and by CS_SESSION_ROLE,
    the role the launcher started it with, never by another session's file.
      (a) an own file exists: judged, and its record is the proof; a corrupt or foreign file gives record None.
      (b) no own file, no id, and CS_SESSION_ROLE unset: not judged (False, None). Today's local behaviour stands.
      (c) CS_SESSION_ROLE set but no own file, no id, or a file whose role differs: judged with record None, because the hook failed to bind.
    A caller refuses a judged session whose record is None or whose role it does not allow. Each of the two readers, the guard and the merge
    tool, reads CS_SESSION_ROLE from its own process environment."""
    launcher = os.environ.get("CS_SESSION_ROLE") or ""
    if not own_file_exists(sid):
        return (True, None) if launcher else (False, None)
    record = own_record(sid)
    if record is not None and launcher and record["role"] != launcher:
        record = None
    return True, record


def prune_stale(now=None):
    """Remove every file in the role folder whose mtime is older than STALE_SECONDS. Any failure is skipped: a file that stays is only clutter.
    Cost: one directory listing and one stat per entry, at most one delete per stale file, once per session start (inside `write`)."""
    now = time.time() if now is None else now
    try:
        entries = list(roles_dir().iterdir())
    except OSError:
        return
    for entry in entries:
        try:
            if now - entry.stat().st_mtime > STALE_SECONDS:
                entry.unlink()
        except OSError:
            continue


def _repo_of(cwd):
    try:
        from git_reads import github_repo
        return github_repo(cwd)
    except Exception:
        return None


def write(session_id, cwd, role):
    """Record `role` for session `session_id`, or remove that session's file when `role` is empty or outside SESSION_ROLES (a stale
    file must not outlive a role the launcher no longer names). Returns True when the file now says what was asked. An id outside
    the id shape writes nothing. Each call first prunes files older than STALE_SECONDS (prune_stale)."""
    if not valid_id(session_id):
        return False
    prune_stale()
    path = roles_dir() / (session_id + ".json")
    if role not in SESSION_ROLES:
        try:
            path.unlink()
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return True
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")  # replace, so a reader never sees half a file
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps({"session": session_id, "role": role, "repo": _repo_of(cwd) if cwd else None}), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:  # PermissionError on Windows is one: the old file, if any, stays and the next start writes again
        with contextlib.suppress(OSError):
            tmp.unlink()
        return False
    return True


def main(argv):
    if argv[1:] != ["write"]:
        return 0
    try:
        payload = json.loads(sys.stdin.read())
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else ""
    write(payload.get("session_id"), cwd, os.environ.get("CS_SESSION_ROLE", ""))
    return 0  # a hook that fails writes nothing and says nothing


if __name__ == "__main__":
    sys.exit(main(sys.argv))
