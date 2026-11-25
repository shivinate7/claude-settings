"""Per-case test times: the one recording home (decision per-case-times).

sitecustomize.py arms a process at its start when env CASE_TIMES=1 and RUNNER_TEMP is set. record() reads that
latch, never the env, so a process that drops CASE_TIMES from its env still records. Rows wait in memory and
go to RUNNER_TEMP/case-times/GITHUB_JOB.jsonl once, at exit, in one append. A process that records nothing
writes no file.

A row has the keys suite, group, case, s, fixture_s and outcome (pass, fail or skip). `s` is the case's own
seconds and `fixture_s` the seconds its fixtures took, apart from it. unittest rows have group equal to suite:
a test method is one row, timed from its start to its stop. Its setUp and tearDown seconds are its fixture_s, and for
an IsolatedAsyncioTestCase so are its asyncSetUp and asyncTearDown seconds. `s` is the rest. A test method's subTests
are one row.

The clock is time.perf_counter, read through the time module at each call, so a test can patch it.

The suite name is the file's path relative to the cwd latched at arm time, so a test that removes its cwd or chdirs
without restoring it changes neither the name nor the run.
"""
__unittest = True  # unittest hides frames of modules that set this: an armed setUp error then reads as an unarmed one
import atexit
import json
import os
import sys
import time

_LATCH = {"path": None, "cwd": None}
_ROWS = []
OUTCOMES = ("pass", "fail", "skip")


def arm(path):
    """Latch the job file this process appends to, and the cwd its suite names are relative to. The exit flush is
    registered once."""
    if _LATCH["path"] is None:
        atexit.register(_flush)
    _LATCH["path"] = path
    try:
        _LATCH["cwd"] = os.getcwd()
    except OSError:  # the process started in a folder that is already gone: names stay absolute
        _LATCH["cwd"] = None


def armed():
    return _LATCH["path"] is not None


def record(suite, group, case, s, fixture_s, outcome):
    """Keep one case's row. Does nothing in an unarmed process."""
    if not armed():
        return
    if outcome not in OUTCOMES:
        raise ValueError("case_times: outcome %r is not one of %s" % (outcome, OUTCOMES))
    _ROWS.append({"suite": suite, "group": group, "case": case,
                  "s": round(float(s), 6), "fixture_s": round(float(fixture_s), 6), "outcome": outcome})


def _flush():
    left = [_case_of(frame["test"]) for frame in _LEFT + _OPEN]  # a frame that never stopped is named here too
    if left:
        sys.stderr.write("case_times: left open and dropped, no row kept: %s\n" % ", ".join(left))
    if not _ROWS:
        return
    path = _LATCH["path"]
    data = "".join(json.dumps(row, sort_keys=True) + "\n" for row in _ROWS).encode("utf-8")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            while data:  # one write for a regular file; the loop only covers a short write
                data = data[os.write(fd, data):]
        finally:
            os.close(fd)
    except OSError as error:
        sys.stderr.write("case_times: could not append %s: %s\n" % (path, error))


def _import_failure_suite(test):
    """The file of the module the loader could not import, when the case's id names a module whose file is under the
    latched cwd. Else the literal import-failure. The loader's own file is never a suite."""
    name = getattr(test, "_testMethodName", None) or ""
    base = _LATCH["cwd"]
    if base is not None and all(part.isidentifier() for part in name.split(".")):
        path = name.replace(".", "/") + ".py"
        if os.path.isfile(os.path.join(base, path)):
            return path
    return "import-failure"


def _suite_of(test):
    """The test file's path relative to the cwd latched at arm time, with forward slashes. It never reads the live
    cwd, which a test may have removed or moved."""
    if type(test).__name__ == "_FailedTest" and type(test).__module__ == "unittest.loader":
        return _import_failure_suite(test)
    module = sys.modules.get(type(test).__module__)
    path = getattr(module, "__file__", None) or type(test).__module__
    base = _LATCH["cwd"]
    if base is None:
        return path.replace(os.sep, "/")
    path = os.path.normpath(os.path.join(base, path))  # a path already absolute is kept as it is
    try:
        path = os.path.relpath(path, base)
    except ValueError:  # another drive on Windows: keep the absolute path
        pass
    return path.replace(os.sep, "/")


def _case_of(test):
    method = getattr(test, "_testMethodName", None)
    if method is None:
        return test.id()
    return "%s.%s" % (type(test).__qualname__, method)


def _tally(result):
    """(failures, skips) so far in a result. A failed subTest lands in failures or errors."""
    return len(result.failures) + len(result.errors) + len(result.unexpectedSuccesses), len(result.skipped)


