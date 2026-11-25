#!/usr/bin/env python3
"""Fixture cases for lint/check_suites_have_main.py, and a run of it on this repo.

A test file that defines a unittest.TestCase but never calls unittest.main does nothing when it is run
directly: its cases never run, and the run still reads as a pass. problems(root) names each such file as
"<path>: defines a TestCase but never calls unittest.main". The checker reads each file with ast, so a
TestCase named only in a string or a comment is no class, and a script with no TestCase is no suite.

The fixtures are built in the run folder, one folder per case, each holding only its own file.
"""
import importlib.util
import os
import shutil
import sys
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  the one home of the run folder and its sweep (lint/_test_temp.py)

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


class RepoRun(unittest.TestCase):
    def test_repo_has_no_suite_without_main(self):
        found = checker().problems(REPO)
        print("check_suites_have_main: %d problem(s) on this repo" % len(found))
        for item in found:
            print("  " + item)
        self.assertEqual(found, [], "%d suite(s) in this repo define a TestCase and never call unittest.main" % len(found))


if __name__ == "__main__":
    unittest.main()
