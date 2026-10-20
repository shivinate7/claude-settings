"""One home for starting a child process with no console window.

Why: console windows kept popping into the foreground on
Windows when a hook, mod or tool started a helper program. Every product file that starts a child
process calls the wrappers here, never `subprocess` directly. lint/test_no_window_spawn.py scans for
a raw call. hooks/test_nowindow.py pins this contract.

Each wrapper is a drop-in for the `subprocess` function of the same name. On Windows it ORs
CREATE_NO_WINDOW into the caller's `creationflags` and keeps every flag the caller passed. Elsewhere
it adds nothing. The platform is read at call time, and the wrapper looks up `subprocess.<name>` at
call time too, so a test patch on `subprocess.<name>` sees the call.

Limit: on Windows a child with no redirected stdout and stderr, started with this flag, writes to a
hidden console, so its output never reaches the caller's terminal. A site that must show a child's
output on the caller's terminal carries a `# nowindow: <reason>` marker and calls `subprocess` itself.
"""
import os
import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000  # subprocess has no such name on a non-Windows runner


def _flags(kwargs):
    if sys.platform == "win32" or os.name == "nt":
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_NO_WINDOW
    return kwargs


def run(*args, **kwargs):
    return subprocess.run(*args, **_flags(kwargs))


def Popen(*args, **kwargs):
    return subprocess.Popen(*args, **_flags(kwargs))


def call(*args, **kwargs):
    return subprocess.call(*args, **_flags(kwargs))


def check_call(*args, **kwargs):
    return subprocess.check_call(*args, **_flags(kwargs))


def check_output(*args, **kwargs):
    return subprocess.check_output(*args, **_flags(kwargs))
