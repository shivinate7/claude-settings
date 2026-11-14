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
  kill), then one `untested: path:line` line per line whose mutant survived or was not run. It exits 1 when mutants are
  made and none ran, and prints one `no mutant ran: ...` line that names the count not run. It also exits 1, with one
  `no mutant ran: <cause>` line, when no mutant ran because the change did not parse, the diff could not be read, the
  checkout or the install was refused, or the replay raised. It exits 0 otherwise, whatever the share. `--budget S` is a wall deadline counted from the start of the run: a mutant not started by then is
  not_run, and a suite still running then is killed, its mutant not_run too. `--log PATH` writes one JSON file with the
  keys base, head, profile, made, killed, crashed, survived, not_run and untested, and writes nothing else into REPO.
  With no changed mutant the share reads `0/0` with no percentage, and the run exits 0.
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
- `--tests-for PATH`. It prints the REPORT_TARGETS suites for PATH when listed, and nothing else. A path with a row in
  GUARD_MODULE_FAMILIES prints its `hooks/test_guard.py::<family>` lines plus the walk's suites below, except the whole
  `hooks/test_guard.py`, once each, sorted. Else it prints each tracked `test_<stem>.py` and `test_<stem>_*.py` beside
  PATH. A .py PATH also gets each tracked `test_*.py` in the repository that loads the module `<stem>`: an `import`, an
  `importlib.import_module` or `__import__` call, or a file loader (`spec_from_file_location`, `SourceFileLoader`,
  `runpy.run_path`) whose path names `<stem>.py`. The loads are
  found with `ast`, never a grep. A path that a function takes as a parameter counts too: a call of a function defined in
  the same file counts when its argument for that parameter, by position or by keyword, names `<stem>.py`. Calls through
  an attribute, such as `json.load`, are not followed. A path expression (`open`, `shutil.copy*`, `subprocess.run`,
  `os.path.join`, `Path`, `/`) that names the basename of PATH counts for any PATH, .py or not. A tracked test that fails
  to parse is skipped, unless it sits beside PATH. A guard section
  file (a `.py` in the folder that `hooks/test_guard.py` reads its sections from) that loads the module counts as a load
  of `hooks/test_guard.py`, which is printed in its place. The section file itself is never printed.
- `--lint-suites BASE`. It prints each suite that tests a file of `git diff BASE...HEAD`, and each changed suite. A suite
  reaches a changed file through a module it loads, followed through the imports of that module (LintSuitesChainTests).

Each mode is dispatched from main() in hooks/mutate_guard.py and has an entry point beside `report_main` and
`replay_main`: `changed_main`, `known_defects_main`, `tests_for_main`, `lint_suites_main`. A case checks for its entry point first and
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
import ast
import contextlib
import fnmatch
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import unittest
import uuid
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import mutate_guard  # noqa: E402  REPORT_TARGETS, and the mode entry points once built
import mutate_shared  # noqa: E402
import rule_audit  # noqa: E402  SECTION_DIR's one ast reader (lint/rule_audit.py)
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


def guard_section_files(ref):
    """{path: text} of the guard section files at `ref`. The folder is the runner's SECTION_DIR, read from the runner at
    `ref` by rule_audit, so a section file is found whatever its name."""
    runner = os.path.join(REPO, "hooks", "test_guard.py")
    folder = rule_audit._section_dir(ast.parse(show(REPO, ref, "hooks/test_guard.py")), runner)
    if not folder:
        return {}
    rel = os.path.relpath(os.path.normpath(folder), REPO).replace(os.sep, "/")
    listed = git(REPO, "ls-tree", "--name-only", ref, rel + "/")
    return {path: show(REPO, ref, path) for path in listed.split("\n") if path.endswith(".py")}


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

def partial_repo(extra=None):
    """feat adds sub and div. Its suite gains a check for sub only, so sub's mutants die and div's survive. `extra`
    ({path: text}) joins the base commit, for a case that needs a file beside calc.py."""
    repo = new_repo()
    files = {"calc.py": CALC_BASE, "test_calc.py": SUITE}
    files.update(extra or {})
    put(repo, files)
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


def unparsable_repo():
    """feat changes calc.py to a module that does not parse. No mutant can be made of it: its parse error is the only row."""
    repo = new_repo()
    put(repo, {"calc.py": CALC_BASE, "test_calc.py": SUITE})
    commit(repo, "Base: add and mul")
    topic(repo, "feat", {"calc.py": CALC_BASE + "\n\ndef broken(:\n    pass\n"}, "Add a def that does not parse")
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


def walk_suites(target):
    """The suites the read finds for `target` before GUARD_MODULE_DROPPED_SUITES takes any away: `suites_for_paths` on the
    tracked files of REPO, with no union. A drop is a choice of the selector, not a miss of the read."""
    previous = os.getcwd()
    os.chdir(REPO)
    try:
        tracked, reason = mutate_guard._tracked_files()
        assert tracked is not None, reason
        return set(mutate_guard.suites_for_paths([target], tracked, union=False))
    finally:
        os.chdir(previous)


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
NO_MUTANT = re.compile(r"^no mutant ran: .*$", re.M)
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


