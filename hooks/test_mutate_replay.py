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
- a mutant that a suite kills is not run on the suites after it, and a mutant that suite misses is;
- each finished mutant prints one line before its pull request's row, so a long pull request shows progress;
- a profile's `select` gives the suites to run against each product file's mutants, and a failed select falls
  back to every changed suite, with a note in the row;
- a `pr_budget` leaves the mutants not started past it as `not_run`, never as a kill, a survivor or a crash;
- a replay leaves the repository, the temp folders and the child processes as it found them;
- a banchi pull request that changes a T7 group module, harness/tests/t7/<group>.py, is scored by that group's own
  checks, in T7's order and setup, and by no other group's; a changed helper with no CHECKS is no suite; a group
  with no checks reads unusable, never green; a check that raises is a crash, never a kill; a tN module and the
  whole t7_store_and_seams.py still score whole;
- a file the real q_max or banchi profile does not read as product (a `*.test.mjs` browser test, a
  `scripts/*-selftest.py`) is never mutated: a pull request that changes only such files and a suite reads NO_PRODUCT,
  and a product file beside them still reads OK;
- a child repository's profile (REPLAY_PROFILES mailaudit, home, ios_adblock, joyous, degen) names its sample product
  file and suite, uses only the keys the claude_settings, q_max and banchi profiles use, and reads no suite as product.

The JavaScript cases need the typescript package: `npm ci --ignore-scripts --no-audit --no-fund` at the
repository root. A missing package is a FAIL, never a skip. A contract name missing from
hooks/mutate_shared.py is a FAIL line, so the red run reads as a list of FAIL lines, not ERROR lines.

The git and line helpers come from hooks/test_mutate_js.py, the one home of them. Temp files live in
the run folder of lint/_test_temp.py. The sweep of old run folders is proven once, in
hooks/test_mutate_js.py (TempRunFolderTests).

Process checks use `ps` and so run on POSIX only, as the CI step does (ubuntu-latest).
"""
import contextlib
import inspect
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
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
CHECK_SRC = "export function gate(n) {\n  if (n > 1) {\n    return true;\n  }\n  return false;\n}\n"
GRADE_SRC = "export function grade(n) {\n  if (n >= 60) {\n    return 'P';\n  }\n  return 'F';\n}\n"
GRADE_TEST = JS_HEAD + """
import { grade } from '../src/grade.mjs';

test('grade passes at sixty', () => {
  assert.equal(grade(60), 'P');
  assert.equal(grade(59), 'F');
});
"""
CHECK_TEST = JS_HEAD + """
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
                                {"src/gate.mjs": CHECK_SRC, "test/gate.test.mjs": CHECK_TEST,
                                 "test/old.test.mjs": None}),
                4: pull_request(repo, 4, "Grade with a file that does not parse",
                                {"src/grade.mjs": GRADE_SRC, "test/grade.test.mjs": GRADE_TEST,
                                 "src/broken-late.mjs": "export const x = ;\n"})}
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


# The early-stop and progress cases replay one band pull request. The base holds `pass`, so the pull request
# adds only the band function, and every mutant sits on a line it added.
JS_PASS_ONLY_TEST = JS_HEAD + """import { pass } from '../src/band.mjs';

test('pass at 60', () => {
  assert.equal(pass(60), true);
});
"""
def wait_head(ms):
    """A statement that holds the suite's thread for `ms` milliseconds, so each run of it takes that long."""
    return "Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, %d);\n" % ms


def sleeping_suite(text, ms):
    """`text` with each run held for `ms` milliseconds."""
    return text.replace(JS_HEAD, JS_HEAD + wait_head(ms), 1)


def counting_suite(text, log, wait_ms=1000):
    """`text` with a run counter: each run appends an x to `log`. The wait makes it the slower suite by default,
    so the quickest-first order runs the other suite first."""
    head = "import fs from 'node:fs';\n" + wait_head(wait_ms) + "fs.appendFileSync(%s, 'x');\n" % json.dumps(log)
    return text.replace(JS_HEAD, JS_HEAD + head, 1)


def band_pr(name, number, suites):
    """A repository whose one merged pull request, `number`, adds the band function to src/band.mjs and the
    suites, {path: text}. Built once per `name`. Returns (repo, sha)."""
    key = "band-" + name
    if key not in CACHE:
        repo = new_repo(name)
        put(repo, {"README.md": "base\n", "src/band.mjs": JS_PASS_SRC})
        commit(repo, "Base")
        files = {"src/band.mjs": JS_BAND_SRC}
        files.update(suites)
        CACHE[key] = (repo, pull_request(repo, number, "Band grades", files))
    return CACHE[key]


def runs_in(log):
    """The runs a counting suite made: one x in its log per run."""
    if not os.path.exists(log):
        return 0
    with open(log, encoding="utf-8") as handle:
        return handle.read().count("x")


def counted_replay(name, first, second):
    """The replay of a band pull request with suite `first` and suite `second`, which counts its runs. Built and
    replayed once per `name`. Returns (row, runs, mutants). The runs are read right after the replay, because a
    later replay of the same repository appends to the log too. The mutants are the engine's own list for the
    lines the pull request added."""
    key = "counted-" + name
    if key not in CACHE:
        log = os.path.join(fresh(), "runs.txt")
        repo, sha = band_pr(name, 40, {"test/a.test.mjs": first, "test/b.test.mjs": counting_suite(second, log)})
        row = replay(repo, sha, JS_PROFILE)
        runs = runs_in(log)
        mutants = expected_mutants(repo, sha, "src/band.mjs", lines=changed(repo, sha, "src/band.mjs"))
        CACHE[key] = (row, runs, mutants)
    return CACHE[key]


# Per-file selection. The base holds two product files, a suite for each, and a selector that lists the suites of
# one file (shaped like q_max's harness/tests-for.mjs). The pull request changes both files and both suites. Each
# suite counts its runs, so a case reads from the logs which suite ran against which file's mutants. Neither suite
# kills a mutant: each checks only that its export is a function. So no run ends early, and each suite runs on every
# mutant the replay gives it, whatever the order of the suites.
SELECTOR_LISTS = """\
// Prints the suites that test one product file. The replay ignores each line that names no changed suite.
const path = process.argv[2];
console.log('tests for ' + path);
if (path === 'src/x.mjs') {
  console.log('test/a.test.mjs');
  console.log('test/unchanged.test.mjs');
} else if (path === 'src/y.mjs') {
  console.log('test/b.test.mjs');
}
"""
SELECTOR_FAILS_FOR_Y = """\
const path = process.argv[2];
console.log('tests for ' + path);
if (path === 'src/x.mjs') {
  console.log('test/a.test.mjs');
} else if (path === 'src/y.mjs') {
  console.error('no list for ' + path);
  process.exit(1);
}
"""
SELECT_X_BASE = "export const LABEL_X = 'x';\n"
SELECT_X_PR = SELECT_X_BASE + "\nexport function capX(n) {\n  if (n > 10) {\n    return 10;\n  }\n  return n;\n}\n"
SELECT_Y_BASE = "export const LABEL_Y = 'y';\n"
SELECT_Y_PR = SELECT_Y_BASE + "\nexport function passY(score) {\n  return score >= 50;\n}\n"
SELECT_A_BASE = JS_HEAD + ("import { LABEL_X } from '../src/x.mjs';\n\n"
                           "test('label x', () => {\n  assert.equal(LABEL_X, 'x');\n});\n")
SELECT_A_PR = JS_HEAD + """import { capX } from '../src/x.mjs';

test('capX is exported', () => {
  assert.equal(typeof capX, 'function');
});
"""
SELECT_B_BASE = JS_HEAD + ("import { LABEL_Y } from '../src/y.mjs';\n\n"
                           "test('label y', () => {\n  assert.equal(LABEL_Y, 'y');\n});\n")
