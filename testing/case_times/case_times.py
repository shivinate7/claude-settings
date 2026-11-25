"""Per-case test times: the one recording home (decision per-case-times).

sitecustomize.py arms a process at its start when env CASE_TIMES=1 and RUNNER_TEMP is set. record() reads that
latch, never the env, so a process that drops CASE_TIMES from its env still records. Rows wait in memory and
go to RUNNER_TEMP/case-times/GITHUB_JOB.jsonl once, at exit, in one append. A process that records nothing
writes no file.

A row has the keys suite, group, case, s, fixture_s and outcome (pass, fail or skip). `s` is the case's own
seconds and `fixture_s` the seconds its fixtures took, apart from it. unittest rows have group equal to suite,
and a test method's subTests are one row, timed from the method's start to its stop.

The clock is time.perf_counter, read through the time module at each call, so a test can patch it.

The suite name is the file's path relative to the cwd latched at arm time, so a test that removes its cwd or chdirs
without restoring it changes neither the name nor the run.
"""
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


def _suite_of(test):
    """The test file's path relative to the cwd latched at arm time, with forward slashes. It never reads the live
    cwd, which a test may have removed or moved."""
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


def patch_result(cls):
    """Wrap a unittest TestResult so each test method gets one row, from its start to its stop. The outcome
    reads the result's own lists: a failure, an error or an unexpected success is fail, a skip is skip."""
    if getattr(cls, "_case_times_patched", False):
        return
    real_start, real_stop = cls.startTest, cls.stopTest

    def startTest(self, test):
        self._case_times_base = _tally(self)
        self._case_times_t0 = time.perf_counter()
        return real_start(self, test)

    def stopTest(self, test):
        try:
            took = time.perf_counter() - getattr(self, "_case_times_t0", time.perf_counter())
            failed, skipped = _tally(self)
            base_failed, base_skipped = getattr(self, "_case_times_base", (failed, skipped))
            outcome = "fail" if failed > base_failed else "skip" if skipped > base_skipped else "pass"
            record(_suite_of(test), _suite_of(test), _case_of(test), took, 0.0, outcome)
        except Exception as error:  # a row that cannot be kept must never abort the run or the result
            sys.stderr.write("case_times: no row for %s: %s\n" % (test.id(), error))
        return real_stop(self, test)

    cls.startTest = startTest
    cls.stopTest = stopTest
    cls._case_times_patched = True
