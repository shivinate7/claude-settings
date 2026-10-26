#!/usr/bin/env python3
"""Cases for lint/layout.json, lint/layout.py, its readers and lint/check_layout.py. Standard library only.

    python3 lint/test_layout.py

Readers: each one finds the records of a fixture repo laid out under docs/ (a rolled-out repo, with
an extras file), and of a repo still at its legacy root folders. Extras: a repo's extras file adds
its own kind. Constant check: a mutant that puts a record path literal back in one reader, or
moves the guard's literal, is red; a kind name, a docstring and a comment are not.

LAYOUT_LINT_UNDER_TEST names the lint folder under test (default: the folder of this file), so the
same cases run against another checkout to show them red there.
"""
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LINT = os.path.abspath(os.environ.get("LAYOUT_LINT_UNDER_TEST") or HERE)
REPO = os.path.dirname(LINT)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)
LONG = "a" * 33 + ".md"  # a slug over 32 characters
EXTRAS = ".claude/layout-extras.json"


def rm_tree(path):
    def clear(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=clear)
    else:
        shutil.rmtree(path, onerror=clear)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # a dataclass reads its module from sys.modules
    spec.loader.exec_module(module)
    return module


def run(cmd, cwd):
    env = dict(os.environ)
    env.pop("CI", None)
    env.pop("HOOK_CATALOG_ROOT", None)
    r = subprocess.run([sys.executable, *cmd], cwd=cwd, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


class Tree(unittest.TestCase):
    def setUp(self):
        self.tree = tempfile.mkdtemp(prefix="layout_")
        self.addCleanup(rm_tree, self.tree)

    def put(self, rel, text="# Record\n"):
        path = os.path.join(self.tree, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def roll_out(self, kinds=None):
        self.put(EXTRAS, json.dumps({"kinds": kinds or {}}))


class LayoutFile(Tree):
    def setUp(self):
        super().setUp()
        self.layout = load("layout_under_test", os.path.join(LINT, "layout.py"))

    def test_core_and_screen_kinds_sit_where_the_layout_says(self):
        kinds = self.layout.kinds()
        want = {"claude-md": "CLAUDE.md", "agents-md": "AGENTS.md", "rules": ".claude/rules",
                "decisions": "docs/decisions", "debts": "docs/debts", "debt-notes": "docs/debts/notes.md",
                "plans": "docs/plans", "specs": "docs/specs", "records-index": "docs/records.md",
                "design": "docs/design", "tokens": "tokens/tokens.json", "shots": "shots"}
        self.assertEqual({k: v["path"] for k, v in kinds.items()}, want)
        self.assertEqual(self.layout.layout()["extras"], EXTRAS)

    def test_rolled_out_repo_reads_docs(self):
        self.roll_out()
        self.put("decisions/x.md")  # a stray root folder is not read once the repo rolled out
        self.assertEqual(self.layout.path(self.tree, "decisions"), "docs/decisions")
        self.assertEqual(self.layout.folders(self.tree, "record"), ("docs/decisions", "docs/debts"))

    def test_repo_not_rolled_out_reads_the_legacy_folders(self):
        self.put("docs/decisions/x.md")  # a docs/ folder alone does not roll a repo out
        self.assertEqual(self.layout.path(self.tree, "decisions"), "decisions")
        self.assertEqual(self.layout.path(self.tree, "debt-notes"), "debts/notes.md")
        self.assertEqual(self.layout.candidates(self.tree, "decisions"), ("decisions", "docs/decisions"))

    def test_extras_file_adds_its_kind(self):
        self.roll_out({"records": {"path": "records", "listed": True, "record": True}})
        kinds = self.layout.kinds(self.tree)
        self.assertEqual(kinds["records"]["path"], "records")
        self.assertEqual(kinds["records"]["set"], "extra")
        self.assertIn("records", self.layout.folders(self.tree, "record"))

    def test_extras_file_may_not_replace_a_layout_kind(self):
        self.roll_out({"decisions": {"path": "elsewhere"}})
        with self.assertRaises(self.layout.LayoutError):
            self.layout.kinds(self.tree)

    def test_extras_path_outside_the_repo_is_an_error(self):
        for bad in ("../x", "/etc", "a/../../b", "C:/x"):
            with self.subTest(path=bad):
                self.roll_out({"x": {"path": bad}})
                with self.assertRaises(self.layout.LayoutError):
                    self.layout.kinds(self.tree)

    def test_broken_extras_file_is_an_error_never_a_silent_default(self):
        self.put(EXTRAS, "{not json")
        with self.assertRaises(self.layout.LayoutError):
            self.layout.kinds(self.tree)


class WaitingPage(Tree):
    """The waiting page's URL is one key in a repo's extras file (skill waiting-page)."""
    URL = "https://claude.ai/artifact/abc123"

    def setUp(self):
        super().setUp()
        self.layout = load("layout_under_test", os.path.join(LINT, "layout.py"))

    def test_key_set_returns_the_url(self):
        self.put(EXTRAS, json.dumps({"kinds": {}, "waiting-page": self.URL}))
        self.assertEqual(self.layout.waiting_page(self.tree), self.URL)

    def test_no_extras_file_is_unknown_not_an_error(self):
        self.assertEqual(self.layout.waiting_page(self.tree), "unknown")

    def test_extras_file_without_the_key_is_unknown(self):
        self.roll_out()
        self.assertEqual(self.layout.waiting_page(self.tree), "unknown")

    def test_a_key_that_is_not_a_claude_artifact_link_is_an_error(self):
        self.put(EXTRAS, json.dumps({"kinds": {}, "waiting-page": "https://example.com/x"}))
        with self.assertRaises(self.layout.LayoutError):
            self.layout.waiting_page(self.tree)

    def test_command_prints_the_url_or_unknown(self):
        code, out = run([os.path.join(LINT, "layout.py"), "waiting-page", self.tree], self.tree)
        self.assertEqual((code, out.strip()), (0, "unknown"))
        self.put(EXTRAS, json.dumps({"kinds": {}, "waiting-page": self.URL}))
        code, out = run([os.path.join(LINT, "layout.py"), "waiting-page", self.tree], self.tree)
        self.assertEqual((code, out.strip()), (0, self.URL))


class Readers(Tree):
    """Each reader finds the records of a fixture repo under docs/, and of one at the legacy root."""

    def slug_tree(self):
        """A copy of the slug check with the layout, run from its own tree as in CI."""
        tracked_tree.copy_tracked(self.tree, "lint", "hooks")  # the check's imports, whatever they become
        for name in ("check_record_slugs.py", "layout.py", "layout.json"):  # the files under test, from LINT
            shutil.copyfile(os.path.join(LINT, name), os.path.join(self.tree, "lint", name))
        return [os.path.join(self.tree, "lint", "check_record_slugs.py")]

    def test_record_slugs_judges_docs_records_in_a_rolled_out_repo(self):
        cmd = self.slug_tree()
        self.roll_out()
        rc, out = run(cmd + ["docs/decisions/" + LONG, "docs/debts/" + LONG, "decisions/" + LONG], self.tree)
        self.assertEqual(rc, 1, out)
        self.assertIn("docs/decisions/" + LONG, out)
        self.assertIn("docs/debts/" + LONG, out)
        self.assertNotIn(" decisions/" + LONG, out)

    def test_record_slugs_judges_an_extra_record_kind(self):
        cmd = self.slug_tree()
        self.roll_out({"records": {"path": "records", "record": True}})
        rc, out = run(cmd + ["records/" + LONG], self.tree)
        self.assertEqual(rc, 1, out)
        self.assertIn("records/" + LONG, out)

    def test_record_slugs_keeps_the_root_folders_before_roll_out(self):
        cmd = self.slug_tree()
        rc, out = run(cmd + ["decisions/" + LONG, "docs/decisions/" + LONG], self.tree)
        self.assertEqual(rc, 1, out)
        self.assertIn(" decisions/" + LONG, out)
        self.assertNotIn("docs/decisions/" + LONG, out)

    def test_ruling_kind_judges_docs_decisions_by_default(self):
        self.roll_out()
        self.put("docs/decisions/no-kind.md", "A ruling with no kind line.\n")
        rc, out = run([os.path.join(LINT, "check_ruling_kind.py"), "--root", self.tree, "docs/decisions/no-kind.md"], self.tree)
        self.assertEqual(rc, 1, out)
        self.assertIn("docs/decisions/no-kind.md", out)

    def test_records_page_lists_docs_records_and_an_extra_kind(self):
        self.roll_out({"records": {"path": "records", "listed": True}})
        self.put("CLAUDE.md", "# Rules\n\nCite by id.<!-- rule:cite-by-id -->\n")
        self.put("docs/decisions/one-ruling.md", "# One ruling\n\nKind: process\nHome: CLAUDE.md\n\n## The ruling\n\nRecords live under docs.\n")
        self.put("docs/debts/one-debt.md", "# One debt\n\n**What.** A gap.\n")
        self.put("docs/debts/notes.md", "- a note, never a row\n")
        self.put("records/ops-log.md", "# The ops log\n")
        self.put("decisions/stray.md", "# Stray\n")
        rc, out = run([os.path.join(LINT, "hook_catalog.py"), "--root", self.tree, "--records-only"], self.tree)
        self.assertEqual(rc, 0, out)
        with open(os.path.join(self.tree, "docs", "records.md"), encoding="utf-8") as f:
            page = f.read()
        self.assertIn("[`docs/decisions/one-ruling.md`](../docs/decisions/one-ruling.md)", page)
        self.assertIn("[`docs/debts/one-debt.md`]", page)
        self.assertIn("## Records", page)
        self.assertIn("[`records/ops-log.md`]", page)
        self.assertNotIn("notes.md", page)
        self.assertNotIn("stray", page)
        self.assertIn("`docs/decisions/`, `docs/debts/`, `docs/plans/` and `records/`", page)

    def test_records_page_keeps_the_root_folders_before_roll_out(self):
        self.put("docs/decisions/D001-heading.md", "## D1 Not this page's shape\n")
        self.put("decisions/one-ruling.md", "# One ruling\n\nKind: process\nHome: x\n\n## The ruling\n\nRoot records.\n")
        rc, out = run([os.path.join(LINT, "hook_catalog.py"), "--root", self.tree, "--records-only"], self.tree)
        self.assertEqual(rc, 0, out)
        with open(os.path.join(self.tree, "docs", "records.md"), encoding="utf-8") as f:
            page = f.read()
        self.assertIn("[`decisions/one-ruling.md`]", page)
        self.assertNotIn("D001", page)

    def ste_dir(self):
        ste = load("ste_lint_under_test", os.path.join(LINT, "ste_lint.py"))
        old = os.getcwd()
        os.chdir(self.tree)
        try:
            return ste.find_decisions_dir(dict(ste.DEFAULT_CONFIG))
        finally:
            os.chdir(old)

    def test_ste_lint_finds_docs_decisions(self):
        self.put("docs/decisions/x.md")
        self.assertEqual(self.ste_dir(), "docs/decisions")

    def test_ste_lint_finds_root_decisions_before_roll_out(self):
        # The incident: a default of docs/decisions missed this repo's own decisions/ folder.
        self.put("decisions/x.md")
        self.assertEqual(self.ste_dir(), "decisions")

    def test_ste_lint_and_records_page_are_red_on_a_broken_extras_file(self):
        self.put(EXTRAS, "{not json")
        self.put("a.md", "# A\n")
        rc, out = run([os.path.join(LINT, "ste_lint.py"), "a.md"], self.tree)
        self.assertEqual(rc, 2, out)
        self.assertIn("cannot read the layout", out)
        self.assertNotIn("Traceback", out)
        rc, out = run([os.path.join(LINT, "hook_catalog.py"), "--root", self.tree, "--records-only"], self.tree)
        self.assertEqual(rc, 2, out)
        self.assertNotIn("Traceback", out)

    def test_guard_reads_record_folders_from_the_layout_text(self):
        guard = load("guard_under_test", os.path.join(REPO, "hooks", "guard.py"))
        with open(os.path.join(LINT, "layout.json"), encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(guard.record_folders(json.dumps(data)), ["decisions", "debts"])
        data.pop("legacy")
        self.assertEqual(guard.record_folders(json.dumps(data)), ["docs/decisions", "docs/debts"])
        with self.assertRaises(ValueError):
            guard.record_folders("not a layout")


class ConstantCheck(Tree):
    """lint/check_layout.py over a copy of the repo's readers, with one mutant at a time."""

    def setUp(self):
        super().setUp()
        tracked_tree.copy_tracked(self.tree, "lint", "actions")  # the lint readers, the actions and the stamp examples
        os.makedirs(os.path.join(self.tree, "hooks"))  # the check parses hooks/ text and imports none of it
        shutil.copyfile(os.path.join(REPO, "hooks", "guard.py"), os.path.join(self.tree, "hooks", "guard.py"))
        for name in ("layout.py", "layout.json"):  # the files under test, from LINT
            shutil.copyfile(os.path.join(LINT, name), os.path.join(self.tree, "lint", name))

    def check(self):
        return run([os.path.join(LINT, "check_layout.py"), "--root", self.tree], self.tree)

    def edit(self, rel, old, new):
        path = os.path.join(self.tree, *rel.split("/"))
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(text.count(old), 1, "%s: %r" % (rel, old))
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text.replace(old, new))

    def append(self, rel, line):
        with open(os.path.join(self.tree, *rel.split("/")), "a", encoding="utf-8", newline="\n") as f:
            f.write("\n" + line + "\n")

    def assert_red(self, needle):
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn(needle, out)

    def test_the_repo_agrees(self):
        rc, out = self.check()
        self.assertEqual((rc, out), (0, ""))

    def test_a_record_path_literal_in_any_reader_is_red(self):
        for rel in ("lint/check_record_slugs.py", "lint/check_ruling_kind.py", "lint/check_skill_model_rows.py",
                    "lint/hook_catalog.py", "lint/ste_lint.py", "hooks/guard.py"):
            for literal in ('"decisions/"', '"docs/decisions"', '"./debts/x.md"', '"debts/notes.md"', '"plans/"',
                            'os.path.join(ROOT, "decisions", "x.md")', 'ROOT + "/decisions/x.md"',
                            '"x/decisions/a.md"', 'pathlib.Path(ROOT) / "decisions"'):
                with self.subTest(reader=rel, literal=literal):
                    self.setUp()
                    self.append(rel, "MUTANT = %s" % literal)
                    self.assert_red("%s:" % rel)

    def test_a_new_reader_in_any_scanned_folder_is_red(self):
        for folder in ("lint", "hooks", "merge", "janitor"):
            with self.subTest(folder=folder):
                self.setUp()
                self.put(folder + "/new_reader.py", 'FOLDER = "decisions/"\n')
                self.assert_red(folder + "/new_reader.py:")

    def test_a_test_file_is_not_a_reader(self):
        self.put("lint/test_new.py", 'FIXTURE = "decisions/x.md"\n')
        rc, out = self.check()
        self.assertEqual((rc, out), (0, ""))

    def test_a_word_in_a_shell_message_stays_green(self):
        self.append("actions/ruling-kind/check.sh", 'echo "ruling-kind: no decisions here"')
        rc, out = self.check()
        self.assertEqual((rc, out), (0, ""))

    def test_a_kind_name_a_docstring_and_a_comment_stay_green(self):
        self.append("lint/hook_catalog.py", 'KIND_NAME = "decisions"  # decisions/ in a comment')
        self.append("lint/hook_catalog.py", 'def f():\n    """Reads decisions/x.md."""')
        rc, out = self.check()
        self.assertEqual((rc, out), (0, ""))

    def test_guard_literal_that_drifts_is_red(self):
        self.edit("hooks/guard.py", 'RECORD_LAYOUT_FILE = os.path.join("lint", "layout.json")',
                  'RECORD_LAYOUT_FILE = os.path.join("lint", "check_record_slugs.py")')
        self.assert_red("RECORD_LAYOUT_FILE")

    def test_action_default_that_names_a_folder_is_red(self):
        self.edit("actions/ruling-kind/action.yml", 'default: ""', "default: decisions")
        self.assert_red("records-dir")
        self.setUp()
        self.edit("actions/ste-lint/action.yml", '    default: ""\nruns:', '    default: "docs/decisions"\nruns:')
        self.assert_red("decisions-dir")

    def test_action_script_that_names_a_folder_is_red(self):
        self.edit("actions/ruling-kind/check.sh", '"${RECORDS_DIR-}"', '"${RECORDS_DIR-decisions}"')
        self.assert_red("check.sh")

    def test_stamp_example_outside_docs_is_red(self):
        self.edit("actions/stamp/examples/frontmatter-prefixed-cite.stamp.json",
                  '"folder": "docs/questions"', '"folder": "questions"')
        self.assert_red("outside docs/")


if __name__ == "__main__":
    unittest.main()
