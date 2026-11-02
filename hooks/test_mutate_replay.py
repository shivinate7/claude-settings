#!/usr/bin/env python3
"""Cases for the mutation replay: hooks/mutate_shared.py (`merged_prs`, `replay_pr`, `format_replay`)
and its `--replay` mode in hooks/mutate_guard.py. Standard library only, unittest style.

    python3 hooks/test_mutate_replay.py

A replay scores the suites a pull request changed against mechanical mutants of the product lines
that pull request added. Each case builds a small fixture repository of merged pull requests and
asks for the score. The failure classes under test:

- a crash (a throw, an import error, a hang killed at the timeout) is not a kill;
- a suite red on the clean source is unusable, and a row with no usable suite is UNKNOWN;
- UNKNOWN never reads as a rate or as green;
- a replay leaves the repository, the temp folders and the child processes as it found them.

The JavaScript cases need the typescript package: `npm ci --ignore-scripts --no-audit --no-fund` at the
repository root. A missing package is a FAIL, never a skip. A contract name missing from
hooks/mutate_shared.py is a FAIL line, so the red run reads as a list of FAIL lines, not ERROR lines.

The git and line helpers come from hooks/test_mutate_js.py, the one home of them. Temp files live in
the run folder of lint/_test_temp.py. The sweep of old run folders is proven once, in
hooks/test_mutate_js.py (TempRunFolderTests).

Process checks use `ps` and so run on POSIX only, as the CI step does (ubuntu-latest).
"""
import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import mutate_guard  # noqa: E402  REPLAY_PROFILES, the banchi per-module runner among them
import mutate_shared  # noqa: E402
from test_mutate_js import git, unique_line  # noqa: E402  the one home of these two helpers

RUN = ""  # this run's folder, made in setUpModule and removed in tearDownModule
CACHE = {}  # built fixtures and replayed rows, per run: a replay runs once, not once per case


def setUpModule():
    global RUN
    RUN = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)


def api(name):
    """A contract name from hooks/mutate_shared.py. Its absence is a FAIL line, not an ERROR."""
    found = getattr(mutate_shared, name, None)
    if found is None:
        raise AssertionError("hooks/mutate_shared.py has no %s yet" % name)
    return found


# ---------------------------------------------------------------------------------------------------
# Fixture builders. Each PR is a branch cut from main, merged back with a merge commit whose body
# starts with the title, as GitHub writes it.

def fresh():
    """A new empty folder under the run folder."""
    folder = os.path.join(RUN, uuid.uuid4().hex)
    os.makedirs(folder)
    return folder


def new_repo(name):
    repo = os.path.join(fresh(), name)
    os.makedirs(repo)
    git(repo, "init", "-q", "-b", "main")
    return repo


def put(repo, files):
    """Write each file. A None text removes it, and a bytes value is written as it is. Folders are made as needed."""
    for path, text in files.items():
        full = os.path.join(repo, path)
        if text is None:
            os.remove(full)
            continue
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if isinstance(text, bytes):
            with open(full, "wb") as handle:
                handle.write(text)
            continue
        with open(full, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)


def commit(repo, message):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def topic(repo, branch, files, message):
    """Commit `files` on a new branch cut from main. Leaves the repository on main."""
    git(repo, "checkout", "-q", "-b", branch, "main")
    put(repo, files)
    commit(repo, message)
    git(repo, "checkout", "-q", "main")


def merge_pr(repo, number, title, branch):
    """Merge `branch` into main as GitHub does: a merge commit whose body starts with the title."""
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "Merge pull request #%d from fixture/%s" % (number, branch),
        "-m", title, branch)
    return git(repo, "rev-parse", "HEAD")


def pull_request(repo, number, title, files):
    branch = "pr-%d" % number
    topic(repo, branch, files, title)
    return merge_pr(repo, number, title, branch)


def show(repo, sha, path):
    """The text of `path` at `sha`, unstripped."""
    done = subprocess.run(["git", "-C", repo, "show", "%s:%s" % (sha, path)], capture_output=True,
                          text=True, encoding="utf-8", check=True)
    return done.stdout


def checkout_of(repo, sha):
    """A folder holding the tree of `sha`, unpacked with git archive and tar."""
    folder = os.path.join(fresh(), "checkout")
    os.makedirs(folder)
    archive = subprocess.run(["git", "-C", repo, "archive", "--format=tar", sha], capture_output=True,
                             check=True).stdout
    subprocess.run(["tar", "-x", "-C", folder], input=archive, check=True)
    return folder


def changed(repo, sha, path):
    """The 1-based lines of `path` that `sha` adds against its first parent."""
    return mutate_shared.changed_lines(repo, "%s^1" % sha, sha, path)


