#!/usr/bin/env python3
"""Cases for lint/find_time_pinned.py. Standard library only.

    python3 lint/test_find_time_pinned.py

Each case writes a small fixture folder of plain files under the run folder and runs the real finder
on it. The cases cover the four categories for Python, JS/TS and Swift, the must-stay-clean list, the
scanner traps of building-scanner-respects-strings, test-file selection, the text and JSON output, and
the exit codes, and the keep marker. The JS trap table that the scanner suite shares is in lint/test_scanner_traps.mjs.
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
SWIFT_CLOCKS = [
    "Date()", "CFAbsoluteTimeGetCurrent()", "DispatchTime.now()",
    "ProcessInfo.processInfo.systemUptime", "mach_absolute_time()",
    "ContinuousClock.now", "SuspendingClock.now",
    "start.timeIntervalSinceNow", "start.duration(to: .now)",
]
SUMMARY_ZERO = "0 time-pinned in 0 files (sleep 0, elapsed-assert 0, test-cap 0, wait-cap 0); 0 unread"


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
            *[(f"assert {c}() > t", "elapsed-assert") for c in PY_CLOCKS]))

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
            ("assert.strictEqual(hr.length", "elapsed-assert"),
        ))

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
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "Tests/TimingTests.swift", text,
            *[(f"XCTAssertLessThan(t{i}, 9)", "elapsed-assert") for i in range(len(SWIFT_CLOCKS))],
            ("XCTAssertLessThan(elapsed, 1.0)", "elapsed-assert"),
            ("#expect(elapsed < 2)", "elapsed-assert"),
        ))

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
    def test_patterns_in_comments_and_strings_are_clean(self):
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
        self.assertEqual((code, self.rows(out)), (0, set()))


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
        self.assertEqual(
            lines[-1],
            "2 time-pinned in 1 files (sleep 1, elapsed-assert 0, test-cap 0, wait-cap 1); 0 unread")

    def test_summary_line_for_an_empty_root(self):
        proc = run(self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.splitlines()[-1], SUMMARY_ZERO)

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
        self.assertEqual(out["counts"], {"sleep": 1, "elapsed-assert": 1, "test-cap": 1, "wait-cap": 1})
        proc = run(self.root)
        self.assertEqual(proc.stdout.splitlines()[-1],
                         "4 time-pinned in 1 files (sleep 1, elapsed-assert 1, test-cap 1, wait-cap 1); 0 unread")

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
        self.assertEqual(out["counts"], {"sleep": 1, "elapsed-assert": 0, "test-cap": 0, "wait-cap": 0})


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
        code, out = self.report()
        self.assertEqual(self.rows(out), pinned(
            "Tests/TraceTests.swift", text,
            ('XCTAssertGreaterThanOrEqual(LaunchTrace.ms(end - start)', "elapsed-assert")))

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


# ---- the keep marker: `# time-pinned-ok: <reason>` (Python), `// time-pinned-ok: <reason>` (JS, TS, Swift) ----
# A comment on a finding's own line keeps it out of the list for sleep, elapsed-assert and wait-cap. A blank
# reason keeps nothing. The red cases fail on their marked line. Each control stays green on the old code.
# Each case has an unmarked sibling that must still list, so a failure names the marker, not a broken read.

MIXED_KEPT = src(
    "import time",
    "",
    "def test_mixed(p):",
    "    time.sleep(1)  # time-pinned-ok: poll gap",
    "    t0 = time.monotonic()",
    "    assert time.monotonic() - t0 < 2  # time-pinned-ok: budget checked in a manual run",
    "    p.wait(timeout=3)  # time-pinned-ok: child exits fast",
    "    time.sleep(4)",
)


class KeepMarkerPythonTest(FinderCase):
    def test_sleep_with_marker_and_reason_is_kept(self):
        text = src(
            "import time",
            "",
            "def test_wait():",
            "    time.sleep(1)  # time-pinned-ok: poll gap of a condition wait",
            "    time.sleep(2)",
        )
        self.put("tests/test_kept_sleep.py", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/test_kept_sleep.py", text, ("time.sleep(2)", "sleep")),
            "a sleep with a marker and a reason still lists")

    def test_elapsed_assert_with_marker_and_reason_is_kept(self):
        text = src(
            "import time",
            "",
            "def test_budget():",
            "    t0 = time.monotonic()",
            "    assert time.monotonic() - t0 < 1  # time-pinned-ok: budget read in a manual run",
            "    assert time.monotonic() - t0 < 2",
        )
        self.put("tests/test_kept_elapsed.py", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/test_kept_elapsed.py", text, ("t0 < 2", "elapsed-assert")),
            "an elapsed-assert with a marker and a reason still lists")

    def test_wait_cap_with_marker_and_reason_is_kept(self):
        text = src(
            "def test_waits(p, q):",
            "    p.wait(timeout=3)  # time-pinned-ok: child exits within a second",
            "    q.get(timeout=1)",
        )
        self.put("tests/test_kept_wait.py", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/test_kept_wait.py", text, ("q.get(timeout=1)", "wait-cap")),
            "a wait-cap with a marker and a reason still lists")

    def test_reason_with_a_quote_and_a_hash_is_kept(self):
        text = src(
            "import time",
            "",
            "def test_wait():",
            "    time.sleep(1)  # time-pinned-ok: don't wait on load # see http://a.test/",
            "    time.sleep(2)",
        )
        self.put("tests/test_reason_text.py", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/test_reason_text.py", text, ("time.sleep(2)", "sleep")),
            "a marker whose reason holds a quote or a hash still lists")

    def test_hash_in_a_string_before_a_real_marker_is_kept(self):
        text = src(
            "import time",
            "",
            "def test_tag():",
            '    tag = "a # b"; time.sleep(2)  # time-pinned-ok: real reason',
            "    time.sleep(3)",
        )
        self.put("tests/test_hash_string.py", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/test_hash_string.py", text, ("time.sleep(3)", "sleep")),
            "a sleep whose real marker follows a hash in a string still lists")

    def test_real_poll_sleep_is_kept(self):
        text = src(
            "import subprocess",
            "import time",
            "",
            "def stranded_pid(pid):",
            "    answer = subprocess.run(['sh', '-c', 'true'], timeout=20)",
            "    for _ in range(100):",
            "        ppid, pgid = subprocess.run(['ps', '-o', 'ppid=,pgid=', '-p', str(pid)], capture_output=True, text=True, timeout=5).stdout.split()",
            "        if ppid != '1':",
            "            return None",
            "        if pgid == str(pid):",
            "            return pid",
            "        time.sleep(0.05)  # time-pinned-ok: poll gap of a condition wait: ends when the pgid reads back, "
            "not on elapsed time",
            "    return None",
            "",
            "def free_text_poll(pid):",
            "    for _ in range(100):",
            "        time.sleep(0.1)  # poll gap of a condition wait: ends when the pgid reads back, not on elapsed time",
            "    return None",
        )
        self.put("tests/guard/s05163-kill.py", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/guard/s05163-kill.py", text,
            ("timeout=20", "wait-cap"), ("timeout=5)", "wait-cap"), ("time.sleep(0.1)", "sleep")),
            "the kept poll sleep still lists")


class KeepMarkerPythonControlTest(FinderCase):
    def test_empty_or_blank_reason_still_lists(self):
        text = src(
            "import time",
            "",
            "def test_x():",
            "    time.sleep(1)  # time-pinned-ok:",
            "    time.sleep(2)  # time-pinned-ok:    ",
            "    time.sleep(3)",
        )
        self.put("tests/test_blank_reason.py", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/test_blank_reason.py", text,
            ("time.sleep(1)", "sleep"), ("time.sleep(2)", "sleep"), ("time.sleep(3)", "sleep")),
            "a marker with a blank reason is kept")

    def test_marker_on_another_line_still_lists(self):
        text = src(
            "import time",
            "",
            "def test_x():",
            "    # time-pinned-ok: the reason is on the line above",
            "    time.sleep(1)",
            "    time.sleep(2)",
            "    # time-pinned-ok: the reason is on the line below",
        )
        self.put("tests/test_other_line.py", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/test_other_line.py", text, ("time.sleep(1)", "sleep"), ("time.sleep(2)", "sleep")),
            "a marker on another line keeps the sleep")

    def test_marker_text_in_a_string_on_the_sleep_line_still_lists(self):
        text = src(
            "import time",
            "",
            "def test_x():",
            '    note = "# time-pinned-ok: a reason"; time.sleep(1)',
            "    time.sleep(2)",
        )
        self.put("tests/test_string_marker.py", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/test_string_marker.py", text, ("time.sleep(1)", "sleep"), ("time.sleep(2)", "sleep")),
            "a marker inside a string is read as a comment")

    def test_marker_in_a_triple_quoted_string_still_lists(self):
        text = src(
            "import time",
            "",
            "def test_doc():",
            '    doc = """first',
            '# time-pinned-ok: reason"""; time.sleep(1)',
            "    time.sleep(2)",
        )
        self.put("tests/test_triple_marker.py", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/test_triple_marker.py", text, ("time.sleep(1)", "sleep"), ("time.sleep(2)", "sleep")),
            "a marker inside a triple-quoted string is read as a comment")

    def test_marker_in_a_string_opened_on_the_sleep_line_still_lists(self):
        text = src(
            "import time",
            "",
            "def test_doc():",
            '    time.sleep(1); doc = """first',
            "# time-pinned-ok: reason",
            '"""',
            "    time.sleep(2)",
        )
        self.put("tests/test_opener_marker.py", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/test_opener_marker.py", text, ("time.sleep(1)", "sleep"), ("time.sleep(2)", "sleep")),
            "a marker in a string keeps the sleep on the line where the string opens")


