"""Tests the code-check runner on throwaway repos. `python3 actions/code-check/test_action.py`.
Asserts: a tracked language with no row is red (by extension and by shebang), a planted mypy error in
a listed module is red, a shrunk mypy list is red against the base ref, a missing listed module is red,
an excluded folder is not scanned, and the standard's table is whole (every layer runs or has a one-line reason).
The tools run from PATH (CODE_CHECK_TOOLS=path), so ruff, mypy and shellcheck must be installed."""
import json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, "code_check.py")
STANDARD = os.path.join(HERE, "standard.json")
GOOD_PY = "def add(a: int, b: int) -> int:\n    return a + b\n"
BAD_PY = "def add(a: int, b: int) -> int:\n    return str(a)\n"


def git(cwd, *a):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def put(root, files):
    for name, content in files.items():
        path = os.path.join(root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="\n") as f:
            f.write(content)


def config(modules, exclude=()):
    return json.dumps({"exclude": list(exclude), "mypy_modules": list(modules)})


def check(files, base_files=None, **env):
    """Commit base_files (when given) as the base, then files on top; run the runner. Returns (exit, output)."""
    with tempfile.TemporaryDirectory() as d:
        git(d, "init", "-q", "-b", "main")
        base = None
        if base_files is not None:
            put(d, base_files)
            git(d, "add", "-A"); git(d, "commit", "-qm", "base")
            base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, capture_output=True, text=True).stdout.strip()
        put(d, files)
        git(d, "add", "-A"); git(d, "commit", "-qm", "head", "--allow-empty")
        args = [sys.executable, RUNNER, "--root", d] + (["--base", base] if base else [])
        p = subprocess.run(args, capture_output=True, text=True, env=dict(os.environ, CODE_CHECK_TOOLS="path", **env))
        return p.returncode, p.stdout + p.stderr


class CodeCheck(unittest.TestCase):
    def test_clean_repo_is_green(self):
        rc, out = check({".code-check.json": config(["a.py"]), "a.py": GOOD_PY, "README.md": "# t\n"})
        self.assertEqual(rc, 0, out)

    def test_language_with_no_row_is_red(self):
        rc, out = check({".code-check.json": config([]), "main.rs": "fn main() {}\n"})
        self.assertNotEqual(rc, 0, out)
        self.assertIn("no row", out)
        self.assertIn("main.rs", out)

    def test_unknown_shebang_with_no_row_is_red(self):
        rc, out = check({".code-check.json": config([]), "bin/tool": "#!/usr/bin/env ruby\nputs 1\n"})
        self.assertNotEqual(rc, 0, out)
        self.assertIn("bin/tool", out)

    def test_extensionless_shell_script_gets_shellcheck(self):
        rc, out = check({".code-check.json": config([]), "bin/tool": "#!/bin/sh\ncd /x\nrm -rf $y/z\n"})
        self.assertNotEqual(rc, 0, out)
        self.assertIn("shellcheck", out)

    def test_excluded_folder_is_not_scanned(self):
        rc, out = check({".code-check.json": config([], ["vendor/"]), "vendor/x.rs": "fn main() {}\n"})
        self.assertEqual(rc, 0, out)

    def test_mypy_error_in_listed_module_is_red(self):
        rc, out = check({".code-check.json": config(["a.py"]), "a.py": BAD_PY})
        self.assertNotEqual(rc, 0, out)
        self.assertIn("mypy", out)

    def test_mypy_error_in_unlisted_module_is_not_checked(self):
        rc, out = check({".code-check.json": config(["a.py"]), "a.py": GOOD_PY, "b.py": BAD_PY})
        self.assertEqual(rc, 0, out)

    def test_listed_module_that_is_gone_is_red(self):
        rc, out = check({".code-check.json": config(["a.py", "gone.py"]), "a.py": GOOD_PY})
        self.assertNotEqual(rc, 0, out)
        self.assertIn("gone.py", out)

    def test_shrunk_list_is_red(self):
        base = {".code-check.json": config(["a.py", "b.py"]), "a.py": GOOD_PY, "b.py": GOOD_PY}
        rc, out = check({".code-check.json": config(["a.py"])}, base_files=base)
        self.assertNotEqual(rc, 0, out)
        self.assertIn("b.py", out)
        self.assertIn("shrank", out)

    def test_grown_list_is_green(self):
        base = {".code-check.json": config(["a.py"]), "a.py": GOOD_PY}
        rc, out = check({".code-check.json": config(["a.py", "b.py"]), "b.py": GOOD_PY}, base_files=base)
        self.assertEqual(rc, 0, out)

    def test_ruff_finding_is_red(self):
        rc, out = check({".code-check.json": config([]), "a.py": "import os\n"})
        self.assertNotEqual(rc, 0, out)
        self.assertIn("ruff", out)

    def test_standard_table_is_whole(self):
        std = json.load(open(STANDARD, encoding="utf-8"))
        self.assertTrue(std["languages"])
        for name, row in std["languages"].items():
            self.assertTrue(row["extensions"] or row["shebangs"], name)
            for layer in std["layers"]:
                self.assertIn(layer, row, name)
                self.assertTrue(row["gold"][layer], name)
                cell = row[layer]
                self.assertEqual(len(cell), 1, name)
                if "skip" in cell:
                    self.assertTrue(cell["skip"].strip() and "\n" not in cell["skip"], name)
        for tool in ("ruff", "mypy", "shellcheck-py", "typescript"):
            self.assertRegex(std["tools"][tool], r"^\d+\.\d+\.\d+(\.\d+)?$")

    def test_format_layer_waits_for_o2(self):
        std = json.load(open(STANDARD, encoding="utf-8"))
        for name, row in std["languages"].items():
            self.assertNotIn("run", row["format"], name)


if __name__ == "__main__":
    unittest.main()
