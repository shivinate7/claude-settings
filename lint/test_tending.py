#!/usr/bin/env python3
"""Cases for lint/tending.py, the one runner of the prose-tending contract (decision prose-tending-contract).

    python3 lint/test_tending.py
    TENDING_UNDER_TEST=<absolute path to lint/tending_stub_test.py> python3 lint/test_tending.py   # the red run

Three groups. The contract group reads lint/layout.json only, so its reds are real on the old code. The runner
group loads the runner from TENDING_UNDER_TEST, else lint/tending.py; with no runner the load fails with an
assert that names the absent file. The stand-in lint/tending_stub_test.py is wrong on purpose, so each runner
case fails on an assert about a verdict, an exit code or a file. The cost cases pass on the stand-in, which
starts nothing: they are controls, and their red comes from a mutant after the build.

Shapes this file assumes, pinned in one place (the adapter `verdicts_of`, and the fixture helpers below):
  - layout "tending" is a dict keyed by store name; an entry is {where, item, still-true, close, runs-from, state}.
  - item is a regex whose group 1 is the id. Fixture items are `- <id> ...` lines.
  - tend(entry, text, root) returns {id: verdict} or [(id, verdict)]; verdict is true, stale or unknown.
  - close(entry, text, verdicts) returns the new text. mark appends " [closed]" to a stale item's line, after any
    ` repeats <ref>` tail and before a "\r"; delete drops a stale item's line; none changes nothing.
    Only stale items are closed.
  - home-held reads `Home: <path>` or `Home: step:<slug>`. A path is held when some ref tracks it; a step is held
    when roadmap/data/steps/<slug>.json is tracked on some ref.
  - until-date reads `until YYYY-MM-DD`; a past date is stale, a future date true.
  - cite-resolves reads `cites <id>`; the record is docs/decisions/<id>.md under the root.
  - copy-matches-live reads `copy of <path>: <text>`; the file at <path> under the root must hold <text> as a line.
  - command line: python3 lint/tending.py --point P [--store S] [--root R]. Exit 1 for a live store with a stale
    item that its close step cannot fix, or for a malformed contract. Exit 0 otherwise.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(ROOT, "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)

LAYOUT = os.path.join(HERE, "layout.json")
RUNNER = os.path.abspath(os.environ.get("TENDING_UNDER_TEST") or os.path.join(HERE, "tending.py"))
PLAN_STORES = ("decisions", "rules", "docs", "debts", "handoffs", "feedback-log", "roadmap", "queue",
               "page-copies", "mailbox")
FIELDS = ("where", "item", "still-true", "close", "runs-from", "state")
ITEM = r"^- (\S+) "
FIXED_MTIME = 978307200  # 2001-01-01T00:00:00Z, set on each file a run may rewrite, so a rewrite shows in mtime_ns
GIT_READS = ("ls-tree", "ls-files", "rev-parse", "cat-file", "for-each-ref", "show", "show-ref", "log", "grep")
TODO_HELD = "- A1 held. Home: lint/held.py\n"
TODO_STALE = "- A1 held. Home: lint/held.py\n- A2 gone. Home: lint/gone.py\n"

GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
for _name in ("BASE_SHA", "CI", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
    GIT_ENV.pop(_name, None)  # the outer shell's values never reach a fixture repo

RUN_FOLDER = None


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    if RUN_FOLDER and os.path.isdir(RUN_FOLDER):
        tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


def layout_data():
    with open(LAYOUT, encoding="utf-8") as f:
        return json.load(f)


def runner_path():
    """The runner under test. Its absence is an assert that names the file, and it is never raised at import."""
    if not os.path.isfile(RUNNER):
        raise AssertionError("the runner %s is absent on this commit" % RUNNER)
    return RUNNER


def load_runner():
    spec = importlib.util.spec_from_file_location("tending_under_test", runner_path())
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verdicts_of(runner, entry, text, root):
    """{id: verdict} from runner.tend(entry, text, root). The one place that reads tend's return shape."""
    result = runner.tend(entry, text, root)
    if isinstance(result, dict):
        return dict(result)
    return {pair[0]: pair[1] for pair in result}


