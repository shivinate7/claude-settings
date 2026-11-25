#!/usr/bin/env python3
"""Cases for lint/conflict_hotspots.py. Standard library only; needs git 2.38 or newer on PATH.

    python3 lint/test_conflict_hotspots.py

The script ranks the files that merges conflict on. It finds each merge of two heads since a date (a merge of main
into a branch, and a merge on main whose second parent is a branch) and replays it with
`git merge-tree --write-tree --name-only`. The contract the cases hold, which the builder prints exactly:

    base: <name> <sha9>           the first line: the base the run read and its commit, the first 9 hex digits
    merges replayed: N            every merge the script replayed, an unknown one too
    merges conflicted: M
    merges unknown: U             a replay whose read failed (git exit other than 0 or 1): counted as replayed, never as clean
    conflict rate: R%             conflicted / replayed in percent, one decimal place; 0.0% when nothing was replayed
    merges not replayed: K (octopus O, off base B)
    <count> <path>               one row per conflicted file: count descending, then path ascending; the path is
                                  unquoted and printed as UTF-8
    cost: merge-trees N, wall S s N is the merge-tree process starts; S is wall seconds
    caveat: <text>                three lines after the cost line, in this order: a replay is what git finds now, not
                                  what the author resolved; squash and rebase merges leave no merge commit, so they are
                                  absent; refs walked: all

Options. Without the flags below the output above is unchanged. The base line and the caveats always print.

    --base NAME                   the ref whose history a merge must touch. Default: origin/main when
                                  refs/remotes/origin/main exists, else main. The base line names the one read.
    --exposure                    each row reads `<conflicts>/<exposure> <path>`, not `<count> <path>`. Exposure is
                                  the replayed merges where both sides changed the file: it differs from the merge
                                  base on each parent. A file no merge conflicts on is no row at any exposure, so the
                                  rows are the same set as without the flag: no row reads `0/N`.
    --into-branches               the filter runs before every count: only a merge of the base INTO a branch counts.
                                  Its first parent is the branch, off the base's first-parent line, and its second
                                  parent is on that line. A merge whose first parent is on the line (a branch merged
                                  into main, or any merge off a main-line commit) is dropped, as are a PR merge into
                                  main, a merge of two branches, and a merge with no main parent. They appear in no
                                  line, `merges not replayed` included.
    --list                        after the file rows, one line per conflicted merge: `merge <sha9> <paths>`, the merge
                                  commit and the files git names, so a reader can check one by hand.
    --since DATE                  YYYY-MM-DD and no other form, a real calendar date. Any other value is refused.
    --top N                       N below 1 is refused.

Summary lines start with a letter, rows with a digit, the cost line with `cost`, caveat lines with `caveat: `. Exit
codes: 0 for a report (zero merges included); 1 for a bad argument (--since, --top) or any other failure, one line;
2 for a git too old for `merge-tree --write-tree`, with one line of output that names merge-tree, --write-tree or 2.38;
3 for a history cut at depth (a shallow clone). Exit 3 is one line: `history is cut at depth ...; counts are a lower
bound`, and no report follows it. The contract had no exit code for unknown, so 3 is pinned here.

Git and temp contract: the script runs git by its name on PATH, one merge-tree per replay. Its object folder is a
fresh folder under TMPDIR (GIT_OBJECT_DIRECTORY). The script makes no clone. It removes that folder before
it exits, also when KeyboardInterrupt stops the run. It writes nothing into the repo it reads.

Fixtures are built with plain git under the run folder (lint/_test_temp.py). Every commit and merge has a fixed date,
and the cases never read the clock. Each case holds one scenario: the one-merge and clean fixtures, the two-kind and
ranking fixture (`selection`), the tie fixture, the rename/delete fixture, the non-ASCII fixture, the old-only fixture
(zeros), the missing-blob fixture (unknown), the exposure fixture (`exposure`), the into-branches fixtures
(`into_branches`, `pr_parent`, a branch merge whose parent reaches main only through a PR, and `into_first_parent`, a
branch merge whose first parent is on main's line), the remote fixture (`remote_behind`, a remote main that the local
main misses), and the clones (`clone_of`, shallow with depth 1, or whole). A git shim on PATH logs or fails the
merge-tree calls.
"""
import collections
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402  the one home of the commit-signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

MODULE = os.path.join(HERE, "conflict_hotspots.py")
REAL_GIT = shutil.which("git")
SINCE = "2026-11-18"
DAY1 = "2026-11-19T10:00:00+0000"
DAY2 = "2026-11-20T10:00:00+0000"
OLD = "2026-11-10T10:00:00+0000"  # before SINCE: a merge this old is not replayed
# The variables that point git at a repo or an object folder. A caller's value would send each git call elsewhere.
STRIP = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
         "GIT_COMMON_DIR")
NO_HOOKS = "no-hooks"  # a folder that does not exist, so git runs no hook of the caller's
COST = re.compile(r"^cost: merge-trees (\d+), wall (\d+(?:\.\d+)?) s$", re.MULTILINE)
RUN = None
# A git on PATH for the shim: the real one, found before any test changes PATH.
SHIM = '''#!@PY@
import json
import os
import signal
import sys

REAL = @REAL@
MODE = @MODE@
LOG = @LOG@
args = sys.argv[1:]
if MODE == "old" and args == ["--version"]:
    print("git version 2.37.0")
    sys.exit(0)
if "merge-tree" in args:
    if MODE == "old":
        sys.stderr.write("error: unknown option `write-tree'\\n")
        sys.exit(129)
    with open(LOG, "a", encoding="utf-8") as log:
        log.write(json.dumps({"cwd": os.getcwd(), "objdir": os.environ.get("GIT_OBJECT_DIRECTORY")}) + "\\n")
    if MODE == "interrupt":
        os.kill(os.getppid(), signal.SIGINT)
os.execv(REAL, [REAL] + args)
'''


