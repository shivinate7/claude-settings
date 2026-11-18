#!/usr/bin/env python3
"""Cases for the guard-case comparison with the base branch: the listing mode of hooks/test_guard.py (GUARD_LIST)
and lint/check_guard_cases_from_base.py. Standard library only, unittest style.

    python3 lint/test_check_guard_cases_from_base.py

The contract this file pins. The builder implements it. On origin/main neither the check nor the listing exists.

- GUARD_LIST=<path> python3 hooks/test_guard.py writes a JSON list of rows {name, tool, expected, key}, one row per
  case, then exits before any case runs. Run filters do not narrow the listing. The listing case sets GUARD_FAMILY to a
  name no family has, so a runner that still runs cases before its listing stops at once. key is a hash of the
  case's payload with the per-run values normalised: the run's root folder, the temp root and the clock.
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

Each case builds a fixture repository under this run's folder (lint/_test_temp.py). It holds the tracked tests/guard,
copied by testing/tracked_tree.py, the one home of that copy. The copy is whole because the runner's sections share
globals (ROOT, OWNED) that only the real suite defines. One section file, s99101-guard-cases-fixture.py, sits on top,
with a base commit and a head commit.
"""
import json
import os
import signal
import subprocess
import sys
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


class GuardCasesFromBase(unittest.TestCase):

    def run_check(self, repo, base):
        self.assertTrue(os.path.isfile(CHECK), "the check module is missing: %s" % CHECK)
        return run([sys.executable, CHECK, "--base", base], cwd=repo, env=GIT_ENV)

    def assert_red(self, rc, out, name):
        """A loosening that reads red: a RED line naming the case, and exit 1."""
        hits = [line for line in reds(out) if line.startswith("RED %s:" % name)]
        self.assertTrue(hits, "a loosening read green: no RED line for %r, exit %s: %s" % (name, rc, tail(out)))
        self.assertEqual(rc, 1, "RED printed for %r but exit is %s, want 1" % (name, rc))

    def assert_green(self, rc, out, what):
        """A control that reads green: no RED line at all, and exit 0."""
        self.assertEqual(reds(out), [], "%s: a RED line printed: %s" % (what, tail(out)))
        self.assertEqual(rc, 0, "%s: no RED line but exit %s, want 0: %s" % (what, rc, tail(out)))

    def test_listing_same_tree_twice_gives_equal_keys(self):
        """Red on pid-runner (GUARD_CASES_RUNNER_UNDER_TEST): its key carries the process id, so the two runs differ.
        The fixture's clock line puts a time-derived value in a payload, so a build that does not normalise it reads red too."""
        clock = ['sh("fixture clock", "touch " + ROOT + "/clock-" + repr(time.time()), "deny", "fixture-rule")']
        text = section_text([case("fixture deny", "deny", "fixture-rule", "listed")], clock)
        repo, _ = make_pair(text, text)
        folder = os.path.join(repo, "tests", "guard")
        listings = []
        for number in (1, 2):
            path = os.path.join(RUN_FOLDER, "listing-%s-%d.json" % (uuid.uuid4().hex[:8], number))
            env = dict(GIT_ENV, GUARD_SECTION_DIR=folder, GUARD_LIST=path, GUARD_FAMILY="no-such-family")
            rc, out = run([sys.executable, RUNNER], cwd=repo, env=env)
            self.assertTrue(os.path.isfile(path), "no listing written by run %d, exit %s: %s" % (number, rc, tail(out)))
            with open(path, encoding="utf-8") as f:
                listings.append({row["name"]: row["key"] for row in json.load(f)})
        self.assertTrue(listings[0], "the listing holds no rows")
        differ = sorted(name for name in listings[0] if listings[0][name] != listings[1].get(name))
        self.assertFalse(differ, "keys differ between two runs of one tree, first: %s" % differ[:1])

    def test_deny_to_allow_flip_reads_red(self):
        """Red on pass-all: the flipped verdict reads green. The case is edited; its name and payload stay."""
        repo, base = make_pair(
            section_text([case("fixture flip", "deny", "fixture-rule", "flip")]),
            section_text([case("fixture flip", "allow", None, "flip")]))
        rc, out = self.run_check(repo, base)
        self.assert_red(rc, out, "fixture flip")

    def test_deny_to_ask_reads_red(self):
        """Red on pass-all: the verdict drops from deny to ask, and that reads green."""
        repo, base = make_pair(
            section_text([case("fixture to ask", "deny", "fixture-rule", "to-ask")]),
            section_text([case("fixture to ask", "ask", "fixture-ask-rule", "to-ask")]))
        rc, out = self.run_check(repo, base)
        self.assert_red(rc, out, "fixture to ask")

    def test_removed_deny_case_reads_red(self):
        """Red on pass-all, and on red-all, which flags only the case that stays and so never names the removed one."""
        repo, base = make_pair(
            section_text([case("fixture kept", "deny", "fixture-rule", "kept"),
                          case("fixture removed", "deny", "fixture-rule", "removed")]),
            section_text([case("fixture kept", "deny", "fixture-rule", "kept")]))
        rc, out = self.run_check(repo, base)
        self.assert_red(rc, out, "fixture removed")

    def test_tightening_allow_to_deny_passes(self):
        """Control, red on red-all: it flags the tightened case, and a tightening must read green."""
        repo, base = make_pair(
            section_text([case("fixture tighten", "allow", None, "tighten")]),
            section_text([case("fixture tighten", "deny", "fixture-rule", "tighten")]))
        rc, out = self.run_check(repo, base)
        self.assert_green(rc, out, "a tightening, allow to deny")

    def test_ask_to_deny_passes(self):
        """Control, red on red-all: an ask that becomes a deny is a tightening, and reads green."""
        repo, base = make_pair(
            section_text([case("fixture ask to deny", "ask", "fixture-ask-rule", "ask-deny")]),
            section_text([case("fixture ask to deny", "deny", "fixture-rule", "ask-deny")]))
        rc, out = self.run_check(repo, base)
        self.assert_green(rc, out, "a tightening, ask to deny")

    def test_reworded_reason_passes(self):
        """Control, red on red-all: the reason's rule changes but the verdict and the payload stay, so it reads green."""
        repo, base = make_pair(
            section_text([case("fixture reason", "deny", "fixture-reason-old", "reason")]),
            section_text([case("fixture reason", "deny", "fixture-reason-new", "reason")]))
        rc, out = self.run_check(repo, base)
        self.assert_green(rc, out, "a reworded reason")

    def test_pure_rename_passes(self):
        """Control, red on red-all: the name changes and the payload and verdict stay, so the key still matches."""
        repo, base = make_pair(
            section_text([case("fixture rename old", "deny", "fixture-rule", "renamed")]),
            section_text([case("fixture rename new", "deny", "fixture-rule", "renamed")]))
        rc, out = self.run_check(repo, base)
        self.assert_green(rc, out, "a pure rename")

    def test_loosening_with_exact_trailer_passes(self):
        """Control, red on red-all: the green control beside test_deny_to_allow_flip_reads_red. The same flip, with
        its exact trailer, reads green."""
        repo, base = make_pair(
            section_text([case("fixture waived", "deny", "fixture-rule", "waived")]),
            section_text([case("fixture waived", "allow", None, "waived")]),
            head_message="Loosen one case\n\nGuard-case-loosened: fixture waived")
        rc, out = self.run_check(repo, base)
        self.assert_green(rc, out, "a loosening with its exact trailer")

    def test_trailer_naming_another_case_still_reads_red(self):
        """Red on pass-all. The flip has no trailer of its own: a trailer that names another, unchanged case waives nothing."""
        repo, base = make_pair(
            section_text([case("fixture unwaived", "deny", "fixture-rule", "unwaived"),
                          case("fixture stays", "deny", "fixture-rule", "stays")]),
            section_text([case("fixture unwaived", "allow", None, "unwaived"),
                          case("fixture stays", "deny", "fixture-rule", "stays")]),
            head_message="Loosen one case\n\nGuard-case-loosened: fixture stays")
        rc, out = self.run_check(repo, base)
        self.assert_red(rc, out, "fixture unwaived")

    def test_unreadable_list_prints_unknown(self):
        """Red on pass-all and on red-all: neither prints an UNKNOWN line. The base holds two section files with
        number 99101, so the runner refuses the set before any case, and the base list cannot be read."""
        base_text = section_text([case("fixture kept", "deny", "fixture-rule", "kept")])
        repo, base = make_pair(
            base_text, base_text,
            extra_base={"s99101-duplicate.py": section_text([case("fixture dup", "deny", "fixture-rule", "dup")])})
        rc, out = self.run_check(repo, base)
        unknown = [line for line in out.splitlines() if line.startswith("UNKNOWN")]
        self.assertTrue(unknown, "an unreadable list read green: no UNKNOWN line, exit %s: %s" % (rc, tail(out)))
        self.assertNotEqual(rc, 0, "UNKNOWN printed but exit is 0")


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    if RUN_FOLDER and os.path.isdir(RUN_FOLDER):
        tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