class KeepMarkerTestCapTest(FinderCase):
    def test_marked_test_cap_is_kept_and_counted(self):
        text = src(
            "import time",
            "import pytest",
            "",
            "pytestmark = pytest.mark.timeout(10)  # time-pinned-ok: suite runs under a fixed budget",
            "",
            "def test_x():",
            "    time.sleep(1)",
        )
        path = "tests/test_kept_cap.py"
        self.put(path, text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(path, text, ("time.sleep(1)", "sleep")),
                         "a test-cap with a marker and a reason still lists")
        proc = run(self.root)
        last = proc.stdout.splitlines()[-1]
        self.assertTrue(last.startswith("1 time-pinned in 1 files (sleep 1, elapsed-assert 0, test-cap 0, wait-cap 0)"),
                        "the summary counts a kept test-cap: " + last)
        self.assertIn("kept 1", last, "the summary does not count the kept test-cap")

    def test_unmarked_test_cap_still_lists(self):
        text = src(
            "import time",
            "import pytest",
            "",
            "pytestmark = pytest.mark.timeout(10)",
            "",
            "def test_x():",
            "    time.sleep(1)",
        )
        path = "tests/test_unkept_cap.py"
        self.put(path, text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            path, text, ("pytestmark = pytest.mark.timeout(10)", "test-cap"), ("time.sleep(1)", "sleep")),
            "an unmarked test-cap no longer lists")


