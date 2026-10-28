#!/usr/bin/env python3
"""Cases for lint/compliance_probes.py, on fixture git repos. Standard library only.

    python3 lint/test_compliance_probes.py

Each group goes red on the gap it guards, and stays quiet on a repo that is fine: a tool's own
folder, a vendored screenshot script, a generated token file, a cited cap and an owner-named cap.
PROBES_UNDER_TEST names the script under test (default: the one beside this file).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROBES = os.path.abspath(os.environ.get("PROBES_UNDER_TEST") or os.path.join(HERE, "compliance_probes.py"))
sys.path.insert(0, HERE)
import layout  # noqa: E402

EXTRAS = layout.layout()["extras"]


def kind_path(name):
    return layout.layout()["kinds"][name]["path"]


class Repo:
    def __init__(self, test):
        self.root = tempfile.mkdtemp(prefix="probes-")
        test.addCleanup(shutil.rmtree, self.root, True)
        subprocess.run(["git", "init", "-q", self.root], check=True)

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
        root = tempfile.mkdtemp(prefix="probes-")
        self.addCleanup(shutil.rmtree, root, True)
        done = subprocess.run([sys.executable, PROBES, "layout", root], capture_output=True, text=True)
        self.assertEqual(done.returncode, 2, done.stdout)
        self.assertIn("layout: unknown", done.stdout)


SHOOT = '{"baseUrl": "http://localhost:5173", "routes": ["/", "/b"]}'


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

    def test_a_config_shoot_refuses_is_a_gap(self):
        for bad in ('{"routes": ["/"]}', '{"baseUrl": "http://h", "routes": ["/"], "sizes": "x"}',
                    '{"baseUrl": "http://h", "routes": ["/"], "themes": ["sepia"]}', '{"baseUrl": "http://h", "routes": []}'):
            code, out = Repo(self).write("a.tsx").write(".claude/shoot.json", bad).write("tokens.css").run("design")
            self.assertEqual(code, 1, bad)
            self.assertIn("screens named: gap", out)
            self.assertIn("screenshot command: gap", out)
            self.assertNotIn(": pass - the shared shoot", out)

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

    def test_the_starter_tree_is_in_shape(self):
        code, out = self.gold().run("ios")
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("ios: in shape"), out)
        self.assertEqual(out.count(": pass"), 9, out)

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


class ProbesText(unittest.TestCase):
    """probes.md commands, as a session copies them into a shell."""

    def text(self):
        with open(PROBES_MD, encoding="utf-8") as handle:
            return handle.read()

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


if __name__ == "__main__":
    unittest.main()
