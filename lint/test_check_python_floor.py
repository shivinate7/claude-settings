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
  command is FLOOR_VERMIN_CMD when set. Otherwise the check runs a cached venv that holds the pin in VERMIN_PIN,
  built on first use; FLOOR_VENV_DIR overrides the cache path. That bootstrap is the check's only network use.
- A `|` between types needs 3.10 when it runs. In an annotation (not evaluated under `from __future__
  import annotations`) the check flags any `|`, since a flag OR is never an annotation. In a module or class
  assignment value, or as isinstance/issubclass's second argument, it flags a `|` with a None, builtin-type or
  builtin-subscript operand. Its line names file:line and says union type `|` needs 3.10. vermin does not
  flag these by default, so the check runs an ast pass.

A case that expects a finding fails on a check that flags nothing. The controls expect silence.
"""
import ast
import contextlib
import importlib.util
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, "check_python_floor.py")
REPO = os.path.dirname(HERE)
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


def pinned_version():
    """The pin the check holds in its one home, VERMIN_PIN. None when the check holds none."""
    need_check()
    with open(CHECK, encoding="utf-8") as handle:
        match = re.search(r'^VERMIN_PIN = "([^"]+)"', handle.read(), re.M)
    return match.group(1) if match else None


def require_pin():
    pin = pinned_version()
    if pin is None:
        raise AssertionError("lint/check_python_floor.py has no VERMIN_PIN constant: the vermin pin has no home")
    return pin


_WHEELS = []  # the one local index, made on first use


def index_env():
    """Pip reads only a local index that holds the pinned vermin, so the suite reaches the network once."""
    pin = pinned_version()
    if pin is None:
        return {}  # no pin yet: the check runs on the test python's own vermin
    if not _WHEELS:
        wheels = os.path.join(RUN_FOLDER, "wheels")
        os.makedirs(wheels, exist_ok=True)
        proc = subprocess.run([sys.executable, "-m", "pip", "download", "--no-deps", "-q", "-d", wheels,
                               "vermin==" + pin], capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            raise AssertionError("could not download vermin==%s for the local index: %s"
                                 % (pin, proc.stderr.strip()[-300:]))
        _WHEELS.append(wheels)
    return {"PIP_NO_INDEX": "1", "PIP_FIND_LINKS": _WHEELS[0]}


def shared_cache():
    """One cache for the suite's fixtures, so they share one bootstrap."""
    return os.path.join(RUN_FOLDER, "shared-vermin")


def fresh_cache():
    """A cache path that does not exist yet, under the run folder."""
    return os.path.join(tempfile.mkdtemp(prefix="cache_", dir=RUN_FOLDER), "vermin")


def cache_python(cache):
    """The python inside a cache venv, for fixtures that change what the cache holds."""
    parts = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    return os.path.join(cache, *parts)


def load_check_module():
    """A fresh copy of the check, so its one-time bootstrap memo starts empty in this process."""
    spec = importlib.util.spec_from_file_location("floor_check_" + os.urandom(4).hex(), CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def check_env(changes):
    """Set environment values for an in-process check; None removes one. The old values come back on exit."""
    saved = {key: os.environ.get(key) for key in changes}
    try:
        for key, value in changes.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def bootstrap_starts(cache):
    """The command lines the check starts through _nowindow.run while it bootstraps `cache` in this process."""
    starts = []
    module = load_check_module()
    real = module._nowindow.run

    def counting(cmd, *args, **kwargs):
        starts.append(" ".join(str(part) for part in cmd))
        return real(cmd, *args, **kwargs)

    module._nowindow.run = counting
    try:
        changes = dict(index_env())
        changes.update({"FLOOR_VENV_DIR": cache, "FLOOR_VERMIN_CMD": None})
        with check_env(changes):
            module.vermin_command()
    finally:
        module._nowindow.run = real
    return starts


def empty_index():
    path = os.path.join(RUN_FOLDER, "empty-index")
    os.makedirs(path, exist_ok=True)
    return path


_BARE = []  # a python with no vermin, made on first use


def bare_python():
    """A python with no vermin in it, made once per run. The lint's python3 has none either."""
    if not _BARE:
        path = os.path.join(RUN_FOLDER, "bare-venv")
        proc = subprocess.run([sys.executable, "-m", "venv", "--without-pip", path], capture_output=True,
                              text=True, timeout=300)
        if proc.returncode != 0:
            raise AssertionError("could not make a python without vermin: %s" % proc.stderr.strip()[-300:])
        exe = os.path.join(path, "Scripts", "python.exe") if os.name == "nt" else os.path.join(path, "bin", "python")
        probe = subprocess.run([exe, "-c", "import vermin"], capture_output=True, text=True, timeout=120)
        if probe.returncode == 0:
            raise AssertionError("the python without vermin imports vermin: a bootstrap case would prove nothing")
        _BARE.append(exe)
    return _BARE[0]


def run_check(root=None, env=None, python=None):
    """Run the check on `root` (or the repo root) with `python` (default: this one). -> (exit code, stdout and stderr).

    The suite's environment: no inherited FLOOR_VERMIN_CMD, one shared vermin cache, and a local index when the check
    holds a pin. A value of None in `env` removes that variable.
    """
    need_check()
    cmd = [python or sys.executable, CHECK] + (["--root", root] if root else [])
    environ = dict(os.environ)
    environ.pop("FLOOR_VERMIN_CMD", None)
    environ["FLOOR_VENV_DIR"] = shared_cache()
    environ.update(index_env())
    for key, value in (env or {}).items():
        if value is None:
            environ.pop(key, None)
        else:
            environ[key] = value
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=300, env=environ)
    return proc.returncode, proc.stdout + proc.stderr


