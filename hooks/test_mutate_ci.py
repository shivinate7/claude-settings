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
  share. `--budget S` is a wall deadline counted from the start of the run: a mutant not started by then is not_run, and
  a suite still running then is killed, its mutant not_run too. `--log PATH` writes one JSON file with the keys base,
  head, profile, made, killed, crashed, survived, not_run and untested, and writes nothing else into REPO. With no
  changed mutant the share reads `0/0` with no percentage.
- `--known-defects FILE --repo REPO (--profile NAME | --profile-file JSON) [--base REF] [--suite-timeout S] [--log PATH]`. FILE
  is a JSON list of planted defects. The profile is required, as for `--changed`: its install runs and its folder is linked
  into the checkout. A missing profile exits 2. Each defect prints one line, `CAUGHT|MISS|UNKNOWN id: name [reason]`. It exits 1 when any defect is MISS or UNKNOWN, else 0. A
  missing FILE prints one `UNKNOWN` line that names the path, and exits 1. An empty list prints one line and exits 0, and with `--base REF` an empty list `[]` exits 0 only when REF's list names no entry.
  With `--base REF`, FILE is the head list and REF's list is read with `git show REF:<FILE relative to REPO>`. Each id on
  REF's list needs a head row, unless a commit in `REF..HEAD` has a `Known-defect-removed: <id>` trailer naming that exact
  id. A dropped id prints `MISSING <id>: ...` and exits 1. A REF that does not resolve, a FILE outside REPO, or a head with
  no list prints an `UNKNOWN` line and exits 1. A REF with no list file checks nothing against it. An entry on REF's list with no `id` reads UNKNOWN. A base entry whose fields differ on the head, compared as parsed objects,
  reads `CHANGED <id>` and exits 1, unless a commit in `REF..HEAD` has a `Known-defect-changed: <id>` trailer. A
  `Known-defect-removed` trailer does not count for it.
- `--tests-for PATH`. It prints the REPORT_TARGETS suites for PATH when listed, and nothing else. Else it prints each
  tracked `test_<stem>.py` and `test_<stem>_*.py` beside PATH. A .py PATH also gets each tracked `test_*.py` in the
  repository that loads the module `<stem>`: an `import`, an `importlib.import_module` or `__import__` call, or a file
  loader (`spec_from_file_location`, `SourceFileLoader`, `runpy.run_path`) whose path names `<stem>.py`. The loads are
  found with `ast`, never a grep. A tracked test that fails to parse is skipped.
- `--lint-suites BASE`. It prints each suite that tests a file of `git diff BASE...HEAD`, and each changed suite. A suite
  reaches a changed file through a module it loads, followed through the imports of that module (LintSuitesChainTests).

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
ENTRY = {"--changed": "changed_main", "--known-defects": "known_defects_main", "--tests-for": "tests_for_main",
         "--lint-suites": "lint_suites_main"}

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


def state_of(repo):
    """What a run must leave as found, by name: the worktrees, the branches, the working tree and HEAD of `repo`."""
    return {"worktrees": git(repo, "worktree", "list", "--porcelain"), "branches": git(repo, "branch", "--list"),
            "status": status_of(repo), "HEAD": rev(repo, "HEAD")}


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
# The clean sub returns 3 at once. A mutant whose sub returns None hangs here until a kill: the budget's deadline, which comes first.
SUITE_HANGS_ON_NONE = ("import sys\n"
                       "import time\n"
                       "from calc import sub\n\n"
                       "if sub(5, 2) is None:\n"
                       "    time.sleep(30)\n"
                       "if sub(5, 2) != 3:\n"
                       "    print('FAIL: sub(5, 2) is not 3')\n"
                       "    sys.exit(1)\n"
                       "print('ok')\n")

CHANGED = {"code": r"^calc\.py$", "tests": r"^test_[^/]+\.py$", "argv": [PY, "{suite}"],
           "classify": "fail_line", "install": None, "sparse_skip": []}
SELECTED = dict(CHANGED, select=[PY, "select_for.py", "{path}"])

# The profile a case names when it installs nothing: the one known_run passes by default.
NO_INSTALL = {"install": None}
# A profile's install writes kb_oracle.py into node_modules, in the deps folder it runs in. The catcher beside
# the lockfile imports it from node_modules, and so reads the install. The module name is this fixture's alone.
ORACLE_MODULE = "def add(a, b):\n    return a + b\n"
ORACLE_INSTALL = [PY, "-c", "import pathlib\npathlib.Path('node_modules').mkdir(exist_ok=True)\n"
                  "pathlib.Path('node_modules', 'kb_oracle.py').write_text(%r, encoding='utf-8')" % ORACLE_MODULE]
ORACLE_SUITE = ("import os\n"
                "import sys\n\n"
                "HERE = os.path.dirname(os.path.abspath(__file__))\n"
                "sys.path.insert(0, os.path.join(HERE, 'node_modules'))\n"
                "from calc import add\n"
                "import kb_oracle\n\n"
                "if add(1, 2) != kb_oracle.add(1, 2):\n"
                "    print('FAIL: add(1, 2) is not the installed oracle value')\n"
                "    sys.exit(1)\n"
                "print('ok')\n")
ROOT_LOCK, APP_LOCK = "requirements.lock", "app/deps.lock"  # committed, so their hashes are the cache keys
LOCK_TEXT = "kb-oracle==1.0\n"


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


def budget_repo():
    """feat adds sub, and its changed suite hangs on a sub that returns None: every mutant of sub runs into the budget."""
    repo = new_repo()
    put(repo, {"calc.py": CALC_BASE, "test_calc.py": SUITE})
    commit(repo, "Base: add and mul")
    topic(repo, "feat", {"calc.py": CALC_SUB_ONLY, "test_calc.py": SUITE_HANGS_ON_NONE}, "Add sub and wait on it")
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


def defect_repo(extra_files=None):
    """main holds calc.py and six suites. Each suite is green on the clean source, except test_red.py and
    test_boom.py, which are red and crashing on it. `extra_files` ({path: text}) are committed with them."""
    repo = new_repo()
    files = {
        "calc.py": CALC_BASE,
        "test_calc.py": SUITE,
        "test_nothing.py": "print('ok')\n",
        "test_crash.py": "from calc import mul\nprint(mul(2, 3) * 2)\n",
        "test_hang.py": "from calc import add\nwhile add(1, 2) != 3:\n    pass\nprint('ok')\n",
        "test_red.py": "print('FAIL: the clean code is wrong')\nraise SystemExit(1)\n",
        "test_boom.py": "raise RuntimeError('the clean suite crashes')\n",
    }
    files.update(extra_files or {})
    put(repo, files)
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


def run_cli(args, cwd=REPO):
    """`hooks/mutate_guard.py <args>` in a child Python, from `cwd`: the repository root, or a fixture repository, whose
    `git ls-files` the mode reads. Returns (exit code, stdout, stderr). The mode's entry point is checked first: when it
    is missing, the case fails by name and nothing runs. A run past CLI_LIMIT is killed with its group and fails."""
    flag = args[0]
    name = ENTRY[flag]
    if getattr(mutate_guard, name, None) is None:
        raise AssertionError("the %s mode is missing: hooks/mutate_guard.py has no %s" % (flag, name))
    command = [PY, os.path.join(HERE, "mutate_guard.py")] + list(args)
    proc = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
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