SELECT_B_PR = JS_HEAD + """import { passY } from '../src/y.mjs';

test('passY is exported', () => {
  assert.equal(typeof passY, 'function');
});
"""
SELECT_PROFILE = dict(JS_PROFILE, select=["node", "harness/tests-for.mjs", "{path}"])
BANCHI_SELECT = ["python3", "scripts/tests-for.py", "{path}"]  # the per-file selector both banchi parts name
# A selector that a later pull request adds at HEAD. Its lists live in harness/lists.mjs, a sibling it imports, so a
# copy of the selector alone cannot run.
SELECTOR_IMPORTS_LISTS = """\
import { LISTS } from './lists.mjs';
const path = process.argv[2];
console.log('tests for ' + path);
for (const suite of LISTS[path] || []) {
  console.log(suite);
}
"""
LISTS_MODULE = """\
export const LISTS = {
  'src/x.mjs': ['test/a.test.mjs', 'test/unchanged.test.mjs'],
  'src/y.mjs': ['test/b.test.mjs'],
};
"""
# A selector at HEAD that lists both suites for both files. The commit's own selector must win over it.
SELECTOR_LISTS_BOTH = """\
const path = process.argv[2];
console.log('tests for ' + path);
console.log('test/a.test.mjs');
console.log('test/b.test.mjs');
"""
LATER_IMPORTS = {"harness/tests-for.mjs": SELECTOR_IMPORTS_LISTS, "harness/lists.mjs": LISTS_MODULE}
LATER_BOTH = {"harness/tests-for.mjs": SELECTOR_LISTS_BOTH}
# A root file named node at HEAD. The select argv's `node` is a command PATH resolves, never this file.
LATER_BARE_NODE = dict(LATER_IMPORTS, node="not a program\n")


def select_fixture(name, selector=SELECTOR_LISTS, pr_deletes_selector=False, later=None):
    """One merged pull request, 1, that changes src/x.mjs, src/y.mjs, test/a.test.mjs and test/b.test.mjs. Its base
    holds `selector` at harness/tests-for.mjs, or no selector when `selector` is None. With `pr_deletes_selector` the
    pull request deletes that file, so the selector is missing at its commit. With `later`, a {path: text} map, a
    second merged pull request, 2, writes those files after pull request 1: the repository's HEAD is then pull
    request 2's merge, and `sha` stays pull request 1's. Built once per `name`."""
    key = "select-" + name
    if key not in CACHE:
        repo = new_repo(name)
        base = {"README.md": "base\n", "src/x.mjs": SELECT_X_BASE, "src/y.mjs": SELECT_Y_BASE,
                "test/a.test.mjs": SELECT_A_BASE, "test/b.test.mjs": SELECT_B_BASE}
        if selector is not None:
            base["harness/tests-for.mjs"] = selector
        put(repo, base)
        commit(repo, "Base")
        logs = {"a": os.path.join(fresh(), "runs-a.txt"), "b": os.path.join(fresh(), "runs-b.txt")}
        files = {"src/x.mjs": SELECT_X_PR, "src/y.mjs": SELECT_Y_PR,
                 "test/a.test.mjs": counting_suite(SELECT_A_PR, logs["a"], wait_ms=0),
                 "test/b.test.mjs": counting_suite(SELECT_B_PR, logs["b"], wait_ms=0)}
        if pr_deletes_selector:
            files["harness/tests-for.mjs"] = None
        sha = pull_request(repo, 1, "Select per file", files)
        mutants = {"x": expected_mutants(repo, sha, "src/x.mjs", lines=changed(repo, sha, "src/x.mjs")),
                   "y": expected_mutants(repo, sha, "src/y.mjs", lines=changed(repo, sha, "src/y.mjs"))}
        if later:
            pull_request(repo, 2, "Add the later selector", later)
        CACHE[key] = {"repo": repo, "sha": sha, "logs": logs, "mutants": mutants}
    return CACHE[key]


def select_run(name, **options):
    """The replay of select_fixture(name) with every mutant kept, and the runs each suite made. Returns (row, runs,
    fixture). The runs are read right after the replay, because a later replay appends to the logs too."""
    key = "select-run-" + name
    if key not in CACHE:
        fixture = select_fixture(name, **options)
        row = replay(fixture["repo"], fixture["sha"], SELECT_PROFILE, limit=1000)
        runs = {suite: runs_in(path) for suite, path in fixture["logs"].items()}
        CACHE[key] = (row, runs, fixture)
    return CACHE[key]


# Budget. One band pull request whose suite holds each run for BUDGET_RUN_MS. The clean run and the first mutant
# start within about 4 s (the mutant engine and the checkout take about 0.6 s), and a second mutant would start
# after about 6.8 s. BUDGET_S sits between the two, so the budget cuts after the first mutant.
BUDGET_RUN_MS = 3000
BUDGET_S = 5.0


def budget_fixture():
    """One band pull request, 42, whose suite holds each run for BUDGET_RUN_MS. Built once."""
    if "budget" not in CACHE:
        CACHE["budget"] = band_pr("budget", 42, {"test/band.test.mjs": sleeping_suite(JS_BAND_TEST, BUDGET_RUN_MS)})
    return CACHE["budget"]


def replay_budget(repo, sha, pr_budget, limit=4):
    """A replay of `sha` with one job, so the budget alone decides which mutants start. None is no budget."""
    if "pr_budget" not in inspect.signature(api("replay_pr")).parameters:
        raise AssertionError("replay_pr has no pr_budget parameter yet")
    return api("replay_pr")(repo, sha, JS_PROFILE, limit=limit, seed=0, suite_timeout=60, jobs=1,
                            pr_budget=pr_budget)


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

from typing import List, NamedTuple


class Result(NamedTuple):
    passed: bool
    detail: str = ""


class NotImplementedYet(Exception):
    """Raised by a stub. The runner reports it as a failure, never as a skip."""


class Checks:
    """Collects assertions so one run reports every failure. Shaped like banchi's Checks: an ok line starts
    with two spaces, and a run with no checks is a failure."""

    def __init__(self) -> None:
        self.lines: List[str] = []
        self.failures = 0

    def ok(self, condition, label):
        self.lines.append("  %s %s" % ("ok  " if condition else "FAIL", label))
        if not condition:
            self.failures += 1
        return bool(condition)

    def equal(self, actual, expected, label):
        if self.ok(actual == expected, label):
            return True
        self.lines.append("       expected %r, actual %r" % (expected, actual))
        return False

    def result(self, headline=""):
        total = sum(1 for line in self.lines if line.startswith(("  ok  ", "  FAIL")))
        body = ([headline] if headline else []) + self.lines
        if not total:
            body.append("  FAIL no checks ran")
        return Result(self.failures == 0 and total > 0, "\\n".join(body))
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


def banchi_part(part="py"):
    """The banchi runner's profile part `part` ("py" or "ts"), as hooks/mutate_guard.py names it."""
    try:
        return mutate_guard.REPLAY_PROFILES["banchi"]["parts"][part]
    except (KeyError, TypeError):
        raise AssertionError("REPLAY_PROFILES has no banchi %s part" % part)


def banchi_profile():
    """The banchi py part made runnable here: every list value names the test's own interpreter in place of the
    install's venv, and the install is off, since the fixtures need no requirements. Built from the real part, so a
    key the build adds reaches these cases."""
    def local(value):
        if isinstance(value, list):
            return [local(item) for item in value]
        return sys.executable if value == "{deps}/venv/bin/python" else value

    profile = {key: local(value) for key, value in banchi_part().items()}
    profile["install"] = None
    return profile


def banchi_harness(suite_text):
    """The files of banchi's harness that a fixture needs: the shared types, the home helper, and one tN module at
    BANCHI_SUITE holding `suite_text`."""
    return {"harness/tests/__init__.py": BANCHI_INIT, "harness/tests/home.py": BANCHI_HOME, BANCHI_SUITE: suite_text}


def banchi_suite(module_text):
    """A tree shaped like banchi's harness, with one module at BANCHI_SUITE. Returns (folder, argv): argv is
    the profile's own runner command, with the suite path filled in and the test's interpreter in place of
    the install's venv."""
    folder = os.path.join(fresh(), "banchi")
    put(folder, banchi_harness(module_text))
    argv = [piece.replace("{suite}", BANCHI_SUITE) for piece in banchi_profile()["argv"]]
    return folder, argv


# THE T7 GROUP FIXTURE: a banchi repository whose T7 is split into group modules, harness/tests/t7/<group>.py. Each
# group has a CHECKS tuple, and harness/tests/t7_store_and_seams.py's run(order=) runs the checks of the groups in
# CHECK_ORDER with hermetic() around each one. Every group, and T7's box-map checks, appends a line to its own log
# when a check runs. Each log path is baked into the file text from this case's run folder, so a replay leaves
# the line where the case reads it. Product: pricing/grade.py, which every group tests.
GRADE_PATH = "pricing/grade.py"
GRADE_BASE = 'def band(score):\n    return "C"  # the base grades every score C\n'
GRADE_BANDS = ('def band(score):\n    if score >= 90:\n        return "A"\n    if score >= 50:\n'
               '        return "B"\n    return "C"\n')