def is_test_name(name):
    return name.startswith("test_") or name.startswith("_test") or name.endswith("_test.py")


def naming(out, name):
    """The output lines that name `name`."""
    return [line for line in out.splitlines() if name in line]


def flagged_at(out, rel, lineno):
    """The output lines that name rel:lineno. A line 1 does not match rel:10."""
    pattern = re.compile(re.escape(rel) + r":%d(?!\d)" % lineno)
    return [line for line in out.splitlines() if pattern.search(line)]


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


# A `|` between types needs 3.10 when it runs. Each form evaluates one at module, class or call level.
FUTURE = "from __future__ import annotations\n\n"
UNION_FORMS = (
    ("function argument annotation", "def f(x: str | None = None):\n    return x\n", 1),
    ("function return annotation", "def f() -> int | None:\n    return None\n", 1),
    ("module annotation", "x: int | None = None\n", 1),
    ("class annotation", "class C:\n    x: int | None = None\n", 2),
    ("module assignment value", "Alias = str | None\n", 1),
    ("class assignment value", "class C:\n    Alias = str | None\n", 2),
    ("isinstance second argument", "ok = isinstance(value, int | str)\n", 1),
    ("issubclass second argument", "ok = issubclass(kind, int | str)\n", 1),
    ("None on the left", "Alias = None | int\n", 1),
    ("subscripted builtin operand", "Alias = list[str] | None\n", 1),
    ("builtin beside a plain name", "Alias = int | Widget\n", 1),
    # The argument check alone: these are not assignment values, so only the isinstance/issubclass rule flags them.
    ("isinstance inside a function body", "def f(value):\n    return isinstance(value, int | str)\n", 2),
    ("issubclass inside a function body", "def f(kind):\n    return issubclass(kind, int | str)\n", 2),
    ("isinstance in a module-level if", "if isinstance(value, int | str):\n    pass\n", 1),
)


class UnionForms(unittest.TestCase):
    def test_each_form_is_flagged_and_named_by_file_and_line(self):
        for label, text, lineno in UNION_FORMS:
            with self.subTest(form=label):
                code, out = run_check(tree({"hooks/x.py": text}))
                self.assertEqual(code, 1, "%s: union type `|` at hooks/x.py:%d was not flagged: exit %d"
                                 % (label, lineno, code))
                named = flagged_at(out, "hooks/x.py", lineno)
                self.assertTrue(any("union" in line and "3.10" in line for line in named),
                                "%s: no line names hooks/x.py:%d as a union type needing 3.10: %r"
                                % (label, lineno, out))

    def test_novermin_text_in_a_string_does_not_excuse_the_line(self):
        # Addition beyond the spec. As with vermin's marker, the text in a string is not a comment.
        code, out = run_check(tree({"hooks/x.py": 'Alias = str | None; NOTE = "# novermin"\n'}))
        self.assertEqual(code, 1, "a union type beside a marker in a string was not flagged: exit %d" % code)
        self.assertTrue(flagged_at(out, "hooks/x.py", 1), "no output line names hooks/x.py:1: %r" % out)

    def test_lint_folder_is_scanned_for_union_types(self):
        # The floor covers lint/ as well as hooks/.
        code, out = run_check(tree({"lint/union_probe.py": "Alias = str | None\n"}))
        self.assertEqual(code, 1, "union type `|` in lint/union_probe.py was not flagged: exit %d" % code)
        self.assertTrue(flagged_at(out, "lint/union_probe.py", 1),
                        "no output line names lint/union_probe.py:1: %r" % out)


