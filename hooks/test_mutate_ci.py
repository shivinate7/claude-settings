#!/usr/bin/env python3
"""Cases for the mutation CI report and the known-defect replay in hooks/mutate_guard.py: the `--changed`,
`--known-defects` and `--tests-for` modes. Standard library only, unittest style.

    python3 hooks/test_mutate_ci.py

The modes, as the builder implements them. This file is their interface.

- `--changed REPO (--profile NAME | --profile-file JSON) --base REF [--head REF] [--limit N] [--budget S]
  [--suite-timeout S] [--jobs N] [--log PATH]`. It mutates only the product lines that a change adds between
  merge-base(base, head) and head, with the engines and `changed_lines` of `--replay`. A profile with `select`
  runs every suite that `select` lists for a file, changed or not. Without `select`, only the changed suites run,
  as `--replay` does. It prints the replay row, then `catch share: K/R (P%)` (K killed over R ran; a crash is not a
  kill), then one `untested: path:line` line per line whose mutant survived or was not run. It exits 0 whatever the
  share. `--log PATH` writes one JSON file with the keys base, head, profile, made, killed, crashed, survived,
  not_run and untested, and writes nothing else into REPO. With no changed mutant the share reads `0/0` with no
  percentage.
- `--known-defects FILE --repo REPO [--suite-timeout S] [--log PATH]`. FILE is a JSON list of planted defects. Each defect
  prints one line, `CAUGHT|MISS|UNKNOWN id: name [reason]`. It exits 1 when any defect is MISS or UNKNOWN, else 0.
- `--tests-for PATH`. It prints the REPORT_TARGETS suites for PATH when listed, else each tracked `test_<stem>.py`
  and `test_<stem>_*.py` beside it.

Each mode is dispatched from main() in hooks/mutate_guard.py and has an entry point beside `report_main` and
`replay_main`: `changed_main`, `known_defects_main`, `tests_for_main`. A case checks for its entry point first and
fails by name when it is missing. So a red run never reaches the guard campaign that main() runs for an argument it
does not know.

The real list, `.github/known-defects.json`, is read at HEAD. Its three pinned entries carry the exact catchers and
plants that the coordinator measured. Every entry's `old` text must occur exactly once in its file at HEAD.

Test temp files take the run folder of lint/_test_temp.py. The fixture writers (put, commit, topic, pull_request)
come from hooks/test_mutate_replay.py, and git from hooks/test_mutate_js.py: the one home of each. This module's
fresh() and new_repo() take their folder from this module's run folder, since test_mutate_replay's fresh() reads
that module's own run global. The sweep of old run folders is proven once, in hooks/test_mutate_js.py.

Process checks use os.killpg and so run on POSIX only, as the CI step does (ubuntu-latest).
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import mutate_guard  # noqa: E402  REPORT_TARGETS, and the mode entry points once built
import mutate_shared  # noqa: E402
from test_mutate_js import git, unique_line  # noqa: E402  the one home of these helpers
from test_mutate_replay import commit, pull_request, put, topic  # noqa: E402  the one home of the fixture writers

PY = sys.executable
CLI_LIMIT = 300  # seconds a mode run may take before its case fails
KNOWN_DEFECTS_FILE = ".github/known-defects.json"
ENTRY = {"--changed": "changed_main", "--known-defects": "known_defects_main", "--tests-for": "tests_for_main"}

RUN = ""  # this run's folder, made in setUpModule and removed in tearDownModule
CACHE = {}  # the fixture of a case built once per run, where a case reuses it


def setUpModule():
    global RUN
    RUN = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)


def fresh():
    """A new empty folder under this module's run folder."""
    folder = os.path.join(RUN, uuid.uuid4().hex)
    os.makedirs(folder)
    return folder


def new_repo():
    repo = os.path.join(fresh(), "repo")
    os.makedirs(repo)
    git(repo, "init", "-q", "-b", "main")
    return repo


def show(repo, ref, path):
    """The text of `path` at `ref`, unstripped. A missing path is a FAIL."""
    done = subprocess.run(["git", "show", "%s:%s" % (ref, path)], cwd=repo, capture_output=True, text=True,
                          encoding="utf-8")
    if done.returncode != 0:
        raise AssertionError("%s has no %s: %s" % (ref, path, done.stderr.strip()))
    return done.stdout


def rev(repo, ref):
    return git(repo, "rev-parse", ref)


def status_of(repo):
    return git(repo, "status", "--porcelain")


def tree_of(repo):
    """Every file under the repository but .git, as sorted relative paths: what a run must not add to."""
    names = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [name for name in dirs if name != ".git"]
        for name in files:
            names.append(os.path.relpath(os.path.join(root, name), repo))
    return sorted(names)


# ---------------------------------------------------------------------------------------------------
# Fixture sources. Each product line that a case mutates is one of these returns or assignments. The engine makes
# a mutant of a `return` (to None, or dropped) and of a comparison or a condition. It makes none of an arithmetic
# operator, so the suites below kill a `return` by calling its function and checking the value.

