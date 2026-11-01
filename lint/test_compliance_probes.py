#!/usr/bin/env python3
"""Cases for lint/compliance_probes.py, on fixture git repos. Standard library only.

    python3 lint/test_compliance_probes.py

Each group goes red on the gap it guards, and stays quiet on a repo that is fine: a tool's own
folder, a vendored screenshot script, a generated token file, a cited cap and an owner-named cap.
PROBES_UNDER_TEST names the script under test (default: the one beside this file).
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PROBES = os.path.abspath(os.environ.get("PROBES_UNDER_TEST") or os.path.join(HERE, "compliance_probes.py"))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: every temp path comes from this run's folder
import check_glossary  # noqa: E402  the glossary the words group reads; a case patches it in this process
import layout  # noqa: E402
import rule_audit  # noqa: E402  the live anchors the supersede group reads; a case patches it in this process

RUN_FOLDER = _test_temp.run_folder()  # test-temp-standard (one run folder per test run)
EXTRAS = layout.layout()["extras"]


def kind_path(name):
    return layout.layout()["kinds"][name]["path"]


class Repo:
    def __init__(self, test, origin=False):
        """`origin`: a child clone of a bare origin, on main. `publish()` then makes origin/main, the base
        a child's `git diff origin/main...HEAD` reads."""
        self.root = tempfile.mkdtemp(prefix="probes-", dir=RUN_FOLDER)
        test.addCleanup(shutil.rmtree, self.root, True)
        subprocess.run(["git", "init", "-q", self.root], check=True)
        if origin:
            bare = tempfile.mkdtemp(prefix="origin-", dir=RUN_FOLDER)
            test.addCleanup(shutil.rmtree, bare, True)
            subprocess.run(["git", "init", "-q", "--bare", bare], check=True)
            self.git("symbolic-ref", "HEAD", "refs/heads/main")
            self.git("remote", "add", "origin", bare)

    def git(self, *args):
        subprocess.run(["git", "-C", self.root, "-c", "user.name=test", "-c", "user.email=test@example.com",
                        *args], check=True, capture_output=True)
        return self

    def publish(self):
        """Commit what is staged as main and push it, so origin/main exists."""
        return self.git("commit", "-q", "-m", "base").git("push", "-q", "origin", "main")

    def branch(self, name):
        return self.git("checkout", "-q", "-b", name)

    def commit(self, message="change"):
        return self.git("commit", "-q", "-m", message)

    def write(self, rel, text="x\n"):
        full = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(text)
        subprocess.run(["git", "-C", self.root, "add", "-f", rel], check=True)
        return self

    def core(self):
        """Every core kind of the layout, at its layout path."""
        for name, kind in layout.layout()["kinds"].items():
            if kind["set"] != "core":
                continue
            path = kind["path"]
            self.write(path + "/a.md" if "." not in os.path.basename(path) else path)
        return self

    def run(self, group):
        done = subprocess.run([sys.executable, PROBES, group, self.root], capture_output=True, text=True)
        return done.returncode, done.stdout


class Layout(unittest.TestCase):
    def test_not_rolled_out_previews_and_passes(self):
        code, out = Repo(self).write("src/a.py").run("layout")
        self.assertEqual(code, 0, out)
        self.assertIn("not rolled out", out)
        self.assertIn("preview folder src/", out)

    def test_stray_folder_and_missing_core_kind_are_red(self):
        repo = Repo(self).write(EXTRAS, '{"kinds": {}, "rolled-out": true}').write("src/a.py").write("CLAUDE.md")
        code, out = repo.run("layout")
        self.assertEqual(code, 1, out)
        self.assertIn("folder src/: neither", out)
        self.assertIn("missing core kind decisions: " + kind_path("decisions"), out)
        self.assertNotIn("missing core kind claude-md", out)

    def test_stray_folder_inside_a_kind_parent_is_red(self):
        parent = kind_path("decisions").rsplit("/", 1)[0]
        repo = Repo(self).core().write(EXTRAS, '{"kinds": {}, "rolled-out": true}').write(parent + "/odd/a.md")
        code, out = repo.run("layout")
        self.assertEqual(code, 1, out)
        self.assertIn("folder %s/odd/" % parent, out)

    def test_extras_tool_folders_and_kind_subfolders_pass(self):
        repo = Repo(self).core().write(EXTRAS, '{"kinds": {"src": {"path": "src"}}, "rolled-out": true}')
        repo.write("src/deep/a.py").write(".github/workflows/a.yml").write(".claude/skills/s/SKILL.md")
        repo.write(kind_path("decisions") + "/sub/a.md")
        code, out = repo.run("layout")
        self.assertEqual((code, out.strip()), (0, "layout: in shape"))

    def test_scorecard_file_is_a_layout_kind(self):
        repo = Repo(self).core().write(EXTRAS, '{"kinds": {}, "rolled-out": true}').write("docs/health/compliance.md")
        code, out = repo.run("layout")
        self.assertEqual((code, out.strip()), (0, "layout: in shape"))

    def test_legacy_folder_names_its_move(self):
        legacy = layout.legacy("decisions")
        if legacy == kind_path("decisions"):
            self.skipTest("the layout has no legacy decisions path")
        code, out = Repo(self).write(legacy + "/a.md").run("layout")
        self.assertIn("legacy home of decisions, moves to " + kind_path("decisions"), out)

    def test_a_todo_kept_by_legacy_repos_is_not_missing(self):
        repo = Repo(self).core().write(EXTRAS, '{"kinds": {"todo": {"path": "records"}}, "rolled-out": true}').write("records/backlog.md")
        subprocess.run(["git", "-C", repo.root, "rm", "-q", "--cached", kind_path("todo")], check=True)
        code, out = repo.run("layout")
        self.assertEqual((code, out.strip()), (0, "layout: in shape"))

    def test_untracked_core_kind_is_missing(self):
        rules = kind_path("rules")
        repo = Repo(self).write(EXTRAS, '{"kinds": {}, "rolled-out": true}')
        os.makedirs(os.path.join(repo.root, *rules.split("/")))
        code, out = repo.run("layout")
        self.assertIn("missing core kind rules: " + rules, out)

    def test_this_repo_is_in_shape(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        done = subprocess.run([sys.executable, PROBES, "layout", root], capture_output=True, text=True)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "layout: in shape"))

    def test_this_repos_extras_name_real_folders_and_no_wildcard(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, *EXTRAS.split("/")), encoding="utf-8") as handle:
            text = handle.read()
        kinds = json.loads(text)["kinds"]
        files = subprocess.run(["git", "-C", root, "ls-files"], capture_output=True, text=True, check=True).stdout.split("\n")
        for name, kind in kinds.items():
            where = kind["path"].strip("/")
            self.assertNotIn("*", where, name)
            self.assertTrue(any(f.startswith(where + "/") for f in files), "%s: no tracked file under %s" % (name, where))
        repo = Repo(self).core().write(EXTRAS, text)
        for kind in kinds.values():
            repo.write(kind["path"].strip("/") + "/a.x")
        self.assertEqual(repo.run("layout")[1].strip(), "layout: in shape")
        code, out = repo.write("undeclared/a.x").run("layout")
        self.assertEqual(code, 1, out)
        self.assertIn("folder undeclared/: neither", out)

    def test_not_a_git_repo_is_unknown(self):
        root = tempfile.mkdtemp(prefix="probes-", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, root, True)
        done = subprocess.run([sys.executable, PROBES, "layout", root], capture_output=True, text=True)
        self.assertEqual(done.returncode, 2, done.stdout)
        self.assertIn("layout: unknown", done.stdout)


SHOOT = '{"baseUrl": "http://localhost:5173", "routes": ["/", "/b"]}'


def shoot_json(route=None, **config):
    """A one-route shoot config. `route` adds keys to the route object, `config` to the top level."""
    return json.dumps({"baseUrl": "http://localhost:5173", "routes": [dict({"path": "/"}, **(route or {}))], **config})


# Each malformed value of the reach keys, as (label, route keys, config keys, a pattern the gap line must match).
# bin/shoot refuses the same list (lint/test_shoot.mjs, REFUSED). It is a copy because that suite is
# Node and this one is Python, and a shared data file would sit outside the CI scope map.
SHOOT_STEPS = "step|state|click|wait"
SHOOT_REACH_BAD = (
    [("steps is %s" % label, {"steps": value}, {}, SHOOT_STEPS) for label, value in (
        ("an object", {"click": "#a"}), ("a string", "click #a"), ("a number", 5), ("an empty list", []),
        ("null", None), ("an empty string", ""), ("the number 0", 0),
        ("a click selector that is empty", [{"click": ""}]),
        ("a click selector that is blank", [{"click": " "}]),
        ("a state that is null", [{"wait": "#a", "state": None}]),
        ("a step with neither click nor wait", [{}]),
        ("a step with both click and wait", [{"click": "#a", "wait": "#b"}]),
        ("a step with only a state", [{"state": "hidden"}]),
        ("a click step with a state", [{"click": "#a", "state": "visible"}]),
        ("a step with another key", [{"tap": "#a"}]),
        ("a step that is a string", ["#a"]), ("a step that is null", [None]), ("a step that is a number", [5]),
        ("a step that is a list", [["click", "#a"]]),
        ("a good step, then a bad one", [{"click": "#a"}, {}]),
        ("a click selector that is a number", [{"click": 5}]),
        ("a click selector that is null", [{"click": None}]),
        ("a click selector that is true", [{"click": True}]),
        ("a wait selector that is a list", [{"wait": ["#a"]}]),
        ("a wait selector that is an object", [{"wait": {"css": "#a"}}]),
        ("a state of attached", [{"wait": "#a", "state": "attached"}]),
        ("a state of detached", [{"wait": "#a", "state": "detached"}]),
        ("a state that is true", [{"wait": "#a", "state": True}]),
    )]
    + [("localStorage: %s" % label, {"localStorage": value}, {}, "localStorage") for label, value in (
        ("a string", "k=v"), ("a number", 5), ("true", True), ("a list", ["k", "v"]),
        ("a value that is a number", {"k": 1}), ("a value that is null", {"k": None}),
        ("a value that is true", {"k": True}), ("a value that is an object", {"k": {"a": "b"}}),
        ("a value that is a list", {"k": ["v"]}), ("a good value, then a bad one", {"a": "x", "b": 2}),
    )]
    + [("ignoreHTTPSErrors: %s" % label, {}, {"ignoreHTTPSErrors": value}, "ignoreHTTPSErrors") for label, value in (
        ("a string", "yes"), ("the string true", "true"), ("the number 1", 1), ("the number 0", 0),
        ("a list", []), ("an object", {}),
    )]
)


class Design(unittest.TestCase):
    def test_no_screens_is_na(self):
        code, out = Repo(self).write("a.py").run("design")
        self.assertEqual((code, out.strip()), (0, "design: n/a - no screen files"))

    def test_ready_repo_is_in_shape(self):
        repo = Repo(self).write("src/App.tsx").write(".claude/shoot.json", SHOOT).write("src/tokens.css")
        repo.write("ios/Tokens.swift", "// Generated from src/tokens.css. Do not edit.\n")
        code, out = repo.run("design")
        self.assertEqual(code, 0, out)
        self.assertIn("screens named: pass - 2 route(s)", out)
        self.assertIn("sizes named: pass - shoot's default", out)
        self.assertIn("token file: pass - src/tokens.css, plus 1 generated", out)
        self.assertTrue(out.startswith("design: in shape"), out)

    def test_each_gap_is_its_own_line(self):
        repo = Repo(self).write("src/App.tsx").write("Makefile", "screenshot:\n\tnode s.mjs\n")
        repo.write(".claude/skills/x/scripts/modern-screenshot.umd.js")
        code, out = repo.run("design")
        self.assertEqual(code, 1, out)
        self.assertIn("screens named: gap - no .claude/shoot.json", out)
        self.assertIn("screenshot command: partial - own command, not the shared shoot: Makefile target screenshot\n", out)
        self.assertIn("token file: gap - no tokens file", out)
        self.assertIn("ui copy: known gap", out)
        self.assertTrue(out.startswith("design: out"), out)

    def assert_gap(self, bad, key=None):
        """A config shoot refuses reads as a gap. `key`, when given, is a pattern the gap line must match."""
        code, out = Repo(self).write("a.tsx").write(".claude/shoot.json", bad).write("tokens.css").run("design")
        self.assertEqual(code, 1, bad)
        self.assertIn("screens named: gap", out)
        self.assertIn("screenshot command: gap", out)
        self.assertNotIn(": pass - the shared shoot", out)
        if key:
            line = next(line for line in out.splitlines() if line.startswith("  screens named: gap"))
            self.assertRegex(line, "(?i)" + key, "the gap line does not name the bad key")

    def test_a_config_shoot_refuses_is_a_gap(self):
        for bad in ('{"routes": ["/"]}', '{"baseUrl": "http://h", "routes": ["/"], "sizes": "x"}',
                    '{"baseUrl": "http://h", "routes": ["/"], "themes": ["sepia"]}', '{"baseUrl": "http://h", "routes": []}'):
            self.assert_gap(bad)

    def test_a_malformed_steps_localstorage_or_https_flag_is_a_gap(self):
        for label, route, config, key in SHOOT_REACH_BAD:
            with self.subTest(label):
                self.assert_gap(shoot_json(route, **config), key)

    def test_a_config_using_the_new_keys_correctly_is_in_shape(self):
        steps = [{"click": "#menu"}, {"wait": "#ready"}, {"wait": "#spinner", "state": "hidden"}, {"wait": "#view", "state": "visible"}]
        for flag in (True, False):
            good = json.dumps({"baseUrl": "http://localhost:5173", "ignoreHTTPSErrors": flag, "futureKey": 1, "routes": [
                "/", {"path": "/b", "steps": steps, "futureRouteKey": {"a": 1}},
                {"name": "c", "path": "/c", "localStorage": {"token": "abc", "theme": "dark"}},
                {"path": "/d", "steps": [{"click": "#x"}], "localStorage": {"k": "v"}}]})
            with self.subTest(ignoreHTTPSErrors=flag):
                repo = Repo(self).write("src/App.tsx").write(".claude/shoot.json", good).write("src/tokens.css")
                repo.write("ios/Tokens.swift", "// Generated from src/tokens.css. Do not edit.\n")
                code, out = repo.run("design")
                self.assertEqual(code, 0, out)
                self.assertIn("screens named: pass - 4 route(s)", out)
                self.assertIn("screenshot command: pass - the shared shoot reads", out)
                self.assertTrue(out.startswith("design: in shape"), out)

    def test_token_paths_tests_and_generated(self):
        repo = Repo(self).write("a.tsx").write(".claude/shoot.json", SHOOT)
        repo.write("latest/tokens.css", "/* not generated: the source */\n").write("tests/tokens.json")
        repo.write("app/tokens.test.ts").write("lint/test_shoot.mjs")
        code, out = repo.run("design")
        self.assertIn("token file: pass - latest/tokens.css\n", out)
        self.assertEqual(code, 0, out)

    def test_layout_token_path_counts(self):
        home = layout.layout()["kinds"]["tokens"]["path"]
        code, out = Repo(self).write("a.tsx").write(".claude/shoot.json", SHOOT).write(home, "{}").run("design")
        self.assertIn("token file: pass - " + home, out)  # TOKEN_FILE must keep matching the layout's name

    def test_two_token_sources_are_partial(self):
        repo = Repo(self).write("App.swift").write(".claude/shoot.json", SHOOT)
        repo.write("web/tokens.css").write("ios/Tokens.swift")
        code, out = repo.run("design")
        self.assertEqual(code, 1, out)
        self.assertIn("token file: partial - 2 token sources", out)

    def test_shoot_config_matches_bin_shoot(self):
        with open(os.path.join(os.path.dirname(HERE), "bin", "shoot"), encoding="utf-8") as handle:
            found = re.search(r"config: path\.join\(([^)]*)\)", handle.read())
        parts = re.findall(r'"([^"]+)"', found.group(1))
        code, out = Repo(self).write("a.tsx").write("/".join(parts), SHOOT).run("design")
        self.assertIn("screens named: pass", out)