GRADE_ONE = 'def band(score):\n    return "A"\n'
GROUPS = ("alpha", "beta", "box")
STRONG = ((95, "A"), (60, "B"), (10, "C"))

T7_RUNNER = '''"""T7 fixture: shaped like banchi's t7_store_and_seams.py. run() walks CHECK_ORDER, each check in hermetic()."""

from harness.tests import Checks, Result
from harness.tests.t7 import alpha, beta
from harness.tests.t7.common import hermetic

NAME = "T7"
CHECK_ORDER = (*alpha.CHECKS, *beta.CHECKS)


def run(order=None) -> Result:
    from harness.tests import t7_box_map  # its checks run in T7's run, after CHECK_ORDER

    checks = Checks()
    todo = list(CHECK_ORDER) + list(t7_box_map.CHECKS)
    if order is not None:
        todo = list(order(todo))
    for check in todo:
        with hermetic():
            check(checks)
    return checks.result("store/ and the seams")
'''

# A helper, not a group. Its text holds every shape a naive scan could take for a CHECKS line, and none is one.
COMMON = '''"""Helpers the T7 group modules share. Not a group: this file has no checks of its own.

A text scan that reads a CHECKS line at column 0 would take this file for a group:
CHECKS = (
    never_run,
)
"""

import contextlib
import os

MARKER = "FIXTURE_HERMETIC"
# CHECKS = () here is a comment, not a group.
NOT_A_GROUP = "CHECKS = ()"
OPENER = "# not a comment, though it opens like one"


@contextlib.contextmanager
def hermetic():
    """The setup each check runs in: the marker is set while the check runs, and no longer."""
    os.environ[MARKER] = "1"
    try:
        yield
    finally:
        os.environ.pop(MARKER, None)


def band_label(score):
    return "band %d" % score
'''
COMMON_CHANGED = COMMON + '\n\ndef band_span():\n    return "10 to 95"\n'

ALPHA = '''"""T7 group fixture: alpha. Its first check runs first, and its second reads what the first left behind.

Don't reorder the two: the order is part of what this group proves.
"""

import os

from harness.tests.t7.common import MARKER
from pricing import grade

LOG = %(log)r
RAN = []


def _log():
    with open(LOG, "a", encoding="utf-8") as handle:
        handle.write("x")


def check_first(checks):
    checks.ok(os.environ.get(MARKER) == "1", "alpha runs inside hermetic()")
    _log()
    RAN.append("first")
%(first)s


def check_rest(checks):
    checks.ok(RAN == ["first"], "alpha's first check ran before this one")
%(rest)s


CHECKS = (check_first, check_rest)
'''


def alpha_text(log, bands, lower=False):
    """alpha.py for `bands`, a ((score, label), ...) of what band() must return: the first pair is checked in
    check_first and the rest in check_rest. With `lower`, the result is lowercased before the compare, so a
    None raises rather than failing the compare."""
    lines = []
    for score, label in bands:
        got = "grade.band(%d)%s" % (score, ".lower()" if lower else "")
        want = label.lower() if lower else label
        lines.append('    checks.equal(%s, %r, "band %d is %s")' % (got, want, score, label))
    return ALPHA % {"log": log, "first": "\n".join(lines[:1]), "rest": "\n".join(lines[1:]) or "    pass"}


def beta_text(log):
    return '''"""T7 group fixture: beta. Its one check writes a line, so a run that reaches it leaves a trace."""

LOG = %r


def check_beta(checks):
    with open(LOG, "a", encoding="utf-8") as handle:
        handle.write("x")
    checks.ok(True, "beta check ran")


CHECKS = (check_beta,)
''' % (log,)


def box_map_text(log):
    return '''"""T7 fixture: the box-map checks, which T7's run adds to its own."""

LOG = %r


def check_box_map(checks):
    with open(LOG, "a", encoding="utf-8") as handle:
        handle.write("x")
    checks.ok(True, "box map check ran")


CHECKS = (check_box_map,)
''' % (log,)


GAMMA = '''"""T7 group fixture: gamma. Its CHECKS tuple is empty, so a run of it checks nothing."""

CHECKS = ()
'''

T1_X = '''"""Fixture tN module: a suite of its own, run whole, as today."""

from harness.tests import Checks, Result
from pricing import grade


def run() -> Result:
    checks = Checks()
    checks.equal(grade.band(95), "A", "band 95 is A")
    checks.equal(grade.band(60), "B", "band 60 is B")
    checks.equal(grade.band(10), "C", "band 10 is C")
    return checks.result("grades")
'''


def t7_base(logs):
    """The files every T7 case starts from: the banchi harness, the T7 modules at their base, and the product at
    its base. Its one band() returns "C" for every score, and the base alpha checks exactly that."""
    return {
        "README.md": "base\n",
        "pricing/__init__.py": "",
        GRADE_PATH: GRADE_BASE,
        "harness/tests/__init__.py": BANCHI_INIT,
        "harness/tests/home.py": BANCHI_HOME,
        "harness/tests/t7_store_and_seams.py": T7_RUNNER,
        "harness/tests/t7_box_map.py": box_map_text(logs["box"]),
        "harness/tests/t7/__init__.py": '"""T7 group modules."""\n',
        "harness/tests/t7/common.py": COMMON,
        "harness/tests/t7/alpha.py": alpha_text(logs["alpha"], ((10, "C"),)),
        "harness/tests/t7/beta.py": beta_text(logs["beta"]),
    }


# Each case's pull request: the files it writes, given the case's log paths.
T7_CHANGES = {
    "strong": lambda logs: {GRADE_PATH: GRADE_BANDS, "harness/tests/t7/alpha.py": alpha_text(logs["alpha"], STRONG)},
    "weak": lambda logs: {GRADE_PATH: GRADE_BANDS, "harness/tests/t7/alpha.py": alpha_text(logs["alpha"], ((95, "A"),))},
    "helper": lambda logs: {GRADE_PATH: GRADE_BANDS, "harness/tests/t7/alpha.py": alpha_text(logs["alpha"], STRONG),
                            "harness/tests/t7/common.py": COMMON_CHANGED},
    "helper_alone": lambda logs: {GRADE_PATH: GRADE_BANDS, "harness/tests/t7/common.py": COMMON_CHANGED},
    "raise": lambda logs: {GRADE_PATH: GRADE_ONE,
                           "harness/tests/t7/alpha.py": alpha_text(logs["alpha"], ((95, "A"),), lower=True)},
    "gamma": lambda logs: {GRADE_PATH: GRADE_BANDS, "harness/tests/t7/alpha.py": alpha_text(logs["alpha"], STRONG),
                           "harness/tests/t7/gamma.py": GAMMA},
    "tn": lambda logs: {GRADE_PATH: GRADE_BANDS, "harness/tests/t1_x.py": T1_X},
    "whole": lambda logs: {GRADE_PATH: GRADE_BANDS,
                           "harness/tests/t7_store_and_seams.py": T7_RUNNER + "# a comment this change adds\n"},
}


def t7_pr(name):
    """(repo, sha, logs) of the case `name`: the base commit, then its pull request. Built once per name. `logs`
    maps each group, and the box map, to the log path its checks append to."""
    key = "t7-" + name
    if key not in CACHE:
        logs = {group: os.path.join(fresh(), group + ".log") for group in GROUPS}
        repo = new_repo("t7-" + name)
        put(repo, t7_base(logs))
        commit(repo, "Base")
        sha = pull_request(repo, 1, "T7 group change", T7_CHANGES[name](logs))
        CACHE[key] = (repo, sha, logs)
    return CACHE[key]


def t7_row(name):
    """(replay row, logs) of the case `name`, replayed once under the banchi part made runnable here."""
    key = "t7-row-" + name
    if key not in CACHE:
        repo, sha, logs = t7_pr(name)
        CACHE[key] = (replay_no_raise(repo, sha, banchi_profile(), limit=50), logs)
    return CACHE[key]


def t7_mutants(name):
    """The engine's own list of mutants for the product lines the case's pull request added."""
    repo, sha, _logs = t7_pr(name)
    return expected_mutants(repo, sha, GRADE_PATH, lines=changed(repo, sha, GRADE_PATH))


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
        CACHE["edge_rows"] = {n: replay(fixture["repo"], fixture["sha"][n], JS_PROFILE) for n in range(1, 5)}
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


# ---------------------------------------------------------------------------------------------------
# Product files under the REAL profiles. The replay reads a changed file as product when the profile's `code`
# pattern matches it and its `code_not` pattern does not, and a pull request with no product file reads NO_PRODUCT.
# Each case replays its pull request under the profile that hooks/mutate_guard.py names, and reads the row. So the
# cases test that decision where it is made, with no copy of it here. Each pull request also changes a suite, so
# NO_PRODUCT can come only from the product decision.