CALC_BASE = "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"
CALC_SUB_DIV = CALC_BASE + "\n\ndef sub(a, b):\n    return a - b\n\n\ndef div(a, b):\n    return a / b\n"
CALC_SUB_ONLY = CALC_BASE + "\n\ndef sub(a, b):\n    return a - b\n"
CALC_MUL_PRODUCT = ("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    product = a * b\n"
                    "    return product\n")
CALC_ADD_MOVED = "def add(a, b):\n    return b + a\n\n\ndef mul(a, b):\n    return a * b\n"

# The base suite pins add and mul. It never calls sub or div.
SUITE = ("import sys\n"
         "from calc import add, mul\n\n"
         "if add(1, 2) != 3:\n"
         "    print('FAIL: add(1, 2) is not 3')\n"
         "    sys.exit(1)\n"
         "if mul(2, 3) != 6:\n"
         "    print('FAIL: mul(2, 3) is not 6')\n"
         "    sys.exit(1)\n"
         "print('ok')\n")
SUITE_WITH_SUB = ("import sys\n"
                  "from calc import add, mul, sub\n\n"
                  "if add(1, 2) != 3:\n"
                  "    print('FAIL: add(1, 2) is not 3')\n"
                  "    sys.exit(1)\n"
                  "if mul(2, 3) != 6:\n"
                  "    print('FAIL: mul(2, 3) is not 6')\n"
                  "    sys.exit(1)\n"
                  "if sub(5, 2) != 3:\n"
                  "    print('FAIL: sub(5, 2) is not 3')\n"
                  "    sys.exit(1)\n"
                  "print('ok')\n")
# Green on the clean source. A mutant that returns None makes `sub(5, 2) + 1` throw: a crash, not a FAIL line.
SUITE_CRASH = "from calc import sub\nprint(sub(5, 2) + 1)\n"
# The select script names the suite that pins calc.py. It is part of the commit, so a checkout at head has it.
SELECT_SRC = "import sys\nif sys.argv[1] == 'calc.py':\n    print('test_calc.py')\n"

CHANGED = {"code": r"^calc\.py$", "tests": r"^test_[^/]+\.py$", "argv": [PY, "{suite}"],
           "classify": "fail_line", "install": None, "sparse_skip": []}
SELECTED = dict(CHANGED, select=[PY, "select_for.py", "{path}"])


# ---------------------------------------------------------------------------------------------------
# Fixture repositories. Each one is a base commit on main, and a change cut from it on branch feat.

def partial_repo():
    """feat adds sub and div. Its suite gains a check for sub only, so sub's mutants die and div's survive."""
    repo = new_repo()
    put(repo, {"calc.py": CALC_BASE, "test_calc.py": SUITE})
    commit(repo, "Base: add and mul")
    topic(repo, "feat", {"calc.py": CALC_SUB_DIV, "test_calc.py": SUITE_WITH_SUB}, "Add sub and div")
    return repo


def partial_facts(repo):
    """The lines the partial change adds, and how many mutants each one has. The oracle the rows are checked against."""
    text = show(repo, "feat", "calc.py")
    sub_line = unique_line(text, "    return a - b")
    div_line = unique_line(text, "    return a / b")
    return {"sub": sub_line, "div": div_line, "sub_n": mutants_on(text, [sub_line]),
            "div_n": mutants_on(text, [div_line])}


def moved_repo():
    """main moves on after feat is cut: its add() line changes, a line feat does not touch. Only feat's own lines
    belong to the change; a diff against main's tip would also take feat's add() line."""
    repo = new_repo()
    put(repo, {"calc.py": CALC_BASE, "test_calc.py": SUITE})
    commit(repo, "Base: add and mul")
    topic(repo, "feat", {"calc.py": CALC_SUB_DIV, "test_calc.py": SUITE_WITH_SUB}, "Add sub and div")
    put(repo, {"calc.py": CALC_ADD_MOVED})
    commit(repo, "Main rewords add")
    return repo


def crash_repo():
    """feat adds sub, and its changed suite calls sub: every mutant of sub throws, and none prints a FAIL line."""
    repo = new_repo()
    put(repo, {"calc.py": CALC_BASE, "test_calc.py": SUITE})
    commit(repo, "Base: add and mul")
    topic(repo, "feat", {"calc.py": CALC_SUB_ONLY, "test_calc.py": SUITE_CRASH}, "Add sub and call it")
    return repo


def selected_repo():
    """feat rewrites mul through a name. Its suite is untouched, so only `select` brings the suite to its mutants."""
    repo = new_repo()
    put(repo, {"calc.py": CALC_BASE, "test_calc.py": SUITE, "select_for.py": SELECT_SRC})
    commit(repo, "Base: add and mul, and the select script")
    topic(repo, "feat", {"calc.py": CALC_MUL_PRODUCT}, "Name the product in mul")
    return repo


