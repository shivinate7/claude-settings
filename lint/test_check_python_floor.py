#!/usr/bin/env python3
"""Cases for lint/check_python_floor.py. Run: python3 lint/test_check_python_floor.py

The Python floor for hooks/ and lint/ is 3.9 (README.md, lint/ste_lint.py). CI runs 3.11, so a 3.10+ call
passes CI and crashes a guard on a 3.9 install, where the guard fails open. The check runs vermin
(-t=3.9-) over the product files of hooks/ and lint/.

Interface the check must meet (the builder builds to it):
- python3 lint/check_python_floor.py [--root DIR]. DIR defaults to the repo root and holds hooks/ and lint/.
- A product file is a .py file in those folders whose name is not test_*.py, _test*.py or *_test.py.
- A `# novermin` line comment excuses its line, as vermin's marker does. The same text in a string does not.
- Exit 0 with no output when clean. Exit 1 with one line per offending file, naming the file and the
  feature, when a file needs more than 3.9. Exit 2, naming the cause, when vermin cannot run. The vermin
  command is FLOOR_VERMIN_CMD when set, so a test makes vermin missing or odd with that variable.

A case that expects a finding fails on a check that flags nothing. The controls expect silence.
"""
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, "check_python_floor.py")
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder

# The incident: a 3.10 call. CI runs 3.11 and passed it; a 3.9 guard crashed on it and failed open.
IGLOB = 'import glob\n\nFILES = glob.iglob("*.py", root_dir=".")\n'
SYS_NAMES = "import sys\n\nNAMES = sorted(sys.stdlib_module_names)\n"  # a 3.10 attribute, not a call
TOML_PLAIN = "try:\n    import tomllib\nexcept ImportError:\n    tomllib = None\n"  # 3.11, no marker
TOML_MARKED = "try:\n    import tomllib  # novermin\nexcept ImportError:\n    tomllib = None\n"
TOML_STRING_MARK = ('try:\n    import tomllib; NOTE = "# novermin"\nexcept ImportError:\n'
                    '    tomllib = None\n')
CLEAN = ('import glob\nimport os\n\n\ndef names(root):\n'
         '    return sorted(glob.glob(os.path.join(root, "*.py")))\n\n\nTOTAL = len(names("."))\n')
TRAP_COMMENT = 'x = 1  # glob.iglob("*.py", root_dir=".") needs 3.10\n'
TRAP_STRING = 'NOTE = \'call glob.iglob("*.py", root_dir=".") only on 3.10+\'\n'
TRAP_DOCSTRING = ('"""Module notes.\n\nDon\'t pass root_dir= to glob.iglob: that call is 3.10 only.\n'
                  '# this line is string text, not a comment\n"""\n')


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def need_check():
    if not os.path.isfile(CHECK):
        raise AssertionError("lint/check_python_floor.py does not exist: nothing holds the 3.9 floor")


def tree(files):
    """A fixture tree under the run folder, from {relpath: text}. hooks/ and lint/ exist even when empty."""
    root = tempfile.mkdtemp(prefix="pyfloor_", dir=RUN_FOLDER)
    for folder in ("hooks", "lint"):
        os.makedirs(os.path.join(root, folder))
    for rel, text in files.items():
        path = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    return root


def run_check(root=None, env=None):
    """Run the check on `root`, or on the repo root when none is given. -> (exit code, stdout and stderr).

    An inherited FLOOR_VERMIN_CMD is removed, so each case sets its own vermin or uses the default.
    """
    need_check()
    cmd = [sys.executable, CHECK] + (["--root", root] if root else [])
    environ = dict(os.environ)
    environ.pop("FLOOR_VERMIN_CMD", None)
    environ.update(env or {})
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=120, env=environ)
    return proc.returncode, proc.stdout + proc.stderr


def naming(out, name):
    """The output lines that name `name`."""
    return [line for line in out.splitlines() if name in line]


