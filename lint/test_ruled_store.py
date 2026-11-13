#!/usr/bin/env python3
"""Cases for lint/ruled_store.py, the one store of owner rulings not yet on main. Standard library only.

    python3 lint/test_ruled_store.py

The store is roadmap/rulings/<id>.json on origin/roadmap. Each case builds a real git repo under this run's folder
(lint/_test_temp.py) with the store helpers defined below, which point the refs with git plumbing, then call
the module's functions or runs its CLI. RULED_STORE_UNDER_TEST overrides the module path, as a mutant run needs.
hooks/test_session_start.py and hooks/test_question_form.py import this file as `fixture` for the same helpers.
"""
import contextlib
import hashlib
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
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

# The store helpers. A store is the folder roadmap/rulings on origin/roadmap, one JSON file per ruling. The helpers
# point refs with git plumbing only (hash-object, update-index on a temp index, write-tree, commit-tree, update-ref),
# so no checkout moves and no branch changes. The caller owns the folder it passes as `scratch` for the temp index.
VCS = "g" + "it"  # assembled, as hooks/test_session_start.py assembles its own git name
IDENT = ("-c", "user.name=test", "-c", "user.email=test@example.invalid")
STORE_REF = "refs/remotes/origin/roadmap"
MAIN_REF = "refs/remotes/origin/main"
RULINGS_DIR = "roadmap/rulings"
AT = "2026-11-12T14:15:00-06:00"
TEST_SUPERSEDES = [{"kind": "test", "ref": "lint/test_ruled_store.py::test_case"}]
# A git start must not read the outer repo: a hook or CI step may set these to point at its own checkout.
STRIPPED = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY", "GIT_NAMESPACE")
ENV = {key: value for key, value in os.environ.items() if key not in STRIPPED}


def git(repo, *args, text=None, env=None):
    """stdout of one git start in `repo`. A failure raises: a fixture that cannot be built is an error, not a case result."""
    answer = _nowindow.run([VCS, "-C", repo, *IDENT, *args], input=text, capture_output=True, text=True,
                           env=env or ENV, timeout=60)
    if answer.returncode != 0:
        raise RuntimeError("fixture: %s %s failed: %s" % (VCS, " ".join(args), answer.stderr.strip()))
    return answer.stdout.strip()


def init_repo(path):
    """A new repo at `path`. The folder is made when it is missing."""
    os.makedirs(path, exist_ok=True)
    git(path, "init", "-q")
    return path


def point_ref(repo, ref, files, scratch):
    """Points `ref` at a new commit whose whole tree is `files` ({path: text}). Returns the commit's sha."""
    index = os.path.join(scratch, "index-" + ref.replace("/", "_"))
    if os.path.exists(index):
        os.remove(index)
    env = dict(ENV, GIT_INDEX_FILE=index)
    for path, text in sorted(files.items()):
        blob = git(repo, "hash-object", "-w", "--stdin", text=text, env=env)
        git(repo, "update-index", "--add", "--cacheinfo", "100644,%s,%s" % (blob, path), env=env)
    tree = git(repo, "write-tree", env=env)
    commit = git(repo, "commit-tree", tree, "-m", "fixture for " + ref, env=env)
    git(repo, "update-ref", ref, commit, env=env)
    return commit


def ruling_files(entries):
    """{path: text} for a store: each id maps to roadmap/rulings/<id>.json. A dict is written as JSON; a str is
    written as it is, which is how a case makes a malformed file."""
    return {"%s/%s.json" % (RULINGS_DIR, rid): body if isinstance(body, str) else json.dumps(body, indent=2)
            for rid, body in entries.items()}


def entry(rid, **over):
    """A valid ruling entry for `rid`: open, dated AT, with one test ref under supersedes. A key set to None is left out."""
    body = {"id": rid, "at": AT, "ruling": "Owner: keep the store to one place.",
            "quote": "keep it in one place", "source": "page item 1", "status": "open",
            "supersedes": [dict(ref) for ref in TEST_SUPERSEDES]}
    body.update(over)
    return {key: value for key, value in body.items() if value is not None}


# The cases name the helpers as fixture.<name>. A hook test that imports this file gets the same names as its module.
fixture = sys.modules[__name__]

MODULE = os.path.abspath(os.environ.get("RULED_STORE_UNDER_TEST") or os.path.join(HERE, "ruled_store.py"))
_RUN = []  # this run's folder, made on first use so that importing this file starts nothing


def run_folder():
    """This run's temp folder (test-temp-standard), made on the first call."""
    if not _RUN:
        _RUN.append(_test_temp.run_folder())
    return _RUN[0]
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


