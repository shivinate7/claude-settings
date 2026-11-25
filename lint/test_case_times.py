#!/usr/bin/env python3
"""Per-case test times: the recording home (testing/case_times/) and the rows it writes.

The home is on when env CASE_TIMES=1 and testing/case_times is on PYTHONPATH. Every case runs the home in a
child process, so each failure is an assert on rows or output, never an import error here.

Row contract (the builder's target): one JSON object per line, with keys suite, group, case, s, fixture_s, outcome.
suite is the test file's path relative to the process's cwd; unittest rows have group equal to suite; case is
"Class.test_method"; outcome is pass, fail or skip; a subTest set gives one row for its test method. The file is
RUNNER_TEMP/case-times/GITHUB_JOB.jsonl, appended at exit, and only when a row was recorded.

The clock: runner.py swaps the time module's sleep and clock for cost_probe.FakeClock, so each case's time is an
exact synthetic number. No assert reads a real elapsed time (decision test-practices, rule P5), and no case sleeps.

Each child gets its env from child_env(): the caller's CASE_TIMES, PYTHONPATH, RUNNER_TEMP and GITHUB_JOB are
never inherited, so these cases never write to the real job file.
"""
import json
import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
HOME = os.path.join(REPO, "testing", "case_times")
SITE_HOME = os.path.realpath(os.path.join(HOME, "sitecustomize.py"))
HOOKS = os.path.join(REPO, "hooks")
PROBE = os.path.join(REPO, "testing")
sys.path.insert(0, HERE)
sys.path.insert(0, PROBE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import cost_probe  # noqa: E402  children(), leftovers(), FakeClock: the one home of each counter

JOB = "fixture-job"
RUN_TIMEOUT = 120  # a hang guard, well above any run here
DROPPED = ("CASE_TIMES", "PYTHONPATH", "RUNNER_TEMP", "GITHUB_JOB")
RUN = None

RUNNER = r'''
import os
import sys
import time

site = sys.modules.get("sitecustomize")
site_file = getattr(site, "__file__", None) if site is not None else None
print("SITE_FILE", os.path.realpath(site_file) if site_file else "none")
if "absent" in sys.argv[2:] or "deleted" in sys.argv[2:]:  # TestCase._callSetUp unreadable ("absent") or gone ("deleted"), as a Python that renamed it would have it
    import importlib.machinery

    class Absent(object):
        def __init__(self, function):
            self.function = function

        def __get__(self, obj, owner=None):
            if obj is None:
                raise AttributeError("type object 'TestCase' has no attribute '_callSetUp'")
            return self.function.__get__(obj, owner)

    class Finder(object):
        def find_spec(self, fullname, path=None, target=None):
            if fullname != "unittest.case":
                return None
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec is None or spec.loader is None:
                return None
            load = spec.loader.exec_module

            def exec_module(module):
                load(module)
                if "deleted" in sys.argv[2:]:
                    del module.TestCase._callSetUp
                else:
                    module.TestCase._callSetUp = Absent(module.TestCase._callSetUp)

            spec.loader.exec_module = exec_module
            return spec

    sys.meta_path.insert(0, Finder())  # before the arm's hook, so the absence is in place when the arm reads it
import unittest
sys.path.insert(0, os.environ["PROBE_DIR"])
import cost_probe  # noqa: E402

clock = cost_probe.FakeClock(start=0.0, cap=100000)
time.sleep = clock.sleep
time.monotonic = clock.monotonic
time.perf_counter = clock.monotonic
time.time = clock.time
sys.path.insert(0, os.getcwd())
suite = unittest.defaultTestLoader.loadTestsFromName(sys.argv[1])
quiet = open(os.devnull, "w")
if "count" in sys.argv[2:]:
    with cost_probe.children() as log:
        result = unittest.TextTestRunner(stream=quiet, verbosity=0).run(suite)
    print("CHILDREN", len(log.argvs))
else:
    result = unittest.TextTestRunner(stream=quiet, verbosity=0).run(suite)
if "report" in sys.argv[2:]:
    print("RESULT ran=%d failures=%d errors=%d skipped=%d" % (result.testsRun, len(result.failures), len(result.errors), len(result.skipped)))
if "tracebacks" in sys.argv[2:]:
    for test, text in result.errors:
        print("TRACEBACK-BEGIN")
        print(text, end="")
        print("TRACEBACK-END")
'''

RECORDS = '''import os
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


class Fixture(unittest.TestCase):
    def test_pass(self):
        time.sleep(0.5)

    def test_fail(self):
        time.sleep(0.25)
        self.assertEqual(1, 2, "fixture fail")

    def test_skip(self):
        self.skipTest("fixture skip")

    def test_subtests(self):
        for i in range(2):
            with self.subTest(i=i):
                time.sleep(0.125)

    def test_child(self):
        subprocess.run([sys.executable, os.path.join(HERE, "fixture_child.py")], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
'''

CHILD = '''import unittest


class Child(unittest.TestCase):
    def test_child_case(self):
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
'''

PLAIN = '''import time
import unittest


class Plain(unittest.TestCase):
    def test_one(self):
        time.sleep(0.5)
'''

PARENT = '''import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


class Parent(unittest.TestCase):
    def test_spawn(self):
        subprocess.run([sys.executable, os.path.join(HERE, "fixture_inner.py")], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
'''

INNER = '''import unittest


class Inner(unittest.TestCase):
    def test_inner(self):
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
'''

CONTROL_CHILD = '''import unittest


class Control(unittest.TestCase):
    def test_one(self):
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
'''

MUTANT_CHILD = CONTROL_CHILD.replace("Control", "Mutant")

# No unittest import here: the parent of a mutant run imports none, so CASE_TIMES stays in its env unless the mutant runner drops it.
MUTANT_RUNNER = '''import os
import subprocess
import sys
sys.path.insert(0, %r)
import mutate_shared
subprocess.run([sys.executable, "control_child.py"], cwd=os.getcwd(), check=True, timeout=%d)
print("CONTROL_DONE")
verdict, seconds = mutate_shared.run_suite_file(os.getcwd(), "mutant_child.py", %d)
print("MUTANT_DONE", verdict)
''' % (HOOKS, RUN_TIMEOUT, RUN_TIMEOUT)

# A process that loads the home, then imports unittest.mock, then records a row. The latch is read at startup, so the row is still written.
GUARD_LATCH = '''import os
import sys
site = sys.modules.get("sitecustomize")
print("SITE_FILE", os.path.realpath(site.__file__) if site is not None and getattr(site, "__file__", None) else "none")
import unittest.mock  # noqa: F401
print("CASE_TIMES_AFTER_MOCK", os.environ.get("CASE_TIMES", "absent"))
import case_times
case_times.record("hooks/test_guard.py", "merge", "Guard.test_latch", 0.25, 0.0, "pass")
'''

# A guard-style process that records three cases of two families, with the fixture time apart from the case time.
GUARD_ROWS = '''import os
import sys
site = sys.modules.get("sitecustomize")
print("SITE_FILE", os.path.realpath(site.__file__) if site is not None and getattr(site, "__file__", None) else "none")
import case_times
case_times.record("hooks/test_guard.py", "merge", "Guard.test_first", 0.25, 0.5, "pass")
case_times.record("hooks/test_guard.py", "merge", "Guard.test_second", 0.125, 0.0, "pass")
case_times.record("hooks/test_guard.py", "pure", "Guard.test_third", 0.5, 0.0, "fail")
'''

# A process that loads the home with no unittest import anywhere: it reports the home and records nothing.
NO_UNITTEST = '''import os
import sys
site = sys.modules.get("sitecustomize")
print("SITE_FILE", os.path.realpath(site.__file__) if site is not None and getattr(site, "__file__", None) else "none")
'''

# An unarmed child: it counts the child starts its own sitecustomize makes (a re-run under the count) and reports the file it loaded.
UNARMED_PROBE = '''import importlib
import os
import subprocess
import sys
starts = []
real = subprocess.Popen


class Counted(real):
    def __init__(self, args, *rest, **kwargs):
        starts.append(args)
        real.__init__(self, args, *rest, **kwargs)


subprocess.Popen = Counted
import sitecustomize  # noqa: E402
print("SITE_FILE", os.path.realpath(sitecustomize.__file__))
importlib.reload(sitecustomize)
print("CHILDREN", len(starts))
'''


# The first case's row cannot be kept: record raises once, then the real record is back for the next case.
ROW_BROKEN = '''import unittest

import case_times


class Broken(unittest.TestCase):
    def test_a_row_cannot_be_kept(self):
        real = case_times.record

        def broken(*args, **kwargs):
            case_times.record = real
            raise OSError("disk full")

        case_times.record = broken

    def test_b_plain(self):
        self.assertTrue(True)

    def test_c_plain(self):
        self.assertTrue(True)
'''

# The first case removes its own cwd. Each case must still run and record, as an unarmed run does.
CWD_GONE = '''import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


class Gone(unittest.TestCase):
    def test_a_removes_its_cwd(self):
        here = os.path.join(HERE, "gone")
        os.makedirs(here, exist_ok=True)
        os.chdir(here)
        os.rmdir(here)

    def test_b_plain(self):
        self.assertTrue(True)

    def test_c_plain(self):
        self.assertTrue(True)
'''

# A test chdirs and does not restore the cwd. Its file's rows must still share one suite name.
CHDIR_AWAY = '''import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


class Away(unittest.TestCase):
    def test_a_plain(self):
        self.assertTrue(True)

    def test_b_chdir_no_restore(self):
        elsewhere = os.path.join(HERE, "elsewhere")
        os.makedirs(elsewhere, exist_ok=True)
        os.chdir(elsewhere)

    def test_c_plain(self):
        self.assertTrue(True)
'''

# Two outer cases each run an inner case in-process, on a fresh result, as hooks/test_auto_mode_allow.py does. The inner
# case is part of the outer case's time, so it keeps no row of its own; the outer rows hold the whole time.
NESTED = '''import time
import unittest


class Inner(unittest.TestCase):
    def test_inner_sleeps(self):
        time.sleep(0.25)


class Outer(unittest.TestCase):
    def test_a_runs_inner(self):
        result = unittest.TestResult()
        Inner("test_inner_sleeps").run(result)
        time.sleep(0.5)

    def test_b_runs_inner(self):
        result = unittest.TestResult()
        Inner("test_inner_sleeps").run(result)
'''


# A test module whose import fails on a module that is not there: the loader gives its failure a _FailedTest case.
IMPORT_FAILS = '''import fixture_missing_dependency_for_case_times  # noqa: F401  the import fails on purpose
import unittest


class Never(unittest.TestCase):
    def test_never_runs(self):
        self.assertTrue(True)
'''


# A case with a setUp and a tearDown: their seconds are fixture time, apart from the case's own seconds.
TIMED = '''import time
import unittest


class Timed(unittest.TestCase):
    def setUp(self):
        time.sleep(0.5)

    def tearDown(self):
        time.sleep(0.125)

    def test_case(self):
        time.sleep(0.25)
'''


# A case that starts a frame on a result of its own and never stops it, so the frame is still open when the run ends.
LEAK = '''import unittest


class Leak(unittest.TestCase):
    def test_a_leaves_frame_open(self):
        unittest.TestResult().startTest(self)

    def test_b_plain(self):
        self.assertTrue(True)

    def test_c_plain(self):
        self.assertTrue(True)
'''

# A frame opened at module level, outside any case, that no stop ever closes. The cases around it keep their rows.
LEAK_MODULE = '''import unittest


class Seed(unittest.TestCase):
    def test_a(self):
        pass


unittest.TestResult().startTest(Seed("test_a"))


class Module(unittest.TestCase):
    def test_b_plain(self):
        self.assertTrue(True)

    def test_c_plain(self):
        self.assertTrue(True)
'''

# A case that starts a second frame for itself on the runner's own result and never stops it. The runner's stop closes
# that second frame, so the runner's first frame stays open. The case keeps its row, and so do the cases after it.
LEAK_OWN = '''import unittest


class Own(unittest.TestCase):
    def run(self, result=None):
        Own.runner_result = result
        return super().run(result)

    def test_a_opens_a_frame_on_the_runner_result(self):
        Own.runner_result.startTest(self)

    def test_b_plain(self):
        self.assertTrue(True)

    def test_c_plain(self):
        self.assertTrue(True)
'''

# An async case: its asyncSetUp seconds are fixture time, apart from the case's own seconds.
ASYNC = '''import time
import unittest


class Async(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        time.sleep(0.5)

    async def test_case(self):
        time.sleep(0.25)
'''

# A setUp that raises. Its traceback text must be the same armed and unarmed.
SETUP_ERROR = '''import unittest


class SetupError(unittest.TestCase):
    def setUp(self):
        raise RuntimeError("setup broke")

    def test_case(self):
        self.assertTrue(True)
'''

# A fresh process that imports unittest, then reports whether asyncio or unittest.async_case is loaded.
IMPORTS_PROBE = '''import os
import sys
site = sys.modules.get("sitecustomize")
print("SITE_FILE", os.path.realpath(site.__file__) if site is not None and getattr(site, "__file__", None) else "none")
import unittest  # noqa: F401
print("LOADED asyncio=%s async_case=%s" % ("asyncio" in sys.modules, "unittest.async_case" in sys.modules))
'''


def setUpModule():
    global RUN
    RUN = _test_temp.run_folder()
    with open(os.path.join(RUN, "runner.py"), "w", encoding="utf-8") as f:
        f.write(RUNNER)


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)


