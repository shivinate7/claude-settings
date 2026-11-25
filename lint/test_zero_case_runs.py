#!/usr/bin/env python3
"""A run of zero cases must exit non-zero, for the hand runners and for the mods test collector.

A hand runner prints its own `PASS: N of N` line and exits 0 when its case list is empty, so a suite
that lost every case still passes when run directly. CI runs most steps without bin/verdict, the one
place that fails a run of zero tests. So each hand runner here runs with its case lists emptied, and
must exit non-zero without a traceback. The token-weather collector runs with every `await test(`
disabled, and must exit non-zero too.

The runner's case lists are emptied by a driver in the run folder: it loads the runner file as a module
(not as __main__), sets each case list it finds to an empty one of the same type, then calls main().
A runner that loads its cases in another name must be added to CASE_LISTS.
"""
import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  the one home of the run folder and its sweep (lint/_test_temp.py)

TIMEOUT = 300  # seconds for one runner; a hang guard well above a runner's run
CASE_LISTS = ("CASES", "RED_CASES", "GENERAL_CASES", "BAD_CASES")
# Not listed: hooks/test_guard.py, whose cases come from section files on disk and not from a case list,
# and lint/check_guardset_lists.py, which with no case names runs hooks/test_install_src.sh whole.
RUNNERS = [
    "hooks/test_config_watch_fast_exit.py",
    "hooks/test_shared_names.py",
    "hooks/test_rm_prompt_answer.py",
    "hooks/test_page_link_check.py",
    "hooks/test_config_watch.py",
    "hooks/test_agent_brief.py",
    "hooks/test_guard_load_os.py",
    "hooks/test_feedback_inbox.py",
    "hooks/test_waiting_export.py",
    "hooks/test_wrappers.py",
    "hooks/test_reply_judge.py",
]
MODS_TEST = os.path.join("mods", "token-weather", "token-weather.test.mjs")
DISABLE_FROM = "await test("  # every case in the collector starts with this call

DRIVER = '''import importlib.util, os, sys
path = os.path.abspath(sys.argv[1])
sys.argv = [path]
sys.path.insert(0, os.path.dirname(path))
spec = importlib.util.spec_from_file_location("runner_under_test", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
for name in %r:
    if hasattr(mod, name):
        value = getattr(mod, name)
        setattr(mod, name, type(value)())
sys.exit(mod.main())
''' % (CASE_LISTS,)


def setUpModule():
    global RUN
    RUN = _test_temp.run_folder()
    with open(os.path.join(RUN, "drive_runner.py"), "w", encoding="utf-8") as f:
        f.write(DRIVER)


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)


class HandRunnersWithNoCases(unittest.TestCase):
    def test_each_runner_exits_nonzero_when_its_cases_are_emptied(self):
        driver = os.path.join(RUN, "drive_runner.py")
        for path in RUNNERS:
            with self.subTest(runner=path):
                proc = subprocess.run([sys.executable, driver, path], cwd=REPO, capture_output=True,
                                      text=True, timeout=TIMEOUT)
                last = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or ["<no output>"]
                self.assertNotEqual(proc.returncode, 0,
                                    "%s exits 0 with zero cases run: its last line is %r" % (path, last[0]))
                self.assertNotIn("Traceback", proc.stderr, "%s crashed with zero cases, not failed" % path)


class TokenWeatherCollectorWithNoTests(unittest.TestCase):
    def test_collector_exits_nonzero_when_every_test_is_disabled(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not on PATH: the token-weather zero-test case skips here")
        with open(os.path.join(REPO, MODS_TEST), encoding="utf-8") as f:
            source = f.read()
        self.assertGreater(source.count(DISABLE_FROM), 0,
                           "%s has no `await test(` call to disable, so no zero-test run can be made" % MODS_TEST)
        variant = os.path.join(RUN, "token_weather_zero.test.mjs")
        with open(variant, "w", encoding="utf-8") as f:
            f.write(source.replace(DISABLE_FROM, "if (false) " + DISABLE_FROM))
        proc = subprocess.run([node, variant], cwd=RUN, capture_output=True, text=True, timeout=TIMEOUT)
        last = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or ["<no output>"]
        self.assertNotEqual(proc.returncode, 0,
                            "token-weather collector exits 0 with zero tests run: its last line is %r" % last[0])


if __name__ == "__main__":
    unittest.main()