class UnionFuture(unittest.TestCase):
    def test_annotations_are_not_evaluated_under_the_future_import(self):
        # No annotation runs under the future import, so a `|` in one is never evaluated.
        text = FUTURE + "def f(x: str | None = None) -> int | None:\n    return None\n\n\ny: int | None = None\n"
        code, out = run_check(tree({"hooks/x.py": text}))
        self.assertEqual(code, 0, "annotations under the future import were flagged: exit %d, output %r"
                         % (code, out))
        self.assertEqual(out, "", "a clean run printed output: %r" % out)

    def test_assignment_value_is_still_flagged_under_the_future_import(self):
        # An assignment value runs at import time, so the future import does not cover it.
        code, out = run_check(tree({"hooks/x.py": FUTURE + "Alias = str | None\n"}))
        self.assertEqual(code, 1, "an assignment value under the future import was not flagged: exit %d" % code)
        self.assertTrue(flagged_at(out, "hooks/x.py", 3), "no output line names hooks/x.py:3: %r" % out)

    def test_isinstance_argument_is_still_flagged_under_the_future_import(self):
        code, out = run_check(tree({"hooks/x.py": FUTURE + "ok = isinstance(value, int | str)\n"}))
        self.assertEqual(code, 1, "an isinstance argument under the future import was not flagged: exit %d"
                         % code)
        self.assertTrue(flagged_at(out, "hooks/x.py", 3), "no output line names hooks/x.py:3: %r" % out)

    def test_isinstance_inside_a_function_is_still_flagged_under_the_future_import(self):
        # A call runs, so the future import does not exempt its second argument.
        code, out = run_check(tree({"hooks/x.py": FUTURE + "def f(value):\n    return isinstance(value, int | str)\n"}))
        self.assertEqual(code, 1, "an isinstance argument in a function body under the future import was not "
                                  "flagged: exit %d" % code)
        self.assertTrue(flagged_at(out, "hooks/x.py", 4), "no output line names hooks/x.py:4: %r" % out)