def assert_no_mutant_ran(case, code, out, err, not_run=None, cause=None):
    """A run in which no mutant ran exits 1 and prints one `no mutant ran:` line. With `not_run`, the line names that count
    (a run every mutant of which is not_run). With `cause`, the line names the cause (a run that stopped before any mutant
    ran has no count). One shared step for every case of that run, so the rule is stated once."""
    case.assertEqual(code, 1, "a run in which no mutant ran must exit 1, got exit %d\n%s%s" % (code, out, err))
    lines = NO_MUTANT.findall(out)
    case.assertEqual(len(lines), 1, "want one `no mutant ran:` line, got %d in:\n%s" % (len(lines), out))
    if not_run is not None:
        case.assertRegex(lines[0], r"(?<!\d)%d(?!\d)" % not_run,
                         "the `no mutant ran:` line must name the %d mutants not run:\n%s" % (not_run, lines[0]))
    if cause is not None:
        case.assertIn(cause, lines[0], "the `no mutant ran:` line must name the cause %r:\n%s" % (cause, lines[0]))


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
        assert_no_mutant_ran(self, code, out, err, want)
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

    def test_one_mutant_that_ran_and_survived_still_exits_0(self):
        repo = weak_repo()
        folder, log = fixture_log()
        code, out, err = changed_run(repo, SELECTED, log=log, limit=1)
        data = read_log(log)
        self.assertEqual((data["made"], data["not_run"], data["survived"]), (1, 0, 1),
                         "the fixture: one mutant is made, it runs, and it survives")
        self.assertEqual(code, 0, "one mutant ran, so no mutant ran is false, and a low share exits 0\n"
                                  "exit %d\n%s%s" % (code, out, err))
        self.assertIsNone(NO_MUTANT.search(out), "a run in which a mutant ran prints no `no mutant ran:` line:\n" + out)

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

    def test_a_refused_install_exits_1_and_names_the_deps_cause(self):
        repo = partial_repo()
        facts = partial_facts(repo)
        self.assertGreater(facts["sub_n"] + facts["div_n"], 0, "the fixture: the change adds lines with mutants")
        code, out, err = changed_run(repo, dict(CHANGED, install=[PY, "-c", "pass"]))
        assert_no_mutant_ran(self, code, out, err, cause="no lockfile")

    def test_a_checkout_refused_by_its_install_link_exits_1_and_names_the_checkout_cause(self):
        repo = partial_repo(extra={"package-lock.json": LOCK_TEXT})
        facts = partial_facts(repo)
        self.assertGreater(facts["sub_n"] + facts["div_n"], 0, "the fixture: the change adds lines with mutants")
        code, out, err = changed_run(repo, dict(CHANGED, install=[PY, "-c", "pass"], link="calc.py"))
        assert_no_mutant_ran(self, code, out, err, cause="checkout failed")

    def test_an_error_in_the_replay_exits_1_and_names_the_error(self):
        repo = partial_repo()
        facts = partial_facts(repo)
        self.assertGreater(facts["sub_n"] + facts["div_n"], 0, "the fixture: the change adds lines with mutants")
        code, out, err = changed_run(repo, dict(CHANGED, classify="no-such-classifier"))
        assert_no_mutant_ran(self, code, out, err, cause="the replay raised KeyError")

    def test_a_change_that_does_not_parse_exits_1_and_names_the_parse_error(self):
        repo = unparsable_repo()
        code, out, err = changed_run(repo, CHANGED)
        assert_no_mutant_ran(self, code, out, err, cause="parse error")

    def test_a_diff_that_cannot_be_read_exits_1_and_names_the_diff_cause(self):
        repo = partial_repo()
        facts = partial_facts(repo)
        self.assertGreater(facts["sub_n"] + facts["div_n"], 0, "the fixture: the change adds lines with mutants")
        # A CLI run cannot make `git diff` fail on a valid pair of commits, so the one diff reader is patched in process.
        # The temp folder of the run is this case's own, so the deps folder changed_main makes stays in the run folder.
        out = io.StringIO()
        with mock.patch.object(mutate_shared, "_changed_files", side_effect=ValueError("fixture: git diff failed")), \
                mock.patch.object(tempfile, "tempdir", fresh()), contextlib.redirect_stdout(out):
            code = mutate_guard.changed_main(["--changed", repo, "--profile-file", profile_file(CHANGED),
                                              "--base", "main", "--head", "feat"])
        assert_no_mutant_ran(self, code, out.getvalue(), "", cause="cannot read the diff")

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
        total = facts["sub_n"] + facts["div_n"]
        code, out, err = changed_run(repo, CHANGED, extra=["--budget", "0"], log=log)
        assert_no_mutant_ran(self, code, out, err, total)
        data = read_log(log)
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
        assert_no_mutant_ran(self, code, out, err, want)
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


ACTION = os.path.join(REPO, "actions", "mutation-report", "action.yml")


def action_step(name):
    """The text of the step named `name` in actions/mutation-report/action.yml, from its header to the next step: its env
    and its run block. The one home of reading a step of that action."""
    with open(ACTION, encoding="utf-8") as handle:
        text = handle.read()
    header = "    - name: %s\n" % name
    start = text.find(header)
    if start < 0:
        raise AssertionError("%s has no step named %s" % (ACTION, name))
    after = start + len(header)
    ends = re.search(r"^    - name:", text[after:], re.M)
    return text[start:] if ends is None else text[start:after + ends.start()]


class ReplayBaseWiringTests(unittest.TestCase):
    """The replay step of actions/mutation-report/action.yml passes `--base "origin/$BASE_REF"` to --known-defects, and its
    own env sets BASE_REF. Only that step's block is read: the catch-share step sets BASE_REF and passes --base too."""

    def replay_step(self):
        block = action_step("Replay the known defects")
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


CATCH_STEP = "Report the catch share of the changed lines"
NO_MUTANT_OUTPUT = "catch share: 0/0\nno mutant ran: 4 mutants not run, no changed suite reaches calc.py\n"
# A tool that crashes on an uncaught error exits 1 too, and its output holds no `no mutant ran:` line.
TRACEBACK_OUTPUT = ("Traceback (most recent call last):\n"
                    "  File \"mutate_guard.py\", line 1, in <module>\n"
                    "KeyError: 'no-such-classifier'\n")


class ReportSummaryTests(unittest.TestCase):
    """The catch-share step of actions/mutation-report/action.yml, run as the runner runs its script (bash with -e and
    pipefail, from a file), with a fake tool in place of hooks/mutate_guard.py. The fake prints `output` and exits `code`.
    The tool's exit code and its output are the contract the step reads: a run that exits 1 for no mutant ran prints its
    `no mutant ran:` line, and the job summary must show that line. The step itself is a report, never a check, so it
    exits 0 whatever the tool exits."""

    def summary_for(self, code, output):
        """The job summary the step writes when the tool prints `output` and exits `code`."""
        folder = fresh()
        repo = new_repo()
        git(repo, "commit", "--allow-empty", "-q", "-m", "Base")
        git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        tool = os.path.join(folder, "tool.py")
        with open(tool, "w", encoding="utf-8") as handle:
            handle.write("import sys\nsys.stdout.write(%r)\nsys.exit(%d)\n" % (output, code))
        _env, marker, run = action_step(CATCH_STEP).partition("      run: |\n")
        self.assertTrue(marker, "the catch-share step has no run block")
        script = os.path.join(folder, "step.sh")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write(textwrap.dedent(run))
        summary = os.path.join(folder, "summary.md")
        env = dict(os.environ, TOOL=tool, PROFILE="claude_settings", LIMIT="10", BUDGET="300", SUITE_TIMEOUT="180",
                   BASE_REF="main", EVENT="pull_request", OUT=os.path.join(folder, "out"), GITHUB_STEP_SUMMARY=summary)
        proc = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", script], cwd=repo, env=env,
                              capture_output=True, text=True, encoding="utf-8")
        text = ""
        if os.path.isfile(summary):
            with open(summary, encoding="utf-8") as handle:
                text = handle.read()
        self.assertIn("### Mutation catch share", text,
                      "the step wrote no job summary; its output:\n" + proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 0,
                         "the step exits 0 whatever the tool exits, got %d; its output:\n%s%s"
                         % (proc.returncode, proc.stdout, proc.stderr))
        return text

    def test_a_run_that_exits_1_shows_its_no_mutant_ran_line_in_the_summary(self):
        summary = self.summary_for(1, NO_MUTANT_OUTPUT)
        self.assertRegex(summary, r"(?m)^no mutant ran: ",
                         "the job summary has no `no mutant ran:` line for exit 1:\n" + summary)

    def test_a_run_that_exits_1_does_not_read_as_the_report_did_not_run(self):
        summary = self.summary_for(1, NO_MUTANT_OUTPUT)
        self.assertNotIn("UNKNOWN: the report did not run", summary,
                         "the job summary reads UNKNOWN for exit 1:\n" + summary)

    def test_an_exit_1_with_no_no_mutant_ran_line_reads_unknown_in_the_summary(self):
        self.assertIsNone(NO_MUTANT.search(TRACEBACK_OUTPUT), "the fixture: the output holds no `no mutant ran:` line")
        summary = self.summary_for(1, TRACEBACK_OUTPUT)
        self.assertRegex(summary, r"(?m)^UNKNOWN: .*exit 1",
                         "an exit 1 with no `no mutant ran:` line must read UNKNOWN in the job summary:\n" + summary)

    def test_a_run_that_exits_2_still_reads_as_the_report_did_not_run(self):
        summary = self.summary_for(2, "ERROR no such profile\n")
        self.assertIn("UNKNOWN: the report did not run (exit 2)", summary,
                      "a bad argument (exit 2) must still read UNKNOWN in the job summary:\n" + summary)


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
    """The replay runs a changed suite only. These cases pin that opt-in boundary."""

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