def entry(still_true, close="mark", runs_from=("merge-check",), state="live", where="todo"):
    return {"where": where, "item": ITEM, "still-true": still_true, "close": close,
            "runs-from": list(runs_from), "state": state}


def write_files(root, files):
    for rel, text in files.items():
        path = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)


def make_repo(files):
    """A plain folder, not a git repo, holding `files`."""
    root = tempfile.mkdtemp(prefix="tending_repo_", dir=RUN_FOLDER)
    write_files(root, files)
    return root


def git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                   cwd=root, env=GIT_ENV, check=True, capture_output=True)


def make_git_repo(files):
    """A git repo on one commit holding `files`."""
    root = make_repo({})
    git(root, "init", "-q")
    write_files(root, files)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture")
    return root


GIT_VALUE_OPTIONS = ("-C", "-c")  # git's global options that take the next word as their value


def git_subcommand(argv):
    """The git subcommand of an argv, past the global options: `git [--literal-pathspecs] -C <dir> <read>`."""
    words = list(argv)[1:]
    while words and words[0].startswith("-"):
        words = words[2:] if words[0] in GIT_VALUE_OPTIONS else words[1:]
    return words[0] if words else None


def make_tree(tending=None):
    """A copy of lint/ and hooks/ under the run folder, the runner at lint/tending.py, and, when `tending` is
    given, the copy's layout "tending" key set to it. The real layout is never edited."""
    runner = runner_path()
    tree = tempfile.mkdtemp(prefix="tending_tree_", dir=RUN_FOLDER)
    tracked_tree.copy_tracked(tree, "lint", "hooks")
    shutil.copyfile(runner, os.path.join(tree, "lint", "tending.py"))
    if tending is not None:
        path = os.path.join(tree, "lint", "layout.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        data["tending"] = tending
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    return tree


def run_cli(tree, root, point="merge-check", store=None):
    cmd = [sys.executable, os.path.join(tree, "lint", "tending.py"), "--point", point, "--root", root]
    if store:
        cmd += ["--store", store]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=GIT_ENV)


def snapshot(root):
    """{relative path: (bytes, mtime_ns)} for every file under root, .git included."""
    found = {}
    for folder, _, names in os.walk(root):
        for name in names:
            path = os.path.join(folder, name)
            with open(path, "rb") as f:
                data = f.read()
            found[os.path.relpath(path, root)] = (data, os.stat(path).st_mtime_ns)
    return found


def changed(before, after):
    """The relative paths whose bytes or mtime differ between two snapshots, sorted."""
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def fix_mtimes(root):
    for folder, _, names in os.walk(root):
        for name in names:
            os.utime(os.path.join(folder, name), (FIXED_MTIME, FIXED_MTIME))


class CountingPopen(subprocess.Popen):
    """subprocess.Popen that records each argv it is asked to start."""
    started = []

    def __init__(self, *args, **kwargs):
        CountingPopen.started.append(args[0] if args else kwargs.get("args"))
        super().__init__(*args, **kwargs)


CHILD_PROBE = r"""
import importlib.util, json, subprocess, sys, threading
starts, thread_starts = [], []
real_popen, real_start = subprocess.Popen, threading.Thread.start
class Counting(real_popen):
    def __init__(self, *args, **kwargs):
        starts.append(str(args[0] if args else kwargs.get("args")))
        super().__init__(*args, **kwargs)
def counting_start(self):
    thread_starts.append(self.name)
    return real_start(self)
subprocess.Popen = Counting
threading.Thread.start = counting_start
before = set(threading.enumerate())
spec = importlib.util.spec_from_file_location("tending_under_test", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
new = [t.name for t in threading.enumerate() if t not in before]
print(json.dumps({"threads": new, "thread_starts": thread_starts, "child_starts": starts}))
"""