class UnionNegatives(unittest.TestCase):
    def assert_silent(self, label, files):
        code, out = run_check(tree(files))
        self.assertEqual(code, 0, "%s was flagged: exit %d, output %r" % (label, code, out))
        self.assertEqual(out, "", "%s printed output: %r" % (label, out))

    def test_operands_that_are_not_types_are_not_flagged(self):
        # Bit flags, set unions, plain names and an int are not types, so their `|` is no union type.
        cases = (
            ("bit flags", "import re\n\nFLAGS = re.MULTILINE | re.DOTALL\n"),
            ("a flag with an int", "def combine(flags):\n    return flags | 0x2\n"),
            ("plain names", "combined = a | b\n"),
            ("set calls", "CHANGED = set(before) | set(after)\n"),
        )
        for label, text in cases:
            with self.subTest(form=label):
                self.assert_silent(label, {"hooks/x.py": text})

    def test_local_variable_annotation_is_not_evaluated(self):
        # A local annotation in a function body is never evaluated.
        self.assert_silent("a local annotation", {"hooks/x.py": "def f():\n    x: int | None = None\n    return x\n"})

    def test_string_annotations_are_not_flagged(self):
        cases = (
            ("a string argument annotation", 'def f(x: "str | None" = None):\n    return x\n'),
            ("a string module annotation", 'x: "int | None" = None\n'),
        )
        for label, text in cases:
            with self.subTest(form=label):
                self.assert_silent(label, {"hooks/x.py": text})

    def test_comment_and_docstring_text_is_not_flagged(self):
        cases = (
            ("a comment", "# Alias = str | None\n"),
            ("a docstring", '"""Alias = str | None needs 3.10."""\n'),
        )
        for label, text in cases:
            with self.subTest(form=label):
                self.assert_silent(label, {"hooks/x.py": text})

    def test_test_file_is_excluded_and_the_scope_control_is_named(self):
        # Scope first: the same line in hooks/x.py is flagged in the same run, so the scan reached hooks/.
        files = {"hooks/x.py": "Alias = str | None\n", "hooks/test_foo.py": "Alias = str | None\n"}
        code, out = run_check(tree(files))
        self.assertEqual(code, 1, "scope control hooks/x.py was not flagged: exit %d" % code)
        self.assertTrue(flagged_at(out, "hooks/x.py", 1), "scope control is not named: %r" % out)
        self.assertEqual(naming(out, "test_foo.py"), [], "hooks/test_foo.py, a test file, was named: %r" % out)

    def test_novermin_on_the_line_excuses_it(self):
        cases = (
            ("an annotation line", "def f(x: str | None = None):  # novermin\n    return x\n"),
            ("an assignment line", "Alias = str | None  # novermin\n"),
        )
        for label, text in cases:
            with self.subTest(form=label):
                self.assert_silent(label, {"hooks/x.py": text})

    def test_local_annotation_at_each_form_is_not_evaluated(self):
        # A local annotation in a function body is never evaluated, whatever its union.
        for form in UNION_TYPES:
            with self.subTest(form=form):
                self.assert_silent(form, {"hooks/x.py": "def f():\n    x: %s = None\n    return x\n" % form})

    def test_string_annotations_at_each_position_are_not_flagged(self):
        for form in UNION_TYPES:
            with self.subTest(form=form):
                text, _ = positions_file('"%s"' % form)
                self.assert_silent(form, {"hooks/x.py": text})

    def test_novermin_on_the_union_line_excuses_each_position(self):
        for form in UNION_TYPES:
            with self.subTest(form=form):
                text, _ = positions_file(form, marker="  # novermin")
                self.assert_silent(form, {"hooks/x.py": text})

    def test_future_import_exempts_each_position(self):
        for form in UNION_TYPES:
            with self.subTest(form=form):
                text, _ = positions_file(form, prefix=["from __future__ import annotations"])
                self.assert_silent(form, {"hooks/x.py": text})

    def test_test_file_is_excluded_at_each_position(self):
        # Scope first: the same union in hooks/x.py is flagged in the same run, so the scan reached hooks/.
        for form in UNION_TYPES:
            with self.subTest(form=form):
                text, _ = positions_file(form)
                code, out = run_check(tree({"hooks/x.py": "mod_scope: %s\n" % form, "hooks/test_foo.py": text}))
                self.assertEqual(code, 1, "scope control hooks/x.py (%s) was not flagged: exit %d" % (form, code))
                self.assertTrue(flagged_at(out, "hooks/x.py", 1), "scope control is not named: %r" % out)
                self.assertEqual(naming(out, "test_foo.py"), [], "hooks/test_foo.py was named: %r" % out)


# Annotation positions, each holding one union. `{U}` is the union and `{i}` a unique suffix. The union sits on
# the line that holds `{U}`, which is the line the check names.
ANNOTATION_POSITIONS = (
    ("function argument", ["def arg_{i}(a: {U}):", "    return a"]),
    ("function return", ["def ret_{i}() -> {U}:", "    return None"]),
    ("vararg", ["def var_{i}(*args: {U}):", "    return args"]),
    ("kwarg", ["def kw_{i}(**kwargs: {U}):", "    return kwargs"]),
    ("positional-only", ["def posonly_{i}(a: {U}, /):", "    return a"]),
    ("keyword-only", ["def kwonly_{i}(*, a: {U}):", "    return a"]),
    ("async function", ["async def afn_{i}(a: {U}):", "    return a"]),
    ("nested function", ["def outer_{i}():", "    def inner(a: {U}):", "        return a", "    return inner"]),
    ("method", ["class Box_{i}:", "    def m(self, a: {U}):", "        return a"]),
    ("module annotation", ["mod_{i}: {U}"]),
    ("class annotation", ["class Holder_{i}:", "    attr: {U}"]),
)
# Forms that are not builtin types: a flag OR is never an annotation, so each must be flagged in every position.
UNION_TYPES = (
    "ast.FunctionDef | ast.AsyncFunctionDef",
    "Foo | Bar",
    "List[int] | Dict[int, int]",
    "typing.List[int] | typing.Dict[str, int]",
    "pathlib.Path | pathlib.PurePath",
    "Sequence[Segment] | Segment",
)


