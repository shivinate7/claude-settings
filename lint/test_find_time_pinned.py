#!/usr/bin/env python3
"""Cases for lint/find_time_pinned.py. Standard library only.

    python3 lint/test_find_time_pinned.py

Each case writes a small fixture folder of plain files under the run folder and runs the real finder
on it. The cases cover the four categories for Python, JS/TS and Swift, the calendar category (a real
date or the local zone), the must-stay-clean list, the scanner traps of building-scanner-respects-strings,
test-file selection, the text and JSON output, and the exit codes. The JS trap table that the scanner
suite shares is in lint/test_scanner_traps.mjs.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _test_temp  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.path.join(HERE, "find_time_pinned.py")
RUN_FOLDER = _test_temp.run_folder()  # test-temp-standard (one run folder per test run)

PY_SLEEP = "time.sleep(1)"
JS_SLEEP = "await new Promise((r) => setTimeout(r, 500));"
SWIFT_SLEEP = "Thread.sleep(forTimeInterval: 0.5)"
PY_CLOCKS = [
    "time.time", "time.monotonic", "time.perf_counter", "time.process_time",
    "time.time_ns", "time.monotonic_ns", "time.perf_counter_ns",
    "datetime.now", "datetime.utcnow", "datetime.datetime.now",
]
PY_CALENDAR = [
    "datetime.now()", "datetime.datetime.now()", "date.today()", "datetime.today()",
    "time.localtime()", 'time.strftime("%Y")', "datetime.now().astimezone()",
    "datetime.utcnow()", "datetime.datetime.utcnow()",
]
SWIFT_CLOCKS = [
    "Date()", "CFAbsoluteTimeGetCurrent()", "DispatchTime.now()",
    "ProcessInfo.processInfo.systemUptime", "mach_absolute_time()",
    "ContinuousClock.now", "SuspendingClock.now",
    "start.timeIntervalSinceNow", "start.duration(to: .now)",
]
def summary_line(total, files, sleep=0, elapsed=0, calendar=0, hang_guards=0, unread=0):
    """The one summary line. A hang guard (test-cap or wait-cap) is its own count: it is never added to the
    total or the file count, and it is not a kind in the parenthesised list (test-practices P5)."""
    return ("%d time-pinned in %d files (sleep %d, elapsed-assert %d, calendar %d); "
            "hang guards %d (allowed; check each cap sits well above the run); %d unread"
            % (total, files, sleep, elapsed, calendar, hang_guards, unread))


SUMMARY_ZERO = summary_line(0, 0)


def assert_summary(case, stdout, expected):
    """The summary is the last line. The total and the file count come first, so a hang guard counted there
    fails with that cause alone. Then the whole line, so a changed kinds list or hang guards count fails
    with the summary-form cause alone."""
    last = (stdout.splitlines() or [""])[-1]
    case.assertEqual(last.split(" (", 1)[0], expected.split(" (", 1)[0],
                     "a hang guard or test-cap is counted in the time-pinned total or files")
    case.assertEqual(last, expected, "the summary line is not the pinned form")


def src(*lines):
    return "\n".join(lines) + "\n"


def put(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def lineno(text, needle):
    """The 1-based line that holds needle. The needle must be unique in the fixture."""
    hits = [n for n, line in enumerate(text.split("\n"), 1) if needle in line]
    assert len(hits) == 1, (needle, hits)
    return hits[0]


def pinned(path, text, *pairs):
    """The expected (path, line, category) rows. Each pair is (needle, category)."""
    return {(path, lineno(text, needle), cat) for needle, cat in pairs}


def run(root, *extra):
    if not os.path.isfile(MODULE):
        raise AssertionError("lint/find_time_pinned.py is missing (the tool is not built)")
    return subprocess.run(
        [sys.executable, MODULE, root, *extra], capture_output=True, text=True, timeout=60,
    )


class FinderCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)
        self.root = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, rel, text):
        put(self.root, rel, text)

    def report(self):
        proc = run(self.root, "--json")
        self.assertIn(proc.returncode, (0, 1), proc.stdout + proc.stderr)
        return proc.returncode, json.loads(proc.stdout)

    def rows(self, out):
        return {(f["path"], f["line"], f["category"]) for f in out["findings"]}


# ---- Python: ast-based categories -------------------------------------------------------------

class PythonCategoriesTest(FinderCase):
    def test_sleep_is_flagged_except_a_zero_yield(self):
        text = src(
            "import asyncio",
            "import time",
            "from time import sleep",
            "",
            "def test_wait(delay):",
            "    time.sleep(0.5)",
            "    time.sleep(delay)",
            "    sleep(2)",
            "    time.sleep(0)",
            "    time.sleep(0.0)",
            "",
            "async def test_async():",
            "    await asyncio.sleep(0.2)",
            "    await asyncio.sleep(0)",
            "    await asyncio.sleep(0.0)",
        )
        self.put("tests/test_wait.py", text)
        code, out = self.report()
        self.assertEqual(code, 1)
        self.assertEqual(self.rows(out), pinned(
            "tests/test_wait.py", text,
            ("time.sleep(0.5)", "sleep"), ("time.sleep(delay)", "sleep"),
            ("sleep(2)", "sleep"), ("asyncio.sleep(0.2)", "sleep"),
        ))

    def test_bare_sleep_needs_an_import(self):
        text = src("def sleep(seconds):", "    return seconds", "", "def test_local():", "    sleep(1)")
        self.put("tests/test_local.py", text)
        code, out = self.report()
        self.assertEqual((code, self.rows(out)), (0, set()))

    def test_elapsed_assert_on_a_clock_or_a_tainted_name(self):
        text = src(
            "import time",
            "",
            "def test_budget():",
            "    t0 = time.monotonic()",
            "    elapsed = time.monotonic() - t0",
            "    assert elapsed < 1",
            "    assert time.time() > 0",
        )
        self.put("tests/test_budget.py", text)
        code, out = self.report()
        self.assertEqual(code, 1)
        self.assertEqual(self.rows(out), pinned(
            "tests/test_budget.py", text,
            ("assert elapsed < 1", "elapsed-assert"), ("assert time.time() > 0", "elapsed-assert"),
        ))

    def test_elapsed_taint_repeats_until_no_change(self):
        text = src(
            "import time",
            "",
            "def test_chain():",
            "    a = time.time()",
            "    b = a + 1",
            "    c = b * 2",
            "    assert c > 0",
        )
        self.put("tests/test_chain.py", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/test_chain.py", text, ("assert c > 0", "elapsed-assert")))

    def test_elapsed_assert_call_whose_name_starts_with_assert(self):
        text = src(
            "import time",
            "import unittest",
            "",
            "class BudgetTest(unittest.TestCase):",
            "    def test_budget(self):",
            "        t0 = time.perf_counter()",
            "        self.assertLess(time.perf_counter() - t0, 2)",
            "        self.assertEqual(len([]), 0)",
        )
        self.put("tests/test_budget.py", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/test_budget.py", text, ("self.assertLess(", "elapsed-assert")))

    def test_elapsed_assert_reads_each_clock(self):
        lines = ["import datetime", "import time", ""]
        for i, clock in enumerate(PY_CLOCKS):
            lines += [f"def test_{i}():", f"    t = {clock}()", f"    assert {clock}() > t", ""]
        text = src(*lines)
        self.put("tests/test_clocks.py", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/test_clocks.py", text,
            *[(f"assert {c}() > t", "elapsed-assert") for c in PY_CLOCKS],
            ("t = datetime.now()", "calendar"), ("t = datetime.datetime.now()", "calendar"),
            ("t = datetime.utcnow()", "calendar"),
            ("assert datetime.now() > t", "calendar"), ("assert datetime.datetime.now() > t", "calendar"),
            ("assert datetime.utcnow() > t", "calendar"),
        ), "calendar not listed")

    def test_elapsed_assert_on_a_bare_imported_clock(self):
        text = src(
            "from time import monotonic",
            "",
            "def test_budget():",
            "    t0 = monotonic()",
            "    assert monotonic() - t0 < 1",
        )
        self.put("tests/test_budget.py", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/test_budget.py", text, ("assert monotonic() - t0 < 1", "elapsed-assert")))

    def test_taint_stays_inside_one_function(self):
        text = src(
            "import time",
            "",
            "def stamp():",
            "    t = time.time()",
            "    return t",
            "",
            "def test_value():",
            "    t = 5",
            "    assert t > 0",
        )
        self.put("tests/test_scope.py", text)
        code, out = self.report()
        self.assertEqual((code, self.rows(out)), (0, set()))

    def test_test_cap_forms(self):
        text = src(
            "import pytest",
            "import signal",
            "import timeout_decorator",
            "from timeout_decorator import timeout",
            "",
            "pytestmark = pytest.mark.timeout(10)",
            "",
            "@pytest.mark.timeout(5)",
            "def test_a():",
            "    pass",
            "",
            "@timeout(5)",
            "def test_b():",
            "    pass",
            "",
            "@timeout_decorator.timeout(5)",
            "def test_c():",
            "    pass",
            "",
            "def test_d():",
            "    signal.alarm(3)",
            "    signal.setitimer(signal.ITIMER_REAL, 2)",
        )
        self.put("tests/test_caps.py", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/test_caps.py", text,
            ("pytestmark = pytest.mark.timeout(10)", "test-cap"),
            ("@pytest.mark.timeout(5)", "test-cap"),
            ("@timeout(5)", "test-cap"),
            ("@timeout_decorator.timeout(5)", "test-cap"),
            ("signal.alarm(3)", "test-cap"),
            ("signal.setitimer(", "test-cap"),
        ))

    def test_wait_cap_keyword_timeout_number(self):
        text = src(
            "import subprocess",
            "",
            "def test_waits(p, q, t, ev, cmd):",
            "    subprocess.run(cmd, timeout=5)",
            "    p.wait(timeout=3)",
            "    q.get(timeout=1)",
            "    t.join(timeout=2)",
            "    ev.wait(timeout=1)",
            "    q.get(timeout=-1)",
            "    subprocess.run(cmd, timeout=LIMIT)",
        )
        self.put("tests/test_waits.py", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/test_waits.py", text,
            ("subprocess.run(cmd, timeout=5)", "wait-cap"), ("p.wait(timeout=3)", "wait-cap"),
            ("q.get(timeout=1)", "wait-cap"), ("t.join(timeout=2)", "wait-cap"),
            ("ev.wait(timeout=1)", "wait-cap"), ("q.get(timeout=-1)", "wait-cap"),
        ))


class PythonCleanTest(FinderCase):
    def test_patterns_in_comments_and_strings_are_clean(self):
        text = src(
            "import time",
            "# time.sleep(1) in a comment",
            "NOTE = 'time.sleep(1) in a string'",
            "BLOCK = '''",
            "time.sleep(1)",
            "'''",
            "",
            "def test_docs():",
            "    '''Docstring: assert time.time() > 0 and time.sleep(2)'''",
            "    msg = \"Don't wait: time.sleep(2)\"",
            "    assert msg",
        )
        self.put("tests/test_docs.py", text)
        code, out = self.report()
        self.assertEqual((code, self.rows(out)), (0, set()))

    def test_quote_in_text_does_not_hide_the_defect(self):
        text = src("import time", "msg = \"Don't wait\"", "time.sleep(1)")
        self.put("tests/test_quote.py", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/test_quote.py", text, ("time.sleep(1)", "sleep")))

    def test_clock_without_an_assert_is_clean(self):
        text = src(
            "import logging",
            "import time",
            "",
            "log = logging.getLogger(__name__)",
            "",
            "def test_log():",
            "    t0 = time.monotonic()",
            "    log.info('took %s', time.monotonic() - t0)",
            "    print(time.time())",
        )
        self.put("tests/test_log.py", text)
        code, out = self.report()
        self.assertEqual((code, self.rows(out)), (0, set()))


# ---- calendar: a test that reads the real date or the local zone (P5: a calendar date is a real clock) ----

def calendar_judge(case, path, text, listed=(), clean=(), root=None):
    """Scope first (P7): the fixture was read. Then the calendar rows: each listed form is one, no clean form
    is one, and no other line is one. Each failure names one cause."""
    proc = run(root or case.root, "--json")
    case.assertIn(proc.returncode, (0, 1), proc.stdout + proc.stderr)
    out = json.loads(proc.stdout)
    case.assertFalse(out["unread"], "scope: the fixture was not read: %s" % out["unread"])
    got = {(f["path"], f["line"]) for f in out["findings"] if f["category"] == "calendar"}
    missing = [n for n in listed if (path, lineno(text, n)) not in got]
    case.assertFalse(missing, "calendar not listed: " + "; ".join(missing))
    extra = [n for n in clean if (path, lineno(text, n)) in got]
    case.assertFalse(extra, "calendar listed where it must not be: " + "; ".join(extra))
    case.assertEqual(got, {(path, lineno(text, n)) for n in listed}, "calendar listed on a line no case names")
    return out


def fake_clock_judge(case, path, text, proof, categories):
    """Scope first (P7): the fixture was read. The proof row is an elapsed-assert, which a fake clock keeps, so a
    file the finder skips has no row there and fails. Then no row of each named category. Each failure names one cause."""
    proc = run(case.root, "--json")
    case.assertIn(proc.returncode, (0, 1), proc.stdout + proc.stderr)
    out = json.loads(proc.stdout)
    case.assertFalse(out["unread"], "scope: the fixture was not read: %s" % out["unread"])
    case.assertIn((path, lineno(text, proof), "elapsed-assert"), case.rows(out),
                  "scope: the fixture was not read, so its elapsed-assert row is not listed")
    for cat in categories:
        rows = sorted(r for r in case.rows(out) if r[2] == cat)
        case.assertFalse(rows, "%s listed under a fake clock: %s" % (cat, rows))


# A JS test that reads the date. The fake clock, when a case adds one, sets the date it reads.
JS_DATE_READ = [
    "it('reads the faked date', () => {",
    "  const f_now = new Date();",
    "  expect(f_now.getUTCFullYear()).toBe(2024);",
    "});",
]
# A JS clock difference. A fake clock keeps its elapsed-assert row, so a fake-clock case lists it as the proof
# that the finder read its file (fake_clock_judge).
JS_ELAPSED = [
    "const t0 = Date.now();",
    "expect(Date.now() - t0).toBeLessThan(100);",
]


class PythonCalendarTest(FinderCase):
    def last_line(self):
        proc = run(self.root)
        self.assertIn(proc.returncode, (0, 1), proc.stdout + proc.stderr)
        return proc.stdout.splitlines()[-1]

    def test_each_python_calendar_form_is_listed(self):
        forms = [f"t_{i} = {form}" for i, form in enumerate(PY_CALENDAR)]
        text = src("import datetime", "import time", "from datetime import date", "", "def test_forms(stamp):",
                   *["    " + f for f in forms])
        self.put("tests/test_forms.py", text)
        calendar_judge(self, "tests/test_forms.py", text, listed=forms)

    def test_datetime_now_with_a_zone_is_listed(self):
        text = src(
            "import datetime",
            "from datetime import timezone",
            "",
            "def test_zone(tz):",
            "    t_utc = datetime.now(timezone.utc)",
            "    t_tz = datetime.now(tz)",
        )
        self.put("tests/test_zone.py", text)
        calendar_judge(self, "tests/test_zone.py", text,
                       listed=["t_utc = datetime.now(timezone.utc)", "t_tz = datetime.now(tz)"])

    def test_utcnow_and_a_local_read_of_an_epoch_are_listed(self):
        text = src(
            "import datetime",
            "import time",
            "",
            "EPOCH = 0",
            "",
            "def test_utc(stamp):",
            "    t_utc = datetime.utcnow()",
            "    t_utc_dt = datetime.datetime.utcnow()",
            "    t_fixed = time.localtime(EPOCH)",
        )
        self.put("tests/test_utc.py", text)
        calendar_judge(self, "tests/test_utc.py", text,
                       listed=["t_utc = datetime.utcnow()", "t_utc_dt = datetime.datetime.utcnow()",
                               "t_fixed = time.localtime(EPOCH)"])

    def test_local_read_of_an_epoch_is_listed_and_strftime_with_a_time_is_not(self):
        text = src(
            "import time",
            "EPOCH = 0",
            "",
            "def test_fixed(stamp):",
            "    t_fixed = time.localtime(EPOCH)",
            "    t_given = time.strftime('%Y', stamp)",
            "    t_now = time.localtime()",
        )
        self.put("tests/test_fixed.py", text)
        calendar_judge(self, "tests/test_fixed.py", text,
                       listed=["t_fixed = time.localtime(EPOCH)", "t_now = time.localtime()"],
                       clean=["t_given = time.strftime('%Y', stamp)"])

    def test_summary_and_counts_include_calendar(self):
        text = src(
            "import datetime",
            "import time",
            "",
            "def test_summary(stamp):",
            "    t_a = datetime.now()",
            "    t_b = time.localtime()",
            "    time.sleep(1)",
        )
        self.put("tests/test_summary.py", text)
        out = calendar_judge(self, "tests/test_summary.py", text,
                             listed=["t_a = datetime.now()", "t_b = time.localtime()"])
        self.assertEqual(out["counts"].get("calendar"), 2, "calendar not counted in the JSON counts")
        last = self.last_line()
        self.assertTrue(last.startswith("3 time-pinned in 1 files ("), "summary total is not 3: " + last)
        self.assertIn("calendar 2", last, "calendar not listed in the summary")

    def test_summary_shows_calendar_zero_when_no_form(self):
        text = src(
            "import time",
            "EPOCH = 0",
            "",
            "def test_none(stamp):",
            "    t_fixed = time.gmtime(EPOCH)",
            "    time.sleep(1)",
        )
        self.put("tests/test_none.py", text)
        calendar_judge(self, "tests/test_none.py", text, clean=["t_fixed = time.gmtime(EPOCH)"])
        self.assertIn("calendar 0", self.last_line(), "calendar not listed in the summary")

    def test_hash_opener_in_a_string_does_not_hide_a_form(self):
        text = src(
            "import datetime",
            "",
            "def test_label():",
            "    label = '# not a comment'; t_hash = datetime.now()",
            "    t_str = 'datetime.now()'",
        )
        self.put("tests/test_hash.py", text)
        calendar_judge(self, "tests/test_hash.py", text,
                       listed=["t_hash = datetime.now()"], clean=["t_str = 'datetime.now()'"])

    def test_forms_in_a_comment_or_a_string_are_not_listed(self):
        text = src(
            "import datetime",
            "import time",
            "",
            "# t_comment = datetime.now()",
            "NOTE = 't_note = date.today()'",
            "",
            "def test_docs():",
            "    '''Docstring: t_doc = time.localtime()'''",
            "    t_real = datetime.today()",
        )
        self.put("tests/test_docs.py", text)
        calendar_judge(self, "tests/test_docs.py", text,
                       listed=["t_real = datetime.today()"],
                       clean=["t_comment = datetime.now()", "t_note = date.today()", "t_doc = time.localtime()"])

    def test_multi_line_string_and_a_lone_quote_do_not_hide_a_form(self):
        text = src(
            "import datetime",
            "import time",
            "",
            'BLOCK = """',
            "t_block = time.localtime()",
            '"""',
            "msg = \"Don't stop\"",
            "",
            "def test_after():",
            "    t_after = datetime.now()",
        )
        self.put("tests/test_block.py", text)
        calendar_judge(self, "tests/test_block.py", text,
                       listed=["t_after = datetime.now()"], clean=["t_block = time.localtime()"])

    def test_ctime_and_no_argument_readers_are_listed_and_gmtime_asctime_are_not(self):
        text = src(
            "import time",
            "EPOCH = 0",
            "",
            "def test_readers(stamp):",
            "    t_gm_now = time.gmtime()",
            "    t_ct_now = time.ctime()",
            "    t_as_now = time.asctime()",
            "    t_gm_fixed = time.gmtime(EPOCH)",
            "    t_ct_fixed = time.ctime(EPOCH)",
            "    t_as_fixed = time.asctime(stamp)",
        )
        self.put("tests/test_readers.py", text)
        calendar_judge(self, "tests/test_readers.py", text,
                       listed=["t_gm_now = time.gmtime()", "t_ct_now = time.ctime()", "t_as_now = time.asctime()",
                               "t_ct_fixed = time.ctime(EPOCH)"],
                       clean=["t_gm_fixed = time.gmtime(EPOCH)", "t_as_fixed = time.asctime(stamp)"])

    def test_zone_attributes_are_listed(self):
        text = src(
            "import time",
            "",
            "def test_zone():",
            "    t_tzname = time.tzname",
            "    t_offset = time.timezone",
        )
        self.put("tests/test_zone_attrs.py", text)
        calendar_judge(self, "tests/test_zone_attrs.py", text,
                       listed=["t_tzname = time.tzname", "t_offset = time.timezone"])

    def test_time_readers_in_a_comment_or_a_string_are_not_listed(self):
        text = src(
            "import time",
            "",
            "# t_comment = time.gmtime()",
            "NOTE = 't_note = time.ctime()'",
            "",
            "def test_text():",
            "    '''Docstring: t_doc = time.asctime(), t_zone = time.timezone'''",
            "    t_real = time.gmtime()",
        )
        self.put("tests/test_text_readers.py", text)
        calendar_judge(self, "tests/test_text_readers.py", text,
                       listed=["t_real = time.gmtime()"],
                       clean=["# t_comment = time.gmtime()", "NOTE = 't_note = time.ctime()'", "Docstring:"])

    def test_date_today_and_datetime_today_on_a_module_chain_are_listed(self):
        text = src(
            "import datetime",
            "",
            "def test_today(x):",
            "    assert datetime.date.today() == x",
            "    assert datetime.datetime.today() == x",
        )
        self.put("tests/test_today.py", text)
        calendar_judge(self, "tests/test_today.py", text,
                       listed=["assert datetime.date.today() == x", "assert datetime.datetime.today() == x"])

    def test_python_date_library_now_reads_are_listed(self):
        text = src(
            "import arrow",
            "import pandas",
            "import pandas as pd",
            "import pendulum",
            "from django.utils import timezone",
            "",
            "def test_libraries(stamp):",
            "    t_pendulum = pendulum.now()",
            "    t_arrow = arrow.now()",
            "    t_arrow_utc = arrow.utcnow()",
            "    t_pd = pd.Timestamp.now()",
            "    t_pandas = pandas.Timestamp.now()",
            "    t_django = timezone.now()",
        )
        self.put("tests/test_libraries.py", text)
        calendar_judge(self, "tests/test_libraries.py", text, listed=[
            "t_pendulum = pendulum.now()", "t_arrow = arrow.now()", "t_arrow_utc = arrow.utcnow()",
            "t_pd = pd.Timestamp.now()", "t_pandas = pandas.Timestamp.now()", "t_django = timezone.now()",
        ])

    def test_python_date_library_fixed_time_is_not_listed(self):
        text = src(
            "import pendulum",
            "",
            "def test_fixed(stamp):",
            "    t_fixed = pendulum.datetime(2024, 1, 1)",
        )
        self.put("tests/test_fixed_dates.py", text)
        calendar_judge(self, "tests/test_fixed_dates.py", text,
                       clean=["t_fixed = pendulum.datetime(2024, 1, 1)"])

    def test_python_date_library_no_argument_reads_are_listed(self):
        text = src(
            "import arrow",
            "import pandas as pd",
            "import pendulum",
            "from django.utils import timezone",
            "",
            "def test_no_argument(stamp):",
            "    t_pd_utc = pd.Timestamp.utcnow()",
            "    t_today = pendulum.today()",
            "    t_arrow = arrow.get()",
            "    t_local = timezone.localtime()",
            "    t_local_date = timezone.localdate()",
        )
        self.put("tests/test_no_argument.py", text)
        calendar_judge(self, "tests/test_no_argument.py", text, listed=[
            "t_pd_utc = pd.Timestamp.utcnow()", "t_today = pendulum.today()", "t_arrow = arrow.get()",
            "t_local = timezone.localtime()", "t_local_date = timezone.localdate()",
        ])

    def test_python_date_library_with_an_argument_is_not_listed(self):
        text = src(
            "import arrow",
            "from django.utils import timezone",
            "",
            "def test_given(fixed_dt):",
            "    t_arrow_fixed = arrow.get(0)",
            "    t_local_fixed = timezone.localtime(fixed_dt)",
            "    t_date_fixed = timezone.localdate(fixed_dt)",
        )
        self.put("tests/test_given_argument.py", text)
        calendar_judge(self, "tests/test_given_argument.py", text, clean=[
            "t_arrow_fixed = arrow.get(0)", "t_local_fixed = timezone.localtime(fixed_dt)",
            "t_date_fixed = timezone.localdate(fixed_dt)",
        ])

    def test_date_library_zone_argument_reads_are_listed_and_fixed_ones_are_not(self):
        text = src(
            "import arrow",
            "import pandas as pd",
            "import pendulum",
            "from django.utils import timezone",
            "",
            "def test_zone(tz, fixed_dt):",
            "    t_pendulum_zone = pendulum.today('UTC')",
            "    t_pd_today = pd.Timestamp.today()",
            "    t_arrow_tz = arrow.get(tzinfo=tz)",
            "    t_local_tz = timezone.localtime(timezone=tz)",
            "    t_arrow_fixed = arrow.get(0)",
            "    t_local_fixed = timezone.localtime(fixed_dt)",
        )
        self.put("tests/test_zone_argument.py", text)
        calendar_judge(self, "tests/test_zone_argument.py", text, listed=[
            "t_pendulum_zone = pendulum.today('UTC')", "t_pd_today = pd.Timestamp.today()",
            "t_arrow_tz = arrow.get(tzinfo=tz)", "t_local_tz = timezone.localtime(timezone=tz)",
        ], clean=["t_arrow_fixed = arrow.get(0)", "t_local_fixed = timezone.localtime(fixed_dt)"])

    def test_freeze_time_decorator_suppresses_calendar_not_elapsed_assert(self):
        text = src(
            "import datetime",
            "from datetime import timedelta",
            "from freezegun import freeze_time",
            "",
            "@freeze_time('2024-01-01')",
            "def test_decorated(stamp):",
            "    t0 = datetime.datetime.now()",
            "    t_now = datetime.datetime.now()",
            "    assert datetime.datetime.now() - t0 < timedelta(seconds=1)",
        )
        self.put("tests/test_frozen.py", text)
        out = calendar_judge(self, "tests/test_frozen.py", text, clean=[
            "t0 = datetime.datetime.now()", "t_now = datetime.datetime.now()",
            "assert datetime.datetime.now() - t0 < timedelta(seconds=1)",
        ])
        self.assertEqual(self.rows(out), pinned(
            "tests/test_frozen.py", text, ("assert datetime.datetime.now() - t0", "elapsed-assert")),
            "a fake clock must leave the elapsed-assert row on a subtracted clock read")

    def test_freeze_time_block_suppresses_calendar_for_a_plain_read(self):
        text = src(
            "import datetime",
            "from freezegun import freeze_time",
            "",
            "def test_block(stamp):",
            "    with freeze_time('2024-01-01'):",
            "        t_now = datetime.datetime.now()",
            "        assert stamp == 2024",
        )
        self.put("tests/test_frozen_block.py", text)
        out = calendar_judge(self, "tests/test_frozen_block.py", text, clean=["t_now = datetime.datetime.now()"])
        self.assertEqual(self.rows(out), set(), "a plain read under a fake clock is listed in some category")

    def test_fake_clock_scope_block_ends_before_the_read(self):
        text = src(
            "import datetime",
            "from freezegun import freeze_time",
            "",
            "def test_after_block(stamp):",
            "    with freeze_time('2024-01-01'):",
            "        t_inside = datetime.datetime.now()",
            "    t_after = datetime.datetime.now()",
        )
        self.put("tests/test_block_scope.py", text)
        calendar_judge(self, "tests/test_block_scope.py", text,
                       listed=["t_after = datetime.datetime.now()"],
                       clean=["t_inside = datetime.datetime.now()"])

    def test_fake_clock_scope_stops_at_an_undecorated_sibling_def(self):
        text = src(
            "import datetime",
            "from freezegun import freeze_time",
            "",
            "@freeze_time('2024-01-01')",
            "def test_frozen(stamp):",
            "    t_frozen = datetime.datetime.now()",
            "",
            "",
            "def test_plain(stamp):",
            "    t_plain = datetime.datetime.now()",
        )
        self.put("tests/test_sibling_scope.py", text)
        calendar_judge(self, "tests/test_sibling_scope.py", text,
                       listed=["t_plain = datetime.datetime.now()"],
                       clean=["t_frozen = datetime.datetime.now()"])

    def test_freeze_time_class_decorator_hides_calendar_in_its_methods(self):
        text = src(
            "import datetime",
            "from freezegun import freeze_time",
            "",
            "@freeze_time('2024-01-01')",
            "class TestFrozen:",
            "    def test_method(self, stamp):",
            "        t_method = datetime.datetime.now()",
        )
        self.put("tests/test_class_frozen.py", text)
        calendar_judge(self, "tests/test_class_frozen.py", text,
                       clean=["t_method = datetime.datetime.now()"])

    def test_fake_clock_argument_in_a_decorator_is_still_listed(self):
        text = src(
            "import datetime",
            "from freezegun import freeze_time",
            "",
            "@freeze_time(datetime.datetime.now().isoformat())",
            "def test_decorator_argument(stamp):",
            "    t_body = datetime.datetime.now()",
        )
        self.put("tests/test_decorator_argument.py", text)
        calendar_judge(self, "tests/test_decorator_argument.py", text,
                       listed=["@freeze_time(datetime.datetime.now().isoformat())"],
                       clean=["t_body = datetime.datetime.now()"])

    def test_fake_clock_argument_in_a_with_is_still_listed(self):
        text = src(
            "import datetime",
            "from freezegun import freeze_time",
            "",
            "def test_with_argument(stamp):",
            "    with freeze_time(datetime.datetime.now()):",
            "        t_body = datetime.datetime.now()",
        )
        self.put("tests/test_with_argument.py", text)
        calendar_judge(self, "tests/test_with_argument.py", text,
                       listed=["with freeze_time(datetime.datetime.now()):"],
                       clean=["t_body = datetime.datetime.now()"])

    def test_fake_clock_does_not_hide_zone_attribute_reads(self):
        text = src(
            "import time",
            "from freezegun import freeze_time",
            "",
            "@freeze_time('2024-01-01')",
            "def test_zone(stamp):",
            "    z_name = time.tzname",
            "    z_offset = time.timezone",
        )
        self.put("tests/test_zone_attr.py", text)
        calendar_judge(self, "tests/test_zone_attr.py", text,
                       listed=["z_name = time.tzname", "z_offset = time.timezone"])

    def test_freezegun_dotted_decorator_hides_calendar_in_its_def(self):
        text = src(
            "import datetime",
            "import freezegun",
            "",
            "@freezegun.freeze_time('2024-01-01')",
            "def test_dotted(stamp):",
            "    t_dotted = datetime.datetime.now()",
        )
        self.put("tests/test_dotted_freeze.py", text)
        calendar_judge(self, "tests/test_dotted_freeze.py", text,
                       clean=["t_dotted = datetime.datetime.now()"])

    def test_zone_read_with_a_non_zone_keyword_is_not_listed(self):
        text = src(
            "from django.utils import timezone",
            "",
            "def test_value_keyword(fixed_dt):",
            "    t_value_local = timezone.localtime(value=fixed_dt)",
            "    t_value_date = timezone.localdate(value=fixed_dt)",
        )
        self.put("tests/test_value_keyword.py", text)
        calendar_judge(self, "tests/test_value_keyword.py", text, clean=[
            "t_value_local = timezone.localtime(value=fixed_dt)",
            "t_value_date = timezone.localdate(value=fixed_dt)",
        ])

    def test_freeze_time_in_a_comment_or_a_string_does_not_suppress_calendar(self):
        text = src(
            "import datetime",
            "",
            "# from freezegun import freeze_time",
            "FROZEN = \"@freeze_time('2024-01-01')\"",
            "",
            "",
            "def test_real(stamp):",
            "    t_real = datetime.datetime.now()",
        )
        self.put("tests/test_freeze_text.py", text)
        calendar_judge(self, "tests/test_freeze_text.py", text, listed=["t_real = datetime.datetime.now()"])

    def test_python_date_library_in_a_string_or_comment_is_not_listed(self):
        text = src(
            "import pendulum",
            "",
            "# t_comment = pendulum.now()",
            "NOTE = 't_note = pendulum.now()'",
            "",
            "",
            "def test_text(stamp):",
            "    '''Docstring: t_doc = pendulum.now()'''",
        )
        self.put("tests/test_library_text.py", text)
        calendar_judge(self, "tests/test_library_text.py", text, clean=[
            "# t_comment = pendulum.now()", "NOTE = 't_note = pendulum.now()'",
            "Docstring: t_doc = pendulum.now()",
        ])

    def test_hash_opener_in_a_string_before_pendulum_now_still_lists(self):
        text = src(
            "import pendulum",
            "",
            "NOTE = \"# not a comment\"",
            "",
            "",
            "def test_hash(stamp):",
            "    t_real = pendulum.now()",
        )
        self.put("tests/test_hash_library.py", text)
        calendar_judge(self, "tests/test_hash_library.py", text, listed=["t_real = pendulum.now()"])

    def test_unfrozen_datetime_now_still_lists_calendar(self):
        text = src(
            "import datetime",
            "from datetime import timedelta",
            "",
            "def test_unfrozen(stamp):",
            "    t0 = datetime.datetime.now()",
            "    t_now = datetime.datetime.now()",
            "    assert datetime.datetime.now() - t0 < timedelta(seconds=1)",
        )
        self.put("tests/test_unfrozen.py", text)
        calendar_judge(self, "tests/test_unfrozen.py", text, listed=[
            "t0 = datetime.datetime.now()", "t_now = datetime.datetime.now()",
            "assert datetime.datetime.now() - t0 < timedelta(seconds=1)",
        ])

    def test_bare_name_imported_from_time_is_listed_in_an_assert(self):
        text = src(
            "from time import timezone",
            "",
            "def test_offset():",
            "    assert timezone == 0",
        )
        self.put("tests/test_bare_zone.py", text)
        calendar_judge(self, "tests/test_bare_zone.py", text, listed=["assert timezone == 0"])

    def test_fromtimestamp_without_a_zone_is_listed_and_a_zone_argument_is_not(self):
        text = src(
            "import time",
            "from datetime import datetime, timezone",
            "",
            "EPOCH = 0",
            "",
            "def test_fromtimestamp(stamp):",
            "    t_ft_fixed = datetime.fromtimestamp(EPOCH)",
            "    t_ft_stamp = datetime.fromtimestamp(stamp)",
            "    t_ft_utc_kw = datetime.fromtimestamp(stamp, tz=timezone.utc)",
            "    t_ft_utc_pos = datetime.fromtimestamp(stamp, timezone.utc)",
            "    t_ft_none_pos = datetime.fromtimestamp(stamp, None)",
            "    t_ft_none_kw = datetime.fromtimestamp(stamp, tz=None)",
            "    t_ft_utc = datetime.utcfromtimestamp(stamp)",
            "    t_gm = time.gmtime(EPOCH)",
            "    # t_comment = datetime.fromtimestamp(EPOCH)",
            "    NOTE = 't_note = datetime.fromtimestamp(EPOCH)'",
        )
        self.put("tests/test_fromtimestamp.py", text)
        calendar_judge(self, "tests/test_fromtimestamp.py", text,
                       listed=["t_ft_fixed = datetime.fromtimestamp(EPOCH)",
                               "t_ft_stamp = datetime.fromtimestamp(stamp)",
                               "t_ft_none_pos = datetime.fromtimestamp(stamp, None)",
                               "t_ft_none_kw = datetime.fromtimestamp(stamp, tz=None)"],
                       clean=["t_ft_utc_kw = datetime.fromtimestamp(stamp, tz=timezone.utc)",
                              "t_ft_utc_pos = datetime.fromtimestamp(stamp, timezone.utc)",
                              "t_ft_utc = datetime.utcfromtimestamp(stamp)", "t_gm = time.gmtime(EPOCH)",
                              "# t_comment = datetime.fromtimestamp(EPOCH)", "NOTE = 't_note = datetime"])

    def test_astimezone_without_a_zone_is_listed_and_a_zone_argument_is_not(self):
        text = src(
            "from datetime import timezone",
            "",
            "def test_astimezone(fixed_dt):",
            "    t_as_local = fixed_dt.astimezone()",
            "    t_as_utc = fixed_dt.astimezone(timezone.utc)",
            "    t_as_none_pos = fixed_dt.astimezone(None)",
            "    t_as_none_kw = fixed_dt.astimezone(tz=None)",
        )
        self.put("tests/test_astimezone.py", text)
        calendar_judge(self, "tests/test_astimezone.py", text,
                       listed=["t_as_local = fixed_dt.astimezone()",
                               "t_as_none_pos = fixed_dt.astimezone(None)",
                               "t_as_none_kw = fixed_dt.astimezone(tz=None)"],
                       clean=["t_as_utc = fixed_dt.astimezone(timezone.utc)"])