STARTER = os.path.join(os.path.dirname(HERE), "skills", "ios-apps", "scripts", "new_app.py")


class Ios(unittest.TestCase):
    """The starter's tree is the gold standard. Each case adds one drift and reads its line."""

    def gold(self):
        repo = Repo(self)
        dest = os.path.join(repo.root, "app")
        subprocess.run([sys.executable, STARTER, dest, "--name", "Tally", "--bundle-id", "dev.example.tally",
                        "--repo-url", "https://github.com/example/tally.git"], check=True, capture_output=True)
        for base, _, files in os.walk(dest):
            for name in files:
                rel = os.path.relpath(os.path.join(base, name), dest).replace(os.sep, "/")
                with open(os.path.join(base, name), encoding="utf-8") as handle:
                    repo.write(rel, handle.read())
        shutil.rmtree(dest)
        return repo

    def text(self, repo, rel):
        with open(os.path.join(repo.root, *rel.split("/")), encoding="utf-8") as handle:
            return handle.read()

    def edit(self, repo, rel, old, new):
        text = self.text(repo, rel)
        self.assertIn(old, text)
        return repo.write(rel, text.replace(old, new))

    def red(self, repo, line):
        code, out = repo.run("ios")
        self.assertEqual(code, 1, out)
        self.assertIn(line, out)
        return out

    # The `test diagnostics` item: every xcodebuild test run carries `-collect-test-diagnostics never`.
    # A failed UI test otherwise starts a simctl diagnose of up to 10 minutes. One pass line, one gap line per file list.
    DIAG_PASS = "  test diagnostics: pass - every xcodebuild test run sets -collect-test-diagnostics never\n"

    @staticmethod
    def diag_gap(*files):
        return "  test diagnostics: gap - %s runs xcodebuild test without -collect-test-diagnostics never\n" % ", ".join(files)

    def make_run(self, recipe):
        """The gold plus a Makefile target `ui-run` that holds `recipe`, one tab-led recipe line per line of it."""
        body = "".join("\t%s\n" % line for line in recipe.split("\n"))
        return self.edit(self.gold(), "Makefile", "phone:\n", "ui-run:\n" + body + "\nphone:\n")

    def diag_pass(self, repo):
        code, out = repo.run("ios")
        self.assertEqual(code, 0, out)
        self.assertIn(self.DIAG_PASS, out)

    def test_the_starter_tree_is_in_shape(self):
        code, out = self.gold().run("ios")
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("ios: in shape"), out)
        self.assertEqual(out.count(": pass"), 10, out)
        self.assertIn(self.DIAG_PASS, out)  # the gold runs its UI tests through sim-test, which adds the flag

    def test_no_ios_app_is_na(self):
        code, out = Repo(self).write("Package.swift", "// swift-tools-version: 6.2\n").write("Makefile").run("ios")
        self.assertEqual(code, 0, out)
        self.assertIn("ios: n/a", out)

    def test_floating_ci_runner_is_red(self):
        repo = self.edit(self.gold(), ".github/workflows/ios.yml", "runs-on: macos-26", "runs-on: macos-latest")
        self.red(repo, "ci runner: gap - .github/workflows/ios.yml: macos-latest")

    def test_swift_5_mode_is_red(self):
        repo = self.edit(self.gold(), "native/project.yml", 'SWIFT_VERSION: "6.0"', "SWIFT_VERSION: 5.0")
        self.red(repo, "swift 6: gap - native/project.yml: SWIFT_VERSION 5.0")
        repo = self.edit(self.gold(), "native/TallyKit/Package.swift", "swift-tools-version: 6.2", "swift-tools-version: 5.9")
        self.red(repo, "swift 6: gap - native/TallyKit/Package.swift: swift-tools-version 5.9")
        repo = self.edit(self.gold(), "native/TallyKit/Package.swift", "    ]\n)", "    ],\n    swiftLanguageModes: [.v5]\n)")
        self.red(repo, "swift 6: gap - native/TallyKit/Package.swift: language mode 5")

    def test_missing_make_target_is_red(self):
        repo = self.edit(self.gold(), "Makefile", "native-check:", "batch-check:")
        self.red(repo, "make targets: gap - Makefile lacks native-check")
        code, out = Repo(self).write("ios/project.yml", "options:\n  deploymentTarget:\n    iOS: \"26.0\"\n").run("ios")
        self.assertIn("make targets: gap - no Makefile", out)

    def test_ship_wrapper_is_red(self):
        repo = self.edit(self.gold(), "Makefile", "\tios-ship testflight", "\ttools/testflight")
        self.red(repo, "ship path: gap - Makefile target does not call ios-ship: testflight")

    def test_hand_kept_project_file_is_partial(self):
        repo = self.gold().write("native/Tally.xcodeproj/project.pbxproj", "SWIFT_VERSION = 6.0;\n")
        self.red(repo, "project file: partial - native/Tally.xcodeproj/project.pbxproj is tracked")

    def test_no_kit_package_is_partial(self):
        repo = self.gold()
        subprocess.run(["git", "-C", repo.root, "rm", "-q", "--cached", "native/TallyKit/Package.swift"], check=True)
        out = self.red(repo, "kit package: partial - no tracked Package.swift")
        self.assertIn("ci checks: pass - an app compile on each pull request", out)  # no package, so no package tests to want

    def test_ci_without_package_tests_or_app_compile_is_red(self):
        repo = self.edit(self.gold(), ".github/workflows/ios.yml", "run: make kit-test", "run: echo skipped")
        self.red(repo, "ci checks: gap - no workflow runs the package tests")
        repo = self.edit(self.gold(), ".github/workflows/ios.yml", "run: make app-build", "run: echo skipped")
        self.red(repo, "ci checks: gap - no workflow compiles the app")

    def test_ui_tests_on_each_pull_request_are_red(self):
        repo = self.edit(self.gold(), ".github/workflows/ios.yml", "run: make app-build",
                         "run: xcodebuild test -project native/Tally.xcodeproj -scheme Tally")
        self.red(repo, "slow tests: gap - .github/workflows/ios.yml runs UI tests")

    def test_xcodebuild_test_without_the_flag_in_the_makefile_is_a_gap(self):
        for run in ("xcodebuild test -scheme X",
                    "xcodebuild test-without-building -scheme X",
                    "xcodebuild -project A.xcodeproj -scheme X test",  # the action may follow the flags
                    "xcodebuild test -scheme X -collect-test-diagnostics on-failure",  # only `never` stops the diagnose
                    "xcodebuild test -scheme X -collect-test-diagnostics never\nxcodebuild test -scheme Y",  # each run needs it
                    "xcodebuild test -scheme X && xcodebuild build -scheme Y -collect-test-diagnostics never"):  # another command's flag
            with self.subTest(run=run):
                self.red(self.make_run(run), self.diag_gap("Makefile"))

    def test_xcodebuild_test_with_the_flag_in_the_makefile_passes(self):
        for run in ("xcodebuild test -scheme X -collect-test-diagnostics never",
                    "xcodebuild test-without-building -scheme X -collect-test-diagnostics never",
                    "xcodebuild -collect-test-diagnostics never -scheme X test",  # the flag before the action
                    "xcodebuild test -scheme X \\\n-collect-test-diagnostics never",  # on a backslash continuation line
                    "sim-test -scheme X",  # sim-test adds the flag itself
                    "xcodebuild build-for-testing -scheme X",  # compiles, runs no test
                    "# xcodebuild test -scheme X"):  # a comment is no run
            with self.subTest(run=run):
                self.diag_pass(self.make_run(run))

    def test_a_flag_in_a_comment_does_not_count(self):
        for run in ("xcodebuild test -scheme X # -collect-test-diagnostics never",
                    "@echo it's slow; xcodebuild test -scheme X # -collect-test-diagnostics never"):  # a lone quote opens no string
            with self.subTest(run=run):
                self.red(self.make_run(run), self.diag_gap("Makefile"))

    def test_a_hash_inside_quotes_does_not_cut_the_flag(self):
        for run in ('xcodebuild test -scheme "a #b" -collect-test-diagnostics never',
                    "xcodebuild test -scheme 'a #b' -collect-test-diagnostics never",
                    'xcodebuild test -scheme "a#b" -collect-test-diagnostics never'):
            with self.subTest(run=run):
                self.diag_pass(self.make_run(run))

    def test_a_tracked_shell_script_is_read(self):
        script = "tools/run-tests.sh"
        self.red(self.gold().write(script, "#!/bin/sh\nset -e\nxcodebuild test -scheme Tally\n"), self.diag_gap(script))
        self.diag_pass(self.gold().write(script, "#!/bin/sh\nxcodebuild test -scheme Tally -collect-test-diagnostics never\n"))
        repo = self.make_run("xcodebuild test -scheme X").write(script, "#!/bin/sh\nxcodebuild test -scheme Tally\n")
        self.red(repo, self.diag_gap("Makefile", script))  # one line, the files in tracked order
        self.diag_pass(self.gold().write("docs/testing.md", "Run `xcodebuild test -scheme Tally` by hand.\n"))  # prose is no run

    def test_workflow_runs_are_read(self):
        flow = ".github/workflows/ios.yml"
        run = "xcodebuild test -project native/Tally.xcodeproj -scheme Tally"
        self.red(self.edit(self.gold(), flow, "run: make app-build", "run: " + run), self.diag_gap(flow))
        for step in ("run: %s -collect-test-diagnostics never" % run,
                     "run: >\n          %s\n          -collect-test-diagnostics never" % run,  # a folded scalar is one command
                     "run: |\n          %s \\\n            -collect-test-diagnostics never" % run):  # a literal block with a continuation
            with self.subTest(step=step):
                _, out = self.edit(self.gold(), flow, "run: make app-build", step).run("ios")  # slow tests is a gap here, by design
                self.assertIn(self.DIAG_PASS, out)
                self.assertNotIn("test diagnostics: gap", out)

    def test_account_ids_in_the_repo_are_red(self):
        repo = self.edit(self.gold(), "tools/ios-ship.json", '"repo_url"', '"team_id": "FAKE000000",\n  "repo_url"')
        self.red(repo, "account ids: partial - tools/ios-ship.json overrides team_id")
        repo = self.edit(self.gold(), "native/project.yml", "CODE_SIGN_STYLE: Automatic", "CODE_SIGN_STYLE: Automatic\n    DEVELOPMENT_TEAM: FAKE000000")
        self.red(repo, "account ids: gap - native/project.yml sets DEVELOPMENT_TEAM")

    def test_review_round_1_bypasses_are_red(self):
        flow = ".github/workflows/ios.yml"
        for new in ("run: xcodebuild test-without-building -scheme Tally", "run: make native-check", "run: make ui-test",
                    "run: cd native && sim-test -scheme Tally"):
            repo = self.edit(self.gold(), flow, "run: make app-build", "run: make app-build\n      - " + new)
            self.red(repo, "slow tests: gap - " + flow)
        repo = self.edit(self.gold(), "native/project.yml", '    SWIFT_VERSION: "6.0"\n', "")
        self.red(repo, "swift 6: gap - native/project.yml: no SWIFT_VERSION")
        repo = self.edit(self.gold(), "native/TallyKit/Package.swift", '.target(name: "TallyKit")',
                         '.target(name: "TallyKit", swiftSettings: [.swiftLanguageMode(.v5)])')
        self.red(repo, "swift 6: gap - native/TallyKit/Package.swift: language mode 5")
        repo = self.edit(self.gold(), flow, "  pull_request:\n    types: [opened, synchronize, reopened, ready_for_review]\n", "")
        self.red(repo, "ci checks: gap - no pull_request workflow")
        repo = self.edit(self.gold(), "Makefile", "\tios-ship install", "\tios-ship testflight")
        self.red(repo, "ship path: gap - Makefile target does not call ios-ship: phone")
        repo = self.edit(self.gold(), "Makefile", "app-build: project", "app-build: project\n\tDEVELOPMENT_TEAM=FAKE000000 true")
        self.red(repo, "account ids: gap - Makefile sets DEVELOPMENT_TEAM")
        repo = self.edit(self.gold(), flow, "runs-on: macos-26", "runs-on: ${{ matrix.os }}\n    strategy:\n      matrix:\n        os: [macos-latest]")
        self.red(repo, "ci runner: gap - .github/workflows/ios.yml: macos-latest")

    def test_review_round_1_false_reds_pass(self):
        flow = ".github/workflows/ios.yml"
        repo = self.edit(self.gold(), flow, "run: make app-build", "run: make app-build | tee test.log")
        repo = self.edit(repo, flow, "runs-on: macos-26", "runs-on: macos-26-xlarge")
        repo = self.edit(repo, "Makefile", "phone:\n\tios-ship install\n", "SHIP := ios-ship\nphone: ; $(SHIP) install\n")
        repo = self.edit(repo, flow, "  macos:\n", "  macos:\n    name: macos-sim-build\n")
        code, out = repo.run("ios")
        self.assertEqual(code, 0, out)

    FLOW = ".github/workflows/ios.yml"
    PROJ = "native/project.yml"
    UNIT = ("  TallyTests:\n    type: bundle.unit-test\n    platform: iOS\n    sources: [TallyTests]\n"
            "    dependencies:\n      - target: Tally\n")  # a hosted unit-test bundle, as XcodeGen writes one

    def grade(self, repo, item):
        """The grade of one item line of the ios group: pass, gap or partial."""
        code, out = repo.run("ios")
        for line in out.splitlines():
            if line.strip().startswith(item + ":"):
                return line.strip().split(": ", 1)[1].split(" - ", 1)[0]
        self.fail("no '%s' line in:\n%s" % (item, out))

    def step(self, repo, command):
        """`repo` with `command` as one more step of the macOS job."""
        return self.edit(repo, self.FLOW, "run: make app-build", "run: make app-build\n      - run: " + command)

    def unit_only(self):
        """The starter with its UI bundle swapped for a unit-test bundle: what a hosted-unit-test repo holds."""
        repo = self.edit(self.gold(), self.PROJ, "TallyUITests", "TallyTests")
        return self.edit(repo, self.PROJ, "bundle.ui-testing", "bundle.unit-test")

    def both(self, scheme=True):
        """The starter plus a unit bundle beside its UI bundle. `scheme`: the scheme's test action runs both."""
        repo = self.edit(self.gold(), self.PROJ, "schemes:\n", self.UNIT + "schemes:\n")
        if scheme:
            repo = self.edit(repo, self.PROJ, "targets: [TallyUITests]", "targets: [TallyTests, TallyUITests]")
        return repo

    # An `xcodebuild ... test` on a pull request is a slow test only when it covers a UI bundle (project.yml
    # `type: bundle.ui-testing`), by its scheme's test targets or by `-only-testing:`. A run that cannot be resolved stays a gap.
    TEST = "xcodebuild test -project native/Tally.xcodeproj -scheme Tally"

    def test_a_unit_bundle_only_run_is_not_a_slow_test(self):
        for command in (self.TEST, "cd native && xcodebuild test -scheme Tally",
                        "xcodebuild test-without-building -project native/Tally.xcodeproj -scheme Tally"):
            with self.subTest(command=command):
                self.assertEqual(self.grade(self.step(self.unit_only(), command), "slow tests"), "pass")

    def test_a_unit_filter_beside_a_ui_bundle_is_not_a_slow_test(self):
        for flag in ("-only-testing:TallyTests", "-only-testing:TallyTests/GreetingTests/testHello"):
            with self.subTest(flag=flag):
                self.assertEqual(self.grade(self.step(self.both(), self.TEST + " " + flag), "slow tests"), "pass")

    def test_a_ui_bundle_in_the_scheme_or_a_ui_filter_is_a_slow_test(self):
        for repo, flag in ((self.both(), ""), (self.gold(), ""),  # the scheme's test action holds the UI bundle
                           (self.both(), "-only-testing:TallyUITests"), (self.both(), "-only-testing:TallyUITests/LaunchTests/testLaunch"),
                           (self.both(), "-only-testing:TallyTests -only-testing:TallyUITests"),
                           (self.both(scheme=False), "-only-testing:TallyUITests")):  # the filter names a UI bundle the scheme lacks
            with self.subTest(flag=flag):
                self.red(self.step(repo, self.TEST + " " + flag), "slow tests: gap - " + self.FLOW)

    def test_a_target_scheme_is_read_by_its_bundle_type(self):
        # XcodeGen makes a scheme named for each target, so `-scheme <bundle>` runs that bundle alone. My reading of the
        # coordinator's "the run covers": the unit bundle passes, the UI bundle is a gap.
        self.assertEqual(self.grade(self.step(self.both(scheme=False), "xcodebuild test -scheme TallyTests"), "slow tests"), "pass")
        self.red(self.step(self.both(scheme=False), "xcodebuild test -scheme TallyUITests"), "slow tests: gap - " + self.FLOW)

    def test_ui_runners_stay_flagged_in_a_unit_only_project(self):
        for command in ("make ui-test", "make native-check", "sim-test -scheme Tally", "cd native && sim-test -scheme Tally"):
            with self.subTest(command=command):
                self.red(self.step(self.unit_only(), command), "slow tests: gap - " + self.FLOW)
        both_runs = self.step(self.step(self.unit_only(), self.TEST), "make ui-test")  # one pass step does not clear a gap step
        self.red(both_runs, "slow tests: gap - " + self.FLOW)

    def test_a_run_that_cannot_be_resolved_keeps_the_gap(self):
        # No false pass: an unknown scheme or target, or no project.yml, could hold a UI bundle. Today each is a gap.
        repo = self.step(self.unit_only(), "xcodebuild test -project native/Tally.xcodeproj -scheme Ghost")
        self.red(repo, "slow tests: gap - " + self.FLOW)
        repo = self.step(self.unit_only(), self.TEST + " -only-testing:Ghost")
        self.red(repo, "slow tests: gap - " + self.FLOW)
        repo = self.step(self.gold(), self.TEST + " -only-testing:TallyTests")  # no such target: a name ending in Tests is no proof
        self.red(repo, "slow tests: gap - " + self.FLOW)
        repo = self.step(self.unit_only(), self.TEST + " -only-testing:TallyTests")  # project.yml gone, a hand-kept project file left
        subprocess.run(["git", "-C", repo.root, "rm", "-q", "--cached", self.PROJ], check=True)
        repo.write("native/Tally.xcodeproj/project.pbxproj", "SWIFT_VERSION = 6.0;\n")
        self.red(repo, "slow tests: gap - " + self.FLOW)

    def test_a_filter_in_a_comment_does_not_narrow_the_run(self):
        repo = self.step(self.both(), self.TEST + "  # -only-testing:TallyTests")
        self.red(repo, "slow tests: gap - " + self.FLOW)

    def test_the_run_line_is_scanned_past_strings_and_lone_quotes(self):
        # Each command sits in a `run: |` block, where YAML reads no comment and the shell reads the quotes.
        block = "|\n          %s"
        quoted = block % (self.TEST + ' -destination "platform=iOS Simulator,name=iPhone #1" -only-testing:TallyTests')  # `#` in a string
        lone = block % ("echo don't stop\n          " + self.TEST + " -only-testing:TallyTests")  # a lone quote in text
        opener = block % ('echo "# not a comment"; ' + self.TEST + " -only-testing:TallyTests")
        for command in (quoted, lone, opener):
            with self.subTest(command=command):
                self.assertEqual(self.grade(self.step(self.both(), command), "slow tests"), "pass")

    def test_a_quoted_command_is_read_inside_its_quotes(self):
        # A YAML-quoted `run:` value and a `bash -c "..."` argument hold a command: it is read as if it were unquoted.
        quoted = ('"xcodebuild test -scheme TallyUITests"', "'xcodebuild test -scheme TallyUITests'",
                  'bash -c "xcodebuild test -scheme TallyUITests"', "sh -c 'xcodebuild test -scheme TallyUITests'",
                  'bash -c "cd native && xcodebuild test -scheme TallyUITests"',
                  '''bash -c "xcodebuild test -scheme TallyUITests -destination 'platform=iOS Simulator,name=iPhone 17'"''')
        for command in quoted:
            with self.subTest(command=command):
                self.red(self.step(self.gold(), command), "slow tests: gap - " + self.FLOW)
        for command in ('"xcodebuild test -scheme Tally -only-testing:TallyTests"', 'bash -c "xcodebuild test -scheme Tally -only-testing:TallyTests"'):
            with self.subTest(command=command):  # the quotes narrow nothing and widen nothing: a unit-only run stays a pass
                self.assertEqual(self.grade(self.step(self.both(), command), "slow tests"), "pass")

    def test_a_lone_apostrophe_in_text_swallows_no_command(self):
        for command in ("echo it's; xcodebuild test -scheme TallyUITests; echo 'ok'", "|\n          echo it's\n          xcodebuild test -scheme TallyUITests"):
            with self.subTest(command=command):
                self.red(self.step(self.gold(), command), "slow tests: gap - " + self.FLOW)

    def test_a_quoted_compile_is_an_app_compile_and_a_quoted_info_call_is_not(self):
        for command in ('"xcodebuild build -scheme Tally"', "'xcodebuild build -scheme Tally'", 'bash -c "xcodebuild build -scheme Tally"',
                        "sh -c 'xcodebuild build -project native/Tally.xcodeproj -scheme Tally'",
                        "echo it's; xcodebuild build -scheme Tally; echo 'ok'"):
            with self.subTest(command=command):
                repo = self.edit(self.gold(), self.FLOW, "run: make app-build", "run: " + command)
                self.assertEqual(self.grade(repo, "ci checks"), "pass")
        for command in ('"xcodebuild -showsdks"', 'bash -c "xcodebuild -showsdks"', "echo it's; xcodebuild -list; echo 'ok'"):
            with self.subTest(command=command):
                repo = self.edit(self.gold(), self.FLOW, "run: make app-build", "run: " + command)
                self.red(repo, "ci checks: gap - no workflow compiles the app")

    SUBSHELL = ("x=$(%s)", "(%s)", "x=`%s`", 'echo "$(%s)"', "x=$( %s )")  # `$(`, `(` and a backtick open a command

    def test_a_command_in_a_subshell_or_backticks_is_read(self):
        for form in self.SUBSHELL:
            command = form % "xcodebuild test -scheme TallyUITests"
            with self.subTest(command=command):
                self.red(self.step(self.gold(), command), "slow tests: gap - " + self.FLOW)
        for form in self.SUBSHELL:  # the open and close marks narrow nothing: a unit-only run stays a pass
            command = form % "xcodebuild test -scheme Tally -only-testing:TallyTests"
            with self.subTest(command=command):
                self.assertEqual(self.grade(self.step(self.both(), command), "slow tests"), "pass")

    def test_a_compile_in_a_subshell_or_backticks_counts_and_an_info_call_there_does_not(self):
        for form in self.SUBSHELL:
            command = form % "xcodebuild build -scheme Tally"
            with self.subTest(command=command):
                repo = self.edit(self.gold(), self.FLOW, "run: make app-build", "run: " + command)
                self.assertEqual(self.grade(repo, "ci checks"), "pass")
        for form in self.SUBSHELL:
            command = form % "xcodebuild -showsdks"
            with self.subTest(command=command):
                repo = self.edit(self.gold(), self.FLOW, "run: make app-build", "run: " + command)
                self.red(repo, "ci checks: gap - no workflow compiles the app")

    @staticmethod
    def paren_destination(quote):
        """A simulator name with parentheses, as Xcode lists an iPad: the marks of a subshell are text in it."""
        return "%splatform=iOS Simulator,name=iPad Pro (12.9-inch) (6th generation)%s" % (quote, quote)

    def test_a_parenthesis_in_an_argument_ends_no_command(self):
        for quote in ("'", '"'):
            dest = self.paren_destination(quote)
            line = "xcodebuild -scheme TallyUITests -destination %s test" % dest  # the action comes after the parentheses
            for command in (line, "|\n          " + line,
                            "|\n          xcodebuild -scheme TallyUITests \\\n            -destination %s \\\n            test" % dest):
                with self.subTest(command=command):
                    self.red(self.step(self.gold(), command), "slow tests: gap - " + self.FLOW)
            command = "xcodebuild test -scheme Tally -destination %s -only-testing:TallyTests" % dest  # a unit filter after them
            with self.subTest(command=command):
                self.assertEqual(self.grade(self.step(self.both(), command), "slow tests"), "pass")

    def test_a_compile_with_a_parenthesis_in_an_argument_counts_and_an_info_call_does_not(self):
        for quote in ("'", '"'):
            dest = self.paren_destination(quote)
            for build in ("xcodebuild -scheme Tally -destination %s build" % dest, "|\n          xcodebuild -scheme Tally -destination %s build" % dest):
                with self.subTest(command=build):
                    repo = self.edit(self.gold(), self.FLOW, "run: make app-build", "run: " + build)
                    self.assertEqual(self.grade(repo, "ci checks"), "pass")
            info = "xcodebuild -destination %s -showsdks" % dest  # the info flag comes after the parentheses
            with self.subTest(command=info):
                repo = self.edit(self.gold(), self.FLOW, "run: make app-build", "run: " + info)
                self.red(repo, "ci checks: gap - no workflow compiles the app")

    def nested_type(self, repo, target):
        """`repo` with the sources of `target` written as a path entry that carries its own `type: folder`."""
        return self.edit(repo, self.PROJ, "sources: [%s]" % target, "sources:\n      - path: %s\n        type: folder" % target)

    def test_a_type_nested_under_a_target_is_not_the_targets_type(self):
        # The UI target's own `type: bundle.ui-testing` stands, whatever `type:` its sources hold below it.
        for command in ("xcodebuild test -scheme TallyUITests", "xcodebuild test -scheme Tally -only-testing:TallyUITests",
                        "xcodebuild test -scheme Tally"):  # the scheme `Tally` lists TallyUITests
            with self.subTest(command=command):
                self.red(self.step(self.nested_type(self.gold(), "TallyUITests"), command), "slow tests: gap - " + self.FLOW)
        # An app target's own type is `application`, so its scheme is no bundle's: with no scheme written, `-scheme Tally` stays unresolved.
        bare = self.step(self.gold(), "xcodebuild test -scheme Tally")
        bare = bare.write(self.PROJ, self.text(bare, self.PROJ).split("schemes:")[0])
        self.red(bare, "slow tests: gap - " + self.FLOW)
        nested = self.nested_type(bare, "Tally")
        self.red(nested, "slow tests: gap - " + self.FLOW)

    def test_an_info_only_xcodebuild_is_not_an_app_compile(self):
        for flags in ("-showsdks", "-list -project native/Tally.xcodeproj", "-showBuildSettings -scheme Tally", "-help", "-version"):
            with self.subTest(flags=flags):
                repo = self.edit(self.gold(), self.FLOW, "run: make app-build", "run: xcodebuild " + flags)
                self.red(repo, "ci checks: gap - no workflow compiles the app")
        repo = self.edit(self.gold(), self.FLOW, "run: make app-build", "run: xcodebuild -showsdks  # xcodebuild build -scheme Tally")
        self.red(repo, "ci checks: gap - no workflow compiles the app")  # a comment is no compile

    def test_a_real_compile_beside_an_info_step_is_an_app_compile(self):
        for command in ("xcodebuild build -project native/Tally.xcodeproj -scheme Tally", "xcodebuild -scheme Tally build", "xcodebuild build",
                        "xcodebuild build-for-testing -scheme Tally", "xcodebuild clean build -scheme Tally",
                        "xcodebuild -showsdks && xcodebuild -scheme Tally build"):
            with self.subTest(command=command):
                repo = self.edit(self.gold(), self.FLOW, "run: make app-build", "run: " + command)
                self.assertEqual(self.grade(repo, "ci checks"), "pass")
        repo = self.edit(self.gold(), self.FLOW, "run: make app-build", "run: xcodebuild -showsdks\n      - run: make app-build")
        self.assertEqual(self.grade(repo, "ci checks"), "pass")  # the info step comes first; the compile after it counts

    def test_repo_config_override_is_partial(self):
        repo = self.edit(self.gold(), "tools/ios-ship.json", '"repo_url"', '"team_id": "FAKE000000",\n  "repo_url"')
        self.red(repo, "account ids: partial - tools/ios-ship.json overrides team_id")

    def test_comments_do_not_count(self):
        repo = self.gold()
        self.edit(repo, ".github/workflows/ios.yml", "    steps:\n      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1\n        with: {persist-credentials: false}",
                  "    # was runs-on: macos-latest, and xcodebuild test ran here\n    steps:\n      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1\n        with: {persist-credentials: false}")
        self.edit(repo, "native/project.yml", "name: Tally", "name: Tally  # not SWIFT_VERSION: 5.0, and no DEVELOPMENT_TEAM: X")
        code, out = repo.run("ios")
        self.assertEqual(code, 0, out)

    def test_account_keys_match_ios_ship(self):
        with open(os.path.join(os.path.dirname(HERE), "bin", "ios-ship"), encoding="utf-8") as handle:
            keys = set(re.findall(r"\bresolve [A-Z_]+ ([a-z_]+)", handle.read()))
        sys.path.insert(0, HERE)
        import compliance_probes
        self.assertEqual(set(compliance_probes.ACCOUNT_KEYS), keys)


