"""Read one process's exec-time environment: does it hold this session's tag, or what is its agent marker?

The one home of that read (decision a-kill-by-pid-needs-an-owned-pid). The guard asks it before it
allows a kill of a PPID-1 pid; the SessionEnd sweep asks it before it stops a scratchpad orphan.

A server an agent's Bash call starts holds `CLAUDE_CODE_SESSION_ID=<the session's id>` in its
exec-time environment, the same id the hook payload carries as `session_id`. An agent-level marker
exists too: the stall_watch hook puts `export CLAUDE_AGENT_ID=<agent_id>` ahead of a background agent
Bash call's wrapper, so each process the job execs holds it (AGENT_TAG_NAME, read by entry_value). A
foreground call is not rewritten, so its processes hold no marker. The job's `( )` subshell is a fork,
so it holds neither at exec (the shell sets the session id afterwards, and the export runs inside the
shell) and reads unmarked; its exec'd children read marked. Measured on Linux. The macOS read of
CLAUDE_AGENT_ID is unmeasured. Read on macOS and on Linux; lint/test_wait_pid.py reads the session
tag live on Linux.

Stdlib only, no child process. Every failure (EPERM, EINVAL, a dead pid, a bad id) answers False
from holds_session_tag and None from entry_value.
"""
import ctypes
import sys

TAG_NAME = "CLAUDE_CODE_SESSION_ID"
AGENT_TAG_NAME = "CLAUDE_AGENT_ID"
CTL_KERN, KERN_PROCARGS2 = 1, 49


def _environ_entries_macos(pid: int):
    """The environment strings (bytes) of `pid` from sysctl KERN_PROCARGS2, or None.

    Layout: int argc, the exec path, NUL padding, argc argv strings, then the env strings. The env
    starts after exactly argc strings, so an argv entry that looks like `NAME=value` is never
    read as env. ponytail: an EMPTY argv[0] is eaten by the padding skip, which shifts the env
    by one entry, so a read can miss the tag (foreign) and never invent one.
    """
    libc = ctypes.CDLL(None, use_errno=True)
    libc.sysctl.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_uint, ctypes.c_void_p,
                            ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p, ctypes.c_size_t]
    libc.sysctl.restype = ctypes.c_int
    mib = (ctypes.c_int * 3)(CTL_KERN, KERN_PROCARGS2, pid)
    size = ctypes.c_size_t(0)
    if libc.sysctl(mib, 3, None, ctypes.byref(size), None, 0) != 0 or size.value < 8:
        return None
    buf = ctypes.create_string_buffer(size.value)
    if libc.sysctl(mib, 3, buf, ctypes.byref(size), None, 0) != 0:
        return None
    data = buf.raw[:size.value]
    argc = int.from_bytes(data[:4], sys.byteorder)
    pos = data.find(b"\0", 4)            # end of the exec path
    if pos < 0:
        return None
    while pos < len(data) and data[pos] == 0:
        pos += 1                         # the padding
    parts = data[pos:].split(b"\0")
    return parts[argc:]


def _environ_entries_linux(pid: int):
    with open("/proc/%d/environ" % pid, "rb") as handle:
        return handle.read().split(b"\0")


def _entries(pid):
    """The env entries (bytes) of `pid` on macOS or Linux, or None on another platform. May raise."""
    if sys.platform == "darwin":
        return _environ_entries_macos(pid)
    if sys.platform.startswith("linux"):
        return _environ_entries_linux(pid)
    return None


def _usable_pid(pid) -> bool:
    return not isinstance(pid, bool) and isinstance(pid, int) and pid > 1


def entry_value(pid: int, name: str):
    """The value of the first `<name>=` entry in `pid`'s exec-time environment, or None.

    Matches the whole entry name, so `X_NAME` and `NAME_X` are not `NAME`. An empty value is "".
    A bad pid or name, a dead pid, EPERM, an undecodable value, an absent name, Windows and any other
    platform answer None.
    """
    if not _usable_pid(pid) or not isinstance(name, str) or not name or "=" in name or "\0" in name:
        return None
    try:
        entries = _entries(pid)
        if entries is None:
            return None
        prefix = (name + "=").encode()
        for entry in entries:
            if entry.startswith(prefix):
                return entry[len(prefix):].decode()
        return None
    except Exception:
        return None


def holds_session_tag(pid: int, session_id) -> bool:
    """True when `pid`'s exec-time environment holds exactly `CLAUDE_CODE_SESSION_ID=<session_id>`.

    A whole entry, never a substring: a suffix, a prefix, another variable's value and argv do not
    match. An empty or malformed `session_id`, Windows and any other platform answer False.
    """
    if not isinstance(session_id, str) or not session_id or "\0" in session_id or not _usable_pid(pid):
        return False
    try:
        entries = _entries(pid)
        want = (TAG_NAME + "=" + session_id).encode()
        return entries is not None and any(entry == want for entry in entries)
    except Exception:
        return False
