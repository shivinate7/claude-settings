"""The test temp-file standard for lint/ suites (decision test-temp-standard).

One temp root for this repo, one run folder per test run named `<pid>-<UUID>`, and a sweep of
sibling run folders: one whose pid is dead goes after an hour, and one whose pid is alive goes
after a day. hooks/test_guard.py keeps the same root and name, so each sweep also cleans the
other's crashed runs.
"""
import os
import re
import shutil
import tempfile
import time
import uuid

TEMP_ROOT = os.path.join(tempfile.gettempdir(), "claude-settings-test-temp")
RUN_FOLDER_RE = re.compile(r"[0-9]+-[0-9a-f]{32}")
MAX_AGE = 24 * 60 * 60  # a live run's folder
DEAD_MAX_AGE = 60 * 60  # a folder whose run is dead


def pid_alive(pid):
    """False only when no process has this pid. A pid we cannot tell reads alive, so its folder keeps the day limit."""
    if os.name == "nt":
        import ctypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION; os.kill(pid, 0) is CTRL_C_EVENT there
        if not h:
            return ctypes.get_last_error() == 5  # access denied: it exists
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return not ok or code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OverflowError, ValueError, OSError):
        return True
    return True


def sweep(temp_root, own, now=None):
    """Remove each sibling run folder under `temp_root` whose mtime is over an hour old and whose pid is dead, or over a day old. `own` stays."""
    now = time.time() if now is None else now
    try:
        names = os.listdir(temp_root)
    except OSError:
        return
    for name in names:
        path = os.path.join(temp_root, name)
        if path == own or not RUN_FOLDER_RE.fullmatch(name) or not os.path.isdir(path):
            continue
        try:
            age = now - os.path.getmtime(path)
        except OSError:
            continue
        if age > MAX_AGE or (age > DEAD_MAX_AGE and not pid_alive(int(name.split("-", 1)[0]))):
            shutil.rmtree(path, ignore_errors=True)


def run_folder(temp_root=TEMP_ROOT):
    """Make this run's folder, sweep old siblings, and return the folder. The caller removes it."""
    os.makedirs(temp_root, exist_ok=True)
    own = os.path.join(temp_root, "%d-%s" % (os.getpid(), uuid.uuid4().hex))
    os.makedirs(own)
    sweep(temp_root, own)
    return own