# ---- JS/TS: masker then patterns ----------------------------------------------------------------

class JsCategoriesTest(FinderCase):
    def test_sleep_forms(self):
        text = src(
            "test('waits', async () => {",
            "  " + JS_SLEEP,
            "  await sleep(250);",
            "  await delay(100);",
            "  await wait(75);",
            "  await setTimeoutPromise(60);",
            "  await setTimeout(40);",
            "  setTimeout(done, 1000);",
            "  Atomics.wait(view, 0, 0, 100);",
            "});",
        )
        self.put("tests/waits.test.js", text)
        code, out = self.report()
        self.assertEqual(code, 1)
        self.assertEqual(self.rows(out), pinned(
            "tests/waits.test.js", text,
            ("setTimeout(r, 500)", "sleep"), ("await sleep(250)", "sleep"),
            ("await delay(100)", "sleep"), ("await wait(75)", "sleep"),
            ("await setTimeoutPromise(60)", "sleep"), ("await setTimeout(40)", "sleep"),
            ("setTimeout(done, 1000)", "sleep"), ("Atomics.wait(", "sleep"),
        ))

    def test_fake_timers_skip_sleep_findings(self):
        text = src(
            "vi.useFakeTimers();",
            JS_SLEEP,
        )
        self.put("tests/fake.test.js", text)
        code, out = self.report()
        self.assertEqual((code, self.rows(out)), (0, set()))

    def test_fake_timers_skip_only_the_sleep(self):
        text = src(
            "jest.useFakeTimers();",
            "const t0 = Date.now();",
            JS_SLEEP,
            "expect(Date.now() - t0).toBeLessThan(100);",
        )
        self.put("tests/fake.test.js", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/fake.test.js", text, ("expect(Date.now() - t0)", "elapsed-assert")))

    def test_jest_fake_clock_skips_new_date_calendar(self):
        text = src("jest.useFakeTimers();", "jest.setSystemTime(new Date(0));", *JS_DATE_READ, *JS_ELAPSED)
        self.put("tests/jest_clock.test.js", text)
        fake_clock_judge(self, "tests/jest_clock.test.js", text, "expect(Date.now() - t0)", ("calendar",))

    def test_vi_fake_clock_skips_new_date_calendar(self):
        text = src("vi.useFakeTimers();", "vi.setSystemTime(new Date(0));", *JS_DATE_READ, *JS_ELAPSED)
        self.put("tests/vi_clock.test.js", text)
        fake_clock_judge(self, "tests/vi_clock.test.js", text, "expect(Date.now() - t0)", ("calendar",))

    def test_new_date_without_a_fake_clock_still_lists_calendar(self):
        text = src(*JS_DATE_READ)
        self.put("tests/real_clock.test.js", text)
        calendar_judge(self, "tests/real_clock.test.js", text, listed=["const f_now = new Date();"])

    def test_jest_fake_clock_still_lists_temporal_now(self):
        """Jest fakes Date, not Temporal, so a Temporal.Now read under it is still a real-date read."""
        text = src(
            "jest.useFakeTimers();",
            "it('reads the clocks', () => {",
            "  const t_date = new Date();",
            "  const t_instant = Temporal.Now.instant();",
            "  const t_plain = Temporal.Now.plainDateISO();",
            "});",
        )
        self.put("tests/jest_temporal.test.js", text)
        calendar_judge(self, "tests/jest_temporal.test.js", text,
                       listed=["const t_instant = Temporal.Now.instant();",
                               "const t_plain = Temporal.Now.plainDateISO();"],
                       clean=["const t_date = new Date();"])

    def test_vi_fake_clock_still_lists_temporal_now(self):
        """Vitest fakes Date, not Temporal, so a Temporal.Now read under it is still a real-date read."""
        text = src(
            "vi.useFakeTimers();",
            "it('reads the clocks', () => {",
            "  const t_date = new Date();",
            "  const t_instant = Temporal.Now.instant();",
            "  const t_plain = Temporal.Now.plainDateISO();",
            "});",
        )
        self.put("tests/vi_temporal.test.js", text)
        calendar_judge(self, "tests/vi_temporal.test.js", text,
                       listed=["const t_instant = Temporal.Now.instant();",
                               "const t_plain = Temporal.Now.plainDateISO();"],
                       clean=["const t_date = new Date();"])

    def test_fake_clock_in_a_line_comment_does_not_hide_new_date(self):
        text = src(
            "// jest.useFakeTimers();",
            "const d_line = new Date();",
        )
        self.put("tests/line_comment_fake.test.js", text)
        calendar_judge(self, "tests/line_comment_fake.test.js", text,
                       listed=["const d_line = new Date();"])

    def test_fake_clock_in_a_block_comment_does_not_hide_new_date(self):
        text = src(
            "/* vi.useFakeTimers(); */",
            "const d_block = new Date();",
        )
        self.put("tests/block_comment_fake.test.js", text)
        calendar_judge(self, "tests/block_comment_fake.test.js", text,
                       listed=["const d_block = new Date();"])

    def test_fake_clock_in_a_string_does_not_hide_new_date(self):
        text = src(
            "const note = 'jest.useFakeTimers();';",
            "const d_string = new Date();",
        )
        self.put("tests/string_fake.test.js", text)
        calendar_judge(self, "tests/string_fake.test.js", text,
                       listed=["const d_string = new Date();"])

    def test_elapsed_assert_on_expect_or_assert_calls(self):
        text = src(
            "const t0 = Date.now();",
            "const dt = performance.now() - t0;",
            "expect(dt).toBeLessThan(100);",
            "assert(new Date() > t0);",
            "assert.ok(process.hrtime.bigint() > 0n);",
            "expect(Date.now()).toBeGreaterThan(0);",
            "const hr = process.hrtime();",
            "assert.strictEqual(hr.length, 2);",
        )
        self.put("tests/timing.test.js", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/timing.test.js", text,
            ("expect(dt)", "elapsed-assert"), ("assert(new Date()", "elapsed-assert"),
            ("assert.ok(process.hrtime.bigint()", "elapsed-assert"),
            ("expect(Date.now()).toBeGreaterThan", "elapsed-assert"),
            ("assert.strictEqual(hr.length", "elapsed-assert"), ("assert(new Date()", "calendar"),
        ), "calendar not listed")

    def test_elapsed_taint_repeats_in_js(self):
        text = src(
            "const a = Date.now();",
            "let b = a + 1;",
            "var c = b * 2;",
            "expect(c).toBeGreaterThan(0);",
        )
        self.put("tests/chain.test.js", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/chain.test.js", text, ("expect(c)", "elapsed-assert")))

    def test_test_cap_forms(self):
        text = src(
            "jest.setTimeout(10000);",
            "vi.setConfig({ testTimeout: 10000 });",
            "describe('suite', function () {",
            "  this.timeout(5000);",
            "});",
            "it('slow', async () => {}, 5000);",
            "test.only('slower', async () => {}, 9000);",
            "describe.skip('skipped', () => {}, 8000);",
            "it.concurrent('parallel', async () => {}, 7000);",
            "it.each([1])('each', (n) => {}, 6000);",
            "const cfg = { testTimeout: 4000 };",
        )
        self.put("tests/caps.test.js", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/caps.test.js", text,
            ("jest.setTimeout(10000)", "test-cap"), ("vi.setConfig({ testTimeout", "test-cap"),
            ("this.timeout(5000)", "test-cap"), ("it('slow'", "test-cap"),
            ("test.only('slower'", "test-cap"), ("describe.skip('skipped'", "test-cap"),
            ("it.concurrent('parallel'", "test-cap"), ("'each', (n) => {}, 6000", "test-cap"),
            ("const cfg = { testTimeout: 4000 }", "test-cap"),
        ))

    def test_object_timeout_on_a_test_call_is_test_cap_only(self):
        text = src("it('object form', async () => {}, { timeout: 3000 });")
        self.put("tests/object.test.js", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/object.test.js", text, ("{ timeout: 3000 }", "test-cap")))

    def test_wait_cap_forms(self):
        text = src(
            "await waitFor(() => ready(), { timeout: 2000 });",
            "execFileSync(cmd, args, { timeout: 5000 });",
            "const signal = AbortSignal.timeout(1000);",
            "const limit = { timeout: budget };",
        )
        self.put("tests/waits.test.js", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/waits.test.js", text,
            ("waitFor(() => ready()", "wait-cap"), ("execFileSync(cmd", "wait-cap"),
            ("AbortSignal.timeout(1000)", "wait-cap"),
        ))