_OPEN = []  # a frame per case started and not yet stopped in this process, innermost last
_LEFT = []  # frames a case dropped when it stopped above them: the flush names them
_FIXTURE_CALLS = ("_callSetUp", "_callTearDown")


def _close(test, result):
    """Pop the open frame of this test on this result. The frames above it were opened after it and never stopped:
    they are dropped and returned with it. (None, []) when no frame holds the test on the result."""
    for index in range(len(_OPEN) - 1, -1, -1):
        frame = _OPEN[index]
        if frame["test"] is test and frame["result"] is result:
            left_open = _OPEN[index + 1:]
            del _OPEN[index:]
            return frame, left_open
    return None, []


def patch_result(cls):
    """Wrap a unittest TestResult so each test method gets one row, from its start to its stop. The outcome
    reads the result's own lists: a failure, an error or an unexpected success is fail, a skip is skip.

    A case that starts inside another case keeps no row once the outer case stops: the outer row holds its time. So
    each stop drops the rows kept since its own start, before it keeps its own row. A frame that a case never stops
    keeps no row, and the rows around it are kept. A frame still open at exit, or dropped by a case that stopped
    above it, is named in one stderr line at flush."""
    if getattr(cls, "_case_times_patched", False):
        return
    real_start, real_stop = cls.startTest, cls.stopTest

    def startTest(self, test):
        frame = {"test": test, "result": self, "base": _tally(self), "t0": time.perf_counter(), "fixture": 0.0,
                 "mark": len(_ROWS)}
        real_start(self, test)
        _OPEN.append(frame)

    def stopTest(self, test):
        frame, left_open = _close(test, self)
        _LEFT.extend(left_open)
        try:
            if frame is not None:
                took = time.perf_counter() - frame["t0"]
                failed, skipped = _tally(frame["result"])
                base_failed, base_skipped = frame["base"]
                outcome = "fail" if failed > base_failed else "skip" if skipped > base_skipped else "pass"
                fixture = frame["fixture"]
                record(_suite_of(test), _suite_of(test), _case_of(test), took - fixture, fixture, outcome)
                del _ROWS[frame["mark"]:-1]  # record put this row last: the rows kept since its start are inside it
        except Exception as error:  # a row that cannot be kept must never abort the run or the result
            sys.stderr.write("case_times: no row for %s: %s\n" % (test.id(), error))
        return real_stop(self, test)

    cls.startTest = startTest
    cls.stopTest = stopTest
    cls._case_times_patched = True


def _add_fixture(test, seconds):
    """Add seconds to the fixture time of this test's open frame, so they stay out of its own time."""
    for frame in reversed(_OPEN):
        if frame["test"] is test:
            frame["fixture"] += seconds
            return


def _timed(real):
    """Wrap one fixture call so its seconds go to the test's fixture_s, not s. The wrapper only times the call: its
    result and any exception pass through unchanged."""
    def call(self):
        t0 = time.perf_counter()
        try:
            return real(self)
        finally:
            _add_fixture(self, time.perf_counter() - t0)
    return call


def _wrap_fixture_calls(cls):
    """Wrap each fixture call cls defines itself, once per class, and leave the other one as it is. A class that only
    inherits a call is wrapped where its base defines it. A call that no class in the MRO defines (a Python that
    renamed it), or that is defined but cannot be read, writes one stderr line naming it. The call that exists is
    still wrapped."""
    if cls.__dict__.get("_case_times_fixture_patched"):
        return
    cls._case_times_fixture_patched = True
    for name in _FIXTURE_CALLS:
        if not any(name in klass.__dict__ for klass in cls.__mro__):
            sys.stderr.write("case_times: fixture time not kept for %s: %s is not defined\n" % (cls.__name__, name))
            continue
        if name not in cls.__dict__:
            continue  # inherited: the base that defines it wraps it
        try:
            real = getattr(cls, name)
        except AttributeError as error:
            sys.stderr.write("case_times: fixture time not kept for %s: %s\n" % (cls.__name__, error))
            continue
        setattr(cls, name, _timed(real))


def patch_case():
    """Wrap TestCase's setUp and tearDown calls so their seconds go to fixture_s, not s. Called when unittest.result
    loads."""
    import unittest.case
    _wrap_fixture_calls(unittest.case.TestCase)


def patch_async_case(module):
    """Wrap IsolatedAsyncioTestCase's own fixture calls, which also run asyncSetUp and asyncTearDown. Called when
    unittest.async_case loads, so the arm never imports asyncio."""
    _wrap_fixture_calls(module.IsolatedAsyncioTestCase)