QMAX_SUITE = "harness/tests/x.test.mjs"
QMAX_SUITE_TEXT = JS_HEAD + "\ntest('sum', () => {\n  assert.equal(1 + 1, 2);\n});\n"
QMAX_SUITE_CHANGED = QMAX_SUITE_TEXT + "\ntest('product', () => {\n  assert.equal(2 * 2, 4);\n});\n"
QMAX_BROWSER_TEST = "harness/browser/verify.test.mjs"
QMAX_BROWSER_TEST_TEXT = (JS_HEAD + "\nfunction passes(score) {\n  return score >= 50;\n}\n\n"
                          "test('verify', () => {\n  assert.equal(passes(60), true);\n});\n")
QMAX_BROWSER_SOURCE = "harness/browser/verify.mjs"
QMAX_BROWSER_SOURCE_TEXT = "export function verify(score) {\n  return score >= 50;\n}\n"
QMAX_TSX = "src/components/Chat.tsx"
QMAX_TSX_TEXT = "export function chat(score: number): boolean {\n  return score >= 50;\n}\n"
QMAX_BASE = {"README.md": "base\n", QMAX_SUITE: QMAX_SUITE_TEXT}

BANCHI_SUITE_CHANGED = BANCHI_GREEN + "# this change touches the suite too\n"
BANCHI_SELFTEST = "scripts/pricearchive-selftest.py"
BANCHI_SELFTEST_TEXT = "def check(price):\n    return price >= 0\n"
BANCHI_STATUS = "scripts/status.py"
BANCHI_STATUS_TEXT = "def status(count):\n    return count >= 1\n"
BANCHI_ROUTES = "server/send_routes.py"
BANCHI_ROUTES_TEXT = 'def route(path):\n    return path == "/status"\n'
BANCHI_BASE = {"README.md": "base\n", **banchi_harness(BANCHI_GREEN)}
# claude_settings: each case's base holds only README.md, except cs_suite_out, whose base holds the suite it changes.
# A pull request adds the files its case names. A suite imports its module from its own folder.
CS_SUITE_HEAD = """import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
"""
CS_STALE = "skills/waiting-page/stale_pages.py"
CS_STALE_TEXT = "def stale(count):\n    return count >= 1\n"
CS_STALE_SUITE = "skills/waiting-page/test_stale_pages.py"
CS_STALE_SUITE_TEXT = CS_SUITE_HEAD + """import stale_pages  # noqa: E402

sys.exit(0 if stale_pages.stale(1) and not stale_pages.stale(0) else 1)
"""
CS_STALE_SUITE_CHANGED = CS_STALE_SUITE_TEXT + "# this change touches the suite too\n"
CS_FIXTURE = "skills/plain-english-map/tests/fixture/src/retry.py"
CS_FIXTURE_TEXT = "def retry(count):\n    return count < 3\n"
CS_HELPER = "skills/waiting-page/tests/merged_page.py"
CS_HELPER_TEXT = "def merged(page):\n    return page is not None\n"
CS_GUARD = "hooks/guard.py"
CS_GUARD_TEXT = "def allowed(n):\n    return n >= 1\n"
CS_GUARD_SUITE = "hooks/test_guard_scope.py"
CS_GUARD_SUITE_TEXT = CS_SUITE_HEAD + """import guard  # noqa: E402

sys.exit(0 if guard.allowed(1) and not guard.allowed(0) else 1)
"""
CS_LINT = "lint/check_scope.py"
CS_LINT_TEXT = "def scope(n):\n    return n >= 1\n"
CS_LINT_SUITE = "lint/test_check_scope.py"
CS_LINT_SUITE_TEXT = CS_SUITE_HEAD + """import check_scope  # noqa: E402

sys.exit(0 if check_scope.scope(1) and not check_scope.scope(0) else 1)
"""
CS_FIXTURES_CLI = "hooks/fixtures_cli/main.py"
CS_FIXTURES_CLI_TEXT = "def run(n):\n    return n >= 1\n"
CS_FIXTURES_CLI_SUITE = "hooks/test_fixtures_cli.py"
CS_FIXTURES_CLI_SUITE_TEXT = CS_SUITE_HEAD + """from fixtures_cli import main  # noqa: E402

sys.exit(0 if main.run(1) and not main.run(0) else 1)
"""
CS_DEMO_FIXTURE = "skills/demo/fixture/a.py"
CS_DEMO_FIXTURE_TEXT = "def a(n):\n    return n < 3\n"


def qmax_profile():
    """The q_max profile as hooks/mutate_guard.py names it, with its install off: these fixtures need no npm ci."""
    return dict(mutate_guard.REPLAY_PROFILES["q_max"], install=None)


def claude_settings_profile():
    """The claude_settings profile as hooks/mutate_guard.py names it. Its `code` and `code_not` are read here, never
    copied, so a widened scope changes these cases with it."""
    return dict(mutate_guard.REPLAY_PROFILES["claude_settings"])


PRODUCT_PROFILES = {"q_max": qmax_profile, "banchi": banchi_profile, "claude_settings": claude_settings_profile}
# case: (profile name, the base commit's files, the pull request's files). A new case adds one entry here.
PRODUCT_CASES = {
    "qmax_test_file": ("q_max", QMAX_BASE,
                       {QMAX_BROWSER_TEST: QMAX_BROWSER_TEST_TEXT, QMAX_SUITE: QMAX_SUITE_CHANGED}),
    "qmax_browser_source": ("q_max", QMAX_BASE,
                            {QMAX_BROWSER_SOURCE: QMAX_BROWSER_SOURCE_TEXT, QMAX_SUITE: QMAX_SUITE_CHANGED}),
    "qmax_tsx_source": ("q_max", QMAX_BASE, {QMAX_TSX: QMAX_TSX_TEXT, QMAX_SUITE: QMAX_SUITE_CHANGED}),
    "qmax_suite_alone": ("q_max", QMAX_BASE, {QMAX_SUITE: QMAX_SUITE_CHANGED}),
    "banchi_selftest": ("banchi", BANCHI_BASE,
                        {BANCHI_SELFTEST: BANCHI_SELFTEST_TEXT, BANCHI_SUITE: BANCHI_SUITE_CHANGED}),
    "banchi_status": ("banchi", BANCHI_BASE, {BANCHI_STATUS: BANCHI_STATUS_TEXT, BANCHI_SUITE: BANCHI_SUITE_CHANGED}),
    "banchi_routes": ("banchi", BANCHI_BASE, {BANCHI_ROUTES: BANCHI_ROUTES_TEXT, BANCHI_SUITE: BANCHI_SUITE_CHANGED}),
    "cs_skills_source": ("claude_settings", {"README.md": "base\n"},
                         {CS_STALE: CS_STALE_TEXT, CS_STALE_SUITE: CS_STALE_SUITE_TEXT}),
    "cs_hooks_source": ("claude_settings", {"README.md": "base\n"},
                        {CS_GUARD: CS_GUARD_TEXT, CS_GUARD_SUITE: CS_GUARD_SUITE_TEXT}),
    "cs_lint_source": ("claude_settings", {"README.md": "base\n"},
                       {CS_LINT: CS_LINT_TEXT, CS_LINT_SUITE: CS_LINT_SUITE_TEXT}),
    "cs_fixture_out": ("claude_settings", {"README.md": "base\n"},
                       {CS_FIXTURE: CS_FIXTURE_TEXT, CS_STALE_SUITE: CS_STALE_SUITE_TEXT}),
    "cs_helper_out": ("claude_settings", {"README.md": "base\n"},
                      {CS_HELPER: CS_HELPER_TEXT, CS_STALE_SUITE: CS_STALE_SUITE_TEXT}),
    "cs_suite_out": ("claude_settings", {"README.md": "base\n", CS_STALE_SUITE: CS_STALE_SUITE_TEXT},
                     {CS_STALE_SUITE: CS_STALE_SUITE_CHANGED}),
    "cs_fixtures_folder_in": ("claude_settings", {"README.md": "base\n"},
                              {CS_FIXTURES_CLI: CS_FIXTURES_CLI_TEXT,
                               CS_FIXTURES_CLI_SUITE: CS_FIXTURES_CLI_SUITE_TEXT}),
    "cs_demo_fixture_out": ("claude_settings", {"README.md": "base\n"},
                            {CS_DEMO_FIXTURE: CS_DEMO_FIXTURE_TEXT, CS_STALE_SUITE: CS_STALE_SUITE_TEXT}),
}