def weak_repo():
    """feat adds sub and div, and the suite that `select` lists pins neither: every mutant survives."""
    repo = new_repo()
    put(repo, {"calc.py": CALC_BASE, "test_calc.py": SUITE, "select_for.py": SELECT_SRC})
    commit(repo, "Base: add and mul, and the select script")
    topic(repo, "feat", {"calc.py": CALC_SUB_DIV}, "Add sub and div, untested")
    return repo


def empty_repo():
    """feat adds a comment only: no line of it has a mutant."""
    repo = new_repo()
    put(repo, {"calc.py": CALC_BASE, "test_calc.py": SUITE})
    commit(repo, "Base: add and mul")
    topic(repo, "feat", {"calc.py": CALC_BASE + "# sub is next\n"}, "Note the next change")
    return repo


def replayed(files):
    """A repository whose main holds calc.py, the suite and the select script, and one merged pull request that
    writes `files`. Returns (repo, merge sha)."""
    repo = new_repo()
    put(repo, {"calc.py": CALC_BASE, "test_calc.py": SUITE, "select_for.py": SELECT_SRC})
    commit(repo, "Base")
    sha = pull_request(repo, 7, "Name the product in mul", files)
    return repo, sha


def defect_repo():
    """main holds calc.py and six suites. Each suite is green on the clean source, except test_red.py and
    test_boom.py, which are red and crashing on it."""
    repo = new_repo()
    put(repo, {
        "calc.py": CALC_BASE,
        "test_calc.py": SUITE,
        "test_nothing.py": "print('ok')\n",
        "test_crash.py": "from calc import mul\nprint(mul(2, 3) * 2)\n",
        "test_hang.py": "from calc import add\nwhile add(1, 2) != 3:\n    pass\nprint('ok')\n",
        "test_red.py": "print('FAIL: the clean code is wrong')\nraise SystemExit(1)\n",
        "test_boom.py": "raise RuntimeError('the clean suite crashes')\n",
    })
    commit(repo, "Base")
    return repo


# ---------------------------------------------------------------------------------------------------
# Oracles and runners.

def mutants_on(text, lines):
    """How many mutants the engine makes of `text` on `lines`. The engine has its own cases; these only read its output."""
    return len(mutate_shared.ast_mutants(text, lines=set(lines)))


