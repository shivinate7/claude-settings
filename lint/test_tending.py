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
import ast
import builtins
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


WORST = {"true": 0, "unknown": 1, "stale": 2}  # the rank a repeated id keeps: its worst verdict


def line_rows(runner, entry, text, root):
    """[(key, id, verdict)] from runner.tend(entry, text, root): one row per open item line, in file order. The one
    place that reads tend's return shape. A dict (one verdict per id, so repeated ids merge) gives rows with no key."""
    result = runner.tend(entry, text, root)
    if isinstance(result, dict):
        return [(None, ident, verdict) for ident, verdict in result.items()]
    return [tuple(row) for row in result]


def verdicts_of(runner, entry, text, root):
    """{id: verdict}, each id's worst verdict over its lines. The shape the one-verdict-per-id cases read."""
    worst = {}
    for _, ident, verdict in line_rows(runner, entry, text, root):
        if ident not in worst or WORST[verdict] > WORST[worst[ident]]:
            worst[ident] = verdict
    return worst


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


FEEDBACK_LINES = (  # the real line forms of a feedback-log item (hooks/feedback_guard.py, decision owner-feedback-inbox)
    ("- fb-0958-1 [ruling] -> decisions/a-ruling.md", "fb-0958-1"),
    ("- fb-0958-2 [task] -> debts/a-task.md repeats roadmap:wheel-speed", "fb-0958-2"),
    ("- fb-0958-3 [ruling] -> decisions/a-ruling.md [closed]", "fb-0958-3"),
    ("- fb-0958-4 [task] -> step:wheel-speed", "fb-0958-4"),
)


class FeedbackLogContractTests(unittest.TestCase):
    """The feedback log is the first live store (plan prose-tending-contract, step feedback-log-tends-itself, R27)."""

    def feedback_entry(self):
        entry = layout_data().get("tending", {}).get("feedback-log")
        self.assertIsNotNone(entry, "lint/layout.json's tending key has no feedback-log entry")
        return entry

    def test_feedback_log_is_live(self):
        state = self.feedback_entry().get("state")
        self.assertEqual(state, "live", "the feedback-log store is %r, not live: no call point runs it" % state)

    def test_feedback_log_runs_from_stop_and_compact(self):
        points = sorted(self.feedback_entry().get("runs-from", []))
        self.assertEqual(points, ["compact", "stop"],
                         "the feedback-log store runs from %r, not from stop and compact" % points)

    def test_feedback_log_item_regex_reads_the_real_line_form(self):
        item = self.feedback_entry().get("item", "")
        for line, want in FEEDBACK_LINES:
            with self.subTest(line=line):
                found = re.search(item, line)
                got = found.group(1) if found and found.groups() else None
                self.assertEqual(got, want, "the item regex reads %r as %r, not %r" % (line, got, want))


class FeedbackLogCommandLineTests(unittest.TestCase):
    """The runner's command line reads the feedback log at stop and at compact: the caller supplies its text."""

    def test_feedback_log_is_read_at_stop_and_compact(self):
        root = make_git_repo({"README.md": "x\n"})
        for point in ("stop", "compact"):
            with self.subTest(point=point):
                result = run_cli(make_tree(), root, point=point, store="feedback-log")
                self.assertIn("tending: unknown feedback-log: caller supplies text", result.stdout,
                              "at %s the runner printed %r, not the caller-supplies line" % (point, result.stdout))


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
        # Ruling B: marking happens at a closing point (stop), never at merge-check.
        tree = make_tree({"probe": entry("home-held", close="mark", runs_from=("stop",))})
        root = make_git_repo({"lint/held.py": "x\n", "docs/todo.md": TODO_STALE})
        result = run_cli(tree, root, point="stop")
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
        # Ruling B: the write is seen at a closing point (stop), never at merge-check.
        tree = make_tree({"probe": entry("home-held", close="mark", runs_from=("stop",))})
        root = make_git_repo({"lint/held.py": "x\n", "docs/todo.md": TODO_STALE})
        fix_mtimes(root)
        before = snapshot(root)
        result = run_cli(tree, root, point="stop")
        self.assertEqual(result.returncode, 0, "scope: the fixable run exited %d, not 0" % result.returncode)
        self.assertTrue(changed(before, snapshot(root)),
                        "a stale fixable item was not written: the no-write case proves nothing")