def product_row(case):
    """The row of the case's pull request, replayed once per run under the case's real profile."""
    key = "product-" + case
    if key not in CACHE:
        profile_name, base, changes = PRODUCT_CASES[case]
        repo = new_repo("product-" + case)
        put(repo, base)
        commit(repo, "Base")
        sha = pull_request(repo, 1, "Change under test", changes)
        CACHE[key] = replay_no_raise(repo, sha, PRODUCT_PROFILES[profile_name](), limit=3)
    return CACHE[key]


class QMaxProductTests(unittest.TestCase):
    """The q_max profile reads a browser test file as test code, so a replay never mutates it. The product files
    beside it stay product, and so does a source file of the tsx kind."""

    def test_a_browser_test_file_is_not_product(self):
        row = product_row("qmax_test_file")
        self.assertEqual(row["status"], "NO_PRODUCT", api("format_replay_row")(row))

    def test_a_browser_source_file_is_product(self):
        row = product_row("qmax_browser_source")
        self.assertEqual(row["status"], "OK", api("format_replay_row")(row))

    def test_a_tsx_source_file_is_product(self):
        row = product_row("qmax_tsx_source")
        self.assertEqual(row["status"], "OK", api("format_replay_row")(row))

    def test_a_suite_under_harness_tests_is_not_product(self):
        row = product_row("qmax_suite_alone")
        self.assertEqual(row["status"], "NO_PRODUCT", api("format_replay_row")(row))


class BanchiSelftestTests(unittest.TestCase):
    """The banchi python profile reads a self-test script as test code, so a replay never mutates it. The modules
    under scripts/ and server/ stay product."""

    def test_a_python_selftest_script_is_not_product(self):
        row = product_row("banchi_selftest")
        self.assertEqual(row["status"], "NO_PRODUCT", api("format_replay_row")(row))

    def test_a_scripts_module_is_product(self):
        row = product_row("banchi_status")
        self.assertEqual(row["status"], "OK", api("format_replay_row")(row))

    def test_a_server_module_is_product(self):
        row = product_row("banchi_routes")
        self.assertEqual(row["status"], "OK", api("format_replay_row")(row))


# The child repositories' profiles: the REPLAY_PROFILES keys mailaudit, home, ios_adblock, joyous and degen. A row is
# (key, part, sample product file, sample suite, pins). `part` is None for a repository with one profile; home and
# ios_adblock name each part. The samples are hardcoded paths, since CI has no child clones. `pins` holds the literal
# classify, argv, install and lockfile of the row, and link where the row installs.
CHILD_ROWS = [
    ("mailaudit", None, "src/view-rules.mjs", "test/view-rules.test.mjs", {
        "classify": "fail_line", "argv": ["node", "{suite}"],
        "install": ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
        "lockfile": "package-lock.json", "link": "node_modules"}),
    ("home", "js", "web/model.js", "web/model.test.js", {
        "classify": "node_tap", "argv": ["node", "--test", "--test-reporter=tap", "{suite}"],
        "install": None, "lockfile": None}),
    ("home", "py", "tools/switchbot-ble-gaps.py", "tools/test_switchbot_ble_gaps.py", {
        "classify": "fail_line", "argv": ["python3", "{suite}"], "install": None, "lockfile": None}),
    ("ios_adblock", "node", "chrome/slice.mjs", "chrome/test/slice.test.mjs", {
        "classify": "node_tap", "argv": ["node", "--test", "--test-reporter=tap", "{suite}"],
        "install": ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
        "lockfile": "chrome/package-lock.json", "link": "node_modules"}),
    ("ios_adblock", "shell", "ios/WebExtension/src/strictmode.js", "tests/test_strictmode.sh", {
        "classify": "fail_line", "argv": ["bash", "{suite}"], "install": None, "lockfile": None}),
    ("joyous", None, "src/lib/conversions/normalize.ts", "tests/conversions/normalize.test.ts", {
        "classify": "node_tap",
        "argv": ["node", "--experimental-strip-types", "--test", "--test-reporter=tap", "{suite}"],
        "install": ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
        "lockfile": "package-lock.json", "link": "node_modules"}),
    ("degen", None, "server/jd.py", "tests/addon/test_jd_heal.py", {
        "classify": "fail_line",
        "argv": ["env", "FEED_FREE_FLOOR_GB=0", "{deps}/venv/bin/python", "-m", "unittest", "{suite}"],
        "install": [[sys.executable, "-m", "venv", "{deps}/venv"],
                    ["{deps}/venv/bin/pip", "install", "--quiet", "--disable-pip-version-check", "-r",
                     "requirements.txt"]],
        "lockfile": "requirements.txt", "link": None}),
]
# Suites left out of ios_adblock: test_chrome_slice.sh is TAP, which the node part covers; test_build_rules.sh and
# test_export_lists.sh are zsh; test_merge_chunks.sh needs macOS Swift.
IOS_LEFT_OUT = ["tests/test_chrome_slice.sh", "tests/test_build_rules.sh", "tests/test_export_lists.sh",
                "tests/test_merge_chunks.sh"]


def child_label(key, part):
    return key if part is None else "%s %s" % (key, part)


def child_profile(key, part):
    """The child profile `key`, or its `part`, as hooks/mutate_guard.py names it. A missing key or part is a FAIL
    line."""
    entry = mutate_guard.REPLAY_PROFILES.get(key)
    if entry is None:
        raise AssertionError("REPLAY_PROFILES has no %s key" % key)
    if part is None:
        return entry
    try:
        return entry["parts"][part]
    except (KeyError, TypeError):
        raise AssertionError("REPLAY_PROFILES %s has no %s part" % (key, part))


def known_profile_keys():
    """The keys the claude_settings, q_max and banchi entries use. A child profile uses no other key: no new field."""
    banchi = mutate_guard.REPLAY_PROFILES.get("banchi", {})
    entries = [mutate_guard.REPLAY_PROFILES.get("claude_settings", {}), mutate_guard.REPLAY_PROFILES.get("q_max", {}),
               banchi, *banchi.get("parts", {}).values()]
    return set().union(*entries)


def child_pattern(profile, field, label):
    """The regex in `field` of a child profile. A missing or non-text field is a FAIL line, never a KeyError."""
    value = profile.get(field)
    if not isinstance(value, str):
        raise AssertionError("%s has no %s regex" % (label, field))
    return re.compile(value)


def child_is_product(profile, label, path):
    """`code` matches `path` and `code_not` does not: the rule replay_pr applies to each changed file."""
    code = child_pattern(profile, "code", label)
    not_code = child_pattern(profile, "code_not", label) if profile.get("code_not") else None
    return bool(code.search(path)) and not (not_code and not_code.search(path))


def replay_value(profile, field):
    """The value the replay reads for `field`. A row that installs reads link and lockfile with the replay's defaults; a
    row with no install reads the raw value, None."""
    if profile.get("install") is None:
        return profile.get(field)
    return profile.get(field, {"link": "node_modules", "lockfile": "package-lock.json"}.get(field))


