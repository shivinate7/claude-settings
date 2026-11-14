#!/usr/bin/env python3
"""The launcher's role file: the one home of how a local session's tier is written and read (decision session-tiers).

bin/claude-role starts `claude` with CS_SESSION_ROLE set. The session-start hook runs `session_role.py write`, which records
that role in <config dir>/state/session-roles/<session id>.json as {"session", "role", "repo"}. The guard and the merge tool read
it with `own_record` / `own_role` where a cloud session reads its get_session tags. Claude cannot write the folder: the
configuration rule and settings.json's Edit deny refuse a write under the config directory.

Every read fails closed: a failure is None (or True for `roles_in_use`), never a role. pathlib only, so the same code runs on
Windows; an os.replace that raises (a reader holds the file open there) leaves the old file or none, which no reader trusts.
Cost: `write` is one small file write or delete per session start; a reader is one file read, or one folder listing.
"""
import contextlib
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guard_shared_tree import SESSION_ID_RE  # noqa: E402  the one home of the session id's shape

SESSION_ROLES = ("coordinator", "triage", "batch-runner")  # what bin/claude-role may start; a lane is never launched


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


def roles_in_use():
    """True when the folder holds any role file. The local gates judge a session only then: with no file, no session was started by
    the launcher and today's local behaviour stands. A folder that cannot be listed for any reason but being absent counts as in use."""
    try:
        return any(entry.suffix == ".json" for entry in roles_dir().iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:
        return True


def _repo_of(cwd):
    try:
        from git_reads import github_repo
        return github_repo(cwd)
    except Exception:
        return None


def write(session_id, cwd, role):
    """Record `role` for session `session_id`, or remove that session's file when `role` is empty or outside SESSION_ROLES (a stale
    file must not outlive a role the launcher no longer names). Returns True when the file now says what was asked. An id outside
    the id shape writes nothing."""
    if not valid_id(session_id):
        return False
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
