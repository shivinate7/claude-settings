#!/usr/bin/env python3
"""Fixture cases for lint/check_suites_have_main.py, and a run of it on this repo.

A test file that defines a unittest.TestCase but never calls unittest.main does nothing when it is run
directly: its cases never run, and the run still reads as a pass. problems(root) names each such file as
"<path>: defines a TestCase but never calls unittest.main". The checker reads each file with ast, so a
TestCase named only in a string or a comment is no class, and a script with no TestCase is no suite.

The fixtures are built in the run folder, one folder per case, each holding only its own file.
"""
import contextlib
import importlib.util
import io
import os
import shutil
import sys
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  the one home of the run folder and its sweep (lint/_test_temp.py)
sys.path.insert(0, os.path.join(REPO, "testing"))
import cost_probe  # noqa: E402  the one home of run_class (testing/cost_probe.py)

CHECKER = os.path.join(REPO, "lint", "check_suites_have_main.py")
SUFFIX = "defines a TestCase but never calls unittest.main"

SUITE_WITHOUT_MAIN = (
    "import unittest\n"
    "\n"
    "\n"
    "class Cases(unittest.TestCase):\n"
    "    def test_one(self):\n"
    "        self.assertTrue(True)\n"
)
SUITE_WITH_MAIN = SUITE_WITHOUT_MAIN + (
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    unittest.main()\n"
)
SCRIPT_WITHOUT_SUITE = (
    "import sys\n"
    "\n"
    "print('hello from a script')\n"
    "sys.exit(0)\n"
)
MENTIONS_ONLY = (
    "# from unittest import TestCase\n"
    '# class Cases(unittest.TestCase): pass\n'
    'NOTE = "class Cases(unittest.TestCase):\\n    pass"\n'
    "print(NOTE)\n"
)
MAIN_UNDER_IF_FALSE = SUITE_WITHOUT_MAIN + (
    "\n"
    "\n"
    "if False:\n"
    "    unittest.main()\n"
)
MAIN_IN_UNCALLED_FUNCTION = SUITE_WITHOUT_MAIN + (
    "\n"
    "\n"
    "def main():\n"
    "    unittest.main()\n"
)
MAIN_IN_FUNCTION_CALLED_FROM_GUARD = SUITE_WITHOUT_MAIN + (
    "\n"
    "\n"
    "def main():\n"
    "    unittest.main()\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    main()\n"
)
RUNNER_RESULT_SETS_EXIT_CODE = "import sys\n" + SUITE_WITHOUT_MAIN + (
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Cases))\n"
    "    sys.exit(0 if result.wasSuccessful() else 1)\n"
)

RUN_CLASS_ATTRIBUTE_UNDER_MAIN = "import sys\nimport cost_probe\n" + SUITE_WITHOUT_MAIN + (
    "\n"
    "\n"
    "def main():\n"
    "    return 0 if cost_probe.run_class(Cases) else 1\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    sys.exit(main())\n"
)
# The shape of hooks/test_local_time.py: run_class sits in a case function, and run_cases is handed that function by name
# inside a list that suite_cases() returns. No call reaches case_cost_tests, so the walk from the __main__ block misses it.
RUN_CLASS_IN_A_LISTED_CASE = (
    "import sys\n"
    "import unittest\n"
    "import cost_probe\n"
    "from case_runner_test import run_cases\n"
    "\n"
    "\n"
    "class CostTests(unittest.TestCase):\n"
    "    def test_one(self):\n"
    "        self.assertTrue(True)\n"
    "\n"
    "\n"
    "def case_cost_tests():\n"
    "    if cost_probe.run_class(CostTests):\n"
    "        return None\n"
    "    return ['the CostTests class has a failing case']\n"
    "\n"
    "\n"
    "def suite_cases():\n"
    "    return [case_cost_tests]\n"
    "\n"
    "\n"
    "def main():\n"
    "    return run_cases(suite_cases())\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    sys.exit(main())\n"
)


ASYNC_TESTCASE_BASE = (
    "import unittest\n"
    "\n"
    "\n"
    "class Cases(unittest.IsolatedAsyncioTestCase):\n"
    "    async def test_one(self):\n"
    "        self.assertTrue(True)\n"
)
NOT_EQUAL_MAIN_GUARD = SUITE_WITHOUT_MAIN + (
    "\n"
    "\n"
    'if __name__ != "__main__":\n'
    "    unittest.main()\n"
)
FROM_UNITTEST_IMPORT_MAIN = (
    "from unittest import main\n"
    "import unittest\n"
    "\n"
    "\n"
    "class Cases(unittest.TestCase):\n"
    "    def test_one(self):\n"
    "        self.assertTrue(True)\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    main()\n"
)


