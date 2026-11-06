"""Tests the code-check runner on throwaway repos. `python3 actions/code-check/test_action.py`.
Asserts: a tracked language with no row is red (by extension and by shebang), a planted mypy error in
a listed module is red, a shrunk mypy list is red against the base ref, a missing listed module is red,
a listed module renamed off the list is red, a shrink against --main (current main) is red,
Swift, .entitlements and zsh files have rows and zsh skips ShellCheck, web app data and image files have rows, archive, sheet, model and node config files have rows, an excluded folder is not scanned, an .astro type error is red and a clean Astro project green, and the
standard's table is whole (every layer runs or has a one-line reason). The comment check reads only added
lines; with no base it is skipped with a reason, and with a base outside the clone it is unknown, never red.
A .mjs file's broken or extensionless relative import, and TS-only syntax in it, is red; its builtin, bare, JSON, .cjs and type-error imports, a JSDoc type, and npm notice lines on stderr are not; a .js or .cjs file is not checked, and a clean .mjs with no tsc on PATH is red. With a "link" key in .code-check.json, each root links unrun: a broken import, a missing named export or a missing bare package is red, and the file never runs; with no link key nothing changes.
The tools run from PATH (CODE_CHECK_TOOLS=path), so ruff, mypy, shellcheck (the --pins specs, via pipx) and
astro-check (the tools/ lockfile, via npm ci, bin on PATH) must be installed. Without astro-check the Astro tests
skip and say so, except under CI, where they fail."""
import functools, json, os, re, shlex, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
RUN_FOLDER = _test_temp.run_folder()
RUNNER = os.path.join(HERE, "code_check.py")
STANDARD = os.path.join(HERE, "standard.json")
TS_SOURCE = os.path.join(HERE, "tools", "node_modules", "typescript")  # the copy CI installs too
TS_LINK = object()  # an untracked value: a symlink to TS_SOURCE, the repo's own typescript
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
NEEDS_NODE = unittest.skipUnless(shutil.which("node") or os.environ.get("CI"), "node not on PATH")
NEEDS_LINK = unittest.skipUnless((shutil.which("node") and os.path.isdir(TS_SOURCE)) or os.environ.get("CI"),
                                 "node or actions/code-check/tools/node_modules/typescript missing; npm ci --ignore-scripts --prefix actions/code-check/tools (CI does)")
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


def config(modules, exclude=(), link=None):
    cfg = {"exclude": list(exclude), "mypy_modules": list(modules)}
    if link is not None:
        cfg["link"] = link
    return json.dumps(cfg)


def head(d):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, capture_output=True, text=True).stdout.strip()


