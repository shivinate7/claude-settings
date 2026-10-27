#!/usr/bin/env python3
"""Cases for lint/compliance_probes.py, on fixture git repos. Standard library only.

    python3 lint/test_compliance_probes.py

Each group goes red on the gap it guards, and stays quiet on a repo that is fine: a tool's own
folder, a vendored screenshot script, a generated token file, a cited cap and an owner-named cap.
PROBES_UNDER_TEST names the script under test (default: the one beside this file).
"""
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
        repo = Repo(self).write(EXTRAS, '{"kinds": {}}').write("src/a.py").write("CLAUDE.md")
        code, out = repo.run("layout")
        self.assertEqual(code, 1, out)
        self.assertIn("folder src/: neither", out)
        self.assertIn("missing core kind decisions: " + kind_path("decisions"), out)
        self.assertNotIn("missing core kind claude-md", out)

    def test_stray_folder_inside_a_kind_parent_is_red(self):
        parent = kind_path("decisions").rsplit("/", 1)[0]
        repo = Repo(self).core().write(EXTRAS, '{"kinds": {}}').write(parent + "/odd/a.md")
        code, out = repo.run("layout")
        self.assertEqual(code, 1, out)
        self.assertIn("folder %s/odd/" % parent, out)

    def test_extras_tool_folders_and_kind_subfolders_pass(self):
        repo = Repo(self).core().write(EXTRAS, '{"kinds": {"src": {"path": "src"}}}')
        repo.write("src/deep/a.py").write(".github/workflows/a.yml").write(".claude/skills/s/SKILL.md")
        repo.write(kind_path("decisions") + "/sub/a.md")
        code, out = repo.run("layout")
        self.assertEqual((code, out.strip()), (0, "layout: in shape"))

    def test_legacy_folder_names_its_move(self):
        legacy = layout.legacy("decisions")
        if legacy == kind_path("decisions"):
            self.skipTest("the layout has no legacy decisions path")
        code, out = Repo(self).write(legacy + "/a.md").run("layout")
        self.assertIn("legacy home of decisions, moves to " + kind_path("decisions"), out)

    def test_a_todo_kept_by_legacy_repos_is_not_missing(self):
        repo = Repo(self).core().write(EXTRAS, '{"kinds": {"todo": {"path": "records"}}}').write("records/backlog.md")
        subprocess.run(["git", "-C", repo.root, "rm", "-q", "--cached", kind_path("todo")], check=True)
        code, out = repo.run("layout")
        self.assertEqual((code, out.strip()), (0, "layout: in shape"))

    def test_untracked_core_kind_is_missing(self):
        rules = kind_path("rules")
        repo = Repo(self).write(EXTRAS, '{"kinds": {}}')
        os.makedirs(os.path.join(repo.root, *rules.split("/")))
        code, out = repo.run("layout")
        self.assertIn("missing core kind rules: " + rules, out)

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
        self.assertTrue(out.rstrip().endswith("design: in shape"), out)

    def test_each_gap_is_its_own_line(self):
        repo = Repo(self).write("src/App.tsx").write("Makefile", "screenshot:\n\tnode s.mjs\n")
        repo.write(".claude/skills/x/scripts/modern-screenshot.umd.js")
        code, out = repo.run("design")
        self.assertEqual(code, 1, out)
        self.assertIn("screens named: gap - no .claude/shoot.json", out)
        self.assertIn("screenshot command: partial - own command, not the shared shoot: Makefile target screenshot\n", out)
        self.assertIn("token file: gap - no tokens file", out)
        self.assertIn("ui copy: known gap", out)
        self.assertTrue(out.rstrip().endswith("design: out"), out)

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


if __name__ == "__main__":
    unittest.main()