class LaneCap(unittest.TestCase):
    def test_guessed_cap_in_a_brief_is_red(self):
        repo = Repo(self).write("briefs/b.md", "Run lanes one or two at a time.\n")
        repo.write(kind_path("plans") + "/p.md", "Keep at most 3 lanes open.\n")
        code, out = repo.run("lanecap")
        self.assertEqual(code, 1, out)
        self.assertIn("briefs/b.md:1", out)
        self.assertIn("p.md:1", out)

    def test_more_cap_forms_are_red(self):
        text = "Keep 3 lanes max.\nRun three lanes in parallel.\nLimit to 2 lanes.\nThe owner left it open; at most 3 lanes.\nWe said \"fine\" and run at most 3 lanes.\nHe wrote \"at most 3 lanes for now\" here.\n"
        code, out = Repo(self).write("docs/brief-x.md", text).run("lanecap")
        self.assertEqual(code, 1, out)
        for line in range(1, 7):
            self.assertIn("guessed cap? docs/brief-x.md:%d:" % line, out)

    def test_owner_named_cited_and_other_files_pass(self):
        repo = Repo(self).write("briefs/b.md", 'Two lanes at a time (owner, 2026-10-12).\nWe dropped "one or two at a time".\n')
        repo.write("specs/todo.md", "One global lane at a time.\n")
        code, out = repo.run("lanecap")
        self.assertEqual(code, 0, out)
        self.assertIn("owner-named, passes: briefs/b.md:1", out)
        self.assertNotIn("b.md:2", out)
        self.assertNotIn("todo.md", out)