# ---- Rules A-E. Each case below asserts its rule on the runner at lint/tending.py, except the
# ---- controls, which pass on it and hold a rule's positive side. -----------------------------------------------

def probe_tree(close="mark", runs_from=("merge-check",), still_true="home-held"):
    """A tree whose only contract entry is the live store `probe`, over docs/todo.md."""
    return make_tree({"probe": entry(still_true, close=close, runs_from=runs_from)})


def stale_repo():
    """A git repo whose docs/todo.md holds one stale item (A2): its home is not tracked on any ref."""
    return make_git_repo({"lint/held.py": "x\n", "docs/todo.md": TODO_STALE})


def hook_module(name):
    """A hooks/ module by name: the resolver the runner must agree with (ruling E)."""
    folder = os.path.join(ROOT, "hooks")
    if folder not in sys.path:
        sys.path.insert(0, folder)
    return __import__(name)


class MissingOrUnreadableStoreTests(unittest.TestCase):
    """Ruling A: a live store whose file is missing fails the point and names the store and the file. A file
    that cannot be read is one `unknown <store>: <why>` line, and the exit stays 0."""

    def test_live_store_with_no_file_exits_1(self):
        root = make_git_repo({"lint/held.py": "x\n"})  # no docs/todo.md
        result = run_cli(probe_tree(close="none"), root)
        self.assertEqual(result.returncode, 1, "a live store whose file is missing exited %d, not 1" % result.returncode)

    def test_live_store_with_no_file_names_the_store_and_the_file(self):
        root = make_git_repo({"lint/held.py": "x\n"})
        result = run_cli(probe_tree(close="none"), root)
        named = [line for line in result.stdout.splitlines()
                 if "FAIL" in line and "probe" in line and "docs/todo.md" in line]
        self.assertTrue(named, "no FAIL line names store probe and file docs/todo.md: %r" % result.stdout)

    def test_non_utf8_store_file_is_one_unknown_line_and_exit_0(self):
        root = make_git_repo({"lint/held.py": "x\n", "docs/todo.md": TODO_HELD})
        with open(os.path.join(root, "docs", "todo.md"), "wb") as f:
            f.write(b"- A1 held. Home: lint/held.py\n\xff\xfe\n")
        result = run_cli(probe_tree(close="none"), root)
        self.assertEqual(result.returncode, 0, "a non-UTF-8 store exited %d, not 0" % result.returncode)
        unknown = [line for line in result.stdout.splitlines() if "unknown probe:" in line]
        self.assertEqual(len(unknown), 1, "a non-UTF-8 store gave %d `unknown probe:` line(s), not 1: %r"
                         % (len(unknown), result.stdout))


