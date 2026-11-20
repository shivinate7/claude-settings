"""Process helpers for the fixture suites that start a tool and signal it: lint/test_verdict.py and
merge/test_launch.py. One home, so no suite copies them. Posix only: a caller skips on Windows.
"""
import os
import signal
import subprocess
import time


def zombie(pid):
    """True when pid has ended but not yet been reaped. /proc answers on Linux, ps elsewhere."""
    try:
        with open("/proc/%d/stat" % pid, encoding="utf-8") as handle:
            return handle.read().rsplit(")", 1)[1].split()[0] == "Z"
    except OSError:
        pass
    try:
        out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return out.strip().startswith("Z")


def alive(pid):
    """True when pid runs. A zombie has ended: a grandchild's zombie waits for init to reap it, so it reads as gone."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return not zombie(pid)


def wait_for(path, cap, proc=None):
    """True once `path` exists. False at `cap` seconds, or when `proc` ends first. A poll on the marker, never a fixed sleep."""
    end = time.monotonic() + cap
    while not os.path.exists(path):
        if (proc is not None and proc.poll() is not None) or time.monotonic() > end:
            return False
        time.sleep(0.05)
    return True


def kill_all(pids):
    """SIGKILL each pid that is still set. A cleanup: a red run leaves no process behind."""
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def stop_group(proc):
    """SIGKILL the process group of a proc started with start_new_session=True, then reap proc."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    proc.wait()