PROBES_MD = os.path.join(os.path.dirname(HERE), "skills", "compliance-check", "probes.md")


class Playwright(unittest.TestCase):
    WORKFLOW = ".github/workflows/ci.yml"

    def test_apt_installs_are_red(self):
        wf = self.WORKFLOW
        for rel, text in (
                (wf, "jobs:\n  t:\n    steps:\n      - run: npx playwright install --with-deps chromium\n"),
                (wf, "      - run: npx playwright install-deps chromium\n"),
                (wf, "      - run: |\n          npx playwright install \\\n            --with-deps chromium\n"),
                (wf, "      - run: echo \"a # b\" && npx playwright install --with-deps\n"),
                (wf, "      - name: Don't skip\n        run: npx playwright install --with-deps\n"),
                (wf, "      - run: >\n          npx playwright install\n          --with-deps chromium\n"),
                ("Dockerfile", "RUN npx playwright install --with-deps chromium\n"),
                ("justfile", "e2e:\n    npx playwright install --with-deps\n"),
                ("Taskfile.yml", "tasks:\n  e2e:\n    cmds:\n      - npx playwright install --with-deps\n"),
                (".devcontainer/devcontainer.json", '{"postCreateCommand": "npx playwright install --with-deps"}\n'),
                (".github/actions/web/action.yml", "    - run: npx playwright install --with-deps\n"),
                ("Makefile", "e2e:\n\tnpx playwright install --with-deps\n"),
                ("scripts/ci.sh", "npx playwright install --with-deps chromium\n"),
                ("app/package.json", '{"scripts": {"postinstall": "playwright install --with-deps"}}\n')):
            with self.subTest(rel=rel, text=text):
                code, out = Repo(self).write(rel, text).run("playwright")
                self.assertEqual(code, 1, out)
                self.assertIn("apt install: " + rel, out)

    def test_no_apt_comments_and_other_files_pass(self):
        repo = Repo(self).write(self.WORKFLOW, "      # was: npx playwright install --with-deps\n"
                                               "      - run: npx playwright install chromium  # never --with-deps\n"
                                               "      - run: echo \"don't\"  # playwright install-deps\n"
                                               "      - name: Don't use apt  # playwright install --with-deps\n")
        repo.write(".github/workflows/b.yml", "      - run: >\n          npx playwright install chromium\n"
                                              "      - run: echo done --with-deps\n")
        repo.write("docs/ci.md", "Never run `playwright install --with-deps`.\n")
        code, out = repo.run("playwright")
        self.assertEqual((code, out.strip()), (0, "playwright: in shape - no apt step"))

    def test_no_playwright_is_na(self):
        code, out = Repo(self).write(self.WORKFLOW, "      - run: npm test\n").run("playwright")
        self.assertEqual((code, out.strip()), (0, "playwright: n/a - no Playwright install"))


def load_probes():
    """The probes module under test, loaded here so a case can patch check_glossary in this process."""
    spec = importlib.util.spec_from_file_location("probes_under_test", PROBES)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def in_process(root, group="words", probes=None):
    """(exit code, stdout) of the probes' main on `root`, run in this process. `probes`: a module a case patched."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = (probes or load_probes()).main([group, root])
    return code, out.getvalue()


def head(out):
    return out.partition("\n")[0]


# An item line of the words group: `  <word>: <file>:<line> <detail>`. The word may hold spaces; the line is `-` for a path hit.
ITEM = re.compile(r"^\s+(?:- )?([^:]+?): (\S+?):(\d+|-)(?=\s|$)")
SPARE = {"claim", "try", "gap"}  # names another lane is restoring: no case plants one


def hits(out):
    """(word, file, line) of each item line."""
    return [m.groups() for m in map(ITEM.match, out.splitlines()[1:]) if m]


def planted(prose=False, one_word=False, nth=0):
    """The first "not" name of the live glossary, read on each run, so no case writes one. `prose`
    takes an everyday name, tagged (prose), in place of a retired one. `one_word`: a name of one word, which a
    child term wraps in a prefix. `nth`: the later names of that kind, for a case that needs two."""
    table = check_glossary.rows(check_glossary.read(check_glossary.GLOSSARY))
    found = []
    for _, _, names in table:
        for name in names:
            tagged = name.endswith(check_glossary.THIS_SENSE)
            word = name[:-len(check_glossary.THIS_SENSE)] if tagged else name
            if tagged == prose and word not in SPARE and not (one_word and re.search(r"[\s-]", word)) and word not in found:
                found.append(word)
    if nth >= len(found):
        raise AssertionError("the glossary holds no such name")
    return found[nth]


def dropping(word):
    """check_glossary.rows as it is, with `word` taken out of every "not" cell."""
    real_rows = check_glossary.rows

    def rows(text):
        return [(term, homes, [name for name in names if name != word]) for term, homes, names in real_rows(text)]
    return rows


CHILD_MARK = "<!-- child glossary -->"  # a patched rows() tells the child's file from this repo's by it


def child_glossary(repo, *terms, where="GLOSSARY.md"):
    """`repo` with a glossary of its own domain terms: the same `## Terms` table as this repo's (GLOSSARY.md line 4)."""
    rows = "".join("| %s | A term of this repo. | `README.md` | - |\n" % term for term in terms)
    return repo.write(where, "# Glossary\n\n%s\n\n## Terms\n\n| Term | Meaning | Home | Not |\n|---|---|---|---|\n%s" % (CHILD_MARK, rows))