def probe_import():
    """What importing the runner in a fresh interpreter starts: threads, and child processes."""
    result = subprocess.run([sys.executable, "-c", CHILD_PROBE, runner_path()], capture_output=True,
                            text=True, timeout=120, env=GIT_ENV)
    if result.returncode != 0:
        raise AssertionError("importing the runner failed: %s" % result.stderr.strip())
    return json.loads(result.stdout)


# ---- Contract: lint/layout.json only. Real reds on the old code. -------------------------------------------

class ContractTests(unittest.TestCase):

    def store_entries(self):
        tending = layout_data().get("tending")
        self.assertTrue(tending, "lint/layout.json has no \"tending\" entries: the contract is not declared")
        return tending

    def test_layout_declares_a_tending_key(self):
        self.assertTrue("tending" in layout_data(), "lint/layout.json has no \"tending\" key")

    def test_every_store_entry_has_the_six_fields(self):
        for store, found in self.store_entries().items():
            with self.subTest(store=store):
                missing = [field for field in FIELDS if field not in found]
                self.assertEqual(missing, [], "store %s lacks the field(s) %s" % (store, ", ".join(missing)))

    def test_each_plan_store_has_an_entry(self):
        entries = self.store_entries()
        for store in PLAN_STORES:
            with self.subTest(store=store):
                self.assertTrue(store in entries, "the plan's store %s has no tending entry" % store)

    def test_each_where_is_a_layout_kind_or_an_external_store(self):
        kinds = set(layout_data()["kinds"])
        for store, found in self.store_entries().items():
            with self.subTest(store=store):
                where = found.get("where")
                if not isinstance(where, str):
                    self.fail("store %s: where %r is not a string" % (store, where))
                external = where.startswith("external:") and len(where) > len("external:")
                self.assertTrue(where in kinds or external,
                                "store %s: where %r is neither a layout kind nor external:<name>" % (store, where))


# ---- Runner: the verdicts, the close step, the command line, and the cost. --------------------------------