def profile_file(profile):
    path = os.path.join(fresh(), "profile.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(profile, handle)
    return path


def run_cli(args):
    """`hooks/mutate_guard.py <args>` in a child Python, from the repository root. Returns (exit code, stdout,
    stderr). The mode's entry point is checked first: when it is missing, the case fails by name and nothing runs.
    A run past CLI_LIMIT is killed with its group and fails."""
    flag = args[0]
    name = ENTRY[flag]
    if getattr(mutate_guard, name, None) is None:
        raise AssertionError("the %s mode is missing: hooks/mutate_guard.py has no %s" % (flag, name))
    command = [PY, os.path.join(HERE, "mutate_guard.py")] + list(args)
    proc = subprocess.Popen(command, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", start_new_session=True)
    try:
        out, err = proc.communicate(timeout=CLI_LIMIT)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise AssertionError("%s did not finish in %d s" % (flag, CLI_LIMIT))
    return proc.returncode, out, err


def changed_run(repo, profile, base="main", head="feat", extra=(), log=None, limit=1000):
    """`--changed` on `repo`. A head of None leaves --head out, so the mode reads HEAD."""
    args = ["--changed", repo, "--profile-file", profile_file(profile), "--base", base, "--limit", str(limit)]
    if head is not None:
        args += ["--head", head]
    if log is not None:
        args += ["--log", log]
    return run_cli(args + list(extra))


def known_run(defects, repo, extra=(), log=None):
    """`--known-defects` on `defects`, a list of planted defects, against `repo`."""
    spec = os.path.join(fresh(), "known-defects.json")
    with open(spec, "w", encoding="utf-8") as handle:
        json.dump(defects, handle)
    args = ["--known-defects", spec, "--repo", repo] + list(extra)
    if log is not None:
        args += ["--log", log]
    return run_cli(args)


def defect(defect_id, old, new, suite, file="calc.py"):
    return {"id": defect_id, "name": defect_id, "file": file, "old": old, "new": new, "argv": [PY, suite],
            "classify": "fail_line"}


SHARE = re.compile(r"^catch share: (\d+)/(\d+)(.*)$", re.M)
PERCENT = re.compile(r"\(([\d.]+)%\)")
UNTESTED = re.compile(r"^untested: (\S+):(\d+)\s*$", re.M)
VERDICT = re.compile(r"^(CAUGHT|MISS|UNKNOWN) (\S+?): ", re.M)
SUITE_NAME = re.compile(r"[\w./-]*test_[\w./-]*\.py")


def share_of(out):
    """(killed, ran, percent or None) from the one `catch share` line. A percent is read only when the line has one."""
    found = SHARE.findall(out)
    if len(found) != 1:
        raise AssertionError("want one `catch share: K/R` line, got %d, in:\n%s" % (len(found), out))
    killed, ran, rest = found[0]
    match = PERCENT.search(rest)
    return int(killed), int(ran), (float(match.group(1)) if match else None)


def untested_of(out):
    return ["%s:%s" % pair for pair in UNTESTED.findall(out)]


def verdicts_of(out):
    """{defect id: verdict} from the verdict lines. An id on two lines is a FAIL."""
    found = VERDICT.findall(out)
    ids = [defect_id for _verdict, defect_id in found]
    if len(ids) != len(set(ids)):
        raise AssertionError("a defect id has two verdict lines: %s" % ids)
    return {defect_id: verdict for verdict, defect_id in found}


def read_log(path):
    if not os.path.isfile(path):
        raise AssertionError("--log wrote no file at %s" % path)
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def fixture_log():
    """A log path in a folder of its own, so a case can see exactly what was written there."""
    folder = fresh()
    return folder, os.path.join(folder, "log.json")


# ---------------------------------------------------------------------------------------------------

class ChangedTests(unittest.TestCase):
    """`--changed`: the share, the untested lines, the lines it mutates, the suites it runs, the log."""

    def test_exit_is_0_at_a_partial_share(self):
        repo = partial_repo()
        code, out, err = changed_run(repo, CHANGED)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))

    def test_the_share_line_counts_killed_over_ran(self):
        repo = partial_repo()
        facts = partial_facts(repo)
        self.assertTrue(facts["sub_n"] and facts["div_n"], "the fixture needs mutants on sub and on div")
        code, out, err = changed_run(repo, CHANGED)
        killed, ran, percent = share_of(out)
        self.assertEqual(killed, facts["sub_n"], "killed should be the mutants of sub, which its check kills")
        self.assertEqual(ran, facts["sub_n"] + facts["div_n"], "ran should be every mutant that ran")
        self.assertAlmostEqual(percent, 100.0 * killed / ran, delta=1.0, msg="the percentage is not killed over ran")

    def test_untested_lists_the_surviving_line_once_and_never_a_killed_line(self):
        repo = partial_repo()
        facts = partial_facts(repo)
        code, out, err = changed_run(repo, CHANGED)
        self.assertEqual(untested_of(out), ["calc.py:%d" % facts["div"]],
                         "untested should name div's line once (two of its mutants survive), not sub's killed line")

    def test_only_the_lines_the_change_adds_are_mutated(self):
        repo = partial_repo()
        facts = partial_facts(repo)
        text = show(repo, "feat", "calc.py")
        whole_file = mutants_on(text, range(1, len(text.split("\n")) + 1))
        self.assertGreater(whole_file, facts["sub_n"] + facts["div_n"],
                           "the fixture needs mutants on add and mul too, so the test can tell them apart")
        folder, log = fixture_log()
        code, out, err = changed_run(repo, CHANGED, log=log)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(read_log(log)["made"], facts["sub_n"] + facts["div_n"],
                         "made should count the mutants of the added lines only, not add's or mul's")

    def test_the_mutants_are_those_the_change_adds_between_the_merge_base_and_head(self):
        repo = moved_repo()
        feat = rev(repo, "feat")
        base = git(repo, "merge-base", "main", "feat")
        branch_lines = mutate_shared.changed_lines(repo, base, feat, "calc.py")
        tip_lines = mutate_shared.changed_lines(repo, rev(repo, "main"), feat, "calc.py")
        add_line = unique_line(show(repo, feat, "calc.py"), "    return a + b")
        self.assertIn(add_line, tip_lines, "the fixture: main's move must make feat's add() line differ from main")
        self.assertNotIn(add_line, branch_lines, "the fixture: feat's add() line is not the change's")
        text = show(repo, feat, "calc.py")
        want_made = mutants_on(text, branch_lines)
        self.assertNotEqual(want_made, mutants_on(text, tip_lines), "the two oracles must differ, or the test is idle")
        folder, log = fixture_log()
        code, out, err = changed_run(repo, CHANGED, base="main", head="feat", log=log)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(read_log(log)["made"], want_made,
                         "made should count the mutants of the merge-base lines, not the lines against main's tip")

    def test_a_crash_is_not_a_kill(self):
        repo = crash_repo()
        text = show(repo, "feat", "calc.py")
        sub_line = unique_line(text, "    return a - b")
        want = mutants_on(text, [sub_line])
        self.assertGreater(want, 0, "the fixture needs mutants on sub")
        folder, log = fixture_log()
        code, out, err = changed_run(repo, CHANGED, log=log)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        data = read_log(log)
        self.assertEqual(data["killed"], 0, "a mutant whose suite throws must not count as killed")
        self.assertEqual(data["crashed"], want, "every mutant of sub throws, so each one reads crashed")
        self.assertEqual(share_of(out)[:2], (0, want), "the share should read 0 over the %d that ran" % want)

    def test_select_runs_the_unchanged_suite_on_the_mutants_of_its_file(self):
        repo = selected_repo()
        text = show(repo, "feat", "calc.py")
        line = unique_line(text, "    return product")
        want = mutants_on(text, [line])
        self.assertGreater(want, 0, "the fixture needs mutants on the product line")
        self.assertEqual(git(repo, "diff", "--name-only", "main", "feat"), "calc.py",
                         "the fixture: the change must touch the product only, not the suite")
        folder, log = fixture_log()
        code, out, err = changed_run(repo, SELECTED, log=log)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        data = read_log(log)
        self.assertEqual(data["killed"], want, "select must bring the unchanged suite to the mutants of calc.py")
        self.assertEqual(data["not_run"], 0, "every mutant of a file the select lists must run")
        self.assertEqual(share_of(out)[2], 100.0, "a full kill reads 100%")
        self.assertEqual(untested_of(out), [], "a full kill leaves no untested line")

    def test_without_select_only_the_changed_suites_run(self):
        repo = selected_repo()
        text = show(repo, "feat", "calc.py")
        line = unique_line(text, "    return product")
        want = mutants_on(text, [line])
        folder, log = fixture_log()
        code, out, err = changed_run(repo, CHANGED, log=log)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        data = read_log(log)
        self.assertEqual(data["not_run"], want, "no changed suite reaches calc.py, so every mutant is not_run")
        self.assertEqual(data["killed"], 0, "the unchanged suite must not kill without select")
        self.assertEqual(share_of(out)[:2], (0, 0), "nothing ran, so the share reads 0/0")
        self.assertEqual(untested_of(out), ["calc.py:%d" % line], "the not_run line is untested")

    def test_a_select_that_pins_nothing_still_exits_0_at_0_percent(self):
        repo = weak_repo()
        facts = partial_facts(repo)
        folder, log = fixture_log()
        code, out, err = changed_run(repo, SELECTED, log=log)
        self.assertEqual(code, 0, "a low share must not fail the run: exit %d\n%s%s" % (code, out, err))
        data = read_log(log)
        self.assertEqual(data["survived"], facts["sub_n"] + facts["div_n"], "every mutant survives")
        killed, ran, percent = share_of(out)
        self.assertEqual((killed, percent), (0, 0.0), "the share reads 0 of %d, as 0%%" % ran)
        self.assertEqual(sorted(untested_of(out)), sorted(["calc.py:%d" % facts["sub"], "calc.py:%d" % facts["div"]]),
                         "each line with a surviving mutant is untested")

    def test_a_change_with_no_mutant_reads_zero_of_zero_and_no_percentage(self):
        repo = empty_repo()
        folder, log = fixture_log()
        code, out, err = changed_run(repo, CHANGED, log=log)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(read_log(log)["made"], 0, "a comment line has no mutant")
        killed, ran, percent = share_of(out)
        self.assertEqual((killed, ran), (0, 0), "no mutant ran: the share reads 0/0")
        self.assertIsNone(percent, "0/0 must not print a percentage: UNKNOWN never reads as a rate")
        self.assertEqual(untested_of(out), [], "no mutant, no untested line")

    def test_limit_caps_the_mutants_made_and_jobs_and_timeout_are_accepted(self):
        repo = partial_repo()
        folder, log = fixture_log()
        code, out, err = changed_run(repo, CHANGED, extra=["--jobs", "2", "--suite-timeout", "60"], log=log,
                                     limit=1)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(read_log(log)["made"], 1, "--limit 1 makes one mutant")

    def test_budget_zero_leaves_every_mutant_not_run_and_never_a_kill(self):
        repo = partial_repo()
        facts = partial_facts(repo)
        folder, log = fixture_log()
        code, out, err = changed_run(repo, CHANGED, extra=["--budget", "0"], log=log)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        data = read_log(log)
        total = facts["sub_n"] + facts["div_n"]
        self.assertEqual((data["killed"], data["crashed"], data["survived"]), (0, 0, 0),
                         "a mutant the budget stopped is never a kill, a crash or a survivor")
        self.assertEqual(data["not_run"], total, "every mutant the budget stopped is not_run")
        self.assertEqual(sorted(untested_of(out)), sorted(["calc.py:%d" % facts["sub"], "calc.py:%d" % facts["div"]]),
                         "a not_run line is untested")

    def test_the_log_writes_one_json_file_and_nothing_into_the_repository(self):
        repo = partial_repo()
        before = (tree_of(repo), status_of(repo))
        self.assertEqual(before[1], "", "the fixture repository must start clean")
        folder, log = fixture_log()
        code, out, err = changed_run(repo, CHANGED, log=log)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(os.listdir(folder), ["log.json"], "the log folder must hold exactly the log")
        self.assertEqual((tree_of(repo), status_of(repo)), before, "the run wrote into the repository")

    def test_the_log_keys_add_up_and_match_the_printed_share(self):
        repo = partial_repo()
        folder, log = fixture_log()
        code, out, err = changed_run(repo, CHANGED, log=log)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        data = read_log(log)
        for key in ("base", "head", "profile", "made", "killed", "crashed", "survived", "not_run", "untested"):
            self.assertIn(key, data, "the log has no %s key" % key)
        self.assertEqual(data["made"], data["killed"] + data["crashed"] + data["survived"] + data["not_run"],
                         "made must equal killed + crashed + survived + not_run")
        killed, ran, _percent = share_of(out)
        self.assertEqual((killed, ran), (data["killed"], data["made"] - data["not_run"]),
                         "the printed share must agree with the log")
        self.assertEqual(sorted(untested_of(out)), sorted(data["untested"]),
                         "the untested lines and the log's untested list must be the same lines")
        self.assertEqual(len(data["untested"]), len(set(data["untested"])), "an untested line is listed once")

    def test_head_defaults_to_HEAD(self):
        repo = partial_repo()
        facts = partial_facts(repo)
        git(repo, "checkout", "-q", "feat")
        folder, log = fixture_log()
        code, out, err = changed_run(repo, CHANGED, head=None, log=log)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(read_log(log)["made"], facts["sub_n"] + facts["div_n"],
                         "with no --head, the mutants are those of HEAD")

    def test_bad_arguments_exit_2(self):
        repo = partial_repo()
        spec = profile_file(CHANGED)
        code, out, err = run_cli(["--changed", repo, "--profile-file", spec])
        self.assertEqual(code, 2, "a missing --base is a bad argument")
        code, out, err = run_cli(["--changed", repo, "--profile-file", spec, "--base", "main", "--limit", "abc"])
        self.assertEqual(code, 2, "a non-number --limit is a bad argument")
        code, out, err = run_cli(["--changed", repo, "--profile", "no-such-profile", "--base", "main"])
        self.assertEqual(code, 2, "a profile name the repository does not hold is a bad argument")