# `--changed` on a select that lists `path::family`: the family suite runs with GUARD_FAMILY set, from its file `path`. The
# change adds mul to calc.py, so the mutants of the change are mul's. SELECTED's select script names one suite per fixture.
CALC_ADD_ONLY = "def add(a, b):\n    return a + b\n"
MUL_ADDED = "\n\ndef mul(a, b):\n    return a * b\n"
FAMILY_CHECK = ("import os\nimport sys\n\nfrom calc import mul\n\n"
                "if os.environ.get('GUARD_FAMILY') == 'kill' and mul(2, 3) != 6:\n"
                "    print('FAIL: mul(2, 3) is not 6 under the kill family')\n"
                "    sys.exit(1)\n"
                "print('ok')\n")
PLAIN_CHECK = ("import sys\n\nfrom calc import mul\n\n"
               "if mul(2, 3) != 6:\n"
               "    print('FAIL: mul(2, 3) is not 6')\n"
               "    sys.exit(1)\n"
               "print('ok')\n")
FAMILY_SELECT = "import sys\nif sys.argv[1] == 'calc.py':\n    print('test_kill.py::kill')\n"
PLAIN_SELECT = "import sys\nif sys.argv[1] == 'calc.py':\n    print('test_plain.py')\n"


def family_repo(select_text, suite_name, suite_text):
    """main holds add, the select script and one suite. The feat branch adds mul to calc.py."""
    repo = new_repo()
    put(repo, {"calc.py": CALC_ADD_ONLY, "select_for.py": select_text, suite_name: suite_text})
    commit(repo, "Base: add, the select script and its suite")
    topic(repo, "feat", {"calc.py": CALC_ADD_ONLY + MUL_ADDED}, "Add mul")
    return repo


class FamilySuiteChangedTests(unittest.TestCase):
    """`--changed` on a select that lists `path::family`. The family suite runs with its family set, so it kills the mutants
    of the change. A plain suite line kills them too: the control that the plain path is unchanged."""

    def mul_mutants(self, repo):
        """How many mutants the change makes on mul's return line."""
        text = show(repo, "feat", "calc.py")
        mul_line = text.split("\n").index("    return a * b") + 1
        want = mutants_on(text, [mul_line])
        self.assertGreater(want, 0, "the fixture needs a mutant on mul's return")
        return want

    def test_the_family_suite_runs_under_its_family_and_kills_the_change_mutants(self):
        repo = family_repo(FAMILY_SELECT, "test_kill.py", FAMILY_CHECK)
        want = self.mul_mutants(repo)
        code, out, err = changed_run(repo, SELECTED)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        killed, _ran, _percent = share_of(out)
        self.assertEqual(killed, want, "test_kill.py::kill must run under GUARD_FAMILY=kill and kill mul's mutants, "
                                       "got %d of %d" % (killed, want))

    def test_a_plain_suite_line_kills_the_same_change_mutants(self):
        repo = family_repo(PLAIN_SELECT, "test_plain.py", PLAIN_CHECK)
        want = self.mul_mutants(repo)
        code, out, err = changed_run(repo, SELECTED)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        killed, _ran, _percent = share_of(out)
        self.assertEqual(killed, want, "a plain suite line kills mul's mutants with no family set, got %d of %d"
                         % (killed, want))


# The --tests-for fixture: one product module, the suites beside it, and one tracked file per form that loads it or only
# mentions it. Each dict maps a path to its text. A load is printed; a mention, a parse failure, a non-test file, an
# untracked file and a different module name are not.
SPEC_HEADER = "import importlib.util\nimport os\n\nHERE = os.path.dirname(os.path.abspath(__file__))\n"
# A loader function whose path is its `path` parameter and whose module name is its `name` parameter, in either order.
LOADER_BODY = ("    spec = importlib.util.spec_from_file_location(name, path)\n"
               "    module = importlib.util.module_from_spec(spec)\n"
               "    spec.loader.exec_module(module)\n"
               "    return module\n")


def wrapper_suite(def_line, tail):
    """A suite text: the header, one loader function under `def_line`, then `tail`."""
    return SPEC_HEADER + "\n\n" + def_line + "\n" + LOADER_BODY + "\n" + tail


