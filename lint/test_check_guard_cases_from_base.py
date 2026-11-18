#!/usr/bin/env python3
"""Cases for the guard-case comparison with the base branch: the listing mode of hooks/test_guard.py (GUARD_LIST)
and lint/check_guard_cases_from_base.py. Standard library only, unittest style.

    python3 lint/test_check_guard_cases_from_base.py

The contract this file pins. The builder implements it. On origin/main neither the check nor the listing exists.

- GUARD_LIST=<path> python3 hooks/test_guard.py writes a JSON list of rows {name, tool, expected, key}, one row per
  case, then exits before any case runs. Run filters do not narrow the listing. The listing case sets GUARD_FAMILY to a
  name no family has, so a runner that still runs cases before its listing stops at once. key is a hash of the
  case's payload with the per-run values normalised: the run's root folder, the temp root, the clock, and each pid a
  kill names, as its class (own, live or gone).
- python3 lint/check_guard_cases_from_base.py --base REF, run in a repository, lists the base's tests/guard (from
  `git archive REF`) and the head's, and matches each base case by name, then by key. It prints one line per finding:
    RED <name>: ...      a loosening that no trailer waives: a verdict drops (allow < ask < deny), or the key is gone. Exit 1.
    WAIVED <name>: ...   a loosening that a commit of REF..HEAD waives with the exact trailer `Guard-case-loosened: <name>`.
    REPORT <name>: ...   a tightening, a reworded reason or a rename. Exit 0.
    UNKNOWN <reason>     the case list cannot be read. Exit 1 (decision ci-unknown-is-red: an unknown read is red in CI).
  It exits 0 when it prints no RED and no UNKNOWN. The cases pin the RED and UNKNOWN lines and the exit codes. The
  WAIVED and REPORT lines are the builder's words, and no case reads them.

Stand-ins, not the feature. Each red is shown on a stand-in that is wrong in one way. An env variable picks it:
- CHECK_GUARD_CASES_UNDER_TEST. pass-all exits 0 and prints nothing, so every loosening reads green. red-all prints RED
  for every case of the head's section file, so every control reads red.
- GUARD_CASES_RUNNER_UNDER_TEST. pid-runner writes a key that carries os.getpid(), so two runs of one tree differ.
The stand-ins sit outside every repository. Each case's docstring names the stand-in it is red on.

The fixtures. setUpModule builds three fixture trees, one commit pair each, over the tracked tests/guard. testing/tracked_tree.py
copies it, the one home of that copy. The copy is whole because the runner's sections share globals (ROOT, OWNED) that
only the real suite defines. One section file, s99101-guard-cases-fixture.py, sits on top of it in each tree. The check
of each tree and two listings of the green head run once, in parallel, and each case reads its own lines:
- red tree: each red case reads RED for its name, and the tree exits 1.
- green tree: each control reads no RED for its names, and the tree exits 0.
- unknown tree: its base holds two section files with one number, so the base list cannot be read.
- listing pair: two listings of the green head's folder give equal keys.
Each tree's cases have distinct payloads, so no case of one tree matches a case of another.
"""
import json
import os
import signal
import subprocess
import sys
import threading
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists (testing/tracked_tree.py)

REPO = os.path.dirname(HERE)
CHECK = os.path.abspath(os.environ.get("CHECK_GUARD_CASES_UNDER_TEST")
                        or os.path.join(HERE, "check_guard_cases_from_base.py"))
RUNNER = os.path.abspath(os.environ.get("GUARD_CASES_RUNNER_UNDER_TEST")
                         or os.path.join(REPO, "hooks", "test_guard.py"))
SECTION_NO = 99101
SECTION_FILE = "s99101-guard-cases-fixture.py"
CAP = 120  # seconds. A check or a listing takes well under one; the cap sits far above the run.
RUN_FOLDER = None
RESULTS = {}  # fixture label -> ("ran", rc, out[, path]) or ("error", reason), set by setUpModule