def git_starts(trace):
    """The git commands a GIT_TRACE file records, one per git start; [] when the file was never written."""
    if not os.path.exists(trace):
        return []
    with open(trace, encoding="utf-8") as handle:
        return [line.split("built-in: git ", 1)[1].strip() for line in handle if "built-in: git " in line]


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="ruled_store_", dir=run_folder())
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

    def store_with(self, name, entries, steps=None, main=None):
        """A repo whose origin/roadmap holds `entries` ({id: entry}) and the step files `steps`, and whose origin/main
        is the tree `main` when one is given."""
        files = fixture.ruling_files(entries)
        files.update(steps or {})
        return self.make_repo(name, store=files, main=main)


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

    def test_the_switch_defaults_on_so_an_open_entry_lifts_its_guard(self):
        self.assertIs(ruled_store.ENTRIES_LIFT_GUARDS, True, "ENTRIES_LIFT_GUARDS is not True")
        self.assertEqual(ruled_store.lifted_guards(self.open_guarded_entries()), ["guard-apps"],
                         "the switch is on by default, yet an open entry's guard was not lifted")

    def test_switch_off_lifts_no_guard(self):
        with mock.patch.object(ruled_store, "ENTRIES_LIFT_GUARDS", False):
            got = ruled_store.lifted_guards(self.open_guarded_entries())
        self.assertEqual(got, [], "the switch is off, yet %r was lifted" % got)

    def test_switch_on_lifts_the_guard_refs_of_open_entries_only(self):
        with mock.patch.object(ruled_store, "ENTRIES_LIFT_GUARDS", True):
            got = ruled_store.lifted_guards(self.open_guarded_entries())
        self.assertEqual(got, ["guard-apps"], "switch on lifted %r, want only the open entry's guard-rule ref" % got)

    def test_an_entry_that_check_entry_flags_or_is_not_open_lifts_nothing(self):
        good = fixture.entry("good", supersedes=[{"kind": "guard-rule", "ref": "guard-apps"}])
        flagged = fixture.entry("no-source", source=None, supersedes=[{"kind": "guard-rule", "ref": "guard-apps"}])
        pending = fixture.entry("pending", status="pending", supersedes=[{"kind": "guard-rule", "ref": "guard-apps"}])
        with mock.patch.object(ruled_store, "ENTRIES_LIFT_GUARDS", True):
            control = ruled_store.lifted_guards([good])
            got_flagged = ruled_store.lifted_guards([flagged])
            got_pending = ruled_store.lifted_guards([pending])
        self.assertEqual(control, ["guard-apps"], "control: a complete open entry did not lift its guard")
        self.assertEqual(got_flagged, [], "an entry that check_entry flags lifted a guard: %r" % got_flagged)
        self.assertEqual(got_pending, [], "an entry whose status is not open lifted a guard: %r" % got_pending)


def guard_entry(rid, at=fixture.AT, guard_ref="guard-apps", status="open"):
    """A store entry whose supersedes names one guard rule: the shape ruling_for_guard reads."""
    return fixture.entry(rid, at=at, status=status, supersedes=[{"kind": "guard-rule", "ref": guard_ref}])