class JsCleanTest(FinderCase):
    def test_patterns_in_comments_and_strings_are_clean(self):
        text = src(
            "// await new Promise((r) => setTimeout(r, 500));",
            "/* setTimeout(r, 500) and expect(Date.now() - t0).toBeLessThan(1) */",
            "const s = 'setTimeout(r, 500)';",
            "const u = \"await sleep(250)\";",
            "const q = \"it('x', async () => {}, 5000)\";",
            "const n = 'this.timeout(5000)';",
            "const v = \"waitFor(() => 1, { timeout: 2000 })\";",
        )
        self.put("tests/clean.test.js", text)
        code, out = self.report()
        self.assertEqual((code, self.rows(out)), (0, set()))

    def test_zero_delay_and_non_literal_delay_are_clean(self):
        text = src(
            "setTimeout(() => done(), 0);",
            "setTimeout(done, delay);",
            "await sleep(0);",
            "Atomics.wait(view, 0, 0, limit);",
        )
        self.put("tests/zero.test.js", text)
        code, out = self.report()
        self.assertEqual((code, self.rows(out)), (0, set()))

    def test_clock_without_an_assert_is_clean(self):
        text = src(
            "const t0 = Date.now();",
            "console.log(Date.now() - t0);",
            "const label = `at ${Date.now()}`;",
        )
        self.put("tests/log.test.js", text)
        code, out = self.report()
        self.assertEqual((code, self.rows(out)), (0, set()))