class MergeCheckWritesNothingTests(unittest.TestCase):
    """Ruling B: at merge-check nothing is written. A stale item that close would mark fails the point with a
    `stale <id>` line, and the store file stays byte-identical. Closing happens at stop, compact and triage-status."""

    def test_merge_check_exits_1_on_a_stale_mark_item(self):
        result = run_cli(probe_tree(close="mark"), stale_repo())
        self.assertEqual(result.returncode, 1, "merge-check on a stale mark item exited %d, not 1" % result.returncode)

    def test_merge_check_names_the_stale_id_on_a_stale_line(self):
        result = run_cli(probe_tree(close="mark"), stale_repo())
        self.assertTrue(any("stale A2" in line for line in result.stdout.splitlines()),
                        "no `stale A2` line at merge-check: %r" % result.stdout)

    def test_merge_check_leaves_the_store_file_byte_identical(self):
        root = stale_repo()
        path = os.path.join(root, "docs", "todo.md")
        with open(path, "rb") as f:
            before = f.read()
        run_cli(probe_tree(close="mark"), root)
        with open(path, "rb") as f:
            after = f.read()
        self.assertEqual(after, before, "merge-check rewrote docs/todo.md")

    def test_stop_compact_and_triage_status_close_the_stale_item(self):
        # A control: the closing points already close. Each point gets its own store, so the point alone decides.
        for point in ("stop", "compact", "triage-status"):
            with self.subTest(point=point):
                root = stale_repo()
                result = run_cli(probe_tree(close="mark", runs_from=(point,)), root, point=point)
                self.assertEqual(result.returncode, 0, "%s on a stale mark item exited %d, not 0"
                                 % (point, result.returncode))
                with open(os.path.join(root, "docs", "todo.md"), encoding="utf-8") as f:
                    self.assertIn("A2 gone. Home: lint/gone.py [closed]", f.read(), "%s did not close A2" % point)