class RulingForGuardTests(unittest.TestCase):
    def test_the_newest_open_entry_that_names_the_guard_is_returned(self):
        entries = [guard_entry("older", at="2026-11-10T09:00:00-06:00"),
                   guard_entry("newest", at="2026-11-12T09:00:00-06:00"),
                   guard_entry("middle", at="2026-11-11T09:00:00-06:00")]
        with mock.patch.object(ruled_store, "ENTRIES_LIFT_GUARDS", True):
            got = ruled_store.ruling_for_guard("guard-apps", entries)
        self.assertIsNotNone(got, "no entry returned, though three open entries name the guard")
        self.assertEqual(got["id"], "newest", "returned %r, want the newest open entry" % got["id"])

    def test_the_newest_is_the_later_instant_across_a_clock_change(self):
        # 01:30 -05:00 is 06:30 UTC; 01:10 -06:00 is 07:10 UTC, so the second is later though its text sorts first
        entries = [guard_entry("earlier-instant", at=DST_CDT), guard_entry("later-instant", at=DST_CST)]
        with mock.patch.object(ruled_store, "ENTRIES_LIFT_GUARDS", True):
            got = ruled_store.ruling_for_guard("guard-apps", entries)
        self.assertIsNotNone(got, "no entry returned, though two open entries name the guard")
        self.assertEqual(got["id"], "later-instant",
                         "returned %r, want the later instant (07:10 UTC, not the text-newest 06:30 UTC)" % got["id"])

    def test_the_one_open_entry_that_names_the_guard_is_returned(self):
        with mock.patch.object(ruled_store, "ENTRIES_LIFT_GUARDS", True):
            got = ruled_store.ruling_for_guard("guard-apps", [guard_entry("only")])
        self.assertIsNotNone(got, "no entry returned for the one open entry that names the guard")
        self.assertEqual(got["id"], "only", "returned %r, want the one open entry" % got["id"])

    def test_switch_off_gives_none_though_an_open_entry_names_the_guard(self):
        entries = [guard_entry("only")]
        with mock.patch.object(ruled_store, "ENTRIES_LIFT_GUARDS", True):
            on = ruled_store.ruling_for_guard("guard-apps", entries)
        self.assertIsNotNone(on, "control: the switch on finds the entry")
        with mock.patch.object(ruled_store, "ENTRIES_LIFT_GUARDS", False):
            off = ruled_store.ruling_for_guard("guard-apps", entries)
        self.assertIsNone(off, "the switch is off, yet an entry was returned: %r" % off)

    def test_a_closed_entry_is_ignored(self):
        entries = [guard_entry("shut-newest", at="2026-11-12T09:00:00-06:00", status="closed"),
                   guard_entry("open-older", at="2026-11-10T09:00:00-06:00")]
        with mock.patch.object(ruled_store, "ENTRIES_LIFT_GUARDS", True):
            got = ruled_store.ruling_for_guard("guard-apps", entries)
            only_shut = ruled_store.ruling_for_guard("guard-apps", [guard_entry("shut", status="closed")])
        self.assertIsNotNone(got, "no entry returned, though an open entry names the guard")
        self.assertEqual(got["id"], "open-older", "returned %r, want the open entry, not the closed one" % got["id"])
        self.assertIsNone(only_shut, "a closed entry alone was returned: %r" % only_shut)

    def test_a_prose_scoped_ref_governs_its_rule_id_in_both_lookups(self):
        scoped = fixture.entry("scoped", supersedes=[{"kind": "guard-rule", "ref": "builder-test-edit only for docs/"}])
        with mock.patch.object(ruled_store, "ENTRIES_LIFT_GUARDS", True):
            got = ruled_store.ruling_for_guard("builder-test-edit", [scoped])
            lifted = ruled_store.lifted_guards([scoped])
            shorter = ruled_store.ruling_for_guard("builder-test", [scoped])
        self.assertIsNotNone(got, "ruling_for_guard did not find the rule id that a prose-scoped ref names")
        self.assertEqual(got["id"], "scoped", "returned %r for the prose-scoped ref" % got["id"])
        self.assertEqual(lifted, ["builder-test-edit"], "lifted_guards gave %r, want the rule id alone" % lifted)
        self.assertIsNone(shorter, "a shorter name matched a rule id it does not equal: %r" % shorter)

    def test_a_colon_after_the_rule_id_is_stripped_in_both_lookups(self):
        colon = fixture.entry("colon", supersedes=[{"kind": "guard-rule", "ref": "builder-test-edit: only for docs/"}])
        with mock.patch.object(ruled_store, "ENTRIES_LIFT_GUARDS", True):
            got = ruled_store.ruling_for_guard("builder-test-edit", [colon])
            lifted = ruled_store.lifted_guards([colon])
        self.assertIsNotNone(got, "ruling_for_guard did not strip the colon after the rule id")
        self.assertEqual(lifted, ["builder-test-edit"], "lifted_guards gave %r, want the rule id with no colon" % lifted)

    def test_a_ref_whose_first_token_is_not_kebab_case_lifts_nothing(self):
        path = fixture.entry("path", supersedes=[{"kind": "guard-rule",
                                                  "ref": "settings.json:271,376: keep the timeouts"}])
        kept = fixture.entry("kept", supersedes=[{"kind": "guard-rule", "ref": "guard-apps only for docs/"}])
        with mock.patch.object(ruled_store, "ENTRIES_LIFT_GUARDS", True):
            lifted = ruled_store.lifted_guards([path, kept])
        self.assertEqual(lifted, ["guard-apps"], "lifted_guards gave %r, want only the kebab-case rule id" % lifted)

    def test_an_entry_that_check_entry_flags_or_is_not_open_governs_nothing(self):
        flagged = fixture.entry("no-source", source=None, supersedes=[{"kind": "guard-rule", "ref": "guard-apps"}])
        pending = guard_entry("pending", status="pending")
        with mock.patch.object(ruled_store, "ENTRIES_LIFT_GUARDS", True):
            control = ruled_store.ruling_for_guard("guard-apps", [guard_entry("good")])
            got_flagged = ruled_store.ruling_for_guard("guard-apps", [flagged])
            got_pending = ruled_store.ruling_for_guard("guard-apps", [pending])
        self.assertIsNotNone(control, "control: a complete open entry was not returned")
        self.assertIsNone(got_flagged, "an entry that check_entry flags governed: %r" % got_flagged)
        self.assertIsNone(got_pending, "an entry whose status is not open governed: %r" % got_pending)

    def test_an_entry_marked_unread_is_ignored(self):
        unread = fixture.entry("unread-newest", at="2026-11-12T09:00:00-06:00",
                               supersedes=[{"kind": "guard-rule", "ref": "guard-apps"}],
                               supersedes_none="unread: triage has not read this entry yet")
        read = guard_entry("read-older", at="2026-11-10T09:00:00-06:00")
        with mock.patch.object(ruled_store, "ENTRIES_LIFT_GUARDS", True):
            control = ruled_store.ruling_for_guard("guard-apps", [read])
            got = ruled_store.ruling_for_guard("guard-apps", [unread, read])
        self.assertIsNotNone(control, "control: the read entry alone was not returned")
        self.assertIsNotNone(got, "no entry returned, though a read entry names the guard")
        self.assertEqual(got["id"], "read-older",
                         "returned %r, want the read entry: an entry whose supersedes_none reads unread does not govern"
                         % got["id"])

    def test_only_a_guard_rule_ref_counts_and_another_guard_gives_none(self):
        test_kind = fixture.entry("test-kind", supersedes=[{"kind": "test", "ref": "guard-apps"}])
        with mock.patch.object(ruled_store, "ENTRIES_LIFT_GUARDS", True):
            got_test = ruled_store.ruling_for_guard("guard-apps", [test_kind])
            got_other = ruled_store.ruling_for_guard("guard-other", [guard_entry("named")])
        self.assertIsNone(got_test, "a test ref matched a guard name: %r" % got_test)
        self.assertIsNone(got_other, "an entry naming another guard matched: %r" % got_other)