class JsTrapsTest(FinderCase):
    def test_comment_openers_and_a_lone_quote_in_strings(self):
        text = src(
            "const u = \"http://a.test/\";",
            "const s = \"/* not a comment\";",
            "const h = \"# not a comment\";",
            "const q = \"<p>Don't</p>\";",
            JS_SLEEP,
        )
        self.put("tests/traps.test.js", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/traps.test.js", text, ("setTimeout(r, 500)", "sleep")))

    def test_multi_line_template_holding_a_timer_is_clean(self):
        text = src(
            "const doc = `",
            "await new Promise((r) => setTimeout(r, 100));",
            "`;",
            JS_SLEEP,
        )
        self.put("tests/template.test.js", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/template.test.js", text, ("setTimeout(r, 500)", "sleep")))

    def test_lone_quote_in_jsx_text_does_not_hide_the_defect(self):
        for name in ("note.test.jsx", "note.test.tsx"):
            with self.subTest(name=name):
                root = os.path.join(self.tmp.name, name)
                text = src("export const Note = () => <p>Don't stop here</p>;", JS_SLEEP)
                put(root, f"tests/{name}", text)
                proc = run(root, "--json")
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertEqual(self.rows(json.loads(proc.stdout)), pinned(
                    f"tests/{name}", text, ("setTimeout(r, 500)", "sleep")))

    def test_regex_literal_with_a_quote(self):
        text = src("const re = /don't/;", JS_SLEEP)
        self.put("tests/regex.test.js", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/regex.test.js", text, ("setTimeout(r, 500)", "sleep")))

    def test_division_then_a_string_with_a_quote(self):
        text = src("const half = total / 2; const s = 'x';", JS_SLEEP)
        self.put("tests/divide.test.js", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/divide.test.js", text, ("setTimeout(r, 500)", "sleep")))

    def test_nested_template_parts_with_strings(self):
        text = src('const n = `outer ${ `inner ${ "}" }` } end`;', JS_SLEEP)
        self.put("tests/template_parts.test.js", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/template_parts.test.js", text, ("setTimeout(r, 500)", "sleep")))

    def test_calendar_after_a_comment_opener_in_a_string(self):
        text = src(
            'const u = "http://a.test/"; const today = new Date();',
            "const later = new Date();",
        )
        self.put("tests/calendar_slashes.test.js", text)
        calendar_judge(self, "tests/calendar_slashes.test.js", text,
                       listed=["const today = new Date();", "const later = new Date();"])

    def test_bare_date_after_a_comment_opener_in_a_string(self):
        text = src(
            'const u = "http://a.test/"; const today = Date();',
            "const later = Date();",
        )
        self.put("tests/bare_slashes.test.js", text)
        calendar_judge(self, "tests/bare_slashes.test.js", text,
                       listed=["const today = Date();", "const later = Date();"])

    def test_calendar_inside_a_multi_line_template_is_not_listed(self):
        text = src(
            "const doc = `",
            "const inside = new Date();",
            "`;",
            "const outside = new Date();",
        )
        self.put("tests/calendar_template.test.js", text)
        calendar_judge(self, "tests/calendar_template.test.js", text,
                       listed=["const outside = new Date();"], clean=["const inside = new Date();"])

    def test_lone_quote_in_jsx_text_does_not_hide_a_calendar_form(self):
        for name in ("note.test.jsx", "note.test.tsx"):
            with self.subTest(name=name):
                root = os.path.join(self.tmp.name, name)
                text = src("export const Note = () => <p>Don't stop here</p>;", "const today = new Date();")
                put(root, f"tests/{name}", text)
                calendar_judge(self, f"tests/{name}", text,
                               listed=["const today = new Date();"], root=root)

    def test_comment_openers_in_a_string_before_dayjs_still_list(self):
        text = src(
            'const u = "http://a.test/"; const today = dayjs();',
            'const v = "/* open"; const later = dayjs();',
            'const w = "# tag"; const hashed = dayjs();',
        )
        self.put("tests/library_slashes.test.js", text)
        calendar_judge(self, "tests/library_slashes.test.js", text, listed=[
            "const today = dayjs();", "const later = dayjs();", "const hashed = dayjs();",
        ])

    def test_moment_text_in_a_template_is_not_listed_and_its_interpolation_is(self):
        text = src(
            "const doc = `",
            "  note: moment() text",
            "`;",
            "const label = `at ${moment()}`;",
        )
        self.put("tests/template_moment.test.js", text)
        calendar_judge(self, "tests/template_moment.test.js", text,
                       listed=["const label = `at ${moment()}`;"], clean=["note: moment() text"])

    def test_lone_quote_in_jsx_text_does_not_hide_a_date_library_read(self):
        for name in ("note.test.jsx", "note.test.tsx"):
            with self.subTest(name=name):
                root = os.path.join(self.tmp.name, name)
                text = src("export const Note = () => <p>Don't stop here</p>;", "const today = dayjs();")
                put(root, f"tests/{name}", text)
                calendar_judge(self, f"tests/{name}", text,
                               listed=["const today = dayjs();"], root=root)


class JsCalendarTest(FinderCase):
    def test_new_date_with_no_argument_is_listed_and_with_one_is_not(self):
        text = src(
            "const c_0 = new Date();",
            "let c_1 = new Date();",
            "const fixed = new Date(0);",
            "const epoch = new Date(EPOCH_MS);",
        )
        self.put("tests/calendar.test.js", text)
        calendar_judge(self, "tests/calendar.test.js", text,
                       listed=["const c_0 = new Date();", "let c_1 = new Date();"],
                       clean=["const fixed = new Date(0);", "const epoch = new Date(EPOCH_MS);"])

    def test_calendar_forms_in_a_comment_or_a_string_are_not_listed(self):
        text = src(
            "// const note = new Date();",
            "/* let block = new Date(); */",
            "const quoted = 'const q = new Date();';",
            "const real = new Date();",
        )
        self.put("tests/calendar_text.test.js", text)
        calendar_judge(self, "tests/calendar_text.test.js", text,
                       listed=["const real = new Date();"],
                       clean=["// const note = new Date();", "/* let block = new Date(); */",
                              "const q = new Date();"])

    def test_bare_date_call_without_new_is_listed(self):
        text = src(
            "const b_0 = Date();",
            "let b_1 = Date();",
        )
        self.put("tests/bare_date.test.js", text)
        calendar_judge(self, "tests/bare_date.test.js", text,
                       listed=["const b_0 = Date();", "let b_1 = Date();"])

    def test_bare_date_in_a_comment_or_a_string_is_not_listed(self):
        text = src(
            "// const note = Date();",
            "const quoted = 'const q = Date();';",
            "const doc = `",
            "const inside = Date();",
            "`;",
            "const real = Date();",
        )
        self.put("tests/bare_date_text.test.js", text)
        calendar_judge(self, "tests/bare_date_text.test.js", text,
                       listed=["const real = Date();"],
                       clean=["// const note = Date();", "const q = Date();", "const inside = Date();"])

    def test_new_date_fed_by_date_now_is_listed(self):
        text = src("const ago = new Date(Date.now() - 60000);")
        self.put("tests/clock_fed.test.js", text)
        calendar_judge(self, "tests/clock_fed.test.js", text,
                       listed=["const ago = new Date(Date.now() - 60000);"])

    def test_new_date_fed_by_performance_now_is_listed(self):
        text = src("const perf = new Date(performance.now());")
        self.put("tests/clock_perf.test.js", text)
        calendar_judge(self, "tests/clock_perf.test.js", text,
                       listed=["const perf = new Date(performance.now());"])

    def test_new_date_with_a_declared_constant_or_a_literal_is_not_listed(self):
        text = src(
            "const EPOCH_MS = 1700000000000;",
            "const fixed = new Date(0);",
            "const epoch = new Date(EPOCH_MS);",
        )
        self.put("tests/fixed_date.test.js", text)
        calendar_judge(self, "tests/fixed_date.test.js", text,
                       clean=["const fixed = new Date(0);", "const epoch = new Date(EPOCH_MS);"])

    def test_date_library_now_reads_are_listed(self):
        text = src(
            "it('reads the library clocks', () => {",
            "  const d_day = dayjs();",
            "  let d_moment = moment();",
            "  const d_instant = Temporal.Now.instant();",
            "  const d_plain = Temporal.Now.plainDateISO();",
            "});",
        )
        self.put("tests/library_now.test.js", text)
        calendar_judge(self, "tests/library_now.test.js", text, listed=[
            "const d_day = dayjs();", "let d_moment = moment();",
            "const d_instant = Temporal.Now.instant();", "const d_plain = Temporal.Now.plainDateISO();",
        ])

    def test_date_library_fixed_time_is_not_listed(self):
        text = src(
            "const EPOCH = 0;",
            "const c_day_fixed = dayjs(0);",
            "const c_moment_fixed = moment(EPOCH);",
        )
        self.put("tests/library_fixed.test.js", text)
        calendar_judge(self, "tests/library_fixed.test.js", text,
                       clean=["const c_day_fixed = dayjs(0);", "const c_moment_fixed = moment(EPOCH);"])

    def test_utc_library_no_argument_reads_are_listed(self):
        text = src(
            "it('reads the utc library clocks', () => {",
            "  const u_day = dayjs.utc();",
            "  let u_moment = moment.utc();",
            "  const u_new = new dayjs();",
            "});",
        )
        self.put("tests/utc_library.test.js", text)
        calendar_judge(self, "tests/utc_library.test.js", text, listed=[
            "const u_day = dayjs.utc();", "let u_moment = moment.utc();", "const u_new = new dayjs();",
        ])

    def test_utc_library_with_an_argument_is_not_listed(self):
        text = src(
            "const EPOCH = 0;",
            "const u_day_fixed = dayjs.utc(0);",
            "const u_moment_fixed = moment.utc(EPOCH);",
        )
        self.put("tests/utc_fixed.test.js", text)
        calendar_judge(self, "tests/utc_fixed.test.js", text, clean=[
            "const u_day_fixed = dayjs.utc(0);", "const u_moment_fixed = moment.utc(EPOCH);",
        ])

    def test_function_moment_declaration_is_not_listed(self):
        text = src(
            "const EPOCH = 0;",
            "function moment(x) { return x + EPOCH; }",
            "function moment() { return EPOCH; }",
        )
        self.put("tests/moment_declaration.test.js", text)
        calendar_judge(self, "tests/moment_declaration.test.js", text, clean=[
            "function moment(x) { return x + EPOCH; }",
            "function moment() { return EPOCH; }",
        ])

    def test_new_dayjs_with_a_fixed_time_is_not_listed(self):
        text = src(
            "const EPOCH = 0;",
            "const n_fixed = new dayjs(0);",
            "const n_epoch = new dayjs(EPOCH);",
        )
        self.put("tests/new_dayjs_fixed.test.js", text)
        calendar_judge(self, "tests/new_dayjs_fixed.test.js", text,
                       clean=["const n_fixed = new dayjs(0);", "const n_epoch = new dayjs(EPOCH);"])

    def test_temporal_text_in_a_comment_string_or_template_is_not_listed_and_interpolation_is(self):
        text = src(
            "// const c_note = Temporal.Now.instant();",
            "/* let c_block = Temporal.Now.plainDateISO(); */",
            "const c_str = 'Temporal.Now.instant()';",
            "const c_tpl = `Temporal.Now.instant()`;",
            "const c_interp = `${Temporal.Now.instant()}`;",
        )
        self.put("tests/temporal_text.test.js", text)
        calendar_judge(self, "tests/temporal_text.test.js", text,
                       listed=["const c_interp = `${Temporal.Now.instant()}`;"],
                       clean=["// const c_note = Temporal.Now.instant();",
                              "/* let c_block = Temporal.Now.plainDateISO(); */",
                              "const c_str = 'Temporal.Now.instant()';",
                              "const c_tpl = `Temporal.Now.instant()`;"])

    def test_new_date_in_a_template_interpolation_is_listed(self):
        text = src(
            "test('labels the run', () => {",
            "  const label = `run at ${new Date()}`;",
            "  const block = `",
            "    stamp ${new Date()}",
            "  `;",
            "  expect(label + block).toMatch(/run/);",
            "});",
        )
        self.put("tests/template_clock.test.js", text)
        calendar_judge(self, "tests/template_clock.test.js", text, listed=[
            "const label = `run at ${new Date()}`;", "stamp ${new Date()}",
        ])

    def test_date_library_in_a_string_or_comment_is_not_listed(self):
        text = src(
            "// const note = dayjs();",
            "const quoted = 'const q = dayjs();';",
        )
        self.put("tests/library_text.test.js", text)
        calendar_judge(self, "tests/library_text.test.js", text,
                       clean=["// const note = dayjs();", "const q = dayjs();"])


# ---- Swift: one-pass masker then patterns --------------------------------------------------------

class SwiftCategoriesTest(FinderCase):
    def test_sleep_forms(self):
        text = src(
            "import XCTest",
            "final class WaitTests: XCTestCase {",
            "    func testWaits() async throws {",
            "        " + SWIFT_SLEEP,
            "        sleep(1)",
            "        usleep(500)",
            "        try await Task.sleep(nanoseconds: 1_000)",
            "    }",
            "}",
        )
        self.put("Tests/WaitTests.swift", text)
        code, out = self.report()
        self.assertEqual(code, 1)
        self.assertEqual(self.rows(out), pinned(
            "Tests/WaitTests.swift", text,
            ("Thread.sleep(forTimeInterval: 0.5)", "sleep"), ("sleep(1)", "sleep"),
            ("usleep(500)", "sleep"), ("Task.sleep(nanoseconds", "sleep"),
        ))

    def test_elapsed_assert_on_clock_or_tainted_name(self):
        lines = ["import XCTest", "final class TimingTests: XCTestCase {"]
        for i, expr in enumerate(SWIFT_CLOCKS):
            lines += [
                f"    func testClock{i}() {{",
                f"        let t{i} = {expr}",
                f"        XCTAssertLessThan(t{i}, 9)",
                "    }",
            ]
        lines += [
            "    func testElapsed() {",
            "        let start = Date()",
            "        let elapsed = Date().timeIntervalSince(start)",
            "        XCTAssertLessThan(elapsed, 1.0)",
            "        #expect(elapsed < 2)",
            "        print(Date())",
            "    }",
            "}",
        ]
        text = src(*lines)
        self.put("Tests/TimingTests.swift", text)
        out = calendar_judge(self, "Tests/TimingTests.swift", text, listed=[
            "let t0 = Date()", "let start = Date()", "let elapsed = Date().timeIntervalSince(start)",
            "print(Date())",
        ])
        self.assertEqual({row for row in self.rows(out) if row[2] == "elapsed-assert"}, pinned(
            "Tests/TimingTests.swift", text,
            *[(f"XCTAssertLessThan(t{i}, 9)", "elapsed-assert") for i in range(len(SWIFT_CLOCKS))],
            ("XCTAssertLessThan(elapsed, 1.0)", "elapsed-assert"),
            ("#expect(elapsed < 2)", "elapsed-assert"),
        ), "the elapsed-assert rows are not the pinned set")
        other = sorted(row for row in self.rows(out) if row[2] not in ("calendar", "elapsed-assert"))
        self.assertFalse(other, "a row of another category is listed: %s" % other)

    def test_test_cap_forms(self):
        text = src(
            "import XCTest",
            "final class CapTests: XCTestCase {",
            "    override func setUp() {",
            "        executionTimeAllowance = 5",
            "    }",
            "    func testMeasured() {",
            "        measure {",
            "            work()",
            "        }",
            "        measure(metrics: [XCTClockMetric()]) { work() }",
            "    }",
            "    @Test(.timeLimit(.minutes(1)))",
            "    func slow() {}",
            "}",
        )
        self.put("Tests/CapTests.swift", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "Tests/CapTests.swift", text,
            ("executionTimeAllowance = 5", "test-cap"), ("measure {", "test-cap"),
            ("measure(metrics:", "test-cap"), (".timeLimit(", "test-cap"),
        ))

    def test_wait_cap_forms(self):
        text = src(
            "import XCTest",
            "final class WaitCapTests: XCTestCase {",
            "    func testAsync() {",
            "        wait(for: [exp], timeout: 5)",
            "        waitForExpectations(timeout: 3)",
            '        app.buttons["Go"].waitForExistence(timeout: 3)',
            "        XCTWaiter().wait(for: [exp], timeout: 2)",
            "        fulfillment(of: [exp], timeout: 2)",
            "    }",
            "}",
        )
        self.put("Tests/WaitCapTests.swift", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "Tests/WaitCapTests.swift", text,
            ("wait(for: [exp], timeout: 5)", "wait-cap"),
            ("waitForExpectations(timeout: 3)", "wait-cap"),
            ("waitForExistence(timeout: 3)", "wait-cap"),
            ("XCTWaiter().wait(for:", "wait-cap"),
            ("fulfillment(of:", "wait-cap"),
        ))


class SwiftCleanTest(FinderCase):
    def test_patterns_in_comments_and_strings_are_clean_and_a_code_date_is_listed(self):
        text = src(
            "// Thread.sleep(forTimeInterval: 1) and XCTAssertLessThan(Date(), 1)",
            'let s = "measure { executionTimeAllowance = 5 }"',
            "/* waitForExpectations(timeout: 3) */",
            'let d = "wait(for: [e], timeout: 9)"',
            'let e = "Task.sleep(nanoseconds: 1)"',
            "print(Date())",
        )
        self.put("Tests/CleanTests.swift", text)
        code, out = self.report()
        self.assertFalse(out["unread"], "scope: the fixture was not read: %s" % out["unread"])
        self.assertEqual(self.rows(out), pinned(
            "Tests/CleanTests.swift", text, ("print(Date())", "calendar")),
            "a comment or a string line is listed, or the code-level Date() is not")
        self.assertEqual(code, 1, "the listed code-level Date() does not set exit 1")


class SwiftCalendarTest(FinderCase):
    def test_calendar_and_zone_reads_are_listed(self):
        text = src(
            "import XCTest",
            "final class CalendarTests: XCTestCase {",
            "    func testReads() {",
            "        let c_cal = Calendar.current",
            "        let c_zone = TimeZone.current",
            "        let c_now = Date()",
            "        XCTAssertEqual(Date(), stamp)",
            "    }",
            "}",
        )
        self.put("Tests/CalendarTests.swift", text)
        calendar_judge(self, "Tests/CalendarTests.swift", text, listed=[
            "let c_cal = Calendar.current", "let c_zone = TimeZone.current", "let c_now = Date()",
            "XCTAssertEqual(Date(), stamp)",
        ])

    def test_fixed_calendar_and_zone_forms_are_clean(self):
        text = src(
            "import XCTest",
            "final class FixedTests: XCTestCase {",
            "    func testFixed() {",
            "        let f_date = Date(timeIntervalSince1970: 0)",
            "        let f_cal = Calendar(identifier: .gregorian)",
            '        let f_zone = TimeZone(identifier: "UTC")',
            "        // let note = Calendar.current",
            '        let s_text = "let s = TimeZone.current"',
            "    }",
            "}",
        )
        self.put("Tests/FixedTests.swift", text)
        calendar_judge(self, "Tests/FixedTests.swift", text, clean=[
            "let f_date = Date(timeIntervalSince1970: 0)", "let f_cal = Calendar(identifier: .gregorian)",
            'let f_zone = TimeZone(identifier: "UTC")', "// let note = Calendar.current", "let s_text =",
        ])

    def test_elapsed_subtraction_in_an_assert_is_elapsed_only(self):
        text = src(
            "import XCTest",
            "final class SpanTests: XCTestCase {",
            "    func testSpan() {",
            "        let begin = Date(timeIntervalSince1970: 0)",
            "        XCTAssertLessThan(Date().timeIntervalSince(begin), 1)",
            "    }",
            "}",
        )
        self.put("Tests/SpanTests.swift", text)
        out = calendar_judge(self, "Tests/SpanTests.swift", text,
                             clean=["XCTAssertLessThan(Date().timeIntervalSince(begin), 1)"])
        self.assertIn(("Tests/SpanTests.swift", lineno(text, "XCTAssertLessThan(Date()"), "elapsed-assert"),
                      self.rows(out), "the elapsed subtraction in the assert is no longer elapsed-assert")

    def test_date_now_and_date_since_now_outside_an_assert_are_listed(self):
        text = src(
            "import XCTest",
            "final class StampReadTests: XCTestCase {",
            "    func testStamps() {",
            "        let n_now = Date.now",
            "        let n_soon = Date(timeIntervalSinceNow: 60)",
            "        let n_fixed = Date(timeIntervalSince1970: 0)",
            "        let n_ref = Date(timeIntervalSinceReferenceDate: 0)",
            "        let m_prefix = MyDate.now",
            "        let m_suffix = Date.nowish",
            "        let m_since = Date(timeIntervalSinceNowish: 1)",
            "        print(n_now, n_soon, n_fixed, n_ref)",
            "    }",
            "}",
        )
        self.put("Tests/StampReadTests.swift", text)
        calendar_judge(self, "Tests/StampReadTests.swift", text,
                       listed=["let n_now = Date.now", "let n_soon = Date(timeIntervalSinceNow: 60)"],
                       clean=["let n_fixed = Date(timeIntervalSince1970: 0)",
                              "let n_ref = Date(timeIntervalSinceReferenceDate: 0)",
                              "let m_prefix = MyDate.now", "let m_suffix = Date.nowish",
                              "let m_since = Date(timeIntervalSinceNowish: 1)"])

    def test_date_now_inside_an_elapsed_assert_is_that_assert_only(self):
        text = src(
            "import XCTest",
            "final class StampSpanTests: XCTestCase {",
            "    func testSpan() {",
            "        let s_begin = Date(timeIntervalSince1970: 0)",
            "        XCTAssertLessThan(Date.now.timeIntervalSince(s_begin), 1)",
            "    }",
            "}",
        )
        self.put("Tests/StampSpanTests.swift", text)
        out = calendar_judge(self, "Tests/StampSpanTests.swift", text,
                             clean=["XCTAssertLessThan(Date.now.timeIntervalSince(s_begin), 1)"])
        self.assertIn(("Tests/StampSpanTests.swift", lineno(text, "XCTAssertLessThan(Date.now"), "elapsed-assert"),
                      self.rows(out), "the elapsed subtraction of Date.now is no longer elapsed-assert")

    def test_since_now_inside_an_elapsed_assert_is_that_assert_only(self):
        text = src(
            "import XCTest",
            "final class SinceNowSpanTests: XCTestCase {",
            "    func testSpan() {",
            "        let s_since = Date(timeIntervalSince1970: 0)",
            "        XCTAssertLessThan(Date(timeIntervalSinceNow: 0).timeIntervalSince(s_since), 1)",
            "    }",
            "}",
        )
        self.put("Tests/SinceNowSpanTests.swift", text)
        out = calendar_judge(self, "Tests/SinceNowSpanTests.swift", text,
                             clean=["XCTAssertLessThan(Date(timeIntervalSinceNow: 0).timeIntervalSince(s_since), 1)"])
        proof = lineno(text, "XCTAssertLessThan(Date(timeIntervalSinceNow")
        self.assertIn(("Tests/SinceNowSpanTests.swift", proof, "elapsed-assert"), self.rows(out),
                      "the elapsed subtraction of Date(timeIntervalSinceNow:) is no longer elapsed-assert")

    def test_calendar_forms_after_comment_openers_quotes_and_multi_line_strings(self):
        text = src(
            'let u = "http://a.test/"; let z_zone = TimeZone.current',
            'let v = "http://b.test/"; let n_after_url = Date.now',
            'let s = "/* not a comment"',
            "let c_after = Calendar.current",
            "// Don't use Calendar.current here",
            "// Don't read Date.now here",
            "let c_last = Calendar.current",
            'let block = """',
            "let t_block = Calendar.current",
            "let t_block_now = Date.now",
            '"""',
        )
        self.put("Tests/CalendarTrapTests.swift", text)
        calendar_judge(self, "Tests/CalendarTrapTests.swift", text,
                       listed=["let z_zone = TimeZone.current", "let n_after_url = Date.now",
                               "let c_after = Calendar.current", "let c_last = Calendar.current"],
                       clean=["// Don't use Calendar.current here", "// Don't read Date.now here",
                              "let t_block = Calendar.current", "let t_block_now = Date.now"])


class SwiftTrapsTest(FinderCase):
    def test_comment_openers_and_a_lone_quote_in_a_comment(self):
        text = src(
            'let u = "http://a.test/"',
            'let s = "/* not a comment"',
            'let h = "# not a comment"',
            "// Don't wait on this line",
            SWIFT_SLEEP,
        )
        self.put("Tests/TrapTests.swift", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "Tests/TrapTests.swift", text, (SWIFT_SLEEP, "sleep")))

    def test_nested_block_comment_hides_its_inner_pattern(self):
        text = src(
            "/* outer /* inner */ Thread.sleep(forTimeInterval: 1)",
            "Thread.sleep(forTimeInterval: 2) */",
            "let x = 1",
            SWIFT_SLEEP,
        )
        self.put("Tests/NestTests.swift", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "Tests/NestTests.swift", text, (SWIFT_SLEEP, "sleep")))

    def test_triple_quote_string_holding_a_pattern(self):
        text = src(
            'let doc = """',
            "Thread.sleep(forTimeInterval: 1)",
            "// a /* opener in the text",
            '"""',
            "let after = 1",
            SWIFT_SLEEP,
        )
        self.put("Tests/MultiTests.swift", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "Tests/MultiTests.swift", text, (SWIFT_SLEEP, "sleep")))

    def test_raw_strings_hold_a_pattern(self):
        text = src(
            r'let raw = #"sleep(1) says "hi""#',
            r'let deeper = ##"Thread.sleep(forTimeInterval: 1) "# still in"##',
            SWIFT_SLEEP,
        )
        self.put("Tests/RawTests.swift", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "Tests/RawTests.swift", text, (SWIFT_SLEEP, "sleep")))

    def test_interpolation_holds_quotes_and_parentheses(self):
        text = src(
            r'let msg = "a \(pick("x)")) b"',
            r'let pct = "\(String("sleep(1)"))"',
            SWIFT_SLEEP,
        )
        self.put("Tests/InterpTests.swift", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "Tests/InterpTests.swift", text, (SWIFT_SLEEP, "sleep")))