def case_folder(test):
    folder = os.path.join(RUN, test.id().replace(".", "_"))
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    return folder


def write(folder, name, text):
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        f.write(text)


def child_env(folder, armed=True, pythonpath=HOME, extra=None):
    env = {k: v for k, v in os.environ.items() if k not in DROPPED}
    env["PYTHONPATH"] = pythonpath
    env["RUNNER_TEMP"] = folder
    env["GITHUB_JOB"] = JOB
    env["PROBE_DIR"] = PROBE
    if armed:
        env["CASE_TIMES"] = "1"
    env.update(extra or {})
    return env


def run_py(folder, argv, armed=True, pythonpath=HOME, extra=None):
    return subprocess.run([sys.executable] + argv, cwd=folder, env=child_env(folder, armed, pythonpath, extra),
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=RUN_TIMEOUT)


def run_module(folder, module, armed=True, count=False, extra=None, pythonpath=HOME, report=False, flags=()):
    options = (["count"] if count else []) + (["report"] if report else []) + list(flags)
    argv = [os.path.join(RUN, "runner.py"), module] + options
    return run_py(folder, argv, armed=armed, pythonpath=pythonpath, extra=extra)


def result_line(result):
    for line in result.stdout.splitlines():
        if line.startswith("RESULT "):
            return line
    return None