TESTS_FOR_PRODUCT = {
    "pkg/widget.py": "VALUE = 1\n",
    "pkg/lonely.py": "VALUE = 2\n",
    "pkg/widget.mjs": "export const VALUE = 1;\n",
}
TESTS_FOR_BESIDE = {
    "pkg/test_widget.py": "VALUE = 1\n",
    "pkg/test_widget_extra.py": "VALUE = 1\n",
    "pkg/test_widget_also.py": "import widget\n",  # beside and a load: printed once
    "pkg/test_widget_broken.py": "def broken(:\n",  # beside, and unparsable: printed all the same, as the beside rule is by name
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
    "tests/test_form_wrapper_first.py": wrapper_suite(
        "def load_file_module(path, name):",
        'WIDGET = os.path.join(HERE, "widget.py")\n\n\ndef read_value():\n'
        '    return load_file_module(WIDGET, "x_under_test").VALUE\n'),
    "tests/test_form_wrapper_second.py": wrapper_suite(
        "def load(name, path):", 'WIDGET = load("x_under_test", os.path.join(HERE, "widget.py"))\n'),
    "tests/test_form_wrapper_keyword.py": wrapper_suite(
        "def load(name, path):", 'WIDGET = load(name="x_under_test", path=os.path.join(HERE, "widget.py"))\n'),
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
    # The loader is called, but never with widget.py: the path parameter is fed another module.
    "tests/test_no_wrapper_other.py": wrapper_suite(
        "def load_file_module(path, name):",
        'OTHER = load_file_module(os.path.join(HERE, "other_module.py"), "x_under_test")\n'),
    # "widget.py" reaches the module-name slot, not the path. A path-only read of the call would print this file.
    "tests/test_no_wrapper_name_slot.py": wrapper_suite(
        "def load(path, name):", 'OTHER = load(os.path.join(HERE, "other_module.py"), "widget.py")\n'),
    # A path with no .py suffix does not name the module, as bin/sim-lease does not name a .py file.
    "tests/test_no_wrapper_bare_name.py": wrapper_suite(
        "def load(path, name):", 'BARE = load(os.path.join(HERE, "widget"), "x_under_test")\n'),
    # json.load is an attribute call, not a load of the module. The loader in this file is called with another module.
    # The name is a bare string, not a path expression: a path expression (open, join) of widget.py is a read of it.
    "tests/test_no_json_load.py": "import json\n" + wrapper_suite(
        "def load(path, name):",
        'DATA = json.load("widget.py")\n'
        'OTHER = load(os.path.join(HERE, "other_module.py"), "x_under_test")\n'),
    # Two functions share the parameter name `path`. Only the loader is called with another module, so only a
    # per-function read keeps widget.py out of the loader's path. describe gets a bare string: a join of widget.py is a read.
    "tests/test_no_shared_param_name.py": SPEC_HEADER
        + "\n\ndef describe(path):\n    return os.path.basename(path)\n\n\ndef load(path, name):\n" + LOADER_BODY
        + '\nNAME = describe("widget.py")\n'
        + 'OTHER = load(os.path.join(HERE, "other_module.py"), "x_under_test")\n',
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
    Any unlisted path also gets each suite that names its basename in a path expression. A tracked test that fails to
    parse is skipped, unless it sits beside the path."""

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
        tracked = git(repo, "ls-files").split("\n")
        self.assertIn("pkg/widget.py", tracked, "the fixture: the product module is tracked")
        code, out, err = run_cli(["--tests-for", "pkg/widget.py"], cwd=repo)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        printed = set(out.splitlines())
        for name in sorted(TESTS_FOR_LOADS):
            with self.subTest(form=name):
                self.assertIn(name, tracked, "the fixture: %s is tracked, so it can load widget" % name)
                self.assertIn(name, printed, "%s loads widget, so --tests-for pkg/widget.py must print it" % name)

    def test_each_mention_that_is_not_a_load_prints_nothing(self):
        repo = tests_for_fixture()
        tracked = git(repo, "ls-files").split("\n")
        code, out, err = run_cli(["--tests-for", "pkg/widget.py"], cwd=repo)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        printed = set(out.splitlines())
        for name in sorted(TESTS_FOR_MENTIONS):
            with self.subTest(file=name):
                self.assertIn(name, tracked, "the fixture: %s is tracked, so the read reaches it" % name)
                self.assertNotIn(name, printed, "%s does not load widget, so --tests-for must not print it" % name)
        for name in sorted(UNTRACKED):
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
                         "a non-.py path that no suite names gets the beside suites only, with no loads")

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
        # hooks/guard.py has a GUARD_MODULE_FAMILIES row, so hooks/test_guard.py prints as `hooks/test_guard.py::<family>` lines:
        # the file counts as printed when one of its family lines is.
        families = {line.split("::")[1] for line in out.splitlines() if line.startswith("hooks/test_guard.py::")}
        self.assertEqual(families, set(guard_table()[target]), "the row's families are the family lines it prints")
        printed = {line.split("::")[0] for line in out.splitlines()}
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

    def test_a_load_bound_inside_a_function_is_the_rm_var_family_line_for_guard_rm_var(self):
        target = "hooks/guard_rm_var.py"
        self.assertNotIn(target, dict(mutate_guard.REPORT_TARGETS), "the fixture: %s must be unlisted" % target)
        sections = guard_section_files("HEAD")
        self.assertTrue(sections, "the fixture: no guard section file is read from the runner's SECTION_DIR at HEAD")
        loaders = sorted(path for path, text in sections.items()
                         if re.search(r'(?m)^    path = os\.path\.join\(.*"guard_rm_var\.py"\)$', text))
        self.assertEqual(len(loaders), 1, "the fixture: one guard section file binds the guard_rm_var path inside a "
                         "function, found %s" % loaders)
        self.assertTrue(mutate_guard._loads_module(sections[loaders[0]], "guard_rm_var"),
                        "the fixture: %s loads guard_rm_var, as the walk reads it" % loaders[0])
        runner = "hooks/test_guard.py"
        code, out, err = run_cli(["--tests-for", target])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(out.splitlines(), ["%s::rm-var" % runner],
                         "guard_rm_var's only walk suite is the rm-var family line of %s" % runner)

    def test_a_module_only_a_guard_section_file_loads_prints_the_whole_runner(self):
        """hooks/reread_check.py is loaded by a tests/guard section file alone. The runner that runs that section file is
        printed in its place, and the section file is not. The module has no GUARD_MODULE_FAMILIES row, so no family line."""
        target = "hooks/reread_check.py"
        self.assertNotIn(target, guard_table(), "the fixture: %s has no GUARD_MODULE_FAMILIES row" % target)
        self.assertNotIn(target, dict(mutate_guard.REPORT_TARGETS), "the fixture: %s is no REPORT_TARGETS row" % target)
        sections = guard_section_files("HEAD")
        loaders = sorted(path for path, text in sections.items() if mutate_guard._loads_module(text, "reread_check"))
        self.assertTrue(loaders, "the fixture: a guard section file at HEAD loads reread_check, as the walk reads it")
        code, out, err = run_cli(["--tests-for", target])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        printed = out.splitlines()
        self.assertIn("hooks/test_guard.py", printed,
                      "--tests-for %s must list hooks/test_guard.py, the runner of %s" % (target, loaders[0]))
        self.assertEqual([line for line in printed if "::" in line], [],
                         "%s has no GUARD_MODULE_FAMILIES row, so no hooks/test_guard.py::<family> line is printed" % target)
        section_folder = os.path.dirname(loaders[0]) + "/"
        self.assertEqual([line for line in printed if line.startswith(section_folder)], [],
                         "the section file %s is never printed: the runner stands for it" % loaders[0])

    def test_the_real_suites_that_load_a_module_through_a_parameter_are_printed(self):
        """Each suite passes the module's path to a function of its own, which loads it by that parameter. The call text is
        the scope: it is asserted first, so the print is asserted on a suite known to reach the load."""
        cases = (
            ("hooks/guard.py", "hooks/test_call_judge.py", "load_file_module(GUARD, "),
            ("hooks/guard.py", "lint/test_layout.py", 'load("guard_under_test", os.path.join(REPO, "hooks", "guard.py"))'),
            ("lint/ste_lint.py", "lint/test_layout.py", 'load("ste_lint_under_test", os.path.join(LINT, "ste_lint.py"))'),
        )
        printed = {}
        for target in sorted({target for target, _, _ in cases}):
            code, out, err = run_cli(["--tests-for", target])
            self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
            printed[target] = walk_suites(target) if target == "hooks/guard.py" else set(out.splitlines())
        for target, suite, call in cases:
            with self.subTest(suite=suite, target=target):
                self.assertIn(call, show(REPO, "HEAD", suite), "the fixture: %s calls its loader with %s" % (suite, target))
                self.assertIn(suite, printed[target],
                              "%s loads %s through a parameter, so --tests-for %s must print it" % (suite, target, target))

    def test_a_path_constant_naming_guard_py_is_read_but_its_suite_is_dropped_as_unusable(self):
        target = "hooks/guard.py"
        self.assertNotIn(target, dict(mutate_guard.REPORT_TARGETS), "the fixture: %s must be unlisted" % target)
        loader = "hooks/test_wrappers.py"
        self.assertRegex(show(REPO, "HEAD", loader), r'(?m)^GUARD_PY = os\.path\.join\(HERE, "guard\.py"\)$',
                         "the fixture: %s binds guard.py to the GUARD_PY path constant" % loader)
        self.assertIn(loader, walk_suites(target),
                      "%s copies guard.py by its GUARD_PY path constant, so the read of %s must find it" % (loader, target))
        code, out, err = run_cli(["--tests-for", target])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertNotIn(loader, out.splitlines(),
                         "%s reads not green on the unparsed copy, so --tests-for %s drops it" % (loader, target))

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

    def test_a_beside_suite_that_fails_to_parse_is_still_printed(self):
        repo = tests_for_fixture()
        self.assertIn("pkg/test_widget_broken.py", git(repo, "ls-files").split("\n"),
                      "the fixture: the broken suite is tracked")
        code, out, err = run_cli(["--tests-for", "pkg/widget.py"], cwd=repo)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertIn("pkg/test_widget_broken.py", out.splitlines(),
                      "a suite beside pkg/widget.py is printed by name, though it fails to parse")

    def test_a_non_hooks_file_that_no_suite_names_prints_nothing(self):  # the control for the lint case below
        repo = tests_for_fixture()
        code, out, err = run_cli(["--tests-for", "docs/notes.md"], cwd=repo)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(out, "", "no suite sits beside docs/notes.md, and none names it, so nothing is printed")


CHAIN_SUITE = "hooks/test_chain.py"  # opens hooks/entry.py by a path constant, so it loads entry.py
CHAIN_OPENS = ("import os\n\nHERE = os.path.dirname(os.path.abspath(__file__))\nENTRY = os.path.join(HERE, \"entry.py\")\n"
               "with open(ENTRY, encoding='utf-8') as handle:\n    handle.read()\n")
CHAIN_LOADS = {"import": "import leaf\n\nVALUE = leaf.V\n",  # entry.py loads leaf.py by an import
               "importlib": "import importlib\n\nleaf = importlib.import_module(\"leaf\")\n"}  # or by importlib


def chain_repo(entry_text, lane):
    """A repository whose base holds CHAIN_SUITE, hooks/entry.py (`entry_text`) and hooks/leaf.py. The branch `lane` then
    writes `lane` (path -> text) and commits, so main...HEAD is the files `lane` names."""
    repo = new_repo()
    put(repo, {CHAIN_SUITE: CHAIN_OPENS, "hooks/entry.py": entry_text, "hooks/leaf.py": "V = 1\n"})
    commit(repo, "base")
    git(repo, "checkout", "-qb", "lane")
    put(repo, lane)
    commit(repo, "change")
    return repo


class LintSuitesChainTests(unittest.TestCase):
    """`--lint-suites BASE` picks a suite that reaches a changed file through a module the suite loads. CHAIN_SUITE opens
    hooks/entry.py by a path constant, and entry.py loads hooks/leaf.py by an import, or by importlib.import_module. A diff
    that changes only leaf.py picks the suite (one case per form). A diff that changes entry.py picks it too (the control)."""

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

    def test_a_diff_that_deletes_a_module_that_a_suite_reaches_by_import_picks_the_suite(self):
        # the control is test_a_diff_of_only_a_module_that_a_suite_reaches_by_import_picks_the_suite: the same fixture, with
        # leaf.py edited. Here the lane deletes leaf.py, and the unchanged entry.py still imports it.
        repo = chain_repo(CHAIN_LOADS["import"], {"hooks/leaf.py": None})
        self.assertEqual(self.changed(repo), ["hooks/leaf.py"], "the scope: the diff holds only the deletion of leaf.py")
        self.assertIn(CHAIN_SUITE, self.picked(repo),
                      "--lint-suites must pick %s for a diff that deletes hooks/leaf.py: entry.py, unchanged, imports it, and the "
                      "suite opens entry.py" % CHAIN_SUITE)

    def test_a_diff_touching_no_hooks_file_picks_no_suite(self):  # the control: CHAIN_SUITE is a hooks suite in this repository
        repo = chain_repo(CHAIN_LOADS["import"], {"docs/notes.md": "one\n"})
        self.assertEqual(self.changed(repo), ["docs/notes.md"], "the scope: the diff holds only a file no hooks suite names")
        self.assertEqual(self.picked(repo), [],
                         "--lint-suites must pick no suite for a diff that touches no hooks file, though %s is in the repository"
                         % CHAIN_SUITE)


# GUARD_MODULE_FAMILIES (hooks/mutate_guard.py) gives a guard module its family suites, hooks/test_guard.py::<family>,
# and the import walk's suites come with them. row_walk_suites reads those walk suites for a row from walk_suites (the one
# read of the tracked tree), so a suite that starts to load a module is counted with no list to update (rule
# building-allow-list-is-the-constant).
def row_walk_suites(module):
    """The import walk's suites for a table row: walk_suites, minus the whole hooks/test_guard.py (its family lines stand
    in for it) and the row's GUARD_MODULE_DROPPED_SUITES."""
    dropped = getattr(mutate_guard, "GUARD_MODULE_DROPPED_SUITES", {}).get(module, ())
    return walk_suites(module) - {"hooks/test_guard.py"} - set(dropped)