class GuardRulingLineTests(unittest.TestCase):
    def test_the_line_names_the_id_the_owner_time_and_the_ruling(self):
        entry = fixture.entry("ruled-apps-keep", ruling="Owner: keep the apps' access as is.")
        self.assertEqual(ruled_store.guard_ruling_line(entry),
                         "ruled by ruled-apps-keep (owner %s): Owner: keep the apps' access as is." % fixture.AT,
                         "guard_ruling_line did not print the id, owner time and ruling of the entry")

    def test_the_ruling_is_cut_to_one_hundred_characters(self):
        ruling = "a" * 100 + "TAILMARK" + "b" * 40
        got = ruled_store.guard_ruling_line(fixture.entry("long", ruling=ruling))
        self.assertEqual(got, "ruled by long (owner %s): %s" % (fixture.AT, ruling[:100]),
                         "the guard line is not the ruling cut to 100 characters: %r" % got)


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


    def test_a_status_outside_open_and_closed_is_one_problem_that_names_it(self):
        self.assertEqual(ruled_store.check_entry(fixture.entry("shut", status="closed")), [],
                         "control: a closed status has a problem")
        problems = ruled_store.check_entry(fixture.entry("odd", status="pending"))
        self.assertEqual(len(problems), 1, "a pending status: want one problem, got %r" % problems)
        self.assertTrue(names(problems[0], "status"), "a pending status: the problem does not name status: %r"
                        % problems[0])


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


def step_file(slug, status, **over):
    """The roadmap step file a store ref carries for `slug`, with its status and any keys in `over` (a `lane`, say;
    None is written as null). With no `over`, the file has no lane key."""
    body = {"slug": slug, "status": status}
    body.update(over)
    return {"roadmap/data/steps/%s.json" % slug: json.dumps(body)}


