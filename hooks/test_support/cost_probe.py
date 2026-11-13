"""Counters for the cost tests (rule outcomes-mechanize-rules).

A cost record names the child processes a mechanism starts, the files it writes and how often it runs.
Its test runs the mechanism, reads these counts and asserts the record's numbers. This module is the one
home of each counter. A case calls it; no case keeps its own copy.

  children()          context manager: lists the argv of every child process started in its block.
                      subprocess.run and the _nowindow wrappers start children through Popen, so they count too.
  StubRun             stands in for _nowindow.run: records each call, then returns or raises.
  CountingModel       stands in for a caller's model call: records each prompt and its kwargs, returns one answer.
  snapshot, written   the files a run created or changed under a folder.
  leftovers           every file and folder under a folder, for "nothing is left behind".
  FakeClock           the module `time`: it moves only when the code sleeps, and fails at a cap.
  settings_timeout    the `timeout` of the settings.json hook row whose command holds a name.
  run_hook            runs one hook file as its own process, under a probe that counts its starts and model calls.
  run_class           runs one unittest.TestCase class and reports whether every case passed.

Callers pass the folder they own. This module makes no run folder: the test-temp standard
(lint/_test_temp.py) gives each test file one run folder, and each case works under it.
"""
import contextlib
import json
import os
import signal
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "hooks"))
import _nowindow  # noqa: E402  the one home of a child start (hooks/_nowindow.py)


class ChildLog(object):
    """What children() saw: `argvs`, one list per start, and `procs`, the Popen object of each start."""

    def __init__(self):
        self.argvs, self.procs = [], []


@contextlib.contextmanager
def children():
    """Yields a ChildLog that records each child process started while the block runs."""
    log = ChildLog()
    real = subprocess.Popen

    class Counted(real):
        def __init__(self, args, *rest, **kwargs):
            argv = args if isinstance(args, (list, tuple)) else [args]
            log.argvs.append([str(part) for part in argv])
            real.__init__(self, args, *rest, **kwargs)
            log.procs.append(self)

    subprocess.Popen = Counted
    try:
        yield log
    finally:
        subprocess.Popen = real


def names(argvs):
    """The program name of each argv, without its folder: 'claude', 'git', ..."""
    return [os.path.basename(argv[0]).lower() for argv in argvs]


def stop_group(proc):
    """Kill a process this test started, and its process group, so a failing case leaves nothing running."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        proc.kill()
        proc.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


def group_members(pgid):
    """The pids in process group `pgid` that are alive, not zombies (Linux /proc). [] when none is."""
    found = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            with open("/proc/%s/stat" % name, encoding="utf-8") as f:
                fields = f.read().rsplit(")", 1)[1].split()  # the command name may hold spaces; fields follow ')'
        except OSError:
            continue
        state, group = fields[0], int(fields[2])
        if group == pgid and state != "Z":
            found.append(int(name))
    return found


class StubRun(object):
    """Stands in for _nowindow.run. Records each call's argv and kwargs. A call that `fails` accepts gets
    `error` raised; every other call gets `result`. The default `fails` takes nothing, so no call fails."""

    def __init__(self, result=None, error=None, fails=lambda argv: False):
        self.calls, self.result, self.error, self.fails = [], result, error, fails

    def __call__(self, argv, *args, **kwargs):
        self.calls.append((list(argv), kwargs))
        if self.error is not None and self.fails(list(argv)):
            raise self.error
        return self.result

    def argvs(self):
        return [argv for argv, _ in self.calls]


class CountingModel(object):
    """Stands in for a caller's model call (decision_watch.invoke_model). Records each prompt and each call's
    keyword arguments (model, timeout, effort), then returns `answer`."""

    def __init__(self, answer=({"ok": True}, None)):
        self.answer, self.prompts, self.kwargs = answer, [], []

    def __call__(self, prompt, *args, **kwargs):
        self.prompts.append(prompt)
        self.kwargs.append(kwargs)
        return self.answer


def snapshot(folder):
    """{relative path: (size, mtime_ns)} for each file under `folder`."""
    seen = {}
    for root, _dirs, files in os.walk(folder):
        for name in files:
            path = os.path.join(root, name)
            st = os.stat(path, follow_symlinks=False)
            seen[os.path.relpath(path, folder).replace(os.sep, "/")] = (st.st_size, st.st_mtime_ns)
    return seen


def written(before, after):
    """The sorted relative paths of the files that appear or change between two snapshots."""
    return sorted(path for path in after if before.get(path) != after[path])


def leftovers(folder):
    """Every file and folder under `folder`, relative, sorted. An empty folder gives []."""
    found = []
    for root, dirs, files in os.walk(folder):
        for name in dirs + files:
            found.append(os.path.relpath(os.path.join(root, name), folder).replace(os.sep, "/"))
    return sorted(found)


class FakeClock(object):
    """The module's `time`. It moves only when the code sleeps. A loop with no end fails at `cap` sleeps."""

    def __init__(self, start=1000.0, cap=400):
        self.now, self.sleeps, self.cap = start, [], cap

    def monotonic(self):
        return self.now

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        if len(self.sleeps) > self.cap:
            raise AssertionError("runaway wait: %d sleeps" % self.cap)
        self.now += max(seconds, 0)


