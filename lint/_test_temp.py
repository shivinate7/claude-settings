"""The test temp-file standard for lint/ suites (decision test-temp-standard).

One temp root for this repo, one run folder per test run named `<pid>-<UUID>`, and a sweep of
sibling run folders older than one day. hooks/test_guard.py keeps the same root and name, so
each sweep also cleans the other's crashed runs.
"""
import os
import re
import shutil
import tempfile
import time
import uuid

TEMP_ROOT = os.path.join(tempfile.gettempdir(), "claude-settings-test-temp")
RUN_FOLDER_RE = re.compile(r"[0-9]+-[0-9a-f]{32}")
MAX_AGE = 24 * 60 * 60


def sweep(temp_root, own, now=None):
    """Remove each sibling run folder under `temp_root` whose mtime is over a day old. `own` stays."""
    now = time.time() if now is None else now
    try:
        names = os.listdir(temp_root)
    except OSError:
        return
    for name in names:
        path = os.path.join(temp_root, name)
        if path == own or not RUN_FOLDER_RE.fullmatch(name) or not os.path.isdir(path):
            continue
        if now - os.path.getmtime(path) > MAX_AGE:
            shutil.rmtree(path, ignore_errors=True)


def run_folder(temp_root=TEMP_ROOT):
    """Make this run's folder, sweep old siblings, and return the folder. The caller removes it."""
    os.makedirs(temp_root, exist_ok=True)
    own = os.path.join(temp_root, "%d-%s" % (os.getpid(), uuid.uuid4().hex))
    os.makedirs(own)
    sweep(temp_root, own)
    return own