class KnownDefectsTests(unittest.TestCase):
    """`--known-defects`: CAUGHT, MISS and UNKNOWN, the exit codes, the repository left as found, the log."""

    def test_a_caught_mutant_reads_caught_and_exits_0(self):
        repo = defect_repo()
        code, out, err = known_run([defect("kb-caught", "return a + b", "return a - b", "test_calc.py")], repo)
        self.assertEqual(verdicts_of(out), {"kb-caught": "CAUGHT"}, out + err)
        self.assertEqual(code, 0, "all defects caught must exit 0: exit %d" % code)

    def test_a_suite_that_pins_nothing_reads_miss_and_exits_1(self):
        repo = defect_repo()
        code, out, err = known_run([defect("kb-miss", "return a * b", "return 0", "test_nothing.py")], repo)
        self.assertEqual(verdicts_of(out), {"kb-miss": "MISS"}, out + err)
        self.assertEqual(code, 1, "a MISS must exit 1: exit %d" % code)

    def test_a_crash_is_a_miss_not_a_catch(self):
        repo = defect_repo()
        code, out, err = known_run([defect("kb-crash", "return a * b", "return None", "test_crash.py")], repo)
        self.assertEqual(verdicts_of(out), {"kb-crash": "MISS"}, "a suite that throws reads MISS, never CAUGHT\n" + out)
        self.assertEqual(code, 1, "exit %d" % code)

    def test_a_mutant_that_hangs_past_the_suite_timeout_reads_miss(self):
        repo = defect_repo()
        code, out, err = known_run([defect("kb-hang", "return a + b", "return a - b", "test_hang.py")], repo,
                                   extra=["--suite-timeout", "5"])
        self.assertEqual(verdicts_of(out), {"kb-hang": "MISS"}, "a timeout reads MISS, never CAUGHT\n" + out)
        self.assertEqual(code, 1, "exit %d" % code)

    def test_a_stale_anchor_reads_unknown_and_its_mutant_never_runs(self):
        repo = defect_repo()
        code, out, err = known_run([defect("kb-stale", "return a ** b", "return a", "test_nothing.py")], repo)
        self.assertEqual(verdicts_of(out), {"kb-stale": "UNKNOWN"}, "a missing anchor reads UNKNOWN\n" + out)
        self.assertEqual(code, 1, "UNKNOWN must exit 1: exit %d" % code)

    def test_an_anchor_found_twice_reads_unknown_as_ambiguous(self):
        repo = defect_repo()
        code, out, err = known_run([defect("kb-twice", "return a", "return 0", "test_nothing.py")], repo)
        self.assertEqual(verdicts_of(out), {"kb-twice": "UNKNOWN"}, "an anchor in two places reads UNKNOWN\n" + out)
        self.assertEqual(code, 1, "exit %d" % code)

    def test_a_red_clean_suite_reads_unknown_and_is_never_caught(self):
        repo = defect_repo()
        code, out, err = known_run([defect("kb-red", "return a + b", "return a - b", "test_red.py")], repo)
        self.assertEqual(verdicts_of(out), {"kb-red": "UNKNOWN"},
                         "a suite red on the clean copy is a control failure: UNKNOWN, never CAUGHT\n" + out)
        self.assertEqual(code, 1, "exit %d" % code)

    def test_a_clean_suite_that_crashes_reads_unknown(self):
        repo = defect_repo()
        code, out, err = known_run([defect("kb-boom", "return a + b", "return a - b", "test_boom.py")], repo)
        self.assertEqual(verdicts_of(out), {"kb-boom": "UNKNOWN"}, "a control that crashes reads UNKNOWN\n" + out)
        self.assertEqual(code, 1, "exit %d" % code)

    def test_one_line_per_defect_and_all_caught_exits_0(self):
        repo = defect_repo()
        defects = [defect("kb-caught", "return a + b", "return a - b", "test_calc.py"),
                defect("kb-mul", "return a * b", "return a + b", "test_calc.py")]
        code, out, err = known_run(defects, repo)
        self.assertEqual(verdicts_of(out), {"kb-caught": "CAUGHT", "kb-mul": "CAUGHT"}, out + err)
        self.assertEqual(code, 0, "exit %d" % code)

    def test_an_empty_list_prints_one_line_and_exits_0(self):
        repo = defect_repo()
        code, out, err = known_run([], repo)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(len(out.strip().splitlines()), 1, "an empty list prints one line:\n" + out)

    def test_a_missing_file_exits_0_and_says_no_known_defects_listed(self):
        repo = defect_repo()
        absent = os.path.join(fresh(), "absent.json")
        code, out, err = run_cli(["--known-defects", absent, "--repo", repo])
        self.assertEqual(code, 0, "a missing file is not a failure: exit %d\n%s%s" % (code, out, err))
        self.assertIn("no known defects listed", out)

    def test_the_repository_is_left_as_found_and_the_plant_runs_on_head(self):
        repo = defect_repo()
        edited = os.path.join(repo, "calc.py")
        with open(edited, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(CALC_BASE.replace("return a + b", "return (a + b)"))
        before = (status_of(repo), rev(repo, "HEAD"))
        self.assertIn("calc.py", before[0], "the fixture: the working tree must be dirty")
        # The working copy has no `return a + b`, so the anchor is stale there. HEAD has it once.
        code, out, err = known_run([defect("kb-caught", "return a + b", "return a - b", "test_calc.py")], repo)
        self.assertEqual(verdicts_of(out), {"kb-caught": "CAUGHT"}, "the plant reads the HEAD tree, not the working tree\n"
                         + out)
        self.assertEqual((status_of(repo), rev(repo, "HEAD")), before, "the run changed the repository")
        with open(edited, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), CALC_BASE.replace("return a + b", "return (a + b)"),
                             "the run changed the working copy of calc.py")

    def test_the_log_is_one_json_file_and_the_repository_is_untouched(self):
        repo = defect_repo()
        before = (tree_of(repo), status_of(repo))
        folder, log = fixture_log()
        defects = [defect("kb-caught", "return a + b", "return a - b", "test_calc.py"),
                defect("kb-miss", "return a * b", "return 0", "test_nothing.py")]
        code, out, err = known_run(defects, repo, log=log)
        self.assertEqual(code, 1, "exit %d" % code)
        self.assertEqual(os.listdir(folder), ["log.json"], "the log folder must hold exactly the log")
        with open(log, encoding="utf-8") as handle:
            raw = handle.read()
        json.loads(raw)
        for defect_id in ("kb-caught", "kb-miss"):
            self.assertIn(defect_id, raw, "the log names %s" % defect_id)
        self.assertEqual((tree_of(repo), status_of(repo)), before, "the run wrote into the repository")

    def test_known_defects_without_repo_is_a_bad_argument_exit_2(self):
        spec = profile_file([defect("kb-caught", "return a + b", "return a - b", "test_calc.py")])
        code, out, err = run_cli(["--known-defects", spec])
        self.assertEqual(code, 2, "--repo is required: exit %d" % code)


