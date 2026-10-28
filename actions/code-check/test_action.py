"""Tests the code-check runner on throwaway repos. `python3 actions/code-check/test_action.py`.
Asserts: a tracked language with no row is red (by extension and by shebang), a planted mypy error in
a listed module is red, a shrunk mypy list is red against the base ref, a missing listed module is red,
Swift, .entitlements and zsh files have rows and zsh skips ShellCheck, an excluded folder is not scanned, an .astro type error is red and a clean Astro project green, and the
standard's table is whole (every layer runs or has a one-line reason).
The tools run from PATH (CODE_CHECK_TOOLS=path), so ruff, mypy, shellcheck (the --pins specs, via pipx) and
astro-check (the tools/ lockfile, via npm ci, bin on PATH) must be installed. Without astro-check the Astro tests
skip and say so, except under CI, where they fail."""
import json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, "code_check.py")
STANDARD = os.path.join(HERE, "standard.json")
GOOD_PY = "def add(a: int, b: int) -> int:\n    return a + b\n"
BAD_PY = "def add(a: int, b: int) -> int:\n    return str(a)\n"
GOOD_ASTRO = "---\ninterface Props { title: string }\nconst { title } = Astro.props;\nconst n: number = 2;\n---\n<h2>{title} {n}</h2>\n"
BAD_ASTRO = "---\nconst n: number = \"x\";\n---\n<p>{n}</p>\n"
ASTRO_CONFIG = "export default {};\n"
# CI must not go green by skipping: there a missing astro-check fails the test instead.
NEEDS_ASTRO = unittest.skipUnless(shutil.which("astro-check") or os.environ.get("CI"),
                                  "astro-check not on PATH; npm ci in actions/code-check/tools (CI does)")


def git(cwd, *a):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def put(root, files):
    for name, content in files.items():
        path = os.path.join(root, name)
        if content is None:
            os.remove(path)
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="\n") as f:
            f.write(content)


def config(modules, exclude=()):
    return json.dumps({"exclude": list(exclude), "mypy_modules": list(modules)})