class CloseMarksOnlyItsOwnStaleLineTests(unittest.TestCase):
    """Ruling C: close marks a line by its own verdict, never every line that shares its id."""

    def test_repeated_id_closes_only_its_stale_line(self):
        root = make_git_repo({"docs/todo.md": "- D1 until 2020-01-01\n- D1 until 2099-01-01\n"})
        result = run_cli(probe_tree(close="mark", still_true="until-date", runs_from=("stop",)), root, point="stop")
        self.assertEqual(result.returncode, 0, "scope: the stop run exited %d, not 0" % result.returncode)
        with open(os.path.join(root, "docs", "todo.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "- D1 until 2020-01-01 [closed]\n- D1 until 2099-01-01\n",
                             "close marked a line whose own verdict is not stale")

    def test_dict_verdict_does_not_close_lines_that_share_an_id(self):
        # Two open lines share the id F1. A dict verdict {id: verdict} gives one verdict for the id, so it must not
        # rewrite either line. If that route is dropped, close refuses the dict or ignores it: no line changes.
        runner, text = load_runner(), "- F1 a\n- F1 b\n"
        rows = line_rows(runner, entry("home-held"), text, make_repo({}))
        self.assertEqual([ident for _, ident, _ in rows], ["F1", "F1"],
                         "scope: the two lines are not both open items with id F1: %r" % (rows,))
        try:
            out = runner.close(entry("home-held"), text, {"F1": "stale"})
        except (TypeError, ValueError):
            return  # the dict route is dropped, and close refuses it: no line is rewritten
        self.assertEqual(out, text, "a dict verdict rewrote a line that shares its id with a stale line: %r" % out)


class UnknownShapeTests(unittest.TestCase):
    """Ruling D: a live-store line that starts like an item but that the item regex does not match is reported
    as `unknown <store>: shape`, never passed over in silence."""

    def test_item_shaped_line_the_regex_misses_is_reported_as_unknown_shape(self):
        root = make_git_repo({"docs/todo.md": "- U1 wait. until 2999-12-31\n* D3 until 2020-01-01\n"})
        result = run_cli(probe_tree(close="none", still_true="until-date"), root)
        self.assertTrue(any("unknown probe: shape" in line for line in result.stdout.splitlines()),
                        "a `* D3` line in a live store passed in silence: %r" % result.stdout)

    def test_a_store_of_plain_items_prints_no_shape_line(self):
        # A control: a clean store prints nothing about shape.
        root = make_git_repo({"docs/todo.md": "- U1 wait. until 2999-12-31\n"})
        result = run_cli(probe_tree(close="none", still_true="until-date"), root)
        self.assertFalse(any("shape" in line for line in result.stdout.splitlines()),
                         "a clean store printed a shape line: %r" % result.stdout)


class ResolverAgreementTests(unittest.TestCase):
    """Ruling E: a home is judged as the repo's resolver judges it. A step home is the file hooks/feedback_guard.py
    STEP_PATH names, resolved by hooks/ruling_home.py value_resolves. A `Home:` value is the whole value, as
    ruling_home.check_file reads it. The runner's verdict must equal the resolver's on the same inputs."""

    def test_step_home_agrees_with_the_resolver_when_the_step_file_is_committed(self):
        feedback, ruling = hook_module("feedback_guard"), hook_module("ruling_home")
        root = make_git_repo({"lint/held.py": "x\n", "roadmap/data/steps/alpha.json": "{}\n"})
        self.assertTrue(ruling.value_resolves(feedback.STEP_PATH % "alpha", root),
                        "scope: the resolver does not hold the committed step file")
        expected = "true" if ruling.value_resolves(feedback.STEP_PATH % "alpha", root) else "stale"
        got = verdicts_of(load_runner(), entry("home-held"), "- S1 a step. Home: step:alpha\n", root)
        self.assertEqual(got.get("S1"), expected, "step:alpha: the runner says %r, the resolver says %r"
                         % (got.get("S1"), expected))

    def test_step_home_agrees_with_the_resolver_when_the_step_file_is_absent(self):
        feedback, ruling = hook_module("feedback_guard"), hook_module("ruling_home")
        root = make_git_repo({"lint/held.py": "x\n"})
        expected = "true" if ruling.value_resolves(feedback.STEP_PATH % "alpha", root) else "stale"
        self.assertEqual(expected, "stale", "scope: the resolver holds a step file that was never committed")
        got = verdicts_of(load_runner(), entry("home-held"), "- S2 a step. Home: step:alpha\n", root)
        self.assertEqual(got.get("S2"), expected, "step:alpha with no file: the runner says %r, the resolver says %r"
                         % (got.get("S2"), expected))

    def test_parenthetical_home_agrees_with_the_resolver_on_the_whole_value(self):
        ruling = hook_module("ruling_home")
        root = make_git_repo({"lint/held.py": "x\n", "docs/x.md": "# x\n"})
        self.assertTrue(ruling.value_resolves("docs/x.md", root), "scope: the resolver does not hold docs/x.md")
        expected = "true" if ruling.value_resolves("docs/x.md (note)", root) else "stale"
        got = verdicts_of(load_runner(), entry("home-held"), "- H1 a note. Home: docs/x.md (note)\n", root)
        self.assertEqual(got.get("H1"), expected, "`Home: docs/x.md (note)`: the runner says %r, the resolver says %r"
                         % (got.get("H1"), expected))

    def test_plain_home_agrees_with_the_resolver(self):
        # A control: a bare path that resolves reads true on both.
        ruling = hook_module("ruling_home")
        root = make_git_repo({"lint/held.py": "x\n", "docs/x.md": "# x\n"})
        self.assertTrue(ruling.value_resolves("docs/x.md", root), "scope: the resolver does not hold docs/x.md")
        got = verdicts_of(load_runner(), entry("home-held"), "- H2 a note. Home: docs/x.md\n", root)
        self.assertEqual(got, {"H2": "true"}, "a bare path the resolver holds read as %r" % got)

    def test_copied_path_checks_agree_with_the_resolver_from_a_subfolder(self):
        # The runner repeats value_resolves's path checks. Git reads `../x` from the cwd, so from sub/ it names the
        # top-level x, a blob: only the checks keep that value from reading as held, as the resolver refuses it.
        ruling, runner = hook_module("ruling_home"), load_runner()
        repo = make_git_repo({"x": "top\n", "sub/keep.txt": "k\n", "lint/held.py": "x\n"})
        sub = os.path.join(repo, "sub")
        self.assertTrue(ruling.value_resolves("x", repo), "scope: the resolver does not hold the top-level x")
        self.assertFalse(ruling.value_resolves("../x", sub), "scope: the resolver holds ../x from sub/")
        for value in ("/abs", ".", "..", "../x"):
            with self.subTest(value=value):
                expected = "true" if ruling.value_resolves(value, sub) else "stale"
                got = verdicts_of(runner, entry("home-held"), "- P1 a path. Home: %s\n" % value, sub)
                self.assertEqual(got, {"P1": expected}, "Home: %s from a subfolder: the runner says %r, the resolver "
                                 "says %r" % (value, got.get("P1"), expected))


def settling_names(path, name):
    """The names a module-level `name` is built from, read with ast: each Name and Attribute in its value, builtins
    left out. None when the module assigns no `name` at its top level."""
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), path)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            used = {n.id for n in ast.walk(value) if isinstance(n, ast.Name)}
            used |= {n.attr for n in ast.walk(value) if isinstance(n, ast.Attribute)}
            return used - set(dir(builtins))
    return None