def guard_table():
    """GUARD_MODULE_FAMILIES. A missing table reads as no rows."""
    return getattr(mutate_guard, "GUARD_MODULE_FAMILIES", None) or {}


def guard_exempt():
    """GUARD_MODULE_EXEMPT: each module shared by every family, with the reason it has no row."""
    return getattr(mutate_guard, "GUARD_MODULE_EXEMPT", None) or {}


def guard_family_names():
    """The keys of FAMILIES in hooks/test_guard.py, read from its source by ast. The file runs its cases on import, so it is
    never imported here."""
    with open(os.path.join(HERE, "test_guard.py"), encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "FAMILIES"
                                                for target in node.targets):
            return set(ast.literal_eval(node.value))
    raise AssertionError("hooks/test_guard.py has no FAMILIES dict")


def guard_modules_on_disk(folder):
    """Each hooks/guard_*.py under `folder`, read from the folder itself, so a new file is listed with no list to update."""
    return sorted("hooks/" + name for name in os.listdir(os.path.join(folder, "hooks"))
                  if fnmatch.fnmatchcase(name, "guard_*.py"))


def unlisted_guard_modules(folder, table, exempt):
    """The check. Each guard module under `folder` that has no row in `table`, is not REPORT_GOLD's file, and has no exemption
    in `exempt` with a non-empty reason. An exemption with a blank reason is no exemption, so the check never skips silently."""
    gold = mutate_guard.REPORT_GOLD[0]
    reasoned = {path for path, reason in exempt.items() if isinstance(reason, str) and reason.strip()}
    return [path for path in guard_modules_on_disk(folder)
            if path not in table and path != gold and path not in reasoned]