def site_file(result):
    for line in result.stdout.splitlines():
        if line.startswith("SITE_FILE "):
            return line[len("SITE_FILE "):]
    return None


def traceback_text(result):
    """The text between a traceback runner's markers, or None when it printed none."""
    begin = result.stdout.find("TRACEBACK-BEGIN\n")
    end = result.stdout.find("TRACEBACK-END\n")
    if begin < 0 or end < begin:
        return None
    return result.stdout[begin + len("TRACEBACK-BEGIN\n"):end]


def scope_ok(test, result):
    test.assertEqual(site_file(result), SITE_HOME,
                     "the case_times sitecustomize did not load in this child (SITE_FILE %r); stderr tail: %s"
                     % (site_file(result), result.stderr[-300:]))


def job_file(folder):
    return os.path.join(folder, "case-times", JOB + ".jsonl")


def rows_of(folder):
    path = job_file(folder)
    if not os.path.exists(path):
        return None
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    raise AssertionError("the job row file holds a line that is not JSON: %r" % line[:120])
    return rows


def rows_by_case(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row.get("case"), []).append(row)
    return grouped


def assert_records_rows(test, folder):
    rows = rows_of(folder)
    test.assertIsNotNone(rows, "no case-times file was written under %s" % folder)
    got = {case: rs for case, rs in rows_by_case(rows).items() if case and case.startswith("Fixture.")}
    expected = {
        "Fixture.test_pass": ("pass", 0.5),
        "Fixture.test_fail": ("fail", 0.25),
        "Fixture.test_skip": ("skip", 0.0),
        "Fixture.test_subtests": ("pass", 0.25),
        "Fixture.test_child": ("pass", 0.0),
    }
    test.assertEqual(sorted(got), sorted(expected),
                     "fixture case rows differ: want %s, got %s" % (sorted(expected), sorted(got)))
    for case, (outcome, seconds) in expected.items():
        test.assertEqual(len(got[case]), 1, "%s has %d rows, want one" % (case, len(got[case])))
        row = got[case][0]
        test.assertEqual(row.get("outcome"), outcome, "%s outcome is %r, want %r" % (case, row.get("outcome"), outcome))
        test.assertEqual(row.get("s"), seconds, "%s s is %r, want the synthetic %r" % (case, row.get("s"), seconds))
        test.assertEqual(row.get("suite"), "fixture_records.py", "%s suite is %r" % (case, row.get("suite")))
        test.assertEqual(row.get("group"), "fixture_records.py", "%s group is %r" % (case, row.get("group")))
        test.assertIn("fixture_s", row, "%s row has no fixture_s" % case)