class SettlingKindsOneHomeTests(unittest.TestCase):
    """Ruling: the kinds that settle on their file home have one home. feedback_guard's SETTLING_PREFIXES (the Stop's
    `[kind]` prefixes) and the runner's SETTLING_KINDS (the bare kind words) name the same kinds, and one of the two is
    built from the other, or both are built from one shared name. Two literal lists agree until one of them is edited."""

    def test_the_two_lists_name_the_same_kinds(self):
        feedback, runner = hook_module("feedback_guard"), load_runner()
        self.assertTrue(feedback.SETTLING_PREFIXES, "scope: feedback_guard.SETTLING_PREFIXES is empty")
        prefixes = tuple(p.strip("[]") for p in feedback.SETTLING_PREFIXES)
        self.assertEqual(prefixes, tuple(runner.SETTLING_KINDS),
                         "settling kinds: the Stop's prefixes name %r, the runner's kinds name %r"
                         % (prefixes, tuple(runner.SETTLING_KINDS)))

    def test_one_list_is_built_from_the_other_or_both_from_one_source(self):
        kinds = settling_names(runner_path(), "SETTLING_KINDS")
        prefixes = settling_names(hook_module("feedback_guard").__file__, "SETTLING_PREFIXES")
        self.assertIsNotNone(kinds, "scope: lint/tending.py assigns no module-level SETTLING_KINDS")
        self.assertIsNotNone(prefixes, "scope: hooks/feedback_guard.py assigns no module-level SETTLING_PREFIXES")
        one_names_the_other = "SETTLING_PREFIXES" in kinds or "SETTLING_KINDS" in prefixes
        self.assertTrue(one_names_the_other or bool(kinds & prefixes),
                        "two literal homes: lint/tending.py SETTLING_KINDS and hooks/feedback_guard.py "
                        "SETTLING_PREFIXES are not built from each other or from one shared name")