class ChildProfileTests(unittest.TestCase):
    """Each child repository's profile, pinned by the literal values in CHILD_ROWS, by its sample paths and by
    IOS_LEFT_OUT, and read here, never run: a child clone is not in CI. A red here means the profile changed from its
    pin or lost its key or part. That change is the defect, not a stale case."""

    def test_each_child_profile_key_exists(self):
        for key, part, _, _, _ in CHILD_ROWS:
            with self.subTest(profile=child_label(key, part)):
                child_profile(key, part)

    def test_each_child_profile_uses_only_the_known_keys(self):
        known = known_profile_keys()
        for key, part, _, _, _ in CHILD_ROWS:
            label = child_label(key, part)
            with self.subTest(profile=label):
                extra = (set(child_profile(key, part)) | set(mutate_guard.REPLAY_PROFILES[key])) - known
                self.assertFalse(extra, "%s uses keys no claude_settings, q_max or banchi entry uses: %s"
                                 % (label, sorted(extra)))

    def test_each_child_profile_code_matches_the_sample_product_file(self):
        for key, part, product, _, _ in CHILD_ROWS:
            label = child_label(key, part)
            with self.subTest(profile=label):
                self.assertTrue(child_is_product(child_profile(key, part), label, product),
                                "%s: code does not match the sample product file %s" % (label, product))

    def test_each_child_profile_code_skips_the_sample_suite(self):
        for key, part, _, suite, _ in CHILD_ROWS:
            label = child_label(key, part)
            with self.subTest(profile=label):
                self.assertFalse(child_is_product(child_profile(key, part), label, suite),
                                 "%s: code matches the sample suite %s, so a suite is mutated as product"
                                 % (label, suite))

    def test_each_child_profile_tests_matches_the_sample_suite(self):
        for key, part, _, suite, _ in CHILD_ROWS:
            label = child_label(key, part)
            with self.subTest(profile=label):
                tests = child_pattern(child_profile(key, part), "tests", label)
                self.assertTrue(tests.search(suite), "%s: tests does not match the sample suite %s" % (label, suite))

    def test_each_child_profile_classify_is_a_known_classifier(self):
        for key, part, _, _, _ in CHILD_ROWS:
            label = child_label(key, part)
            with self.subTest(profile=label):
                classify = child_profile(key, part).get("classify")
                self.assertTrue(isinstance(classify, str) and classify in mutate_shared.CLASSIFIERS,
                                "%s: classify %r is not a mutate_shared.CLASSIFIERS name" % (label, classify))

    def test_each_child_profile_select_is_a_list_holding_the_path(self):
        for key, part, _, _, _ in CHILD_ROWS:
            label = child_label(key, part)
            with self.subTest(profile=label):
                select = child_profile(key, part).get("select")
                self.assertTrue(isinstance(select, list) and "{path}" in select,
                                "%s: select is not a list holding {path}" % label)

    def test_each_child_row_pins_the_four_fields(self):
        for key, part, _, _, pins in CHILD_ROWS:
            label = child_label(key, part)
            with self.subTest(profile=label):
                missing = {"classify", "argv", "install", "lockfile"} - set(pins)
                self.assertFalse(missing, "%s pins no %s" % (label, ", ".join(sorted(missing))))

    def test_each_child_profile_pins_its_literal_values(self):
        for key, part, _, _, pins in CHILD_ROWS:
            label = child_label(key, part)
            profile = child_profile(key, part)
            for field, want in pins.items():
                with self.subTest(profile=label, field=field):
                    got = replay_value(profile, field)
                    self.assertEqual(got, want, "%s: %s is %r, want %r" % (label, field, got, want))

    def test_mailaudit_code_skips_a_worker_test_file(self):
        self.assertFalse(child_is_product(child_profile("mailaudit", None), "mailaudit", "worker/core.test.mjs"),
                         "mailaudit code reads the suite worker/core.test.mjs as product")

    def test_joyous_code_skips_astro_files(self):
        self.assertFalse(child_is_product(child_profile("joyous", None), "joyous", "src/pages/index.astro"),
                         "joyous code reads a .astro file as product")

    def test_joyous_code_skips_a_test_file_under_src(self):
        self.assertFalse(child_is_product(child_profile("joyous", None), "joyous", "src/lib/x.test.ts"),
                         "joyous code reads the test file src/lib/x.test.ts as product")

    def test_degen_tests_skip_the_web_folder(self):
        tests = child_pattern(child_profile("degen", None), "tests", "degen")
        self.assertIsNone(tests.search("tests/web/test_feed.py"),
                          "degen tests reads tests/web/test_feed.py, a browser suite, as a unittest suite")

    def test_home_code_skips_its_suites(self):
        for part, suite in (("js", "web/model.test.js"), ("py", "tools/test_switchbot_ble_gaps.py")):
            label = child_label("home", part)
            with self.subTest(profile=label):
                self.assertFalse(child_is_product(child_profile("home", part), label, suite),
                                 "%s code reads the suite %s as product" % (label, suite))

    def test_ios_adblock_tests_skip_the_suites_left_out(self):
        for part in ("node", "shell"):
            label = child_label("ios_adblock", part)
            for path in IOS_LEFT_OUT:
                with self.subTest(profile=label, suite=path):
                    tests = child_pattern(child_profile("ios_adblock", part), "tests", label)
                    self.assertIsNone(tests.search(path), "%s tests selects %s, which IOS_LEFT_OUT leaves out"
                                      % (label, path))


class ClaudeSettingsScopeTests(unittest.TestCase):
    """Pins the product scope that the claude_settings profile reads from hooks/mutate_guard.py through `code` and
    `code_not`. A .py file under skills/ is product. A file under hooks/ or lint/ stays product. A fixture folder, a
    tests/ folder or a suite under skills/ is not. A folder named fixtures_cli is product: the fixture term matches a
    whole folder name only."""

    def test_a_skills_source_file_is_product(self):
        row = product_row("cs_skills_source")
        self.assertEqual(row["status"], "OK", "%s reads %s, not product: %s"
                         % (CS_STALE, row["status"], api("format_replay_row")(row)))

    def test_a_hooks_source_file_is_still_product(self):
        row = product_row("cs_hooks_source")
        self.assertEqual(row["status"], "OK", "%s reads %s, not product: %s"
                         % (CS_GUARD, row["status"], api("format_replay_row")(row)))

    def test_a_lint_source_file_is_still_product(self):
        row = product_row("cs_lint_source")
        self.assertEqual(row["status"], "OK", "%s reads %s, not product: %s"
                         % (CS_LINT, row["status"], api("format_replay_row")(row)))

    def test_a_fixture_under_a_skills_tests_folder_is_not_product(self):
        row = product_row("cs_fixture_out")
        self.assertEqual(row["status"], "NO_PRODUCT", "%s reads %s, not NO_PRODUCT: %s"
                         % (CS_FIXTURE, row["status"], api("format_replay_row")(row)))

    def test_a_helper_under_a_skills_tests_folder_is_not_product(self):
        row = product_row("cs_helper_out")
        self.assertEqual(row["status"], "NO_PRODUCT", "%s reads %s, not NO_PRODUCT: %s"
                         % (CS_HELPER, row["status"], api("format_replay_row")(row)))

    def test_a_suite_under_skills_is_not_product(self):
        row = product_row("cs_suite_out")
        self.assertEqual(row["status"], "NO_PRODUCT", "%s reads %s, not NO_PRODUCT: %s"
                         % (CS_STALE_SUITE, row["status"], api("format_replay_row")(row)))

    def test_a_module_in_a_folder_named_fixtures_cli_is_product(self):
        row = product_row("cs_fixtures_folder_in")
        self.assertEqual(row["status"], "OK", "%s reads %s, not product: %s"
                         % (CS_FIXTURES_CLI, row["status"], api("format_replay_row")(row)))

    def test_a_module_in_a_fixture_folder_under_skills_is_not_product(self):
        row = product_row("cs_demo_fixture_out")
        self.assertEqual(row["status"], "NO_PRODUCT", "%s reads %s, not NO_PRODUCT: %s"
                         % (CS_DEMO_FIXTURE, row["status"], api("format_replay_row")(row)))