class Records(unittest.TestCase):
    def test_one_row_per_case_with_outcome(self):
        folder = case_folder(self)
        write(folder, "fixture_records.py", RECORDS)
        write(folder, "fixture_child.py", CHILD)
        result = run_module(folder, "fixture_records")
        scope_ok(self, result)
        assert_records_rows(self, folder)

    def test_wrapped_by_verdict_still_records(self):
        folder = case_folder(self)
        write(folder, "fixture_records.py", RECORDS)
        write(folder, "fixture_child.py", CHILD)
        log = os.path.join(folder, "verdict.log")
        result = subprocess.run([sys.executable, os.path.join(REPO, "bin", "verdict"), sys.executable,
                                 os.path.join(RUN, "runner.py"), "fixture_records"],
                                cwd=folder, env=child_env(folder, extra={"VERDICT_LOG": log}),
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=RUN_TIMEOUT)
        self.assertTrue(os.path.exists(log), "bin/verdict wrote no log: %s" % result.stderr[-300:])
        with open(log, encoding="utf-8", errors="replace") as f:
            wrapped = f.read()
        self.assertIn("SITE_FILE %s" % SITE_HOME, wrapped,
                      "the command under bin/verdict did not load the case_times sitecustomize")
        assert_records_rows(self, folder)


class Children(unittest.TestCase):
    def test_suite_child_writes_no_row(self):
        folder = case_folder(self)
        write(folder, "fixture_parent.py", PARENT)
        write(folder, "fixture_inner.py", INNER)
        result = run_module(folder, "fixture_parent")
        scope_ok(self, result)
        rows = rows_of(folder)
        self.assertIsNotNone(rows, "the parent suite wrote no case-times file")
        parent = rows_by_case(rows).get("Parent.test_spawn", [])
        self.assertEqual(len(parent), 1, "the parent case has %d rows, want one" % len(parent))
        inner = [row for row in rows if (row.get("case") or "").startswith("Inner.")
                 or row.get("suite") == "fixture_inner.py"]
        self.assertEqual(inner, [], "the child suite wrote rows: %s" % inner)

    def test_mutation_child_writes_no_row(self):
        folder = case_folder(self)
        write(folder, "control_child.py", CONTROL_CHILD)
        write(folder, "mutant_child.py", MUTANT_CHILD)
        write(folder, "mutant_runner.py", MUTANT_RUNNER)
        # The runner imports no unittest, so CASE_TIMES reaches every child unless mutate_shared drops it.
        result = run_py(folder, ["mutant_runner.py"])
        rows = rows_of(folder)
        self.assertIsNotNone(rows, "the control child, run with CASE_TIMES in its env, wrote no case-times file; "
                                   "runner stderr tail: %s" % result.stderr[-300:])
        control = rows_by_case(rows).get("Control.test_one", [])
        self.assertEqual(len(control), 1, "the control child has %d rows, want one" % len(control))
        self.assertIn("MUTANT_DONE", result.stdout,
                      "the mutant child never ran through mutate_shared.run_suite_file; stderr tail: %s"
                      % result.stderr[-300:])
        mutant = [row for row in rows if (row.get("case") or "").startswith("Mutant.")]
        self.assertEqual(mutant, [], "the mutant child wrote rows: %s" % mutant)


class Unarmed(unittest.TestCase):
    def test_no_env_writes_no_file(self):
        folder = case_folder(self)
        write(folder, "fixture_records.py", RECORDS)
        write(folder, "fixture_child.py", CHILD)
        result = run_module(folder, "fixture_records", armed=False)
        scope_ok(self, result)
        self.assertEqual(cost_probe.leftovers(os.path.join(folder, "case-times")), [],
                         "an unarmed run wrote a case-times file")

    def test_no_unittest_import_writes_no_file(self):
        folder = case_folder(self)
        write(folder, "no_unittest.py", NO_UNITTEST)
        result = run_py(folder, ["no_unittest.py"])
        scope_ok(self, result)
        self.assertEqual(cost_probe.leftovers(os.path.join(folder, "case-times")), [],
                         "a process that imports no unittest wrote a case-times file")


class Chain(unittest.TestCase):
    def test_next_sitecustomize_still_runs(self):
        folder = case_folder(self)
        write(folder, "fixture_plain.py", PLAIN)
        nxt = os.path.join(folder, "next")
        os.makedirs(nxt)
        write(nxt, "sitecustomize.py",
              'import os\nwith open(os.environ["CHAIN_MARK"], "w", encoding="utf-8") as f:\n'
              '    f.write("next ran")\n')
        mark = os.path.join(folder, "chain.mark")
        result = run_module(folder, "fixture_plain", pythonpath=HOME + os.pathsep + nxt,
                            extra={"CHAIN_MARK": mark})
        scope_ok(self, result)
        self.assertIsNotNone(rows_of(folder), "the case_times sitecustomize recorded no rows, so the chain is unproven")
        self.assertTrue(os.path.exists(mark), "the sitecustomize after case_times on PYTHONPATH did not run")