def check(files, base_files=None, base=None, **env):
    """Commit base_files (when given) as the base, then files on top (None deletes); run the runner.
    `base` names a ref outright. Returns (exit, output)."""
    with tempfile.TemporaryDirectory() as d:
        git(d, "init", "-q", "-b", "main")
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

    def test_apple_app_files_have_rows_and_zsh_skips_shellcheck(self):
        # An Apple app repo's own files: Swift, an entitlements plist, zsh scripts by shebang and by extension.
        zsh = "#!/bin/zsh\nparts=(${(s:,:)1})\nprint -P \"%F{green}${#parts}%f\"\n"
        rc, out = check({".code-check.json": config([]), "App/App.swift": "import SwiftUI\n",
                         "App/App.entitlements": "<?xml version=\"1.0\"?>\n<plist version=\"1.0\"><dict/></plist>\n",
                         "bin/build": zsh, "scripts/env.zsh": zsh})
        self.assertEqual(rc, 0, out)
        self.assertNotIn("no row", out)
        self.assertIn("swift lint: skipped", out)
        self.assertIn("zsh lint: skipped", out)
        self.assertNotIn("shellcheck", out)

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

    def test_added_exclude_entry_is_red(self):
        base = {".code-check.json": config([], ["vendor/"]), "vendor/x.rs": "x\n"}
        rc, out = check({".code-check.json": config([], ["vendor/", "src/"]), "src/y.rs": "x\n"}, base_files=base)
        self.assertNotEqual(rc, 0, out)
        self.assertIn("exclude grew", out)
        self.assertIn("src/", out)

    def test_removed_exclude_entry_is_green(self):
        base = {".code-check.json": config([], ["vendor/", "old/"])}
        rc, out = check({".code-check.json": config([], ["vendor/"])}, base_files=base)
        self.assertEqual(rc, 0, out)

    def test_empty_or_slash_exclude_entry_is_red(self):
        for entry in ("", "/", " "):
            rc, out = check({".code-check.json": config([], [entry]), "main.rs": "x\n"})
            self.assertNotEqual(rc, 0, repr(entry) + out)
            self.assertIn("empty exclude", out)

    def test_deleted_module_may_leave_the_list(self):
        base = {".code-check.json": config(["a.py", "b.py"]), "a.py": GOOD_PY, "b.py": GOOD_PY}
        rc, out = check({".code-check.json": config(["a.py"]), "b.py": None}, base_files=base)
        self.assertEqual(rc, 0, out)

    def test_gone_module_still_listed_gets_one_message(self):
        rc, out = check({".code-check.json": config(["a.py", "gone.py"]), "a.py": GOOD_PY})
        self.assertNotEqual(rc, 0, out)
        self.assertIn("remove it from mypy_modules, or list its new path", out)
        self.assertEqual(len([l for l in out.splitlines() if "gone.py" in l and not l.startswith("::")]), 1, out)

    def test_base_not_in_clone_is_unknown_not_red(self):
        rc, out = check({".code-check.json": config(["a.py"]), "a.py": GOOD_PY}, base="1" * 40)
        self.assertEqual(rc, 0, out)
        self.assertIn("unknown", out)

    def test_pins_flag_prints_install_specs_from_the_standard(self):
        std = json.load(open(STANDARD, encoding="utf-8"))
        p = subprocess.run([sys.executable, RUNNER, "--pins"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        want = ["%s==%s" % (k, std["tools"][k]) for k in ("ruff", "mypy", "shellcheck-py")]
        self.assertEqual(p.stdout.split(), want)

    def test_action_path_goes_through_env(self):
        text = open(os.path.join(HERE, "action.yml"), encoding="utf-8").read()
        self.assertNotIn("${{", text.split("      run: |", 1)[1])

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
        self.assertEqual(std["languages"]["astro"]["typecheck"], {"run": "astro-check"})
        for tool in ("ruff", "mypy", "shellcheck-py", "typescript", "@astrojs/check"):
            self.assertRegex(std["tools"][tool], r"^\d+\.\d+\.\d+(\.\d+)?$")

    def test_astro_file_has_a_row(self):
        rc, out = check({".code-check.json": config([]), "astro.config.mjs": ASTRO_CONFIG, "src/pages/index.astro": GOOD_ASTRO})
        self.assertNotIn("no row", out)
        self.assertIn("astro typecheck", out)

    @NEEDS_ASTRO
    def test_astro_type_error_is_red(self):
        rc, out = check({".code-check.json": config([]), "site/astro.config.mjs": ASTRO_CONFIG,
                         "site/src/pages/index.astro": BAD_ASTRO})
        self.assertNotEqual(rc, 0, out)
        self.assertIn("astro-check found problems", out)
        self.assertIn("index.astro", out)

    @NEEDS_ASTRO
    def test_astro_file_under_no_config_is_checked(self):
        rc, out = check({".code-check.json": config([]), "pages/a.astro": BAD_ASTRO})
        self.assertNotEqual(rc, 0, out)
        self.assertIn("astro-check found problems", out)

    @NEEDS_ASTRO
    def test_clean_astro_project_is_green(self):
        rc, out = check({".code-check.json": config([]), "astro.config.mjs": ASTRO_CONFIG,
                         "src/components/Card.astro": GOOD_ASTRO})
        self.assertEqual(rc, 0, out)
        self.assertIn("astro typecheck: astro-check pass", out)

    def test_npm_lockfile_matches_the_standard(self):
        std = json.load(open(STANDARD, encoding="utf-8"))
        tools = os.path.join(HERE, "tools")
        want = {k: std["tools"][k] for k in ("@astrojs/check", "typescript")}
        self.assertEqual(json.load(open(os.path.join(tools, "package.json"), encoding="utf-8"))["dependencies"], want)
        lock = json.load(open(os.path.join(tools, "package-lock.json"), encoding="utf-8"))["packages"]
        self.assertEqual(lock[""]["dependencies"], want)
        for name, version in want.items():
            self.assertEqual(lock["node_modules/" + name]["version"], version, name)

    def test_format_layer_waits_for_o2(self):
        std = json.load(open(STANDARD, encoding="utf-8"))
        for name, row in std["languages"].items():
            self.assertNotIn("run", row["format"], name)


if __name__ == "__main__":
    unittest.main()
