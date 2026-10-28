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
        self.addCleanup(tracked_tree.rm_tree, self.tree)

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

    def test_core_scorecard_and_screen_kinds_sit_where_the_layout_says(self):
        kinds = self.layout.kinds()
        want = {"claude-md": "CLAUDE.md", "agents-md": "AGENTS.md", "rules": ".claude/rules",
                "decisions": "docs/decisions", "debts": "docs/debts", "debt-notes": "docs/debts/notes.md",
                "plans": "docs/plans", "specs": "docs/specs", "records-index": "docs/records.md",
                "todo": "docs/todo.md", "scorecard": "docs/health/compliance.md", "design": "docs/design", "tokens": "tokens/tokens.json", "shots": "shots"}
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

    def origin(self, url, worktree=False):
        """A repo whose origin is `url`, read from git's config file as git writes it."""
        common = os.path.join(self.tree, "main.git") if worktree else os.path.join(self.tree, ".git")
        self.put(os.path.relpath(os.path.join(common, "config"), self.tree).replace(os.sep, "/"),
                 '[core]\n\tbare = false\n[remote "origin"]\n\turl = %s\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n' % url)
        if worktree:  # a linked worktree: .git is a file naming its git dir, which names the common dir
            self.put("main.git/worktrees/lane/commondir", "../..\n")
            self.put(".git", "gitdir: %s\n" % os.path.join(self.tree, "main.git", "worktrees", "lane"))

    def test_todo_sits_at_docs_todo_in_a_repo_with_no_entry(self):
        self.origin("https://github.com/shivinate7/degen.git")
        self.assertEqual(self.layout.path(self.tree, "todo"), "docs/todo.md")
        self.roll_out()
        self.assertEqual(self.layout.path(self.tree, "todo"), "docs/todo.md")

    def test_a_repo_entry_keeps_its_todo_where_it_is(self):
        for url in ("https://github.com/shivinate7/q_max", "git@github.com:shivinate7/q_max.git"):
            with self.subTest(url=url):
                self.origin(url)
                self.assertEqual(self.layout.path(self.tree, "todo"), "specs/todo.md")
                self.assertEqual(self.layout.candidates(self.tree, "todo"), ("specs/todo.md", "docs/todo.md"))

    def test_a_repo_entry_holds_in_a_linked_worktree(self):
        self.origin("https://github.com/shivinate7/q_max", worktree=True)
        self.assertEqual(self.layout.path(self.tree, "todo"), "specs/todo.md")

    def test_a_repo_entry_holds_after_roll_out_and_its_extras_may_repeat_it(self):
        self.origin("https://github.com/shivinate7/home")
        self.roll_out({"todo": {"path": "records"}})  # the extras file of home repeats its task home
        self.assertEqual(self.layout.path(self.tree, "todo"), "records")
        self.assertEqual(self.layout.path(self.tree, "decisions"), "docs/decisions")

    def test_an_extras_repeat_holds_when_the_origin_cannot_be_read(self):
        for url in (None, "http://local_proxy@127.0.0.1:41999/git/shivinate7/home", "file:///srv/home.git"):
            with self.subTest(url=url):
                self.setUp()
                if url:
                    self.origin(url)
                self.roll_out({"todo": {"path": "records"}})
                self.assertEqual(self.layout.path(self.tree, "todo"), "records")
                self.assertEqual(self.layout.path(self.tree, "decisions"), "docs/decisions")

    def test_origin_forms(self):
        for url, want in (("http://local_proxy@127.0.0.1:41999/git/shivinate7/Q_Max", "shivinate7/q_max"),
                          ("ssh://git@github.com/shivinate7/q_max.git/", "shivinate7/q_max"),
                          ("https://notgithub.com/shivinate7/q_max", None),
                          ("https://gitlab.com/shivinate7/q_max", None)):
            with self.subTest(url=url):
                self.setUp()
                self.origin(url)
                self.assertEqual(self.layout.repo_name(self.tree), want)

    def test_an_unreadable_git_file_is_no_origin_never_a_crash(self):
        with open(os.path.join(self.tree, ".git"), "wb") as f:
            f.write(b"gitdir: \xff\xfe\x00\n")
        self.assertIsNone(self.layout.repo_name(self.tree))
        self.assertEqual(self.layout.path(self.tree, "todo"), "docs/todo.md")

    def test_an_extras_todo_that_differs_from_the_repo_entry_is_an_error(self):
        for url in ("https://github.com/shivinate7/home", "https://github.com/shivinate7/q_max"):
            with self.subTest(url=url):
                self.origin(url)
                self.roll_out({"todo": {"path": "elsewhere"}})
                with self.assertRaises(self.layout.LayoutError):
                    self.layout.kinds(self.tree)

    def test_each_repo_entry_names_a_layout_kind_inside_the_repo(self):
        for repo, entry in self.layout.layout()["legacy-repos"].items():
            for name, found in entry.items():
                with self.subTest(repo=repo, kind=name):
                    self.assertIn(name, self.layout.layout()["kinds"])
                    self.assertEqual(self.layout._safe(found, repo), found)

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