class KeepMarkerJsTest(FinderCase):
    def test_sleep_after_settimeout_or_sleep_with_marker_is_kept(self):
        text = src(
            "test('waits', async () => {",
            "  await new Promise((r) => setTimeout(r, 500)); // time-pinned-ok: poll gap of a condition wait",
            "  await sleep(250); // time-pinned-ok: fixed gap for a manual repro",
            "  await sleep(100);",
            "});",
        )
        self.put("tests/waits.test.js", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/waits.test.js", text, ("await sleep(100)", "sleep")),
            "a setTimeout or sleep with a marker and a reason still lists")

    def test_elapsed_assert_with_marker_and_reason_is_kept(self):
        text = src(
            "const t0 = Date.now();",
            "expect(Date.now() - t0).toBeLessThan(100); // time-pinned-ok: budget checked in a manual run",
            "expect(Date.now() - t0).toBeLessThan(200);",
        )
        self.put("tests/timing.test.js", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/timing.test.js", text, ("toBeLessThan(200)", "elapsed-assert")),
            "an elapsed-assert with a marker and a reason still lists")

    def test_wait_cap_with_marker_and_reason_is_kept(self):
        text = src(
            "await waitFor(() => ready(), { timeout: 2000 });",
            "execFileSync(cmd, args, { timeout: 5000 }); // time-pinned-ok: child exits within a second",
        )
        self.put("tests/caps.test.js", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/caps.test.js", text, ("timeout: 2000", "wait-cap")),
            "a wait-cap with a marker and a reason still lists")

    def test_slashes_in_a_string_before_a_real_marker_is_kept(self):
        text = src(
            'const u = "http://a.test/"; await sleep(300); // time-pinned-ok: real reason',
            "await sleep(400);",
        )
        self.put("tests/slash_string.test.js", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/slash_string.test.js", text, ("await sleep(400)", "sleep")),
            "a sleep whose real marker follows a // in a string still lists")

    def test_lone_quote_in_jsx_text_does_not_hide_a_real_marker(self):
        text = src(
            "export const Note = () => <p>Don't stop; await sleep(250); // time-pinned-ok: real reason",
            "export const Other = () => <p>It's</p>; await sleep(100);",
        )
        self.put("tests/note.test.tsx", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/note.test.tsx", text, ("await sleep(100)", "sleep")),
            "a lone quote in JSX text hides a real marker, or the sleep after it still lists")