class RealListTests(unittest.TestCase):
    """The list the repository ships, read at HEAD: the three pinned entries and their anchors."""

    PINNED = {
        "df25a68d-rlock": {
            "file": "hooks/mutate_shared.py", "old": "_LIVE_LOCK = threading.RLock()",
            "new": "_LIVE_LOCK = threading.Lock()",
            "argv": ["python3", "hooks/test_mutate_replay.py", "RequestStopTests"]},
        "df25a68d-pw-timeout": {
            "file": "hooks/mutate_shared.py", "old": "if not _PW_NOT_ASSERT.search(error) and _PW_ASSERT",
            "new": "if _PW_ASSERT",
            "argv": ["python3", "hooks/test_mutate_replay.py", "PlaywrightClassifyTests"]},
        "3297d8fa-take-spare": {
            "file": "merge/merge.py", "old": "+ 10) * 60)", "new": ") * 60)",
            "argv": ["python3", "merge/test_merge.py", "LockProseStatesTheCode"]},
    }

    def listed(self):
        """The entries at HEAD, or [] when the list is not committed."""
        done = subprocess.run(["git", "show", "HEAD:%s" % KNOWN_DEFECTS_FILE], cwd=REPO, capture_output=True,
                              text=True, encoding="utf-8")
        if done.returncode != 0:
            return []
        return json.loads(done.stdout)

    def test_the_list_holds_the_three_pinned_defects_by_id(self):
        entries = self.listed()
        self.assertTrue(entries, "%s lists no defects at HEAD" % KNOWN_DEFECTS_FILE)
        ids = {entry.get("id") for entry in entries}
        for defect_id in self.PINNED:
            self.assertIn(defect_id, ids, "%s has no entry %s" % (KNOWN_DEFECTS_FILE, defect_id))

    def test_each_pinned_entry_carries_the_coordinator_plant_and_catcher(self):
        entries = {entry.get("id"): entry for entry in self.listed()}
        self.assertTrue(entries, "%s lists no defects at HEAD" % KNOWN_DEFECTS_FILE)
        for defect_id, want in self.PINNED.items():
            self.assertIn(defect_id, entries, "%s has no entry %s" % (KNOWN_DEFECTS_FILE, defect_id))
            for field, value in want.items():
                self.assertEqual(entries[defect_id].get(field), value, "%s: %s differs" % (defect_id, field))

    def test_every_entry_anchor_is_present_exactly_once_at_head(self):
        entries = self.listed()
        self.assertTrue(entries, "%s lists no defects at HEAD" % KNOWN_DEFECTS_FILE)
        for entry in entries:
            for field in ("id", "name", "file", "old", "new", "argv", "classify"):
                self.assertIn(field, entry, "%s has no %s" % (entry.get("id"), field))
            self.assertIn(entry["classify"], ("fail_line", "node_tap", "playwright"),
                          "%s names an unknown classifier" % entry["id"])
            text = show(REPO, "HEAD", entry["file"])
            self.assertEqual(text.count(entry["old"]), 1,
                             "%s: the anchor must occur exactly once in %s at HEAD" % (entry["id"], entry["file"]))