class RuleHomeTests(unittest.TestCase):
    """Triage ruling (rule git-cite-by-id, the rules store): `Home: rule:<id>` is a home when the anchor
    `<!-- rule:<id> -->` is in CLAUDE.md. lint/check_ruling_kind.py home_problem accepts that form. The runner reads it
    as a file path, so every rule home reads stale. hooks/ruling_home.py value_resolves has no rule form, so these
    cases do not compare with it: the oracle is the anchor's presence in the fixture's CLAUDE.md."""

    ANCHOR = "<!-- rule:some-id -->"
    FORMS = ("Home: rule:some-id", "- Home: rule:some-id", "home: rule:some-id", "- home: rule:some-id")

    def test_rule_home_with_its_anchor_in_claude_md_reads_true(self):
        text = "# Rules\n\n## A rule\n\n%s\n" % self.ANCHOR
        root = make_git_repo({"CLAUDE.md": text, "lint/held.py": "x\n"})
        self.assertIn(self.ANCHOR, text, "scope: the fixture CLAUDE.md does not hold the anchor")
        got = verdicts_of(load_runner(), entry("home-held"), "- R1 a rule. Home: rule:some-id\n", root)
        self.assertEqual(got, {"R1": "true"}, "Home: rule:some-id with its anchor in CLAUDE.md read as %r, not true"
                         % got)

    def test_rule_home_is_held_when_its_anchor_is_the_last_of_many(self):
        text = "".join("<!-- rule:r%03d -->\n" % i for i in range(300)) + self.ANCHOR + "\n"
        root = make_git_repo({"CLAUDE.md": text, "lint/held.py": "x\n"})
        self.assertIn(self.ANCHOR, text, "scope: the fixture CLAUDE.md does not hold the anchor")
        got = verdicts_of(load_runner(), entry("home-held"), "- R2 a rule. Home: rule:some-id\n", root)
        self.assertEqual(got, {"R2": "true"}, "Home: rule:some-id, the last of 301 anchors, read as %r, not true" % got)

    def test_rule_home_with_no_anchor_in_claude_md_reads_stale(self):
        text = "# Rules\n\n<!-- rule:other-id -->\n"
        root = make_git_repo({"CLAUDE.md": text, "lint/held.py": "x\n"})
        self.assertNotIn(self.ANCHOR, text, "scope: the fixture CLAUDE.md holds the anchor")
        got = verdicts_of(load_runner(), entry("home-held"), "- R3 a rule. Home: rule:some-id\n", root)
        self.assertEqual(got, {"R3": "stale"}, "Home: rule:some-id with no anchor in CLAUDE.md read as %r, not stale"
                         % got)

    def test_each_rule_home_line_shape_reads_true_with_its_anchor(self):
        decisions, runner = layout_data()["tending"]["decisions"], load_runner()
        root = make_git_repo({"CLAUDE.md": "# Rules\n\n%s\n" % self.ANCHOR, "lint/held.py": "x\n"})
        for line in self.FORMS:
            with self.subTest(line=line):
                rows = line_rows(runner, decisions, line + "\n", root)
                self.assertEqual(len(rows), 1, "the decisions store gave %d row(s) for %r, not one: the line is silent"
                                 % (len(rows), line))
                self.assertEqual([(ident, verdict) for _, ident, verdict in rows], [("rule:some-id", "true")],
                                 "%r with its anchor in CLAUDE.md is not read as held" % line)


# ---- The import route per line, skipped stores, and a byte-order mark. Each case asserts its rule, except
# ---- the controls, which hold a rule's positive side.

REPEATED_D1 = "- D1 until 2020-01-01\n- D1 until 2099-01-01\n"
REPEATED_D1_ONE_CLOSED = "- D1 until 2020-01-01 [closed]\n- D1 until 2099-01-01\n"


class PerLineRouteTests(unittest.TestCase):
    """Ruling 1: tend gives one verdict per line, so a repeated id does not merge. close, called on tend's output,
    closes only the stale line. The command line and the import route give the same text."""

    def test_tend_gives_one_row_per_line_for_a_repeated_id(self):
        rows = line_rows(load_runner(), entry("until-date"), REPEATED_D1, make_repo({}))
        self.assertEqual([(ident, verdict) for _, ident, verdict in rows], [("D1", "stale"), ("D1", "true")],
                         "tend merged the two D1 lines into one verdict: got %r" % (rows,))

    def test_import_close_marks_only_the_stale_line(self):
        runner, root = load_runner(), make_repo({})
        out = runner.close(entry("until-date"), REPEATED_D1, runner.tend(entry("until-date"), REPEATED_D1, root))
        self.assertEqual(out, REPEATED_D1_ONE_CLOSED, "the import route closed a line whose own verdict is not stale")

    def test_command_line_and_import_give_the_same_text(self):
        runner = load_runner()
        root = make_git_repo({"docs/todo.md": REPEATED_D1})
        import_text = runner.close(entry("until-date"), REPEATED_D1, runner.tend(entry("until-date"), REPEATED_D1, root))
        self.assertEqual(import_text, REPEATED_D1_ONE_CLOSED, "scope: the import route did not close only the stale line")
        run_cli(probe_tree(close="mark", still_true="until-date", runs_from=("stop",)), root, point="stop")
        with open(os.path.join(root, "docs", "todo.md"), encoding="utf-8") as f:
            cli_text = f.read()
        self.assertEqual(cli_text, import_text, "the command line and the import route close different lines")


