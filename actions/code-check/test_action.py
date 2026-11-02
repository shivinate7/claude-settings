"""Tests the code-check runner on throwaway repos. `python3 actions/code-check/test_action.py`.
Asserts: a tracked language with no row is red (by extension and by shebang), a planted mypy error in
a listed module is red, a shrunk mypy list is red against the base ref, a missing listed module is red,
a listed module renamed off the list is red, a shrink against --main (current main) is red,
Swift, .entitlements and zsh files have rows and zsh skips ShellCheck, web app data and image files have rows, archive, sheet, model and node config files have rows, an excluded folder is not scanned, an .astro type error is red and a clean Astro project green, and the
standard's table is whole (every layer runs or has a one-line reason). The comment check reads only added
lines; with no base it is skipped with a reason, and with a base outside the clone it is unknown, never red.
The tools run from PATH (CODE_CHECK_TOOLS=path), so ruff, mypy, shellcheck (the --pins specs, via pipx) and
astro-check (the tools/ lockfile, via npm ci, bin on PATH) must be installed. Without astro-check the Astro tests
skip and say so, except under CI, where they fail."""
import functools, json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
RUN_FOLDER = _test_temp.run_folder()
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
NEEDS_TSC = unittest.skipUnless(shutil.which("tsc") or os.environ.get("CI"),
                                "tsc not on PATH; npm ci --ignore-scripts --prefix actions/code-check/tools (CI does)")
with open(STANDARD, encoding="utf-8") as f:
    TS_PIN = json.load(f)["tools"]["typescript"]


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


def head(d):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, capture_output=True, text=True).stdout.strip()