BARE_RUN_CASES = (
    "from case_runner_test import run_cases\n"
    "\n"
    "\n"
    "def case_one():\n"
    "    return None\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    run_cases([case_one])\n"
)
RUN_CASES_IN_SYS_EXIT = (
    "import sys\n"
    "from case_runner_test import run_cases\n"
    "\n"
    "\n"
    "def case_one():\n"
    "    return None\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    sys.exit(run_cases([case_one]))\n"
)
RUN_CASES_ASSIGNED = (
    "import sys\n"
    "from case_runner_test import run_cases\n"
    "\n"
    "\n"
    "def case_one():\n"
    "    return None\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    rc = run_cases([case_one])\n"
    "    sys.exit(rc)\n"
)
RUN_CASES_OR_ASSIGNED = (
    "import sys\n"
    "from case_runner_test import run_cases\n"
    "\n"
    "\n"
    "def case_one():\n"
    "    return None\n"
    "\n"
    "\n"
    "def main():\n"
    "    failed = 0\n"
    "    failed |= run_cases([case_one])\n"
    "    return failed\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    sys.exit(main())\n"
)
RUN_CASES_RETURNED = (
    "import sys\n"
    "from case_runner_test import run_cases\n"
    "\n"
    "\n"
    "def case_one():\n"
    "    return None\n"
    "\n"
    "\n"
    "def main():\n"
    "    return run_cases([case_one])\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    sys.exit(main())\n"
)


BARE_ATTRIBUTE_RUN_CASES = (
    "import case_runner_test as m\n"
    "\n"
    "\n"
    "def case_one():\n"
    "    return None\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    m.run_cases([case_one])\n"
)
ASSIGNED_ATTRIBUTE_RUN_CASES = (
    "import sys\n"
    "import case_runner_test as m\n"
    "\n"
    "\n"
    "def case_one():\n"
    "    return None\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    code = m.run_cases([case_one])\n"
    "    sys.exit(code)\n"
)


def tree(name, files):
    """A fresh folder in the run folder holding the given test files, each at its relative path (posix form)."""
    root = os.path.join(RUN, name)
    for rel, text in files.items():
        path = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return root


def checker():
    """The checker module. It is loaded from lint/check_suites_have_main.py by path, as the other lint tests load tools."""
    spec = importlib.util.spec_from_file_location("check_suites_have_main", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(name, text):
    """A fresh folder in the run folder holding one test file: the checker reads only this file."""
    root = os.path.join(RUN, name)
    os.makedirs(root)
    with open(os.path.join(root, "test_one.py"), "w", encoding="utf-8") as f:
        f.write(text)
    return root


def setUpModule():
    global RUN
    RUN = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)