def positions_file(union, prefix=(), marker=""):
    """A fixture with every annotation position holding `union`. -> (text, {position: line of the union})."""
    lines = list(prefix)
    where = {}
    for index, (label, block) in enumerate(ANNOTATION_POSITIONS):
        if lines:
            lines.append("")
        for line in block:
            if "{U}" in line:
                where[label] = len(lines) + 1
                lines.append(line.replace("{U}", union).replace("{i}", str(index)) + marker)
            else:
                lines.append(line.replace("{i}", str(index)))
    return "\n".join(lines) + "\n", where


class AnnotationPositions(unittest.TestCase):
    def test_each_form_is_flagged_at_each_annotation_position(self):
        for form in UNION_TYPES:
            text, where = positions_file(form)
            code, out = run_check(tree({"hooks/x.py": text}))
            for label, lineno in where.items():
                with self.subTest(form=form, position=label):
                    named = flagged_at(out, "hooks/x.py", lineno)
                    self.assertTrue(any("union" in line and "3.10" in line for line in named),
                                    "union type `|` at the %s, hooks/x.py:%d, was not flagged: exit %d, output %r"
                                    % (label, lineno, code, out))


class Bootstrap(unittest.TestCase):
    """With no FLOOR_VERMIN_CMD, the check runs a cached venv holding the pin, built on first use."""

    def marker(self, cache):
        return os.path.join(cache, ".ok")

    def test_fresh_cache_bootstraps_vermin_and_flags_the_fixture(self):
        python = bare_python()
        cache = fresh_cache()
        code, out = run_check(tree({"hooks/x.py": IGLOB}), env={"FLOOR_VENV_DIR": cache}, python=python)
        self.assertEqual(code, 1, "with no vermin in its python and a fresh cache, the check exited %d, not 1: %r"
                         % (code, out))
        self.assertTrue(any("iglob" in line for line in naming(out, "x.py")),
                        "the bootstrapped check did not flag hooks/x.py's iglob: %r" % out)
        self.assertTrue(os.path.isfile(self.marker(cache)), "the bootstrap left no .ok marker in the cache")

    def test_second_run_reuses_the_cache_and_installs_nothing(self):
        python = bare_python()
        cache = fresh_cache()
        code, out = run_check(tree({"hooks/x.py": IGLOB}), env={"FLOOR_VENV_DIR": cache}, python=python)
        self.assertEqual(code, 1, "the first run did not bootstrap: exit %d, output %r" % (code, out))
        self.assertTrue(os.path.isfile(self.marker(cache)), "the first run wrote no .ok marker: nothing was cached")
        stamp = os.stat(self.marker(cache)).st_mtime_ns
        # An empty index: a second install would fail, so exit 1 proves the run installed nothing.
        code, out = run_check(tree({"hooks/x.py": IGLOB}),
                              env={"FLOOR_VENV_DIR": cache, "PIP_NO_INDEX": "1", "PIP_FIND_LINKS": empty_index()},
                              python=python)
        self.assertEqual(code, 1, "the second run reinstalled: with an empty index it exited %d, not 1: %r"
                         % (code, out))
        self.assertEqual(os.stat(self.marker(cache)).st_mtime_ns, stamp, "the second run rewrote the cache marker")

    def test_offline_with_a_fresh_cache_exits_two_naming_the_pin(self):
        python = bare_python()
        pin = require_pin()
        cache = fresh_cache()
        code, out = run_check(tree({"hooks/x.py": IGLOB}),
                              env={"FLOOR_VENV_DIR": cache, "PIP_NO_INDEX": "1", "PIP_FIND_LINKS": empty_index()},
                              python=python)
        self.assertEqual(code, 2, "an offline bootstrap exited %d, not 2: %r" % (code, out))
        self.assertTrue(out.strip(), "exit 2 printed nothing: an unread check is never clean")
        self.assertIn(pin, out, "exit 2 does not name vermin %s, the pin that failed to install: %r" % (pin, out))
        self.assertFalse(os.path.exists(self.marker(cache)), "a failed install left a .ok marker")

    def test_half_made_cache_without_the_marker_is_rebuilt(self):
        python = bare_python()
        cache = fresh_cache()
        os.makedirs(cache)
        with open(os.path.join(cache, "pyvenv.cfg"), "w", encoding="utf-8") as handle:
            handle.write("home = /nowhere\n")  # an old venv, cut short before its .ok marker
        partial = os.path.join(cache, "half-made")
        with open(partial, "w", encoding="utf-8") as handle:
            handle.write("an install cut short\n")
        code, out = run_check(tree({"hooks/x.py": IGLOB}), env={"FLOOR_VENV_DIR": cache}, python=python)
        self.assertEqual(code, 1, "a half-made cache without .ok was not rebuilt: exit %d, output %r" % (code, out))
        self.assertTrue(os.path.isfile(self.marker(cache)), "the rebuilt cache has no .ok marker")
        self.assertFalse(os.path.exists(partial), "the half-made file survived: the cache was reused, not rebuilt")

    def test_cache_for_another_pin_is_not_used(self):
        python = bare_python()
        pin = require_pin()
        tmp = tempfile.mkdtemp(prefix="tmp_", dir=RUN_FOLDER)
        other = os.path.join(tmp, "floor-vermin-0.0.1-py%d%d" % sys.version_info[:2])
        os.makedirs(other)
        with open(os.path.join(other, ".ok"), "w", encoding="utf-8") as handle:
            handle.write("0.0.1\n")
        ours = os.path.join(tmp, "floor-vermin-%s-py%d%d" % ((pin,) + tuple(sys.version_info[:2])))
        env = {"FLOOR_VENV_DIR": None, "TMPDIR": tmp, "TEMP": tmp, "TMP": tmp}
        code, out = run_check(tree({"hooks/x.py": IGLOB}), env=env, python=python)
        self.assertEqual(code, 1, "a cache for another pin was used instead of the pinned one: exit %d, output %r"
                         % (code, out))
        self.assertTrue(os.path.isfile(os.path.join(ours, ".ok")), "the pinned cache %s was not built" % ours)

    def test_install_outside_the_venv_leaves_no_marker_and_a_later_run_rebuilds(self):
        python = bare_python()
        pin = require_pin()
        cache = fresh_cache()
        target = os.path.join(tempfile.mkdtemp(prefix="target_", dir=RUN_FOLDER), "lib")
        code, out = run_check(tree({"hooks/x.py": IGLOB}),
                              env={"FLOOR_VENV_DIR": cache, "PIP_TARGET": target}, python=python)
        self.assertEqual(code, 2, "an install that put vermin outside the venv exited %d, not 2: %r" % (code, out))
        self.assertFalse(os.path.exists(self.marker(cache)),
                         "a valid .ok marker was written for a venv that cannot import vermin")
        self.assertIn(pin, out, "the failed install does not name vermin %s: %r" % (pin, out))
        code, out = run_check(tree({"hooks/x.py": IGLOB}), env={"FLOOR_VENV_DIR": cache, "PIP_TARGET": None},
                              python=python)
        self.assertEqual(code, 1, "a later run with PIP_TARGET unset did not rebuild and succeed: exit %d, output %r"
                         % (code, out))
        self.assertTrue(os.path.isfile(self.marker(cache)), "the rebuilt cache has no .ok marker")

    def test_a_cache_with_a_marker_but_no_vermin_is_rebuilt(self):
        python = bare_python()
        cache = fresh_cache()
        code, out = run_check(tree({"hooks/x.py": IGLOB}), env={"FLOOR_VENV_DIR": cache}, python=python)
        self.assertEqual(code, 1, "the first run did not bootstrap: exit %d, output %r" % (code, out))
        removed = subprocess.run([cache_python(cache), "-m", "pip", "uninstall", "-y", "vermin"],
                                 capture_output=True, text=True, timeout=300)
        self.assertEqual(removed.returncode, 0, "fixture: could not take vermin out of the cache: %s"
                         % removed.stderr.strip()[-300:])
        probe = subprocess.run([cache_python(cache), "-c", "import vermin"], capture_output=True, text=True,
                               timeout=120)
        self.assertNotEqual(probe.returncode, 0, "fixture: vermin still imports from the cache after uninstall")
        self.assertTrue(os.path.isfile(self.marker(cache)), "fixture: the cache lost its .ok marker")
        code, out = run_check(tree({"hooks/x.py": IGLOB}), env={"FLOOR_VENV_DIR": cache}, python=python)
        self.assertEqual(code, 1, "a cache with .ok but no vermin was used, not rebuilt: exit %d, output %r"
                         % (code, out))
        self.assertTrue(any("iglob" in line for line in naming(out, "x.py")),
                        "the rebuilt check did not flag hooks/x.py's iglob: %r" % out)
        self.assertTrue(os.path.isfile(self.marker(cache)), "the rebuilt cache has no .ok marker")