class KeepMarkerJsControlTest(FinderCase):
    def test_empty_or_blank_reason_still_lists(self):
        text = src(
            "test('x', async () => {",
            "  await sleep(250); // time-pinned-ok:",
            "  await sleep(100); // time-pinned-ok:   ",
            "  await sleep(300);",
            "});",
        )
        self.put("tests/blank.test.js", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/blank.test.js", text,
            ("await sleep(250)", "sleep"), ("await sleep(100)", "sleep"), ("await sleep(300)", "sleep")),
            "a marker with a blank reason is kept")

    def test_marker_text_in_a_string_after_the_call_still_lists(self):
        text = src(
            'await sleep(250); const note = "// time-pinned-ok: a reason";',
            "await sleep(100);",
        )
        self.put("tests/string_marker.test.js", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/string_marker.test.js", text, ("await sleep(250)", "sleep"), ("await sleep(100)", "sleep")),
            "a marker inside a string is read as a comment")

    def test_marker_in_a_multi_line_template_still_lists(self):
        text = src(
            "const doc = `first line",
            "// time-pinned-ok: reason`; await sleep(100);",
            "await sleep(300);",
        )
        self.put("tests/template_marker.test.js", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/template_marker.test.js", text, ("await sleep(100)", "sleep"), ("await sleep(300)", "sleep")),
            "a marker inside a multi-line template is read as a comment")

    def test_marker_in_a_block_comment_still_lists(self):
        text = src(
            "await sleep(250); /* time-pinned-ok: reason */",
            "await sleep(100);",
        )
        self.put("tests/block.test.js", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/block.test.js", text, ("await sleep(250)", "sleep"), ("await sleep(100)", "sleep")),
            "a marker in a block comment is read as a keep marker")

    def test_marker_in_a_regex_literal_still_lists(self):
        text = src(
            "const re = /time-pinned-ok: reason/; await sleep(250);",
            "await sleep(100);",
        )
        self.put("tests/regex.test.js", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/regex.test.js", text, ("await sleep(250)", "sleep"), ("await sleep(100)", "sleep")),
            "a marker in a regex literal is read as a keep marker")


class KeepMarkerSwiftTest(FinderCase):
    def test_sleep_with_marker_and_reason_is_kept(self):
        text = src(
            "import XCTest",
            "final class KeptWaitTests: XCTestCase {",
            "    func testWaits() {",
            "        Thread.sleep(forTimeInterval: 0.7) // time-pinned-ok: poll gap of a condition wait",
            "        Thread.sleep(forTimeInterval: 0.5)",
            "    }",
            "}",
        )
        self.put("Tests/KeptWaitTests.swift", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "Tests/KeptWaitTests.swift", text, ("forTimeInterval: 0.5)", "sleep")),
            "a sleep with a marker and a reason still lists")

    def test_elapsed_assert_with_marker_and_reason_is_kept(self):
        text = src(
            "import XCTest",
            "final class KeptTimingTests: XCTestCase {",
            "    func testElapsed() {",
            "        let start = Date()",
            "        let elapsed = Date().timeIntervalSince(start)",
            "        XCTAssertLessThan(elapsed, 1.0) // time-pinned-ok: budget checked in a manual run",
            "        XCTAssertLessThan(elapsed, 2.0)",
            "    }",
            "}",
        )
        self.put("Tests/KeptTimingTests.swift", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "Tests/KeptTimingTests.swift", text, ("XCTAssertLessThan(elapsed, 2.0)", "elapsed-assert")),
            "an elapsed-assert with a marker and a reason still lists")

    def test_wait_cap_with_marker_and_reason_is_kept(self):
        text = src(
            "import XCTest",
            "final class KeptWaitCapTests: XCTestCase {",
            "    func testAsync() {",
            "        waitForExpectations(timeout: 3) // time-pinned-ok: expectation fulfils in the same run",
            "        wait(for: [exp], timeout: 2)",
            "    }",
            "}",
        )
        self.put("Tests/KeptWaitCapTests.swift", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "Tests/KeptWaitCapTests.swift", text, ("wait(for: [exp], timeout: 2)", "wait-cap")),
            "a wait-cap with a marker and a reason still lists")


