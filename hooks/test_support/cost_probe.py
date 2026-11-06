"""Counters for the cost tests (rule outcomes-mechanize-rules; plan align-watchers, section 1, rule 5).

A cost record names the child processes a mechanism starts, the files it writes and how often it
runs. Its test runs the mechanism in process, reads these counts and asserts the record's numbers.
This module is the one home of each counter. A case calls it, and no case keeps its own copy.

  children()          context manager: lists the argv of every child process started in its block.
                      subprocess.run and the _nowindow wrappers all start children through Popen,
                      so they are counted too.
  StubRun             stands in for _nowindow.run: records each call, then returns or raises.
  CountingModel       stands in for a caller's model call: records each prompt, returns one answer.
  snapshot, written   the files a run created or changed under a folder.
  leftovers           every file and folder under a folder, for "nothing is left behind".
  FakeClock           the module `time`: it moves only when the code sleeps, and fails at a cap.
  settings_timeout    the `timeout` of the settings.json hook row whose command holds a name.
  run_class           runs one unittest.TestCase class and reports whether every case passed.
  run_folder          this test run's folder under the repo's temp root (test-temp-standard).
"""
import contextlib
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_temp  # noqa: E402  the run folder, one temp root per repo (lint/_test_temp.py)


@contextlib.contextmanager
def children():
    """Yields a list that gets one argv list per child process started while the block runs."""
    started = []
    real = subprocess.Popen

    class Counted(real):
        def __init__(self, args, *rest, **kwargs):
            argv = args if isinstance(args, (list, tuple)) else [args]
            started.append([str(part) for part in argv])
            real.__init__(self, args, *rest, **kwargs)

    subprocess.Popen = Counted
    try:
        yield started
    finally:
        subprocess.Popen = real


def names(argvs):
    """The program name of each argv, without its folder: 'claude', 'git', ..."""
    return [os.path.basename(argv[0]).lower() for argv in argvs]


class StubRun(object):
    """Stands in for _nowindow.run. Records each call's argv and kwargs, then returns `result`, or raises `error`."""

    def __init__(self, result=None, error=None):
        self.calls, self.result, self.error = [], result, error

    def __call__(self, argv, *args, **kwargs):
        self.calls.append((list(argv), kwargs))
        if self.error is not None:
            raise self.error
        return self.result

    def argvs(self):
        return [argv for argv, _ in self.calls]


class CountingModel(object):
    """Stands in for a caller's model call (decision_watch.invoke_model). Records each prompt, returns `answer`."""

    def __init__(self, answer=({"ok": True}, None)):
        self.answer, self.prompts = answer, []

    def __call__(self, prompt, *args, **kwargs):
        self.prompts.append(prompt)
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


def run_class(case_class):
    """Runs one unittest.TestCase class and prints its report. True when every case passed."""
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(case_class)
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


def run_folder():
    """This test run's folder under the repo's temp root. The test class removes it in tearDownClass."""
    return _test_temp.run_folder()
