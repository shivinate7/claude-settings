"""Cases for lint/check_tests_set_config.py: problems(root) names each test_*.py under root that pops, deletes or clears CLAUDE_CONFIG_DIR
from the environment and never sets it, so its cases read the real ~/.claude. The incident: merge/test_merge.py pops it at import,
and its cases that need it set it only inside their own patch.dict.

Only a module-level pop, del or os.environ.clear() counts: it runs at import and reaches every case. A pop inside one test method is that case's own choice,
so it is clean. The last module-level removal is cleared only by a set at module level after it, by a set in setUpModule(), or by a set in a function the module calls at import; a set under `if False:` does not clear it. A set in a test
method, or inside a patch.dict call, does not clear it: the other cases still run without the variable.
Each problem is a string that starts with the test file's path under root, then a colon. A file that does not parse is a problem too:
it is not clean.

TESTS_SET_CONFIG_UNDER_TEST, a path from the repo root, names a stand-in checker to run these cases against:
lint/tests_set_config_stub_test.py finds nothing, and lint/tests_set_config_flags_all_stub_test.py flags every test file. The red
runs use them. Unset, the cases run against lint/check_tests_set_config.py.

Run: python3 -m unittest discover -s lint -p test_tests_set_config.py
"""
import atexit
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest

import _test_temp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN = _test_temp.run_folder()  # this run's one folder (test-temp-standard); removed when the process exits
atexit.register(shutil.rmtree, RUN, True)
MERGE_TEST = "merge/test_merge.py"  # the incident's file: the checker must name it on this repo

POP_NEVER_SET = ("import os\n\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\n\n\ndef test_a():\n    assert True\n")
LOOP_POP = ("import os\n\nfor _name in ('CLAUDE_CODE_REMOTE', 'CLAUDE_CONFIG_DIR'):\n    os.environ.pop(_name, None)\n\n\n"
            "def test_a():\n    assert True\n")  # the form merge/test_merge.py uses
DEL_NEVER_SET = ("import os\n\ndel os.environ['CLAUDE_CONFIG_DIR']\n\n\ndef test_a():\n    assert True\n")
POP_THEN_SET = ("import os\n\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\nos.environ['CLAUDE_CONFIG_DIR'] = '/tmp/config'\n\n\n"
                "def test_a():\n    assert True\n")
SET_IN_SETUP_MODULE = ("import os\n\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\n\n\ndef setUpModule():\n"
                       "    os.environ['CLAUDE_CONFIG_DIR'] = '/tmp/config'\n\n\ndef test_a():\n    assert True\n")
SET_IN_ONE_TEST = ("import os\n\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\n\n\ndef test_a():\n"
                   "    os.environ['CLAUDE_CONFIG_DIR'] = '/tmp/config'\n    assert True\n\n\ndef test_b():\n    assert True\n")
NEVER_TOUCHES = ("import os\n\n\ndef test_a():\n    assert os.environ.get('HOME')\n")
NAME_IN_STRING = ("import os\n\nNOTE = \"os.environ.pop('CLAUDE_CONFIG_DIR', None) is the bad form\"\n\n\n"
                  "def test_a():\n    assert NOTE\n")
POP_IN_ONE_TEST = ("import os\n\n\ndef test_a():\n    os.environ.pop('CLAUDE_CONFIG_DIR', None)\n    assert True\n")
UNPARSEABLE = "def test_a(:\n    pass\n"
LOOP_POP_THEN_LOOP_SET = ("import os\n\nfor _name in ('CLAUDE_CONFIG_DIR',):\n    os.environ.pop(_name, None)\n"
                          "for _n in ('CLAUDE_CONFIG_DIR',):\n    os.environ[_n] = '/tmp/config'\n\n\ndef test_a():\n    assert True\n")
CLEAR_NEVER_SET = "import os\n\nos.environ.clear()\n\n\ndef test_a():\n    assert True\n"
CLEAR_THEN_SET = "import os\n\nos.environ.clear()\nos.environ['CLAUDE_CONFIG_DIR'] = '/tmp/config'\n\n\ndef test_a():\n    assert True\n"
IMPORTED_NAME_POP = ("import os\n\nfrom _test_temp import CONFIG_VAR\n\nos.environ.pop(CONFIG_VAR, None)\n\n\n"
                     "def test_a():\n    assert True\n")
TUPLE_CONSTANT_LOOP_POP = ("import os\n\nNAMES = ('CLAUDE_CONFIG_DIR',)\n\nfor _name in NAMES:\n    os.environ.pop(_name, None)\n\n\n"
                           "def test_a():\n    assert True\n")
ALIAS_POP = "import os\n\nenv = os.environ\nenv.pop('CLAUDE_CONFIG_DIR', None)\n\n\ndef test_a():\n    assert True\n"
POP_SET_POP = ("import os\n\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\nos.environ['CLAUDE_CONFIG_DIR'] = '/tmp/config'\n"
               "os.environ.pop('CLAUDE_CONFIG_DIR', None)\n\n\ndef test_a():\n    assert True\n")
POP_THEN_SET_UNDER_IF_FALSE = ("import os\n\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\nif False:\n"
                               "    os.environ['CLAUDE_CONFIG_DIR'] = '/tmp/config'\n\n\ndef test_a():\n    assert True\n")
SET_IN_HELPER_AT_IMPORT = ("import os\n\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\n\n\ndef _set_config():\n"
                           "    os.environ['CLAUDE_CONFIG_DIR'] = '/tmp/config'\n\n\n_set_config()\n\n\ndef test_a():\n    assert True\n")