def known_run(defects, repo, extra=(), log=None, profile=None):
    """`--known-defects` on `defects`, a list of planted defects, against `repo`, under `profile` (a plain profile or a
    profile of parts). With no profile it installs nothing: NO_INSTALL."""
    spec = os.path.join(fresh(), "known-defects.json")
    with open(spec, "w", encoding="utf-8") as handle:
        json.dump(defects, handle)
    profile = NO_INSTALL if profile is None else profile
    args = ["--known-defects", spec, "--repo", repo, "--profile-file", profile_file(profile)] + list(extra)
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

    def test_the_budget_is_a_wall_deadline_that_kills_the_suite_still_running(self):
        repo = budget_repo()
        text = show(repo, "feat", "calc.py")
        want = mutants_on(text, [unique_line(text, "    return a - b")])
        self.assertGreater(want, 0, "the fixture needs mutants on sub")
        folder, log = fixture_log()
        # The suite timeout is past the budget, so only the deadline kill can end a hung mutant before it; it keeps a red run short.
        code, out, err = changed_run(repo, CHANGED, extra=["--budget", "3", "--suite-timeout", "5"], log=log)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        data = read_log(log)
        self.assertEqual(data["not_run"], want,
                         "a suite the budget passes while it runs is killed and counts not_run\n" + out)
        self.assertEqual((data["killed"], data["survived"], data["crashed"]), (0, 0, 0),
                         "a mutant the budget killed is neither a kill, a survivor nor a crash")

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

    def test_a_missing_file_reads_unknown_naming_the_path_and_exits_1(self):
        repo = defect_repo()
        absent = os.path.join(fresh(), "absent.json")
        code, out, err = run_cli(["--known-defects", absent, "--repo", repo, "--profile-file", profile_file(NO_INSTALL)])
        self.assertEqual(code, 1, "a missing list reads UNKNOWN, and UNKNOWN exits 1: exit %d\n%s%s" % (code, out, err))
        unknown = [line for line in out.splitlines() if line.startswith("UNKNOWN")]
        self.assertTrue(any(absent in line for line in unknown), "no UNKNOWN line names %s:\n%s" % (absent, out))

    def test_the_repository_is_left_as_found_and_the_plant_runs_on_head(self):
        repo = defect_repo()
        edited = os.path.join(repo, "calc.py")
        with open(edited, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(CALC_BASE.replace("return a + b", "return (a + b)"))
        before = state_of(repo)
        self.assertIn("calc.py", before["status"], "the fixture: the working tree must be dirty")
        # The working copy has no `return a + b`, so the anchor is stale there. HEAD has it once.
        code, out, err = known_run([defect("kb-caught", "return a + b", "return a - b", "test_calc.py")], repo)
        self.assertEqual(verdicts_of(out), {"kb-caught": "CAUGHT"}, "the plant reads the HEAD tree, not the working tree\n"
                         + out)
        self.assertEqual(state_of(repo), before, "the run changed the repository's worktrees, branches, status or HEAD")
        with open(edited, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), CALC_BASE.replace("return a + b", "return (a + b)"),
                             "the run changed the working copy of calc.py")

    def test_the_log_is_one_json_file_and_the_repository_is_untouched(self):
        repo = defect_repo()
        before = (tree_of(repo), state_of(repo))
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
        self.assertEqual((tree_of(repo), state_of(repo)), before,
                         "the run wrote into the repository's files, worktrees, branches, status or HEAD")

    def test_known_defects_without_repo_is_a_bad_argument_exit_2(self):
        spec = profile_file([defect("kb-caught", "return a + b", "return a - b", "test_calc.py")])
        code, out, err = run_cli(["--known-defects", spec, "--profile-file", profile_file(NO_INSTALL)])
        self.assertEqual(code, 2, "--repo is required: exit %d" % code)

    def test_a_profile_install_that_writes_a_module_lets_the_catcher_import_it_and_reads_caught(self):
        repo = defect_repo(extra_files={ROOT_LOCK: LOCK_TEXT, "test_oracle.py": ORACLE_SUITE})
        profile = {"install": ORACLE_INSTALL, "lockfile": ROOT_LOCK}
        code, out, err = known_run([defect("kb-deps", "return a + b", "return a - b", "test_oracle.py")], repo,
                                   profile=profile)
        self.assertIn("kb-deps", verdicts_of(out), "no verdict line for kb-deps (exit %d):\n%s%s" % (code, out, err))
        self.assertEqual(verdicts_of(out), {"kb-deps": "CAUGHT"},
                         "the catcher imports a module the profile's install wrote into node_modules, so it reads "
                         "CAUGHT, not UNKNOWN\n" + out + err)
        self.assertEqual(code, 0, "all defects caught must exit 0: exit %d\n%s%s" % (code, out, err))

    def test_a_parts_profile_links_the_install_of_its_part_beside_its_lockfile_and_reads_caught(self):
        repo = defect_repo(extra_files={"app/calc.py": CALC_BASE, "app/test_oracle.py": ORACLE_SUITE,
                                        APP_LOCK: LOCK_TEXT})
        profile = {"parts": {"oracle": {"install": ORACLE_INSTALL, "lockfile": APP_LOCK},
                             "plain": {"install": None}}}
        defects = [defect("kb-part", "return a + b", "return a - b", "app/test_oracle.py", file="app/calc.py")]
        code, out, err = known_run(defects, repo, profile=profile)
        self.assertIn("kb-part", verdicts_of(out), "no verdict line for kb-part (exit %d):\n%s%s" % (code, out, err))
        self.assertEqual(verdicts_of(out), {"kb-part": "CAUGHT"},
                         "the install of the part with a lockfile is linked beside that lockfile, so the catcher "
                         "reads CAUGHT\n" + out + err)
        self.assertEqual(code, 0, "all defects caught must exit 0: exit %d\n%s%s" % (code, out, err))

    def test_a_failed_install_reads_every_defect_unknown_naming_the_install_and_exits_1(self):
        repo = defect_repo(extra_files={ROOT_LOCK: LOCK_TEXT, "test_oracle.py": ORACLE_SUITE})
        profile = {"install": [PY, "-c", "import sys\nsys.exit(3)"], "lockfile": ROOT_LOCK}
        defects = [defect("kb-dep", "return a + b", "return a - b", "test_oracle.py"),
                   defect("kb-plain", "return a * b", "return a + b", "test_calc.py")]
        code, out, err = known_run(defects, repo, profile=profile)
        self.assertEqual(verdicts_of(out), {"kb-dep": "UNKNOWN", "kb-plain": "UNKNOWN"},
                         "a failed install makes every defect UNKNOWN, the install-free catcher too\n" + out + err)
        lines = [line for line in out.splitlines() if line.startswith("UNKNOWN kb-")]
        self.assertEqual(len(lines), 2, "one UNKNOWN line per defect:\n" + out)
        for line in lines:
            self.assertIn("install", line, "the UNKNOWN reason must name the install: " + line)
        self.assertEqual(code, 1, "UNKNOWN exits 1: exit %d\n%s%s" % (code, out, err))

    def test_known_defects_without_a_profile_is_a_bad_argument_exit_2(self):
        repo = defect_repo()
        spec = profile_file([defect("kb-caught", "return a + b", "return a - b", "test_calc.py")])
        code, out, err = run_cli(["--known-defects", spec, "--repo", repo])
        self.assertEqual(code, 2, "--known-defects takes --profile or --profile-file, and exits 2 without one: "
                         "exit %d\n%s%s" % (code, out, err))

    def test_a_failed_install_of_one_part_reads_every_defect_unknown_when_another_part_shares_its_lockfile(self):
        repo = defect_repo(extra_files={ROOT_LOCK: LOCK_TEXT, "test_oracle.py": ORACLE_SUITE})
        profile = {"parts": {"a": {"install": ORACLE_INSTALL, "lockfile": ROOT_LOCK},
                             "b": {"install": [PY, "-c", "import sys\nsys.exit(3)"], "lockfile": ROOT_LOCK}}}
        defects = [defect("kb-f1-dep", "return a + b", "return a - b", "test_oracle.py"),
                   defect("kb-f1-plain", "return a * b", "return a + b", "test_calc.py")]
        code, out, err = known_run(defects, repo, profile=profile)
        self.assertEqual(verdicts_of(out), {"kb-f1-dep": "UNKNOWN", "kb-f1-plain": "UNKNOWN"},
                         "part b's install failed, so every defect reads UNKNOWN; a shared lockfile must not hide it\n"
                         + out + err)
        lines = [line for line in out.splitlines() if line.startswith("UNKNOWN kb-f1-")]
        self.assertEqual(len(lines), 2, "one UNKNOWN line per defect:\n" + out)
        for line in lines:
            self.assertIn("install", line, "the UNKNOWN reason must name the install: " + line)
        self.assertEqual(code, 1, "UNKNOWN exits 1: exit %d\n%s%s" % (code, out, err))

    def test_a_tracked_file_at_the_link_path_reads_unknown_naming_the_path_and_never_runs_on_it(self):
        # The tracked node_modules/kb_oracle.py is the module itself. A run that silently used it would read CAUGHT.
        repo = defect_repo(extra_files={ROOT_LOCK: LOCK_TEXT, "test_oracle.py": ORACLE_SUITE,
                                        "node_modules/kb_oracle.py": ORACLE_MODULE})
        profile = {"install": ORACLE_INSTALL, "lockfile": ROOT_LOCK}
        code, out, err = known_run([defect("kb-f2", "return a + b", "return a - b", "test_oracle.py")], repo,
                                   profile=profile)
        self.assertIn("kb-f2", verdicts_of(out), "no verdict line for kb-f2 (exit %d):\n%s%s" % (code, out, err))
        self.assertEqual(verdicts_of(out)["kb-f2"], "UNKNOWN",
                         "a tracked file at the link path is a link failure: UNKNOWN, never a silent run\n" + out + err)
        lines = [line for line in out.splitlines() if line.startswith("UNKNOWN kb-f2")]
        self.assertEqual(len(lines), 1, "one UNKNOWN line for kb-f2:\n" + out)
        self.assertIn("node_modules", lines[0], "the UNKNOWN reason must name the link path: " + lines[0])
        self.assertEqual(code, 1, "UNKNOWN exits 1: exit %d\n%s%s" % (code, out, err))

    def test_two_parts_with_one_lockfile_and_one_install_share_one_link_and_read_caught(self):
        # Good skip, pinned: the second part finds the link its first part made and leaves it. Green on the current code.
        repo = defect_repo(extra_files={ROOT_LOCK: LOCK_TEXT, "test_oracle.py": ORACLE_SUITE})
        profile = {"parts": {"a": {"install": ORACLE_INSTALL, "lockfile": ROOT_LOCK},
                             "b": {"install": ORACLE_INSTALL, "lockfile": ROOT_LOCK}}}
        code, out, err = known_run([defect("kb-f2b", "return a + b", "return a - b", "test_oracle.py")], repo,
                                   profile=profile)
        self.assertIn("kb-f2b", verdicts_of(out), "no verdict line for kb-f2b (exit %d):\n%s%s" % (code, out, err))
        self.assertEqual(verdicts_of(out), {"kb-f2b": "CAUGHT"},
                         "two parts with one lockfile and one install share one link, so the catcher reads CAUGHT\n"
                         + out + err)
        self.assertEqual(code, 0, "all defects caught must exit 0: exit %d\n%s%s" % (code, out, err))

    def test_a_failed_install_with_several_output_lines_gives_a_one_line_reason(self):
        repo = defect_repo(extra_files={ROOT_LOCK: LOCK_TEXT, "test_oracle.py": ORACLE_SUITE})
        profile = {"install": [PY, "-c", "import sys\nprint('one')\nprint('two')\nprint('three', file=sys.stderr)\n"
                                         "sys.exit(4)\n"], "lockfile": ROOT_LOCK}
        code, out, err = known_run([defect("kb-f3", "return a + b", "return a - b", "test_oracle.py")], repo,
                                   profile=profile)
        self.assertEqual(verdicts_of(out), {"kb-f3": "UNKNOWN"}, "a failed install reads UNKNOWN\n" + out + err)
        self.assertEqual(len(out.strip().splitlines()), 2,
                         "the UNKNOWN reason is one line, so the output is one defect line and the totals line:\n"
                         + out + err)
        self.assertEqual(code, 1, "UNKNOWN exits 1: exit %d\n%s%s" % (code, out, err))

    def test_a_profile_file_holding_a_json_list_is_a_bad_argument_exit_2_with_no_traceback(self):
        repo = defect_repo()
        code, out, err = known_run([defect("kb-f4", "return a + b", "return a - b", "test_calc.py")], repo,
                                   profile=[1])
        self.assertEqual(code, 2, "a profile that is not a JSON object is a bad argument: exit %d\n%s%s"
                         % (code, out, err))
        self.assertNotIn("Traceback", err, "a bad profile file prints one ERROR line, never a traceback:\n" + err)

    def test_two_parts_with_one_lockfile_and_link_but_different_installs_read_unknown_naming_the_link_path(self):
        # Both installs succeed. Only one folder can sit at the link, so the second part must read UNKNOWN, not reuse it.
        repo = defect_repo(extra_files={ROOT_LOCK: LOCK_TEXT, "test_oracle.py": ORACLE_SUITE})
        other = [PY, "-c", "import pathlib\npathlib.Path('node_modules').mkdir(exist_ok=True)\n"
                 "pathlib.Path('node_modules', 'kb_other.py').write_text(%r, encoding='utf-8')" % "X = 1\n"]
        profile = {"parts": {"a": {"install": ORACLE_INSTALL, "lockfile": ROOT_LOCK},
                             "b": {"install": other, "lockfile": ROOT_LOCK}}}
        defects = [defect("kb-l1", "return a + b", "return a - b", "test_oracle.py"),
                   defect("kb-l2", "return a * b", "return a + b", "test_calc.py")]
        code, out, err = known_run(defects, repo, profile=profile)
        self.assertEqual(verdicts_of(out), {"kb-l1": "UNKNOWN", "kb-l2": "UNKNOWN"},
                         "two installs cannot share one link: every defect reads UNKNOWN\n" + out + err)
        lines = [line for line in out.splitlines() if line.startswith("UNKNOWN kb-l")]
        self.assertEqual(len(lines), 2, "one UNKNOWN line per defect:\n" + out)
        for line in lines:
            self.assertIn("node_modules", line, "the UNKNOWN reason must name the link path: " + line)
        self.assertEqual(code, 1, "UNKNOWN exits 1: exit %d\n%s%s" % (code, out, err))


