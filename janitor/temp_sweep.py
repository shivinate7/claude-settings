#!/usr/bin/env python3
"""Removes a session's temp folder, `<Temp>/claude/<project>/<session id>/`, once the session's
transcript has been idle over 24 hours. When a read cannot tell, it keeps.

Spec: docs/decisions/windows-temp-sweep.md.

The transcript is `<config dir>/projects/<project>/<session id>.jsonl`. Its mtime decides, never the
folder's own mtime. No transcript, an unreadable one, or a future mtime means keep. A session whose
process is live (`<config dir>/sessions/*.json`) keeps its folder, and so does any folder when the
sessions folder or the session reader (hooks/guard_core.py) cannot be read. The step touches only
direct children of `<Temp>/claude/<project>/`; a link is never followed or removed.
`<Temp>` is TEMP, else LOCALAPPDATA/Temp.

The Windows-only check is the caller's, not this file's: the checks run this suite on Linux and macOS
with fixture folders.

Usage:
    python3 janitor/temp_sweep.py             # preview: print each idle session id
    python3 janitor/temp_sweep.py --confirm   # remove those session folders
"""
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks"))
from shared_names import config_dir  # noqa: E402  the one home of the config dir, no guard module

IDLE_SECONDS = 24 * 3600
past_deadline = lambda: False  # noqa: E731  (the machine-wide sweep sets its own clock check)


def _is_link(path):
    isjunction = getattr(os.path, "isjunction", lambda p: False)
    return os.path.islink(path) or isjunction(path)


def temp_claude_root():
    temp = os.environ.get("TEMP")
    if not temp and os.environ.get("LOCALAPPDATA"):
        temp = os.path.join(os.environ["LOCALAPPDATA"], "Temp")
    return os.path.join(temp, "claude") if temp else None


def live_session_ids():
    """The ids of sessions whose process is live or cannot be told apart from live, or None when
    the sessions folder or the session reader cannot be read. A record names its session by
    `sessionId`, else by its file name."""
    folder = os.path.join(config_dir(), "sessions")
    if not os.path.isdir(folder):
        return set()
    try:
        # Loaded here, not at module load: sweep.py imports this file, and importing sweep.py
        # must load no guard module (its start-up cost lands on every SessionEnd run).
        import guard_core
    except Exception:  # a missing or half-copied guard_core: keep every folder
        return None
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    ids = set()
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as handle:
                record = json.load(handle)
        except (OSError, ValueError):
            continue  # one bad record does not make the folder unreadable
        if guard_core.session_is_live(record) is False:
            continue
        ids.add(name[:-len(".json")])
        if isinstance(record, dict) and isinstance(record.get("sessionId"), str):
            ids.add(record["sessionId"])
    return ids


def idle_sessions(errors, now=None):
    """Yield (session id, folder) for each session folder whose transcript is idle over 24 hours
    and whose session is not live. A read that fails adds a message to ERRORS and keeps."""
    now = time.time() if now is None else now
    root = temp_claude_root()
    if not root or not os.path.isdir(root):
        return
    live = live_session_ids()
    if live is None:
        errors.append("could not read the live sessions; nothing removed")
        return
    transcripts = os.path.join(config_dir(), "projects")
    try:
        projects = sorted(os.listdir(root))
    except OSError as exc:
        errors.append("could not list %s: %s" % (root, exc))
        return
    for project in projects:
        project_dir = os.path.join(root, project)
        if _is_link(project_dir) or not os.path.isdir(project_dir):
            continue
        try:
            sessions = sorted(os.listdir(project_dir))
        except OSError as exc:
            errors.append("could not list %s: %s" % (project_dir, exc))
            continue
        for session in sessions:
            folder = os.path.join(project_dir, session)
            if _is_link(folder) or not os.path.isdir(folder) or session in live:
                continue
            try:
                age = now - os.stat(os.path.join(transcripts, project, session + ".jsonl")).st_mtime
            except OSError:
                continue  # no transcript, or unreadable: unknown is never idle
            if age > IDLE_SECONDS:
                yield session, folder


def run(confirm):
    """Print each idle session id; with CONFIRM remove its folder. Stops at the deadline. Returns
    the number of failures (folders not removed, folders not read)."""
    errors = []
    for session, folder in idle_sessions(errors):
        if past_deadline():
            break  # the next run does the rest
        print(session)
        if confirm:
            try:
                shutil.rmtree(folder)
            except OSError as exc:
                errors.append("could not remove %s: %s" % (folder, exc))
    for message in errors:
        print(message, file=sys.stderr)
    return len(errors)


def main(argv):
    return 1 if run("--confirm" in argv) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
