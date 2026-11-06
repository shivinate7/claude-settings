#!/usr/bin/env python3
"""The tier file: how a local triage session proves its tier to rule roadmap-one-writer (decision session-tiers).

A local session has no get_session record in its transcript, so the transcript proves nothing. Instead the
coordinator grants the triage FOLDER, and the guard binds that grant to the session id of the first top-level call
made from exactly that folder. The bound file then proves the tier. This module is the one home of the tier
value, the tier dir, the file formats and the folder key. The guard (guard.py, guard_merge.py) imports it, and the
coordinator runs its CLI:

    python3 ~/.claude/hooks/session_tier.py grant triage --folder <path>      (Windows: python)

Files, under ${CLAUDE_CONFIG_DIR:-~/.claude}/session-tiers:
    grant-<first 16 hex digits of sha256(folder key)>.json   {"tier", "folder", "at"}   one per folder
    <session id>.json                                        {"tier", "folder", "at"}   one per bound session
    revoked-<session id>.json                                {"revoked", "folder", "at"}  a tombstone

A grant for a folder revokes the sessions bound to that folder: each such bound file is removed and a tombstone
takes its place, so that session id never binds again and never proves again.

Cost, per top-level guard call: one stat of the tier dir. A missing dir ends the work. With the dir, one realpath
of the cwd (one lstat per path component), one stat of the session's tombstone, and one rename of the grant path
for the cwd's folder. No extra process, no timer. A push to the record branch adds one tombstone stat and one
small file read. Standard library only, except on Windows, where norm_folder imports guard_core to read a Git
Bash path; the CLI then needs the guard files beside it, as the install lays them out.
"""
import hashlib
import json
import os
import re
import sys
import tempfile
import time

TRIAGE_TIER = "triage"
TIERS = (TRIAGE_TIER,)
GRANT_TTL_SECONDS = 3600
TIER_DIR_NAME = "session-tiers"
# Same shape as guard_shared_tree.SESSION_ID_RE, repeated because that module imports guard_core and the CLI must
# start without it. A session id names a file in the tier dir, so no separator or leading dot gets through.
_SESSION_ID = re.compile(r"^[A-Za-z0-9._-]{8,200}$")
# A session id may not start like a grant or a tombstone, so its bound file never shares their names.
_RESERVED_PREFIXES = ("grant-", "revoked-")
_CLOCK_SKEW_SECONDS = 300


