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
# The open count of hooks/guard.py in one process. report_guard runs as the Stop hook runs it, then question_form
# imports it again for a reply's Input Needed (hooks/question_form.py _option_keys). An audit hook counts each open of
# the file. argv: report_guard's path, the install root, the reply text.
REIMPORT_CODE = (
    "import json, os, runpy, sys\n"
    "guard_py = os.path.realpath(os.path.join(sys.argv[2], 'hooks', 'guard.py'))\n"
    "opened = []\n"
    "def _count(event, args):\n"
    "    if event == 'open' and args and isinstance(args[0], str) and os.path.realpath(args[0]) == guard_py:\n"
    "        opened.append(args[0])\n"
    "sys.addaudithook(_count)\n"
    "ns = runpy.run_path(sys.argv[1], run_name='report_guard_probe')\n"
    "sys.path.insert(0, os.path.join(sys.argv[2], 'hooks'))\n"
    "import question_form\n"
    "overlap = question_form.key_overlap(sys.argv[3], [])\n"
    "print(json.dumps({'opens': len(opened), 'reimported': 'report_guard' in sys.modules,\n"
    "                  'lane_tag': ns.get('LANE_TAG'), 'overlap': overlap}))\n"
)
REIMPORT_REPLY = "## Input Needed\n\nWhich copy should report_guard read?\n\na) the flat copy\nb) the stamped copy\n"
# argv: report_guard's path, then the name of a module to import once report_guard has set the path.
MODULE_CODE = (
    "import importlib, json, runpy, sys\n"
    "ns = runpy.run_path(sys.argv[1], run_name='report_guard_probe')\n"
    "module = importlib.import_module(sys.argv[2])\n"
    "print(json.dumps({'lane_tag': ns.get('LANE_TAG'), 'module_file': module.__file__}))\n"
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


def build_tree(root, flat_id=None, folder_id=None, flat_text=None):
    """An install tree under root, lint/ beside hooks/, and the report_guard path in it. flat_id stamps the flat
    guard files; None keeps the placeholder, as the repo copy has it. folder_id, when given, adds
    hooks/guard.d/<folder_id>/: the whole module set stamped with that id, whose shared_names.py carries
    STAMPED_LANE_TAG. flat_text, when given, replaces the flat guard.py with that text."""
    _copy_lint(os.path.join(root, "lint"))
    hooks = os.path.join(root, "hooks")
    _copy_hooks(hooks, flat_id)
    if flat_text is not None:
        _write(os.path.join(hooks, "guard.py"), flat_text)
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

    def tree(self, name, flat_id=None, folder_id=None, flat_text=None):
        root = tempfile.mkdtemp(prefix=name + "-", dir=trg.RUN_FOLDER)  # the run folder's, never the system temp dir
        self.addCleanup(shutil.rmtree, root, True)
        return root, build_tree(root, flat_id, folder_id, flat_text)

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

    def run_probe(self, code, args, what):
        """Run code in a fresh process with args; return its last JSON line. A non-zero exit fails with what."""
        run = subprocess.run([sys.executable, "-I", "-c", code, *args], capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, "%s: %s" % (what, run.stderr[-400:]))
        lines = run.stdout.strip().splitlines()
        self.assertTrue(lines, "the probe printed nothing")
        return json.loads(lines[-1])

    def probe(self, root, report_guard, what="report_guard did not import from the install tree"):
        """report_guard imported in a fresh process from the tree. Returns the LANE_TAG it read and the file."""
        got = self.run_probe(PROBE_CODE, [report_guard], what)
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
        # The flat guard.py holds only the placeholder: the repo copy's prose line, INSTALL_ID = "<id>", would match
        # first under an unanchored regex and hide the placeholder.
        root, report_guard = self.tree("unstamped", flat_id=None, folder_id="uninstalled", flat_text=PLACEHOLDER + "\n")
        self.assert_state(root, None, "uninstalled")
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

    def test_rgs_red_reimport_opens_guard_at_most_once(self):
        # Catches: report_guard reads hooks/guard.py again when question_form re-imports it for a reply's Input Needed.
        root, report_guard = self.tree("reimport", flat_id=FLAT_ID, folder_id=FLAT_ID)
        self.assert_state(root, FLAT_ID, FLAT_ID)
        got = self.run_probe(REIMPORT_CODE, [report_guard, root, REIMPORT_REPLY],
                             "report_guard did not run, or question_form did not load it")
        self.assertTrue(got["reimported"], "scope: question_form did not import report_guard for the reply")
        self.assertLessEqual(got["opens"], 1,
                             "hooks/guard.py was opened %d times in one run, at most 1 allowed" % got["opens"])

    def test_rgs_red_non_utf8_byte_in_guard_does_not_crash_import(self):
        # Catches: hooks/guard.py is read as strict UTF-8 for its stamp, so one bad byte stops report_guard importing.
        root, report_guard = self.tree("non-utf8", flat_id=None, folder_id=OTHER_ID)
        self.assert_state(root, None, OTHER_ID)
        guard_py = os.path.join(root, "hooks", "guard.py")
        with open(guard_py, "ab") as handle:
            handle.write(b"\n# \xff is not UTF-8\n")
        with self.assertRaises(UnicodeDecodeError, msg="fixture: hooks/guard.py decodes as UTF-8"):
            with open(guard_py, "rb") as handle:
                handle.read().decode("utf-8")
        got = self.probe(root, report_guard, what="report_guard crashed on a non-UTF-8 byte in hooks/guard.py")
        self.assertEqual(got["lane_tag"], real_lane_tag(),
                         "report_guard did not fall back to the flat helpers: it loaded %s" % got["shared_names"])

    def test_rgs_green_stamped_folder_missing_a_module_imports_it_from_flat(self):
        # Catches: a stamped folder short of one module makes report_guard fail on that module, not read the flat copy.
        # Green on head: the folder comes first on the path, and a name it lacks falls through to hooks/.
        for name in ("local_time", "override"):
            with self.subTest(module=name):
                root, report_guard = self.tree("short-" + name, flat_id=FLAT_ID, folder_id=FLAT_ID)
                self.assert_state(root, FLAT_ID, FLAT_ID)
                folder_module = os.path.join(root, "hooks", "guard.d", FLAT_ID, name + ".py")
                self.assertTrue(os.path.isfile(folder_module), "fixture: the stamped folder holds no %s.py" % name)
                os.remove(folder_module)
                got = self.run_probe(MODULE_CODE, [report_guard, name],
                                     "report_guard did not import, or %s did not load, with the folder short" % name)
                self.assertEqual(got["lane_tag"], STAMPED_LANE_TAG,
                                 "scope: report_guard did not put the stamped folder first: %s" % got["lane_tag"])
                self.assertEqual(os.path.realpath(got["module_file"]),
                                 os.path.realpath(os.path.join(root, "hooks", name + ".py")),
                                 "%s did not import from the flat hooks/ once the stamped folder lost it" % name)


if __name__ == "__main__":
    unittest.main()
