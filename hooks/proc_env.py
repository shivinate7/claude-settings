"""Read one process's exec-time environment, for one question: does it hold this session's tag?

The one home of that read (decision a-kill-by-pid-needs-an-owned-pid). The guard asks it before it
allows a kill of a PPID-1 pid; the SessionEnd sweep asks it before it stops a scratchpad orphan.

A server an agent's Bash call starts holds `CLAUDE_CODE_SESSION_ID=<the session's id>` in its
exec-time environment, the same id the hook payload carries as `session_id`. No agent-level tag
exists. The tool's own zsh does not hold it at exec (the shell sets it afterwards), so a forked
shell stub reads untagged. Read on macOS and on Linux; lint/test_wait_pid.py reads it live on Linux.

Stdlib only, no child process. Every failure (EPERM, EINVAL, a dead pid, a bad id) answers False.
"""
import ctypes
import sys

TAG_NAME = "CLAUDE_CODE_SESSION_ID"
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


def holds_session_tag(pid: int, session_id) -> bool:
    """True when `pid`'s exec-time environment holds exactly `CLAUDE_CODE_SESSION_ID=<session_id>`.

    A whole entry, never a substring: a suffix, a prefix, another variable's value and argv do not
    match. An empty or malformed `session_id`, Windows and any other platform answer False.
    """
    if not isinstance(session_id, str) or not session_id or "\0" in session_id \
            or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 1:
        return False
    try:
        if sys.platform == "darwin":
            entries = _environ_entries_macos(pid)
        elif sys.platform.startswith("linux"):
            entries = _environ_entries_linux(pid)
        else:
            return False
        want = (TAG_NAME + "=" + session_id).encode()
        return entries is not None and any(entry == want for entry in entries)
    except Exception:
        return False