# ---- test-file selection ------------------------------------------------------------------------

class SelectionTest(FinderCase):
    def test_python_test_file_names(self):
        scanned = ["test_a.py", "b_test.py", "conftest.py", "tests/helpers.py", "test/helpers.py"]
        skipped = ["app.py", "testsuite/helpers.py", "lib/testing/x.py"]
        for rel in scanned + skipped:
            self.put(rel, PY_SLEEP + "\n")
        code, out = self.report()
        self.assertEqual({f["path"] for f in out["findings"]}, set(scanned))

    def test_js_test_file_names_and_extensions(self):
        scanned = ["app.test.js", "app.spec.ts", "test_helper.js", "test-setup.mjs",
                   "__tests__/a.js", "tests/b.cjs", "test/c.mts"]
        skipped = ["src/app.js", "src/testing.js", "tests/data.json"]
        for rel in scanned + skipped:
            self.put(rel, JS_SLEEP + "\n")
        code, out = self.report()
        self.assertEqual({f["path"] for f in out["findings"]}, set(scanned))

    def test_every_js_extension_is_scanned(self):
        exts = [".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts"]
        for ext in exts:
            self.put(f"tests/case.test{ext}", JS_SLEEP + "\n")
        code, out = self.report()
        self.assertEqual({f["path"] for f in out["findings"]},
                         {f"tests/case.test{ext}" for ext in exts})

    def test_swift_test_file_names(self):
        scanned = ["WaitTests.swift", "WaitTest.swift", "AppTests/Helpers.swift"]
        skipped = ["Sources/App.swift", "Sources/TestSupport.swift"]
        for rel in scanned + skipped:
            self.put(rel, SWIFT_SLEEP + "\n")
        code, out = self.report()
        self.assertEqual({f["path"] for f in out["findings"]}, set(scanned))

    def test_nothing_else_is_scanned(self):
        self.put("tests/run.sh", "sleep 1\n")
        self.put("tests/run.ps1", "Start-Sleep 1\n")
        self.put("tests/ci.yml", "sleep 2\n")
        code, out = self.report()
        self.assertEqual((code, self.rows(out)), (0, set()))

    def test_non_test_files_are_never_read(self):
        self.put("app.py", "def broken(:\n    pass\n")
        self.put("lib/testing/x.py", "def broken(:\n    pass\n")
        self.put("src/app.js", JS_SLEEP + "\n")
        code, out = self.report()
        self.assertEqual((code, out["unread"], out["findings"]), (0, [], []))