class Incident(unittest.TestCase):
    def test_iglob_root_dir_in_a_hook_is_flagged_and_named(self):
        # Pins the incident: a 3.10 call in hooks/, the folder the guards run from.
        code, out = run_check(tree({"hooks/x.py": IGLOB}))
        self.assertEqual(code, 1, "glob.iglob(root_dir=) (3.10) in hooks/x.py was not flagged: exit %d" % code)
        lines = naming(out, "x.py")
        self.assertEqual(len(lines), 1, "hooks/x.py needs one output line, got %d: %r" % (len(lines), out))
        self.assertIn("iglob", lines[0], "the line for hooks/x.py does not name the 3.10 feature: %r" % lines[0])


class Clean(unittest.TestCase):
    def test_three_nine_code_passes_with_no_output(self):
        # Control: 3.9-valid code in both folders is silent. A check that flags everything fails here.
        code, out = run_check(tree({"hooks/ok.py": CLEAN, "lint/ok.py": CLEAN}))
        self.assertEqual(code, 0, "3.9-valid code was flagged: exit %d, output %r" % (code, out))
        self.assertEqual(out, "", "a clean run printed output: %r" % out)

    def test_empty_product_folders_pass_with_no_output(self):
        # Empty state: hooks/ and lint/ hold no file. Scanning nothing is clean and silent.
        code, out = run_check(tree({}))
        self.assertEqual(code, 0, "empty hooks/ and lint/ were not clean: exit %d, output %r" % (code, out))
        self.assertEqual(out, "", "empty product folders printed output: %r" % out)


class Stdlib(unittest.TestCase):
    def test_sys_stdlib_module_names_in_a_hook_is_flagged(self):
        # Pins a 3.10 attribute, not a call.
        code, out = run_check(tree({"hooks/stdlib_names.py": SYS_NAMES}))
        self.assertEqual(code, 1, "sys.stdlib_module_names (3.10) in hooks/stdlib_names.py was not flagged: "
                                  "exit %d" % code)
        self.assertTrue(naming(out, "stdlib_names.py"), "no output line names hooks/stdlib_names.py: %r" % out)

    def test_test_files_are_not_scanned(self):
        # Scope first (P7): the same use in a product file of the same run is flagged, so the scan reached
        # hooks/. Then no test-named file is named.
        for name in ("test_foo.py", "_test_foo.py", "foo_test.py"):
            with self.subTest(name=name):
                root = tree({"hooks/stdlib_names.py": SYS_NAMES, "hooks/" + name: SYS_NAMES})
                code, out = run_check(root)
                self.assertEqual(code, 1, "scope control hooks/stdlib_names.py was not flagged: exit %d" % code)
                self.assertTrue(naming(out, "stdlib_names.py"), "scope control is not named: %r" % out)
                self.assertEqual(naming(out, name), [], "hooks/%s is a test file and was named: %r"
                                 % (name, out))

    def test_a_lone_test_file_with_the_use_passes(self):
        # Control: the use in hooks/test_foo.py alone is silent.
        code, out = run_check(tree({"hooks/test_foo.py": SYS_NAMES}))
        self.assertEqual(code, 0, "hooks/test_foo.py, a test file, was flagged: exit %d" % code)
        self.assertEqual(out, "", "hooks/test_foo.py, a test file, printed output: %r" % out)


class Marker(unittest.TestCase):
    def test_novermin_on_the_import_line_excuses_it(self):
        # Control: a 3.11 import under try/except ImportError passes with the marker on its line.
        code, out = run_check(tree({"lint/tomlcfg.py": TOML_MARKED}))
        self.assertEqual(code, 0, "the import marked # novermin was flagged: exit %d" % code)
        self.assertEqual(out, "", "the import marked # novermin printed output: %r" % out)

    def test_the_same_import_without_the_marker_is_flagged(self):
        # try/except ImportError does not excuse a 3.11 import. The marker does.
        code, out = run_check(tree({"lint/tomlcfg.py": TOML_PLAIN}))
        self.assertEqual(code, 1, "the unmarked 3.11 import in lint/tomlcfg.py was not flagged: exit %d" % code)
        self.assertTrue(naming(out, "tomlcfg.py"), "no output line names lint/tomlcfg.py: %r" % out)

    def test_marker_inside_a_string_does_not_excuse_the_line(self):
        # Trap: "# novermin" in a string is not a comment, so the 3.11 import on that line is still flagged.
        code, out = run_check(tree({"lint/tomlcfg.py": TOML_STRING_MARK}))
        self.assertEqual(code, 1, "a 3.11 import beside a marker in a string was not flagged: exit %d" % code)
        self.assertTrue(naming(out, "tomlcfg.py"), "no output line names lint/tomlcfg.py: %r" % out)