# ---------------------------------------------------------------------------------------------------
# `--known-defects FILE --repo REPO --base REF`. The fixtures commit the list inside the repository, so FILE is a path in
# it, and REF's list is read with `git show REF:<FILE relative to REPO>`. Each case checks its fixture before the run: the
# base holds the id it probes, and the head has, or has not, the row it probes.

BASE_TAG = "base"
DROP = defect("kb-drop", "return a + b", "return a - b", "test_calc.py")  # CAUGHT on the clean calc.py (add)
KEEP = defect("kb-keep", "return a * b", "return a + b", "test_calc.py")  # CAUGHT on the clean calc.py (mul)
MISSING_LINE = re.compile(r"^MISSING (\S+):", re.M)
CAUGHT_LINE = re.compile(r"^CAUGHT (\S+?): ", re.M)
CHANGED_LINE = re.compile(r"^CHANGED (\S+?)(?::|\s|$)", re.M)


def list_text(entries):
    return json.dumps(entries, indent=1) + "\n"


def base_list_repo(entries):
    """defect_repo() with `entries` committed as the list, and the tag BASE_TAG on that commit."""
    repo = defect_repo()
    put(repo, {KNOWN_DEFECTS_FILE: list_text(entries)})
    commit(repo, "List the planted defects")
    git(repo, "tag", BASE_TAG)
    return repo


def head_list(repo, entries, message):
    """Commit `entries` as the list at HEAD. None deletes the file. Returns the list's path in `repo`."""
    put(repo, {KNOWN_DEFECTS_FILE: None if entries is None else list_text(entries)})
    commit(repo, message)
    return os.path.join(repo, KNOWN_DEFECTS_FILE)


def base_ids(repo):
    """The ids on the list at BASE_TAG. A base with no list file raises."""
    return {entry["id"] for entry in json.loads(show(repo, BASE_TAG, KNOWN_DEFECTS_FILE))}


def known_base_run(list_path, repo, base=BASE_TAG):
    """`--known-defects LIST --repo REPO --profile-file (no install) --base REF`. A missing --base flag fails the case by name."""
    code, out, err = run_cli(["--known-defects", list_path, "--repo", repo, "--profile-file", profile_file(NO_INSTALL), "--base", base])
    if code == 2 and "unrecognized arguments" in err and "--base" in err:
        raise AssertionError("--known-defects has no --base flag, so no base list was compared:\n" + err)
    return code, out, err


def missing_of(out):
    return set(MISSING_LINE.findall(out))


def caught_of(out):
    return set(CAUGHT_LINE.findall(out))


def changed_of(out):
    return set(CHANGED_LINE.findall(out))


def unknown_lines(out):
    return [line for line in out.splitlines() if line.startswith("UNKNOWN")]