def git_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GUARD_", "CHECK_GUARD", "GIT_"))}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
               GIT_AUTHOR_NAME="fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
               GIT_COMMITTER_NAME="fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")
    return _test_git.apply(env)


GIT_ENV = git_env()


def run(argv, cwd, env):
    """-> (rc, output). rc is None when the run passes CAP seconds. Its process group is killed, since a runner starts sleeps."""
    posix = os.name != "nt"
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, start_new_session=posix)
    try:
        out, _ = proc.communicate(timeout=CAP)
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        if posix:
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
        out, _ = proc.communicate()
        return None, out + "\n(cut at %d s)" % CAP


def git(repo, *args, input_text=None):
    done = subprocess.run(["git", *args], cwd=repo, env=GIT_ENV, input=input_text,
                          capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError("fixture git %s failed: %s" % (args[0], done.stderr.strip()))
    return done.stdout.strip()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def case(name, expected, rule=None, path=None):
    """One case: `name` with the payload `rm -rf` of a path under ROOT. A case that keeps `path` keeps its payload."""
    path = path or name.replace(" ", "-")
    return (name, '"rm -rf " + ROOT + "/%s"' % path, expected, rule)


def section_text(cases, extra=()):
    """A section file: the header, one sh() line per case, then the extra lines as given."""
    lines = ["# section %d" % SECTION_NO]
    for name, command, expected, rule in cases:
        lines.append("sh(%s, %s, %s, %s)" % (json.dumps(name), command, json.dumps(expected),
                                             "None" if rule is None else json.dumps(rule)))
    lines.extend(extra)
    return "\n".join(lines) + "\n"


def make_pair(base_text, head_text, head_message="", extra_base=None):
    """A fixture repository. A base commit holds the tracked tests/guard, with base_text as the section file and each
    extra_base file (name -> text). A head commit holds head_text as the section file, with head_message, and no extra
    file. -> (repository, base sha)."""
    repo = os.path.join(RUN_FOLDER, uuid.uuid4().hex)
    os.makedirs(repo)
    git(repo, "init", "-q")
    tracked_tree.copy_tracked(repo, "tests/guard")
    folder = os.path.join(repo, "tests", "guard")
    write(os.path.join(folder, SECTION_FILE), base_text)
    for name, text in (extra_base or {}).items():
        write(os.path.join(folder, name), text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "fixture base")
    base = git(repo, "rev-parse", "HEAD")
    write(os.path.join(folder, SECTION_FILE), head_text)
    for name in (extra_base or {}):
        os.remove(os.path.join(folder, name))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-F", "-", input_text=(head_message or "fixture head") + "\n")
    return repo, base


def reds(out):
    return [line for line in out.splitlines() if line.startswith("RED ")]


def tail(out, lines=6):
    return "\n".join(out.splitlines()[-lines:])


CLOCK = ['sh("fixture clock", "touch " + ROOT + "/clock-" + repr(time.time()), "deny", "fixture-rule")']

RED_BASE = section_text([
    case("fixture flip", "deny", "fixture-rule", "flip"),
    case("fixture to ask", "deny", "fixture-rule", "to-ask"),
    case("fixture kept", "deny", "fixture-rule", "kept"),
    case("fixture removed", "deny", "fixture-rule", "removed"),
    case("fixture unwaived", "deny", "fixture-rule", "unwaived"),
    case("fixture stays", "deny", "fixture-rule", "stays"),
])
RED_HEAD = section_text([
    case("fixture flip", "allow", None, "flip"),
    case("fixture to ask", "ask", "fixture-ask-rule", "to-ask"),
    case("fixture kept", "deny", "fixture-rule", "kept"),
    case("fixture unwaived", "allow", None, "unwaived"),
    case("fixture stays", "deny", "fixture-rule", "stays"),
])
RED_MESSAGE = "Loosen some cases\n\nGuard-case-loosened: fixture stays"

GREEN_BASE = section_text([
    case("fixture tighten", "allow", None, "tighten"),
    case("fixture ask to deny", "ask", "fixture-ask-rule", "ask-deny"),
    case("fixture reason", "deny", "fixture-reason-old", "reason"),
    case("fixture rename old", "deny", "fixture-rule", "renamed"),
    case("fixture waived", "deny", "fixture-rule", "waived"),
], CLOCK)
GREEN_HEAD = section_text([
    case("fixture tighten", "deny", "fixture-rule", "tighten"),
    case("fixture ask to deny", "deny", "fixture-rule", "ask-deny"),
    case("fixture reason", "deny", "fixture-reason-new", "reason"),
    case("fixture rename new", "deny", "fixture-rule", "renamed"),
    case("fixture waived", "allow", None, "waived"),
], CLOCK)
GREEN_MESSAGE = "Tighten some cases, rename one and loosen one with its trailer\n\nGuard-case-loosened: fixture waived"

UNKNOWN_BASE = section_text([case("fixture kept", "deny", "fixture-rule", "kept")])
UNKNOWN_EXTRA = {"s99101-duplicate.py": section_text([case("fixture dup", "deny", "fixture-rule", "dup")])}

# label -> (base text, head text, head message, extra base files). setUpModule builds each one.
TREES = {
    "red": (RED_BASE, RED_HEAD, RED_MESSAGE, None),
    "green": (GREEN_BASE, GREEN_HEAD, GREEN_MESSAGE, None),
    "unknown": (UNKNOWN_BASE, UNKNOWN_BASE, "fixture head", UNKNOWN_EXTRA),
}


def _job(label, work):
    """One fixture run in its own thread. A fault is kept here, and the case that reads the label fails with it."""
    try:
        RESULTS[label] = ("ran",) + tuple(work())
    except Exception as exc:  # a fault is one case's failure, never a module error
        RESULTS[label] = ("error", "%s: %s" % (type(exc).__name__, exc))


def _check(repo, base):
    if not os.path.isfile(CHECK):
        raise FileNotFoundError("the check module is missing: %s" % CHECK)
    return run([sys.executable, CHECK, "--base", base], cwd=repo, env=GIT_ENV)


def _listing(repo, folder, path):
    env = dict(GIT_ENV, GUARD_SECTION_DIR=folder, GUARD_LIST=path, GUARD_FAMILY="no-such-family")
    rc, out = run([sys.executable, RUNNER], cwd=repo, env=env)
    return rc, out, path


class GuardCasesFromBase(unittest.TestCase):

    def result(self, label):
        """The run of one fixture, as setUpModule made it. A fault fails the case that reads it."""
        got = RESULTS.get(label)
        self.assertIsNotNone(got, "the fixture %r did not run" % label)
        self.assertEqual(got[0], "ran", "the %s fixture did not build or run: %s" % (label, got[1]))
        return got[1:]

    def assert_red(self, label, name):
        """A loosening that reads red: a RED line naming the case in the tree, and the tree exits 1."""
        rc, out = self.result(label)[:2]
        hits = [line for line in reds(out) if line.startswith("RED %s:" % name)]
        self.assertTrue(hits, "a loosening read green: no RED line for %r, exit %s: %s" % (name, rc, tail(out)))
        self.assertEqual(rc, 1, "RED printed for %r but exit is %s, want 1" % (name, rc))

    def assert_green(self, label, *names):
        """Controls that read green: no RED line naming any of them, and the tree exits 0."""
        rc, out = self.result(label)[:2]
        for name in names:
            hits = [line for line in reds(out) if line.startswith("RED %s:" % name)]
            self.assertFalse(hits, "a control reads red: %s" % hits[:1])
        self.assertEqual(rc, 0, "the %s tree exits %s, want 0, with these RED lines: %s" % (label, rc, reds(out)))

    def test_listing_same_tree_twice_gives_equal_keys(self):
        """Red on pid-runner (GUARD_CASES_RUNNER_UNDER_TEST): its key carries the process id, so the two runs differ.
        The green head holds a clock line, which puts a time-derived value in a payload, so a build that does not
        normalise it reads red too."""
        listings = []
        for label in ("listing-1", "listing-2"):
            rc, out, path = self.result(label)
            self.assertTrue(os.path.isfile(path), "no listing written by %s, exit %s: %s" % (label, rc, tail(out)))
            with open(path, encoding="utf-8") as f:
                listings.append({row["name"]: row["key"] for row in json.load(f)})
        self.assertTrue(listings[0], "the listing holds no rows")
        differ = sorted(name for name in listings[0] if listings[0][name] != listings[1].get(name))
        self.assertFalse(differ, "keys differ between two runs of one tree, first: %s" % differ[:1])

    def test_deny_to_allow_flip_reads_red(self):
        """Red on pass-all: the flipped verdict reads green. The case is edited; its name and payload stay."""
        self.assert_red("red", "fixture flip")

    def test_deny_to_ask_reads_red(self):
        """Red on pass-all: the verdict drops from deny to ask, and that reads green."""
        self.assert_red("red", "fixture to ask")

    def test_removed_deny_case_reads_red(self):
        """Red on pass-all, and on red-all, which flags only the case that stays and so never names the removed one."""
        self.assert_red("red", "fixture removed")

    def test_tightening_allow_to_deny_passes(self):
        """Control, red on red-all: it flags the tightened case, and a tightening must read green."""
        self.assert_green("green", "fixture tighten")

    def test_ask_to_deny_passes(self):
        """Control, red on red-all: an ask that becomes a deny is a tightening, and reads green."""
        self.assert_green("green", "fixture ask to deny")

    def test_reworded_reason_passes(self):
        """Control, red on red-all: the reason's rule changes but the verdict and the payload stay, so it reads green."""
        self.assert_green("green", "fixture reason")

    def test_pure_rename_passes(self):
        """Control, red on red-all: the name changes and the payload and verdict stay, so the key still matches."""
        self.assert_green("green", "fixture rename old", "fixture rename new")

    def test_loosening_with_exact_trailer_passes(self):
        """Control, red on red-all: the green control beside test_deny_to_allow_flip_reads_red. The same flip, with
        its exact trailer, reads green."""
        self.assert_green("green", "fixture waived")

    def test_trailer_naming_another_case_still_reads_red(self):
        """Red on pass-all. The flip has no trailer of its own: a trailer that names another, unchanged case waives nothing."""
        self.assert_red("red", "fixture unwaived")

    def test_unreadable_list_prints_unknown(self):
        """Red on pass-all and on red-all: neither prints an UNKNOWN line. The base holds two section files with
        number 99101, so the runner refuses the set before any case, and the base list cannot be read."""
        rc, out = self.result("unknown")[:2]
        unknown = [line for line in out.splitlines() if line.startswith("UNKNOWN")]
        self.assertTrue(unknown, "an unreadable list read green: no UNKNOWN line, exit %s: %s" % (rc, tail(out)))
        self.assertNotEqual(rc, 0, "UNKNOWN printed but exit is 0")


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()
    built = {}
    for label, spec in TREES.items():
        try:
            built[label] = make_pair(*spec)
        except Exception as exc:  # a fixture fault fails the cases that read this tree
            RESULTS[label] = ("error", "%s: %s" % (type(exc).__name__, exc))
    jobs = {label: (lambda label=label: _check(*built[label])) for label in built}
    if "green" in built:
        green_repo = built["green"][0]
        green_folder = os.path.join(green_repo, "tests", "guard")
        for number in (1, 2):
            path = os.path.join(RUN_FOLDER, "listing-%d.json" % number)
            jobs["listing-%d" % number] = (lambda path=path: _listing(green_repo, green_folder, path))
    threads = [threading.Thread(target=_job, args=(label, work)) for label, work in jobs.items()]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def tearDownModule():
    if RUN_FOLDER and os.path.isdir(RUN_FOLDER):
        tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