class TwoHomes(unittest.TestCase):
    def test_two_copies_of_the_home_chain_once(self):
        folder = case_folder(self)
        write(folder, "fixture_plain.py", PLAIN)
        # Two distinct copies of the home on PYTHONPATH, then a real sitecustomize after them. The copies are the
        # case's input: it needs two files, and only a copy makes the second one.
        copies = []
        for name in ("home_a", "home_b"):
            copy = os.path.join(folder, name)
            os.makedirs(copy)
            for file_name in ("sitecustomize.py", "case_times.py"):
                shutil.copy(os.path.join(HOME, file_name), copy)
            copies.append(copy)
        nxt = os.path.join(folder, "next")
        os.makedirs(nxt)
        write(nxt, "sitecustomize.py",
              'import os\nwith open(os.environ["CHAIN_MARK"], "w", encoding="utf-8") as f:\n'
              '    f.write("next ran")\n')
        pythonpath = os.pathsep.join(copies + [nxt])
        mark = os.path.join(folder, "chain.mark")
        unarmed = run_module(folder, "fixture_plain", armed=False, report=True, pythonpath=pythonpath,
                             extra={"CHAIN_MARK": mark})
        self.assertEqual(result_line(unarmed), "RESULT ran=1 failures=0 errors=0 skipped=0",
                         "two copies of the home on PYTHONPATH: the unarmed child did not run its one case; "
                         "exit %d, stderr tail: %s" % (unarmed.returncode, unarmed.stderr[-300:]))
        self.assertTrue(os.path.exists(mark), "two copies of the home on PYTHONPATH: the chain did not reach the "
                                              "sitecustomize after them (unarmed); stderr tail: %s"
                        % unarmed.stderr[-300:])
        mark_armed = os.path.join(folder, "chain_armed.mark")
        armed = run_module(folder, "fixture_plain", report=True, pythonpath=pythonpath,
                           extra={"CHAIN_MARK": mark_armed})
        self.assertEqual(site_file(armed), os.path.realpath(os.path.join(copies[0], "sitecustomize.py")),
                         "two copies of the home on PYTHONPATH: the first copy did not load (SITE_FILE %r); "
                         "stderr tail: %s" % (site_file(armed), armed.stderr[-300:]))
        self.assertEqual(armed.returncode, unarmed.returncode, "the armed run exited %d, the unarmed %d"
                         % (armed.returncode, unarmed.returncode))
        self.assertEqual(result_line(armed), result_line(unarmed),
                         "the armed run's outcome differs from the unarmed run's")
        self.assertIsNotNone(rows_of(folder), "the armed run wrote no case-times file")
        self.assertTrue(os.path.exists(mark_armed), "two copies of the home on PYTHONPATH: the chain did not reach "
                                                    "the sitecustomize after them (armed); stderr tail: %s"
                        % armed.stderr[-300:])


class Cost(unittest.TestCase):
    def test_no_child_and_one_file(self):
        folder = case_folder(self)
        write(folder, "fixture_plain.py", PLAIN)
        result = run_module(folder, "fixture_plain", count=True)
        scope_ok(self, result)
        self.assertIsNotNone(rows_of(folder), "the armed run wrote no case-times file")
        children = [line for line in result.stdout.splitlines() if line.startswith("CHILDREN ")]
        self.assertEqual(children, ["CHILDREN 0"], "the armed run started child processes: %s" % children)
        self.assertEqual(cost_probe.leftovers(os.path.join(folder, "case-times")), [JOB + ".jsonl"],
                         "the armed run should leave exactly one job file")

    def test_unarmed_child_one_import_no_file(self):
        folder = case_folder(self)
        result = run_py(folder, ["-X", "importtime", "-c", UNARMED_PROBE], armed=False)
        self.assertEqual(site_file(result), SITE_HOME,
                         "the unarmed child did not load the case_times sitecustomize; stderr tail: %s"
                         % result.stderr[-300:])
        imports = [line for line in result.stderr.splitlines() if line.rstrip().endswith("sitecustomize")]
        self.assertEqual(len(imports), 1, "the unarmed child imported sitecustomize %d times, want one" % len(imports))
        children = [line for line in result.stdout.splitlines() if line.startswith("CHILDREN ")]
        self.assertEqual(children, ["CHILDREN 0"], "the unarmed child started child processes: %s" % children)
        self.assertEqual(cost_probe.leftovers(os.path.join(folder, "case-times")), [],
                         "the unarmed child wrote a case-times file")


class GuardRows(unittest.TestCase):
    def test_one_row_per_case_fixture_netted(self):
        folder = case_folder(self)
        result = run_py(folder, ["-c", GUARD_ROWS])
        scope_ok(self, result)
        rows = rows_of(folder)
        self.assertIsNotNone(rows, "the guard-style process wrote no case-times file")
        want = [
            ("hooks/test_guard.py", "merge", "Guard.test_first", 0.25, 0.5, "pass"),
            ("hooks/test_guard.py", "merge", "Guard.test_second", 0.125, 0.0, "pass"),
            ("hooks/test_guard.py", "pure", "Guard.test_third", 0.5, 0.0, "fail"),
        ]
        got = sorted((r.get("suite"), r.get("group"), r.get("case"), r.get("s"), r.get("fixture_s"), r.get("outcome"))
                     for r in rows)
        self.assertEqual(got, sorted(want), "guard rows differ: want %s, got %s" % (sorted(want), got))

    def test_mock_import_keeps_recording(self):
        folder = case_folder(self)
        result = run_py(folder, ["-c", GUARD_LATCH])
        scope_ok(self, result)
        self.assertIn("CASE_TIMES_AFTER_MOCK absent", result.stdout,
                      "the unittest.mock import did not remove CASE_TIMES from the env; the hook never ran")
        rows = rows_of(folder)
        self.assertIsNotNone(rows, "a process that imports unittest.mock then records wrote no row")
        latch = [r for r in rows if r.get("case") == "Guard.test_latch"]
        self.assertEqual(len(latch), 1, "Guard.test_latch has %d rows, want one" % len(latch))