class ClaudeSettingsSelectPinTests(unittest.TestCase):
    """Pins the select command of the real claude_settings profile: it prints the suite beside a skills/ file. The
    command runs in this checkout, so the suite must be tracked here."""

    def test_the_selector_names_the_suite_beside_a_skills_file(self):
        select = mutate_guard.REPLAY_PROFILES["claude_settings"]["select"]
        argv = [part.replace("{path}", CS_STALE) for part in select]
        done = subprocess.run(argv, cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(done.returncode, 0, "the select command of claude_settings exited %d: %s"
                         % (done.returncode, done.stderr.strip()))
        listed = [line.strip() for line in done.stdout.splitlines()]
        self.assertIn(CS_STALE_SUITE, listed, "the select command of claude_settings does not name %s for %s; it "
                      "printed %r" % (CS_STALE_SUITE, CS_STALE, listed))


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

    def test_a_skipped_file_reads_the_row_unknown_when_other_files_made_mutants(self):
        row = edge_rows()[4]
        self.assertEqual(sorted(row["skipped"]), ["src/broken-late.mjs"])
        self.assertGreater(row["made"], 0, "src/grade.mjs must make mutants, or the row is UNKNOWN for another cause")
        self.assertEqual(row["status"], "UNKNOWN",
                         "a file that does not parse is skipped, so the row must not read OK with a rate")


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


class EarlyStopTests(unittest.TestCase):

    def test_once_a_suite_kills_a_mutant_the_next_suite_does_not_run_on_it(self):
        row, runs, mutants = counted_replay("early", JS_BAND_TEST, JS_BAND_TEST)
        self.assertEqual(row["status"], "OK", row["reason"])
        self.assertEqual(row["unusable"], {}, "both suites must be green on the clean source")
        self.assertGreater(row["made"], 0)
        self.assertEqual(row["made"], len(mutants))
        self.assertEqual((row["killed"], row["crashed"], row["survived"]), (row["made"], 0, 0))
        self.assertEqual(runs, 1, "the second suite ran %d times, want 1: its clean-source run only" % runs)

    def test_a_mutant_the_first_suite_misses_still_runs_the_second(self):
        row, runs, mutants = counted_replay("weak", JS_PASS_ONLY_TEST, JS_BAND_TEST)
        self.assertEqual(row["status"], "OK", row["reason"])
        self.assertEqual(row["unusable"], {}, "both suites must be green on the clean source")
        self.assertGreater(row["made"], 0)
        self.assertEqual(row["made"], len(mutants))
        self.assertEqual((row["killed"], row["crashed"], row["survived"]), (row["made"], 0, 0),
                         "the second suite must kill each mutant the first one misses")
        self.assertEqual(runs, 1 + row["made"], "the second suite must run on each mutant, plus the clean source")


class SelectTests(unittest.TestCase):
    """The profile's `select` argv names the suites to run against each product file's mutants, and the selector a
    replay reads when its commit has none."""

    def assert_per_file_runs(self, row, runs, fixture):
        """The row reads OK with both suites green on the clean source. Each suite ran its clean run and the mutants of
        the one file its selector lists: suite a on src/x.mjs, suite b on src/y.mjs."""
        made_x, made_y = len(fixture["mutants"]["x"]), len(fixture["mutants"]["y"])
        self.assertGreater(made_x, 0, "src/x.mjs needs mutants")
        self.assertGreater(made_y, 0, "src/y.mjs needs mutants")
        self.assertEqual(row["status"], "OK", row["reason"])
        self.assertEqual(row["unusable"], {}, "both suites must be green on the clean source")
        self.assertEqual(row["made"], made_x + made_y)
        self.assertEqual(runs["a"], 1 + made_x, "suite a ran %d times, want its clean run and the %d mutants of "
                         "src/x.mjs only" % (runs["a"], made_x))
        self.assertEqual(runs["b"], 1 + made_y, "suite b ran %d times, want its clean run and the %d mutants of "
                         "src/y.mjs only" % (runs["b"], made_y))

    def test_a_changed_suite_the_selector_does_not_list_for_a_file_never_runs_on_its_mutants(self):
        row, runs, fixture = select_run("main")
        self.assert_per_file_runs(row, runs, fixture)

    def test_a_selector_missing_at_the_pr_commit_runs_the_copy_at_head(self):
        """The commit has no selector, so the copy at HEAD runs, with its folder: the sibling it imports comes along.
        The row names the file it read from HEAD."""
        row, runs, fixture = select_run("added-later", selector=None, later=LATER_IMPORTS)
        self.assert_per_file_runs(row, runs, fixture)
        notes = repr(row.get("notes"))
        self.assertIn("harness/tests-for.mjs", notes, "the row must name the selector it read from HEAD")
        self.assertNotIn("every changed suite runs", notes, "the row fell back to every changed suite")

    def test_a_bare_command_name_is_never_served_from_head(self):
        """A select argv part with no slash is a command PATH resolves. A root file named node at HEAD is not that
        command: the run keeps `node`, each suite runs on its own file's mutants, and no note names node."""
        row, runs, fixture = select_run("bare-node", selector=None, later=LATER_BARE_NODE)
        self.assert_per_file_runs(row, runs, fixture)
        notes = row.get("notes") or []
        self.assertFalse([note for note in notes if re.search(r"\bnode\b", note)],
                         "a note names the bare command node: %r" % notes)
        self.assertTrue(any("harness/tests-for.mjs" in note for note in notes),
                        "the note for the selector read from HEAD is missing: %r" % notes)

    def test_a_selector_at_the_pr_commit_wins_over_a_later_one_at_head(self):
        """Passes on the old code too: the commit's own selector is read first, so the later one at HEAD never runs.
        It pins that order: a replay that read HEAD first would run both suites on both files."""
        row, runs, fixture = select_run("commit-wins", later=LATER_BOTH)
        self.assert_per_file_runs(row, runs, fixture)
        self.assertNotIn("harness/tests-for.mjs", repr(row.get("notes")),
                         "the row names a selector read from HEAD, but the commit's own selector should run")

    def test_a_selector_that_fails_for_one_file_runs_every_changed_suite_on_that_file(self):
        row, runs, fixture = select_run("fails", selector=SELECTOR_FAILS_FOR_Y)
        made_x, made_y = len(fixture["mutants"]["x"]), len(fixture["mutants"]["y"])
        self.assertEqual(row["status"], "OK", row["reason"])
        self.assertEqual(runs["a"], 1 + made_x + made_y, "suite a must run on each mutant of src/x.mjs, and on each "
                         "mutant of src/y.mjs after the fallback")
        self.assertEqual(runs["b"], 1 + made_y, "suite b must run on each mutant of src/y.mjs after the fallback, "
                         "and on no mutant of src/x.mjs, which its selector lists for src/x.mjs only")
        self.assertIn("src/y.mjs", repr(row.get("notes")), "the row must record the fallback for src/y.mjs")

    def test_a_selector_missing_at_the_pr_commit_falls_back_to_every_changed_suite(self):
        row, runs, fixture = select_run("gone", pr_deletes_selector=True)
        made_x, made_y = len(fixture["mutants"]["x"]), len(fixture["mutants"]["y"])
        self.assertEqual(row["status"], "OK", row["reason"])
        self.assertEqual(runs["a"], 1 + made_x + made_y, "suite a must run on every mutant after the fallback")
        self.assertEqual(runs["b"], 1 + made_x + made_y, "suite b must run on every mutant after the fallback")
        notes = repr(row.get("notes"))
        self.assertIn("src/x.mjs", notes, "the row must record the fallback for src/x.mjs")
        self.assertIn("src/y.mjs", notes, "the row must record the fallback for src/y.mjs")

    def test_the_banchi_ts_part_names_the_per_file_selector(self):
        self.assertEqual(banchi_part("ts").get("select"), BANCHI_SELECT, "the banchi ts part has no per-file selector")

    def test_the_banchi_py_part_names_the_per_file_selector(self):
        self.assertEqual(banchi_part("py").get("select"), BANCHI_SELECT, "the banchi py part has no per-file selector")


class PrBudgetTests(unittest.TestCase):
    """--pr-budget: a mutant not started once the pull request's time has passed the budget is not_run. It is never
    a kill, a survivor or a crash."""

    def test_mutants_not_started_past_the_budget_are_not_run(self):
        repo, sha = budget_fixture()
        row = replay_budget(repo, sha, BUDGET_S)
        self.assertEqual(row["status"], "OK", row["reason"])
        self.assertEqual(row["made"], 4)
        ran = row["killed"] + row["crashed"] + row["survived"]
        self.assertEqual(ran, 1, "the budget must cut after the first mutant: %r" % row)
        self.assertEqual(row["not_run"], 3)
        self.assertEqual(len(row["survivors"]), row["survived"], "a mutant not run is not a survivor")

    def test_no_budget_runs_every_mutant(self):
        repo, sha = budget_fixture()
        row = replay_budget(repo, sha, None, limit=2)
        self.assertEqual(row["status"], "OK", row["reason"])
        self.assertEqual(row["made"], 2)
        self.assertEqual(row.get("not_run", 0), 0)
        self.assertEqual(row["killed"] + row["crashed"] + row["survived"], 2)

    def test_the_cli_takes_pr_budget_and_prints_the_not_run_count(self):
        repo, _sha = budget_fixture()
        code, out, err = run_cli(["--replay", repo, "--profile", "fixture-js", "--prs", "1", "--limit", "4",
                                  "--suite-timeout", "60", "--jobs", "1", "--pr-budget", str(BUDGET_S)])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        self.assertIn("not_run", out, out)


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

    def test_a_row_with_mutants_not_run_shows_their_count(self):
        row = fake_row(made=5, killed=1, crashed=0, survived=1, not_run=3)
        text = api("format_replay")([row])
        lines = [line for line in text.split("\n") if "not_run" in line]
        self.assertTrue(lines, "no line shows not_run:\n" + text)
        self.assertIn("3", lines[0], lines[0])


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


class ProgressTests(unittest.TestCase):

    def test_each_finished_mutant_prints_a_line_naming_its_pr_before_the_pr_row(self):
        repo, sha = band_pr("one", 41, {"test/band.test.mjs": JS_BAND_TEST})
        row = replay(repo, sha, JS_PROFILE)
        code, out, err = run_cli(["--replay", repo, "--profile", "fixture-js", "--prs", "1", "--limit", "50",
                                  "--suite-timeout", "60", "--jobs", "2"])
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        lines = out.split("\n")
        row_line = api("format_replay_row")(row).split("\n")[0]
        self.assertIn(row_line, lines, "no row for PR 41 in the output")
        progress = [line for line in lines[1:lines.index(row_line)] if re.search(r"(?<!\d)41(?!\d)", line)]
        self.assertGreater(row["made"], 0)
        self.assertEqual(len(progress), row["made"],
                         "want one progress line per finished mutant for PR 41, before its row")


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
# A web-first matcher that times out prints the timeout, then its own expect error and call log.
PW_TIMEOUT_MATCHER = ("Running 1 test using 1 worker\n\n" + PW_HEADER + "\n"
                      "    Test timeout of 30000ms exceeded.\n\n"
                      "    Error: expect(locator).toBeVisible() failed\n\n"
                      "    Locator: getByRole('button', { name: 'Save' })\n"
                      "    Expected: visible\n"
                      "    Received: <element(s) not found>\n"
                      "    Call log:\n"
                      "      - expect.toBeVisible with timeout 5000ms\n\n" + PW_FRAME + PW_SUMMARY)
PW_CLOSED_MATCHER = ("Running 1 test using 1 worker\n\n" + PW_HEADER + "\n"
                     "    Error: Target page, context or browser has been closed\n\n"
                     "    Error: expect(page).toHaveURL(expected) failed\n\n" + PW_FRAME + PW_SUMMARY)


class PlaywrightClassifyTests(unittest.TestCase):
    """classify_playwright reads the error text of a failure block. The source frame shows where the run
    stood, not what went wrong, so a frame that quotes `expect(page)` is no evidence of an assertion."""

    def test_a_closed_target_under_an_expect_frame_is_a_crash(self):
        self.assertEqual(api("classify_playwright")(1, PW_CLOSED, False), "crash")

    def test_a_test_timeout_under_an_expect_frame_is_not_a_kill(self):
        self.assertIn(api("classify_playwright")(1, PW_TIMEOUT, False), ("crash", "timeout"))

    def test_a_test_timeout_inside_a_web_first_matcher_is_not_an_assert(self):
        self.assertIn(api("classify_playwright")(1, PW_TIMEOUT_MATCHER, False), ("crash", "timeout"))

    def test_a_closed_target_followed_by_an_expect_page_line_is_a_crash(self):
        self.assertEqual(api("classify_playwright")(1, PW_CLOSED_MATCHER, False), "crash")

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


class BanchiT7GroupTests(unittest.TestCase):
    """A banchi pull request that changes a T7 group module, harness/tests/t7/<group>.py, is scored by that group's own
    checks, run in T7's order and setup and nothing else. A changed helper with no CHECKS is not a suite."""

    def scored(self, name):
        row, logs = t7_row(name)
        self.assertEqual(row["status"], "OK", "%s\n%s" % (name, api("format_replay_row")(row)))
        return row, logs

    def test_a_pull_request_that_changes_a_group_and_the_product_reads_ok(self):
        row, _logs = self.scored("strong")
        self.assertGreater(row["made"], 0)

    def test_every_mutant_the_group_reaches_is_killed(self):
        row, _logs = self.scored("strong")
        want = t7_mutants("strong")
        self.assertEqual((row["made"], row["killed"], row["crashed"], row["survived"]),
                         (len(want), len(want), 0, 0), api("format_replay_row")(row))

    def test_only_the_changed_group_runs(self):
        _row, logs = self.scored("strong")
        self.assertTrue(os.path.exists(logs["alpha"]), "alpha never ran, so the other assertions prove nothing")
        self.assertFalse(os.path.exists(logs["beta"]), "beta ran, but only alpha changed")
        self.assertFalse(os.path.exists(logs["box"]), "T7's box-map checks ran inside a group run")

    def test_a_weak_group_leaves_its_unreached_mutants_as_survivors_with_path_and_line(self):
        row, _logs = self.scored("weak")
        repo, sha, _logs = t7_pr("weak")
        text = show(repo, sha, GRADE_PATH)
        unreached = {unique_line(text, "    if score >= 50:"), unique_line(text, '        return "B"'),
                     unique_line(text, '    return "C"')}
        want = set()
        for label, _mutated in t7_mutants("weak"):
            line = int(re.match(r"L(\d+)", label).group(1))
            if line in unreached:
                want.add((GRADE_PATH, line, label))
        self.assertTrue(want, "the band 60 and band 10 lines hold no mutant, so the case proves nothing")
        self.assertEqual(survivor_set(row), want, api("format_replay_row")(row))
        line = unique_line(text, "    if score >= 50:")
        self.assertIn("%s:%d L%d compare GtE -> Lt" % (GRADE_PATH, line, line), api("format_replay_row")(row))

    def test_a_changed_helper_with_no_checks_is_not_a_suite(self):
        row, _logs = self.scored("helper")
        self.assertNotIn("harness/tests/t7/common.py", row["unusable"], api("format_replay_row")(row))
        self.assertGreater(row["killed"], 0)

    def test_a_helper_alone_has_no_suite_and_reads_no_tests(self):
        row, _logs = t7_row("helper_alone")
        self.assertEqual(row["status"], "NO_TESTS", api("format_replay_row")(row))

    def test_a_check_that_raises_is_a_crash_and_never_a_kill(self):
        row, _logs = self.scored("raise")
        self.assertEqual(row["made"], 2, "one return with a value: its None and its drop are the two mutants")
        self.assertEqual((row["killed"], row["crashed"], row["survived"]), (0, row["made"], 0),
                         api("format_replay_row")(row))

    def test_a_group_with_no_checks_is_unusable_and_never_green(self):
        row, _logs = self.scored("gamma")
        self.assertIn("harness/tests/t7/gamma.py", row["unusable"], api("format_replay_row")(row))
        self.assertGreater(row["killed"], 0, "alpha, changed in the same pull request, still scores")

    def test_a_tN_module_is_still_scored_whole(self):
        row, _logs = self.scored("tn")
        self.assertEqual(row["unusable"], {}, api("format_replay_row")(row))
        self.assertGreater(row["killed"], 0)

    def test_a_changed_t7_store_and_seams_is_still_scored_whole(self):
        row, _logs = self.scored("whole")
        self.assertEqual(row["unusable"], {}, api("format_replay_row")(row))
        self.assertGreater(row["killed"], 0)

    def test_the_whole_t7_reaches_beta_and_the_box_map_through_todays_runner(self):
        """The pins above can go red: the whole module, run as a tN module, does reach beta and the box map."""
        repo, sha, logs = t7_pr("whole")
        for path in (logs["beta"], logs["box"]):
            if os.path.exists(path):
                os.remove(path)  # the replay of the case left its own lines here
        folder = checkout_of(repo, sha)
        argv = [piece.replace("{suite}", "harness/tests/t7_store_and_seams.py") for piece in banchi_profile()["argv"]]
        done = subprocess.run(argv, cwd=folder, capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue(os.path.exists(logs["beta"]), "the whole run never reached beta")
        self.assertTrue(os.path.exists(logs["box"]), "the whole run never reached the box map")


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


class RequestStopTests(unittest.TestCase):
    """request_stop is the handler of SIGTERM and SIGINT. A signal that lands on the thread holding _LIVE_LOCK
    (an install's Popen) must return, not wait on a lock its own thread holds."""

    def test_request_stop_called_under_the_held_live_lock_returns(self):
        stop, live_lock = api("request_stop"), api("_LIVE_LOCK")
        returned = []

        def hold_and_stop():
            try:
                with live_lock:
                    stop()
                returned.append(True)
            except RuntimeError:
                pass  # a stuck thread that the release below frees ends its `with` here; returned stays empty

        # Patched, so a stop sets a flag of this case and signals no real child group.
        with mock.patch.object(mutate_shared, "_STOP", threading.Event()):
            with mock.patch.object(mutate_shared, "_LIVE_GROUPS", set()):
                worker = threading.Thread(target=hold_and_stop, daemon=True)
                worker.start()
                worker.join(5)
                alive = worker.is_alive()
                if alive:
                    live_lock.release()  # a plain Lock has no owner: free it, so later cases can take it
                    worker.join(5)
        self.assertFalse(alive, "request_stop waited on _LIVE_LOCK, which its own thread held")
        self.assertTrue(returned, "request_stop did not return")


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
