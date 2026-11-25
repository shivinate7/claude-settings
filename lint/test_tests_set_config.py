"""Cases for lint/check_tests_set_config.py: problems(root) names each test_*.py under root that pops, deletes or clears CLAUDE_CONFIG_DIR
from the environment at import and never sets it again, so its cases read the real ~/.claude. A module that pops it at import and
sets it only inside a case's own patch.dict is one such file.

Only a module-level pop, del or os.environ.clear() counts: it runs at import and reaches every case. A pop inside one test method is that case's own choice,
so it is clean. The last module-level removal is cleared only by a set at module level after it, by a set in setUpModule(), or by a set in a function the module calls at import; a set under `if False:` does not clear it. A set in a test
method, or inside a patch.dict call, does not clear it: the other cases still run without the variable.
Each problem is a string that starts with the test file's path under root, then a colon. A file that does not parse is a problem too:
it is not clean.

--stand-in PATH, a path from the repo root, names a stand-in checker to run these cases against: lint/tests_set_config_stub_test.py
finds nothing, and lint/tests_set_config_flags_all_stub_test.py flags every test file. The red runs use them. Without it, the cases
run against lint/check_tests_set_config.py. The caller's environment is never read: a stray value there changes nothing.

Run: python3 lint/test_tests_set_config.py [--stand-in PATH]
"""
import ast
import atexit
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import _test_temp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAND_IN = None  # the __main__ block sets it from --stand-in; the caller's environment is never read
RUN = _test_temp.run_folder()  # this run's one folder (test-temp-standard); removed when the process exits
atexit.register(shutil.rmtree, RUN, True)
INCIDENT_PATH = "merge/test_merge_incident.py"  # a fixture path: the file is written under the run folder, never read from the repo
# The smallest shape the check must name: a module-level loop pop over names that include CLAUDE_CONFIG_DIR, with no set after it, and
# a case that sets the variable only inside its own patch.dict.
INCIDENT_SHAPE = ("import os\nfrom unittest import mock\n\nfor _name in ('CLAUDE_CODE_REMOTE', 'CLAUDE_CONFIG_DIR'):\n"
                  "    os.environ.pop(_name, None)\n\n\ndef test_a():\n    with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': '/tmp/config'}):\n"
                  "        assert True\n")

POP_NEVER_SET = ("import os\n\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\n\n\ndef test_a():\n    assert True\n")
LOOP_POP = ("import os\n\nfor _name in ('CLAUDE_CODE_REMOTE', 'CLAUDE_CONFIG_DIR'):\n    os.environ.pop(_name, None)\n\n\n"
            "def test_a():\n    assert True\n")
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
ENTER_CONTEXT_AT_IMPORT = ("import os\nfrom contextlib import ExitStack\nfrom _test_temp import isolated_config\n\nRUN = 'run'\nSTACK = ExitStack()\n"
                           "os.environ.pop('CLAUDE_CONFIG_DIR', None)\nSTACK.enter_context(isolated_config(RUN))\n\n\n"
                           "def test_a():\n    assert True\n")
ENTER_CONTEXT_IN_SETUP_MODULE = ("import os\nfrom contextlib import ExitStack\nfrom _test_temp import isolated_config\n\nSTACK = ExitStack()\n"
                                 "os.environ.pop('CLAUDE_CONFIG_DIR', None)\n\n\ndef setUpModule():\n"
                                 "    STACK.enter_context(isolated_config('run'))\n\n\ndef test_a():\n    assert True\n")
UPDATE_NAMED_DICT = ("import os\n\nENV = {'CLAUDE_CONFIG_DIR': '/tmp/config'}\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\n"
                     "os.environ.update(ENV)\n\n\ndef test_a():\n    assert True\n")
UPDATE_DICT_CALL = ("import os\n\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\nos.environ.update(dict(CLAUDE_CONFIG_DIR='/tmp/config'))\n\n\n"
                    "def test_a():\n    assert True\n")
OR_ASSIGN_SET = ("import os\n\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\nos.environ |= {'CLAUDE_CONFIG_DIR': '/tmp/config'}\n\n\n"
                 "def test_a():\n    assert True\n")