class CwdGone(unittest.TestCase):
    def test_removed_cwd_runs_every_case_as_unarmed_does(self):
        folder = case_folder(self)
        write(folder, "fixture_gone.py", CWD_GONE)
        unarmed = run_module(folder, "fixture_gone", armed=False, report=True)
        self.assertEqual(result_line(unarmed), "RESULT ran=3 failures=0 errors=0 skipped=0",
                         "the unarmed control run did not pass its three cases: %r" % unarmed.stderr[-300:])
        armed = run_module(folder, "fixture_gone", report=True)
        scope_ok(self, armed)
        self.assertEqual(armed.returncode, 0,
                         "the armed run exited %d, want 0 as the unarmed run does: a case that removed its cwd "
                         "aborted the run; stderr tail: %s" % (armed.returncode, armed.stderr[-300:]))
        self.assertEqual(result_line(armed), result_line(unarmed),
                         "the armed run's outcome differs from the unarmed run's")
        rows = rows_of(folder)
        self.assertIsNotNone(rows, "the armed run wrote no case-times file")
        cases = sorted(row.get("case") for row in rows if (row.get("case") or "").startswith("Gone."))
        self.assertEqual(cases, ["Gone.test_a_removes_its_cwd", "Gone.test_b_plain", "Gone.test_c_plain"],
                         "the armed run did not record one row per case: %s" % cases)


class CwdChdir(unittest.TestCase):
    def test_chdir_without_restore_keeps_one_suite_name(self):
        folder = case_folder(self)
        write(folder, "fixture_away.py", CHDIR_AWAY)
        result = run_module(folder, "fixture_away")
        scope_ok(self, result)
        rows = rows_of(folder)
        self.assertIsNotNone(rows, "the armed run wrote no case-times file")
        suites = sorted(set(row.get("suite") for row in rows))
        self.assertEqual(suites, ["fixture_away.py"],
                         "a test that chdired without restoring split its file's rows across suite names: %s" % suites)


class NestedRuns(unittest.TestCase):
    def test_inner_case_keeps_no_row_of_its_own(self):
        folder = case_folder(self)
        write(folder, "fixture_nested.py", NESTED)
        unarmed = run_module(folder, "fixture_nested", armed=False, report=True)
        self.assertEqual(result_line(unarmed), "RESULT ran=3 failures=0 errors=0 skipped=0",
                         "the unarmed control run did not pass its three cases: %r" % unarmed.stderr[-300:])
        armed = run_module(folder, "fixture_nested", report=True)
        scope_ok(self, armed)
        self.assertEqual(armed.returncode, 0, "the armed run exited %d, want 0: stderr tail: %s"
                         % (armed.returncode, armed.stderr[-300:]))
        self.assertEqual(result_line(armed), result_line(unarmed),
                         "the armed run's outcome differs from the unarmed run's")
        rows = rows_of(folder)
        self.assertIsNotNone(rows, "the armed run wrote no case-times file")
        inner = [row for row in rows if (row.get("case") or "").startswith("Inner.")]
        self.assertEqual(len(inner), 1, "Inner.test_inner_sleeps has %d rows, want one: the suite's own run. The "
                                        "runs inside Outer kept a row each: %s" % (len(inner), inner))
        self.assertEqual(inner[0].get("s"), 0.25, "the suite's own Inner row has s %r, want 0.25" % inner[0].get("s"))
        outer = {row.get("case"): row.get("s") for row in rows if (row.get("case") or "").startswith("Outer.")}
        self.assertEqual(outer, {"Outer.test_a_runs_inner": 0.75, "Outer.test_b_runs_inner": 0.25},
                         "the outer rows do not hold the time of the inner case they run: %s" % outer)


class ImportFailure(unittest.TestCase):
    def assert_failed_import_row(self, module, folder, want_suite):
        unarmed = run_module(folder, module, armed=False, report=True)
        self.assertEqual(result_line(unarmed), "RESULT ran=1 failures=0 errors=1 skipped=0",
                         "the unarmed control run did not report one import error: %r" % unarmed.stderr[-300:])
        armed = run_module(folder, module, report=True)
        scope_ok(self, armed)
        self.assertEqual(armed.returncode, unarmed.returncode, "the armed run exited %d, the unarmed %d"
                         % (armed.returncode, unarmed.returncode))
        self.assertEqual(result_line(armed), result_line(unarmed),
                         "the armed run's outcome differs from the unarmed run's")
        rows = rows_of(folder)
        self.assertIsNotNone(rows, "the armed run wrote no case-times file")
        failed = [row for row in rows if row.get("case") == "_FailedTest." + module]
        self.assertEqual(len(failed), 1, "the import failure has %d rows, want one: %s" % (len(failed), rows))
        self.assertEqual(failed[0].get("suite"), want_suite,
                         "the import failure's row is named for %r, want %r: the loader's own file is not a suite"
                         % (failed[0].get("suite"), want_suite))
        self.assertEqual(failed[0].get("group"), want_suite, "the import failure's group is %r, want %r"
                         % (failed[0].get("group"), want_suite))

    def test_named_by_the_failed_modules_own_file(self):
        folder = case_folder(self)
        write(folder, "fixture_import_fails.py", IMPORT_FAILS)
        self.assert_failed_import_row("fixture_import_fails", folder, "fixture_import_fails.py")

    def test_no_file_is_named_import_failure(self):
        folder = case_folder(self)
        self.assert_failed_import_row("fixture_no_such_module", folder, "import-failure")


