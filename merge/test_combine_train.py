#!/usr/bin/env python3
"""Fixture suite for merge/combine_train.py, the dry combine-train tool (roadmap step combine-train-tool).

Run: python3 merge/test_combine_train.py

The tool is dry: temp trees and `git merge-tree`. It never runs `git push`, `gh pr ready` or `gh pr merge`.
These cases hold that with a `git` and a `gh` first on PATH that log every call and refuse push, ready and
merge. The fast checks reach ci-job through merge.CI_JOB, which these cases point at a fake ci-job, so no
real lint runs. Every fixture repo is a clone of a seed repo under this run's folder (test-temp-standard).
The PATH shims are Python scripts with a shebang line, so these cases run on POSIX.

The contract these cases read (the tool's own output; the labels are exact):
  main(argv, clock=None) -> exit code, printing to stdout. argv: --queue FILE --root DIR [--lint].
  clock: a callable returning seconds, injected for tests; the tool never reads the real clock for a number.
  queue FILE: {"prs": [{"number": N, "head": SHA}, ...] in priority order,
               "batches": [{"name": B, "state": "in-ci" | "next-in-line" | "queued", "members": [N, ...]}, ...]}
  line 1: a header that names the readings used ((a) to (f)), no push, and dry. It does not begin with "batch".
  per batch: a line that begins `batch NAME` and names its members as #N tokens in order. Then these
    lines, each starting at the line's beginning: `members in: N`, `members left out: N`,
    `clash rate: N/M` (or `clash rate: n/a (reason)`), N the members left out, M the pairs tried (a merge with main is no pair),
    `dry rounds: N`, `dry-round minutes: X`, `lint minutes: X` (`unknown` when the lint cannot finish), `CI minutes: X`.
    A left-out member names its PR number and its conflicting paths; a member that clashes with main reads `(clash with main)`.
  a fast check with no home: `unknown (fast-checks-before-ready not landed)`.
  a git that is not on PATH: exit 2, one `unknown` line that names git, no traceback.
  exit: 0 ok, 1 something left out or a failed check, 2 unknown or cannot run.
  --build (roadmap step combine-train-build): with --name NAME, the members fold into the local branch
    merge.integration_branch(NAME), built from the newest origin/main: one `git merge --no-ff` per member, in queue order.
    The members are merge.reviewed_read's rows whose act is batch, the front PR (the first such row) left out. A run with no
    --queue reads them.
    A member's live head is the ref GitHub serves a pull head at, refs/pull/N/head on origin. A member whose live head is not
    its queued head, or that clashes with the newest main, leaves by name (`left out #N: ...`, with its paths); no conflict is
    fixed by hand. Under 10 ready members (ruling 10:23 CST Nov 20: a backlog of 10 or more combines) the run prints
    `merge alone`, builds nothing, and exits 3. The run prints the integration PR's freeze block, from merge.BATCH_BEGIN to
    merge.BATCH_END: the body the PR carries (ruling own-811-c-marker-line, the combined PR's marker line). It pushes nothing
    and makes no gh pr create, ready or merge call.
"""
import ast
import atexit
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(os.path.dirname(HERE), "lint"))  # append: no lint module shadows one this suite imports
import _test_git  # noqa: E402,F401  test-run signing opt-out for the fixture commits (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: the run folder's one home (lint/_test_temp.py)
import merge  # noqa: E402  merge.CI_JOB is the one home of a ci-job run; these cases point it at a fake