def setUpModule():
    global RUN
    RUN = _test_temp.run_folder()  # test-temp-standard: this run's folder, and the sweep of old siblings
    with open(os.path.join(RUN, "empty.gitconfig"), "w", encoding="utf-8"):
        pass


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def base_env(run):
    """The caller environment minus the repo pointers, with git's global and system config off and the opt-out kept."""
    env = {k: v for k, v in os.environ.items() if k not in STRIP}
    env["GIT_CONFIG_GLOBAL"] = os.path.join(run, "empty.gitconfig")
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return _test_git.apply(env)


def fixture_env(run, date):
    env = base_env(run)
    env.update({"GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
                "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
                "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date})
    return env


class Fixture:
    """One fixture repo under the run folder, built with plain git. Every write takes a fixed date."""

    def __init__(self, name):
        self.path = os.path.join(RUN, name)
        os.makedirs(self.path)
        self.git("init", "-q", "-b", "main")

    def git(self, *args, date=DAY1, check=True):
        cmd = ["git", "-C", self.path, "-c", "core.hooksPath=" + os.path.join(RUN, NO_HOOKS),
               "-c", "rerere.enabled=false", "-c", "gc.auto=0"] + list(args)
        p = subprocess.run(cmd, env=fixture_env(RUN, date), capture_output=True, text=True, encoding="utf-8")
        if check and p.returncode:
            raise RuntimeError("fixture git %s failed (%d): %s" % (" ".join(args), p.returncode, p.stderr.strip()))
        return p

    def write(self, name, text):
        with open(os.path.join(self.path, name), "w", encoding="utf-8", newline="") as f:
            f.write(text)

    def commit(self, message, date, paths=None):
        if paths is None:
            self.git("add", "-A", date=date)
        else:
            self.git("add", "--", *paths, date=date)
        self.git("commit", "-q", "-m", message, date=date)

    def branch(self, name, start):
        self.git("checkout", "-q", "-b", name, start)

    def checkout(self, name):
        self.git("checkout", "-q", name)

    def edit(self, name, files, message, date):
        self.checkout(name)
        for path, text in files.items():
            self.write(path, text)
        self.commit(message, date, paths=sorted(files))

    def unmerged(self):
        out = self.git("diff", "--name-only", "--diff-filter=U", "-z").stdout
        return [p for p in out.split("\0") if p]

    def merge(self, into, other, date, conflict=False, resolve=None):
        """Merge `other` into `into` with --no-ff. A conflicting merge resolves each unmerged path to `resolve[path]`,
        or to a fixed line, and commits: that merge commit is one of the merges the script replays."""
        self.checkout(into)
        p = self.git("merge", "--no-ff", "--no-edit", other, date=date, check=False)
        if not conflict:
            if p.returncode:
                raise RuntimeError("fixture merge of %s into %s conflicted" % (other, into))
            return
        if p.returncode == 0:
            raise RuntimeError("fixture merge of %s into %s did not conflict" % (other, into))
        for path in self.unmerged():
            self.write(path, (resolve or {}).get(path, "resolved\n"))
            self.git("add", "--", path, date=date)
        self.git("commit", "-q", "--no-edit", date=date)

    def remove_loose(self, rev_path):
        sha = self.git("rev-parse", rev_path).stdout.strip()
        path = os.path.join(self.path, ".git", "objects", sha[:2], sha[2:])
        if not os.path.isfile(path):
            raise RuntimeError("blob %s is not a loose object, so the fixture cannot drop it" % sha)
        os.remove(path)

    def merges(self):
        return self.git("log", "--all", "--merges", "--format=%H").stdout.split()

    def snapshot(self):
        objects = set()
        for dirpath, _, names in os.walk(os.path.join(self.path, ".git", "objects")):
            for name in names:
                objects.add(os.path.relpath(os.path.join(dirpath, name), self.path))
        refs = self.git("for-each-ref", "--format=%(refname) %(objectname)").stdout
        status = self.git("status", "--porcelain").stdout
        return objects, refs, status


def single_conflict(name, paths=("a.txt",)):
    """Main and feature edit each path differently; main merges into feature: one merge, one conflict per path."""
    fx = Fixture(name)
    for path in paths:
        fx.write(path, "one\n")
    fx.commit("c0", DAY1)
    fx.branch("f", "main")
    fx.edit("f", {p: "feature\n" for p in paths}, "f1", DAY1)
    fx.edit("main", {p: "main\n" for p in paths}, "m1", DAY1)
    fx.merge("f", "main", DAY2, conflict=True)
    return fx


def clean_merge(name):
    fx = Fixture(name)
    fx.write("a.txt", "one\n")
    fx.write("b.txt", "one\n")
    fx.commit("c0", DAY1)
    fx.branch("f", "main")
    fx.edit("f", {"b.txt": "feature\n"}, "f1", DAY1)
    fx.edit("main", {"a.txt": "main\n"}, "m1", DAY1)
    fx.merge("f", "main", DAY2)
    return fx


def selection(name):
    """Three merges, both kinds. Mf is a merge of main into f (second parent c1 on main), conflicting on z.txt. P
    merges f into main (a PR merge, clean): Mf is reachable from two refs, so it must count once. Q merges g into main
    (a PR merge), conflicting on a.txt and z.txt. z.txt then conflicts twice and a.txt once, so z.txt sorts first."""
    fx = Fixture(name)
    fx.write("a.txt", "one\n")
    fx.write("z.txt", "one\n")
    fx.commit("c0", DAY1)
    fx.branch("f", "main")
    fx.branch("g", "main")
    fx.edit("f", {"z.txt": "f-z\n"}, "f1", DAY1)
    fx.edit("g", {"z.txt": "g-z\n", "a.txt": "g-a\n"}, "g1", DAY1)
    fx.edit("main", {"z.txt": "m-z\n"}, "c1", DAY1)
    fx.merge("f", "main", DAY2, conflict=True, resolve={"z.txt": "f-merged\n"})
    fx.merge("main", "f", DAY2)
    fx.edit("main", {"a.txt": "m-a\n", "z.txt": "m-z2\n"}, "c2", DAY2)
    fx.merge("main", "g", DAY2, conflict=True, resolve={"a.txt": "merged-a\n", "z.txt": "merged-z\n"})
    return fx


def ties(name):
    """Two merges, each conflicting on one different file. Newest first, c.txt comes before b.txt, so a count
    kept in first-seen order would put c.txt first. Both have count 1: path order decides."""
    fx = Fixture(name)
    fx.write("b.txt", "one\n")
    fx.write("c.txt", "one\n")
    fx.commit("c0", DAY1)
    fx.branch("f", "main")
    fx.edit("f", {"b.txt": "f-b\n"}, "f1", DAY1)
    fx.edit("main", {"b.txt": "m-b\n"}, "m1", DAY1)
    fx.merge("f", "main", DAY1, conflict=True)
    fx.edit("f", {"c.txt": "f-c\n"}, "f2", DAY2)
    fx.edit("main", {"c.txt": "m-c\n"}, "m2", DAY2)
    fx.merge("f", "main", DAY2, conflict=True)
    return fx


def rename_delete(name):
    """Feature renames r.txt to renamed.txt; main deletes r.txt. Main merges into feature: a rename/delete conflict."""
    fx = Fixture(name)
    fx.write("r.txt", "one\n")
    fx.commit("c0", DAY1)
    fx.branch("ren", "main")
    fx.git("mv", "r.txt", "renamed.txt")
    fx.git("commit", "-q", "-m", "rename")
    fx.checkout("main")
    fx.git("rm", "-q", "r.txt")
    fx.git("commit", "-q", "-m", "delete")
    fx.merge("ren", "main", DAY2, conflict=True)
    return fx


def old_only(name):
    """One conflicting merge, dated before SINCE, and nothing since."""
    fx = Fixture(name)
    fx.write("a.txt", "one\n")
    fx.commit("c0", OLD)
    fx.branch("f", "main")
    fx.edit("f", {"a.txt": "feature\n"}, "f1", OLD)
    fx.edit("main", {"a.txt": "main\n"}, "m1", OLD)
    fx.merge("f", "main", OLD, conflict=True)
    return fx


def missing_blob(name):
    """A conflicting merge whose main-side blob is dropped from the object store, so the replay cannot read it."""
    fx = single_conflict(name)
    fx.remove_loose("main:a.txt")
    return fx


def exposure(name):
    """Five merges of main into a branch, each replayed. f.txt changes on both sides in merges 1 to 3 and conflicts only
    in merge 2, so its row is 1/3. Merge 4 changes g.txt on both sides and merges clean: g.txt has exposure 1 and no
    conflict, so it is no row. Merge 5 changes f.txt on main's side only, so it adds no exposure to f.txt."""
    fx = Fixture(name)
    fx.write("f.txt", "1\n2\n3\n4\n5\n")
    fx.write("g.txt", "x1\nx2\nx3\n")
    fx.commit("c0", DAY1)
    fx.branch("b1", "main")
    fx.edit("b1", {"f.txt": "A\n2\n3\n4\n5\n"}, "b1", DAY1)
    fx.edit("main", {"f.txt": "1\n2\n3\n4\nE\n"}, "m1", DAY1)
    fx.merge("b1", "main", DAY2)
    fx.branch("b2", "main")
    fx.edit("b2", {"f.txt": "1\n2\nC\n4\nE\n"}, "b2", DAY1)
    fx.edit("main", {"f.txt": "1\n2\nD\n4\nE\n"}, "m2", DAY1)
    fx.merge("b2", "main", DAY2, conflict=True, resolve={"f.txt": "1\n2\nmerged\n4\nE\n"})
    fx.branch("b3", "main")
    fx.edit("b3", {"f.txt": "A\n2\nD\n4\nE\n"}, "b3", DAY1)
    fx.edit("main", {"f.txt": "1\n2\nD\nF\nE\n"}, "m3", DAY1)
    fx.merge("b3", "main", DAY2)
    fx.branch("b4", "main")
    fx.edit("b4", {"g.txt": "y1\nx2\nx3\n"}, "b4", DAY1)
    fx.edit("main", {"g.txt": "x1\nx2\ny3\n"}, "m4", DAY1)
    fx.merge("b4", "main", DAY2)
    fx.branch("b5", "main")
    fx.edit("b5", {"h.txt": "h\n"}, "b5", DAY1)
    fx.edit("main", {"f.txt": "1\nB\nD\nF\nE\n"}, "m5", DAY1)
    fx.merge("b5", "main", DAY2)
    return fx


def into_branches(name):
    """A PR merge of f into main (conflicts on a.txt), a merge of main into g (conflicts on b.txt), and a merge of x and
    y, which touches no main history. --into-branches keeps only the second: replayed 1, its b.txt conflict the only
    row. Without the flag the first two are replayed, and the third is off base."""
    fx = Fixture(name)
    fx.write("a.txt", "one\n")
    fx.write("b.txt", "one\n")
    fx.commit("c0", DAY1)
    for branch in ("f", "g", "x", "y"):
        fx.branch(branch, "main")
    fx.edit("f", {"a.txt": "f-a\n"}, "f1", DAY1)
    fx.edit("g", {"b.txt": "g-b\n"}, "g1", DAY1)
    fx.edit("x", {"x.txt": "x\n"}, "x1", DAY1)
    fx.edit("y", {"y.txt": "y\n"}, "y1", DAY1)
    fx.edit("main", {"a.txt": "m-a\n"}, "m1", DAY1)
    fx.merge("main", "f", DAY2, conflict=True, resolve={"a.txt": "merged-a\n"})
    fx.edit("main", {"b.txt": "m-b\n"}, "m2", DAY2)
    fx.merge("g", "main", DAY2, conflict=True, resolve={"b.txt": "merged-b\n"})
    fx.merge("x", "y", DAY2)
    return fx


def pr_parent(name):
    """A PR merge of f into main, then a merge of f into g. The merge of g reaches f's tip only through the PR's second
    parent: f's tip is not on main's first-parent line, and no parent of the merge is main, so the filter drops it."""
    fx = Fixture(name)
    fx.write("a.txt", "one\n")
    fx.commit("c0", DAY1)
    fx.branch("f", "main")
    fx.branch("g", "main")
    fx.edit("f", {"f.txt": "feature\n"}, "f1", DAY1)
    fx.edit("g", {"g.txt": "g\n"}, "g1", DAY1)
    fx.edit("main", {"a.txt": "m\n"}, "m1", DAY1)
    fx.merge("main", "f", DAY2)
    fx.merge("g", "f", DAY2)
    return fx


def into_first_parent(name):
    """Two merges, one of each first parent. Mg merges main into g: its first parent g1 is off main's line, its second
    m1 is on it, and it conflicts on b.txt. Mh merges f into h, where h starts at main's tip m1: its first parent is on
    main's line, its second is the branch f, and it conflicts on a.txt. --into-branches keeps Mg only. Before the
    first-parent rule, the old filter counted Mh too."""
    fx = Fixture(name)
    fx.write("a.txt", "one\n")
    fx.write("b.txt", "one\n")
    fx.commit("c0", DAY1)
    fx.branch("f", "main")
    fx.branch("g", "main")
    fx.edit("f", {"a.txt": "f-a\n"}, "f1", DAY1)
    fx.edit("g", {"b.txt": "g-b\n"}, "g1", DAY1)
    fx.edit("main", {"a.txt": "m-a\n", "b.txt": "m-b\n"}, "m1", DAY1)
    fx.merge("g", "main", DAY2, conflict=True, resolve={"b.txt": "merged-b\n"})
    fx.branch("h", "main")
    fx.merge("h", "f", DAY2, conflict=True, resolve={"a.txt": "merged-a\n"})
    return fx


def remote_behind(name):
    """A merge of main into f, conflicting on a.txt, with origin/main set to m1, main's tip before the merge. The local
    main is then set back to c0, so it misses both parents of the merge. Only the default base reaches the merge.
    Returns the fixture and m1. The remote is a name in this fixture; nothing is pushed or fetched."""
    fx = Fixture(name)
    fx.write("a.txt", "one\n")
    fx.commit("c0", DAY1)
    c0 = fx.git("rev-parse", "main").stdout.strip()
    fx.branch("f", "main")
    fx.edit("f", {"a.txt": "feature\n"}, "f1", DAY1)
    fx.edit("main", {"a.txt": "main\n"}, "m1", DAY1)
    m1 = fx.git("rev-parse", "main").stdout.strip()
    fx.merge("f", "main", DAY2, conflict=True)
    fx.git("remote", "add", "origin", os.path.join(RUN, name + "-remote"))
    fx.git("update-ref", "refs/remotes/origin/main", m1)
    fx.git("update-ref", "refs/heads/main", c0)
    return fx, m1


def clone_of(fx, name, depth=None):
    """A clone of `fx`, checked out on its branch f, made from file:// so that --depth is honoured. Returns the path.
    With depth, the clone holds only the tip commits up to that depth, and reads as shallow."""
    dest = os.path.join(RUN, name + "-clone")
    cmd = ["git", "clone", "-q", "-b", "f"] + (["--depth", str(depth)] if depth else []) + ["file://" + fx.path, dest]
    p = subprocess.run(cmd, env=fixture_env(RUN, DAY2), capture_output=True, text=True, encoding="utf-8")
    if p.returncode:
        raise RuntimeError("fixture clone failed (%d): %s" % (p.returncode, p.stderr.strip()))
    return dest


Run = collections.namedtuple("Run", "rc out err scratch log")


def make_shim(mode, log):
    """A folder holding a `git` shim, to put first on PATH. mode: "spy" logs each merge-tree call to `log`;
    "interrupt" logs, then sends SIGINT to the script that started it; "old" answers as git 2.37."""
    folder = tempfile.mkdtemp(prefix="shim-", dir=RUN)
    path = os.path.join(folder, "git")
    text = (SHIM.replace("@PY@", sys.executable).replace("@REAL@", repr(REAL_GIT))
            .replace("@MODE@", repr(mode)).replace("@LOG@", repr(log)))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, 0o755)
    return folder


def run_hotspots(repo, shim=None, top="10", since=SINCE, flags=(), base="main"):
    """Run the script on `repo`, with TMPDIR a fresh empty folder under the run folder, and the extra `flags` after the
    fixed arguments. base=None leaves --base off, so the default base applies. Returns a Run."""
    if not os.path.isfile(MODULE):
        raise AssertionError("lint/conflict_hotspots.py is not built")
    scratch = tempfile.mkdtemp(prefix="scratch-", dir=RUN)
    log = os.path.join(RUN, "merge-tree-%s.log" % uuid.uuid4().hex)
    env = base_env(RUN)
    env["TMPDIR"] = scratch
    env["PYTHONIOENCODING"] = "utf-8"
    if shim:
        env["PATH"] = make_shim(shim, log) + os.pathsep + os.environ.get("PATH", "")
    cmd = [sys.executable, MODULE, "--since", since] + (["--base", base] if base else [])
    cmd += ["--top", top, "--repo", repo] + list(flags)
    p = subprocess.run(cmd, cwd=RUN, env=env, capture_output=True, timeout=120)
    return Run(p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace"), scratch, log)


def field(out, label):
    """The text after `label: ` on the summary line that starts with it, or None when no such line prints."""
    for line in out.splitlines():
        if line.startswith(label + ": "):
            return line[len(label) + 2:]
    return None


def rows(out):
    """[(count, path)] for each line that starts with a digit, in printed order."""
    found = []
    for line in out.splitlines():
        head, _, rest = line.partition(" ")
        if head.isdigit() and rest:
            found.append((int(head), rest))
    return found


def exposure_rows(out):
    """[(conflicts, exposure, path)] for each `<conflicts>/<exposure> <path>` row, in printed order."""
    found = []
    for line in out.splitlines():
        m = re.fullmatch(r"(\d+)/(\d+) (.+)", line)
        if m:
            found.append((int(m.group(1)), int(m.group(2)), m.group(3)))
    return found


def cost(out):
    """(merge-tree count, wall text) from the cost line, or None when no cost line prints."""
    m = COST.search(out)
    return (int(m.group(1)), m.group(2)) if m else None


def caveats(out):
    """The lines that start `caveat: `, in printed order."""
    return [line for line in out.splitlines() if line.startswith("caveat: ")]


def output_lines(r):
    """The non-blank lines of a run's stdout and stderr together: the one line a refusal prints."""
    return [line for line in (r.out + r.err).splitlines() if line.strip()]


def read_log(log):
    if not os.path.isfile(log):
        return []
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def temp_paths(entries, scratch):
    """The paths a merge-tree call named as its object folder or its cwd, when they sit under the script's TMPDIR."""
    root = os.path.realpath(scratch) + os.sep
    found = set()
    for entry in entries:
        for key in ("cwd", "objdir"):
            value = entry.get(key)
            if value and os.path.realpath(value).startswith(root):
                found.add(os.path.realpath(value))
    return found


class ConflictHotspotsCases(unittest.TestCase):

    def assert_summary(self, out, replayed, conflicted, unknown, rate):
        self.assertEqual(field(out, "merges replayed"), str(replayed), "merges replayed line")
        self.assertEqual(field(out, "merges conflicted"), str(conflicted), "merges conflicted line")
        self.assertEqual(field(out, "merges unknown"), str(unknown), "merges unknown line")
        self.assertEqual(field(out, "conflict rate"), rate, "conflict rate line")

    def assert_same(self, got, want, cause):
        """assertEqual that keeps the cause. On Python 3.15 unittest drops the message of a text or list assertEqual."""
        self.assertTrue(got == want, "%s: got %r, want %r" % (cause, got, want))

    def test_known_conflict_lists_one_file_with_count_one(self):
        fx = single_conflict("known")
        r = run_hotspots(fx.path)
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        self.assertEqual(field(r.out, "merges replayed"), "1", "merges replayed line")
        self.assertEqual(field(r.out, "merges conflicted"), "1", "merges conflicted line")
        self.assertEqual(rows(r.out), [(1, "a.txt")], "file rows")

    def test_clean_merge_is_replayed_but_not_listed(self):
        fx = clean_merge("clean")
        r = run_hotspots(fx.path)
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        self.assert_summary(r.out, 1, 0, 0, "0.0%")
        self.assertEqual(rows(r.out), [], "file rows: a clean merge lists nothing")

    def test_both_merge_kinds_are_counted_once_with_the_rate(self):
        fx = selection("selection")
        r = run_hotspots(fx.path)
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        self.assertEqual(len(fx.merges()), 3, "fixture merge count")
        self.assert_summary(r.out, 3, 2, 0, "66.7%")

    def test_hot_file_ranks_first_by_count_not_path(self):
        fx = selection("ranking")
        r = run_hotspots(fx.path)
        self.assertEqual(field(r.out, "merges replayed"), "3", "merges replayed line")
        self.assertEqual(rows(r.out), [(2, "z.txt"), (1, "a.txt")], "file rows: count first, then path")

    def test_ties_sort_by_path(self):
        fx = ties("ties")
        r = run_hotspots(fx.path)
        self.assertEqual(field(r.out, "merges replayed"), "2", "merges replayed line")
        self.assertEqual(rows(r.out), [(1, "b.txt"), (1, "c.txt")], "file rows: equal counts, path order")

    def test_rename_delete_conflict_lists_the_path(self):
        fx = rename_delete("rename")
        r = run_hotspots(fx.path)
        self.assertEqual(field(r.out, "merges replayed"), "1", "merges replayed line")
        self.assertEqual(rows(r.out), [(1, "renamed.txt")], "file rows: git lists the renamed path")

    def test_path_with_space_and_non_ascii_prints_unquoted(self):
        fx = single_conflict("unicode", paths=("my notes é.txt",))
        r = run_hotspots(fx.path)
        self.assertEqual(field(r.out, "merges replayed"), "1", "merges replayed line")
        self.assertEqual(rows(r.out), [(1, "my notes é.txt")], "file rows: git quotes this path, the script must not")

    def test_no_merge_since_date_prints_zeros_and_counts_nothing_before_date(self):
        fx = old_only("zeros")
        self.assertEqual(len(fx.merges()), 1, "fixture holds one conflicting merge, dated before SINCE")
        r = run_hotspots(fx.path)
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        self.assert_summary(r.out, 0, 0, 0, "0.0%")
        self.assertEqual(rows(r.out), [], "file rows")
        c = cost(r.out)
        self.assertIsNotNone(c, "cost line: `cost: merge-trees N, wall S s`")
        self.assertEqual(c[0], 0, "cost line merge-tree count: no replay ran")

    def test_read_that_fails_counts_as_unknown_not_clean(self):
        fx = missing_blob("missing")
        self.assertEqual(len(fx.merges()), 1, "fixture holds one merge")
        r = run_hotspots(fx.path)
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        self.assert_summary(r.out, 1, 0, 1, "0.0%")
        self.assertEqual(rows(r.out), [], "file rows: the unread merge is not clean")

    def test_top_limits_the_file_rows(self):
        fx = selection("top")
        r = run_hotspots(fx.path, top="1")
        self.assertEqual(field(r.out, "merges replayed"), "3", "merges replayed line")
        self.assertEqual(rows(r.out), [(2, "z.txt")], "file rows: only the top one")

    def test_cost_line_counts_one_merge_tree_per_replay(self):
        fx = selection("cost")
        r = run_hotspots(fx.path, shim="spy")
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        self.assertEqual(field(r.out, "merges replayed"), "3", "merges replayed line")
        c = cost(r.out)
        self.assertIsNotNone(c, "cost line: `cost: merge-trees N, wall S s`")
        self.assertEqual(c[0], 3, "cost line merge-tree count")
        self.assertEqual(len(read_log(r.log)), 3, "merge-tree process starts counted by the shim")

    def test_normal_run_removes_its_temp_object_folder(self):
        fx = single_conflict("normal")
        r = run_hotspots(fx.path, shim="spy")
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        self.assertEqual(field(r.out, "merges replayed"), "1", "merges replayed line")
        temp = temp_paths(read_log(r.log), r.scratch)
        self.assertTrue(temp, "no merge-tree ran in a folder under TMPDIR, so no object folder was made")
        for path in temp:
            self.assertFalse(os.path.exists(path), "temp object folder left after the run: %s" % path)
        self.assertEqual(os.listdir(r.scratch), [], "TMPDIR holds files after the run")

    def test_forced_error_removes_its_temp_object_folder(self):
        fx = single_conflict("forced")
        r = run_hotspots(fx.path, shim="interrupt")
        self.assertNotEqual(r.rc, 0, "exit code of a run stopped by a forced error")
        temp = temp_paths(read_log(r.log), r.scratch)
        self.assertTrue(temp, "the forced error came before any temp object folder was made")
        for path in temp:
            self.assertFalse(os.path.exists(path), "temp object folder left after the forced error: %s" % path)
        self.assertEqual(os.listdir(r.scratch), [], "TMPDIR holds files after the forced error")

    def test_repo_is_unchanged_by_a_run(self):
        fx = single_conflict("unchanged")
        before = fx.snapshot()
        self.assertEqual(before[2], "", "fixture starts with a clean status")
        r = run_hotspots(fx.path)
        self.assertEqual(field(r.out, "merges replayed"), "1", "merges replayed line")
        after = fx.snapshot()
        self.assertEqual(after[0], before[0], "object files in the repo: a run writes none")
        self.assertEqual(after[1], before[1], "refs: a run creates none")
        self.assertEqual(after[2], before[2], "git status: a run changes none")

    def test_git_too_old_exits_two_with_one_line(self):
        fx = single_conflict("old")
        r = run_hotspots(fx.path, shim="old")
        self.assertEqual(r.rc, 2, "exit code for a git too old for merge-tree --write-tree")
        lines = [line for line in (r.out + r.err).splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, "output lines: one line for a too-old git")
        self.assertTrue(any(k in lines[0] for k in ("merge-tree", "--write-tree", "2.38")),
                        "the line names the cause: %r" % lines[0])

    def test_without_exposure_flag_rows_keep_the_conflict_count(self):
        fx = exposure("exposure-off")
        self.assertEqual(len(fx.merges()), 5, "fixture merge count")
        r = run_hotspots(fx.path)
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        self.assert_summary(r.out, 5, 1, 0, "20.0%")
        self.assertEqual(rows(r.out), [(1, "f.txt")], "file rows without --exposure: the count alone")

    def test_exposure_flag_reads_conflicts_over_both_sides_merges(self):
        fx = exposure("exposure-on")
        self.assertEqual(len(fx.merges()), 5, "fixture merge count")
        r = run_hotspots(fx.path, flags=["--exposure"])
        self.assertEqual(exposure_rows(r.out), [(1, 3, "f.txt")],
                         "--exposure rows: conflicts over both-sides merges, and no row for a file with no conflict "
                         "(stderr: %s)" % r.err)
        self.assertEqual(r.rc, 0, "exit code with --exposure (stderr: %s)" % r.err)

    def test_without_into_branches_flag_both_merge_kinds_count(self):
        fx = into_branches("into-off")
        self.assertEqual(len(fx.merges()), 3, "fixture merge count")
        r = run_hotspots(fx.path)
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        self.assert_summary(r.out, 2, 2, 0, "100.0%")
        self.assertEqual(field(r.out, "merges not replayed"), "1 (octopus 0, off base 1)", "merges not replayed line")
        self.assertEqual(rows(r.out), [(1, "a.txt"), (1, "b.txt")], "file rows: both conflicts")

    def test_into_branches_flag_counts_only_main_merged_into_a_branch(self):
        fx = into_branches("into-on")
        self.assertEqual(len(fx.merges()), 3, "fixture merge count")
        r = run_hotspots(fx.path, flags=["--into-branches"])
        self.assertEqual(field(r.out, "merges replayed"), "1",
                         "merges replayed with --into-branches: the PR merge into main is dropped")
        self.assertEqual(r.rc, 0, "exit code with --into-branches (stderr: %s)" % r.err)
        self.assertEqual(rows(r.out), [(1, "b.txt")], "file rows with --into-branches: the merge of main into g only")

    def test_into_branches_flag_leaves_dropped_merges_out_of_not_replayed(self):
        fx = into_branches("into-skip")
        r = run_hotspots(fx.path, flags=["--into-branches"])
        self.assertEqual(field(r.out, "merges not replayed"), "0 (octopus 0, off base 0)",
                         "merges not replayed with --into-branches: the merge of x and y is dropped, not counted")

    def test_into_branches_flag_drops_a_branch_merge_with_only_a_pr_parent(self):
        fx = pr_parent("into-pr-parent")
        self.assertEqual(len(fx.merges()), 2, "fixture merge count")
        r = run_hotspots(fx.path, flags=["--into-branches"])
        self.assert_summary(r.out, 0, 0, 0, "0.0%")
        self.assertEqual(r.rc, 0, "exit code with --into-branches (stderr: %s)" % r.err)

    def test_green_control_git_merge_tree_on_the_fixtures(self):
        """Runs without the script: the fixtures hold the conflicts the cases count."""
        conflict = single_conflict("green-conflict")
        p = subprocess.run(["git", "-C", conflict.path, "merge-tree", "--write-tree", "--name-only", "f^1", "f^2"],
                           env=fixture_env(RUN, DAY2), capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.returncode, 1, "a conflicting merge: git merge-tree exits 1")
        self.assertIn("a.txt", p.stdout.splitlines()[1:], "a conflicting merge: git names a.txt")
        clean = clean_merge("green-clean")
        p = subprocess.run(["git", "-C", clean.path, "merge-tree", "--write-tree", "--name-only", "f^1", "f^2"],
                           env=fixture_env(RUN, DAY2), capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.returncode, 0, "a clean merge: git merge-tree exits 0")
        gone = missing_blob("green-missing")
        p = subprocess.run(["git", "-C", gone.path, "merge-tree", "--write-tree", "--name-only", "f^1", "f^2"],
                           env=fixture_env(RUN, DAY2), capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.returncode, 128, "a dropped blob: git merge-tree exits 128")

    def test_since_must_be_a_real_iso_date_and_is_refused_with_one_line(self):
        fx = single_conflict("since-bad")
        for value in ("foo", "2026-13-45", "2026-02-30", "11/18/2026"):
            with self.subTest(since=value):
                r = run_hotspots(fx.path, since=value)
                self.assertEqual(r.rc, 1, "--since %s: exit code 1, a bad argument (stderr: %s)" % (value, r.err))
                self.assertEqual(len(output_lines(r)), 1, "--since %s: one line of output" % value)
                self.assertIsNone(field(r.out, "merges replayed"), "--since %s: no count line is printed" % value)

    def test_header_names_the_base_read_and_its_first_nine_hex_digits(self):
        fx = single_conflict("header-base")
        sha = fx.git("rev-parse", "main").stdout.strip()
        r = run_hotspots(fx.path)
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        self.assert_same(r.out.splitlines()[0], "base: main " + sha[:9], "first line: the base read and its commit")

    def test_default_base_is_the_remote_main_when_a_remote_ref_exists(self):
        fx, m1 = remote_behind("remote-count")
        self.assert_same(fx.git("rev-parse", "refs/remotes/origin/main").stdout.strip(), m1,
                         "fixture: origin/main is set to m1")
        r = run_hotspots(fx.path, base=None)
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        self.assert_same(field(r.out, "merges replayed"), "1",
                         "merges replayed with the default base: origin/main holds the merge, local main does not")

    def test_default_header_names_origin_main_and_its_commit(self):
        fx, m1 = remote_behind("remote-header")
        r = run_hotspots(fx.path, base=None)
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        self.assert_same(r.out.splitlines()[0], "base: origin/main " + m1[:9], "first line: origin/main and its commit")

    def test_default_header_names_main_when_no_remote_ref_exists(self):
        fx = single_conflict("no-remote-header")
        sha = fx.git("rev-parse", "main").stdout.strip()
        r = run_hotspots(fx.path, base=None)
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        self.assert_same(r.out.splitlines()[0], "base: main " + sha[:9], "first line: main and its commit")

    def test_default_base_without_a_remote_still_counts_local_main(self):
        fx = single_conflict("no-remote-count")
        self.assert_same(fx.git("remote").stdout.strip(), "", "fixture: no remote is set")
        r = run_hotspots(fx.path, base=None)
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        self.assert_same(field(r.out, "merges replayed"), "1", "merges replayed with no remote: local main is the base")

    def test_shallow_clone_prints_one_cut_line_and_exits_three(self):
        fx = single_conflict("shallow")
        clone = clone_of(fx, "shallow", depth=1)
        p = subprocess.run(["git", "-C", clone, "rev-parse", "--is-shallow-repository"],
                           env=fixture_env(RUN, DAY2), capture_output=True, text=True, encoding="utf-8")
        self.assert_same(p.stdout.strip(), "true", "scope: the clone is shallow")
        r = run_hotspots(clone, base="f")
        self.assertEqual(r.rc, 3, "exit code 3, the code for unknown: the history is cut at depth (stderr: %s)" % r.err)
        lines = output_lines(r)
        self.assertEqual(len(lines), 1, "one line of output: the cut line, and no report")
        self.assertIn("cut at depth", lines[0], "the line says the history is cut at depth")
        self.assertIn("lower bound", lines[0], "the line says the counts are a lower bound")

    def test_whole_clone_prints_no_cut_line(self):
        fx = single_conflict("whole")
        clone = clone_of(fx, "whole")
        r = run_hotspots(clone, base="f")
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        self.assert_same(field(r.out, "merges replayed"), "1", "merges replayed in a whole clone")
        self.assertNotIn("cut at depth", r.out, "no line says the history is cut, in a whole clone")

    def test_into_branches_drops_a_merge_whose_first_parent_is_on_main_line(self):
        fx = into_first_parent("into-first")
        self.assertEqual(len(fx.merges()), 2, "fixture merge count")
        trunk = fx.git("rev-list", "--first-parent", "main").stdout.split()
        self.assertNotIn(fx.git("rev-parse", "g^1").stdout.strip(), trunk, "scope: g's first parent is off main's line")
        self.assertIn(fx.git("rev-parse", "g^2").stdout.strip(), trunk, "scope: g's second parent is on main's line")
        self.assertIn(fx.git("rev-parse", "h^1").stdout.strip(), trunk, "scope: h's first parent is on main's line")
        self.assertNotIn(fx.git("rev-parse", "h").stdout.strip(), trunk, "scope: the merge h is off main's line")
        r = run_hotspots(fx.path, flags=["--into-branches"])
        self.assertEqual(r.rc, 0, "exit code with --into-branches (stderr: %s)" % r.err)
        self.assert_same(field(r.out, "merges replayed"), "1",
                         "merges replayed with --into-branches: the merge whose first parent is on main's line is dropped")
        self.assert_same(rows(r.out), [(1, "b.txt")], "file rows with --into-branches: the merge of main into g only")

    def test_top_below_one_is_refused_with_one_line(self):
        fx = single_conflict("top-low")
        for value in ("0", "-1"):
            with self.subTest(top=value):
                r = run_hotspots(fx.path, top=value)
                self.assertEqual(r.rc, 1, "--top %s: exit code 1, a bad argument (stderr: %s)" % (value, r.err))
                self.assertEqual(len(output_lines(r)), 1, "--top %s: one line of output" % value)
                self.assert_same(rows(r.out), [], "--top %s: no file rows" % value)

    def test_output_ends_with_three_caveat_lines_after_the_cost_line(self):
        fx = single_conflict("caveat-end")
        r = run_hotspots(fx.path)
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        lines = r.out.splitlines()
        cost_at = [i for i, line in enumerate(lines) if line.startswith("cost: ")]
        self.assertEqual(len(cost_at), 1, "the cost line prints once")
        tail = lines[cost_at[0] + 1:]
        self.assertEqual(len(tail), 3, "three lines after the cost line, the caveats (tail: %r)" % tail)
        self.assert_same(caveats(r.out), tail, "each line after the cost line is a caveat line")

    def test_caveat_says_a_replay_is_what_git_finds_now_not_what_the_author_resolved(self):
        fx = single_conflict("caveat-replay")
        r = run_hotspots(fx.path)
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        self.assertTrue(any("replay" in c and "resolv" in c for c in caveats(r.out)),
                        "a caveat line says the replay is not what the author resolved (caveats: %r)" % caveats(r.out))

    def test_caveat_says_squash_and_rebase_merges_are_absent(self):
        fx = single_conflict("caveat-squash")
        r = run_hotspots(fx.path)
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        self.assertTrue(any("squash" in c and "rebase" in c for c in caveats(r.out)),
                        "a caveat line says squash and rebase merges are absent (caveats: %r)" % caveats(r.out))

    def test_caveat_says_refs_walked_all(self):
        fx = single_conflict("caveat-refs")
        r = run_hotspots(fx.path)
        self.assertEqual(r.rc, 0, "exit code (stderr: %s)" % r.err)
        self.assertTrue(any("refs walked: all" in c for c in caveats(r.out)),
                        "a caveat line says refs walked: all (caveats: %r)" % caveats(r.out))

    def test_list_flag_prints_each_conflicted_merge_with_its_sha9_and_files(self):
        fx = selection("list-on")
        mf = fx.git("rev-parse", "f").stdout.strip()
        q = fx.git("rev-parse", "main").stdout.strip()
        r = run_hotspots(fx.path, flags=["--list"])
        lines = r.out.splitlines()
        mf_lines = [line for line in lines if line.startswith("merge " + mf[:9] + " ")]
        q_lines = [line for line in lines if line.startswith("merge " + q[:9] + " ")]
        self.assertTrue(mf_lines and "z.txt" in mf_lines[0],
                        "--list: a `merge <sha9> <paths>` line for the merge of main into f, with z.txt (stdout: %r)"
                        % r.out)
        self.assertTrue(q_lines and "a.txt" in q_lines[0] and "z.txt" in q_lines[0],
                        "--list: a `merge <sha9> <paths>` line for the last merge, with a.txt and z.txt (stdout: %r)"
                        % r.out)
        self.assertEqual(r.rc, 0, "exit code with --list (stderr: %s)" % r.err)

    def test_list_flag_leaves_out_the_clean_merge(self):
        fx = selection("list-clean")
        p = fx.git("rev-parse", "main~2").stdout.strip()
        r = run_hotspots(fx.path, flags=["--list"])
        lines = r.out.splitlines()
        self.assertTrue(any(line.startswith("merge ") for line in lines),
                        "--list prints merge lines (stdout: %r)" % r.out)
        self.assertFalse(any(line.startswith("merge " + p[:9] + " ") for line in lines),
                         "--list: the clean merge is not listed")
        self.assertEqual(r.rc, 0, "exit code with --list (stderr: %s)" % r.err)


if __name__ == "__main__":
    unittest.main()