class FixtureTime(unittest.TestCase):
    def test_setup_and_teardown_land_in_fixture_s(self):
        folder = case_folder(self)
        write(folder, "fixture_timed.py", TIMED)
        unarmed = run_module(folder, "fixture_timed", armed=False, report=True)
        self.assertEqual(result_line(unarmed), "RESULT ran=1 failures=0 errors=0 skipped=0",
                         "the unarmed control run did not pass its one case: %r" % unarmed.stderr[-300:])
        armed = run_module(folder, "fixture_timed", report=True)
        scope_ok(self, armed)
        self.assertEqual(armed.returncode, unarmed.returncode, "the armed run exited %d, the unarmed %d"
                         % (armed.returncode, unarmed.returncode))
        self.assertEqual(result_line(armed), result_line(unarmed),
                         "the armed run's outcome differs from the unarmed run's")
        rows = rows_of(folder)
        self.assertIsNotNone(rows, "the armed run wrote no case-times file")
        timed = [row for row in rows if row.get("case") == "Timed.test_case"]
        self.assertEqual(len(timed), 1, "Timed.test_case has %d rows, want one" % len(timed))
        self.assertEqual(timed[0].get("s"), 0.25, "Timed.test_case s is %r, want its own 0.25: its setUp and tearDown "
                                                  "(0.625 s) belong in fixture_s, not in s" % timed[0].get("s"))
        self.assertEqual(timed[0].get("fixture_s"), 0.625, "Timed.test_case fixture_s is %r, want 0.625 (setUp 0.5 s, "
                                                           "tearDown 0.125 s)" % timed[0].get("fixture_s"))


class RowFails(unittest.TestCase):
    def test_a_row_that_cannot_be_kept_writes_one_stderr_line(self):
        folder = case_folder(self)
        write(folder, "fixture_broken.py", ROW_BROKEN)
        unarmed = run_module(folder, "fixture_broken", armed=False, report=True)
        self.assertEqual(result_line(unarmed), "RESULT ran=3 failures=0 errors=0 skipped=0",
                         "the unarmed control run did not pass its three cases: %r" % unarmed.stderr[-300:])
        armed = run_module(folder, "fixture_broken", report=True)
        scope_ok(self, armed)
        self.assertEqual(armed.returncode, 0,
                         "the armed run exited %d, want 0: a row that could not be kept aborted the run; "
                         "stderr tail: %s" % (armed.returncode, armed.stderr[-300:]))
        self.assertEqual(result_line(armed), result_line(unarmed),
                         "the armed run's outcome differs from the unarmed run's")
        notes = [line for line in armed.stderr.splitlines() if line.startswith("case_times: no row for ")]
        self.assertEqual(len(notes), 1,
                         "a row that could not be kept wrote %d stderr lines, want one: %s" % (len(notes), notes))
        rows = rows_of(folder)
        self.assertIsNotNone(rows, "the armed run wrote no case-times file")
        cases = sorted(row.get("case") for row in rows if (row.get("case") or "").startswith("Broken."))
        self.assertEqual(cases, ["Broken.test_b_plain", "Broken.test_c_plain"],
                         "the rows after the one that could not be kept are wrong: %s" % cases)


class OpenFrame(unittest.TestCase):
    def assert_open_frame(self, module, folder, ran_line, cases, named):
        """The unarmed control runs as ran_line says. The armed run keeps one row per (case, outcome) in cases, and
        writes one stderr line that names the open frame."""
        unarmed = run_module(folder, module, armed=False, report=True)
        self.assertEqual(result_line(unarmed), ran_line,
                         "the unarmed control run is not %r: %r" % (ran_line, unarmed.stderr[-300:]))
        armed = run_module(folder, module, report=True)
        scope_ok(self, armed)
        self.assertEqual(result_line(armed), result_line(unarmed),
                         "the armed run's outcome differs from the unarmed run's")
        rows = rows_of(folder) or []
        for case, outcome in cases:
            got = [row for row in rows if row.get("case") == case]
            self.assertEqual(len(got), 1, "%s has %d rows, want one: an open frame dropped its row"
                             % (case, len(got)))
            self.assertEqual(got[0].get("outcome"), outcome,
                             "%s outcome is %r, want %r" % (case, got[0].get("outcome"), outcome))
        notes = [line for line in armed.stderr.splitlines() if line.startswith("case_times:")]
        self.assertEqual(len(notes), 1, "the open frame at flush wrote %d case_times stderr lines, want one: %s"
                         % (len(notes), notes))
        self.assertIn(named, notes[0], "the stderr line does not name the open frame: %r" % notes[0])

    def test_open_frame_at_flush_keeps_later_rows_and_names_it(self):
        folder = case_folder(self)
        write(folder, "fixture_leak.py", LEAK)
        self.assert_open_frame("fixture_leak", folder, "RESULT ran=3 failures=0 errors=0 skipped=0",
                               [("Leak.test_b_plain", "pass"), ("Leak.test_c_plain", "pass")],
                               "Leak.test_a_leaves_frame_open")

    def test_frame_opened_outside_any_case_keeps_rows(self):
        folder = case_folder(self)
        write(folder, "fixture_leak_module.py", LEAK_MODULE)
        self.assert_open_frame("fixture_leak_module", folder, "RESULT ran=3 failures=0 errors=0 skipped=0",
                               [("Module.test_b_plain", "pass"), ("Module.test_c_plain", "pass")],
                               "Seed.test_a")

    def test_case_frame_on_runner_result_keeps_its_row(self):
        folder = case_folder(self)
        write(folder, "fixture_leak_own.py", LEAK_OWN)
        self.assert_open_frame("fixture_leak_own", folder, "RESULT ran=4 failures=0 errors=0 skipped=0",
                               [("Own.test_a_opens_a_frame_on_the_runner_result", "pass"),
                                ("Own.test_b_plain", "pass"), ("Own.test_c_plain", "pass")],
                               "Own.test_a_opens_a_frame_on_the_runner_result")