TOOL = os.path.join(HERE, "combine_train.py")
MERGE_PY = os.path.join(HERE, "merge.py")
READY = ["STE lint", "split guard", "cost pins", "scaffold", "debt retire", "open-PR clash"]
GIT_WRAPPERS = {"merge_tree", "conflicting_files", "ci_job_run", "ready_job_groups", "integration_branch", "freeze_lines", "reviewed_read", "Host", "BUILD_THRESHOLD", "ready_batch_numbers"}  # the merge.py names the tool may reach; ready_job_groups splits the ready checks by job, no run; integration_branch and freeze_lines are the one home of the integration branch name and the freeze body (coordinator pick, rule building-one-home-per-capability); reviewed_read (merge.py:6230) is the queue's reader, and Host is the host it reads through, as the --reviewed path builds it (merge.py:7746); BUILD_THRESHOLD and ready_batch_numbers are the one home of the threshold and of the ready filter, which the hint reads too
NO_HOME = "unknown (fast-checks-before-ready not landed)"
SIX = ["members in", "members left out", "clash rate", "dry-round minutes", "lint minutes", "CI minutes"]
PASS_WORD = re.compile(r"(?<!not a )(?<!not )(?<!no )\b(?:pass(?:es|ed)?|ok)\b", re.I)  # a claim of pass ("pass", "passed", "ok"), not "not a pass" or "not ok"
CALLER_ENV = ("GH_REPO", "CLAUDE_CODE_REMOTE", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_CODE_SESSION_ID")  # the caller's env that merge.py reads for a repo or a session role; run_tool strips these and GITHUB_*

os.environ.update(LC_ALL="C", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                  GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

_RUN = []


def run_folder():
    """This run's one folder (test-temp-standard), made on the first request and removed when the process exits."""
    if not _RUN:
        _RUN.append(_test_temp.run_folder())
        atexit.register(shutil.rmtree, _RUN[0], True)
    return _RUN[0]


def scratch(prefix):
    """A new empty folder under this run's folder. Every helper below takes its folders from here."""
    return tempfile.mkdtemp(prefix=prefix, dir=run_folder())


FAKE_CI_JOB = '''import json, os, sys
args = sys.argv[1:]
log = os.environ.get("FAKE_CI_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(args) + "\\n")
steps = [args[i + 1] for i in range(len(args) - 1) if args[i] == "--step"]
job = args[0] if args else ""
known = os.environ.get("FAKE_CI_JOB_STEPS")  # JSON {job: [steps]}: a step that job does not hold is unknown, as bin/ci-job reads it
if known:
    held = json.loads(known).get(job, [])
    for s in steps:
        if s not in held:
            print("unknown " + s + ": no step of job " + repr(job))
            sys.exit(2)
mode = os.environ.get("FAKE_CI_MODE", "pass")
if mode == "unknown":
    print("unknown " + (steps[0] if steps else "checks") + ": cannot run here")
    sys.exit(2)
if mode == "fail" and steps:
    print("FAIL " + steps[0] + ": fake failure")
    sys.exit(1)
for s in steps:
    print("PASS " + s)
sys.exit(0)
'''

_FAKE = []


def fake_ci_job():
    """The fake bin/ci-job: logs its argv, then passes, fails or cannot run, as FAKE_CI_MODE says."""
    if not _FAKE:
        path = os.path.join(run_folder(), "fake_ci_job.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(FAKE_CI_JOB)
        _FAKE.append(path)
    return _FAKE[0]


SHIM = '''import json, os, sys
LOG = %(log)r
REAL = %(real)r
REFUSE = %(refuse)r
args = sys.argv[1:]
name = os.path.basename(sys.argv[0])
with open(LOG, "a", encoding="utf-8") as f:
    f.write(json.dumps([name] + args) + "\\n")
if name == "git" and not any(v in args for v in REFUSE):
    os.execv(REAL, [REAL] + args)
sys.stderr.write("refused by the test shim\\n")
sys.exit(1)
'''


def write_shims(refuse=("push",)):
    """A folder with a `git` and a `gh`. Each logs its call as a JSON list. git forwards every call but those naming a word of
    `refuse` (default `push`), which it refuses; gh refuses every call. -> (folder, log path)."""
    folder = scratch("shims-")
    log = os.path.join(folder, "calls.jsonl")
    body = SHIM % {"log": log, "real": shutil.which("git") or "/usr/bin/git", "refuse": tuple(refuse)}
    for name in ("git", "gh"):
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write("#!%s\n%s" % (sys.executable, body))
        os.chmod(path, 0o755)
    return folder, log


def calls(log):
    """Each JSON line of a call log as a list (the program's name, then its arguments). A missing log is no calls."""
    try:
        with open(log, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []


def step_names(argv):
    """The --step names of one ci-job argv (a list), in order."""
    return [argv[i + 1] for i in range(len(argv) - 1) if argv[i] == "--step"]


def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def git_ok(cwd, *args):
    rc, out = git(cwd, *args)
    if rc:
        raise RuntimeError("git %s failed in %s: %s" % (" ".join(args), cwd, out.strip()))
    return out


def write(repo, path, text):
    full = os.path.join(repo, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def make_repo(files, checks=None):
    """A seed repo whose `main` holds `files` ({path: text}), and a root clone of it, so origin/main is set.
    `checks` is merge.readyChecks in .github/stamp.json on main; None leaves that key out. -> the root path."""
    base = scratch("repo-")
    seed, root = os.path.join(base, "seed"), os.path.join(base, "root")
    git_ok(base, "init", "-q", "-b", "main", seed)
    cfg = {"defaultBranch": "main", "merge": {}}
    if checks is not None:
        cfg["merge"]["readyChecks"] = list(checks)
    write(seed, ".github/stamp.json", json.dumps(cfg))
    for path, text in files.items():
        write(seed, path, text)
    git_ok(seed, "add", "-A")
    git_ok(seed, "commit", "-q", "-m", "main")
    git_ok(base, "clone", "-q", seed, root)
    return root


def add_pr(root, number, edits):
    """A commit on branch pr-N, from origin/main in `root`, with `edits` ({path: text}). -> the head sha."""
    git_ok(root, "checkout", "-q", "-B", "pr-%d" % number, "origin/main")
    for path, text in edits.items():
        write(root, path, text)
    git_ok(root, "add", "-A")
    git_ok(root, "commit", "-q", "-m", "pr %d" % number)
    return git_ok(root, "rev-parse", "HEAD").strip()


def advance_main(root, edits):
    """A commit on the seed's main (the repo `root` was cloned from), then a fetch: origin/main moves, and root's own main does not.
    -> the new origin/main sha."""
    seed = git_ok(root, "config", "--get", "remote.origin.url").strip()
    for path, text in edits.items():
        write(seed, path, text)
    git_ok(seed, "add", "-A")
    git_ok(seed, "commit", "-q", "-m", "main moves")
    git_ok(root, "fetch", "-q", "origin")
    return git_ok(root, "rev-parse", "origin/main").strip()


def queue_file(prs, batches):
    """A queue file. prs: [(number, head sha)] in priority order. batches: [(name, state, [members])]."""
    path = os.path.join(scratch("queue-"), "queue.json")
    doc = {"prs": [{"number": n, "head": h} for n, h in prs],
           "batches": [{"name": b, "state": s, "members": list(m)} for b, s, m in batches]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    return path


def ticking_clock(step=60.0):
    """A fake clock: each read advances `step` seconds. Never the real clock."""
    now = [0.0]

    def clock():
        now[0] += step
        return now[0]
    return clock


def run_tool(queue, root, mode="pass", lint=False, clock=None, ci_job=None, shims=None, job_steps=None, extra=(), reviewed=None):
    """Run the tool in-process: main() with merge.CI_JOB at the fake ci-job (or `ci_job`), FAKE_CI_MODE set, and the folder
    `shims` first on PATH. `job_steps` ({job: [steps]}) is the steps each job holds: the fake reads a step another job holds as unknown.
    None lets every step through. `extra` is more argv (the --build cases). `queue` None omits --queue; `reviewed` stands in for
    merge.reviewed_read for the run. -> (exit code, stdout, stderr, ci_calls), where each ci-job argv is a list.
    A flag the tool does not know ends the run with argparse's exit 2 and its message on stderr: the case reads that run, it does not crash."""
    import combine_train  # the tool; imported here so a missing tool fails the case that runs it, not the whole suite
    log = os.path.join(scratch("ci-"), "ci-calls.jsonl")
    env = {"FAKE_CI_MODE": mode, "FAKE_CI_LOG": log}
    if job_steps is not None:
        env["FAKE_CI_JOB_STEPS"] = json.dumps(job_steps)
    if shims:
        env["PATH"] = shims + os.pathsep + os.environ.get("PATH", "")
    argv = (["--queue", queue] if queue is not None else []) + ["--root", root] + (["--lint"] if lint else []) + list(extra)
    out, err = io.StringIO(), io.StringIO()
    try:
        with unittest.mock.patch.dict(os.environ, env), \
                unittest.mock.patch.object(merge, "CI_JOB", ci_job or fake_ci_job()), \
                unittest.mock.patch.object(merge, "reviewed_read", reviewed or merge.reviewed_read), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            for name in list(os.environ):  # the caller's environment, stripped for this run only (patch.dict restores it)
                if name.startswith("GITHUB_") or name in CALLER_ENV:
                    del os.environ[name]
            rc = combine_train.main(argv, clock=clock)
    except SystemExit as e:  # argparse exits on a flag it does not know: the run ended, and its output says so
        rc = e.code
    return rc, out.getvalue(), err.getvalue(), calls(log)


BUILD_NAME = "combine"  # the --name the build cases pass; the branch the build makes is merge.integration_branch(BUILD_NAME)
BUILD_ARGS = ["--build", "--name", BUILD_NAME]
BUILD_BATCH = "Q"  # the queued batch the build folds
TWELVE = list(range(101, 113))  # full size: 12 members; the last one (112) is the member the moved-head and clash cases change
NINE = list(range(101, 110))  # under the threshold of 10 (ruling 10:23 CST Nov 20)
TEN = list(range(101, 111))  # at the threshold: a backlog of 10 ready drafts combines (ruling 10:23 CST Nov 20)
LEFT_OUT = re.compile(r"^\s*left out #(\d+)\b")


def add_members(root, numbers):
    """One real PR per number, each adding its own file on origin/main. -> [(number, head sha)] in queue order."""
    return [(n, add_pr(root, n, {"f%d.txt" % n: "%d\n" % n})) for n in numbers]


def publish_pull(root, numbers):
    """Serve each PR's head at refs/pull/N/head on the fixture origin, the ref GitHub serves a pull head at. The build reads the live head there."""
    if not numbers:
        return
    seed = git_ok(root, "config", "--get", "remote.origin.url").strip()
    git_ok(seed, "fetch", "-q", "--no-tags", root, *["+refs/heads/pr-%d:refs/pull/%d/head" % (n, n) for n in numbers])


def move_pr(root, number, edits):
    """A new commit on PR `number`, served as its live head. The queued head stays its ancestor. -> the new head sha."""
    git_ok(root, "checkout", "-q", "pr-%d" % number)
    for path, text in edits.items():
        write(root, path, text)
    git_ok(root, "add", "-A")
    git_ok(root, "commit", "-q", "-m", "pr %d moves" % number)
    publish_pull(root, [number])
    return git_ok(root, "rev-parse", "HEAD").strip()


def build_queue(root, heads):
    """The queue file: `heads` as one queued batch. Each head is served on the origin, where the build reads the live head."""
    publish_pull(root, [n for n, _ in heads])
    return queue_file(heads, [(BUILD_BATCH, "queued", [n for n, _ in heads])])


def run_build(root, queue, shims=None):
    """The tool run with --build --name, in-process. -> run_tool's four values."""
    return run_tool(queue, root, clock=ticking_clock(), shims=shims, extra=BUILD_ARGS)


FRONT = 101  # the first batch row: the front PR, which merges alone and is no member (ruling 10:23 CST Nov 20)
MEMBERS = list(range(102, 112))  # ten batch rows behind the front: the backlog at the threshold, counted without the front
BATCH_ROWS = [(n, "batch") for n in [FRONT] + MEMBERS]  # eleven batch rows, so the build runs under either reading of the count
OTHER_ROWS = [(112, "lane lint"), (113, "none"), (114, "blocked on #111")]  # rows whose act is not batch: each has a real head, so one folded in shows as a second parent
STACKED_BASE = "pr-99"  # a base ref that no open fixture PR holds as its head: a stacked PR on it reads act batch, not blocked on #N
STACKED = {101: STACKED_BASE, 106: STACKED_BASE}  # batch rows whose pull's base ref is not main: the lowest one takes the front slot on old code, the other sits mid-list
NO_PULL = 110  # a batch row in the middle of the twelve with no pull behind it: the reader names it, and the build exits 2 with no branch


def reviewed_stub(rows, heads, bases=None, no_pull=(), fail=None):
    """A stand-in for merge.reviewed_read (merge.py:6230), with its signature. `rows` is [(number, act)] in number order, and `heads`
    {number: sha}, the heads the fixture serves. `bases` is {number: base ref} for each pull whose base is not main (default: main).
    `no_pull` numbers keep their ledger row but get no pull. `fail` is an exception the read raises before it fills anything.
    It fills `ledger` with one row per pull request, with the keys the reader gives
    (number, act, owner, ageHours, red, blockedOn), and returns (lines, pulls, totals) with the pulls it read. Each call is kept in `.calls`."""
    def stub(h, cfgrel=None, facts=None, ledger=None):
        stub.calls.append(cfgrel)
        if fail is not None:
            raise fail
        if ledger is not None:
            ledger.extend({"number": n, "act": act, "owner": "batch runner" if act == "batch" else "lane", "ageHours": 1.0, "red": False,
                           "blockedOn": int(act.split("#")[1]) if act.startswith("blocked on") else None} for n, act in rows)
        pulls = [{"number": n, "head": {"sha": heads[n], "ref": "pr-%d" % n}, "base": {"ref": (bases or {}).get(n, "main")}, "draft": True,
                  "created_at": "2026-11-20T00:00:00Z", "updated_at": "2026-11-20T00:00:00Z", "labels": [], "body": ""} for n, _act in rows if n not in no_pull]
        lines = ["#%d pr-%d %s: %s" % (n, n, heads[n][:9], act) for n, act in rows]
        return lines, pulls, ["longest wait from a done record: 0.0h", "open PRs with no next act: 0"]
    stub.calls = []
    return stub


def run_reviewed_build(root, stub, shims=None):
    """The build with no --queue: its members come from merge.reviewed_read, which `stub` stands in for. -> run_tool's four values."""
    return run_tool(None, root, clock=ticking_clock(), shims=shims, reviewed=stub, extra=BUILD_ARGS)


def left_out_lines(out):
    """-> {member number: its line} for each `left out #N` line of a run."""
    found = {}
    for line in out.splitlines():
        m = LEFT_OUT.match(line)
        if m:
            found[int(m.group(1))] = line.strip()
    return found


def shown(out, err):
    """The last line a run printed, for a failure message: stdout, else stderr. argparse puts its refusal last."""
    lines = (out or err or "").strip().splitlines()
    return lines[-1][:160] if lines else "(no output)"


def branch_exists(root, branch):
    return git(root, "rev-parse", "--verify", "-q", "refs/heads/" + branch)[0] == 0


def first_parent_chain(root, branch, base):
    """-> the merges from `base` up the first parents of `branch`, oldest first, as (sha, first parent, second parent or None).
    None when `branch` does not exist."""
    rc, out = git(root, "rev-list", "--first-parent", "--parents", "%s..%s" % (base, branch))
    if rc:
        return None
    rows = [line.split() for line in out.splitlines() if line.strip()]
    return [(r[0], r[1] if len(r) > 1 else None, r[2] if len(r) > 2 else None) for r in reversed(rows)]


def printed_block(out):
    """-> (begin markers, end markers, block text). The block runs from the printed begin marker to the end marker. It is the freeze block
    the PR carries, and merge.parse_freeze reads nothing else of a body. The text is None unless the markers make exactly one pair."""
    lines = [line.rstrip("\r") for line in out.splitlines()]
    begins = [i for i, line in enumerate(lines) if line == merge.BATCH_BEGIN]
    ends = [i for i, line in enumerate(lines) if line == merge.BATCH_END]
    one_pair = len(begins) == 1 and len(ends) == 1 and ends[0] > begins[0]
    return len(begins), len(ends), "\n".join(lines[begins[0]:ends[0] + 1]) if one_pair else None


BATCH_RE = re.compile(r"^\s*batch\s+([^\s:(,]+)", re.I)


def batch_blocks(text):
    """-> (names in print order, {name: its lines}). A block starts at its `batch NAME` line and runs to the next one."""
    order, blocks, current = [], {}, None
    for line in text.splitlines():
        m = BATCH_RE.match(line)
        if m:
            current = m.group(1)
            order.append(current)
            blocks[current] = [line]
        elif current is not None:
            blocks[current].append(line)
    return order, blocks


def header_members(block):
    """The member numbers on a batch's header line, in the order printed."""
    return [int(n) for n in re.findall(r"#(\d+)", block[0])]


def value(block, label):
    """The text after `label:` on the first line of `block` that starts with that label, or None."""
    pat = re.compile(r"^\s*" + re.escape(label) + r"\s*[:=]\s*(.*?)\s*$", re.I)
    for line in block:
        m = pat.match(line)
        if m:
            return m.group(1)
    return None


def number_of(text):
    """The leading number of a value as a float, or None when it does not start with one."""
    m = re.match(r"^(\d+(?:\.\d+)?)\b", text or "")
    return float(m.group(1)) if m else None


def label_index(block, label):
    pat = re.compile(r"^\s*" + re.escape(label) + r"\s*[:=]", re.I)
    for i, line in enumerate(block):
        if pat.match(line):
            return i
    return None


def claims_pass(text):
    """The lines of `text` that claim a pass. A line that says not a pass, or no pass, is no claim."""
    return [line for line in text.splitlines() if PASS_WORD.search(line)]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def imported_names(path):
    """The top-level module names a file imports, read from its AST."""
    names = set()
    for node in ast.walk(ast.parse(read(path))):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def merge_names_used(path):
    """The merge.py names a file reaches: `from merge import X`, and `merge.X` for `import merge`. Read from the AST."""
    tree = ast.parse(read(path))
    aliases, names = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "merge":
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            aliases.update(a.asname or a.name for a in node.names if a.name == "merge")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases:
            names.add(node.attr)
    return names


def assert_six_in_order(test, block, name):
    idx = [label_index(block, label) for label in SIX]
    missing = [label for label, i in zip(SIX, idx) if i is None]
    test.assertFalse(missing, "batch %s lacks the number line(s): %s" % (name, ", ".join(missing)))
    test.assertEqual(idx, sorted(idx), "batch %s prints its six numbers out of the order the brief gives" % name)


class Controls(unittest.TestCase):
    """Green on the old code too. They prove the fixtures and the boundary, so a red elsewhere is the tool's and not the harness's."""

    def test_control_two_heads_editing_one_line_conflict_in_git(self):
        root = make_repo({"x.txt": "line a\n"})
        one = add_pr(root, 1, {"x.txt": "line b\n"})
        two = add_pr(root, 2, {"x.txt": "line c\n"})
        rc, out = git(root, "merge-tree", "--write-tree", "--name-only", "--no-messages", one, two)
        self.assertEqual(rc, 1, "git merge-tree of two heads that edit one line must exit 1 (conflict): %s" % out.strip())
        self.assertIn("x.txt", out, "the conflict must name x.txt")

    def test_control_merge_py_does_not_import_the_tool(self):
        self.assertNotIn("combine_train", imported_names(MERGE_PY),
                         "merge.py imports the tool, so the tool could alter a merge verdict")


    def test_control_pass_reader_sees_the_tool_pass_word_ok(self):
        self.assertTrue(claims_pass("batch Q (queued, folded): #3\nround 1, leading tip #3: fast checks ok"),
                        "claims_pass does not read 'fast checks ok' as a pass claim, so the no-pass asserts miss the tool's pass wording")

    def test_control_pass_reader_skips_not_ok(self):
        self.assertEqual(claims_pass("round 1, leading tip #3: fast checks not ok"), [],
                         "claims_pass reads 'not ok' as a pass claim")


class NoPushNoReadyNoMerge(unittest.TestCase):
    def test_full_run_makes_no_git_push_and_no_gh_pr_ready_or_pr_merge_call(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        heads = [(101, add_pr(root, 101, {"f101.txt": "1\n"})),
                 (102, add_pr(root, 102, {"x.txt": "line b\n"})),
                 (103, add_pr(root, 103, {"x.txt": "line c\n"}))]
        queue = queue_file(heads, [("B1", "in-ci", [101]), ("B2", "queued", [102, 103])])
        shims, shim_log = write_shims()
        rc, out, err, ci = run_tool(queue, root, clock=ticking_clock(), shims=shims)
        shim = calls(shim_log)
        git_calls = [c[1:] for c in shim if c[0] == "git"]
        self.assertTrue(git_calls, "the tool made no git call, so the no-push check below proves nothing")
        self.assertTrue(ci, "the tool never reached the fast checks, so this is not a full run")
        self.assertEqual([a for a in git_calls if "push" in a], [], "the tool ran git push")
        gh_calls = [c[1:] for c in shim if c[0] == "gh"]
        self.assertEqual([a for a in gh_calls if a[:2] == ["pr", "ready"]], [], "the tool ran gh pr ready")
        self.assertEqual([a for a in gh_calls if a[:2] == ["pr", "merge"]], [], "the tool ran gh pr merge")


class FrozenBatches(unittest.TestCase):
    def test_frozen_batches_keep_their_member_lists_after_a_fold(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        heads = [(n, add_pr(root, n, {"f%d.txt" % n: "%d\n" % n})) for n in range(101, 107)]
        queue = queue_file(heads, [("B1", "in-ci", [101, 102]), ("B2", "next-in-line", [103]),
                                   ("B3", "queued", [104, 105]), ("B4", "queued", [106])])
        rc, out, err, ci = run_tool(queue, root, clock=ticking_clock())
        order, blocks = batch_blocks(out)
        self.assertIn("B1", blocks, "no batch B1 line in the output: %r" % order)
        self.assertIn("B2", blocks, "no batch B2 line in the output: %r" % order)
        self.assertEqual(len(order), 3, "two frozen batches and one fold of the queued ones make 3 batch lines, got %r" % order)
        self.assertEqual(header_members(blocks["B1"]), [101, 102], "the in-ci batch B1 changed after the fold")
        self.assertEqual(header_members(blocks["B2"]), [103], "the next-in-line batch B2 changed after the fold")
        self.assertEqual(value(blocks["B1"], "members left out"), "0", "the in-ci batch B1 lost a member")
        self.assertEqual(value(blocks["B2"], "members left out"), "0", "the next-in-line batch B2 lost a member")
        folded = [n for n in order if n not in ("B1", "B2")][0]
        self.assertEqual(sorted(header_members(blocks[folded])), [104, 105, 106],
                         "the queued batches must fold into one batch of members 104, 105 and 106")


class FoldRounds(unittest.TestCase):
    """Clean members fold pairwise in rounds: ceil(log2 n) rounds and n-1 merges. One member makes no round and no merge."""

    def _fold(self, members, rounds):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        heads = [(n, add_pr(root, n, {"f%d.txt" % n: "%d\n" % n})) for n in range(1, members + 1)]
        queue = queue_file(heads, [("Q", "queued", list(range(1, members + 1)))])
        rc, out, err, ci = run_tool(queue, root, clock=ticking_clock())
        order, blocks = batch_blocks(out)
        self.assertEqual(order, ["Q"], "one queued batch of %d members must print one batch line, got %r" % (members, order))
        block = blocks["Q"]
        self.assertEqual(number_of(value(block, "members in")), members, "members in for %d members" % members)
        self.assertEqual(number_of(value(block, "dry rounds")), rounds, "dry rounds for %d clean members" % members)
        self.assertEqual(value(block, "members left out"), "0", "a clean fold of %d members left one out" % members)
        clash = value(block, "clash rate") or ""
        if members > 1:
            self.assertEqual(clash, "0/%d" % (members - 1), "a clean fold of %d members makes %d merges and none clash" % (members, members - 1))
        else:
            self.assertTrue(clash.startswith("n/a"), "one member makes no merge, so its clash rate is n/a, not 0: %r" % clash)
        return ci, block

    def test_eight_members_fold_in_three_rounds(self):
        ci, block = self._fold(8, 3)
        self.assertGreaterEqual(len([c for c in ci if "checks" in c]), 3, "the fast checks must run each round: 3 rounds")
        self.assertGreater(number_of(value(block, "dry-round minutes")) or 0, 0, "the dry-round minutes come from the injected clock and must be measured")

    def test_five_members_fold_in_three_rounds(self):
        self._fold(5, 3)

    def test_one_member_makes_no_round(self):
        self._fold(1, 0)


class SixNumbers(unittest.TestCase):
    def test_each_batch_prints_the_six_numbers_in_order_with_unmeasured_ones_named(self):
        root = make_repo({"x.txt": "line a\n", "README.md": "x\n"}, checks=READY)
        heads = [(1, add_pr(root, 1, {"x.txt": "line b\n"})),
                 (2, add_pr(root, 2, {"x.txt": "line c\n"})),
                 (3, add_pr(root, 3, {"f3.txt": "3\n"}))]
        queue = queue_file(heads, [("R", "in-ci", [3]), ("Q", "queued", [1, 2])])
        rc, out, err, ci = run_tool(queue, root, clock=ticking_clock())
        order, blocks = batch_blocks(out)
        self.assertEqual(sorted(order), ["Q", "R"], "each batch must print its own line: got %r" % order)
        q, r = blocks["Q"], blocks["R"]
        assert_six_in_order(self, q, "Q")
        assert_six_in_order(self, r, "R")
        self.assertEqual(value(q, "CI minutes"), "n/a (dry run)", "CI minutes is never measured in a dry run")
        self.assertEqual(value(r, "CI minutes"), "n/a (dry run)", "CI minutes is never measured in a dry run")
        self.assertEqual(value(q, "lint minutes"), "n/a (not run)", "lint minutes without --lint must say not run")
        self.assertEqual(number_of(value(q, "members in")), 2, "batch Q members in")
        self.assertEqual(number_of(value(q, "members left out")), 1, "batch Q members left out: one of the two clashing members")
        self.assertEqual(value(q, "clash rate"), "1/1", "batch Q clash rate: one merge tried, and it left one out")
        self.assertGreater(number_of(value(q, "dry-round minutes")) or 0, 0, "batch Q dry-round minutes come from the injected clock")
        r_clash = value(r, "clash rate") or ""
        self.assertTrue(r_clash.startswith("n/a"), "batch R has one member, no pair tried: its clash rate is n/a, never 0: %r" % r_clash)

    def test_lint_minutes_measured_only_when_the_lint_flag_is_given(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        heads = [(3, add_pr(root, 3, {"f3.txt": "3\n"})), (4, add_pr(root, 4, {"f4.txt": "4\n"}))]
        queue = queue_file(heads, [("Q", "queued", [3, 4])])
        rc, out, err, ci = run_tool(queue, root, clock=ticking_clock())
        self.assertEqual(value(batch_blocks(out)[1]["Q"], "lint minutes"), "n/a (not run)", "no --lint: lint minutes must say not run")
        self.assertEqual([c for c in ci if "--lint" in c], [], "no --lint: the tool must not run the lint")
        rc, out, err, ci = run_tool(queue, root, lint=True, clock=ticking_clock())
        lint = value(batch_blocks(out)[1]["Q"], "lint minutes") or ""
        self.assertIsNotNone(number_of(lint), "--lint on a passing lint: lint minutes must be a measured number, got %r" % lint)
        self.assertEqual(len([c for c in ci if "--lint" in c]), 1, "--lint: one lint call for the one batch, on its final tree")

    def test_header_line_names_the_readings_no_push_and_dry(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        heads = [(3, add_pr(root, 3, {"f3.txt": "3\n"}))]
        queue = queue_file(heads, [("Q", "queued", [3])])
        rc, out, err, ci = run_tool(queue, root, clock=ticking_clock())
        header = (out.splitlines() or [""])[0].lower()
        for word in ("reading", "no push", "dry"):
            self.assertIn(word, header, "the first line must name the readings used, no push and dry; it lacks %r: %r" % (word, header))


class FastChecks(unittest.TestCase):
    def test_no_home_prints_unknown_exits_2_and_claims_no_pass(self):
        root = make_repo({"README.md": "x\n"})
        heads = [(3, add_pr(root, 3, {"f3.txt": "3\n"}))]
        queue = queue_file(heads, [("Q", "queued", [3])])
        rc, out, err, ci = run_tool(queue, root, clock=ticking_clock())
        self.assertIn(NO_HOME, out, "a fast check with no home must print: %s" % NO_HOME)
        self.assertEqual(claims_pass(out), [], "a fast check with no home must not claim pass")
        self.assertEqual(rc, 2, "an unknown fast check must exit 2")

    def test_check_that_cannot_run_exits_2_and_claims_no_pass(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        heads = [(3, add_pr(root, 3, {"f3.txt": "3\n"}))]
        queue = queue_file(heads, [("Q", "queued", [3])])
        rc, out, err, ci = run_tool(queue, root, mode="unknown", clock=ticking_clock())
        self.assertIn("unknown", out.lower(), "a check that cannot run must read unknown")
        self.assertEqual(claims_pass(out), [], "a check that cannot run must not claim pass")
        self.assertEqual(rc, 2, "a check that cannot run must exit 2")

    def test_missing_ci_job_exits_2_and_claims_no_pass(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        heads = [(3, add_pr(root, 3, {"f3.txt": "3\n"}))]
        queue = queue_file(heads, [("Q", "queued", [3])])
        absent = os.path.join(scratch("absent-"), "bin", "ci-job")
        rc, out, err, ci = run_tool(queue, root, ci_job=absent, clock=ticking_clock())
        self.assertEqual(claims_pass(out), [], "a fast check whose ci-job cannot run must not claim pass")
        self.assertEqual(rc, 2, "a fast check whose ci-job cannot run must exit 2")

    def test_failed_check_names_its_step_and_exits_1(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        heads = [(3, add_pr(root, 3, {"f3.txt": "3\n"}))]
        queue = queue_file(heads, [("Q", "queued", [3])])
        rc, out, err, ci = run_tool(queue, root, mode="fail", clock=ticking_clock())
        self.assertIn("FAIL", out, "a failed fast check must print FAIL")
        self.assertIn(READY[0], out, "a failed fast check must name its step: %s" % READY[0])
        self.assertEqual(rc, 1, "a failed fast check must exit 1")


class FastChecksByJob(unittest.TestCase):
    """A qualified ready check (`<job>:<step>`) runs in its own job's ci-job run, and the bare ones in job checks. Each run names only its own steps."""
    QUALIFIED = "checks-rest:project-ops skill scaffold suite"
    JOB_STEPS = {"checks": ["STE lint", "split guard"], "checks-rest": ["project-ops skill scaffold suite"]}

    def _run_one_member(self, checks, job_steps):
        root = make_repo({"README.md": "x\n"}, checks=checks)
        heads = [(3, add_pr(root, 3, {"f3.txt": "3\n"}))]
        queue = queue_file(heads, [("Q", "queued", [3])])
        return run_tool(queue, root, clock=ticking_clock(), job_steps=job_steps)

    def test_qualified_check_runs_in_its_own_job_and_the_fold_passes(self):
        rc, out, err, ci = self._run_one_member(["STE lint", self.QUALIFIED], self.JOB_STEPS)
        self.assertTrue(ci, "the tool never reached ci-job, so this proves nothing")
        self.assertEqual(sorted(c[0] for c in ci), ["checks", "checks-rest"],
                         "ci-job ran for jobs %r; a qualified ready check needs its own ci-job run for its job, one run per job of readyChecks"
                         % [c[0] for c in ci])
        by_job = {c[0]: step_names(c) for c in ci}
        self.assertEqual(by_job["checks"], ["STE lint"], "the checks job's ci-job run must name only its own bare step, not the qualified one")
        self.assertEqual(by_job["checks-rest"], ["project-ops skill scaffold suite"],
                         "the checks-rest job's ci-job run must name only its own step, as bare name")
        self.assertEqual(rc, 0, "a fold whose both job runs pass must exit 0, got %r" % rc)
        self.assertTrue(any("fast checks ok" in line for line in out.splitlines()),
                        "a fold whose both job runs pass must print fast checks ok: %s" % out)

    def test_bare_only_ready_checks_run_one_checks_job_run_and_pass(self):
        rc, out, err, ci = self._run_one_member(READY[:2], {"checks": READY[:2]})
        self.assertTrue(ci, "the tool never reached ci-job, so this proves nothing")
        self.assertEqual([(c[0], step_names(c)) for c in ci], [("checks", READY[:2])],
                         "bare-only ready checks must run one ci-job run for job checks with all of them")
        self.assertEqual(rc, 0, "bare-only ready checks that pass must exit 0, got %r" % rc)
        self.assertTrue(any("fast checks ok" in line for line in out.splitlines()),
                        "bare-only ready checks that pass must print fast checks ok: %s" % out)


class LintMinutes(unittest.TestCase):
    def test_lint_that_cannot_finish_prints_unknown_not_an_elapsed_time(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        heads = [(3, add_pr(root, 3, {"f3.txt": "3\n"})), (4, add_pr(root, 4, {"f4.txt": "4\n"}))]
        queue = queue_file(heads, [("Q", "queued", [3, 4])])
        rc, out, err, ci = run_tool(queue, root, mode="unknown", lint=True, clock=ticking_clock(step=0.001))
        order, blocks = batch_blocks(out)
        self.assertEqual(order, ["Q"], "one queued batch must print one batch line, got %r" % order)
        lint = value(blocks["Q"], "lint minutes") or ""
        self.assertTrue(lint.startswith("unknown"),
                        "a lint that cannot finish is unmeasured: its minutes must print unknown, not an elapsed time: %r" % lint)


class MissingGit(unittest.TestCase):
    """A git that is not on PATH is a run that cannot start: exit 2, and one unknown line that names git, with no traceback."""

    def _run_without_git(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        heads = [(3, add_pr(root, 3, {"f3.txt": "3\n"}))]
        queue = queue_file(heads, [("Q", "queued", [3])])
        env = dict(os.environ, PATH=scratch("no-git-"))  # an empty folder on PATH: no git
        return subprocess.run([sys.executable, TOOL, "--queue", queue, "--root", root], capture_output=True, text=True, env=env)

    def test_missing_git_exits_2(self):
        r = self._run_without_git()
        self.assertEqual(r.returncode, 2, "a git that cannot start is cannot-run: exit 2, got %d" % r.returncode)

    def test_missing_git_prints_no_traceback(self):
        r = self._run_without_git()
        self.assertNotIn("Traceback", r.stderr, "a missing git escapes as a Python traceback; it must print one unknown line")

    def test_missing_git_refusal_is_one_unknown_line_naming_git(self):
        r = self._run_without_git()
        refusal = [line for line in r.stdout.splitlines() if line.startswith("unknown") and "git" in line]
        self.assertTrue(refusal, "a missing git must print one unknown line that names git: stdout %r" % r.stdout)


class ClashLeavesByName(unittest.TestCase):
    def test_clashing_member_leaves_by_name_with_its_conflicting_path(self):
        root = make_repo({"x.txt": "line a\n"}, checks=READY)
        heads = [(1, add_pr(root, 1, {"x.txt": "line b\n"})), (2, add_pr(root, 2, {"x.txt": "line c\n"}))]
        queue = queue_file(heads, [("Q", "queued", [1, 2])])
        rc, out, err, ci = run_tool(queue, root, clock=ticking_clock())
        order, blocks = batch_blocks(out)
        self.assertEqual(order, ["Q"], "one queued batch must print one batch line, got %r" % order)
        block = blocks["Q"]
        self.assertEqual(number_of(value(block, "members left out")), 1, "one of the two clashing members must be left out")
        named = [line for line in block if re.search(r"#2\b", line) and "x.txt" in line]
        self.assertTrue(named, "the left-out member must be named by PR number (#2) with its conflicting path (x.txt): %r" % block)


class RetryBranch(unittest.TestCase):
    """A later side of several members that clashes as a group is retried one member at a time, so only the clashing member leaves.
    This reaches the retry branch of Fold.pair: deleting that branch turns this case red."""

    def test_clashing_group_retries_each_member_and_only_the_clashing_one_leaves(self):
        root = make_repo({"x.txt": "line a\n", "README.md": "x\n"}, checks=READY)
        heads = [(1, add_pr(root, 1, {"x.txt": "line 1\n"})),
                 (2, add_pr(root, 2, {"f2.txt": "2\n"})),
                 (3, add_pr(root, 3, {"x.txt": "line 3\n"})),
                 (4, add_pr(root, 4, {"f4.txt": "4\n"}))]
        queue = queue_file(heads, [("Q", "queued", [1, 2, 3, 4])])
        rc, out, err, ci = run_tool(queue, root, clock=ticking_clock())
        order, blocks = batch_blocks(out)
        self.assertEqual(order, ["Q"], "one queued batch must print one batch line, got %r" % order)
        block = blocks["Q"]
        self.assertEqual(header_members(block), [1, 2, 4],
                         "the group #3 #4 clashes with #1 #2 on #3, so its retry must keep #4 and leave #3: the batch must fold to #1 #2 #4")
        self.assertEqual(number_of(value(block, "members left out")), 1, "one member leaves: only the clashing #3, not the group")
        named = [line for line in block if re.search(r"left out #3\b", line) and "x.txt" in line]
        self.assertTrue(named, "the left-out #3 must name its conflicting path x.txt: %r" % block)


class ClashRate(unittest.TestCase):
    def test_clash_rate_is_members_left_out_over_pairs_tried(self):
        root = make_repo({"x.txt": "line a\n", "README.md": "x\n"}, checks=READY)
        heads = [(1, add_pr(root, 1, {"x.txt": "line 1\n"})),
                 (2, add_pr(root, 2, {"x.txt": "line 2\n"})),
                 (3, add_pr(root, 3, {"x.txt": "line 3\n"})),
                 (4, add_pr(root, 4, {"f4.txt": "4\n"}))]
        queue = queue_file(heads, [("Q", "queued", [1, 2, 3, 4])])
        rc, out, err, ci = run_tool(queue, root, clock=ticking_clock())
        order, blocks = batch_blocks(out)
        self.assertEqual(order, ["Q"], "one queued batch must print one batch line, got %r" % order)
        block = blocks["Q"]
        self.assertEqual(number_of(value(block, "members left out")), 2, "#2 and #3 clash with #1, so 2 members are left out")
        self.assertEqual(value(block, "clash rate"), "2/5",
                         "the clash rate must be members left out over pairs tried (2 of 5), not every conflicting merge (3)")


class MainClash(unittest.TestCase):
    """Each queued member is merge-tested against origin/main before it pairs (reading f). A member that clashes with main leaves by name,
    with its paths and `(clash with main)`, and its merges with main are no pair tried. origin/main moves after the PRs are cut, so
    a tool that read root's own main would not see the clash."""

    def _main_moved_past_pr1(self):
        root = make_repo({"x.txt": "line a\n", "README.md": "x\n"}, checks=READY)
        heads = [(1, add_pr(root, 1, {"x.txt": "line b\n"})),
                 (2, add_pr(root, 2, {"f2.txt": "2\n"})),
                 (3, add_pr(root, 3, {"f3.txt": "3\n"}))]
        advance_main(root, {"x.txt": "line m\n"})
        return root, queue_file(heads, [("Q", "queued", [1, 2, 3])])

    def test_member_that_clashes_with_main_leaves_by_name_with_its_path(self):
        root, queue = self._main_moved_past_pr1()
        rc, out, err, ci = run_tool(queue, root, clock=ticking_clock())
        order, blocks = batch_blocks(out)
        self.assertEqual(order, ["Q"], "one queued batch must print one batch line, got %r" % order)
        named = [line for line in blocks["Q"] if re.search(r"left out #1\b", line) and "x.txt" in line and "(clash with main)" in line]
        self.assertTrue(named, "#1 clashes with main on x.txt: it must leave by name with its path and (clash with main): %r" % blocks["Q"])

    def test_merges_with_main_are_not_pairs_tried(self):
        root, queue = self._main_moved_past_pr1()
        rc, out, err, ci = run_tool(queue, root, clock=ticking_clock())
        order, blocks = batch_blocks(out)
        self.assertEqual(order, ["Q"], "one queued batch must print one batch line, got %r" % order)
        self.assertEqual(value(blocks["Q"], "clash rate"), "0/1",
                         "the only pair tried is #2 with #3, and it is clean: the merge of #1 with main must not count as a pair")

    def test_header_names_reading_f(self):
        root, queue = self._main_moved_past_pr1()
        rc, out, err, ci = run_tool(queue, root, clock=ticking_clock())
        header = (out.splitlines() or [""])[0]
        self.assertIn("(f)", header, "the header must name reading (f), the test of each member against main: %r" % header)


class ExitCodes(unittest.TestCase):
    def test_exit_0_when_members_fold_clean_and_checks_pass(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        heads = [(n, add_pr(root, n, {"f%d.txt" % n: "%d\n" % n})) for n in (1, 2, 3)]
        queue = queue_file(heads, [("Q", "queued", [1, 2, 3])])
        rc, out, err, ci = run_tool(queue, root, clock=ticking_clock())
        order, blocks = batch_blocks(out)
        self.assertEqual(order, ["Q"], "a clean run must still print its batch line: got %r" % order)
        self.assertTrue(ci, "a clean run with a home for the checks must run them")
        self.assertEqual(rc, 0, "clean members with passing checks must exit 0")

    def test_exit_1_when_a_member_is_left_out(self):
        root = make_repo({"x.txt": "line a\n"}, checks=READY)
        heads = [(1, add_pr(root, 1, {"x.txt": "line b\n"})), (2, add_pr(root, 2, {"x.txt": "line c\n"}))]
        queue = queue_file(heads, [("Q", "queued", [1, 2])])
        rc, out, err, ci = run_tool(queue, root, clock=ticking_clock())
        self.assertEqual(rc, 1, "a member left out must exit 1")

    def test_exit_2_when_the_queue_file_is_missing(self):
        self.assertTrue(os.path.exists(TOOL), "the tool file is absent, so this run proves nothing: %s" % TOOL)
        root = make_repo({"README.md": "x\n"}, checks=READY)
        absent = os.path.join(scratch("absent-"), "queue.json")
        r = subprocess.run([sys.executable, TOOL, "--queue", absent, "--root", root], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, "a queue file that cannot be read is cannot-run: exit 2, got %d" % r.returncode)
        self.assertIn(absent, r.stdout + r.stderr, "a missing queue file must be named in the refusal")


class EmptyQueue(unittest.TestCase):
    def test_empty_queue_prints_a_header_and_no_batch_and_exits_0(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        queue = queue_file([], [])
        rc, out, err, ci = run_tool(queue, root, clock=ticking_clock())
        self.assertTrue(out.strip(), "an empty queue must still print the header line; the tool printed nothing")
        self.assertEqual(batch_blocks(out)[0], [], "an empty queue has no batch to print")
        self.assertEqual(rc, 0, "an empty queue has nothing left out and nothing failed: exit 0")


class MergeWrapperOnly(unittest.TestCase):
    def test_tool_reaches_merge_py_only_through_the_git_wrapper_and_the_one_ci_job_run(self):
        self.assertTrue(os.path.exists(TOOL), "the tool file is absent: %s" % TOOL)
        used = merge_names_used(TOOL)
        self.assertTrue(used, "the tool uses no merge.py helper, so its dry folds do not go through merge.merge_tree")
        self.assertTrue(used & {"merge_tree", "conflicting_files"},
                        "the dry folds must use merge.merge_tree or merge.conflicting_files, it uses %s" % sorted(used))
        self.assertLessEqual(used, GIT_WRAPPERS,
                             "the tool reaches into merge.py beyond the git wrapper and the one ci-job run: %s" % sorted(used - GIT_WRAPPERS))


class BuildControls(unittest.TestCase):
    """Green on the old code too: the fixtures fold the way the dry run reads them, so a red elsewhere is the build's."""

    def test_control_twelve_member_queue_folds_clean_in_the_dry_run(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        queue = build_queue(root, add_members(root, TWELVE))
        rc, out, err, _ci = run_tool(queue, root, clock=ticking_clock())
        self.assertIn("members in: 12", out, "the dry run does not read 12 members in: %s" % shown(out, err))
        self.assertIn("members left out: 0", out, "the dry run leaves a member of the clean 12-member fixture out")

    def test_control_clash_with_newest_main_leaves_by_name_in_the_dry_run(self):
        root = make_repo({"README.md": "x\n", "shared.txt": "line a\n"}, checks=READY)
        clash = TWELVE[-1]
        heads = add_members(root, TWELVE[:-1]) + [(clash, add_pr(root, clash, {"shared.txt": "line b\n"}))]
        queue = build_queue(root, heads)
        advance_main(root, {"shared.txt": "line c\n"})
        rc, out, err, _ci = run_tool(queue, root, clock=ticking_clock())
        self.assertIn(clash, left_out_lines(out), "the dry run does not leave #%d out by name when it clashes with main: %s" % (clash, shown(out, err)))


class BuildChain(unittest.TestCase):
    """Twelve members build a first-parent chain of no-ff merges onto the newest main, in queue order (roadmap step combine-train-build)."""

    def test_twelve_members_build_a_first_parent_chain_of_no_ff_merges(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        heads = add_members(root, TWELVE)
        queue = build_queue(root, heads)
        base = git_ok(root, "rev-parse", "origin/main").strip()
        rc, out, err, _ci = run_build(root, queue)
        self.assertEqual(rc, 0, "a clean 12-member build exits %s, not 0: %s" % (rc, shown(out, err)))
        branch = merge.integration_branch(BUILD_NAME)
        chain = first_parent_chain(root, branch, base)
        self.assertIsNotNone(chain, "the build left no %s branch in the root; the run ended with: %s" % (branch, shown(out, err)))
        self.assertEqual(len(chain), 12, "%s holds %d commits above origin/main, not 12 merges; the run ended with: %s" % (branch, len(chain), shown(out, err)))
        self.assertTrue(all(p2 for _sha, _p1, p2 in chain), "%s has a commit on its first-parent chain with one parent: not a no-ff merge" % branch)
        self.assertEqual(chain[0][1], base, "the chain does not start at origin/main: its oldest merge's first parent is another commit")
        self.assertEqual([p1 for _s, p1, _p2 in chain[1:]], [s for s, _p1, _p2 in chain[:-1]], "the first parents do not chain: a merge does not sit on the one before it")
        self.assertEqual([p2 for _s, _p1, p2 in chain], [h for _n, h in heads], "the second parents are not the 12 member heads in queue order")


class BuildMergeAloneUnderTen(unittest.TestCase):
    """Under the threshold of 10 ready members the run prints `merge alone` and builds no integration branch (ruling 10:23 CST Nov 20)."""

    def test_nine_members_print_merge_alone_and_build_no_branch(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        queue = build_queue(root, add_members(root, NINE))
        rc, out, err, _ci = run_build(root, queue)
        self.assertTrue(any("merge alone" in line for line in out.splitlines()), "nine members under the threshold of 10 print no 'merge alone' line; the run ended with: %s" % shown(out, err))
        self.assertEqual(rc, 3, "nine members under the threshold of 10 exit %s, not 3 (merge alone has its own exit code): %s" % (rc, shown(out, err)))
        alone = [line for line in out.splitlines() if "merge alone" in line]
        self.assertTrue(alone and "no integration branch built" in alone[0], "the merge alone line does not say 'no integration branch built': %s" % shown(out, err))
        self.assertFalse(branch_exists(root, merge.integration_branch(BUILD_NAME)), "nine members under the threshold of 10 made an integration branch")

    def test_empty_queue_prints_merge_alone_and_builds_no_branch(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        queue = build_queue(root, [])
        rc, out, err, _ci = run_build(root, queue)
        self.assertTrue(any("merge alone" in line for line in out.splitlines()), "an empty queue prints no 'merge alone' line; the run ended with: %s" % shown(out, err))
        self.assertEqual(rc, 3, "an empty queue under the threshold of 10 exits %s, not 3 (merge alone has its own exit code): %s" % (rc, shown(out, err)))
        alone = [line for line in out.splitlines() if "merge alone" in line]
        self.assertTrue(alone and "no integration branch built" in alone[0], "the merge alone line does not say 'no integration branch built': %s" % shown(out, err))
        self.assertFalse(branch_exists(root, merge.integration_branch(BUILD_NAME)), "an empty queue made an integration branch")


class BuildBoundaryAtTen(unittest.TestCase):
    """Ten ready members are the backlog the threshold names, so they build; nine print merge alone (BuildMergeAloneUnderTen) (ruling 10:23 CST Nov 20)."""

    def test_ten_members_build_a_chain_of_ten_no_ff_merges(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        heads = add_members(root, TEN)
        queue = build_queue(root, heads)
        base = git_ok(root, "rev-parse", "origin/main").strip()
        rc, out, err, _ci = run_build(root, queue)
        branch = merge.integration_branch(BUILD_NAME)
        chain = first_parent_chain(root, branch, base)
        self.assertIsNotNone(chain, "ten members left no %s branch in the root; the run ended with: %s" % (branch, shown(out, err)))
        self.assertEqual(len(chain), 10, "%s holds %d commits above origin/main, not 10 merges; the run ended with: %s" % (branch, len(chain), shown(out, err)))
        self.assertEqual([p2 for _s, _p1, p2 in chain], [h for _n, h in heads], "the second parents are not the 10 member heads in queue order")
        self.assertFalse(any("merge alone" in line for line in out.splitlines()), "ten members at the threshold print 'merge alone'")


class BuildLeavesMovedHeadByName(unittest.TestCase):
    """A member whose live head moved after it was queued leaves by name; the chain keeps the other eleven and neither head of that member."""

    def test_member_whose_live_head_moved_since_folding_leaves_by_name(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        heads = add_members(root, TWELVE)
        queue = build_queue(root, heads)
        moved_number, folded = TWELVE[-1], heads[-1][1]
        moved = move_pr(root, moved_number, {"f%d.txt" % moved_number: "moved\n"})
        rc, out, err, _ci = run_build(root, queue)
        self.assertEqual(rc, 1, "a build that leaves #%d out for a moved head exits %s, not 1: %s" % (moved_number, rc, shown(out, err)))
        self.assertIn(moved_number, left_out_lines(out), "the build did not leave #%d out by name though its live head moved; the run ended with: %s" % (moved_number, shown(out, err)))
        base = git_ok(root, "rev-parse", "origin/main").strip()
        chain = first_parent_chain(root, merge.integration_branch(BUILD_NAME), base)
        self.assertIsNotNone(chain, "the build left no %s branch in the root, so the other members cannot be checked" % merge.integration_branch(BUILD_NAME))
        self.assertEqual(len(chain), 11, "the batch holds %d merges, not the 11 members whose heads did not move" % len(chain))
        seconds = [p2 for _s, _p1, p2 in chain]
        self.assertNotIn(folded, seconds, "the queued head of #%d is a second parent though its live head moved" % moved_number)
        self.assertNotIn(moved, seconds, "the moved live head of #%d is a second parent of the batch" % moved_number)


class BuildLeavesClashByName(unittest.TestCase):
    """A member that clashes with the newest main leaves by name with its path. No conflict is fixed by hand: the batch keeps main's text."""

    def test_member_that_clashes_with_newest_main_leaves_by_name_and_no_conflict_is_fixed_by_hand(self):
        root = make_repo({"README.md": "x\n", "shared.txt": "line a\n"}, checks=READY)
        clash = TWELVE[-1]
        heads = add_members(root, TWELVE[:-1]) + [(clash, add_pr(root, clash, {"shared.txt": "line b\n"}))]
        queue = build_queue(root, heads)
        newest = advance_main(root, {"shared.txt": "line c\n"})
        rc, out, err, _ci = run_build(root, queue)
        left = left_out_lines(out)
        self.assertIn(clash, left, "the build did not leave #%d out by name though it clashes with the newest main; the run ended with: %s" % (clash, shown(out, err)))
        self.assertIn("shared.txt", left[clash], "the left-out line of #%d does not name its conflicting path: %r" % (clash, left[clash]))
        branch = merge.integration_branch(BUILD_NAME)
        chain = first_parent_chain(root, branch, newest)
        self.assertIsNotNone(chain, "the build left no %s branch in the root, so no clash can be checked" % branch)
        self.assertEqual(len(chain), 11, "the batch holds %d merges, not the 11 members that clash with nothing" % len(chain))
        self.assertNotIn(heads[-1][1], [p2 for _s, _p1, p2 in chain], "the clashing head of #%d is a second parent of the batch" % clash)
        self.assertEqual(git_ok(root, "show", "%s:shared.txt" % branch), "line c\n", "shared.txt on the batch is not the newest main's text: a conflict was fixed by hand, or the clash went in")


class BuildMakesNoPush(unittest.TestCase):
    """The build pushes nothing and opens, readies and merges no pull request: the git and gh shims log every call."""

    def test_build_makes_no_git_push_and_no_gh_pr_create_ready_or_merge_call(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        heads = add_members(root, TWELVE)
        queue = build_queue(root, heads)
        base = git_ok(root, "rev-parse", "origin/main").strip()
        shims, shim_log = write_shims()
        run_build(root, queue, shims=shims)
        self.assertIsNotNone(first_parent_chain(root, merge.integration_branch(BUILD_NAME), base), "the build made no integration branch, so the push check below proves nothing")
        shim = calls(shim_log)
        git_calls = [c[1:] for c in shim if c[0] == "git"]
        gh_calls = [c[1:] for c in shim if c[0] == "gh"]
        self.assertEqual([a for a in git_calls if "push" in a], [], "the build ran git push")
        self.assertEqual([a for a in gh_calls if a[:2] in (["pr", "create"], ["pr", "ready"], ["pr", "merge"])], [], "the build ran gh pr create, ready or merge")


class BuildPrintsFreezeBlock(unittest.TestCase):
    """The printed body is the freeze block: it reads back through merge.parse_freeze and is an integration PR of its batch (ruling own-811-c-marker-line)."""

    def test_printed_freeze_block_round_trips_through_parse_freeze_and_is_integration_pr(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        heads = add_members(root, TWELVE)
        queue = build_queue(root, heads)
        rc, out, err, _ci = run_build(root, queue)
        begins, ends, body = printed_block(out)
        self.assertEqual((begins, ends), (1, 1), "the build printed %d begin and %d end markers, not one pair; the run ended with: %s" % (begins, ends, shown(out, err)))
        self.assertIsNotNone(body, "the printed freeze block does not run from its begin marker to its end marker")
        block = merge.parse_freeze(body)
        self.assertEqual(block["name"], BUILD_NAME, "parse_freeze reads the batch name as %r, not %r" % (block["name"], BUILD_NAME))
        self.assertEqual(block["lanes"], dict(heads), "parse_freeze reads the lanes as %r, not the 12 member heads" % (block["lanes"],))
        branch = merge.integration_branch(BUILD_NAME)
        self.assertTrue(merge.is_integration_pr({"branch": branch, "body": body}), "is_integration_pr says the printed body is not an integration PR of %s" % branch)


class BuildReadsReviewedRows(unittest.TestCase):
    """--build with no --queue reads its members from merge.reviewed_read's rows whose act is batch, and the front PR (the first such
    row) is no member (ruling 10:23 CST Nov 20; merge.py:6230). Each case stubs the reader, and every PR head is served on the origin."""

    def build_from(self, rows, bases=None, no_pull=()):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        numbers = [n for n, _act in rows]
        heads = dict(add_members(root, numbers))
        publish_pull(root, numbers)
        stub = reviewed_stub(rows, heads, bases, no_pull=no_pull)
        shims, _log = write_shims()
        base = git_ok(root, "rev-parse", "origin/main").strip()
        rc, out, err, _ci = run_reviewed_build(root, stub, shims=shims)
        chain = first_parent_chain(root, merge.integration_branch(BUILD_NAME), base)
        return heads, stub, rc, out, err, chain

    def test_rows_whose_act_is_not_batch_are_left_out_of_the_batch(self):
        heads, stub, rc, out, err, chain = self.build_from(BATCH_ROWS + OTHER_ROWS)
        self.assertTrue(stub.calls, "the build with no --queue did not read merge.reviewed_read; the run ended with: %s" % shown(out, err))
        self.assertEqual(rc, 0, "the build with no --queue exits %s, not 0: %s" % (rc, shown(out, err)))
        self.assertIsNotNone(chain, "the build left no %s branch in the root; the run ended with: %s" % (merge.integration_branch(BUILD_NAME), shown(out, err)))
        folded = [p2 for _s, _p1, p2 in chain]
        other = [heads[n] for n, _act in OTHER_ROWS]
        self.assertEqual([h for h in folded if h in other], [], "rows whose act is not batch are folded into the batch as members")
        self.assertEqual(len(chain), len(MEMBERS), "the batch holds %d merges, not the %d batch members behind the front" % (len(chain), len(MEMBERS)))

    def test_front_pr_is_no_member_of_the_batch(self):
        heads, stub, rc, out, err, chain = self.build_from([(100, "lane lint")] + BATCH_ROWS)
        self.assertTrue(stub.calls, "the build with no --queue did not read merge.reviewed_read; the run ended with: %s" % shown(out, err))
        self.assertEqual(rc, 0, "the build with no --queue exits %s, not 0: %s" % (rc, shown(out, err)))
        self.assertIsNotNone(chain, "the build left no %s branch in the root; the run ended with: %s" % (merge.integration_branch(BUILD_NAME), shown(out, err)))
        folded = [p2 for _s, _p1, p2 in chain]
        self.assertNotIn(heads[FRONT], folded, "the front PR #%d is folded in as a member of the batch" % FRONT)
        self.assertEqual(folded, [heads[n] for n in MEMBERS], "the batch is not the members #%d to #%d in order behind the front" % (MEMBERS[0], MEMBERS[-1]))

    def test_batch_row_on_a_stacked_base_is_no_member_and_no_front(self):
        rows = [(n, "batch") for n in range(101, 114)]
        heads, stub, rc, out, err, chain = self.build_from(rows, bases=STACKED)
        self.assertTrue(stub.calls, "the build with no --queue did not read merge.reviewed_read; the run ended with: %s" % shown(out, err))
        self.assertEqual(rc, 0, "the build with no --queue exits %s, not 0: %s" % (rc, shown(out, err)))
        self.assertIsNotNone(chain, "the build left no %s branch in the root; the run ended with: %s" % (merge.integration_branch(BUILD_NAME), shown(out, err)))
        on_main = [n for n in range(101, 114) if n not in STACKED]  # #102 is the first row on main, so the front; #103 to #113 on main are the members
        by_head = {sha: n for n, sha in heads.items()}
        folded = [p2 for _s, _p1, p2 in chain]
        self.assertEqual([by_head.get(h, h) for h in folded], on_main[1:],
                         "a batch row whose base is not main is in the batch: the batch folds %s, not the members %s behind the front #%d (the rows on %s are #%d and #%d)"
                         % (["#%s" % by_head.get(h, h) for h in folded], ["#%d" % n for n in on_main[1:]], on_main[0], STACKED_BASE, *sorted(STACKED)))

    def test_batch_row_on_main_stays_a_member(self):
        on_main = {n: "main" for n in STACKED}  # the same rows as the case above, each base set to main: only the base differs
        rows = [(n, "batch") for n in range(101, 114)]
        heads, stub, rc, out, err, chain = self.build_from(rows, bases=on_main)
        self.assertTrue(stub.calls, "the build with no --queue did not read merge.reviewed_read; the run ended with: %s" % shown(out, err))
        self.assertEqual(rc, 0, "the build with no --queue exits %s, not 0: %s" % (rc, shown(out, err)))
        self.assertIsNotNone(chain, "the build left no %s branch in the root; the run ended with: %s" % (merge.integration_branch(BUILD_NAME), shown(out, err)))
        folded = [p2 for _s, _p1, p2 in chain]
        self.assertEqual(folded, [heads[n] for n in range(102, 114)], "a batch row on main is not a member of the batch: the members #102 to #113 behind the front #101 are not all folded")

    def test_batch_row_with_no_pull_exits_2_naming_it_and_makes_no_branch(self):
        heads, stub, rc, out, err, chain = self.build_from([(n, "batch") for n in TWELVE], no_pull=(NO_PULL,))
        self.assertTrue(stub.calls, "the build with no --queue did not read merge.reviewed_read; the run ended with: %s" % shown(out, err))
        self.assertEqual(rc, 2, "a batch row with no pull exits %s, not 2: %s" % (rc, shown(out, err)))
        unknown = [line for line in out.splitlines() if line.startswith("unknown")]
        self.assertTrue(unknown and ("#%d" % NO_PULL) in unknown[0], "the unknown line does not name #%d, the batch row with no pull: %s" % (NO_PULL, shown(out, err)))
        self.assertIsNone(chain, "a batch row with no pull still made the %s branch" % merge.integration_branch(BUILD_NAME))


class BuildExitCodes(unittest.TestCase):
    """Green controls on the old code too: the exit codes the build keeps for an existing branch (2, and the branch kept) and for a failed
    live-head read (2, named by ls-remote). The fixtures use the queue file the old code reads, so a red elsewhere is the build's."""

    def test_existing_branch_is_refused_with_exit_2_and_kept(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        queue = build_queue(root, add_members(root, TWELVE))
        branch = merge.integration_branch(BUILD_NAME)
        git_ok(root, "branch", branch, "origin/main")
        before = git_ok(root, "rev-parse", "refs/heads/" + branch).strip()
        rc, out, err, _ci = run_build(root, queue)
        self.assertEqual(rc, 2, "a build onto the existing branch %s exits %s, not 2: %s" % (branch, rc, shown(out, err)))
        self.assertIn(branch, out, "the refusal does not name the existing branch %s: %s" % (branch, shown(out, err)))
        self.assertEqual(git_ok(root, "rev-parse", "refs/heads/" + branch).strip(), before, "the existing branch %s was replaced" % branch)

    def test_failed_live_head_read_exits_2_and_is_named_by_ls_remote(self):
        root = make_repo({"README.md": "x\n"}, checks=READY)
        queue = build_queue(root, add_members(root, TWELVE))
        shims, _log = write_shims(refuse=("ls-remote",))
        rc, out, err, _ci = run_build(root, queue, shims=shims)
        self.assertEqual(rc, 2, "a failed live-head read exits %s, not 2: %s" % (rc, shown(out, err)))
        self.assertIn("ls-remote", out, "the unknown line does not name the failed ls-remote read: %s" % shown(out, err))
        self.assertFalse(branch_exists(root, merge.integration_branch(BUILD_NAME)), "a failed live-head read still built an integration branch")

    def test_failed_reviewed_read_exits_2_unknown_and_makes_no_branch(self):
        import combine_train  # the tool; imported in the case, so a missing tool fails this case alone
        root = make_repo({"README.md": "x\n"}, checks=READY)
        heads = dict(add_members(root, TWELVE))
        publish_pull(root, TWELVE)
        stub = reviewed_stub([(n, "batch") for n in TWELVE], heads, fail=OSError("the reader is down"))
        try:
            rc, out, err, _ci = run_reviewed_build(root, stub)
        except combine_train.ReadError as e:
            self.fail("a failed merge.reviewed_read left main as ReadError instead of exiting 2 unknown: %s" % e)
        self.assertEqual(rc, 2, "a failed merge.reviewed_read exits %s, not 2: %s" % (rc, shown(out, err)))
        self.assertTrue(any(line.startswith("unknown") for line in out.splitlines()), "a failed merge.reviewed_read prints no unknown line: %s" % shown(out, err))
        self.assertFalse(branch_exists(root, merge.integration_branch(BUILD_NAME)), "a failed merge.reviewed_read still built an integration branch")

    def test_failed_main_fetch_exits_2_names_it_and_makes_no_branch(self):
        import combine_train  # the tool; imported in the case, so a missing tool fails this case alone
        root = make_repo({"README.md": "x\n"}, checks=READY)
        queue = build_queue(root, add_members(root, TWELVE))
        refspec = "+refs/heads/%s:refs/remotes/%s" % (combine_train.BASE.split("/", 1)[1], combine_train.BASE)
        shims, shim_log = write_shims(refuse=("push", refspec))
        rc, out, err, _ci = run_build(root, queue, shims=shims)
        self.assertTrue([c for c in calls(shim_log) if c[0] == "git" and refspec in c[1:]], "the build never ran the fetch of main, so the refusal proves nothing: %s" % shown(out, err))
        self.assertEqual(rc, 2, "a failed fetch of main exits %s, not 2: %s" % (rc, shown(out, err)))
        self.assertTrue(any(line.startswith("unknown") and "fetch of main failed" in line for line in out.splitlines()), "the unknown line does not name the failed fetch of main: %s" % shown(out, err))
        self.assertFalse(branch_exists(root, merge.integration_branch(BUILD_NAME)), "a failed fetch of main still built an integration branch")


class BuildThresholdHasOneHome(unittest.TestCase):
    """merge.BUILD_THRESHOLD is the one home of the ready count that builds a train. The tool takes its threshold from it, and does not keep a
    number of its own, so the lane lint's hint and the tool cannot disagree about when a train is built."""

    def test_the_tool_takes_its_build_threshold_from_merge(self):
        import combine_train  # the tool; imported in the case, so a missing tool fails this case alone
        with open(TOOL, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        assigned = [node.value for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "BUILD_THRESHOLD" for t in node.targets)]
        self.assertEqual(len(assigned), 1, "combine_train.py assigns BUILD_THRESHOLD %d times, want once" % len(assigned))
        value = assigned[0]
        self.assertTrue(isinstance(value, ast.Attribute) and value.attr == "BUILD_THRESHOLD" and isinstance(value.value, ast.Name) and value.value.id == "merge",
                        "combine_train.py sets BUILD_THRESHOLD to something other than merge.BUILD_THRESHOLD, so the threshold has a second home")
        self.assertIsNotNone(getattr(merge, "BUILD_THRESHOLD", None), "merge.py names no BUILD_THRESHOLD, so the tool has no home for its threshold")
        self.assertEqual(combine_train.BUILD_THRESHOLD, merge.BUILD_THRESHOLD, "combine_train.BUILD_THRESHOLD is not merge.BUILD_THRESHOLD")


if __name__ == "__main__":
    unittest.main(verbosity=2)