UPDATE_STAR_DICT = ("import os\n\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\nos.environ.update(**{'CLAUDE_CONFIG_DIR': '/tmp/config'})\n\n\n"
                    "def test_a():\n    assert True\n")
PATCH_DICT_START_AT_IMPORT = ("import os\nfrom unittest.mock import patch\n\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\n"
                              "patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': '/tmp/config'}).start()\n\n\n"
                              "def test_a():\n    assert True\n")
HELPER_CALLS_LATER_HELPER = ("import os\n\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\n\n\ndef _outer():\n    _inner()\n\n\n"
                             "def _inner():\n    os.environ['CLAUDE_CONFIG_DIR'] = '/tmp/config'\n\n\n_outer()\n\n\n"
                             "def test_a():\n    assert True\n")
OTHER_IMPORTED_SETTER = ("import os\nfrom elsewhere_config import make_config\n\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\nmake_config()\n\n\n"
                         "def test_a():\n    assert True\n")
MAIN_GUARD_SET = ("import os\n\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\n\nif __name__ == '__main__':\n"
                  "    os.environ['CLAUDE_CONFIG_DIR'] = '/tmp/config'\n\n\ndef test_a():\n    assert True\n")
ANNOTATED_NAME_POP = ("import os\n\nVAR: str = 'CLAUDE_CONFIG_DIR'\nos.environ.pop(VAR, None)\n\n\n"
                      "def test_a():\n    assert True\n")
SHARED_NAME_POP = ("import os\n\nfrom shared_names import CONFIG_VAR\n\nos.environ.pop(CONFIG_VAR, None)\n\n\n"
                   "def test_a():\n    assert True\n")
PREFIX_SWEEP = ("import os\n\nfor _name in list(os.environ):\n    if _name.startswith('CLAUDE_'):\n        os.environ.pop(_name, None)\n\n\n"
                "def test_a():\n    assert True\n")
PREFIX_SWEEP_THEN_SET = ("import os\n\nfor _name in list(os.environ):\n    if _name.startswith('CLAUDE_'):\n        os.environ.pop(_name, None)\n"
                         "os.environ['CLAUDE_CONFIG_DIR'] = '/tmp/config'\n\n\ndef test_a():\n    assert True\n")
PREFIX_SWEEP_OTHER_PREFIX = ("import os\n\nfor _name in list(os.environ):\n    if _name.startswith('AWS_'):\n        os.environ.pop(_name, None)\n\n\n"
                             "def test_a():\n    assert True\n")
DICT_KEY_LOOP = ("import os\n\nGONE = {'CLAUDE_CONFIG_DIR': None, 'CLAUDE_CODE_REMOTE': None}\nfor _name in GONE:\n"
                 "    os.environ.pop(_name, None)\n\n\ndef test_a():\n    assert True\n")
DICT_KEY_LOOP_THEN_SET = ("import os\n\nGONE = {'CLAUDE_CONFIG_DIR': None, 'CLAUDE_CODE_REMOTE': None}\nfor _name in GONE:\n"
                          "    os.environ.pop(_name, None)\nos.environ['CLAUDE_CONFIG_DIR'] = '/tmp/config'\n\n\n"
                          "def test_a():\n    assert True\n")
PATCH_DICT_CLEAR = ("import os\nfrom unittest import mock\n\nmock.patch.dict(os.environ, {'PATH': '/usr/bin'}, clear=True).start()\n\n\n"
                    "def test_a():\n    assert True\n")
PATCH_DICT_CLEAR_THEN_SET = ("import os\nfrom unittest import mock\n\nmock.patch.dict(os.environ, {'PATH': '/usr/bin'}, clear=True).start()\n"
                             "os.environ['CLAUDE_CONFIG_DIR'] = '/tmp/config'\n\n\ndef test_a():\n    assert True\n")
PATCH_DICT_CLEAR_FALSE = ("import os\nfrom unittest import mock\n\nmock.patch.dict(os.environ, {'PATH': '/usr/bin'}, clear=False).start()\n\n\n"
                          "def test_a():\n    assert True\n")
