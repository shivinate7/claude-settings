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
import unittest

site = sys.modules.get("sitecustomize")
site_file = getattr(site, "__file__", None) if site is not None else None
print("SITE_FILE", os.path.realpath(site_file) if site_file else "none")
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


def run_module(folder, module, armed=True, count=False, extra=None, pythonpath=HOME, report=False):
    options = (["count"] if count else []) + (["report"] if report else [])
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


if __name__ == "__main__":
    unittest.main()