class CheckStoreTests(RepoCase):
    def test_a_clean_store_has_no_problem(self):
        repo = self.store_with("clean", {"ok": fixture.entry("ok")})
        self.assertEqual(ruled_store.check_store(repo), [], "a clean store has a problem")

    def test_every_check_entry_problem_is_listed(self):
        bad = {"no-zone": fixture.entry("no-zone", at="2026-11-12T14:15:00"),
               "no-ruling": fixture.entry("no-ruling", ruling=None)}
        expected = [problem for entry in bad.values() for problem in ruled_store.check_entry(entry)]
        self.assertEqual(len(expected), 2, "control: want two check_entry problems, got %r" % expected)
        got = ruled_store.check_store(self.store_with("problems", bad))
        for problem in expected:
            self.assertTrue(any(problem in line for line in got),
                            "check_store did not list the check_entry problem %r: %r" % (problem, got))

    def test_two_open_entries_that_supersede_one_ref_are_flagged(self):
        repo = self.store_with("twins", {
            "rule-a": fixture.entry("rule-a", at="2026-11-10T09:00:00-06:00"),
            "rule-b": fixture.entry("rule-b", at="2026-11-11T09:00:00-06:00"),
        })
        want = "entries rule-a and rule-b both supersede lint/test_ruled_store.py::test_case"
        got = ruled_store.check_store(repo)
        self.assertTrue(any(want in line for line in got), "check_store did not flag the shared ref: %r" % got)

    def test_refs_match_by_their_first_token(self):
        repo = self.store_with("tokens", {
            "rule-a": fixture.entry("rule-a", at="2026-11-10T09:00:00-06:00",
                                    supersedes=[{"kind": "test",
                                                 "ref": "lint/test_ruled_store.py::test_case check the flow"}]),
            "rule-b": fixture.entry("rule-b", at="2026-11-11T09:00:00-06:00"),
        })
        got = ruled_store.check_store(repo)
        self.assertTrue(any("both supersede lint/test_ruled_store.py::test_case" in line and "rule-a" in line
                            and "rule-b" in line for line in got),
                        "a ref with trailing text did not match its first token: %r" % got)

    def test_the_same_token_under_another_kind_is_not_flagged(self):
        repo = self.store_with("kinds", {
            "rule-a": fixture.entry("rule-a", at="2026-11-10T09:00:00-06:00",
                                    supersedes=[{"kind": "guard-rule", "ref": "lint/test_ruled_store.py::test_case"}]),
            "rule-b": fixture.entry("rule-b", at="2026-11-11T09:00:00-06:00"),
        })
        flagged = [line for line in ruled_store.check_store(repo) if "both supersede" in line]
        self.assertEqual(flagged, [], "a guard-rule ref and a test ref were flagged as one: %r" % flagged)

    def test_a_closed_entry_sharing_a_ref_is_not_flagged(self):
        repo = self.store_with("closed-twin", {
            "rule-a": fixture.entry("rule-a", at="2026-11-10T09:00:00-06:00"),
            "rule-b": fixture.entry("rule-b", at="2026-11-11T09:00:00-06:00", status="closed"),
        })
        flagged = [line for line in ruled_store.check_store(repo) if "both supersede" in line]
        self.assertEqual(flagged, [], "a closed entry was counted as a second supersede: %r" % flagged)

    def test_an_open_entry_on_a_done_step_is_flagged(self):
        repo = self.store_with("done-step", {"stepped": fixture.entry("stepped", step="ruled-store-one-home")},
                               steps=step_file("ruled-store-one-home", "done"))
        want = "step ruled-store-one-home is done but entry stepped is still open"
        got = ruled_store.check_store(repo)
        self.assertTrue(any(want in line for line in got), "check_store did not flag the open entry: %r" % got)

    def test_a_closed_entry_on_a_done_step_is_not_flagged(self):
        repo = self.store_with("done-closed", {
            "stepped": fixture.entry("stepped", step="ruled-store-one-home", status="closed")},
            steps=step_file("ruled-store-one-home", "done"))
        flagged = [line for line in ruled_store.check_store(repo) if "is done but entry" in line]
        self.assertEqual(flagged, [], "a closed entry was flagged against its done step: %r" % flagged)

    def test_a_missing_step_file_is_no_problem(self):
        repo = self.store_with("no-step", {"stepped": fixture.entry("stepped", step="no-such-step")})
        self.assertEqual(ruled_store.check_store(repo), [], "an entry whose step file is missing was reported")

    def test_a_steps_list_is_flagged_only_when_every_listed_step_is_done(self):
        steps = {}
        for slug, status in (("step-one", "done"), ("step-two", "done"), ("step-open", "in_progress")):
            steps.update(step_file(slug, status))
        repo = self.store_with("steps-list", {
            "stepped-all": fixture.entry("stepped-all", steps=["step-one", "step-two"],
                                         supersedes=[{"kind": "test", "ref": "lint/test_ruled_store.py::stepped-all"}]),
            "stepped-mixed": fixture.entry("stepped-mixed", steps=["step-one", "step-open"],
                                           supersedes=[{"kind": "test",
                                                        "ref": "lint/test_ruled_store.py::stepped-mixed"}]),
        }, steps=steps)
        got = ruled_store.check_store(repo)
        self.assertTrue(any("stepped-all" in line and "done" in line for line in got),
                        "check_store did not flag an entry whose every listed step is done: %r" % got)
        mixed = [line for line in got if "stepped-mixed" in line and "done" in line]
        self.assertEqual(mixed, [], "an entry with a step still open was flagged as done: %r" % mixed)

    def test_a_single_step_keeps_its_one_line(self):
        repo = self.store_with("single-step", {"solo": fixture.entry("solo", step="step-one")},
                               steps=step_file("step-one", "done"))
        got = ruled_store.check_store(repo)
        self.assertTrue(any("step step-one is done but entry solo is still open" in line for line in got),
                        "control: a single done step was not flagged: %r" % got)

    def test_an_unparseable_store_file_is_flagged_and_skipped(self):
        repo = self.store_with("broken-file", {"ok": fixture.entry("ok"), "broken": "{not json"})
        self.assertEqual([e["id"] for e in ruled_store.ruled_entries(repo)], ["ok"],
                         "control: the valid entry did not read, or the broken file was not skipped")
        got = ruled_store.check_store(repo)
        self.assertTrue(any("broken.json" in line and "is not valid JSON" in line for line in got),
                        "check_store did not flag the unparseable store file: %r" % got)

    def test_a_guard_ref_with_no_rule_id_is_flagged(self):
        repo = self.store_with("no-rule-id", {"non-kebab": fixture.entry("non-kebab", supersedes=[
            {"kind": "guard-rule", "ref": "settings.json:271,376: keep the timeouts"}])})
        got = ruled_store.check_store(repo)
        self.assertTrue(any("entry non-kebab: guard-rule ref names no rule id" in line for line in got),
                        "check_store did not flag a guard-rule ref with no rule id: %r" % got)

    def test_check_cli_refuses_an_open_entry_on_a_done_step(self):
        repo = self.store_with("cli-step", {"stepped": fixture.entry("stepped", step="ruled-store-one-home")},
                               steps=step_file("ruled-store-one-home", "done"))
        proc = subprocess.run([sys.executable, MODULE, "check", repo], capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 1, "check exited %d on an open entry whose step is done, want 1: %s"
                         % (proc.returncode, proc.stderr))
        self.assertIn("step ruled-store-one-home is done but entry stepped is still open", proc.stdout + proc.stderr,
                      "check did not name the open entry on a done step")


LANDED = {"path": "docs/rules.md", "contains": RULING_LAND}  # its text is on main in ON_MAIN, not in NOT_ON_MAIN
ON_MAIN = {"docs/rules.md": RULING_LAND + "\n"}
NOT_ON_MAIN = {"docs/rules.md": "Nothing here yet.\n"}
OLD_AT = "2019-03-01T09:00:00-06:00"  # an old entry is still listed: the stale list has no age limit


def stale_id(line):
    """The entry id that a `stale` output line names: its first word, without a trailing colon."""
    return line.split()[0].rstrip(":")


def stale_ids_of(lines):
    return [stale_id(line) for line in lines]


def stale_line(lines, rid):
    """The `stale` output line that names entry `rid`, or None."""
    return next((line for line in lines if stale_id(line) == rid), None)


