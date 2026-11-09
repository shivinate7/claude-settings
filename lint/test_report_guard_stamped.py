#!/usr/bin/env python3
"""report_guard reads the helper modules of the install that runs it (roadmap step report-guard-stamped-copy).

The installer stamps a copy of the guard set into hooks/guard.d/<INSTALL_ID>/ and stamps the flat hooks/guard.py
with the same id (install.sh land_guard_set). report_guard puts hooks/ first on sys.path, so it reads the flat
helpers even when the install holds a stamped copy beside them. A half-installed hooks folder can then pair a new
report_guard with an old flat helper.

Each case builds an install tree in this run's folder, lint/ beside hooks/, and runs report_guard from it in a
fresh process. The name pinned is LANE_TAG, which report_guard imports at load from hooks/shared_names.py.
Each case names one stamp state:

- a stamp, with hooks/guard.d/<id>/ present: the stamped copy wins;
- no stamp, with a folder present: the flat copy wins;
- a stamp, with no folder: the flat copy wins.

Run with:

    python3 lint/test_report_guard_stamped.py -v

The run folder, the module set-up and the report_guard path come from lint/test_report_guard.py (trg), borrowed
by name. The install tree's module list comes from hooks/mutate_shared.py module_files, the one home.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_report_guard as trg  # noqa: E402  the run folder, the module set-up and tear-down (one home)
import mutate_shared  # noqa: E402  module_files: every module a copied guard may import (one home)

LINT_SRC = HERE
HOOKS_SRC = trg.HOOKS
PLACEHOLDER = '# INSTALL_ID = "uninstalled"'
FLAT_ID = "20261109121100123"       # an install id, as install.sh writes it: a date and a process id
OTHER_ID = "20261108090000456"      # the id of an earlier install, whose folder is still on disk
STAMPED_LANE_TAG = "fixture-stamped-lane"  # the distinct value the stamped shared_names carries
LANE_LINE = re.compile(r"^LANE_TAG = .*$", re.MULTILINE)
# A fresh process. -I drops PYTHONPATH and the script folder, so only report_guard's own sys.path edits decide
# what it imports. Prints the LANE_TAG it got and the file its shared_names module was loaded from.
PROBE_CODE = (
    "import json, runpy, sys\n"
    "ns = runpy.run_path(sys.argv[1], run_name='report_guard_probe')\n"
    "print(json.dumps({'lane_tag': ns.get('LANE_TAG'),\n"
    "                  'shared_names': getattr(sys.modules.get('shared_names'), '__file__', None)}))\n"
)


def setUpModule():
    trg.setUpModule()


def tearDownModule():
    trg.tearDownModule()


def real_lane_tag():
    """The repo's own LANE_TAG, read from hooks/shared_names.py: the value the flat copy of an install carries."""
    spec = importlib.util.spec_from_file_location("shared_names_under_test", os.path.join(HOOKS_SRC, "shared_names.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.LANE_TAG


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _stamp(text, install_id, name):
    """The installer's stamp (install.sh put_file): the placeholder line becomes INSTALL_ID = "<id>"."""
    found = text.count(PLACEHOLDER)
    if found != 1:
        raise AssertionError("fixture: %s holds %d placeholder lines, expected 1" % (name, found))
    return text.replace(PLACEHOLDER, 'INSTALL_ID = "%s"' % install_id)


def _copy_lint(dest):
    """lint/ as an install lands it: report_guard.py and its siblings, the non-test modules and the data files."""
    os.makedirs(dest)
    for name in sorted(os.listdir(LINT_SRC)):
        if name.startswith(("test_", "_test_")) or not name.endswith((".py", ".json")):
            continue
        shutil.copyfile(os.path.join(LINT_SRC, name), os.path.join(dest, name))


def _copy_hooks(dest, install_id):
    """The hooks' modules copied into dest. guard.py and each guard_*.py take the stamp when install_id is given."""
    os.makedirs(dest)
    for path in mutate_shared.module_files(HOOKS_SRC):
        name = os.path.basename(path)
        target = os.path.join(dest, name)
        if install_id is None or not (name == "guard.py" or name.startswith("guard_")):
            shutil.copyfile(path, target)
            continue
        with open(path, encoding="utf-8") as handle:
            _write(target, _stamp(handle.read(), install_id, name))


def build_tree(root, flat_id=None, folder_id=None):
    """An install tree under root, lint/ beside hooks/, and the report_guard path in it. flat_id stamps the flat
    guard files; None keeps the placeholder, as the repo copy has it. folder_id, when given, adds
    hooks/guard.d/<folder_id>/: the whole module set stamped with that id, whose shared_names.py carries
    STAMPED_LANE_TAG."""
    _copy_lint(os.path.join(root, "lint"))
    hooks = os.path.join(root, "hooks")
    _copy_hooks(hooks, flat_id)
    if folder_id is not None:
        folder = os.path.join(hooks, "guard.d", folder_id)
        _copy_hooks(folder, folder_id)
        names = os.path.join(folder, "shared_names.py")
        with open(names, encoding="utf-8") as handle:
            text = handle.read()
        found = len(LANE_LINE.findall(text))
        if found != 1:
            raise AssertionError("fixture: shared_names.py holds %d LANE_TAG lines, expected 1" % found)
        _write(names, LANE_LINE.sub('LANE_TAG = "%s"' % STAMPED_LANE_TAG, text))
    return os.path.join(root, "lint", "report_guard.py")


class StampedCopyTests(unittest.TestCase):

    def tree(self, name, flat_id=None, folder_id=None):
        root = tempfile.mkdtemp(prefix=name + "-", dir=trg.RUN_FOLDER)  # the run folder's, never the system temp dir
        self.addCleanup(shutil.rmtree, root, True)
        return root, build_tree(root, flat_id, folder_id)

    def assert_state(self, root, flat_id, folder_id):
        """Scope before subject (P7): the tree holds the stamp and the folder this case names."""
        self.assertNotEqual(real_lane_tag(), STAMPED_LANE_TAG, "fixture: the stamped value must differ from the flat one")
        with open(os.path.join(root, "hooks", "guard.py"), encoding="utf-8") as handle:
            stamp = re.search(r'^INSTALL_ID = "([^"]*)"', handle.read(), re.MULTILINE)
        self.assertEqual(stamp.group(1) if stamp else None, flat_id, "fixture: hooks/guard.py holds the wrong stamp")
        guard_d = os.path.join(root, "hooks", "guard.d")
        if folder_id is None:
            self.assertFalse(os.path.exists(guard_d), "fixture: hooks/guard.d exists, but the case names no folder")
        else:
            self.assertTrue(os.path.isdir(os.path.join(guard_d, folder_id)),
                            "fixture: hooks/guard.d/%s is missing" % folder_id)

    def probe(self, root, report_guard):
        """report_guard imported in a fresh process from the tree. Returns the LANE_TAG it read and the file."""
        run = subprocess.run([sys.executable, "-I", "-c", PROBE_CODE, report_guard],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, "report_guard did not import from the install tree: %s" % run.stderr[-400:])
        lines = run.stdout.strip().splitlines()
        self.assertTrue(lines, "the probe printed nothing")
        got = json.loads(lines[-1])
        loaded = got["shared_names"] or ""
        self.assertTrue(os.path.realpath(loaded).startswith(os.path.realpath(root) + os.sep),
                        "scope: report_guard loaded shared_names from outside the install tree: %s" % loaded)
        return got

    def test_rgs_red_stamp_and_folder_load_the_stamped_helper(self):
        # Catches: report_guard puts hooks/ first and reads the flat shared_names beside a stamped guard.d copy.
        root, report_guard = self.tree("stamped", flat_id=FLAT_ID, folder_id=FLAT_ID)
        self.assert_state(root, FLAT_ID, FLAT_ID)
        got = self.probe(root, report_guard)
        self.assertEqual(got["lane_tag"], STAMPED_LANE_TAG,
                         "report_guard read the flat shared_names from %s, not the stamped copy under "
                         "hooks/guard.d/%s/" % (got["shared_names"], FLAT_ID))

    def test_rgs_green_no_stamp_loads_the_flat_helper_beside_a_folder(self):
        # Catches: a report_guard that loads any guard.d folder, or reads the placeholder as a stamp.
        root, report_guard = self.tree("unstamped", flat_id=None, folder_id=OTHER_ID)
        self.assert_state(root, None, OTHER_ID)
        got = self.probe(root, report_guard)
        self.assertEqual(got["lane_tag"], real_lane_tag(),
                         "report_guard read a stamped copy although hooks/guard.py carries no stamp: %s"
                         % got["shared_names"])

    def test_rgs_green_stamp_without_a_folder_loads_the_flat_helper(self):
        # Catches: a report_guard that loads a stamped id whose folder is missing, and fails on it.
        root, report_guard = self.tree("no-folder", flat_id=FLAT_ID, folder_id=None)
        self.assert_state(root, FLAT_ID, None)
        got = self.probe(root, report_guard)
        self.assertEqual(got["lane_tag"], real_lane_tag(),
                         "report_guard did not load the flat shared_names when the stamped folder is missing: %s"
                         % got["shared_names"])


if __name__ == "__main__":
    unittest.main()