class WalkTest(FinderCase):
    def test_build_and_vendor_folders_are_skipped_outside_git(self):
        for name in [".git", "node_modules", ".build", "DerivedData", "venv", ".venv"]:
            self.put(f"{name}/tests/test_skip.py", PY_SLEEP + "\n")
        self.put("tests/test_real.py", PY_SLEEP + "\n")
        code, out = self.report()
        self.assertEqual(self.rows(out), {("tests/test_real.py", 1, "sleep")})

    def test_git_root_lists_tracked_files_only(self):
        subprocess.run(["git", "init", "-q", self.root], check=True)
        self.put("tests/test_tracked.py", PY_SLEEP + "\n")
        self.put("tests/test_untracked.py", PY_SLEEP + "\n")
        subprocess.run(["git", "-C", self.root, "add", "tests/test_tracked.py"], check=True)
        code, out = self.report()
        self.assertEqual({f["path"] for f in out["findings"]}, {"tests/test_tracked.py"})


# ---- output ---------------------------------------------------------------------------------------

class OutputTest(FinderCase):
    def test_text_lines_then_summary_last(self):
        text = src(
            "import subprocess",
            "import time",
            "",
            "def test_x(cmd):",
            "    time.sleep(1)",
            "    subprocess.run(cmd, timeout=5)",
        )
        self.put("tests/test_x.py", text)
        proc = run(self.root)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        lines = proc.stdout.splitlines()
        self.assertIn("tests/test_x.py:%d: sleep: time.sleep(1)" % lineno(text, "time.sleep(1)"), lines)
        self.assertIn(
            "tests/test_x.py:%d: wait-cap: subprocess.run(cmd, timeout=5)" % lineno(text, "subprocess.run"),
            lines)
        assert_summary(self, proc.stdout, summary_line(1, 1, sleep=1, hang_guards=1))

    def test_summary_line_for_an_empty_root(self):
        proc = run(self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert_summary(self, proc.stdout, SUMMARY_ZERO)

    def test_summary_counts_each_category(self):
        text = src(
            "import time",
            "import pytest",
            "",
            "def test_all(p):",
            "    time.sleep(1)",
            "    t0 = time.monotonic()",
            "    assert time.monotonic() - t0 < 2",
            "",
            "@pytest.mark.timeout(5)",
            "def test_capped(p):",
            "    p.wait(timeout=3)",
        )
        self.put("tests/test_all.py", text)
        proc = run(self.root, "--json")
        out = json.loads(proc.stdout)
        self.assertEqual(out["counts"], {"sleep": 1, "elapsed-assert": 1, "test-cap": 1, "wait-cap": 1, "calendar": 0},
                         "calendar not listed in the counts")
        proc = run(self.root)
        assert_summary(self, proc.stdout, summary_line(2, 1, sleep=1, elapsed=1, hang_guards=2))

    def test_line_text_is_trimmed_and_capped_at_120(self):
        long_line = "    time.sleep(1)  # " + "x" * 200
        self.put("tests/test_long.py", src("import time", "def test_long():", long_line))
        code, out = self.report()
        text = out["findings"][0]["text"]
        self.assertTrue(text.startswith("time.sleep(1)"), text)
        self.assertLessEqual(len(text), 120)
        self.assertEqual(text, text.strip())

    def test_json_shape_and_paths(self):
        self.put("tests/test_ok.py", src("import time", "time.sleep(1)"))
        self.put("tests/test_bad.py", "def broken(:\n    pass\n")
        code, out = self.report()
        self.assertEqual(code, 1)
        self.assertEqual(set(out), {"findings", "unread", "counts"})
        finding = out["findings"][0]
        self.assertEqual(set(finding), {"path", "line", "category", "lang", "text"})
        self.assertEqual((finding["path"], finding["line"], finding["text"]),
                         ("tests/test_ok.py", 2, "time.sleep(1)"))
        self.assertEqual(out["unread"][0]["path"], "tests/test_bad.py")
        self.assertEqual(set(out["unread"][0]), {"path", "reason"})
        self.assertEqual(out["counts"], {"sleep": 1, "elapsed-assert": 0, "test-cap": 0, "wait-cap": 0, "calendar": 0},
                         "calendar not listed in the counts")


# ---- exit codes -----------------------------------------------------------------------------------

class ExitCodeTest(FinderCase):
    def test_exit_0_when_clean(self):
        self.put("tests/test_clean.py", src("import time", "time.monotonic()"))
        code, out = self.report()
        self.assertEqual((code, out["findings"], out["unread"]), (0, [], []))

    def test_exit_2_for_a_missing_root(self):
        proc = run(os.path.join(self.tmp.name, "nowhere"))
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

    def test_syntax_error_alone_is_unread_and_exits_2(self):
        self.put("tests/test_bad.py", "def broken(:\n    pass\n")
        proc = run(self.root)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        unread = [line for line in proc.stdout.splitlines() if line.startswith("UNREAD tests/test_bad.py: ")]
        self.assertEqual(len(unread), 1, proc.stdout)
        self.assertTrue(proc.stdout.splitlines()[-1].endswith("; 1 unread"), proc.stdout)
        proc = run(self.root, "--json")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["findings"], [])
        self.assertEqual(out["unread"][0]["path"], "tests/test_bad.py")
        self.assertTrue(out["unread"][0]["reason"])

    def test_findings_with_an_unread_file_exit_1_and_still_list_it(self):
        self.put("tests/test_ok.py", PY_SLEEP + "\n")
        self.put("tests/test_bad.py", "def broken(:\n    pass\n")
        proc = run(self.root)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("UNREAD tests/test_bad.py: ", proc.stdout)

    def test_calendar_alone_exits_1(self):
        self.put("tests/test_stamp.py", src("import datetime", "", "def test_stamp():", "    t_now = datetime.datetime.now()"))
        code, out = self.report()
        self.assertEqual(out["unread"], [], "scope: the fixture was not read")
        self.assertEqual([f["category"] for f in out["findings"]], ["calendar"], "the fixture is not calendar-only")
        self.assertEqual(code, 1, "a calendar-only finding does not exit 1")