class VerdictTests(unittest.TestCase):

    def test_home_held_is_true_when_the_home_is_tracked(self):
        root = make_git_repo({"lint/held.py": "x\n"})
        got = verdicts_of(load_runner(), entry("home-held"), "- D1 decided. Home: lint/held.py\n", root)
        self.assertEqual(got, {"D1": "true"}, "a home tracked on main read as %r" % got)

    def test_home_held_is_stale_when_the_home_is_tracked_nowhere(self):
        root = make_git_repo({"lint/held.py": "x\n"})
        got = verdicts_of(load_runner(), entry("home-held"), "- D2 decided. Home: lint/gone.py\n", root)
        self.assertEqual(got, {"D2": "stale"}, "a home no ref tracks read as %r" % got)

    def test_home_held_is_true_for_a_step_on_another_branch(self):
        root = make_git_repo({"lint/held.py": "x\n"})
        git(root, "checkout", "-q", "-b", "other")
        write_files(root, {"roadmap/data/steps/alpha.json": "{}\n"})
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "step")
        git(root, "checkout", "-q", "-")
        text = "- S1 a step. Home: step:alpha\n- S2 a step. Home: step:beta\n"
        got = verdicts_of(load_runner(), entry("home-held"), text, root)
        self.assertEqual(got, {"S1": "true", "S2": "stale"},
                         "a step on some ref should be held, and one on no ref stale: read as %r" % got)

    def test_home_held_is_unknown_when_git_cannot_read_the_root(self):
        got = verdicts_of(load_runner(), entry("home-held"), "- D3 decided. Home: lint/held.py\n",
                          make_repo({}))
        self.assertEqual(got, {"D3": "unknown"}, "a read that cannot run read as %r, not unknown" % got)

    def test_until_date_in_the_past_is_stale(self):
        got = verdicts_of(load_runner(), entry("until-date"), "- U1 wait. until 2001-01-01\n", make_repo({}))
        self.assertEqual(got, {"U1": "stale"}, "a claim dated 2001-01-01 read as %r" % got)

    def test_until_date_in_the_future_is_true(self):
        got = verdicts_of(load_runner(), entry("until-date"), "- U2 wait. until 2999-12-31\n", make_repo({}))
        self.assertEqual(got, {"U2": "true"}, "a claim dated 2999-12-31 read as %r" % got)

    def test_cite_resolves_is_true_when_the_record_is_there(self):
        root = make_repo({"docs/decisions/decision-a.md": "# a\n"})
        got = verdicts_of(load_runner(), entry("cite-resolves"), "- C1 kept. cites decision-a\n", root)
        self.assertEqual(got, {"C1": "true"}, "a cite of a record that exists read as %r" % got)

    def test_cite_resolves_is_stale_when_the_record_is_gone(self):
        root = make_repo({"docs/decisions/decision-a.md": "# a\n"})
        got = verdicts_of(load_runner(), entry("cite-resolves"), "- C2 kept. cites gone-one\n", root)
        self.assertEqual(got, {"C2": "stale"}, "a cite of a record that is gone read as %r" % got)

    def test_copy_matches_live_is_true_when_the_copy_equals_its_source(self):
        root = make_repo({"docs/live.md": "alpha\n"})
        got = verdicts_of(load_runner(), entry("copy-matches-live"), "- K1 copy of docs/live.md: alpha\n", root)
        self.assertEqual(got, {"K1": "true"}, "a copy equal to its live source read as %r" % got)

    def test_copy_matches_live_is_stale_when_the_copy_differs(self):
        root = make_repo({"docs/live.md": "alpha\n"})
        got = verdicts_of(load_runner(), entry("copy-matches-live"), "- K2 copy of docs/live.md: beta\n", root)
        self.assertEqual(got, {"K2": "stale"}, "a copy that differs from its live source read as %r" % got)

    def test_copy_matches_live_is_unknown_when_the_live_source_is_missing(self):
        root = make_repo({"docs/live.md": "alpha\n"})
        got = verdicts_of(load_runner(), entry("copy-matches-live"), "- K3 copy of docs/absent.md: alpha\n", root)
        self.assertEqual(got, {"K3": "unknown"}, "a copy with no live source read as %r, not unknown" % got)

    def test_empty_store_has_no_verdicts(self):
        got = verdicts_of(load_runner(), entry("until-date"), "", make_repo({}))
        self.assertEqual(got, {}, "an empty store gave verdicts %r" % got)

    def test_full_size_store_gets_one_verdict_per_item(self):
        text = "".join("- U%d wait. until 2999-12-31\n" % n for n in range(400))
        got = verdicts_of(load_runner(), entry("until-date"), text, make_repo({}))
        self.assertEqual(len(got), 400, "a 400-item store gave %d verdicts" % len(got))
        self.assertEqual(set(got.values()), {"true"}, "a future-dated store gave verdicts %r" % sorted(set(got.values())))