class SkippedStoreTests(unittest.TestCase):
    """Ruling 2: a store named with --store that the point does not read prints one `skipped <store>: <why>` line
    and exits 0, never silence."""

    def test_declared_store_named_with_store_prints_one_skipped_line(self):
        tree = make_tree({"probe": entry("home-held", close="mark", state="declared")})
        root = make_git_repo({"lint/held.py": "x\n", "docs/todo.md": TODO_STALE})
        result = run_cli(tree, root, store="probe")
        self.assertEqual(result.returncode, 0, "a declared store named with --store exited %d, not 0" % result.returncode)
        skipped = [line for line in result.stdout.splitlines() if "skipped probe:" in line]
        self.assertEqual(len(skipped), 1, "a declared store named with --store printed %d `skipped probe:` line(s), "
                         "not 1: %r" % (len(skipped), result.stdout))

    def test_live_store_that_does_not_run_from_the_point_prints_one_skipped_line(self):
        tree = make_tree({"probe": entry("home-held", close="none", runs_from=("stop",))})
        root = make_git_repo({"lint/held.py": "x\n", "docs/todo.md": TODO_HELD})
        result = run_cli(tree, root, point="merge-check", store="probe")
        self.assertEqual(result.returncode, 0, "a live store off its point, named with --store, exited %d, not 0"
                         % result.returncode)
        skipped = [line for line in result.stdout.splitlines() if "skipped probe:" in line]
        self.assertEqual(len(skipped), 1, "a live store off its point printed %d `skipped probe:` line(s), not 1: %r"
                         % (len(skipped), result.stdout))

    def test_store_that_runs_from_the_point_prints_no_skipped_line(self):
        # A control: a store the point reads is read, and nothing is skipped.
        tree = make_tree({"probe": entry("home-held", close="none")})
        root = make_git_repo({"lint/held.py": "x\n", "docs/todo.md": TODO_HELD})
        result = run_cli(tree, root, store="probe")
        self.assertFalse(any("skipped" in line for line in result.stdout.splitlines()),
                         "a store the point reads printed a skipped line: %r" % result.stdout)


class ByteOrderMarkTests(unittest.TestCase):
    """Ruling 3: a UTF-8 byte-order mark before the first bullet does not drop that item."""

    def test_bom_before_the_first_bullet_still_reads_the_item(self):
        root = make_git_repo({"lint/held.py": "x\n"})
        rows = line_rows(load_runner(), entry("home-held"), "﻿- A1 held. Home: lint/held.py\n", root)
        self.assertEqual([(ident, verdict) for _, ident, verdict in rows], [("A1", "true")],
                         "a byte-order mark before the first bullet dropped A1: got %r" % (rows,))

    def test_bom_store_with_a_stale_first_item_fails_merge_check(self):
        root = make_git_repo({"lint/held.py": "x\n", "docs/todo.md": TODO_HELD})
        with open(os.path.join(root, "docs", "todo.md"), "wb") as f:
            f.write(b"\xef\xbb\xbf- A2 gone. Home: lint/gone.py\n")
        result = run_cli(probe_tree(close="none"), root)
        self.assertEqual(result.returncode, 1, "a store whose first item carries a byte-order mark and is stale "
                         "exited %d, not 1: the item was dropped" % result.returncode)


