"""The one definition of a loaded machine (decision one-load-definition): the readings, the limits and the verdict.

The guard (hooks/guard.py, decision machine-load-brake) and bin/sim-lease (decision sim-lease-tool) both call this
module, so they cannot disagree. Standard library only, and no import of any other guard module, so bin/sim-lease
loads it from hooks/ alone. No read starts a child process or writes a file.

Readings: memory in use as a percent, and GB free and GB total of the drive that holds the home folder. No CPU and no
load average. A reading that fails or that the platform does not offer is None (unread); one unread reading hides no
other. Each caller says what an unread reading does to its own act.
"""
import os
import sys

BUSY_MEMORY = 85.0
FULL_MEMORY = 95.0
BUSY_DISK_SHARE, BUSY_DISK_GB = 10.0, 15.0   # busy: free under the smaller of the two
FULL_DISK_SHARE, FULL_DISK_GB = 5.0, 5.0
GIB = 2 ** 30


def _read_memory():
    """Percent of physical memory in use, from the OS's own counter, or None on another platform."""
    import ctypes
    if sys.platform == "win32":
        from ctypes import wintypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return 100.0 * (status.ullTotalPhys - status.ullAvailPhys) / status.ullTotalPhys
    if sys.platform == "darwin":
        # kern.memorystatus_level is the free share that `memory_pressure` prints.
        level, size = ctypes.c_int(0), ctypes.c_size_t(ctypes.sizeof(ctypes.c_int))
        if ctypes.CDLL(None).sysctlbyname(b"kern.memorystatus_level", ctypes.byref(level),
                                          ctypes.byref(size), None, 0) != 0:
            return None
        return 100.0 - level.value
    return None


def _read_disk():
    """(GB free, GB total) of the drive that holds the home folder, 2**30 bytes to the GB."""
    import shutil
    usage = shutil.disk_usage(os.path.expanduser("~"))
    return usage.free / GIB, usage.total / GIB


def read_load() -> dict:
    """The readings: memory_pct (percent in use, clamped to 0-100) and disk_free_gb
    and disk_total_gb (GB, not clamped). No child process and no file. A reading that fails or cannot be read
    is None, and one failure hides no other."""
    out = {}
    for key, read in (("memory_pct", _read_memory),):
        try:
            value = read()
            out[key] = None if value is None else min(100.0, max(0.0, float(value)))
        except Exception:
            out[key] = None
    try:
        out["disk_free_gb"], out["disk_total_gb"] = _read_disk()
    except Exception:
        out["disk_free_gb"] = out["disk_total_gb"] = None
    return out


def _value(reading, key):
    """A reading as a float, or None when it is unread or not a number."""
    v = reading.get(key)
    return None if isinstance(v, bool) or not isinstance(v, (int, float)) else float(v)


def load_verdict(reading) -> dict:
    """The level of a reading: {"level": "full" | "busy" | "normal", "full": [...], "busy": [...], "unread": [...]}.
    full and busy list each reading over that line, as text ("busy" also holds the full ones). unread names each reading
    that is None or malformed ("memory", "disk"). The level is computed from the readings that were read, so an
    unread reading never hides another. A reading that is not a dict is wholly unread."""
    if not isinstance(reading, dict):
        reading = {}
    memory = _value(reading, "memory_pct")
    free, total = _value(reading, "disk_free_gb"), _value(reading, "disk_total_gb")
    disk_read = free is not None and total is not None
    full, busy = [], []
    if memory is not None:
        text = "memory %.1f%% in use" % memory
        if memory > FULL_MEMORY:
            full.append(text)
        if memory > BUSY_MEMORY:
            busy.append(text)
    if disk_read:
        text = "disk %.1f GB free of %.0f GB" % (free, total)
        if free < min(total * FULL_DISK_SHARE / 100.0, FULL_DISK_GB):
            full.append(text)
        if free < min(total * BUSY_DISK_SHARE / 100.0, BUSY_DISK_GB):
            busy.append(text)
    unread = (["memory"] if memory is None else []) + ([] if disk_read else ["disk"])
    return {"level": "full" if full else ("busy" if busy else "normal"), "full": full, "busy": busy, "unread": unread}


# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