class GuardModuleFamilyTests(unittest.TestCase):
    """GUARD_MODULE_FAMILIES. Each hooks/guard_*.py on disk has a row, is REPORT_GOLD's file, or is exempt with a reason."""

    def test_every_guard_module_on_disk_has_a_row_or_is_gold_or_exempt(self):
        missing = unlisted_guard_modules(REPO, guard_table(), guard_exempt())
        self.assertEqual(missing, [], "each hooks/guard_*.py needs a row in GUARD_MODULE_FAMILIES, or a reason in "
                                      "GUARD_MODULE_EXEMPT")

    def test_a_new_guard_module_with_no_row_fails_the_check_and_no_other_does(self):
        folder = fresh()
        put(folder, {path: "" for path in guard_modules_on_disk(REPO)})
        table, exempt = guard_table(), guard_exempt()
        self.assertEqual(unlisted_guard_modules(folder, table, exempt), [],
                         "the fixture of the real guard modules flags nothing: each one needs its row or its exemption")
        put(folder, {"hooks/guard_zzz_new.py": ""})
        self.assertEqual(unlisted_guard_modules(folder, table, exempt), ["hooks/guard_zzz_new.py"],
                         "a new guard module with no row fails the check, and no other module does")

    def test_an_exemption_with_a_blank_reason_is_no_exemption(self):
        folder = fresh()
        put(folder, {"hooks/guard_core.py": "", "hooks/guard_kill.py": ""})
        flagged = unlisted_guard_modules(folder, {"hooks/guard_kill.py": ["kill"]}, {"hooks/guard_core.py": " "})
        self.assertEqual(flagged, ["hooks/guard_core.py"], "an exemption with a blank reason is no exemption")

    def test_guard_core_is_exempt_with_a_reason_and_has_no_row(self):
        reason = guard_exempt().get("hooks/guard_core.py")
        self.assertIsInstance(reason, str, "guard_core.py is shared by every family: GUARD_MODULE_EXEMPT must name it "
                                           "with a reason")
        self.assertTrue(reason.strip(), "guard_core.py's exemption has a blank reason")
        self.assertNotIn("hooks/guard_core.py", guard_table(), "guard_core.py is exempt, not a family row")

    def test_every_row_is_a_non_empty_list(self):
        table = guard_table()
        self.assertIn("hooks/guard_kill.py", table, "GUARD_MODULE_FAMILIES has no row for hooks/guard_kill.py")
        for module, families in sorted(table.items()):
            with self.subTest(module=module):
                self.assertIsInstance(families, list, "%s: a row is a list of families" % module)
                self.assertTrue(families, "%s has an empty row: --tests-for would print nothing for it" % module)

    def test_every_family_a_row_names_is_a_key_of_test_guard_families(self):
        table = guard_table()
        self.assertIn("hooks/guard_kill.py", table, "GUARD_MODULE_FAMILIES has no row for hooks/guard_kill.py")
        named = {family for families in table.values() for family in families}
        self.assertEqual(sorted(named - guard_family_names()), [],
                         "a row names a family that hooks/test_guard.py does not have")

    def test_tests_for_guard_kill_prints_its_family_lines_and_its_import_walk_suite(self):
        code, out, err = run_cli(["--tests-for", "hooks/guard_kill.py"])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(out.splitlines(), ["hooks/test_agent_procs.py", "hooks/test_checks_never_raise.py",
                                            "hooks/test_guard.py::git-env", "hooks/test_guard.py::kill"],
                         "guard_kill.py's suites are the git-env and kill family lines, plus the import walk's "
                         "test_agent_procs.py and test_checks_never_raise.py, which reach the kill checks the "
                         "families miss, sorted")

    def test_tests_for_guard_env_prints_its_family_lines_and_its_import_walk_suite(self):
        code, out, err = run_cli(["--tests-for", "hooks/guard_env.py"])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(out.splitlines(), ["hooks/test_guard.py::env", "hooks/test_guard.py::git-env",
                                            "janitor/test_session_end_sweep.py"],
                         "guard_env.py's suites are the env and git-env family lines, plus the import walk's "
                         "janitor/test_session_end_sweep.py, sorted")

    def test_every_table_module_prints_its_family_lines_and_its_walk_suites(self):
        table = guard_table()
        self.assertIn("hooks/guard_kill.py", table, "GUARD_MODULE_FAMILIES has no row for hooks/guard_kill.py")
        for module, families in sorted(table.items()):
            with self.subTest(module=module):
                code, out, err = run_cli(["--tests-for", module])
                self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
                expected = {"hooks/test_guard.py::%s" % family for family in families} | row_walk_suites(module)
                self.assertEqual(out.splitlines(), sorted(expected),
                                 "%s prints its family lines and its import-walk suites, each once, sorted" % module)

    def test_no_table_module_prints_the_whole_test_guard_file(self):
        """The whole file takes minutes per mutant, so a table module's family lines stand in for it, never the file."""
        table = guard_table()
        self.assertIn("hooks/guard_kill.py", table, "GUARD_MODULE_FAMILIES has no row for hooks/guard_kill.py")
        for module in sorted(table):
            with self.subTest(module=module):
                code, out, err = run_cli(["--tests-for", module])
                self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
                self.assertNotIn("hooks/test_guard.py", out.splitlines(),
                                 "%s prints the whole hooks/test_guard.py, which takes minutes per mutant" % module)

    def test_tests_for_guard_py_runs_family_slices_and_never_the_two_whole_slow_suites(self):
        """hooks/guard.py: the whole hooks/test_guard.py and merge/test_merge.py time out at 180 s on the clean source, so
        no mutant starts inside the 300 s budget (step mutation-tests-for-cost, 6 runs, 0 of 10 mutants ran)."""
        target = "hooks/guard.py"
        self.assertNotIn(target, dict(mutate_guard.REPORT_TARGETS), "the fixture: %s is no REPORT_TARGETS row" % target)
        code, out, err = run_cli(["--tests-for", target])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        printed = out.splitlines()
        self.assertIn(target, guard_table(), "hooks/guard.py needs a GUARD_MODULE_FAMILIES row")
        self.assertNotIn("hooks/test_guard.py", printed, "the whole hooks/test_guard.py takes minutes per mutant")
        self.assertNotIn("merge/test_merge.py", printed, "the whole merge/test_merge.py takes minutes per mutant")
        self.assertTrue([line for line in printed if line.startswith("hooks/test_guard.py::")],
                        "hooks/guard.py prints at least one hooks/test_guard.py::<family> line")
        for name in ("hooks/test_wrappers.py", "lint/test_layout.py", "lint/test_report_guard_stamped.py"):
            self.assertNotIn(name, printed, "%s asserts on guard.py's own text, so it reads not green on the unparsed "
                                            "copy and never kills a mutant" % name)

    def test_a_suite_that_loads_a_table_module_inside_a_function_is_kept(self):
        """lint/test_hook_catalog.py imports guard_merge inside a test method, so the import walk finds it only
        through a function-bound load. The union keeps it beside the family line. The scope is asserted first, then
        the print."""
        target, suite = "hooks/guard_merge.py", "lint/test_hook_catalog.py"
        self.assertIn(target, guard_table(), "the fixture: %s keeps its GUARD_MODULE_FAMILIES row" % target)
        self.assertIn(suite, row_walk_suites(target), "the fixture: the import walk reaches %s for %s" % (suite, target))
        tree = ast.parse(show(REPO, "HEAD", suite))
        module_level = [node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == "guard_merge"]
        self.assertEqual(module_level, [], "the fixture: %s has no module-level import of guard_merge" % suite)
        in_def = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and any(isinstance(inner, ast.ImportFrom) and inner.module == "guard_merge"
                          for inner in ast.walk(node))]
        self.assertTrue(in_def, "the fixture: %s imports guard_merge inside a def" % suite)
        code, out, err = run_cli(["--tests-for", target])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        expected = {"hooks/test_guard.py::%s" % family for family in guard_table()[target]} | row_walk_suites(target)
        self.assertEqual(out.splitlines(), sorted(expected),
                         "%s loads guard_merge only inside a def, so the import walk finds it through a function-bound "
                         "load, and the union keeps it beside the merge family line" % suite)

    def test_guard_wsl_is_report_gold_and_no_row_and_no_report_target(self):
        gold = mutate_guard.REPORT_GOLD[0]
        self.assertEqual(gold, "hooks/guard_wsl.py", "the fixture: REPORT_GOLD scores guard_wsl.py")
        self.assertNotIn(gold, guard_table(), "REPORT_GOLD's file is scored once, against the whole test_guard.py")
        self.assertFalse(set(guard_table()) & set(dict(mutate_guard.REPORT_TARGETS)),
                         "a table module is no REPORT_TARGETS row, so the report does not score it twice")