class ReadsOncePerRunTests(unittest.TestCase):
    """Cost (the runner's docstring, Cost): one run lists the refs once, and reads each distinct home once, however
    many files its store holds. Counted as the git process starts of one in-process `main` run."""

    def counted_run(self, root, store):
        """(exit code, git subcommands started) for `main --point merge-check` over one live store `probe`."""
        runner = load_runner()
        CountingPopen.started = []
        with mock.patch.object(runner.layout, "tending", return_value={"probe": store}), \
                mock.patch.object(subprocess, "Popen", CountingPopen), contextlib.redirect_stdout(io.StringIO()):
            code = runner.main(["--point", "merge-check", "--root", root])
        return code, [git_subcommand(argv) for argv in CountingPopen.started]

    def eight_file_store(self):
        """A live decisions store of 8 files that all name one home, lint/held.py, which is tracked."""
        files = {"docs/decisions/d%02d.md" % n: "- D%d decided. Home: lint/held.py\n" % n for n in range(8)}
        files["lint/held.py"] = "x\n"
        return make_git_repo(files)

    def test_store_of_several_files_lists_refs_once_per_run(self):
        code, started = self.counted_run(self.eight_file_store(), entry("home-held", close="none", where="decisions"))
        self.assertEqual(code, 0, "scope: the all-true store exited %d, not 0" % code)
        self.assertIn("for-each-ref", started, "scope: the run listed no refs, so the count below proves nothing")
        self.assertLessEqual(started.count("for-each-ref"), 1,
                             "an 8-file store listed the refs %d times in one run, not once" % started.count("for-each-ref"))

    def test_store_of_several_files_reads_each_home_once_per_run(self):
        code, started = self.counted_run(self.eight_file_store(), entry("home-held", close="none", where="decisions"))
        self.assertEqual(code, 0, "scope: the all-true store exited %d, not 0" % code)
        self.assertIn("cat-file", started, "scope: the run read no home, so the count below proves nothing")
        self.assertLessEqual(started.count("cat-file"), 1,
                             "an 8-file store read its one home %d times in one run, not once" % started.count("cat-file"))

    def test_empty_store_lists_refs_at_most_once(self):
        # A control for the empty state: a store folder with no item file. It may start no git read, and never two.
        files = {"docs/decisions/.keep": "\n", "lint/held.py": "x\n"}
        code, started = self.counted_run(make_git_repo(files), entry("home-held", close="none", where="decisions"))
        self.assertEqual(code, 0, "scope: the empty store exited %d, not 0" % code)
        self.assertLessEqual(started.count("for-each-ref"), 1,
                             "an empty store listed the refs %d times in one run, not at most once" % started.count("for-each-ref"))
        self.assertLessEqual(started.count("cat-file"), 1,
                             "an empty store read a home %d times in one run, not at most once" % started.count("cat-file"))


class DecisionsHomeFormTests(unittest.TestCase):
    """The decisions store reads the home lines hooks/ruling_home.py reads: HOME_RE, the `home:` form with an optional
    bullet, in any case. An item regex that misses such a line is silence, so each form must yield a row."""

    FORMS = ("Home: lint/held.py", "- Home: lint/held.py", "home: lint/held.py", "- home: lint/held.py")

    def test_decisions_item_regex_matches_every_form_the_resolver_reads_as_a_home(self):
        ruling = hook_module("ruling_home")
        item = re.compile(layout_data()["tending"]["decisions"]["item"], re.M)
        for line in self.FORMS:
            with self.subTest(line=line):
                self.assertIsNotNone(ruling.HOME_RE.search(line),
                                     "scope: the resolver does not read %r as a home" % line)
                self.assertIsNotNone(item.search(line),
                                     "the decisions item regex misses %r, which the resolver reads as a home" % line)

    def test_each_home_form_gets_a_row_or_an_unknown(self):
        decisions, runner = layout_data()["tending"]["decisions"], load_runner()
        root = make_git_repo({"lint/held.py": "x\n"})
        for line in self.FORMS:
            with self.subTest(line=line):
                rows = line_rows(runner, decisions, line + "\n", root)
                self.assertEqual(len(rows), 1, "the decisions store gave %d row(s) for %r, not one: the line is silent"
                                 % (len(rows), line))


if __name__ == "__main__":
    unittest.main()