def tree_digest(root):
    """{relative path: sha256 of its bytes} for each file under `root`, so a test can tell what a run wrote."""
    digest = {}
    for folder, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(folder, name)
            with open(path, "rb") as handle:
                digest[os.path.relpath(path, root)] = hashlib.sha256(handle.read()).hexdigest()
    return digest


class StaleEntriesTests(RepoCase):
    """`stale REPO` prints one line per open entry whose step is done, dropped, or doing with no lane, while main
    still lacks the ruling. Most cases run the CLI in a child process, so a subcommand that is missing shows as an
    exit code and no lines, never as an exception in this run. The read-failure case calls main in this process."""

    def stale_run(self, repo):
        """(the child process, its non-empty output lines) of `stale REPO`."""
        proc = subprocess.run([sys.executable, MODULE, "stale", repo], capture_output=True, text=True, timeout=60)
        return proc, [line for line in proc.stdout.splitlines() if line.strip()]

    def test_control_the_existing_readers_see_the_fixture_the_cases_expect(self):
        repo = self.store_with("control", {
            "stale": fixture.entry("stale", step="step-done"),
            "busy": fixture.entry("busy", step="step-doing"),
            "absorbed": fixture.entry("absorbed", step="step-done", lands_in=LANDED),
            "shut": fixture.entry("shut", step="step-done", status="closed"),
        }, steps={**step_file("step-done", "done"), **step_file("step-doing", "doing", lane="lane-a")}, main=ON_MAIN)
        opened = ruled_store.open_entries(ruled_store.ruled_entries(repo), repo)
        self.assertEqual(sorted(ids(opened)), ["busy", "stale"],
                         "control: open_entries did not keep the two open entries")
        self.assertIn("step step-done is done but entry stale is still open", ruled_store.check_store(repo),
                      "control: check_store did not flag the open entry on the done step")

    def test_an_open_entry_on_a_done_step_is_listed_and_one_already_on_main_is_not(self):
        repo = self.store_with("done", {
            "stale": fixture.entry("stale", step="step-done"),
            "absorbed": fixture.entry("absorbed", step="step-done", lands_in=LANDED),
        }, steps=step_file("step-done", "done"), main=ON_MAIN)
        proc, lines = self.stale_run(repo)
        self.assertIn("stale", stale_ids_of(lines), "stale did not list the open entry whose step is done: %r" % lines)
        self.assertIn("done", stale_line(lines, "stale"),
                      "the line for the done-step entry does not say its step is done: %r" % lines)
        self.assertNotIn("absorbed", stale_ids_of(lines),
                         "stale listed an entry whose ruling is already on main: %r" % lines)

    def test_an_open_entry_on_a_step_that_is_not_done_but_has_a_lane_is_not_listed(self):
        repo = self.store_with("busy", {
            "stale": fixture.entry("stale", step="step-done"),
            "busy": fixture.entry("busy", step="step-doing"),
        }, steps={**step_file("step-done", "done"), **step_file("step-doing", "doing", lane="lane-a")})
        proc, lines = self.stale_run(repo)
        self.assertIn("stale", stale_ids_of(lines),
                      "control: stale did not list the open entry whose step is done: %r" % lines)
        self.assertNotIn("busy", stale_ids_of(lines),
                         "stale listed an entry whose step is doing and has a lane: %r" % lines)

    def test_an_open_entry_on_a_step_that_is_doing_with_no_lane_is_listed(self):
        cases = (("lane is null", {"lane": None}), ("lane is missing", {}), ("lane is empty", {"lane": ""}),
                 ("lane is not a string", {"lane": 5}))
        for index, (label, over) in enumerate(cases):
            with self.subTest(case=label):
                repo = self.store_with("nolane-%d" % index, {"stale": fixture.entry("stale", step="step-doing")},
                                       steps=step_file("step-doing", "doing", **over))
                proc, lines = self.stale_run(repo)
                self.assertIn("stale", stale_ids_of(lines),
                              "stale did not list an open entry whose step is doing and %s: %r" % (label, lines))
                self.assertIn("lane", stale_line(lines, "stale"),
                              "the line for the no-lane entry does not name the lane: %r" % lines)

    def test_an_open_entry_on_a_ready_or_todo_step_with_no_lane_is_not_listed(self):
        repo = self.store_with("queued", {
            "stale": fixture.entry("stale", step="step-done"),
            "ready": fixture.entry("ready", step="step-ready"),
            "todo": fixture.entry("todo", step="step-todo"),
        }, steps={**step_file("step-done", "done"), **step_file("step-ready", "ready"),
                  **step_file("step-todo", "todo")})
        proc, lines = self.stale_run(repo)
        self.assertIn("stale", stale_ids_of(lines), "control: stale did not list the open entry on a done step: %r"
                      % lines)
        self.assertNotIn("ready", stale_ids_of(lines),
                         "stale listed an entry whose step is ready and has no lane: %r" % lines)
        self.assertNotIn("todo", stale_ids_of(lines),
                         "stale listed an entry whose step is todo and has no lane: %r" % lines)

    def test_an_open_entry_on_a_dropped_step_is_listed_and_its_line_says_dropped(self):
        repo = self.store_with("dropped", {
            "stale": fixture.entry("stale", step="step-done"),
            "shelved": fixture.entry("shelved", step="step-dropped"),
        }, steps={**step_file("step-done", "done"), **step_file("step-dropped", "dropped", lane="lane-a")})
        proc, lines = self.stale_run(repo)
        self.assertIn("stale", stale_ids_of(lines), "control: stale did not list the open entry on a done step: %r"
                      % lines)
        self.assertIn("shelved", stale_ids_of(lines),
                      "stale did not list the open entry whose step is dropped: %r" % lines)
        self.assertIn("step step-dropped is dropped", stale_line(lines, "shelved"),
                      "the line for the dropped-step entry does not say its step is dropped: %r" % lines)

    def test_a_multi_step_entry_is_listed_only_when_every_step_file_exists_and_qualifies(self):
        steps = {}
        for slug, status, over in (("step-done", "done", {}), ("step-dropped", "dropped", {"lane": "lane-a"}),
                                   ("step-doing-no-lane", "doing", {}),
                                   ("step-doing-lane", "doing", {"lane": "lane-a"}),
                                   ("step-ready", "ready", {}), ("step-todo", "todo", {})):
            steps.update(step_file(slug, status, **over))
        multi = {  # entry id: (its steps, listed?). step-missing has no step file.
            "done-dropped": (["step-done", "step-dropped"], True),
            "done-doing-no-lane": (["step-done", "step-doing-no-lane"], True),
            "done-doing-lane": (["step-done", "step-doing-lane"], False),
            "done-ready": (["step-done", "step-ready"], False),
            "done-todo": (["step-done", "step-todo"], False),
            "done-missing": (["step-done", "step-missing"], False),
        }
        entries = {"control": fixture.entry("control", step="step-done")}
        for rid, (slugs, _listed) in multi.items():
            entries[rid] = fixture.entry(rid, steps=slugs)
        repo = self.store_with("multi", entries, steps=steps)
        proc, lines = self.stale_run(repo)
        listed = stale_ids_of(lines)
        self.assertIn("control", listed, "control: stale did not list the single done-step entry: %r" % lines)
        for rid, (slugs, want) in multi.items():
            with self.subTest(entry=rid):
                if want:
                    self.assertIn(rid, listed, "stale did not list %s, whose steps %s all qualify: %r"
                                  % (rid, ", ".join(slugs), lines))
                else:
                    self.assertNotIn(rid, listed, "stale listed %s, whose steps %s do not all qualify: %r"
                                     % (rid, ", ".join(slugs), lines))

    def test_a_closed_entry_is_not_listed_even_when_its_step_is_done(self):
        repo = self.store_with("shut", {
            "stale": fixture.entry("stale", step="step-done"),
            "shut": fixture.entry("shut", step="step-done", status="closed"),
        }, steps=step_file("step-done", "done"))
        proc, lines = self.stale_run(repo)
        self.assertIn("stale", stale_ids_of(lines), "control: stale did not list the open entry on a done step: %r"
                      % lines)
        self.assertNotIn("shut", stale_ids_of(lines), "stale listed a closed entry: %r" % lines)

    def test_an_open_entry_with_no_step_is_not_listed(self):
        repo = self.store_with("nostep", {
            "stale": fixture.entry("stale", step="step-done"),
            "bare": fixture.entry("bare"),
        }, steps=step_file("step-done", "done"))
        proc, lines = self.stale_run(repo)
        self.assertIn("stale", stale_ids_of(lines), "control: stale did not list the open entry on a done step: %r"
                      % lines)
        self.assertNotIn("bare", stale_ids_of(lines), "stale listed an entry that names no step: %r" % lines)

    def test_an_open_entry_whose_step_file_is_missing_is_not_listed(self):
        repo = self.store_with("nofile", {
            "stale": fixture.entry("stale", step="step-done"),
            "gone": fixture.entry("gone", step="step-gone"),
        }, steps=step_file("step-done", "done"))
        proc, lines = self.stale_run(repo)
        self.assertIn("stale", stale_ids_of(lines), "control: stale did not list the open entry on a done step: %r"
                      % lines)
        self.assertNotIn("gone", stale_ids_of(lines), "stale listed an entry whose step file is missing: %r" % lines)

    def test_an_old_entry_on_a_done_step_is_listed_however_old_it_is(self):
        repo = self.store_with("old", {"old": fixture.entry("old", at=OLD_AT, step="step-done")},
                               steps=step_file("step-done", "done"))
        proc, lines = self.stale_run(repo)
        self.assertIn("old", stale_ids_of(lines),
                      "stale did not list an open entry from %s on a done step: %r" % (OLD_AT, lines))

    def test_every_stale_entry_is_listed_in_a_full_store_not_only_the_newest_five(self):
        entries = {"s%02d" % day: fixture.entry("s%02d" % day, at="2026-11-%02dT09:00:00-06:00" % day,
                                               step="step-done")
                   for day in range(1, 13)}
        repo = self.store_with("full", entries, steps=step_file("step-done", "done"))
        proc, lines = self.stale_run(repo)
        self.assertEqual(sorted(stale_ids_of(lines)), sorted(entries),
                         "stale did not list all twelve stale entries: %r" % lines)

    def test_stale_exits_zero_and_prints_nothing_when_nothing_is_stale(self):
        empty = {
            "closed only": self.store_with("closed-only",
                                           {"shut": fixture.entry("shut", step="step-done", status="closed")},
                                           steps=step_file("step-done", "done")),
            "no roadmap": self.make_repo("no-roadmap", main={"README.md": "main\n"}),
        }
        for label, repo in empty.items():
            with self.subTest(case=label):
                proc, lines = self.stale_run(repo)
                self.assertEqual(proc.returncode, 0, "stale exited %d on %s, want 0: %s"
                                 % (proc.returncode, label, proc.stderr.strip()))
                self.assertEqual(lines, [], "stale printed lines on %s: %r" % (label, lines))

    def test_stale_starts_only_the_git_reads_the_store_needs(self):
        full = self.store_with("cost-full", {
            "a": fixture.entry("a", step="step-done", lands_in=LANDED),
            "b": fixture.entry("b", step="step-doing"),
            "c": fixture.entry("c"),
            "d": fixture.entry("d", step="step-done", status="closed"),
            "e": fixture.entry("e", lands_in=LANDED),
            "f": fixture.entry("f", step="step-done"),
        }, steps={**step_file("step-done", "done"), **step_file("step-doing", "doing", lane="lane-a")},
            main=NOT_ON_MAIN)
        bare = self.store_with("cost-bare", {"a": fixture.entry("a"), "b": fixture.entry("b"),
                                             "c": fixture.entry("c")})
        read_trace = os.path.join(self.root, "read.trace")
        with mock.patch.dict(os.environ, {"GIT_TRACE": read_trace}):
            ruled_store.ruled_entries(full)
        control = sorted(start.split()[0] for start in git_starts(read_trace))
        self.assertEqual(control, ["cat-file", "ls-tree"], "control: one read of the store started git %r" % control)
        cases = (("with lands_in and steps", full, ["cat-file", "cat-file", "cat-file", "ls-tree"]),
                 ("with neither", bare, ["cat-file", "ls-tree"]))
        for index, (label, repo, want) in enumerate(cases):
            with self.subTest(case=label):
                trace = os.path.join(self.root, "stale-%d.trace" % index)
                with mock.patch.dict(os.environ, {"GIT_TRACE": trace}):
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        ruled_store.main(["stale", repo])
                got = sorted(start.split()[0] for start in git_starts(trace))
                self.assertEqual(got, sorted(want), "stale started git %r %s, want %r" % (got, label, sorted(want)))

    def test_stale_starts_no_process_but_git_and_writes_no_file(self):
        repo = self.store_with("procs", {
            "a": fixture.entry("a", step="step-done", lands_in=LANDED),
            "b": fixture.entry("b", step="step-doing"),
        }, steps={**step_file("step-done", "done"), **step_file("step-doing", "doing", lane="lane-a")},
            main=NOT_ON_MAIN)
        with mock.patch.object(subprocess, "Popen", wraps=subprocess.Popen) as popen:
            ruled_store.ruled_entries(repo)
            control = [call[0][0] for call in popen.call_args_list]
            popen.reset_mock()
            before = tree_digest(self.root)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                ruled_store.main(["stale", repo])
            started = [call[0][0] for call in popen.call_args_list]
        after = tree_digest(self.root)
        self.assertTrue(control and all(os.path.basename(argv[0]) == "git" for argv in control),
                        "control: the existing read did not start git through subprocess.Popen: %r" % control)
        self.assertTrue(started, "stale started no process at all, so it reads nothing")
        others = sorted({os.path.basename(argv[0]) for argv in started} - {"git"})
        self.assertEqual(others, [], "stale started a process other than git: %r" % others)
        changed = sorted(set(before) ^ set(after)) + sorted(p for p in before if p in after and before[p] != after[p])
        self.assertEqual(changed, [], "stale wrote or changed files under the test tree: %r" % changed)

    def test_a_stale_read_that_raises_exits_two_and_writes_one_stderr_line(self):
        failure = RuntimeError("the store read failed\nno ref at origin/roadmap")
        with mock.patch.object(ruled_store, "stale_entries", side_effect=failure) as read:
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = ruled_store.main(["stale", self.root])
        self.assertTrue(read.called, "control: stale did not call the read that was patched to raise")
        self.assertEqual(code, 2, "stale returned %r when its read raised, want 2" % code)
        lines = err.getvalue().splitlines()
        self.assertEqual(len(lines), 1, "stale wrote %d stderr lines for one failure, want 1: %r" % (len(lines), lines))
        self.assertIn("the store read failed no ref at origin/roadmap", lines[0],
                      "the stderr line does not carry the error message: %r" % lines[0])


class CostAndCliTests(RepoCase):
    def test_reading_the_store_starts_one_ls_tree_and_one_cat_file(self):
        repo = self.make_repo("cost", store=fixture.ruling_files(
            {"r%d" % number: fixture.entry("r%d" % number) for number in range(6)}))
        trace = os.path.join(self.root, "git-trace.log")
        with mock.patch.dict(os.environ, {"GIT_TRACE": trace}):
            entries = ruled_store.ruled_entries(repo)
        self.assertEqual(len(entries), 6, "control: the six entries did not all read")
        starts = git_starts(trace)
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
    for folder in _RUN:
        shutil.rmtree(folder, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main(verbosity=2)