def put_untracked(root, files):
    """Writes files after the commit, so git never tracks them, as an install leaves them. TS_LINK links TS_SOURCE."""
    for name, content in files.items():
        path = os.path.join(root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if content is TS_LINK:
            if not os.path.isdir(TS_SOURCE):
                raise AssertionError("no typescript at %s; npm ci --ignore-scripts --prefix actions/code-check/tools" % TS_SOURCE)
            os.symlink(TS_SOURCE, path)
        else:
            with open(path, "w", newline="\n") as f:
                f.write(content)


def check(files, base_files=None, base=None, main_files=None, main=None, send_base=True, path_tools=True, unset=(), untracked=None, **env):
    """Commit base_files (when given) as the base, then files on top (None deletes); run the runner.
    main_files (when given) are a commit on top of the base that the PR does not hold, passed as --main;
    the PR's files then go on the base. `base` and `main` name a ref outright; send_base=False omits --base.
    untracked (when given) is written after the commit and never committed. unset names are dropped from the
    run env; env adds or replaces variables there. Returns (exit, output)."""
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
        put_untracked(d, untracked or {})
        args = [sys.executable, RUNNER, "--root", d] + (["--base", base] if base and send_base else []) + (["--main", main] if main else [])
        run_env = dict(os.environ, **env)
        for name in unset:
            run_env.pop(name, None)
        run_env.pop("CODE_CHECK_TOOLS", None)
        if path_tools:
            run_env["CODE_CHECK_TOOLS"] = "path"
        p = subprocess.run(args, capture_output=True, text=True, env=run_env)
        return p.returncode, p.stdout + p.stderr


LINK_PASS = "javascript typecheck: mjs-link pass"
LINK_FAIL = "javascript typecheck: mjs-link FAIL"
FAKE_PKG = {"node_modules/fakepkg/package.json": '{"name": "fakepkg", "type": "module", "main": "index.mjs"}\n',
            "node_modules/fakepkg/index.mjs": "export const present = 1;\n"}
# A .tsx transpile may emit an import of react/jsx-runtime; this fake gives it the names TypeScript imports.
REACT_JSX = {"node_modules/react/package.json": '{"name": "react", "type": "module", "exports": {"./jsx-runtime": "./jsx-runtime.mjs"}}\n',
             "node_modules/react/jsx-runtime.mjs": "export const jsx = () => null;\nexport const jsxs = () => null;\nexport const Fragment = null;\n"}


def link_check(files, roots=(), skip=(), npm_scripts=(), untracked=None, ts=True, link=None, **kw):
    """check() with the link step opted in: the config's link key, and node_modules/typescript linked to TS_SOURCE
    unless ts is False. untracked adds more files that git never tracks, such as installed packages. link, when
    given, is the key as written, for a malformed value the three lists cannot hold."""
    if link is None:
        link = {"roots": list(roots), "skip": list(skip), "npm_scripts": list(npm_scripts)}
    hidden = {"node_modules/typescript": TS_LINK} if ts else {}
    hidden.update(untracked or {})
    return check({".code-check.json": config([], link=link), **files}, untracked=hidden, **kw)


def failure(out, path):
    """The text under `FAIL load: <path>`, up to the next FAIL load line, so one root's error is never another's.
    Empty when that root did not fail."""
    marker = "FAIL load: %s" % path
    if marker not in out:
        return ""
    return out.split(marker, 1)[1].split("FAIL load:", 1)[0]


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

    @NEEDS_TSC
    def test_mjs_import_of_missing_relative_file_is_red(self):
        rc, out = check({".code-check.json": config([]),
                         "app.mjs": 'import { x } from "./gone.mjs";\nexport default x;\n'})
        self.assertEqual(rc, 1, out)
        self.assertIn("app.mjs", out)
        self.assertIn("gone.mjs", out)

    @NEEDS_TSC
    def test_mjs_named_import_the_sibling_does_not_export_is_red(self):
        rc, out = check({".code-check.json": config([]), "lib.mjs": "export const a = 1;\n",
                         "app.mjs": 'import { b } from "./lib.mjs";\nexport default b;\n'})
        self.assertEqual(rc, 1, out)
        self.assertIn("app.mjs", out)
        self.assertIn("lib.mjs", out)

    @NEEDS_TSC
    def test_mjs_side_effect_import_of_missing_file_is_red(self):
        rc, out = check({".code-check.json": config([]), "app.mjs": 'import "./gone.mjs";\n'})
        self.assertEqual(rc, 1, out)
        self.assertIn("app.mjs", out)
        self.assertIn("gone.mjs", out)

    @NEEDS_TSC
    def test_mjs_imports_that_resolve_or_are_out_of_scope_are_green(self):
        # Node builtins, a bare package that is not installed, a JSON file with an import attribute, a .cjs file by
        # default import, and a type error (checkJs reports it; the import check drops it): none is a broken import.
        rc, out = check({".code-check.json": config([]), "d.json": '{"a": 1}\n',
                         "c.cjs": "module.exports = { a: 1 };\n",
                         "app.mjs": ('import fs from "node:fs";\n'
                                     'import x from "somepkg";\n'
                                     'import data from "./d.json" with { type: "json" };\n'
                                     'import c from "./c.cjs";\n'
                                     'const n = 1;\nn.foo;\n'
                                     'export { fs, x, data, c };\n')})
        self.assertIn("javascript typecheck: mjs-imports pass", out, out)
        self.assertEqual(rc, 0, out)

    @NEEDS_TSC
    def test_broken_import_in_js_or_cjs_is_not_checked(self):
        rc, out = check({".code-check.json": config([]),
                         "app.js": 'import { x } from "./gone.js";\nexport default x;\n',
                         "app.cjs": 'const { y } = require("./gone.cjs");\nmodule.exports = y;\n'})
        self.assertIn("javascript typecheck", out, out)
        self.assertEqual(rc, 0, out)

    def test_mjs_import_check_fails_closed_when_tsc_cannot_start(self):
        # No tsc on PATH: a clean .mjs must still be red, since the import check cannot say that it is clean.
        rc, out = check({".code-check.json": config([]), "lib.mjs": "export const a = 1;\n",
                         "app.mjs": 'import { a } from "./lib.mjs";\nexport default a;\n'}, PATH=path_with("git"))
        self.assertEqual(rc, 1, out)
        self.assertIn("could not", out)

    def test_mjs_import_check_whose_tsc_exits_1_with_no_stdout_is_red(self):
        # tsc fails and writes only to stderr: no diagnostic on stdout, so the import check cannot call the .mjs clean.
        shim = path_shim("tsc", "echo 'tsc: failed before it checked the file' >&2\nexit 1")
        rc, out = check({".code-check.json": config([]), "app.mjs": "export const a = 1;\n"},
                        PATH=shim + os.pathsep + os.environ["PATH"])
        self.assertEqual(rc, 1, out)
        self.assertIn("printed no diagnostics", out)

    @NEEDS_TSC
    def test_mjs_extensionless_import_of_a_sibling_is_red(self):
        # Node 22 rejects "./lib" for lib.mjs: the specifier needs its extension (TS2835).
        rc, out = check({".code-check.json": config([]), "lib.mjs": "export const a = 1;\n",
                         "app.mjs": 'import { a } from "./lib";\nexport default a;\n'})
        self.assertEqual(rc, 1, out)
        self.assertIn("app.mjs", out)
        self.assertIn("TS2835", out)

    @NEEDS_TSC
    def test_mjs_extensionless_import_of_a_missing_file_is_red(self):
        # Node 22 rejects "./nope" before it looks for the file: the specifier needs its extension (TS2834).
        rc, out = check({".code-check.json": config([]), "app.mjs": 'import { a } from "./nope";\nexport default a;\n'})
        self.assertEqual(rc, 1, out)
        self.assertIn("app.mjs", out)
        self.assertIn("TS2834", out)

    @NEEDS_TSC
    def test_mjs_import_of_a_directory_is_red(self):
        # Node 22 rejects "./dir" for a folder with an index.mjs: a directory is not a module (TS2834).
        rc, out = check({".code-check.json": config([]), "dir/index.mjs": "export const q = 1;\n",
                         "app.mjs": 'import { q } from "./dir";\nexport default q;\n'})
        self.assertEqual(rc, 1, out)
        self.assertIn("app.mjs", out)
        self.assertIn("TS2834", out)

    @NEEDS_TSC
    def test_mjs_type_annotation_is_red(self):
        # Node 22 cannot parse a type annotation in a .mjs file (TS8010).
        rc, out = check({".code-check.json": config([]), "app.mjs": "const x: number = 1;\nexport default x;\n"})
        self.assertEqual(rc, 1, out)
        self.assertIn("app.mjs", out)
        self.assertIn("TS8010", out)

    @NEEDS_TSC
    def test_mjs_type_assertion_is_red(self):
        # Node 22 cannot parse an `as` assertion in a .mjs file (TS8016).
        rc, out = check({".code-check.json": config([]),
                         "app.mjs": "const z = 1;\nconst y = z as number;\nexport default y;\n"})
        self.assertEqual(rc, 1, out)
        self.assertIn("app.mjs", out)
        self.assertIn("TS8016", out)

    @NEEDS_TSC
    def test_mjs_ts_only_forms_are_each_red_by_their_code(self):
        # Node 22 cannot parse these in a .mjs file: `satisfies` is TS8037; enum, interface and import type are TS8006.
        # Each form has its own file, so each output row must name that file and its code.
        forms = {"sat.mjs": ("const c = {} satisfies object;\nexport default c;\n", "TS8037"),
                 "en.mjs": ("enum E {}\n", "TS8006"),
                 "ifc.mjs": ("interface I {}\n", "TS8006"),
                 "it.mjs": ('import type { X } from "./x.mjs";\n', "TS8006")}
        _, out = check({".code-check.json": config([]), "x.mjs": "export class X {}\n",
                        **{name: text for name, (text, _) in forms.items()}})
        for name, (_, code) in forms.items():
            with self.subTest(form=name):
                self.assertTrue(one_line_with(out, name, code), "%s: no %s row in:\n%s" % (name, code, out))

    @NEEDS_TSC
    def test_mjs_jsdoc_type_annotation_is_green(self):
        # The control for the two cases above: a JSDoc type is plain comment syntax to Node, so it stays green.
        rc, out = check({".code-check.json": config([]),
                         "app.mjs": "/** @type {number} */\nconst x = 1;\nexport default x;\n"})
        self.assertIn("javascript typecheck: mjs-imports pass", out, out)
        self.assertEqual(rc, 0, out)

    @NEEDS_TSC
    def test_npm_notice_on_stderr_is_not_an_mjs_problem(self):
        # The shim fakes the npm update notice that npm prints on stderr when CI is unset. A .mjs with only a type
        # error stays green: the notice is no diagnostic, and it is not a problem.
        real = shutil.which("tsc")
        self.assertIsNotNone(real, "tsc not on PATH")
        shim = path_shim("tsc", "echo 'npm notice New minor version of npm available' >&2\nexec %s \"$@\"" % shlex.quote(real))
        rc, out = check({".code-check.json": config([]), "app.mjs": "const n = 1;\nn.foo;\nexport default n;\n"},
                        PATH=shim + os.pathsep + os.environ["PATH"], unset=("CI",))
        self.assertIn("javascript typecheck: mjs-imports pass", out, out)
        self.assertEqual(rc, 0, out)


class LinkStep(unittest.TestCase):
    """The opt-in link step: each root in .code-check.json's "link" key links unrun, as harness/load-files.mjs does.
    The file never runs; a failing root names its own error under its FAIL load line."""

    @NEEDS_LINK
    def test_missing_bare_package_is_red_and_not_unknown(self):
        rc, out = link_check({"app.mjs": 'import x from "nopkg";\nexport default x;\n'}, roots=["app.mjs"])
        self.assertIn(LINK_FAIL, out, out)
        self.assertNotIn("mjs-link unknown", out, out)
        self.assertIn("nopkg", failure(out, "app.mjs"), out)
        self.assertEqual(rc, 1, out)

    @NEEDS_LINK
    def test_package_with_the_named_export_is_green(self):
        rc, out = link_check({"app.mjs": 'import { present } from "fakepkg";\nexport default present;\n'},
                             roots=["app.mjs"], untracked=FAKE_PKG)
        self.assertIn(LINK_PASS, out, out)
        self.assertEqual(rc, 0, out)

    @NEEDS_LINK
    def test_package_missing_the_named_export_is_red(self):
        rc, out = link_check({"app.mjs": 'import { missingName } from "fakepkg";\nexport default missingName;\n'},
                             roots=["app.mjs"], untracked=FAKE_PKG)
        self.assertIn(LINK_FAIL, out, out)
        self.assertIn("missingName", failure(out, "app.mjs"), out)
        self.assertEqual(rc, 1, out)

    @NEEDS_LINK
    def test_node_builtin_missing_a_named_export_is_red(self):
        rc, out = link_check({"app.mjs": 'import { notThere } from "node:fs";\nexport default notThere;\n'},
                             roots=["app.mjs"])
        self.assertIn(LINK_FAIL, out, out)
        self.assertIn("notThere", failure(out, "app.mjs"), out)
        self.assertEqual(rc, 1, out)

    @NEEDS_LINK
    def test_package_in_a_subfolder_resolves_from_the_importing_file(self):
        # Only pkgs/web/node_modules holds innerpkg: a lookup from the repo root or from the action's folder finds nothing.
        inner = {"pkgs/web/node_modules/innerpkg/package.json": '{"name": "innerpkg", "type": "module", "main": "index.mjs"}\n',
                 "pkgs/web/node_modules/innerpkg/index.mjs": "export const present = 1;\n"}
        rc, out = link_check({"pkgs/web/app.mjs": 'import { present } from "innerpkg";\nexport default present;\n'},
                             roots=["pkgs/web/app.mjs"], untracked=inner)
        self.assertIn(LINK_PASS, out, out)
        self.assertEqual(rc, 0, out)

    @NEEDS_LINK
    def test_mjs_root_reaches_a_ts_file_missing_a_named_export_is_red(self):
        # The root's own imports resolve. The break is one .ts file down, so the link must follow the graph through .ts.
        rc, out = link_check({"app.mjs": 'import { viaMid } from "./mid.ts";\nexport default viaMid;\n',
                              "mid.ts": 'import { notThere } from "./lib.ts";\nexport const viaMid = notThere;\n',
                              "lib.ts": "export const present = 1;\n"}, roots=["app.mjs"])
        self.assertIn(LINK_FAIL, out, out)
        self.assertIn("notThere", failure(out, "app.mjs"), out)
        self.assertEqual(rc, 1, out)

    @NEEDS_LINK
    def test_mjs_root_importing_a_ts_file_missing_a_named_export_is_red(self):
        rc, out = link_check({"app.mjs": 'import { notThere } from "./lib.ts";\nexport default notThere;\n',
                              "lib.ts": "export const present = 1;\n"}, roots=["app.mjs"])
        self.assertIn(LINK_FAIL, out, out)
        self.assertIn("notThere", failure(out, "app.mjs"), out)
        self.assertEqual(rc, 1, out)

    @NEEDS_LINK
    def test_ts_root_resolves_as_tsx_does_and_is_green(self):
        # ./f.js names f.ts, ./g probes to g.tsx, ./d names d/index.ts, and @/x names x.ts from the repo root.
        rc, out = link_check({"app.ts": ('import { fromF } from "./f.js";\nimport { fromG } from "./g";\n'
                                         'import { fromD } from "./d";\nimport { fromX } from "@/x";\n'
                                         "export const all: number = fromF + fromG + fromD + fromX;\n"),
                              "f.ts": "export const fromF: number = 1;\n",
                              "g.tsx": "export const fromG: number = 2;\n",
                              "d/index.ts": "export const fromD: number = 3;\n",
                              "x.ts": "export const fromX: number = 4;\n"}, roots=["app.ts"])
        self.assertIn(LINK_PASS, out, out)
        self.assertEqual(rc, 0, out)

    @NEEDS_LINK
    def test_mjs_root_extensionless_import_of_a_ts_only_file_is_red(self):
        # A .mjs root resolves as node does: "./f" is not f.ts, so the probe that tsx runs does not apply.
        rc, out = link_check({"app.mjs": 'import { a } from "./f";\nexport default a;\n', "f.ts": "export const a = 1;\n"},
                             roots=["app.mjs"])
        self.assertIn(LINK_FAIL, out, out)
        self.assertIn("./f", failure(out, "app.mjs"), out)
        self.assertEqual(rc, 1, out)

    @NEEDS_LINK
    def test_ts_root_side_effect_import_of_a_missing_file_is_red(self):
        rc, out = link_check({"app.ts": 'import "./gone.ts";\nexport const n: number = 1;\n'}, roots=["app.ts"])
        self.assertIn(LINK_FAIL, out, out)
        self.assertIn("gone.ts", failure(out, "app.ts"), out)
        self.assertEqual(rc, 1, out)

    @NEEDS_LINK
    def test_file_named_by_an_npm_script_is_a_root_and_its_broken_import_is_red(self):
        pkg = '{"name": "fixture", "scripts": {"cli": "tsx src/runCli.ts --once"}}\n'
        rc, out = link_check({"package.json": pkg, "src/runCli.ts": 'import { x } from "./gone.ts";\nexport const y = x;\n'},
                             npm_scripts=["src/"])
        self.assertIn(LINK_FAIL, out, out)
        self.assertIn("gone.ts", failure(out, "src/runCli.ts"), out)
        self.assertEqual(rc, 1, out)

    @NEEDS_LINK
    def test_file_no_script_names_and_no_root_matches_is_not_checked(self):
        pkg = '{"name": "fixture", "scripts": {"cli": "tsx other.ts"}}\n'
        rc, out = link_check({"package.json": pkg, "other.ts": "export const z: number = 1;\n",
                              "src/runCli.ts": 'import { x } from "./gone.ts";\nexport const y = x;\n'},
                             roots=["other.ts"], npm_scripts=["src/"])
        self.assertIn(LINK_PASS, out, out)
        self.assertNotIn("FAIL load:", out, out)
        self.assertEqual(rc, 0, out)

    @NEEDS_LINK
    def test_skip_prefix_drops_a_broken_root_and_is_green(self):
        files = {"app.ts": "export const n: number = 1;\n",
                 "legacy/old.ts": 'import { gone } from "./gone.ts";\nexport const o = gone;\n'}
        rc, out = link_check(files, roots=["*.ts"], skip=["legacy/"])
        self.assertIn(LINK_PASS, out, out)
        self.assertNotIn("FAIL load:", out, out)
        self.assertEqual(rc, 0, out)

    @NEEDS_LINK
    def test_same_broken_root_without_skip_is_red(self):
        files = {"app.ts": "export const n: number = 1;\n",
                 "legacy/old.ts": 'import { gone } from "./gone.ts";\nexport const o = gone;\n'}
        rc, out = link_check(files, roots=["*.ts"])
        self.assertIn(LINK_FAIL, out, out)
        self.assertIn("gone.ts", failure(out, "legacy/old.ts"), out)
        self.assertEqual(rc, 1, out)

    @NEEDS_NODE
    def test_no_typescript_in_the_repo_is_unknown_and_exits_0_locally(self):
        rc, out = link_check({"app.mjs": "export const a = 1;\n"}, roots=["app.mjs"], ts=False, unset=("CI",))
        self.assertTrue(one_line_with(out, "mjs-link unknown"), out)
        self.assertEqual(rc, 0, out)

    @NEEDS_NODE
    def test_no_typescript_in_the_repo_is_red_under_ci(self):
        rc, out = link_check({"app.mjs": "export const a = 1;\n"}, roots=["app.mjs"], ts=False, CI="1")
        self.assertTrue(one_line_with(out, "mjs-link unknown"), out)
        self.assertEqual(rc, 1, out)
        self.assertIn("code-check: FAIL", out, out)

    @NEEDS_TSC
    def test_without_a_link_key_nothing_is_linked(self):
        # The same broken bare import and broken .ts root as main checks: with no link key both stay green, as on main.
        rc, out = check({".code-check.json": config([]), "app.mjs": 'import x from "nopkg";\nexport default x;\n',
                         "lone.ts": 'import "./gone.ts";\nexport const z: number = 1;\n'})
        self.assertNotIn("mjs-link", out, out)
        self.assertIn("javascript typecheck: mjs-imports pass", out, out)
        self.assertEqual(rc, 0, out)

    @NEEDS_LINK
    def test_ts_scanner_traps_are_green(self):
        # A string holding an import, a comment opener and a line comment; a template literal with an import line.
        rc, out = link_check({"app.ts": ("// don't mind this comment, it holds /* an opener\n"
                                         "export const text = \"import x from './gone' // /* not a comment\";\n"
                                         "export const block = `\nimport './gone.mjs';\n`;\n"
                                         "export const n: number = 1;\n")}, roots=["app.ts"])
        self.assertIn(LINK_PASS, out, out)
        self.assertEqual(rc, 0, out)

    @NEEDS_LINK
    def test_tsx_lone_quote_in_jsx_text_is_green(self):
        rc, out = link_check({"app.tsx": ("export const text = \"import x from './gone' // /* not a comment\";\n"
                                          "export const el = <p>Don't</p>;\n")}, roots=["app.tsx"], untracked=REACT_JSX)
        self.assertIn(LINK_PASS, out, out)
        self.assertEqual(rc, 0, out)

    @NEEDS_LINK
    def test_link_never_runs_the_file(self):
        # app.mjs writes a marker at its top level; boom.ts throws at its top level. Linking runs neither.
        marker = os.path.join(tempfile.mkdtemp(dir=RUN_FOLDER), "ran.txt")
        files = {"app.mjs": 'import { writeFileSync } from "node:fs";\nwriteFileSync(%s, "ran");\nexport const a = 1;\n' % json.dumps(marker),
                 "boom.ts": 'throw new Error("ran");\nexport const b: number = 1;\n'}
        rc, out = link_check(files, roots=["app.mjs", "boom.ts"])
        self.assertIn(LINK_PASS, out, out)
        self.assertFalse(os.path.exists(marker), "the link step ran app.mjs and wrote its marker")
        self.assertEqual(rc, 0, out)

    @NEEDS_LINK
    def test_many_roots_sharing_one_target_fail_only_the_broken_one(self):
        files = {"lib.ts": "export const present = 1;\n",
                 "broken.mjs": 'import { notThere } from "./lib.ts";\nexport default notThere;\n'}
        for i in range(40):
            files["m%02d.mjs" % i] = 'import { present } from "./lib.ts";\nexport default present;\n'
        rc, out = link_check(files, roots=["*.mjs"])
        self.assertIn(LINK_FAIL, out, out)
        self.assertEqual(out.count("FAIL load:"), 1, out)
        self.assertIn("notThere", failure(out, "broken.mjs"), out)
        self.assertEqual(rc, 1, out)

    @NEEDS_LINK
    def test_empty_roots_check_nothing(self):
        rc, out = link_check({"lone.ts": 'import "./gone.ts";\nexport const z: number = 1;\n'}, roots=[])
        self.assertNotIn("FAIL load:", out, out)
        self.assertEqual(rc, 0, out)

    @NEEDS_LINK
    def test_star_in_a_root_crosses_folders(self):
        rc, out = link_check({"src/deep/b.ts": 'import "./gone.ts";\nexport const b: number = 1;\n',
                              "app.ts": "export const n: number = 1;\n"}, roots=["src/*.ts"])
        self.assertIn(LINK_FAIL, out, out)
        self.assertIn("gone.ts", failure(out, "src/deep/b.ts"), out)
        self.assertEqual(rc, 1, out)

    @NEEDS_LINK
    def test_roots_match_tracked_files_only(self):
        rc, out = link_check({"app.ts": "export const n: number = 1;\n"}, roots=["*.ts"],
                             untracked={"stray.ts": 'import "./gone.ts";\n'})
        self.assertIn(LINK_PASS, out, out)
        self.assertNotIn("FAIL load:", out, out)
        self.assertEqual(rc, 0, out)


def names_word(out, word):
    """True when a line of out holds `word` as a whole word. "skipped" does not hold "skip"."""
    return any(re.search(r"\b%s\b" % re.escape(word), line) for line in out.splitlines())


class LinkConfig(unittest.TestCase):
    """A malformed "link" value is red, and the failure names its key. A roots glob that matches no tracked file, or
    only files the link step cannot load, is red, and the failure names the glob. An unknown key in "link" is red. An
    npm_scripts prefix that matches nothing is not an error. A file dropped by skip is printed, and the verdict stays green."""
    CLEAN = {"app.mjs": "export const a = 1;\n"}

    def assertMalformed(self, link, key, files=CLEAN):
        rc, out = link_check(files, link=link)
        self.assertNotIn("Traceback", out, out)
        self.assertEqual(rc, 1, out)
        self.assertIn("code-check: FAIL", out, out)
        self.assertTrue(names_word(out, key), "no line names %s:\n%s" % (key, out))

    @NEEDS_LINK
    def test_roots_as_a_string_is_red_and_names_roots(self):
        self.assertMalformed({"roots": "harness/*.mjs", "skip": [], "npm_scripts": []}, "roots",
                             {"harness/a.mjs": self.CLEAN["app.mjs"]})

    @NEEDS_LINK
    def test_roots_with_a_non_string_entry_is_red_and_names_roots(self):
        self.assertMalformed({"roots": [5], "skip": [], "npm_scripts": []}, "roots")

    @NEEDS_LINK
    def test_skip_as_a_string_is_red_and_names_skip(self):
        self.assertMalformed({"roots": ["app.mjs"], "skip": "legacy/", "npm_scripts": []}, "skip")

    @NEEDS_LINK
    def test_skip_with_a_non_string_entry_is_red_and_names_skip(self):
        self.assertMalformed({"roots": ["app.mjs"], "skip": [5], "npm_scripts": []}, "skip")

    @NEEDS_LINK
    def test_npm_scripts_as_a_string_is_red_and_names_npm_scripts(self):
        self.assertMalformed({"roots": ["app.mjs"], "skip": [], "npm_scripts": "src/"}, "npm_scripts")

    @NEEDS_LINK
    def test_npm_scripts_with_a_non_string_entry_is_red_and_names_npm_scripts(self):
        self.assertMalformed({"roots": ["app.mjs"], "skip": [], "npm_scripts": [5]}, "npm_scripts")

    @NEEDS_LINK
    def test_empty_skip_entry_is_red_and_names_skip(self):
        self.assertMalformed({"roots": ["app.mjs"], "skip": [""], "npm_scripts": []}, "skip")

    @NEEDS_LINK
    def test_slash_skip_entry_is_red_and_names_skip(self):
        self.assertMalformed({"roots": ["app.mjs"], "skip": ["/"], "npm_scripts": []}, "skip")

    @NEEDS_LINK
    def test_empty_npm_scripts_entry_is_red_and_names_npm_scripts(self):
        self.assertMalformed({"roots": ["app.mjs"], "skip": [], "npm_scripts": [""]}, "npm_scripts")

    @NEEDS_LINK
    def test_slash_npm_scripts_entry_is_red_and_names_npm_scripts(self):
        self.assertMalformed({"roots": ["app.mjs"], "skip": [], "npm_scripts": ["/"]}, "npm_scripts")

    @NEEDS_LINK
    def test_roots_glob_matching_no_tracked_file_is_red_and_names_the_glob(self):
        rc, out = link_check(self.CLEAN, roots=["app.mjs", "harness/*.mjs"])
        self.assertNotIn("Traceback", out, out)
        self.assertEqual(rc, 1, out)
        self.assertIn("code-check: FAIL", out, out)
        self.assertIn("harness/*.mjs", out, out)

    @NEEDS_LINK
    def test_empty_roots_entry_is_red_and_names_roots(self):
        self.assertMalformed({"roots": [""], "skip": [], "npm_scripts": []}, "roots")

    @NEEDS_LINK
    def test_roots_glob_matching_only_unlinkable_files_is_red_and_names_the_glob(self):
        rc, out = link_check({"harness/a.js": "export const a = 1;\n"}, roots=["harness/*.js"])
        self.assertNotIn("Traceback", out, out)
        self.assertEqual(rc, 1, out)
        self.assertIn("code-check: FAIL", out, out)
        self.assertIn("harness/*.js", out, out)

    @NEEDS_LINK
    def test_unknown_key_in_link_is_red_and_names_the_key(self):
        self.assertMalformed({"roots": ["app.mjs"], "skip": [], "npm_scripts": [], "root": ["app.mjs"]}, "root")

    @NEEDS_LINK
    def test_file_dropped_by_skip_is_printed_and_stays_green(self):
        rc, out = link_check({"app.ts": "export const n: number = 1;\n",
                              "legacy/old.ts": 'import "./gone.ts";\nexport const o = 1;\n'},
                             roots=["*.ts"], skip=["legacy/"])
        self.assertIn(LINK_PASS, out, out)
        self.assertTrue(one_line_with(out, "skip drops legacy/old.ts"), out)
        self.assertEqual(rc, 0, out)

    @NEEDS_LINK
    def test_npm_scripts_prefix_matching_no_tracked_file_stays_green(self):
        rc, out = link_check(self.CLEAN, roots=["app.mjs"], npm_scripts=["nope/"])
        self.assertIn(LINK_PASS, out, out)
        self.assertEqual(rc, 0, out)


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


def path_shim(name, body):
    """A PATH folder holding one executable `name`, an sh script of `body`. Returns the folder."""
    folder = tempfile.mkdtemp(dir=RUN_FOLDER)
    path = os.path.join(folder, name)
    with open(path, "w", newline="\n") as f:
        f.write("#!/bin/sh\n" + body + "\n")
    os.chmod(path, 0o755)
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
