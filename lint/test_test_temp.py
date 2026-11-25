"""Cases for isolated_config(run) in lint/_test_temp.py: CLAUDE_CONFIG_DIR points at a fresh folder under the run folder while the
block runs, is put back after it (also when the block raises), and HOME and USERPROFILE stay as they were.

--stand-in PATH, a path from the repo root, names a stand-in module to run these cases against: lint/_test_temp_stub_test.py
changes nothing, and lint/_test_temp_leaky_stub_test.py never puts anything back. The red runs use them. Without it, the cases run
against lint/_test_temp.py. The caller's environment is never read: a stray value there changes nothing.

Run: python3 lint/test_test_temp.py [--stand-in PATH]
"""
import atexit
import importlib.util
import os
import shutil
import sys
import unittest
from unittest import mock

import _test_temp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAND_IN = None  # the __main__ block sets it from --stand-in; the caller's environment is never read
RUN = _test_temp.run_folder()  # this run's one folder (test-temp-standard); removed when the process exits
atexit.register(shutil.rmtree, RUN, True)
VAR = "CLAUDE_CONFIG_DIR"
PRIOR = "/prior/config/the/block/must/restore"  # what a caller sets before the block


def isolated_config_under_test():
    """The isolated_config the cases drive: the stand-in named by --stand-in, else the one in lint/_test_temp.py."""
    if not STAND_IN:
        return _test_temp.isolated_config
    spec = importlib.util.spec_from_file_location("test_temp_under_test", os.path.join(ROOT, STAND_IN))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.isolated_config


def put(value):
    """Set CLAUDE_CONFIG_DIR to `value`, or unset it when `value` is None."""
    if value is None:
        os.environ.pop(VAR, None)
    else:
        os.environ[VAR] = value


def under(path, folder):
    """True when `path` is a folder strictly inside `folder`, both resolved."""
    real, base = os.path.realpath(path), os.path.realpath(folder)
    return os.path.isdir(real) and real != base and os.path.commonpath([real, base]) == base


class IsolatedConfig(unittest.TestCase):
    def setUp(self):
        self.caller = os.environ.get(VAR)  # the test process's own value, put back in tearDown
        self.homes = (os.environ.get("HOME"), os.environ.get("USERPROFILE"))

    def tearDown(self):
        put(self.caller)

    def test_points_inside_run_folder_while_active(self):
        put(PRIOR)
        with isolated_config_under_test()(RUN) as folder:
            self.assertTrue(under(os.environ.get(VAR) or "", RUN),
                            "CLAUDE_CONFIG_DIR is %r inside the block, not a folder under the run folder" % os.environ.get(VAR))
            self.assertEqual(os.environ.get(VAR), folder, "CLAUDE_CONFIG_DIR does not name the folder the block yields")

    def test_restores_prior_value(self):
        put(PRIOR)
        with isolated_config_under_test()(RUN):
            pass
        self.assertEqual(os.environ.get(VAR), PRIOR,
                         "CLAUDE_CONFIG_DIR is %r after the block, not the value set before it" % os.environ.get(VAR))

    def test_restores_unset(self):
        put(None)
        with isolated_config_under_test()(RUN):
            pass
        self.assertIsNone(os.environ.get(VAR), "CLAUDE_CONFIG_DIR is set after the block, though it was unset before")

    def test_restores_when_block_raises(self):
        put(PRIOR)
        with self.assertRaises(RuntimeError):
            with isolated_config_under_test()(RUN):
                raise RuntimeError("the block's own error")
        self.assertEqual(os.environ.get(VAR), PRIOR,
                         "CLAUDE_CONFIG_DIR is %r after a block that raised, not the value set before it" % os.environ.get(VAR))

    def test_leaves_home_and_userprofile_alone(self):
        put(PRIOR)
        with isolated_config_under_test()(RUN):
            self.assertEqual((os.environ.get("HOME"), os.environ.get("USERPROFILE")), self.homes,
                             "HOME or USERPROFILE changed inside the block")
        self.assertEqual((os.environ.get("HOME"), os.environ.get("USERPROFILE")), self.homes,
                         "HOME or USERPROFILE changed after the block")

    def test_each_block_gets_a_fresh_folder(self):
        put(None)
        with isolated_config_under_test()(RUN) as first:
            pass
        with isolated_config_under_test()(RUN) as second:
            pass
        self.assertNotEqual(first, second, "two blocks gave the same folder, so one block's files reach the next")

    def test_stray_stand_in_in_the_environment_changes_nothing(self):
        put(PRIOR)
        with mock.patch.dict(os.environ, {"TEST_TEMP_UNDER_TEST": "lint/_test_temp_stub_test.py"}):
            with isolated_config_under_test()(RUN):
                self.assertTrue(under(os.environ.get(VAR) or "", RUN),
                                "a stand-in named in the caller's environment changes what the suite tests: CLAUDE_CONFIG_DIR is %r inside the block"
                                % os.environ.get(VAR))


if __name__ == "__main__":
    if "--stand-in" in sys.argv:  # this suite's own entry point sets its stand-in; unittest never sees the flag
        at = sys.argv.index("--stand-in")
        if at + 1 == len(sys.argv):
            sys.exit("--stand-in needs a path from the repo root")
        STAND_IN = sys.argv[at + 1]
        del sys.argv[at:at + 2]
    unittest.main()