class CloseTests(unittest.TestCase):

    def test_mark_appends_closed_after_the_repeats_tail(self):
        text = "- F1 do the thing repeats roadmap:x\n"
        out = load_runner().close(entry("home-held"), text, {"F1": "stale"})
        self.assertEqual(out, "- F1 do the thing repeats roadmap:x [closed]\n",
                         "the closed token did not follow the repeats tail: %r" % out)

    def test_mark_keeps_the_carriage_return_last(self):
        out = load_runner().close(entry("home-held"), "- F2 do it\r\n", {"F2": "stale"})
        self.assertEqual(out, "- F2 do it [closed]\r\n", "the token went after the carriage return: %r" % out)

    def test_mark_keeps_a_missing_final_newline_missing(self):
        out = load_runner().close(entry("home-held"), "- F5 a stale item", {"F5": "stale"})
        self.assertEqual(out, "- F5 a stale item [closed]", "a final line gained or lost its newline: %r" % out)

    def test_mark_is_idempotent(self):
        runner = load_runner()
        once = runner.close(entry("home-held"), "- F1 a\n- F2 b repeats debt:x [closed]\n",
                            {"F1": "stale", "F2": "stale"})
        twice = runner.close(entry("home-held"), once, {"F1": "stale", "F2": "stale"})
        self.assertEqual(twice, once, "a second mark changed the text again: %r" % twice)

    def test_mark_leaves_every_other_line_byte_identical(self):
        text = "# head\n\n- F3 stale one\nprose line with a trailing space  \n- F4 keep\n"
        out = load_runner().close(entry("home-held"), text, {"F3": "stale", "F4": "true"})
        self.assertEqual(out, "# head\n\n- F3 stale one [closed]\nprose line with a trailing space  \n- F4 keep\n",
                         "a line other than the stale item changed: %r" % out)

    def test_unknown_and_true_items_are_not_closed(self):
        text = "- F6 cannot read\n- F7 still true\n"
        out = load_runner().close(entry("home-held"), text, {"F6": "unknown", "F7": "true"})
        self.assertEqual(out, text, "an unknown or true item was closed: %r" % out)

    def test_none_changes_nothing(self):
        text = "- F8 stale\n"
        out = load_runner().close(entry("home-held", close="none"), text, {"F8": "stale"})
        self.assertEqual(out, text, "close none rewrote a stale item: %r" % out)

    def test_delete_drops_only_the_item_line(self):
        out = load_runner().close(entry("home-held", close="delete"), "# head\n- F9 gone\nkeep\n", {"F9": "stale"})
        self.assertEqual(out, "# head\nkeep\n", "delete changed more than the item line: %r" % out)

    def test_empty_text_stays_empty(self):
        out = load_runner().close(entry("home-held"), "", {})
        self.assertEqual(out, "", "an empty store was rewritten: %r" % out)

    def test_full_size_store_marks_every_stale_item_and_nothing_else(self):
        lines = ["- G%d stale item\n" % n for n in range(300)] + ["# closing prose\n"]
        verdicts = {"G%d" % n: "stale" for n in range(300)}
        out = load_runner().close(entry("home-held"), "".join(lines), verdicts).split("\n")
        self.assertEqual(sum(1 for line in out if line.endswith(" [closed]")), 300,
                         "a 300-item store did not get 300 closed tokens")
        self.assertEqual(out[-2], "# closing prose", "the prose line after the items changed")