# ---- a hang guard (wait-cap or test-cap) is listed, never counted (test-practices P5) ----

HANG_GUARD = src(
    "import subprocess",
    "",
    "def test_run(cmd):",
    "    subprocess.run(cmd, timeout=5)",
)
SLEEP_FILE = src("import time", "", "def test_wait():", "    time.sleep(1)")
TEST_CAP = src(
    "import pytest",
    "",
    "pytestmark = pytest.mark.timeout(10)",
    "",
    "@pytest.mark.timeout(5)",
    "def test_run():",
    "    pass",
)


def hang_row(path="tests/test_run.py"):
    return "%s:%d: wait-cap: subprocess.run(cmd, timeout=5)" % (path, lineno(HANG_GUARD, "subprocess.run"))


def cap_rows(path="tests/test_run.py"):
    """The two text rows of TEST_CAP: the per-suite pytestmark and the per-test decorator."""
    return {
        "%s:%d: test-cap: pytestmark = pytest.mark.timeout(10)" % (path, lineno(TEST_CAP, "pytestmark")),
        "%s:%d: test-cap: @pytest.mark.timeout(5)" % (path, lineno(TEST_CAP, "@pytest.mark.timeout(5)")),
    }


def assert_cap_rows_listed(case, stdout):
    """Scope first (P7): the test-cap rows are listed and the fixture was read."""
    missing = sorted(row for row in cap_rows() if row not in stdout.splitlines())
    case.assertFalse(missing, "scope: the test-cap was not found: %s" % missing)
    case.assertNotIn("UNREAD", stdout, "scope: the fixture was not read")