def settings_timeout(needle, event=None):
    """The `timeout` in seconds of the settings.json hook row whose command holds `needle`, else None.
    `event` limits the search to one hook event, such as "Stop"."""
    with open(os.path.join(REPO, "settings.json"), encoding="utf-8") as f:
        settings = json.load(f)
    for name, rows in settings.get("hooks", {}).items():
        if event is not None and name != event:
            continue
        for row in rows:
            for hook in row.get("hooks", []):
                if needle in (hook.get("command") or ""):
                    return hook.get("timeout")
    return None


# One hook run, as its own process, with the child starts and the model calls it makes written to a log.
# The probe patches subprocess.Popen and decision_watch.invoke_model before it runs the hook file as
# __main__. Each caller reaches the model through decision_watch at call time, so one patch covers all.
PROBE = r'''
import io, json, os, runpy, subprocess, sys
LOG = os.environ["COST_LOG"]


def note(kind, value):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps([kind, value]) + "\n")


real_popen = subprocess.Popen


class CountedPopen(real_popen):
    def __init__(self, args, *rest, **kwargs):
        argv = args if isinstance(args, (list, tuple)) else [args]
        note("child", [str(part) for part in argv])
        real_popen.__init__(self, args, *rest, **kwargs)


subprocess.Popen = CountedPopen
sys.path.insert(0, os.environ["COST_HOOKS"])
import decision_watch  # noqa: E402

ANSWERS = json.loads(os.environ.get("COST_ANSWERS") or "[]") or [[{"ok": True}, None]]
calls = [0]


def stub(prompt, *args, **kwargs):
    note("model", {"model": kwargs.get("model"), "timeout": kwargs.get("timeout"), "effort": kwargs.get("effort")})
    answer = ANSWERS[min(calls[0], len(ANSWERS) - 1)]
    calls[0] += 1
    return tuple(answer)


decision_watch.invoke_model = stub
sys.stdin = io.TextIOWrapper(io.BytesIO(os.environ["COST_STDIN"].encode("utf-8")), encoding="utf-8")
hook = sys.argv[1]
sys.argv = sys.argv[1:]
sys.path.insert(0, os.path.dirname(os.path.abspath(hook)))
try:
    runpy.run_path(hook, run_name="__main__")
except SystemExit as done:
    sys.exit(done.code)
'''


def run_hook(hook, stdin_text, folder, answers=None, env=None):
    """Run the hook file once, as a process of its own, under PROBE. `folder` is this case's own folder:
    the config dir is folder/config, and the event log is folder/events.log. `answers` is a list of
    (verdict, error) pairs, the model's answers in call order, the last one repeated. `env` adds variables.
    Returns a dict: code, out, err, children (argv lists), models (kwargs of each call), files (relative
    paths the run created or changed under the config dir)."""
    config = os.path.join(folder, "config")
    os.makedirs(config, exist_ok=True)
    log = os.path.join(folder, "events.log")
    if os.path.exists(log):  # a folder can hold several runs in a row: each run reads its own events
        os.remove(log)
    before = snapshot(config)
    run_env = dict(os.environ, CLAUDE_CONFIG_DIR=config, COST_LOG=log, COST_STDIN=stdin_text,
                   COST_HOOKS=os.path.join(REPO, "hooks"), COST_ANSWERS=json.dumps(answers or []))
    run_env.update(env or {})
    run = _nowindow.run([sys.executable, "-c", PROBE, hook], env=run_env, capture_output=True,
                        text=True, encoding="utf-8", errors="replace", timeout=120)
    events = []
    if os.path.exists(log):
        with open(log, encoding="utf-8") as f:
            events = [json.loads(line) for line in f if line.strip()]
    return {
        "code": run.returncode,
        "out": run.stdout,
        "err": run.stderr,
        "children": [value for kind, value in events if kind == "child"],
        "models": [value for kind, value in events if kind == "model"],
        "files": written(before, snapshot(config)),
    }


def run_class(case_class):
    """Runs one unittest.TestCase class and prints its report. True when every case passed."""
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(case_class)
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()