class CommandLineTests(unittest.TestCase):
    """`python3 lint/tending.py --point merge-check --root <tmp>`, run from a copy of the tree."""

    def test_clean_repo_exits_0(self):
        result = run_cli(make_tree(), make_repo({}))
        self.assertEqual(result.returncode, 0, "a clean repo exited %d, not 0: %s" % (result.returncode, result.stderr))

    def test_live_store_with_a_stale_unfixable_item_exits_1(self):
        tree = make_tree({"probe": entry("home-held", close="none")})
        root = make_git_repo({"lint/held.py": "x\n", "docs/todo.md": TODO_STALE})
        result = run_cli(tree, root)
        self.assertEqual(result.returncode, 1, "a live store with a stale item close cannot fix exited %d, not 1"
                         % result.returncode)

    def test_live_store_with_a_stale_fixable_item_exits_0_and_marks_it(self):
        tree = make_tree({"probe": entry("home-held", close="mark")})
        root = make_git_repo({"lint/held.py": "x\n", "docs/todo.md": TODO_STALE})
        result = run_cli(tree, root)
        self.assertEqual(result.returncode, 0, "a stale item close can fix exited %d, not 0" % result.returncode)
        with open(os.path.join(root, "docs", "todo.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), TODO_HELD + "- A2 gone. Home: lint/gone.py [closed]\n",
                             "the fixable stale item was not marked, or another line changed")

    def test_declared_store_never_fails_the_point(self):
        tree = make_tree({"probe": entry("home-held", close="none", state="declared")})
        root = make_git_repo({"lint/held.py": "x\n", "docs/todo.md": TODO_STALE})
        result = run_cli(tree, root)
        self.assertEqual(result.returncode, 0, "a declared store failed the point with exit %d" % result.returncode)

    def test_entry_missing_close_exits_1(self):
        bad = entry("home-held")
        del bad["close"]
        tree = make_tree({"probe": bad})
        root = make_git_repo({"lint/held.py": "x\n", "docs/todo.md": TODO_HELD})
        result = run_cli(tree, root)
        self.assertEqual(result.returncode, 1, "an entry with no close key exited %d, not 1" % result.returncode)

    def test_entry_with_an_unknown_call_point_exits_1(self):
        tree = make_tree({"probe": entry("home-held", runs_from=("merge-chek",))})
        root = make_git_repo({"lint/held.py": "x\n", "docs/todo.md": TODO_HELD})
        result = run_cli(tree, root)
        self.assertEqual(result.returncode, 1, "an unknown call point exited %d, not 1" % result.returncode)

    def test_entry_with_an_unknown_still_true_name_exits_1(self):
        tree = make_tree({"probe": entry("no-such-test")})
        root = make_git_repo({"lint/held.py": "x\n", "docs/todo.md": TODO_HELD})
        result = run_cli(tree, root)
        self.assertEqual(result.returncode, 1, "an unknown still-true name exited %d, not 1" % result.returncode)


class CostTests(unittest.TestCase):
    """The cost the decision names: no process, timer or thread of its own, and no write when no verdict changed.
    On the stand-in these pass (it starts nothing), so they are controls for the mutant run."""

    def test_import_starts_no_thread_or_timer(self):
        self.assertEqual(probe_import()["threads"], [], "importing the runner left new threads running")

    def test_import_starts_no_thread(self):
        self.assertEqual(probe_import()["thread_starts"], [], "importing the runner started a thread")

    def test_import_starts_no_child_process(self):
        self.assertEqual(probe_import()["child_starts"], [], "importing the runner started a child process")

    def test_until_date_store_starts_no_child_process(self):
        runner, root = load_runner(), make_repo({})
        CountingPopen.started = []
        with mock.patch.object(subprocess, "Popen", CountingPopen):
            got = verdicts_of(runner, entry("until-date"), "- U1 x. until 2001-01-01\n- U2 y. until 2999-12-31\n", root)
        self.assertEqual(sorted(got), ["U1", "U2"], "scope: until-date read %r, not both items" % sorted(got))
        self.assertEqual(CountingPopen.started, [], "an until-date store started child processes")

    def test_home_held_store_starts_only_git_reads(self):
        runner = load_runner()
        root = make_git_repo({"lint/held.py": "x\n"})
        CountingPopen.started = []
        with mock.patch.object(subprocess, "Popen", CountingPopen):
            verdicts_of(runner, entry("home-held"), "- D1 a. Home: lint/held.py\n- D2 b. Home: lint/gone.py\n", root)
        started = CountingPopen.started
        self.assertTrue(started, "scope: the home-held read started no git process at all")
        for argv in started:
            self.assertEqual(os.path.basename(str(argv[0])), "git", "a home-held read started %r" % (argv,))
            self.assertIn(git_subcommand(argv), GIT_READS, "a home-held read started a git write: %r" % (argv,))

    def test_no_file_is_written_when_no_verdict_changed(self):
        tree = make_tree({"probe": entry("home-held", close="mark")})
        root = make_git_repo({"lint/held.py": "x\n", "docs/todo.md": TODO_HELD})
        fix_mtimes(root)
        before = snapshot(root)
        result = run_cli(tree, root)
        self.assertEqual(result.returncode, 0, "scope: the all-true run exited %d, not 0" % result.returncode)
        self.assertEqual(changed(before, snapshot(root)), [], "a run with no changed verdict rewrote a file")

    def test_a_changed_verdict_is_written(self):
        # The control for the case above: a snapshot that cannot see a write would pass that case for nothing.
        tree = make_tree({"probe": entry("home-held", close="mark")})
        root = make_git_repo({"lint/held.py": "x\n", "docs/todo.md": TODO_STALE})
        fix_mtimes(root)
        before = snapshot(root)
        result = run_cli(tree, root)
        self.assertEqual(result.returncode, 0, "scope: the fixable run exited %d, not 0" % result.returncode)
        self.assertTrue(changed(before, snapshot(root)),
                        "a stale fixable item was not written: the no-write case proves nothing")


if __name__ == "__main__":
    unittest.main()
