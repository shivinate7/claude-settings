#!/usr/bin/env python3
"""Removes a session's temp folder, `<Temp>/claude/<project>/<session id>/`, once the session's
transcript has been idle over 24 hours. When a read cannot tell, it keeps.

Spec: the debt windows-temp-sweep (owner ruling 2026-10-16, 24 hours).

The transcript is `<CLAUDE_CONFIG_DIR or ~/.claude>/projects/<project>/<session id>.jsonl`. Its mtime
decides, never the folder's own mtime. No transcript, an unreadable one, or a future mtime means keep.
The step touches only direct children of `<Temp>/claude/<project>/`; a link is never followed or
removed. `<Temp>` is TEMP, else LOCALAPPDATA/Temp.

The Windows-only gate is the caller's, not this file's: the gates run this suite on Linux and macOS
with fixture folders.

Usage:
    python3 janitor/temp_sweep.py             # preview: print each idle session id
    python3 janitor/temp_sweep.py --confirm   # remove those session folders
"""
import os
import shutil
import sys
import time

IDLE_SECONDS = 24 * 3600


def _is_link(path):
    isjunction = getattr(os.path, "isjunction", lambda p: False)
    return os.path.islink(path) or isjunction(path)


def temp_claude_root():
    temp = os.environ.get("TEMP")
    if not temp and os.environ.get("LOCALAPPDATA"):
        temp = os.path.join(os.environ["LOCALAPPDATA"], "Temp")
    return os.path.join(temp, "claude") if temp else None


def transcripts_root():
    config = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser(os.path.join("~", ".claude"))
    return os.path.join(config, "projects")


def idle_sessions(now=None):
    """Yield (session id, folder) for each session folder whose transcript is idle over 24 hours."""
    now = time.time() if now is None else now
    root = temp_claude_root()
    if not root or not os.path.isdir(root):
        return
    for project in sorted(os.listdir(root)):
        project_dir = os.path.join(root, project)
        if _is_link(project_dir) or not os.path.isdir(project_dir):
            continue
        for session in sorted(os.listdir(project_dir)):
            folder = os.path.join(project_dir, session)
            if _is_link(folder) or not os.path.isdir(folder):
                continue
            transcript = os.path.join(transcripts_root(), project, session + ".jsonl")
            try:
                age = now - os.stat(transcript).st_mtime
            except OSError:
                continue  # no transcript, or unreadable: unknown is never idle
            if age > IDLE_SECONDS:
                yield session, folder


def main(argv):
    confirm = "--confirm" in argv
    failed = 0
    for session, folder in idle_sessions():
        print(session)
        if confirm:
            try:
                shutil.rmtree(folder)
            except OSError as exc:
                failed += 1
                print("could not remove %s: %s" % (folder, exc), file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