PATCH_DICT_NO_CLEAR = ("import os\nfrom unittest import mock\n\nmock.patch.dict(os.environ, {'PATH': '/usr/bin'}).start()\n\n\n"
                       "def test_a():\n    assert True\n")
PATCH_DICT_CLEAR_SETS_VAR = ("import os\nfrom unittest import mock\n\n"
                             "mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': '/tmp/config'}, clear=True).start()\n\n\n"
                             "def test_a():\n    assert True\n")
ITEMS_SWEEP_TUPLE = ("import os\n\nfor _name, _value in os.environ.items():\n    os.environ.pop(_name, None)\n\n\n"
                     "def test_a():\n    assert True\n")
KEYS_SWEEP = ("import os\n\nfor _name in os.environ.keys():\n    os.environ.pop(_name, None)\n\n\n"
              "def test_a():\n    assert True\n")
SORTED_SWEEP = ("import os\n\nfor _name in sorted(os.environ):\n    os.environ.pop(_name, None)\n\n\n"
                "def test_a():\n    assert True\n")
OPENERS_IN_STRINGS = ("import os\n\nOPEN = \"/*\"\nTAG, PATHS = \"#\", \"//\"; os.environ.pop('CLAUDE_CONFIG_DIR', None)\n\n\n"
                      "def test_a():\n    assert True\n")
MULTILINE_TEXT_HOLDS_POP = ("import os\n\nNOTE = \"\"\"\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\n\"\"\"\n\n\n"
                            "def test_a():\n    assert True\n")
LONE_QUOTE_IN_COMMENT = ("import os\n\n# Don't keep this line: the pop below is the real one\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\n\n\n"
                         "def test_a():\n    assert True\n")


COMPREHENSION_SWEEP = ("import os\n\nfor n in [n for n in os.environ if n.startswith('CLAUDE_')]:\n    os.environ.pop(n, None)\n\n\n"
                       "def test_a():\n    assert True\n")
DICT_COPY_SWEEP = "import os\n\nfor n in dict(os.environ):\n    del os.environ[n]\n\n\ndef test_a():\n    assert True\n"
FILTER_SWEEP = "import os\n\nfor n in filter(None, os.environ):\n    os.environ.pop(n, None)\n\n\ndef test_a():\n    assert True\n"
GENERATOR_SWEEP = ("import os\n\nfor n in (k for k in os.environ.keys()):\n    os.environ.pop(n, None)\n\n\n"
                   "def test_a():\n    assert True\n")
COPY_SWEEP_CONTROL = ("import os\n\nenv = dict(os.environ)\nfor n in list(env):\n    env.pop(n, None)\n\n\n"
                      "def test_a():\n    assert True\n")
READ_ONLY_COMPREHENSION_CONTROL = ("import os\n\nfor n in [k for k in os.environ if k.startswith('CLAUDE_')]:\n    _seen = os.environ[n]\n\n\n"
                                   "def test_a():\n    assert True\n")
COMPREHENSION_SWEEP_THEN_SET = ("import os\n\nfor n in [n for n in os.environ if n.startswith('CLAUDE_')]:\n    os.environ.pop(n, None)\n"
                                "os.environ['CLAUDE_CONFIG_DIR'] = '/tmp/config'\n\n\ndef test_a():\n    assert True\n")
LOOP_OVER_NAME_STRING_CONTROL = ("import os\n\nfor n in ['os.environ']:\n    os.environ.pop(n, None)\n\n\ndef test_a():\n    assert True\n")

ENTER_CONTEXT_ATTRIBUTE_AT_IMPORT = ("import os\nfrom contextlib import ExitStack\nimport _test_temp\n\nRUN = 'run'\nSTACK = ExitStack()\n"
                                     "os.environ.pop('CLAUDE_CONFIG_DIR', None)\nSTACK.enter_context(_test_temp.isolated_config(RUN))\n\n\n"
                                     "def test_a():\n    assert True\n")
