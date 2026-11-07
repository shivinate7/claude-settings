"""One home for starting a child process with no console window.

Why: console windows kept popping into the foreground on
Windows when a hook, mod or tool started a helper program. Every product file that starts a child
process calls the wrappers here, never `subprocess` directly. lint/test_no_window_spawn.py scans for
a raw call. hooks/test_nowindow.py pins this contract.

Each wrapper is a drop-in for the `subprocess` function of the same name. On Windows it ORs
CREATE_NO_WINDOW into the caller's `creationflags` and keeps every flag the caller passed. Elsewhere
it adds nothing. On Windows it also gives the child an empty stdin when the caller gives no stdin and no input:
a no-window child cannot use an inherited console stdin, and its own subprocess calls fail with WinError 6. The platform is read at call time, and the wrapper looks up `subprocess.<name>` at
call time too, so a test patch on `subprocess.<name>` sees the call.

Limit: on Windows, because the wrapper sets stdin, Python hands the child the caller's own stdout and stderr
when the caller redirects neither (subprocess fills all three standard handles once one is set). Where that
output lands under the flag is unmeasured. A site that must show a child's output on the caller's terminal
carries a `# nowindow: <reason>` marker and calls `subprocess` itself.
"""
import os
import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000  # subprocess has no such name on a non-Windows runner


def _flags(kwargs):
    if sys.platform == "win32" or os.name == "nt":
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_NO_WINDOW
        if kwargs.get("stdin") is None and kwargs.get("input") is None:
            # The child has no console, so an inherited console stdin is an invalid handle there, and its own
            # subprocess calls fail with WinError 6. An empty stdin is valid. input= sets stdin itself.
            kwargs["stdin"] = subprocess.DEVNULL
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
    if (sys.platform == "win32" or os.name == "nt") and "input" in kwargs and kwargs["input"] is None:
        del kwargs["input"]  # check_output turns input=None into "", which subprocess refuses beside _flags' stdin
    return subprocess.check_output(*args, **_flags(kwargs))