class FixtureCases(unittest.TestCase):
    def test_suite_without_main_is_a_problem(self):
        found = checker().problems(fixture("without_main", SUITE_WITHOUT_MAIN))
        self.assertEqual(len(found), 1, "want one problem for a TestCase with no unittest.main, got %r" % found)
        self.assertTrue(found[0].endswith("test_one.py: " + SUFFIX), "problem text is %r" % found[0])

    def test_suite_with_main_is_clean(self):
        found = checker().problems(fixture("with_main", SUITE_WITH_MAIN))
        self.assertEqual(found, [], "a TestCase that calls unittest.main is reported: %r" % found)

    def test_script_without_a_suite_is_clean(self):
        found = checker().problems(fixture("script", SCRIPT_WITHOUT_SUITE))
        self.assertEqual(found, [], "a script with no TestCase is reported: %r" % found)

    def test_mention_in_string_or_comment_is_clean(self):
        found = checker().problems(fixture("mentions", MENTIONS_ONLY))
        self.assertEqual(found, [], "a TestCase named only in a string or comment is reported: %r" % found)

    def test_main_only_under_if_false_is_a_problem(self):
        found = checker().problems(fixture("main_under_if_false", MAIN_UNDER_IF_FALSE))
        self.assertEqual(len(found), 1, "a unittest.main() that never runs under if False: counts as a call: %r" % found)
        self.assertTrue(found[0].endswith("test_one.py: " + SUFFIX), "problem text is %r" % found[0])

    def test_main_in_uncalled_function_is_a_problem(self):
        found = checker().problems(fixture("main_in_uncalled_function", MAIN_IN_UNCALLED_FUNCTION))
        self.assertEqual(len(found), 1, "a unittest.main() inside a function nothing calls counts as a call: %r" % found)
        self.assertTrue(found[0].endswith("test_one.py: " + SUFFIX), "problem text is %r" % found[0])

    def test_main_in_function_called_from_guard_is_clean(self):
        found = checker().problems(fixture("main_in_called_function", MAIN_IN_FUNCTION_CALLED_FROM_GUARD))
        self.assertEqual(found, [], "a unittest.main() in a function the __main__ block calls is reported: %r" % found)

    def test_text_runner_result_sets_exit_code_is_clean(self):
        found = checker().problems(fixture("text_runner_exit_code", RUNNER_RESULT_SETS_EXIT_CODE))
        self.assertEqual(found, [], "a TextTestRunner run under the __main__ block is reported: %r" % found)

    def test_run_class_attribute_call_under_main_is_clean(self):
        found = checker().problems(fixture("run_class_attribute", RUN_CLASS_ATTRIBUTE_UNDER_MAIN))
        self.assertEqual(found, [], "a TestCase run by cost_probe.run_class under the __main__ block is reported: %r" % found)

    def test_run_class_in_a_case_run_cases_reaches_by_name_is_clean(self):
        found = checker().problems(fixture("run_class_in_listed_case", RUN_CLASS_IN_A_LISTED_CASE))
        self.assertEqual(found, [], "a TestCase run by run_class in a case function that run_cases reaches by name is reported: %r" % found)

    def test_attribute_base_ending_in_testcase_is_a_testcase(self):
        found = checker().problems(fixture("attribute_base_ends_in_testcase", ASYNC_TESTCASE_BASE))
        self.assertEqual(len(found), 1, "a class whose attribute base ends in TestCase (IsolatedAsyncioTestCase) is not a TestCase: %r" % found)
        self.assertTrue(found[0].endswith("test_one.py: " + SUFFIX), "problem text is %r" % found[0])

    def test_not_equal_main_guard_is_not_the_main_guard(self):
        found = checker().problems(fixture("not_equal_main_guard", NOT_EQUAL_MAIN_GUARD))
        self.assertEqual(len(found), 1, "a unittest.main() under `if __name__ != \"__main__\":` counts as the main guard: %r" % found)
        self.assertTrue(found[0].endswith("test_one.py: " + SUFFIX), "problem text is %r" % found[0])

    def test_worktrees_under_claude_are_skipped(self):
        found = checker().problems(tree("worktrees_skipped", {
            ".claude/worktrees/wt/test_one.py": SUITE_WITHOUT_MAIN,
            ".claude/hooks/test_two.py": SUITE_WITHOUT_MAIN,
        }))
        self.assertEqual(found, [".claude/hooks/test_two.py: " + SUFFIX],
                         "the .claude/worktrees skip is not in force, or .claude/hooks is not scanned: %r" % found)

    def test_unittest_main_imported_by_name_is_a_runner(self):
        found = checker().problems(fixture("from_unittest_import_main", FROM_UNITTEST_IMPORT_MAIN))
        self.assertEqual(found, [], "a `main` imported from unittest, called under the __main__ block, is reported: %r" % found)

    def test_bare_run_cases_call_is_reported(self):
        found = checker().problems(fixture("bare_run_cases", BARE_RUN_CASES))
        named = [p for p in found if "run_cases" in p and "return value" in p]
        self.assertTrue(named, "a suite whose __main__ path calls run_cases as a bare statement is not reported with 'run_cases' and 'return value': %r" % found)

    def test_run_cases_inside_sys_exit_is_clean(self):
        found = checker().problems(fixture("run_cases_in_sys_exit", RUN_CASES_IN_SYS_EXIT))
        self.assertEqual(found, [], "sys.exit(run_cases(...)) is reported: %r" % found)

    def test_run_cases_assigned_then_exited_is_clean(self):
        found = checker().problems(fixture("run_cases_assigned", RUN_CASES_ASSIGNED))
        self.assertEqual(found, [], "rc = run_cases(...) then sys.exit(rc) is reported: %r" % found)

    def test_run_cases_or_assigned_is_clean(self):
        found = checker().problems(fixture("run_cases_or_assigned", RUN_CASES_OR_ASSIGNED))
        self.assertEqual(found, [], "failed |= run_cases(...) is reported: %r" % found)

    def test_run_cases_returned_is_clean(self):
        found = checker().problems(fixture("run_cases_returned", RUN_CASES_RETURNED))
        self.assertEqual(found, [], "return run_cases(...) is reported: %r" % found)

    def test_attribute_run_cases_bare_statement_is_reported_and_assigned_is_not(self):
        found = checker().problems(fixture("attribute_run_cases_bare", BARE_ATTRIBUTE_RUN_CASES))
        self.assertEqual(len(found), 1, "a bare m.run_cases(...) statement on the __main__ path is not reported: %r" % found)
        self.assertIn("return value", found[0], "the bare m.run_cases(...) finding does not name the dropped return value: %r" % found)
        clean = checker().problems(fixture("attribute_run_cases_assigned", ASSIGNED_ATTRIBUTE_RUN_CASES))
        self.assertEqual(clean, [], "code = m.run_cases(...) is reported: %r" % clean)


class RunClassCases(unittest.TestCase):
    def test_class_with_no_test_methods_fails_the_run(self):
        class NoTestMethods(unittest.TestCase):
            pass

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ok = cost_probe.run_class(NoTestMethods)
        self.assertIs(ok, False, "run_class of a TestCase class with no test methods returned %r, want False: nothing ran" % ok)
        self.assertIn("NoTestMethods", out.getvalue(), "run_class printed no line naming the class: %r" % out.getvalue())


class RepoRun(unittest.TestCase):
    def test_repo_has_no_suite_without_main(self):
        found = checker().problems(REPO)
        print("check_suites_have_main: %d problem(s) on this repo" % len(found))
        for item in found:
            print("  " + item)
        self.assertEqual(found, [], "%d suite(s) in this repo define a TestCase and never call unittest.main" % len(found))


if __name__ == "__main__":
    unittest.main()