# The `_loads_module` table, called directly. Each row is a form's name and a Python text, read with the stem `widget`.
# A text is the shared header, then the form's own lines. A text that does not parse reads False too, so each row
# asserts that it parses before it asserts False.
def loads_source(*lines):
    """Python text: the shared header, then each line."""
    return SPEC_HEADER + "\n" + "\n".join(lines) + "\n"


def kwargs_copy_source(local):
    """A `**kwargs` loader that copies the keyword `path` into the local `local`, then loads the local. The call passes
    `path=` by keyword, so only the local's name decides whether the loader follows the copy."""
    return loads_source(
        "def load(**kwargs):",
        '    %s = kwargs["path"]' % local,
        '    return importlib.util.spec_from_file_location(kwargs["name"], %s)' % local,
        "",
        "",
        'MODULE = load(name="x_under_test", path=os.path.join(HERE, "widget.py"))',
    )


FOLLOWED_FORMS = (
    ("a positional argument", TESTS_FOR_LOADS["tests/test_form_wrapper_second.py"]),
    ("a keyword argument", TESTS_FOR_LOADS["tests/test_form_wrapper_keyword.py"]),
    ("a bound name", TESTS_FOR_LOADS["tests/test_form_spec_named.py"]),
    ("a **kwargs loader that copies the keyword into a local of the same name", kwargs_copy_source("path")),
)
UNFOLLOWED_FORMS = (
    ("an imported loader", loads_source(
        "from loaders import load_widget",
        "",
        'MODULE = load_widget("x_under_test", os.path.join(HERE, "widget.py"))',
    )),
    ("a wrapper called through another wrapper", loads_source(
        "def inner(path, name):",
        "    return importlib.util.spec_from_file_location(name, path)",
        "",
        "",
        "def outer(path, name):",
        "    return inner(path, name)",
        "",
        "",
        'WIDGET = outer(os.path.join(HERE, "widget.py"), "x_under_test")',
    )),
    ("an attribute call, obj.load(...)", loads_source(
        "class Loader:",
        "    def load(self, name, path):",
        "        return importlib.util.spec_from_file_location(name, path)",
        "",
        "",
        "LOADER = Loader()",
        'MODULE = LOADER.load("x_under_test", os.path.join(HERE, "widget.py"))',
    )),
    ("a self call, self.load(...)", loads_source(
        "class Loader:",
        "    def load(self, name, path):",
        "        return importlib.util.spec_from_file_location(name, path)",
        "",
        "    def run(self):",
        '        return self.load("x_under_test", os.path.join(HERE, "widget.py"))',
    )),
    ("a default literal, path=WIDGET", loads_source(
        'WIDGET = os.path.join(HERE, "widget.py")',
        "",
        "",
        "def load(name, path=WIDGET):",
        "    return importlib.util.spec_from_file_location(name, path)",
        "",
        "",
        'MODULE = load("x_under_test")',
    )),
    ("a lambda loader", loads_source(
        "load = lambda name, path: importlib.util.spec_from_file_location(name, path)",
        'MODULE = load("x_under_test", os.path.join(HERE, "widget.py"))',
    )),
    ("a bare alias, helper = load", loads_source(
        "def load(name, path):",
        "    return importlib.util.spec_from_file_location(name, path)",
        "",
        "",
        "helper = load",
        'MODULE = helper("x_under_test", os.path.join(HERE, "widget.py"))',
    )),
    ("a loader that takes *args", loads_source(
        "def load(*args):",
        "    return importlib.util.spec_from_file_location(args[0], args[1])",
        "",
        "",
        'MODULE = load("x_under_test", os.path.join(HERE, "widget.py"))',
    )),
    ("a loader that takes **kwargs, read inline", loads_source(
        "def load(**kwargs):",
        '    return importlib.util.spec_from_file_location(kwargs["name"], kwargs["path"])',
        "",
        "",
        'MODULE = load(name="x_under_test", path=os.path.join(HERE, "widget.py"))',
    )),
    ("a **kwargs loader that copies the keyword into a differently named local", kwargs_copy_source("p")),
    ("a call that spreads the path in, *names", loads_source(
        "def load(name, path):",
        "    return importlib.util.spec_from_file_location(name, path)",
        "",
        "",
        'NAMES = ["x_under_test"]',
        'MODULE = load(*NAMES, os.path.join(HERE, "widget.py"))',
    )),
    ("a call that spreads a dict, **{...}", loads_source(
        "def load(name, path):",
        "    return importlib.util.spec_from_file_location(name, path)",
        "",
        "",
        'MODULE = load("x_under_test", **{"path": os.path.join(HERE, "widget.py")})',
    )),
    ("a for target", loads_source(
        'for path in [os.path.join(HERE, "widget.py")]:',
        '    MODULE = importlib.util.spec_from_file_location("x_under_test", path)',
    )),
    ("a comprehension target", loads_source(
        "MODULES = [",
        '    importlib.util.spec_from_file_location("x_under_test", path)',
        '    for path in [os.path.join(HERE, "widget.py")]',
        "]",
    )),
    ("a tuple unpacking", loads_source(
        'PATH, MODE = os.path.join(HERE, "widget.py"), "r"',
        'MODULE = importlib.util.spec_from_file_location("x_under_test", PATH)',
    )),
    ("an augmented assignment", loads_source(
        'PATH = os.path.join(HERE, "widget")',
        'PATH += ".py"',
        'MODULE = importlib.util.spec_from_file_location("x_under_test", PATH)',
    )),
    ("a with ... as target", loads_source(
        "import contextlib",
        "",
        'with contextlib.nullcontext(os.path.join(HERE, "widget.py")) as PATH:',
        '    MODULE = importlib.util.spec_from_file_location("x_under_test", PATH)',
    )),
    ("an attribute store, self.path = ...", loads_source(
        "class Holder:",
        "    def __init__(self):",
        '        self.path = os.path.join(HERE, "widget.py")',
        "",
        "    def run(self):",
        '        return importlib.util.spec_from_file_location("x_under_test", self.path)',
    )),
    ("a class constructor that takes the path", loads_source(
        "class Loader:",
        "    def __init__(self, path):",
        '        self.module = importlib.util.spec_from_file_location("x_under_test", path)',
        "",
        "",
        'LOADER = Loader(os.path.join(HERE, "widget.py"))',
    )),
    ("functools.partial", loads_source(
        "import functools",
        "",
        "",
        "def load(name, path):",
        "    return importlib.util.spec_from_file_location(name, path)",
        "",
        "",
        'LOAD_WIDGET = functools.partial(load, "x_under_test", os.path.join(HERE, "widget.py"))',
    )),
    ("map", loads_source(
        "def load(path):",
        '    return importlib.util.spec_from_file_location("x_under_test", path)',
        "",
        "",
        'MODULES = list(map(load, [os.path.join(HERE, "widget.py")]))',
    )),
    ("a walrus binding", loads_source(
        'if (PATH := os.path.join(HERE, "widget.py")):',
        '    MODULE = importlib.util.spec_from_file_location("x_under_test", PATH)',
    )),
    ("a split literal", loads_source(
        'MODULE = importlib.util.spec_from_file_location("x_under_test", os.path.join(HERE, "widget" + ".py"))',
    )),
)


