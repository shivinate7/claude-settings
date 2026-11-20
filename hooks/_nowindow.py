"""One home for starting a child process with no console window.

Why: console windows kept popping into the foreground on
Windows when a hook, mod or tool started a helper program. Every product file that starts a child
process calls the wrappers here, never `subprocess` directly. lint/test_no_window_spawn.py scans for
a raw call. hooks/test_nowindow.py pins this contract.

Each wrapper is a drop-in for the `subprocess` function of the same name. On Windows it ORs
CREATE_NO_WINDOW into the caller's `creationflags` and keeps every flag the caller passed. Elsewhere
it adds nothing. On Windows, when the caller gives no stdin and no input, the child inherits this process's
stdin only when it is a pipe or a file. A console stdin, or one that cannot be read, becomes an empty stdin: a
no-window child cannot use an inherited console stdin, and its own subprocess calls fail with WinError 6. The
platform is read at call time, and the wrapper looks up `subprocess.<name>` at call time too, so a test patch
on `subprocess.<name>` sees the call.

Limit: on Windows, when the wrapper sets stdin, Python hands the child the caller's own stdout and stderr
when the caller redirects neither (subprocess fills all three standard handles once one is set). Where that
output lands under the flag is unmeasured. A site that must show a child's output on the caller's terminal
carries a `# nowindow: <reason>` marker and calls `subprocess` itself.
"""
import contextlib
import os
import signal
import stat
import subprocess
import sys
import threading

CREATE_NO_WINDOW = 0x08000000  # subprocess has no such name on a non-Windows runner


def _stdin_is_data():
    """True when this process's stdin is a pipe or a file: data a child may read, valid with no console."""
    try:
        mode = os.fstat(0).st_mode
    except (OSError, ValueError):
        return False
    return stat.S_ISFIFO(mode) or stat.S_ISREG(mode)


def _flags(kwargs):
    if sys.platform == "win32" or os.name == "nt":
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_NO_WINDOW
        if kwargs.get("stdin") is None and kwargs.get("input") is None and not _stdin_is_data():
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
    had_stdin = kwargs.get("stdin") is not None
    kwargs = _flags(kwargs)
    if not had_stdin and kwargs.get("stdin") is subprocess.DEVNULL and "input" in kwargs and kwargs["input"] is None:
        del kwargs["input"]  # check_output turns input=None into "", which subprocess refuses beside _flags' stdin
    return subprocess.check_output(*args, **kwargs)


def descendants(pid):
    """The pids below `pid`, children first, read once from the process table (Linux /proc, else `ps -A`). [] when the table cannot be read.
    Own reader: hooks/guard_kill.py imports this module, so it cannot be the home of a reader this module calls."""
    table = {}
    try:
        if sys.platform.startswith("linux"):
            for name in os.listdir("/proc"):
                try:
                    with open("/proc/%s/stat" % name, "rb") as handle:
                        data = handle.read().decode("utf-8", "replace")
                    table[int(name)] = int(data[data.rindex(")") + 2:].split()[1])
                except (OSError, ValueError, IndexError):
                    continue  # not a pid, or it ended during the read
        else:
            for line in run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True, timeout=10).stdout.splitlines():
                fields = line.split()
                if len(fields) == 2 and all(f.isdigit() for f in fields):
                    table[int(fields[0])] = int(fields[1])
    except (OSError, subprocess.SubprocessError):
        return []
    found, frontier = [], [pid]
    while frontier:
        frontier = [p for parent in frontier for p, pp in table.items() if pp == parent and p not in found and p != pid]
        found += frontier
    return found


def kill_tree(proc, sig, known=()):
    """Send `sig` to `proc` and to every process below it, and to each pid in `known`. -> the pids it reached, to pass as `known` to a later
    call, because a child that has exited leaves its own children with no parent to find them by. The caller leaves the child in the caller's
    own process group, so a KILL to that group reaches it with no handler; this reaches the tree when only the caller is signalled.
    Windows has no process tree to walk: the signal goes to proc alone, as terminate (or kill for SIGKILL)."""
    if not hasattr(os, "killpg"):
        proc.kill() if sig == getattr(signal, "SIGKILL", None) else proc.terminate()
        return []
    pids = ([proc.pid] if proc.returncode is None else []) + descendants(proc.pid)
    pids += [p for p in known if p not in pids]
    for pid in pids:
        try:
            os.kill(pid, sig)
        except OSError:
            pass
    return pids


@contextlib.contextmanager
def forward_signals(proc, names=("SIGTERM", "SIGHUP"), grace=5):
    """While the block runs, each signal in `names` that reaches this process goes to `proc` and the processes below it (kill_tree).
    A caller killed alone would leave them running. The block keeps waiting on `proc`, so its own clean-up runs once it ends; a process
    still alive `grace` seconds after the signal is killed. Handlers are restored on exit.
    A non-main thread and Windows keep the default handling."""
    nums = [getattr(signal, n) for n in names if hasattr(signal, n)]
    timers = []
    def forward(sig, frame):
        if proc.returncode is not None:
            return  # reaped: its pid may be reused
        reached = kill_tree(proc, sig)
        timer = threading.Timer(grace, kill_tree, (proc, getattr(signal, "SIGKILL", signal.SIGTERM), reached))
        timer.daemon = True
        timer.start()
        timers.append(timer)
    try:
        before = {n: signal.signal(n, forward) for n in nums} if hasattr(os, "killpg") else {}
    except ValueError:
        before = {}
    try:
        yield
    finally:
        for n, handler in before.items():
            signal.signal(n, handler)
        for timer in timers:
            timer.cancel()