class OneHome(unittest.TestCase):
    """The pin is written in one place, and CI installs no vermin of its own."""

    def test_checks_yml_installs_no_vermin(self):
        with open(os.path.join(REPO, ".github", "workflows", "checks.yml"), encoding="utf-8") as handle:
            text = handle.read()
        self.assertNotIn("pip install vermin", text, "checks.yml still installs vermin: the check bootstraps its own")
        self.assertNotIn("Install vermin", text, "checks.yml still has an Install vermin step")

    def test_pin_string_lives_only_in_the_check(self):
        pin = require_pin()
        hits = set()
        for folder in ("lint", ".github"):
            for base, dirs, names in os.walk(os.path.join(REPO, folder)):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for name in names:
                    if is_test_name(name):
                        continue
                    path = os.path.join(base, name)
                    with open(path, encoding="utf-8", errors="replace") as handle:
                        if pin in handle.read():
                            hits.add(os.path.relpath(path, REPO).replace(os.sep, "/"))
        self.assertEqual(hits, {"lint/check_python_floor.py"},
                         "the pin %s is written outside the check: %s" % (pin, sorted(hits)))


class CacheFolder(unittest.TestCase):
    """FLOOR_VENV_DIR may name a folder that already exists. The check refuses one that holds someone's files, and
    builds in an empty one, in one that holds an old venv, and where nothing exists."""

    def fixture_folder(self):
        return os.path.join(tempfile.mkdtemp(prefix="folder_", dir=RUN_FOLDER), "vermin")

    def test_a_non_empty_folder_with_no_marker_or_venv_is_refused_and_kept(self):
        python = bare_python()
        folder = self.fixture_folder()
        os.makedirs(folder)
        notes = os.path.join(folder, "notes.txt")
        with open(notes, "w", encoding="utf-8") as handle:
            handle.write("not the check's to delete\n")
        code, out = run_check(tree({"hooks/x.py": IGLOB}), env={"FLOOR_VENV_DIR": folder}, python=python)
        self.assertTrue(os.path.isfile(notes), "the check deleted notes.txt from a non-empty FLOOR_VENV_DIR")
        self.assertEqual(code, 2, "a non-empty folder with no .ok and no pyvenv.cfg exited %d, not 2: %r"
                         % (code, out))
        self.assertIn(folder, out, "the refusal does not name the folder %s: %r" % (folder, out))

    def test_an_empty_folder_is_built(self):
        python = bare_python()
        folder = self.fixture_folder()
        os.makedirs(folder)
        code, out = run_check(tree({"hooks/x.py": IGLOB}), env={"FLOOR_VENV_DIR": folder}, python=python)
        self.assertEqual(code, 1, "an empty FLOOR_VENV_DIR was not built: exit %d, output %r" % (code, out))
        self.assertTrue(os.path.isfile(os.path.join(folder, ".ok")),
                        "the empty folder has no .ok marker after the build")

    def test_a_folder_with_an_old_pyvenv_cfg_is_rebuilt(self):
        python = bare_python()
        folder = self.fixture_folder()
        os.makedirs(folder)
        with open(os.path.join(folder, "pyvenv.cfg"), "w", encoding="utf-8") as handle:
            handle.write("home = /nowhere\n")
        code, out = run_check(tree({"hooks/x.py": IGLOB}), env={"FLOOR_VENV_DIR": folder}, python=python)
        self.assertEqual(code, 1, "a folder holding an old venv was not rebuilt: exit %d, output %r" % (code, out))
        self.assertTrue(os.path.isfile(os.path.join(folder, ".ok")), "the rebuilt folder has no .ok marker")

    def test_a_missing_folder_is_built(self):
        python = bare_python()
        folder = self.fixture_folder()
        code, out = run_check(tree({"hooks/x.py": IGLOB}), env={"FLOOR_VENV_DIR": folder}, python=python)
        self.assertEqual(code, 1, "a missing FLOOR_VENV_DIR was not built: exit %d, output %r" % (code, out))
        self.assertTrue(os.path.isfile(os.path.join(folder, ".ok")), "the built folder has no .ok marker")

    def make_symlink(self, target, link):
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError):
            self.skipTest("this platform cannot make symlinks")

    def test_a_regular_file_is_refused_and_kept(self):
        python = bare_python()
        path = self.fixture_folder()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("keep me\n")
        code, out = run_check(tree({"hooks/x.py": IGLOB}), env={"FLOOR_VENV_DIR": path}, python=python)
        self.assertTrue(os.path.isfile(path), "the check deleted the file %s named by FLOOR_VENV_DIR" % path)
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "keep me\n", "the check changed the file %s" % path)
        self.assertEqual(code, 2, "a regular file named by FLOOR_VENV_DIR exited %d, not 2: %r" % (code, out))
        self.assertIn(path, out, "the refusal does not name the file %s: %r" % (path, out))

    def test_a_dangling_symlink_is_refused_and_kept(self):
        python = bare_python()
        path = self.fixture_folder()
        self.make_symlink(os.path.join(os.path.dirname(path), "no-such-target"), path)
        code, out = run_check(tree({"hooks/x.py": IGLOB}), env={"FLOOR_VENV_DIR": path}, python=python)
        self.assertTrue(os.path.islink(path),
                        "the check removed the dangling symlink %s named by FLOOR_VENV_DIR" % path)
        self.assertEqual(code, 2, "a dangling symlink named by FLOOR_VENV_DIR exited %d, not 2: %r" % (code, out))
        self.assertIn(path, out, "the refusal does not name the symlink %s: %r" % (path, out))

    def test_a_symlink_to_a_file_is_refused_and_both_kept(self):
        python = bare_python()
        path = self.fixture_folder()
        target = os.path.join(os.path.dirname(path), "target.txt")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("keep me\n")
        self.make_symlink(target, path)
        code, out = run_check(tree({"hooks/x.py": IGLOB}), env={"FLOOR_VENV_DIR": path}, python=python)
        self.assertTrue(os.path.isfile(target), "the check deleted %s, the file the symlink points at" % target)
        with open(target, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "keep me\n", "the check changed %s" % target)
        self.assertTrue(os.path.islink(path), "the check removed the symlink %s named by FLOOR_VENV_DIR" % path)
        self.assertEqual(code, 2, "a symlink to a file named by FLOOR_VENV_DIR exited %d, not 2: %r" % (code, out))
        self.assertIn(path, out, "the refusal does not name the symlink %s: %r" % (path, out))