class Scope(unittest.TestCase):
    def test_a_lint_product_file_is_scanned(self):
        # The floor covers lint/ as well as hooks/.
        code, out = run_check(tree({"lint/floor_probe.py": IGLOB}))
        self.assertEqual(code, 1, "glob.iglob(root_dir=) (3.10) in lint/floor_probe.py was not flagged: "
                                  "exit %d" % code)
        self.assertTrue(naming(out, "floor_probe.py"), "no output line names lint/floor_probe.py: %r" % out)


class Traps(unittest.TestCase):
    def test_root_dir_text_in_a_comment_string_or_docstring_is_not_a_call(self):
        # Scanner trap: the text is not code, so it is no finding. A plain text match on root_dir= fails here.
        for label, text in (("comment", TRAP_COMMENT), ("string", TRAP_STRING), ("docstring", TRAP_DOCSTRING)):
            with self.subTest(case=label):
                code, out = run_check(tree({"hooks/notes.py": text}))
                self.assertEqual(code, 0, "root_dir= in a %s was flagged as a call: exit %d" % (label, code))
                self.assertEqual(out, "", "root_dir= in a %s printed output: %r" % (label, out))


class RealTree(unittest.TestCase):
    def test_repo_tree_passes_with_the_default_root(self):
        # The gate on the real tree. It fails when a product file above 3.9 lands without a marker.
        code, out = run_check()
        self.assertEqual(code, 0, "a product file in the repo's hooks/ or lint/ needs more than 3.9: "
                                  "exit %d, output %r" % (code, out))


MISSING_CMD = "vermin-not-installed-for-floor-test"  # a name no PATH holds


class Vermin(unittest.TestCase):
    """vermin cannot run: exit 2, and the output names the cause. An unread file is never clean."""

    def test_missing_vermin_command_exits_two_and_names_it(self):
        # One product file, so the check reaches vermin.
        code, out = run_check(tree({"hooks/ok.py": CLEAN}), env={"FLOOR_VERMIN_CMD": MISSING_CMD})
        self.assertEqual(code, 2, "a vermin command that cannot start gave exit %d, not 2: %r" % (code, out))
        self.assertIn(MISSING_CMD, out, "the output does not name the missing vermin command: %r" % out)

    def test_vermin_exiting_three_exits_two_and_names_the_exit(self):
        # An exit other than 0 or 1 is vermin failing, not a finding.
        cmd = shlex.join([sys.executable, "-c", "import sys; sys.stderr.write('odd\\n'); sys.exit(3)"])
        code, out = run_check(tree({"hooks/ok.py": CLEAN}), env={"FLOOR_VERMIN_CMD": cmd})
        self.assertEqual(code, 2, "a vermin that exited 3 gave exit %d, not 2: %r" % (code, out))
        self.assertIn("exit 3", out, "the output does not name vermin's exit 3: %r" % out)

    def test_vermin_exiting_one_with_no_finding_exits_two(self):
        # Exit 1 means findings. Exit 1 with none is output the check cannot read.
        cmd = shlex.join([sys.executable, "-c", "import sys; sys.exit(1)"])
        code, out = run_check(tree({"hooks/ok.py": CLEAN}), env={"FLOOR_VERMIN_CMD": cmd})
        self.assertEqual(code, 2, "a vermin that exited 1 with no finding gave exit %d, not 2: %r"
                         % (code, out))
        self.assertIn("exit 1", out, "the output does not name vermin's exit 1: %r" % out)


if __name__ == "__main__":
    unittest.main()