def check(files, base_files=None, base=None, main_files=None, main=None, send_base=True, path_tools=True, **env):
    """Commit base_files (when given) as the base, then files on top (None deletes); run the runner.
    main_files (when given) are a commit on top of the base that the PR does not hold, passed as --main;
    the PR's files then go on the base. `base` and `main` name a ref outright; send_base=False omits --base.
    Returns (exit, output)."""
    with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
        git(d, "init", "-q", "-b", "main")
        if base_files is not None:
            put(d, base_files)
            git(d, "add", "-A"); git(d, "commit", "-qm", "base")
            base = head(d)
        if main_files is not None:
            put(d, main_files)
            git(d, "add", "-A"); git(d, "commit", "-qm", "main moved on")
            main = head(d)
            git(d, "checkout", "-q", base)
        put(d, files)
        git(d, "add", "-A"); git(d, "commit", "-qm", "head", "--allow-empty")
        args = [sys.executable, RUNNER, "--root", d] + (["--base", base] if base and send_base else []) + (["--main", main] if main else [])
        run_env = dict(os.environ, **env)
        run_env.pop("CODE_CHECK_TOOLS", None)
        if path_tools:
            run_env["CODE_CHECK_TOOLS"] = "path"
        p = subprocess.run(args, capture_output=True, text=True, env=run_env)
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

    def test_web_app_data_and_image_files_have_rows(self):
        # A web app repo's own non-code files: env template, worktree list, web manifest, CSV fixture, images.
        rc, out = check({".code-check.json": config([]), ".env.example": "KEY=\n", ".worktreeinclude": ".env\n",
                         "app/public/manifest.webmanifest": "{}\n", "tests/fixtures/rows.csv": "a,b\n1,2\n",
                         "img/a.jpg": "x", "img/b.jpeg": "x", "img/c.webp": "x", "img/d.png": "x"})
        self.assertEqual(rc, 0, out)
        self.assertNotIn("no row", out)

    def test_archive_sheet_model_and_node_config_files_have_rows(self):
        # A data app repo's binary and dotfile kinds; .nvmrc and .npmrc match by whole name, as .gitignore does.
        rc, out = check({".code-check.json": config([]), "data/a.csv.gz": "x", "reports/r.xlsx": "x",
                         "models/m.onnx": "x", "data/w.npz": "x", ".nvmrc": "20\n", ".npmrc": "save-exact=true\n"})
        self.assertEqual(rc, 0, out)
        self.assertNotIn("no row", out)

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

    def test_renamed_module_dropped_from_list_is_red(self):
        base = {".code-check.json": config(["a.py"]), "a.py": GOOD_PY}
        rc, out = check({".code-check.json": config([]), "a.py": None, "b.py": GOOD_PY}, base_files=base)
        self.assertNotEqual(rc, 0, out)
        self.assertIn("mypy list lost a.py, renamed to b.py; list b.py in .code-check.json", out)

    def test_renamed_module_listed_at_new_path_is_green(self):
        base = {".code-check.json": config(["a.py"]), "a.py": GOOD_PY}
        rc, out = check({".code-check.json": config(["b.py"]), "a.py": None, "b.py": GOOD_PY}, base_files=base)
        self.assertEqual(rc, 0, out)

    def test_branch_behind_main_is_green(self):
        # main listed b.py after the fork; the branch never touched the list, so a merge keeps main's entry.
        base = {".code-check.json": config(["a.py"]), "a.py": GOOD_PY, "b.py": GOOD_PY}
        rc, out = check({"c.py": GOOD_PY}, base_files=base, main_files={".code-check.json": config(["a.py", "b.py"])})
        self.assertEqual(rc, 0, out)

    def test_shrink_against_main_and_fork_point_is_red(self):
        # No usable --base: main and the merge-base both list b.py, and the branch drops it.
        base = {".code-check.json": config(["a.py", "b.py"]), "a.py": GOOD_PY, "b.py": GOOD_PY}
        rc, out = check({".code-check.json": config(["a.py"])}, base_files=base, main_files={"c.py": GOOD_PY},
                        send_base=False)
        self.assertNotEqual(rc, 0, out)
        self.assertIn("shrank: b.py", out)

    def test_module_renamed_into_excluded_folder_says_move_it_back(self):
        base = {".code-check.json": config(["a.py"], ["vendor/"]), "a.py": GOOD_PY}
        rc, out = check({".code-check.json": config([], ["vendor/"]), "a.py": None, "vendor/a.py": GOOD_PY},
                        base_files=base)
        self.assertNotEqual(rc, 0, out)
        self.assertIn("mypy list lost a.py, renamed to vendor/a.py", out)
        self.assertIn("move it back", out)
        self.assertNotIn("list vendor/a.py", out)

    def test_module_renamed_to_non_python_path_says_move_it_back(self):
        base = {".code-check.json": config(["a.py"]), "a.py": GOOD_PY}
        rc, out = check({".code-check.json": config([]), "a.py": None, "a.txt": GOOD_PY}, base_files=base)
        self.assertNotEqual(rc, 0, out)
        self.assertIn("renamed to a.txt", out)
        self.assertIn("move it back", out)

    def test_same_failure_from_base_and_main_prints_once(self):
        base = {".code-check.json": config(["a.py", "b.py"]), "a.py": GOOD_PY, "b.py": GOOD_PY}
        rc, out = check({".code-check.json": config(["a.py"])}, base_files=base, main_files={"c.py": GOOD_PY})
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(len([l for l in out.splitlines() if "shrank" in l and not l.startswith("::")]), 1, out)

    def test_main_not_in_clone_is_unknown_not_red(self):
        base = {".code-check.json": config(["a.py"]), "a.py": GOOD_PY}
        rc, out = check({"c.py": GOOD_PY}, base_files=base, main="1" * 40)
        self.assertEqual(rc, 0, out)
        self.assertIn("unknown: main", out)

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


NARRATED = "# fixed on 2026-10-28\n"
NARRATED_FN = "def add(a: int, b: int) -> int:\n    # fixed on 2026-10-28\n    return a + b\n"
WHY_FN = ("def add(a: int, b: int) -> int:\n"
          "    # the cache key must hold the user id, so two users never share rows\n    return a + b\n")