class StartCount(unittest.TestCase):
    """The bootstrap's process starts, counted at the check's one no-window run. First use starts three processes
    the check makes itself (venv create, pip install, import probe); a reused cache starts one import probe."""

    def test_first_use_starts_the_venv_the_pip_install_and_the_import_probe(self):
        require_pin()
        starts = bootstrap_starts(fresh_cache())
        self.assertEqual(len(starts), 3, "first use started %d processes through _nowindow.run, not 3: %r"
                         % (len(starts), starts))
        self.assertIn("-m venv", starts[0], "first use's first start is not the venv create: %r" % starts)
        self.assertIn("-m pip install", starts[1], "first use's second start is not the pip install: %r" % starts)
        self.assertIn("import vermin", starts[2], "first use's third start is not the import probe: %r" % starts)

    def test_a_reused_cache_starts_one_import_probe(self):
        require_pin()
        cache = fresh_cache()
        bootstrap_starts(cache)
        starts = bootstrap_starts(cache)
        self.assertEqual(len(starts), 1, "a reused cache started %d processes through _nowindow.run, not 1: %r"
                         % (len(starts), starts))
        self.assertIn("import vermin", starts[0], "a reused cache's one start is not the import probe: %r" % starts)


class Docstring(unittest.TestCase):
    def test_cost_line_says_four_process_starts_on_first_use_and_names_the_probe_and_15_mb(self):
        with open(CHECK, encoding="utf-8") as handle:
            raw = ast.get_docstring(ast.parse(handle.read())) or ""
        start = raw.find("Cost:")
        self.assertNotEqual(start, -1, "the module docstring has no Cost: line")
        paragraph = " ".join(raw[start:].split("\n\n")[0].split())
        first_use = paragraph.split("Later runs")[0]
        self.assertIn("four process starts", first_use,
                      "the Cost line's first use does not say four process starts "
                      "(venv create, its ensurepip child, pip install, import probe)")
        self.assertIn("import vermin", first_use, "the Cost line's first use does not name the import vermin probe")
        self.assertIn("15 MB", paragraph, "the Cost line does not say 15 MB")


if __name__ == "__main__":
    unittest.main()