class Words(unittest.TestCase):
    """The words group reads the glossary's "not" names on each run, and reports each hit in a checked repo."""

    def test_retired_word_in_a_path_is_red(self):
        word = planted()
        path = "docs/%s_notes.md" % word.replace(" ", "_")
        code, out = Repo(self).write(path).run("words")
        self.assertEqual(code, 1, out)
        self.assertTrue(head(out).startswith("words: out"), out)
        self.assertEqual(hits(out), [(word, path, "-")], out)

    def test_retired_word_in_a_rule_anchor_is_red(self):
        word = planted()
        repo = Repo(self).write("src/cap.py", "VALUE = 1\n# Keep to rule:%s-cap.\n" % word.replace(" ", "-"))
        code, out = repo.run("words")
        self.assertEqual(code, 1, out)
        self.assertEqual(hits(out), [(word, "src/cap.py", "2")], out)

    def test_retired_word_in_a_backticked_slug_is_red(self):
        word = planted()
        hyphen = word.replace(" ", "-")
        text = "Intro line.\nSee `%s-cap-rule` for the cap.\nNot `%s` here.\n" % (hyphen, hyphen)
        code, out = Repo(self).write("docs/guide.md", text).run("words")
        self.assertEqual(code, 1, out)
        self.assertEqual(hits(out), [(word, "docs/guide.md", "2")], out)

    def test_everyday_word_as_an_identifier_is_not_read(self):
        # An everyday name is read in a path, an anchor or a slug, never in a code name.
        word = planted(prose=True)
        code_text = "%s = 3\n\n\ndef run(%s):\n    return %s\n" % (word, word, word)
        code, out = Repo(self).write("src/pool.py", code_text).run("words")
        self.assertEqual((code, head(out)), (0, "words: in shape"), out)
        repo = Repo(self).write("src/pool.py", code_text)
        repo.write("docs/guide.md", "See rule:%s-limit.\n" % word)
        code, out = repo.run("words")
        self.assertEqual(hits(out), [(word, "docs/guide.md", "1")], out)

    def test_clean_repo_is_in_shape_and_names_the_glossary_commit(self):
        repo = Repo(self).write("src/app.py", "def main():\n    return 1\n")
        repo.write("docs/guide.md", "A %s in prose is fine.\n" % planted())
        code, out = repo.run("words")
        self.assertEqual((code, head(out)), (0, "words: in shape"), out)
        self.assertEqual(hits(out), [], out)
        glossary_commit = subprocess.run(["git", "-C", check_glossary.ROOT, "rev-parse", "HEAD"],
                                         capture_output=True, text=True, check=True).stdout.strip()
        self.assertIn(glossary_commit[:7], out)

    def test_the_word_list_is_read_from_the_glossary_not_copied(self):
        word = planted()
        path = "docs/%s_notes.md" % word.replace(" ", "_")
        repo = Repo(self).write(path)
        code, out = in_process(repo.root)
        self.assertEqual(code, 1, out)
        self.assertEqual(hits(out), [(word, path, "-")], out)
        with mock.patch.object(check_glossary, "rows", dropping(word)):
            code, out = in_process(repo.root)
        self.assertEqual((code, head(out)), (0, "words: in shape"), out)
        self.assertEqual(hits(out), [], out)

    def test_probe_output_is_a_scorecard_group(self):
        word = planted()
        out = Repo(self).write("docs/%s_notes.md" % word.replace(" ", "_")).run("words")[1]
        group = load_probes().GROUP_LINE.match(head(out))
        self.assertIsNotNone(group, out)
        self.assertEqual(group.group(1, 2), ("words", "out"), out)
        _, body = Scorecard.run_card(self, Repo(self), out)  # the scorecard step, from its one home
        self.assertIn("| words | out |", body)
        self.assertIn("| words: %s | finding |" % word, body)

    def test_unreadable_or_empty_glossary_and_unparsable_python_are_unknown(self):
        root = Repo(self).write("docs/guide.md").root
        for text in (None, "# Glossary\n\nNo table here.\n"):
            with self.subTest(glossary=text), mock.patch.object(check_glossary, "read", return_value=text):
                code, out = in_process(root)
                self.assertEqual(code, 2, out)
                self.assertTrue(head(out).startswith("words: unknown"), out)
        code, out = Repo(self).write("src/broken.py", "def (:\n").run("words")
        self.assertEqual(code, 2, out)
        self.assertTrue(head(out).startswith("words: unknown"), out)

    def test_scanners_respect_strings_comments_and_lone_quotes(self):
        word = planted()
        under = word.replace(" ", "_")
        cases = (
            ("src/app.js", 'const open = "/*";\nconst url = "https://x // y";\nconst %s_count = 2;\n' % under
             + "// the %s note\n" % word, "3"),
            ("src/tpl.js", "const text = `\n/* a block\n`;\nconst %s_total = 3;\n" % under, "4"),
            ("src/view.tsx", "const note = <p>Don't stop</p>;\nconst %s_view = 1;\n" % under, "2"),
        )
        for rel, text, line in cases:
            with self.subTest(rel=rel):
                code, out = Repo(self).write(rel, text).run("words")
                self.assertEqual(hits(out), [(word, rel, line)], out)

    # A repo's own domain words (`block` in an ad blocker, `worker` for a Cloudflare Worker) are spelled in its own
    # GLOSSARY.md. A child term is a spelling that spans a retired word, like a term of this repo's glossary.

    def test_a_child_term_spans_a_retired_word_wherever_a_name_is_read(self):
        for prose in (False, True):  # a retired word, and an everyday word tagged (this sense)
            word = planted(prose, one_word=True)
            kebab = "ad-" + word
            repo = child_glossary(Repo(self), "ad " + word)
            repo.write("src/ad_%s.py" % word).write("src/ad%sList.js" % word.capitalize())  # snake and camel path
            repo.write("docs/guide.md", "See `%s-list-rule` and rule:%s-list.\n" % (kebab, kebab))  # a slug, an anchor
            if not prose:
                repo.write("src/rules.py", "ad_%s = 1\n" % word)  # an identifier: read for a retired word only
            with self.subTest(word=word):
                code, out = repo.run("words")
                self.assertEqual((code, head(out), hits(out)), (0, "words: in shape", []), out)

    def test_the_bare_word_still_hits_beside_a_child_term(self):
        word, other = planted(one_word=True), planted(one_word=True, nth=1)
        repo = child_glossary(Repo(self), "ad " + word)
        repo.write("src/ad_%s.py" % word)  # spanned by the term
        repo.write("src/%s_list.py" % word).write("src/%s_ad_%s.py" % (word, word))  # bare, alone and beside the term
        repo.write("src/ad_%s_%s.py" % (word, other))  # a second retired word is no part of the term
        repo.write("src/rules.py", "ad_%s = 1\n%s_total = 2\n" % (word, word))
        code, out = repo.run("words")
        self.assertEqual(code, 1, out)
        self.assertEqual(sorted(hits(out)), sorted([
            (word, "src/%s_list.py" % word, "-"), (word, "src/%s_ad_%s.py" % (word, word), "-"),
            (other, "src/ad_%s_%s.py" % (word, other), "-"), (word, "src/rules.py", "2")]), out)

    def test_a_child_term_that_is_the_retired_word_is_not_honoured(self):
        for prose in (False, True):
            word = planted(prose, one_word=True)
            for term in (word, word + "s"):  # the bare word, and its plural, which the check reads as the word
                with self.subTest(word=word, term=term):
                    repo = child_glossary(Repo(self), term).write("src/%s_list.py" % term)
                    code, out = repo.run("words")
                    self.assertEqual((code, hits(out)), (1, [(word, "src/%s_list.py" % term, "-")]), out)

    def test_a_child_term_that_repeats_a_claude_settings_term_is_not_honoured(self):
        # This repo's glossary never lets a repo define a term again that it defines. Here it defines `ad <word>` too.
        word = planted(one_word=True)
        term, path = "ad " + word, "src/ad_%s.py" % word
        repo = child_glossary(Repo(self), term).write(path)
        real_rows = check_glossary.rows

        def repeated(text):
            found = real_rows(text)
            return found if CHILD_MARK in text else found + [(term, ["README.md"], [])]
        with mock.patch.object(check_glossary, "rows", repeated):
            code, out = in_process(repo.root)
        self.assertEqual((code, hits(out)), (1, [(word, path, "-")]), out)
        code, out = in_process(repo.root)  # the same child file, with the term this repo's own: honoured
        self.assertEqual((code, hits(out)), (0, []), out)

    def test_no_child_glossary_at_the_root_changes_nothing(self):
        word = planted(one_word=True)
        path = "src/ad_%s.py" % word
        for repo in (Repo(self).write(path), child_glossary(Repo(self).write(path), "ad " + word, where="docs/GLOSSARY.md")):
            code, out = repo.run("words")  # a glossary anywhere but the root is no child glossary
            self.assertEqual((code, hits(out)), (1, [(word, path, "-")]), out)

    def test_registered_in_groups(self):
        probes = load_probes()
        self.assertIn("words", probes.GROUPS)
        self.assertIs(probes.GROUPS["words"], probes.probe_words)