class RepoKindAndCaution(Tree):
    """A repo names its app kind and its caution level in its extras file. Devices come from the kind,
    caution from the level, and the level defaults by visibility (steps c113 and c115)."""
    BYPASS = ("ignore", "bypass", "skip", "disregard", "override", "waive", "turn off", "disable", "no need to")

    def setUp(self):
        super().setUp()
        self.layout = load("layout_under_test", os.path.join(LINT, "layout.py"))

    def extras(self, **keys):
        self.put(EXTRAS, json.dumps(dict({"kinds": {}}, **keys)))

    def cmd(self, verb):
        return run([os.path.join(LINT, "layout.py"), verb, self.tree], self.tree)

    def test_a_repo_with_no_extras_file_resolves_by_visibility_not_an_error(self):
        self.assertEqual(self.layout.caution(self.tree)["level"], "public")
        self.assertIsNone(self.layout.devices(self.tree))
        self.assertEqual(self.cmd("caution")[0], 0)
        self.assertEqual(self.cmd("devices"), (0, "unknown\n"))

    def test_unknown_visibility_resolves_to_public(self):
        for keys in ({}, {"visibility": "secret-ish"}, {"visibility": None}):
            with self.subTest(keys=keys):
                self.extras(**keys)
                self.assertEqual(self.layout.caution(self.tree)["level"], "public")

    def test_private_visibility_resolves_to_private_solo(self):
        self.extras(visibility="private")
        self.assertEqual(self.layout.caution(self.tree)["level"], "private-solo")
        self.assertIn("private-solo", self.cmd("caution")[1])

    def test_a_named_caution_beats_visibility_and_a_bad_name_is_an_error(self):
        self.extras(visibility="private", caution="public")
        self.assertEqual(self.layout.caution(self.tree)["level"], "public")
        self.extras(caution="reckless")
        with self.assertRaises(self.layout.LayoutError):
            self.layout.caution(self.tree)

    def test_each_kind_has_its_default_device_order(self):
        self.extras(kind="ios")
        got = [d["id"] for d in self.layout.devices(self.tree)]
        self.assertEqual(got, ["iphone-duo-folded", "iphone-duo-unfolded", "iphone-regular"])
        self.extras(kind="web")
        got = [d["id"] for d in self.layout.devices(self.tree)]
        self.assertEqual(got, ["phone-width", "desktop-width"])
        self.assertEqual(self.cmd("devices")[1].splitlines()[0].split(":")[0], "phone-width")

    def test_a_repo_lists_devices_only_where_it_differs(self):
        self.extras(kind="ios", devices=["iphone-regular"])
        self.assertEqual([d["id"] for d in self.layout.devices(self.tree)], ["iphone-regular"])
        self.extras(kind="ios", devices=["no-such-device"])
        with self.assertRaises(self.layout.LayoutError):
            self.layout.devices(self.tree)
        self.extras(kind="toaster")
        with self.assertRaises(self.layout.LayoutError):
            self.layout.devices(self.tree)

    def test_no_device_carries_a_size_without_a_written_source(self):
        for name, device in self.layout.layout()["devices"].items():
            with self.subTest(device=name):
                size = device.get("size")
                self.assertTrue(size is None or (isinstance(size, dict) and size.get("source")), device)

    def test_every_level_holds_facts_and_acts_and_no_bypass_phrase(self):
        for level in ("public", "private-solo"):
            with self.subTest(level=level):
                self.extras(caution=level)
                found = self.layout.caution(self.tree)
                self.assertTrue(found["facts"] and found["acts"])
                text = " ".join(found["facts"] + found["acts"]).lower()
                for phrase in self.BYPASS:
                    self.assertNotIn(phrase, text)

    def test_private_solo_states_the_owners_own_logins_and_the_real_limits(self):
        self.extras(caution="private-solo")
        found = self.layout.caution(self.tree)
        text = " ".join(found["acts"] + found["facts"]).lower()
        self.assertIn("log in", text)
        self.assertIn("tool", text)
        self.assertIn("secret", text)
        self.assertIn("leaves the machine", text)

    def test_the_layout_repo_names_its_own_caution(self):
        found = self.layout.caution(REPO)
        self.assertIn(found["level"], ("public", "private-solo"))


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
        self.assertEqual(guard.record_folders(json.dumps(data)), ["docs/decisions", "decisions", "docs/debts", "debts"])
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

    def test_a_todo_path_literal_in_a_reader_is_red(self):
        for literal in ('"docs/todo.md"', '"specs/todo.md"'):
            with self.subTest(literal=literal):
                self.setUp()
                self.append("lint/hook_catalog.py", "MUTANT = %s" % literal)
                self.assert_red("lint/hook_catalog.py:")

    def test_a_repo_entry_for_an_unknown_kind_or_outside_the_repo_is_red(self):
        for entry in ({"no-such-kind": "x.md"}, {"todo": "../x.md"}, {"todo": 7}):
            with self.subTest(entry=entry):
                self.setUp()
                path = os.path.join(self.tree, "lint", "layout.json")
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                data["legacy-repos"]["shivinate7/x"] = entry
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    json.dump(data, f)
                self.assert_red("legacy-repos")

    def test_stamp_example_outside_docs_is_red(self):
        self.edit("actions/stamp/examples/frontmatter-prefixed-cite.stamp.json",
                  '"folder": "docs/questions"', '"folder": "questions"')
        self.assert_red("outside docs/")


if __name__ == "__main__":
    unittest.main()
