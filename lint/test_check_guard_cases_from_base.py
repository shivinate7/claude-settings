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

The fixtures. setUpModule builds four fixture trees, one commit pair each, over the tracked tests/guard. testing/tracked_tree.py
copies it, the one home of that copy. The copy is whole because the runner's sections share globals (ROOT, OWNED) that
only the real suite defines. One section file, s99101-guard-cases-fixture.py, sits on top of it in each tree. The check
of each tree and two listings of the green head run once, in parallel, and each case reads its own lines:
- red tree: each red case reads RED for its name, and the tree exits 1. Its flip group (three cases on one payload, one of
  them flipped from deny to allow) and its removed group (two cases on one payload, one removed) read RED too.
- green tree: each control reads no RED for its names, and the tree exits 0. Its listing pins the keys of two cases that
  differ only by a fixed epoch, and of a deny and an allow case that share one payload. Its rename group (two cases on one
  payload, one renamed) reads green.
- moved tree: the base ref is a commit that moved on after the branch point, and the head is the branch point's tree.
  Its extra case is the base's only, so the check must read the fork, not the base ref's newest.
- unknown tree: its base holds two section files with one number, so the base list cannot be read.
- listing pair: two listings of the green head's folder give equal keys.
Payloads are distinct across the trees. Within a tree, only the three groups above and the green tree's deny and allow
pair share a payload, on purpose. The two epochs are past values (2020 and 2022), outside the check's clock window for
any run made after 2022.
"""
import json
import os
import re
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


def make_pair(base_text, head_text, head_message="", extra_base=None, ahead_text=None):
    """A fixture repository. A base commit holds the tracked tests/guard, with base_text as the section file and each
    extra_base file (name -> text). A head commit holds head_text as the section file, with head_message, and no extra
    file. With ahead_text, a branch made from the base commit holds it, one commit on, and the head stays where it is:
    the base moved on after the branch point. -> (repository, the base sha, or the ahead sha when ahead_text is set)."""
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
    if ahead_text is not None:
        git(repo, "switch", "-q", "-c", "ahead", base)
        write(os.path.join(folder, SECTION_FILE), ahead_text)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "fixture base moves on")
        base = git(repo, "rev-parse", "HEAD")
        git(repo, "switch", "-q", "-")
    return repo, base


def reds(out):
    return [line for line in out.splitlines() if line.startswith("RED ")]


def tail(out, lines=6):
    return "\n".join(out.splitlines()[-lines:])


# The kill cases. Both are deny and share one payload shape and one cwd, so they differ only by the pid's class:
# own is a pid this process owns (OWNED, the sleep the real suite starts), live is the parent of this process.
# The cwd is unique to them, so no real case of the suite shares their key.
KILL_CWD = 'cwd=ROOT + "/fixture-kill-class"'
KILL_OWN = 'sh("fixture kill own", "kill -9 " + str(OWNED.pid), "deny", "fixture-kill", %s)' % KILL_CWD
KILL_LIVE = 'sh("fixture kill live", "kill -9 " + str(os.getppid()), "deny", "fixture-kill", %s)' % KILL_CWD
CLOCK = ['sh("fixture clock", "touch " + ROOT + "/clock-" + repr(time.time()), "deny", "fixture-rule")']

# The groups. Cases on one payload share a key, so the check matches them by name. A payload that holds two verdicts
# gets one key per verdict. The flip group turns one deny case allow, beside a deny peer and an allow case that stay.
# The removed group drops one of two deny cases. The rename group (green tree) renames one of two deny cases.
RED_BASE = section_text([
    case("fixture flip", "deny", "fixture-rule", "flip"),
    case("fixture to ask", "deny", "fixture-rule", "to-ask"),
    case("fixture kept", "deny", "fixture-rule", "kept"),
    case("fixture removed", "deny", "fixture-rule", "removed"),
    case("fixture unwaived", "deny", "fixture-rule", "unwaived"),
    case("fixture stays", "deny", "fixture-rule", "stays"),
    case("fixture group flip", "deny", "fixture-rule", "group-flip"),
    case("fixture group kept", "deny", "fixture-rule", "group-flip"),
    case("fixture group allow", "allow", None, "group-flip"),
    case("fixture group removed", "deny", "fixture-rule", "group-removed"),
    case("fixture group stays", "deny", "fixture-rule", "group-removed"),
], [KILL_OWN, KILL_LIVE])
RED_HEAD = section_text([
    case("fixture flip", "allow", None, "flip"),
    case("fixture to ask", "ask", "fixture-ask-rule", "to-ask"),
    case("fixture kept", "deny", "fixture-rule", "kept"),
    case("fixture unwaived", "allow", None, "unwaived"),
    case("fixture stays", "deny", "fixture-rule", "stays"),
    case("fixture group flip", "allow", None, "group-flip"),
    case("fixture group kept", "deny", "fixture-rule", "group-flip"),
    case("fixture group allow", "allow", None, "group-flip"),
    case("fixture group stays", "deny", "fixture-rule", "group-removed"),
], [KILL_LIVE])
RED_MESSAGE = "Loosen some cases\n\nGuard-case-loosened: fixture stays"

# Two cases that differ only by a fixed epoch in the payload, and a deny and an allow case that hold one payload. Both pairs
# sit in the green tree, in base and head alike, so the listing pins their keys and the check reads them as unchanged.
EPOCH = [
    ("fixture epoch early", '"touch " + ROOT + "/epoch-1600000000"', "deny", "fixture-rule"),
    ("fixture epoch late", '"touch " + ROOT + "/epoch-1650000000"', "deny", "fixture-rule"),
]
SHARED = [
    case("fixture shared deny", "deny", "fixture-rule", "shared-payload"),
    case("fixture shared allow", "allow", None, "shared-payload"),
]

GREEN_BASE = section_text([
    case("fixture tighten", "allow", None, "tighten"),
    case("fixture ask to deny", "ask", "fixture-ask-rule", "ask-deny"),
    case("fixture reason", "deny", "fixture-reason-old", "reason"),
    case("fixture rename old", "deny", "fixture-rule", "renamed"),
    case("fixture waived", "deny", "fixture-rule", "waived"),
    *EPOCH,
    *SHARED,
    case("fixture group rename old", "deny", "fixture-rule", "group-rename"),
    case("fixture group peer", "deny", "fixture-rule", "group-rename"),
], [*CLOCK, KILL_OWN, KILL_LIVE])
GREEN_HEAD = section_text([
    case("fixture tighten", "deny", "fixture-rule", "tighten"),
    case("fixture ask to deny", "deny", "fixture-rule", "ask-deny"),
    case("fixture reason", "deny", "fixture-reason-new", "reason"),
    case("fixture rename new", "deny", "fixture-rule", "renamed"),
    case("fixture waived", "allow", None, "waived"),
    *EPOCH,
    *SHARED,
    case("fixture group rename new", "deny", "fixture-rule", "group-rename"),
    case("fixture group peer", "deny", "fixture-rule", "group-rename"),
], [*CLOCK, KILL_OWN, KILL_LIVE])
GREEN_MESSAGE = "Tighten some cases, rename one and loosen one with its trailer\n\nGuard-case-loosened: fixture waived"

UNKNOWN_BASE = section_text([case("fixture kept", "deny", "fixture-rule", "kept")])
UNKNOWN_EXTRA = {"s99101-duplicate.py": section_text([case("fixture dup", "deny", "fixture-rule", "dup")])}
# The branch point holds one case. The base moves on with a second deny case, which the head never takes.
MOVED_FORK = section_text([case("fixture moved kept", "deny", "fixture-rule", "moved-kept")])
MOVED_AHEAD = section_text([case("fixture moved kept", "deny", "fixture-rule", "moved-kept"),
                            case("fixture ahead only", "deny", "fixture-rule", "ahead-only")])

# label -> (base text, head text, head message, extra base files, ahead text). setUpModule builds each one.
TREES = {
    "red": (RED_BASE, RED_HEAD, RED_MESSAGE, None),
    "green": (GREEN_BASE, GREEN_HEAD, GREEN_MESSAGE, None),
    "unknown": (UNKNOWN_BASE, UNKNOWN_BASE, "fixture head", UNKNOWN_EXTRA),
    "moved": (MOVED_FORK, MOVED_FORK, "fixture head", None, MOVED_AHEAD),
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

    def listing_keys(self, label):
        """{name: key} of the listing that one run wrote. A listing that was not written fails here, with the run's exit."""
        rc, out, path = self.result(label)
        self.assertTrue(os.path.isfile(path), "no listing written by %s, exit %s: %s" % (label, rc, tail(out)))
        with open(path, encoding="utf-8") as f:
            return {row["name"]: row["key"] for row in json.load(f)}

    def test_listing_same_tree_twice_gives_equal_keys(self):
        """Red on pid-runner (GUARD_CASES_RUNNER_UNDER_TEST): its key carries the process id, so the two runs differ.
        The green head holds a clock line, which puts a time-derived value in a payload, so a build that does not
        normalise it reads red too."""
        listings = [self.listing_keys("listing-1"), self.listing_keys("listing-2")]
        self.assertTrue(listings[0], "the listing holds no rows")
        differ = sorted(name for name in listings[0] if listings[0][name] != listings[1].get(name))
        self.assertFalse(differ, "keys differ between two runs of one tree, first: %s" % differ[:1])

    def test_fixed_epochs_keep_their_keys_apart(self):
        """Red on _clock_word that always reads <CLOCK> (lint/_guard_case_list.py): the two cases differ only by a fixed
        epoch, so their normalised payloads are one, and one key stands for both. The names are checked first, so a
        missing row fails as a missing row."""
        keys = self.listing_keys("listing-1")
        for name in ("fixture epoch early", "fixture epoch late"):
            self.assertIn(name, keys, "the listing holds no row for %r" % name)
        self.assertNotEqual(keys["fixture epoch early"], keys["fixture epoch late"],
                            "two cases that differ only by a fixed epoch share one key")

    def test_refuse_and_allow_on_one_payload_keep_their_keys_apart(self):
        """Red with no verdict suffix on a shared key (lint/_guard_case_list.py): the deny and the allow case hold one
        payload, so only the suffix keeps their keys apart. Without it, a rename of the deny case reads as a drop from
        deny to allow, since the lowest verdict of the shared key is the allow case."""
        keys = self.listing_keys("listing-1")
        for name in ("fixture shared deny", "fixture shared allow"):
            self.assertIn(name, keys, "the listing holds no row for %r" % name)
        self.assertNotEqual(keys["fixture shared deny"], keys["fixture shared allow"],
                            "a deny and an allow case on one payload share one key")

    def test_refuse_to_allow_flip_reads_red(self):
        """Red on pass-all: the flipped verdict reads green. The case is edited; its name and payload stay."""
        self.assert_red("red", "fixture flip")

    def test_refuse_to_ask_reads_red(self):
        """Red on pass-all: the verdict drops from deny to ask, and that reads green."""
        self.assert_red("red", "fixture to ask")

    def test_removed_refuse_case_reads_red(self):
        """Red on pass-all, and on red-all, which flags only the case that stays and so never names the removed one."""
        self.assert_red("red", "fixture removed")

    def test_removed_kill_case_reads_red(self):
        """Red with no stand-in: the head drops the own-pid kill case. Its key carries the pid's class, so no head row
        matches it by name or key, and RED names it. Without the class the two kill cases share one key, the removed
        case reads as a rename of the live one, and no RED names it."""
        self.assert_red("red", "fixture kill own")

    def test_unchanged_kill_cases_read_green(self):
        """Control, red on red-all and on pid-runner: the two kill cases keep their payloads, so neither reads red."""
        self.assert_green("green", "fixture kill own", "fixture kill live")

    def test_tightening_allow_to_refuse_passes(self):
        """Control, red on red-all: it flags the tightened case, and a tightening must read green."""
        self.assert_green("green", "fixture tighten")

    def test_ask_to_refuse_passes(self):
        """Control, red on red-all: an ask that becomes a deny is a tightening, and reads green."""
        self.assert_green("green", "fixture ask to deny")

    def test_reworded_reason_passes(self):
        """Control, red on red-all: the reason's rule changes but the verdict and the payload stay, so it reads green."""
        self.assert_green("green", "fixture reason")

    def test_pure_rename_passes(self):
        """Control, red on red-all: the name changes and the payload and verdict stay, so the key still matches."""
        self.assert_green("green", "fixture rename old", "fixture rename new")

    def test_group_rename_passes(self):
        """Control, red on red-all: one of two cases on a payload is renamed, and its peer stays. The rename reads green,
        so a check that flags every unmatched case of a group fails here."""
        self.assert_green("green", "fixture group rename old", "fixture group peer")

    def test_loosening_with_exact_trailer_passes(self):
        """Control, red on red-all: the green control beside test_refuse_to_allow_flip_reads_red. The same flip, with
        its exact trailer, reads green."""
        self.assert_green("green", "fixture waived")

    def test_trailer_naming_another_case_still_reads_red(self):
        """Red on pass-all. The flip has no trailer of its own: a trailer that names another, unchanged case waives nothing."""
        self.assert_red("red", "fixture unwaived")

    def test_group_refuse_flip_reads_red(self):
        """Red with no stand-in: the flipped case's base key still holds its deny peer on the head, so the check matches
        the flipped case to that peer, reads a rename, and no RED names the flip."""
        self.assert_red("red", "fixture group flip")

    def test_group_refuse_removed_reads_red(self):
        """Red with no stand-in: the removed case's base key still holds its peer on the head, so the check matches the
        removed case to that peer, reads a rename, and no RED names the removal."""
        self.assert_red("red", "fixture group removed")

    def test_unreadable_list_prints_unknown(self):
        """Red on pass-all and on red-all: neither prints an UNKNOWN line. The base holds two section files with
        number 99101, so the runner refuses the set before any case, and the base list cannot be read."""
        rc, out = self.result("unknown")[:2]
        unknown = [line for line in out.splitlines() if line.startswith("UNKNOWN")]
        self.assertTrue(unknown, "an unreadable list read green: no UNKNOWN line, exit %s: %s" % (rc, tail(out)))
        self.assertNotEqual(rc, 0, "UNKNOWN printed but exit is 0")

    def test_base_that_moved_on_reads_the_fork(self):
        """Red on fork = args.base (the base ref's newest, not the merge base): the base ref holds a deny case the branch
        point never had, and the head lacks it, so the mutant reads it as removed. Scope first: the head is the branch
        point's tree, so the base list and the head list hold the same number of cases."""
        rc, out = self.result("moved")[:2]
        counts = re.search(r"(\d+) base cases, (\d+) head cases", out)
        self.assertIsNotNone(counts, "no count line, so the two lists were not compared: %s" % tail(out))
        base, head = (int(n) for n in counts.groups())
        self.assertEqual(base, head, "the base list is not the branch point's: %d base cases, %d head cases" % (base, head))
        self.assert_green("moved", "fixture ahead only")


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