SETDEFAULT_AT_IMPORT = ("import os\n\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\nos.environ.setdefault('CLAUDE_CONFIG_DIR', '/tmp/config')\n\n\n"
                        "def test_a():\n    assert True\n")
SET_IN_PATCH_DICT_AT_IMPORT = ("import os\nfrom unittest import mock\n\nos.environ.pop('CLAUDE_CONFIG_DIR', None)\n"
                               "with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': '/tmp/config'}):\n"
                               "    os.environ['CLAUDE_CONFIG_DIR'] = '/tmp/config'\n\n\ndef test_a():\n    assert True\n")
POP_IN_PATCH_DICT_AT_IMPORT = ("import os\nfrom unittest import mock\n\n"
                               "with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': '/tmp/config'}):\n"
                               "    os.environ.pop('CLAUDE_CONFIG_DIR', None)\n\n\ndef test_a():\n    assert True\n")


def tree_of(files):
    """A fresh folder under the run folder, holding each file of `files`: a dict of a path under the folder to source. A path's
    folders are made first."""
    folder = tempfile.mkdtemp(prefix="tree-", dir=RUN)
    for name, source in files.items():
        path = os.path.join(folder, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(source)
    return folder


def checker():
    """The checker the cases drive: the stand-in named by --stand-in, else lint/check_tests_set_config.py."""
    path = STAND_IN or os.path.join("lint", "check_tests_set_config.py")
    spec = importlib.util.spec_from_file_location("check_tests_set_config_under_test", os.path.join(ROOT, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def problems_of(source):
    """problems() over a fresh folder under the run folder that holds one test file, test_case.py, with `source`."""
    return checker().problems(tree_of({"test_case.py": source}))


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

    def test_enter_context_of_isolated_config_at_import_is_clean(self):
        self.assertEqual(problems_of(ENTER_CONTEXT_AT_IMPORT), [],
                         "a pop that an import-time STACK.enter_context(isolated_config(RUN)) follows is named as a problem")

    def test_enter_context_of_isolated_config_in_setup_module_is_clean(self):
        self.assertEqual(problems_of(ENTER_CONTEXT_IN_SETUP_MODULE), [],
                         "a pop that setUpModule() follows with STACK.enter_context(isolated_config(...)) is named as a problem")

    def test_update_of_a_named_dict_that_holds_the_var_is_clean(self):
        self.assertEqual(problems_of(UPDATE_NAMED_DICT), [],
                         "a pop that os.environ.update(ENV) follows, with ENV = {CLAUDE_CONFIG_DIR: ...}, is named as a problem")

    def test_update_of_dict_call_with_the_var_as_keyword_is_clean(self):
        self.assertEqual(problems_of(UPDATE_DICT_CALL), [],
                         "a pop that os.environ.update(dict(CLAUDE_CONFIG_DIR=...)) follows is named as a problem")

    def test_ior_of_environ_that_holds_the_var_is_clean(self):
        self.assertEqual(problems_of(OR_ASSIGN_SET), [],
                         "a pop that os.environ |= {CLAUDE_CONFIG_DIR: ...} follows is named as a problem")

    def test_update_of_star_star_dict_that_holds_the_var_is_clean(self):
        self.assertEqual(problems_of(UPDATE_STAR_DICT), [],
                         "a pop that os.environ.update(**{CLAUDE_CONFIG_DIR: ...}) follows is named as a problem")

    def test_patch_dict_started_at_import_is_clean(self):
        self.assertEqual(problems_of(PATCH_DICT_START_AT_IMPORT), [],
                         "a pop that a patch.dict(os.environ, ...).start() at import follows is named as a problem")

    def test_enter_context_of_attribute_isolated_config_at_import_is_clean(self):
        self.assertEqual(problems_of(ENTER_CONTEXT_ATTRIBUTE_AT_IMPORT), [],
                         "a pop that an import-time STACK.enter_context(_test_temp.isolated_config(RUN)) follows is named as a problem")

    def test_setdefault_of_config_var_at_import_is_clean(self):
        self.assertEqual(problems_of(SETDEFAULT_AT_IMPORT), [],
                         "a pop that an import-time os.environ.setdefault(CLAUDE_CONFIG_DIR, ...) follows is named as a problem")

    def test_set_inside_import_time_patch_dict_does_not_clear_a_pop(self):
        found = problems_of(SET_IN_PATCH_DICT_AT_IMPORT)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "a set inside an import-time with patch.dict(os.environ, ...) block clears a module-level pop, "
                        "though patch.dict undoes it at exit: %r" % found)

    def test_pop_inside_import_time_patch_dict_is_not_a_removal(self):
        self.assertEqual(problems_of(POP_IN_PATCH_DICT_AT_IMPORT), [],
                         "a pop inside an import-time with patch.dict(os.environ, ...) block, which undoes it at exit, is named as a problem")

    def test_helper_calling_a_later_defined_setter_at_import_is_clean(self):
        self.assertEqual(problems_of(HELPER_CALLS_LATER_HELPER), [],
                         "a pop that an import-time call to a helper, which calls a later-defined helper that sets the var, follows is named")

    def test_import_time_call_to_other_imported_function_stays_a_problem(self):
        found = problems_of(OTHER_IMPORTED_SETTER)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "a pop that an import-time call to an unread imported function follows is cleared, though only isolated_config clears: %r" % found)

    def test_set_under_main_guard_does_not_clear_the_pop(self):
        found = problems_of(MAIN_GUARD_SET)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "a set under `if __name__ == '__main__':` clears a module-level pop, though the tests never run that block: %r" % found)

    def test_annotated_name_holding_the_var_is_a_pop_target(self):
        found = problems_of(ANNOTATED_NAME_POP)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "a pop of a name bound with an annotation to CLAUDE_CONFIG_DIR is not one problem: %r" % found)

    def test_shared_module_is_parsed_once_per_run(self):
        run_checker = checker()
        folder = tree_of({"shared_names.py": "CONFIG_VAR = 'CLAUDE_CONFIG_DIR'\n", "test_one.py": SHARED_NAME_POP,
                          "test_two.py": SHARED_NAME_POP, "test_three.py": SHARED_NAME_POP})
        real_parse = ast.parse
        parsed = []

        def counting_parse(source, *args, **kwargs):
            parsed.append(os.path.basename(kwargs.get("filename", "")))
            return real_parse(source, *args, **kwargs)

        with mock.patch.object(ast, "parse", side_effect=counting_parse):
            found = run_checker.problems(folder)
        self.assertEqual(len(found), 3, "the three test files do not each read as one problem: %r" % found)
        times = parsed.count("shared_names.py")
        self.assertLessEqual(times, 1, "shared_names.py is parsed %d times in one run, where one parse per module would do" % times)

    def test_prefix_sweep_of_the_config_var_is_a_problem(self):
        found = problems_of(PREFIX_SWEEP)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "an import-time loop that pops each CLAUDE_ name, CLAUDE_CONFIG_DIR among them, is not one problem: %r" % found)

    def test_prefix_sweep_then_set_is_clean(self):
        self.assertEqual(problems_of(PREFIX_SWEEP_THEN_SET), [],
                         "a prefix sweep that an import-time set of CLAUDE_CONFIG_DIR follows is named as a problem")

    def test_prefix_sweep_the_check_cannot_evaluate_is_flagged(self):
        found = problems_of(PREFIX_SWEEP_OTHER_PREFIX)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "an import-time sweep by an AWS_ prefix is not flagged, though the check does not evaluate prefixes: %r" % found)

    def test_prefix_sweep_the_check_cannot_evaluate_says_sweep(self):
        found = problems_of(PREFIX_SWEEP_OTHER_PREFIX)
        self.assertEqual(len(found), 1, "an import-time sweep by an AWS_ prefix is not one problem: %r" % found)
        self.assertIn("sweep", found[0],
                      "the message for a sweep the check cannot evaluate does not say it is a sweep: %r" % found)
        self.assertNotIn("removes CLAUDE_CONFIG_DIR", found[0],
                         "the message for a sweep the check cannot evaluate says it removes CLAUDE_CONFIG_DIR, which the check cannot tell: %r" % found)

    def test_direct_pop_message_is_not_called_a_sweep(self):
        found = problems_of(POP_NEVER_SET)
        self.assertEqual(len(found), 1, "a direct pop of CLAUDE_CONFIG_DIR with no set is not one problem: %r" % found)
        self.assertNotIn("sweep", found[0], "the message for a direct pop of CLAUDE_CONFIG_DIR calls it a sweep: %r" % found)

    def test_loop_over_dict_keys_that_pops_the_config_var_is_a_problem(self):
        found = problems_of(DICT_KEY_LOOP)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "an import-time loop over a dict's keys that pops CLAUDE_CONFIG_DIR is not one problem: %r" % found)

    def test_loop_over_dict_keys_then_set_is_clean(self):
        self.assertEqual(problems_of(DICT_KEY_LOOP_THEN_SET), [],
                         "a dict-key loop pop that an import-time set of CLAUDE_CONFIG_DIR follows is named as a problem")

    def test_items_sweep_with_tuple_target_is_a_problem(self):
        found = problems_of(ITEMS_SWEEP_TUPLE)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "an import-time sweep of os.environ.items() that pops the first name of a tuple target is not one problem: %r" % found)

    def test_keys_sweep_is_a_problem(self):
        found = problems_of(KEYS_SWEEP)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "an import-time sweep of os.environ.keys() that pops each name is not one problem: %r" % found)

    def test_sorted_environ_sweep_is_a_problem(self):
        found = problems_of(SORTED_SWEEP)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "an import-time sweep of sorted(os.environ) that pops each name is not one problem: %r" % found)

    def test_comprehension_sweep_of_environ_is_a_problem(self):
        found = problems_of(COMPREHENSION_SWEEP)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "an import-time loop over a comprehension of os.environ that pops each name is not one problem: %r" % found)

    def test_dict_copy_sweep_of_environ_is_a_problem(self):
        found = problems_of(DICT_COPY_SWEEP)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "an import-time loop over dict(os.environ) that deletes each name from os.environ is not one problem: %r" % found)

    def test_filter_sweep_of_environ_is_a_problem(self):
        found = problems_of(FILTER_SWEEP)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "an import-time loop over filter(None, os.environ) that pops each name is not one problem: %r" % found)

    def test_generator_sweep_of_environ_keys_is_a_problem(self):
        found = problems_of(GENERATOR_SWEEP)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "an import-time loop over a generator of os.environ.keys() that pops each name is not one problem: %r" % found)

    def test_loop_over_a_copy_of_environ_that_pops_the_copy_is_clean(self):
        self.assertEqual(problems_of(COPY_SWEEP_CONTROL), [],
                         "a loop over a copy of os.environ that pops from the copy is named as a problem")

    def test_read_only_comprehension_over_environ_is_clean(self):
        self.assertEqual(problems_of(READ_ONLY_COMPREHENSION_CONTROL), [],
                         "an import-time loop over a comprehension of os.environ that only reads each name is named as a problem")

    def test_comprehension_sweep_then_set_is_clean(self):
        self.assertEqual(problems_of(COMPREHENSION_SWEEP_THEN_SET), [],
                         "a comprehension sweep that an import-time set of CLAUDE_CONFIG_DIR follows is named as a problem")

    def test_loop_over_a_string_that_names_environ_is_clean(self):
        self.assertEqual(problems_of(LOOP_OVER_NAME_STRING_CONTROL), [],
                         "a loop over a list of strings that spell os.environ is read as a sweep of os.environ")

    def test_patch_dict_clear_at_import_is_a_problem(self):
        found = problems_of(PATCH_DICT_CLEAR)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "an import-time patch.dict(os.environ, ..., clear=True).start() drops CLAUDE_CONFIG_DIR, yet is not one problem: %r" % found)

    def test_patch_dict_clear_then_set_is_clean(self):
        self.assertEqual(problems_of(PATCH_DICT_CLEAR_THEN_SET), [],
                         "a clearing patch.dict at import that an import-time set of CLAUDE_CONFIG_DIR follows is named as a problem")

    def test_patch_dict_clear_false_is_not_a_clear(self):
        self.assertEqual(problems_of(PATCH_DICT_CLEAR_FALSE), [],
                         "an import-time patch.dict(os.environ, ..., clear=False).start() is read as a clear of CLAUDE_CONFIG_DIR")

    def test_patch_dict_without_clear_is_not_a_clear(self):
        self.assertEqual(problems_of(PATCH_DICT_NO_CLEAR), [],
                         "an import-time patch.dict(os.environ, ...).start() with no clear argument is read as a clear of CLAUDE_CONFIG_DIR")

    def test_clearing_patch_dict_that_sets_the_var_is_not_a_removal(self):
        self.assertEqual(problems_of(PATCH_DICT_CLEAR_SETS_VAR), [],
                         "an import-time clearing patch.dict whose values set CLAUDE_CONFIG_DIR is read as a removal of it")

    def test_comment_openers_inside_strings_do_not_hide_a_pop(self):
        found = problems_of(OPENERS_IN_STRINGS)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "a pop after a string that holds #, // or /* is not one problem: %r" % found)

    def test_pop_text_in_a_multi_line_string_is_clean(self):
        self.assertEqual(problems_of(MULTILINE_TEXT_HOLDS_POP), [],
                         "a pop written inside a multi-line string is read as a real pop")

    def test_lone_quote_in_a_comment_does_not_hide_a_pop(self):
        found = problems_of(LONE_QUOTE_IN_COMMENT)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "a pop after a comment with a lone quote is not one problem: %r" % found)

    def test_stray_stand_in_in_the_environment_changes_nothing(self):
        with mock.patch.dict(os.environ, {"TESTS_SET_CONFIG_UNDER_TEST": "lint/tests_set_config_stub_test.py"}):
            found = problems_of(POP_NEVER_SET)
        self.assertTrue(len(found) == 1 and found[0].startswith("test_case.py:"),
                        "a stand-in named in the caller's environment changes what the suite tests: %r" % found)

    def test_incident_shape_is_named_at_its_path(self):
        found = checker().problems(tree_of({INCIDENT_PATH: INCIDENT_SHAPE}))
        self.assertTrue(len(found) == 1 and found[0].startswith(INCIDENT_PATH + ":"),
                        "the incident's import-time pop, with a set only in a case's patch.dict, is not one problem named for %s: %r"
                        % (INCIDENT_PATH, found))

    def test_test_file_under_a_dot_folder_is_not_scanned(self):
        found = checker().problems(tree_of({"test_case.py": POP_NEVER_SET, ".claude/worktrees/x/test_a.py": POP_NEVER_SET}))
        self.assertTrue(any(problem.startswith("test_case.py:") for problem in found),
                        "the scan did not name the test file outside a dot folder: %r" % found)
        self.assertEqual(len(found), 1, "a test file under a dot folder is named as a problem: %r" % found)

    def test_test_file_under_a_skip_dir_is_not_scanned(self):
        found = checker().problems(tree_of({"test_case.py": POP_NEVER_SET, "node_modules/pkg/test_a.py": POP_NEVER_SET}))
        self.assertTrue(any(problem.startswith("test_case.py:") for problem in found),
                        "the scan did not name the test file outside node_modules: %r" % found)
        self.assertEqual(len(found), 1, "a test file under node_modules is named as a problem: %r" % found)

    def test_repo_has_no_problems_now(self):
        found = checker().problems(ROOT)
        self.assertEqual(found, [], "a test file of this repo pops CLAUDE_CONFIG_DIR at import and never sets it again: %r" % found)


if __name__ == "__main__":
    if "--stand-in" in sys.argv:  # this suite's own entry point sets its stand-in; unittest never sees the flag
        at = sys.argv.index("--stand-in")
        if at + 1 == len(sys.argv):
            sys.exit("--stand-in needs a path from the repo root")
        STAND_IN = sys.argv[at + 1]
        del sys.argv[at:at + 2]
    unittest.main()