def tier_dir() -> str:
    """The tier dir, read from the environment at call time (the same rule as shared_names.config_dir)."""
    return os.path.join(
        os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude"), TIER_DIR_NAME)


def norm_folder(path: str) -> str:
    """The folder key: the real path, case-folded where the platform folds case, no trailing separator. On
    Windows a Git Bash `/c/Users/...` path reads as its drive path (guard_core._expanded, the one reader).
    normcase is the identity on POSIX, so two spellings that differ only in case are two keys there: on a
    case-insensitive macOS volume a cwd spelled with another case than the grant's folder binds nothing. That fails
    closed, and the coordinator re-grants with the spelling the session's cwd carries."""
    text = str(path)
    if os.name == "nt":
        try:
            from guard_core import _expanded
            text = _expanded(text, "")
        except Exception:
            pass
    norm = os.path.normcase(os.path.realpath(text))
    return norm.rstrip(os.sep) or os.sep


def _grant_path_for(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return os.path.join(tier_dir(), "grant-" + digest + ".json")


def grant_path(folder: str) -> str:
    return _grant_path_for(norm_folder(folder))


def _valid_session(session_id) -> bool:
    return (isinstance(session_id, str) and bool(_SESSION_ID.match(session_id))
            and not session_id.startswith((".",) + _RESERVED_PREFIXES))


def bound_path(session_id: str) -> str:
    return os.path.join(tier_dir(), session_id + ".json")


def revoked_path(session_id: str) -> str:
    return os.path.join(tier_dir(), "revoked-" + session_id + ".json")


def _read_tier_file(path: str):
    """The parsed file, or None for a missing, unreadable or malformed one. The text is read as bytes and decoded
    utf-8-sig, so a BOM and CRLF lines (the Windows spelling) parse the same as a plain file."""
    try:
        with open(path, "rb") as handle:
            body = json.loads(handle.read().decode("utf-8-sig").strip())
    except Exception:
        return None
    return body if isinstance(body, dict) else None


def _write_atomic(path: str, body: dict) -> None:
    """Write `body` to `path` through a temp file in the same folder and one rename: a reader never sees half."""
    folder = os.path.dirname(path)
    handle, temp = tempfile.mkstemp(dir=folder, prefix=".tmp-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(body, out)
        os.replace(temp, path)
    except BaseException:
        try:
            os.remove(temp)
        except OSError:
            pass
        raise


def _tier_body(body, folder: str = None):
    """`body` when it is a whole grant or bound body (a tier string, an integer time, and `folder` when given), else None."""
    if not isinstance(body, dict) or not isinstance(body.get("tier"), str):
        return None
    at = body.get("at")
    if not isinstance(at, int) or isinstance(at, bool):
        return None
    if folder is not None and body.get("folder") != folder:
        return None
    return body


def bind_grant(session_id, agent_id, cwd) -> bool:
    """Bind the grant for the cwd's folder to the session, and return True when this call did. Only a top-level call
    (no agent id) with a valid session id and a cwd binds; the grant must be for EXACTLY the cwd's folder, no parent
    walk, and younger than GRANT_TTL_SECONDS. The grant is claimed by one rename, so the first call wins and a second
    session finds nothing. A stale grant is deleted and binds nothing. Any error binds nothing and never raises."""
    try:
        if agent_id or not _valid_session(session_id) or not cwd or not isinstance(cwd, str):
            return False
        if not os.path.isdir(tier_dir()):   # the one stat a call with no grants pays
            return False
        key = norm_folder(cwd)
        if os.path.exists(revoked_path(session_id)):   # a revoked session never binds again
            return False
        grant = _grant_path_for(key)
        claim = os.path.join(os.path.dirname(grant), ".claim-" + session_id + "-" + os.path.basename(grant))
        try:
            os.replace(grant, claim)
        except OSError:
            return False   # no grant for this folder, or another session claimed it first
        try:
            body = _tier_body(_read_tier_file(claim), key)
            if body is None or body["tier"] not in TIERS or (
                    not -_CLOCK_SKEW_SECONDS <= time.time() - body["at"] <= GRANT_TTL_SECONDS):
                return False   # corrupt, unknown tier or stale: consumed, so a re-grant is needed
            _write_atomic(bound_path(session_id), {"tier": body["tier"], "folder": body["folder"],
                                                   "at": int(time.time())})
            return True
        finally:
            try:
                os.remove(claim)
            except OSError:
                pass
    except Exception:
        return False


def file_proved(session_id, agent_id, tier: str = TRIAGE_TIER) -> bool:
    """True when the session's bound file shows `tier`. Never for an agent call. Fails closed: a missing or
    malformed file, an invalid session id or any error is False."""
    try:
        if agent_id or not _valid_session(session_id) or os.path.exists(revoked_path(session_id)):
            return False
        body = _tier_body(_read_tier_file(bound_path(session_id)))
        return body is not None and body["tier"] == tier
    except Exception:
        return False


def _revoke_folder(key: str) -> None:
    """Revoke every session bound to the folder `key`: write its tombstone, then remove its bound file. A bound file
    for another folder, a grant and a tombstone are left alone. The tombstone comes first, so a failure part way
    leaves the session refused, never proved."""
    folder = tier_dir()
    for name in os.listdir(folder):
        if not name.endswith(".json") or name.startswith((".",) + _RESERVED_PREFIXES):
            continue
        session_id = name[:-len(".json")]
        bound = os.path.join(folder, name)
        body = _read_tier_file(bound)
        if not _valid_session(session_id) or body is None or body.get("folder") != key:
            continue
        _write_atomic(revoked_path(session_id), {"revoked": True, "folder": key, "at": int(time.time())})
        os.remove(bound)


def _grant_cli(args) -> int:
    """`grant <tier> --folder <path>`: write the grant atomically and print its path. Exit 2 and write nothing for
    an unknown tier, a missing --folder, or a folder that does not exist."""
    usage = "usage: session_tier.py grant <tier> --folder <path>   (tiers: %s)" % ", ".join(TIERS)
    if len(args) != 3 or args[1] != "--folder" or args[0] not in TIERS:
        print(usage, file=sys.stderr)
        return 2
    key = norm_folder(args[2])
    if not os.path.isdir(key):
        print("session_tier.py: no such folder: %s" % args[2], file=sys.stderr)
        return 2
    try:
        os.makedirs(tier_dir(), exist_ok=True)
        _revoke_folder(key)   # a grant starts a new triage, so the sessions bound to the folder before it end
        path = _grant_path_for(key)
        _write_atomic(path, {"tier": args[0], "folder": key, "at": int(time.time())})
    except OSError as exc:
        print("session_tier.py: could not write the grant: %s" % exc, file=sys.stderr)
        return 1
    print(path)
    return 0


def main(argv) -> int:
    if argv and argv[0] == "grant":
        return _grant_cli(argv[1:])
    print("usage: session_tier.py grant <tier> --folder <path>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