class KeepMarkerSwiftControlTest(FinderCase):
    def test_marker_text_in_a_string_still_lists(self):
        text = src(
            "import XCTest",
            "final class StringTests: XCTestCase {",
            "    func testStrings() {",
            '        let note = "// time-pinned-ok: a reason"; Thread.sleep(forTimeInterval: 0.3)',
            "        Thread.sleep(forTimeInterval: 0.9)",
            "    }",
            "}",
        )
        self.put("Tests/StringTests.swift", text)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "Tests/StringTests.swift", text,
            ("forTimeInterval: 0.3)", "sleep"), ("forTimeInterval: 0.9)", "sleep")),
            "a marker inside a string is read as a comment")


class KeepMarkerOutputTest(FinderCase):
    def test_summary_excludes_kept_lines_and_says_how_many(self):
        self.put("tests/test_mixed.py", MIXED_KEPT)
        proc = run(self.root)
        lines = proc.stdout.splitlines()
        self.assertIn("tests/test_mixed.py:%d: sleep: time.sleep(4)" % lineno(MIXED_KEPT, "time.sleep(4)"), lines,
                      "the unmarked sleep is missing from the text output")
        kept = [lineno(MIXED_KEPT, n) for n in ("time.sleep(1)", "t0 < 2", "p.wait(timeout=3)")]
        self.assertFalse([line for line in lines if any(line.startswith("tests/test_mixed.py:%d:" % k)
                                                        for k in kept)],
                         "a kept line is printed in the text output")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertTrue(lines[-1].startswith(
            "1 time-pinned in 1 files (sleep 1, elapsed-assert 0, test-cap 0, wait-cap 0)"),
            "the summary counts a kept line: " + lines[-1])
        self.assertIn("kept 3", lines[-1], "the summary does not say how many lines were kept")

    def test_json_omits_kept_findings_and_counts_only_listed(self):
        self.put("tests/test_mixed.py", MIXED_KEPT)
        code, out = self.report()
        self.assertEqual(out["unread"], [], "the fixture is not read")
        self.assertEqual(self.rows(out), pinned(
            "tests/test_mixed.py", MIXED_KEPT, ("time.sleep(4)", "sleep")),
            "a kept line is still in the JSON findings")
        self.assertEqual(out["counts"], {"sleep": 1, "elapsed-assert": 0, "test-cap": 0, "wait-cap": 0},
                         "the JSON counts include a kept line")

    def test_exit_0_when_only_kept_lines_remain(self):
        text = src(
            "import time",
            "",
            "def test_x(p):",
            "    time.sleep(1)  # time-pinned-ok: poll gap",
            "    p.wait(timeout=3)  # time-pinned-ok: child exits fast",
        )
        self.put("tests/test_only_kept.py", text)
        proc = run(self.root)
        lines = proc.stdout.splitlines()
        self.assertIn("kept 2", lines[-1], "the summary does not say how many lines were kept")
        self.assertEqual(proc.returncode, 0, "only kept lines remain, so the exit is not 0\n" + proc.stdout)

    def test_many_kept_lines_are_all_counted(self):
        lines = ["import time", "", "def test_many():"]
        lines += ["    time.sleep(%d)  # time-pinned-ok: poll gap %d" % (n, n) for n in range(1, 51)]
        lines += ["    time.sleep(999)"]
        text = src(*lines)
        self.put("tests/test_many.py", text)
        proc = run(self.root)
        out_lines = proc.stdout.splitlines()
        self.assertIn("tests/test_many.py:%d: sleep: time.sleep(999)" % lineno(text, "time.sleep(999)"), out_lines,
                      "the unmarked sleep is missing from the text output")
        self.assertTrue(out_lines[-1].startswith("1 time-pinned in 1 files (sleep 1,"),
                        "the summary counts the kept lines: " + out_lines[-1])
        self.assertIn("kept 50", out_lines[-1], "the summary does not count all 50 kept lines")


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)