class ArmWithoutCallSetUp(unittest.TestCase):
    def test_missing_call_setup_still_starts_and_runs(self):
        folder = case_folder(self)
        write(folder, "fixture_child.py", CHILD)
        unarmed = run_module(folder, "fixture_child", armed=False, report=True, flags=("absent",))
        self.assertEqual(result_line(unarmed), "RESULT ran=1 failures=0 errors=0 skipped=0",
                         "the unarmed control run did not pass its one case with TestCase._callSetUp absent: %r"
                         % unarmed.stderr[-300:])
        armed = run_module(folder, "fixture_child", report=True, flags=("absent",))
        scope_ok(self, armed)
        self.assertEqual(armed.returncode, 0,
                         "the armed run exited %d, want 0: with TestCase._callSetUp absent the arm broke the Python "
                         "start; stderr tail: %s" % (armed.returncode, armed.stderr[-300:]))
        self.assertEqual(result_line(armed), result_line(unarmed),
                         "the armed run's outcome differs from the unarmed run's")
        notes = [line for line in armed.stderr.splitlines() if line.startswith("case_times:")]
        self.assertEqual(len(notes), 1, "the absent TestCase._callSetUp wrote %d case_times stderr lines, want one: %s"
                         % (len(notes), notes))

    def test_deleted_call_setup_writes_one_line_naming_it(self):
        folder = case_folder(self)
        write(folder, "fixture_child.py", CHILD)
        unarmed = run_module(folder, "fixture_child", armed=False, report=True, flags=("deleted",))
        armed = run_module(folder, "fixture_child", report=True, flags=("deleted",))
        scope_ok(self, armed)
        self.assertEqual(armed.returncode, unarmed.returncode, "the armed run exited %d, the unarmed %d"
                         % (armed.returncode, unarmed.returncode))
        self.assertEqual(result_line(armed), result_line(unarmed),
                         "the armed run's outcome differs from the unarmed run's")
        notes = [line for line in armed.stderr.splitlines() if line.startswith("case_times:")]
        self.assertEqual(len(notes), 1, "the deleted TestCase._callSetUp wrote %d case_times stderr lines, want one: %s"
                         % (len(notes), notes))
        self.assertIn("_callSetUp", notes[0], "the stderr line does not name the missing call: %r" % notes[0])


class AsyncFixture(unittest.TestCase):
    def test_async_setup_seconds_land_in_fixture_s(self):
        folder = case_folder(self)
        write(folder, "fixture_async.py", ASYNC)
        unarmed = run_module(folder, "fixture_async", armed=False, report=True)
        self.assertEqual(result_line(unarmed), "RESULT ran=1 failures=0 errors=0 skipped=0",
                         "the unarmed control run did not pass its one case: %r" % unarmed.stderr[-300:])
        armed = run_module(folder, "fixture_async", report=True)
        scope_ok(self, armed)
        self.assertEqual(result_line(armed), result_line(unarmed),
                         "the armed run's outcome differs from the unarmed run's")
        rows = rows_of(folder)
        self.assertIsNotNone(rows, "the armed run wrote no case-times file")
        timed = [row for row in rows if row.get("case") == "Async.test_case"]
        self.assertEqual(len(timed), 1, "Async.test_case has %d rows, want one" % len(timed))
        self.assertEqual(timed[0].get("fixture_s"), 0.5,
                         "Async.test_case fixture_s is %r, want 0.5: its asyncSetUp seconds belong in fixture_s"
                         % timed[0].get("fixture_s"))
        self.assertEqual(timed[0].get("s"), 0.25, "Async.test_case s is %r, want its own 0.25"
                         % timed[0].get("s"))


class SetupTraceback(unittest.TestCase):
    def test_setup_error_traceback_matches_unarmed(self):
        folder = case_folder(self)
        write(folder, "fixture_setup_error.py", SETUP_ERROR)
        unarmed = run_module(folder, "fixture_setup_error", armed=False, flags=("tracebacks",))
        unarmed_text = traceback_text(unarmed)
        self.assertIsNotNone(unarmed_text, "the unarmed run printed no setUp error traceback; stdout tail: %r"
                             % unarmed.stdout[-300:])
        self.assertIn("in setUp", unarmed_text, "the unarmed control traceback has no setUp frame: %r" % unarmed_text)
        armed = run_module(folder, "fixture_setup_error", flags=("tracebacks",))
        scope_ok(self, armed)
        armed_text = traceback_text(armed)
        self.assertIsNotNone(armed_text, "the armed run printed no setUp error traceback; stdout tail: %r"
                             % armed.stdout[-300:])
        frames = [line.strip() for line in armed_text.splitlines() if line.lstrip().startswith("File ")]
        unarmed_frames = [line.strip() for line in unarmed_text.splitlines() if line.lstrip().startswith("File ")]
        self.assertEqual(armed_text, unarmed_text,
                         "the armed setUp traceback differs from the unarmed one: armed frames %s, unarmed frames %s"
                         % (frames, unarmed_frames))


class ArmImports(unittest.TestCase):
    def test_armed_import_unittest_loads_no_asyncio(self):
        folder = case_folder(self)
        loaded = "LOADED asyncio=False async_case=False"
        unarmed = run_py(folder, ["-c", IMPORTS_PROBE], armed=False)
        self.assertIn(loaded, unarmed.stdout, "the unarmed control shows a module loaded after import unittest: %r"
                      % unarmed.stdout[-300:])
        armed = run_py(folder, ["-c", IMPORTS_PROBE])
        scope_ok(self, armed)
        self.assertIn(loaded, armed.stdout, "the armed arm loaded asyncio or unittest.async_case on import unittest: %r"
                      % armed.stdout[-300:])


if __name__ == "__main__":
    unittest.main()