def expected_mutants(repo, sha, path, lines=None):
    """The engine's own list of (label, text) for `path` at `sha`: the oracle a replay row is checked
    against. The engine has its own cases (hooks/test_mutate_js.py), so this only reads its output."""
    text = show(repo, sha, path)
    if path.endswith(".py"):
        return mutate_shared.ast_mutants(text, lines=lines)
    file = os.path.join(fresh(), os.path.basename(path))
    with open(file, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return mutate_shared.js_mutants(file, lines=lines)


def snapshot(repo):
    """What a replay must not change: the work tree, the worktree list and HEAD."""
    return (git(repo, "status", "--porcelain"), git(repo, "worktree", "list", "--porcelain"),
            git(repo, "rev-parse", "HEAD"))


JS_HEAD = "import { test } from 'node:test';\nimport assert from 'node:assert/strict';\n"

JS_PASS_SRC = "export function pass(score) {\n  return score >= 50;\n}\n"
JS_BAND_SRC = JS_PASS_SRC + ("\nexport function band(score) {\n  if (score >= 90) {\n    return 'A';\n  }\n"
                             "  return 'B';\n}\n")
JS_BAND_TEST_BASE = JS_HEAD + """
import { pass } from '../src/band.mjs';

test('pass at the threshold', () => {
  assert.equal(pass(50), true);
});
"""
JS_BAND_TEST = JS_HEAD + """
import { band, pass } from '../src/band.mjs';

test('pass at the threshold', () => {
  assert.equal(pass(50), true);
});

test('band grades at and around 90', () => {
  assert.equal(band(95), 'A');
  assert.equal(band(90), 'A');
  assert.equal(band(89), 'B');
});
"""
JS_LEGACY_RED = JS_HEAD + """
test('legacy expectation', () => {
  assert.equal(1 + 1, 3);
});
"""
JS_CLAMP_SRC = ("export function clamp(score) {\n  if (score > 100) {\n    return 100;\n  }\n"
                "  return score;\n}\n")
JS_CLAMP_TEST = JS_HEAD + """
import { clamp } from '../src/clamp.mjs';

test('clamp keeps a score in range', () => {
  assert.equal(clamp(50), 50);
});
"""
JS_FLAKY_SRC = "export function half(n) {\n  return n / 2;\n}\n"
JS_FLAKY_TEST = JS_HEAD + """
import { half } from '../src/flaky.mjs';

test('half of four is two', () => {
  assert.equal(half(4), 3);
});
"""
CONST_TEST = JS_HEAD + """
import { NAME } from '../src/const.mjs';

test('the name', () => {
  assert.equal(NAME, 'x');
});
"""
BROKEN_TEST = JS_HEAD + """
test('nothing imports the broken file', () => {
  assert.equal(1, 1);
});
"""
GATE_SRC = "export function gate(n) {\n  if (n > 1) {\n    return true;\n  }\n  return false;\n}\n"
GATE_TEST = JS_HEAD + """
import { gate } from '../src/gate.mjs';

test('gate opens above one', () => {
  assert.equal(gate(2), true);
  assert.equal(gate(0), false);
});
"""
DRAIN_SRC = ("export function drain(queue) {\n  while (queue.length > 0) {\n    queue.pop();\n  }\n"
             "  return queue;\n}\n")
# @LOG@ becomes a JSON string holding this fixture's pid log. A suite logs its own pid on load, so a
# case can check that a hung suite process is gone after the replay.
HANG_TEST = JS_HEAD + """import fs from 'node:fs';
import { drain } from '../src/drain.mjs';

fs.appendFileSync(@LOG@, process.pid + '\\n');

test('drain empties a queue', () => {
  assert.deepEqual(drain([1, 2]), []);
});

test('drain of an empty queue is empty', () => {
  assert.deepEqual(drain([]), []);
});
"""
TOOL_SRC = ("export const NAME = 'tool';\n\nexport function same(x) {\n  return x === 'tool';\n}\n")
# The checkout must have no docs folder (sparse_skip) and must see the install's marker through the
# linked deps folder. A red check here reads as an unusable suite, so the row is UNKNOWN.
TOOL_TEST = JS_HEAD + """import fs from 'node:fs';

test('the checkout leaves out docs', () => {
  assert.equal(fs.existsSync('docs'), false);
});

test('the deps folder is linked into the checkout', () => {
  assert.equal(fs.readFileSync('node_modules/marker.txt', 'utf8'), 'ok');
});
"""

PY_BAND_SRC = 'def band(score):\n    if score >= 90:\n        return "A"\n    return "B"\n'
PY_SUITE_HEAD = """import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
"""
PY_BAND_TEST = PY_SUITE_HEAD + """import band  # noqa: E402

failed = []


def check(name, got, want):
    if got != want:
        failed.append(name)
        print("FAIL: %s: got %r, want %r" % (name, got, want))


check("band 95", band.band(95), "A")
check("band 90", band.band(90), "A")
check("band 89", band.band(89), "B")
sys.exit(1 if failed else 0)
"""
PY_CLAMP_SRC = 'def clamp(score):\n    if score > 100:\n        return 100\n    return score\n'
PY_CLAMP_TEST = PY_SUITE_HEAD + """import clamp  # noqa: E402

failed = []


def check(name, got, want):
    if got != want:
        failed.append(name)
        print("FAIL: %s: got %r, want %r" % (name, got, want))


check("clamp 50", clamp.clamp(50), 50)
sys.exit(1 if failed else 0)
"""
# Importing this module raises unless MODE is strict. A mutant that flips the test throws on import:
# the suite dies with a traceback and no FAIL line, which is a crash, not a kill.
PY_MODE_SRC = 'MODE = "strict"\nif MODE != "strict":\n    raise RuntimeError("the gate is not strict")\n'
PY_MODE_TEST = PY_SUITE_HEAD + """import mode  # noqa: E402

sys.exit(0)
"""

JS_PROFILE = {"code": r"^src/.*\.mjs$", "tests": r"^test/.*\.test\.mjs$",
              "argv": ["node", "--test", "--test-reporter=tap", "{suite}"],
              "classify": "node_tap", "install": None, "sparse_skip": []}
PY_PROFILE = {"code": r"^lib/.*\.py$", "tests": r"^tests/test_.*\.py$",
              "argv": [sys.executable, "{suite}"], "classify": "fail_line", "install": None,
              "sparse_skip": []}
# The profile names the --replay CLI accepts in this suite. A fixture profile enters the module's
# REPLAY_PROFILES dict through the wrapper below; nothing in hooks/ is changed for a test.
CLI_PROFILES = {"fixture-js": JS_PROFILE, "fixture-py": PY_PROFILE}


def js_fixture():
    if "js" not in CACHE:
        repo = new_repo("js")
        put(repo, {"src/band.mjs": JS_PASS_SRC, "test/band.test.mjs": JS_BAND_TEST_BASE,
                   "test/legacy.test.mjs": JS_LEGACY_RED})
        commit(repo, "Base")
        shas = {1: pull_request(repo, 1, "Band grades",
                                {"src/band.mjs": JS_BAND_SRC, "test/band.test.mjs": JS_BAND_TEST}),
                2: pull_request(repo, 2, "Clamp scores",
                                {"src/clamp.mjs": JS_CLAMP_SRC, "test/clamp.test.mjs": JS_CLAMP_TEST}),
                3: pull_request(repo, 3, "Docs only", {"docs/notes.md": "# Notes\n\nDocs only.\n"}),
                4: pull_request(repo, 4, "Extra constant", {"src/extra.mjs": "export const VERSION = 'x';\n"}),
                5: pull_request(repo, 5, "Half with a wrong test",
                                {"src/flaky.mjs": JS_FLAKY_SRC, "test/flaky.test.mjs": JS_FLAKY_TEST})}
        CACHE["js"] = {"repo": repo, "sha": shas}
    return CACHE["js"]


def py_fixture():
    if "py" not in CACHE:
        repo = new_repo("py")
        put(repo, {"README.md": "base\n"})
        commit(repo, "Base")
        shas = {1: pull_request(repo, 1, "Band grades",
                                {"lib/band.py": PY_BAND_SRC, "tests/test_band.py": PY_BAND_TEST}),
                2: pull_request(repo, 2, "Clamp scores",
                                {"lib/clamp.py": PY_CLAMP_SRC, "tests/test_clamp.py": PY_CLAMP_TEST}),
                3: pull_request(repo, 3, "Strict mode",
                                {"lib/mode.py": PY_MODE_SRC, "tests/test_mode.py": PY_MODE_TEST})}
        CACHE["py"] = {"repo": repo, "sha": shas}
    return CACHE["py"]


def edge_fixture():
    if "edge" not in CACHE:
        repo = new_repo("edge")
        put(repo, {"README.md": "base\n", "test/old.test.mjs": JS_LEGACY_RED})
        commit(repo, "Base")
        shas = {1: pull_request(repo, 1, "No mutant",
                                {"src/const.mjs": "export const NAME = 'x';\n", "test/const.test.mjs": CONST_TEST}),
                2: pull_request(repo, 2, "Parse error",
                                {"src/broken.mjs": "export const x = ;\n", "test/broken.test.mjs": BROKEN_TEST}),
                3: pull_request(repo, 3, "Gate deletes a red suite",
                                {"src/gate.mjs": GATE_SRC, "test/gate.test.mjs": GATE_TEST,
                                 "test/old.test.mjs": None})}
        CACHE["edge"] = {"repo": repo, "sha": shas}
    return CACHE["edge"]


def merges_fixture():
    """Main holds: PR 1, a merge of a side branch (not a PR), and PR 2 whose branch carries a merge
    titled as PR 9 (a second parent, so it is not on main's first-parent line), then PR 3 and PR 4."""
    if "merges" not in CACHE:
        repo = new_repo("merges")
        put(repo, {"README.md": "base\n"})
        commit(repo, "Base")
        shas = {1: pull_request(repo, 1, "First change", {"a.txt": "a\n"})}
        topic(repo, "side", {"side.txt": "s\n"}, "Side work")
        git(repo, "merge", "-q", "--no-ff", "-m", "Merge branch 'side'", "side")
        topic(repo, "inner", {"c.txt": "c\n"}, "Inner work")
        topic(repo, "pr-2", {"b.txt": "b\n"}, "Second work")
        git(repo, "checkout", "-q", "pr-2")
        git(repo, "merge", "-q", "--no-ff", "-m", "Merge pull request #9 from fixture/inner", "inner")
        shas[2] = merge_pr(repo, 2, "Second change", "pr-2")
        shas[3] = pull_request(repo, 3, "Third change", {"d.txt": "d\n"})
        shas[4] = pull_request(repo, 4, "Fourth #999 won't `break`", {"e.txt": "e\n"})
        CACHE["merges"] = {"repo": repo, "sha": shas}
    return CACHE["merges"]


def hang_fixture():
    """A repository whose one PR has a mutant that loops forever, and the log its suite writes its pid to."""
    log = os.path.join(fresh(), "pids.log")
    repo = new_repo("hang")
    put(repo, {"README.md": "base\n"})
    commit(repo, "Base")
    suite = HANG_TEST.replace("@LOG@", json.dumps(log))
    sha = pull_request(repo, 1, "Drain a queue", {"src/drain.mjs": DRAIN_SRC, "test/drain.test.mjs": suite})
    return repo, sha, log


def tool_fixture():
    repo = new_repo("tool")
    put(repo, {"src/tool.mjs": "export const NAME = 'tool';\n", "docs/big.md": "# big\n",
               "package-lock.json": '{"lock": 1}\n'})
    commit(repo, "Base")
    sha = pull_request(repo, 1, "Tool checks", {"src/tool.mjs": TOOL_SRC, "test/tool.test.mjs": TOOL_TEST})
    return repo, sha


LATIN_NAME_SRC = b"export const NAME = 'caf\xe9';\n"  # latin-1 e-acute: not UTF-8, so no text decodes it
NAME_TEST = JS_HEAD + """import { NAME } from '../src/name.mjs';

test('the name is a string', () => {
  assert.equal(typeof NAME, 'string');
});
"""


def bytes_fixture():
    """PR 1 is a clean clamp change. PR 2, merged after it, adds a product file that is not UTF-8."""
    if "bytes" not in CACHE:
        repo = new_repo("bytes")
        put(repo, {"README.md": "base\n"})
        commit(repo, "Base")
        shas = {1: pull_request(repo, 1, "Clamp scores",
                                {"src/clamp.mjs": JS_CLAMP_SRC, "test/clamp.test.mjs": JS_CLAMP_TEST}),
                2: pull_request(repo, 2, "Latin name",
                                {"src/name.mjs": LATIN_NAME_SRC, "test/name.test.mjs": NAME_TEST})}
        CACHE["bytes"] = {"repo": repo, "sha": shas}
    return CACHE["bytes"]


# A fixture shaped like banchi's harness: harness/tests with Result (a NamedTuple with a bool `passed`),
# isolated_home, and one module that the banchi runner reads as a suite.
BANCHI_SUITE = "harness/tests/t1_x.py"
BANCHI_INIT = '''"""Shared types for the test modules. A fixture shaped like banchi's harness/tests/__init__.py."""

from typing import NamedTuple


class Result(NamedTuple):
    passed: bool
    detail: str = ""


class NotImplementedYet(Exception):
    """Raised by a stub. The runner reports it as a failure, never as a skip."""
'''
BANCHI_HOME = '''import contextlib
from pathlib import Path


@contextlib.contextmanager
def isolated_home(root=None):
    """A stand-in for banchi's isolated_home: a folder under the cwd, yielded as a Path."""
    home = Path(root or Path.cwd()) / "home"
    home.mkdir(parents=True, exist_ok=True)
    yield home
'''
BANCHI_GREEN = "from harness.tests import Result\n\n\ndef run():\n    return Result(True, 'all checks passed')\n"
BANCHI_RED = "from harness.tests import Result\n\n\ndef run():\n    return Result(False, 'the band is wrong')\n"
BANCHI_RAISE = "def run():\n    raise RuntimeError('boom')\n"
BANCHI_NONE = "def run():\n    return None\n"
BANCHI_METHOD = ("class Odd:\n    detail = 'odd'\n\n    def passed(self):\n        return True\n\n\n"
                 "def run():\n    return Odd()\n")


def banchi_part():
    """The banchi per-module runner's profile part, as hooks/mutate_guard.py names it."""
    try:
        return mutate_guard.REPLAY_PROFILES["banchi"]["parts"]["py"]
    except (KeyError, TypeError):
        raise AssertionError("REPLAY_PROFILES has no banchi py part")


def banchi_suite(module_text):
    """A tree shaped like banchi's harness, with one module at BANCHI_SUITE. Returns (folder, argv): argv is
    the profile's own runner command, with the suite path filled in and the test's interpreter in place of
    the install's venv."""
    folder = os.path.join(fresh(), "banchi")
    put(folder, {"harness/tests/__init__.py": BANCHI_INIT, "harness/tests/home.py": BANCHI_HOME,
                 BANCHI_SUITE: module_text})
    argv = [sys.executable if piece == "{deps}/venv/bin/python" else piece.replace("{suite}", BANCHI_SUITE)
            for piece in banchi_part()["argv"]]
    return folder, argv


def install_argv(counter):
    """A stand-in install: it makes node_modules/marker.txt in its folder and counts each run in `counter`."""
    source = ("import os\n"
              "os.makedirs('node_modules', exist_ok=True)\n"
              "open(os.path.join('node_modules', 'marker.txt'), 'w').write('ok')\n"
              "open(%r, 'a').write('x')\n" % counter)
    return [sys.executable, "-c", source]


def replay(repo, sha, profile, limit=50, seed=0, suite_timeout=60, jobs=2):
    return api("replay_pr")(repo, sha, profile, limit=limit, seed=seed, suite_timeout=suite_timeout, jobs=jobs)


def replay_no_raise(repo, sha, profile, **options):
    """replay() with a raise reported as a FAIL line, not an ERROR, as the other cases report a contract miss."""
    try:
        return replay(repo, sha, profile, **options)
    except Exception as error:
        raise AssertionError("the replay raised %s: %s" % (type(error).__name__, error))


def js_rows():
    fixture = js_fixture()
    if "js_rows" not in CACHE:
        CACHE["js_rows"] = {n: replay(fixture["repo"], fixture["sha"][n], JS_PROFILE) for n in range(1, 6)}
    return CACHE["js_rows"]


def py_rows():
    fixture = py_fixture()
    if "py_rows" not in CACHE:
        CACHE["py_rows"] = {n: replay(fixture["repo"], fixture["sha"][n], PY_PROFILE) for n in range(1, 4)}
    return CACHE["py_rows"]


def edge_rows():
    fixture = edge_fixture()
    if "edge_rows" not in CACHE:
        CACHE["edge_rows"] = {n: replay(fixture["repo"], fixture["sha"][n], JS_PROFILE) for n in range(1, 4)}
    return CACHE["edge_rows"]


def survivor_set(row):
    return {tuple(item) for item in row["survivors"]}


# ---------------------------------------------------------------------------------------------------
# Process and temp helpers for the cost checks.

def live_pids():
    """Pid -> parent pid for each process that is not a zombie. The `ps` run itself is left out."""
    done = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,stat=,comm="], capture_output=True, text=True)
    if done.returncode != 0:
        raise AssertionError("cannot list processes: %s" % done.stderr.strip())
    table = {}
    for line in done.stdout.splitlines():
        fields = line.split(None, 3)
        if len(fields) < 3 or fields[2].startswith("Z"):
            continue
        if len(fields) == 4 and fields[3].strip() == "ps":
            continue
        table[int(fields[0])] = int(fields[1])
    return table


def descendants():
    """The live processes this test process started, directly or through others."""
    table = live_pids()
    found, frontier = set(), [os.getpid()]
    while frontier:
        parent = frontier.pop()
        for pid, ppid in table.items():
            if ppid == parent and pid not in found:
                found.add(pid)
                frontier.append(pid)
    return found


def pids_in(log):
    if not os.path.exists(log):
        return []
    with open(log, encoding="utf-8") as handle:
        return [int(text) for text in handle.read().split()]


@contextlib.contextmanager
def temp_under(folder):
    """Point this process's temp folder, and the TMPDIR of its children, at `folder`. A leftover shows in it."""
    keys = ("TMPDIR", "TEMP", "TMP")
    saved_env = {key: os.environ.get(key) for key in keys}
    saved_dir = tempfile.tempdir
    os.makedirs(folder, exist_ok=True)
    tempfile.tempdir = folder
    for key in keys:
        os.environ[key] = folder
    try:
        yield folder
    finally:
        tempfile.tempdir = saved_dir
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


WRAPPER = """\
import json
import sys

sys.path.insert(0, @HOOKS@)
import mutate_guard  # noqa: E402

profiles = json.load(open(sys.argv[1], encoding="utf-8"))
if not hasattr(mutate_guard, "REPLAY_PROFILES"):
    print("ERROR mutate_guard has no REPLAY_PROFILES")
    sys.exit(2)
mutate_guard.REPLAY_PROFILES.update(profiles)
mutate_guard.MUTATIONS = []  # the replay cases must not run the hand-written guard mutants
sys.argv = ["mutate_guard.py"] + sys.argv[2:]
sys.exit(mutate_guard.main())
"""


def cli_wrapper():
    """A child Python that registers the fixture profiles, then runs hooks/mutate_guard.py's main()."""
    path = os.path.join(RUN, "run_replay_cli.py")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(WRAPPER.replace("@HOOKS@", repr(HERE)))
    return path


def run_cli(args):
    """`hooks/mutate_guard.py <args>` in a child Python, with the fixture profiles registered.
    Returns (exit code, stdout, stderr). A run past five minutes is a FAIL."""
    spec = os.path.join(fresh(), "profiles.json")
    with open(spec, "w", encoding="utf-8") as handle:
        json.dump(CLI_PROFILES, handle)
    try:
        done = subprocess.run([sys.executable, cli_wrapper(), spec] + args, capture_output=True,
                              text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise AssertionError("the --replay run passed 300 s")
    return done.returncode, done.stdout, done.stderr


def run_node_suite(folder, rel):
    return subprocess.run(["node", "--test", "--test-reporter=tap", rel], cwd=folder, capture_output=True,
                          text=True, timeout=120)


# ---------------------------------------------------------------------------------------------------

class MergedPrsTests(unittest.TestCase):

    def test_lists_pull_request_merges_newest_first_with_number_and_title(self):
        fixture = merges_fixture()
        rows = [tuple(item) for item in api("merged_prs")(fixture["repo"], "main", 10)]
        shas = fixture["sha"]
        self.assertEqual(rows, [(shas[4], 4, "Fourth #999 won't `break`"), (shas[3], 3, "Third change"),
                                (shas[2], 2, "Second change"), (shas[1], 1, "First change")])

    def test_a_merge_that_is_not_a_pull_request_is_left_out(self):
        fixture = merges_fixture()
        rows = api("merged_prs")(fixture["repo"], "main", 10)
        self.assertEqual({item[0] for item in rows}, set(fixture["sha"].values()),
                         "the side-branch merge has no PR number and must not be listed")

    def test_a_pull_request_merge_inside_a_branch_is_left_out(self):
        fixture = merges_fixture()
        numbers = [item[1] for item in api("merged_prs")(fixture["repo"], "main", 10)]
        self.assertNotIn(9, numbers, "PR 9 is a second parent of PR 2, not on main's first-parent line")

    def test_count_keeps_only_the_newest_merges(self):
        fixture = merges_fixture()
        rows = [tuple(item) for item in api("merged_prs")(fixture["repo"], "main", 2)]
        self.assertEqual(rows, [(fixture["sha"][4], 4, "Fourth #999 won't `break`"),
                                (fixture["sha"][3], 3, "Third change")])

    def test_the_number_is_an_int_and_a_hash_in_the_title_does_not_change_it(self):
        fixture = merges_fixture()
        number = api("merged_prs")(fixture["repo"], "main", 1)[0][1]
        self.assertIsInstance(number, int)
        self.assertEqual(number, 4)


class ReplayJsTests(unittest.TestCase):

    def test_strong_pr_kills_every_mutant(self):
        row = js_rows()[1]
        self.assertEqual(row["status"], "OK")
        self.assertGreater(row["made"], 0)
        self.assertEqual(row["killed"], row["made"])
        self.assertEqual((row["crashed"], row["survived"], survivor_set(row)), (0, 0, set()))
        self.assertEqual(row["unusable"], {}, "the legacy suite is not in this PR, so it must not run")

    def test_the_row_names_its_pr_sha_and_title(self):
        fixture = js_fixture()
        row = js_rows()[1]
        self.assertEqual((row["pr"], row["sha"], row["title"]), (1, fixture["sha"][1], "Band grades"))

    def test_weak_pr_lists_each_survivor_by_path_line_and_label(self):
        fixture = js_fixture()
        repo, sha, path = fixture["repo"], fixture["sha"][2], "src/clamp.mjs"
        ret = unique_line(show(repo, sha, path), "    return 100;")
        want = {(path, ret, label) for label, _ in expected_mutants(repo, sha, path, lines={ret})}
        self.assertEqual(len(want), 2, "two mutants sit on the return line")
        row = js_rows()[2]
        self.assertEqual(row["status"], "OK")
        self.assertEqual(survivor_set(row), want)
        self.assertEqual(row["survived"], len(want))
        self.assertEqual(row["killed"] + row["crashed"] + row["survived"], row["made"])

    def test_docs_only_pr_is_no_product(self):
        self.assertEqual(js_rows()[3]["status"], "NO_PRODUCT")

    def test_code_with_no_test_change_is_no_tests(self):
        self.assertEqual(js_rows()[4]["status"], "NO_TESTS")

    def test_a_suite_red_on_the_clean_source_is_unusable_and_the_row_unknown(self):
        row = js_rows()[5]
        self.assertEqual(row["status"], "UNKNOWN")
        self.assertIn("clean", row["reason"])
        self.assertIn("test/flaky.test.mjs", row["unusable"])

    def test_mutants_come_only_from_the_lines_the_pr_added(self):
        fixture = js_fixture()
        repo, sha, path = fixture["repo"], fixture["sha"][1], "src/band.mjs"
        added = expected_mutants(repo, sha, path, lines=changed(repo, sha, path))
        everything = expected_mutants(repo, sha, path)
        self.assertLess(len(added), len(everything), "the file has sites outside the PR's lines")
        self.assertEqual(js_rows()[1]["made"], len(added))

    def test_limit_caps_the_mutants_made(self):
        fixture = js_fixture()
        row = replay(fixture["repo"], fixture["sha"][1], JS_PROFILE, limit=2)
        self.assertEqual((row["made"], row["killed"]), (2, 2))

    def test_the_same_seed_gives_the_same_row_at_any_job_count(self):
        fixture = js_fixture()
        one = replay(fixture["repo"], fixture["sha"][2], JS_PROFILE, limit=3, seed=7, jobs=1)
        many = replay(fixture["repo"], fixture["sha"][2], JS_PROFILE, limit=3, seed=7, jobs=3)
        self.assertEqual(one["made"], 3)
        self.assertEqual(one, many)


class ProfileTests(unittest.TestCase):

    def test_the_code_regex_decides_which_files_are_product(self):
        fixture = js_fixture()
        row = replay(fixture["repo"], fixture["sha"][1], dict(JS_PROFILE, code=r"^nothing/"))
        self.assertEqual(row["status"], "NO_PRODUCT")

    def test_the_tests_regex_decides_which_files_are_suites(self):
        fixture = js_fixture()
        row = replay(fixture["repo"], fixture["sha"][1], dict(JS_PROFILE, tests=r"^nothing/"))
        self.assertEqual(row["status"], "NO_TESTS")


class EdgeTests(unittest.TestCase):

    def test_a_pr_with_no_mutant_on_its_lines_is_unknown(self):
        row = edge_rows()[1]
        self.assertEqual(row["status"], "UNKNOWN")
        self.assertIn("mutant", row["reason"])

    def test_a_parse_error_is_unknown(self):
        row = edge_rows()[2]
        self.assertEqual(row["status"], "UNKNOWN")
        self.assertIn("parse", row["reason"].lower())

    def test_a_suite_the_pr_deleted_is_not_run(self):
        row = edge_rows()[3]
        self.assertEqual(row["status"], "OK")
        self.assertNotIn("test/old.test.mjs", row["unusable"])


class HangTests(unittest.TestCase):

    def test_a_crash_and_a_hang_are_not_kills(self):
        repo, sha, _log = hang_fixture()
        row = replay(repo, sha, JS_PROFILE, suite_timeout=5)
        self.assertEqual(row["status"], "OK")
        self.assertEqual((row["made"], row["killed"], row["crashed"], row["survived"]), (4, 2, 2, 0))


class ToolTests(unittest.TestCase):

    def test_sparse_skip_and_install_shape_the_checkout_once_per_replay(self):
        counter = os.path.join(fresh(), "installs.txt")
        repo, sha = tool_fixture()
        row = replay(repo, sha, dict(JS_PROFILE, sparse_skip=["docs"], install=install_argv(counter)))
        self.assertEqual(row["status"], "OK", row.get("reason", ""))
        self.assertGreaterEqual(row["made"], 2, "the install must serve more than one checkout")
        self.assertTrue(os.path.exists(counter), "the install did not run")
        with open(counter, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "x", "the install must run once for this replay, not once per checkout")


class PythonReplayTests(unittest.TestCase):

    def test_strong_python_pr_kills_every_mutant(self):
        fixture = py_fixture()
        repo, sha, path = fixture["repo"], fixture["sha"][1], "lib/band.py"
        want = expected_mutants(repo, sha, path, lines=changed(repo, sha, path))
        row = py_rows()[1]
        self.assertEqual(row["status"], "OK")
        self.assertEqual((row["made"], row["killed"], row["survived"], row["crashed"]),
                         (len(want), len(want), 0, 0))

    def test_weak_python_pr_lists_each_survivor(self):
        fixture = py_fixture()
        repo, sha, path = fixture["repo"], fixture["sha"][2], "lib/clamp.py"
        ret = unique_line(show(repo, sha, path), "        return 100")
        want = {(path, ret, label) for label, _ in expected_mutants(repo, sha, path, lines={ret})}
        self.assertEqual(len(want), 2, "two mutants sit on the return line")
        row = py_rows()[2]
        self.assertEqual(row["status"], "OK")
        self.assertEqual(survivor_set(row), want)

    def test_a_suite_that_throws_on_import_is_crashed_not_killed(self):
        row = py_rows()[3]
        self.assertEqual(row["status"], "OK")
        self.assertGreater(row["made"], 0)
        self.assertEqual((row["killed"], row["crashed"], row["survived"]), (0, row["made"], 0))


def fake_row(**changes):
    row = {"pr": 7, "sha": "a" * 40, "title": "Fake", "status": "OK", "reason": "", "made": 5,
           "killed": 4, "crashed": 1, "survived": 0, "survivors": [], "unusable": {}}
    row.update(changes)
    return row


class FormatTests(unittest.TestCase):

    def test_one_line_per_pr_with_its_status_and_counts(self):
        rows = [fake_row(pr=7), fake_row(pr=8, status="NO_TESTS", made=0, killed=0, crashed=0, survived=0)]
        lines = api("format_replay")(rows).split("\n")
        ok = [line for line in lines if "OK" in line]
        no_tests = [line for line in lines if "NO_TESTS" in line]
        self.assertEqual((len(ok), len(no_tests)), (1, 1))
        self.assertTrue({"5", "4", "1", "0"} <= set(re.findall(r"\d+", ok[0])), ok[0])

    def test_each_survivor_is_one_line_pr_path_line_label(self):
        rows = [fake_row(pr=7, survivors=[("src/a.mjs", 12, "L12 compare === -> !==")], killed=4,
                         crashed=0, survived=1)]
        lines = [line.strip() for line in api("format_replay")(rows).split("\n")]
        self.assertIn("#7 src/a.mjs:12 L12 compare === -> !==", lines)

    def test_an_unknown_row_shows_its_reason_and_no_rate(self):
        row = fake_row(status="UNKNOWN", reason="no suite green on clean", made=0, killed=0, crashed=0,
                       survived=0)
        text = api("format_replay")([row])
        unknown = [line for line in text.split("\n") if "UNKNOWN" in line]
        self.assertEqual(len(unknown), 1)
        self.assertIn("no suite green on clean", unknown[0])
        self.assertNotIn("%", text, "UNKNOWN never reads as a rate")
        self.assertNotIn("OK", text, "UNKNOWN never reads as green")


class CliTests(unittest.TestCase):

    def test_replay_prints_each_row_then_the_table_and_exits_0_whatever_the_scores(self):
        code, out, err = run_cli(["--replay", js_fixture()["repo"], "--profile", "fixture-js", "--prs", "5",
                                  "--limit", "50", "--suite-timeout", "60", "--jobs", "2"])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        rows = js_rows()
        order = [5, 4, 3, 2, 1]
        table = api("format_replay")([rows[n] for n in order]).rstrip()
        end = out.rstrip().rfind(table)
        self.assertTrue(table and end > 0, "the table is not the last thing printed")
        head = out[:end]
        for n in order:
            self.assertIn(rows[n]["status"], head, "no row printed for PR %d before the table" % n)


class CostTests(unittest.TestCase):

    def test_a_replay_leaves_the_repository_as_it_was(self):
        fixture = js_fixture()
        before = snapshot(fixture["repo"])
        replay(fixture["repo"], fixture["sha"][2], JS_PROFILE, limit=5)
        self.assertEqual(snapshot(fixture["repo"]), before)

    def test_a_replay_removes_every_temp_folder_it_made(self):
        fixture = js_fixture()
        with temp_under(fresh()) as folder:
            replay(fixture["repo"], fixture["sha"][2], JS_PROFILE, limit=5)
        self.assertEqual(os.listdir(folder), [])

    def test_a_replay_that_hangs_leaves_no_child_process_alive(self):
        repo, sha, log = hang_fixture()
        before = descendants()
        replay(repo, sha, JS_PROFILE, suite_timeout=5)
        self.assertEqual(descendants() - before, set(), "a child process the replay started is alive")
        pids = pids_in(log)
        self.assertTrue(pids, "no suite ran, so the check proves nothing")
        alive = live_pids()
        self.assertEqual([pid for pid in pids if pid in alive], [], "a logged suite process is alive")

    def test_the_cli_run_leaves_the_repository_temp_folders_and_processes_as_they_were(self):
        fixture = js_fixture()
        before, procs = snapshot(fixture["repo"]), descendants()
        with temp_under(fresh()) as folder:
            code, out, err = run_cli(["--replay", fixture["repo"], "--profile", "fixture-js", "--prs", "5",
                                      "--limit", "50", "--suite-timeout", "60", "--jobs", "2"])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertEqual(snapshot(fixture["repo"]), before)
        self.assertEqual(os.listdir(folder), [])
        self.assertEqual(descendants() - procs, set())


# Playwright output in the shape `playwright test` prints on a non-terminal: a failure block headed by its
# number, its title and a rule of box-drawing dashes, then the error text, then the source frame of the line
# that stood when the error was thrown. The frame quotes `expect(page)` in each red case below.
PW_HEADER = "  1) [chromium] › unit/nav.unit.ts:6:5 › nav › keeps the url " + "─" * 30 + "\n"
PW_FRAME = ("      5 | test.describe('nav', () => {\n"
            "    > 6 |   await expect(page).toHaveURL('/x');\n"
            "        |                      ^\n"
            "      7 | });\n\n")
PW_SUMMARY = "  1 failed\n    [chromium] › unit/nav.unit.ts:6:5 › nav › keeps the url\n"
PW_CLOSED = ("Running 1 test using 1 worker\n\n" + PW_HEADER + "\n"
             "    Error: Target page, context or browser has been closed\n\n" + PW_FRAME + PW_SUMMARY)
PW_TIMEOUT = ("Running 1 test using 1 worker\n\n" + PW_HEADER + "\n"
              "    Test timeout of 30000ms exceeded.\n\n" + PW_FRAME + PW_SUMMARY)
PW_PAGE_MATCHER = ("Running 1 test using 1 worker\n\n" + PW_HEADER + "\n"
                   "    Error: expect(page).toHaveURL(expected) failed\n\n"
                   "    Expected pattern: /x/\n"
                   "    Received string:  \"http://127.0.0.1:3000/\"\n"
                   "    Timeout: 5000ms\n\n" + PW_FRAME + PW_SUMMARY)
PW_RECEIVED = ("Running 1 test using 1 worker\n\n"
               "  1) [chromium] › unit/band.unit.ts:4:5 › band › grades " + "─" * 30 + "\n\n"
               "    Error: expect(received).toBe(expected) // Object.is equality\n\n"
               "    Expected: \"A\"\n"
               "    Received: \"B\"\n\n"
               "      3 | test('grades', () => {\n"
               "    > 4 |   expect(band(95)).toBe('A');\n"
               "        |                    ^\n"
               "      5 | });\n\n"
               "  1 failed\n    [chromium] › unit/band.unit.ts:4:5 › band › grades\n")
PW_PASS = "Running 1 test using 1 worker\n\n  1 passed (1.2s)\n"


class PlaywrightClassifyTests(unittest.TestCase):
    """classify_playwright reads the error text of a failure block. The source frame shows where the run
    stood, not what went wrong, so a frame that quotes `expect(page)` is no evidence of an assertion."""

    def test_a_closed_target_under_an_expect_frame_is_a_crash(self):
        self.assertEqual(api("classify_playwright")(1, PW_CLOSED, False), "crash")

    def test_a_test_timeout_under_an_expect_frame_is_not_a_kill(self):
        self.assertIn(api("classify_playwright")(1, PW_TIMEOUT, False), ("crash", "timeout"))

    def test_a_received_expected_failure_is_an_assert(self):
        self.assertEqual(api("classify_playwright")(1, PW_RECEIVED, False), "assert")

    def test_a_failed_page_matcher_is_an_assert(self):
        self.assertEqual(api("classify_playwright")(1, PW_PAGE_MATCHER, False), "assert")

    def test_a_pass_is_a_pass(self):
        self.assertEqual(api("classify_playwright")(0, PW_PASS, False), "pass")


class BanchiRunnerTests(unittest.TestCase):
    """The banchi per-module runner (REPLAY_PROFILES banchi, py part): a module's Result sets its class."""

    def kind(self, module_text):
        folder, argv = banchi_suite(module_text)
        classify = mutate_shared.CLASSIFIERS[banchi_part()["classify"]]
        return mutate_shared.run_suite_file(folder, BANCHI_SUITE, 60, argv=argv, classify=classify)[0]

    def test_a_passed_result_reads_green(self):
        self.assertEqual(self.kind(BANCHI_GREEN), "pass")

    def test_a_failed_result_prints_a_fail_line_exits_1_and_is_an_assert(self):
        folder, argv = banchi_suite(BANCHI_RED)
        done = subprocess.run(argv, cwd=folder, capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertTrue(any(line.startswith("FAIL: harness.tests.t1_x") for line in done.stdout.splitlines()),
                        done.stdout)
        self.assertEqual(self.kind(BANCHI_RED), "assert")

    def test_a_raise_is_a_crash(self):
        self.assertEqual(self.kind(BANCHI_RAISE), "crash")

    def test_a_none_result_is_a_crash(self):
        self.assertEqual(self.kind(BANCHI_NONE), "crash")

    def test_a_passed_that_is_a_method_does_not_read_green(self):
        self.assertEqual(self.kind(BANCHI_METHOD), "crash")


class NonUtf8Tests(unittest.TestCase):
    """A product file that is not UTF-8 gives its pull request an UNKNOWN row with a reason, and the pull
    requests replayed after it still get their rows."""

    def test_a_non_utf8_product_file_gives_its_pr_an_unknown_row_with_a_reason(self):
        fixture = bytes_fixture()
        row = replay_no_raise(fixture["repo"], fixture["sha"][2], JS_PROFILE)
        self.assertEqual(row["status"], "UNKNOWN")
        self.assertTrue(row["reason"].strip(), "an UNKNOWN row needs a reason")

    def test_the_prs_after_a_non_utf8_one_still_get_rows(self):
        fixture = bytes_fixture()
        code, out, err = run_cli(["--replay", fixture["repo"], "--profile", "fixture-js", "--prs", "2",
                                  "--limit", "50", "--suite-timeout", "60", "--jobs", "2"])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertRegex(out, r"#2 UNKNOWN")
        self.assertRegex(out, r"#1 OK")


class InstallTimeoutTests(unittest.TestCase):
    """An install that times out leaves no process of its own alive, its grandchildren included."""

    def test_an_install_that_times_out_leaves_no_process_alive(self):
        repo, sha = tool_fixture()
        real = shutil.which("sleep")
        self.assertIsNotNone(real, "no sleep on PATH")
        bin_dir, log = fresh(), os.path.join(fresh(), "sleeps.log")
        # A shim on PATH logs the pid of each sleep, then execs the real one, so the pid is the sleep's own.
        shim = os.path.join(bin_dir, "sleep")
        with open(shim, "w", encoding="utf-8", newline="\n") as handle:
            handle.write('#!/bin/sh\necho $$ >> "$SLEEP_LOG"\nexec "%s" "$@"\n' % real)
        os.chmod(shim, 0o755)
        profile = dict(JS_PROFILE, install=["sh", "-c", "sleep 30 & sleep 30"], lockfile="package-lock.json")
        env = {"PATH": bin_dir + os.pathsep + os.environ.get("PATH", ""), "SLEEP_LOG": log}
        try:
            with mock.patch.dict(os.environ, env), mock.patch.object(mutate_shared, "INSTALL_TIMEOUT", 1):
                row = replay_no_raise(repo, sha, profile, suite_timeout=5)
            self.assertEqual(row["status"], "UNKNOWN", row["reason"])
            pids = pids_in(log)
            self.assertTrue(pids, "no install sleep ran, so the check proves nothing")
            alive = live_pids()
            self.assertEqual([pid for pid in pids if pid in alive], [], "an install process is alive")
        finally:
            for pid in pids_in(log):
                if pid in live_pids():
                    try:
                        os.kill(pid, signal.SIGKILL)  # only the pids this case logged
                    except OSError:
                        pass


class FixtureSanityTests(unittest.TestCase):
    """Cases that hold on the engine branch too: they check the fixtures, not the replay."""

    def test_the_band_suite_is_green_on_its_pr_checkout(self):
        fixture = js_fixture()
        run = run_node_suite(checkout_of(fixture["repo"], fixture["sha"][1]), "test/band.test.mjs")
        self.assertEqual(run.returncode, 0, run.stdout[-1500:] + run.stderr[-1500:])

    def test_the_clamp_suite_is_green_on_its_pr_checkout(self):
        fixture = js_fixture()
        run = run_node_suite(checkout_of(fixture["repo"], fixture["sha"][2]), "test/clamp.test.mjs")
        self.assertEqual(run.returncode, 0, run.stdout[-1500:] + run.stderr[-1500:])

    def test_the_flaky_suite_is_red_on_its_pr_checkout(self):
        fixture = js_fixture()
        run = run_node_suite(checkout_of(fixture["repo"], fixture["sha"][5]), "test/flaky.test.mjs")
        self.assertNotEqual(run.returncode, 0)

    def test_the_python_band_and_mode_suites_are_green_on_their_pr_checkouts(self):
        fixture = py_fixture()
        for number, rel in ((1, "tests/test_band.py"), (3, "tests/test_mode.py")):
            folder = checkout_of(fixture["repo"], fixture["sha"][number])
            done = subprocess.run([sys.executable, rel], cwd=folder, capture_output=True, text=True, timeout=120)
            self.assertEqual(done.returncode, 0, "%s: %s" % (rel, done.stdout + done.stderr))

    def test_the_merges_fixture_puts_its_pull_requests_on_main_in_order(self):
        fixture = merges_fixture()
        subjects = git(fixture["repo"], "log", "--first-parent", "--merges", "--format=%s", "main").split("\n")
        self.assertEqual(subjects, ["Merge pull request #4 from fixture/pr-4",
                                    "Merge pull request #3 from fixture/pr-3",
                                    "Merge pull request #2 from fixture/pr-2",
                                    "Merge branch 'side'",
                                    "Merge pull request #1 from fixture/pr-1"])


if __name__ == "__main__":
    unittest.main()
