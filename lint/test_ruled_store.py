#!/usr/bin/env python3
"""Cases for lint/ruled_store.py, the one store of owner rulings not yet on main. Standard library only.

    python3 lint/test_ruled_store.py

The store is roadmap/rulings/<id>.json on origin/roadmap. Each case builds a real git repo under this run's folder
(lint/_test_temp.py) with lint/test_support/ruled_store_fixture.py, which points the refs with git plumbing, then calls
the module's functions or runs its CLI. RULED_STORE_UNDER_TEST overrides the module path, as a mutant run needs.
"""
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "test_support"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import ruled_store_fixture as fixture  # noqa: E402  the one home of a store fixture

MODULE = os.path.abspath(os.environ.get("RULED_STORE_UNDER_TEST") or os.path.join(HERE, "ruled_store.py"))
RUN_FOLDER = _test_temp.run_folder()  # test-temp-standard: tearDownModule removes it
HEADER = "rulings not on main: %d open (%d with no supersedes read yet), newest first"
DST_CDT = "2026-11-01T01:30:00-05:00"  # 06:30 UTC, the first 01:30 before the clocks go back
DST_CST = "2026-11-01T01:10:00-06:00"  # 07:10 UTC, after the change: later, though its text sorts first
RULING_LAND = "Rule one: keep the apps."