def minified_bundle(word, entries=6000, blobs=160, blob_size=125000):
    """One line of JSON, the shape of a minified data bundle: many small entries, a few long hex blobs, and `word` as
    the last key. Each entry is two names to check (its key and its value); the blobs make the line about 20 MB."""
    entry = ",".join('{"cid":"%016x"}' % (i * 2654435761 % 2 ** 64) for i in range(entries))
    blob = '"%s"' % (("0123456789abcdef" * (blob_size // 16 + 1))[:blob_size])
    return '{"boxes":[%s],"blobs":[%s],"%s_note":1}' % (entry, ",".join([blob] * blobs), word)


class WordsSpeed(unittest.TestCase):
    """The words group on a repo that holds one giant single-line data file, as banchi holds three of 36 to 42 MB under
    demo-assets/mirror/bundle/. check_glossary.code_problems checks the opt-out marker in its `hit()` for every name,
    and scans the whole line each time, so a one-line file costs its length times its names: minutes with no output."""

    BOUND = 30  # seconds, generous: the fixture takes minutes on the quadratic scan and a few seconds once it is linear
    REL = "data/bundle.json"

    def test_a_giant_single_line_file_does_not_stall_the_probe(self):
        word = planted(one_word=True)
        repo = Repo(self).write("src/app.py", "def main():\n    return 1\n").write(self.REL, minified_bundle(word))
        try:
            done = subprocess.run([sys.executable, PROBES, "words", repo.root], capture_output=True, text=True, timeout=self.BOUND)
        except subprocess.TimeoutExpired:
            self.fail("the words group did not finish %s (a 20 MB line, 12,000 names) in %d s" % (self.REL, self.BOUND))
        out = done.stdout
        reported = (word, self.REL, "1") in hits(out)
        stopped = done.returncode == 2 and head(out).startswith("words: unknown")
        declared = any(self.REL in line for line in out.splitlines() if not ITEM.match(line))  # a note line such as `unread:`
        # Reading the file, stopping with an unknown, or saying it was skipped: never "in shape" with the word unread.
        self.assertTrue(reported or stopped or declared, "the file was skipped and the group read it as clear:\n" + out)
        if reported:
            self.assertEqual((done.returncode, head(out)), (1, "words: out"), out)

    def test_a_deadline_ends_the_probe_with_an_unknown_that_names_the_file(self):
        # WORDS_DEADLINE: a module constant of compliance_probes, in seconds, read when probe_words runs.
        probes = load_probes()
        repo = Repo(self)
        for n in range(6):
            repo.write("src/m%d.py" % n, "def f():\n    return %d\n" % n)
        with mock.patch.object(probes, "WORDS_DEADLINE", 1e-6, create=True):
            code, out = in_process(repo.root, probes=probes)
        found = re.fullmatch(r"words: unknown - stopped at (\S+), (\d+) of (\d+) read", head(out))
        self.assertEqual(code, 2, out)
        self.assertIsNotNone(found, out)
        stopped, read, total = found.group(1), int(found.group(2)), int(found.group(3))
        self.assertEqual(total, 6, out)  # M is the tracked files
        self.assertLess(read, total, out)  # N is how many were read before the stop
        self.assertIn(stopped, ["src/m%d.py" % n for n in range(6)], out)
        group = probes.GROUP_LINE.match(head(out))  # a scorecard group line: score unknown, the stop is its gap
        self.assertEqual(group.group(1, 2), ("words", "unknown"), out)
        _, body = Scorecard.run_card(self, Repo(self), out)
        self.assertIn("| words | unknown |", body)

    def test_a_deadline_also_stops_the_probe_inside_one_giant_file(self):
        # Banchi's chunks hold about 100 times the names per byte of the fixture above, so a probe that fixes the line scan and
        # checks its deadline only between files still runs minutes inside one file. The stop must come from inside it.
        repo = Repo(self).write("src/app.py", "def main():\n    return 1\n").write(self.REL, minified_bundle(planted(one_word=True)))
        script = ("import importlib.util, sys\n"
                  "spec = importlib.util.spec_from_file_location('probes_in_child', %r)\n"
                  "probes = importlib.util.module_from_spec(spec)\n"
                  "spec.loader.exec_module(probes)\n"
                  "probes.WORDS_DEADLINE = 0.5\n"
                  "sys.exit(probes.main(['words', %r]))\n") % (PROBES, repo.root)
        try:
            done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            self.fail("a deadline of 0.5 s did not stop the words group inside %s within 20 s" % self.REL)
        self.assertEqual(done.returncode, 2, done.stdout)
        self.assertRegex(head(done.stdout), r"^words: unknown - stopped at %s, \d+ of 2 read$" % re.escape(self.REL))

    def test_the_default_deadline_leaves_a_normal_repo_alone(self):
        code, out = Repo(self).write("src/a.py", "def f():\n    return 1\n").run("words")
        self.assertEqual((code, head(out)), (0, "words: in shape"), out)
        self.assertNotIn("stopped at", out)


class Slugs(unittest.TestCase):
    """The slugs group: the rule fails a slug over 32 characters that a change ADDS against origin/main, in the child's
    own record folders. Old long slugs are a note, never a scored row. A file list given to check_record_slugs.py skips
    git, so it would fail every old slug."""

    OLD = ["b" * 33, "c" * 33, "d" * 33, "e" * 33]  # over 32 characters, in git's sort order

    def child(self, rolled=False):
        """(repo, record folders) of a child clone, its origin/main holding four old long slugs and a short one."""
        repo = Repo(self, origin=True)
        if rolled:
            repo.write(EXTRAS, '{"kinds": {}, "rolled-out": true}')
        folders = layout.folders(repo.root, "record")  # the child's own folders, never this repo's
        for slug in self.OLD:
            repo.write("%s/%s.md" % (folders[0], slug), "# Record\n")
        repo.write("%s/short.md" % folders[0])
        return repo.publish(), folders

    @staticmethod
    def items(out):
        return [line for line in out.splitlines()[1:] if line[:1].isspace()]

    @staticmethod
    def notes(out):
        return [line for line in out.splitlines()[1:] if line.strip() and not line[:1].isspace()]

    def test_old_long_slugs_alone_are_a_note_and_not_a_gap(self):
        repo, folders = self.child()
        repo.branch("work").write("src/a.py").write("%s/%s.md" % (folders[0], self.OLD[0]), "# Record\nedited\n").commit()  # an edit is no add
        code, out = repo.run("slugs")
        self.assertEqual(code, 0, out)
        self.assertTrue(head(out).startswith("slugs: in shape"), out)
        self.assertEqual(self.items(out), [], out)
        notes = self.notes(out)
        self.assertEqual(len(notes), 1, out)  # one line, as the words group's `unread:` line is one
        self.assertRegex(notes[0], r"\b4\b")
        self.assertTrue(all(slug in notes[0] for slug in self.OLD[:3]), notes)
        self.assertNotIn(self.OLD[3], notes[0])  # the first three names only

    def test_a_slug_added_against_origin_main_is_red_and_the_old_ones_are_no_item(self):
        repo, folders = self.child()
        new = "%s/%s.md" % (folders[0], "f" * 33)
        repo.branch("work").write(new).commit()
        code, out = repo.run("slugs")
        self.assertEqual(code, 1, out)
        self.assertTrue(head(out).startswith("slugs: out"), out)
        items = self.items(out)
        self.assertEqual(len(items), 1, out)
        self.assertIn(new, items[0])
        self.assertFalse(any(slug in line for slug in self.OLD for line in items), out)

    def test_a_short_slug_added_and_a_long_name_outside_a_record_folder_pass(self):
        repo, folders = self.child()
        repo.branch("work").write("%s/%s.md" % (folders[0], "s" * 32))  # 32 characters pass
        repo.write("%s/%s.txt" % (folders[0], "t" * 40)).write("src/%s.md" % ("u" * 40)).commit()  # not a record: a .txt, another folder
        code, out = repo.run("slugs")
        self.assertEqual((code, self.items(out)), (0, []), out)
        self.assertTrue(head(out).startswith("slugs: in shape"), out)

    def test_the_childs_own_record_folders_are_read(self):
        # Not rolled out, a child keeps records at decisions/ and debts/; rolled out, under docs/. This repo's layout is rolled out.
        seen = set()
        for rolled in (False, True):
            repo, folders = self.child(rolled)
            seen.add(folders)
            for folder in folders:
                with self.subTest(rolled=rolled, folder=folder):
                    new = "%s/%s.md" % (folder, "g" * 33)
                    repo.branch("work-" + folder.replace("/", "-")).write(new).commit()
                    code, out = repo.run("slugs")
                    self.assertEqual(code, 1, out)
                    self.assertIn(new, "\n".join(self.items(out)))
        self.assertEqual(len(seen), 2, seen)  # the two children hold their records in different folders

    def test_a_child_with_no_origin_main_is_unknown(self):
        # With no base, an added slug cannot be told from an old one: unknown, never in shape.
        repo = Repo(self)
        folder = layout.folders(repo.root, "record")[0]
        repo.write("%s/%s.md" % (folder, self.OLD[0])).commit("base")
        code, out = repo.run("slugs")
        self.assertEqual(code, 2, out)
        self.assertTrue(head(out).startswith("slugs: unknown"), out)

    def test_probe_output_is_a_scorecard_group_and_old_slugs_land_in_the_notes(self):
        repo, folders = self.child()
        new = "%s/%s.md" % (folders[0], "f" * 33)
        out = repo.branch("work").write("src/a.py").commit().run("slugs")[1]
        group = load_probes().GROUP_LINE.match(head(out))  # the scorecard's one reader of a group line
        self.assertIsNotNone(group, out)
        self.assertEqual(group.group(1, 2), ("slugs", "in shape"), out)
        _, body = Scorecard.run_card(self, Repo(self), out)
        rows, _, notes = body.partition("## Notes")
        self.assertIn("| slugs | in shape |", rows)
        self.assertNotIn("| slugs: ", rows)  # no scored row for an old slug
        self.assertTrue(all(slug in notes and slug not in rows for slug in self.OLD[:3]), body)
        out = repo.write(new).commit().run("slugs")[1]  # a new long slug: a scored row, the old ones still notes
        _, body = Scorecard.run_card(self, Repo(self), out)
        rows, _, notes = body.partition("## Notes")
        self.assertIn("| slugs | out |", rows)
        self.assertEqual(len([r for r in rows.splitlines() if r.startswith("| slugs: ") and new in r]), 1, body)
        self.assertTrue(all(slug in notes and slug not in rows for slug in self.OLD[:3]), body)

    def test_registered_in_groups(self):
        self.assertIn("slugs", load_probes().GROUPS)


def live_anchors():
    """The anchors of the live shared rules, read through rule_audit on each call: no case writes one."""
    return rule_audit.claude_md_anchors(rule_audit.rule_text())


class Supersede(unittest.TestCase):
    """A shared rule supersedes a child's text on the same question, unless that text names it as a known exemption."""

    DEPARTS = "The designation is never inherited. A later session re-asks."

    def anchor(self, nth=0):
        return live_anchors()[nth]

    def unlisted(self, anchor):
        """`anchor`, once it is shown not to be a live id, so a case never plants one by luck."""
        self.assertNotIn(anchor, live_anchors())
        return anchor

    def child(self, *paragraphs, rel="CLAUDE.md"):
        """A child repo whose `rel` holds `paragraphs`, a blank line between each. The group reads a paragraph as one
        unit, so a case that wants two units gives two arguments. `starts` gives the line each one begins at."""
        return Repo(self).write(rel, "\n\n".join(paragraphs) + "\n")

    @staticmethod
    def starts(*paragraphs):
        """The first line number of each paragraph in the file `child` writes."""
        first, line = [], 1
        for text in paragraphs:
            first.append(line)
            line += text.count("\n") + 2
        return first

    def test_a_departure_with_no_exemption_is_red(self):
        code, out = self.child(self.DEPARTS).run("supersede")
        self.assertEqual((code, head(out)), (1, "supersede: out - 1 line(s) to read in 1 file(s)"), out)
        self.assertIn("  departs, no exemption: CLAUDE.md:1: " + self.DEPARTS, out.splitlines())

    def test_a_known_exemption_of_a_live_rule_passes(self):
        for nth in (0, 7):  # any live anchor, not the first one
            line = "%s Known exemption: rule:%s" % (self.DEPARTS, self.anchor(nth))
            with self.subTest(anchor=self.anchor(nth)):
                code, out = self.child(line).run("supersede")
                self.assertEqual((code, out.splitlines()), (0, [
                    "supersede: in shape - 1 file(s) read", "  known exemption, passes: CLAUDE.md:1: " + line]), out)

    def test_an_exemption_of_an_unknown_rule_is_red(self):
        fake = self.unlisted("no-such-rule")
        line = "%s Known exemption: rule:%s" % (self.DEPARTS, fake)
        code, out = self.child(line).run("supersede")
        self.assertEqual(code, 1, out)
        self.assertTrue(head(out).startswith("supersede: out - "), out)
        self.assertIn("  unknown exemption rule:%s: CLAUDE.md:1: %s" % (fake, line), out.splitlines())
        self.assertNotIn("known exemption, passes", out)

    def test_a_known_exemption_that_names_no_rule_is_red(self):
        line = "%s Known exemption: the lane owner decides." % self.DEPARTS
        code, out = self.child(line).run("supersede")
        self.assertEqual(code, 1, out)
        self.assertTrue(head(out).startswith("supersede: out - "), out)
        self.assertIn("  unknown exemption rule:?: CLAUDE.md:1: " + line, out.splitlines())
        self.assertNotIn("known exemption, passes", out)

    def test_a_bare_rule_mention_or_an_exemption_in_another_paragraph_still_departs(self):
        live = self.anchor()
        paragraphs = ("%s See rule:%s." % (self.DEPARTS, live),         # a bare mention, no "known exemption"
                      "%s Exemption: rule:%s" % (self.DEPARTS, live),   # "exemption" is not "known exemption"
                      self.DEPARTS,                                     # its exemption sits in the next paragraph
                      "Known exemption: rule:%s" % live)
        first = self.starts(*paragraphs)
        code, out = self.child(*paragraphs).run("supersede")
        self.assertEqual(code, 1, out)
        self.assertTrue(head(out).startswith("supersede: out - "), out)
        self.assertNotIn("known exemption, passes", out)
        for number in first[:3]:
            self.assertEqual(out.count("  departs, no exemption: CLAUDE.md:%d: " % number), 1, out)
        # The paragraph that holds only the exemption departs from nothing, and its rule is live: no flag of either kind.
        flags = [i for i in out.splitlines()[1:] if i.startswith(("  departs", "  unknown exemption"))]
        self.assertEqual([i for i in flags if "CLAUDE.md:%d:" % first[3] in i], [], out)

    def test_lines_that_agree_with_or_quote_a_shared_rule_are_not_flagged(self):
        own = self.unlisted("own-local-rule")
        repo = self.child(
            "We follow the global rule on lane caps: a brief never caps lanes on its own.",
            "The shared review cap applies here as written (rule:%s)." % self.anchor(),
            "Per the claude-settings rule, never merge failing CI. We run it on every pull request.",
            "The roster file is inherited from the parent repo and kept in sync with it.",
            "Unlike the old design, the new tabs hold one screen each.",
            "Use the make target instead of the shell script.",
            "> Solo: the request is a short list of edits with nothing to run in parallel.",
            "Our own gate holds in this repo only. <!-- rule:%s -->" % own)
        code, out = repo.run("supersede")
        self.assertEqual((code, out.splitlines()), (0, ["supersede: in shape - 1 file(s) read"]), out)

    def test_a_child_anchor_of_a_live_rule_is_red(self):
        live, own = self.anchor(), self.unlisted("own-local-rule")
        repo = self.child("Pick the mode from the request. <!-- rule:%s -->" % live,
                          "A rule of our own. <!-- rule:%s -->" % own)
        code, out = repo.run("supersede")
        self.assertEqual(code, 1, out)
        self.assertTrue(head(out).startswith("supersede: out - "), out)
        self.assertEqual(out.splitlines()[1:], ["  redefines rule:%s: CLAUDE.md:1" % live], out)
        other = self.anchor(3)  # every file the group reads, not only CLAUDE.md
        code, out = self.child("<!-- rule:%s -->" % other, rel="AGENTS.md").run("supersede")
        self.assertEqual((code, out.splitlines()[1:]), (1, ["  redefines rule:%s: AGENTS.md:1" % other]), out)

    def test_unreadable_rule_text_or_no_anchors_is_unknown(self):
        # The departure line would be red if the group went on: unknown must come first, as exit 2 and no item.
        root = self.child(self.DEPARTS).root
        real, live_root = rule_audit.rule_text, os.path.realpath(rule_audit.ROOT)

        def broken(text):
            """rule_text as it is for any other root (a child has no rule files), and `text` for the live rules:
            the group may read the live rules once or twice, and the child's root in between, in either order."""
            def rule_text(path=rule_audit.ROOT):
                if os.path.realpath(path) != live_root:
                    return real(path)
                if text is None:
                    raise OSError("no such file")
                return text
            return rule_text
        for name, text in (("unreadable", None), ("empty", ""), ("no anchors", "# Rules\n\nNo anchors here.\n")):
            with self.subTest(rule_text=name), mock.patch.object(rule_audit, "rule_text", broken(text)):
                code, out = in_process(root, "supersede")  # load_probes runs inside the patch, so a `from` import sees it
                self.assertEqual(code, 2, out)
                self.assertTrue(head(out).startswith("supersede: unknown"), out)
                self.assertEqual(out.splitlines()[1:], [], out)

    def test_claude_settings_itself_is_na(self):
        root = os.path.dirname(os.path.dirname(PROBES))  # the root the probes' own rule_audit.ROOT names
        folder = tempfile.mkdtemp(prefix="link-", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, folder, True)
        link = os.path.join(folder, "settings")
        try:
            os.symlink(root, link)
        except (OSError, NotImplementedError):
            link = None  # no symlinks here: the direct path still runs
        for name, where in (("path", root), ("symlink", link)):
            if where is None:
                continue
            with self.subTest(root=name):
                done = subprocess.run([sys.executable, PROBES, "supersede", where], capture_output=True, text=True)
                self.assertEqual((done.returncode, done.stdout.strip()),
                                 (0, "supersede: n/a - this is claude-settings"), done.stderr)

    FORMS = (
        "This repo's review rule is not inherited by its sub-folders.",
        "These briefs override the global lane rule.",
        "This file overrides the shared review rules.",
        "We run a two-round review instead of the parent review rule.",
        "Unlike the claude-settings default, we merge on green.",
        "The shared rules do not apply to this folder.",
        "The global rule does not apply to the docs folder.",
        "THE DESIGNATION IS NEVER INHERITED.",
        "The shared rules do not apply, and the designation is never inherited.",  # two forms, one paragraph: one flag
    )

    def test_each_departure_form_is_flagged_once(self):
        first = self.starts(*self.FORMS)
        code, out = self.child(*self.FORMS).run("supersede")
        self.assertEqual((code, head(out)), (1, "supersede: out - %d line(s) to read in 1 file(s)" % len(self.FORMS)), out)
        for number, line in zip(first, self.FORMS):
            with self.subTest(line=line):
                self.assertEqual(out.count("CLAUDE.md:%d:" % number), 1, out)
                self.assertIn("  departs, no exemption: CLAUDE.md:%d: %s" % (number, line), out.splitlines())

    def test_claude_md_at_any_depth_agents_md_and_claude_markdown_are_read(self):
        where = ("CLAUDE.md", "apps/web/CLAUDE.md", "AGENTS.md", ".claude/rules/style.md", ".claude/agents/deep/lane.md")
        repo = Repo(self)
        for rel in where:
            repo.write(rel, self.DEPARTS + "\n")
        code, out = repo.run("supersede")
        self.assertEqual((code, head(out)), (1, "supersede: out - %d line(s) to read in %d file(s)" % (len(where), len(where))), out)
        for rel in where:
            self.assertIn("  departs, no exemption: %s:1: %s" % (rel, self.DEPARTS), out.splitlines())

    def test_other_files_are_not_read(self):
        repo = self.child("Follow the shared rules.")
        for rel in ("README.md", "docs/guide.md", "src/notes.py", "hooks/guard.py", ".claude/settings.json", ".claude/hooks/run.sh"):
            repo.write(rel, self.DEPARTS + "\n")
        code, out = repo.run("supersede")
        self.assertEqual((code, out.splitlines()), (0, ["supersede: in shape - 1 file(s) read"]), out)

    TECHNICAL = (
        "Run `npx tsc` instead of the global tsc.",
        "A subclass overrides the parent method.",
        "This file overrides the global ESLint config.",
        "Env vars are not inherited by the spawned worker.",
        "Unlike the shared pool, each test gets its own database.",
        # The old wording of three forms above, now narrower: the rule noun or the cue word is missing, or sits in another sentence.
        "This repo's review gate is not inherited by its sub-folders.",
        "These briefs override the global lane cap.",
        "We run a two-round review instead of the parent review cap.",
        "Env vars are not inherited by workers. See the rule list for the full set.",
        # The wider cues of the departure forms below take no more than their rule noun or cue word.
        "Overriding the global ESLint config is fine here.",
        "We overrode the parent method in the subclass.",
        "Env vars aren't inherited by the spawned worker.",
        # A cue and a shared rule in two sentences are no departure: the limit of a one-sentence read.
        "We follow the global rules. Use pnpm instead of npm.",
    )

    def test_technical_prose_with_departure_words_is_not_flagged(self):
        code, out = self.child(*self.TECHNICAL).run("supersede")
        self.assertEqual((code, out.splitlines()), (0, ["supersede: in shape - 1 file(s) read"]), out)

    def test_a_departure_wrapped_across_lines_is_flagged_at_its_first_line(self):
        paragraphs = ("# Rules",
                      "The designation is never\ninherited by a later session.",
                      "We keep our own lane list instead of the\nglobal rule on lane caps.")
        first = self.starts(*paragraphs)
        code, out = self.child(*paragraphs).run("supersede")
        self.assertEqual((code, head(out)), (1, "supersede: out - 2 line(s) to read in 1 file(s)"), out)
        self.assertEqual(out.splitlines()[1:], [
            "  departs, no exemption: CLAUDE.md:%d: The designation is never inherited by a later session." % first[1],
            "  departs, no exemption: CLAUDE.md:%d: We keep our own lane list instead of the global rule on lane caps." % first[2]], out)

    def test_a_known_exemption_wrapped_across_lines_passes(self):
        text = "The designation is never inherited here, a known\nexemption of rule:%s for this folder." % self.anchor()
        first = self.starts("# Rules", text)
        code, out = self.child("# Rules", text).run("supersede")
        self.assertEqual((code, out.splitlines()), (0, [
            "supersede: in shape - 1 file(s) read",
            "  known exemption, passes: CLAUDE.md:%d: %s" % (first[1], text.replace("\n", " ")[:160])]), out)

    def test_known_exemptions_in_the_plural_passes(self):
        line = "%s Known exemptions: rule:%s" % (self.DEPARTS, self.anchor(2))
        code, out = self.child(line).run("supersede")
        self.assertEqual((code, out.splitlines()), (0, [
            "supersede: in shape - 1 file(s) read", "  known exemption, passes: CLAUDE.md:1: " + line]), out)

    def test_a_contracted_do_not_apply_is_a_departure(self):
        paragraphs = ("Global rules don't apply here.", "The shared rule doesn't apply to this folder.")
        first = self.starts(*paragraphs)
        code, out = self.child(*paragraphs).run("supersede")
        self.assertEqual((code, head(out)), (1, "supersede: out - 2 line(s) to read in 1 file(s)"), out)
        for number, text in zip(first, paragraphs):
            self.assertIn("  departs, no exemption: CLAUDE.md:%d: %s" % (number, text), out.splitlines())

    def test_a_fenced_departure_is_not_read(self):
        # The first fence holds a blank line: the fence, not the paragraph break, decides what is read.
        paragraphs = ("# Rules",
                      "```text\nsample output\n\nThe designation is never inherited.\n```",
                      "~~~\nThe shared rules do not apply to this folder.\n~~~",
                      "The designation is never inherited.")
        first = self.starts(*paragraphs)
        code, out = self.child(*paragraphs).run("supersede")
        self.assertEqual((code, head(out)), (1, "supersede: out - 1 line(s) to read in 1 file(s)"), out)
        self.assertEqual(out.splitlines()[1:], ["  departs, no exemption: CLAUDE.md:%d: The designation is never inherited." % first[3]], out)

    def test_a_child_lint_exemption_is_not_ours(self):
        # "known exemption" with no rule id is flagged only beside departure wording: a child's own lint exemption is not ours.
        code, out = self.child("`legacy/` is a known exemption from the no-print check.").run("supersede")
        self.assertEqual((code, out.splitlines()), (0, ["supersede: in shape - 1 file(s) read"]), out)

    def settings_copy(self, drop=(), keep=None, merged=False):
        """A second claude-settings checkout: the rule files of this one at another path, less the anchors in `drop`.
        `keep`: only the first `keep` of them. `merged`: the text of all of them in the first file alone."""
        files = []
        for rel in rule_audit.RULE_FILES:
            with open(os.path.join(rule_audit.ROOT, rel), encoding="utf-8") as handle:
                text = handle.read()
            for anchor in drop:
                text = text.replace("<!-- rule:%s -->" % anchor, "")
            files.append((rel.replace(os.sep, "/"), text))
        if merged:
            files = [(files[0][0], "\n".join(text for _, text in files))]
        repo = Repo(self)
        for rel, text in files[:keep]:
            repo.write(rel, text)
        return repo

    def test_a_second_claude_settings_checkout_is_na(self):
        every = list(dict.fromkeys(live_anchors()))
        # Rule files all present, and nearly all the live anchors: the copy may lag a little behind this checkout.
        for name, drop in (("same anchors", []), ("one anchor less", every[5:6]), ("5% less", every[:len(every) // 20])):
            repo = self.settings_copy(drop=drop)
            with self.subTest(copy=name):
                held = set(rule_audit.claude_md_anchors(rule_audit.rule_text(repo.root)))
                self.assertEqual(len(held), len(every) - len(drop))  # the fixture holds what the case says
                code, out = repo.run("supersede")
                self.assertEqual((code, out.strip()), (0, "supersede: n/a - this is claude-settings"), out)

    def test_a_copy_with_too_few_anchors_or_a_missing_rule_file_is_read_as_a_child(self):
        every = list(dict.fromkeys(live_anchors()))
        cases = (("30% of the anchors less", self.settings_copy(drop=every[:len(every) * 3 // 10])),
                 ("the first rule file alone", self.settings_copy(keep=1)),
                 # All the anchors, but not in the rule files: the second path is missing.
                 ("all the anchors in one file", self.settings_copy(merged=True)))
        for name, repo in cases:
            with self.subTest(copy=name):
                code, out = repo.run("supersede")
                self.assertEqual(code, 1, out)
                self.assertTrue(head(out).startswith("supersede: out - "), out)

    def test_a_file_reached_twice_is_read_once(self):
        repo = self.child(self.DEPARTS)
        try:
            os.symlink("CLAUDE.md", os.path.join(repo.root, "AGENTS.md"))
        except (OSError, NotImplementedError):
            self.skipTest("no symlinks here")
        subprocess.run(["git", "-C", repo.root, "add", "-f", "AGENTS.md"], check=True)
        code, out = repo.run("supersede")
        self.assertEqual(code, 1, out)
        self.assertRegex(head(out), r"^supersede: out - 1 line\(s\) to read in \d+ file\(s\)$")
        items = out.splitlines()[1:]
        self.assertEqual(len(items), 1, out)
        self.assertRegex(items[0], r"^  departs, no exemption: (CLAUDE|AGENTS)\.md:1: " + re.escape(self.DEPARTS) + "$")

    def test_skill_md_names_supersede_among_the_groups_that_list_items(self):
        with open(os.path.join(os.path.dirname(HERE), "skills", "compliance-check", "SKILL.md"), encoding="utf-8") as handle:
            text = handle.read()
        found = re.search(r"([^.]*?)\blist each item under the\s+group line", text)
        self.assertIsNotNone(found, "SKILL.md no longer says which groups list each item")
        self.assertIn("Supersede", found.group(1))

    def test_each_list_item_is_its_own_unit(self):
        # Joined into one paragraph, the two bullets would read "global rules ... instead of": a cue and a shared rule.
        for marker in ("-", "*", "+", "1.", "1)", "  -"):
            with self.subTest(marker=marker):
                text = "%s Follow the global rules\n%s Use pnpm instead of npm\n" % (marker, marker)
                code, out = Repo(self).write("CLAUDE.md", text).run("supersede")
                self.assertEqual((code, out.splitlines()), (0, ["supersede: in shape - 1 file(s) read"]), out)

    def test_an_exemption_in_one_bullet_does_not_pass_another(self):
        for marker in ("-", "*", "+", "1.", "1)"):
            text = "%s The designation is never inherited here.\n%s Known exemption of rule:%s: the lane owner decides.\n" % (
                marker, marker, self.anchor())
            with self.subTest(marker=marker):
                code, out = Repo(self).write("CLAUDE.md", text).run("supersede")
                self.assertEqual((code, head(out)), (1, "supersede: out - 1 line(s) to read in 1 file(s)"), out)
                items = out.splitlines()[1:]
                self.assertEqual(len(items), 1, out)
                self.assertRegex(items[0], r"^  departs, no exemption: CLAUDE\.md:1: .*The designation is never inherited here\.$")
                self.assertNotIn("known exemption, passes", out)

    def test_a_departure_in_a_later_bullet_reports_its_own_line(self):
        bullets = ["- Item %d is fine." % number for number in range(1, 11)]
        bullets[7] = "- The designation is never inherited here."
        code, out = Repo(self).write("CLAUDE.md", "\n".join(bullets) + "\n").run("supersede")
        self.assertEqual((code, head(out)), (1, "supersede: out - 1 line(s) to read in 1 file(s)"), out)
        self.assertRegex(out.splitlines()[1], r"^  departs, no exemption: CLAUDE\.md:8: ")
        # A list that follows a line with no blank between: the bullet starts its own unit, at its own line.
        text = "Rules for sessions:\n- Keep notes short.\n- The designation is never\n  inherited by a later session.\n- Use pnpm.\n"
        code, out = Repo(self).write("CLAUDE.md", text).run("supersede")
        self.assertEqual(code, 1, out)
        self.assertEqual(len(out.splitlines()), 2, out)
        self.assertRegex(out.splitlines()[1], r"^  departs, no exemption: CLAUDE\.md:3: .*never\s+inherited by a later session\.$")

    def test_each_table_row_is_its_own_unit(self):
        head_rows = "| Rule | Note |\n| --- | --- |\n"
        text = head_rows + "| Follow the global rules | ok |\n| Use pnpm instead of npm | ok |\n"
        code, out = Repo(self).write("CLAUDE.md", text).run("supersede")
        self.assertEqual((code, out.splitlines()), (0, ["supersede: in shape - 1 file(s) read"]), out)
        text = head_rows + "| The designation is never inherited | here |\n| Use pnpm | ok |\n"
        code, out = Repo(self).write("CLAUDE.md", text).run("supersede")
        self.assertEqual(code, 1, out)
        self.assertEqual(len(out.splitlines()), 2, out)
        self.assertRegex(out.splitlines()[1], r"^  departs, no exemption: CLAUDE\.md:3: ")

    def test_a_heading_is_its_own_unit(self):
        text = "## Global rules\nUse pnpm instead of npm in scripts.\n"
        code, out = Repo(self).write("CLAUDE.md", text).run("supersede")
        self.assertEqual((code, out.splitlines()), (0, ["supersede: in shape - 1 file(s) read"]), out)
        code, out = Repo(self).write("CLAUDE.md", "# Rules\nThe designation is never inherited.\n").run("supersede")
        self.assertEqual(code, 1, out)
        self.assertEqual(out.splitlines()[1:], ["  departs, no exemption: CLAUDE.md:2: The designation is never inherited."], out)
        # A heading right after a line of text, with no blank between, is a unit of its own too.
        code, out = Repo(self).write("CLAUDE.md", "Use pnpm instead of npm\n## Global rules\n").run("supersede")
        self.assertEqual((code, out.splitlines()), (0, ["supersede: in shape - 1 file(s) read"]), out)
        code, out = Repo(self).write("CLAUDE.md", "Intro.\n\n## The designation is never inherited\n").run("supersede")
        self.assertEqual(code, 1, out)
        self.assertEqual(out.splitlines()[1:], ["  departs, no exemption: CLAUDE.md:3: ## The designation is never inherited"], out)

    def test_a_fence_left_open_at_the_end_of_the_file_is_unknown(self):
        for marker, rel in (("```", "CLAUDE.md"), ("~~~", ".claude/rules/style.md")):
            paragraphs = ("# Rules", "Intro.", "%ssh\nThe designation is never inherited." % marker)
            first = self.starts(*paragraphs)
            with self.subTest(marker=marker):
                code, out = self.child(*paragraphs, rel=rel).run("supersede")
                self.assertEqual(code, 2, out)
                self.assertTrue(head(out).startswith("supersede: unknown"), out)
                # The file and the line of the fence that never closed.
                self.assertRegex(head(out), re.escape(rel) + r"\D{1,24}" + str(first[2]) + r"\b")
                self.assertNotIn("departs", out)

    def test_backticks_that_close_on_the_same_line_open_no_fence(self):
        paragraphs = ("```x``` is code.", "The designation is never inherited.")
        first = self.starts(*paragraphs)
        code, out = self.child(*paragraphs).run("supersede")
        self.assertEqual((code, head(out)), (1, "supersede: out - 1 line(s) to read in 1 file(s)"), out)
        self.assertEqual(out.splitlines()[1:], ["  departs, no exemption: CLAUDE.md:%d: The designation is never inherited." % first[1]], out)
        # The next line, with no blank between: one paragraph or two, the departure is read.
        code, out = Repo(self).write("CLAUDE.md", "```x``` is code.\nThe designation is never inherited.\n").run("supersede")
        self.assertEqual(code, 1, out)
        self.assertEqual(len(out.splitlines()), 2, out)
        self.assertRegex(out.splitlines()[1], r"^  departs, no exemption: CLAUDE\.md:[12]: ")

    def test_overriding_overrode_and_a_contracted_not_inherited_are_departures(self):
        paragraphs = ("Overriding the global rule on lane caps is how we run here.",
                      "We overrode the global rule on lane caps last week.",
                      "The designation isn't inherited by a later session.",
                      "Tier assignments aren't inherited by sub-folders.")
        first = self.starts(*paragraphs)
        code, out = self.child(*paragraphs).run("supersede")
        self.assertEqual((code, head(out)), (1, "supersede: out - %d line(s) to read in 1 file(s)" % len(paragraphs)), out)
        for number, text in zip(first, paragraphs):
            self.assertIn("  departs, no exemption: CLAUDE.md:%d: %s" % (number, text), out.splitlines())

    def test_the_docs_say_paragraph_or_list_item_and_never_the_same_line(self):
        record = os.path.join(os.path.dirname(HERE), *kind_path("decisions").split("/"), "compliance-defined.md")
        with open(record, encoding="utf-8") as handle:
            record_text = handle.read()
        with open(PROBES_MD, encoding="utf-8") as handle:
            probes_text = handle.read()
        section = re.search(r"(?ms)^## Supersede\n.*?(?=^## |\Z)", probes_text)
        self.assertIsNotNone(section, "probes.md has no Supersede section")
        paragraph = re.search(r"(?ms)^supersede: .*?(?=^\w+: |\Z)", load_probes().__doc__)
        self.assertIsNotNone(paragraph)
        # The check reads a unit, a paragraph or a list item, so no doc says it reads "the line" of an exemption.
        for name, text in (("the record", record_text), ("probes.md", probes_text), ("the docstring", paragraph.group(0))):
            with self.subTest(doc=name):
                self.assertNotRegex(text, r"(?i)\b(same|its) line\b")
        for name, text in (("the record", record_text), ("probes.md", section.group(0)), ("the docstring", paragraph.group(0))):
            with self.subTest(doc=name):
                self.assertIn("list item", text)

    def test_the_record_names_the_one_sentence_limit_under_not_mechanized(self):
        record = os.path.join(os.path.dirname(HERE), *kind_path("decisions").split("/"), "compliance-defined.md")
        with open(record, encoding="utf-8") as handle:
            text = handle.read()
        section = re.search(r"(?ms)^## Not mechanized\n.*?(?=^## |\Z)", text)
        self.assertIsNotNone(section, "the record has no Not mechanized section")
        self.assertIn("sentence", section.group(0))

    def test_a_long_paragraph_is_cut_to_160_characters(self):
        line = self.DEPARTS + " " + "a" * 200
        code, out = self.child(line).run("supersede")
        self.assertEqual(code, 1, out)
        self.assertEqual(out.splitlines()[1:], ["  departs, no exemption: CLAUDE.md:1: " + line[:160]], out)
        # A wrapped paragraph is cut after its lines are joined, and reports the line it starts at.
        wrapped = self.DEPARTS + "\n" + "a" * 200
        code, out = self.child("# Rules", wrapped).run("supersede")
        self.assertEqual(out.splitlines()[1:], ["  departs, no exemption: CLAUDE.md:3: " + line[:160]], out)

    def test_comment_openers_and_lone_quotes_in_text_hide_nothing(self):
        # building-scanner-respects-strings: no opener, quote or backtick in a paragraph reaches the next paragraph,
        # and a triple backtick in the middle of a line opens no fence.
        live = self.anchor()
        paragraphs = ("Issue #12 is closed. The designation is never inherited.",
                      "Open the /* block, then: the designation is never inherited.",
                      "See https://example.com/a // the designation is never inherited.",
                      "Don't re-ask: the designation is never inherited.",
                      'A lone " quote, and the designation is never inherited.',
                      "A lone ` tick, and the designation is never inherited.",
                      "Write ``` to start a fence in Markdown.",
                      "Don't",
                      "The designation is never inherited.",
                      "Don't stop here;\nthe designation is never inherited.",  # a lone quote, then a wrapped departure
                      "Don't pick alone. <!-- rule:%s -->" % live)
        first = self.starts(*paragraphs)
        code, out = self.child(*paragraphs).run("supersede")
        self.assertEqual(code, 1, out)
        items = out.splitlines()[1:]
        for index in (0, 1, 2, 3, 4, 5, 8, 9):
            self.assertIn("  departs, no exemption: CLAUDE.md:%d: %s" % (first[index], paragraphs[index].replace("\n", " ")), items)
        self.assertIn("  redefines rule:%s: CLAUDE.md:%d" % (live, first[10]), items)
        self.assertEqual(len(items), 9, out)  # eight departures and one anchor: the fence-like and lone-quote paragraphs add none

    def test_probe_output_is_a_scorecard_group(self):
        live = self.anchor()
        out = self.child(self.DEPARTS, "Pick alone. <!-- rule:%s -->" % live).run("supersede")[1]
        group = load_probes().GROUP_LINE.match(head(out))
        self.assertIsNotNone(group, out)
        self.assertEqual(group.group(1, 2), ("supersede", "out"), out)
        _, body = Scorecard.run_card(self, Repo(self), out)  # the scorecard step, from its one home
        self.assertIn("| supersede | out |", body)
        self.assertIn("| supersede: departs, no exemption | finding |", body)
        self.assertIn("| supersede: redefines rule:%s | finding |" % live, body)

    def test_registered_in_groups(self):
        probes = load_probes()
        self.assertIn("supersede", probes.GROUPS)

    def test_the_docstring_names_the_group_and_each_group_has_a_usage_line(self):
        probes = load_probes()
        doc = probes.__doc__
        self.assertRegex(doc, r"compliance_probes\.py supersede\s+<child root>")
        paragraph = re.search(r"(?ms)^supersede: .*?(?=^\w+: |\Z)", doc)
        self.assertIsNotNone(paragraph, doc)
        # The owner's typed prompt is the glossary's `override`: the group's own word for what it finds is "departure".
        self.assertIn("departure wording", paragraph.group(0))
        self.assertNotIn("override wording", paragraph.group(0))
        for group in probes.GROUPS:
            self.assertIn("compliance_probes.py %s" % group, doc, group)


class ProbesText(unittest.TestCase):
    """probes.md commands, as a session copies them into a shell."""

    def text(self):
        with open(PROBES_MD, encoding="utf-8") as handle:
            return handle.read()

    def test_the_slugs_row_runs_the_slugs_group_and_gives_the_lint_no_record_files(self):
        text = self.text()
        self.assertIn("compliance_probes.py slugs", text)
        git_rows = [line for line in text.splitlines() if line.startswith("| Git |") and "slug" in line]
        self.assertTrue(git_rows and all("compliance_probes.py slugs" in row for row in git_rows), git_rows)
        # A file list makes check_record_slugs.py skip git, so it fails every old slug.
        self.assertEqual(re.findall(r"check_record_slugs\.py[^\n|]*\*\.md", text), [])

    def test_probes_fall_back_to_python(self):
        text = self.text()
        self.assertIn("PY=$(command -v python3 || command -v python)", text)
        self.assertNotRegex(text, r"\bpython3? \$P/")

    def test_cite_probe_finds_each_id_form(self):
        # Each pattern is unescaped as a shell does in double quotes, then run through grep.
        row = next(line for line in self.text().splitlines() if line.startswith("| Speak plainly |"))
        first = row.split("finds numbered")[0]
        patterns = re.findall(r'-e "([^"]+)"', first)
        self.assertTrue(patterns, row)
        args = ["grep", "-cE"] + [x for p in patterns for x in ("-e", re.sub(r'\\([`"$\\])', r"\1", p))]
        for line in ("See D12.", "See D-570.", "Decision draft-until-reviewed holds.", "See D`one-layout-every-repo`.",
                     "See D `one-layout-every-repo`."):
            done = subprocess.run(args, input=line + "\n", capture_output=True, text=True)
            self.assertEqual(done.stdout.strip(), "1", line)
        done = subprocess.run(args, input="Deploy `one-layout` today.\n", capture_output=True, text=True)
        self.assertEqual(done.stdout.strip(), "0")


class Scorecard(unittest.TestCase):
    LINES = ("Layout: out - 1 folder (lint/compliance_probes.py layout)\n"
             "Design: in shape - one token file (lint/compliance_probes.py design)\n")

    def run_card(self, repo, text):
        done = subprocess.run([sys.executable, PROBES, "scorecard", repo.root], input=text, capture_output=True, text=True)
        path = os.path.join(repo.root, "docs", "health", "compliance.md")
        body = None
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                body = handle.read()
        return done.returncode, body

    def test_writes_one_table_with_a_gold_column(self):
        code, body = self.run_card(Repo(self), self.LINES)
        self.assertEqual(code, 0)
        self.assertIsNotNone(body)
        self.assertIn("| Group | Score | Gold standard | Gap | Source |", body)
        self.assertIn("| Layout | out | in shape | 1 folder | lint/compliance_probes.py layout |", body)
        self.assertIn("| Design | in shape | in shape | one token file | lint/compliance_probes.py design |", body)

    def test_writes_to_the_path_the_layout_kind_names(self):
        repo = Repo(self)
        done = subprocess.run([sys.executable, PROBES, "scorecard", repo.root], input=self.LINES, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(layout.path(repo.root, "scorecard"), kind_path("scorecard"))
        self.assertTrue(os.path.isfile(os.path.join(repo.root, *kind_path("scorecard").split("/"))))
        self.assertIn("wrote " + kind_path("scorecard") + " ", done.stdout)

    def test_second_run_overwrites_and_leaves_one_file(self):
        repo = Repo(self)
        self.run_card(repo, self.LINES)
        code, body = self.run_card(repo, "Layout: in shape - clean (command)\n")
        self.assertEqual(code, 0)
        self.assertIn("| Layout | in shape |", body)
        self.assertNotIn("| Design |", body)
        self.assertEqual(os.listdir(os.path.join(repo.root, "docs", "health")), ["compliance.md"])

    def test_same_input_gives_the_same_file(self):
        repo = Repo(self)
        self.run_card(repo, self.LINES)
        first = self.run_card(repo, self.LINES)[1]
        self.assertEqual(first, self.run_card(repo, self.LINES)[1])

    def test_item_line_becomes_a_row_after_its_group(self):
        text = "Design: partial - two gaps (a)\n  - screens: gap - no config (b)\n  - sizes: pass - ok\nLayout: in shape - ok (c)\n"
        _, body = self.run_card(Repo(self), text)
        rows = [line for line in body.splitlines() if line.startswith("| ")]
        at = rows.index("| Design | partial | in shape | two gaps | a |")
        self.assertEqual(rows[at + 1], "| Design: screens | gap | in shape | no config | b |", body)
        self.assertEqual(rows[at + 2], "| Design: sizes | pass | in shape | ok | none cited |", body)
        self.assertNotIn("## Notes", body)

    def test_skill_order_items_stay_under_their_lower_case_group(self):
        text = "layout: partial - x (a:1)\n  - extras: gap - none (f)\ndesign: out - bad (c)\n"
        _, body = self.run_card(Repo(self), text)
        rows = [line for line in body.splitlines() if line.startswith("| ")]
        at = rows.index("| layout | partial | in shape | x | a:1 |")
        self.assertEqual(rows[at + 1], "| layout: extras | gap | in shape | none | f |", body)
        self.assertNotIn("design: extras", body)
        self.assertEqual(rows[at + 2], "| design | out | in shape | bad | c |", body)

    def test_probe_output_files_its_items_under_its_own_group(self):
        repo = Repo(self).write("src/a.py")
        out = repo.run("layout")[1]
        self.assertTrue(out.startswith("layout: "), out)
        _, body = self.run_card(Repo(self), out + "design: in shape - ok (c)\n")
        rows = [line for line in body.splitlines() if line.startswith("| ")]
        names = [r.split(" | ")[0] for r in rows]
        self.assertTrue(any(n.startswith("| layout: ") for n in names), body)
        self.assertEqual([n for n in names if n.startswith("| design: ")], [], body)

    def test_every_probe_item_line_becomes_a_row_after_its_group(self):
        # Real probe output: each probe prints its group line, then its item lines.
        repo = Repo(self).write("src/App.tsx").write("src/tokens.css").write("Makefile", "screenshot:\n\tnode s.mjs\n")
        repo.write("briefs/b.md", "Run lanes one or two at a time.\nTwo lanes at a time (owner, 2026-10-12).\n")
        repo.write(".github/workflows/ci.yml", "      - run: npx playwright install --with-deps chromium\n")
        ios = Ios.gold(self)
        flow = os.path.join(ios.root, ".github", "workflows", "ios.yml")
        with open(flow, encoding="utf-8") as handle:
            ios.write(".github/workflows/ios.yml", handle.read().replace("runs-on: macos-26", "runs-on: macos-latest"))
        outs = [r.run(g)[1] for r, g in ((repo, "layout"), (repo, "design"), (repo, "lanecap"), (repo, "playwright"), (ios, "ios"))]
        _, body = self.run_card(Repo(self), "".join(outs))
        rows = [line for line in body.splitlines() if line.startswith("| ")]
        grades = set()
        for out in outs:
            lines = out.rstrip("\n").split("\n")
            items, group = lines[1:], lines[0].split(": ", 1)[0]
            self.assertTrue(items and all(i.startswith("  ") for i in items), out)
            at = [n for n, row in enumerate(rows) if row.startswith("| %s | " % group)]
            self.assertEqual(len(at), 1, body)
            for n, line in enumerate(items, at[0] + 1):
                name, rest = line.strip().split(": ", 1)
                self.assertTrue(rows[n].startswith("| %s: %s | " % (group, name)), (line, body))
                grades.add(rest.split(" - ", 1)[0] if " - " in rest else None)
        self.assertTrue({"pass", "gap", "partial", "known gap", None} <= grades, grades)
        self.assertNotIn("## Notes", body)

    def test_other_lines_are_kept_as_notes(self):
        out, body = self.run_card(Repo(self), "Layout: in shape - ok (c)\nCaution: rule x has no probe\n\n")
        self.assertIn("## Notes", body)
        self.assertIn("- Caution: rule x has no probe", body)
        self.assertEqual(body.count("rule x has no probe"), 1)

    def test_sourceless_line_says_none_cited(self):
        _, body = self.run_card(Repo(self), "Layout: out - no source here\n")
        self.assertIn("| Layout | out | in shape | no source here | none cited |", body)

    def test_pipe_is_escaped_and_dash_and_parens_survive(self):
        _, body = self.run_card(Repo(self), "Layout: out - a | b - c (d) e (src)\n")
        self.assertIn("| Layout | out | in shape | a \\| b - c (d) e | src |", body)

    def test_ui_file_gap_is_a_known_gap_row(self):
        _, body = self.run_card(Repo(self), self.LINES)
        row = next(line for line in body.splitlines() if line.startswith("| STE lint on UI files |"))
        self.assertIn("| partial | in shape |", row)
        self.assertIn("known gap", row)


def listing(folder):
    """Every path under `folder`, relative, so a case sees a file or folder a probe made."""
    return sorted(os.path.relpath(os.path.join(base, name), folder)
                  for base, dirs, files in os.walk(folder) for name in dirs + files)


class BadRoot(unittest.TestCase):
    """A root that is an option, or is no folder, is refused with the usage line and exit 2, for every group, and nothing
    is written: the scorecard group would otherwise write `--help/docs/health/compliance.md` under the cwd."""

    def refused(self, group, root, folder):
        before = listing(folder)
        done = subprocess.run([sys.executable, PROBES, group, root], cwd=folder, input="", capture_output=True, text=True)
        self.assertEqual(done.returncode, 2, (group, root, done.stdout, done.stderr))
        self.assertIn("usage:", done.stderr, (group, root))
        self.assertEqual(listing(folder), before, "%s %s made a file or folder" % (group, root))

    def test_each_group_refuses_an_option_a_missing_folder_and_a_file(self):
        for group in load_probes().GROUPS:
            folder = tempfile.mkdtemp(prefix="badroot-", dir=RUN_FOLDER)
            self.addCleanup(shutil.rmtree, folder, True)
            os.makedirs(os.path.join(folder, "-x"))  # a real folder whose name starts with `-`: still read as an option
            with open(os.path.join(folder, "a.txt"), "w", encoding="utf-8") as handle:
                handle.write("x\n")
            for root in ("--help", "-h", "-x", "no-such-folder", "a.txt"):
                with self.subTest(group=group, root=root):
                    self.refused(group, root, folder)

    def test_a_folder_given_as_dot_or_dot_slash_name_is_still_read(self):
        # The refusal must not catch the way probes.md passes a root (`.`) or a folder whose name starts with `-`.
        repo = Repo(self).write("src/a.py")
        folder = os.path.join(repo.root, "-x")
        os.makedirs(folder)
        subprocess.run(["git", "init", "-q", folder], check=True)
        for cwd, root in ((repo.root, "."), (repo.root, "./-x")):
            with self.subTest(root=root):
                done = subprocess.run([sys.executable, PROBES, "layout", root], cwd=cwd, capture_output=True, text=True)
                self.assertTrue(done.stdout.startswith("layout: "), (done.stdout, done.stderr))
                self.assertNotIn("usage:", done.stderr)
                self.assertIn(done.returncode, (0, 1), done.stdout)


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