def shift_source(call):
    """The method-shift fixture: a module-level `load` that returns a basename, and `Reader.load`, whose second parameter
    is the path. Only `call` differs between the subject and its control."""
    return loads_source(
        "def load(name, path):",
        "    return os.path.basename(path)",
        "",
        "",
        "class Reader:",
        "    def load(self, path):",
        '        return importlib.util.spec_from_file_location("x_under_test", path)',
        "",
        call,
    )


class LoadsModuleTests(unittest.TestCase):
    """`_loads_module(text, stem)` in hooks/mutate_guard.py, called directly. The followed forms read True. The unfollowed
    forms its docstring names read False. A text that fails to parse also reads False, so each row asserts it parses."""

    def assert_parses(self, name, text):
        try:
            ast.parse(text)
        except SyntaxError as error:
            self.fail("%s does not parse, so its False proves nothing: %s" % (name, error))

    def test_a_followed_form_reads_as_a_load(self):
        for name, text in FOLLOWED_FORMS:
            with self.subTest(form=name):
                self.assert_parses(name, text)
                self.assertTrue(mutate_guard._loads_module(text, "widget"),
                                "%s loads widget.py, so _loads_module reads True" % name)

    def test_an_unfollowed_form_reads_as_not_a_load(self):
        for name, text in UNFOLLOWED_FORMS:
            with self.subTest(form=name):
                self.assert_parses(name, text)
                self.assertFalse(mutate_guard._loads_module(text, "widget"),
                                 "%s is not followed, so _loads_module reads False" % name)

    def test_an_empty_text_reads_as_not_a_load(self):
        self.assertFalse(mutate_guard._loads_module("", "widget"), "an empty text loads nothing")

    def test_a_positional_bare_call_feeds_a_same_named_method_and_reads_true(self):
        # A known false selection, pinned as the docstring states it. The bare call `load("x", "widget.py")` also feeds
        # `Reader.load`, since every def of that name takes the call, and its second parameter is the path. The control
        # passes another module, so the True comes from the bare call's literal and not from the method's own text.
        control = shift_source('LOADED = load("x", "other_module.py")')
        subject = shift_source('LOADED = load("x", "widget.py")')
        self.assert_parses("the control", control)
        self.assertFalse(mutate_guard._loads_module(control, "widget"),
                         "the control passes another module, so _loads_module reads False")
        self.assert_parses("the subject", subject)
        self.assertTrue(mutate_guard._loads_module(subject, "widget"),
                        "the known false selection: the bare call feeds Reader.load, so _loads_module reads True")

    def test_a_keyword_bare_call_feeds_the_same_method_and_reads_true(self):
        # The docstring's own example, `load(path=X)`: the keyword feeds the method's path as well.
        control = shift_source('LOADED = load(path="other_module.py")')
        subject = shift_source('LOADED = load(path="widget.py")')
        self.assert_parses("the control", control)
        self.assertFalse(mutate_guard._loads_module(control, "widget"),
                         "the control passes another module, so _loads_module reads False")
        self.assert_parses("the subject", subject)
        self.assertTrue(mutate_guard._loads_module(subject, "widget"),
                        "the known false selection: the keyword call feeds Reader.load, so _loads_module reads True")


if __name__ == "__main__":
    unittest.main()