class HangGuardTest(FinderCase):
    def test_hang_guard_alone_exits_0(self):
        self.put("tests/test_run.py", HANG_GUARD)
        proc = run(self.root)
        self.assertIn(hang_row(), proc.stdout.splitlines(), "scope: the hang guard was not found")
        self.assertNotIn("UNREAD", proc.stdout, "scope: the fixture was not read")
        self.assertEqual(proc.returncode, 0,
                         "a file whose only finding is a hang guard exits %d, not 0" % proc.returncode)

    def test_hang_guard_is_not_counted_in_the_summary(self):
        self.put("tests/test_run.py", HANG_GUARD)
        proc = run(self.root)
        self.assertIn(hang_row(), proc.stdout.splitlines(), "scope: the hang guard was not found")
        self.assertNotIn("UNREAD", proc.stdout, "scope: the fixture was not read")
        assert_summary(self, proc.stdout, summary_line(0, 0, hang_guards=1))

    def test_hang_guard_file_is_not_a_time_pinned_file(self):
        self.put("tests/test_run.py", HANG_GUARD)
        self.put("tests/test_wait.py", SLEEP_FILE)
        proc = run(self.root)
        lines = proc.stdout.splitlines()
        self.assertIn(hang_row(), lines, "scope: the hang guard was not found")
        self.assertIn("tests/test_wait.py:%d: sleep: time.sleep(1)" % lineno(SLEEP_FILE, "time.sleep(1)"), lines,
                      "scope: the sleep was not found")
        assert_summary(self, proc.stdout, summary_line(1, 1, sleep=1, hang_guards=1))

    def test_hang_guard_stays_listed_in_text(self):
        self.put("tests/test_run.py", HANG_GUARD)
        proc = run(self.root)
        self.assertIn(hang_row(), proc.stdout.splitlines(), "a hang guard is no longer listed in the text output")

    def test_json_still_carries_wait_cap_rows(self):
        self.put("tests/test_run.py", HANG_GUARD)
        code, out = self.report()
        self.assertEqual(self.rows(out), {("tests/test_run.py", lineno(HANG_GUARD, "subprocess.run"), "wait-cap")},
                         "the JSON rows lost the wait-cap finding")
        self.assertEqual(out["counts"]["wait-cap"], 1, "the JSON counts lost the wait-cap")

    def test_test_cap_alone_exits_0(self):
        self.put("tests/test_run.py", TEST_CAP)
        proc = run(self.root)
        assert_cap_rows_listed(self, proc.stdout)
        self.assertEqual(proc.returncode, 0,
                         "a file whose only finding is a test-cap exits %d, not 0" % proc.returncode)

    def test_test_cap_is_not_counted_in_the_summary(self):
        self.put("tests/test_run.py", TEST_CAP)
        proc = run(self.root)
        assert_cap_rows_listed(self, proc.stdout)
        assert_summary(self, proc.stdout, summary_line(0, 0, hang_guards=2))

    def test_test_cap_file_is_not_a_time_pinned_file(self):
        self.put("tests/test_run.py", TEST_CAP)
        self.put("tests/test_wait.py", SLEEP_FILE)
        proc = run(self.root)
        assert_cap_rows_listed(self, proc.stdout)
        self.assertIn("tests/test_wait.py:%d: sleep: time.sleep(1)" % lineno(SLEEP_FILE, "time.sleep(1)"),
                      proc.stdout.splitlines(), "scope: the sleep was not found")
        assert_summary(self, proc.stdout, summary_line(1, 1, sleep=1, hang_guards=2))

    def test_test_cap_stays_listed_in_text(self):
        self.put("tests/test_run.py", TEST_CAP)
        proc = run(self.root)
        missing = sorted(row for row in cap_rows() if row not in proc.stdout.splitlines())
        self.assertFalse(missing, "a test-cap is no longer listed in the text output: %s" % missing)

    def test_json_keeps_test_cap_rows(self):
        self.put("tests/test_run.py", TEST_CAP)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/test_run.py", TEST_CAP,
            ("pytestmark = pytest.mark.timeout(10)", "test-cap"), ("@pytest.mark.timeout(5)", "test-cap"),
        ), "the JSON rows lost a test-cap finding or its category")
        self.assertEqual(out["counts"]["test-cap"], 2, "the JSON counts lost a test-cap")
        self.assertEqual(code, 0, "a file whose only findings are test-caps exits %d, not 0" % code)

    def test_hang_guard_with_an_unread_file_exits_2(self):
        self.put("tests/test_run.py", HANG_GUARD)
        self.put("tests/test_bad.py", "def broken(:\n    pass\n")
        proc = run(self.root)
        self.assertIn(hang_row(), proc.stdout.splitlines(), "scope: the hang guard was not found")
        self.assertIn("UNREAD tests/test_bad.py: ", proc.stdout, "scope: the unread file was not found")
        self.assertEqual(proc.returncode, 2,
                         "a hang guard with an unread file exits %d, not 2" % proc.returncode)


# ---- helper taint, assert arguments, a Playwright wait, an unlistable folder --------------

class HelperTaintTest(FinderCase):
    def test_js_helper_that_reads_a_clock_taints_neither_name_nor_result(self):
        text = src(
            "const until = async (c) => { const s = Date.now(); while (!c() && Date.now() - s < 1000) {} return c(); };",
            "expect(await until(f)).toBe(true);",
        )
        self.put("tests/until.test.js", text)
        code, out = self.report()
        hit = {line for path, line, cat in self.rows(out) if cat == "elapsed-assert"}
        self.assertNotIn(lineno(text, "expect(await until(f))"), hit)

    def test_swift_closure_that_reads_a_clock_taints_neither_name_nor_result(self):
        text = src(
            "import XCTest",
            "final class HelperTests: XCTestCase {",
            "    func testClosure() {",
            "        let h = { () -> Double in let t = Date(); return 1 }",
            "        XCTAssertEqual(h(), 1)",
            "    }",
            "}",
        )
        self.put("Tests/HelperTests.swift", text)
        code, out = self.report()
        hit = {line for path, line, cat in self.rows(out) if cat == "elapsed-assert"}
        self.assertNotIn(lineno(text, "XCTAssertEqual(h(), 1)"), hit)


class AssertArgumentTest(FinderCase):
    def test_python_clock_in_assert_message_or_input_is_clean(self):
        text = src(
            "import time",
            "import unittest",
            "",
            "class MsgTest(unittest.TestCase):",
            "    def test_msg(self):",
            '        self.assertTrue(x, f"{time.time()}")',
            "        self.assertEqual(sweep(now=time.time()), [])",
            "        t0 = time.monotonic()",
            "        assert time.monotonic() - t0 < 1",
        )
        self.put("tests/test_msg.py", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/test_msg.py", text, ("assert time.monotonic() - t0 < 1", "elapsed-assert")))

    def test_js_clock_in_assert_message_or_input_is_clean(self):
        text = src(
            "assert.ok(x, `at ${Date.now()}`);",
            "expect(run(Date.now())).toEqual([]);",
            "const s = Date.now();",
            "expect(Date.now() - s).toBeLessThan(150);",
        )
        self.put("tests/msg.test.js", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/msg.test.js", text, ("expect(Date.now() - s)", "elapsed-assert")))


class WaitForTimeoutTest(FinderCase):
    def test_playwright_wait_for_timeout_is_a_sleep(self):
        text = src(
            "import { test } from '@playwright/test';",
            "test('waits', async ({ page }) => {",
            "  await page.waitForTimeout(500);",
            "});",
        )
        self.put("tests/page.spec.ts", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/page.spec.ts", text, ("page.waitForTimeout(500)", "sleep")))


class UnlistableFolderTest(FinderCase):
    def test_unlistable_folder_is_unread_and_exits_2(self):
        self.put("locked/tests/test_hidden.py", PY_SLEEP + "\n")
        locked = os.path.join(self.root, "locked")
        os.chmod(locked, 0)
        try:
            if os.access(locked, os.R_OK | os.X_OK):
                # Root reads a mode-000 folder, so no permission can make the walk fail here.
                self.skipTest("folder stays readable (running as root); unlisting is not testable")
            proc = run(self.root)
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            unread = [line for line in proc.stdout.splitlines() if line.startswith("UNREAD ") and "locked" in line]
            self.assertTrue(unread, proc.stdout + proc.stderr)
        finally:
            os.chmod(locked, 0o755)


# ---- a duration through a call, a function that returns one, and typed helpers ----------

def elapsed_lines(out):
    return {line for path, line, cat in out_rows(out) if cat == "elapsed-assert"}


def out_rows(out):
    return {(f["path"], f["line"], f["category"]) for f in out["findings"]}


class DurationThroughCallTest(FinderCase):
    def test_swift_duration_operand_inside_a_helper_call_is_flagged(self):
        text = src(
            "import XCTest",
            "final class TraceTests: XCTestCase {",
            "    func testLaunch() {",
            "        let start = Date()",
            "        let end = Date()",
            '        XCTAssertGreaterThanOrEqual(LaunchTrace.ms(end - start), 140, "x")',
            "    }",
            "}",
        )
        self.put("Tests/TraceTests.swift", text)
        out = calendar_judge(self, "Tests/TraceTests.swift", text,
                             listed=["let start = Date()", "let end = Date()"])
        self.assertEqual({row for row in self.rows(out) if row[2] == "elapsed-assert"}, pinned(
            "Tests/TraceTests.swift", text,
            ('XCTAssertGreaterThanOrEqual(LaunchTrace.ms(end - start)', "elapsed-assert")),
            "the elapsed-assert rows are not the pinned set")
        other = sorted(row for row in self.rows(out) if row[2] not in ("calendar", "elapsed-assert"))
        self.assertFalse(other, "a row of another category is listed: %s" % other)

    def test_swift_interval_and_duration_inside_a_call_are_flagged(self):
        text = src(
            "import XCTest",
            "final class SpanTests: XCTestCase {",
            "    func testSpans() {",
            "        let start = ContinuousClock.now",
            "        let end = ContinuousClock.now",
            "        XCTAssertLessThan(LaunchTrace.ms(end.timeIntervalSince(start)), 9)",
            "        XCTAssertLessThan(LaunchTrace.ms(start.duration(to: end)), 9)",
            "    }",
            "}",
        )
        self.put("Tests/SpanTests.swift", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "Tests/SpanTests.swift", text,
            ("XCTAssertLessThan(LaunchTrace.ms(end.timeIntervalSince", "elapsed-assert"),
            ("XCTAssertLessThan(LaunchTrace.ms(start.duration(to: end))", "elapsed-assert")))

    def test_js_duration_inside_a_helper_call_is_flagged(self):
        text = src(
            "const t0 = Date.now();",
            "expect(toMs(Date.now() - t0)).toBeLessThan(100);",
        )
        self.put("tests/span.test.js", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/span.test.js", text,
            ("expect(toMs(Date.now() - t0))", "elapsed-assert")))

    def test_python_duration_inside_a_helper_call_is_flagged(self):
        text = src(
            "import time",
            "",
            "def test_latency():",
            "    t0 = time.time()",
            "    assert to_ms(time.time() - t0) < 100",
        )
        self.put("tests/test_latency.py", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/test_latency.py", text,
            ("assert to_ms(time.time() - t0) < 100", "elapsed-assert")))

    def test_js_function_whose_return_reads_a_clock_taints_its_call(self):
        text = src(
            "const time = async (q) => { const from = performance.now(); await run(q); return performance.now() - from; };",
            "assert.ok(await time(sql) >= 250);",
        )
        self.put("tests/time.test.js", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/time.test.js", text,
            ("assert.ok(await time(sql) >= 250);", "elapsed-assert")))

    def test_js_clock_alias_is_flagged(self):
        text = src(
            "const now = () => performance.now();",
            "const t0 = now();",
            "expect(now() - t0).toBeLessThan(100);",
        )
        self.put("tests/alias.test.js", text)
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "tests/alias.test.js", text,
            ("expect(now() - t0)", "elapsed-assert")))


class TypedHelperCleanTest(FinderCase):
    def test_typed_wait_helpers_taint_neither_name_nor_result(self):
        text = src(
            "const until = async (fn: () => boolean): Promise<boolean> => { const t0 = Date.now(); while (!fn() && Date.now() - t0 < 1000) {} return fn(); };",
            "expect(await until(f)).toBe(true);",
            "const untilT = async <T>(fn: () => T) => { const t0 = Date.now(); while (!fn() && Date.now() - t0 < 1000) {} return fn(); };",
            "expect(await untilT(f)).toBe(true);",
            "const ms0 = () => 1000;",
            "const untilMs = async (fn, ms = ms0()) => { const t0 = Date.now(); while (!fn() && Date.now() - t0 < ms) {} return fn(); };",
            "expect(await untilMs(f)).toBe(true);",
        )
        self.put("tests/until.test.ts", text)
        code, out = self.report()
        hit = elapsed_lines(out)
        for needle in ("expect(await until(f))", "expect(await untilT(f))", "expect(await untilMs(f))"):
            self.assertNotIn(lineno(text, needle), hit, needle)


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)