ANNOTATED_SET = ("import os\n\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\nos.environ['CLAUDE_CONFIG_DIR']: str = '/tmp/config'\n\n\n"
                 "def test_a():\n    assert True\n")


def checker():
    """The checker the cases drive: the stand-in named by TESTS_SET_CONFIG_UNDER_TEST, else lint/check_tests_set_config.py."""
    path = os.environ.get("TESTS_SET_CONFIG_UNDER_TEST") or os.path.join("lint", "check_tests_set_config.py")
    spec = importlib.util.spec_from_file_location("check_tests_set_config_under_test", os.path.join(ROOT, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def problems_of(source):
    """problems() over a fresh folder under the run folder that holds one test file, test_case.py, with `source`."""
    folder = tempfile.mkdtemp(prefix="tree-", dir=RUN)
    with open(os.path.join(folder, "test_case.py"), "w", encoding="utf-8") as handle:
        handle.write(source)
    return checker().problems(folder)


class TestsSetConfig(unittest.TestCase):
    def test_pop_never_set_is_a_problem(self):
        found = problems_of(POP_NEVER_SET)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "a module-level pop with no set is not one problem named for its file: %r" % found)

    def test_loop_pop_is_a_problem(self):
        found = problems_of(LOOP_POP)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "a pop in a loop over a tuple that names CLAUDE_CONFIG_DIR is not one problem: %r" % found)

    def test_del_never_set_is_a_problem(self):
        found = problems_of(DEL_NEVER_SET)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "a del of CLAUDE_CONFIG_DIR with no set is not one problem: %r" % found)

    def test_set_in_one_test_does_not_clear_a_module_pop(self):
        found = problems_of(SET_IN_ONE_TEST)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "a module-level pop, cleared only inside one test method, is not one problem: %r" % found)

    def test_pop_then_set_at_module_level_is_clean(self):
        self.assertEqual(problems_of(POP_THEN_SET), [], "a pop that a module-level set follows is named as a problem")

    def test_set_in_setup_module_is_clean(self):
        self.assertEqual(problems_of(SET_IN_SETUP_MODULE), [], "a pop that setUpModule() sets is named as a problem")

    def test_never_touching_is_clean(self):
        self.assertEqual(problems_of(NEVER_TOUCHES), [], "a file that never touches CLAUDE_CONFIG_DIR is named as a problem")

    def test_name_only_inside_a_string_is_clean(self):
        self.assertEqual(problems_of(NAME_IN_STRING), [], "a pop written only inside a string is read as a real pop")

    def test_pop_inside_one_test_is_clean(self):
        self.assertEqual(problems_of(POP_IN_ONE_TEST), [], "a pop inside one test method is named as a problem; only import-time pops count")

    def test_unparseable_file_is_not_clean(self):
        found = problems_of(UNPARSEABLE)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "a test file that does not parse reads clean: %r" % found)

    def test_loop_set_after_loop_pop_is_clean(self):
        self.assertEqual(problems_of(LOOP_POP_THEN_LOOP_SET), [],
                         "a set in a module-level loop over a literal that names CLAUDE_CONFIG_DIR is not counted, so the pop reads as never set")

    def test_clear_with_no_set_is_a_problem(self):
        found = problems_of(CLEAR_NEVER_SET)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "a module-level os.environ.clear() with no later set is not one problem named for its file: %r" % found)

    def test_clear_then_set_is_clean(self):
        self.assertEqual(problems_of(CLEAR_THEN_SET), [], "a clear that a module-level set follows is named as a problem")

    def test_pop_of_imported_name_is_a_problem(self):
        found = problems_of(IMPORTED_NAME_POP)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "a pop of a name imported from _test_temp, which holds CLAUDE_CONFIG_DIR, is not one problem: %r" % found)

    def test_loop_pop_over_tuple_constant_is_a_problem(self):
        found = problems_of(TUPLE_CONSTANT_LOOP_POP)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "a loop pop over a module-level tuple that holds CLAUDE_CONFIG_DIR is not one problem: %r" % found)

    def test_pop_through_alias_is_a_problem(self):
        found = problems_of(ALIAS_POP)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "a pop through an alias of os.environ (env = os.environ) is not one problem: %r" % found)

    def test_pop_after_last_set_is_a_problem(self):
        found = problems_of(POP_SET_POP)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "a module-level pop after the last set leaves CLAUDE_CONFIG_DIR unset, yet the file is not one problem: %r" % found)

    def test_set_under_if_false_does_not_clear_the_pop(self):
        found = problems_of(POP_THEN_SET_UNDER_IF_FALSE)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "a set under `if False:` clears a module-level pop, so the pop is not named: %r" % found)

    def test_set_in_helper_called_at_import_is_clean(self):
        self.assertEqual(problems_of(SET_IN_HELPER_AT_IMPORT), [],
                         "a pop that a function the module calls at import sets is named as a problem")

    def test_annotated_set_is_clean(self):
        self.assertEqual(problems_of(ANNOTATED_SET), [],
                         "an annotated set of CLAUDE_CONFIG_DIR after the pop is not counted, so the pop is named as a problem")

    def test_repo_names_the_incident_file(self):
        found = checker().problems(ROOT)
        print("\nproblems on this repo (%d):" % len(found), file=sys.stderr)
        for line in found:
            print("  " + line, file=sys.stderr)
        self.assertTrue(any(line.startswith(MERGE_TEST + ":") for line in found),
                        "%s pops CLAUDE_CONFIG_DIR at import and is not among the repo's findings: %r" % (MERGE_TEST, found))


if __name__ == "__main__":
    unittest.main()