class ReplayChangedOnlyTests(unittest.TestCase):
    """The old replay, unchanged: a changed suite only. These pass on main and pin the opt-in boundary."""

    def test_a_product_only_pull_request_never_runs_the_unchanged_suite_on_its_mutants(self):
        repo, sha = replayed({"calc.py": CALC_MUL_PRODUCT})
        row = mutate_shared.replay_pr(repo, sha, SELECTED, limit=50, suite_timeout=60, jobs=2)
        self.assertEqual(row["status"], "NO_TESTS", "no suite changed: the replay reads NO_TESTS")
        self.assertEqual(row["killed"], 0, "the replay must not run the unchanged suite, even with select")

    def test_a_pull_request_that_changes_its_suite_still_reads_ok_and_kills_its_mutants(self):
        repo, sha = replayed({"calc.py": CALC_MUL_PRODUCT, "test_calc.py": SUITE + "# mul is checked in calc\n"})
        row = mutate_shared.replay_pr(repo, sha, SELECTED, limit=50, suite_timeout=60, jobs=2)
        self.assertEqual(row["status"], "OK", row.get("reason"))
        self.assertGreater(row["made"], 0, "the fixture needs mutants on the product line")
        self.assertEqual(row["killed"], row["made"], "the changed suite pins mul: every mutant dies")


