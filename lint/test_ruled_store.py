#!/usr/bin/env python3
"""Cases for lint/ruled_store.py, the one store of owner rulings not yet on main. Standard library only.

    python3 lint/test_ruled_store.py

The store is roadmap/rulings/<id>.json on origin/roadmap. Each case builds a real git repo under this run's folder
(lint/_test_temp.py) with the store helpers defined below, which point the refs with git plumbing, then call
the module's functions or runs its CLI. RULED_STORE_UNDER_TEST overrides the module path, as a mutant run needs.
hooks/test_session_start.py and hooks/test_question_form.py import this file as `fixture` for the same helpers.
"""
import importlib.util
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


def fetch_head(repo):
    """The path of the repo's FETCH_HEAD, as git names it. The age of origin/roadmap is this file's mtime."""
    return os.path.join(repo, git(repo, "rev-parse", "--git-path", "FETCH_HEAD"))


FETCH_ORIGIN = "fixture-origin"  # the URL git names in a FETCH_HEAD line; the helper reads only the branch name


def write_fetch_head(repo, branch="roadmap", when=None):
    """Writes the repo's FETCH_HEAD as one fetch of `branch`, with its mtime at `when` (an epoch second) or now. Git
    writes one such line per fetched branch; the roadmap ref is fresh only when the line names the roadmap."""
    path = fetch_head(repo)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("%s\t\tbranch '%s' of %s\n" % ("0" * 40, branch, FETCH_ORIGIN))
    os.utime(path, None if when is None else (when, when))


def set_fetch_head(repo, when=None):
    """The repo's FETCH_HEAD as a fetch of the roadmap branch, its mtime at `when` or now."""
    write_fetch_head(repo, "roadmap", when)


def without_fetch_head(repo):
    """Removes the repo's FETCH_HEAD, so origin/roadmap reads as never fetched."""
    path = fetch_head(repo)
    if os.path.exists(path):
        os.remove(path)


def ref_sha(repo, ref=STORE_REF):
    return git(repo, "rev-parse", ref)


def bare_origin(scratch, name, files):
    """A bare repo at scratch/<name>.git whose refs/heads/roadmap holds `files`. Returns its path."""
    path = os.path.join(scratch, name + ".git")
    git(scratch, "init", "--bare", "-q", path)
    point_ref(path, "refs/heads/roadmap", files, scratch)
    return path


def clone_with_origin(root, name, origin, files):
    """A repo whose origin/roadmap holds `files`, with `origin` as its origin remote when it is not None."""
    repo = init_repo(os.path.join(root, name))
    point_ref(repo, STORE_REF, files, root)
    if origin is not None:
        git(repo, "remote", "add", "origin", origin)
    return repo


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
        fixture.set_fetch_head(repo)
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
        fixture.set_fetch_head(repo)
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


def step_file(slug, status):
    """The roadmap step file a store ref carries for `slug`, with its status."""
    return {"roadmap/data/steps/%s.json" % slug: '{"slug": "%s", "status": "%s"}' % (slug, status)}


class CheckStoreTests(RepoCase):
    def store_with(self, name, entries, steps=None):
        files = fixture.ruling_files(entries)
        files.update(steps or {})
        return self.make_repo(name, store=files)

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


class CostAndCliTests(RepoCase):
    def test_reading_the_store_starts_one_ls_tree_and_one_cat_file(self):
        repo = self.make_repo("cost", store=fixture.ruling_files(
            {"r%d" % number: fixture.entry("r%d" % number) for number in range(6)}))
        fixture.set_fetch_head(repo)
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


NOTE_LINE = re.compile(r"read as of \d{2}:\d{2} (CST|CDT)")  # the note lint/roadmap_ref.py adds to a stale read