class KnownDefectsBaseTests(unittest.TestCase):
    """`--base REF`: each id on REF's list needs a head row, or a `Known-defect-removed:` trailer in REF..HEAD that names
    it exactly. A REF that does not resolve, a list outside the repository, and a head with no list read UNKNOWN. A base
    entry whose fields change on the head reads CHANGED unless a `Known-defect-changed:` trailer names its id."""

    def test_without_base_a_dropped_id_passes_as_today(self):
        """The control, green on the old code: with no --base only the head list is read, so a dropped id passes."""
        repo = base_list_repo([DROP, KEEP])
        listed = head_list(repo, [KEEP], "Drop kb-drop")
        self.assertEqual(base_ids(repo), {"kb-drop", "kb-keep"}, "the fixture: the base list holds both ids")
        code, out, err = run_cli(["--known-defects", listed, "--repo", repo, "--profile-file", profile_file(NO_INSTALL)])
        self.assertEqual(caught_of(out), {"kb-keep"}, "the head row for kb-keep must read CAUGHT\n" + out + err)
        self.assertEqual(code, 0, "without --base the head list alone is read: exit %d\n%s%s" % (code, out, err))

    def test_a_dropped_id_with_no_trailer_prints_missing_and_exits_1(self):
        repo = base_list_repo([DROP, KEEP])
        listed = head_list(repo, [KEEP], "Drop kb-drop")
        self.assertIn("kb-drop", base_ids(repo), "the fixture: the base list holds kb-drop")
        code, out, err = known_base_run(listed, repo)
        self.assertIn("kb-drop", missing_of(out),
                      "the head drops kb-drop, no commit names it, and no MISSING kb-drop: line is printed\n" + out + err)
        self.assertEqual(code, 1, "a MISSING id exits 1: exit %d\n%s%s" % (code, out, err))

    def test_a_dropped_id_named_by_a_known_defect_removed_trailer_exits_0(self):
        repo = base_list_repo([DROP, KEEP])
        listed = head_list(repo, [KEEP], "Drop kb-drop\n\nKnown-defect-removed: kb-drop")
        self.assertIn("kb-drop", base_ids(repo), "the fixture: the base list holds kb-drop")
        code, out, err = known_base_run(listed, repo)
        self.assertEqual(missing_of(out), set(),
                         "a commit in REF..HEAD names kb-drop in its trailer, so no MISSING line may print\n" + out + err)
        self.assertEqual(caught_of(out), {"kb-keep"}, "the head row for kb-keep must read CAUGHT\n" + out + err)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))

    def test_a_trailer_naming_a_longer_id_does_not_excuse_the_drop(self):
        repo = base_list_repo([DROP, KEEP])
        listed = head_list(repo, [KEEP], "Drop kb-drop\n\nKnown-defect-removed: kb-drop-2")
        self.assertIn("kb-drop", base_ids(repo), "the fixture: the base list holds kb-drop")
        code, out, err = known_base_run(listed, repo)
        self.assertIn("kb-drop", missing_of(out),
                      "the trailer naming kb-drop-2 excused kb-drop: a trailer must name the exact id\n" + out + err)
        self.assertEqual(code, 1, "exit %d\n%s%s" % (code, out, err))

    def test_an_id_renamed_on_head_prints_missing_for_the_old_id_and_exits_1(self):
        repo = base_list_repo([DROP, KEEP])
        renamed = dict(DROP, id="kb-renamed", name="kb-renamed")
        listed = head_list(repo, [renamed, KEEP], "Rename kb-drop to kb-renamed")
        self.assertIn("kb-drop", base_ids(repo), "the fixture: the base list holds kb-drop")
        code, out, err = known_base_run(listed, repo)
        self.assertIn("kb-drop", missing_of(out),
                      "the old id kb-drop has no head row, so it must read MISSING\n" + out + err)
        self.assertEqual(code, 1, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(caught_of(out), {"kb-renamed", "kb-keep"},
                         "the renamed entry must still run and read CAUGHT\n" + out + err)

    def test_a_head_that_adds_an_entry_exits_0(self):
        repo = base_list_repo([DROP, KEEP])
        added = defect("kb-new", "return a * b", "return a - b", "test_calc.py")
        listed = head_list(repo, [DROP, KEEP, added], "Add kb-new")
        self.assertEqual(base_ids(repo), {"kb-drop", "kb-keep"}, "the fixture: the base list holds two ids")
        code, out, err = known_base_run(listed, repo)
        self.assertEqual(missing_of(out), set(), "an added entry drops nothing, so no MISSING line may print\n" + out + err)
        self.assertEqual(caught_of(out), {"kb-drop", "kb-keep", "kb-new"},
                         "every head row must read CAUGHT\n" + out + err)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))

    def test_a_re_pointed_plant_with_no_trailer_reads_changed_and_exits_1(self):
        repo = base_list_repo([DROP, KEEP])
        repointed = dict(DROP, old="return a * b", new="return a - b")
        listed = head_list(repo, [repointed, KEEP], "Re-point the plant of kb-drop")
        self.assertIn("kb-drop", base_ids(repo), "the fixture: the base list holds kb-drop")
        code, out, err = known_base_run(listed, repo)
        self.assertIn("kb-drop", changed_of(out),
                      "a base entry whose plant changed, with no Known-defect-changed trailer, must read CHANGED kb-drop\n"
                      + out + err)
        self.assertEqual(code, 1, "exit %d\n%s%s" % (code, out, err))

    def test_a_re_pointed_plant_with_a_changed_trailer_in_the_range_exits_0(self):
        repo = base_list_repo([DROP, KEEP])
        repointed = dict(DROP, old="return a * b", new="return a - b")
        message = ("Re-point the plant of kb-drop\n\nKnown-defect-changed: kb-drop\n"
                   "Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>")
        listed = head_list(repo, [repointed, KEEP], message)
        self.assertIn("kb-drop", base_ids(repo), "the fixture: the base list holds kb-drop")
        code, out, err = known_base_run(listed, repo)
        self.assertEqual(changed_of(out), set(),
                         "a commit in REF..HEAD names kb-drop in Known-defect-changed, so no CHANGED line may print\n"
                         + out + err)
        self.assertEqual(caught_of(out), {"kb-drop", "kb-keep"}, "both head rows must read CAUGHT\n" + out + err)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))

    def test_a_re_pointed_plant_with_a_removed_trailer_still_reads_changed_and_exits_1(self):
        repo = base_list_repo([DROP, KEEP])
        repointed = dict(DROP, old="return a * b", new="return a - b")
        message = ("Re-point the plant of kb-drop\n\nKnown-defect-removed: kb-drop\n"
                   "Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>")
        listed = head_list(repo, [repointed, KEEP], message)
        self.assertIn("kb-drop", base_ids(repo), "the fixture: the base list holds kb-drop")
        code, out, err = known_base_run(listed, repo)
        self.assertIn("kb-drop", changed_of(out),
                      "Known-defect-removed names kb-drop, but only Known-defect-changed excuses a changed entry\n"
                      + out + err)
        self.assertEqual(code, 1, "exit %d\n%s%s" % (code, out, err))

    def test_an_argv_only_change_with_no_trailer_reads_changed_and_exits_1(self):
        repo = base_list_repo([DROP, KEEP])
        reargv = dict(DROP, argv=[PY, "test_calc.py", "-q"])
        listed = head_list(repo, [reargv, KEEP], "Pass -q to the suite of kb-drop")
        self.assertIn("kb-drop", base_ids(repo), "the fixture: the base list holds kb-drop")
        code, out, err = known_base_run(listed, repo)
        self.assertIn("kb-drop", changed_of(out),
                      "an argv-only change with no Known-defect-changed trailer must read CHANGED kb-drop\n" + out + err)
        self.assertEqual(code, 1, "exit %d\n%s%s" % (code, out, err))

    def test_a_reordered_or_respaced_entry_is_the_same_entry_and_exits_0(self):
        repo = base_list_repo([DROP, KEEP])
        reordered = dict(reversed(list(DROP.items())))
        text = json.dumps([reordered, KEEP], indent=3, separators=(" , ", " :  ")) + "\n"
        self.assertEqual(json.loads(text)[0], DROP, "the fixture: the head entry parses to the same object")
        self.assertNotEqual(show(repo, BASE_TAG, KNOWN_DEFECTS_FILE), text, "the fixture: the head bytes differ from the base")
        put(repo, {KNOWN_DEFECTS_FILE: text})
        commit(repo, "Reorder the keys and respace the list")
        listed = os.path.join(repo, KNOWN_DEFECTS_FILE)
        code, out, err = known_base_run(listed, repo)
        self.assertEqual(changed_of(out), set(), "the same parsed entry must read no CHANGED line\n" + out + err)
        self.assertEqual(caught_of(out), {"kb-drop", "kb-keep"}, "both head rows must read CAUGHT\n" + out + err)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))

    def test_a_base_ref_that_does_not_resolve_reads_unknown_and_exits_1(self):
        repo = base_list_repo([DROP, KEEP])
        listed = os.path.join(repo, KNOWN_DEFECTS_FILE)
        code, out, err = known_base_run(listed, repo, base="no-such-ref")
        self.assertTrue(any("no-such-ref" in line for line in unknown_lines(out)),
                        "an unresolved --base must print an UNKNOWN line that names the ref\n" + out + err)
        self.assertEqual(code, 1, "exit %d\n%s%s" % (code, out, err))

    def test_a_base_with_no_list_file_exits_0_on_first_adoption(self):
        repo = defect_repo()
        git(repo, "tag", BASE_TAG)
        with self.assertRaises(AssertionError):
            base_ids(repo)  # the fixture: the base commit has no list file
        listed = head_list(repo, [DROP, KEEP], "Adopt the list")
        code, out, err = known_base_run(listed, repo)
        self.assertEqual(missing_of(out), set(), "a base with no list has nothing to be missing\n" + out + err)
        self.assertEqual(caught_of(out), {"kb-drop", "kb-keep"}, "both head rows must read CAUGHT\n" + out + err)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))

    def test_a_head_that_deletes_the_list_reads_unknown_and_exits_1(self):
        repo = base_list_repo([DROP, KEEP])
        listed = head_list(repo, None, "Delete the list")
        self.assertFalse(os.path.exists(listed), "the fixture: the head has no list file")
        self.assertEqual(base_ids(repo), {"kb-drop", "kb-keep"}, "the fixture: the base list holds both ids")
        code, out, err = known_base_run(listed, repo)
        self.assertTrue(any(listed in line for line in unknown_lines(out)),
                        "a head with no list must print an UNKNOWN line that names %s\n" % listed + out + err)
        self.assertEqual(code, 1, "exit %d\n%s%s" % (code, out, err))

    def test_a_list_path_outside_the_repository_with_base_reads_unknown_and_exits_1(self):
        repo = base_list_repo([DROP, KEEP])
        outside = os.path.abspath(os.path.join(fresh(), "known-defects.json"))
        with open(outside, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(list_text([KEEP]))
        self.assertNotEqual(os.path.commonpath([outside, os.path.abspath(repo)]), os.path.abspath(repo),
                            "the fixture: the list sits outside the repository")
        code, out, err = known_base_run(outside, repo)
        self.assertTrue(any(outside in line for line in unknown_lines(out)),
                        "a list outside the repository must print an UNKNOWN line that names its path\n" + out + err)
        self.assertEqual(code, 1, "exit %d\n%s%s" % (code, out, err))

    def test_a_trailer_on_a_commit_before_the_base_does_not_excuse_the_drop(self):
        """The trailer sits on a commit that is an ancestor of REF, so REF..HEAD does not hold it: the drop reads MISSING."""
        repo = defect_repo()
        put(repo, {"NOTES.md": "kb-drop was retired before the base.\n"})
        retired = commit(repo, "Retire kb-drop\n\nKnown-defect-removed: kb-drop")
        put(repo, {KNOWN_DEFECTS_FILE: list_text([DROP, KEEP])})
        commit(repo, "List the planted defects")
        git(repo, "tag", BASE_TAG)
        listed = head_list(repo, [KEEP], "Drop kb-drop")
        git(repo, "merge-base", "--is-ancestor", retired, BASE_TAG)  # the fixture: the trailer commit is before the base
        self.assertIn("kb-drop", base_ids(repo), "the fixture: the base list holds kb-drop")
        code, out, err = known_base_run(listed, repo)
        self.assertIn("kb-drop", missing_of(out),
                      "a trailer on a commit before REF excused kb-drop: only REF..HEAD may name it\n" + out + err)
        self.assertEqual(code, 1, "exit %d\n%s%s" % (code, out, err))

    def test_a_base_entry_with_no_id_and_an_empty_head_reads_unknown_and_exits_1(self):
        """An entry on REF's list with no `id` is not skipped: an empty head would read green if it were."""
        idless = {key: value for key, value in DROP.items() if key != "id"}
        repo = base_list_repo([idless])
        listed = head_list(repo, [], "Empty the list")
        entries = json.loads(show(repo, BASE_TAG, KNOWN_DEFECTS_FILE))
        self.assertEqual(len(entries), 1, "the fixture: the base list holds one entry")
        self.assertNotIn("id", entries[0], "the fixture: the base entry has no id")
        code, out, err = known_base_run(listed, repo)
        self.assertTrue(unknown_lines(out), "a base entry with no id must read UNKNOWN, not be skipped\n" + out + err)
        self.assertEqual(code, 1, "exit %d\n%s%s" % (code, out, err))


class ReplayBaseWiringTests(unittest.TestCase):
    """The replay step of actions/mutation-report/action.yml passes `--base "origin/$BASE_REF"` to --known-defects, and its
    own env sets BASE_REF. Only that step's block is read: the catch-share step sets BASE_REF and passes --base too."""

    ACTION = os.path.join(REPO, "actions", "mutation-report", "action.yml")
    HEADER = "    - name: Replay the known defects\n"

    def replay_step(self):
        with open(self.ACTION, encoding="utf-8") as handle:
            text = handle.read()
        start = text.find(self.HEADER)
        self.assertGreaterEqual(start, 0, "%s has no step named Replay the known defects" % self.ACTION)
        after = start + len(self.HEADER)
        ends = re.search(r"^    - name:", text[after:], re.M)
        block = text[start:] if ends is None else text[start:after + ends.start()]
        self.assertIn("      run: |\n", block, "the replay step has no run block:\n" + block)
        self.assertIn("--known-defects", block, "the replay step runs no --known-defects command:\n" + block)
        return block

    def test_the_replay_step_passes_base_origin_base_ref_and_sets_base_ref(self):
        env, _, run = self.replay_step().partition("      run: |\n")
        joined = run.replace("\\\n", " ")  # a command continued on the next line is one command
        commands = [line for line in joined.splitlines() if "--known-defects" in line]
        self.assertEqual(len(commands), 1, "the replay step must run one --known-defects command:\n" + run)
        self.assertRegex(commands[0], r'--base\s+"?origin/\$BASE_REF"?',
                         "the replay command passes no --base origin/$BASE_REF:\n" + commands[0])
        self.assertRegex(env, r"(?m)^        BASE_REF: ",
                         "the replay step's env does not set BASE_REF:\n" + env)


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


# The --tests-for fixture: one product module, the suites beside it, and one tracked file per form that loads it or only
# mentions it. Each dict maps a path to its text. A load is printed; a mention, a parse failure, a non-test file, an
# untracked file and a different module name are not.
SPEC_HEADER = "import importlib.util\nimport os\n\nHERE = os.path.dirname(os.path.abspath(__file__))\n"
TESTS_FOR_PRODUCT = {
    "pkg/widget.py": "VALUE = 1\n",
    "pkg/lonely.py": "VALUE = 2\n",
    "pkg/widget.mjs": "export const VALUE = 1;\n",
}
TESTS_FOR_BESIDE = {
    "pkg/test_widget.py": "VALUE = 1\n",
    "pkg/test_widget_extra.py": "VALUE = 1\n",
    "pkg/test_widget_also.py": "import widget\n",  # beside and a load: printed once
}
TESTS_FOR_LOADS = {
    "tests/test_form_import.py": "import widget\n",
    "tests/test_form_import_as.py": "import widget as w\n",
    "tests/test_form_from.py": "from widget import VALUE\n",
    "tests/test_form_import_module.py": 'import importlib\n\nWIDGET = importlib.import_module("widget")\n',
    "tests/test_form_dunder.py": 'WIDGET = __import__("widget")\n',
    "tests/test_form_spec_inline.py": SPEC_HEADER
        + 'SPEC = importlib.util.spec_from_file_location("x_under_test", os.path.join(HERE, "widget.py"))\n',
    "tests/test_form_spec_named.py": SPEC_HEADER
        + 'MODULE = os.path.join(HERE, "widget.py")\nSPEC = importlib.util.spec_from_file_location("x_under_test", MODULE)\n',
    "tests/test_form_loader.py": "import os\nfrom importlib.machinery import SourceFileLoader\n\n"
        + 'HERE = os.path.dirname(os.path.abspath(__file__))\nLOADER = SourceFileLoader("x_under_test", os.path.join(HERE, "widget.py"))\n',
    "tests/test_form_runpy.py": "import os\nimport runpy\n\n"
        + 'HERE = os.path.dirname(os.path.abspath(__file__))\nrunpy.run_path(os.path.join(HERE, "widget.py"))\n',
    "tests/test_form_from_package.py": "from pkg import widget\n",
    "tests/test_form_import_dotted.py": "import pkg.widget\n",
    "tests/test_form_spec_keyword.py": SPEC_HEADER
        + 'SPEC = importlib.util.spec_from_file_location("x_under_test", location=os.path.join(HERE, "widget.py"))\n',
    "tests/test_form_spec_in_function.py": SPEC_HEADER
        + 'def load():\n    path = os.path.join(HERE, "widget.py")\n    spec = importlib.util.spec_from_file_location("x_under_test", path)\n',
    "tests/test_form_lone_quote.py": "# don't mind this note\nimport widget\n",
    "other/sub/test_form_deep.py": "import widget\n",
}
TESTS_FOR_MENTIONS = {
    "tests/test_no_comment.py": "# import widget\n",
    "tests/test_no_string.py": 'TEXT = "import widget"\n',
    "tests/test_no_docstring.py": '"""Pins the rule in widget.py."""\n',
    "tests/test_no_block.py": 'BLOCK = """\nimport widget\n"""\n',
    "tests/test_no_c_opener.py": 'TEXT = "/* import widget"\n',
    "tests/test_no_slash_opener.py": 'TEXT = "// import widget"\n',
    "tests/test_no_hash_opener.py": 'TEXT = "# import widget"\n',
    "tests/test_no_spec_name.py": SPEC_HEADER
        + 'OTHER = os.path.join(HERE, "other_module.py")\nSPEC = importlib.util.spec_from_file_location("widget", OTHER)\n',
    "tests/test_no_spec_name_arg.py": SPEC_HEADER
        + 'OTHER = os.path.join(HERE, "other_module.py")\nSPEC = importlib.util.spec_from_file_location("widget.py", OTHER)\n',
    "tests/test_no_other_basename.py": SPEC_HEADER
        + 'SPEC = importlib.util.spec_from_file_location("x_under_test", os.path.join(HERE, "old_widget.py"))\n',
    "tests/test_no_prefix.py": "import widget_extra\n",
    "tests/test_broken.py": "import widget\ndef broken(:\n",
    "tests/helper.py": "import widget\n",
    "pkg/test_widgets.py": "VALUE = 1\n",
}
UNTRACKED = {"tests/test_untracked.py": "import widget\n"}  # written after the commit, so `git ls-files` never lists it


def tests_for_fixture():
    """The fixture repository the --tests-for cases read, built once per run. The one commit holds every tracked file;
    UNTRACKED is written after it. A suite that lists the listed path's module is tracked too, for the override case."""
    if "tests_for" not in CACHE:
        repo = new_repo()
        listed = mutate_guard.REPORT_TARGETS[0][0]
        files = dict(TESTS_FOR_PRODUCT)
        files.update(TESTS_FOR_BESIDE)
        files.update(TESTS_FOR_LOADS)
        files.update(TESTS_FOR_MENTIONS)
        files[listed] = "VALUE = 3\n"
        files["tests/test_form_listed.py"] = "import %s\n" % os.path.splitext(os.path.basename(listed))[0]
        put(repo, files)
        commit(repo, "Fixture: a product module, its suites, and each form that loads or mentions it")
        put(repo, UNTRACKED)
        CACHE["tests_for"] = repo
    return CACHE["tests_for"]


class TestsForTests(unittest.TestCase):
    """`--tests-for PATH`. A listed path prints exactly its REPORT_TARGETS suites, with no union. An unlisted .py path
    prints the tests beside it plus each tracked test_*.py in the repository that loads its module by name or by file.
    Any other unlisted path prints the tests beside it only. A tracked test that fails to parse is skipped."""

    def test_a_listed_path_prints_its_report_targets_suites(self):
        targets = dict(mutate_guard.REPORT_TARGETS)
        target = "hooks/feedback_guard.py"
        self.assertIn(target, targets, "REPORT_TARGETS does not list %s" % target)
        code, out, err = run_cli(["--tests-for", target])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(set(SUITE_NAME.findall(out)), set(targets[target]),
                         "--tests-for must print the REPORT_TARGETS suites of %s" % target)

    def test_a_listed_path_prints_exactly_its_suites_though_a_suite_loads_it(self):
        target, suites = mutate_guard.REPORT_TARGETS[0]
        repo = tests_for_fixture()
        self.assertIn("tests/test_form_listed.py", git(repo, "ls-files").split("\n"),
                      "the fixture: a tracked suite loads %s" % target)
        code, out, err = run_cli(["--tests-for", target], cwd=repo)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(sorted(out.splitlines()), sorted(suites),
                         "a listed path prints its REPORT_TARGETS suites and no union with its loads")

    def test_the_incident_prints_the_suites_that_load_mutate_shared(self):
        target = "hooks/mutate_shared.py"
        self.assertNotIn(target, dict(mutate_guard.REPORT_TARGETS), "the fixture: %s must be unlisted" % target)
        code, out, err = run_cli(["--tests-for", target])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        printed = set(out.splitlines())
        for name in ("hooks/test_mutate_shared.py", "hooks/test_mutate_replay.py", "hooks/test_mutate_ci.py"):
            with self.subTest(suite=name):
                self.assertIn(name, printed, "--tests-for %s must print %s, which loads mutate_shared" % (target, name))

    def test_each_load_form_prints_its_file(self):
        repo = tests_for_fixture()
        self.assertIn("pkg/widget.py", git(repo, "ls-files").split("\n"), "the fixture: the product module is tracked")
        code, out, err = run_cli(["--tests-for", "pkg/widget.py"], cwd=repo)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        printed = set(out.splitlines())
        for name in sorted(TESTS_FOR_LOADS):
            with self.subTest(form=name):
                self.assertIn(name, printed, "%s loads widget, so --tests-for pkg/widget.py must print it" % name)

    def test_each_mention_that_is_not_a_load_prints_nothing(self):
        repo = tests_for_fixture()
        code, out, err = run_cli(["--tests-for", "pkg/widget.py"], cwd=repo)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        printed = set(out.splitlines())
        for name in sorted(set(TESTS_FOR_MENTIONS) | set(UNTRACKED)):
            with self.subTest(file=name):
                self.assertNotIn(name, printed, "%s does not load widget, so --tests-for must not print it" % name)

    def test_an_unlisted_py_path_prints_exactly_the_beside_suites_and_the_loads(self):
        repo = tests_for_fixture()
        code, out, err = run_cli(["--tests-for", "pkg/widget.py"], cwd=repo)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        want = sorted(set(TESTS_FOR_BESIDE) | set(TESTS_FOR_LOADS))
        self.assertEqual(sorted(out.splitlines()), want,
                         "the union: each beside suite and each load, each printed once")

    def test_a_non_py_path_prints_only_the_suites_beside_it(self):
        repo = tests_for_fixture()
        code, out, err = run_cli(["--tests-for", "pkg/widget.mjs"], cwd=repo)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(sorted(out.splitlines()), sorted(TESTS_FOR_BESIDE),
                         "a non-.py path gets the beside suites only, with no loads")

    def test_an_unparsable_suite_is_skipped_and_the_command_exits_zero(self):
        repo = tests_for_fixture()
        self.assertIn("tests/test_broken.py", git(repo, "ls-files").split("\n"), "the fixture: the broken suite is tracked")
        code, out, err = run_cli(["--tests-for", "pkg/widget.py"], cwd=repo)
        self.assertEqual(code, 0, "a suite that fails to parse must not stop the command\n%s%s" % (out, err))
        self.assertNotIn("tests/test_broken.py", out.splitlines(), "a suite that fails to parse is skipped")

    def test_a_file_nothing_loads_prints_nothing(self):
        repo = tests_for_fixture()
        code, out, err = run_cli(["--tests-for", "pkg/lonely.py"], cwd=repo)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(out, "", "no suite sits beside pkg/lonely.py and none loads it: nothing is printed")

    def test_an_unlisted_path_prints_the_suites_beside_it_and_the_loads_of_guard(self):
        target = "hooks/guard.py"
        self.assertNotIn(target, dict(mutate_guard.REPORT_TARGETS), "the fixture: %s must be unlisted" % target)
        beside = {name for name in git(REPO, "ls-files", "hooks").split("\n")
                  if re.fullmatch(r"hooks/test_guard(_[^/]*)?\.py", name)}
        self.assertTrue(beside, "the fixture: hooks/ holds tracked test_guard files")
        code, out, err = run_cli(["--tests-for", target])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        printed = set(out.splitlines())
        for name in sorted(beside):
            with self.subTest(beside=name):
                self.assertIn(name, printed, "%s sits beside hooks/guard.py, so it is printed" % name)
        # Each pinned suite loads guard by a top-level import. The check on the text is the scope; the print is the subject.
        for name in ("hooks/test_agent_brief.py", "hooks/test_question_form.py"):
            with self.subTest(load=name):
                self.assertIn("import guard", show(REPO, "HEAD", name), "the fixture: %s must import guard" % name)
                self.assertIn(name, printed, "%s loads guard, so --tests-for %s must print it" % (name, target))
        # Each extra suite names guard. That is a necessary condition for a load, not a proof of one.
        for name in sorted(printed - beside):
            with self.subTest(extra=name):
                self.assertRegex(show(REPO, "HEAD", name), r"\bguard\b", "%s is printed but names no guard" % name)

    def test_a_load_bound_inside_a_function_prints_its_suite_for_guard_rm_var(self):
        target = "hooks/guard_rm_var.py"
        self.assertNotIn(target, dict(mutate_guard.REPORT_TARGETS), "the fixture: %s must be unlisted" % target)
        loader = "hooks/test_guard.py"
        self.assertRegex(show(REPO, "HEAD", loader), r'(?m)^    path = os\.path\.join\(.*"guard_rm_var\.py"\)$',
                         "the fixture: %s binds the guard_rm_var path inside a function" % loader)
        code, out, err = run_cli(["--tests-for", target])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertIn(loader, out.splitlines(),
                      "%s loads guard_rm_var inside a function, so --tests-for %s must print it" % (loader, target))

    def test_a_path_constant_naming_guard_py_prints_the_suite_that_copies_it(self):
        target = "hooks/guard.py"
        self.assertNotIn(target, dict(mutate_guard.REPORT_TARGETS), "the fixture: %s must be unlisted" % target)
        loader = "hooks/test_wrappers.py"
        self.assertRegex(show(REPO, "HEAD", loader), r'(?m)^GUARD_PY = os\.path\.join\(HERE, "guard\.py"\)$',
                         "the fixture: %s binds guard.py to the GUARD_PY path constant" % loader)
        code, out, err = run_cli(["--tests-for", target])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertIn(loader, out.splitlines(),
                      "%s copies guard.py by its GUARD_PY path constant, so --tests-for %s must print it" % (loader, target))

    def test_a_path_constant_naming_settings_json_prints_the_suite_that_opens_it(self):
        target = "settings.json"
        loader = "hooks/test_wrappers.py"
        self.assertRegex(show(REPO, "HEAD", loader),
                         r'(?m)^SETTINGS = .*os\.path\.join\(HERE, "\.\.", "settings\.json"\)$',
                         "the fixture: %s binds settings.json to the SETTINGS path constant" % loader)
        code, out, err = run_cli(["--tests-for", target])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertIn(loader, out.splitlines(),
                      "%s opens settings.json by its SETTINGS path constant, so --tests-for %s must print it" % (loader, target))

    def test_a_path_constant_naming_bin_ci_job_prints_the_suite_that_runs_it(self):
        target = "bin/ci-job"
        loader = "lint/test_ci_job.py"
        self.assertRegex(show(REPO, "HEAD", loader), r'(?m)^CI_JOB = os\.path\.join\(HERE, "\.\.", "bin", "ci-job"\)$',
                         "the fixture: %s binds bin/ci-job to the CI_JOB path constant" % loader)
        code, out, err = run_cli(["--tests-for", target])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertIn(loader, out.splitlines(),
                      "%s runs bin/ci-job by its CI_JOB path constant, so --tests-for %s must print it" % (loader, target))


CHAIN_SUITE = "hooks/test_chain.py"  # opens hooks/entry.py by a path constant, so it loads entry.py
CHAIN_OPENS = ("import os\n\nHERE = os.path.dirname(os.path.abspath(__file__))\nENTRY = os.path.join(HERE, \"entry.py\")\n"
               "with open(ENTRY, encoding='utf-8') as handle:\n    handle.read()\n")
CHAIN_LOADS = {"import": "import leaf\n\nVALUE = leaf.V\n",  # entry.py loads leaf.py by an import
               "importlib": "import importlib\n\nleaf = importlib.import_module(\"leaf\")\n"}  # or by importlib


CHAIN_HEAD = "import os\n\nHERE = os.path.dirname(os.path.abspath(__file__))\n"
CHAIN_MID_LOADS = {  # hooks/entry.py, the intermediate module, loads merge/target.py by a path constant
    "spec": CHAIN_HEAD + "import importlib.util\n\nTARGET = os.path.join(HERE, \"..\", \"merge\", \"target.py\")\n"
            "spec = importlib.util.spec_from_file_location(\"target\", TARGET)\n",
    "open": CHAIN_HEAD + "TARGET = os.path.join(HERE, \"..\", \"merge\", \"target.py\")\n"
            "with open(TARGET, encoding='utf-8') as handle:\n    handle.read()\n"}
CHAIN_LOOP_OPENS = (CHAIN_HEAD + "for name in (\"leaf.py\", \"other.py\"):\n"  # the suite opens each file in a loop
                    "    with open(os.path.join(HERE, name), encoding='utf-8') as handle:\n        handle.read()\n")
CHAIN_LOOP_COPIES = (CHAIN_HEAD + "import shutil\n\nfor name in (\"leaf.py\", \"other.py\"):\n"  # or copies each one
                     "    shutil.copy(os.path.join(HERE, name), HERE)\n")
CHAIN_LOOP_FORMS = {  # the suite opens leaf.py and other.py through each loop form that the scan does not bind yet
    "comprehension": CHAIN_HEAD + "CONTENTS = [open(os.path.join(HERE, n), encoding='utf-8').read() for n in (\"leaf.py\", \"other.py\")]\n",
    "generator": CHAIN_HEAD + "SIZES = sum(len(open(os.path.join(HERE, n), encoding='utf-8').read())\n"
                              "            for n in (\"leaf.py\", \"other.py\"))\n",
    "sorted": CHAIN_HEAD + "for name in sorted((\"leaf.py\", \"other.py\")):\n"
                           "    with open(os.path.join(HERE, name), encoding='utf-8') as handle:\n        handle.read()\n",
    "enumerate": CHAIN_HEAD + "for index, name in enumerate((\"leaf.py\", \"other.py\")):\n"
                              "    with open(os.path.join(HERE, name), encoding='utf-8') as handle:\n        handle.read()\n",
    "alias": CHAIN_HEAD + "FIRST = (\"leaf.py\", \"other.py\")\nNAMES = FIRST\n"
                          "for name in NAMES:\n    with open(os.path.join(HERE, name), encoding='utf-8') as handle:\n        handle.read()\n",
    # the gaps: a loop name that a path reaches through a form the scan does not follow yet
    "split": CHAIN_HEAD + "ROOT = os.path.dirname(HERE)\nfor rel in (\"hooks/leaf.py\",):\n"
                          "    with open(os.path.join(ROOT, *rel.split(\"/\")), encoding='utf-8') as handle:\n        handle.read()\n",
    "dict_items": CHAIN_HEAD + "for k, v in {\"a\": \"leaf.py\"}.items():\n"
                               "    with open(os.path.join(HERE, v), encoding='utf-8') as handle:\n        handle.read()\n",
    "dict_values": CHAIN_HEAD + "NAMES = {\"a\": \"leaf.py\"}\nfor n in NAMES.values():\n"
                                "    with open(os.path.join(HERE, n), encoding='utf-8') as handle:\n        handle.read()\n",
    "zip": CHAIN_HEAD + "for a, n in zip((\"x\",), (\"leaf.py\",)):\n"
                        "    with open(os.path.join(HERE, n), encoding='utf-8') as handle:\n        handle.read()\n",
    "basename": CHAIN_HEAD + "for n in (\"leaf.py\",):\n"
                             "    with open(os.path.join(HERE, os.path.basename(n)), encoding='utf-8') as handle:\n"
                             "        handle.read()\n",
    "replace": CHAIN_HEAD + "for n in (\"leaf.py\",):\n"
                            "    with open(os.path.join(HERE, n.replace(\"-\", \"_\")), encoding='utf-8') as handle:\n"
                            "        handle.read()\n",
}
CHAIN_PIN_FORMS = {  # the pins, and the green controls beside the gaps: the same construct with a literal for the loop name
    "label": CHAIN_HEAD + "\n\ndef label(name):\n    return \"entry.py\"\n\n\nseen = []\n"
             "for n in (\"leaf.py\", \"other.py\"):\n    seen.append(n)\n"
             "    with open(os.path.join(HERE, label(n)), encoding='utf-8') as handle:\n        handle.read()\n"
             "with open(os.path.join(HERE, \"entry.py\"), encoding='utf-8') as handle:\n    handle.read()\n",
    "str": CHAIN_HEAD + "for n in (\"leaf.py\",):\n    with open(str(n), encoding='utf-8') as handle:\n        handle.read()\n",
    "format": CHAIN_HEAD + "for n in (\"leaf.py\",):\n    with open(\"{}\".format(n), encoding='utf-8') as handle:\n        handle.read()\n",
    "join_wrapped": CHAIN_HEAD + "from os.path import join\n\nfor n in (\"leaf.py\",):\n"
                                 "    with open(str(os.path.join(HERE, n)), encoding='utf-8') as handle:\n        handle.read()\n"
                                 "    print(\"{}\".format(join(HERE, n)))\n",
    "other_fn": CHAIN_HEAD + "\n\ndef load():\n    NAMES = (\"leaf.py\",)\n    for n in NAMES:\n"
                             "        with open(os.path.join(HERE, n), encoding='utf-8') as handle:\n            handle.read()\n\n\n"
                             "def names():\n    NAMES = (\"guard.py\",)\n    return NAMES\n",
    "split_literal": CHAIN_HEAD + "ROOT = os.path.dirname(HERE)\n"
                                  "with open(os.path.join(ROOT, *\"hooks/leaf.py\".split(\"/\")), encoding='utf-8') as handle:\n"
                                  "    handle.read()\n",
    "dict_keys": CHAIN_HEAD + "NAMES = {\"leaf.py\": 1}\nfor n in NAMES:\n"
                              "    with open(os.path.join(HERE, n), encoding='utf-8') as handle:\n        handle.read()\n",
    "zip_pairs": CHAIN_HEAD + "for a, n in ((\"x\", \"leaf.py\"),):\n"
                              "    with open(os.path.join(HERE, n), encoding='utf-8') as handle:\n        handle.read()\n",
    "basename_literal": CHAIN_HEAD + "with open(os.path.join(HERE, os.path.basename(\"leaf.py\")), encoding='utf-8') as handle:\n"
                                    "    handle.read()\n",
    "own_def_run": CHAIN_HEAD + "\n\ndef run(paths):\n    return len(paths)\n\n\n"  # a helper the file defines
                                "run([\"hooks/leaf.py\"])\n",
    "items_pair": CHAIN_HEAD + "ROOT = os.path.dirname(HERE)\nfor k, v in {\"hooks/leaf.py\": \"x\"}.items():\n"
                               "    with open(os.path.join(ROOT, v), encoding='utf-8') as handle:\n        handle.read()\n",
    "zip_pair": CHAIN_HEAD + "for a, n in zip((\"hooks/leaf.py\",), (\"x.py\",)):\n"  # the first name of each pair is leaf.py
                             "    with open(os.path.join(HERE, n), encoding='utf-8') as handle:\n        handle.read()\n",
}
CHAIN_POOLED_NAME = (CHAIN_HEAD + "\n\ndef load():\n    for n in (\"leaf.py\",):\n"  # the loop that loads leaf.py
                     "        with open(os.path.join(HERE, n), encoding='utf-8') as handle:\n            handle.read()\n\n\n"
                     "def names():\n    seen = []\n    for n in [\"guard.py\", \"notes.md\"]:  # a loop that reaches no load\n"
                     "        seen.append(n)\n    return seen\n")
CHAIN_HELPER_OPENS = "with open(os.path.join(HERE, \"helper.py\"), encoding='utf-8') as handle:\n    handle.read()\n"
CHAIN_CYCLE_HELPER = (CHAIN_HEAD + "with open(os.path.join(HERE, \"entry.py\"), encoding='utf-8') as handle:\n"
                      "    handle.read()\n")  # helper.py loads entry.py, and entry.py loads helper.py: a cycle


def chain_repo(entry_text, lane, suite=CHAIN_OPENS, base=None):
    """A repository whose base holds `suite` (CHAIN_SUITE, which opens hooks/entry.py by default), hooks/entry.py
    (`entry_text`), hooks/leaf.py and the `base` files (path -> text; each replaces a default of the same path). The branch
    `lane` then writes `lane` (path -> text) and commits, so main...HEAD is the files `lane` names."""
    repo = new_repo()
    files = {CHAIN_SUITE: suite, "hooks/entry.py": entry_text, "hooks/leaf.py": "V = 1\n"}
    files.update(base or {})
    put(repo, files)
    commit(repo, "base")
    git(repo, "checkout", "-qb", "lane")
    put(repo, lane)
    commit(repo, "change")
    return repo


class LintSuitesChainTests(unittest.TestCase):
    """`--lint-suites BASE` picks a suite that reaches a changed file through the modules it loads, however deep. CHAIN_SUITE
    opens hooks/entry.py by a path constant, and entry.py loads hooks/leaf.py by an import, or by importlib.import_module. A
    diff that changes only leaf.py picks the suite (one case per form). A diff that changes entry.py picks it too (the
    control). A path that an intermediate module loads, and a path a loop variable names, are followed too: in a for loop,
    a comprehension, a sorted() or enumerate() loop, or through an alias. A loop name that another loop binds to a list
    picks no suite (the over-pick case and its control). A file that nothing loads picks no suite, and a cycle of loads
    ends (the controls). A loop name passed to a helper that builds no path is not followed, one passed whole to str() or
    format() is, and a name is read only in the function that binds it. A loop name split into path parts, read from a
    dict's items() or values(), zipped, or passed through basename() or replace() is followed; each of these forms has a
    control with a literal in place of the loop name. A module-level def named like a file call (`run`) is a helper, so a
    call of it with a path is no load, and a dict's key or a zip's first name is not the name a suite opens (the pins)."""

    def picked(self, repo):
        code, out, err = run_cli(["--lint-suites", "main"], cwd=repo)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        return out.splitlines()

    def changed(self, repo):
        return git(repo, "diff", "--name-only", "main...HEAD").split("\n")

    def test_a_diff_of_only_a_module_that_a_suite_reaches_by_import_picks_the_suite(self):
        repo = chain_repo(CHAIN_LOADS["import"], {"hooks/leaf.py": "V = 2\n"})
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: entry.py imports it, and the suite opens entry.py"
                      % CHAIN_SUITE)

    def test_a_diff_of_only_a_module_that_a_suite_reaches_by_importlib_picks_the_suite(self):
        repo = chain_repo(CHAIN_LOADS["importlib"], {"hooks/leaf.py": "V = 2\n"})
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: entry.py loads it by importlib, and the suite "
                      "opens entry.py" % CHAIN_SUITE)

    def test_a_diff_that_changes_the_file_the_suite_opens_picks_the_suite(self):  # the control
        repo = chain_repo(CHAIN_LOADS["import"], {"hooks/entry.py": CHAIN_LOADS["import"] + "# changed\n"})
        self.assertEqual(self.changed(repo), ["hooks/entry.py"], "the scope: the diff holds only entry.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo), "--lint-suites must pick %s for a diff of the file it opens" % CHAIN_SUITE)

    def test_a_diff_of_only_a_path_an_intermediate_module_loads_picks_the_suite(self):
        repo = chain_repo(CHAIN_MID_LOADS["spec"], {"merge/target.py": "X = 2\n"}, base={"merge/target.py": "X = 1\n"})
        self.assertEqual(self.changed(repo), ["merge/target.py"], "the scope: the diff holds only merge/target.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only merge/target.py: it opens entry.py, and entry.py loads "
                      "merge/target.py by a path constant" % CHAIN_SUITE)

    def test_a_diff_of_only_a_path_an_imported_intermediate_module_opens_picks_the_suite(self):
        repo = chain_repo(CHAIN_MID_LOADS["open"], {"merge/target.py": "X = 2\n"}, suite="import entry\n",
                          base={"merge/target.py": "X = 1\n"})
        self.assertEqual(self.changed(repo), ["merge/target.py"], "the scope: the diff holds only merge/target.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only merge/target.py: it imports entry.py, and entry.py opens "
                      "merge/target.py by a path constant" % CHAIN_SUITE)

    def test_a_diff_of_only_a_module_a_suite_opens_in_a_loop_picks_the_suite(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_LOOP_OPENS)
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: it opens each name of a loop, and leaf.py "
                      "is one of them" % CHAIN_SUITE)

    def test_a_diff_of_only_a_module_a_suite_copies_in_a_loop_picks_the_suite(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_LOOP_COPIES)
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: it copies each name of a loop, and leaf.py "
                      "is one of them" % CHAIN_SUITE)

    def test_a_diff_of_only_a_module_a_suite_opens_in_a_comprehension_picks_the_suite(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_LOOP_FORMS["comprehension"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: it opens each name of a list comprehension, "
                      "and leaf.py is one of them" % CHAIN_SUITE)

    def test_a_diff_of_only_a_module_a_suite_opens_in_a_generator_picks_the_suite(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_LOOP_FORMS["generator"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: it opens each name of a generator expression, "
                      "and leaf.py is one of them" % CHAIN_SUITE)

    def test_a_diff_of_only_a_module_a_suite_opens_in_a_sorted_loop_picks_the_suite(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_LOOP_FORMS["sorted"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: it opens each name of sorted() over a tuple, "
                      "and leaf.py is one of them" % CHAIN_SUITE)

    def test_a_diff_of_only_a_module_a_suite_opens_in_an_enumerate_loop_picks_the_suite(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_LOOP_FORMS["enumerate"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: it opens each name of enumerate() over a "
                      "tuple, and leaf.py is one of them" % CHAIN_SUITE)

    def test_a_diff_of_only_a_module_a_suite_opens_in_a_loop_over_an_alias_picks_the_suite(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_LOOP_FORMS["alias"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: it loops over a name bound to another name "
                      "bound to a tuple, and leaf.py is in it" % CHAIN_SUITE)

    def test_a_diff_of_only_guard_py_does_not_pick_a_suite_whose_loop_name_another_loop_binds_to_a_list(self):
        repo = chain_repo("V = 0\n", {"hooks/guard.py": "V = 2\n"}, suite=CHAIN_POOLED_NAME, base={"hooks/guard.py": "V = 1\n"})
        self.assertEqual(self.changed(repo), ["hooks/guard.py"], "the scope: the diff holds only hooks/guard.py")
        self.assertNotIn(CHAIN_SUITE, self.picked(repo),
                         "--lint-suites must not pick %s for a diff of only hooks/guard.py: the name n that a loop opens leaf.py by "
                         "is also bound, in another loop, to a list that holds guard.py, and that loop reaches no load"
                         % CHAIN_SUITE)

    def test_a_diff_of_only_leaf_py_picks_the_suite_whose_loop_name_another_loop_binds_to_a_list(self):  # the control
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_POOLED_NAME)
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: its loop opens leaf.py by the shared name"
                      % CHAIN_SUITE)

    def test_a_diff_of_a_file_that_nothing_loads_picks_no_suite(self):  # the control for cost
        repo = chain_repo(CHAIN_MID_LOADS["spec"], {"merge/orphan.py": "X = 2\n"},
                          base={"merge/target.py": "X = 1\n", "merge/orphan.py": "X = 1\n"})
        self.assertEqual(self.changed(repo), ["merge/orphan.py"], "the scope: the diff holds only merge/orphan.py")
        self.assertEqual(self.picked(repo), [],
                         "--lint-suites must pick no suite for merge/orphan.py: nothing loads it, though entry.py loads its "
                         "sibling merge/target.py")

    def test_a_cycle_of_path_loads_ends_and_picks_the_suite_for_a_file_in_it(self):  # the control for cost
        repo = chain_repo(CHAIN_HEAD + CHAIN_HELPER_OPENS, {"hooks/helper.py": CHAIN_CYCLE_HELPER + "V = 2\n"},
                          suite=CHAIN_OPENS + CHAIN_HELPER_OPENS, base={"hooks/helper.py": CHAIN_CYCLE_HELPER + "V = 1\n"})
        self.assertEqual(self.changed(repo), ["hooks/helper.py"], "the scope: the diff holds only helper.py")
        self.assertEqual(self.picked(repo), [CHAIN_SUITE],
                         "--lint-suites must pick %s for a diff of hooks/helper.py, which the suite loads, and the cycle "
                         "entry.py <-> helper.py must end" % CHAIN_SUITE)

    def test_a_loop_name_passed_to_a_helper_that_builds_no_path_does_not_pick_the_suite_for_that_name(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_PIN_FORMS["label"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only hooks/leaf.py")
        self.assertNotIn(CHAIN_SUITE, self.picked(repo),
                         "--lint-suites must not pick %s for a diff of only hooks/leaf.py: the loop passes its name to label(), "
                         "which builds no path, and the path load beside it opens entry.py only" % CHAIN_SUITE)

    def test_a_diff_of_entry_py_picks_the_suite_beside_a_loop_name_passed_to_a_helper(self):  # the control
        repo = chain_repo("V = 0\n", {"hooks/entry.py": "V = 2\n"}, suite=CHAIN_PIN_FORMS["label"])
        self.assertEqual(self.changed(repo), ["hooks/entry.py"], "the scope: the diff holds only hooks/entry.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of hooks/entry.py: the suite opens entry.py by a path load" % CHAIN_SUITE)

    def test_a_loop_name_passed_whole_to_str_picks_the_suite_for_that_name(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_PIN_FORMS["str"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only hooks/leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: it opens str(n) for a loop over leaf.py, and "
                      "str() passes the name on as the path" % CHAIN_SUITE)

    def test_a_loop_name_passed_whole_to_format_picks_the_suite_for_that_name(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_PIN_FORMS["format"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only hooks/leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: it opens format(n) for a loop over leaf.py, and "
                      "format() passes the name on as the path" % CHAIN_SUITE)

    def test_a_loop_name_inside_a_joined_path_under_str_or_format_picks_the_suite_for_that_name(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_PIN_FORMS["join_wrapped"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only hooks/leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: the loop opens os.path.join(HERE, n) under "
                      "str(), and formats the same join" % CHAIN_SUITE)

    def test_a_loop_over_a_name_bound_in_its_own_function_does_not_pick_the_suite_for_another_functions_literal(self):
        repo = chain_repo("V = 0\n", {"hooks/guard.py": "V = 2\n"}, suite=CHAIN_PIN_FORMS["other_fn"],
                          base={"hooks/guard.py": "V = 1\n"})
        self.assertEqual(self.changed(repo), ["hooks/guard.py"], "the scope: the diff holds only hooks/guard.py")
        self.assertNotIn(CHAIN_SUITE, self.picked(repo),
                         "--lint-suites must not pick %s for a diff of only hooks/guard.py: load() loops over its own NAMES, and "
                         "names() binds NAMES to a tuple that holds guard.py" % CHAIN_SUITE)

    def test_a_diff_of_only_leaf_py_picks_the_suite_whose_loop_reads_a_name_bound_in_its_own_function(self):  # the control
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_PIN_FORMS["other_fn"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only hooks/leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: load()'s loop opens leaf.py by its own NAMES"
                      % CHAIN_SUITE)

    def test_a_diff_of_only_leaf_py_picks_the_suite_that_opens_a_loop_name_split_into_path_parts(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_LOOP_FORMS["split"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only hooks/leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: the loop opens os.path.join(ROOT, *rel.split(\"/\")) "
                      "and rel is leaf.py's path" % CHAIN_SUITE)

    def test_a_diff_of_only_leaf_py_picks_the_suite_that_opens_a_literal_split_into_path_parts(self):  # the control
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_PIN_FORMS["split_literal"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only hooks/leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: the suite opens the literal \"hooks/leaf.py\" "
                      "split into path parts" % CHAIN_SUITE)

    def test_a_diff_of_only_leaf_py_picks_the_suite_that_opens_the_value_of_a_dict_items_loop(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_LOOP_FORMS["dict_items"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only hooks/leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: the loop reads the items() of a dict literal, "
                      "opens v, and v is leaf.py" % CHAIN_SUITE)

    def test_a_diff_of_only_leaf_py_picks_the_suite_that_opens_a_name_from_a_dict_values_loop(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_LOOP_FORMS["dict_values"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only hooks/leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: the loop reads the values() of a dict literal, "
                      "opens n, and n is leaf.py" % CHAIN_SUITE)

    def test_a_diff_of_only_leaf_py_picks_the_suite_that_loops_over_the_keys_of_a_dict_literal(self):  # the control
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_PIN_FORMS["dict_keys"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only hooks/leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: the loop reads the keys of a dict literal, "
                      "and the key is leaf.py" % CHAIN_SUITE)

    def test_a_diff_of_only_leaf_py_picks_the_suite_that_opens_the_second_name_of_a_zip_loop(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_LOOP_FORMS["zip"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only hooks/leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: the loop zips two tuples, opens n, the second "
                      "of them, and n is leaf.py" % CHAIN_SUITE)

    def test_a_diff_of_only_leaf_py_picks_the_suite_that_opens_the_second_name_of_a_loop_over_pairs(self):  # the control
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_PIN_FORMS["zip_pairs"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only hooks/leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: the loop unpacks a tuple of pairs, opens n, "
                      "and n is leaf.py" % CHAIN_SUITE)

    def test_a_diff_of_only_leaf_py_picks_the_suite_that_opens_a_loop_name_through_basename(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_LOOP_FORMS["basename"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only hooks/leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: the loop opens os.path.basename(n), and n is "
                      "leaf.py" % CHAIN_SUITE)

    def test_a_diff_of_only_leaf_py_picks_the_suite_that_opens_a_loop_name_through_replace(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_LOOP_FORMS["replace"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only hooks/leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: the loop opens n.replace(...), and n is "
                      "leaf.py" % CHAIN_SUITE)

    def test_a_diff_of_only_leaf_py_picks_the_suite_that_opens_a_literal_through_basename(self):  # the control
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_PIN_FORMS["basename_literal"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only hooks/leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff of only hooks/leaf.py: the suite opens os.path.basename(\"leaf.py\")"
                      % CHAIN_SUITE)

    def test_a_diff_of_only_leaf_py_does_not_pick_the_suite_that_calls_a_run_helper_the_file_defines_with_leaf_py(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_PIN_FORMS["own_def_run"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only hooks/leaf.py")
        self.assertNotIn(CHAIN_SUITE, self.picked(repo),
                         "--lint-suites must not pick %s for a diff of only hooks/leaf.py: run() is defined at module level, so "
                         "its call with the path is a call of that helper, and the helper never opens the path" % CHAIN_SUITE)

    def test_a_diff_of_only_leaf_py_does_not_pick_the_suite_that_opens_the_value_of_a_dict_items_pair_keyed_by_leaf_py(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_PIN_FORMS["items_pair"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only hooks/leaf.py")
        self.assertNotIn(CHAIN_SUITE, self.picked(repo),
                         "--lint-suites must not pick %s for a diff of only hooks/leaf.py: the loop's pair is (key, value) of "
                         "a dict literal, the suite opens the value x, and only the key is leaf.py" % CHAIN_SUITE)

    def test_a_diff_of_only_leaf_py_does_not_pick_the_suite_that_opens_the_second_name_of_a_zip_pair_led_by_leaf_py(self):
        repo = chain_repo("V = 0\n", {"hooks/leaf.py": "V = 2\n"}, suite=CHAIN_PIN_FORMS["zip_pair"])
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only hooks/leaf.py")
        self.assertNotIn(CHAIN_SUITE, self.picked(repo),
                         "--lint-suites must not pick %s for a diff of only hooks/leaf.py: the loop zips two tuples and opens n, "
                         "the second of each pair, which is x.py; leaf.py is only the first" % CHAIN_SUITE)

    def test_a_diff_that_deletes_a_module_that_a_suite_reaches_by_import_picks_the_suite(self):
        # the control is test_a_diff_of_only_a_module_that_a_suite_reaches_by_import_picks_the_suite: the same fixture, with
        # leaf.py edited. Here the lane deletes leaf.py, and the unchanged entry.py still imports it.
        repo = chain_repo(CHAIN_LOADS["import"], {"hooks/leaf.py": None})
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only the deletion of leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff that deletes hooks/leaf.py: entry.py, unchanged, imports it, and the "
                      "suite opens entry.py" % CHAIN_SUITE)


if __name__ == "__main__":
    unittest.main()