class TestsForTests(unittest.TestCase):
    """`--tests-for`: the REPORT_TARGETS suites of a listed file, else the tracked tests beside an unlisted one."""

    def test_a_listed_path_prints_its_report_targets_suites(self):
        targets = dict(mutate_guard.REPORT_TARGETS)
        target = "hooks/feedback_guard.py"
        self.assertIn(target, targets, "REPORT_TARGETS does not list %s" % target)
        code, out, err = run_cli(["--tests-for", target])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(set(SUITE_NAME.findall(out)), set(targets[target]),
                         "--tests-for must print the REPORT_TARGETS suites of %s" % target)

    def test_an_unlisted_path_prints_each_tracked_test_beside_it(self):
        target = "hooks/guard.py"
        self.assertNotIn(target, dict(mutate_guard.REPORT_TARGETS), "the fixture: %s must be unlisted" % target)
        want = {name for name in git(REPO, "ls-files", "hooks").split("\n")
                if re.fullmatch(r"hooks/test_guard(_[^/]*)?\.py", name)}
        self.assertTrue(want, "the fixture: hooks/ holds tracked test_guard files")
        code, out, err = run_cli(["--tests-for", target])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(set(SUITE_NAME.findall(out)), want,
                         "an unlisted path reads each tracked test_<stem>.py and test_<stem>_*.py beside it")


if __name__ == "__main__":
    unittest.main()