class StaleRefReadTests(RepoCase):
    """The store read fetches a stale origin/roadmap first, and says the read is as of a time when it cannot
    (lint/roadmap_ref.py). The helper's own cases are in lint/test_roadmap_ref.py."""

    def stale_pair(self):
        """(older, newer) store trees: the newer one adds the ruling `new`."""
        older = ruling_files({"old": entry("old")})
        return older, ruling_files({"old": entry("old"), "new": entry("new")})

    def test_a_stale_ref_is_fetched_before_the_store_is_read(self):
        older, newer = self.stale_pair()
        origin = bare_origin(self.root, "fetch-origin", older)
        repo = self.make_repo("fetch", store=older)
        git(repo, "remote", "add", "origin", origin)
        point_ref(origin, "refs/heads/roadmap", newer, self.root)
        without_fetch_head(repo)
        self.assertIn("new", ids(ruled_store.ruled_entries(repo)),
                      "the stale origin/roadmap was read without a fetch: the newer ruling is missing")

    def test_a_stale_ref_with_no_network_says_read_as_of_in_the_session_block(self):
        repo = self.make_repo("offline", store=ruling_files({"r-1": entry("r-1")}))
        git(repo, "remote", "add", "origin", os.path.join(self.root, "gone.git"))
        without_fetch_head(repo)
        lines = ruled_store.session_lines(repo)
        self.assertTrue(any(NOTE_LINE.search(line) for line in lines),
                        "the session block did not say the ref was read as of a time: %r" % lines)

    def test_a_fetch_cut_at_the_timeout_is_bounded_at_two_seconds_and_says_read_as_of(self):
        older, _newer = self.stale_pair()
        origin = bare_origin(self.root, "cut-origin", older)
        repo = self.make_repo("cut", store=older)
        git(repo, "remote", "add", "origin", origin)
        without_fetch_head(repo)
        real_run = subprocess.run
        started = []

        def cut(args, *rest, **kwargs):
            if isinstance(args, (list, tuple)) and "fetch" in args:
                started.append(kwargs.get("timeout"))
                raise subprocess.TimeoutExpired(args, kwargs.get("timeout"))
            return real_run(args, *rest, **kwargs)

        with mock.patch("subprocess.run", side_effect=cut):
            lines = ruled_store.session_lines(repo)
        self.assertEqual(started, [2.0], "the fetch was not started through subprocess with a 2.0 s timeout: %r"
                         % started)
        self.assertTrue(any(NOTE_LINE.search(line) for line in lines),
                        "a cut fetch did not leave the session block saying read as of: %r" % lines)

    def test_a_fresh_ref_is_read_without_a_fetch(self):
        older, newer = self.stale_pair()
        origin = bare_origin(self.root, "fresh-origin", older)
        repo = self.make_repo("fresh", store=older)
        git(repo, "remote", "add", "origin", origin)
        point_ref(origin, "refs/heads/roadmap", newer, self.root)
        set_fetch_head(repo)
        before = ref_sha(repo)
        entries = ruled_store.ruled_entries(repo)
        self.assertNotIn("new", ids(entries), "a fresh ref was fetched: the newer ruling was read")
        self.assertEqual(ref_sha(repo), before, "a fresh ref moved")

    def test_the_session_block_carries_the_note_the_helper_returns(self):
        repo = self.make_repo("carry", store=ruling_files({"r-1": entry("r-1")}))
        helper = mock.Mock()
        helper.fresh_ref.return_value = "read as of 11:05 CST"
        with mock.patch.dict(sys.modules, {"roadmap_ref": helper}):
            lines = load_module().session_lines(repo)
        self.assertTrue(any("read as of 11:05 CST" in line for line in lines),
                        "the session block dropped the note the helper returned: %r" % lines)

    def test_each_store_read_calls_the_helper_once(self):
        repo = self.make_repo("once", store=ruling_files({"r-1": entry("r-1")}))
        helper = mock.Mock()
        helper.fresh_ref.return_value = ""
        with mock.patch.dict(sys.modules, {"roadmap_ref": helper}):
            module = load_module()
            module.ruled_entries(repo)
            once = helper.fresh_ref.call_count
            module.read_store(repo)
            twice = helper.fresh_ref.call_count
        self.assertEqual(once, 1, "ruled_entries called the helper %d times, want 1" % once)
        self.assertEqual(twice, 2, "read_store did not add one call to the helper: %d in all, want 2" % twice)

    def test_an_offline_stale_ref_is_not_a_store_problem(self):
        clean = self.make_repo("offline-clean", store=ruling_files({"ok": entry("ok")}))
        git(clean, "remote", "add", "origin", os.path.join(self.root, "gone-clean.git"))
        without_fetch_head(clean)
        self.assertEqual(ruled_store.check_store(clean), [],
                         "a stale ref with no network counted as a store problem")


def tearDownModule():
    for folder in _RUN:
        shutil.rmtree(folder, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main(verbosity=2)