def one_line_with(out, *needles):
    return any(all(n in row for n in needles) for row in out.splitlines())


def path_with(*tools):
    """A PATH folder that links only the named tools from this machine. Returns the folder."""
    folder = tempfile.mkdtemp(dir=RUN_FOLDER)
    for tool in tools:
        os.symlink(shutil.which(tool), os.path.join(folder, tool))
    return folder


def npx_reaches_registry():
    if not shutil.which("npx"):
        return False
    try:
        p = subprocess.run(["npx", "--yes", "-p", "typescript@" + TS_PIN, "tsc", "--version"],
                           capture_output=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return p.returncode == 0


def needs_npx(test):
    """Runs the test where npx reaches the registry; skips it elsewhere, and fails it under CI."""
    @functools.wraps(test)
    def run(self):
        if npx_reaches_registry():
            return test(self)
        if os.environ.get("CI"):
            self.fail("npx cannot reach the npm registry; CI must reach it")
        self.skipTest("npx cannot reach the npm registry")
    return run


class CommentCheck(unittest.TestCase):
    def assertSkipped(self, out):
        rows = [r for r in out.splitlines() if "comment check: skipped" in r]
        self.assertTrue(rows, out)
        self.assertTrue(rows[0].split("comment check: skipped", 1)[1].strip(" ,:;-()"), "no reason: " + out)

    def test_added_narrating_comment_is_red_and_names_the_line(self):
        rc, out = check({"a.py": NARRATED_FN}, base_files={".code-check.json": config(["a.py"]), "a.py": GOOD_PY})
        self.assertNotEqual(rc, 0, out)
        self.assertTrue(one_line_with(out, "a.py:2", "2026-10-28"), out)

    def test_added_why_comment_is_green(self):
        rc, out = check({"a.py": WHY_FN}, base_files={".code-check.json": config(["a.py"]), "a.py": GOOD_PY})
        self.assertEqual(rc, 0, out)

    def test_narrating_comment_already_in_base_is_green(self):
        base = {".code-check.json": config(["a.py"]), "a.py": NARRATED + GOOD_PY}
        rc, out = check({"a.py": NARRATED + GOOD_PY + "\n\nSCALE = 2\n"}, base_files=base)
        self.assertEqual(rc, 0, out)

    def test_narrating_comment_under_excluded_folders_is_green(self):
        base = {".code-check.json": config([], ["vendor/", "third_party/"]), "a.py": GOOD_PY}
        head = {"vendor/x.py": NARRATED + GOOD_PY, "third_party/y.py": NARRATED + GOOD_PY}
        rc, out = check(head, base_files=base)
        self.assertEqual(rc, 0, out)

    def test_narrating_comment_outside_excluded_folders_is_red_and_only_it_is_named(self):
        base = {".code-check.json": config([], ["vendor/", "third_party/"]), "a.py": GOOD_PY}
        head = {"vendor/x.py": NARRATED + GOOD_PY, "third_party/y.py": NARRATED + GOOD_PY, "a.py": NARRATED_FN}
        rc, out = check(head, base_files=base)
        self.assertNotEqual(rc, 0, out)
        self.assertTrue(one_line_with(out, "a.py:2", "2026-10-28"), out)
        self.assertNotIn("vendor/x.py", out)
        self.assertNotIn("third_party/y.py", out)

    def test_no_base_passed_skips_the_comment_check_with_a_reason(self):
        rc, out = check({".code-check.json": config([]), "a.py": NARRATED + GOOD_PY}, send_base=False)
        self.assertEqual(rc, 0, out)
        self.assertSkipped(out)

    def test_base_not_in_clone_is_unknown_not_red(self):
        rc, out = check({".code-check.json": config([]), "a.py": NARRATED + GOOD_PY}, base="1" * 40)
        self.assertEqual(rc, 0, out)
        self.assertTrue(one_line_with(out, "comment check", "unknown"), out)

    def test_zero_sha_base_skips_the_comment_check(self):
        rc, out = check({".code-check.json": config([]), "a.py": NARRATED + GOOD_PY}, base="0" * 40)
        self.assertEqual(rc, 0, out)
        self.assertSkipped(out)

    def test_round_comment_is_named_when_another_python_file_does_not_parse(self):
        base = {".code-check.json": config(["a.py"]), "a.py": GOOD_PY}
        head = {"a.py": "def add(a: int, b: int) -> int:\n    # fixed in round 2\n    return a + b\n",
                "b.py": "def broken(:\n"}
        rc, out = check(head, base_files=base)
        self.assertNotEqual(rc, 0, out)
        self.assertTrue(one_line_with(out, "a.py:2", "round 2"), out)

    def test_round_comment_in_an_extensionless_python_script_is_red(self):
        base = {".code-check.json": config([]), "bin/tool": "#!/usr/bin/env python3\nprint(1)\n"}
        head = {"bin/tool": "#!/usr/bin/env python3\n# fixed in round 2\nprint(1)\n"}
        rc, out = check(head, base_files=base)
        self.assertNotEqual(rc, 0, out)
        self.assertTrue(one_line_with(out, "bin/tool:2", "round 2"), out)


JS_BASE = "const a = 1;\n"
JS_HIT = "const a = 1;\n// fixed in round 2\n"
SWIFT_BASE = "let a = 1\n"
SWIFT_HIT = "let a = 1\n// fixed on 2026-10-28\n"
ASTRO_HIT = ("---\n// fixed in round 2\ninterface Props { title: string }\n"
             "const { title } = Astro.props;\nconst n: number = 2;\n---\n<h2>{title} {n}</h2>\n")


class CommentCheckLanguages(unittest.TestCase):
    @NEEDS_TSC
    def test_js_hit_is_red_and_names_the_line(self):
        rc, out = check({"app.js": JS_HIT}, base_files={".code-check.json": config([]), "app.js": JS_BASE})
        self.assertNotEqual(rc, 0, out)
        self.assertTrue(one_line_with(out, "app.js:2", "round 2"), out)

    def test_swift_hit_is_red_and_names_the_line(self):
        rc, out = check({"Thing.swift": SWIFT_HIT},
                        base_files={".code-check.json": config([]), "Thing.swift": SWIFT_BASE})
        self.assertNotEqual(rc, 0, out)
        self.assertTrue(one_line_with(out, "Thing.swift:2", "2026-10-28"), out)

    @NEEDS_ASTRO
    def test_astro_frontmatter_hit_is_red_and_names_the_line(self):
        base = {".code-check.json": config([]), "astro.config.mjs": ASTRO_CONFIG, "src/pages/index.astro": GOOD_ASTRO}
        rc, out = check({"src/pages/index.astro": ASTRO_HIT}, base_files=base)
        self.assertNotEqual(rc, 0, out)
        self.assertTrue(one_line_with(out, "index.astro:2", "round 2"), out)

    @needs_npx
    def test_js_hit_is_red_through_npx_without_tools_on_path(self):
        rc, out = check({"app.js": JS_HIT}, base_files={".code-check.json": config([]), "app.js": JS_BASE},
                        path_tools=False)
        self.assertNotEqual(rc, 0, out)
        self.assertTrue(one_line_with(out, "app.js:2", "round 2"), out)

    def test_no_npx_is_red_and_says_the_comment_check_could_not_run(self):
        base = {".code-check.json": config([]), "app.js": JS_BASE}
        rc, out = check({"app.js": JS_HIT}, base_files=base, path_tools=False, PATH=path_with("git"))
        self.assertEqual(rc, 1, out)
        self.assertIn("comment check could not run", out)


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