def load_module():
    spec = importlib.util.spec_from_file_location("ruled_store", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ruled_store = load_module()


def ids(entries):
    return [entry["id"] for entry in entries]


def names(text, key):
    """True when `key` appears in `text` as a whole word, so "at" does not match "that"."""
    return re.search(r"\b%s\b" % re.escape(key), text) is not None


def entry_lines(lines):
    """The entry lines of a session block: every line between the header and the command line."""
    return lines[1:-1]


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="ruled_store_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.root, True)

    def make_repo(self, name, store=None, main=None):
        """A repo under this case's folder. `store` and `main` are {path: text} trees, pointed at origin/roadmap
        and origin/main. A tree left as None gives a repo with no such ref."""
        repo = fixture.init_repo(os.path.join(self.root, name))
        if store is not None:
            fixture.point_ref(repo, fixture.STORE_REF, store, self.root)
        if main is not None:
            fixture.point_ref(repo, fixture.MAIN_REF, main, self.root)
        return repo


class RuledEntriesTests(RepoCase):
    def test_entries_come_back_in_time_order_not_text_order(self):
        repo = self.make_repo("order", store=fixture.ruling_files({
            "late": fixture.entry("late"),
            "cdt": fixture.entry("cdt", at=DST_CDT),
            "cst": fixture.entry("cst", at=DST_CST),
        }))
        got = ids(ruled_store.ruled_entries(repo))
        self.assertEqual(got, ["cdt", "cst", "late"], "entries not in time order: %r" % got)

    def test_a_store_on_origin_roadmap_is_read(self):
        repo = self.make_repo("read", store=fixture.ruling_files({"r1": fixture.entry("r1")}))
        self.assertEqual(ids(ruled_store.ruled_entries(repo)), ["r1"])

    def test_a_missing_origin_roadmap_returns_nothing(self):
        repo = self.make_repo("no-ref", main={"README.md": "main\n"})
        self.assertEqual(ruled_store.ruled_entries(repo), [], "a repo with no origin/roadmap did not read as []")

    def test_a_local_roadmap_branch_alone_is_not_read(self):
        repo = self.make_repo("local-only")
        fixture.point_ref(repo, "refs/heads/roadmap", fixture.ruling_files({"r1": fixture.entry("r1")}), self.root)
        self.assertEqual(ruled_store.ruled_entries(repo), [], "the local roadmap branch was read as the store")

    def test_a_roadmap_with_no_rulings_folder_returns_nothing(self):
        repo = self.make_repo("no-folder", store={"roadmap/README.md": "No rulings yet.\n"})
        self.assertEqual(ruled_store.ruled_entries(repo), [], "a roadmap with no rulings folder did not read as []")

    def test_a_malformed_file_is_skipped_and_its_valid_neighbour_is_returned(self):
        repo = self.make_repo("malformed", store=fixture.ruling_files({
            "good": fixture.entry("good"),
            "broken": "{not json",
        }))
        self.assertEqual(ids(ruled_store.ruled_entries(repo)), ["good"],
                         "the malformed file was not skipped beside its valid neighbour")

    def test_a_git_call_that_fails_returns_nothing_and_never_raises(self):
        good = self.make_repo("good", store=fixture.ruling_files({"r1": fixture.entry("r1")}))
        self.assertEqual(ids(ruled_store.ruled_entries(good)), ["r1"], "control: the store reads before the failures")
        plain = os.path.join(self.root, "plain")
        os.makedirs(plain)
        for label, where in (("not a git repo", plain), ("missing folder", os.path.join(self.root, "missing"))):
            with self.subTest(case=label):
                self.assertEqual(ruled_store.ruled_entries(where), [], "%s: the read did not return []" % label)
        with self.subTest(case="git not on PATH"), mock.patch.dict(os.environ, {"PATH": plain}):
            self.assertEqual(ruled_store.ruled_entries(good), [], "git not on PATH: the read did not return []")


class OpenEntriesTests(RepoCase):
    def test_closed_status_is_closed_and_an_open_entry_stays_open(self):
        repo = self.make_repo("status", store=fixture.ruling_files({
            "open": fixture.entry("open"),
            "shut": fixture.entry("shut", status="closed"),
        }))
        got = ids(ruled_store.open_entries(ruled_store.ruled_entries(repo), repo))
        self.assertEqual(got, ["open"], "open_entries returned %r, want only the open entry" % got)

    def test_lands_in_text_on_origin_main_closes_the_entry_with_whitespace_normalised(self):
        repo = self.make_repo(
            "landed",
            store=fixture.ruling_files({
                "landed": fixture.entry("landed", lands_in={"path": "docs/rules.md", "contains": RULING_LAND}),
                "pending": fixture.entry("pending", lands_in={"path": "docs/rules.md",
                                                              "contains": "Rule two: keep the apps."}),
            }),
            main={"docs/rules.md": "Rule one:\n   keep\tthe apps.\n"},
        )
        got = ids(ruled_store.open_entries(ruled_store.ruled_entries(repo), repo))
        self.assertEqual(got, ["pending"], "open_entries returned %r, want only the entry whose text is not on main"
                         % got)

    def test_text_only_in_the_checkout_does_not_close_the_entry(self):
        repo = self.make_repo(
            "checkout-only",
            store=fixture.ruling_files({
                "landed": fixture.entry("landed", lands_in={"path": "docs/rules.md", "contains": RULING_LAND}),
            }),
            main={"docs/rules.md": "Nothing here yet.\n"},
        )
        os.makedirs(os.path.join(repo, "docs"))
        with open(os.path.join(repo, "docs", "rules.md"), "w", encoding="utf-8") as handle:
            handle.write(RULING_LAND + "\n")
        got = ids(ruled_store.open_entries(ruled_store.ruled_entries(repo), repo))
        self.assertEqual(got, ["landed"], "the checkout's copy of the text closed the entry: %r" % got)

    def test_lands_in_path_missing_from_origin_main_leaves_the_entry_open(self):
        repo = self.make_repo(
            "wrong-path",
            store=fixture.ruling_files({
                "elsewhere": fixture.entry("elsewhere", lands_in={"path": "docs/other.md", "contains": RULING_LAND}),
            }),
            main={"docs/rules.md": RULING_LAND + "\n"},
        )
        got = ids(ruled_store.open_entries(ruled_store.ruled_entries(repo), repo))
        self.assertEqual(got, ["elsewhere"], "the text at another path closed the entry: %r" % got)


class LiftGuardsTests(RepoCase):
    def open_guarded_entries(self):
        repo = self.make_repo("guards", store=fixture.ruling_files({
            "guarded": fixture.entry("guarded", supersedes=[
                {"kind": "guard-rule", "ref": "guard-apps"},
                {"kind": "test", "ref": "lint/test_x.py::case"},
            ]),
            "shut": fixture.entry("shut", status="closed",
                                  supersedes=[{"kind": "guard-rule", "ref": "guard-shut"}]),
        }))
        return ruled_store.open_entries(ruled_store.ruled_entries(repo), repo)

    def test_the_switch_is_off_and_lifts_no_guard(self):
        self.assertIs(ruled_store.ENTRIES_LIFT_GUARDS, False, "ENTRIES_LIFT_GUARDS is not False")
        self.assertEqual(ruled_store.lifted_guards(self.open_guarded_entries()), [],
                         "the switch is off, yet a guard was lifted")

    def test_switch_on_lifts_the_guard_refs_of_open_entries_only(self):
        with mock.patch.object(ruled_store, "ENTRIES_LIFT_GUARDS", True):
            got = ruled_store.lifted_guards(self.open_guarded_entries())
        self.assertEqual(got, ["guard-apps"], "switch on lifted %r, want only the open entry's guard-rule ref" % got)


class CheckEntryTests(unittest.TestCase):
    def test_complete_entries_have_no_problem(self):
        self.assertEqual(ruled_store.check_entry(fixture.entry("listed")), [], "a complete entry has a problem")
        reasoned = fixture.entry("reasoned", supersedes=None, supersedes_none="the ruling fixes wording only")
        self.assertEqual(ruled_store.check_entry(reasoned), [], "an entry with supersedes_none has a problem")

    def test_each_missing_required_key_is_one_problem_that_names_it(self):
        for key in ("id", "at", "ruling", "source"):
            with self.subTest(key=key):
                problems = ruled_store.check_entry(fixture.entry("r", **{key: None}))
                self.assertEqual(len(problems), 1, "missing %s: want one problem, got %r" % (key, problems))
                self.assertTrue(names(problems[0], key), "missing %s: the problem does not name it: %r"
                                % (key, problems[0]))

    def test_a_naive_at_is_one_problem_and_a_zoned_at_passes(self):
        self.assertEqual(ruled_store.check_entry(fixture.entry("zoned")), [], "control: a zoned at has a problem")
        problems = ruled_store.check_entry(fixture.entry("naive", at="2026-11-12T14:15:00"))
        self.assertEqual(len(problems), 1, "a naive at: want one problem, got %r" % problems)
        self.assertTrue(names(problems[0], "at"), "a naive at: the problem does not name at: %r" % problems[0])

    def test_an_unreadable_at_is_one_problem(self):
        problems = ruled_store.check_entry(fixture.entry("odd", at="12 Nov 2026, mid-afternoon"))
        self.assertEqual(len(problems), 1, "an unreadable at: want one problem, got %r" % problems)
        self.assertTrue(names(problems[0], "at"), "an unreadable at: the problem does not name at: %r" % problems[0])

    def test_a_migrated_entry_with_neither_supersedes_key_fails(self):
        self.assertEqual(ruled_store.check_entry(fixture.entry("ok")), [], "control: a listed supersedes has a problem")
        problems = ruled_store.check_entry(fixture.entry("migrated", supersedes=None))
        self.assertEqual(len(problems), 1, "migrated entry with neither key: want one problem, got %r" % problems)
        self.assertIn("supersedes", problems[0], "the problem does not name supersedes: %r" % problems[0])


class SessionLinesTests(RepoCase):
    def test_no_store_and_no_open_entry_print_nothing(self):
        absent = self.make_repo("absent", main={"README.md": "main\n"})
        self.assertEqual(ruled_store.session_lines(absent), [], "a repo with no store printed lines")
        closed = self.make_repo(
            "closed",
            store=fixture.ruling_files({
                "shut": fixture.entry("shut", status="closed"),
                "landed": fixture.entry("landed", lands_in={"path": "docs/rules.md", "contains": RULING_LAND}),
            }),
            main={"docs/rules.md": RULING_LAND + "\n"},
        )
        self.assertEqual(ruled_store.session_lines(closed), [], "a store with no open entry printed lines")

    def test_one_open_entry_prints_the_header_the_entry_and_the_command(self):
        repo = self.make_repo("one", store=fixture.ruling_files({
            "r-1": fixture.entry("r-1", supersedes=[{"kind": "test", "ref": "lint/test_x.py::case_a"}]),
        }))
        lines = ruled_store.session_lines(repo)
        self.assertEqual(len(lines), 3, "want header, one entry, command; got %r" % lines)
        self.assertEqual(lines[0], HEADER % (1, 0), "header: %r" % lines[0])
        self.assertTrue(lines[1].startswith("  r-1 %s: " % fixture.AT), "entry line: %r" % lines[1])
        self.assertIn("| supersedes ", lines[1], "entry line has no supersedes part: %r" % lines[1])
        self.assertIn("lint/test_x.py::case_a", lines[1], "entry line does not name its supersedes ref: %r" % lines[1])
        self.assertIn("python3 lint/ruled_store.py list", lines[2], "command line: %r" % lines[2])
        self.assertIn(repo, lines[2], "command line does not name the repo: %r" % lines[2])

    def test_a_supersedes_none_entry_says_none(self):
        repo = self.make_repo("none", store=fixture.ruling_files({
            "r-2": fixture.entry("r-2", supersedes=None, supersedes_none="the ruling fixes wording only"),
        }))
        lines = ruled_store.session_lines(repo)
        self.assertEqual(len(lines), 3, "want header, one entry, command; got %r" % lines)
        self.assertIn("| supersedes none", lines[1], "entry line does not say none: %r" % lines[1])

    def test_the_ruling_is_cut_at_one_hundred_characters(self):
        ruling = "a" * 100 + "TAILMARK" + "b" * 60
        repo = self.make_repo("cut", store=fixture.ruling_files({"long": fixture.entry("long", ruling=ruling)}))
        lines = ruled_store.session_lines(repo)
        entries = entry_lines(lines)
        self.assertEqual(len(entries), 1, "want one entry line, got %r" % lines)
        self.assertIn(ruling[:100], entries[0], "the ruling is cut shorter than 100 characters: %r" % entries[0])
        self.assertNotIn(ruling[:101], entries[0], "the ruling is cut longer than 100 characters: %r" % entries[0])
        self.assertNotIn("TAILMARK", entries[0], "the ruling's tail reached the session line: %r" % entries[0])

    def test_the_header_counts_every_open_entry_and_lists_the_five_newest(self):
        entries = {
            "r%02d" % day: fixture.entry("r%02d" % day, at="2026-11-%02dT09:00:00-06:00" % day,
                                         supersedes=None, supersedes_none="a reason")
            for day in range(1, 13)
        }
        repo = self.make_repo("twelve", store=fixture.ruling_files(entries))
        lines = ruled_store.session_lines(repo)
        self.assertLessEqual(len(lines), 8, "session lines exceed 8: %d lines" % len(lines))
        self.assertEqual(lines[0], HEADER % (12, 0), "header: %r" % lines[0])
        listed = [line.split()[0] for line in entry_lines(lines)]
        self.assertEqual(listed, ["r12", "r11", "r10", "r09", "r08"], "listed %r, want the five newest" % listed)
        self.assertIn("python3 lint/ruled_store.py list", lines[-1], "command line: %r" % lines[-1])

    def test_newest_first_compares_instants_across_a_clock_change(self):
        repo = self.make_repo("dst", store=fixture.ruling_files({
            "cdt": fixture.entry("cdt", at=DST_CDT),
            "cst": fixture.entry("cst", at=DST_CST),
        }))
        listed = [line.split()[0] for line in entry_lines(ruled_store.session_lines(repo))]
        self.assertEqual(listed, ["cst", "cdt"], "newest first by instant, got %r" % listed)


class CostAndCliTests(RepoCase):
    def test_reading_the_store_starts_one_ls_tree_and_one_cat_file(self):
        repo = self.make_repo("cost", store=fixture.ruling_files(
            {"r%d" % number: fixture.entry("r%d" % number) for number in range(6)}))
        trace = os.path.join(self.root, "git-trace.log")
        with mock.patch.dict(os.environ, {"GIT_TRACE": trace}):
            entries = ruled_store.ruled_entries(repo)
        self.assertEqual(len(entries), 6, "control: the six entries did not all read")
        with open(trace, encoding="utf-8") as handle:
            starts = [line.split("built-in: git ", 1)[1].strip() for line in handle if "built-in: git " in line]
        self.assertEqual(len(starts), 2, "git starts for one read: %r" % starts)
        self.assertTrue(any("ls-tree" in start for start in starts), "no ls-tree start: %r" % starts)
        self.assertTrue(any("cat-file --batch" in start for start in starts), "no cat-file --batch start: %r" % starts)

    def test_session_line_flag_prints_the_session_lines(self):
        repo = self.make_repo("flag", store=fixture.ruling_files({"r1": fixture.entry("r1")}))
        proc = subprocess.run([sys.executable, MODULE, "--session-line", repo], capture_output=True, text=True,
                              timeout=60)
        self.assertEqual(proc.returncode, 0, "--session-line exited %d: %s" % (proc.returncode, proc.stderr))
        self.assertTrue(proc.stdout.strip(), "control: --session-line printed nothing")
        self.assertEqual(proc.stdout.splitlines(), ruled_store.session_lines(repo),
                         "--session-line did not print session_lines")

    def test_list_prints_every_open_entry_in_full(self):
        long_ruling = "Owner: " + "word " * 30 + "END-MARK."
        repo = self.make_repo("list", store=fixture.ruling_files({
            "open-a": fixture.entry("open-a"),
            "open-b": fixture.entry("open-b", ruling=long_ruling),
            "closed-old": fixture.entry("closed-old", status="closed"),
        }))
        proc = subprocess.run([sys.executable, MODULE, "list", repo], capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, "list exited %d: %s" % (proc.returncode, proc.stderr))
        self.assertIn("open-a", proc.stdout, "list did not print the open entry open-a")
        self.assertIn("open-b", proc.stdout, "list did not print the open entry open-b")
        self.assertIn(long_ruling, proc.stdout, "list cut or dropped the long ruling")
        self.assertNotIn("closed-old", proc.stdout, "list printed a closed entry")

    def test_check_exits_one_on_a_problem_and_zero_when_clean(self):
        clean = self.make_repo("clean", store=fixture.ruling_files({"ok": fixture.entry("ok")}))
        broken = self.make_repo("broken", store=fixture.ruling_files({
            "ok": fixture.entry("ok"),
            "migrated": fixture.entry("migrated", supersedes=None),
        }))
        passed = subprocess.run([sys.executable, MODULE, "check", clean], capture_output=True, text=True, timeout=60)
        self.assertEqual(passed.returncode, 0, "check on a clean store exited %d: %s"
                         % (passed.returncode, passed.stderr))
        failed = subprocess.run([sys.executable, MODULE, "check", broken], capture_output=True, text=True, timeout=60)
        self.assertEqual(failed.returncode, 1, "check on a store with a migrated entry exited %d, want 1"
                         % failed.returncode)
        self.assertIn("migrated", failed.stdout + failed.stderr, "check did not name the entry it refused")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main(verbosity=2)
