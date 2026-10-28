#!/usr/bin/env python3
"""Fixture suite for merge/merge.py, the git and GitHub halves.

Run: python3 merge/test_merge.py
MERGE_TESTS=windows-slice runs only the marked tests. MERGE_SHARD=<i>/<n> then runs every n-th test,
starting at the i-th (1-based): the n shards are disjoint and together hold every test, so CI can split
the suite across jobs and drop none.
No network, no real repo. Every run uses a local bare origin in a temp dir, the real
actions/stamp/stamp.mjs, and a fake Host for the git half. The lock backend is
GitLock against that origin. GhLock and the GitHub half (Host) are covered with a fake `gh` on PATH.
"""
import ast, atexit, contextlib, inspect, io, pathlib, json, os, re, shutil, signal, socket, stat, subprocess, sys, tempfile, threading, time, tokenize, types, unittest, unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import merge  # noqa: E402

os.environ.update(LC_ALL="C", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                  GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

def windows_slice(x):
    """Mark a test or a leaf class as Windows-specific. MERGE_TESTS=windows-slice runs only these.
    Put it outermost on a test, so a skip decorator below it keeps the mark. Never mark a base class."""
    x._windows_slice = True
    return x

def iter_tests(suite):
    for t in suite:
        yield from iter_tests(t) if isinstance(t, unittest.TestSuite) else [t]

def select_tests(suite, mode):
    """"" keeps every test. "windows-slice" keeps the marked ones. Anything else, or an empty slice, stops the run."""
    if mode == "":
        return suite
    if mode != "windows-slice":
        raise SystemExit(f"MERGE_TESTS={mode!r}: want unset or 'windows-slice'. Nothing ran.")
    keep = [t for t in iter_tests(suite) if t.__class__.__dict__.get("_windows_slice")
            or getattr(getattr(t, t._testMethodName), "_windows_slice", False)]
    if not keep:
        raise SystemExit("MERGE_TESTS=windows-slice: no test is marked. Nothing ran.")
    return unittest.TestSuite(keep)

def select_shard(suite, value):
    """"" keeps every test. "<i>/<n>" (1 <= i <= n) keeps every n-th test from index i-1. Anything else stops the run."""
    if value == "":
        return suite
    m = re.fullmatch(r"([1-9][0-9]*)/([1-9][0-9]*)", value)
    if not m or int(m.group(1)) > int(m.group(2)):
        raise SystemExit(f"MERGE_SHARD={value!r}: want <i>/<n> with 1 <= i <= n. Nothing ran.")
    i, n = int(m.group(1)), int(m.group(2))
    keep = list(iter_tests(suite))[i - 1::n]
    if not keep:
        raise SystemExit(f"MERGE_SHARD={value!r}: this shard holds no test. Nothing ran.")
    return unittest.TestSuite(keep)

def sh(cwd, *cmd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, (cmd, r.stdout, r.stderr)
    return r.stdout.strip()

def tree_listed(cwd, path):
    """-> True when `git worktree list` names `path`. Git prints C:/ paths on Windows, so both sides are normalized."""
    norm = lambda p: os.path.normcase(os.path.realpath(p))
    out = sh(cwd, "git", "worktree", "list", "--porcelain")
    return norm(path) in {norm(l[9:]) for l in out.splitlines() if l.startswith("worktree ")}

def put(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)

def put_shim(path, text):
    """Write an extension-less fake program and make it runnable from PATH.

    merge.py resolves programs with shutil.which, which on Windows only matches
    PATHEXT extensions (.exe/.cmd/...), never an extension-less script. So on
    Windows we also drop a matching `<name>.cmd` beside it that re-dispatches
    to the script through the current Python.
    """
    put(path, text)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    if os.name == "nt":
        put(path + ".cmd", '@"%s" "%%~dp0%s" %%*\n' % (sys.executable, os.path.basename(path)))

CONFIG = {
    "defaultBranch": "main",
    "regenerate": '[ -z "$MERGE_TEST_HOOK" ] || bash "$MERGE_TEST_HOOK"',
    "kinds": [{"id": "decision", "folder": "docs/decisions", "filePattern": "*.md", "prefix": "D", "pad": 3,
               "idTemplate": "{prefix}-{n}", "pendingRegex": "^id:[ \\t]*pending[ \\t]*$", "location": "frontmatter",
               "order": "filename", "numbering": "max_plus_one", "slugField": "slug", "glossField": "title"}],
    "merge": {"method": "merge", "deadlineMinutes": 5, "afterMerge": [], "deleteBranch": True},
}

def record(id_, slug):
    return f"---\nid: {id_}\nslug: {slug}\ntitle: {slug.title()}\n---\nbody\n"

class FakeHost:
    """The GitHub half, scripted. `other` is a second clone that plays a competing pusher and the merger."""
    built = True

    def __init__(self, root, other, branch="feat"):
        self.root, self.other, self.branch = root, other, branch
        self.checks, self.refuse, self.on_wait = (True, ""), None, None
        self.head_override, self.mergeable = None, "MERGEABLE"
        self.pr_state = "OPEN"
        self.draft = False
        self.body = ""  # the PR body gh reports: a `Drops-lines:` line in it excuses a path at the silent-undo check
        self.base, self.base_seq = "main", None  # base_seq: one base per pr() read, the last one repeats
        self.waits, self.seq, self.state = [], None, "green"  # waits: (sha, prior) per call; seq: scripted results, then self.checks

    def pr(self, n):
        head = merge.origin_head(self.root, self.branch)
        base = (self.base_seq.pop(0) if len(self.base_seq) > 1 else self.base_seq[0]) if self.base_seq else self.base
        return {"head": self.head_override or head, "branch": self.branch, "base": base, "state": self.pr_state,
                "mergeable": self.mergeable, "merge_state": "CLEAN", "draft": self.draft, "body": self.body}

    def required_names(self):
        return ["checks"]

    def head_state(self, n):
        return self.state

    def base_state(self, base, flows):  # main's latest run is green unless a case says so (RedMainBrake)
        return "green", ""

    def wait_checks(self, n, sha, d, prior=None):
        self.waits.append((sha, prior))
        if prior is not None and self.on_wait:  # on_wait plays the rival during the wait after the claim push
            self.on_wait()
        return self.seq.pop(0) if self.seq else self.checks

    def merge(self, n, method, sha):
        if self.refuse:
            return None, self.refuse
        self.merged = True
        o = self.other
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", self.base, f"origin/{self.base}")
        sh(o, "git", "merge", "-q", "--no-ff", "-m", f"merge #{n}", sha)
        sh(o, "git", "push", "-q", "origin", self.base)
        return sh(o, "git", "rev-parse", "HEAD"), ""

def wait_sites(src):
    """-> (count, in_loop) over the `wait_checks` calls in a Python source. A call inside a for or while may run many
    times, so a caller trusts the count only when in_loop is False."""
    found = []
    def walk(node, looped):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == "wait_checks":
                found.append(looped)
            walk(child, looped or isinstance(child, (ast.For, ast.While, ast.AsyncFor)))
    walk(ast.parse(src), False)
    return len(found), any(found)

class PipeOut(io.TextIOWrapper):
    """A Windows stdout piped to a reader (no PYTHONUTF8): cp1252, errors strict. getvalue() reads back what the pipe got."""
    def __init__(self):
        super().__init__(io.BytesIO(), encoding="cp1252", errors="strict")

    def getvalue(self):
        self.flush()
        return self.buffer.getvalue().decode("cp1252", errors="replace")

def build_repos(t):
    """In folder t: origin.git (main with the seed commit, feat one commit ahead of it), and two clones of it, co and other."""
    bare = os.path.join(t, "origin.git")
    sh(t, "git", "init", "-q", "--bare", "-b", "main", bare)
    seed = os.path.join(t, "seed")
    sh(t, "git", "clone", "-q", bare, seed)
    sh(seed, "git", "checkout", "-q", "-b", "main")
    put(os.path.join(seed, ".github/stamp.json"), json.dumps(CONFIG))
    put(os.path.join(seed, "docs/decisions/first.md"), record("D-001", "first"))
    sh(seed, "git", "add", "-A"); sh(seed, "git", "commit", "-q", "-m", "seed"); sh(seed, "git", "push", "-q", "origin", "main")
    sh(seed, "git", "checkout", "-q", "-b", "feat")
    put(os.path.join(seed, "docs/decisions/second.md"), record("pending", "second"))
    sh(seed, "git", "add", "-A"); sh(seed, "git", "commit", "-q", "-m", "feat: second"); sh(seed, "git", "push", "-q", "origin", "feat")
    for name in ("co", "other"):
        sh(t, "git", "clone", "-q", bare, os.path.join(t, name))

_TEMPLATE = []

def copy_repos(t):
    """Put build_repos(t)'s result in t without running git: copy a template built once per process, then point the two clones at the copy of origin.
    Setup was 14 git starts per test (a clone is the slow one on Windows); a copy is files only. False when the copy cannot be made or checked: the caller builds with git."""
    try:
        if not _TEMPLATE:
            root = os.path.realpath(tempfile.mkdtemp(prefix="test-merge-template-"))
            atexit.register(shutil.rmtree, root, True)
            build_repos(root)
            _TEMPLATE.append(root)
        tpl = _TEMPLATE[0]
        for name in ("origin.git", "co", "other"):
            shutil.copytree(os.path.join(tpl, name), os.path.join(t, name), symlinks=True)
        for name in ("co", "other"):
            cfg = os.path.join(t, name, ".git", "config")
            with open(cfg, encoding="utf-8", newline="") as f:
                text = f.read()
            # the clone's url as git wrote it: the path as given, with a backslash doubled (config escaping), or with forward slashes
            for form in (lambda p: p.replace("\\", "\\\\"), lambda p: p.replace("\\", "/"), lambda p: p):
                was, now = (form(os.path.join(base, "origin.git")) for base in (tpl, t))
                if text.count(was) == 1:
                    break
            else:
                raise OSError(f"the config of the clone {name} does not name the template origin once: {text!r}")
            with open(cfg, "w", encoding="utf-8", newline="") as f:
                f.write(text.replace(was, now))
        return True
    except (OSError, subprocess.SubprocessError) as e:
        print(f"test_merge: the repo template could not be copied ({e}); building this test's repos with git", file=sys.stderr)
        for name in os.listdir(t):
            shutil.rmtree(os.path.join(t, name), True)
        return False

class Env(unittest.TestCase):
    def setUp(self):
        self.t = os.path.realpath(tempfile.mkdtemp(prefix="test-merge-"))
        self.addCleanup(shutil.rmtree, self.t, True)
        self.bare = os.path.join(self.t, "origin.git")
        self.co, self.other = (os.path.join(self.t, n) for n in ("co", "other"))
        if not copy_repos(self.t):
            build_repos(self.t)
        self.now = time.time()
        self.host = FakeHost(self.co, self.other)
        self.lock = merge.GitLock(self.co, now=lambda: self.now, pause=lambda s: None)  # a retry pause is a no-op: a test never sleeps
        self.addCleanup(lambda: os.environ.pop("MERGE_TEST_HOOK", None))

    def run_merge(self, *args, host=None, lock=None, stdout=None):
        out, err = stdout or io.StringIO(), io.StringIO()
        cwd = os.getcwd()
        os.chdir(self.co)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = merge.main(list(args), host=host or self.host, lock=lock or self.lock)
        finally:
            os.chdir(cwd)
        return rc, out.getvalue() + err.getvalue()

    def refs(self):
        return sh(self.co, "git", "ls-remote", "origin")

    def head(self, ref="feat"):
        return sh(self.co, "git", "ls-remote", "origin", f"refs/heads/{ref}").split("\t")[0]

    def show(self, ref, path):
        sh(self.co, "git", "fetch", "-q", "origin")
        return sh(self.co, "git", "show", f"origin/{ref}:{path}")

    def claims(self, ref="main"):
        sh(self.co, "git", "fetch", "-q", "origin")
        return sh(self.co, "git", "log", f"origin/{ref}", "--format=%s").splitlines().count("Claim record numbers")

    def lock_ref(self):
        return "refs/heads/merge-lock/main" in self.refs()

    def worktrees(self):
        return sh(self.co, "git", "worktree", "list").count("\n") + 1

    def competitor_push(self):
        o = self.other
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        put(os.path.join(o, "rival.txt"), "someone else pushed\n")
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-q", "-m", "rival"); sh(o, "git", "push", "-q", "origin", "feat")
        return sh(o, "git", "rev-parse", "HEAD")

    def hook(self, fn_script):
        p = os.path.join(self.t, "hook.sh")
        put(p, fn_script)
        os.environ["MERGE_TEST_HOOK"] = p

class Flow(Env):
    def test_preview_presses_nothing(self):
        before = self.refs()
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 0, out)
        self.assertIn("PREVIEW", out)
        self.assertIn("Record-claim: D-002", out)
        self.assertEqual(self.refs(), before)
        self.assertEqual(self.worktrees(), 1)

    def test_preview_says_the_state_of_the_head_checks(self):
        self.host.state = "red: checks: fail"
        rc, out = self.run_merge("7")
        self.assertIn("head checks: red: checks: fail", out)

    def test_the_lock_outlives_every_wait_one_run_can_take(self):
        # Each wait_checks call site in merge.py is one wait, and none sits in a loop, so one run takes at most one wait per
        # site: the head, the claim, the merge commit. Limit: a helper that wraps wait_checks and is called N times undercounts.
        with open(merge.__file__, encoding="utf-8") as f:
            sites, looped = wait_sites(f.read())
        self.assertGreater(sites, 0)
        self.assertFalse(looped, "a wait_checks call sits in a loop, so the site count is no bound")
        d = merge.MERGE_DEFAULTS["deadlineMinutes"]  # the code's default deadline, set in the base config as the tool reads it
        put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], deadlineMinutes=d))))
        ttls = []
        acquire = self.lock.acquire
        self.lock.acquire = lambda b, ttl: (ttls.append(ttl), acquire(b, ttl))[1]
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        need = sites * d * 60
        self.assertGreaterEqual(ttls[0], need, "lock ttl %d s; %d waits of %d min need %d s" % (ttls[0], sites, d, need))

    def test_head_red_claims_nothing_pushes_nothing_and_frees_the_lock(self):
        before = self.refs()
        self.host.seq = [(False, "a check is red: checks: fail")]
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1)
        self.assertIn("a check is red: checks: fail", out)
        self.assertEqual(self.refs(), before)  # no claim push, and the lock ref is gone
        self.assertEqual(len(self.host.waits), 1)

    def test_head_pending_then_green_claims_after_the_wait(self):
        rc, out = self.run_merge("7", "--confirm")  # the fake wait returns green: one wait on the head, one on the claim
        self.assertEqual(rc, 0, out)
        (s1, p1), (s2, p2) = self.host.waits
        self.assertIsNone(p1)  # the first wait is on the head as it stands, before any push
        self.assertNotEqual(s1, s2)
        self.assertEqual(p2, s1)
        self.assertEqual(self.claims(), 1)

    def test_head_pending_then_red_claims_nothing(self):
        before = self.refs()
        self.host.seq = [(False, "a check is red: checks: fail https://x")]  # the wait saw pending, then red
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1)
        self.assertEqual(self.refs(), before)
        self.assertEqual(self.claims(), 0)

    def test_nothing_to_claim_waits_once(self):
        sh(self.other, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        sh(self.other, "git", "rm", "-q", "docs/decisions/second.md")
        sh(self.other, "git", "commit", "-qm", "no pending record left"); sh(self.other, "git", "push", "-q", "origin", "feat")
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertIn("nothing to claim", out)
        self.assertEqual(len(self.host.waits), 1)

    @windows_slice
    def test_full_merge_claims_pushes_merges_syncs_cleans(self):
        # A name relative to afterMerge's own cwd (root, i.e. self.co): the command only needs to
        # prove afterMerge ran, not survive bash's own quoting of a native Windows path. An
        # absolute `self.t`-joined path here was this test's own route, not the subject: unquoted,
        # it is bash itself reading "\U" etc. as an escape and mangling the path (confirmed by
        # direct repro, independent of merge.py). See test_afterMerge_runs_in_git_bash_not_the_wsl_stub
        # for the real afterMerge defect this same line also hits.
        mark = os.path.join(self.co, "after.txt")
        cfg = dict(CONFIG, merge=dict(CONFIG["merge"], afterMerge=["echo ran > after.txt"]))
        sh(self.other, "git", "checkout", "-q", "main"); put(os.path.join(self.other, ".github/stamp.json"), json.dumps(cfg))
        sh(self.other, "git", "commit", "-qam", "cfg"); sh(self.other, "git", "push", "-q", "origin", "main")
        sh(self.co, "git", "pull", "-q", "--ff-only")
        head_takes_base(self)
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))
        self.assertEqual(self.claims(), 1)
        trailer = sh(self.co, "git", "log", "-1", "--format=%(trailers:key=Record-claim,valueonly)", "origin/main^2")
        self.assertEqual(trailer.strip(), "D-002")
        self.assertEqual(sh(self.co, "git", "rev-parse", "main"), sh(self.co, "git", "rev-parse", "origin/main"))
        self.assertTrue(os.path.exists(os.path.join(self.co, "docs/decisions/second.md")))
        self.assertTrue(os.path.exists(mark))
        self.assertNotIn("refs/heads/feat", self.refs())
        self.assertFalse(self.lock_ref())
        self.assertEqual(self.worktrees(), 1)

    @windows_slice
    def test_afterMerge_runs_in_git_bash_not_the_wsl_stub(self):
        """after_merge() (merge/merge.py:470) hands subprocess.run a bare "bash". On Windows,
        CreateProcess searches C:\\Windows\\System32 before PATH, and that folder holds the WSL
        launcher stub, not Git Bash (decision bare-bash-on-windows-can-resolve-to-the-wsl-stub;
        the fix, _find_git_bash(), lives only in hooks/test_config_watch.py). A command that
        prints $OSTYPE tells the two apart: Git Bash (MSYS/MINGW) says "msys" or "msys-...", the
        WSL stub says "linux-gnu". The redirect target is a bare relative name so this case does
        not also depend on the separate native-path-quoting defect above."""
        cfg = dict(CONFIG, merge=dict(CONFIG["merge"], afterMerge=["echo $OSTYPE > ostype.txt"]))
        sh(self.other, "git", "checkout", "-q", "main"); put(os.path.join(self.other, ".github/stamp.json"), json.dumps(cfg))
        sh(self.other, "git", "commit", "-qam", "cfg"); sh(self.other, "git", "push", "-q", "origin", "main")
        sh(self.co, "git", "pull", "-q", "--ff-only")
        head_takes_base(self)
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        p = os.path.join(self.co, "ostype.txt")
        self.assertTrue(os.path.exists(p), "afterMerge did not run at all")
        with open(p) as f:
            ostype = f.read().strip()
        if os.name == "nt":
            self.assertRegex(ostype, r"msys|cygwin|mingw",
                              f"afterMerge ran under $OSTYPE={ostype!r}: that is the WSL stub, not Git Bash")
        else:
            self.assertTrue(ostype, "afterMerge ran but $OSTYPE was empty")

    def test_local_main_moves_by_fetch_when_no_worktree_holds_it(self):
        sh(self.co, "git", "checkout", "-q", "-b", "side")
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertEqual(sh(self.co, "git", "rev-parse", "main"), sh(self.co, "git", "rev-parse", "origin/main"))
        self.assertEqual(sh(self.co, "git", "rev-parse", "--abbrev-ref", "HEAD"), "side")

    def test_an_unrelated_dirty_file_does_not_block_the_fast_forward(self):
        put(os.path.join(self.co, "scratch.txt"), "x")
        sh(self.co, "git", "add", "scratch.txt")
        put(os.path.join(self.co, "docs/decisions/first.md"), "my edit\n")  # tracked, modified, not in the merge
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertEqual(sh(self.co, "git", "rev-parse", "main"), sh(self.co, "git", "rev-parse", "origin/main"))
        self.assertEqual(open(os.path.join(self.co, "scratch.txt")).read(), "x")
        self.assertEqual(open(os.path.join(self.co, "docs/decisions/first.md")).read(), "my edit\n")

    def assert_git_refuses_the_overwrite(self, rc, out, old, path, content):
        self.assertEqual(rc, 1, out)  # a failed local fast-forward exits non-zero
        self.assertIn("the merge landed. The local main did not move", out)
        self.assertIn(path, out)  # git named the blocking path
        self.assertIn(os.path.realpath(self.co), out)  # the checkout that was checked, by path (ff_main names it on both cases)
        self.assertIn("overwritten", out)  # and it was git's refusal
        self.assertNotIn("stash", out)  # never git's raw advice
        self.assertIn("Fast-forward main there by hand.", out)
        self.assertEqual(sh(self.co, "git", "rev-parse", "main"), old)
        self.assertEqual(open(os.path.join(self.co, path)).read(), content)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))

    def test_a_dirty_tracked_file_the_merge_changes_keeps_its_content_and_main_stays(self):
        o = self.other  # the PR also edits first.md, so the merge changes a file that is dirty here
        sh(o, "git", "fetch", "-q", "origin"); sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        put(os.path.join(o, "docs/decisions/first.md"), record("D-001", "first") + "pr edit\n")
        sh(o, "git", "commit", "-qam", "pr edits first"); sh(o, "git", "push", "-q", "origin", "feat")
        put(os.path.join(self.co, "docs/decisions/first.md"), "my edit\n")
        old = sh(self.co, "git", "rev-parse", "main")
        rc, out = self.run_merge("7", "--confirm")
        self.assert_git_refuses_the_overwrite(rc, out, old, "docs/decisions/first.md", "my edit\n")

    def test_an_untracked_file_at_a_path_the_merge_adds_keeps_its_content_and_main_stays(self):
        put(os.path.join(self.co, "docs/decisions/second.md"), "mine\n")  # the merge adds this path
        old = sh(self.co, "git", "rev-parse", "main")
        rc, out = self.run_merge("7", "--confirm")
        self.assert_git_refuses_the_overwrite(rc, out, old, "docs/decisions/second.md", "mine\n")

    def test_after_merge_failure_is_reported_and_the_merge_stays(self):
        sh(self.other, "git", "checkout", "-q", "main")
        cfg = dict(CONFIG, merge=dict(CONFIG["merge"], afterMerge=["exit 3"]))
        put(os.path.join(self.other, ".github/stamp.json"), json.dumps(cfg))
        sh(self.other, "git", "commit", "-qam", "cfg"); sh(self.other, "git", "push", "-q", "origin", "main")
        sh(self.co, "git", "pull", "-q", "--ff-only")
        head_takes_base(self)
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)  # a failed afterMerge exits non-zero
        self.assertIn("FAILED (exit 3). The merge landed and stays.", out)
        self.assertNotIn("refs/heads/feat", self.refs())  # the rest of the cleanup still ran
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))

    def test_conflicting_pr_is_refused_before_any_claim(self):
        self.host.mergeable = "CONFLICTING"
        before = self.head()
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1)
        self.assertIn("CONFLICTING", out)
        self.assertEqual(self.head(), before)
        self.assertFalse(self.lock_ref())

    def test_a_refusal_says_that_no_override_lifts_it(self):
        # merge.py runs as a command, after the guard, so an owner override cannot reach a Stop
        # (decision owner-override). The printed refusal says so.
        self.host.mergeable = "CONFLICTING"
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)
        self.assertIn("CONFLICTING", out)
        self.assertIn("no override", out.lower())

    def test_a_closed_or_merged_pr_is_refused_before_any_claim(self):
        before = self.head()
        for state in ("CLOSED", "MERGED"):
            self.host.pr_state = state
            rc, out = self.run_merge("7", "--confirm")
            self.assertEqual(rc, 1, out)
            self.assertIn("the pull request is " + state, out)
            self.assertEqual(self.head(), before)
            self.assertFalse(self.lock_ref())

    def test_ff_main_refuses_a_commit_origin_main_does_not_hold(self):
        feat = self.head("feat")  # on origin, but never merged into origin/main
        main_before = sh(self.co, "git", "rev-parse", "refs/heads/main")
        with self.assertRaises(merge.Stop) as cm:
            merge.ff_main(self.co, "main", feat)
        self.assertIn("is not on origin/main", str(cm.exception))
        self.assertEqual(sh(self.co, "git", "rev-parse", "refs/heads/main"), main_before)

    def test_config_without_merge_method_takes_the_default_and_says_so(self):
        put_base_config(self, json.dumps(dict(CONFIG, merge={"deadlineMinutes": 5})))  # the base leaves out method
        methods = []
        real = self.host.merge
        self.host.merge = lambda n, m, sha: (methods.append(m), real(n, m, sha))[1]
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertEqual(methods, ["merge"])  # the default method
        filled = [l for l in out.splitlines() if ".github/stamp.json" in l and "method" in l]
        self.assertEqual(len(filled), 1, out)  # one line names the filled field

class ClaudeMdFlag(Env):
    """A CLAUDE.md change is flagged and only reported (decision claude-md-change-is-flagged).
    After a merge, one line per changed rule file (CLAUDE.md, .claude/CLAUDE.md, each file under output-styles/). Never a hold.

    The PR's own paths come from git, in the merge worktree and before host.merge: `git diff --name-only <base_ref>...<sha>`
    (three dots: the PR's changes, not the base's). Not `gh pr view --json files`: FakeHost has no such read. Not the merge commit's first
    parent: under the rebase method it sees one commit. Fixtures are real commits on feat, so most cases need no stub.
    The cases pin the printed lines only. Paths are literal "/" strings: git prints "/" on Windows too.

    Edge cases:
    - A rename is a change to both paths: the old path is flagged too, and git's default rename detection hides it.
    - The timeout seam: `merge.sh` is patched for the one `git diff` call whose args hold a `...` range (the PR-paths
      read). Any other call goes to the real `sh`. A case that never reaches that call fails, so a changed read cannot pass blind.
    - The match is case-insensitive on the whole rule-file path; the line prints the path as git names it."""

    def line(self, path):
        return f"merge: #7 changes {path}, a rule file every session loads."

    def flags(self, out):
        return [l for l in out.splitlines() if "a rule file every session loads" in l]

    def on_main(self, path, text):
        """Main gains a commit, pushed from the other clone, that the PR branch does not hold."""
        o = self.other
        sh(o, "git", "fetch", "-q", "origin"); sh(o, "git", "checkout", "-q", "-B", "main", "origin/main")
        put(os.path.join(o, path), text)
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-qm", f"main: {path}"); sh(o, "git", "push", "-q", "origin", "main")

    def pr_writes(self, files, sync_main=False):
        """The PR gains one commit that writes these paths. sync_main first merges the current origin/main into feat."""
        o = self.other
        sh(o, "git", "fetch", "-q", "origin"); sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        if sync_main:
            sh(o, "git", "merge", "-q", "-m", "sync main", "origin/main")
        for path, text in files.items():
            put(os.path.join(o, path), text)
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-qm", "pr: rule files"); sh(o, "git", "push", "-q", "origin", "feat")

    def assert_flagged(self, rc, out, *paths):
        """The merge landed first, so a red here means only that a flag line is wrong or missing. Then: one line per path,
        and every flag line comes after the merged-as line."""
        self.assertEqual(rc, 0, out)
        self.assertTrue(getattr(self.host, "merged", False), out)
        self.assertCountEqual(self.flags(out), [self.line(p) for p in paths], out)
        lines = out.splitlines()
        merged_at = [i for i, l in enumerate(lines) if l.startswith("merge: #7 merged as ")]
        self.assertEqual(len(merged_at), 1, out)
        self.assertTrue(all(i > merged_at[0] for i, l in enumerate(lines) if "a rule file every session loads" in l), out)

    def test_a_merged_pr_that_adds_claude_md_is_flagged_after_the_merged_as_line(self):
        self.pr_writes({"CLAUDE.md": "new rules\n"})
        rc, out = self.run_merge("7", "--confirm")
        self.assert_flagged(rc, out, "CLAUDE.md")

    def test_a_merged_pr_that_edits_a_claude_md_already_on_main_is_flagged(self):
        self.on_main("CLAUDE.md", "rules\n")  # the owner's fear: an edit to the file main already holds
        # an added line, not a replaced one: the silent-undo scan reads a replaced line as an undo of the commit that wrote it
        self.pr_writes({"CLAUDE.md": "rules\nand one more rule\n"}, sync_main=True)
        rc, out = self.run_merge("7", "--confirm")
        self.assert_flagged(rc, out, "CLAUDE.md")

    def test_each_changed_rule_file_gets_its_own_line(self):
        self.pr_writes({".claude/CLAUDE.md": "project rules\n", "output-styles/a.md": "a\n", "output-styles/sub/b.md": "b\n"})
        rc, out = self.run_merge("7", "--confirm")
        self.assert_flagged(rc, out, ".claude/CLAUDE.md", "output-styles/a.md", "output-styles/sub/b.md")

    def test_a_pr_that_changes_none_of_them_prints_no_line(self):
        rc, out = self.run_merge("7", "--confirm")  # the fixture PR adds docs/decisions/second.md only
        self.assert_flagged(rc, out)

    def test_a_near_miss_path_is_not_flagged(self):
        self.pr_writes({"CLAUDE.md": "rules\n", "CLAUDE.md.bak": "x\n", "output-styles.md": "x\n", "notes/output-styles/x.md": "x\n"})
        rc, out = self.run_merge("7", "--confirm")
        self.assert_flagged(rc, out, "CLAUDE.md")  # only the exact paths of the ruling

    def test_a_rule_file_that_only_main_changed_is_not_flagged(self):
        self.on_main("CLAUDE.md", "main's own change\n")  # the PR never touches it; it reaches the head only by the sync merge
        self.pr_writes({".claude/CLAUDE.md": "pr rules\n"}, sync_main=True)
        rc, out = self.run_merge("7", "--confirm")
        self.assert_flagged(rc, out, ".claude/CLAUDE.md")

    def test_the_flag_never_holds_the_merge(self):
        self.pr_writes({"CLAUDE.md": "rules\n", ".claude/CLAUDE.md": "rules\n", "output-styles/a.md": "a\n"})
        asked = unittest.mock.patch("builtins.input", side_effect=AssertionError("the merge asked for input"))
        asked.start(); self.addCleanup(asked.stop)
        rc, out = self.run_merge("7", "--confirm")  # no extra flag, no extra word
        self.assertEqual(len(self.host.waits), 2, out)  # the head and the claim, as for any PR: no wait added
        self.assertFalse(self.lock_ref(), out)
        self.assert_flagged(rc, out, "CLAUDE.md", ".claude/CLAUDE.md", "output-styles/a.md")

    def pr_renames(self, moves):
        """Main holds each old path first. The PR merges main, then renames each (old, new). Same text, so git sees a rename."""
        for old, _ in moves:
            self.on_main(old, "".join(f"rule line {i}\n" for i in range(8)))
        o = self.other
        sh(o, "git", "fetch", "-q", "origin"); sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        sh(o, "git", "merge", "-q", "-m", "sync main", "origin/main")
        for old, new in moves:
            sh(o, "git", "mv", old, new)
        sh(o, "git", "commit", "-qm", "pr: move"); sh(o, "git", "push", "-q", "origin", "feat")

    def test_a_rename_out_of_output_styles_flags_the_old_path(self):  # F1: --name-only names the new path only
        self.pr_renames([("output-styles/x.md", "docs/x.md")])
        rc, out = self.run_merge("7", "--confirm")
        self.assert_flagged(rc, out, "output-styles/x.md")  # docs/x.md is no rule file

    def test_a_rename_into_claude_md_flags_the_new_path(self):
        self.pr_renames([("docs/y.md", "CLAUDE.md")])
        rc, out = self.run_merge("7", "--confirm")
        self.assert_flagged(rc, out, "CLAUDE.md")  # docs/y.md is no rule file

    def test_a_rename_away_from_claude_md_flags_the_old_path(self):  # F1: a moved CLAUDE.md
        self.pr_renames([("CLAUDE.md", "docs/c.md")])
        rc, out = self.run_merge("7", "--confirm")
        self.assert_flagged(rc, out, "CLAUDE.md")

    def unreadable(self, fail):
        """Patch merge.sh so the PR-paths read fails: `fail(args)` returns (rc, text) or raises. -> the list of args it saw."""
        real_sh, seen = merge.sh, []
        def stub(args, cwd=None, input=None, env=None):
            if "diff" in args and any("..." in a for a in args):
                seen.append(args)
                return fail(args)
            return real_sh(args, cwd=cwd, input=input, env=env)
        patch = unittest.mock.patch.object(merge, "sh", stub)
        patch.start(); self.addCleanup(patch.stop)
        return seen

    def assert_check_could_not_run(self, rc, out, seen):
        """The merge landed (rc 0, merged, lock free) and one line after the merged-as line says the check could not run."""
        self.assertTrue(seen, "the PR-paths read never ran, so the stub did nothing")
        self.assertEqual(rc, 0, out)
        self.assertTrue(getattr(self.host, "merged", False), out)
        self.assertFalse(self.lock_ref(), out)
        self.assertEqual(self.flags(out), [], out)  # an unread diff names no file
        lines = out.splitlines()
        said = [i for i, l in enumerate(lines) if l.startswith("merge: #7 ") and "the rule-file check could not run" in l]
        merged_at = [i for i, l in enumerate(lines) if l.startswith("merge: #7 merged as ")]
        self.assertEqual((len(said), len(merged_at)), (1, 1), out)
        self.assertGreater(said[0], merged_at[0], out)

    def test_a_timeout_on_the_changed_paths_read_still_merges_and_says_the_check_could_not_run(self):  # F2
        self.pr_writes({"CLAUDE.md": "rules\n"})
        def slow(args):
            raise subprocess.TimeoutExpired(args, 1)
        seen = self.unreadable(slow)
        rc, out = self.run_merge("7", "--confirm")
        self.assert_check_could_not_run(rc, out, seen)

    def test_a_failed_changed_paths_read_still_merges_and_says_the_check_could_not_run(self):
        self.pr_writes({"CLAUDE.md": "rules\n"})
        seen = self.unreadable(lambda args: (128, "fatal: bad revision"))
        rc, out = self.run_merge("7", "--confirm")
        self.assert_check_could_not_run(rc, out, seen)

    def test_a_non_ascii_name_under_output_styles_is_flagged_with_its_real_name(self):  # git quotes it: "output-styles/caf\303\251.md"
        self.pr_writes({"output-styles/café.md": "a\n"})
        rc, out = self.run_merge("7", "--confirm")
        self.assert_flagged(rc, out, "output-styles/café.md")

    @windows_slice
    def test_a_name_outside_cp1252_on_a_piped_stdout_still_flags_and_runs_every_step_after_the_merge(self):  # N1: say() raises after the merge landed
        cfg = dict(CONFIG, merge=dict(CONFIG["merge"], afterMerge=["echo ran > after.txt"]))
        sh(self.other, "git", "checkout", "-q", "main"); put(os.path.join(self.other, ".github/stamp.json"), json.dumps(cfg))
        sh(self.other, "git", "commit", "-qam", "cfg"); sh(self.other, "git", "push", "-q", "origin", "main")
        sh(self.co, "git", "pull", "-q", "--ff-only")
        head_takes_base(self)
        self.pr_writes({"output-styles/日本.md": "a\n"})  # not in cp1252, unlike café
        try:
            rc, out = self.run_merge("7", "--confirm", stdout=PipeOut())
        except UnicodeEncodeError as e:
            self.fail(f"the run died with a traceback after the merge landed: {e}")
        self.assertEqual(rc, 0, out)
        self.assertTrue(getattr(self.host, "merged", False), out)
        flags = self.flags(out)
        self.assertEqual(len(flags), 1, out)  # one line, in any escaped form: only that it names the file
        self.assertTrue("output-styles/" in flags[0] and ".md" in flags[0], out)
        self.assertEqual(sh(self.co, "git", "rev-parse", "main"), sh(self.co, "git", "rev-parse", "origin/main"), out)  # ff_main ran
        self.assertTrue(os.path.exists(os.path.join(self.co, "after.txt")), out)  # afterMerge ran
        self.assertNotIn("refs/heads/feat", self.refs(), out)  # cut_branch ran
        self.assertFalse(self.lock_ref(), out)

    def test_a_lower_case_root_claude_md_is_flagged(self):  # Windows loads claude.md as CLAUDE.md
        self.pr_writes({"claude.md": "rules\n", "docs/claude.md": "x\n"})
        rc, out = self.run_merge("7", "--confirm")
        self.assert_flagged(rc, out, "claude.md")  # docs/claude.md is no rule file

    def test_the_other_rule_file_paths_match_without_case_too(self):
        self.pr_writes({".Claude/claude.md": "rules\n", "Output-Styles/A.md": "a\n", "notes/Output-Styles/b.md": "b\n"})
        rc, out = self.run_merge("7", "--confirm")
        self.assert_flagged(rc, out, ".Claude/claude.md", "Output-Styles/A.md")

class Race(Env):
    def test_two_runs_one_lock(self):
        lock2 = merge.GitLock(self.other, now=lambda: self.now)
        for _ in range(6):
            res = []
            bar = threading.Barrier(2)
            def go(lk):
                bar.wait()
                try:
                    res.append(lk.acquire("main", 600))
                except merge.Held:
                    res.append(None)
            ts = [threading.Thread(target=go, args=(lk,)) for lk in (self.lock, lock2)]
            [t.start() for t in ts]; [t.join() for t in ts]
            self.assertEqual(len([r for r in res if r]), 1, res)
            merge.GitLock(self.co).unlock("main")

    def test_a_stale_read_still_loses_at_the_push(self):
        # Both runs read "no lock" before either wrote. Only the create-only push can tell them apart.
        self.lock.acquire("main", 600)
        lock2 = merge.GitLock(self.other, now=lambda: self.now)
        lock2.read = lambda b, ref=None: None
        with self.assertRaises(merge.Held):
            lock2.acquire("main", 600)

    def test_a_held_lock_stops_a_full_run_and_touches_nothing(self):
        merge.GitLock(self.other, now=lambda: self.now).acquire("main", 600)
        before = self.refs()
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1)
        self.assertIn("held", out)
        self.assertEqual(self.refs(), before)

    def test_a_lock_that_is_not_ours_never_expires(self):
        sha = sh(self.co, "git", "commit-tree", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", "-m", "not ours")
        sh(self.co, "git", "push", "-q", "origin", f"{sha}:refs/heads/merge-lock/main")
        self.now += 10 ** 9
        with self.assertRaises(merge.Held):
            self.lock.acquire("main", 600)

class CloudProxy(Env):
    """The cloud proxy, measured on throwaway branches (c53): a push to refs/heads/* passes, any other ref and any ref delete get
    HTTP 403, and every REST write under git/ is refused. A pre-receive hook on the origin refuses the same pushes."""
    def setUp(self):
        super().setUp()
        hook = os.path.join(self.bare, "hooks", "pre-receive")
        put(hook, "#!/bin/sh\nwhile read old new ref; do\n"
                  "  case $new in 0000000000000000000000000000000000000000) echo 'proxy: 403 delete' >&2; exit 1;; esac\n"
                  "  case $ref in refs/heads/*) ;; *) echo 'proxy: 403 ref' >&2; exit 1;; esac\n"
                  "done\n")
        os.chmod(hook, 0o755)

    def lock_text(self):
        sh(self.co, "git", "fetch", "-q", "origin", "refs/heads/merge-lock/main")
        return sh(self.co, "git", "log", "-1", "--format=%B", "FETCH_HEAD")

    def test_a_full_merge_through_the_proxy_lands_and_leaves_an_expired_lock(self):
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertNotRegex(self.refs(), r"\trefs/merge-lock/")  # the ref the proxy refuses
        self.assertLessEqual(merge.expiry_of(self.lock_text()), self.now, out)  # released by a swap to an expired commit, never deleted
        self.assertNotIn("lock release failed", out)

    def test_a_second_run_is_held_while_the_first_holds_then_takes_the_released_lock(self):
        lock2 = merge.GitLock(self.other, now=lambda: self.now)
        token = self.lock.acquire("main", 600)
        with self.assertRaises(merge.Held):
            lock2.acquire("main", 600)
        self.lock.release("main", token)
        self.assertTrue(lock2.acquire("main", 600))

    def test_unlock_through_the_proxy_leaves_a_lock_anyone_may_take(self):
        merge.GitLock(self.other, now=lambda: self.now).acquire("main", 600)
        self.assertTrue(self.lock.unlock("main"))
        self.assertEqual(merge.expiry_of(self.lock_text()), 0)
        self.assertFalse(self.lock.unlock("main"))  # a released lock is no lock: nothing is pushed again
        self.assertEqual(merge.expiry_of(self.lock_text()), 0)
        self.assertTrue(self.lock.acquire("main", 600))

    def test_unlock_with_no_lock_reports_none_and_writes_nothing(self):
        before = self.refs()
        self.assertFalse(self.lock.unlock("main"))
        self.assertEqual(self.refs(), before)

    def test_a_release_never_touches_a_lock_another_run_took(self):
        token = self.lock.acquire("main", 600)
        self.now += 601  # expired: another run takes it by a leased push
        rival = merge.GitLock(self.other, now=lambda: self.now).acquire("main", 600)
        self.lock.release("main", token)
        self.assertEqual(self.refs().split("\trefs/heads/merge-lock/main")[0].split("\n")[-1], rival)

    def test_a_live_lock_under_the_old_name_holds_a_new_run_off(self):
        old = sh(self.co, "git", "commit-tree", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", "-m", merge.lock_message(600, self.now))
        hook = os.path.join(self.bare, "hooks", "pre-receive")
        os.rename(hook, hook + ".off")  # the old name was pushed by a Mac run, past no proxy
        sh(self.co, "git", "push", "-q", "origin", f"{old}:refs/merge-lock/main")
        os.rename(hook + ".off", hook)
        with self.assertRaisesRegex(merge.Held, "old name"):
            self.lock.acquire("main", 600)
        self.now += 601
        self.assertTrue(self.lock.acquire("main", 600))

    def test_a_cloud_session_picks_the_git_lock_and_a_mac_the_api_lock(self):
        with unittest.mock.patch.dict(os.environ, {"CLAUDE_CODE_REMOTE": "true"}):
            self.assertIsInstance(merge.default_lock(self.co), merge.GitLock)
        with unittest.mock.patch.dict(os.environ, {"CLAUDE_CODE_REMOTE": ""}):
            self.assertIsInstance(merge.default_lock(self.co), merge.GhLock)

class Guards(Env):
    def test_moved_head_is_refused_and_nothing_is_claimed(self):
        old = self.head()
        self.competitor_push()
        moved = self.head()
        self.host.head_override = old  # gh still names the old head
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1)
        self.assertIn("moved", out)
        self.assertEqual(self.head(), moved)
        self.assertEqual(self.claims(), 0)
        self.assertFalse(self.lock_ref())

    def test_refused_push_leaves_origin_alone_and_never_forces(self):
        self.hook(f'git -C "{self.other}" fetch -q origin feat && git -C "{self.other}" checkout -q -B feat origin/feat '
                  f'&& echo r > "{self.other}/rival.txt" && git -C "{self.other}" add -A && git -C "{self.other}" commit -qm rival '
                  f'&& git -C "{self.other}" push -q origin feat\n')
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)
        self.assertIn("refused", out)
        self.assertEqual(self.claims(), 0)
        self.assertEqual(self.head(), sh(self.other, "git", "rev-parse", "HEAD"))  # the rival commit survives
        self.assertFalse(self.lock_ref())
        self.assertEqual(self.worktrees(), 1)

    def test_red_check_reverts_the_claim(self):
        self.host.seq = [(True, ""), (False, "required check `build` is red")]  # the head is green, the claim run is red
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1)
        self.assertIn("`build` is red", out)
        self.assertIn("id: pending", self.show("feat", "docs/decisions/second.md"))
        self.assertEqual(self.claims("feat"), 1)  # the claim commit stays in history, reverted
        self.assertFalse(self.lock_ref())

    def test_red_check_after_a_push_in_the_wait_reverts_nothing(self):
        self.host.seq = [(True, ""), (False, "red")]
        self.host.on_wait = self.competitor_push
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1)
        self.assertIn("Nothing reverted", out)
        self.assertEqual(self.head(), sh(self.other, "git", "rev-parse", "HEAD"))
        self.assertIn("id: D-002", self.show("feat", "docs/decisions/second.md"))

    def test_protection_refusal_reverts_the_claim(self):
        self.host.refuse = "protected branch: 1 approving review required"
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1)
        self.assertIn("approving review", out)
        self.assertIn("id: pending", self.show("feat", "docs/decisions/second.md"))
        self.assertEqual(self.worktrees(), 1)

    def test_a_number_the_base_took_during_the_wait_reverts_the_claim(self):
        def base_takes_d2():
            o = self.other
            sh(o, "git", "fetch", "-q", "origin"); sh(o, "git", "checkout", "-q", "-B", "main", "origin/main")
            put(os.path.join(o, "docs/decisions/third.md"), record("D-002", "third"))
            sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-q", "-m", "base takes D-002"); sh(o, "git", "push", "-q", "origin", "main")
        self.host.on_wait = base_takes_d2
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1)
        self.assertIn("stale", out)
        self.assertIn("id: pending", self.show("feat", "docs/decisions/second.md"))

    def test_a_failed_base_fetch_stops_the_merge_and_never_checks_a_stale_base(self):
        self.host.merged = False
        self.host.on_wait = lambda: sh(self.co, "git", "remote", "set-url", "origin", os.path.join(self.t, "gone.git"))
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1)
        self.assertIn("cannot fetch origin main", out)
        self.assertFalse(self.host.merged)

    def main_moves(self):
        o = self.other
        sh(o, "git", "fetch", "-q", "origin"); sh(o, "git", "checkout", "-q", "-B", "main", "origin/main")
        put(os.path.join(o, "elsewhere.txt"), "main moved\n")
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-q", "-m", "main moves"); sh(o, "git", "push", "-q", "origin", "main")

    def test_a_head_without_the_base_tip_is_refused_before_any_claim(self):  # merge-needs-current-base
        self.main_moves()
        self.host.merged = False
        before = self.refs()
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)
        self.assertIn("does not hold origin/main", out)
        self.assertIn("Merge main into the branch", out)
        self.assertFalse(self.host.merged)
        self.assertEqual(self.host.waits, [])
        self.assertEqual(self.refs(), before)  # no claim push, and the lock ref is gone

    def test_a_base_that_moves_during_the_wait_reverts_the_claim_and_merges_nothing(self):
        self.host.merged = False
        self.host.on_wait = self.main_moves
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)
        self.assertIn("does not hold origin/main", out)
        self.assertFalse(self.host.merged)
        self.assertIn("id: pending", self.show("feat", "docs/decisions/second.md"))

    def test_a_head_that_merged_the_moved_base_merges(self):
        self.main_moves()
        o = self.other
        sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat"); sh(o, "git", "merge", "-q", "--no-edit", "main"); sh(o, "git", "push", "-q", "origin", "feat")
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertTrue(self.host.merged)

    def test_the_preview_names_a_head_without_the_base_tip(self):
        self.main_moves()
        rc, out = self.run_merge("7")
        self.assertIn("base:   BEHIND:", out)
        self.assertIn("--confirm refuses it", out)
        sh(self.other, "git", "checkout", "-q", "-B", "feat", "origin/feat"); sh(self.other, "git", "merge", "-q", "--no-edit", "main"); sh(self.other, "git", "push", "-q", "origin", "feat")
        rc, out = self.run_merge("7")
        self.assertIn("base:   holds main's tip", out)

    def test_the_claim_commit_works_with_no_git_identity(self):
        info = self.host.pr(7)
        tmp, wt = merge.open_worktree(self.co, info, "main")
        keep = {k: os.environ.pop(k) for k in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")}
        os.environ.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="user.useConfigOnly", GIT_CONFIG_VALUE_0="true")
        try:
            trailer = merge.do_claim(wt, ".github/stamp.json", "origin/main")
            self.assertEqual(len(merge.commit_claim(wt, trailer)), 40)
        finally:
            for k in ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0"):
                os.environ.pop(k)
            os.environ.update(keep)
            merge.drop_worktree(self.co, tmp, wt)

SCOPE_SCRIPT = os.path.join(HERE, "..", ".github", "scripts", "ci-scope.sh")  # the real script: the one home of which jobs read which paths
CHECKS_YML = ("name: checks\non: pull_request\njobs:\n  checks:\n    runs-on: ubuntu-latest\n    steps:\n"
             "      - name: Record slug check\n        run: python3 lint/check_slugs.py\n"
             "      - name: Guide reader suite\n        run: python3 hooks/test_reads_guide.py\n")
SLUG_LINT = '''import collections, os, re, sys
seen = collections.defaultdict(list)
for d, _, names in os.walk("docs"):
    for n in names:
        if n.endswith(".md"):
            m = re.search(r"^slug: (.+)$", open(os.path.join(d, n), encoding="utf-8").read(), re.M)
            if m:
                seen[m.group(1)].append(n)
bad = {k: v for k, v in seen.items() if len(v) > 1}
print(bad or "ok")
sys.exit(1 if bad else 0)
'''
DOC_SUITE = '''import os, sys
path = os.path.join("docs", "guide.md")  # a checks suite that reads one tracked doc, named in no list
sys.exit(1 if os.path.exists(path) and "BROKEN" in open(path, encoding="utf-8").read() else 0)
'''

class SmallBaseMove(Env):
    """Main moved, but only by paths that no CI job of the batch reads (merge-needs-current-base, step c150).
    The real ci-scope.sh and the real bin/ci-job run against a fixture workflow whose `checks` job holds one cross-file lint:
    no two docs share a slug. hooks/test_reads_guide.py is a checks suite outside --lint that reads docs/guide.md."""

    def scoped(self, workflow=CHECKS_YML, scope=True):
        """Main and feat both gain the CI files; feat then holds main's tip."""
        o = self.other
        sh(o, "git", "fetch", "-q", "origin"); sh(o, "git", "checkout", "-q", "-B", "main", "origin/main")
        if scope:
            with open(SCOPE_SCRIPT, encoding="utf-8") as f:
                put(os.path.join(o, ".github/scripts/ci-scope.sh"), f.read())
        put(os.path.join(o, ".github/workflows/checks.yml"), workflow)
        put(os.path.join(o, "landed-dirs.txt"), "hooks\n")
        put(os.path.join(o, "lint/check_slugs.py"), SLUG_LINT)
        put(os.path.join(o, "hooks/test_reads_guide.py"), DOC_SUITE)
        put(os.path.join(o, "hooks/x.py"), "X = 1\n")
        put(os.path.join(o, "docs/shared.md"), "one\ntwo\nthree\nfour\nfive\n")
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-qm", "ci files"); sh(o, "git", "push", "-q", "origin", "main")
        sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat"); sh(o, "git", "merge", "-q", "--no-edit", "main"); sh(o, "git", "push", "-q", "origin", "feat")

    def on(self, branch, files):
        o = self.other
        sh(o, "git", "fetch", "-q", "origin"); sh(o, "git", "checkout", "-q", "-B", branch, f"origin/{branch}")
        for path, text in files.items():
            put(os.path.join(o, path), text)
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-qm", f"{branch} moves"); sh(o, "git", "push", "-q", "origin", branch)

    def refused(self):
        self.host.merged = False
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)
        self.assertIn("does not hold origin/main", out)
        self.assertIn("Merge main into the branch", out)
        self.assertFalse(self.host.merged, out)
        return out

    def test_a_docs_only_main_move_keeps_the_green_run(self):
        self.scoped()
        self.on("main", {"docs/guide.md": "# Guide\n"})
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertTrue(self.host.merged, out)
        self.assertNotIn("does not hold", out)
        self.assertIn("main moved by 1 commit touching only paths no job of this batch reads; the lints pass on the merge", out)
        self.assertIn("# Guide", self.show("main", "docs/guide.md"))

    def test_a_docs_only_move_during_the_wait_keeps_the_green_run(self):
        self.scoped()
        self.host.on_wait = lambda: self.on("main", {"docs/late.md": "# Late\n"})
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertTrue(self.host.merged, out)

    def test_the_preview_says_a_docs_only_move_keeps_the_green_run(self):
        self.scoped()
        self.on("main", {"docs/guide.md": "# Guide\n"})
        rc, out = self.run_merge("7")
        self.assertIn("base:   main moved by 1 commit touching only paths no job of this batch reads", out)
        self.assertNotIn("BEHIND", out)

    def test_main_touching_a_file_of_the_batch_is_refused(self):
        self.scoped()
        self.on("feat", {"docs/shared.md": "one changed\ntwo\nthree\nfour\nfive\n"})
        self.on("main", {"docs/shared.md": "one\ntwo\nthree\nfour\nfive changed\n"})  # merges clean, but one path
        self.assertIn("docs/shared.md", self.refused())

    def test_a_conflicting_main_move_is_refused(self):
        self.scoped()
        self.on("feat", {"docs/shared.md": "one\nfeat\n"})
        self.on("main", {"docs/shared.md": "one\nmain\n"})
        self.refused()

    def test_main_touching_a_code_path_is_refused(self):
        self.scoped()
        self.on("main", {"hooks/x.py": "X = 2\n"})
        self.refused()

    def test_main_touching_an_unmapped_path_is_refused(self):
        self.scoped()
        self.on("main", {"notes.txt": "a note\n"})
        self.refused()

    def test_a_main_doc_that_breaks_a_cross_file_lint_on_the_merge_is_refused(self):
        self.scoped()
        self.on("main", {"docs/other.md": "---\nslug: second\n---\n"})  # feat's record has slug second: each side alone passes
        self.refused()

    def test_a_main_doc_that_breaks_a_checks_suite_reading_docs_is_refused(self):
        self.scoped()
        self.on("main", {"docs/guide.md": "BROKEN\n"})
        self.refused()

    def test_a_scope_script_that_fails_with_every_flag_off_is_refused_with_its_exit(self):
        self.scoped()
        self.on("main", {".github/scripts/ci-scope.sh": 'for n in code mods; do echo "$n=false" >> "$GITHUB_OUTPUT"; done; exit 3\n'})
        o = self.other  # feat takes main's script, then main moves by a doc only
        sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat"); sh(o, "git", "merge", "-q", "--no-edit", "origin/main"); sh(o, "git", "push", "-q", "origin", "feat")
        self.on("main", {"docs/guide.md": "# Guide\n"})
        self.assertIn("exit 3", self.refused())

    def test_the_suites_a_doc_hits_come_from_the_checks_job(self):
        root = os.path.join(HERE, "..")
        lints = merge.lint_steps(root, "origin/main")
        hits = lambda path: [f for f, _ in merge.hit_suites(root, [path], lints)]
        self.assertIn("hooks/test_sendmessage_state.py", hits("docs/decisions/agent-model-cap.md"))
        self.assertIn("skills/project-ops/tests/test_scaffold.py", hits("skills/project-ops/templates/new.md"))
        self.assertNotIn("hooks/test_sendmessage_state.py", hits("docs/guide-c150.md"))
        new = hits("docs/decisions/" + "new-" + "rec.md")  # a new record, split so this file names no such path: the suite that lists the folder runs, fixture-only suites do not
        self.assertIn("hooks/test_precompact_handoff.py", new)
        self.assertNotIn("hooks/test_guard.py", new)
        self.assertIn("merge/test_merge.py", new)  # this suite reads the real tree whole, just above, so every path hits it
        self.assertIn("skills/ios-apps/tests/test_new_app.py", hits("skills/ios-apps/templates/" + "new.md"))  # through new_app.py

    def test_a_folder_named_only_in_a_temp_tree_is_no_hit(self):
        hit = lambda src: merge.python_suite_hits(src, "hooks/test_x.py", ["docs/decisions/x.md"])
        self.assertFalse(hit('import os, tempfile\nd = tempfile.mkdtemp()\nos.makedirs(os.path.join(d, "docs", "decisions"))\n'))
        self.assertFalse(hit('TEXT = "see decisions/other.md"  # a cite in text\n'))
        self.assertTrue(hit('import os\nROOT = os.path.dirname(os.path.dirname(__file__))\nD = os.path.join(ROOT, "docs", "decisions")\n'))
        self.assertTrue(hit('import pathlib\nROOT = pathlib.Path(__file__).parent.parent\nD = ROOT / "docs" / "decisions"\n'))
        self.assertTrue(hit('open("docs/decisions/y.md").read()\n'))
        self.assertTrue(hit('import os\nos.listdir(os.path.join("docs", "decisions"))\n'))
        self.assertTrue(hit('X = "docs/decisions/x.md"\n'))  # the exact path, anywhere
        # a root anchored on __file__ and walked whole: a path under it is read
        self.assertTrue(merge.python_suite_hits('import os\nHERE = os.path.dirname(__file__)\nSKILL = os.path.dirname(HERE)\nwalk(SKILL)\n',
                                                "skills/s/tests/test_s.py", ["skills/s/templates/new.md"]))
        with self.assertRaises(SyntaxError):
            hit("def (:\n")

    def test_a_root_read_in_any_form_is_a_hit(self):
        hit = lambda src, path="docs/decisions/x.md": merge.python_suite_hits(src, "hooks/test_x.py", [path])
        here = "import os, pathlib\nHERE = os.path.dirname(os.path.abspath(__file__))\nROOT = os.path.dirname(HERE)\n"
        for form in ('open(f"{ROOT}/docs/decisions/a.md")', 'open(ROOT + "/docs/decisions/a.md")',
                     'open("{}/docs/decisions/a.md".format(ROOT))', 'open("%s/docs/decisions/a.md" % ROOT)',
                     'D = pathlib.Path(__file__).resolve().parents[1] / "docs" / "decisions"'):
            with self.subTest(form=form):
                self.assertTrue(hit(here + form + "\n"))

    def test_a_root_at_the_repo_top_is_a_hit(self):
        hit = lambda src, path="docs/decisions/x.md": merge.python_suite_hits(src, "hooks/test_x.py", [path])
        here = "import os, pathlib\nHERE = os.path.dirname(os.path.abspath(__file__))\n"
        self.assertTrue(hit(here + 'DOCS = os.path.join(os.path.dirname(HERE), "docs")\nos.listdir(DOCS)\n'))
        self.assertTrue(hit(here + 'DOCS = os.path.join(os.path.dirname(HERE), "docs")\nfor x in os.walk(DOCS): pass\n'))
        self.assertTrue(hit('import pathlib\nD = pathlib.Path(__file__).resolve().parent.parent / "docs"\nlist(D.rglob("*.md"))\n'))
        self.assertTrue(hit(here + 'for x in os.walk(os.path.dirname(HERE)): pass\n', "notes/any.md"))  # the whole repo: every path

    def test_a_read_through_a_local_module_is_a_hit(self):
        files = {"skills/s/tests/test_s.py": "import os, sys\nsys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts'))\nimport helper\n",
                 "skills/s/scripts/helper.py": "import os\nT = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')\nos.listdir(T)\n",
                 "hooks/test_y.py": "import sibling\n", "hooks/sibling.py": "open('docs/decisions/y.md')\n"}
        read = files.get
        self.assertTrue(merge.python_suite_hits(files["skills/s/tests/test_s.py"], "skills/s/tests/test_s.py", ["skills/s/templates/new.md"], read))
        self.assertTrue(merge.python_suite_hits(files["hooks/test_y.py"], "hooks/test_y.py", ["docs/decisions/z.md"], read))
        self.assertFalse(merge.python_suite_hits("import nowhere\n", "hooks/test_z.py", ["docs/decisions/z.md"], read))

    def test_a_checks_line_of_no_suite_form_that_names_main_s_path_is_refused(self):
        self.scoped(workflow=CHECKS_YML + "      - name: Other runner\n        run: sh -c 'grep -q x docs/guide.md || true'\n")
        self.on("main", {"docs/guide.md": "# Guide\n"})
        self.assertIn("docs/guide.md", self.refused())

    def test_a_records_only_main_move_keeps_the_green_run(self):
        """A new record and the page rebuilt on main; a checks suite names the record folder only in its temp tree."""
        self.scoped(workflow=CHECKS_YML + "      - name: Temp tree suite\n        run: python3 hooks/test_temp_tree.py\n")
        o = self.other
        sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        put(os.path.join(o, "hooks/test_temp_tree.py"), 'import os, sys, tempfile\nd = tempfile.mkdtemp()\n'
            'os.makedirs(os.path.join(d, "docs", "decisions"))\nsys.exit(1)  # fails if it is ever run on the merge\n')
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-qm", "temp suite"); sh(o, "git", "push", "-q", "origin", "feat")
        sh(o, "git", "checkout", "-q", "-B", "main", "origin/main"); sh(o, "git", "merge", "-q", "--no-edit", "origin/feat")
        sh(o, "git", "push", "-q", "origin", "main")
        put(os.path.join(o, "docs/decisions/third.md"), record("D-009", "third"))
        sh(o, sys.executable, merge.RECORDS, "--root", o, "--records-only")
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-qm", "main: a record"); sh(o, "git", "push", "-q", "origin", "main")
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertTrue(self.host.merged, out)
        self.assertIn("touching only paths no job of this batch reads", out)

    def test_an_unreadable_merge_base_is_refused(self):
        self.scoped()
        self.on("main", {"docs/guide.md": "# Guide\n"})
        real = merge.git
        def git(cwd, *a, **k):
            if a and a[0] == "merge-base" and "--is-ancestor" not in a:
                return 128, "fatal: no merge base"
            return real(cwd, *a, **k)
        with unittest.mock.patch.object(merge, "git", git):
            self.refused()

    def test_a_repo_without_the_scope_script_is_refused(self):
        self.scoped(scope=False)
        self.on("main", {"docs/guide.md": "# Guide\n"})
        self.refused()

    def test_a_lint_run_that_cannot_find_the_job_is_refused(self):
        self.scoped(workflow=CHECKS_YML.replace("  checks:", "  other:"))
        self.on("main", {"docs/guide.md": "# Guide\n"})
        self.refused()

    def test_a_lint_step_ci_job_cannot_read_is_refused(self):
        self.scoped(workflow=CHECKS_YML + "      - name: Unread\n        if: ${{ github.actor == 'x' }}\n        run: python3 lint/check_slugs.py\n")
        self.on("main", {"docs/guide.md": "# Guide\n"})
        self.refused()

class CutBranch(Env):
    def local_branch(self, extra):
        sh(self.co, "git", "fetch", "-q", "origin")
        sh(self.co, "git", "branch", "feat", "origin/feat")
        if extra:
            sh(self.co, "git", "checkout", "-q", "feat")
            put(os.path.join(self.co, "local-only.txt"), "x")
            sh(self.co, "git", "add", "-A"); sh(self.co, "git", "commit", "-q", "-m", "local only")
            sh(self.co, "git", "checkout", "-q", "main")
        return self.head()

    def cut(self, merged):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            merge.cut_branch(self.co, "feat", merged)
        return out.getvalue()

    def exists(self):
        return subprocess.run(["git", "-C", self.co, "rev-parse", "-q", "--verify", "refs/heads/feat"], capture_output=True).returncode == 0

    def test_local_branch_inside_the_merged_head_is_deleted(self):
        out = self.cut(self.local_branch(False))
        self.assertIn("feat here: deleted", out)
        self.assertFalse(self.exists())
        self.assertNotIn("refs/heads/feat", self.refs())

    def test_a_gone_remote_ref_counts_as_deleted(self):
        self.local_branch(False)
        sh(self.co, "git", "push", "-q", "origin", "--delete", "feat")
        out = self.cut(self.head())
        self.assertIn("origin/feat: already deleted.", out)
        self.assertNotIn("not deleted", out.split("feat here")[0])

    def test_local_only_commits_keep_the_branch(self):
        out = self.cut(self.local_branch(True))
        self.assertIn("local-only commits", out)
        self.assertTrue(self.exists())

class CutBranchTree(Env):
    """cut_branch when a worktree holds the merged branch. A clean tree whose HEAD is in the merged default branch goes,
    with its folder and its branch. Any other tree stays, with one `merge: feat kept here: ...` line that says why."""

    def setUp(self):
        super().setUp()
        self.wt = os.path.join(self.t, "wt-feat")
        self.old_cwd = os.getcwd()
        self.addCleanup(os.chdir, self.old_cwd)

    def merged_feat(self):
        """Put feat's tip on origin/main, as a merge would, and move the local main onto it. -> the merged sha."""
        o = self.other
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", "main", "origin/main")
        sh(o, "git", "merge", "-q", "--no-ff", "-m", "merge feat", "origin/feat")
        sh(o, "git", "push", "-q", "origin", "main")
        sh(self.co, "git", "fetch", "-q", "origin")
        sh(self.co, "git", "merge", "-q", "--ff-only", "origin/main")
        return sh(self.co, "git", "rev-parse", "origin/main")

    def worktree(self):
        """A worktree on local feat, at origin/feat. Returns nothing; the caller edits it."""
        sh(self.co, "git", "branch", "feat", "origin/feat")
        sh(self.co, "git", "worktree", "add", "-q", self.wt, "feat")
        self.assertTrue(tree_listed(self.co, self.wt), "subject: the worktree must exist first")

    def cut(self, merged):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            merge.cut_branch(self.co, "feat", merged)
        return out.getvalue()

    def exists(self):
        return subprocess.run(["git", "-C", self.co, "rev-parse", "-q", "--verify", "refs/heads/feat"], capture_output=True).returncode == 0

    def listed(self):
        return sh(self.co, "git", "worktree", "list")

    def kept_lines(self, out):
        return [l for l in out.splitlines() if l.startswith("merge: feat kept here:")]

    def assertKept(self, out, why):
        lines = self.kept_lines(out)
        self.assertEqual(len(lines), 1, f"one kept line, got: {out!r}")
        self.assertRegex(lines[0], why)
        self.assertTrue(os.path.isdir(self.wt), f"the tree was removed; out: {out!r}")
        self.assertTrue(tree_listed(self.co, self.wt), self.listed())
        self.assertTrue(self.exists(), f"the branch was deleted; out: {out!r}")

    def assert_clean_tree_removed(self, merged):
        self.worktree()
        out = self.cut(merged)
        self.assertFalse(os.path.exists(self.wt), f"the worktree folder is still there; out: {out!r}")
        self.assertFalse(tree_listed(self.co, self.wt), self.listed())
        self.assertFalse(self.exists(), f"the local branch feat was not deleted; out: {out!r}")
        self.assertIn("feat here: deleted", out)

    def test_clean_merged_tree_is_removed_with_its_branch(self):
        self.assert_clean_tree_removed(self.merged_feat())

    def test_clean_merged_tree_is_removed_when_merged_is_the_pr_head(self):
        # Production passes the PR head sha (merge.py `cut_branch(root, branch, sha)`), not origin/main.
        head = sh(self.co, "git", "rev-parse", "origin/feat")
        self.merged_feat()
        self.assert_clean_tree_removed(head)

    def test_dirty_tree_is_kept(self):
        merged = self.merged_feat()
        self.worktree()
        put(os.path.join(self.wt, "scratch.txt"), "an uncommitted edit\n")
        self.assertKept(self.cut(merged), r"feat kept here: .*dirty")

    def test_head_with_a_commit_the_default_branch_lacks_is_kept(self):
        merged = self.merged_feat()
        self.worktree()
        put(os.path.join(self.wt, "local-only.txt"), "x\n")
        sh(self.wt, "git", "add", "-A"); sh(self.wt, "git", "commit", "-q", "-m", "local only")
        self.assertKept(self.cut(merged), r"feat kept here: .*(local-only|not in)")

    def test_tree_whose_cwd_is_inside_it_is_kept(self):
        merged = self.merged_feat()
        self.worktree()
        os.chdir(self.wt)
        self.assertKept(self.cut(merged), r"feat kept here: .*(cwd|current directory|working directory)")

    def test_tree_locked_by_a_live_agent_is_kept(self):
        sys.path.insert(0, os.path.join(HERE, "..", "hooks"))  # the process-start read the lock's verdict uses
        sys.path.insert(0, os.path.join(HERE, "..", "janitor"))
        import git_reads
        merged = self.merged_feat()
        self.worktree()
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        self.addCleanup(lambda: (child.kill(), child.wait()))
        started = git_reads._process_start_ms(child.pid)
        self.assertIsNotNone(started, "could not read the child's start time")
        start = time.strftime("%a %b %d %H:%M:%S %Y", time.gmtime(started / 1000))
        sh(self.co, "git", "worktree", "lock", "--reason", f"claude agent agent-x (pid {child.pid} start {start})", self.wt)
        import sweep  # janitor/sweep.py, the module merge.remove_held_tree imports
        with unittest.mock.patch.object(sweep, "remove_worktree", wraps=sweep.remove_worktree) as remove:
            out = self.cut(merged)
        self.assertFalse(remove.called, f"the sweep removed a tree its own lock rule keeps; out: {out!r}")
        self.assertKept(out, r"feat kept here: .*locked: claude agent agent-x")

# ------------------------------------------------------------------ the lanes of a batch
# One line per lane, pinned here and nowhere else. A merge deletes the lane branches its batch took in.
LANE_KEPT = "merge: lane origin/{b}: kept: {why}"
LANE_FAILED = "merge: lane origin/{b}: not deleted: "  # then the last line of git's reply, as cut_branch prints it
WHY = {"open": "it has an open PR.", "keep": "it is in merge.keepBranches.", "unproven": "its tip is not in the merge commit.",
       "unread": "the open PRs could not be read."}
HELD = {"batch-map", "map-format-version", "map-skill-move", "claude-p-fetch-key"}  # the branches the repo's own config keeps
# The new lines, pinned by their words. The builder picks the rest of each line.
LANE_HEADS_UNREAD = ("unreadable", "could not be read")  # ruling 2: the one line when the origin heads cannot be read
LANE_MOVED = ("moved", "gone")  # ruling 2: the one line for a lane tip that no origin head sits at; it names the tip
LANE_PROOF_NOT_RUN = "could not run"  # ruling 5: the kept line when the merge commit cannot be read, in place of WHY["unproven"]

def lane_batch(env, *names):
    """Cut each lane off origin/main, push it, then merge every lane into feat with a merge commit, as an integration branch does.
    -> {lane: tip}. Without --no-ff there is no merge commit, so no second parent. Also sets env.tips for lane_deleted_line."""
    o, tips = env.other, {}
    for n in names:
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", n, "origin/main")
        put(os.path.join(o, n.replace("/", "-") + ".txt"), n + "\n")
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-q", "-m", f"lane {n}"); sh(o, "git", "push", "-q", "origin", n)
        tips[n] = sh(o, "git", "rev-parse", "HEAD")
    sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
    for n in names:
        sh(o, "git", "merge", "-q", "--no-ff", "-m", f"Merge remote-tracking branch 'origin/{n}' into feat", tips[n])
    sh(o, "git", "push", "-q", "origin", "feat")
    env.tips = tips
    return tips

def lane_lines(out, b):
    """Every line that names lane origin/b with a deleted outcome."""
    return [l for l in out.splitlines() if f"origin/{b}" in l and "deleted" in l and "not deleted" not in l]

def lane_deleted_line(test, out, b):
    """Finding 4: the one line for a deleted lane names the lane's branch and its 9-character tip. -> that line."""
    lines = lane_lines(out, b)
    test.assertEqual(len(lines), 1, out)
    test.assertIn(test.tips[b][:9], lines[0], "the deleted line of %s must name its tip %s" % (b, test.tips[b][:9]))
    return lines[0]

def kept_line(test, out, b):
    """The one kept line of lane origin/b. -> that line."""
    lines = [l for l in out.splitlines() if l.startswith(f"merge: lane origin/{b}: kept:")]
    test.assertEqual(len(lines), 1, out)
    return lines[0]

def raw_tab_strings(source):
    """Source scan through tokenize. -> (line, text) of each string token that holds a raw TAB character. Tokenize reads a string
    whole, so a '#' or a quote inside a string, and a string over several lines, are never taken for code or for a comment."""
    kinds = {tokenize.STRING} | ({tokenize.FSTRING_MIDDLE} if hasattr(tokenize, "FSTRING_MIDDLE") else set())
    return [(tok.start[0], tok.string) for tok in tokenize.generate_tokens(io.StringIO(source).readline)
            if tok.type in kinds and "\t" in tok.string]

class LaneHost(FakeHost):
    """FakeHost plus the open-PR read. style: how the merge lands, merge (a merge commit), squash or rebase.
    unreadable: stop (raises Stop), none (returns None) or error (raises ValueError). on_merged runs once the merge is on origin.
    open: {head name: (head sha, PR base)} of the open pull requests, the shape Host.open_heads returns.
    A PR at the lane tip is the lane's own only when its base is the batch's base.
    prs: raw rows [(head name, head sha, PR base), ...], one per open PR, in the order GitHub lists them. When set, open_heads
    runs the real Host.open_heads over these rows, so a case does not pin the shape that read returns."""
    style, open, unreadable, on_merged, prs = "merge", {}, None, None, None

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.open_calls = 0

    def open_heads(self):
        self.open_calls += 1
        if self.unreadable == "stop":
            raise merge.Stop("gh pr list failed: HTTP 502")
        if self.unreadable == "none":
            return None
        if self.unreadable == "error":
            raise ValueError("not json")
        if self.prs is not None:
            host = merge.Host()
            items = [REST.list_item(100 + i, s, h, b) for i, (h, s, b) in enumerate(self.prs)]

            def gh(args, cwd=None):
                assert args[:1] == ["api"], f"unexpected gh call: {args}"
                method, path, params, flags, jq = REST.parse(args[1:])
                assert method == "GET" and re.fullmatch(r"repos/(?:\{owner\}/\{repo\}|[^/]+/[^/]+)/pulls", path), (method, path)
                return 0, REST.listing(items, None, params, flags, jq, 100)
            host.gh = gh
            return host.open_heads()
        return dict(self.open)

    def merge(self, n, method, sha):
        if self.style == "merge":
            got = super().merge(n, method, sha)
        else:
            o = self.other
            sh(o, "git", "fetch", "-q", "origin")
            if self.style == "squash":
                sh(o, "git", "checkout", "-q", "-B", "main", "origin/main")
                sh(o, "git", "merge", "-q", "--squash", sha)
                sh(o, "git", "commit", "-q", "-m", f"squash #{n}")
                sh(o, "git", "push", "-q", "origin", "main")
            else:  # rebase: the lane commits are replayed with new ids and the merge commits drop out
                sh(o, "git", "checkout", "-q", "-B", "rebased", sha)
                sh(o, "git", "rebase", "-q", "origin/main")
                sh(o, "git", "push", "-q", "origin", "rebased:main")
            got = sh(o, "git", "rev-parse", "HEAD"), ""
        if self.on_merged:
            self.on_merged()
        return got

class CutLanes(Env):
    """After a merge, the lane branches the batch took in are deleted on origin. Driven end to end through merge.main,
    so the split of work inside cut_lanes stays the builder's. Each keep case has a lane in the same batch that must go,
    so a tool that deletes nothing fails it."""
    def setUp(self):
        super().setUp()
        self.host = LaneHost(self.co, self.other)

    def go(self):
        return self.run_merge("7", "--confirm")

    @contextlib.contextmanager
    def spy(self, after=None):
        """Every program merge.py runs through merge.sh, as arg lists. after(args, result) runs after each real call."""
        real, calls = merge.sh, []
        def wrapped(args, *a, **k):
            r = real(args, *a, **k)
            calls.append(list(args))
            if after:
                after(args, r)
            return r
        with unittest.mock.patch.object(merge, "sh", wrapped):
            yield calls

    def push_to(self, branch):
        """A rival pushes one more commit to `branch`. -> its new tip."""
        o = self.other
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", branch, f"origin/{branch}")
        put(os.path.join(o, "rival.txt"), "pushed after the batch\n")
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-q", "-m", "rival"); sh(o, "git", "push", "-q", "origin", branch)
        return sh(o, "git", "rev-parse", "HEAD")

    def assert_deleted(self, out, *names):
        for b in names:
            lane_deleted_line(self, out, b)
            self.assertEqual(self.head(b), "", f"{b} is still on origin")

    def assert_kept(self, out, b, why):
        self.assertIn(LANE_KEPT.format(b=b, why=WHY[why]), out)
        self.assertNotEqual(self.head(b), "", f"{b} was deleted")

    def assert_kept_line(self, out, b):
        """The lane is kept, with exactly one kept line for it and no deleted line. The reason text is not pinned."""
        kept = [l for l in out.splitlines() if l.startswith(f"merge: lane origin/{b}: kept:")]
        self.assertEqual(len(kept), 1, out)
        self.assertNotEqual(self.head(b), "", f"{b} was deleted")
        self.assertEqual(lane_lines(out, b), [], out)

    def assert_merged(self):
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))

    def assert_moved_line(self, out, tip):
        """Ruling 2: no origin head sits at this lane tip. One line names the tip (its first 9 characters) and says moved or gone."""
        lines = [l for l in out.splitlines() if tip[:9] in l]
        self.assertEqual(len(lines), 1, out)
        self.assertTrue(any(w in lines[0] for w in LANE_MOVED), lines[0])

    def assert_one_lane_line(self, out, words=None):
        """Rulings 2 and 3: the whole cleanup prints one line, and when `words` is given that line holds one of them."""
        lines = [l for l in out.splitlines() if "lane" in l]
        self.assertEqual(len(lines), 1, out)
        if words:
            self.assertTrue(any(w in lines[0] for w in words), lines[0])
        self.assertNotIn("Traceback", out)

    def test_two_lanes_in_the_batch_are_deleted_after_the_merge(self):
        tips = lane_batch(self, "agent/lane1", "lane2")
        with self.spy() as calls:
            rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_merged()
        self.assert_deleted(out, "agent/lane1", "lane2")
        self.assertEqual(self.host.open_calls, 1)
        self.assertEqual(self.head("feat"), "")  # the PR's own branch is cut_branch's, and it prints its own line
        self.assertNotIn("merge: lane origin/feat", out)
        self.assertNotIn("not deleted", out)
        self.assertNotIn("keepBranches", out)  # a config without the field is no notice
        self.assertNotEqual(self.head("main"), "")
        for b, tip in tips.items():  # the delete is leased to the tip the batch took in
            want = [f"--force-with-lease=refs/heads/{b}:{tip}", f":refs/heads/{b}"]
            self.assertTrue(any("push" in c and "origin" in c and all(w in c for w in want) for c in calls), f"no leased delete push for {b}")
        self.assertFalse(self.lock_ref())

    def merge_of(self, lane):
        """The batch's newest merge commit for `lane`, on the other clone's feat."""
        return sh(self.other, "git", "log", "-1", "--merges", "--format=%H", f"--grep=origin/{lane}' into", "feat")

    def revert_on_batch(self, sha, merge=True):
        """Revert `sha` on the batch (-m 1 for a merge commit) and push. -> the revert commit."""
        o = self.other
        sh(o, "git", "revert", *(["-m", "1"] if merge else []), "--no-edit", sha)
        sh(o, "git", "push", "-q", "origin", "feat")
        return sh(o, "git", "rev-parse", "HEAD")

    def assert_refused_drop(self, rc, out, feat):
        """c110: a batch that drops a lane by a revert of its merge is refused before anything is claimed, pushed or merged."""
        self.assertEqual(rc, 1, out)
        self.assertIn("rebuild the batch branch from main without the lane", out)
        self.assertNotIn("merged as", out)
        self.assertEqual(self.claims("feat"), 0, "the refusal claimed record numbers")
        self.assertEqual(self.head("feat"), feat, "the refusal pushed to the batch branch")
        for b in self.tips:
            self.assertNotEqual(self.head(b), "", f"{b} was deleted")
        self.assertFalse(self.lock_ref())

    def test_a_batch_that_drops_a_lane_by_a_revert_is_refused(self):
        lane_batch(self, "lane1", "lane2")
        feat = self.revert_on_batch(self.merge_of("lane1"))
        rc, out = self.go()
        self.assert_refused_drop(rc, out, feat)

    def test_the_preview_blocks_a_batch_that_drops_a_lane_by_a_revert(self):
        lane_batch(self, "lane1", "lane2")
        self.revert_on_batch(self.merge_of("lane1"))
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 1, out)
        blocked = [l for l in out.splitlines() if l.startswith("BLOCKED:")]
        self.assertEqual(len(blocked), 1, out)
        self.assertIn("revert", blocked[0])

    def test_a_lane_reverted_then_reapplied_is_deleted(self):
        lane_batch(self, "lane1", "lane2")
        rev = self.revert_on_batch(self.merge_of("lane1"))
        self.revert_on_batch(rev, merge=False)  # revert the revert: the lane is live again
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_deleted(out, "lane1", "lane2")

    def test_a_lane_reverted_then_merged_again_at_a_new_tip_is_refused(self):
        lane_batch(self, "lane1", "lane2")
        self.revert_on_batch(self.merge_of("lane1"))
        o = self.other
        sh(o, "git", "checkout", "-q", "-B", "lane1", "origin/lane1")
        put(os.path.join(o, "lane1-fix.txt"), "fix\n")
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-q", "-m", "lane lane1 fix"); sh(o, "git", "push", "-q", "origin", "lane1")
        new_tip = sh(o, "git", "rev-parse", "HEAD")
        sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        sh(o, "git", "merge", "-q", "--no-ff", "-m", "Merge remote-tracking branch 'origin/lane1' into feat", new_tip)
        sh(o, "git", "push", "-q", "origin", "feat")
        self.tips["lane1"] = new_tip
        rc, out = self.go()  # the new merge brings only the fix: the reverted lane commit stays undone, so main would lose its file
        self.assert_refused_drop(rc, out, self.head("feat"))

    def test_a_lane_pushed_to_after_the_merge_is_kept(self):
        tips = lane_batch(self, "lane1", "lane2")
        moved = []
        self.host.on_merged = lambda: moved.append(self.push_to("lane2"))
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_deleted(out, "lane1")
        self.assertEqual(self.head("lane2"), moved[0])
        self.assertEqual(lane_lines(out, "lane2"), [], out)
        self.assert_moved_line(out, tips["lane2"])  # ruling 2: the tip has no origin head now, so one line says so

    def test_a_lane_deleted_on_origin_after_the_merge_gets_one_line(self):
        tips = lane_batch(self, "lane1", "lane2")
        self.host.on_merged = lambda: sh(self.other, "git", "push", "-q", "origin", "--delete", "lane2")
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_deleted(out, "lane1")
        self.assertEqual(self.head("lane2"), "")
        self.assert_moved_line(out, tips["lane2"])  # ruling 2: gone counts as no head at the tip

    def test_a_lane_that_moves_between_the_read_and_the_delete_is_kept(self):
        lane_batch(self, "lane1", "lane2")
        moved = []
        def rival(args, result):  # the first read of the heads that lists lane2
            if "ls-remote" in args and "refs/heads/lane2" in result[1] and not moved:
                moved.append(self.push_to("lane2"))
        with self.spy(rival):
            rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertTrue(moved, "no read of the origin heads listed lane2")
        self.assert_deleted(out, "lane1")
        self.assertEqual(self.head("lane2"), moved[0])
        self.assertEqual(lane_lines(out, "lane2"), [], out)

    def test_a_lane_with_an_open_pr_at_its_tip_is_deleted(self):
        # Per decision merge-deletes-batch-lanes (lane cleanup): GitHub marks a lane's PR merged 1-2 s after the batch, so the read can see it open at the tip.
        # That PR's base is the batch's base, so it is the lane's own PR, and the lane is deleted.
        tips = lane_batch(self, "lane1", "lane2")
        self.host.open = {"lane1": (tips["lane1"], "main")}
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_deleted(out, "lane1", "lane2")
        self.assertNotIn(WHY["open"], out)

    def test_a_lane_with_an_open_pr_at_a_newer_sha_is_kept(self):
        # The control: this passes on the old code, which blocks on any open PR. A fix that ignores the sha fails it.
        lane_batch(self, "lane1", "lane2")
        self.host.open = {"lane1": (self.head("main"), "main")}  # the PR reports a commit that is not the lane tip
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_deleted(out, "lane2")
        self.assert_kept(out, "lane1", "open")

    def test_a_backport_pr_at_the_lane_tip_keeps_the_lane(self):
        # The open PR at the tip has another base (a backport to release/1.0), so it is not the lane's own, and the lane is kept.
        tips = lane_batch(self, "lane1", "lane2")
        self.host.open = {"lane1": (tips["lane1"], "release/1.0")}
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_kept_line(out, "lane1")
        self.assert_deleted(out, "lane2")

    def test_a_lane_that_is_the_base_of_an_open_pr_is_kept(self):
        # A stacked PR (head stack, base lane1) is open, so lane1 stays. The stack's head is not lane1's tip, so this is not lane1's own PR.
        lane_batch(self, "lane1", "lane2")
        self.host.open = {"stack": (self.head("main"), "lane1")}
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_kept_line(out, "lane1")
        self.assert_deleted(out, "lane2")

    def test_a_full_stack_of_two_is_deleted_in_full(self):
        # Per decision merge-deletes-batch-lanes (lane cleanup): lane2's open PR sits at its tip with base lane1, a lane of this batch, so it is done.
        # lane1's only PR-base reference comes from that lane, so nothing outside the batch keeps it. Both lanes go.
        tips = lane_batch(self, "lane1", "lane2")
        self.host.prs = [("lane1", tips["lane1"], "main"), ("lane2", tips["lane2"], "lane1")]
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_deleted(out, "lane1", "lane2")
        self.assertEqual([l for l in out.splitlines() if ": kept:" in l], [], out)

    def test_a_partial_stack_keeps_its_base_and_names_the_stacked_branch(self):
        # Per decision merge-deletes-batch-lanes (lane cleanup): stack-top is an open PR outside the batch, based on lane1, so lane1 stays. Its kept line names stack-top.
        # lane2 is a lane of the batch with no PR, so it must still go: a cut that deletes nothing fails here.
        lane_batch(self, "lane1", "lane2")
        self.host.prs = [("stack-top", self.head("main"), "lane1")]
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertIn("stack-top", kept_line(self, out, "lane1"))
        self.assertNotEqual(self.head("lane1"), "", "lane1 was deleted")
        self.assert_deleted(out, "lane2")

    def test_a_three_deep_full_stack_is_deleted_in_full(self):
        # Per decision merge-deletes-batch-lanes (lane cleanup): each lane's open PR sits at its tip, based on the lane below it or on the batch's base.
        tips = lane_batch(self, "lane1", "lane2", "lane3")
        self.host.prs = [("lane1", tips["lane1"], "main"), ("lane2", tips["lane2"], "lane1"), ("lane3", tips["lane3"], "lane2")]
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_deleted(out, "lane1", "lane2", "lane3")
        self.assertEqual([l for l in out.splitlines() if ": kept:" in l], [], out)

    def test_a_backport_pr_beside_the_lane_own_pr_keeps_the_lane(self):
        # Per decision merge-deletes-batch-lanes (lane cleanup): lane1 has its own PR to main at its tip, and a second open PR at the same tip to release/1.0. The second base
        # is neither the batch's base nor a batch lane, so lane1 stays. Passes on the old code (a head with two PRs is never its own).
        tips = lane_batch(self, "lane1", "lane2")
        self.host.prs = [("lane1", tips["lane1"], "main"), ("lane1", tips["lane1"], "release/1.0")]
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_kept_line(out, "lane1")
        self.assert_deleted(out, "lane2")

    def test_a_stacked_pr_whose_head_is_past_the_lane_tip_keeps_its_base(self):
        # Control, passes on the old code. A PR counts as inside the batch only when its head sits at a lane tip. lane2's head is
        # past its tip here, so that PR is outside, and lane1 stays as the base of an open PR. A cut that counts it as inside
        # deletes a live base. The kept line's wording is not pinned here.
        lane_batch(self, "lane1", "lane2")
        self.host.prs = [("lane2", self.head("main"), "lane1")]
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        kept = [l for l in out.splitlines() if l.startswith("merge: lane origin/lane1: kept:")]
        self.assertEqual(len(kept), 1, out)
        self.assertNotEqual(self.head("lane1"), "", "lane1 was deleted")

    def stack_of_three(self):
        """Lanes lane1 <- lane2 <- lane3 in one batch, each open at its tip, each PR based on the lane below it. -> tips."""
        tips = lane_batch(self, "lane1", "lane2", "lane3")
        self.host.prs = [("lane1", tips["lane1"], "main"), ("lane2", tips["lane2"], "lane1"), ("lane3", tips["lane3"], "lane2")]
        return tips

    def one_lane_line_matches_state(self, out, b):
        """One lane line for origin/b, and it says deleted exactly when no origin head is left for b. -> that line."""
        lines = [l for l in out.splitlines() if l.startswith(f"merge: lane origin/{b}:")]
        self.assertEqual(len(lines), 1, out)
        self.assertEqual(" deleted at " in lines[0], self.head(b) == "", lines[0])
        return lines[0]

    def delete_index(self, calls, b):
        """The position of the leased delete push of lane b among the git calls. Each lane is pushed once."""
        hits = [i for i, c in enumerate(calls) if "push" in c and f":refs/heads/{b}" in c]
        self.assertEqual(len(hits), 1, f"{b}: {len(hits)} delete pushes")
        return hits[0]

    def proof_fails_for(self, tip):
        """-> a patch under which the ancestry proof of one lane tip cannot run (merge-base exits 128). Every other git call is real.
        c110: read_lanes asks merge-base against origin/main before the claim, and a failure there refuses; that read stays real."""
        real = merge.sh
        def broken(args, *a, **k):
            if "merge-base" in args and tip in args and "origin/main" not in args:
                return 128, "fatal: simulated: the ancestry proof cannot run"
            return real(args, *a, **k)
        return unittest.mock.patch.object(merge, "sh", broken)

    def test_a_stack_whose_middle_lane_has_an_unproven_tip_keeps_the_base_below_it(self):
        # Fixpoint: lane2's tip cannot be proven, so lane2 is kept. Its open PR still needs lane1, so lane1 is kept too.
        # lane3 gets one line that matches its state. The proof is made to fail for lane2 only.
        tips = self.stack_of_three()
        with self.proof_fails_for(tips["lane2"]):
            rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertIn(LANE_PROOF_NOT_RUN, kept_line(self, out, "lane2"))
        self.assertNotEqual(self.head("lane2"), "", "lane2 was deleted")
        kept_line(self, out, "lane1")
        self.assertNotEqual(self.head("lane1"), "", "lane1 was deleted")
        self.one_lane_line_matches_state(out, "lane3")

    def test_a_stack_whose_middle_lane_moved_keeps_the_base_below_it_as_a_control(self):
        # Control, passes on the old code. lane2's origin head moves after the merge, so it sits at no lane tip and is not cut.
        # Its open PR still needs lane1, so lane1 stays. lane3 gets one line that matches its state.
        tips = self.stack_of_three()
        def moved():
            sha = self.push_to("lane2")
            self.host.prs = [("lane1", tips["lane1"], "main"), ("lane2", sha, "lane1"), ("lane3", tips["lane3"], "lane2")]
        self.host.on_merged = moved
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        kept_line(self, out, "lane1")
        self.assertNotEqual(self.head("lane1"), "", "lane1 was deleted")
        self.one_lane_line_matches_state(out, "lane3")

    def test_a_keepBranches_middle_lane_keeps_the_base_below_it_like_an_unproven_one(self):
        # Control, passes on the old code. lane2 is in merge.keepBranches, so it is kept, and lane1 is kept as its base, as in the unproven case.
        put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], keepBranches=["lane2"]))))
        self.stack_of_three()
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_kept(out, "lane2", "keep")
        kept_line(self, out, "lane1")
        self.assertNotEqual(self.head("lane1"), "", "lane1 was deleted")
        self.one_lane_line_matches_state(out, "lane3")

    def test_a_stack_is_deleted_dependents_first(self):
        # Delete order: a dependent is deleted before its base: lane3's delete is pushed first, then lane2's, then lane1's.
        self.stack_of_three()
        with self.spy() as calls:
            rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_deleted(out, "lane1", "lane2", "lane3")
        order = [self.delete_index(calls, b) for b in ("lane3", "lane2", "lane1")]
        self.assertEqual(order, sorted(order), out)

    def test_a_stack_whose_middle_lane_delete_goes_stale_keeps_the_base_below_it_and_says_why(self):
        # Stale delete: lane2 moves after the cleanup reads the heads, so its leased delete fails with stale info.
        # lane3, its dependent, is deleted. lane1 is kept, with a line, because lane2 is still on origin and its PR needs lane1.
        self.stack_of_three()
        merged, moved = [], []
        self.host.on_merged = lambda: merged.append(True)
        def rival(args, result):  # the first read of the heads after the merge that lists lane2: the cleanup's read
            if merged and not moved and "ls-remote" in args and "--heads" in args and "refs/heads/lane2" in result[1]:
                moved.append(self.push_to("lane2"))
        with self.spy(rival):
            rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertTrue(moved, "the cleanup never read the heads after the merge")
        self.assertEqual(self.head("lane2"), moved[0])
        self.assertEqual(len([l for l in out.splitlines() if LANE_FAILED.format(b="lane2") in l]), 1, out)
        kept_line(self, out, "lane1")
        self.assertNotEqual(self.head("lane1"), "", "lane1 was deleted")
        lane_deleted_line(self, out, "lane3")
        self.assertEqual(self.head("lane3"), "", "lane3 is still on origin")

    def test_a_deleted_lane_line_names_its_nine_character_tip(self):
        # The line that deletes a lane names its branch and the first 9 characters of its tip.
        tips = lane_batch(self, "lane1", "lane2")
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        line = lane_deleted_line(self, out, "lane1")
        self.assertIn(tips["lane1"][:9], line)
        self.assertEqual(len(tips["lane1"][:9]), 9)

    def test_a_lane_in_keepBranches_is_kept(self):
        put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], keepBranches=["batch-map"]))))
        lane_batch(self, "batch-map", "lane2")
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_deleted(out, "lane2")
        self.assert_kept(out, "batch-map", "keep")

    def unreadable(self, how):
        """The open-PR read fails: nothing is deleted, each lane says why, and the merge still lands."""
        lane_batch(self, "lane1", "lane2")
        self.host.unreadable = how
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_merged()
        self.assertEqual(self.host.open_calls, 1)
        for b in ("lane1", "lane2"):
            self.assert_kept(out, b, "unread")
        self.assertNotIn("Traceback", out)

    def test_an_open_pr_read_that_stops_deletes_nothing_and_the_merge_lands(self):
        self.unreadable("stop")

    def test_an_open_pr_read_that_returns_none_deletes_nothing_and_the_merge_lands(self):
        self.unreadable("none")

    def test_an_open_pr_read_that_raises_deletes_nothing_and_the_merge_lands(self):
        self.unreadable("error")

    def test_a_squash_merged_lane_is_not_proven_and_is_kept(self):
        lane_batch(self, "lane1", "lane2")
        self.host.style = "squash"  # no lane tip is in the squash commit, and no lane patch is alone in it
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_merged()
        for b in ("lane1", "lane2"):
            self.assert_kept(out, b, "unproven")

    def test_a_rebase_merged_lane_is_proven_by_its_patches_and_deleted(self):
        lane_batch(self, "lane1", "lane2")
        self.host.style = "rebase"  # the lane commits sit on main under new ids: the tip is no ancestor, the patches are all there
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_merged()
        self.assert_deleted(out, "lane1", "lane2")

    def test_a_delete_push_that_fails_does_not_fail_the_merge(self):
        lane_batch(self, "agent/lane1", "lane2")
        hook = os.path.join(self.bare, "hooks", "pre-receive")
        put_lf(hook, '#!/bin/sh\nwhile read old new ref; do\n  if [ "$ref" = refs/heads/agent/lane1 ] && [ -z "$(echo "$new" | tr -d 0)" ]; then\n'
                     '    echo "agent/lane1 may not be deleted" >&2; exit 1\n  fi\ndone\n')
        os.chmod(hook, 0o755)
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_merged()
        self.assertIn(LANE_FAILED.format(b="agent/lane1"), out)
        self.assertNotEqual(self.head("agent/lane1"), "")
        self.assert_deleted(out, "lane2")  # the failure stops no other lane
        self.assertFalse(self.lock_ref())

    def test_an_origin_heads_read_that_fails_prints_one_line_and_deletes_nothing(self):
        # Ruling 2: the read of the origin heads fails after the merge has landed. Only the ls-remote with --heads fails.
        lane_batch(self, "lane1", "lane2")
        real, merged = merge.sh, []
        def failing(args, *a, **k):
            if merged and "ls-remote" in args and "--heads" in args:
                return 128, "fatal: unable to access 'https://github.com/o/r.git/': Could not resolve host: github.com"
            return real(args, *a, **k)
        self.host.on_merged = lambda: merged.append(True)
        with unittest.mock.patch.object(merge, "sh", failing):
            rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_merged()
        for b in ("lane1", "lane2"):
            self.assertNotEqual(self.head(b), "", f"{b} was deleted")
        self.assert_one_lane_line(out, LANE_HEADS_UNREAD)

    def lane_tips_breaks(self, effect, fail_from=0):
        """Rulings 2 and 3: the read of the lane tips fails before the merge. effect is the (rc, text) git returns, or an
        exception its read raises. The merge still lands, no lane is deleted, and one line says so.
        c110: the same read runs first for the dropped-lane check, which refuses a failed read. fail_from=1 lets that first
        read pass, so the cleanup's own read is the one that fails."""
        lane_batch(self, "lane1", "lane2")
        real, n = merge.sh, [0]
        def broken(args, *a, **k):
            if "log" in args and any("%x01" in a for a in args):  # read_lanes' one git log: merges and reverts
                n[0] += 1
                if n[0] > fail_from:
                    if isinstance(effect, BaseException):
                        raise effect
                    return effect
            return real(args, *a, **k)
        with unittest.mock.patch.object(merge, "sh", broken):
            rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_merged()
        for b in ("lane1", "lane2"):
            self.assertNotEqual(self.head(b), "", f"{b} was deleted")
        self.assert_one_lane_line(out)

    def test_a_failed_dropped_lane_read_refuses_and_claims_nothing(self):
        # c110: the check that guards the lane's files fails closed.
        lane_batch(self, "lane1", "lane2")
        feat, real = self.head("feat"), merge.sh
        def broken(args, *a, **k):
            if "log" in args and any("%x01" in a for a in args):
                return 128, "fatal: bad revision"
            return real(args, *a, **k)
        with unittest.mock.patch.object(merge, "sh", broken):
            rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertIn("--undo-check-unknown-ok", out)
        self.assertNotIn("merged as", out)
        self.assertEqual(self.claims("feat"), 0)
        self.assertEqual(self.head("feat"), feat)
        self.assertFalse(self.lock_ref())

    def test_a_failed_ancestry_read_in_the_dropped_lane_check_refuses(self):
        # c110: a merge-base failure is a failed read, never "not an ancestor".
        tips = lane_batch(self, "lane1", "lane2")
        real = merge.sh
        def broken(args, *a, **k):
            if "merge-base" in args and tips["lane1"] in args and "origin/main" in args:
                return 128, "fatal: simulated"
            return real(args, *a, **k)
        with unittest.mock.patch.object(merge, "sh", broken):
            rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertIn("git merge-base failed", out)
        self.assertEqual(self.claims("feat"), 0)

    def test_an_override_past_a_failed_dropped_lane_read_still_keeps_a_reverted_lane(self):
        # c110: the cleanup's kept line is the fallback when the owner overrides a failed first read.
        lane_batch(self, "lane1", "lane2")
        self.revert_on_batch(self.merge_of("lane1"))
        real, n = merge.sh, [0]
        def first_fails(args, *a, **k):
            if "log" in args and any("%x01" in a for a in args):
                n[0] += 1
                if n[0] == 1:
                    return 128, "fatal: bad revision"
            return real(args, *a, **k)
        with unittest.mock.patch.object(merge, "sh", first_fails):
            rc, out = self.run_merge("7", "--confirm", "--undo-check-unknown-ok", "owner read the batch")
        self.assertEqual(rc, 0, out)
        self.assertIn("dropped-lane check UNKNOWN", out)
        self.assert_merged()
        self.assertIn("reverted", kept_line(self, out, "lane1"))
        self.assert_deleted(out, "lane2")

    def test_a_failed_git_log_in_lane_tips_prints_one_line_and_deletes_nothing(self):
        self.lane_tips_breaks((128, "fatal: bad revision"), fail_from=1)

    def test_a_lane_tips_read_that_raises_oserror_still_lands_the_merge(self):
        self.lane_tips_breaks(OSError("git could not start"), fail_from=1)

    def test_a_lane_tips_read_that_times_out_still_lands_the_merge(self):
        self.lane_tips_breaks(subprocess.TimeoutExpired(["git", "log"], 5), fail_from=1)

    def test_a_merge_commit_that_cannot_be_read_says_the_proof_could_not_run(self):
        # Ruling 5: the merge lands on origin, but the local repo cannot read the commit id host.merge returns.
        lane_batch(self, "lane1", "lane2")
        real_merge = self.host.merge
        def unreadable(n, method, sha):
            real_merge(n, method, sha)
            return "f" * 40, ""
        self.host.merge = unreadable
        rc, out = self.go()  # the local main cannot move onto that id, so rc is not pinned here
        self.assert_merged()
        self.assertNotIn(WHY["unproven"], out)
        for b in ("lane1", "lane2"):
            self.assertNotEqual(self.head(b), "", f"{b} was deleted")
            kept = [l for l in out.splitlines() if l.startswith(f"merge: lane origin/{b}: kept:")]
            self.assertEqual(len(kept), 1, out)
            self.assertIn(LANE_PROOF_NOT_RUN, kept[0])
        self.assertNotIn("Traceback", out)

    def lane_push_raises(self, b, exc):
        """The delete push of lane b raises. Lane b gets one line of its own, and the later lane still gets its line."""
        lane_batch(self, "lane1", "lane2")
        real = merge.sh
        def broken(args, *a, **k):
            if "push" in args and f":refs/heads/{b}" in args:
                raise exc
            return real(args, *a, **k)
        with unittest.mock.patch.object(merge, "sh", broken):
            rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_merged()
        self.assertNotEqual(self.head(b), "", f"{b} was deleted")
        own = [l for l in out.splitlines() if f"origin/{b}" in l]
        self.assertEqual(len(own), 1, out)
        other = "lane2" if b == "lane1" else "lane1"
        lane_deleted_line(self, out, other)
        self.assertEqual(self.head(other), "", f"{other} is still on origin")
        self.assertNotIn("Traceback", out)

    def test_a_lane_push_that_times_out_gets_one_line_and_the_later_lane_still_goes(self):
        self.lane_push_raises("lane1", subprocess.TimeoutExpired(["git", "push"], 5))

    def test_a_lane_push_that_raises_oserror_gets_one_line_and_the_later_lane_still_goes(self):
        self.lane_push_raises("lane1", OSError("git could not start"))

    def test_a_head_at_a_commit_already_on_main_is_not_a_lane(self):
        # The batch merged main in ("sync main"): that merge commit's second parent is a main commit. A head still at that
        # commit is no lane, and its tip is an ancestor of the merge, so only the base check keeps it.
        o = self.other
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", "main", "origin/main")
        put(os.path.join(o, "moves.txt"), "main moves\n")
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-q", "-m", "main moves"); sh(o, "git", "push", "-q", "origin", "main")
        sh(o, "git", "push", "-q", "origin", "HEAD:refs/heads/stale")
        sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        sh(o, "git", "merge", "-q", "-m", "sync main", "origin/main")
        sh(o, "git", "push", "-q", "origin", "feat")
        lane_batch(self, "lane2")
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_deleted(out, "lane2")
        self.assertNotEqual(self.head("stale"), "")
        self.assertNotIn("origin/stale", out)

    # The local side of a lane: a local branch at a lane tip, and its worktree, go with the lane when the batch took it in.
    def local_branch(self, branch, sha, tree=None):
        """A local branch at `sha`, and a worktree on it at `tree` when given. -> the worktree path, or None."""
        sh(self.co, "git", "fetch", "-q", "origin")
        sh(self.co, "git", "branch", branch, sha)
        if tree is None:
            return None
        sh(self.co, "git", "worktree", "add", "-q", tree, branch)
        return tree

    def has_local(self, branch):
        return subprocess.run(["git", "-C", self.co, "rev-parse", "-q", "--verify", f"refs/heads/{branch}"], capture_output=True).returncode == 0

    def tree_listed(self, path):
        return tree_listed(self.co, path)

    def test_a_batch_takes_its_local_lane_branches_and_clean_trees_with_it(self):
        tips = lane_batch(self, "lane1", "lane2")
        self.host.on_merged = lambda: [sh(self.other, "git", "push", "-q", "origin", "--delete", n) for n in ("lane1", "lane2")]  # GitHub deleted the heads
        tree = self.local_branch("lane-a", tips["lane1"], os.path.join(self.t, "wt-lane-a"))
        self.local_branch("worktree-agent-x", tips["lane2"])
        self.assertTrue(self.tree_listed(tree), "subject: the lane's worktree must exist first")
        self.assertTrue(self.has_local("lane-a") and self.has_local("worktree-agent-x"), "subject: both local lane branches must exist first")
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_merged()
        self.assertFalse(self.tree_listed(tree), f"the lane's clean worktree is still listed; out: {out!r}")
        self.assertFalse(os.path.exists(tree), f"the lane's clean worktree folder is still there; out: {out!r}")
        self.assertFalse(self.has_local("lane-a"), f"local lane-a was not deleted; out: {out!r}")
        self.assertFalse(self.has_local("worktree-agent-x"), f"local worktree-agent-x was not deleted; out: {out!r}")

    def test_a_lane_tree_with_uncommitted_edits_keeps_its_branch_and_says_dirty(self):
        tips = lane_batch(self, "lane1", "lane2")
        tree = self.local_branch("lane-a", tips["lane1"], os.path.join(self.t, "wt-lane-a"))
        put(os.path.join(tree, "scratch.txt"), "an uncommitted edit\n")
        self.assertTrue(self.tree_listed(tree), "subject: the lane's worktree must exist first")
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_merged()
        kept = [l for l in out.splitlines() if l.startswith("merge: lane-a kept here:")]
        self.assertEqual(len(kept), 1, f"one kept line for lane-a, got: {out!r}")
        self.assertIn("dirty", kept[0])
        self.assertTrue(os.path.isdir(tree), f"the dirty tree was removed; out: {out!r}")
        self.assertTrue(self.tree_listed(tree), out)
        self.assertTrue(self.has_local("lane-a"), f"the local branch of a kept tree was deleted; out: {out!r}")
        self.assert_deleted(out, "lane1", "lane2")  # control: the lanes on origin still go

    def test_a_dropped_lane_keeps_its_local_branch_and_clean_tree(self):
        tips = lane_batch(self, "lane1", "lane2")
        feat = self.revert_on_batch(self.merge_of("lane1"))  # lane1's merge is reverted on the batch: a dropped lane
        tree = self.local_branch("lane-a", tips["lane1"], os.path.join(self.t, "wt-lane-a"))
        self.assertTrue(self.tree_listed(tree), "subject: the dropped lane's worktree must exist first")
        rc, out = self.go()
        self.assert_refused_drop(rc, out, feat)
        self.assertTrue(os.path.isdir(tree), f"the dropped lane's clean tree was removed; out: {out!r}")
        self.assertTrue(self.tree_listed(tree), out)
        self.assertTrue(self.has_local("lane-a"), f"the dropped lane's local branch was deleted; out: {out!r}")

    def kept_local_lane(self, branch, tip):
        """A local lane branch at `tip`, with a clean worktree on it. -> the worktree path. Both must exist before the merge."""
        tree = self.local_branch(branch, tip, os.path.join(self.t, "wt-" + branch))
        self.assertTrue(self.tree_listed(tree), "subject: the lane's worktree must exist first")
        self.assertTrue(self.has_local(branch), "subject: the local lane branch must exist first")
        return tree

    def test_a_local_lane_in_keepBranches_keeps_its_branch_and_clean_tree(self):
        put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], keepBranches=["lane1"]))))
        tips = lane_batch(self, "lane1", "lane2")
        tree = self.kept_local_lane("lane1", tips["lane1"])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_merged()
        self.assert_kept(out, "lane1", "keep")  # the remote lane is kept by its name
        self.assertTrue(self.tree_listed(tree), f"the kept lane's clean worktree is no longer listed; out: {out!r}")
        self.assertTrue(self.has_local("lane1"), f"the local branch of a keepBranches lane was deleted; out: {out!r}")
        self.assert_deleted(out, "lane2")  # control: the other lane still goes

    def test_a_local_branch_of_a_lane_kept_for_an_open_pr_keeps_its_clean_tree(self):
        tips = lane_batch(self, "lane1", "lane2")
        self.host.prs = [("stack-top", self.head("main"), "lane1")]  # a partial stack: its base is lane1
        tree = self.kept_local_lane("lane-a", tips["lane1"])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_merged()
        self.assert_kept_line(out, "lane1")  # the remote lane is kept for its open PR
        self.assertTrue(self.tree_listed(tree), f"the kept lane's clean worktree is no longer listed; out: {out!r}")
        self.assertTrue(self.has_local("lane-a"), f"the local branch of an open-PR base was deleted; out: {out!r}")
        self.assert_deleted(out, "lane2")  # control: the other lane still goes

    def test_a_local_lane_branch_is_untouched_when_the_open_pr_read_fails(self):
        tips = lane_batch(self, "lane1", "lane2")
        self.host.unreadable = "error"  # the open-PR read raises
        tree = self.kept_local_lane("lane-a", tips["lane1"])
        self.assertNotEqual(self.head("lane1"), "", "subject: origin/lane1 must exist, so the remote pass has a head to keep")
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_merged()
        self.assertNotEqual(self.head("lane1"), "", f"origin/lane1 was deleted; out: {out!r}")
        self.assertTrue(self.tree_listed(tree), f"the lane's clean worktree is no longer listed; out: {out!r}")
        self.assertTrue(self.has_local("lane-a"), f"a local lane branch was deleted when the open-PR read failed; out: {out!r}")

    def test_a_local_lane_branch_is_untouched_when_the_origin_heads_read_fails(self):
        tips = lane_batch(self, "lane1", "lane2")
        tree = self.kept_local_lane("lane-a", tips["lane1"])
        self.assertNotEqual(self.head("lane1"), "", "subject: origin/lane1 must exist, so the remote pass has a head to read")
        real, merged = merge.sh, []
        def failing(args, *a, **k):
            if merged and "ls-remote" in args and "--heads" in args:
                return 128, "fatal: unable to access 'https://github.com/o/r.git/': Could not resolve host: github.com"
            return real(args, *a, **k)
        self.host.on_merged = lambda: merged.append(True)
        with unittest.mock.patch.object(merge, "sh", failing):
            rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_merged()
        self.assertNotEqual(self.head("lane1"), "", f"origin/lane1 was deleted; out: {out!r}")
        self.assertTrue(self.tree_listed(tree), f"the lane's clean worktree is no longer listed; out: {out!r}")
        self.assertTrue(self.has_local("lane-a"), f"a local lane branch was deleted when the origin heads read failed; out: {out!r}")

    def test_a_local_branch_at_no_lane_tip_is_untouched(self):
        lane_batch(self, "lane1", "lane2")
        base = sh(self.co, "git", "rev-parse", "origin/main")  # the base is no lane tip; it is an ancestor of the merge
        self.local_branch("stray", base)
        self.assertTrue(self.has_local("stray"), "subject: the stray local branch must exist first")
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assert_merged()
        self.assert_deleted(out, "lane1", "lane2")
        self.assertTrue(self.has_local("stray"), f"a local branch at no lane tip was deleted; out: {out!r}")
        self.assertNotIn("stray", out)

    def test_deleteBranch_false_keeps_every_lane_and_reads_no_open_prs(self):
        put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], deleteBranch=False))))
        lane_batch(self, "lane1", "lane2")
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.host.open_calls, 0)
        self.assertNotIn("merge: lane", out)
        for b in ("lane1", "lane2", "feat"):
            self.assertNotEqual(self.head(b), "")

    def test_a_batch_without_lanes_reads_no_open_prs_and_prints_no_lane_line(self):
        rc, out = self.go()  # feat holds no merge commit
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.host.open_calls, 0)
        self.assertNotIn("merge: lane", out)

    def keepBranches_config(self, value):
        put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], keepBranches=value))))
        return self.run_merge("7")

    def test_keepBranches_takes_a_list_of_names(self):
        rc, out = self.keepBranches_config(["batch-map", "map-skill-move"])
        self.assertEqual(rc, 0, out)
        self.assertNotIn("unknown field", out)

    def test_keepBranches_that_is_not_a_list_of_names_stops_with_one_line(self):
        for bad in ("batch-map", [""], [5], [None], None):
            with self.subTest(bad=bad):
                rc, out = self.keepBranches_config(bad)
                lines = [l for l in out.splitlines() if l.strip()]
                self.assertEqual(rc, 1, out)
                self.assertEqual(len(lines), 1, out)
                self.assertIn(".github/stamp.json", lines[0])
                self.assertIn("merge.keepBranches is not valid", lines[0])

    def test_keepBranches_rejects_a_ref_path_an_origin_path_or_a_name_with_whitespace(self):
        # Ruling 4. The old check strips a name before it tests it, so " x" gets through.
        for bad in ("refs/heads/lane1", "origin/lane1", "a b", "x\t", " x", "x "):
            with self.subTest(bad=bad):
                rc, out = self.keepBranches_config([bad])
                lines = [l for l in out.splitlines() if l.strip()]
                self.assertEqual(rc, 1, out)
                self.assertEqual(len(lines), 1, out)
                self.assertIn("merge.keepBranches is not valid", lines[0])

    def test_keepBranches_rejects_a_name_that_cannot_be_a_branch(self):
        # Names that break a git ref rule are refused: glob characters, ':', '~', '^', '\', '..', and the names `git check-ref-format --branch` refuses.
        # Git refuses each of these names, except the backslash, which the rule names itself.
        for bad in ("a*b", "a?b", "a[b", "a:b", "a~b", "a^b", "a\\b", "a..b", "a.lock", "a/.b", "a@{b", "a//b", "a/", "HEAD"):
            with self.subTest(bad=bad):
                rc, out = self.keepBranches_config([bad])
                lines = [l for l in out.splitlines() if l.strip()]
                self.assertEqual(rc, 1, out)
                self.assertEqual(len(lines), 1, out)
                self.assertIn("merge.keepBranches is not valid", lines[0])

    def test_keepBranches_takes_the_names_git_check_ref_format_accepts(self):  # control
        rc, out = self.keepBranches_config(["agent/lane1", "release/1.0", "lane-1", "a_b"])
        self.assertEqual(rc, 0, out)
        self.assertNotIn("is not valid", out)

    def test_keepBranches_takes_names_that_only_start_like_a_ref_path(self):  # control: the rule must not over-reject
        rc, out = self.keepBranches_config(["agent/lane1", "refsync", "originlane"])
        self.assertEqual(rc, 0, out)
        self.assertNotIn("is not valid", out)

    def test_the_preview_says_the_merge_also_deletes_the_lane_branches(self):
        # Ruling 6: the then-line of the preview names the lane branches, when deleteBranch is on.
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 0, out)
        move = [l for l in out.splitlines() if "move local main" in l]
        self.assertEqual(len(move), 1, out)
        self.assertIn("lane", move[0])

    def test_the_preview_without_deleteBranch_names_no_lane_branches(self):  # control
        put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], deleteBranch=False))))
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 0, out)
        move = [l for l in out.splitlines() if "move local main" in l]
        self.assertEqual(len(move), 1, out)
        self.assertNotIn("lane", move[0])

    def test_the_repos_own_config_keeps_the_held_branches(self):
        with open(os.path.join(HERE, "..", ".github", "stamp.json"), encoding="utf-8") as f:
            kept = json.load(f)["merge"].get("keepBranches")
        self.assertIsInstance(kept, list, "merge.keepBranches is missing from .github/stamp.json")
        self.assertLessEqual(HELD, set(kept))

class CutLanesHome(unittest.TestCase):
    """The names the lane cleanup is built on. One home each: cut_lanes beside cut_branch and called from confirm, the proof
    from guard's own branch_cherry_empty, the open-PR read on Host."""
    def tree(self):
        with open(merge.__file__, encoding="utf-8") as f:
            return ast.parse(f.read())

    def test_cut_lanes_is_defined_and_confirm_calls_it(self):
        self.assertTrue(callable(getattr(merge, "cut_lanes", None)), "merge.py must define cut_lanes(root, lanes, commit)")
        self.assertEqual(list(inspect.signature(merge.cut_lanes).parameters)[:3], ["root", "lanes", "commit"])
        confirm = next(n for n in ast.walk(self.tree()) if isinstance(n, ast.FunctionDef) and n.name == "confirm")
        self.assertTrue([n for n in ast.walk(confirm) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "cut_lanes"],
                        "confirm must call cut_lanes where deleteBranch is honoured")

    def test_the_open_pr_read_and_the_config_field_exist(self):
        self.assertTrue(callable(getattr(merge.Host, "open_heads", None)), "merge.Host must define open_heads()")
        self.assertIn("keepBranches", merge.MERGE_FIELDS)

    def test_the_proof_calls_guards_cherry_test_and_holds_no_copy(self):
        tree = self.tree()
        copies = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "branch_cherry_empty"
                  or isinstance(n, ast.Constant) and n.value == "cherry"]
        self.assertEqual(copies, [], "merge.py copies guard.branch_cherry_empty at line %s. Call it." % copies)
        uses = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "branch_cherry_empty"]
        self.assertTrue(uses, "cut_lanes must call guard.branch_cherry_empty")

    def test_the_ls_remote_split_is_an_escape_not_a_raw_tab(self):
        # The ls-remote parse splits on the escape \t. A raw TAB in a string is invisible in review and breaks on a re-save.
        # The scan reads merge.py through tokenize, so a string over several lines or a '#' in a string is read as a string.
        with open(merge.__file__, encoding="utf-8") as f:
            found = raw_tab_strings(f.read())
        self.assertEqual(found, [], "merge.py holds a raw TAB in a string, at line %s. Write it as \\t." % (found[:1],))

    def test_the_tab_scan_reads_strings_and_comments_as_tokenize_does(self):
        # Scanner self-checks, per building-scanner-respects-strings. <TAB> stands for a raw TAB character in each source.
        cases = [
            ('s = "a\\tb"  # a comment with a # and a lone quote: don\'t\n', []),           # an escape in a string, and a comment, are no raw TAB
            ('s = "a<TAB>b"\n', [1]),                                                         # a raw TAB in a string
            ('t = """one\n<TAB>two"""\n', [1]),                                              # a multi-line string: reported once, at its first line
            ('# a <TAB> in a comment\nx = 1\n', []),                                          # a TAB in a comment is not a string
            ('s = "# not a comment <TAB>"\n', [1]),                                           # a '#' inside a string does not end it
            ("# don't\ns = '<TAB>'\n", [2]),                                                   # a lone quote in a comment does not open a string
        ]
        for source, want in cases:
            with self.subTest(source=source):
                got = [line for line, _ in raw_tab_strings(source.replace("<TAB>", "\t"))]
                self.assertEqual(got, want)

class AfterPush(Env):
    """A crash between the claim push and the merge must stop cleanly: claim reverted, lock released."""
    def merge_tree(self):
        out = sh(self.co, "git", "worktree", "list", "--porcelain")
        return [l.split(" ", 1)[1] for l in out.splitlines() if l.startswith("worktree ") and "merge-wt-" in l][0]

    def assert_clean_stop(self, rc, out):
        self.assertEqual(rc, 1, out)
        self.assertNotIn("Traceback", out)
        self.assertEqual(self.show("feat", "docs/decisions/second.md"), record("pending", "second").strip())
        self.assertIn("reverted", out)
        self.assertFalse(self.lock_ref())
        self.assertEqual(self.worktrees(), 1)

    def base_loses(self, text):
        """The base moves during the wait: its .github/stamp.json is removed when text is None, else rewritten to text."""
        o = self.other
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", "main", "origin/main")
        if text is None:
            sh(o, "git", "rm", "-q", ".github/stamp.json")
        else:
            put(os.path.join(o, ".github/stamp.json"), text)
        sh(o, "git", "commit", "-qam", "base loses its config")
        sh(o, "git", "push", "-q", "origin", "main")

    def assert_base_lost(self, rc, out):
        self.assert_clean_stop(rc, out)
        lines = [l for l in out.splitlines() if "base lost its config" in l]
        self.assertEqual(len(lines), 1, out)  # one line, from merge
        self.assertTrue(lines[0].startswith("merge: "), lines[0])

    def test_the_tree_config_or_kinds_gone_at_the_base_check_stops_clean(self):
        """The tree, the config or the kinds gone at the base check: one outcome, a stop with no claim left
        behind. Each row is a fresh fixture, so subTest runs its own setUp."""
        def tree_gone():
            shutil.rmtree(os.path.dirname(self.merge_tree()))
        cases = (
            ("tree", tree_gone, self.assert_clean_stop),
            ("config", lambda: self.base_loses(None), self.assert_base_lost),
            ("kinds", lambda: self.base_loses(json.dumps({k: v for k, v in CONFIG.items() if k != "kinds"})), self.assert_base_lost),
        )
        for name, hook, check in cases:
            with self.subTest(gone=name):
                self.setUp()
                self.host.on_wait = hook
                check(*self.run_merge("7", "--confirm"))

    def test_any_error_after_the_push_reverts_the_claim(self):
        def boom():
            raise RuntimeError("boom")
        self.host.on_wait = boom
        self.assert_clean_stop(*self.run_merge("7", "--confirm"))

    def test_an_error_in_the_merge_call_reverts_the_claim(self):
        def boom(*a):
            raise RuntimeError("boom")
        self.host.merge = boom
        self.assert_clean_stop(*self.run_merge("7", "--confirm"))

    def test_the_tree_is_locked_while_the_run_waits(self):
        seen = []
        self.host.on_wait = lambda: seen.append(sh(self.co, "git", "worktree", "list", "--porcelain"))
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertIn("locked", seen[0])
        self.assertEqual(self.worktrees(), 1)

class RerunAfterRevert(Env):
    def test_second_run_claims_the_same_number_again_and_merges(self):
        # Banchi #595, DEBT81: a red check reverts the claim; the rerun, after green, must claim again.
        self.host.seq = [(True, ""), (False, "check checks is red")]
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)
        self.assertIn("reverted", out)
        self.assertEqual(self.show("feat", "docs/decisions/second.md"), record("pending", "second").strip())
        self.host.checks = (True, "")
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("resumed", out)
        self.assertIn("Record-claim: D-002 pushed", out)  # the same number, no branch reset
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))
        # the claim, its revert, and the claim again: three commits on top of the feature commit
        subjects = sh(self.co, "git", "log", "--first-parent", "--format=%s", "origin/main^2").splitlines()  # feat is deleted after the merge.splitlines()
        self.assertEqual(subjects[:4], ["Claim record numbers", 'Revert "Claim record numbers"', "Claim record numbers", "feat: second"], subjects)
        self.assertEqual(sh(self.co, "git", "log", "--first-parent", "--format=%s", "origin/main").splitlines()[0], "merge #7")
        self.assertFalse(self.lock_ref())
        self.assertEqual(self.worktrees(), 1)

class Stopped(Env):
    def test_stopped_run_resumes_after_its_dead_holder_lock_is_taken_over(self):  # c189: its live lock used to refuse with "Run: merge --unlock"
        child = subprocess.run([sys.executable, __file__, "--child", self.co], capture_output=True, text=True)
        self.assertEqual(child.returncode, 9, child.stderr)
        self.assertEqual(self.claims("feat"), 1)
        self.assertTrue(self.lock_ref())  # the run died holding the lock
        rc, out = self.run_merge("7", "--confirm")  # the lock is unexpired, its pid is dead, this host
        self.assertEqual(rc, 0, out)
        self.assertIn("took over", out)
        self.assertIn("resumed", out)
        self.assertEqual(self.claims(), 1)  # no second claim
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))
        self.assertFalse(self.lock_ref())

    def test_an_unreadable_base_is_never_a_resume(self):
        # stamp --check prints UNKNOWN and exits 0 off Actions. The tool must read that as failure.
        info = self.host.pr(7)
        tmp, wt = merge.open_worktree(self.co, info, "main")
        try:
            cfg = ".github/stamp.json"
            trailer = merge.do_claim(wt, cfg, "origin/main")
            merge.commit_claim(wt, trailer)
            self.assertEqual(merge.own_claim(wt, cfg, "origin/main"), "D-002")
            self.assertIsNone(merge.own_claim(wt, cfg, "origin/no-such-ref"))
        finally:
            merge.drop_worktree(self.co, tmp, wt)

class BaseAware(Env):
    """The pull request's own base drives every step."""
    BASE = "integ"

    def setUp(self):
        super().setUp()
        sh(self.other, "git", "fetch", "-q", "origin")
        sh(self.other, "git", "push", "-q", "origin", f"origin/main:refs/heads/{self.BASE}")
        self.host.base = self.BASE
        self.modes, self.fetches, self.undo_bases = [], [], []
        real_stamp, real_git, real_undo = merge.node_stamp, merge.git, merge.undo_check
        def stamp(wt, cfgrel, mode, base):
            self.modes.append((mode, base))
            return real_stamp(wt, cfgrel, mode, base)
        def git(cwd, *a, **k):
            if "fetch" in a:
                self.fetches.append((len(self.host.waits), a))
            return real_git(cwd, *a, **k)
        def undo(wt, base_ref, unknown_ok="", pr_body=""):
            self.undo_bases.append(base_ref)
            return real_undo(wt, base_ref, unknown_ok, pr_body)
        for name, fn in (("node_stamp", stamp), ("git", git), ("undo_check", undo)):
            p = unittest.mock.patch.object(merge, name, fn); p.start(); self.addCleanup(p.stop)

    def put_locks(self, *branches):
        sha = sh(self.co, "git", "commit-tree", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", "-m", "lock")
        for b in branches:
            sh(self.co, "git", "push", "-q", "origin", f"{sha}:refs/heads/merge-lock/{b}")

    def test_1_confirm_into_another_base_claims_and_pushes_nothing_but_merges(self):
        feat_before = self.head()
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertTrue(getattr(self.host, "merged", False), out)
        self.assertNotIn("claim", [m for m, _ in self.modes])  # stamp --claim never runs
        # nothing pushed to the head branch. deleteBranch removes `feat` after the merge, so read the merge commit instead.
        sh(self.co, "git", "fetch", "-q", "origin")
        self.assertEqual(sh(self.co, "git", "rev-parse", f"origin/{self.BASE}^2"), feat_before)
        self.assertEqual(sh(self.co, "git", "log", f"{feat_before}..origin/{self.BASE}^2", "--format=%B"), "")
        self.assertNotIn("Record-claim", sh(self.co, "git", "log", f"origin/{self.BASE}^2", "--format=%B"))
        self.assertIn("id: pending", self.show(self.BASE, "docs/decisions/second.md"))  # ids stay pending
        self.assertNotIn("second.md", sh(self.co, "git", "ls-tree", "-r", "--name-only", "origin/main"))  # main untouched

    def test_2_preview_into_another_base_prints_no_claim_and_says_ids_stay_pending(self):
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Record-claim", out)
        self.assertTrue(any("pending" in l.lower() and "default branch" in l.lower() for l in out.splitlines()), out)

    def test_3_the_lock_is_taken_and_released_on_the_base(self):
        calls = []
        acquire, release = self.lock.acquire, self.lock.release
        self.lock.acquire = lambda b, ttl: (calls.append(("acquire", b)), acquire(b, ttl))[1]
        self.lock.release = lambda b, tok: (calls.append(("release", b)), release(b, tok))[1]
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertEqual(calls, [("acquire", self.BASE), ("release", self.BASE)])

    def test_3_unlock_with_a_branch_unlocks_that_branch_only(self):
        self.put_locks("main", self.BASE)
        try:
            rc, out = self.run_merge("--unlock", self.BASE)
        except SystemExit as e:
            rc, out = e.code, "SystemExit"
        self.assertEqual(rc, 0, out)
        refs = self.refs()
        self.assertNotIn(f"refs/heads/merge-lock/{self.BASE}", refs)
        self.assertIn("refs/heads/merge-lock/main", refs)

    def test_3_bare_unlock_still_unlocks_the_default_branch(self):  # guard
        self.put_locks("main", self.BASE)
        rc, out = self.run_merge("--unlock")
        self.assertEqual(rc, 0, out)
        refs = self.refs()
        self.assertNotIn("refs/heads/merge-lock/main", refs)
        self.assertIn(f"refs/heads/merge-lock/{self.BASE}", refs)

    def test_4_a_base_that_changes_between_the_reads_stops_before_any_claim_or_push(self):
        sh(self.other, "git", "push", "-q", "origin", "origin/main:refs/heads/other-base")
        self.host.base_seq = [self.BASE, "other-base"]
        feat_before = self.head()
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.head(), feat_before)
        self.assertNotIn("claim", [m for m, _ in self.modes])
        self.assertFalse(getattr(self.host, "merged", False))
        self.assertNotIn("refs/heads/merge-lock/", self.refs())

    def test_6_undo_check_the_base_fetch_after_the_wait_and_stamp_check_use_the_base(self):
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        want = f"origin/{self.BASE}"
        self.assertTrue(self.undo_bases and all(b == want for b in self.undo_bases), self.undo_bases)
        checks = [b for m, b in self.modes if m == "check"]
        self.assertTrue(checks and all(b == want for b in checks), self.modes)
        after_wait = [a for n, a in self.fetches if n >= 1]  # fetches made once the wait has run
        self.assertTrue(any(f"+refs/heads/{self.BASE}:refs/remotes/origin/{self.BASE}" in a for a in after_wait), after_wait)
        self.assertFalse(any("+refs/heads/main:refs/remotes/origin/main" in a for a in after_wait), after_wait)

    def test_7_the_local_fast_forward_moves_the_base_not_the_default_branch(self):
        main_before = sh(self.co, "git", "rev-parse", "main")
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertEqual(sh(self.co, "git", "rev-parse", self.BASE), sh(self.co, "git", "rev-parse", f"origin/{self.BASE}"))
        self.assertEqual(sh(self.co, "git", "rev-parse", "main"), main_before)

    def test_8_control_a_pr_into_the_default_branch_still_claims(self):
        self.host.base = "main"
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertIn("claim", [m for m, _ in self.modes])
        self.assertEqual(self.claims("main"), 1)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))

    def test_A_preview_reads_the_lock_of_the_base(self):  # mutant: lock.read(cfg["defaultBranch"]) in preview()
        self.put_locks(self.BASE)  # live on integ, none on main
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 0, out)
        self.assertIn(f"lock:   the merge lock on {self.BASE} is held", out)  # say() prints each line on its own line

    def test_B_a_head_that_holds_an_old_claim_stops_before_the_wait_on_another_base(self):
        o = self.other
        sh(o, "git", "fetch", "-q", "origin"); sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        sh(o, "git", "commit", "-q", "--allow-empty", "-m", "Claim record numbers", "-m", "Record-claim: D-002")
        sh(o, "git", "push", "-q", "origin", "feat")
        claim = sh(o, "git", "rev-parse", "HEAD")
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)
        self.assertIn(claim[:7], out)  # names the claim commit by its short SHA
        self.assertEqual(self.host.waits, [])  # stopped before the wait
        self.assertFalse(getattr(self.host, "merged", False))
        self.assertEqual(self.head(), claim)  # nothing pushed
        self.assertNotIn("refs/heads/merge-lock/", self.refs())

    def test_C_a_base_that_changes_during_the_wait_ends_the_wait_and_merges_nothing(self):
        fake = self.host
        class WaitHost(merge.Host):  # the real wait loop; every other read comes from the fake
            def __init__(h):
                super().__init__(["checks"], minute=60, now=lambda: 0, pause=lambda s: None)
                h.in_wait, h.passes = False, 0
            def pr(h, n, *a, **k):
                info = fake.pr(n)
                if h.in_wait:
                    h.passes += 1
                    if h.passes > 1:
                        info["base"] = "other-base"  # the second pass of the wait sees a new base
                h.base = info["base"]  # as Host.pr does: the baseline is "integ" from the reads before the wait
                return info
            def required_names(h): return ["checks"]
            def checks(h, n, *a, **k): return {"checks": [("pass", "")]}
            def runs(h, sha): return []
            def base_state(h, base, flows): return "green", ""
            def head_state(h, n, *a, **k): return "green"
            def wait_checks(h, *a, **k):
                h.in_wait = True
                try:
                    return super().wait_checks(*a, **k)
                finally:
                    h.in_wait = False
            def merge(h, *a): return fake.merge(*a)
        rc, out = self.run_merge("7", "--confirm", host=WaitHost())
        self.assertEqual(rc, 1, out)
        self.assertFalse(getattr(fake, "merged", False), out)
        self.assertNotIn("refs/heads/merge-lock/", self.refs())

class Unlock(Env):
    def test_unlock_removes_a_live_lock_and_reads_nothing_first(self):
        sha = sh(self.co, "git", "commit-tree", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", "-m", "unreadable, not ours")
        sh(self.co, "git", "push", "-q", "origin", f"{sha}:refs/heads/merge-lock/main")
        rc, out = self.run_merge("--unlock")
        self.assertEqual(rc, 0, out)
        self.assertFalse(self.lock_ref())

    def test_unlock_with_no_lock_is_fine(self):
        self.assertEqual(self.run_merge("--unlock")[0], 0)

    def test_unlock_of_a_missing_ref_says_so_and_never_says_the_lock_was_removed(self):  # the ref is absent, nothing was removed
        rc, out = self.run_merge("--unlock", "main")
        self.assertEqual(rc, 0, out)
        self.assertNotRegex(out, r"lock on main removed")
        self.assertRegex(out, r"(?i)no (merge )?lock|not found|does not exist|nothing to remove")

FAKE_GH = r'''#!/usr/bin/env python3
import hashlib, json, os, sys
d = os.environ["FAKE_GH_DIR"]; a = sys.argv[1:]; assert a[0] == "api"; a = a[1:]
method = "GET"; fields = {}; jq = None; path = None; i = 0; include = False
while i < len(a):
    if a[i] == "-X": method = a[i + 1]; i += 2
    elif a[i] == "-f": k, v = a[i + 1].split("=", 1); fields[k] = v; i += 2
    elif a[i] == "--jq": jq = a[i + 1]; i += 2
    elif a[i] in ("-i", "--include"): include = True; i += 1  # gh prints the status line and the headers first, on a success and on a failure
    else: path = a[i]; i += 1
p = path.split("/git/", 1)[1]; ref = os.path.join(d, "ref")
def head(code, text):
    if include: sys.stdout.buffer.write(("HTTP/2.0 %d %s\r\nContent-Type: application/json\r\nX-Ratelimit-Remaining: 4999\r\n\r\n" % (code, text)).encode())  # bytes: no newline translation
def out(v): head(200, "OK"); print(v); sys.exit(0)
def fail(m): head(int(m.split()[1].rstrip(":")) if m.startswith("HTTP ") else 400, "Error"); print(m); sys.exit(1)
if p == "ref/heads/main": out("head1")
if p == "commits/head1": out("tree1")
if p == "commits" and method == "POST":
    sha = hashlib.sha1(fields["message"].encode()).hexdigest(); open(os.path.join(d, sha), "w").write(fields["message"]); out(sha)
if p.startswith("commits/"):
    out(open(os.path.join(d, p[8:])).read() if jq == ".message" else "tree1")
if p == "refs" and method == "POST":
    if os.path.exists(ref): fail("HTTP 422: Reference already exists")
    open(ref, "w").write(fields["sha"]); out("{}")
if p == "ref/heads/merge-lock/main" and method == "GET":
    if not os.path.exists(ref): fail("HTTP 404: Not Found")
    out(open(ref).read())
if p == "refs/heads/merge-lock/main" and method == "DELETE":
    if not os.path.exists(ref): fail("HTTP 404: Not Found")
    os.remove(ref); out("")
fail("unhandled " + p)
'''

class GhLockTest(unittest.TestCase):
    def setUp(self):
        t = tempfile.mkdtemp(prefix="test-ghlock-")
        self.addCleanup(shutil.rmtree, t, True)
        bindir = os.path.join(t, "bin"); os.makedirs(bindir)
        gh = os.path.join(bindir, "gh"); put_shim(gh, FAKE_GH)
        self.state = os.path.join(t, "state"); os.makedirs(self.state)
        old = {k: os.environ.get(k) for k in ("PATH", "FAKE_GH_DIR")}
        os.environ["PATH"] = bindir + os.pathsep + old["PATH"]; os.environ["FAKE_GH_DIR"] = self.state
        self.addCleanup(lambda: [os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None) for k, v in old.items()])
        self.now = 1000.0
        self.lock = merge.GhLock(now=lambda: self.now)

    @unittest.skipIf(os.name == "nt",
        "cmd.exe cannot carry an embedded newline through a .cmd dispatch: lock_message()'s "
        "commit message always has one, so any .cmd-shimmed fake `gh` loses it before this "
        "script ever sees it (confirmed directly: list2cmdline embeds the raw \\n, and cmd /c "
        "reads it as a line break, truncating the argument first). Real gh.exe is a native PE "
        "with no cmd.exe hop and keeps argv newlines intact, so production is unaffected. "
        "Linux CI still proves this round trip.")
    def test_acquire_hold_expire_release_unlock(self):
        tok = self.lock.acquire("main", 600)
        with self.assertRaises(merge.Held):
            self.lock.acquire("main", 600)
        self.now += 601
        tok2 = self.lock.acquire("main", 600)  # broke the expired lock
        self.assertNotEqual(tok, tok2)
        self.lock.release("main", tok)  # not the holder: leaves it
        self.assertEqual(self.lock.read("main")[0], tok2)
        self.lock.release("main", tok2)
        self.assertIsNone(self.lock.read("main"))
        self.lock.acquire("main", 600)
        self.lock.unlock("main")
        self.assertIsNone(self.lock.read("main"))
        self.lock.unlock("main")  # none left: fine

    @unittest.skipIf(os.name == "nt", "the fake gh loses the lock message's newline under cmd.exe (see the test above)")
    def test_a_live_lock_whose_holder_is_dead_is_taken_over_and_a_live_holder_is_not(self):  # c189 part 3
        self.lock.holder = {"pr": 7, "branch": "b"}
        first = self.lock.acquire("main", 600)
        with unittest.mock.patch.object(merge, "pid_alive", return_value=True), self.assertRaises(merge.Held):
            self.lock.acquire("main", 600)
        out = io.StringIO()
        with unittest.mock.patch.object(merge, "pid_alive", return_value=False), contextlib.redirect_stdout(out):
            second = self.lock.acquire("main", 600)
        self.assertNotEqual(first, second)
        self.assertEqual(len([l for l in out.getvalue().splitlines() if "took over" in l]), 1, out.getvalue())


# The fake GitHub REST API behind `gh api`. One home for the routes the merge tool reads and writes (c53): the shim FAKE_GH_PR
# below runs it as a program, and the in-process fakes (CapsHost, LaneHost) run it through rest_lib(). It models what `gh` does, not
# what a builder hopes it does:
#   - `-f`/`-F` fields with no `-X` make a POST (gh's own rule), so a GET that sends fields must say `-X GET`.
#   - a list read returns ONE page (`per_page`, at most the shim's page_cap, 100 on GitHub) unless `--paginate` is given.
#   - `--paginate` joins JSON-array pages into one array, and prints object pages back to back (`{...}{...}`, not valid JSON as a
#     whole). `--slurp` (needs `--paginate`, refuses `--jq`) prints the pages as one array of pages.
#   - `--jq` knows only: `.`  `.a.b`  `.a[]`  `.[]`  `.a[].b`  (applied to each page).
#   - an argument holding `&` is refused: the Windows `.cmd` shim of this suite lets cmd.exe split the command there. Send query values with `-f`.
#   - GraphQL (`gh pr ...`, `gh repo view`, `gh api graphql`, any other gh command) answers the HTTP 403 a Claude Code cloud session gives.
GH_REST_LIB = r'''
import json, re

GRAPHQL_403 = "HTTP 403: GitHub GraphQL is not available from Claude Code sessions; use the REST API (https://api.github.com/graphql)"
TEST_MERGE_SHA = "e" * 40  # REST sets merge_commit_sha on an OPEN pull request too: the sha of GitHub's test merge

class Refused(Exception):
    """An answer the fake gives as a failure: .text is what gh prints, .code its exit status."""
    def __init__(self, text, code=1):
        super().__init__(text)
        self.text, self.code = text, code

def api_error(code, message):
    """What `gh api` prints when GitHub answers an error: the JSON body with no newline after it, then gh's own line."""
    body = json.dumps({"message": message, "documentation_url": "https://docs.github.com/rest", "status": str(code)}, separators=(",", ":"))
    return "%sgh: %s (HTTP %d)" % (body, message, code)

def parse(argv):
    """The args after `gh api` -> (method, path, params, flags, jq). Query values in the path and -f/-F fields land in params."""
    method, path, params, flags, jq, typed = None, None, {}, set(), None, False
    argv = [part for x in argv for part in (x.split("=", 1) if x.startswith("--") and "=" in x else [x])]  # --method=PUT is --method PUT
    i = 0
    while i < len(argv):
        x = argv[i]
        if "&" in x:
            raise Refused("fake gh api: an argument holds '&' (%r). The Windows .cmd shim of this suite lets cmd.exe split the command there. Send query values with -f fields and -X GET." % x)
        if x in ("-X", "--method"):
            method = argv[i + 1]; i += 2
        elif x in ("-f", "-F", "--raw-field", "--field"):
            k, _, v = argv[i + 1].partition("="); params[k] = v; typed = True; i += 2
        elif x in ("-q", "--jq"):
            jq = argv[i + 1]; i += 2
        elif x in ("-H", "--header"):
            i += 2
        elif x in ("-i", "--include"):
            flags.add("include"); i += 1
        elif x in ("--paginate", "--slurp"):
            flags.add(x[2:]); i += 1
        elif x.startswith("-"):
            raise Refused("fake gh api: the flag %s is not one this fake knows" % x)
        elif path is None:
            path = x; i += 1
        else:
            raise Refused("fake gh api: a second path %r" % x)
    if path is None:
        raise Refused("fake gh api: no path")
    path, _, query = path.lstrip("/").partition("?")
    for pair in filter(None, query.split("&")):
        k, _, v = pair.partition("="); params.setdefault(k, v)
    if "slurp" in flags and "paginate" not in flags:
        raise Refused("the `--slurp` option requires `--paginate`")
    if "slurp" in flags and jq:
        raise Refused("the `--slurp` option is not supported with `--jq` or `--template`")
    return method or ("POST" if typed else "GET"), path, params, flags, jq

def jq_lines(expr, value):
    """The few jq programs the fake knows. -> the lines gh prints: a string raw, anything else as compact JSON."""
    if not re.fullmatch(r"\.(?:[A-Za-z_]\w*|\[\])?(?:\.[A-Za-z_]\w*|\[\])*", expr):
        raise Refused("fake gh api: --jq %r is not one of: .  .a.b  .a[]  .[]  .a[].b" % expr)
    vals = [value]
    for name, each in re.findall(r"\.([A-Za-z_]\w*)|(\[\])", expr):
        vals = [v.get(name) if isinstance(v, dict) else None for v in vals] if name else [x for v in vals for x in (v if isinstance(v, list) else [])]
    return [v if isinstance(v, str) else json.dumps(v, separators=(",", ":")) for v in vals]

def listing(items, key, params, flags, jq, cap, top=None):
    """The text gh prints for a list read. `items` is the whole list; `key` is None for a JSON array reply, else the object field that
    holds the page (check_runs, statuses), with `top` the object's other fields. Without --paginate only the page asked for comes back."""
    size = max(1, min(int(params.get("per_page", 30)), cap))
    pages = [items[i:i + size] for i in range(0, len(items), size)] or [[]]
    if "paginate" in flags:
        chosen = pages
    else:
        n = int(params.get("page", 1))
        chosen = [pages[n - 1] if 1 <= n <= len(pages) else []]
    bodies = [c if key is None else dict(top or {}, **{key: c}) for c in chosen]
    if jq:
        return "\n".join(line for b in bodies for line in jq_lines(jq, b))
    if "slurp" in flags:
        return json.dumps(bodies)
    if key is None:
        return json.dumps([x for c in chosen for x in c])
    return "".join(json.dumps(b) for b in bodies)

def one(obj, jq):
    """The text gh prints for a single object."""
    return "\n".join(jq_lines(jq, obj)) if jq else json.dumps(obj)

RUN_OF = {"pass": ("completed", "success"), "fail": ("completed", "failure"), "pending": ("in_progress", None),
          "skipping": ("completed", "skipped"), "cancel": ("completed", "cancelled")}
STATUS_OF = {"pass": "success", "fail": "failure", "pending": "pending", "error": "error"}

def check_run(row, i, started=None, completed=None):
    """One check run from a bucket row (name, bucket, link). An unknown bucket is taken as the raw conclusion."""
    status, conclusion = RUN_OF.get(row[1], ("completed", row[1]))
    return {"id": 1000 + i, "name": row[0], "status": status, "conclusion": conclusion, "details_url": row[2] or None,
            "started_at": started, "completed_at": completed if status == "completed" else None}

def status_entry(row, i):
    return {"id": 2000 + i, "context": row[0], "state": STATUS_OF.get(row[1], row[1]), "target_url": row[2] or None, "description": ""}

def combined_state(statuses):
    """The combined status GitHub reports: "pending" when there are no statuses at all."""
    states = {s["state"] for s in statuses}
    return "failure" if states & {"failure", "error"} else "pending" if (not states or "pending" in states) else "success"

def pull(number, head, head_ref, base_ref, state="open", merged=False, draft=False, mergeable=True, mergeable_state="clean", body="", merge_commit_sha=TEST_MERGE_SHA):
    """A pull request as `GET pulls/<n>` returns it. An empty body is null, as on GitHub."""
    return {"number": number, "state": state, "merged": merged, "draft": draft, "body": body or None, "mergeable": mergeable,
            "mergeable_state": mergeable_state, "merge_commit_sha": merge_commit_sha, "html_url": "https://github.com/o/r/pull/%d" % number,
            "head": {"ref": head_ref, "sha": head, "label": "o:" + head_ref}, "base": {"ref": base_ref, "sha": "b" * 40, "label": "o:" + base_ref}}

def list_item(number, head, head_ref, base_ref):
    """An open pull request as `GET pulls` lists it: no mergeable, merged or mergeable_state."""
    full = pull(number, head, head_ref, base_ref)
    return {k: v for k, v in full.items() if k not in ("merged", "mergeable", "mergeable_state")}
'''

FAKE_GH_PR = "#!/usr/bin/env python3\nimport os, sys\n" + GH_REST_LIB + r'''
d = os.environ["FAKE_GH_DIR"]; a = sys.argv[1:]
sp = os.path.join(d, "state.json"); S = json.load(open(sp))
def save(): json.dump(S, open(sp, "w"))
def note(name, line): open(os.path.join(d, name), "a").write(line + "\n")
def git(*c):  # subprocess is imported here, not at the top: most calls never start git, and the import is a measurable part of a start (a Windows .cmd shim pays it per call)
    import subprocess
    return subprocess.run(["git", *c], capture_output=True, text=True, cwd=S["other"]).stdout.strip()  # the "other" clone shares origin with the test's checkout, and gh runs wherever the caller does
def ref(name):
    """The object id of a ref on origin, "" when there is none. Read from the files of the bare repo (a loose ref, else packed-refs), so a read starts no git process:
    the same answer as `git ls-remote origin <name>`, at a cost that matters when a Windows .cmd shim answers hundreds of calls."""
    bare = S["bare"]
    try:
        return open(os.path.join(bare, *name.split("/"))).read().strip()
    except OSError:
        pass
    try:
        for line in open(os.path.join(bare, "packed-refs")):
            if line.rstrip("\n").endswith(" " + name):
                return line.split()[0]
    except OSError:
        pass
    return ""
def feat_head(): return ref("refs/heads/feat")
def hold(kind):  # the first such call starts a helper that keeps this process's stdout open, as a detached git or gh helper can
    h = S.get("hold")
    if h and h["on"] == kind and not os.path.exists(os.path.join(d, "held")):
        open(os.path.join(d, "held"), "w").close()
        import subprocess
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(%d)" % h["seconds"]])
def finish(text, code, include=False):
    if include and not (code and not re.search(r"\(HTTP \d{3}\)\s*$", text)):  # a transport error has no HTTP reply, so no header block
        got = int(re.search(r"\(HTTP (\d{3})\)\s*$", text).group(1)) if code else 200
        sys.stdout.buffer.write(("HTTP/2.0 %d %s\r\nContent-Type: application/json\r\nX-Ratelimit-Remaining: 4999\r\n\r\n" % (got, "Error" if code else "OK")).encode())
    print(text)
    sys.exit(code)
def graphql():
    note("graphql.log", " ".join(a))
    print(GRAPHQL_403); sys.exit(1)

if a[:1] != ["api"]:
    note("calls.log", " ".join(a))
    hold(" ".join(a[:2]))
    if a[:2] == ["run", "list"]:
        rf = S.get("runs_fail_first")  # [text, ...]: the first len() calls fail, one text each, then it answers
        if rf:
            S["runs_fail_first"] = rf[1:]; S["runs_failed"] = S.get("runs_failed", 0) + 1; save()
            print(rf[0]); sys.exit(1)
        if S.get("runs_fail"):  # the text of every failing `gh run list`
            print(S["runs_fail"]); sys.exit(1)
        seq = S.get("runs_seq") or [[]]; cur = seq.pop(0) if len(seq) > 1 else seq[0]; save()
        print(json.dumps([{"name": n, "status": st, "conclusion": c} for n, st, c in cur]))
        sys.exit(0)
    if a[:2] == ["run", "watch"]:
        sys.exit(0)
    graphql()  # gh pr ..., gh repo view, any other command: GraphQL

include = False
try:
    method, path, params, flags, jq = parse(a[1:])
    include = "include" in flags
    if path.split("/")[0] == "graphql":
        graphql()
    m = re.match(r"^repos/(\{owner\}/\{repo\}|[^/{}]+/[^/{}]+)(?:/(.*))?$", path)
    if not m:
        raise Refused(api_error(404, "Not Found"))
    repo, rel = m.group(1), m.group(2) or ""
    cap = S.get("page_cap", 100)
    num = S.get("pr_number", 7)
    rows = S.get("open_prs", [])
    numbered = {(r[3] if len(r) > 3 else 101 + i): r for i, r in enumerate(rows)}
    canon = rel or "(repo)"
    line = "%s %s%s%s" % (method, canon, "".join(" %s=%s" % kv for kv in sorted(params.items())), "".join(" --" + f for f in ("paginate", "slurp") if f in flags))
    m_pr, m_put = re.fullmatch(r"pulls/(\d+)", rel), re.fullmatch(r"pulls/(\d+)/merge", rel)
    m_run, m_sta = re.fullmatch(r"commits/([^/]+)/check-runs", rel), re.fullmatch(r"commits/([^/]+)/status", rel)
    m_req = re.fullmatch(r"branches/(.+)/protection/required_status_checks", rel)
    m_jobs = re.fullmatch(r"actions/runs/(\d+)/jobs", rel)  # main's runs (the red-main check): none unless a case sets base_runs / base_jobs
    after = bool(S.get("put_done")) and bool(m_pr) and method == "GET"
    note("calls.log", line + (" after-merge" if after else ""))
    note("repos.log", repo)
    kind = "merge" if m_put else "check-runs" if m_run else "status" if m_sta else "pr" if m_pr else "list" if rel == "pulls" else "repo" if not rel else "required" if m_req else "base-runs" if rel == "actions/runs" else "base-jobs" if m_jobs else "other"
    hold(kind)
    rf = (S.get("route_fail") or {}).get(kind)  # {kind: {"n", "msg"}}: the next n calls of that route fail with msg, then it answers
    if rf and rf["n"] > 0:
        rf["n"] -= 1; S["route_failed"] = dict(S.get("route_failed", {}), **{kind: S.get("route_failed", {}).get(kind, 0) + 1}); save()
        raise Refused(rf["msg"])

    if method == "GET" and not rel:
        finish(one({"default_branch": S.get("default_branch", "main"), "full_name": "o/r"}, jq), 0, include)

    elif method == "GET" and rel == "pulls":
        if S.get("open_heads_fail"):
            raise Refused(S["open_heads_fail"])
        if params.get("state", "open") != "open" or set(params) - {"state", "per_page", "page"}:
            raise Refused(api_error(422, "fake gh: the open pull requests are read with state=open and per_page only, then matched on head.ref"))
        items = [list_item(n, r[1], r[0], r[2]) for n, r in numbered.items()]
        finish(listing(items, None, params, flags, jq, cap), 0, include)

    elif method == "GET" and m_pr:
        n = int(m_pr.group(1))
        if n in numbered and n != num:
            r = numbered[n]
            finish(one(pull(n, r[1], r[0], r[2]), jq), 0, include)
        if n != num:
            raise Refused(api_error(404, "Not Found"))
        head = feat_head()
        if S.get("put_done"):  # a read after the merge call: the state read
            if S.get("state_read_fail"):
                raise Refused(S["state_read_fail"])
            head = S.get("state_head") or head
            merged = bool(S.get("oid"))
            pr = pull(n, head, "feat", S.get("base", "main"), "closed" if merged else "open", merged, False, None if merged else True,
                      "unknown" if merged else "clean", S.get("body", ""), S["oid"] if merged else TEST_MERGE_SHA)
        else:  # the head read
            lag = S.get("lag")
            if lag and lag["n"] > 0 and head != lag["prior"]:  # GitHub still shows the head before the push
                lag["n"] -= 1; save(); head = lag["prior"]
            vf = S.get("view_fail")  # {"n", "msg", "after"}: once the head is off `after` (the pre-claim head), the next n reads fail with msg
            if vf and vf["n"] > 0 and head != vf["after"]:
                vf["n"] -= 1; S["view_failed"] = S.get("view_failed", 0) + 1; save()
                raise Refused(vf["msg"])
            seq = S.get("mergeable_seq")  # one value per head read, the last repeats: true, false or null (GitHub is still working it out)
            if seq:
                val = seq.pop(0) if len(seq) > 1 else seq[0]; save()
            else:
                val = not (S.get("dirty_after_checks") is not None and S.get("checks_calls", 0) >= S["dirty_after_checks"])
            locked = bool(ref("refs/heads/merge-lock/main"))
            draft = bool(S.get("draft")) or (bool(S.get("draft_when_locked")) and locked)  # draft_when_locked: the PR turns draft once the merge lock is taken
            pr = pull(n, head, "feat", S.get("base", "main"), "open", False, draft, val, {True: "clean", False: "dirty", None: "unknown"}[val], S.get("body", ""))
            if locked and S.get("merge_state_when_locked"):  # mergeable_state once the merge lock is taken: clean for the preview read, this for every read after it
                pr["mergeable_state"] = S["merge_state_when_locked"]
            S["shown"] = S.get("shown", []) + [head]; save()
        pr.update(S.get("pr_raw") or {})  # a test's own raw fields, for the mapping table
        finish(one(pr, jq), 0, include)

    elif method == "PUT" and m_put and int(m_put.group(1)) == num:
        S["put_done"] = True; save()
        sha = params.get("sha")
        if S.get("rival_at_merge") and not S.get("rival_done"):  # a push lands between the last read and the merge call
            S["rival_done"] = True; save()
            git("fetch", "-q", "origin"); git("checkout", "-q", "-B", "feat", "origin/feat")
            open(os.path.join(S["other"], "rival.txt"), "w").write("someone else pushed\n")
            git("add", "-A"); git("commit", "-q", "-m", "rival"); git("push", "-q", "origin", "feat")
        if S.get("merge_fail"):
            raise Refused(S["merge_fail"])
        seq = S.get("merge_replies") or []  # [msg, lands(, code)] per call, the last repeats. lands: the merge reaches the server first; msg: the reply ("" for a success); code: the exit status, 1 unless given
        ent = (seq.pop(0) if len(seq) > 1 else seq[0]) if seq else ["", True]
        msg, lands, code = ent[0], ent[1], (ent[2] if len(ent) > 2 else 1)
        if seq: save()
        if not lands:
            if code:
                raise Refused(msg, code)
            finish(msg, 0, include)
        if sha is not None and feat_head() != sha:
            raise Refused(api_error(409, "Head branch was modified. Review and try the merge again."))
        B = S.get("base", "main")
        git("fetch", "-q", "origin"); git("checkout", "-q", "-B", B, "origin/" + B)
        git("merge", "-q", "--no-ff", "-m", "merge", sha or feat_head()); git("push", "-q", "origin", B)
        S["oid"] = git("rev-parse", "HEAD"); save()
        if msg:
            finish(msg, code, include)
        finish(json.dumps({"sha": S["oid"], "merged": True, "message": "Pull Request successfully merged"}), 0, include)

    elif method == "GET" and (m_run or m_sta):
        sha = (m_run or m_sta).group(1)
        if sha not in set(S.get("shown", [])) | {feat_head()}:
            raise Refused(api_error(422, "No commit found for SHA: " + sha))
        cf = S.get("checks_fail")  # {"n", "msg"}: the next n reads fail with msg, then it answers
        if cf and cf["n"] > 0:
            cf["n"] -= 1; S["checks_failed"] = S.get("checks_failed", 0) + 1; save()
            raise Refused(cf["msg"])
        key = "n_runs" if m_run else "n_status"
        i = S.get(key, 0); S[key] = i + 1
        # broken_from counts rounds per route (a round is one check-run read and one status read, in either order), so the second route of a round is not cut off early
        if S.get("checks_broken") and i >= S.get("broken_from", 0):
            S[key] = i; save()
            raise Refused(api_error(404, "Not Found"))  # a 4xx is a refusal, not a network error: the wait's read reverts (a 5xx is a network stop, see GhHalf)
        if m_run:
            S["checks_calls"] = S.get("checks_calls", 0) + 1
        save()
        raw = S.get("raw_checks")  # a round written as REST objects: {"check_runs": [...], "statuses": [...]}
        if raw:
            cur = raw[min(i, len(raw) - 1)]
        else:
            seq = S["checks_seq"]; rows_now = seq[min(i, len(seq) - 1)]
            cur = {"check_runs": [check_run(r, k) for k, r in enumerate(rows_now) if len(r) < 4 or r[3] != "status"],
                   "statuses": [status_entry(r, k) for k, r in enumerate(rows_now) if len(r) >= 4 and r[3] == "status"]}
        if m_run:
            finish(listing(cur["check_runs"], "check_runs", params, flags, jq, cap, {"total_count": len(cur["check_runs"])}), 0, include)
        finish(listing(cur["statuses"], "statuses", params, flags, jq, cap, {"state": combined_state(cur["statuses"]), "sha": sha, "total_count": len(cur["statuses"])}), 0, include)

    elif method == "GET" and rel == "actions/runs":
        runs = S.get("base_runs", [])
        finish(one({"total_count": len(runs), "workflow_runs": runs}, jq), 0, include)

    elif method == "GET" and m_jobs:
        jobs = (S.get("base_jobs") or {}).get(m_jobs.group(1), [])
        finish(listing(jobs, "jobs", params, flags, jq, cap, {"total_count": len(jobs)}), 0, include)

    elif method == "GET" and m_req:
        af = S.get("api_fail")  # {"msg", "after_checks"}: once the checks have been read that many times, each read fails with msg
        if af and S.get("checks_calls", 0) >= af["after_checks"]:
            S["api_failed"] = S.get("api_failed", 0) + 1; save()
            raise Refused(af["msg"])
        if S.get("contexts") is None:
            raise Refused(api_error(404, "Branch not protected"))
        finish(one({"strict": True, "contexts": S["contexts"], "checks": [{"context": c, "app_id": None} for c in S["contexts"]]}, jq), 0, include)

    else:
        raise Refused(api_error(404, "Not Found"))
except Refused as e:
    finish(e.text, e.code, include)
'''


def rest_lib():
    """GH_REST_LIB as a namespace, for the fakes that run in this process (CapsHost, LaneHost)."""
    ns = {}
    exec(GH_REST_LIB, ns)
    return types.SimpleNamespace(**{k: v for k, v in ns.items() if not k.startswith("__")})

REST = rest_lib()
rest_err = REST.api_error

def install_gh_shim(test):
    """Put the fake `gh` (FAKE_GH_PR) first on PATH for one test. Its state lives in test.state. A GraphQL call that reaches it fails the test."""
    bindir = os.path.join(test.t, "bin"); os.makedirs(bindir)
    put_shim(os.path.join(bindir, "gh"), FAKE_GH_PR)
    test.state = os.path.join(test.t, "ghstate"); os.makedirs(test.state)
    old = {k: os.environ.get(k) for k in ("PATH", "FAKE_GH_DIR")}
    os.environ["PATH"] = bindir + os.pathsep + old["PATH"]; os.environ["FAKE_GH_DIR"] = test.state
    test.addCleanup(lambda: [os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None) for k, v in old.items()])
    test.addCleanup(assert_no_graphql, test)

def assert_no_graphql(test):
    log = pathlib.Path(test.state, "graphql.log")
    if log.exists():
        test.fail("a GraphQL call reached gh, and a Claude Code cloud session answers it HTTP 403: " + "; ".join(log.read_text().splitlines()))

# The text real gh prints for a network failure.
NET_TLS = 'Get "https://api.github.com/repos/o/r/pulls/7": net/http: TLS handshake timeout'
# Network texts NET_ERROR must match: a Windows socket, a deadline, a refused connect; git's name lookup.
NET_WSARECV = 'Get "https://api.github.com/repos/o/r/pulls/7": read tcp 10.0.0.5:51322->140.82.112.6:443: wsarecv: An existing connection was forcibly closed by the remote host'
NET_DEADLINE = 'Get "https://api.github.com/repos/o/r/pulls/7": context deadline exceeded'
NET_REFUSED = 'Get "https://api.github.com/repos/o/r/pulls/7": dial tcp 140.82.112.6:443: connect: connection refused'
NET_HOST = "fatal: unable to access 'https://github.com/shivinate7/claude-settings/': Could not resolve host: github.com"

# Rate-limit texts (`gh run list` answered HTTP 403). The request id and the
# timestamp in a text belong to the request. They are no reset time.
RATE_403 = ("failed to get runs: HTTP 403: API rate limit exceeded for user ID 309471439. If you reach out to GitHub Support for help, please include the request ID "
            "727E:322B55:45396D:E55920:6ACF7502 and timestamp 2026-10-14 12:26:42 UTC. For more on scraping GitHub and how it may affect your rights, please review our Terms of Service "
            "(https://docs.github.com/en/site-policy/github-terms/github-terms-of-service) (https://api.github.com/repos/ssemwal-cdc/q_max/actions/workflows?page=1&per_page=100)")
_SECONDARY = ("You have exceeded a secondary rate limit. Please wait a few minutes before you try again. If you reach out to GitHub Support for help, "
              "please include the request ID 1A2B:3C4D:5E6F and timestamp 2026-10-14 12:30:00 UTC.")
RATE_SECONDARY_403 = f"failed to get runs: HTTP 403: {_SECONDARY} (https://api.github.com/repos/o/r/actions/runs?head_sha=abc)"
RATE_GQL_403 = f"HTTP 403: {_SECONDARY} (https://api.github.com/graphql)"  # the form on `gh pr merge`
# `gh api` prints the JSON body, then its own line, with no newline between (see GH_API_TAIL).
RATE_API_403 = ('{"message":"API rate limit exceeded for user ID 309471439.","documentation_url":"https://docs.github.com/rest/overview/rate-limits-for-the-rest-api","status":"403"}'
                "gh: API rate limit exceeded for user ID 309471439. If you reach out to GitHub Support for help, please include the request ID 727E:322B55:45396D:E55920:6ACF7502 "
                "and timestamp 2026-10-14 12:26:42 UTC. (HTTP 403)")
RATE_API_SECONDARY_403 = ('{"message":"You have exceeded a secondary rate limit.","documentation_url":"https://docs.github.com/rest/overview/rate-limits-for-the-rest-api","status":"403"}'
                          f"gh: {_SECONDARY} (HTTP 403)")
R429 = "failed to get runs: HTTP 429: Too Many Requests (https://api.github.com/repos/o/r/actions/runs?head_sha=abc)"
# A 403 that is a permission refusal: the same three shapes, no rate limit.
PLAIN_403 = "failed to get runs: HTTP 403: Resource not accessible by integration (https://api.github.com/repos/o/r/actions/runs?head_sha=abc)"
PLAIN_403_BRANCH = "HTTP 403: Must have admin rights to Repository. (https://api.github.com/repos/o/r/branches/main/protection/required_status_checks)"
PLAIN_403_API = ('{"message":"Resource not accessible by integration","documentation_url":"https://docs.github.com/rest","status":"403"}'
                 "gh: Resource not accessible by integration (HTTP 403)")
# The GraphQL form on `gh pr checks`, `gh pr view` and `gh pr merge`: no HTTP status in the line.
RATE_GQL_ALREADY = "GraphQL: API rate limit already exceeded for user ID 309471439."

# c53: the merge tool reads and merges through the REST API (`gh api`), because a cloud session answers GraphQL with HTTP 403.
# The fake gh logs one line per call: METHOD, the route under repos/<owner>/<repo>, the fields sorted, then --paginate or --slurp.
# A read of the pull request after the merge call carries the suffix "after-merge".
MERGE_CALL = "PUT pulls/7/merge"
STATE_READ = "GET pulls/7 after-merge"
LIST_CALL = "GET pulls "
CHECKS_CALL = "GET commits/"
REPO_CALL = "GET (repo)"
NOT_MERGEABLE = rest_err(405, "Pull Request is not mergeable")
NOT_FOUND = rest_err(404, "Not Found")

# The rate waits, in seconds, when GitHub gives no reset time: one per retry. The last one is also the cap on any wait.
# The retry count is 3. The ladder waits 21 minutes in all.
RATE_LADDER = [60, 300, 900]
_HTTP_TEXT = {200: "OK", 403: "Forbidden", 404: "Not Found", 422: "Unprocessable Entity", 429: "Too Many Requests", 500: "Internal Server Error", 502: "Bad Gateway"}

def http_code_of(text):
    """The status in gh's own error line, `(HTTP 403)` or `HTTP 422: ...`. Else 400."""
    found = re.findall(r"HTTP (\d{3})", text)
    return int(found[-1]) if found else 400

def gh_i(code, body, **headers):
    """What `gh api -i` prints (measured on gh 2.98.0, on 200 and 403, with and without --jq): the status line, the headers with
    Go-canonical names, a blank line, then the body and, on a failure, gh's own error line after it. `--jq` does not strip the block. A
    keyword's underscores are dashes: Retry_After is `Retry-After`. GitHub itself answers HTTP/2.0, so the status line is too."""
    lines = [f"HTTP/2.0 {code} {_HTTP_TEXT.get(code, 'Error')}", "Content-Type: application/json; charset=utf-8",
             *(f"{k.replace('_', '-')}: {v}" for k, v in headers.items())]
    return "\r\n".join(lines) + "\r\n\r\n" + body

def without_include(args):
    """`gh api`'s args with -i/--include left out, so a fake that reads them by position keeps working wherever the build puts the flag."""
    return [x for x in args if x not in ("-i", "--include")]

class Clock:
    """A fake clock for the rate waits: each pause moves it on and records the wait, so a 900 s wait costs no time and expiry arithmetic is real.
    now() and pause() are the seams every gh caller already takes."""
    def __init__(self, t=1000.0):
        self.t, self.pauses = t, []

    def now(self):
        return self.t

    def pause(self, seconds):
        self.pauses.append(seconds)
        self.t += seconds

def drop_config(env):
    """Remove .github/stamp.json from main and feat, as in 5 of the owner's 8 repos. Then pull main into env.co."""
    o = env.other
    for b in ("main", "feat"):
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", b, f"origin/{b}")
        sh(o, "git", "rm", "-q", ".github/stamp.json")
        sh(o, "git", "commit", "-qm", f"no config on {b}")
        sh(o, "git", "push", "-q", "origin", b)
    sh(env.co, "git", "pull", "-q", "--ff-only")
    head_takes_base(env)

def stamp_marker(env):
    """Point merge.STAMP at a stub that writes a file when it runs. -> that file's path; absent unless stamp ran."""
    mark = os.path.join(env.t, "stamp-ran")
    fake = os.path.join(env.t, "marker-stamp.mjs")
    put(fake, 'import { writeFileSync } from "node:fs";\nwriteFileSync(process.env.STAMP_MARK, "ran");\n')
    for p in (unittest.mock.patch.object(merge, "STAMP", fake), unittest.mock.patch.dict(os.environ, {"STAMP_MARK": mark})):
        p.start(); env.addCleanup(p.stop)
    return mark

class GhHalf(Env):
    """Host against a `gh` shim on PATH. The shim merges into the local bare origin through the `other` clone."""
    def setUp(self):
        super().setUp()
        install_gh_shim(self)
        self.ticks, self.paused, self.at_pause = 0, [], []
        self.set(checks_seq=[[("checks", "pass", "")]])

    def set(self, **kw):
        p = os.path.join(self.state, "state.json")
        f = pathlib.Path(p)
        s = json.loads(f.read_text()) if f.exists() else {"other": self.other, "bare": self.bare, "checks_calls": 0}
        s.update(kw)
        f.write_text(json.dumps(s))

    def calls(self):
        p = pathlib.Path(self.state, "calls.log")
        return p.read_text() if p.exists() else ""  # a case that makes no gh call leaves no log

    def gh_host(self, required=("checks",), pause=None, ignore=None, minute=60):
        def tick(s):
            self.ticks += 1
            self.paused.append(s)
            assert self.ticks < 200, "the wait never ended"
            self.now += s
            if s in RATE_LADDER:  # a rate wait: what the lock on origin says as the wait starts (the clock is already at the wait's end)
                cur = self.lock.read("main")
                self.at_pause.append((s, self.now, cur[1] if cur else None))
            if pause:
                pause()
        return merge.Host(required if required == "protection" else list(required), "main", minute=minute, now=lambda: self.now, pause=tick, ignore=ignore)

    def go(self, **kw):
        return self.run_merge("7", "--confirm", host=self.gh_host(**kw))

    def test_a_red_main_run_read_through_gh_refuses_the_merge(self):
        # the red-main check's REST reads through the real gh call: one page of main's runs, then the red run's jobs
        push_base(self, {".github/workflows/checks.yml": MAIN_WORKFLOW})  # only a workflow file on main is judged
        self.set(base_runs=[main_run(901, "failure")], base_jobs={"901": [main_job("scope", "success"), main_job("checks", "failure", 20)]})
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertIn("run 901", out)
        self.assertIn("checks: fail", out)
        self.assertIn("GET actions/runs branch=main per_page=50", self.calls())
        self.assertNotIn("PUT pulls/7/merge", self.calls())

    def test_open_heads_lists_the_open_pr_heads_past_ghs_default_of_30(self):
        # A list read stops at its first page (30 rows by default) unless it asks for 100 a page and every page. A lane whose open PR is past row 30 would be deleted, and its PR closed.
        # Each head comes with its sha and its PR's base, {name: (sha, base)}, so the cut can tell the lane's own PR
        # (base = the batch's base) from a backport, and see a stacked PR whose base is a lane.
        self.set(open_prs=[["lane2", "a" * 40, "main"], ["agent/lane1", "b" * 40, "release/1.0"]])
        got = self.gh_host().open_heads()
        self.assertEqual(got, {"lane2": ("a" * 40, "main"), "agent/lane1": ("b" * 40, "release/1.0")})
        calls = self.calls()
        for part in (LIST_CALL, "state=open", "per_page=100", "--paginate"):  # one page holds 100 at most, and --paginate takes the rest
            self.assertIn(part, calls)

    def test_a_failed_open_pr_read_is_never_an_empty_set(self):
        # An empty set means no PR is open, and every lane would go. A failure stops (merge.Stop) or answers None.
        self.set(open_heads_fail="HTTP 404: Not Found")
        try:
            got = self.gh_host().open_heads()
        except merge.Stop:
            return
        self.assertIsNone(got)

    def test_the_pr_body_gh_reports_reaches_the_silent_undo_check_at_preview(self):
        # Host.pr reads the body in its read of the pull request (GET pulls/7), so a Drops-lines line in the body excuses its path.
        SilentUndo.stale_feat(self)
        self.set(body="Drops-lines: docs/decisions/first.md -- the lines are dead")
        rc, out = self.run_merge("7", host=self.gh_host())
        self.assertEqual(rc, 0, out)
        self.assertIn("ALLOWED docs/decisions/first.md: the lines are dead", out)
        self.assertIn("GET pulls/7", self.calls())

    def test_a_batch_with_lanes_reads_the_open_prs_through_gh_and_keeps_those_lanes(self):
        # Ruling 1: the open PR's head is a newer commit than lane2's tip, so lane2 is kept. Origin's lane2 stays at the tip.
        lane_batch(self, "agent/lane1", "lane2")
        self.set(open_prs=[["lane2", self.head("main"), "main"]])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertIn(LIST_CALL, self.calls())
        lane_deleted_line(self, out, "agent/lane1")
        self.assertEqual(self.head("agent/lane1"), "")
        self.assertIn(LANE_KEPT.format(b="lane2", why=WHY["open"]), out)
        self.assertNotEqual(self.head("lane2"), "")

    def test_a_batch_lane_whose_open_pr_is_at_its_tip_is_deleted_through_gh(self):
        # Per decision merge-deletes-batch-lanes (lane cleanup), through gh: the PR head is the lane tip, so the PR does not block the delete. Its base is the batch's base.
        tips = lane_batch(self, "agent/lane1", "lane2")
        self.set(open_prs=[["agent/lane1", tips["agent/lane1"], "main"]])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        lane_deleted_line(self, out, "agent/lane1")
        lane_deleted_line(self, out, "lane2")
        self.assertEqual(self.head("agent/lane1"), "")
        self.assertNotIn(WHY["open"], out)

    def test_a_backport_pr_at_the_lane_tip_keeps_the_lane_through_gh(self):
        # Through gh: the PR at the tip has base release/1.0, so it is a backport, not the lane's own PR, and the lane is kept.
        tips = lane_batch(self, "agent/lane1", "lane2")
        self.set(open_prs=[["agent/lane1", tips["agent/lane1"], "release/1.0"]])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        kept = [l for l in out.splitlines() if l.startswith("merge: lane origin/agent/lane1: kept:")]
        self.assertEqual(len(kept), 1, out)
        self.assertNotEqual(self.head("agent/lane1"), "", "agent/lane1 was deleted")
        lane_deleted_line(self, out, "lane2")

    def test_a_stacked_pr_keeps_the_lane_that_is_its_base_through_gh(self):
        # Through gh: an open PR (head stack) has lane2 as its base, so lane2 stays. agent/lane1 has no PR.
        lane_batch(self, "agent/lane1", "lane2")
        self.set(open_prs=[["stack", self.head("main"), "lane2"]])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        kept = [l for l in out.splitlines() if l.startswith("merge: lane origin/lane2: kept:")]
        self.assertEqual(len(kept), 1, out)
        self.assertNotEqual(self.head("lane2"), "", "lane2 was deleted")
        lane_deleted_line(self, out, "agent/lane1")

    def batch_with_open_prs(self, rows_of):
        """Two lanes in one batch, then the open-PR rows that rows_of(tips) returns, in the order gh lists them. -> (tips, out)."""
        tips = lane_batch(self, "lane1", "lane2")
        self.set(open_prs=rows_of(tips))
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        return tips, out

    def assert_both_lanes_deleted(self, out):
        for b in ("lane1", "lane2"):
            lane_deleted_line(self, out, b)
            self.assertEqual(self.head(b), "", f"{b} is still on origin")
        self.assertEqual([l for l in out.splitlines() if ": kept:" in l], [], out)

    def test_a_same_batch_lane_with_a_main_pr_first_and_a_stacked_pr_second_is_deleted(self):
        # Through gh: lane2 has two open PRs at its tip, to main then to lane1. Both are done, so both lanes go.
        # Before the fix, the second row's base was kept under a new key, and lane2 read as having more than one PR.
        _, out = self.batch_with_open_prs(lambda t: [["lane2", t["lane2"], "main"], ["lane2", t["lane2"], "lane1"]])
        self.assert_both_lanes_deleted(out)

    def test_a_same_batch_lane_with_a_stacked_pr_first_and_a_main_pr_second_is_deleted(self):
        # Through gh: the same two PRs in the other row order. The result must not change with the order.
        _, out = self.batch_with_open_prs(lambda t: [["lane2", t["lane2"], "lane1"], ["lane2", t["lane2"], "main"]])
        self.assert_both_lanes_deleted(out)

    def test_an_outside_head_whose_stacked_pr_comes_first_keeps_the_base_lane(self):
        # Through gh: outside head stack-top has two open PRs, to lane1 then to main. Its PR to lane1 keeps lane1.
        # The first row's base must not be lost: before the fix it was, and lane1 was deleted under an open PR.
        _, out = self.batch_with_open_prs(lambda t: [["stack-top", self.head("main"), "lane1"], ["stack-top", self.head("main"), "main"]])
        self.assertIn("stack-top", kept_line(self, out, "lane1"))
        self.assertNotEqual(self.head("lane1"), "", "lane1 was deleted")
        self.assert_deleted_lane2(out)

    def test_an_outside_head_whose_main_pr_comes_first_keeps_the_base_lane(self):
        # Control, through gh: the same two PRs, main row first. Lane1 is kept whichever row comes first.
        _, out = self.batch_with_open_prs(lambda t: [["stack-top", self.head("main"), "main"], ["stack-top", self.head("main"), "lane1"]])
        self.assertIn("stack-top", kept_line(self, out, "lane1"))
        self.assertNotEqual(self.head("lane1"), "", "lane1 was deleted")
        self.assert_deleted_lane2(out)

    def assert_deleted_lane2(self, out):
        lane_deleted_line(self, out, "lane2")
        self.assertEqual(self.head("lane2"), "", "lane2 is still on origin")

    def test_a_batch_without_lanes_makes_no_open_pr_list_call(self):
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertNotIn(LIST_CALL, self.calls())

    def test_5_base_aware_protection_mode_reads_the_protection_of_the_base(self):
        sh(self.other, "git", "fetch", "-q", "origin")
        sh(self.other, "git", "push", "-q", "origin", "origin/main:refs/heads/integ")
        self.set(base="integ", contexts=["checks"])
        self.host = None  # run_merge then lets main() build the real Host from the config
        self.run_merge("7")
        calls = self.calls()
        self.assertIn("branches/integ/protection/required_status_checks", calls)
        self.assertNotIn("branches/main/protection", calls)

    def reverted(self):
        return "id: pending" in self.show("feat", "docs/decisions/second.md")

    def gh_state(self, key):
        return json.loads(pathlib.Path(self.state, "state.json").read_text()).get(key)

    def feat_subjects(self):
        sh(self.co, "git", "fetch", "-q", "origin")
        return sh(self.co, "git", "log", "origin/feat", "--format=%s")

    def test_a_network_error_on_the_wait_read_is_retried_and_the_merge_goes_on(self):
        self.set(view_fail={"n": 1, "msg": NET_TLS, "after": self.head()})  # the first read after the claim push fails
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.gh_state("view_failed"), 1)
        self.assertIn(MERGE_CALL, self.calls())
        self.assertNotIn("reverted on", out)
        self.assertEqual(self.claims("main"), 1)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))
        self.assertFalse(self.lock_ref())

    def test_three_network_errors_are_retried_and_the_fourth_try_goes_through(self):
        self.set(view_fail={"n": 3, "msg": NET_TLS, "after": self.head()})  # the boundary of "up to 3 times"
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.gh_state("view_failed"), 3)
        self.assertNotIn("reverted on", out)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))

    def test_four_network_errors_stop_the_merge_and_keep_the_claim(self):
        self.set(view_fail={"n": 4, "msg": NET_TLS, "after": self.head()})
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.gh_state("view_failed"), 4, out)  # one try and three retries, then stop: no fifth try
        self.assertIn("network", out.lower())
        self.assertIn("TLS handshake timeout", out)
        self.assertNotIn("reverted on", out)
        self.assertNotIn("Revert", self.feat_subjects())  # the claim stands on the branch
        self.assertIn("Claim record numbers", self.feat_subjects())
        self.assertFalse(self.reverted())
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertFalse(self.lock_ref())
        self.set(view_fail=None)  # the network is back: the next run resumes the claim and merges
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertIn("resumed", out)
        self.assertEqual(self.claims("main"), 1)

    def test_a_real_refusal_in_the_wait_reverts_the_claim_and_is_not_retried(self):
        self.set(view_fail={"n": 1, "msg": PLAIN_403_API, "after": self.head()})
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.gh_state("view_failed"), 1, out)  # tried once
        self.assertIn("reverted on feat", out)
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertTrue(self.reverted())
        self.assertFalse(self.lock_ref())

    def test_a_lost_merge_reply_then_not_mergeable_reads_merged_and_carries_on(self):
        self.set(merge_replies=[[NET_TLS, True], [NOT_MERGEABLE, False]])  # the merge lands, its reply is lost
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("reverted on", out)
        self.assertEqual(self.calls().count(MERGE_CALL), 2)
        self.assertIn(STATE_READ, self.calls())  # the retry's answer is not trusted: the PR state is read
        self.assertEqual(self.claims("main"), 1)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))
        self.assertFalse(self.lock_ref())

    def test_a_lost_merge_reply_then_404_reads_merged_and_carries_on(self):
        self.set(merge_replies=[[NET_TLS, True], [NOT_FOUND, False]])  # a stale ref on the retry
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("reverted on", out)
        self.assertEqual(self.calls().count(MERGE_CALL), 2)
        self.assertIn(STATE_READ, self.calls())
        self.assertEqual(self.claims("main"), 1)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))
        self.assertFalse(self.lock_ref())

    def test_a_plain_already_merged_answer_on_the_first_merge_reads_the_state_and_carries_on(self):
        self.set(merge_replies=[[NOT_MERGEABLE, True]])  # no network error before it
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("reverted on", out)
        self.assertEqual(self.calls().count(MERGE_CALL), 1)
        self.assertIn(STATE_READ, self.calls())
        self.assertEqual(self.claims("main"), 1)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))
        self.assertFalse(self.lock_ref())

    def test_a_red_check_named_eof_is_a_refusal_not_a_network_retry(self):
        self.set(checks_seq=[[("checks", "pass", ""), ("EOF lint", "fail", "https://x/y")]])  # "EOF" in the JSON must not match the network pattern
        rc, out = self.go()
        self.assertEqual(self.paused, [], out)  # no retry, so no pause
        self.assertEqual(rc, 1, out)
        self.assertIn("a check is red: EOF lint: fail", out)
        self.assertNotIn("network", out.lower())
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertEqual(self.claims("feat"), 0)  # refused before the claim push

    def test_four_network_errors_on_the_merge_read_merged_and_carry_on(self):
        self.set(merge_replies=[[NET_TLS, True], [NET_TLS, False]])  # the first merge lands, its reply and the three retries are lost
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.calls().count(MERGE_CALL), 4)
        self.assertIn(STATE_READ, self.calls())
        self.assertNotIn("reverted on", out)
        self.assertEqual(self.claims("main"), 1)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))
        self.assertFalse(self.lock_ref())

    def test_four_network_errors_on_the_merge_with_the_pr_open_stop_without_a_revert(self):
        self.set(merge_replies=[[NET_TLS, False]])  # nothing lands: four calls, all lost
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.calls().count(MERGE_CALL), 4)
        self.assertIn(STATE_READ, self.calls())  # the PR state is read: OPEN
        self.assertNotIn("reverted on", out)
        self.assertIn("network", out.lower())
        self.assertIn("Claim record numbers", self.feat_subjects())  # the claim stays
        self.assertFalse(self.lock_ref())

    def go_with_fetch_after_push(self, msg):
        """The fetch of main after the claim push fails with `msg`. -> (rc, out)."""
        real_git, real_push = merge.git, merge.push_branch
        pushed = []
        def push(wt, branch):
            pushed.append(branch)
            return real_push(wt, branch)
        def git_fails(cwd, *a, input=None):
            if pushed and a[:2] == ("fetch", "-q") and a[-1] == "+refs/heads/main:refs/remotes/origin/main":
                return 1, msg
            return real_git(cwd, *a, input=input)
        with unittest.mock.patch.object(merge, "push_branch", push), unittest.mock.patch.object(merge, "git", git_fails):
            return self.go()

    def test_a_git_fetch_network_error_after_the_claim_push_stops_without_a_revert(self):
        rc, out = self.go_with_fetch_after_push(NET_TLS)  # the fetch of main loses its network
        self.assertEqual(rc, 1, out)
        self.assertNotIn("reverted on", out)
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertIn("network", out.lower())
        self.assertIn("Claim record numbers", self.feat_subjects())  # the claim stays
        self.assertFalse(self.lock_ref())

    def test_a_git_fetch_could_not_resolve_host_after_the_claim_push_stops_without_a_revert(self):
        rc, out = self.go_with_fetch_after_push(NET_HOST)
        self.assertNotIn("reverted on", out)
        self.assertEqual(rc, 1, out)
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertIn("Claim record numbers", self.feat_subjects())  # the claim stays
        self.assertFalse(self.lock_ref())

    def lost_reply_reads_merged(self, msg):
        """The merge lands, its reply is `msg`, and the retries are lost too. The PR reads MERGED at the proven head: carry on."""
        self.set(merge_replies=[[msg, True], [msg, False]])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("reverted on", out)
        self.assertIn(STATE_READ, self.calls())  # the PR state is read
        self.assertEqual(self.claims("main"), 1)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))
        self.assertFalse(self.lock_ref())

    def test_a_lost_merge_reply_with_a_wsarecv_error_reads_merged_and_carries_on(self):
        self.lost_reply_reads_merged(NET_WSARECV)

    def test_a_network_error_then_a_real_not_mergeable_reply_reverts_the_claim(self):
        self.set(merge_replies=[[NET_TLS, False], [NOT_MERGEABLE, False]])  # the retry gets a real refusal
        rc, out = self.go()
        self.assertIn("reverted on feat", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.calls().count(MERGE_CALL), 2)  # the refusal is not retried
        self.assertTrue(self.reverted())
        self.assertFalse(self.lock_ref())

    def test_already_merged_at_another_head_is_not_this_runs_merge_and_stops_without_a_revert(self):
        before = self.head()  # the branch head before the claim push: not the proven sha
        self.set(merge_replies=[[NOT_MERGEABLE, True]], state_head=before)
        rc, out = self.go()
        self.assertNotIn("reverted on", out)
        self.assertEqual(rc, 1, out)
        self.assertIn(STATE_READ, self.calls())
        self.assertIn("Claim record numbers", self.feat_subjects())  # the claim stays
        self.assertFalse(self.lock_ref())

    def test_already_merged_then_a_plain_state_read_failure_reverts_nothing(self):
        self.set(merge_replies=[[NOT_MERGEABLE, False]],
                 state_read_fail=NOT_FOUND)
        rc, out = self.go()
        self.assertNotIn("reverted on", out)
        self.assertEqual(rc, 1, out)
        self.assertIn(STATE_READ, self.calls())
        self.assertIn("Claim record numbers", self.feat_subjects())  # the claim stays
        self.assertFalse(self.lock_ref())

    # ---- only a proven refusal reverts the claim

    def test_a_merge_that_exits_zero_while_the_pr_reads_open_stops_without_a_revert(self):
        self.set(merge_replies=[["", False, 0]])  # gh exits 0 and says nothing; nothing landed; the PR reads OPEN
        rc, out = self.go()
        self.assertNotIn("reverted on", out)
        self.assertEqual(rc, 1, out)
        self.assertIn(STATE_READ, self.calls())
        self.assertIn("Claim record numbers", self.feat_subjects())  # the claim stays
        self.assertFalse(self.lock_ref())

    def required_read_fails_after_the_claim(self, msg, rate=False):
        """The required-checks read fails with `msg` from the wait after the claim push on. Retried 3 times, then a stop: no revert.
        `rate`: msg is a rate limit, and the run waits the whole ladder (see rate_waits_the_whole_ladder)."""
        self.set(contexts=["checks"], api_fail={"msg": msg, "after_checks": 1})
        rc, out = self.go(required="protection")
        self.assertNotIn("reverted on", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.gh_state("api_failed"), 4, out)  # one try and three retries
        if rate:
            self.rate_waits_the_whole_ladder(out)
        self.assertIn("Claim record numbers", self.feat_subjects())  # the claim stays
        self.assertFalse(self.lock_ref())

    def test_a_required_check_read_with_gh_server_error_502_stops_without_a_revert(self):
        self.required_read_fails_after_the_claim("gh: Server Error (HTTP 502)")

    def merge_reply_is_retried_then_stops(self, msg, rate=False):
        """Every merge try answers `msg` and nothing lands: a network-class error, retried 3 times, then a stop. The PR reads OPEN: no revert.
        `rate`: msg is a rate limit, and the run waits the whole ladder (see rate_waits_the_whole_ladder)."""
        self.set(merge_replies=[[msg, False]])
        rc, out = self.go()
        self.assertNotIn("reverted on", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.calls().count(MERGE_CALL), 4, out)  # one try and three retries
        if rate:
            self.rate_waits_the_whole_ladder(out)
        self.assertIn(STATE_READ, self.calls())
        self.assertIn("Claim record numbers", self.feat_subjects())  # the claim stays
        self.assertFalse(self.lock_ref())

    def test_a_merge_reply_server_error_502_is_retried_then_stops_without_a_revert(self):
        self.merge_reply_is_retried_then_stops(rest_err(502, "Server Error"))

    def fetch_fails_after_the_claim_push(self, msg):
        """The fetch of main after the claim push fails with `msg`, a network-class error: the claim stays, nothing is reverted."""
        rc, out = self.go_with_fetch_after_push(msg)
        self.assertNotIn("reverted on", out)
        self.assertEqual(rc, 1, out)
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertIn("Claim record numbers", self.feat_subjects())  # the claim stays
        self.assertFalse(self.lock_ref())

    def test_a_git_fetch_http2_stream_error_after_the_claim_push_stops_without_a_revert(self):
        self.fetch_fails_after_the_claim_push("fatal: unable to access 'https://github.com/shivinate7/claude-settings/': HTTP/2 stream 1 was not closed cleanly: INTERNAL_ERROR (err 2)")

    def test_a_merge_that_may_have_landed_with_an_unreadable_state_says_to_finish_by_hand(self):
        self.set(merge_replies=[[NET_TLS, True], [NET_TLS, False]],  # the merge lands, its reply and the retries are lost
                 state_read_fail=NOT_FOUND)
        rc, out = self.go()
        self.assertNotIn("reverted on", out)
        self.assertEqual(rc, 1, out)
        self.assertIn("by hand", out)  # the owner's next steps are named, not only "Run again"
        self.assertRegex(out, r"(?i)after-?merge")
        self.assertRegex(out, r"(?i)check (?:the|#7)")

    def test_a_real_first_refusal_reverts_the_claim_and_is_not_retried(self):  # pin: a proven refusal still reverts
        self.set(merge_replies=[[NOT_MERGEABLE, False]])
        rc, out = self.go()
        self.assertIn("reverted on feat", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.calls().count(MERGE_CALL), 1)  # a refusal is not retried
        self.assertTrue(self.reverted())
        self.assertFalse(self.lock_ref())

    def test_a_run_list_http_500_with_green_checks_is_a_network_error_not_not_green(self):
        # every check is green, gh run list answers HTTP 500
        self.set(runs_fail="HTTP 500: Internal Server Error (https://api.github.com/repos/o/r/actions/runs?head_sha=abc)")
        before = self.head()
        rc, out = self.go()
        self.assertNotIn("not green", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.calls().count("run list"), 4, out)  # one try and three retries
        self.assertIn("network", out.lower())
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertEqual(self.head(), before)  # nothing claimed or pushed
        self.assertFalse(self.lock_ref())

    LOCK_MARGIN = 300  # seconds, written as a literal so these cases do not read merge.LOCK_MARGIN

    def rate_waits_the_whole_ladder(self, out):
        """A rate limit that never clears, under the lock (a rate wait is the exception to the lock's 600 s cap). The run waits
        the whole ladder, 60 + 300 + 900 s, and only then stops as a network error: it never stops for the lock. As each wait starts, the lock on origin
        (read there, never lock.until) already expires LOCK_MARGIN after the wait ends. The caller counts the gh calls: 4. A settle pause is no rate wait."""
        self.assertEqual([s for s in self.paused if s != merge.SETTLE_SECONDS], RATE_LADDER, out)
        self.assertEqual([w[0] for w in self.at_pause], RATE_LADDER, out)
        for wait, ends, expiry in self.at_pause:
            self.assertIsNotNone(expiry, f"no lock on origin at the {wait} s wait")
            self.assertGreaterEqual(expiry, int(ends + self.LOCK_MARGIN), f"the lock expires at {expiry}, before the {wait} s wait (ends {ends}) plus the margin")
        self.assertIn("network", out.lower())  # the last try fails: the ordinary network stop, not a lock stop
        self.assertNotRegex(out, r"(?i)needs the merge lock extended|cannot extend")

    def run_list_fails_wrapped(self, msg, rate=False):
        """Every check is green and `gh run list` fails with the wrapped line `msg`: a network error, retried 3 times, then a stop. Nothing is claimed.
        `rate`: msg is a rate limit, and the run waits the whole ladder (see rate_waits_the_whole_ladder)."""
        self.set(runs_fail=msg)
        before = self.head()
        rc, out = self.go()
        self.assertNotIn("not green", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.calls().count("run list"), 4, out)  # one try and three retries
        if rate:
            self.rate_waits_the_whole_ladder(out)
        else:
            self.assertIn("network", out.lower())
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertEqual(self.head(), before)  # nothing claimed or pushed
        self.assertFalse(self.lock_ref())

    def test_a_wrapped_run_list_http_502_is_a_network_error_retried_then_stopped(self):
        self.run_list_fails_wrapped("failed to get runs: HTTP 502: 502 Bad Gateway (https://api.github.com/repos/o/r/actions/runs?head_sha=abc)")
        self.assertEqual(self.paused, [merge.NET_PAUSE] * 3)  # a plain network error waits the normal pause

    def test_a_wrapped_run_list_http_429_is_a_network_error_retried_then_stopped(self):
        self.run_list_fails_wrapped("failed to get runs: HTTP 429: Too Many Requests (https://api.github.com/repos/o/r/actions/runs?head_sha=abc)", rate=True)  # a 429 is a rate limit: the whole ladder, then the network stop

    # ---- a rate-limit 403 or a 429 is a network fault, never "not green" (RATE_LADDER)

    def test_a_run_list_rate_limit_403_is_a_network_error_retried_then_stopped(self):
        self.run_list_fails_wrapped(RATE_403, rate=True)  # 4 calls over the whole ladder, never "not green". Its request timestamp is no reset time.

    def test_a_run_list_secondary_rate_limit_403_is_a_network_error_retried_then_stopped(self):
        self.run_list_fails_wrapped(RATE_SECONDARY_403, rate=True)

    def test_a_run_list_rate_limit_403_that_clears_on_the_retry_lets_the_merge_go_on(self):
        self.set(runs_fail_first=[RATE_403])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("not green", out)
        self.assertEqual(self.gh_state("runs_failed"), 1)
        self.assertEqual(self.paused[0], RATE_LADDER[0], self.paused)  # the first pause is the retry's
        self.assertEqual(self.claims("main"), 1)
        self.assertFalse(self.lock_ref())

    def test_a_retry_after_in_the_gh_text_never_changes_the_rate_wait(self):
        self.set(runs_fail_first=["Retry-After: 17\n" + RATE_403])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.paused[0], RATE_LADDER[0], self.paused)  # the header's 17 s is ignored

    def checks_read_fails(self, msg, n=99, rate=False):
        """Every check is green and the checks read fails n times with `msg`. A network-class text: retried 3 times, then a stop. Nothing is claimed.
        `rate`: msg is a rate limit, and the run waits the whole ladder (see rate_waits_the_whole_ladder)."""
        self.set(checks_fail={"n": n, "msg": msg})
        before = self.head()
        rc, out = self.go()
        self.assertNotIn("not green", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.gh_state("checks_failed"), 4, out)  # one try and three retries
        if rate:
            self.rate_waits_the_whole_ladder(out)
        else:
            self.assertIn("network", out.lower())
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertEqual(self.head(), before)  # nothing claimed or pushed
        self.assertFalse(self.lock_ref())

    def test_a_checks_read_http_429_is_a_network_error_retried_then_stopped(self):
        self.checks_read_fails(rest_err(429, "Too Many Requests"), rate=True)  # a 429 is a rate limit: the whole ladder, then the network stop

    def test_a_checks_read_secondary_rate_limit_403_is_a_network_error_retried_then_stopped(self):
        self.checks_read_fails(RATE_API_SECONDARY_403, rate=True)

    def test_a_checks_read_primary_rate_limit_403_is_a_network_error_retried_then_stopped(self):
        self.checks_read_fails(RATE_API_403, rate=True)  # owner's grant: it retries like the 403 (the GraphQL form of this text is gone with GraphQL)

    def test_a_retry_after_on_a_checks_429_never_changes_the_rate_wait(self):
        self.set(checks_fail={"n": 1, "msg": "Retry-After: 17\n" + rest_err(429, "Too Many Requests")})
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.gh_state("checks_failed"), 1)
        self.assertEqual(self.paused[0], RATE_LADDER[0], self.paused)  # the header's 17 s is ignored

    def test_a_required_check_read_with_a_rate_limit_403_stops_without_a_revert(self):
        self.required_read_fails_after_the_claim(RATE_API_403, rate=True)  # `gh api` form: the claim stays, 4 tries over the whole ladder, then the network stop

    def test_a_required_check_read_with_a_secondary_rate_limit_403_stops_without_a_revert(self):
        self.required_read_fails_after_the_claim(RATE_API_SECONDARY_403, rate=True)

    def test_a_merge_reply_secondary_rate_limit_403_is_retried_then_stops_without_a_revert(self):
        self.merge_reply_is_retried_then_stops(RATE_API_SECONDARY_403, rate=True)

    def test_a_rate_wait_past_the_lock_spare_extends_the_lock_and_the_merge_goes_on(self):
        put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], deadlineMinutes=1))))  # the lock lasts (3 * 1 + 10) * 60 = 780 s: the 60 s and 300 s waits fit its spare, the 900 s wait does not
        self.set(merge_replies=[[RATE_API_SECONDARY_403, False]] * 3 + [["", True]])  # three rate-limited merge tries, then the merge lands
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.calls().count(MERGE_CALL), 4, out)
        self.assertEqual([s for s in self.paused if s != merge.SETTLE_SECONDS], RATE_LADDER, out)  # no wait cut short, none past the cap
        self.assertEqual([w[0] for w in self.at_pause], RATE_LADDER, out)
        for wait, ends, expiry in self.at_pause:
            self.assertGreaterEqual(expiry, int(ends + self.LOCK_MARGIN), f"the lock expires at {expiry}, before the {wait} s wait (ends {ends}) plus the margin")
        self.assertGreater(self.at_pause[2][2], self.at_pause[0][2], "the 900 s wait left the published expiry where it was: the lock was not extended")
        self.assertNotIn("reverted on", out)
        self.assertEqual(self.claims("main"), 1)  # the claim landed with the merge
        self.assertFalse(self.lock_ref())  # released

    def test_a_plain_403_on_run_list_is_a_refusal_not_retried_and_not_a_network_stop(self):  # (d): green before the lane, a guard
        self.set(runs_fail=PLAIN_403)
        before = self.head()
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.calls().count("run list"), 1, out)  # a refusal is not retried
        self.assertEqual(self.paused, [])  # no retry pause
        self.assertIn("HTTP 403", out)  # the refusal's own text
        self.assertNotIn("network", out.lower())
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertEqual(self.head(), before)
        self.assertFalse(self.lock_ref())

    def test_a_plain_403_on_the_required_check_read_reverts_the_claim_and_is_not_retried(self):  # (d): a guard
        self.set(contexts=["checks"], api_fail={"msg": PLAIN_403_API, "after_checks": 1})
        rc, out = self.go(required="protection")
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.gh_state("api_failed"), 1, out)  # tried once
        self.assertIn("reverted on feat", out)
        self.assertNotIn("network", out.lower())
        self.assertTrue(self.reverted())
        self.assertFalse(self.lock_ref())

    def test_a_merge_lock_read_that_fails_once_with_a_json_error_is_retried_and_the_run_goes_on(self):
        # Windows credential manager: ls-remote of the lock ref fails once, then works
        real_git = merge.git
        hits = []
        def flaky(cwd, *a, input=None):
            if a[:1] == ("ls-remote",) and a[-1] == "refs/heads/merge-lock/main" and not hits:
                hits.append(1)
                return 1, "unexpected end of JSON input"
            return real_git(cwd, *a, input=input)
        with unittest.mock.patch.object(merge, "git", flaky):
            rc, out = self.go()
        self.assertEqual(hits, [1])  # the first read failed
        self.assertNotIn("cannot read the merge lock", out)
        self.assertEqual(rc, 0, out)
        self.assertIn(MERGE_CALL, self.calls())
        self.assertEqual(self.claims("main"), 1)
        self.assertFalse(self.lock_ref())

    def test_a_refusal_whose_text_names_an_http_502_title_reverts_and_is_not_retried(self):
        self.set(merge_replies=[[rest_err(405, 'Pull Request is not mergeable: #7 "Fix (HTTP 502 retry)"'), False]])  # a real refusal; its text carries a 5xx-looking title
        rc, out = self.go()
        self.assertIn("reverted on feat", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.calls().count(MERGE_CALL), 1)  # a refusal is not retried
        self.assertNotIn(merge.NET_PAUSE, self.paused)  # no network-retry pause
        self.assertTrue(self.reverted())
        self.assertFalse(self.lock_ref())

    def test_a_red_check_named_http_500_is_a_refusal_that_reverts_and_is_not_retried(self):
        # the wait after the claim push reads the red check; its name carries "HTTP 500"
        self.set(checks_seq=[[("checks", "pass", "")], [("checks", "pass", "")],
                             [("checks", "pass", ""), ("build: HTTP 500 guard", "fail", "https://x/y")]])
        rc, out = self.go()
        self.assertIn("a check is red: build: HTTP 500 guard: fail", out)
        self.assertIn("reverted on feat", out)
        self.assertEqual(rc, 1, out)
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertNotIn(merge.NET_PAUSE, self.paused)  # no network-retry pause
        self.assertNotIn("network", out.lower())
        self.assertTrue(self.reverted())
        self.assertFalse(self.lock_ref())

    def test_green_run_waits_without_a_watch_and_merges_pinned_to_the_claim_head(self):
        self.set(checks_seq=[[("checks", "pending", "https://github.com/o/r/actions/runs/99/job/1")], [("checks", "pass", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        log = self.calls()
        self.assertNotIn("run watch", log)  # decision ci-wait-reads-run-status
        self.assertIn(30, self.paused)  # the wait between two reads of the checks
        self.assertIn(MERGE_CALL + " merge_method=merge sha=" + sh(self.co, "git", "rev-parse", "origin/main^2"), log)
        self.assertEqual(log.count("PUT "), 1)  # the one write is the merge
        self.assertNotIn("DELETE", log)  # the branch is cut through git (cut_branch), never by the merge call
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))
        self.assertFalse(self.lock_ref())

    def test_red_required_check_reverts_the_claim_and_merges_nothing(self):
        self.set(checks_seq=[[("checks", "fail", "https://x/y"), ("other", "pass", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("a check is red: checks: fail", out)
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertTrue(self.reverted())
        self.assertFalse(self.lock_ref())

    def test_a_red_check_that_is_not_required_still_stops_the_merge(self):
        self.set(checks_seq=[[("checks", "pass", ""), ("lint", "fail", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("a check is red: lint: fail", out)
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertTrue(self.reverted())

    @windows_slice
    def test_an_empty_required_list_is_refused(self):
        before = self.head()
        for kw, extra in (({"required": []}, {}), ({"required": "protection"}, {"contexts": []})):
            self.set(**extra)
            rc, out = self.go(**kw)
            self.assertEqual(rc, 1)
            self.assertEqual(self.head(), before)  # nothing was pushed
            self.assertFalse(self.lock_ref())
            self.assertIn("no required checks are named", out)
            self.assertNotIn(MERGE_CALL, self.calls())

    def test_one_red_entry_under_a_name_makes_the_name_red(self):
        self.set(checks_seq=[[("checks", "fail", ""), ("checks", "pass", "")]])  # a last-entry-wins map would pass
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("a check is red: checks: fail", out)
        self.assertNotIn(MERGE_CALL, self.calls())

    def test_a_name_is_green_only_when_every_entry_passed(self):
        self.set(checks_seq=[[("checks", "pending", ""), ("checks", "pass", "")]])  # pending then pass: never green
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("Still pending: checks", out)

    def test_a_lagging_head_is_waited_out_not_called_moved(self):
        self.set(lag={"n": 2, "prior": self.head()})
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertGreaterEqual(len(self.paused), 2)

    def test_a_head_that_never_leaves_the_prior_sha_stops_at_the_deadline(self):
        self.set(lag={"n": 1000, "prior": self.head()})
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("still shows the head before the push", out)
        self.assertNotIn(MERGE_CALL, self.calls())

    # Decision ci-wait-reads-run-status: block never runs `gh run watch`. It pauses 30 s, and the next pass of the wait loop reads.
    # The old spin guard ("a watch that returned at once pauses a full minute") went with the watch.
    def test_a_pending_run_pauses_30_seconds_and_returns(self):
        self.gh_host().block(["checks"], {"checks": [("pending", "https://x/actions/runs/5/job/1")]})
        self.assertEqual(self.paused, [30])  # one pause, and not host.minute (60 here)

    def test_a_pending_run_starts_no_gh_watch_and_makes_no_gh_call(self):
        self.gh_host().block(["checks", "lint"], {"checks": [("pending", "https://x/actions/runs/5/job/1")],
                                                  "lint": [("pending", "https://x/actions/runs/6/job/2")]})
        self.assertNotIn("run watch", self.calls())
        self.assertEqual(self.calls(), "")  # block only pauses; the wait loop reads the checks and the runs

    def test_dirty_in_the_wait_reverts_the_claim(self):
        self.set(checks_seq=[[("checks", "pending", "")], [("checks", "pass", "")]], dirty_after_checks=1)
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("went DIRTY", out)
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertTrue(self.reverted())

    def test_force_push_in_the_wait_reverts_nothing_and_merges_nothing(self):
        self.set(checks_seq=[[("checks", "pending", "")], [("checks", "pass", "")]])
        rival = []
        rc, out = self.go(pause=lambda: rival.append(self.competitor_push()))
        self.assertEqual(rc, 1)
        self.assertIn("head moved", out)
        self.assertEqual(self.head(), rival[0])  # the rival's head stands: no revert on top of it
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertFalse(self.lock_ref())

    def test_the_merge_sha_refuses_a_moved_head(self):
        old = self.head()
        self.competitor_push()
        commit, msg = self.gh_host().merge(7, "merge", old)
        self.assertIsNone(commit)
        self.assertIn("Head branch was modified", msg)
        self.assertIn(f"{MERGE_CALL} merge_method=merge sha={old}", self.calls())  # the sha is the head guard

    def test_protection_refusal_reverts_the_claim_and_prints_gh_whole(self):
        self.set(merge_fail=rest_err(405, 'Required status check "checks" is expected.'))
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("the merge was refused", out)
        self.assertIn('Required status check "checks" is expected.', out)
        self.assertNotIn("DELETE", self.calls())
        self.assertTrue(self.reverted())
        self.assertNotIn("merge #", sh(self.co, "git", "log", "origin/main", "--format=%s"))

    def test_protection_names_come_from_the_api_and_an_absent_one_stops_the_wait(self):  # c189: re-pointed from the deadline; the absent name ends the wait at once
        self.set(contexts=["checks", "needed"], checks_seq=[[("checks", "pass", "")]])
        rc, out = self.go(required="protection")
        self.assertEqual(rc, 1)
        self.assertIn("no run reports the required check needed", out)
        self.assertTrue(self.reverted())

    def test_no_protection_and_no_list_stops_with_the_remedy(self):
        before = self.head()
        self.set(contexts=None)
        rc, out = self.go(required="protection")
        self.assertEqual(rc, 1)
        self.assertIn("Set merge.requiredChecks to a list", out)
        self.assertEqual(self.head(), before)  # nothing was pushed
        self.assertTrue(self.reverted())  # still the pending record: no claim on the branch

    def test_head_red_pushes_no_claim(self):
        before = self.head()
        self.set(checks_seq=[[("checks", "fail", "https://x/y")]])
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("checks: fail", out)
        self.assertEqual(self.head(), before)
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertFalse(self.lock_ref())

    def test_head_pending_then_red_pushes_no_claim(self):
        before = self.head()
        self.set(checks_seq=[[("checks", "pending", "")], [("checks", "fail", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertEqual(self.head(), before)
        self.assertNotIn(MERGE_CALL, self.calls())

    def test_head_pending_then_green_claims_and_waits_again(self):
        self.set(checks_seq=[[("checks", "pending", "")], [("checks", "pass", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.claims("main"), 1)
        self.assertGreaterEqual(self.paused.count(60), 1)  # the head's own pending check was waited on

    def test_the_preview_names_the_head_state(self):
        for seq, want in (([("checks", "pass", "")], "head checks: green"), ([("checks", "pending", "")], "head checks: pending: checks"),
                          ([("checks", "fail", "")], "head checks: red: checks: fail")):
            self.set(checks_seq=[seq])
            rc, out = self.run_merge("7", host=self.gh_host())
            self.assertEqual(rc, 0, out)
            self.assertIn(want, out)

    def test_banchi_604_a_pending_check_that_is_not_required_goes_red_after_the_required_are_green(self):
        # The head reads green on `checks`, `design` still pending, then red. The wait must not end on the green required check.
        before = self.head()
        self.set(checks_seq=[[("checks", "pass", ""), ("design", "pending", "")], [("checks", "pass", ""), ("design", "fail", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("a check is red: design: fail", out)
        self.assertEqual(self.head(), before)  # stopped at the head wait: nothing claimed
        self.assertNotIn(MERGE_CALL, self.calls())

    def test_banchi_604_same_in_the_wait_after_the_claim_push(self):
        self.set(checks_seq=[[("checks", "pass", ""), ("design", "pass", "")], [("checks", "pass", ""), ("design", "pending", "")],
                             [("checks", "pass", ""), ("design", "fail", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("a check is red: design: fail", out)
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertTrue(self.reverted())

    def test_a_pending_check_that_is_not_required_is_waited_on_then_merges_on_green(self):
        self.set(checks_seq=[[("checks", "pass", ""), ("design", "pending", "")], [("checks", "pass", ""), ("design", "pass", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertGreaterEqual(self.paused.count(60), 1)
        self.assertIn(MERGE_CALL, self.calls())

    def test_skipped_and_neutral_count_as_passed(self):
        self.set(checks_seq=[[("checks", "pass", ""), ("a", "skipping", ""), ("b", "pass", "")]])  # skipped and neutral both land in the skipping bucket
        rc, out = self.go()
        self.assertEqual(rc, 0, out)

    def test_a_required_check_that_is_skipped_reads_green(self):
        # B skips whole jobs on a docs-only PR. A skipped required check is not red, not pending, and the run judge agrees.
        red, pending, _ = merge.Host.classify({"checks": [("pass", "")], "checks-windows": [("skipping", "")]}, ["checks", "checks-windows"])
        self.assertEqual((red, pending), ([], []))
        runs = [{"name": "checks", "status": "completed", "conclusion": c} for c in ("success", "skipped", "neutral")]
        self.assertEqual(merge.Host.judge_runs(runs), ([], []))
        self.set(checks_seq=[[("checks", "skipping", ""), ("scope", "pass", "")]])  # a required check skipped beside a passing check reads green
        rc, out = self.go()
        self.assertEqual(rc, 0, out)

    def test_a_head_where_no_check_ran_is_unproven_not_green(self):
        # Every check skipped: the synchronize run skipped as a draft.
        red, pending, _ = merge.Host.classify({"checks": [("skipping", "")], "checks-windows": [("skipping", "")]}, ["checks", "checks-windows"])
        self.assertEqual(pending, [])
        self.assertTrue(any("no check ran on this head" in r for r in red), red)
        self.assertTrue(any("gh workflow run checks.yml --ref" in r for r in red), red)
        self.assertTrue(any("gh pr ready" in r for r in red), red)

    def test_a_docs_only_head_whose_scope_check_passed_is_not_unproven(self):
        red, pending, _ = merge.Host.classify({"scope": [("pass", "")], "checks": [("skipping", "")], "checks-windows": [("skipping", "")]}, ["checks", "checks-windows"])
        self.assertEqual((red, pending), ([], []))

    def test_a_run_list_where_every_run_skipped_and_none_pending_is_red(self):
        red, pending = merge.Host.judge_runs([{"name": "checks", "status": "completed", "conclusion": "skipped"}])
        self.assertEqual(red, ["workflow checks: skipped, no job ran"])
        self.assertEqual(pending, [])

    def test_a_success_run_and_a_skipped_run_on_the_same_head_are_green(self):
        runs = [{"name": "checks", "status": "completed", "conclusion": "success"}, {"name": "checks-windows", "status": "completed", "conclusion": "skipped"}]
        self.assertEqual(merge.Host.judge_runs(runs), ([], []))

    def test_an_older_cancelled_run_under_a_newer_success_of_the_same_name_is_superseded(self):
        # gh lists the newest run first. Only the newest run per workflow name counts.
        runs = [{"name": "checks", "status": "completed", "conclusion": "success"}, {"name": "checks", "status": "completed", "conclusion": "cancelled"}]
        self.assertEqual(merge.Host.judge_runs(runs), ([], []))

    def test_a_cancelled_run_beside_a_success_of_its_name_is_superseded(self):
        # On one head, a run of a name that ran outranks a cancelled run of that name.
        runs = [{"name": "checks", "status": "completed", "conclusion": "cancelled"}, {"name": "checks", "status": "completed", "conclusion": "success"}]
        self.assertEqual(merge.Host.judge_runs(runs), ([], []))

    def test_a_cancelled_run_with_no_newer_run_of_its_name_is_red(self):
        runs = [{"name": "checks", "status": "completed", "conclusion": "success"}, {"name": "ci", "status": "completed", "conclusion": "cancelled"}]
        red, pending = merge.Host.judge_runs(runs)
        self.assertEqual(red, ["workflow ci: cancelled"])
        self.assertEqual(pending, [])

    # Two checks runs start on one head in the same second. GitHub cancels one (concurrency).
    # judge_runs must read the live twin, not the cancelled one, whatever the list order.
    def test_a_cancelled_twin_beside_a_run_of_its_name_is_judged_by_the_run_that_ran_in_either_order(self):
        # Rows, one outcome each: a live twin waits; a succeeded twin is green (a run that ran outranks a cancelled run of its name);
        # a failed twin is red on the failure. Either order.
        cancelled = {"name": "checks", "status": "completed", "conclusion": "cancelled"}
        rows = (
            ("live", {"name": "checks", "status": "in_progress", "conclusion": ""}, ([], ["workflow checks"])),
            ("succeeded", {"name": "checks", "status": "completed", "conclusion": "success"}, ([], [])),
            ("failed", {"name": "checks", "status": "completed", "conclusion": "failure"}, (["workflow checks: failure"], [])),
        )
        for twin, other, want in rows:
            for order, runs in (("cancelled first", [cancelled, other]), ("twin first", [other, cancelled])):
                with self.subTest(twin=twin, order=order):
                    self.assertEqual(merge.Host.judge_runs(runs), want)

    def test_a_newer_skipped_run_does_not_outrank_hide_or_erase_an_older_run_of_its_name(self):
        # A draft PR marked ready in the same second. The skipped `opened` run is
        # newer than the green `ready_for_review` run of the same workflow. A skip never outranks a run that ran.
        # Rows: the older run is a success, in progress, cancelled, or failed. Each row is one pure judge_runs input.
        skipped = {"name": "checks", "status": "completed", "conclusion": "skipped"}
        rows = (
            ("success", {"name": "checks", "status": "completed", "conclusion": "success"}, ([], [])),
            ("in progress", {"name": "checks", "status": "in_progress", "conclusion": ""}, ([], ["workflow checks"])),
            ("cancelled", {"name": "checks", "status": "completed", "conclusion": "cancelled"}, (["workflow checks: cancelled"], [])),
            ("failure", {"name": "checks", "status": "completed", "conclusion": "failure"}, (["workflow checks: failure"], [])),
        )
        for older, run, want in rows:
            with self.subTest(older=older):
                self.assertEqual(merge.Host.judge_runs([skipped, run]), want)

    def test_a_head_where_every_check_skipped_is_refused_with_the_remedy(self):
        before = self.head()
        self.set(checks_seq=[[("checks", "skipping", "")]], runs_seq=[[("checks", "completed", "skipped")]])
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertIn("no check ran on this head", out)
        self.assertIn("gh workflow run checks.yml --ref", out)
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertEqual(self.head(), before)

    def test_a_newer_skipped_run_on_the_wait_path_does_not_refuse_an_older_success(self):
        # The same race through run_state. Checks pass; the runs are skipped then success.
        before = self.head()
        self.set(checks_seq=[[("checks", "pass", "")]], runs_seq=[[("checks", "completed", "skipped"), ("checks", "completed", "success")]])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertIn(MERGE_CALL, self.calls())
        self.assertNotEqual(self.head(), before)

    def test_a_missing_required_check_beside_a_skipped_one_is_pending_not_red(self):
        # B1: nothing has reported checks yet. The skipped checks-windows row is not proof that no check ran.
        red, pending, _ = merge.Host.classify({"checks-windows": [("skipping", "")]}, ["checks", "checks-windows"])
        self.assertEqual((red, pending), ([], ["checks"]))

    def test_a_skipped_head_with_a_run_in_progress_waits_for_the_run(self):
        # B1: the skipped rows are old. The checks run is still in progress with no job rows, so the wait holds.
        self.set(checks_seq=[[("checks", "skipping", "")]], runs_seq=[[("checks", "in_progress", "")], [("checks", "completed", "skipped")]])
        rc, out = self.go()
        self.assertGreaterEqual(self.paused.count(60), 1, out)
        self.assertEqual(rc, 1, out)
        self.assertIn("no check ran on this head", out)
        self.assertNotIn(MERGE_CALL, self.calls())

    def test_the_remedy_run_in_progress_beside_old_skipped_rows_waits(self):
        # B1: the remedy's own run. Old skipped rows and a run in progress hold the wait, then the pass lets it merge.
        self.set(checks_seq=[[("checks", "skipping", "")], [("checks", "pass", "")]], runs_seq=[[("checks", "in_progress", "")], [("checks", "completed", "success")]])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertGreaterEqual(self.paused.count(60), 1, out)

    def test_an_older_run_still_in_progress_holds_the_wait_under_a_newer_success(self):
        # B2: gh lists the newest run first. The older in-progress run is read as pending before the dedup.
        runs = [{"name": "checks", "status": "completed", "conclusion": "success"}, {"name": "checks", "status": "in_progress", "conclusion": ""}]
        self.assertEqual(merge.Host.judge_runs(runs), ([], ["workflow checks"]))

    def test_the_no_check_ran_remedy_names_the_real_branch(self):
        self.set(checks_seq=[[("checks", "skipping", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertIn("gh workflow run checks.yml --ref feat", out)
        self.assertNotIn("<branch>", out)

    def test_cancelled_and_unknown_buckets_stop_the_run(self):
        for conclusion, bucket in (("cancelled", "cancel"), ("startup_failure", "fail")):  # the conclusion GitHub names, and the bucket it lands in
            self.set(checks_seq=[[("checks", "pass", ""), ("x", conclusion, "")]])
            rc, out = self.go()
            self.assertEqual(rc, 1, bucket)
            self.assertIn(f"x: {bucket}", out)
        self.assertNotIn(MERGE_CALL, self.calls())

    def test_an_ignore_entry_without_a_reason_refuses_the_config(self):
        for bad in ({"name": "design"}, {"name": "design", "reason": "  "}, {"reason": "r"}):
            cfg = dict(CONFIG, merge=dict(CONFIG["merge"], ignoreChecks=[bad]))
            put_base_config(self, json.dumps(cfg))
            rc, out = self.run_merge("7", "--confirm")
            self.assertEqual(rc, 1)
            self.assertIn("merge.ignoreChecks", out)
            self.assertFalse(self.lock_ref())

    def test_an_ignored_red_check_is_reported_and_the_merge_goes_on(self):
        self.set(checks_seq=[[("checks", "pass", ""), ("design", "fail", ""), ("slow", "pending", "")]])
        rc, out = self.go(ignore={"design": "flaky upstream", "slow": "nightly"})
        self.assertEqual(rc, 0, out)
        self.assertIn("design (flaky upstream): fail", out)
        self.assertIn(MERGE_CALL, self.calls())

    def test_the_preview_lists_a_pending_check_that_is_not_required(self):
        self.set(checks_seq=[[("checks", "pass", ""), ("design", "pending", "")]])
        rc, out = self.run_merge("7", host=self.gh_host())
        self.assertIn("head checks: pending: design", out)

    def test_a_required_check_is_never_ignored(self):
        before = self.head()
        rc, out = self.go(ignore={"checks": "flaky"})
        self.assertEqual(rc, 1)
        self.assertIn("A required check is never ignored", out)
        self.assertEqual(self.head(), before)
        self.assertNotIn(MERGE_CALL, self.calls())

    def test_classify_keeps_an_absent_required_name_pending_even_when_ignored(self):
        red, pending, _ = merge.Host.classify({"a": [("pass", "")]}, ["a", "b"], {"b": "x"})
        self.assertEqual(pending, ["b"])

    def test_classify_drops_a_cancelled_duplicate_beside_a_pass_in_either_order(self):
        names = [f"job{i}" for i in range(13)]
        got = {k: ([("cancel", "l1"), ("pass", "l2")] if i % 2 else [("pass", "l2"), ("cancel", "l1")]) for i, k in enumerate(names)}
        red, pending, _ = merge.Host.classify(got, names)
        self.assertEqual((red, pending), ([], []))

    def test_classify_reads_a_cancel_beside_pending_as_pending_not_red(self):
        red, pending, _ = merge.Host.classify({"a": [("cancel", ""), ("pending", "")]}, ["a"])
        self.assertEqual((red, pending), ([], ["a"]))

    def test_classify_keeps_a_cancel_only_name_red(self):
        red, _, _ = merge.Host.classify({"a": [("cancel", "l")]}, ["a"])
        self.assertEqual(red, ["a: cancel l"])

    def test_classify_keeps_a_cancel_beside_only_a_skip_red(self):
        red, _, _ = merge.Host.classify({"a": [("skipping", ""), ("cancel", "l")], "b": [("pass", "")]}, [])
        self.assertEqual(red, ["a: cancel l"])

    def test_classify_never_drops_a_fail_or_timeout_beside_a_cancel(self):
        t = "timed out at its 50-minute cap; re-cap or split"
        got = {"a": [("cancel", ""), ("pass", ""), ("fail", "x")], "b": [("cancel", ""), ("pass", ""), (t, "")]}
        red, _, _ = merge.Host.classify(got, ["a", "b"])
        self.assertIn("a: fail x", red)
        self.assertIn(f"b: {t}", red)
        self.assertFalse([e for e in red if "cancel" in e], red)

    def test_a_workflow_run_in_progress_holds_the_wait_though_no_job_is_listed(self):
        self.set(runs_seq=[[("ci", "in_progress", "")], [("ci", "completed", "success")]])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertGreaterEqual(self.paused.count(60), 1)

    def test_a_failed_workflow_run_stops_the_run_and_an_ignored_one_does_not(self):
        before = self.head()
        self.set(runs_seq=[[("ci", "completed", "failure")]])
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("workflow ci: failure", out)
        self.assertEqual(self.head(), before)
        rc, out = self.go(ignore={"ci": "known"})
        self.assertEqual(rc, 0, out)

    def test_a_check_that_appears_on_the_settle_reread_holds_the_wait(self):
        before = self.head()
        self.set(checks_seq=[[("checks", "pass", "")], [("checks", "pass", ""), ("late", "fail", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("late: fail", out)
        self.assertIn(merge.SETTLE_SECONDS, self.paused)
        self.assertEqual(self.head(), before)  # stopped at the head wait: nothing claimed

    def test_a_failed_read_in_the_wait_reverts_the_claim(self):
        before = self.head()
        self.set(checks_broken=True, broken_from=2)  # the head and its settle read fine, the wait after the claim push does not
        self.set(checks_seq=[[("checks", "pass", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"checks?\b[^\n]*\bfailed")
        self.assertNotEqual(self.head(), before)  # the claim was pushed, then reverted
        self.assertTrue(self.reverted())
        self.assertFalse(self.lock_ref())

    # ---- no .github/stamp.json: the defaults

    def test_no_config_preview_uses_the_defaults_and_names_the_file_once(self):
        drop_config(self)
        rc, out = self.run_merge("7", host=self.gh_host())
        self.assertEqual(rc, 0, out)
        self.assertRegex(out, r"merge_method=merge|--merge\b")  # method "merge"
        self.assertIn("run 0 afterMerge command(s)", out)  # afterMerge empty
        named = [l for l in out.splitlines() if ".github/stamp.json" in l]
        self.assertEqual(len(named), 1, out)
        self.assertIn("default", named[0].lower())
        self.assertIn(REPO_CALL, self.calls())  # defaultBranch from the host

    def test_no_config_takes_the_default_branch_from_the_host(self):
        drop_config(self)
        self.set(default_branch="trunk")
        rc, out = self.run_merge("7", host=self.gh_host())
        self.assertIn("is not the default branch (trunk)", out)

    def test_no_config_merges_on_the_defaults_and_claims_nothing(self):
        drop_config(self)
        self.set(contexts=["checks"])
        self.host = None  # main builds the real Host from the defaults: requiredChecks "protection"
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        log = self.calls()
        self.assertIn("branches/main/protection/required_status_checks", log)
        self.assertIn(MERGE_CALL + " merge_method=merge sha=", log)
        self.assertEqual(self.claims(), 0)
        self.assertIn("id: pending", self.show("main", "docs/decisions/second.md"))
        named = [l for l in out.splitlines() if ".github/stamp.json" in l]
        self.assertEqual(len(named), 1, out)
        self.assertIn("default", named[0].lower())

    def test_no_config_waits_the_default_45_minutes(self):
        drop_config(self)
        self.set(contexts=["checks"], checks_seq=[[("checks", "pending", "")]])
        rc, out = self.go(required="protection", minute=900)  # a poll every 15 minutes of the fake clock: 3 reads reach the deadline, not 45 (each read is a few process starts)
        self.assertEqual(rc, 1)
        self.assertIn("the deadline of 45 minutes passed", out)
        self.assertNotIn(MERGE_CALL, self.calls())

    def test_no_config_never_runs_stamp(self):
        drop_config(self)
        mark = stamp_marker(self)
        self.set(contexts=["checks"])
        rc, out = self.go(required="protection")
        self.assertEqual(rc, 0, out)
        self.assertFalse(os.path.exists(mark), "stamp.mjs ran with no config")
        self.assertEqual(self.claims(), 0)

    def test_no_config_and_no_protection_stops_with_the_remedy(self):
        drop_config(self)
        before = self.head()
        for contexts, remedy in ((None, "Set merge.requiredChecks to a list"), ([], "no required checks are named")):
            self.set(contexts=contexts)
            rc, out = self.go(required="protection")
            self.assertEqual(rc, 1, out)
            self.assertIn(remedy, out)
            self.assertEqual(self.head(), before)  # nothing was pushed
            self.assertNotIn(MERGE_CALL, self.calls())

    def test_a_partial_merge_block_takes_the_defaults_for_the_missing_fields(self):
        put_base_config(self, json.dumps({"defaultBranch": "main", "merge": {"method": "squash"}}))
        self.set(contexts=["checks"])
        self.host = None  # main builds the Host from the filled defaults: requiredChecks "protection"
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        log = self.calls()
        self.assertIn(MERGE_CALL + " merge_method=squash sha=", log)  # method from the file
        self.assertIn("branches/main/protection/required_status_checks", log)  # requiredChecks default
        filled = [l for l in out.splitlines() if all(f in l for f in ("deadlineMinutes", "requiredChecks", "afterMerge"))]
        self.assertEqual(len(filled), 1, out)  # one line names the fields it filled
        self.assertNotIn("method", filled[0])  # the file's own field is not filled

    def test_a_config_without_defaultBranch_reads_it_from_the_host(self):
        put_base_config(self, json.dumps({"merge": dict(CONFIG["merge"])}))
        self.set(default_branch="trunk")
        rc, out = self.run_merge("7", host=self.gh_host())
        self.assertEqual(rc, 0, out)
        self.assertIn(REPO_CALL, self.calls())
        self.assertIn("main is not the default branch (trunk)", out)

    def assert_draft_refused(self, rc, out, before):
        self.assertEqual(rc, 1, out)
        lines = [l for l in out.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1, out)
        self.assertTrue(lines[0].startswith("merge:"), out)
        self.assertIn("draft", lines[0])
        self.assertEqual(self.refs(), before)  # no claim pushed
        self.assertEqual(self.ticks, 0, "waited on a draft")
        self.assertNotIn(CHECKS_CALL, self.calls())
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertNotIn("Traceback", out)

    def test_a_draft_pr_previews_with_the_undo_check_and_claims_nothing_or_waits(self):
        self.set(draft=True)
        before = self.refs()
        real, seen = merge.undo_check, []
        def spy(wt, base_ref, unknown_ok="", pr_body=""):
            seen.append((base_ref, sh(wt, "git", "rev-parse", "HEAD")))  # the check runs on the PR head's worktree
            return real(wt, base_ref, unknown_ok, pr_body)
        with unittest.mock.patch.object(merge, "undo_check", spy):
            rc, out = self.run_merge("7", host=self.gh_host())
        self.assertEqual(rc, 0, out)
        self.assertIn("draft", out.lower())
        self.assertEqual(seen, [("origin/main", self.head("feat"))])
        self.assertEqual(self.refs(), before)  # no claim pushed
        self.assertEqual(self.ticks, 0, "waited on a draft")
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertNotIn("Traceback", out)

    def test_a_pr_that_turns_draft_after_the_preview_read_is_refused_at_confirm(self):  # guard: merge.py checks draft under the lock
        put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], requiredChecks=["checks"]))))  # complete: no defaults notice in the output
        self.set(draft_when_locked=True)  # main's read at the top of --confirm sees a ready PR; confirm's read under the lock sees a draft
        before = self.refs()
        rc, out = self.run_merge("7", "--confirm", host=self.gh_host())
        self.assert_draft_refused(rc, out, before)

    def test_a_draft_pr_is_refused_at_confirm_before_any_claim_or_wait(self):
        self.set(draft=True)
        before = self.refs()
        rc, out = self.run_merge("7", "--confirm", host=self.gh_host())
        self.assert_draft_refused(rc, out, before)

class RestRoutes(Env):
    """c53: the merge tool reads and merges through the REST API (`gh api`), never GraphQL, which a Claude Code cloud session answers with HTTP 403
    (the fake gh answers it that way, and a GraphQL call that reaches it fails the test). Each case pins one way a REST read could count a pending or
    red check as green, drop a check or a pull request, or merge a head nobody read. The fake behaves as gh does: a list read gives one page unless
    --paginate is given, object pages come back to back, and fields without -X make a POST. Not a GhHalf subclass: the GhHalf tests must not run twice."""
    set, calls, gh_host, go, gh_state, reverted = GhHalf.set, GhHalf.calls, GhHalf.gh_host, GhHalf.go, GhHalf.gh_state, GhHalf.reverted

    def setUp(self):
        super().setUp()
        install_gh_shim(self)
        self.ticks, self.paused, self.at_pause = 0, [], []
        self.set(checks_seq=[[("checks", "pass", "")]])

    # ---- the checks of a head are the check runs AND the commit statuses

    def test_one_green_check_run_and_one_pending_status_is_not_green(self):
        self.set(checks_seq=[[("checks", "pass", ""), ("deploy", "pending", "https://x/s", "status")]], runs_seq=[[("checks", "completed", "success")]])
        verdict, detail = self.gh_host().head_read(7)
        self.assertEqual(verdict, "pending", detail)
        self.assertIn("deploy", detail)
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertIn("Still pending: deploy", out)
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertFalse(self.lock_ref())

    def test_a_failed_or_errored_status_is_red(self):
        for bucket in ("fail", "error"):  # the status states failure and error
            with self.subTest(status=bucket):
                self.set(checks_seq=[[("checks", "pass", ""), ("deploy", bucket, "https://x/s", "status")]])
                verdict, detail = self.gh_host().head_read(7)
                self.assertEqual(verdict, "red", detail)
                self.assertIn("deploy", detail)
                rc, out = self.go()
                self.assertEqual(rc, 1, out)
                self.assertIn("a check is red: deploy: fail", out)
        self.assertNotIn(MERGE_CALL, self.calls())

    def test_a_required_check_that_exists_only_as_a_status_is_found(self):
        self.set(checks_seq=[[("legacy-ci", "pass", "https://x/s", "status")]])
        rc, out = self.go(required=("legacy-ci",))
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Still pending", out)
        self.assertIn(MERGE_CALL, self.calls())

    def test_no_statuses_and_a_pending_combined_state_is_green_when_the_check_runs_are_green(self):
        sha = self.head()
        c, out = self.gh_host().gh(["api", f"repos/{{owner}}/{{repo}}/commits/{sha}/status", "-X", "GET"])
        self.assertEqual(c, 0, out)
        self.assertEqual((json.loads(out)["state"], json.loads(out)["statuses"]), ("pending", []))  # GitHub's own answer for a commit with no statuses
        self.assertEqual(self.gh_host().checks(7, warn=False), {"checks": [("pass", "")]})  # the combined state adds no pending entry
        self.set(runs_seq=[[("checks", "completed", "success")]])
        self.assertEqual(self.gh_host().head_read(7), ("green", ""))
        rc, out = self.go()
        self.assertEqual(rc, 0, out)

    def test_the_checks_are_read_at_the_head_the_pull_request_shows(self):
        head = self.head()
        self.gh_host().head_read(7)
        calls = self.calls()
        self.assertIn(f"GET commits/{head}/check-runs", calls)
        self.assertIn(f"GET commits/{head}/status", calls)

    # ---- a list read takes every page

    def test_two_pages_of_check_runs_with_the_red_one_on_page_two_is_red(self):
        self.set(page_cap=2, checks_seq=[[("lint", "pass", ""), ("checks", "pass", ""), ("e2e", "fail", "https://x/e2e")]])
        self.assertEqual(sorted(self.gh_host().checks(7, warn=False)), ["checks", "e2e", "lint"])
        verdict, detail = self.gh_host().head_read(7)
        self.assertEqual(verdict, "red", detail)
        self.assertIn("e2e", detail)
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertIn("a check is red: e2e: fail", out)
        self.assertNotIn(MERGE_CALL, self.calls())

    def test_two_pages_of_commit_statuses_with_the_red_one_on_page_two_is_red(self):
        self.set(page_cap=2, checks_seq=[[("checks", "pass", ""), ("a", "pass", "u", "status"), ("b", "pass", "u", "status"), ("c", "fail", "u", "status")]])
        self.assertEqual(sorted(self.gh_host().checks(7, warn=False)), ["a", "b", "c", "checks"])
        verdict, detail = self.gh_host().head_read(7)
        self.assertEqual(verdict, "red", detail)
        self.assertIn("c", detail)
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertNotIn(MERGE_CALL, self.calls())

    def test_two_pages_of_open_pull_requests_with_the_head_on_page_two_is_found(self):
        lane = "c" * 40
        self.set(page_cap=2, open_prs=[["one", "a" * 40, "main"], ["two", "b" * 40, "main"], ["lane", lane, "main"]])
        self.assertEqual(self.gh_host().open_heads(), {"one": ("a" * 40, "main"), "two": ("b" * 40, "main"), "lane": (lane, "main")})

    def test_open_heads_reads_every_page_of_more_than_a_hundred_open_pull_requests(self):
        self.set(open_prs=[[f"b{i}", f"{i:040x}", "main"] for i in range(250)])
        self.assertEqual(len(self.gh_host().open_heads()), 250)

    # ---- every conclusion and state lands in one bucket

    RUN_BUCKETS = [("completed", "success", "pass"), ("completed", "neutral", "skipping"), ("completed", "skipped", "skipping"),
                   ("completed", "cancelled", "cancel"), ("completed", "failure", "fail"), ("completed", "timed_out", "fail"),
                   ("completed", "action_required", "fail"), ("completed", "startup_failure", "fail"), ("completed", "stale", "fail"),
                   ("completed", "a_conclusion_github_adds_later", "fail"), ("completed", None, "fail"),
                   ("queued", None, "pending"), ("in_progress", None, "pending"), ("waiting", None, "pending"), ("queued", "failure", "pending")]
    STATUS_BUCKETS = [("success", "pass"), ("pending", "pending"), ("failure", "fail"), ("error", "fail"), ("a_state_github_adds_later", "fail")]

    def test_each_check_run_conclusion_and_status_state_maps_to_its_bucket(self):
        runs = [{"id": i, "name": f"run {s}/{c}", "status": s, "conclusion": c, "details_url": f"https://x/run/{i}", "started_at": None, "completed_at": None}
                for i, (s, c, _) in enumerate(self.RUN_BUCKETS)]
        runs.append({"id": 90, "name": "run with no link", "status": "completed", "conclusion": "success", "details_url": None, "started_at": None, "completed_at": None})
        statuses = [{"id": 50 + i, "context": f"status {st}", "state": st, "target_url": f"https://x/status/{i}", "description": ""} for i, (st, _) in enumerate(self.STATUS_BUCKETS)]
        statuses.append({"id": 99, "context": "status with no link", "state": "success", "target_url": None, "description": ""})
        self.set(raw_checks=[{"check_runs": runs, "statuses": statuses}])
        got = self.gh_host().checks(7, warn=False)
        want = {r["name"]: [(b, r["details_url"])] for r, (_, _, b) in zip(runs, self.RUN_BUCKETS)}
        want.update({s["context"]: [(b, s["target_url"])] for s, (_, b) in zip(statuses, self.STATUS_BUCKETS)})
        want.update({"run with no link": [("pass", "")], "status with no link": [("pass", "")]})
        for name, rows in want.items():
            with self.subTest(check=name):
                self.assertEqual(got.get(name), rows)
        self.assertEqual(sorted(got), sorted(want))

    PR_FIELDS = [({"state": "open"}, {"state": "OPEN"}),
                 ({"state": "closed", "merged": False}, {"state": "CLOSED"}),
                 ({"state": "closed", "merged": True}, {"state": "MERGED"}),
                 ({"mergeable": True, "mergeable_state": "clean"}, {"mergeable": "MERGEABLE", "merge_state": "CLEAN"}),
                 ({"mergeable": False, "mergeable_state": "dirty"}, {"mergeable": "CONFLICTING", "merge_state": "DIRTY"}),
                 ({"mergeable": None, "mergeable_state": "unknown"}, {"mergeable": "UNKNOWN", "merge_state": "UNKNOWN"}),
                 ({"mergeable": None, "mergeable_state": None}, {"mergeable": "UNKNOWN", "merge_state": "UNKNOWN"}),
                 ({"mergeable_state": "blocked"}, {"merge_state": "BLOCKED"}), ({"mergeable_state": "behind"}, {"merge_state": "BEHIND"}),
                 ({"mergeable_state": "unstable"}, {"merge_state": "UNSTABLE"}), ({"mergeable_state": "has_hooks"}, {"merge_state": "HAS_HOOKS"}),
                 ({"mergeable_state": "draft"}, {"merge_state": "DRAFT"}),
                 ({"draft": True}, {"draft": True}), ({"draft": False}, {"draft": False}),
                 ({"body": None}, {"body": ""}), ({"body": "Drops-lines: a -- b"}, {"body": "Drops-lines: a -- b"})]

    def test_pull_request_fields_map_to_the_values_the_tool_reads(self):
        head = self.head()
        for raw, want in self.PR_FIELDS:
            with self.subTest(raw=raw):
                self.set(pr_raw=raw)
                info = self.gh_host().pr(7)
                for key, value in want.items():
                    self.assertEqual(info[key], value, info)
                self.assertEqual((info["head"], info["branch"], info["base"]), (head, "feat", "main"))

    # ---- the merge: the head guard, and what counts as merged

    def test_a_head_that_moves_between_the_last_read_and_the_merge_is_refused_and_nothing_merges(self):
        self.set(rival_at_merge=True)  # a push lands after the wait's last read and before the merge call
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.calls().count(MERGE_CALL), 1, out)  # GitHub answered 409: a refusal is not retried
        sent = re.search(r"sha=([0-9a-f]{40})", self.calls()).group(1)
        self.assertNotEqual(sent, self.head(), "the rival's push must have moved the head after the sha was fixed")
        self.assertIn("Head branch was modified", out)
        self.assertIn("the merge was refused", out)
        self.assertIn("Nothing reverted", out)  # the head is not the claim any more: the revert path runs and leaves the rival's work
        self.assertIsNone(self.gh_state("oid"), "the merge landed on a head nobody read")
        self.assertFalse(self.lock_ref())

    def test_a_merge_sends_the_method_and_the_head_it_was_given(self):
        head = self.head()
        self.set(merge_fail=NOT_MERGEABLE)
        for method in ("merge", "squash", "rebase"):
            with self.subTest(method=method):
                commit, msg = self.gh_host().merge(7, method, head)
                self.assertIsNone(commit)
                self.assertIn("Pull Request is not mergeable", msg)
                self.assertIn(f"{MERGE_CALL} merge_method={method} sha={head}", self.calls())

    def test_a_merge_that_lands_returns_the_merge_commit_of_the_pull_request(self):
        head = self.head()
        commit, msg = self.gh_host().merge(7, "merge", head)
        self.assertEqual((commit, msg), (self.gh_state("oid"), ""))
        self.assertEqual(commit, sh(self.co, "git", "ls-remote", "origin", "refs/heads/main").split("\t")[0])
        self.assertIn(STATE_READ, self.calls())

    def test_a_merge_reply_with_no_merge_behind_it_is_not_a_merge(self):
        # An OPEN pull request carries a merge_commit_sha on REST too (GitHub's test merge), and a lost or untrue reply can say merged. Only
        # merged: true at the head that was sent counts.
        untrue = json.dumps({"sha": "f" * 40, "merged": True, "message": "Pull Request successfully merged"})
        for reply in ("", untrue):
            with self.subTest(reply=reply[:24]):
                self.set(merge_replies=[[reply, False, 0]])  # exit 0, nothing landed
                with self.assertRaises(merge.NetStop):
                    self.gh_host().merge(7, "merge", self.head())
                self.assertIn(STATE_READ, self.calls())

    # ---- the merge state: the old `gh pr merge` (no --admin) refused a BLOCKED or BEHIND pull request itself; the REST PUT does not,
    # and a token that may bypass branch protection merges it. Host.merge reads the pull request right before the PUT.

    def clear_calls(self):
        pathlib.Path(self.state, "calls.log").unlink(missing_ok=True)

    def test_a_merge_of_a_blocked_or_behind_pull_request_sends_no_put_and_is_a_refusal(self):
        head = self.head()
        for state in ("blocked", "behind"):
            with self.subTest(state=state):
                self.clear_calls()
                self.set(pr_raw={"mergeable_state": state})
                commit, msg = self.gh_host().merge(7, "merge", head)
                self.assertIsNone(commit)  # a proven refusal: confirm reverts the claim on it
                self.assertRegex(msg, "(?i)" + state)  # the message names the state
                self.assertIn("GET pulls/7", self.calls())  # it was read, not assumed
                self.assertNotIn(MERGE_CALL, self.calls())
        self.assertIsNone(self.gh_state("oid"))

    def merged_in_state(self, state):
        head = self.head()
        self.set(pr_raw={"mergeable_state": state})
        commit, msg = self.gh_host().merge(7, "merge", head)
        self.assertEqual((commit, msg), (self.gh_state("oid"), ""))
        lines = self.calls().splitlines()
        puts = [i for i, line in enumerate(lines) if line.startswith(MERGE_CALL)]
        self.assertEqual(len(puts), 1, lines)
        self.assertIn("GET pulls/7", lines[:puts[0]])  # the pull request is read before the call, not taken from an earlier read

    def test_a_merge_of_a_clean_pull_request_reads_it_and_then_sends_the_put(self):
        self.merged_in_state("clean")

    def test_a_merge_of_an_unstable_pull_request_reads_it_and_then_sends_the_put(self):
        self.merged_in_state("unstable")  # a failing check that is not required: the old gh merged it too

    def refused_under_the_lock(self, state):
        self.set(merge_state_when_locked=state)  # the preview read says clean; every read after the lock is taken says `state`
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertIn("the merge was refused", out)
        self.assertRegex(out, "(?i)" + state)
        self.assertNotIn(MERGE_CALL, self.calls())
        self.assertTrue(self.reverted())
        self.assertFalse(self.lock_ref())
        self.assertIsNone(self.gh_state("oid"))
        self.assertNotIn("merge #", sh(self.co, "git", "log", "origin/main", "--format=%s"))

    def test_a_pull_request_that_turns_blocked_after_the_preview_is_refused_and_the_claim_reverted(self):
        self.refused_under_the_lock("blocked")

    def test_a_pull_request_that_turns_behind_after_the_preview_is_refused_and_the_claim_reverted(self):
        self.refused_under_the_lock("behind")

    def test_a_pull_request_that_turns_unstable_after_the_preview_is_still_merged(self):
        self.set(merge_state_when_locked="unstable")
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertIn(MERGE_CALL, self.calls())

    # ---- mergeable is null while GitHub works it out

    def test_a_pull_request_whose_mergeable_is_null_is_read_again_until_it_answers(self):
        self.set(mergeable_seq=[None, None, True])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertGreaterEqual(self.calls().count("GET pulls/7\n"), 3, self.calls())
        self.assertIn(MERGE_CALL, self.calls())

    def test_a_null_mergeable_that_then_reads_conflicting_stops_the_merge(self):
        self.set(mergeable_seq=[None, None, False])
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertRegex(out, r"DIRTY|CONFLICTING")
        self.assertNotIn(MERGE_CALL, self.calls())

    # ---- the selector: a number, a URL, a branch name, or the current branch

    def two_open_prs(self):
        self.set(pr_number=41, open_prs=[["other", "d" * 40, "main", 40], ["feat", self.head(), "main", 41]])

    def test_a_pr_number_or_url_is_the_route_number_and_reads_no_list(self):
        for selector in (7, "7", "https://github.com/o/r/pull/7"):
            with self.subTest(selector=selector):
                info = self.gh_host().pr(selector)
                self.assertEqual((info["head"], info["branch"], info["base"]), (self.head(), "feat", "main"))
        self.assertIn("GET pulls/7", self.calls())
        self.assertNotIn(LIST_CALL, self.calls())

    def test_a_pull_request_url_routes_every_call_to_the_repo_in_the_url(self):
        # A host with no repo and no -R reads the repo of the working directory. A URL names its own repo, so every call it makes goes there.
        url = "https://github.com/acme/widgets/pull/7"
        for name, read, least in (("pr", lambda h: h.pr(url), 1), ("head_read", lambda h: h.head_read(url), 3)):
            with self.subTest(read=name):
                pathlib.Path(self.state, "repos.log").unlink(missing_ok=True)
                read(merge.Host(["checks"], "main", minute=60, now=lambda: self.now, pause=lambda s: None))
                used = pathlib.Path(self.state, "repos.log").read_text().split()
                self.assertGreaterEqual(len(used), least, used)
                self.assertEqual(set(used), {"acme/widgets"})

    def test_a_branch_name_resolves_through_the_open_pull_request_list(self):
        self.two_open_prs()
        info = self.gh_host().pr("feat")
        self.assertEqual((info["head"], info["branch"]), (self.head(), "feat"))
        calls = self.calls()
        self.assertIn(LIST_CALL, calls)
        self.assertIn("GET pulls/41", calls)
        self.assertNotIn("GET pulls/7", calls)

    def test_an_empty_selector_is_the_pull_request_of_the_current_branch(self):
        self.two_open_prs()
        cur = os.path.join(self.t, "cur")
        sh(self.t, "git", "clone", "-q", self.bare, cur)
        sh(cur, "git", "checkout", "-q", "feat")
        host = merge.Host(["checks"], "main", minute=60, now=lambda: self.now, pause=lambda s: None, cwd=cur)
        for selector in ("", None):
            with self.subTest(selector=selector):
                info = host.pr(selector)
                self.assertEqual((info["branch"], info["head"]), ("feat", self.head()))
        self.assertIn("GET pulls/41", self.calls())

    def test_the_guards_read_by_branch_name_judges_the_head_of_that_branchs_pull_request(self):
        self.two_open_prs()
        self.set(runs_seq=[[("checks", "completed", "success")]])
        self.assertEqual(self.gh_host().head_read("feat"), ("green", ""))
        self.assertIn(f"GET commits/{self.head()}/check-runs", self.calls())

    def test_a_branch_with_no_open_pull_request_is_a_stop_and_the_guard_reads_it_as_unknown(self):
        self.set(open_prs=[["other", "d" * 40, "main", 40]])
        with self.assertRaises(merge.Stop):
            self.gh_host().pr("feat")
        verdict, detail = self.gh_host().head_read("feat")
        self.assertEqual(verdict, "unknown", detail)

    def test_a_branch_with_two_open_pull_requests_is_a_stop_and_the_guard_reads_it_as_unknown(self):
        self.set(open_prs=[["feat", "a" * 40, "main", 40], ["feat", "b" * 40, "release", 41]])
        with self.assertRaises(merge.Stop):
            self.gh_host().pr("feat")
        verdict, detail = self.gh_host().head_read("feat")
        self.assertEqual(verdict, "unknown", detail)

    # ---- no GraphQL, and the repo of every call

    def test_a_graphql_call_is_refused_with_the_cloud_session_403(self):
        host = self.gh_host()
        for args in (["pr", "view", "7"], ["pr", "list"], ["pr", "checks", "7"], ["pr", "merge", "7"], ["repo", "view"], ["api", "graphql"]):
            with self.subTest(args=args):
                c, out = host.gh(args)
                self.assertEqual(c, 1)
                self.assertIn("GitHub GraphQL is not available from Claude Code sessions; use the REST API", out)
        os.remove(os.path.join(self.state, "graphql.log"))  # these calls were the point of this test; any other GraphQL call fails its test

    def test_every_call_names_the_repo_by_the_hosts_repo_or_the_working_directorys(self):
        head = self.head()
        self.set(merge_fail=NOT_MERGEABLE)
        for repo, want in (("o/r", "o/r"), (None, "{owner}/{repo}")):
            with self.subTest(repo=repo):
                pathlib.Path(self.state, "repos.log").unlink(missing_ok=True)
                host = merge.Host(["checks"], "main", minute=60, now=lambda: self.now, pause=lambda s: None, repo=repo)
                host.pr(7)
                host.open_heads()
                host.checks(7, warn=False)
                host.head_read(7)
                host.merge(7, "merge", head)
                used = pathlib.Path(self.state, "repos.log").read_text().split()
                self.assertGreaterEqual(len(used), 8, used)
                self.assertEqual(set(used), {want})

    # ---- retries hold on every REST route

    def read_calls(self):
        return {"pr": lambda h: h.pr(7), "list": lambda h: h.open_heads(),
                "check-runs": lambda h: h.checks(7, warn=False), "status": lambda h: h.checks(7, warn=False)}

    def test_a_502_on_any_rest_read_is_retried_and_the_read_goes_through(self):
        for kind, call in self.read_calls().items():
            with self.subTest(route=kind):
                self.set(route_fail={kind: {"n": 1, "msg": rest_err(502, "Server Error")}}, route_failed={})
                call(self.gh_host())
                self.assertEqual(self.gh_state("route_failed"), {kind: 1})

    def test_four_502s_on_any_rest_read_are_a_network_stop(self):
        for kind, call in self.read_calls().items():
            with self.subTest(route=kind):
                self.set(route_fail={kind: {"n": 9, "msg": rest_err(502, "Server Error")}}, route_failed={})
                with self.assertRaises(merge.NetStop):
                    call(self.gh_host())
                self.assertEqual(self.gh_state("route_failed"), {kind: 4})  # one try and three retries

    def test_a_rate_limit_403_on_the_pull_request_read_waits_the_ladder_and_goes_through(self):
        self.set(route_fail={"pr": {"n": 1, "msg": RATE_API_403}})
        self.gh_host().pr(7)
        self.assertEqual(self.paused, RATE_LADDER[:1])

    def test_a_permission_403_on_the_pull_request_read_is_a_stop_and_is_not_retried(self):
        self.set(route_fail={"pr": {"n": 1, "msg": PLAIN_403_API}})
        with self.assertRaises(merge.Stop) as raised:
            self.gh_host().pr(7)
        self.assertNotIsInstance(raised.exception, merge.NetStop)
        self.assertEqual((self.paused, self.gh_state("route_failed")), ([], {"pr": 1}))

def put_base_config(env, text):
    """Commit `text` as .github/stamp.json on origin's main from the other clone. env.co keeps its local checkout."""
    o = env.other
    sh(o, "git", "fetch", "-q", "origin")
    sh(o, "git", "checkout", "-q", "-B", "main", "origin/main")
    put(os.path.join(o, ".github/stamp.json"), text)
    sh(o, "git", "commit", "-qam", "base config")
    sh(o, "git", "push", "-q", "origin", "main")
    head_takes_base(env)

def head_takes_base(env):
    """Merge origin's main into the PR branch, as a lane does before its run, so a setup push to main is not a moved base (merge-needs-current-base)."""
    o, b = env.other, env.host.branch
    if sh(o, "git", "ls-remote", "origin", f"refs/heads/{b}"):
        sh(o, "git", "checkout", "-q", "-B", b, f"origin/{b}")
        sh(o, "git", "merge", "-q", "--no-edit", "main")
        sh(o, "git", "push", "-q", "origin", b)
    sh(env.co, "git", "fetch", "-q", "origin")  # the base is visible to env.co; its checkout is not pulled

def put_base_bytes(env, data):
    """Commit raw `data` as .github/stamp.json on origin's main, as put_base_config does for text."""
    o = env.other
    sh(o, "git", "fetch", "-q", "origin")
    sh(o, "git", "checkout", "-q", "-B", "main", "origin/main")
    path = os.path.join(o, ".github/stamp.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    sh(o, "git", "commit", "-qam", "base config, raw bytes")
    sh(o, "git", "push", "-q", "origin", "main")
    head_takes_base(env)

class ConfigFile(Env):
    """The merge block and defaultBranch come from the base branch's .github/stamp.json, never the local checkout.
    A base file that is broken stops with one line that names the file, never the defaults."""
    def stops_on(self, problem):
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 1, out)
        lines = [l for l in out.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1, out)
        self.assertIn(".github/stamp.json", lines[0])
        self.assertIn(problem, lines[0])
        self.assertNotIn("defaults", out)

    def test_bad_json_on_the_base_stops_with_one_line_naming_the_file(self):
        put_base_config(self, "{not json")
        self.stops_on("line 1")

    def test_a_base_file_that_is_not_utf8_stops_with_one_line_naming_the_file(self):
        put_base_bytes(self, json.dumps(CONFIG).encode("utf-16"))  # BOM + UTF-16 bytes, not UTF-8
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 1, out)
        lines = [l for l in out.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1, out)
        self.assertIn(".github/stamp.json", lines[0])
        self.assertNotIn("Traceback", out)

    def one_merge_line(self, out):
        lines = [l for l in out.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1, out)
        self.assertTrue(lines[0].startswith("merge:"), out)
        self.assertNotIn("Traceback", out)
        return lines[0]

    def test_a_bad_deadlineMinutes_or_ignoreChecks_stops_with_one_line_naming_it_and_no_lock(self):
        """One validator per field, many inputs. Rows: deadlineMinutes of the wrong type, zero or negative, past the
        360 cap (GitHub's longest job run; 10**400 too), each at preview and at confirm; ignoreChecks null, a list as a
        name, a null reason, a non-string name (a check name is a string; 5 never matches one). Each row stops with one
        merge line naming the field, with no traceback, no TypeError, no OverflowError and no lock taken. A deadlineMinutes
        preview row also names the config file, the line the refusal at load has always printed."""
        rows = [("deadlineMinutes", v) for v in ("45", True, 0, -5, 361, 10 ** 400)]
        rows += [("ignoreChecks", v) for v in (None,
                                              [{"name": ["checks"], "reason": "x"}],
                                              [{"name": "design", "reason": None}],
                                              [{"name": 5, "reason": "x"}])]
        for field, bad in rows:
            text = json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], **{field: bad})))
            args_list = (("7",), ("7", "--confirm")) if field == "deadlineMinutes" else (("7",),)
            for args in args_list:
                with self.subTest(field=field, value=repr(bad)[:40], args=args):
                    self.setUp()  # a fresh checkout per row: the same config text twice is "nothing to commit"
                    put_base_config(self, text)
                    rc, out = self.run_merge(*args)
                    self.assertEqual(rc, 1, out)
                    line = self.one_merge_line(out)
                    self.assertIn(field, line)
                    if args == ("7",) and field == "deadlineMinutes":
                        self.assertIn(".github/stamp.json", line)
                    self.assertNotIn("TypeError", out)
                    self.assertNotIn("OverflowError", out)
                    self.assertFalse(self.lock_ref())

    def test_deadlineMinutes_360_is_accepted_at_preview_and_confirm(self):  # the cap's edge: a guard
        put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], deadlineMinutes=360))))
        for args in (("7",), ("7", "--confirm")):
            with self.subTest(args=args):
                rc, out = self.run_merge(*args)
                self.assertEqual(rc, 0, out)

    def config_text(self, fields=None, **top):
        """A complete merge block (no defaults notice), with `fields` replaced and `top` keys set at the top level."""
        block = dict({"method": "merge", "deadlineMinutes": 5, "requiredChecks": ["checks"], "afterMerge": [], "deleteBranch": True}, **(fields or {}))
        return json.dumps(dict(CONFIG, merge=block, **top))

    def refused_at_preview(self, text, field):
        """One `merge:` line naming the field, at preview, before any lock, claim or merge."""
        put_base_config(self, text)
        before = self.refs()
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 1, out)
        self.assertIn(field, self.one_merge_line(out))
        self.assertEqual(self.refs(), before)  # no claim pushed, no lock taken
        self.assertFalse(getattr(self.host, "merged", False))

    def test_a_bad_value_of_a_merge_field_is_refused_at_preview_naming_the_field(self):
        """One validator, many inputs. Each row is one bad value of one field: refused at preview, one line naming the
        field, before any lock, claim or merge. Rows: afterMerge (wrong type); requiredChecks (wrong shape; only
        "protection" or a non-empty list of non-empty strings); deleteBranch (not a bool); method (not merge, squash or
        rebase); defaultBranch (not a non-empty string; "" must not fall back to the host, so the host is patched)."""
        rows = [("afterMerge", self.config_text({"afterMerge": v})) for v in (None, 5, True, [1], [""])]
        rows += [("requiredChecks", self.config_text({"requiredChecks": v})) for v in ([["checks"]], [{}], [1, "checks"], [], "checks", [""])]
        rows += [("deleteBranch", self.config_text({"deleteBranch": v})) for v in ("false", 1)]
        rows += [("method", self.config_text({"method": v})) for v in ("admin", "Squash")]
        for i, (field, text) in enumerate(rows):
            with self.subTest(field=field, row=i):
                self.setUp()
                self.refused_at_preview(text, field)
        for v in (5, ""):
            with self.subTest(field="defaultBranch", value=v), unittest.mock.patch.object(merge, "host_default_branch", return_value="main"):
                self.setUp()
                self.refused_at_preview(self.config_text(defaultBranch=v), "defaultBranch")

    def test_a_valid_config_with_every_field_is_accepted_at_preview(self):  # the control
        for fields in ({"method": "squash", "requiredChecks": "protection", "afterMerge": ["true"], "deleteBranch": False},
                       {"method": "rebase", "requiredChecks": ["checks"], "afterMerge": ["true", "echo x"], "deleteBranch": True}):
            with self.subTest(fields=fields):
                put_base_config(self, self.config_text(fields))
                rc, out = self.run_merge("7")
                self.assertEqual(rc, 0, out)

    def test_an_unknown_merge_field_stops_with_one_line_naming_it(self):
        put_base_config(self, json.dumps({"merge": {"methd": "squash"}}))
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 1, out)
        lines = [l for l in out.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1, out)
        self.assertIn("unknown field", lines[0])
        self.assertIn("methd", lines[0])

    def test_the_merge_block_comes_from_the_base_not_the_checkout(self):
        put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], method="squash"))))  # the checkout keeps "merge"
        methods = []
        real = self.host.merge
        self.host.merge = lambda n, m, sha: (methods.append(m), real(n, m, sha))[1]
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertEqual(methods, ["squash"])
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))

    def test_defaultBranch_comes_from_the_base_not_the_checkout(self):
        put_base_config(self, json.dumps(dict(CONFIG, defaultBranch="trunk")))  # the checkout says "main"
        rc, out = self.run_merge("7")
        self.assertIn("main is not the default branch (trunk)", out)

class ClaimSkipped(Env):
    """A base with no stamp kinds: the claim and the numbering check are skipped, and stamp.mjs never runs."""
    def setUp(self):
        super().setUp()
        self.mark = stamp_marker(self)

    def base_config(self, cfg):
        o = self.other
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", "main", "origin/main")
        put(os.path.join(o, ".github/stamp.json"), json.dumps(cfg))
        sh(o, "git", "commit", "-qam", "config without kinds"); sh(o, "git", "push", "-q", "origin", "main")
        sh(self.co, "git", "pull", "-q", "--ff-only")
        head_takes_base(self)

    def check_skipped(self, cfg):
        self.base_config(cfg)
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertFalse(os.path.exists(self.mark), "stamp.mjs ran")
        self.assertEqual(self.claims(), 0)
        self.assertIn("id: pending", self.show("main", "docs/decisions/second.md"))

    def test_empty_kinds_skips_the_claim_and_stamp(self):
        self.check_skipped(dict(CONFIG, kinds=[]))

    def test_no_kinds_key_skips_the_claim_and_stamp(self):
        self.check_skipped({k: v for k, v in CONFIG.items() if k != "kinds"})

class ClaimFromBase(Env):
    """The claim reads the config from the base branch, not the pull request's tree (ios-adblock #28)."""
    def test_a_pr_tree_without_the_config_claims_from_the_base(self):
        o = self.other
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        sh(o, "git", "rm", "-q", ".github/stamp.json")
        sh(o, "git", "commit", "-qm", "feat predates the config")
        sh(o, "git", "push", "-q", "origin", "feat")
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Traceback", out)
        self.assertEqual(self.claims(), 1)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))

class StampFailure(Env):
    """stamp.mjs fails for any reason: merge prints one line with the reason and a remedy, never a stack trace."""
    def stamp_fails(self, program, reason):
        before = self.head()
        with unittest.mock.patch.object(merge, "STAMP", program):
            rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)
        stamp_lines = [l for l in out.splitlines() if "claim was refused" in l]  # the stamp line alone
        self.assertEqual(len(stamp_lines), 1, out)
        self.assertIn(reason, stamp_lines[0])
        self.assertNotIn("    at ", out)
        self.assertNotIn("Traceback", out)
        self.assertEqual(self.head(), before)  # nothing was pushed

    def test_a_stamp_that_throws_prints_one_line_and_no_stack(self):
        program = os.path.join(self.t, "throws.mjs")
        put(program, 'throw new Error("boom: fake stamp failure");\n')
        self.stamp_fails(program, "boom")

    def test_a_missing_stamp_program_prints_one_line_and_no_stack(self):
        self.stamp_fails(os.path.join(self.t, "no-such-stamp.mjs"), "Cannot find module")

class SilentUndo(Env):
    def stale_feat(self):
        """main gains lines in first.md, then feat merges main keeping ours: feat carries the old file."""
        o = self.other
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", "main", "origin/main")
        put(os.path.join(o, "docs/decisions/first.md"), record("D-001", "first") + "newer line a\nnewer line b\n")
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-qm", "main moves"); sh(o, "git", "push", "-q", "origin", "main")
        sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        sh(o, "git", "merge", "-q", "-s", "ours", "--no-edit", "origin/main")
        sh(o, "git", "push", "-q", "origin", "feat")

    def test_a_stale_branch_is_refused_before_anything_is_pushed(self):
        self.stale_feat()
        before = self.refs()
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1)
        self.assertIn("silently undoes", out)
        self.assertIn("first.md", out)
        self.assertEqual(self.refs(), before)
        self.assertEqual(self.host.waits, [])
        self.assertFalse(self.lock_ref())  # a refusal frees the lock

    def test_a_trailer_lets_the_deliberate_drop_merge(self):
        self.stale_feat()
        o = self.other
        sh(o, "git", "commit", "-q", "--allow-empty", "-m", "Drop them on purpose\n\nDrops-lines: docs/decisions/first.md -- the lines are dead")
        sh(o, "git", "push", "-q", "origin", "feat")
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)

    def test_the_check_runs_again_after_the_wait_and_a_red_reverts_the_claim(self):
        calls = []
        real = merge.undo_check
        def second_is_red(wt, base, unknown_ok="", pr_body=""):
            calls.append(base)
            if len(calls) == 2:
                raise merge.Stop("the branch silently undoes earlier work: main moved during the wait")
            return real(wt, base, unknown_ok, pr_body)
        with unittest.mock.patch.object(merge, "undo_check", second_is_red):
            rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(len(calls), 2)
        self.assertEqual(rc, 1)
        self.assertEqual(self.claims(), 0)
        self.assertFalse(getattr(self.host, "merged", False))


class DraftPreview(Env):
    """`merge <pr>` with no --confirm: a draft is previewed, not refused. The silent-undo check runs on the head
    in every preview. A closed or merged PR is refused, and the check never runs on it."""

    def test_a_draft_preview_reports_a_dropped_line(self):
        SilentUndo.stale_feat(self)
        self.host.draft = True
        before = self.refs()
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 1, out)
        self.assertIn("silently undoes", out)
        self.assertIn("first.md", out)
        self.assertIn("draft", out.lower())
        self.assertEqual(self.refs(), before)
        self.assertFalse(self.lock_ref())
        self.assertEqual(self.host.waits, [])
        self.assertEqual(self.worktrees(), 1)

    def test_a_ready_preview_reports_a_dropped_line(self):
        SilentUndo.stale_feat(self)
        before = self.refs()
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 1, out)
        self.assertIn("silently undoes", out)
        self.assertIn("first.md", out)
        self.assertEqual(self.refs(), before)
        self.assertFalse(self.lock_ref())
        self.assertEqual(self.host.waits, [])

    def blocked_lines(self, out):
        return [l for l in out.splitlines() if l.startswith("BLOCKED: ")]

    def test_a_ready_preview_of_a_dropped_line_prints_one_blocked_line(self):
        SilentUndo.stale_feat(self)
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 1, out)
        blocked = self.blocked_lines(out)
        self.assertEqual(len(blocked), 1, out)
        self.assertIn("first.md", blocked[0])

    def test_a_draft_preview_of_a_dropped_line_prints_one_blocked_line(self):
        SilentUndo.stale_feat(self)
        self.host.draft = True
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 1, out)
        blocked = self.blocked_lines(out)
        self.assertEqual(len(blocked), 1, out)
        self.assertIn("first.md", blocked[0])

    def test_a_clean_draft_preview_passes_and_names_the_draft(self):
        self.host.draft = True
        before = self.refs()
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 0, out)
        self.assertIn("PREVIEW", out)
        self.assertIn("Nothing was pressed", out)
        self.assertIn("draft", out.lower())
        self.assertNotIn("silently undoes", out)
        self.assertEqual(self.refs(), before)
        self.assertFalse(self.lock_ref())
        self.assertEqual(self.host.waits, [])

    def test_a_closed_or_merged_pr_is_refused_at_preview_and_the_check_never_runs(self):  # control
        real, calls = merge.undo_check, []
        def spy(wt, base_ref, unknown_ok="", pr_body=""):
            calls.append(base_ref)
            return real(wt, base_ref, unknown_ok, pr_body)
        before = self.refs()
        with unittest.mock.patch.object(merge, "undo_check", spy):
            for state in ("CLOSED", "MERGED"):
                self.host.pr_state = state
                rc, out = self.run_merge("7")
                self.assertEqual(rc, 1, out)
                self.assertIn("the pull request is " + state, out)
        self.assertEqual(calls, [])
        self.assertEqual(self.refs(), before)


class PrBodyEscape(Env):
    """`Drops-lines: <path> -- <reason>` in the PR body excuses its path at preview, as a commit trailer does.
    A line with no reason, or one for another path, excuses nothing. Each use prints ALLOWED."""

    def preview(self):
        before = self.refs()
        rc, out = self.run_merge("7")
        self.assertEqual(self.refs(), before)
        self.assertEqual(self.host.waits, [])
        return rc, out

    def test_a_pr_body_line_excuses_its_path_at_preview(self):
        SilentUndo.stale_feat(self)
        self.host.body = "Drops-lines: docs/decisions/first.md -- the lines are dead"
        rc, out = self.preview()
        self.assertEqual(rc, 0, out)
        self.assertIn("ALLOWED docs/decisions/first.md: the lines are dead", out)
        self.assertNotIn("BLOCKED", out)

    def test_a_pr_body_line_without_a_reason_excuses_nothing(self):
        SilentUndo.stale_feat(self)
        for body in ("Drops-lines: docs/decisions/first.md", "Drops-lines: docs/decisions/first.md --"):
            with self.subTest(body=body):
                self.host.body = body
                rc, out = self.preview()
                self.assertEqual(rc, 1, out)
                self.assertIn("first.md", out)
                self.assertNotIn("ALLOWED", out)

    def test_a_pr_body_line_for_another_path_does_not_excuse(self):
        SilentUndo.stale_feat(self)
        self.host.body = "Drops-lines: docs/decisions/second.md -- wrong path"
        rc, out = self.preview()
        self.assertEqual(rc, 1, out)
        self.assertIn("first.md", out)
        self.assertNotIn("ALLOWED", out)

    def test_a_commit_trailer_still_excuses_its_path_at_preview(self):  # control
        SilentUndo.stale_feat(self)
        o = self.other
        sh(o, "git", "commit", "-q", "--allow-empty", "-m", "Drop them on purpose\n\nDrops-lines: docs/decisions/first.md -- the lines are dead")
        sh(o, "git", "push", "-q", "origin", "feat")
        rc, out = self.preview()
        self.assertEqual(rc, 0, out)
        self.assertIn("ALLOWED docs/decisions/first.md: the lines are dead", out)
    def test_the_undo_memo_is_not_reused_across_pr_bodies(self):
        SilentUndo.stale_feat(self)
        co = self.co
        sh(co, "git", "fetch", "-q", "origin")
        sh(co, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        excuse = "Drops-lines: docs/decisions/first.md -- the lines are dead"
        cwd = os.getcwd()
        os.chdir(co)
        try:
            for first, second in (("", excuse), (excuse, "")):
                with self.subTest(first=first, second=second):
                    merge.UNDO_MEMO.clear()
                    outcomes = []
                    for body in (first, second):
                        try:
                            with contextlib.redirect_stdout(io.StringIO()):
                                merge.undo_check(co, "origin/main", pr_body=body)
                            outcomes.append("ok")
                        except merge.Stop:
                            outcomes.append("refused")
                    want = ["ok" if b else "refused" for b in (first, second)]
                    self.assertEqual(outcomes, want)
        finally:
            os.chdir(cwd)
            merge.UNDO_MEMO.clear()


class StampEnv(unittest.TestCase):
    def test_the_stamp_child_never_sees_the_runners_ref(self):
        # On a push to main the runner sets GITHUB_REF=refs/heads/main. stamp would read it as the worktree's branch.
        seen = {}
        def fake(args, cwd=None, input=None, env=None):
            seen.update(env or {"__none__": "1"})
            return 0, ""
        with unittest.mock.patch.dict(os.environ, {"GITHUB_REF": "refs/heads/main", "GITHUB_BASE_REF": "main"}), \
             unittest.mock.patch.object(merge, "sh", fake):
            merge.node_stamp("/wt", ".github/stamp.json", "check", "origin/main")
        self.assertNotIn("__none__", seen)
        self.assertNotIn("GITHUB_REF", seen)
        self.assertNotIn("GITHUB_BASE_REF", seen)

class ClaimStderr(unittest.TestCase):
    """stamp.mjs --claim prints Record-claim: on stdout, but its regenerate step
    (npm) can write warn/notice lines on stderr. sh() concatenates stdout+stderr, so those land
    after the trailer. do_claim must find the trailer, not assume it is the last line."""
    def fake_sh(self, combined):
        # sh() itself does (r.stdout + r.stderr).strip(); patching sh means replicating that join.
        def fake(args, cwd=None, input=None, env=None):
            return 0, combined.strip()
        return fake

    def test_a_trailer_followed_by_npm_noise_on_stderr_is_still_read(self):
        out = "Record-claim: D-701\n" + "npm warn deprecated inflight@1.0.6: this module is not supported\nnpm notice new version of npm available"
        with unittest.mock.patch.object(merge, "sh", self.fake_sh(out)):
            trailer = merge.do_claim("/wt", ".github/stamp.json", "origin/main")
        self.assertEqual(trailer, "Record-claim: D-701")

    def test_nothing_to_claim_is_still_none(self):
        with unittest.mock.patch.object(merge, "sh", self.fake_sh("nothing pending.\n")):
            trailer = merge.do_claim("/wt", ".github/stamp.json", "origin/main")
        self.assertIsNone(trailer)

class UndoMemo(Env):
    """confirm() reads the silent-undo check twice: before the claim, and after the wait. When the head sha,
    origin/<base> and the default ref are the same at both reads, the second read reuses the first scan.
    One scan is one call of check_silent_undo.check. A scan can take about 35 min."""

    def counted(self, fn):
        sys.path.insert(0, os.path.join(HERE, "..", "lint"))
        import check_silent_undo as undo
        real_check, real_undo = undo.check, merge.undo_check
        scans, undos = [], []

        def spy_check(*a, **k):
            scans.append(a[1])
            return real_check(*a, **k)

        def spy_undo(wt, base_ref, unknown_ok="", pr_body=""):
            undos.append(base_ref)
            return real_undo(wt, base_ref, unknown_ok, pr_body)
        with unittest.mock.patch.object(undo, "check", spy_check), unittest.mock.patch.object(merge, "undo_check", spy_undo):
            res = fn()
        return res, len(scans), len(undos)

    def no_claim(self):
        """feat deletes its only pending record, so the run claims nothing and the head does not move."""
        sh(self.other, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        sh(self.other, "git", "rm", "-q", "docs/decisions/second.md")
        sh(self.other, "git", "commit", "-qm", "no pending record left"); sh(self.other, "git", "push", "-q", "origin", "feat")

    def move_main_in_the_wait(self, real_wait, fetch_co=False):
        def wait_while_main_moves(n, sha, d, prior=None):
            sh(self.other, "git", "fetch", "-q", "origin")
            sh(self.other, "git", "checkout", "-q", "-B", "main", "origin/main")
            put(os.path.join(self.other, "moved.txt"), "main moved in the wait\n")
            sh(self.other, "git", "add", "-A"); sh(self.other, "git", "commit", "-qm", "main moves in the wait")
            sh(self.other, "git", "push", "-q", "origin", "main")
            if fetch_co:
                sh(self.co, "git", "fetch", "-q", "origin")
            return real_wait(n, sha, d, prior)
        return wait_while_main_moves

    def test_unchanged_head_base_and_default_scan_once(self):
        self.no_claim()
        (rc, out), scans, undos = self.counted(lambda: self.run_merge("7", "--confirm"))
        self.assertEqual(rc, 0, out)
        self.assertEqual(undos, 2, out)
        self.assertEqual(scans, 1, "scans %d, undo reads %d\n%s" % (scans, undos, out))

    def test_origin_base_moving_during_the_wait_scans_again(self):
        self.no_claim()
        self.host.wait_checks = self.move_main_in_the_wait(self.host.wait_checks)
        (rc, out), scans, undos = self.counted(lambda: self.run_merge("7", "--confirm"))
        self.assertEqual(rc, 1, out)  # the scan runs again, then the moved base refuses the merge (merge-needs-current-base)
        self.assertIn("does not hold origin/main", out)
        self.assertEqual(undos, 2, out)
        self.assertEqual(scans, 2, "scans %d, undo reads %d\n%s" % (scans, undos, out))

    def test_default_ref_moving_during_the_wait_scans_again(self):
        self.no_claim()
        sh(self.other, "git", "fetch", "-q", "origin")
        sh(self.other, "git", "push", "-q", "origin", "origin/main:refs/heads/integ")
        self.host.base = "integ"
        self.host.wait_checks = self.move_main_in_the_wait(self.host.wait_checks, fetch_co=True)
        (rc, out), scans, undos = self.counted(lambda: self.run_merge("7", "--confirm"))
        self.assertEqual(rc, 0, out)
        self.assertEqual(undos, 2, out)
        self.assertEqual(scans, 2, "scans %d, undo reads %d\n%s" % (scans, undos, out))

    def test_head_moving_for_the_claim_scans_again(self):
        (rc, out), scans, undos = self.counted(lambda: self.run_merge("7", "--confirm"))
        self.assertEqual(rc, 0, out)
        self.assertIn("pushed to feat", out)
        self.assertEqual(undos, 2, out)
        self.assertEqual(scans, 2, "scans %d, undo reads %d\n%s" % (scans, undos, out))


class MemoKeyRead(Env):
    """undo_check reads the memo key with git rev-parse. A timeout on that read leaves the history unread,
    so it must surface as the Unknown refusal, not crash the merge tool."""

    def test_a_timeout_on_the_memo_key_read_refuses_as_unknown(self):
        real_sh = merge.sh

        def slow(args, cwd=None, input=None, env=None):
            if "rev-parse" in args:
                raise subprocess.TimeoutExpired(args, 1)
            return real_sh(args, cwd=cwd, input=input, env=env)
        with unittest.mock.patch.object(merge, "sh", slow):
            with self.assertRaises(merge.Stop) as cm:
                merge.undo_check(self.co, "origin/main")
        self.assertIn("could not read the history", str(cm.exception))


class UnknownOverride(Env):
    """Unknown has a way out that does not depend on the check: an owner flag with a reason, logged."""
    def unreadable(self):
        sys.path.insert(0, os.path.join(HERE, "..", "lint"))
        import check_silent_undo as undo
        def boom(*a, **k):
            raise undo.Unknown("git is older than 2.38")
        return unittest.mock.patch.object(undo, "check", boom)

    def test_unknown_refuses_and_names_the_flag(self):
        before = self.refs()
        with self.unreadable():
            rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1)
        self.assertIn("--undo-check-unknown-ok", out)
        self.assertEqual(self.refs(), before)
        self.assertFalse(self.lock_ref())

    def test_the_owner_flag_with_a_reason_goes_on_and_logs_it(self):
        with self.unreadable():
            rc, out = self.run_merge("7", "--confirm", "--undo-check-unknown-ok", "octopus, owner read it")
        self.assertEqual(rc, 0, out)
        self.assertIn("Owner override, reason: octopus, owner read it", out)

    def test_the_flag_with_no_reason_does_not_go_on(self):
        with self.unreadable():
            rc, out = self.run_merge("7", "--confirm", "--undo-check-unknown-ok", " ")
        self.assertEqual(rc, 1)

    def test_the_flag_never_excuses_a_finding(self):
        SilentUndo.stale_feat(self)
        rc, out = self.run_merge("7", "--confirm", "--undo-check-unknown-ok", "just let it through")
        self.assertEqual(rc, 1)
        self.assertIn("silently undoes", out)

class Identity(Env):
    def test_claim_commit_falls_back_when_only_the_email_is_set(self):
        info = self.host.pr(7)
        tmp, wt = merge.open_worktree(self.co, info, "main")
        try:
            sh(wt, "git", "config", "user.email", "x@x"); sh(wt, "git", "config", "user.useConfigOnly", "true")
            trailer = merge.do_claim(wt, ".github/stamp.json", "origin/main")
            with unittest.mock.patch.dict(os.environ):
                for k in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
                    os.environ.pop(k)
                merge.commit_claim(wt, trailer)
            self.assertEqual(sh(wt, "git", "log", "-1", "--format=%an"), "merge")
        finally:
            merge.drop_worktree(self.co, tmp, wt)

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

def dead_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"]); p.wait()
    return p.pid

class LockHolder(Env):
    """The lock names its holder; the Held text says alive, dead, or cannot tell."""
    def push_lock(self, message):
        sha = sh(self.co, "git", "commit-tree", EMPTY_TREE, "-m", message)
        sh(self.co, "git", "push", "-q", "origin", f"{sha}:refs/heads/merge-lock/main")

    def lock_msg(self):
        sh(self.co, "git", "fetch", "-q", "origin", "refs/heads/merge-lock/main")
        return sh(self.co, "git", "log", "-1", "--format=%B", "FETCH_HEAD")

    def peek(self, *args):
        """Run `merge 7 --confirm *args`. Inside its wait, read the lock message and run a second merge.
        Returns (lock message, the second run's output). A run that never reaches the wait gives ("", "")."""
        seen = {"msg": "", "second": ""}
        orig = self.host.wait_checks
        def wait(n, sha, d, prior=None):
            if not seen["msg"]:
                seen["msg"] = self.lock_msg()
                seen["second"] = self.run_merge("8", "--confirm")[1]
            return orig(n, sha, d, prior)
        self.host.wait_checks = wait
        try:
            self.run_merge("7", "--confirm", *args)
        except SystemExit:
            pass  # argparse refuses an unknown flag: the lock was never taken
        return seen["msg"], seen["second"]

    def old_message(self, expires):
        return f"merge lock\nexpires: {int(expires)}\nowner: abc123"

    def new_message(self, host, pid, expires=None, platform=None, boot=None):
        boot = merge.boot_stamp() if boot is None else boot  # "" writes no boot line, as a lock from before c189 has none
        return (f"merge lock\nexpires: {int(expires or self.now + 600)}\nowner: abc123\n"
                f"pr: 445\nbranch: b\nhost: {host}\npid: {pid}\nstarted: 1790000000\nplatform: {platform or sys.platform}"
                + (f"\nboot: {boot}" if boot else ""))

    def held(self, message):
        self.push_lock(message)
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)
        return out

    @windows_slice
    def test_the_lock_records_the_holder_and_a_second_run_sees_it_alive(self):
        msg, second = self.peek("--session", "S")
        lines = msg.splitlines()
        self.assertEqual(lines[:1], ["merge lock"], msg)
        for want in ("pr: 7", "branch: feat", f"host: {socket.gethostname()}", f"pid: {os.getpid()}", "session: S"):
            self.assertIn(want, lines, msg)
        self.assertTrue(any(re.fullmatch(r"started: \d+", l) for l in lines), msg)
        self.assertTrue(any(re.fullmatch(r"expires: \d+", l) for l in lines), msg)
        self.assertTrue(any(re.fullmatch(r"owner: \w+", l) for l in lines), msg)
        for want in ("PR #7", "feat", '"S"', f"pid {os.getpid()}", socket.gethostname(), "alive"):
            self.assertIn(want, second)
        self.assertNotIn("dead", second)
        self.assertNotIn("Cannot tell", second)

    def test_no_session_flag_writes_no_session_line(self):
        msg, _ = self.peek()
        self.assertIn("pr: 7", msg.splitlines())
        self.assertNotIn("session:", msg)

    @windows_slice
    def test_a_lock_on_this_host_whose_pid_is_gone_is_taken_over_with_one_line(self):  # c189: it was refused with "Run: merge --unlock" (#746)
        pid = dead_pid()
        self.push_lock(self.new_message(socket.gethostname(), pid))
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        said = [l for l in out.splitlines() if "took over" in l]
        self.assertEqual(len(said), 1, out)
        for want in ("PR #445", "branch b", f"pid {pid}", "dead"):
            self.assertIn(want, said[0])
        self.assertFalse(self.lock_ref())
        self.assertNotIn("merge --unlock", out)

    def test_a_pid_missing_on_a_machine_that_booted_apart_stays_refused(self):  # cloud VMs share a hostname: a pid absent here proves nothing about the holder's VM
        out = self.held(self.new_message(socket.gethostname(), dead_pid(), boot="some-other-boot"))
        self.assertNotIn("took over", out)
        self.assertIn("Cannot tell if the holder is alive", out)

    def test_a_lock_with_no_boot_line_stays_refused(self):
        out = self.held(self.new_message(socket.gethostname(), dead_pid(), boot=""))
        self.assertNotIn("took over", out)
        self.assertIn("Cannot tell if the holder is alive", out)

    def test_the_lock_records_the_boot(self):
        self.assertIn(f"boot: {merge.boot_stamp()}", self.peek()[0].splitlines())

    @unittest.skipUnless(sys.platform.startswith("linux"), "the pid namespace link is Linux's")
    def test_the_linux_boot_stamp_names_the_pid_namespace(self):  # the same boot id runs under any container's own pid numbers
        self.assertIn(os.readlink("/proc/self/ns/pid"), merge.boot_stamp())

    def test_a_dead_holder_on_another_host_stays_refused(self):
        out = self.held(self.new_message("some-other-host-xyz", dead_pid()))
        self.assertNotIn("took over", out)

    def test_held_says_cannot_tell_for_another_host(self):
        out = self.held(self.new_message("some-other-host-xyz", os.getpid()))
        self.assertIn("PR #445", out)
        self.assertIn("some-other-host-xyz", out)
        self.assertIn("Cannot tell if the holder is alive", out)
        self.assertNotIn("The holder is alive", out)
        self.assertNotIn("The holder is dead", out)

    def test_held_says_cannot_tell_for_an_old_lock_and_the_old_lock_still_expires(self):
        out = self.held(self.old_message(self.now + 600))
        self.assertIn("Cannot tell if the holder is alive", out)
        self.assertIn("merge --unlock", out)
        self.now += 601
        self.assertTrue(self.lock.acquire("main", 600))

    def test_a_new_lock_expires_too(self):
        self.push_lock(self.new_message(socket.gethostname(), os.getpid(), expires=self.now + 600))
        self.now += 601
        self.assertTrue(self.lock.acquire("main", 600))

    def test_the_preview_lock_line_says_the_holder_state(self):
        self.push_lock(self.new_message(socket.gethostname(), dead_pid()))
        rc, out = self.run_merge("7")
        self.assertIn("PR #445", out)
        self.assertIn("dead", out)

    def test_a_session_with_a_newline_cannot_add_an_expires_or_owner_line(self):
        msg, _ = self.peek("--session", "x\nexpires: 1\nowner: evil\r\nexpires: 2")
        lines = msg.splitlines()
        self.assertIn("pr: 7", lines, msg)  # the run took the lock at all
        self.assertEqual(len([l for l in lines if l.startswith("expires:")]), 1, msg)
        self.assertEqual(len([l for l in lines if l.startswith("owner:")]), 1, msg)
        self.assertNotIn("owner: evil", lines)
        self.assertEqual(len([l for l in lines if l.startswith("session:")]), 1, msg)

    def test_a_long_session_is_capped(self):
        msg, _ = self.peek("--session", "a" * 5000)
        self.assertIn("pr: 7", msg.splitlines(), msg)
        self.assertLess(len(msg), 1000)

    def garbled(self, **fields):
        f = {"pid": os.getpid(), "started": 1790000000}; f.update(fields)
        try:
            out = self.held(f"merge lock\nexpires: {int(self.now + 600)}\nowner: abc123\npr: 445\nbranch: b\n"
                            f"host: {socket.gethostname()}\npid: {f['pid']}\nstarted: {f['started']}\nplatform: {sys.platform}")
        except Exception as e:
            self.fail(f"the Held text crashed: {type(e).__name__}: {e}")
        self.assertIn("Cannot tell if the holder is alive", out)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("The holder is dead", out)

    def test_a_garbled_pid_or_started_field_reads_cannot_tell(self):
        # Rows: a pid too big for the OS; a non-ASCII digit in pid; in started; a twenty-digit started.
        # Each row is a fresh fixture: garbled() pushes the lock ref, and a second push is rejected.
        for fields in (dict(pid=10 ** 12), dict(pid="²"), dict(started="²"), dict(started="1" * 20)):
            with self.subTest(fields=fields):
                self.setUp()
                self.garbled(**fields)

    @windows_slice
    def test_the_same_host_name_on_another_platform_reads_cannot_tell_never_dead(self):
        other = "linux" if sys.platform == "win32" else "win32"
        out = self.held(self.new_message(socket.gethostname(), dead_pid(), platform=other))
        self.assertIn("Cannot tell if the holder is alive", out)
        self.assertNotIn("The holder is dead", out)

    @windows_slice
    def test_a_lock_with_no_platform_line_reads_cannot_tell_never_dead(self):
        msg = self.new_message(socket.gethostname(), dead_pid()).rsplit("\nplatform:", 1)[0]
        self.assertNotIn("platform:", msg)
        out = self.held(msg)
        self.assertIn("Cannot tell if the holder is alive", out)
        self.assertNotIn("The holder is dead", out)

    def test_the_lock_records_this_platform(self):
        msg, _ = self.peek()
        self.assertIn(f"platform: {sys.platform}", msg.splitlines(), msg)

    def test_the_module_usage_names_session(self):
        self.assertIn("--session", merge.__doc__)

    def test_a_blank_session_writes_no_session_line(self):
        msg, _ = self.peek("--session", " \t ")
        self.assertIn("pr: 7", msg.splitlines(), msg)
        self.assertNotIn("session:", msg)

    @windows_slice
    @unittest.skipUnless(os.name == "nt", "the Windows probe: os.kill(pid, 0) is CTRL_C_EVENT there")
    def test_windows_liveness_never_calls_os_kill(self):
        self.push_lock(self.new_message(socket.gethostname(), os.getpid()))
        calls = []
        def fake_kill(pid, sig):
            calls.append((pid, sig))
            raise OSError("must not be called")
        with unittest.mock.patch.object(os, "kill", fake_kill):
            rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(calls, [])
        self.assertIn("The holder is alive", out)

def release_out(test, lock, token):
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            lock.release("main", token)
    except Exception as e:
        test.fail(f"release raised {type(e).__name__}: {e}")
    return out.getvalue() + err.getvalue()

class ReleaseReports(Env):
    def test_a_normal_acquire_then_release_prints_no_line(self):
        tok = self.lock.acquire("main", 600)
        self.assertEqual(release_out(self, self.lock, tok), "")
        self.assertFalse(self.lock_ref())

    def test_gh_normal_acquire_then_release_prints_no_line(self):
        S = {}
        def api(self_, *a):
            p = a[2] if a[0] == "-X" else a[0]
            if a[:2] == ("-X", "DELETE"):
                S.pop("ref", None); return 0, ""
            if a[:2] == ("-X", "POST"):
                if p.endswith("git/commits"): return 0, "c1"
                if "ref" in S: return 1, "HTTP 422"
                S["ref"] = "c1"; return 0, "{}"
            if "/git/ref/heads/merge-lock/" in p:
                return (0, S["ref"]) if "ref" in S else (1, "HTTP 404: Not Found")
            if "/git/ref/heads/" in p: return 0, "head1"
            if "/git/commits/head1" in p: return 0, "tree1"
            if "/git/commits/c1" in p: return 0, "merge lock\nexpires: 2000\nowner: x"
            return 1, "unhandled " + p
        with unittest.mock.patch.object(merge.GhLock, "api", api):
            lock = merge.GhLock(now=lambda: 1000.0)
            tok = lock.acquire("main", 600)
            self.assertEqual(release_out(self, lock, tok), "")
            self.assertNotIn("ref", S)

    def test_git_release_says_so_when_the_delete_fails(self):
        tok = self.lock.acquire("main", 600)
        sh(self.co, "git", "remote", "set-url", "origin", os.path.join(self.t, "gone.git"))
        out = release_out(self, self.lock, tok)
        self.assertIn("the lock release failed", out)
        self.assertIn("merge --unlock", out)

    def test_git_release_says_so_when_the_token_was_replaced(self):
        tok = self.lock.acquire("main", 600)
        self.lock.unlock("main")
        merge.GitLock(self.other, now=lambda: self.now).acquire("main", 600)
        out = release_out(self, self.lock, tok)
        self.assertIn("not this run's", out)
        self.assertTrue(self.lock_ref())  # the other run's lock is left

class GhReleaseReports(unittest.TestCase):
    """GhLock.api is patched, so these run on Windows too."""
    def lock_with(self, sha_on_read, delete=(0, ""), read_fail=None):
        calls = []
        def api(self_, *a):
            calls.append(a)
            if a[:2] == ("-X", "DELETE"):
                return delete
            if "/git/ref/heads/merge-lock/" in a[0]:
                return read_fail or (0, sha_on_read)
            if "/git/commits/" in a[0]:
                return 0, "merge lock\nexpires: 2000\nowner: x"
            return 1, "unhandled"
        patcher = unittest.mock.patch.object(merge.GhLock, "api", api)
        patcher.start(); self.addCleanup(patcher.stop)
        return merge.GhLock(now=lambda: 1000.0, pause=lambda s: None), calls  # a retry pause is a no-op: a test never sleeps

    def test_delete_failure_is_reported(self):
        lock, _ = self.lock_with("tok", delete=(1, "HTTP 500 boom"))
        out = release_out(self, lock, "tok")
        self.assertIn("the lock release failed", out)
        self.assertIn("boom", out)

    def test_read_failure_is_reported_and_never_raises(self):
        lock, _ = self.lock_with("tok", read_fail=(1, "HTTP 500 down"))
        out = release_out(self, lock, "tok")
        self.assertIn("the lock release failed", out)

    def test_a_replaced_token_is_reported_and_nothing_is_deleted(self):
        lock, calls = self.lock_with("someone-else")
        out = release_out(self, lock, "tok")
        self.assertIn("not this run's", out)
        self.assertFalse([c for c in calls if c[:2] == ("-X", "DELETE")])

class NetErrorLines(unittest.TestCase):
    """merge.is_net on the output of one failed gh or git call: a wrapped 5xx or 429 line, and a JSON body with gh's
    error line after it. The false-match cases must not match: a PR title, a check name, a refusal that quotes a 5xx."""
    def test_a_wrapped_5xx_or_429_line_is_a_network_error(self):
        for out in ("failed to get runs: HTTP 502: 502 Bad Gateway (https://api.github.com/repos/o/r/actions/runs?head_sha=abc)",
                    "failed to get runs: HTTP 429: Too Many Requests (https://api.github.com/repos/o/r/actions/runs?head_sha=abc)"):
            with self.subTest(out=out):
                self.assertTrue(merge.is_net(1, out))

    def test_a_json_body_with_gh_error_line_after_it_is_a_network_error(self):
        self.assertTrue(merge.is_net(1, '{"message":"Server Error"}gh: Server Error (HTTP 502)'))

    def test_the_jq_html_body_parse_error_line_is_a_network_error(self):
        # `gh api --jq` on a 5xx HTML gateway page prints only this parse error. A title that quotes it is refusal text.
        self.assertTrue(merge.is_net(1, "invalid character '<' looking for beginning of value"))
        self.assertFalse(merge.is_net(1, 'GraphQL: Pull Request is not mergeable: #7 "invalid character \'<\' looking for beginning of value"'))

    def test_a_json_check_list_is_never_a_network_error(self):
        # gh's JSON answer names checks: a check named "build: HTTP 500 guard" is a red check, not a network error
        for out in ('[{"name":"build: HTTP 500 guard","bucket":"fail","link":""}]',
                    '[{"name":"checks: HTTP 502","bucket":"fail","link":""}]',
                    '[{"name":"EOF lint","bucket":"fail","link":""}]'):
            with self.subTest(out=out):
                self.assertFalse(merge.is_net(1, out))

    def test_a_pr_title_or_refusal_that_quotes_a_5xx_is_not_a_network_error(self):
        for out in ('GraphQL: Pull Request is not mergeable: #7 "Fix (HTTP 502 retry)"',
                    "GraphQL: Pull Request is not mergeable: #502 Bad Gateway fix",
                    'GraphQL: Pull Request is not mergeable: #7 "Fix: HTTP 502: proxy"'):
            with self.subTest(out=out):
                self.assertFalse(merge.is_net(1, out))

    def test_a_refusal_that_quotes_a_wrapped_5xx_or_429_line_is_not_a_network_error(self):
        # An unanchored `HTTP 5xx (url)` alternative would match refusal text. A real refusal must revert, not retry into NetStop.
        for out in ("X Pull request #7 is not mergeable: Retry on HTTP 502 (https://github.com/o/r/issues/12)",
                    "X Pull request #7 is not mergeable: Retry on HTTP 429 (https://github.com/o/r/issues/12)"):
            with self.subTest(out=out):
                self.assertFalse(merge.is_net(1, out))

    def test_a_real_server_error_or_wrapped_run_line_is_a_network_error(self):
        # The anchor must keep the 5xx and 429 forms gh really prints, bare or after `: `.
        for out in ("Server Error (HTTP 502)",
                    "HTTP 502 (https://api.github.com/repos/o/r/branches/main/protection/required_status_checks)",
                    "failed to get runs: HTTP 502 (https://api.github.com/repos/o/r/actions/runs?head_sha=abc)",
                    "HTTP 429: Too Many Requests",
                    "failed to get runs: HTTP 429: Too Many Requests (https://api.github.com/repos/o/r/actions/runs?head_sha=abc)"):
            with self.subTest(out=out):
                self.assertTrue(merge.is_net(1, out))

    def test_a_wrapped_5xx_with_no_space_after_its_colon_is_not_a_network_error(self):
        # The anchor must keep the space in `: ` before the message, or `HTTP 502:x (url)` matches.
        self.assertFalse(merge.is_net(1, "failed to get runs: HTTP 502:x (https://x)"))

    def test_each_network_string_a_retried_path_once_drove_is_a_network_error(self):
        """The one matcher, is_net, for every retried path: the git fetch after the claim push, a lost merge reply, the
        required-checks read and the merge reply. These rows held full git flows before (M13). One e2e case per path stays."""
        for out in ("fatal: unable to access 'https://github.com/shivinate7/claude-settings/': Empty reply from server",
                    "fatal: unable to access 'https://github.com/shivinate7/claude-settings/': GnuTLS recv error (-9): Error decoding the received TLS packet.",
                    "fatal: unable to access 'https://github.com/shivinate7/claude-settings/': Failed sending data to the peer",
                    "kex_exchange_identification: Connection closed by remote host\nfatal: Could not read from remote repository.",
                    NET_DEADLINE,
                    NET_REFUSED,
                    "gh: HTTP 503",
                    "gh: HTTP 500",
                    "HTTP 502 (https://api.github.com/repos/o/r/branches/main/protection/required_status_checks)",
                    '{"message":"Server Error"}gh: Server Error (HTTP 502)',
                    "HTTP 429: Too Many Requests"):
            with self.subTest(out=out):
                self.assertTrue(merge.is_net(1, out))

class RateLimitLines(unittest.TestCase):
    """merge.is_net on a rate-limited gh call. A rate-limit 403 is a network fault. A permission 403 is a refusal.
    These scan gh's output, not source text, so the string-opener cases of building-scanner-respects-strings do not apply."""
    def test_a_rate_limit_403_is_a_network_error(self):
        for out in (RATE_403, RATE_SECONDARY_403, RATE_GQL_403, RATE_API_403, RATE_API_SECONDARY_403, "Retry-After: 17\n" + RATE_403):
            with self.subTest(out=out[:70]):
                self.assertTrue(merge.is_net(1, out))

    def test_a_graphql_rate_limit_already_exceeded_is_a_network_error(self):
        self.assertTrue(merge.is_net(1, RATE_GQL_ALREADY))
        self.assertTrue(merge.is_net(1, "Retry-After: 17\n" + RATE_GQL_ALREADY))

    def test_a_403_that_is_not_a_rate_limit_is_not_a_network_error(self):
        for out in (PLAIN_403, PLAIN_403_BRANCH, PLAIN_403_API):  # the same shapes as the rate-limit texts
            with self.subTest(out=out[:70]):
                self.assertFalse(merge.is_net(1, out))

    def test_a_refusal_or_check_that_quotes_a_rate_limit_is_not_a_network_error(self):
        for out in ('GraphQL: Pull Request is not mergeable: #7 "Handle API rate limit exceeded"',
                    'GraphQL: Pull Request is not mergeable: #7 "Back off on a secondary rate limit"',
                    'GraphQL: Pull Request is not mergeable: #7 "Fix: HTTP 403: API rate limit exceeded"',
                    'GraphQL: Pull Request is not mergeable: #7 "Fix: GraphQL: API rate limit already exceeded"',
                    '[{"name":"API rate limit exceeded guard","bucket":"fail","link":""}]'):
            with self.subTest(out=out[:70]):
                self.assertFalse(merge.is_net(1, out))

class RateLimitWait(unittest.TestCase):
    """retry_net and Host.gh on a rate-limited call: how many tries, and how long each wait is. The pause
    is a recorder, so nothing sleeps. A rate-limit text (403 or 429, any form) is retried 3 times. With no reset time from GitHub the waits are
    RATE_LADDER: 60, 300, 900 s. A reset time (a `Retry-After` header, in seconds) is the wait instead, capped at 900 s. Any other network error
    waits merge.NET_PAUSE. Before each rate wait the call runs Host.before_wait (confirm sets it to the lock's extend_for): it
    extends the lock past the wait, or raises NetStop, and then the call stops in place of the wait.
    Headers are read only from a `gh api -i` block: the reply starts with a status line, then the headers (gh_i builds one, in the shape gh 2.98.0
    prints). A header-like line anywhere else is text. Real `gh run list` has no -i, so on it the
    ladder is the only wait. These scan gh's output, not source text, so the string-opener cases of building-scanner-respects-strings do not apply."""
    NOW = 1000.0

    def setUp(self):
        self.pauses, self.calls = [], 0

    def replies(self, *seq):
        """Patch merge.sh so each gh call answers the next of `seq` (the last repeats). Counts them in self.calls."""
        self.calls = 0
        def sh(args, cwd=None, input=None, env=None):
            self.calls += 1
            return seq[min(self.calls, len(seq)) - 1]
        p = unittest.mock.patch.object(merge, "sh", sh)
        p.start(); self.addCleanup(p.stop)

    def host(self):
        return merge.Host(required=["checks"], base="main", minute=60, now=lambda: self.NOW, pause=self.pauses.append)

    def clocked_host(self, before_wait=None):
        """-> (host, clock). The pauses move the clock on. `before_wait` is what confirm hands the host once the lock is taken: the lock's extend_for
        (see LockExtensionReachesHost). It gets the wait in seconds."""
        clock = Clock(self.NOW)
        host = merge.Host(required=["checks"], base="main", minute=60, now=clock.now, pause=clock.pause)
        host.before_wait = before_wait
        return host, clock

    def retry(self, *seq):
        """-> merge.retry_net's result over the replies `seq`."""
        self.calls = 0
        def call():
            self.calls += 1
            return seq[min(self.calls, len(seq)) - 1]
        return merge.retry_net(call, self.pauses.append)

    # retry_net: the tries and the ladder
    def test_a_rate_limit_403_is_retried_with_the_rate_wait(self):
        self.assertEqual(self.retry((1, RATE_403), (1, RATE_SECONDARY_403), (0, "[]")), (0, "[]", 2))
        self.assertEqual(self.pauses, [60, 300])  # a rate limit waits the ladder, not NET_PAUSE

    def test_the_rate_waits_with_no_reset_are_60_300_900_seconds(self):  # the three waits, 21 minutes in all
        self.assertEqual(self.retry(*([(1, RATE_403)] * 3), (0, "[]")), (0, "[]", 3))
        self.assertEqual(self.pauses, [60, 300, 900])

    def test_a_graphql_rate_limit_already_exceeded_is_retried_with_the_rate_wait(self):
        self.assertEqual(self.retry((1, RATE_GQL_ALREADY), (0, "[]")), (0, "[]", 1))
        self.assertEqual(self.pauses, [60])

    def test_a_rate_limit_403_that_never_clears_is_tried_four_times(self):
        self.assertEqual(self.retry((1, RATE_403)), (1, RATE_403, 3))
        self.assertEqual(self.calls, 4)  # one try and three retries
        self.assertEqual(self.pauses, [60, 300, 900])

    def test_a_429_is_retried_with_the_rate_wait(self):
        self.assertEqual(self.retry((1, R429), (0, "[]")), (0, "[]", 1))
        self.assertEqual(self.pauses, [60])

    def test_a_plain_403_is_not_retried(self):  # (d): green before the lane, a guard
        for out in (PLAIN_403, PLAIN_403_BRANCH, PLAIN_403_API):
            with self.subTest(out=out[:70]):
                self.pauses.clear()
                self.assertEqual(self.retry((1, out), (0, "[]")), (1, out, 0))
                self.assertEqual(self.pauses, [])

    def test_a_plain_network_error_waits_the_normal_pause_whatever_its_headers(self):  # the NET_PAUSE half of the rule: a guard, green before the lane
        for out in (NET_TLS, "failed to get runs: HTTP 502: 502 Bad Gateway (https://api.github.com/repos/o/r/actions/runs?head_sha=abc)",
                    "Retry-After: 120\n" + NET_TLS,
                    gh_i(502, '{"message":"Server Error"}gh: Server Error (HTTP 502)', Retry_After=120)):  # a 5xx is not a rate limit: its Retry-After is no rate wait
            with self.subTest(out=out[:40]):
                self.pauses.clear()
                self.assertEqual(self.retry((1, out), (0, "[]")), (0, "[]", 1))
                self.assertEqual(self.pauses, [merge.NET_PAUSE])

    # retry_net: a reset time from GitHub is the wait. It is read from a `gh api -i` block only.
    def test_a_retry_after_in_a_gh_i_block_is_the_rate_wait(self):
        for body in (RATE_API_403, RATE_API_SECONDARY_403):
            for secs in (5, 120, 600):  # below the first rung, between the rungs, above the second
                with self.subTest(body=body[:40], retry_after=secs):
                    self.pauses.clear()
                    self.assertEqual(self.retry((1, gh_i(403, body, Retry_After=secs)), (0, "[]")), (0, "[]", 1))
                    self.assertEqual(self.pauses, [secs])

    def test_a_retry_after_name_is_read_in_any_case(self):
        self.assertEqual(self.retry((1, gh_i(403, RATE_API_403, Retry_After=17).replace("Retry-After", "retry-after")), (0, "[]")), (0, "[]", 1))
        self.assertEqual(self.pauses, [17])

    def test_a_retry_after_over_900_seconds_waits_900(self):  # the cap: 15 minutes
        for secs in (900, 901, 3600, 86400):
            with self.subTest(retry_after=secs):
                self.pauses.clear()
                self.assertEqual(self.retry((1, gh_i(403, RATE_API_SECONDARY_403, Retry_After=secs)), (0, "[]")), (0, "[]", 1))
                self.assertEqual(self.pauses, [900])

    def test_each_retry_honors_its_own_retry_after(self):
        seq = [(1, gh_i(403, RATE_API_403, Retry_After=s)) for s in (30, 45, 600)]
        self.assertEqual(self.retry(*seq, (0, "[]")), (0, "[]", 3))  # three retries, then the call goes through
        self.assertEqual(self.pauses, [30, 45, 600])

    def test_an_unreadable_retry_after_is_never_a_negative_or_an_oversized_wait(self):  # a guard: the exact wait is free, bounded by 0 and 900
        for value in ("soon", "-5", "0", ""):
            with self.subTest(retry_after=value):
                self.pauses.clear()
                self.assertEqual(self.retry((1, gh_i(403, RATE_API_403, Retry_After=value)), (0, "[]")), (0, "[]", 1))
                self.assertEqual(len(self.pauses), 1)
                self.assertTrue(0 <= self.pauses[0] <= 900, self.pauses)

    def test_a_header_like_line_outside_a_gh_i_block_never_changes_the_rate_wait(self):  # a guard: no status line ahead of it, so it is text, not a header
        for text in (R429, RATE_403, RATE_SECONDARY_403, RATE_GQL_ALREADY):
            for header in ("Retry-After: 5", "retry-after: 17", "Retry-After: 600"):
                with self.subTest(text=text[:40], header=header):
                    self.pauses.clear()
                    self.assertEqual(self.retry((1, header + "\n" + text), (0, "[]")), (0, "[]", 1))
                    self.assertEqual(self.pauses, [60])

    # Host.gh: no gh command it runs prints headers, so a header-like line is text, near, far or past.
    def test_a_header_like_reset_time_outside_a_gh_i_block_never_changes_the_rate_wait_on_a_429_or_a_rate_limit_403(self):  # a guard
        for text in (R429, RATE_403):
            for header in (f"X-Ratelimit-Reset: {int(self.NOW) + 5}", f"X-Ratelimit-Reset: {int(self.NOW) + 23}",
                           f"X-RateLimit-Reset: {int(self.NOW) + 3600}"):
                with self.subTest(text=text[:40], header=header):
                    self.pauses.clear()
                    self.replies((1, header + "\n" + text), (0, "[]"))
                    self.assertEqual(self.host().gh(["run", "list"]), (0, "[]"))
                    self.assertEqual(self.pauses, [60])

    def test_a_header_like_reset_time_already_past_waits_the_rate_wait_never_a_negative_time(self):  # a guard
        self.replies((1, f"X-Ratelimit-Reset: {int(self.NOW) - 100}\n" + R429), (0, "[]"))
        self.host().gh(["run", "list"])
        self.assertEqual(self.pauses, [60])

    def test_a_rate_limit_waits_the_rate_wait_whatever_its_timestamp_says(self):
        self.replies((1, RATE_403), (0, "[]"))  # "timestamp 2026-10-14 12:26:42 UTC" is the request's time, not a reset
        self.host().gh(["run", "list"])
        self.assertEqual(self.pauses, [60])

    def test_a_rate_limit_that_never_clears_is_a_net_stop_after_three_retries(self):  # (e)
        self.replies((1, RATE_403))
        with self.assertRaises(merge.NetStop) as cm:
            self.host().gh(["run", "list"])
        self.assertEqual(self.calls, 4)
        self.assertEqual(self.pauses, [60, 300, 900])
        self.assertIn("API rate limit exceeded", str(cm.exception))  # the stop shows gh's own words

    def test_a_plain_403_is_returned_at_once_by_host_gh(self):  # (d): a guard
        self.replies((1, PLAIN_403))
        self.assertEqual(self.host().gh(["run", "list"]), (1, PLAIN_403))
        self.assertEqual((self.calls, self.pauses), (1, []))

    def test_a_rate_wait_in_host_gh_prints_one_line_before_the_wait(self):
        self.replies((1, RATE_403), (0, "[]"))
        buf, snapshots = io.StringIO(), []
        host = merge.Host(required=["checks"], base="main", minute=60, now=lambda: self.NOW, pause=lambda s: snapshots.append(buf.getvalue()))
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            self.assertEqual(host.gh(["run", "list"]), (0, "[]"))
        assert_one_rate_wait_line(self, buf.getvalue(), snapshots)

    def test_each_rate_wait_in_host_gh_prints_its_own_line_naming_the_call_and_the_wait(self):
        self.replies(*([(1, RATE_403)] * 3), (0, "[]"))
        buf, snapshots = io.StringIO(), []
        host = merge.Host(required=["checks"], base="main", minute=60, now=lambda: self.NOW, pause=lambda s: snapshots.append(buf.getvalue()))
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            self.assertEqual(host.gh(["run", "list"]), (0, "[]"))
        assert_rate_wait_lines(self, buf.getvalue(), snapshots, [60, 300, 900], "gh run list")

    def test_a_plain_403_prints_no_wait_line(self):  # control
        self.replies((1, PLAIN_403))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            self.assertEqual(self.host().gh(["run", "list"]), (1, PLAIN_403))
        self.assertNotRegex(buf.getvalue(), r"(?i)\bwait")

    # Host.gh and the lock: before_wait runs before each rate wait and decides it. The clock moves on with each pause, so the waits add up as they do in a run.
    def test_before_wait_runs_before_each_rate_wait_and_the_merge_goes_on(self):
        seen = []
        host, clock = self.clocked_host(before_wait=lambda wait: seen.append((wait, clock.now(), list(clock.pauses))))
        self.replies(*([(1, RATE_403)] * 3), (0, "[]"))
        self.assertEqual(host.gh(["run", "list"]), (0, "[]"))
        self.assertEqual(clock.pauses, [60, 300, 900])
        self.assertEqual(seen, [(60, self.NOW, []), (300, self.NOW + 60, [60]), (900, self.NOW + 360, [60, 300])])  # the wait, the clock and the pauses so far: each hook call comes before its own pause

    def test_host_gh_stops_with_a_net_stop_when_the_lock_cannot_be_extended_for_a_wait(self):
        def refuse(wait):
            if wait == 900:
                raise merge.NetStop("cannot extend the merge lock on main for a wait of 900 s. Run again.")
        host, clock = self.clocked_host(before_wait=refuse)
        self.replies((1, RATE_403))
        with self.assertRaises(merge.NetStop) as cm:
            host.gh(["run", "list"])
        self.assertEqual(clock.pauses, [60, 300])
        self.assertEqual(self.calls, 3)  # no fourth try: the stop comes in place of the third wait
        self.assertRegex(str(cm.exception), r"(?i)merge lock")  # the stop says why: the lock could not be extended
        self.assertIn("API rate limit exceeded", str(cm.exception))  # and shows gh's own words

    def test_host_gh_never_starts_a_rate_wait_when_the_first_extension_fails(self):
        def refuse(wait):
            raise merge.NetStop("cannot extend the merge lock on main for a wait of 60 s. Run again.")
        host, clock = self.clocked_host(before_wait=refuse)
        self.replies((1, RATE_403))
        with self.assertRaises(merge.NetStop) as cm:
            host.gh(["run", "list"])
        self.assertEqual((clock.pauses, self.calls), ([], 1))
        self.assertRegex(str(cm.exception), r"(?i)merge lock")

    def test_a_plain_network_error_never_runs_before_wait(self):  # a guard: only a rate wait needs the lock extended; a 5 s network pause is inside any lock
        calls = []
        host, clock = self.clocked_host(before_wait=calls.append)
        self.replies((1, NET_TLS), (0, "[]"))
        self.assertEqual(host.gh(["run", "list"]), (0, "[]"))
        self.assertEqual((calls, clock.pauses), ([], [merge.NET_PAUSE]))

    # (f) two helpers the extension leans on: the header block of an empty reply, and a whole-second wait
    def test_a_gh_i_reply_with_headers_and_no_body_has_an_empty_body(self):  # the empty body leaves no blank line after the headers
        for out in ("HTTP/2 200\nx: y", "HTTP/2.0 204 No Content\r\nX-Y: z\r\n"):
            with self.subTest(out=out):
                headers, body = merge.split_headers(out)
                self.assertEqual(body, "")
                self.assertEqual(len(headers), 1, headers)
        self.assertEqual(merge.split_headers("HTTP/2 200\nx: y"), ({"x": "y"}, ""))

    def test_a_reply_with_a_blank_line_still_splits_at_it(self):  # a guard: the empty-body rule leaves the normal block alone
        self.assertEqual(merge.split_headers("HTTP/2.0 403 Forbidden\r\nRetry-After: 17\r\n\r\nbody\nmore"), ({"retry-after": "17"}, "body\nmore"))

    def test_the_rate_wait_is_a_whole_number_of_seconds_whatever_the_clock_reads(self):
        reset = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1100"}
        for now, want in ((1000.0, 100), (1000.4, 100), (1000.6, 100), (999.5, 101)):  # 99.4 s, 99.6 s and 100.5 s round up
            with self.subTest(now=now):
                got = merge.rate_wait(reset, 1, now)
                self.assertEqual((got, type(got)), (want, int))
        got = merge.rate_wait({"retry-after": "12"}, 1, 1000.5)
        self.assertEqual((got, type(got)), (12, int))
        got = merge.rate_wait({}, 2, 1000.5)
        self.assertEqual((got, type(got)), (300, int))  # the ladder rung
        got = merge.rate_wait({"x-ratelimit-remaining": "0", "x-ratelimit-reset": "9999"}, 1, 1000.5)
        self.assertEqual((got, type(got)), (900, int))  # the cap

class GhLockReadRetry(unittest.TestCase):
    """GhLock.read on a network error: retried as GitLock is. merge.sh is the only seam,
    so the test holds wherever the retry sits, in read or in api."""
    def run_read(self, replies):
        """The ref reads answer `replies` in order, the last repeats. -> the read's result. self.reads and self.pauses count the calls."""
        seq, self.reads, self.pauses = list(replies), 0, []
        def fake_sh(args, cwd=None, input=None, env=None):
            args = without_include(args)
            if args[:2] == ["gh", "api"] and "/git/ref/heads/merge-lock/" in args[2]:
                self.reads += 1
                return seq.pop(0) if len(seq) > 1 else seq[0]
            if args[:2] == ["gh", "api"] and "/git/commits/" in args[2]:
                return 0, "merge lock\nexpires: 2000\nowner: x"  # a live lock, held until 2000
            return 1, "unhandled " + " ".join(args)
        with unittest.mock.patch.object(merge, "sh", fake_sh):
            lock = merge.GhLock(now=lambda: 1000.0)
            lock.pause = self.pauses.append
            return lock.read("main")

    def read_that_must_not_stop(self, replies):
        try:
            return self.run_read(replies)
        except merge.Stop as e:
            self.fail(f"GhLock.read stopped on a network error after {self.reads} read(s): {e}")

    def test_a_transient_gh_server_error_on_the_lock_read_is_retried_and_the_read_succeeds(self):
        got = self.read_that_must_not_stop([(1, "gh: Server Error (HTTP 502)"), (0, "sha1")])
        self.assertEqual(got[0], "sha1")
        self.assertEqual(self.reads, 2)
        self.assertEqual(len(self.pauses), 1)

    def test_a_gh_server_error_that_keeps_failing_on_the_lock_read_is_a_net_stop_after_three_retries(self):
        try:
            self.run_read([(1, "gh: Server Error (HTTP 502)")])
        except merge.NetStop:
            pass
        except merge.Stop as e:
            self.fail(f"a network error stopped the lock read as a plain Stop, not a NetStop: {e}")
        else:
            self.fail("GhLock.read returned without a stop")
        self.assertEqual(self.reads, 4)  # one try and three retries
        self.assertEqual(len(self.pauses), 3)

    def test_a_404_on_the_lock_read_means_no_lock_and_is_not_retried(self):
        self.assertIsNone(self.read_that_must_not_stop([(1, "gh: Not Found (HTTP 404)")]))
        self.assertEqual(self.reads, 1)
        self.assertEqual(self.pauses, [])

class GitLockReadExhaustion(unittest.TestCase):
    """GitLock.read on a failing ls-remote. A network text stops with NetStop after three retries. Any other text stops at once."""
    def read_fails(self, reply):
        """-> (the Stop the read raised, its ls-remote calls, its retry pauses)."""
        calls, pauses = [], []
        def fake_git(cwd, *a, input=None):
            calls.append(a)
            return reply
        with unittest.mock.patch.object(merge, "git", fake_git):
            lock = merge.GitLock("unused", now=lambda: 1000.0, pause=pauses.append)
            with self.assertRaises(merge.Stop) as cm:
                lock.read("main")
        return cm.exception, calls, pauses

    def test_a_network_text_on_the_lock_read_is_a_net_stop_after_three_retries(self):
        exc, calls, pauses = self.read_fails((1, NET_HOST))
        self.assertIsInstance(exc, merge.NetStop, str(exc))
        self.assertEqual(len(calls), 4, calls)  # one try and three retries
        self.assertEqual(len(pauses), 3)

    def test_fatal_not_a_repository_on_the_lock_read_is_a_plain_stop_after_one_call(self):
        exc, calls, pauses = self.read_fails((128, "fatal: not a repository (or any of the parent directories): .git"))
        self.assertNotIsInstance(exc, merge.NetStop)
        self.assertEqual(len(calls), 1, calls)
        self.assertEqual(pauses, [])

@windows_slice
class ResolveProgram(unittest.TestCase):
    """resolve_program (merge.py): bash never resolves under System32; a bare name finds its .cmd shim."""
    @unittest.skipUnless(os.name == "nt", "the System32 WSL stub is a Windows case")
    def test_bash_skips_system32(self):
        t = tempfile.mkdtemp(prefix="test-resolve-"); self.addCleanup(shutil.rmtree, t, True)
        sysroot = os.path.join(t, "Win"); good = os.path.join(t, "good")
        for d in (os.path.join(sysroot, "System32"), good):
            os.makedirs(d); put(os.path.join(d, "bash.exe"), "x")
        env = {"PATH": os.pathsep.join([os.path.join(sysroot, "System32"), good]), "SystemRoot": sysroot,
               "ProgramFiles": os.path.join(t, "none")}
        self.assertEqual(merge.resolve_program("bash", env), os.path.join(good, "bash.exe"))

    @unittest.skipUnless(os.name == "nt", "PATHEXT lookup of a .cmd shim is a Windows case")
    def test_a_bare_name_finds_its_cmd_shim(self):
        t = tempfile.mkdtemp(prefix="test-resolve-"); self.addCleanup(shutil.rmtree, t, True)
        put_shim(os.path.join(t, "fakeprog"), "x")
        got = merge.resolve_program("fakeprog", {"PATH": t})
        self.assertEqual(os.path.normcase(got), os.path.normcase(os.path.join(t, "fakeprog.cmd")))

    def test_the_program_files_git_bash_wins_over_system32(self):
        t = tempfile.mkdtemp(prefix="test-resolve-"); self.addCleanup(shutil.rmtree, t, True)
        sysroot = os.path.join(t, "Win"); pf = os.path.join(t, "PF")
        git_bash = os.path.join(pf, "Git", "bin", "bash.exe")
        for f in (os.path.join(sysroot, "System32", "bash.exe"), git_bash):
            os.makedirs(os.path.dirname(f)); put(f, "x")
        env = {"PATH": os.path.join(sysroot, "System32"), "SystemRoot": sysroot, "ProgramFiles": pf}
        with unittest.mock.patch.object(merge.os, "name", "nt"):
            self.assertEqual(merge.resolve_program("bash", env), git_bash)

@windows_slice
@unittest.skipUnless(os.name == "nt", "pid_alive's kernel32 branches exist only on Windows")
class PidAlive(unittest.TestCase):
    """pid_alive (merge.py) on Windows, with kernel32 faked so it runs on any OS."""
    def probe(self, handle, last_error=0, exit_code=259):
        k = unittest.mock.Mock()
        k.OpenProcess.return_value = handle
        k.GetExitCodeProcess.side_effect = lambda h, ref: (setattr(ref._obj, "value", exit_code), 1)[1]
        with unittest.mock.patch.object(merge.os, "name", "nt"), \
             unittest.mock.patch("ctypes.WinDLL", create=True, return_value=k) as k_loader, \
             unittest.mock.patch("ctypes.get_last_error", create=True, return_value=last_error):
            result = merge.pid_alive(1234)
        k_loader.assert_called_once_with("kernel32", use_last_error=True)
        return result, k

    def test_access_denied_reads_alive(self):
        alive, k = self.probe(0, last_error=5)
        self.assertTrue(alive)
        k.GetExitCodeProcess.assert_not_called()

    def test_a_process_that_exited_reads_dead_and_its_handle_is_closed(self):
        alive, k = self.probe(77, exit_code=1)
        self.assertFalse(alive)
        k.CloseHandle.assert_called_once_with(77)

    def test_a_still_active_process_reads_alive_and_its_handle_is_closed(self):
        alive, k = self.probe(77, exit_code=259)
        self.assertTrue(alive)
        k.CloseHandle.assert_called_once_with(77)

@windows_slice
class SliceSelector(unittest.TestCase):
    """MERGE_TESTS=windows-slice keeps only the marked tests; no value keeps all; an unknown value stops."""
    def all_tests(self):
        return unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])

    def marked(self, t):
        return bool(t.__class__.__dict__.get("_windows_slice") or getattr(getattr(t, t._testMethodName), "_windows_slice", False))

    def test_the_slice_keeps_only_marked_tests_and_all_of_them(self):
        full = list(iter_tests(self.all_tests()))
        got = list(iter_tests(select_tests(self.all_tests(), "windows-slice")))
        self.assertTrue(0 < len(got) < len(full), (len(got), len(full)))
        self.assertTrue(all(self.marked(t) for t in got))
        self.assertEqual(len(got), sum(self.marked(t) for t in full))

    def test_the_slice_holds_the_windows_probe_and_the_bash_resolver_cases(self):
        """The exact slice, bar this class. Dropping or adding a mark must change this list on purpose."""
        got = {f"{t.__class__.__name__}.{t._testMethodName}" for t in iter_tests(select_tests(self.all_tests(), "windows-slice"))
               if t.__class__.__name__ != "SliceSelector"}
        self.assertEqual(got, {
            "ClaudeMdFlag.test_a_name_outside_cp1252_on_a_piped_stdout_still_flags_and_runs_every_step_after_the_merge",
            "Flow.test_afterMerge_runs_in_git_bash_not_the_wsl_stub",
            "Flow.test_full_merge_claims_pushes_merges_syncs_cleans",
            "GhHalf.test_an_empty_required_list_is_refused",
            "LockHolder.test_a_lock_with_no_platform_line_reads_cannot_tell_never_dead",
            "LockHolder.test_a_lock_on_this_host_whose_pid_is_gone_is_taken_over_with_one_line",
            "LockHolder.test_the_lock_records_the_holder_and_a_second_run_sees_it_alive",
            "LockHolder.test_the_same_host_name_on_another_platform_reads_cannot_tell_never_dead",
            "LockHolder.test_windows_liveness_never_calls_os_kill",
            "PidAlive.test_a_process_that_exited_reads_dead_and_its_handle_is_closed",
            "PidAlive.test_a_still_active_process_reads_alive_and_its_handle_is_closed",
            "PidAlive.test_access_denied_reads_alive",
            "ResolveProgram.test_a_bare_name_finds_its_cmd_shim",
            "ResolveProgram.test_bash_skips_system32",
            "ResolveProgram.test_the_program_files_git_bash_wins_over_system32"})

    def test_no_value_keeps_every_test(self):
        full = len(list(iter_tests(self.all_tests())))
        self.assertEqual(len(list(iter_tests(select_tests(self.all_tests(), "")))), full)

    def test_an_unknown_value_fails_loudly_and_runs_nothing(self):
        with self.assertRaises(SystemExit) as cm:
            select_tests(self.all_tests(), "windows_slice")
        self.assertIn("MERGE_TESTS", str(cm.exception))
        r = subprocess.run([sys.executable, os.path.abspath(__file__)], capture_output=True, text=True,
                           env=dict(os.environ, MERGE_TESTS="bogus"), timeout=60)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("MERGE_TESTS", r.stdout + r.stderr)
        self.assertNotIn("Ran ", r.stdout + r.stderr)

class ShardSelector(unittest.TestCase):
    """MERGE_SHARD=<i>/<n> splits a selection into n disjoint shards that together hold every test."""
    def all_tests(self):
        return unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])

    def ids(self, suite):
        return [t.id() for t in iter_tests(suite)]

    def test_the_shards_are_disjoint_and_hold_every_test(self):
        for base in (self.all_tests, lambda: select_tests(self.all_tests(), "windows-slice")):
            full = self.ids(base())
            for n in (1, 2, 3, 4):
                shards = [self.ids(select_shard(base(), f"{i}/{n}")) for i in range(1, n + 1)]
                self.assertEqual(sorted(sum(shards, [])), sorted(full), n)
                self.assertTrue(all(abs(len(a) - len(b)) <= 1 for a in shards for b in shards), n)

    def test_no_value_keeps_every_test(self):
        self.assertEqual(self.ids(select_shard(self.all_tests(), "")), self.ids(self.all_tests()))

    def test_a_bad_value_fails_loudly_and_runs_nothing(self):
        for bad in ("0/2", "3/2", "1", "1/0", "a/b", "1/2/3"):
            with self.assertRaises(SystemExit) as cm:
                select_shard(self.all_tests(), bad)
            self.assertIn("MERGE_SHARD", str(cm.exception))
        r = subprocess.run([sys.executable, os.path.abspath(__file__)], capture_output=True, text=True,
                           env=dict(os.environ, MERGE_SHARD="2/1"), timeout=60)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("MERGE_SHARD", r.stdout + r.stderr)
        self.assertNotIn("Ran ", r.stdout + r.stderr)

class TimedLines(io.StringIO):
    """stdout that stamps each `merge: ` line with the fake clock at the moment it is written."""
    def __init__(self, clock):
        super().__init__()
        self.clock, self.lines = clock, []

    def write(self, s):
        if s.startswith("merge: "):
            self.lines.append((self.clock[0], s.rstrip("\n")))
        return super().write(s)

READ_SECONDS = 2  # fake time one gh read takes

class ClockedHost(merge.Host):
    """Host with no gh and a fake clock. `checks_at(t)` gives the check buckets at fake time t; `head_at(t)` the head."""
    def __init__(self, checks_at, head_at=lambda t: "sha"):
        self.clock, self.pauses = [0.0], []
        self.checks_at, self.head_at = checks_at, head_at
        super().__init__(required=["checks"], base="main", minute=60, now=lambda: self.clock[0], pause=self.advance)

    def advance(self, s):
        self.pauses.append(s)
        self.clock[0] += s
        assert len(self.pauses) < 500, "the wait never ended"

    def read(self):
        """Each fake gh read costs READ_SECONDS of fake time, as a real call does."""
        self.clock[0] += READ_SECONDS

    def pr(self, n, *a, **k):
        self.read()
        return {"head": self.head_at(self.clock[0]), "branch": "feat", "base": "main", "state": "OPEN",
                "mergeable": "MERGEABLE", "merge_state": "CLEAN", "draft": False}

    def checks(self, n, *a, **k):
        self.read()
        return self.checks_at(self.clock[0])

    def runs(self, sha):
        self.read()
        return []

class WaitProgress(unittest.TestCase):
    """The wait prints progress: a `merge: waiting on` line at first sight, on a change of the pending set, and at least every 120 s."""
    def wait(self, host, deadline, prior=None):
        """-> (ok, why, merge lines, waiting lines, end time). Every `merge: ` line is stamped with fake time."""
        out = TimedLines(host.clock)
        with contextlib.redirect_stdout(out):
            ok, why = host.wait_checks(7, "sha", deadline, prior=prior)
        return ok, why, out.lines, [(t, l) for t, l in out.lines if l.startswith("merge: waiting on")], host.clock[0]

    def assert_gaps_within(self, lines, start, end, bound=135):
        """No quiet gap between start, each `merge:` line and end exceeds bound: 120 s plus one pass of the loop."""
        marks = [start] + [t for t, _ in lines] + [end]
        gaps = [b - a for a, b in zip(marks, marks[1:])]
        self.assertLessEqual(max(gaps), bound, f"longest quiet gap {max(gaps):.0f} s; lines at {[round(t) for t, _ in lines]}")

    def test_a_ten_minute_pending_wait_never_goes_120_seconds_without_a_line(self):
        host = ClockedHost(lambda t: {"checks": [("pending" if t < 600 else "pass", "")]})
        ok, why, lines, waits, end = self.wait(host, 15)
        self.assertTrue(ok, why)
        self.assertTrue(waits, "no `merge: waiting on` line during the 10-minute wait")
        self.assertIn("checks", waits[0][1])  # the first line names the pending check
        self.assert_gaps_within(lines, 0.0, end)

    def test_a_lagging_head_never_goes_120_seconds_without_a_line(self):
        # The head reads as the prior one for 600 s; the checks are pending until 900 s.
        host = ClockedHost(lambda t: {"checks": [("pending" if t < 900 else "pass", "")]},
                           head_at=lambda t: "old" if t < 600 else "sha")
        ok, why, lines, _, end = self.wait(host, 30, prior="old")
        self.assertTrue(ok, why)
        self.assert_gaps_within(lines, 0.0, end)

    def test_a_change_in_the_pending_set_prints_at_once(self):
        def checks_at(t):
            if t < 60:
                return {"checks": [("pending", "")]}
            if t < 300:
                return {"checks": [("pending", "")], "design": [("pending", "")]}
            return {"checks": [("pass", "")], "design": [("pass", "")]}
        host = ClockedHost(checks_at)
        ok, why, _, waits, _ = self.wait(host, 15)
        self.assertTrue(ok, why)
        design = [t for t, l in waits if "design" in l]
        # The change is first read at about 64 s (a read costs 2 s, the loop pauses 60 s). It must print before the next 60 s pass.
        self.assertTrue(design and design[0] < 120, f"a new pending check named at {design[:1]}; lines at {[round(t) for t, _ in waits]}")

    def test_a_wait_that_is_green_on_the_first_read_prints_no_waiting_line(self):
        host = ClockedHost(lambda t: {"checks": [("pass", "")]})
        ok, why, _, waits, _ = self.wait(host, 15)
        self.assertTrue(ok, why)
        self.assertEqual(waits, [])

    def test_a_green_wait_says_what_it_checks_before_the_first_read(self):
        """A start line, not a waiting line: the wait names the checks it reads before its first gh call (fake time 0)."""
        host = ClockedHost(lambda t: {"checks": [("pass", "")]})
        ok, why, lines, _, _ = self.wait(host, 15)
        self.assertTrue(ok, why)
        self.assertTrue(lines and lines[0][0] < READ_SECONDS, f"no line before the first read; lines {lines}")
        self.assertIn("checks", lines[0][1])

class AbsentRequiredCheck(unittest.TestCase):
    """c189 part 2: a required check no run reports ends the wait at once, once every reported check has ended (#746: the pinned checks* names)."""
    wait = WaitProgress.wait

    def host(self, checks_at):
        h = ClockedHost(checks_at)
        h.required = ["checks", "needed"]
        return h

    def test_an_absent_required_check_stops_the_wait_before_the_deadline_naming_it(self):
        host = self.host(lambda t: {"checks": [("pass", "")]})
        ok, why, _, _, end = self.wait(host, 55)
        self.assertFalse(ok)
        self.assertIn("needed", why)
        self.assertLess(end, 300, f"waited {end:.0f} s")

    def test_an_absent_required_check_does_not_stop_the_wait_while_another_check_runs(self):
        host = self.host(lambda t: {"checks": [("pending" if t < 400 else "pass", "")], **({"needed": [("pass", "")]} if t >= 400 else {})})
        ok, why, *_ = self.wait(host, 55)
        self.assertTrue(ok, why)

    def test_a_required_status_posted_45_seconds_after_the_last_job_ended_is_waited_for(self):  # an external status can lag the jobs by a minute
        host = self.host(lambda t: {"checks": [("pass", "")], **({"needed": [("pass", "")]} if t >= 45 else {})})
        ok, why, *_ = self.wait(host, 55)
        self.assertTrue(ok, why)

    def test_a_pending_workflow_run_keeps_the_wait_going(self):
        host = self.host(lambda t: {"checks": [("pass", "")], **({"needed": [("pass", "")]} if t >= 400 else {})})
        host.runs = lambda sha: [{"name": "ci", "status": "in_progress" if host.clock[0] < 400 else "completed", "conclusion": None if host.clock[0] < 400 else "success"}]
        ok, why, *_ = self.wait(host, 55)
        self.assertTrue(ok, why)

    def test_a_required_check_created_late_inside_the_settle_pause_is_waited_for(self):
        host = self.host(lambda t: {"checks": [("pass", "")], **({"needed": [("pass", "")]} if t >= 20 else {})})
        ok, why, *_ = self.wait(host, 55)
        self.assertTrue(ok, why)

    def test_a_head_with_no_check_reported_yet_is_waited_on_to_the_deadline(self):  # GitHub lags a push
        host = self.host(lambda t: {})
        ok, why, _, _, end = self.wait(host, 5)
        self.assertFalse(ok)
        self.assertIn("deadline of 5 minutes", why)

class SilentWait(Env):
    """Silence: merge printed only the launch line for minutes. A long step printed
    nothing before it started. A `gh` call whose helper keeps its stdout open also blocks silently (measured:
    subprocess.run waits for the pipe, not the child). Each case holds one call that way and checks that merge
    prints a line before the call blocks. Not a GhHalf subclass: the GhHalf tests must not run twice."""
    set, calls, gh_host, go = GhHalf.set, GhHalf.calls, GhHalf.gh_host, GhHalf.go

    def setUp(self):  # the fake-gh setup of GhHalf.setUp, without its tests
        Env.setUp(self)
        install_gh_shim(self)
        self.ticks, self.paused, self.at_pause = 0, [], []
        self.set(checks_seq=[[("checks", "pass", "")]])

    def hold_run(self, on, seconds, host):
        """Run the merge in a thread, hold the first `on` call, and read stdout while it is held.
        -> (text printed while held, rc or the thread's error, text printed in all)."""
        out, err, result = io.StringIO(), io.StringIO(), {}
        self.set(hold={"on": on, "seconds": seconds})

        def go():
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    result["rc"] = merge.main(["7", "--confirm"], host=host, lock=self.lock)
            except BaseException as e:  # a crash in the thread must fail the test, not vanish
                result["error"] = repr(e)

        cwd = os.getcwd()
        os.chdir(self.co)
        try:
            t = threading.Thread(target=go, daemon=True)
            t.start()
            marker = os.path.join(self.state, "held")
            stop = time.time() + 60
            while not os.path.exists(marker) and time.time() < stop:
                time.sleep(0.05)
            self.assertTrue(os.path.exists(marker), "the held call never started")
            time.sleep(4)  # a human watching the terminal gets this long before anything is said
            seen = out.getvalue()
            t.join(seconds + 60)
            self.assertFalse(t.is_alive(), "the merge did not end")
        finally:
            os.chdir(cwd)
        return seen, result.get("rc", result.get("error")), out.getvalue() + err.getvalue()

    def assert_names_the_held_step(self, seen, step):
        """The last line printed while the call was held must say merge is waiting or doing that step. A claim's
        `pushed` line is not that: it says what happened, not what merge is blocked on."""
        last = seen.splitlines()[-1] if seen.strip() else ""
        self.assertRegex(last, r"(?i)waiting|checking|merging", f"while `{step}` was held the last line was {last!r}; printed so far: {seen!r}")

    def test_a_held_check_read_names_its_step_before_it_blocks(self):
        seen, _, _ = self.hold_run("check-runs", 12, self.gh_host())
        self.assert_names_the_held_step(seen, "the check runs read")

    def test_a_held_merge_call_names_its_step_before_it_blocks(self):
        seen, rc, out = self.hold_run("merge", 12, self.gh_host())
        self.assertEqual(rc, 0, out)
        self.assert_names_the_held_step(seen, "the merge call")

    def test_red_required_check_beside_skipped_jobs_refuses_at_once(self):
        self.set(checks_seq=[[("checks", "fail", "https://x/checks"), ("scope", "skipping", ""), ("check-windows", "skipping", "")]],
                 runs_seq=[[("checks", "completed", "failure"), ("check-windows", "completed", "skipped")]])
        rc, out = self.go(required=("checks", "scope"))
        self.assertEqual(rc, 1, out)
        self.assertIn("a check is red", out)
        self.assertEqual(self.paused, [], "a red head waited before it refused")
        self.assertNotIn(MERGE_CALL, self.calls())

    def test_zero_contexts_and_a_required_name_with_no_run_say_what_they_wait_on(self):
        self.set(checks_seq=[[]], runs_seq=[[("check", "in_progress", None)]])
        rc, out = self.go(required=("check",))
        self.assertEqual(rc, 1, out)
        self.assertIn("waiting on check", out)
        self.assertIn("workflow check", out)

_real_threading = threading  # the real module. merge's `threading` name is swapped in the scan cases, this name is not

class TickEvent:
    """Stands in for threading.Event in merge.undo_check. wait() returns only when a test releases a tick,
    so the heartbeat thread runs when the test says so. set() ends it, as a real Event does."""
    def __init__(self):
        self.flag, self.ticks = _real_threading.Event(), _real_threading.Semaphore(0)

    def wait(self, timeout=None):
        self.ticks.acquire()
        return self.flag.is_set()

    def set(self):
        self.flag.set()
        self.ticks.release()

    def is_set(self):
        return self.flag.is_set()

    def tick(self):
        self.ticks.release()

class QuickEvent(_real_threading.Event):
    """A real Event whose wait() ignores its timeout and waits 20 ms: the heartbeat's 60 s pass, made tiny."""
    def wait(self, timeout=None):
        return super().wait(0.02)

class FakeThreading:
    """merge's `threading` name for one undo_check call. Event is the test's stand-in. Thread is the real class,
    and every thread it makes is kept, so the test can join it. Any other name is the real module's."""
    def __init__(self, event_cls):
        self.Event, self.threads = event_cls, []

    def Thread(self, *a, **k):
        t = _real_threading.Thread(*a, **k)
        self.threads.append(t)
        return t

    def __getattr__(self, name):
        return getattr(_real_threading, name)

class ScanProgress(Env):
    """The silent-undo scan (lint/check_silent_undo.py) can run for 14 minutes on a long branch. merge.undo_check
    printed nothing until it ended. It must print a start line with the size of the scan, and an end line.
    The scanner is replaced by a stub here: the cases test merge's lines around the call, not the scan."""

    def run_undo(self):
        """-> (text printed before the scanner was called, text printed in all)."""
        out, seen = io.StringIO(), []
        stub = unittest.mock.MagicMock()

        def scan(cwd, upstream, head, default=None, tool=None, pr_body=""):
            seen.append(out.getvalue())
            return [], []

        stub.check.side_effect = scan
        with unittest.mock.patch.dict(sys.modules, {"check_silent_undo": stub}), contextlib.redirect_stdout(out):
            merge.undo_check(self.co, "origin/main")
        return seen[0], out.getvalue()

    def test_a_start_line_with_the_size_comes_before_the_scan(self):
        before, _ = self.run_undo()
        self.assertRegex(before, r"(?m)^merge: scanning for silent undos \(\d+ commits?", f"printed before the scan: {before!r}")

    def test_the_scan_says_when_it_ends(self):
        _, after = self.run_undo()
        self.assertRegex(after, r"(?m)^merge: silent-undo scan done", f"printed after the scan: {after!r}")

    def stub(self, check=None):
        """A stand-in for lint/check_silent_undo: no finding, no progress hook, and a real Unknown class, so an
        error that is not Unknown reaches merge's finally, not a TypeError in its except clause."""
        s = unittest.mock.MagicMock()
        s.progress, s.Unknown = None, type("Unknown", (Exception,), {})
        s.check.side_effect = check if check is not None else (lambda *a, **k: ([], []))
        return s

    def run_undo_scan(self, stub, event_cls=None, on_line=None):
        """Run merge.undo_check on the test checkout with `stub` as the scanner. event_cls swaps in merge's
        threading.Event. on_line(line, from_main_thread) sees each line merge prints, after it prints. -> the printed text."""
        out, real_say = io.StringIO(), merge.say

        def say(*lines):
            real_say(*lines)
            for line in lines:
                if on_line:
                    on_line(line, _real_threading.current_thread() is _real_threading.main_thread())

        fake = FakeThreading(event_cls or _real_threading.Event)
        with unittest.mock.patch.dict(sys.modules, {"check_silent_undo": stub}), unittest.mock.patch.object(merge, "threading", fake), \
                unittest.mock.patch.object(merge, "say", say), contextlib.redirect_stdout(out):
            try:
                merge.undo_check(self.co, "origin/main")
            finally:
                for t in fake.threads:
                    t.join(1)
        return out.getvalue()

    def test_no_heartbeat_prints_after_the_scan_is_done(self):
        """The race: a beat is due as the scan ends. The done line prints first. Then a tick lets the beat's wait
        return, and the beat prints, before done.set() runs. The done line's hook holds merge until that beat has printed."""
        made, beat_printed = [], _real_threading.Event()

        def make_event():
            made.append(TickEvent())
            return made[-1]

        def on_line(line, from_main):
            if from_main and line.startswith("merge: silent-undo scan done"):
                made[0].tick()
                beat_printed.wait(0.5)
            elif not from_main:
                beat_printed.set()

        out = self.run_undo_scan(self.stub(), event_cls=make_event, on_line=on_line)
        lines = out.splitlines()
        done = [i for i, line in enumerate(lines) if line.startswith("merge: silent-undo scan done")]
        self.assertTrue(done, f"no done line printed: {out!r}")
        self.assertEqual(done[-1], len(lines) - 1, f"printed after the scan was done: {lines[done[-1] + 1:]}")

    def test_a_scan_that_outlasts_the_interval_prints_a_beat_before_it_ends(self):
        """A 20 ms beat (QuickEvent) and a scan that holds until a beat prints, for up to 1 s."""
        beat_printed, during = _real_threading.Event(), []

        def on_line(line, from_main):
            if not from_main and line.startswith("merge: silent-undo scan:"):
                beat_printed.set()

        def check(*a, **k):
            during.append(beat_printed.wait(1))
            return [], []

        out = self.run_undo_scan(self.stub(check), event_cls=QuickEvent, on_line=on_line)
        self.assertEqual(during, [True], f"no beat printed during the scan: {out!r}")

    def test_the_progress_hook_is_cleared_after_a_scan_and_when_the_scan_raises(self):
        # Rows: the scan returns (no check error); the scan raises. Either way the hook must not stay set.
        for check in (None, RuntimeError("scan broke")):
            with self.subTest(scan="raises" if check else "returns"):
                merge.UNDO_MEMO.clear()  # a memo hit skips the scan, so the second row must start empty
                stub = self.stub(check)
                if check is None:
                    self.run_undo_scan(stub)
                else:
                    with self.assertRaises(RuntimeError):
                        self.run_undo_scan(stub)
                self.assertIsNone(stub.progress, "the progress hook stayed set after the scan")

class WaitStepLines(unittest.TestCase):
    """Each long step prints its name before its first gh call can block: the check read and the merge call.
    A probe stands in for `gh`. It snapshots stdout at the first call, then raises. No shim, no git repo."""
    class Probe(Exception):
        pass

    def first_call_text(self, host, step):
        """-> the stdout printed before the first gh call that `step` makes."""
        out, seen = io.StringIO(), []

        def gh(args, cwd=None):
            seen.append(out.getvalue())
            raise self.Probe(args)

        host.gh = gh
        with contextlib.redirect_stdout(out), self.assertRaises(self.Probe):
            step(host)
        self.assertTrue(seen, "no gh call was made")
        return seen[0]

    def test_the_check_step_is_named_before_its_first_gh_read(self):
        host = merge.Host(required="protection", base="main", minute=60, now=lambda: 0.0, pause=lambda s: None)
        before = self.first_call_text(host, lambda h: h.wait_checks(7, "sha", 15))
        self.assertRegex(before, r"(?m)^merge: checking", f"printed before the first gh read: {before!r}")

    def test_the_merge_step_is_named_before_the_merge_call(self):
        host = merge.Host(required=["checks"], base="main", minute=60, now=lambda: 0.0, pause=lambda s: None)
        before = self.first_call_text(host, lambda h: h.merge(7, "merge", "sha"))
        self.assertRegex(before, r"(?m)^merge: merging #7", f"printed before the merge call: {before!r}")

# ---- the records page is rebuilt at merge time --------------------------------------------------------------------

# The records-only mode of lint/hook_catalog.py: it writes docs/records.md and nothing else. The merge
# tool passes it with --root on every run, so a root with catalog parts gets no docs/catalog.md in its merge commit.
RECORDS_ONLY = "--records-only"

FAKE_RECORDS = '''import json, os, sys
a = sys.argv[1:]
root = a[a.index("--root") + 1]
with open(os.environ["RECORDS_CALLS"], "a") as f:
    f.write(json.dumps(a) + "\\n")
if os.path.exists(os.path.join(root, "debts", "bad.md")):
    print("records: debts/bad.md has no What")
    sys.exit(1)
d = os.path.join(root, "debts")
names = sorted(n[:-3] for n in os.listdir(d)) if os.path.isdir(d) else []
os.makedirs(os.path.join(root, "docs"), exist_ok=True)
with open(os.path.join(root, "docs", "records.md"), "w", newline="\\n") as f:
    f.write("records\\n" + "".join("- %s\\n" % n for n in names))
'''
DEBT_TEXT = "# Gap one\n\n- **What.** The check misses one case.\n- **Where.** x\n- **Decision.** none\n- **Retire.** y\n"

def page(*names):
    """The page the fake generator writes for these debts."""
    return "records\n" + "".join("- %s\n" % n for n in names)

def put_lf(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n") as f:
        f.write(text)

class RecordsEnv(Env):
    """Helpers for the records-page cases. Holds no test."""
    def kinds_off(self):
        """The base holds claude-settings' own config: no stamp kinds, so no claim."""
        self.on("main", {".github/stamp.json": json.dumps(dict(CONFIG, kinds=[]))}, "no stamp kinds")
        sh(self.co, "git", "pull", "-q", "--ff-only")
        head_takes_base(self)

    def on(self, branch, files, msg="records"):
        """Push one commit to origin/<branch> from the second clone, as a person or another run would."""
        o = self.other
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", branch, f"origin/{branch}")
        for rel, text in files.items():
            put_lf(os.path.join(o, rel), text)
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-qm", msg); sh(o, "git", "push", "-q", "origin", branch)

    def in_wait(self, action, at=1):
        """Run action as the at-th check wait starts: main moves while the run waits, after the head was read current.
        A move before the run is refused at the start (merge-needs-current-base), so a case that needs main ahead of the head moves it here."""
        actions = getattr(self, "_wait_actions", None)
        if actions is None:
            actions = self._wait_actions = {}
            real = self.host.wait_checks
            def wait(n, sha, d, prior=None):
                act = actions.pop(len(self.host.waits) + 1, None)
                if act:
                    act()
                return real(n, sha, d, prior)
            self.host.wait_checks = wait
        actions[at] = action

    def drop(self, branch, rel, msg):
        """Push one commit to origin/<branch> from the second clone that removes rel, as a person would."""
        o = self.other
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", branch, f"origin/{branch}")
        sh(o, "git", "rm", "-q", rel); sh(o, "git", "commit", "-qm", msg); sh(o, "git", "push", "-q", "origin", branch)

    def rev(self, expr):
        sh(self.co, "git", "fetch", "-q", "origin")
        return sh(self.co, "git", "rev-parse", expr)

    def log1(self, fmt, ref):
        sh(self.co, "git", "fetch", "-q", "origin")
        return sh(self.co, "git", "log", "-1", f"--format={fmt}", ref)

    def tree_names(self, ref):
        sh(self.co, "git", "fetch", "-q", "origin")
        return sh(self.co, "git", "ls-tree", "-r", "--name-only", ref).splitlines()

class RecordsRebuild(RecordsEnv):
    """The records index is rebuilt at merge time, the way record numbers are claimed
    from the slug form at merge: merge.py runs a records generator.

    The contract for merge/merge.py. The seam is confirm() and preview(), beside do_claim and commit_claim.
    - One home: `merge.RECORDS`, the path of lint/hook_catalog.py beside merge/ in the same checkout, as `merge.STAMP` is
      for the stamp engine. The tool brings the generator, so a repo adds no config and no script. These cases patch it.
    - Run `python3 <RECORDS> --root <worktree>`, nothing else, in the detached worktree that holds the head: the tree
      that merges, never the caller's checkout. A non-zero exit is one Stop line starting "merge: " that names the
      generator's reason once. Nothing is pushed, and the lock is freed.
    - When: after the claim, only when the pull request's base is the default branch (the claim's own rule), and also
      when the base config has `kinds: []` or no config at all (claude-settings itself has `kinds: []`). The rebuild
      does not depend on the pull request touching a record: a stale page heals at the next merge.
    - The claim and the rebuild share one commit. With a claim: "Claim record numbers", with its Record-claim trailer, and
      the page in the same commit. Without: the subject "Rebuild the records page", and no Record-claim trailer.
      The order is the claim's: wait on the head first, then commit, push, wait on the new sha. A red check on it
      reverts that commit, as for a claim.
    - Nothing changed in the worktree: no commit, and one wait.
    - Proof before the merge call: after the last fetch of the base, merge origin/<base> into the worktree without a
      commit and run the generator. When it would change the page, the page on the head is stale for the merge result
      (the base moved with a record): refuse with a line that says "records page" and "stale", revert the rebuild
      commit, merge nothing. A base that moved with an unrelated change merges. The lock keeps other tool merges out,
      so only a push that did not use the tool can trip it.
    - The preview prints one line `  records: rebuild ...` or `  records: current`, and presses nothing.
    """
    def setUp(self):
        super().setUp()
        self.calls, self.prog = os.path.join(self.t, "records-calls.log"), os.path.join(self.t, "records.py")
        put(self.prog, FAKE_RECORDS)
        for p in (unittest.mock.patch.object(merge, "RECORDS", self.prog, create=True),  # create: a missing name is a failure, not an error
                  unittest.mock.patch.dict(os.environ, {"RECORDS_CALLS": self.calls})):
            p.start(); self.addCleanup(p.stop)

    def test_a_pr_that_adds_a_debt_gets_the_page_in_the_claim_commit(self):
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT})
        before = self.head()
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.show("main", "docs/records.md"), page("gap-one").strip())
        self.assertEqual(self.claims(), 1)
        self.assertEqual(sh(self.co, "git", "rev-list", "--count", f"{before}..origin/main^2"), "1")  # one commit, claim and page together
        changed = sh(self.co, "git", "show", "--name-only", "--format=", "origin/main^2").splitlines()
        self.assertIn("docs/records.md", changed)
        self.assertIn("docs/decisions/second.md", changed)
        self.assertEqual(self.log1("%(trailers:key=Record-claim,valueonly)", "origin/main^2").strip(), "D-002")

    def test_a_repo_with_no_stamp_kinds_still_gets_the_page(self):
        mark = stamp_marker(self)
        self.kinds_off()
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT})
        before = self.head()
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertFalse(os.path.exists(mark), "stamp.mjs ran")
        self.assertEqual(self.show("main", "docs/records.md"), page("gap-one").strip())
        self.assertEqual(self.log1("%s", "origin/main^2"), "Rebuild the records page")
        self.assertEqual(self.log1("%(trailers:key=Record-claim,valueonly)", "origin/main^2").strip(), "")
        self.assertEqual(sh(self.co, "git", "rev-list", "--count", f"{before}..origin/main^2"), "1")
        (s1, p1), (s2, p2) = self.host.waits  # the claim's order: the head first, then the rebuild commit
        self.assertIsNone(p1)
        self.assertEqual(p2, s1)
        self.assertNotEqual(s1, s2)

    def test_a_stale_page_heals_even_when_the_pr_touches_no_record(self):
        self.kinds_off()
        self.on("feat", {"docs/records.md": page("ghost")})  # a page that names a debt nobody has
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.show("main", "docs/records.md"), page().strip())
        self.assertEqual(self.log1("%s", "origin/main^2"), "Rebuild the records page")

    def test_a_current_page_adds_no_commit_and_waits_once(self):
        self.kinds_off()
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT, "docs/records.md": page("gap-one")})
        before = self.head()
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.rev("origin/main^2"), before)
        self.assertEqual(len(self.host.waits), 1)
        self.assertTrue(os.path.exists(self.calls), "the generator did not run on a page that was already current")

    def test_a_base_that_is_not_the_default_is_left_alone(self):
        # A lane merged into an integration branch must not carry the page, or the
        # lanes conflict on it. The pull request that takes that branch into the default branch rebuilds it.
        sh(self.other, "git", "fetch", "-q", "origin")
        sh(self.other, "git", "push", "-q", "origin", "origin/main:refs/heads/integ")
        self.host.base = "integ"
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT})
        before = self.head()
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertFalse(os.path.exists(self.calls), "the generator ran for a base that is not the default branch")
        self.assertEqual(self.rev("origin/integ^2"), before)
        self.assertNotIn("docs/records.md", self.tree_names("origin/integ"))

    def test_the_generator_runs_in_the_merge_worktree_in_records_only_mode(self):
        # The merge tool runs the records-only mode, RECORDS_ONLY, and no other argument:
        # not `--root <wt>` with no mode flag.
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT})
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertTrue(os.path.exists(self.calls), "the generator never ran")
        ran = [json.loads(l) for l in open(self.calls).read().splitlines()]
        self.assertTrue(ran, "the generator log is empty")
        for args in ran:
            self.assertIn("--root", args, args)
            path = args[args.index("--root") + 1]
            self.assertEqual(set(args), {"--root", path, RECORDS_ONLY}, args)
            self.assertEqual(len(args), 3, args)
            self.assertTrue(os.path.basename(os.path.dirname(path)).startswith("merge-wt-"), path)  # the detached worktree
            self.assertNotEqual(os.path.realpath(path), os.path.realpath(self.co))

    def test_the_preview_says_what_the_merge_will_do_to_the_page_and_presses_nothing(self):
        self.kinds_off()
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT})
        before = self.refs()
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 0, out)
        line = [l for l in out.splitlines() if l.startswith("  records:")]
        self.assertEqual(len(line), 1, out)
        self.assertIn("rebuild", line[0])
        self.assertEqual(self.refs(), before)
        self.assertEqual(self.worktrees(), 1)

    def test_the_preview_says_when_the_page_is_current(self):
        self.kinds_off()
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT, "docs/records.md": page("gap-one")})
        before = self.refs()
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 0, out)
        line = [l for l in out.splitlines() if l.startswith("  records:")]
        self.assertEqual(len(line), 1, out)
        self.assertIn("current", line[0])
        self.assertEqual(self.refs(), before)

    def test_a_generator_that_refuses_stops_with_one_line_and_pushes_nothing(self):
        self.kinds_off()
        self.on("feat", {"debts/bad.md": DEBT_TEXT})
        before = self.head()
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)
        lines = [l for l in out.splitlines() if "debts/bad.md has no What" in l]
        self.assertEqual(len(lines), 1, out)
        self.assertTrue(lines[0].startswith("merge: "), lines[0])
        self.assertNotIn("Traceback", out)
        self.assertEqual(self.head(), before)
        self.assertFalse(self.lock_ref())
        self.assertEqual(self.worktrees(), 1)

    def test_a_red_check_on_the_rebuild_commit_reverts_it(self):
        self.kinds_off()
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT})
        before = self.head()
        self.host.seq = [(True, ""), (False, "a check is red: checks: fail")]  # the head is green, the rebuild commit is red
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)
        self.assertIn("reverted", out)
        self.assertEqual(sh(self.co, "git", "diff", "--stat", before, "origin/feat"), "")  # the branch tree is as it was
        self.assertNotIn("docs/records.md", self.tree_names("origin/main"))
        self.assertFalse(getattr(self.host, "merged", False))
        self.assertFalse(self.lock_ref())
        self.assertEqual(self.worktrees(), 1)

    def test_main_gaining_a_record_during_the_wait_refuses_and_reverts(self):
        # A push that did not use the tool: a debt lands on main and the page is not rebuilt. The merge result
        # would hold a stale page, so the merge must not happen.
        self.kinds_off()
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT})
        before = self.head()
        self.host.on_wait = lambda: self.on("main", {"debts/rival-gap.md": DEBT_TEXT.replace("Gap one", "Rival gap")}, "untooled push")
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)
        self.assertIn("records page", out.lower())
        self.assertIn("stale", out.lower())
        self.assertIn("reverted", out)
        self.assertFalse(getattr(self.host, "merged", False), out)
        self.assertEqual(sh(self.co, "git", "diff", "--stat", before, "origin/feat"), "")
        self.assertFalse(self.lock_ref())
        self.assertEqual(self.worktrees(), 1)

    def test_main_gaining_an_unrelated_change_during_the_wait_refuses_and_reverts(self):
        # The page is fresh, but no run tested the head with main's new commit (merge-needs-current-base).
        self.kinds_off()
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT})
        before = self.head()
        self.host.on_wait = lambda: self.on("main", {"notes.txt": "unrelated\n"}, "untooled push")
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)
        self.assertIn("does not hold origin/main", out)
        self.assertIn("reverted", out)
        self.assertFalse(getattr(self.host, "merged", False), out)
        self.assertEqual(sh(self.co, "git", "diff", "--stat", before, "origin/feat"), "")

    def test_the_preview_on_a_non_default_base_says_nothing_about_the_page(self):
        # The records line sits inside the default-branch block of preview(), so a pull request
        # into another base prints no page line, and confirm does not rebuild there either.
        sh(self.other, "git", "fetch", "-q", "origin")
        sh(self.other, "git", "push", "-q", "origin", "origin/main:refs/heads/integ")
        self.host.base = "integ"
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT})
        before = self.refs()
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 0, out)
        for line in [l for l in out.splitlines() if l.startswith("  records:")]:
            self.assertNotIn("rebuild", line)
        self.assertEqual(self.refs(), before)

    def test_the_preview_and_confirm_agree_on_a_resumed_head_that_needs_the_page(self):
        # The preview says the page needs a rebuild. Confirm skips the rebuild on a resumed head,
        # so the stale page is refused at the end. Both must agree: rebuild when the page lands, not otherwise.
        o = self.other
        sh(o, "git", "fetch", "-q", "origin"); sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        put_lf(os.path.join(o, "docs/decisions/second.md"), record("D-002", "second"))
        sh(o, "git", "add", "-A")
        sh(o, "git", "commit", "-q", "-m", "Claim record numbers", "-m", "Record-claim: D-002")
        sh(o, "git", "push", "-q", "origin", "feat")
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 0, out)
        self.assertIn("already claimed (D-002)", out)  # precondition: the head is a resumed claim
        line = [l for l in out.splitlines() if l.startswith("  records:")]
        self.assertEqual(len(line), 1, out)
        rc, out = self.run_merge("7", "--confirm")
        on_main = "docs/records.md" in self.tree_names("origin/main")
        self.assertEqual("rebuild" in line[0], on_main, f"{line[0]}\n{out}")

class RecordsRebuildReal(RecordsEnv):
    """The same seam with the real generator, lint/hook_catalog.py, as merge.RECORDS defaults to it."""
    def test_the_default_generator_is_the_one_in_this_checkout(self):
        want = os.path.join(HERE, "..", "lint", "hook_catalog.py")
        self.assertTrue(getattr(merge, "RECORDS", None), "merge.RECORDS is not defined")
        self.assertTrue(os.path.samefile(merge.RECORDS, want), merge.RECORDS)

    def test_a_pr_that_adds_a_debt_gets_a_real_page_on_main(self):
        self.kinds_off()
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT})
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        text = self.show("main", "docs/records.md")
        self.assertIn("gap-one", text)
        self.assertIn("../debts/gap-one.md", text)
        self.assertIn("The check misses one case.", text)

    def test_a_repo_with_no_records_gains_no_page_and_no_commit(self):
        # The tool runs the generator on every repo, so an empty repo must stay empty.
        self.kinds_off()
        before = self.head()
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.rev("origin/main^2"), before)
        self.assertNotIn("docs/records.md", self.tree_names("origin/main"))

    def generated(self, ref):
        """The page the real generator writes for the tree at ref, made in a scratch worktree that is removed again."""
        self.rev(ref)  # fetches origin first
        wt = os.path.join(self.t, "gen")
        sh(self.co, "git", "worktree", "add", "-q", "--detach", wt, ref)
        try:
            sh(wt, sys.executable, merge.RECORDS, "--root", wt)
            with open(os.path.join(wt, "docs", "records.md"), encoding="utf-8") as f:
                return f.read().strip()
        finally:
            sh(self.co, "git", "worktree", "remove", "--force", wt)

    def test_a_conflict_only_on_the_page_is_rebuilt_on_the_merged_tree(self):
        # Only the generated page conflicts (add/add on both sides), so the tool rebuilds it on the merged tree and goes on.
        # records_stale() must not read any conflict as "cannot be proved fresh" and revert the claim.
        self.kinds_off()
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT})
        self.in_wait(lambda: self.on("main", {"debts/main-gap.md": DEBT_TEXT.replace("Gap one", "Main gap"), "docs/records.md": "records\n- main-gap\n"},
                                     "a debt and a hand-written page on main"))
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertTrue(getattr(self.host, "merged", False), out)
        page = self.show("main", "docs/records.md")
        self.assertIn("gap-one", page)
        self.assertIn("main-gap", page)
        self.assertEqual(page, self.generated("origin/main"))

    def test_a_conflict_on_another_file_still_refuses_and_reverts(self):
        # A conflict outside the generated page must still stop the merge. This blocks a blanket
        # -X ours or -X theirs that would silence every conflict.
        self.kinds_off()
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT, "notes.txt": "head side\n"}, "a debt and a note")
        before = self.head()
        self.in_wait(lambda: self.on("main", {"notes.txt": "main side\n"}, "a note on main"))
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)
        self.assertIn("does not merge cleanly", out)
        self.assertIn("reverted", out)
        self.assertFalse(getattr(self.host, "merged", False), out)
        self.assertEqual(sh(self.co, "git", "diff", "--stat", before, "origin/feat"), "")
        self.assertFalse(self.lock_ref())
        self.assertEqual(self.worktrees(), 1)

class RecordsScope(RecordsEnv):
    """The real generator, lint/hook_catalog.py. merge.py runs it on every root, so a root with catalog parts must merge, and
    its merge commit may carry the records page alone (the records-only mode, RECORDS_ONLY). The whole
    generator must not refuse a root with hooks/ and no settings.json, nor write docs/catalog.md into the merge."""
    def test_a_page_edited_on_both_sides_with_no_records_stops_the_merge(self):
        # The generator writes nothing here, so the page with conflict markers would be committed and merged.
        self.kinds_off()
        self.on("main", {"docs/records.md": "records\n- base\n"}, "a hand-written page")
        o = self.other
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        sh(o, "git", "merge", "-q", "--no-edit", "origin/main")
        put_lf(os.path.join(o, "docs", "records.md"), "records\n- head\n")
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-qm", "the head edits the page"); sh(o, "git", "push", "-q", "origin", "feat")
        self.in_wait(lambda: self.on("main", {"docs/records.md": "records\n- main\n"}, "main edits the page"))
        before = self.head()
        rc, out = self.run_merge("7", "--confirm")
        self.assertNotIn("<<<<<<<", self.show("main", "docs/records.md"))  # the defect: markers reach main
        self.assertEqual(rc, 1, out)
        lines = [l for l in out.splitlines() if l.startswith("merge: ") and "conflict" in l and "records" in l]
        self.assertTrue(lines, out)
        self.assertFalse(getattr(self.host, "merged", False), out)
        self.assertEqual(self.head(), before)  # nothing pushed to feat
        self.assertFalse(self.lock_ref())
        self.assertEqual(self.worktrees(), 1)

    def test_a_page_edited_on_both_sides_with_nine_char_markers_stops_the_merge(self):
        # The heal must not look for seven-character markers only: a page with nine-character markers passes that look.
        self.kinds_off()
        self.on("main", {".gitattributes": "docs/records.md conflict-marker-size=9\n", "docs/records.md": "records\n- base\n"},
                "a hand-written page, nine-character markers")
        o = self.other
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        sh(o, "git", "merge", "-q", "--no-edit", "origin/main")
        self.assertIn("conflict-marker-size: 9", sh(o, "git", "check-attr", "conflict-marker-size", "--", "docs/records.md"))  # the precondition
        put_lf(os.path.join(o, "docs", "records.md"), "records\n- head\n")
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-qm", "the head edits the page"); sh(o, "git", "push", "-q", "origin", "feat")
        self.in_wait(lambda: self.on("main", {"docs/records.md": "records\n- main\n"}, "main edits the page"))
        before = self.head()
        rc, out = self.run_merge("7", "--confirm")
        self.assertNotIn("<<<<<<<", self.show("main", "docs/records.md"), "the defect: nine-character markers reach main")
        self.assertEqual(rc, 1, out)
        lines = [l for l in out.splitlines() if l.startswith("merge: ") and "conflict" in l and "records" in l]
        self.assertTrue(lines, out)
        self.assertFalse(getattr(self.host, "merged", False), out)
        self.assertEqual(self.head(), before)  # nothing pushed to feat
        self.assertFalse(self.lock_ref())
        self.assertEqual(self.worktrees(), 1)

    def delete_edit_setup(self, head_files=None, generated=False, trailer=False):
        """The page is in the base. The head edits it: by hand, or, when generated, to the generator's own output for the head's
        debts (head_files are written first, so the generator sees them). Then main deletes it. trailer adds the Drops-lines
        trailer on the head's commit, as the heal's merge commit carries it."""
        self.kinds_off()
        self.on("main", {"docs/records.md": "records\n- base\n"}, "a hand-written page")
        o = self.other
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        sh(o, "git", "merge", "-q", "--no-edit", "origin/main")
        for rel, text in (head_files or {}).items():
            put_lf(os.path.join(o, rel), text)
        if generated:
            sh(o, sys.executable, merge.RECORDS, "--root", o, "--records-only")
        else:
            put_lf(os.path.join(o, "docs", "records.md"), "records\n- head\n")
        msg = ["-m", "the head edits the page"] + (["-m", "Drops-lines: docs/records.md -- a generated page, rebuilt by the generator"] if trailer else [])
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-q", *msg); sh(o, "git", "push", "-q", "origin", "feat")
        self.in_wait(lambda: self.drop("main", "docs/records.md", "main drops the page"))

    def test_a_page_deleted_on_main_and_edited_on_the_head_with_no_records_stops_the_merge(self):
        # The generator writes nothing here, and the head's page has no marker, so the head's page would be committed to main.
        self.delete_edit_setup()
        head_before = self.head()
        rc, out = self.run_merge("7", "--confirm")
        self.assertNotIn("docs/records.md", self.tree_names("origin/main"), "the defect: the head's page reaches main")
        self.assertEqual(rc, 1, out)
        lines = [l for l in out.splitlines() if l.startswith("merge: ") and "records" in l]
        self.assertTrue(lines, out)
        self.assertFalse(getattr(self.host, "merged", False), out)
        self.assertEqual(self.log1("%s", "origin/main"), "main drops the page")  # main's tip is the drop: nothing merged
        self.assertEqual(self.head(), head_before)  # nothing pushed to feat
        self.assertFalse(self.lock_ref())
        self.assertEqual(self.worktrees(), 1)

    def test_a_generated_page_deleted_on_main_with_records_rebuilds_and_merges(self):
        # The control: a root with a record folder. The head's page is the generator's output for its debt, and main
        # deletes the page. The rebuild should go on. The silent-undo check refuses the head's commit: it drops a base line and
        # carries no Drops-lines trailer. The heal's merge commit carries one, and the next case shows it goes through with it.
        self.delete_edit_setup({"debts/gap-one.md": DEBT_TEXT}, generated=True)
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertTrue(getattr(self.host, "merged", False), out)
        self.assertIn("gap-one", self.show("main", "docs/records.md"))

    def test_a_generated_page_with_a_drops_trailer_deleted_on_main_with_records_rebuilds_and_merges(self):
        # Green control, as the heal's merge commit does it: the same head commit with the Drops-lines trailer. The page is generated,
        # so the drop of a base line is excused, and the merge goes on.
        self.delete_edit_setup({"debts/gap-one.md": DEBT_TEXT}, generated=True, trailer=True)
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertTrue(getattr(self.host, "merged", False), out)
        self.assertIn("gap-one", self.show("main", "docs/records.md"))

    def test_a_root_with_hooks_and_no_settings_merges(self):
        # The generator must not stop on "hook_catalog: cannot read settings.json": the records page can be rebuilt.
        self.kinds_off()
        self.on("feat", {"hooks/guard.sh": "#!/bin/sh\necho hi\n", "debts/gap-one.md": DEBT_TEXT})
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertTrue(getattr(self.host, "merged", False), out)
        self.assertIn("gap-one", self.show("main", "docs/records.md"))
        changed = sh(self.co, "git", "diff", "--name-only", "origin/main^1", "origin/main").split()  # the merge commit
        self.assertIn("docs/records.md", changed)
        self.assertNotIn("docs/catalog.md", changed, changed)  # no generated catalog page: the records-only mode

    def test_the_merge_commit_carries_no_catalog_page(self):
        # The root renders a catalog, so the generator would write docs/catalog.md and the merge would bring it in.
        self.kinds_off()
        self.on("feat", {"settings.json": "{}\n", "hooks/.gitkeep": "", "skills/.gitkeep": "",
                         "decisions/agent-model-cap.md": "# Agent model cap\n\nOwner ruling. The table names each role model.\n",
                         "debts/gap-one.md": DEBT_TEXT})
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertTrue(getattr(self.host, "merged", False), out)
        self.rev("origin/main")  # fetches
        changed = sh(self.co, "git", "diff", "--name-only", "origin/main^1", "origin/main").split()
        self.assertIn("docs/records.md", changed)
        self.assertNotIn("docs/catalog.md", changed, changed)

class RecordsHeal(RecordsEnv):
    """The keep paths of the heal wait in confirm(): the third wait of a run, on the merge commit that heals the page. The
    fake generator writes the page, so the heal is a real conflict on docs/records.md. Each push or red check fires on the
    third wait only (len(host.waits) == 3). These pin the keep paths."""
    def setUp(self):
        super().setUp()
        self.calls, self.prog = os.path.join(self.t, "records-calls.log"), os.path.join(self.t, "records.py")
        put(self.prog, FAKE_RECORDS)
        for p in (unittest.mock.patch.object(merge, "RECORDS", self.prog, create=True),
                  unittest.mock.patch.dict(os.environ, {"RECORDS_CALLS": self.calls})):
            p.start(); self.addCleanup(p.stop)

    def heal_setup(self):
        """The head adds a debt; a debt and a hand-written page land on main during the head's wait. The head's rebuild commits one page, and the heal merges both."""
        self.kinds_off()
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT})
        self.in_wait(lambda: self.on("main", {"debts/main-gap.md": DEBT_TEXT.replace("Gap one", "Main gap"), "docs/records.md": "records\n- main-gap\n"},
                                     "a debt and a hand-written page on main"))

    def on_heal_wait(self, action):
        """Run action when the heal wait starts: the third wait, on the merge commit."""
        self.host.on_wait = lambda: action() if len(self.host.waits) == 3 else None

    def assert_kept(self, rc, out):
        """The merge commit that heals the page stays on feat: no revert, no merge, lock free."""
        self.assertEqual(rc, 1, out)
        self.assertEqual(len(self.host.waits), 3, self.host.waits)
        self.assertIn("stays on feat", out)
        self.assertNotIn("reverted", out)
        self.assertFalse(getattr(self.host, "merged", False), out)
        self.assertEqual(self.rev("origin/feat"), self.host.waits[-1][0])
        self.assertFalse(self.lock_ref())
        self.assertEqual(self.worktrees(), 1)

    def test_red_checks_on_the_heal_commit_keep_it_and_merge_nothing(self):
        self.heal_setup()
        self.host.seq = [(True, ""), (True, ""), (False, "a check is red: checks: fail")]
        rc, out = self.run_merge("7", "--confirm")
        self.assert_kept(rc, out)
        self.assertIn("are not green", out)
        self.assertIn("checks: fail", out)

    def test_a_debt_landing_on_main_during_the_heal_wait_makes_the_page_stale(self):
        self.heal_setup()
        self.on_heal_wait(lambda: self.on("main", {"debts/rival-gap.md": DEBT_TEXT.replace("Gap one", "Rival gap")}, "untooled push"))
        rc, out = self.run_merge("7", "--confirm")
        self.assert_kept(rc, out)
        self.assertIn("records page is stale", out)

    def test_a_page_edit_landing_on_main_during_the_heal_wait_stops_the_second_heal(self):
        self.heal_setup()
        self.on_heal_wait(lambda: self.on("main", {"docs/records.md": "records\n- rival\n"}, "untooled page edit"))
        rc, out = self.run_merge("7", "--confirm")
        self.assert_kept(rc, out)
        self.assertIn("conflicts again", out)

    def test_a_non_page_conflict_landing_on_main_during_the_heal_wait_refuses(self):
        self.heal_setup()
        self.on_heal_wait(lambda: self.on("main", {"debts/gap-one.md": DEBT_TEXT.replace("Gap one", "Rival gap one")}, "untooled debt"))
        rc, out = self.run_merge("7", "--confirm")
        self.assert_kept(rc, out)
        self.assertIn("does not merge cleanly", out)

    def test_the_heal_commit_names_only_the_page_in_drops_lines(self):
        self.heal_setup()
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.rev("origin/main")  # fetches
        body = sh(self.co, "git", "log", "-1", "--format=%B", "origin/main^2")  # the heal commit: the merge's second parent
        drops = [l[len("Drops-lines:"):].split(" -- ")[0].split() for l in body.splitlines() if l.startswith("Drops-lines:")]
        self.assertEqual(drops, [["docs/records.md"]], body)

class MergeImport(unittest.TestCase):
    """merge.py imports the records generator when it loads. With that import blocked, the tool prints one clear line and
    exits non-zero, with no traceback."""
    def tool_root(self):
        """A root with merge/merge.py copied in, and a gh shim that fails if the tool reaches it."""
        root = os.path.realpath(tempfile.mkdtemp(prefix="test-merge-import-"))
        self.addCleanup(shutil.rmtree, root, True)
        tool = os.path.join(root, "merge", "merge.py")
        os.makedirs(os.path.dirname(tool))
        shutil.copyfile(merge.__file__, tool)
        put_shim(os.path.join(root, "bin", "gh"), "#!/bin/sh\necho gh-blocked >&2\nexit 1\n")  # a stray gh call fails here
        old = os.environ.get("PATH", "")
        os.environ["PATH"] = os.path.join(root, "bin") + os.pathsep + old
        self.addCleanup(os.environ.__setitem__, "PATH", old)
        return root, tool

    def assert_one_clear_line(self, r, *names):
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertNotIn("Traceback", out)
        lines = [l for l in out.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1, out)
        self.assertTrue(lines[0].startswith("merge: "), out)
        self.assertRegex(lines[0], r"hook_catalog|records")
        for n in names:  # the error's own type, so a different one-line failure does not pass
            self.assertIn(n, lines[0], out)

    def test_a_blocked_generator_import_stops_with_one_line(self):
        root, tool = self.tool_root()
        code = "import runpy, sys; sys.modules['hook_catalog'] = None; sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')"
        r = subprocess.run([sys.executable, "-c", code, tool, "7", "--confirm"], cwd=root, capture_output=True, text=True)
        self.assert_one_clear_line(r)

    def test_a_syntax_error_in_the_generator_stops_with_one_line(self):
        # The generator file is real and broken at import: merge.py must name the error in one line, as it does for ImportError.
        root, tool = self.tool_root()
        put(os.path.join(root, "lint", "hook_catalog.py"), "RECORDS_PAGE = 'docs/records.md'\ndef broken(:\n    pass\n")
        r = subprocess.run([sys.executable, tool, "7", "--confirm"], cwd=root, capture_output=True, text=True)
        self.assert_one_clear_line(r, "SyntaxError")

    def test_a_name_error_in_the_generator_stops_with_one_line(self):
        # A top-level name the module never binds: the import raises NameError before RECORDS_PAGE exists.
        root, tool = self.tool_root()
        put(os.path.join(root, "lint", "hook_catalog.py"), "RECORDS_PAGE = missing_name\n")
        r = subprocess.run([sys.executable, tool, "7", "--confirm"], cwd=root, capture_output=True, text=True)
        self.assert_one_clear_line(r, "NameError")

class RecordsPageHome(unittest.TestCase):
    """The records page path has one home, lint/hook_catalog.py. merge.py imports it and holds no copy."""
    def test_merge_holds_no_copy_of_the_records_page_path(self):
        with open(merge.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        copies = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value == "docs/records.md"]
        self.assertEqual(copies, [], "merge.py copies the records page path at line %s. Import it from the generator." % copies)

    def test_merge_and_the_generator_name_one_value(self):
        self.assertTrue(hasattr(merge, "RECORDS_PAGE"), "merge.py must bind RECORDS_PAGE, from the generator")
        with open(merge.RECORDS, encoding="utf-8") as f:
            homes = [n.value for n in ast.parse(f.read()).body
                     if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "RECORDS_PAGE" for t in n.targets)]
        self.assertEqual(len(homes), 1, "lint/hook_catalog.py must assign RECORDS_PAGE exactly once")
        # The generator reads the path from the layout file, the one home of every record path.
        with open(os.path.join(os.path.dirname(merge.RECORDS), "layout.json"), encoding="utf-8") as f:
            self.assertEqual(merge.RECORDS_PAGE, json.load(f)["kinds"]["records-index"]["path"])


def assert_one_rate_wait_line(test, text, snapshots):
    """A rate wait prints one line that says it waits, why (a rate limit) and for how long (60 s). `snapshots` holds the
    captured output at each pause: the line must already be there when the wait starts, so a 60 s wait never looks like a hang."""
    lines = [ln for ln in text.splitlines() if re.search(r"wait", ln, re.I)]
    test.assertEqual(len(lines), 1, f"want one wait line, got {text!r}")
    test.assertRegex(lines[0], r"(?i)rate[ -]limit", "the wait line must say why it waits")
    test.assertRegex(lines[0], r"\b60 ?s(econds)?\b", "the wait line must say how long")
    test.assertEqual(len(snapshots), 1, "one rate wait is one pause")
    test.assertIn(lines[0], snapshots[0], "the wait line must print before the wait starts")

def assert_rate_wait_lines(test, text, snapshots, waits, call):
    """One line per rate wait, in order: it says why (a rate limit), names `call` and gives the wait (N s), and it is already printed when its own
    wait starts. `waits` are the seconds, one per retry."""
    lines = [ln for ln in text.splitlines() if re.search(r"wait", ln, re.I)]
    test.assertEqual(len(lines), len(waits), f"want one wait line per wait, got {text!r}")
    test.assertEqual(len(snapshots), len(waits), "one rate wait is one pause")
    for i, (line, secs) in enumerate(zip(lines, waits)):
        test.assertRegex(line, r"(?i)rate[ -]limit", "the wait line must say why it waits")
        test.assertIn(call, line, "the wait line must name the call")
        test.assertRegex(line, rf"\b{secs} ?s(econds)?\b", f"the wait line must say how long: {secs} s")
        test.assertIn(line, snapshots[i], "the wait line must print before its wait starts")

class GhLockRateRetry(unittest.TestCase):
    """GhLock on a rate-limit 403. Each step of acquire, release, unlock and the lock
    read answers [rate limit, then success]: the step is retried with the first rate wait, 60 s. A permission 403 stops at once. merge.sh is the
    seam, so the test holds wherever the retry sits. self.pauses records every pause; nothing sleeps.
    GitHub's reset time is readable on this path only, because `gh api -i` prints the headers and no other gh command here does.
    So every lock call must ask for them (-i), read the wait from them (Retry-After in seconds, or the X-Ratelimit-Reset epoch when X-Ratelimit-Remaining is 0, against the lock's
    clock), and drop the block before it reads the reply. The fake prints that block whenever it sees -i (see fake_sh)."""
    NOW = 1000.0
    OLD, NEW, BASE, TREE = "oldlock", "newlock", "base1", "tree1"
    EXPIRED = (0, merge.lock_message(10, 0.0))  # expires at 10: expired at NOW
    LIVE = (0, "merge lock\nexpires: 2000\nowner: x")
    DEFAULT = {"lock-read": [(1, "gh: Not Found (HTTP 404)")], "lock-commit-read": [EXPIRED], "base-ref": [(0, BASE)],
               "base-tree": [(0, TREE)], "lock-commit-post": [(0, NEW)], "refs-post": [(0, "")], "delete": [(0, "")]}
    OK = {"base-ref": (0, BASE), "base-tree": (0, TREE), "lock-commit-post": (0, NEW), "refs-post": (0, "")}

    def setUp(self):
        self.pauses, self.calls, self.replies, self.arglog = [], {}, {}, []
        p = unittest.mock.patch.object(merge, "sh", self.fake_sh)
        p.start(); self.addCleanup(p.stop)

    @staticmethod
    def step_of(args):
        """Names the gh call by its step: the method and path, and for a GET of a commit, its --jq. A -i or --include flag may sit anywhere."""
        if list(args[:2]) != ["gh", "api"]:
            return "not-gh-api"
        rest = without_include(args[2:])
        method = "GET"
        if rest[:1] == ["-X"]:
            method, rest = rest[1], rest[2:]
        path = rest[0]
        jq = rest[rest.index("--jq") + 1] if "--jq" in rest else ""
        if method == "DELETE" and path.endswith("/git/refs/heads/merge-lock/main"):
            return "delete"
        if method == "POST" and path.endswith("/git/commits"):
            return "lock-commit-post"
        if method == "POST" and path.endswith("/git/refs"):
            return "refs-post"
        if method == "PATCH" and path.endswith("/git/refs/heads/merge-lock/main"):
            return "ref-patch"
        if "/git/ref/heads/merge-lock/" in path:
            return "lock-read"
        if "/git/ref/heads/" in path:
            return "base-ref"
        if "/git/commits/" in path:
            return "base-tree" if jq == ".tree.sha" else "lock-commit-read"
        return "unhandled"

    def fake_sh(self, args, cwd=None, input=None, env=None):
        """A reply is (code, text) or (code, text, headers). With -i or --include in the args the fake prints what `gh api -i` prints (gh_i): the
        status line and the headers first, then the text. Without them it prints the text alone, as gh does."""
        step = self.step_of(args)
        self.calls[step] = self.calls.get(step, 0) + 1
        self.arglog.append(list(args))
        seq = self.replies.get(step) or self.DEFAULT.get(step)
        if not seq:
            return 1, f"unhandled {step}: {' '.join(args)}"
        ent = seq.pop(0) if len(seq) > 1 else seq[0]
        c, out = ent[0], ent[1]
        if "-i" in args or "--include" in args:
            out = gh_i(200 if not c else http_code_of(out), out, **(ent[2] if len(ent) > 2 else {}))
        return c, out

    def reply(self, step, *seq):
        self.replies[step] = list(seq)

    def lock(self):
        return merge.GhLock(now=lambda: self.NOW, pause=self.pauses.append)

    def acquire(self):
        try:
            return self.lock().acquire("main", 600)
        except merge.Stop as e:
            self.fail(f"acquire stopped: {type(e).__name__}: {e}")

    def test_the_fixture_is_a_rate_limit_and_never_a_404(self):  # control: the text the other cases send
        self.assertTrue(merge.is_net(1, RATE_API_403))
        self.assertIsNotNone(merge.RATE_LIMIT.search(RATE_API_403))
        self.assertNotRegex(RATE_API_403, r"404|Not Found|does not exist")

    def test_a_clean_acquire_takes_the_lock_without_a_pause(self):  # control
        self.assertEqual(self.acquire(), self.NEW)
        self.assertEqual((self.calls.get("delete", 0), self.pauses), (0, []))

    def test_a_clean_acquire_over_an_expired_lock_deletes_it_once(self):  # control
        self.reply("lock-read", (0, self.OLD))
        self.assertEqual(self.acquire(), self.NEW)
        self.assertEqual((self.calls["delete"], self.pauses), (1, []))

    def test_a_rate_limit_on_each_acquire_step_is_retried_with_the_rate_wait(self):
        for step in ("base-ref", "base-tree", "lock-commit-post", "refs-post"):
            with self.subTest(step=step):
                self.calls, self.pauses, self.replies = {}, [], {}
                self.reply(step, (1, RATE_API_403), self.OK[step])
                self.assertEqual(self.acquire(), self.NEW)
                self.assertEqual(self.calls[step], 2)
                self.assertEqual(self.pauses, RATE_LADDER[:1])

    # The break path never waits: a retry could land after another run's take and delete its fresh lock.
    def break_over_expired(self, delete):
        """acquire over an expired lock whose DELETE answers `delete`. -> the exception acquire raised, or None."""
        self.reply("lock-read", (0, self.OLD))
        self.reply("delete", delete)
        try:
            self.lock().acquire("main", 600)
        except merge.Stop as e:
            return e

    def test_a_rate_limited_delete_of_an_expired_lock_is_a_net_stop_with_no_wait_and_no_retry(self):
        e = self.break_over_expired((1, RATE_API_403))
        self.assertIsInstance(e, merge.NetStop)
        self.assertEqual((self.calls["delete"], self.pauses), (1, []))
        self.assertEqual((self.calls.get("lock-commit-post", 0), self.calls.get("refs-post", 0)), (0, 0))  # no lock made over a lock that may still stand
        self.assertIn("API rate limit exceeded", str(e))  # the stop shows gh's own words

    def test_a_rate_limited_delete_with_a_retry_after_still_waits_nothing(self):
        e = self.break_over_expired((1, RATE_API_403, {"Retry_After": 17}))
        self.assertIsInstance(e, merge.NetStop)
        self.assertEqual((self.calls["delete"], self.pauses), (1, []))

    def test_a_network_error_on_the_delete_of_an_expired_lock_is_a_net_stop_with_no_retry(self):
        e = self.break_over_expired((1, self.LOCK_5XX))
        self.assertIsInstance(e, merge.NetStop)
        self.assertEqual((self.calls["delete"], self.pauses), (1, []))

    def test_a_404_on_the_delete_of_an_expired_lock_goes_on_to_make_the_new_lock(self):  # control: the ref is gone, which is what the delete wanted
        self.assertIsNone(self.break_over_expired((1, "gh: Not Found (HTTP 404)")))
        self.assertEqual((self.calls["delete"], self.pauses, self.calls["refs-post"]), (1, [], 1))

    def test_any_other_failure_on_the_delete_of_an_expired_lock_is_a_stop_and_not_a_net_stop(self):
        for failure in (PLAIN_403_API, "gh: Validation Failed (HTTP 422)"):
            with self.subTest(failure=failure[:50]):
                self.calls, self.pauses, self.replies = {}, [], {}
                e = self.break_over_expired((1, failure))
                self.assertIsInstance(e, merge.Stop)
                self.assertNotIsInstance(e, merge.NetStop)
                self.assertNotIsInstance(e, merge.Held)
                self.assertEqual((self.calls["delete"], self.pauses), (1, []))
                self.assertEqual((self.calls.get("lock-commit-post", 0), self.calls.get("refs-post", 0)), (0, 0))

    def test_a_rate_limited_read_of_the_lock_commit_is_retried_and_keeps_its_expiry(self):
        self.reply("lock-read", (0, self.OLD))
        self.reply("lock-commit-read", (1, RATE_API_403), self.LIVE)
        got = self.lock().read("main")
        self.assertEqual(got[1], 2000)  # base: inf, a live lock for ever
        self.assertEqual(self.pauses, RATE_LADDER[:1])

    def test_a_permission_403_on_the_lock_commit_stops_at_once(self):  # guard: red if a 403 with no rate text is retried
        self.reply("lock-commit-post", (1, PLAIN_403_API))
        with self.assertRaises(merge.Stop) as cm:
            self.lock().acquire("main", 600)
        self.assertIn("Resource not accessible by integration", str(cm.exception))
        self.assertEqual((self.calls["lock-commit-post"], self.pauses), (1, []))

    def test_a_refs_post_error_that_is_not_a_rate_limit_keeps_its_text(self):
        self.reply("refs-post", (1, "gh: Object does not exist (HTTP 422)"))
        with self.assertRaises(merge.Stop) as cm:
            self.lock().acquire("main", 600)
        self.assertIn("Object does not exist", str(cm.exception))
        self.assertNotIn("another run took", str(cm.exception))
        self.assertEqual(self.pauses, [])

    def test_a_rate_limited_unlock_is_retried_and_a_404_after_it_counts_as_done(self):
        self.reply("delete", (1, RATE_API_403), (1, "gh: Not Found (HTTP 404)"))
        try:
            self.lock().unlock("main")
        except merge.Stop as e:
            self.fail(f"unlock stopped on a rate limit: {e}")
        self.assertEqual(self.calls["delete"], 2)
        self.assertEqual(self.pauses, RATE_LADDER[:1])

    def test_a_rate_limited_release_delete_is_retried_and_a_404_after_it_counts_as_done(self):
        self.reply("lock-read", (0, "tok"))
        self.reply("lock-commit-read", self.LIVE)
        self.reply("delete", (1, RATE_API_403), (1, "gh: Not Found (HTTP 404)"))
        out = release_out(self, self.lock(), "tok")
        self.assertNotIn("the lock release failed", out)
        self.assertEqual(self.calls["delete"], 2)
        self.assertEqual(self.pauses, RATE_LADDER[:1])

    # a 404 inside a rate-limit text is no "ref gone"; a lock read that cannot finish is a NetStop; a wait prints a line.
    RATE_404_ID = RATE_API_403.replace("309471439", "4040404")  # the user id holds "404": a rate limit a bare "404" check reads as gone
    LOCK_5XX = '{"message":"Server Error"}gh: Server Error (HTTP 502)'  # gh's own 5xx line after the body, as GH_API_TAIL reads it

    def test_the_404_fixture_is_a_rate_limit_whose_text_holds_404(self):  # control: the trigger of item 1
        self.assertTrue(merge.is_net(1, self.RATE_404_ID))
        self.assertIsNotNone(merge.RATE_LIMIT.search(self.RATE_404_ID))
        self.assertIn("404", self.RATE_404_ID)

    def test_a_rate_limit_whose_text_holds_404_is_never_a_removed_lock(self):
        self.reply("delete", (1, self.RATE_404_ID))
        try:
            self.lock().unlock("main")
        except merge.NetStop:
            pass
        except merge.Stop as e:
            self.fail(f"unlock stopped as a plain Stop, not a NetStop: {e}")
        else:
            self.fail("unlock returned as if the lock were removed, on a rate limit")
        self.assertEqual(self.calls["delete"], 4)
        self.assertEqual(self.pauses, RATE_LADDER)

    def run_unlock(self, lock):
        """`merge --unlock main` over the fake gh. The one git call (the checkout's root) answers at once. -> (rc, stdout and stderr)."""
        self.reply("not-gh-api", (0, "/repo"))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = merge.main(["--unlock", "main"], lock=lock)
        return rc, buf.getvalue()

    def test_unlock_main_on_a_rate_limit_whose_text_holds_404_stops_and_never_says_removed(self):  # the CLI line
        self.reply("delete", (1, self.RATE_404_ID))
        rc, out = self.run_unlock(self.lock())
        self.assertEqual(rc, 1, out)
        self.assertNotRegex(out, r"lock on main removed")
        self.assertIn("API rate limit exceeded", out)  # the stop shows gh's own words
        self.assertEqual(self.calls["delete"], 4)

    def test_unlock_main_on_a_missing_ref_says_so_and_never_says_removed(self):
        self.reply("delete", (1, "gh: Not Found (HTTP 404)"))
        rc, out = self.run_unlock(self.lock())
        self.assertEqual(rc, 0, out)
        self.assertNotRegex(out, r"lock on main removed")
        self.assertRegex(out, r"(?i)no (merge )?lock|not found|does not exist|nothing to remove")

    def test_a_rate_limit_outlasting_the_retries_on_the_lock_commit_read_is_a_net_stop(self):
        self.reply("lock-read", (0, self.OLD))
        self.reply("lock-commit-read", (1, RATE_API_403))
        try:
            self.lock().read("main")
        except merge.NetStop:
            pass
        except merge.Stop as e:
            self.fail(f"a rate limit on the lock commit read stopped as a plain Stop: {e}")
        else:
            self.fail("read returned an expiry for a lock it could not read")
        self.assertEqual(self.calls["lock-commit-read"], 4)
        self.assertEqual(self.pauses, RATE_LADDER)

    def test_a_network_error_outlasting_the_retries_on_the_lock_commit_read_is_a_net_stop(self):
        self.reply("lock-read", (0, self.OLD))
        self.reply("lock-commit-read", (1, self.LOCK_5XX))
        try:
            self.lock().read("main")
        except merge.NetStop:
            pass
        except merge.Stop as e:
            self.fail(f"a network error on the lock commit read stopped as a plain Stop: {e}")
        else:
            self.fail("read returned an expiry for a lock it could not read")
        self.assertEqual(self.calls["lock-commit-read"], 4)
        self.assertEqual(self.pauses, [merge.NET_PAUSE] * 3)

    def test_a_rate_limit_on_the_lock_commit_read_never_reads_as_a_held_lock(self):  # the acquire path
        self.reply("lock-read", (0, self.OLD))
        self.reply("lock-commit-read", (1, RATE_API_403))
        try:
            self.lock().acquire("main", 600)
        except merge.NetStop:
            pass
        except merge.Held as e:
            self.fail(f"acquire read an unreadable lock as a live one: {e}")
        except merge.Stop as e:
            self.fail(f"acquire stopped as a plain Stop, not a NetStop: {e}")
        else:
            self.fail("acquire took the lock over an unreadable lock")
        self.assertEqual((self.calls.get("lock-commit-post", 0), self.calls.get("refs-post", 0)), (0, 0))

    def test_a_rate_wait_on_the_lock_path_prints_one_line_before_the_wait(self):
        self.reply("lock-commit-post", (1, RATE_API_403), self.OK["lock-commit-post"])
        buf, snapshots = io.StringIO(), []
        lock = merge.GhLock(now=lambda: self.NOW, pause=lambda s: snapshots.append(buf.getvalue()))
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            self.assertEqual(lock.acquire("main", 600), self.NEW)
        self.assertEqual(self.calls["lock-commit-post"], 2)
        assert_one_rate_wait_line(self, buf.getvalue(), snapshots)

    def test_a_clean_acquire_prints_no_wait_line(self):  # control
        buf, snapshots = io.StringIO(), []
        lock = merge.GhLock(now=lambda: self.NOW, pause=lambda s: snapshots.append(buf.getvalue()))
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            self.assertEqual(lock.acquire("main", 600), self.NEW)
        self.assertEqual(snapshots, [])
        self.assertNotRegex(buf.getvalue(), r"(?i)\bwait")

    # the ladder, GitHub's reset time, and the lock's expiry
    HDR_404 = {"X_Github_Request_Id": "4040:1A2B3C:4D5E6F:6700AB:67890CDE", "Content_Length": 404}  # header values that hold "404": a request id, a length

    def test_every_lock_call_asks_gh_for_the_response_headers(self):  # the seam: without -i no reset time reaches the tool, so the reset code is unreachable
        self.reply("lock-read", (0, self.OLD))  # an expired lock: the acquire walks every step (read, commit read, delete, base ref, base tree, commit, ref)
        self.assertEqual(self.acquire(), self.NEW)
        lock_calls = [a for a in self.arglog if list(a[:2]) == ["gh", "api"]]
        self.assertGreaterEqual(len(lock_calls), 7, lock_calls)
        for a in lock_calls:
            self.assertTrue("-i" in a or "--include" in a, f"no -i or --include on {a}")

    def test_a_clean_lock_read_returns_the_bare_sha_and_message_whatever_headers_gh_prints(self):  # a guard: the -i block is dropped before the reply is read
        self.reply("lock-read", (0, self.OLD))
        self.reply("lock-commit-read", self.LIVE)
        self.assertEqual(self.lock().read("main"), (self.OLD, 2000, self.LIVE[1]))

    def test_a_retry_after_on_the_lock_commit_is_the_rate_wait(self):
        for secs, want in ((120, 120), (3600, 900)):  # a reset past 15 minutes is capped at 900 s
            with self.subTest(retry_after=secs):
                self.calls, self.pauses, self.replies = {}, [], {}
                self.reply("lock-commit-post", (1, RATE_API_SECONDARY_403, {"Retry_After": secs}), self.OK["lock-commit-post"])
                self.assertEqual(self.acquire(), self.NEW)
                self.assertEqual((self.calls["lock-commit-post"], self.pauses), (2, [want]))

    def test_an_x_ratelimit_reset_epoch_on_the_lock_commit_is_waited_for_against_the_lock_clock(self):
        for delta, want in ((120, 120), (3600, 900)):  # the lock's clock reads NOW. A reset an hour on is capped at 900 s
            with self.subTest(reset_in=delta):
                self.calls, self.pauses, self.replies = {}, [], {}
                self.reply("lock-commit-post", (1, RATE_API_403, {"X_Ratelimit_Remaining": 0, "X_Ratelimit_Reset": int(self.NOW) + delta}), self.OK["lock-commit-post"])
                self.assertEqual(self.acquire(), self.NEW)
                self.assertEqual((self.calls["lock-commit-post"], self.pauses), (2, [want]))

    def test_a_reset_time_already_past_is_never_a_negative_wait(self):  # a guard: the exact wait is free, bounded by 0 and 900
        for headers in ({"Retry_After": -5}, {"X_Ratelimit_Remaining": 0, "X_Ratelimit_Reset": int(self.NOW) - 100}):
            with self.subTest(headers=headers):
                self.calls, self.pauses, self.replies = {}, [], {}
                self.reply("lock-commit-post", (1, RATE_API_403, headers), self.OK["lock-commit-post"])
                self.assertEqual(self.acquire(), self.NEW)
                self.assertEqual(len(self.pauses), 1)
                self.assertTrue(0 <= self.pauses[0] <= 900, self.pauses)

    def test_a_lock_commit_rate_limit_that_lasts_20_minutes_is_waited_out_and_the_lock_is_taken(self):  # no person has to run it again
        clock = Clock(self.NOW)
        over = self.NOW + 20 * 60
        def limited(args, cwd=None, input=None, env=None):
            if self.step_of(args) == "lock-commit-post" and clock.now() < over:
                return 1, RATE_API_SECONDARY_403  # a secondary limit that gives no reset time
            return self.fake_sh(args, cwd, input, env)
        with unittest.mock.patch.object(merge, "sh", limited):
            lock = merge.GhLock(now=clock.now, pause=clock.pause)
            self.assertEqual(lock.acquire("main", 600), self.NEW)  # no lock is held yet, so no expiry bounds these waits
        self.assertEqual(clock.pauses, [60, 300, 900])

    def test_a_lock_commit_rate_limit_that_outlasts_the_ladder_is_a_net_stop_after_three_retries(self):
        self.reply("lock-commit-post", (1, RATE_API_SECONDARY_403))
        with self.assertRaises(merge.NetStop):
            self.lock().acquire("main", 600)
        self.assertEqual((self.calls["lock-commit-post"], self.pauses), (4, [60, 300, 900]))

    # A wait past the lock's expiry is no stop: the run extends the lock and waits (LockExtendsForRateWaits).

    def test_a_header_that_holds_404_never_makes_a_permission_refusal_read_as_a_removed_lock(self):  # a guard: the headers are no part of the reply text
        self.reply("delete", (1, PLAIN_403_API, self.HDR_404))
        with self.assertRaises(merge.Stop) as cm:
            self.lock().unlock("main")
        self.assertIn("Resource not accessible", str(cm.exception))
        self.assertEqual(self.pauses, [])

    def test_a_header_that_holds_404_never_makes_a_permission_refusal_read_as_no_lock(self):  # a guard
        self.reply("lock-read", (1, PLAIN_403_API, self.HDR_404))
        with self.assertRaises(merge.Stop):
            self.lock().read("main")

class BeforeWaitHost(FakeHost):
    """Keeps the hook the run has handed it (Host.before_wait) when its first wait starts."""
    seen = "never read"

    def wait_checks(self, n, sha, d, prior=None):
        if self.seen == "never read":
            self.seen = getattr(self, "before_wait", None)
        return super().wait_checks(n, sha, d, prior)

class LockExtensionReachesHost(Env):
    """A rate wait is the exception to the lock's 600 s cap. So once the lock is
    taken, confirm hands the host the lock's own extend_for (host.before_wait): the host runs it before each rate wait. It hands over no bound
    (host.until) that stops a wait at the end of the lock's spare."""
    def test_the_run_hands_the_host_the_lock_extension_before_its_first_wait(self):
        host = BeforeWaitHost(self.co, self.other)
        rc, out = self.run_merge("7", "--confirm", host=host)
        self.assertEqual(rc, 0, out)
        self.assertIsNotNone(host.seen, "the host was never given a way to extend the lock before a rate wait")
        self.assertEqual(host.seen, self.lock.extend_for)  # this run's own lock, not a copy of it

# ---- before each rate wait the run extends the lock's expiry past the wait (Lock.extend_for). The cases drive a rate-limited call under a held
# lock, so they fail where the code waits without extending (or stops), and not on a missing name. 300 s and 6 h are written here as literals.

def expires_in(text):
    """The `expires:` epoch in a lock commit's message, read with a pattern of the test's own (never merge.expiry_of)."""
    return int(re.search(r"^expires: (\d+)$", text, re.M).group(1))

class TickClock(Clock):
    """A clock that moves one second on at every read, as real time does between two reads of it."""
    def now(self):
        self.t += 1
        return self.t

class LockApi:
    """A stateful `gh api` for the merge lock, patched in as merge.sh: the lock ref, the commits it points at, and `log`, one ordered list of every call
    and (added by the test's pause) every pause. A call named by GhLockRateRetry.step_of answers the next reply queued for that step by `limit`
    ((code, text) or (code, text, headers)), else what a working API answers. The ref moves only when a PATCH or a POST says so."""
    def __init__(self):
        self.ref, self.commits, self.log, self.queued, self.n, self.lost = None, {}, [], {}, 0, {}

    def limit(self, step, *replies):
        self.queued.setdefault(step, []).extend(replies)

    def lose_reply(self, step, reply):
        """The next call of `step` takes effect (the ref moves), then answers `reply` (code, text): the reply is lost on the way back."""
        self.lost[step] = reply

    def steps(self, since=0):
        return [e[0] for e in self.log[since:]]

    def __call__(self, args, cwd=None, input=None, env=None):
        step = GhLockRateRetry.step_of(args)
        assert "-i" in args, f"a lock call that does not ask for the headers: {args}"
        rest = without_include(args[2:])
        rest = rest[2:] if rest[:1] == ["-X"] else rest
        fields = {}
        for flag, pair in zip(rest, rest[1:]):
            if flag in ("-f", "-F"):
                key, _, value = pair.partition("=")
                fields[key] = value
        self.log.append((step, fields))
        if step in self.lost:
            self.answer(step, rest[0], fields)
            ent = self.lost.pop(step)
        else:
            ent = self.queued[step].pop(0) if self.queued.get(step) else self.answer(step, rest[0], fields)
        c, out = ent[0], ent[1]
        return c, gh_i(200 if not c else http_code_of(out), out, **(ent[2] if len(ent) > 2 else {}))

    def answer(self, step, path, fields):
        if step == "lock-read":
            return (0, self.ref) if self.ref else (1, "gh: Not Found (HTTP 404)")
        if step == "lock-commit-read":
            sha = path.rsplit("/", 1)[1]
            return (0, self.commits[sha]) if sha in self.commits else (1, "gh: Not Found (HTTP 404)")
        if step in ("base-ref", "base-tree"):
            return 0, "base1" if step == "base-ref" else "tree1"
        if step == "lock-commit-post":
            self.n += 1
            self.commits[f"c{self.n}"] = fields["message"]
            return 0, f"c{self.n}"
        if step == "refs-post":
            if self.ref:
                return 1, '{"message":"Reference already exists"}gh: Reference already exists (HTTP 422)'
            self.ref = fields["sha"]
            return 0, ""
        if step == "ref-patch":
            self.ref = fields["sha"]
            return 0, "{}"
        if step == "delete":
            if not self.ref:
                return 1, "gh: Not Found (HTTP 404)"
            self.ref = None
            return 0, ""
        raise AssertionError(f"the fake API has no answer for {step}")

class LockExtendsForRateWaits(unittest.TestCase):
    """GhLock under a rate-limited call. The call is the read of a lock commit, rate limited with `Retry-After`. Before the wait the run
    extends the lock to now + wait + 300 s (LOCK_MARGIN), the lock's text and `lock.until` agree on it, and the pause comes after the PATCH that moved the ref.
    When the extension fails the run stops in place of the wait. `pause` events in api.log carry the lock's `until` and the expiry published on the ref at that moment."""
    NOW, MARGIN, MAX_HOLD = 1000.0, 300, 6 * 3600

    def setUp(self):
        self.api = LockApi()
        p = unittest.mock.patch.object(merge, "sh", self.api)
        p.start(); self.addCleanup(p.stop)

    def published(self):
        return expires_in(self.api.commits[self.api.ref]) if self.api.ref in self.api.commits else None

    def held(self, ttl, clock=None):
        """-> a GhLock this run holds, expiring ttl seconds after NOW (self.token is its take). The clock moves on with each pause."""
        self.clock = clock or Clock(self.NOW)
        def pause(seconds):
            self.api.log.append(("pause", {"wait": seconds, "until": self.lock.until, "published": self.published()}))
            self.clock.pause(seconds)
        self.lock = merge.GhLock(now=self.clock.now, pause=pause)
        self.token = self.lock.acquire("main", ttl)
        self.taken = len(self.api.log)
        return self.lock

    def rate_limited_read(self, retry_after=100):
        """The next read of a lock commit answers a rate limit with this Retry-After. -> the read's result."""
        self.api.limit("lock-commit-read", (1, RATE_API_403, {"Retry_After": retry_after}))
        return self.lock.read("main")

    def pauses(self):
        return [e[1] for e in self.api.log if e[0] == "pause"]

    def test_the_margin_and_the_hold_bound_are_the_ruling_values(self):  # control for the literals below
        self.assertEqual((getattr(merge, "LOCK_MARGIN", None), getattr(merge, "LOCK_MAX_HOLD", None)), (self.MARGIN, self.MAX_HOLD))

    def test_a_rate_wait_past_the_expiry_extends_the_lock_before_the_wait(self):
        self.held(200)  # expires at 1200
        self.assertEqual(self.lock.until, 1200)
        first = self.api.commits[self.token]
        self.rate_limited_read(100)  # a wait of 100 s needs 1000 + 100 + 300 = 1400
        steps = self.api.steps(self.taken)
        self.assertEqual(steps.count("ref-patch"), 1, steps)
        self.assertLess(steps.index("ref-patch"), steps.index("pause"), steps)  # the pause comes after the PATCH
        self.assertEqual(self.pauses(), [{"wait": 100, "until": 1400, "published": 1400}])  # the text on the ref and lock.until are one value, read before the wait
        self.assertEqual(self.lock.until, 1400)
        self.assertEqual(self.published(), int(self.NOW + 100 + self.MARGIN))
        self.assertEqual(re.search(r"^owner: .*$", self.api.commits[self.api.ref], re.M).group(0), re.search(r"^owner: .*$", first, re.M).group(0))  # the same lock, a later expiry

    def test_a_rate_wait_the_expiry_already_covers_extends_nothing(self):  # control: kills an extension that always writes
        self.held(700)  # expires at 1700. 1000 + 100 + 300 = 1400 is inside it
        self.rate_limited_read(100)
        steps = self.api.steps(self.taken)
        self.assertNotIn("ref-patch", steps)
        self.assertNotIn("lock-commit-post", steps)
        self.assertEqual(self.pauses(), [{"wait": 100, "until": 1700, "published": 1700}])

    def test_a_rate_wait_that_ends_exactly_at_the_expiry_extends_nothing(self):  # control, the boundary: the lock covers a wait that needs the very second it expires
        self.held(400)  # expires at 1400 = 1000 + 100 + 300
        self.rate_limited_read(100)
        self.assertNotIn("ref-patch", self.api.steps(self.taken))
        self.assertEqual(self.lock.until, 1400)

    def test_a_ladder_wait_with_no_reset_time_is_covered_the_same_way(self):  # no Retry-After: the 60 s rung
        self.held(30)
        self.api.limit("lock-commit-read", (1, RATE_API_403))
        self.lock.read("main")
        self.assertEqual(self.pauses(), [{"wait": 60, "until": 1360, "published": 1360}])

    def test_each_wait_of_a_run_extends_the_lock_again_when_it_needs_to(self):
        self.held(10)
        self.rate_limited_read(100)  # to 1400
        self.assertEqual(self.clock.t, 1100.0)
        self.rate_limited_read(100)  # 1100 + 100 + 300 = 1500
        self.assertEqual([p["published"] for p in self.pauses()], [1400, 1500])
        self.assertEqual(self.lock.until, 1500)

    # the extension fails: the run stops in place of the wait
    def test_a_rate_limited_extension_stops_the_run_with_no_wait_and_no_retry(self):
        self.held(200)
        self.api.limit("ref-patch", (1, RATE_API_403))
        with self.assertRaises(merge.NetStop) as cm:
            self.rate_limited_read(100)
        self.assertRegex(str(cm.exception), r"(?i)merge lock")
        steps = self.api.steps(self.taken)
        self.assertEqual((steps.count("pause"), steps.count("lock-commit-read"), steps.count("ref-patch")), (0, 1, 1), steps)  # no wait, no second try of the read, no second PATCH
        self.assertEqual(self.lock.until, 1200)  # the lock was not extended

    def test_an_extension_over_a_ref_that_is_not_this_runs_stops_the_run_and_writes_nothing(self):
        self.held(200)
        self.api.ref = "rival"
        self.api.commits["rival"] = "merge lock\nexpires: 99999\nowner: someone-else"
        with self.assertRaises(merge.NetStop) as cm:
            self.rate_limited_read(100)
        self.assertRegex(str(cm.exception), r"(?i)merge lock")
        steps = self.api.steps(self.taken)
        self.assertNotIn("ref-patch", steps)
        self.assertNotIn("lock-commit-post", steps)
        self.assertNotIn("pause", steps)
        self.assertEqual(self.api.ref, "rival")  # the other run's lock is untouched
        self.assertEqual(self.lock.until, 1200)

    def test_a_wait_that_needs_a_hold_past_six_hours_from_the_take_stops_the_run_before_any_write(self):
        self.held(self.MAX_HOLD)  # expires at the bound: began + 6 h
        self.clock.t = self.NOW + self.MAX_HOLD - 1000
        with self.assertRaises(merge.NetStop) as cm:
            self.rate_limited_read(900)  # needs t + 900 + 300 = the bound + 200
        self.assertRegex(str(cm.exception), r"(?i)merge lock")
        steps = self.api.steps(self.taken)
        self.assertNotIn("ref-patch", steps)
        self.assertNotIn("lock-commit-post", steps)
        self.assertNotIn("pause", steps)
        self.assertEqual(self.lock.until, self.NOW + self.MAX_HOLD)

    def test_a_wait_that_needs_exactly_six_hours_from_the_take_is_extended(self):  # the bound is "past": a hold of exactly 6 h is allowed
        self.held(self.MAX_HOLD - 600)  # the lock is live at the read, 600 s left
        self.clock.t = self.NOW + self.MAX_HOLD - 900 - self.MARGIN
        self.rate_limited_read(900)
        self.assertEqual(self.pauses()[0]["published"], self.NOW + self.MAX_HOLD)
        self.assertEqual(self.lock.until, self.NOW + self.MAX_HOLD)

    # a lock whose expiry has passed is not extended. A rival may already have broken it (acquire treats expiry <= now as free), so two runs would both hold it
    def expired_stops_the_run(self, at):
        """The lock expires at 1200. The clock reads `at`. The rate-limited read must stop the run: no write, no wait, no second try."""
        self.held(200)
        self.clock.t = at
        with self.assertRaises(merge.NetStop) as cm:
            self.rate_limited_read(100)
        self.assertRegex(str(cm.exception), r"(?i)merge lock")
        self.assertRegex(str(cm.exception), r"Run again")
        steps = self.api.steps(self.taken)
        self.assertNotIn("ref-patch", steps)
        self.assertNotIn("lock-commit-post", steps)
        self.assertNotIn("pause", steps)
        self.assertEqual(steps.count("lock-commit-read"), 1, steps)  # no second try of the read
        self.assertEqual(self.api.ref, self.token)  # the lock on the ref is not touched
        self.assertEqual(self.lock.until, 1200)

    def test_a_rate_wait_on_an_expired_lock_stops_the_run_before_any_write(self):
        self.expired_stops_the_run(1300)  # 100 s past the expiry

    def test_a_rate_wait_on_a_lock_that_expires_this_second_stops_the_run(self):  # the boundary: acquire frees a lock at expiry <= now, so extend_for must not extend it
        self.expired_stops_the_run(1200)

    def test_a_rate_wait_on_a_lock_with_one_second_left_is_still_extended(self):  # control: kills a guard that stops too early
        self.held(200)
        self.clock.t = 1199
        self.rate_limited_read(100)
        self.assertEqual(self.api.steps(self.taken).count("ref-patch"), 1)
        self.assertEqual(self.pauses(), [{"wait": 100, "until": 1599, "published": 1599}])

    def test_extend_for_on_an_expired_lock_names_the_merge_lock_and_says_run_again(self):  # direct: retry_net wraps every extend_for stop in a text that already says "merge lock"
        self.held(200)
        self.clock.t = 1300
        with self.assertRaises(merge.NetStop) as cm:
            self.lock.extend_for(100)
        self.assertRegex(str(cm.exception), r"(?i)merge lock")
        self.assertRegex(str(cm.exception), r"Run again")
        self.assertNotIn("ref-patch", self.api.steps(self.taken))
        self.assertNotIn("lock-commit-post", self.api.steps(self.taken))

    # the new commit is this run's before the PATCH is sent. A PATCH that lands with a lost reply must still leave a lock that release can delete
    def test_a_release_after_a_patch_whose_reply_was_lost_deletes_the_lock(self):
        self.held(200)
        self.api.lose_reply("ref-patch", (1, '{"message":"Server Error"}gh: Server Error (HTTP 502)'))
        with self.assertRaises(merge.NetStop):
            self.rate_limited_read(100)
        self.assertNotEqual(self.api.ref, self.token, "the PATCH did not land: this case tests nothing")
        self.assertEqual(release_out(self, self.lock, self.token), "")
        self.assertIsNone(self.api.ref)
        self.assertEqual(self.api.steps().count("delete"), 1)

    # (c) one value: the expiry the lock holds is the expiry it published, after the take and after each extension, on a clock that moves between reads
    def test_the_published_expiry_is_the_one_the_lock_holds_after_the_take_and_after_each_extension(self):
        self.held(10, clock=TickClock(self.NOW))
        self.assertEqual(self.lock.until, self.published())
        self.rate_limited_read(100)
        self.rate_limited_read(100)
        pauses = self.pauses()
        self.assertEqual(len(pauses), 2)
        for p in pauses:
            self.assertEqual(p["until"], p["published"], pauses)
        self.assertLess(pauses[0]["published"], pauses[1]["published"])
        self.assertEqual(self.lock.until, self.published())

    # (e) the release of an extended lock
    def extended(self, ttl=200):
        self.held(ttl)
        self.rate_limited_read(100)
        self.assertNotEqual(self.api.ref, self.token, "the lock was not extended: the ref still holds the take")

    def test_a_release_after_an_extension_deletes_the_lock(self):
        self.extended()
        self.assertEqual(release_out(self, self.lock, self.token), "")  # the token is the take: the ref holds a later commit of this run
        self.assertIsNone(self.api.ref)
        self.assertEqual(self.api.steps().count("delete"), 1)

    def test_a_release_with_the_latest_token_after_an_extension_deletes_the_lock(self):
        self.extended()
        self.assertEqual(release_out(self, self.lock, self.api.ref), "")
        self.assertIsNone(self.api.ref)

    def test_a_release_leaves_a_ref_that_is_not_this_runs(self):  # guard: a release must not delete another run's lock, after an extension too (the setup extends)
        self.extended()
        self.api.ref = "rival"
        self.api.commits["rival"] = "merge lock\nexpires: 99999\nowner: someone-else"
        out = release_out(self, self.lock, self.token)
        self.assertIn("not this run's", out)
        self.assertEqual(self.api.ref, "rival")
        self.assertNotIn("delete", self.api.steps())

    def test_a_release_with_a_stale_token_leaves_this_runs_extended_lock(self):  # guard: the token must be this run's too, not only the ref
        self.extended()
        kept = self.api.ref
        out = release_out(self, self.lock, "stale-token")
        self.assertIn("not this run's", out)
        self.assertEqual(self.api.ref, kept)
        self.assertNotIn("delete", self.api.steps())

    def test_a_rate_wait_after_the_release_extends_nothing(self):  # guard: no lock is held after the release
        self.extended()
        release_out(self, self.lock, self.token)
        before = len(self.api.log)
        self.api.limit("lock-read", (1, RATE_API_403, {"Retry_After": 100}))
        self.assertIsNone(self.lock.read("main"))
        steps = self.api.steps(before)
        self.assertNotIn("ref-patch", steps)
        self.assertNotIn("lock-commit-post", steps)
        self.assertEqual(steps.count("pause"), 1)  # the wait itself still happens
        self.assertIsNone(self.lock.until)

class GitLockExtendsForRateWaits(Env):
    """GitLock and Host under a rate-limited `gh` call: the run hands Host.before_wait the lock's extend_for, as confirm does
    (`getattr`, so a lock without one gives None and the host waits plain). The lock is a ref on the bare origin: its text is read there at each pause."""
    NOW, MARGIN = 1000.0, 300

    def published(self):
        if not self.lock_ref():
            return None
        return expires_in(sh(self.bare, "git", "log", "-1", "--format=%B", "refs/heads/merge-lock/main"))

    def held(self, ttl, clock=None):
        """-> the Host. self.glock is a GitLock this run holds, expiring ttl seconds after NOW. `gh` answers self.gh in order (the last repeats); git runs for real."""
        self.clock = clock or Clock(self.NOW)
        self.seen = []
        def pause(seconds):
            self.seen.append((seconds, self.glock.until, self.published()))
            self.clock.pause(seconds)
        self.glock = merge.GitLock(self.co, now=self.clock.now, pause=pause)
        self.token = self.glock.acquire("main", ttl)
        self.gh_calls, self.gh, self.cmds, self.lose_push = 0, [(0, "[]")], [], False  # cmds: every non-gh command after the take
        real = merge.sh
        def fake_sh(args, cwd=None, input=None, env=None):
            if args[0] != "gh":
                self.cmds.append(list(args))
                if self.lose_push and "push" in args and not args[-1].startswith(":"):  # the next ref update lands on origin, and its reply is lost
                    self.lose_push = False
                    real(args, cwd=cwd, input=input, env=env)
                    return 128, NET_HOST
                return real(args, cwd=cwd, input=input, env=env)
            self.gh_calls += 1
            return self.gh[min(self.gh_calls, len(self.gh)) - 1]
        p = unittest.mock.patch.object(merge, "sh", fake_sh)
        p.start(); self.addCleanup(p.stop)
        host = merge.Host(required=["checks"], base="main", minute=60, now=self.clock.now, pause=pause)
        host.before_wait = getattr(self.glock, "extend_for", None)
        return host

    def rival_takes_the_lock(self):
        other = merge.GitLock(self.other, now=self.clock.now)
        other.unlock("main")
        return other.acquire("main", 600)

    def test_a_rate_wait_past_the_expiry_extends_the_lock_on_origin_before_the_wait(self):
        host = self.held(30)  # expires at 1030
        self.gh = [(1, RATE_403), (0, "[]")]
        self.assertEqual(host.gh(["run", "list"]), (0, "[]"))
        self.assertEqual(self.seen, [(60, 1360, 1360)])  # the wait, lock.until and the text on the ref: now + 60 + 300, all read before the wait
        self.assertEqual(self.glock.until, int(self.NOW + 60 + self.MARGIN))

    def test_a_rate_wait_the_expiry_already_covers_extends_nothing(self):  # control
        host = self.held(900)  # expires at 1900
        self.gh = [(1, RATE_403), (0, "[]")]
        host.gh(["run", "list"])
        self.assertEqual(self.seen, [(60, 1900, 1900)])
        self.assertEqual(sh(self.co, "git", "ls-remote", "origin", "refs/heads/merge-lock/main").split()[0], self.token)  # the ref still holds the take

    def test_an_extension_over_a_ref_that_moved_stops_the_run_with_no_wait_and_no_second_try(self):
        host = self.held(30)
        rival = self.rival_takes_the_lock()
        self.gh = [(1, RATE_403)]
        with self.assertRaises(merge.NetStop) as cm:
            host.gh(["run", "list"])
        self.assertRegex(str(cm.exception), r"(?i)merge lock")
        self.assertEqual((self.seen, self.gh_calls), ([], 1))
        self.assertEqual(sh(self.co, "git", "ls-remote", "origin", "refs/heads/merge-lock/main").split()[0], rival)  # the other run's lock is untouched

    def test_the_published_expiry_is_the_one_the_lock_holds_after_the_take_and_after_each_extension(self):  # (c): on a clock that moves between reads
        host = self.held(10, clock=TickClock(self.NOW))
        self.assertEqual(self.glock.until, self.published())
        self.gh = [(1, RATE_403), (0, "[]"), (1, RATE_403), (0, "[]")]
        host.gh(["run", "list"])
        host.gh(["run", "list"])
        self.assertEqual(len(self.seen), 2)
        for wait, until, published in self.seen:
            self.assertEqual(until, published, self.seen)
        self.assertLess(self.seen[0][2], self.seen[1][2])
        self.assertEqual(self.glock.until, self.published())

    # a lock whose expiry has passed is not extended (a rival may already have broken it)
    def expired_stops_the_run(self, at):
        """The lock expires at 1030. The clock reads `at`. The rate-limited call must stop the run: no push, no commit, no wait, no second try."""
        host = self.held(30)
        self.clock.t = at
        self.gh = [(1, RATE_403), (0, "[]")]
        with self.assertRaises(merge.NetStop) as cm:
            host.gh(["run", "list"])
        self.assertRegex(str(cm.exception), r"(?i)merge lock")
        self.assertRegex(str(cm.exception), r"Run again")
        self.assertEqual((self.seen, self.gh_calls), ([], 1))
        self.assertEqual([c for c in self.cmds if "push" in c or "commit-tree" in c], [], "the run wrote a lock commit or pushed on an expired lock")
        self.assertEqual(sh(self.co, "git", "ls-remote", "origin", "refs/heads/merge-lock/main").split()[0], self.token)  # the lock on origin is not touched
        self.assertEqual(self.glock.until, 1030)

    def test_a_rate_wait_on_an_expired_lock_stops_the_run_before_any_write(self):
        self.expired_stops_the_run(1100)

    def test_a_rate_wait_on_a_lock_that_expires_this_second_stops_the_run(self):  # the boundary: acquire frees a lock at expiry <= now
        self.expired_stops_the_run(1030)

    def test_a_rate_wait_on_a_lock_with_one_second_left_is_still_extended(self):  # control: kills a guard that stops too early
        host = self.held(30)
        self.clock.t = 1029
        self.gh = [(1, RATE_403), (0, "[]")]
        self.assertEqual(host.gh(["run", "list"]), (0, "[]"))
        self.assertEqual(self.seen, [(60, 1389, 1389)])

    # a push that lands with a lost reply must still leave a lock that release can delete
    def test_a_release_after_a_push_whose_reply_was_lost_deletes_the_lock(self):
        host = self.held(30)
        self.lose_push = True
        self.gh = [(1, RATE_403), (0, "[]")]
        with self.assertRaises(merge.NetStop):
            host.gh(["run", "list"])
        self.assertNotEqual(sh(self.co, "git", "ls-remote", "origin", "refs/heads/merge-lock/main").split()[0], self.token, "the push did not land: this case tests nothing")
        self.assertEqual(release_out(self, self.glock, self.token), "")
        self.assertFalse(self.lock_ref())

    def extended(self):
        host = self.held(30)
        self.gh = [(1, RATE_403), (0, "[]")]
        host.gh(["run", "list"])
        self.assertNotEqual(sh(self.co, "git", "ls-remote", "origin", "refs/heads/merge-lock/main").split()[0], self.token, "the lock was not extended")

    def test_a_release_after_an_extension_deletes_the_lock(self):  # (e)
        self.extended()
        self.assertEqual(release_out(self, self.glock, self.token), "")
        self.assertFalse(self.lock_ref())

    def test_a_release_leaves_a_ref_that_is_not_this_runs(self):  # (e), guard
        self.extended()
        self.rival_takes_the_lock()
        self.assertIn("not this run's", release_out(self, self.glock, self.token))
        self.assertTrue(self.lock_ref())

    def test_a_release_with_a_stale_token_leaves_this_runs_extended_lock(self):  # (e), guard
        self.extended()
        kept = sh(self.co, "git", "ls-remote", "origin", "refs/heads/merge-lock/main").split()[0]
        self.assertIn("not this run's", release_out(self, self.glock, "0" * 40))
        self.assertEqual(sh(self.co, "git", "ls-remote", "origin", "refs/heads/merge-lock/main").split()[0], kept)

class HostDefaultBranchRateRetry(unittest.TestCase):
    """host_default_branch (`gh api repos/{owner}/{repo}`, run in the checkout's root) on a rate-limit error. It retries like Host.gh:
    the ladder (60, 300, 900 s), three retries, then NetStop. The function has no pause parameter, so the pauses are recorded by
    patching merge.time.sleep. A fix must call time.sleep at call time, or this test sleeps for real."""
    def patched(self, *seq):
        """merge.sh answers `seq` in order (the last repeats). merge.time.sleep records. -> (gh calls, pauses). self.cwds holds the folder of each call."""
        seq, calls, pauses, self.cwds = list(seq), [], [], []
        def fake(args, cwd=None, input=None, env=None):
            calls.append(args); self.cwds.append(cwd)
            return seq.pop(0) if len(seq) > 1 else seq[0]
        for target in ((merge, "sh", fake), (merge.time, "sleep", pauses.append)):
            p = unittest.mock.patch.object(*target)
            p.start(); self.addCleanup(p.stop)
        return calls, pauses

    def test_the_default_branch_is_one_rest_read_of_the_repo_in_the_checkout(self):
        calls, pauses = self.patched((0, '{"default_branch":"trunk","full_name":"o/r"}'))
        self.assertEqual(merge.host_default_branch("/repo"), "trunk")
        self.assertEqual(len(calls), 1, calls)
        self.assertEqual(calls[0][:3], ["gh", "api", "repos/{owner}/{repo}"], calls)  # REST: `gh repo view` is GraphQL
        self.assertEqual(self.cwds, ["/repo"])
        self.assertNotIn("graphql", " ".join(calls[0]))

    def test_a_repo_answer_without_a_default_branch_is_a_stop(self):
        for body in ('{"message":"Not Found"}', '{"default_branch":null}', "[]", "not json"):
            with self.subTest(body=body):
                self.patched((0, body))
                with self.assertRaises(merge.Stop):
                    merge.host_default_branch("/repo")

    def test_a_rate_limited_repo_read_is_retried_and_returns_the_default_branch(self):
        calls, pauses = self.patched((1, RATE_API_403), (0, '{"default_branch":"trunk"}'))
        try:
            got = merge.host_default_branch("/repo")
        except merge.Stop as e:
            self.fail(f"host_default_branch stopped on a rate limit: {e}")
        self.assertEqual(got, "trunk")
        self.assertEqual((len(calls), pauses), (2, RATE_LADDER[:1]))

    def test_a_rate_limit_that_never_clears_is_a_net_stop_after_three_retries(self):
        calls, pauses = self.patched((1, RATE_API_403))
        try:
            merge.host_default_branch("/repo")
        except merge.NetStop:
            pass
        except merge.Stop as e:
            self.fail(f"a rate limit that never clears stopped as a plain Stop, not a NetStop: {e}")
        else:
            self.fail("host_default_branch returned without a stop")
        self.assertEqual((len(calls), pauses), (4, RATE_LADDER))

    def test_a_502_is_retried_after_the_normal_pause_and_then_a_net_stop(self):
        calls, pauses = self.patched((1, rest_err(502, "Server Error")))
        with self.assertRaises(merge.NetStop):
            merge.host_default_branch("/repo")
        self.assertEqual((len(calls), pauses), (4, [merge.NET_PAUSE] * 3))

    def test_a_permission_403_stops_at_once(self):
        calls, pauses = self.patched((1, PLAIN_403_API))
        with self.assertRaises(merge.Stop):
            merge.host_default_branch("/repo")
        self.assertEqual((len(calls), pauses), (1, []))

# ------------------------------------------------------------------ CI time caps
# The merge tool warns when a job has used over 70% of its cap. The job times come from the check runs
# read the tool already makes (their started_at and completed_at). A job's cap is read
# from the workflow files on disk. A job ended by its cap is a check cancelled after its full cap of minutes.
# That verdict is "re-cap or split", not a test failure. When merge.deadlineMinutes is below the floor, load_config
# waits the floor and prints one fix line. The floor is the largest job timeout-minutes in the base's workflows,
# plus 5, clamped at 360. A provisional 60-minute cap counts.
# CapsHost fails the test on any gh call other than the REST reads the merge tool makes (the pull request, the check runs, the statuses) and run list.
from datetime import datetime, timedelta, timezone

HEAD_SHA = "a" * 40
START = datetime(2026, 10, 22, 10, 0, 0, tzinfo=timezone.utc)
CAP_LINE = "job checks: 40 of 50 min; raise the cap from measured runs, or split its slowest suite"
RE_CAP = "re-cap or split"
REPO = pathlib.Path(HERE).parent

CHECKS_WORKFLOW = "\n".join([
    "name: checks", "on: push", "jobs:",
    "  checks:", "    runs-on: ubuntu-latest", "    timeout-minutes: 50", "    steps:", "      - run: echo ok",
    "  scope:", "    runs-on: ubuntu-latest", "    timeout-minutes: 10", "    steps:", "      - run: echo ok",
]) + "\n"

# A new job with the provisional 60-minute cap (fewer than 5 green runs). The floor is then 65.
PROVISIONAL_WORKFLOW = "\n".join([
    "name: checks", "on: push", "jobs:",
    "  checks:", "    runs-on: ubuntu-latest", "    timeout-minutes: 50", "    steps:", "      - run: echo ok",
    "  fresh:", "    runs-on: ubuntu-latest",
    "    # provisional: fewer than 5 green runs", "    timeout-minutes: 60", "    steps:", "      - run: echo ok",
]) + "\n"

# Max job cap in this file is 50. Traps that a naive scan would read as caps: a step cap of 90, a
# block-scalar line of 99, a comment of 120, a quoted string holding "# timeout-minutes: 130", and a lone quote.
TRAPS_WORKFLOW = "\n".join([
    "name: checks", "on: push", "jobs:",
    "  checks:", "    runs-on: ubuntu-latest", "    timeout-minutes: 50", "    steps:",
    "      - run: echo it's fine",
    "      - run: |", "          echo \"timeout-minutes: 99\"", "          # timeout-minutes: 120",
    "      - run: \"echo # timeout-minutes: 130\"",
    "      - name: slow step", "        timeout-minutes: 90", "        run: echo ok",
]) + "\n"

SYNC_WORKFLOW = "\n".join([
    "name: sync", "on: push", "jobs:",
    "  sync:", "    runs-on: ubuntu-latest", "    timeout-minutes: 60", "    steps:", "      - run: echo ok",
]) + "\n"


def at(minutes):
    return (START + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def check(name, bucket, minutes):
    """One check run as a row of name, bucket, link, startedAt and completedAt: the job ran from START for `minutes`. CapsHost serves it as a REST check run."""
    return {"name": name, "bucket": bucket, "link": "https://github.com/shivinate7/claude-settings/actions/runs/100/job/200",
            "startedAt": at(0), "completedAt": at(minutes)}


def run(conclusion):
    return {"name": "checks", "status": "completed", "conclusion": conclusion, "databaseId": 100}


def stamp_text(deadline):
    return json.dumps({"defaultBranch": "main", "merge": {"method": "merge", "deadlineMinutes": deadline}}) + "\n"


def push_base(env, files):
    """Commit `files` (path -> text or bytes) on origin's main from the other clone, then fast-forward env.co to it."""
    o = env.other
    sh(o, "git", "fetch", "-q", "origin")
    sh(o, "git", "checkout", "-q", "-B", "main", "origin/main")
    for path, data in files.items():
        full = os.path.join(o, *path.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
    sh(o, "git", "add", "-A")
    sh(o, "git", "commit", "-q", "-m", "base files")
    sh(o, "git", "push", "-q", "origin", "main")
    sh(env.co, "git", "pull", "-q", "--ff-only", "origin", "main")
    head_takes_base(env)


class CapsHost(merge.Host):
    """A real Host whose only seam is `gh`. It serves fixture REST objects for the calls the merge tool makes: the pull request, the check runs of
    its head (with started_at and completed_at) and the commit statuses (none), and run list. Any other gh call fails the test."""
    def __init__(self, cwd, checks, runs):
        super().__init__(required=["checks"], base="main", minute=60, pause=lambda s: None, cwd=cwd)
        self.fixture = {"checks": checks, "runs": runs}

    def gh(self, args, cwd=None):
        if args[:2] == ["run", "list"]:
            return 0, json.dumps(self.fixture["runs"])
        if args[:1] != ["api"]:
            raise AssertionError(f"unexpected gh call: {args}")
        method, path, params, flags, jq = REST.parse(args[1:])
        m = re.fullmatch(r"repos/(?:\{owner\}/\{repo\}|[^/]+/[^/]+)/(.*)", path)
        rel = m.group(1) if m else path
        if method == "GET" and rel == "pulls/7":
            return 0, REST.one(REST.pull(7, HEAD_SHA, "feat", "main"), jq)
        if method == "GET" and rel == f"commits/{HEAD_SHA}/check-runs":
            rows = [REST.check_run((r["name"], r["bucket"], r["link"]), i, r.get("startedAt"), r.get("completedAt")) for i, r in enumerate(self.fixture["checks"])]
            return 0, REST.listing(rows, "check_runs", params, flags, jq, 100, {"total_count": len(rows)})
        if method == "GET" and rel == f"commits/{HEAD_SHA}/status":
            return 0, REST.listing([], "statuses", params, flags, jq, 100, {"state": "pending", "total_count": 0})  # GitHub's combined state for no statuses
        raise AssertionError(f"unexpected gh call: {args}")


class JobCapWarning(Env):
    """Case a (the 70% line) and case b (the timeout verdict), through a real Host with fixture gh output."""
    def setUp(self):
        super().setUp()
        push_base(self, {".github/workflows/checks.yml": CHECKS_WORKFLOW})

    def read(self, host, fn):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = fn(host)
        return result, out.getvalue()

    def test_a_checks_read_prints_one_line_for_a_job_at_80_percent_and_none_at_50(self):
        host = CapsHost(self.co, [check("checks", "pass", 40), check("scope", "pass", 5)], [run("success")])
        _, out = self.read(host, lambda h: h.checks(7))
        hits = [l for l in out.splitlines() if "job checks:" in l]
        self.assertEqual(len(hits), 1, out)
        self.assertIn(CAP_LINE, hits[0], out)
        self.assertNotIn("job scope", out)

    def test_a_wait_over_a_green_run_prints_the_line_and_still_merges(self):
        host = CapsHost(self.co, [check("checks", "pass", 40), check("scope", "pass", 5)], [run("success")])
        (ok, why), out = self.read(host, lambda h: h.wait_checks(7, HEAD_SHA, 30))
        self.assertTrue(ok, why)
        self.assertIn(CAP_LINE, out)

    def test_a_cancel_at_the_full_cap_is_a_timeout_not_a_test_failure(self):
        host = CapsHost(self.co, [check("checks", "cancel", 50)], [run("cancelled")])
        (ok, why), _ = self.read(host, lambda h: h.wait_checks(7, HEAD_SHA, 30))
        self.assertFalse(ok, why)
        self.assertIn(RE_CAP, why)

    def test_a_cancel_sooner_than_the_cap_is_not_a_timeout(self):
        host = CapsHost(self.co, [check("checks", "cancel", 2)], [run("cancelled")])
        (ok, why), _ = self.read(host, lambda h: h.wait_checks(7, HEAD_SHA, 30))
        self.assertFalse(ok, why)
        self.assertNotIn(RE_CAP, why)


class StampDeadlineFloor(Env):
    """Recovery rule: a deadline under the floor does not stop the merge. The merge waits max(deadlineMinutes, floor)
    and prints one line naming the fix. The floor is the largest job timeout-minutes plus 5, clamped at 360."""
    def test_a_deadline_under_the_largest_cap_plus_five_waits_the_floor_and_names_the_fix(self):
        push_base(self, {".github/stamp.json": merge_stamp_text(54), ".github/workflows/checks.yml": CHECKS_WORKFLOW})
        rc, out, waits = confirmed_wait(self)
        self.assertEqual(rc, 0, out)
        self.assertEqual(set(waits), {55}, out)
        self.assertEqual(out.count(fix_line(55)), 1, out)

    def test_a_deadline_at_the_largest_cap_plus_five_waits_itself_and_names_nothing(self):
        push_base(self, {".github/stamp.json": merge_stamp_text(55), ".github/workflows/checks.yml": CHECKS_WORKFLOW})
        rc, out, waits = confirmed_wait(self)
        self.assertEqual(rc, 0, out)
        self.assertEqual(set(waits), {55}, out)
        self.assertNotIn("raise merge.deadlineMinutes", out)

    def test_the_floor_is_the_largest_job_cap_in_any_file_and_ignores_steps_comments_and_strings(self):
        push_base(self, {".github/stamp.json": merge_stamp_text(64), ".github/workflows/checks.yml": TRAPS_WORKFLOW,
                         ".github/workflows/sync.yml": SYNC_WORKFLOW})
        rc, out, waits = confirmed_wait(self)
        self.assertEqual(rc, 0, out)
        self.assertEqual(set(waits), {65}, "the traps (99, 120, 130, step cap 90) must not raise the floor")
        self.assertEqual(out.count(fix_line(65)), 1, out)

    def test_a_provisional_sixty_minute_cap_sets_the_floor_at_sixty_five(self):
        push_base(self, {".github/stamp.json": merge_stamp_text(55), ".github/workflows/checks.yml": PROVISIONAL_WORKFLOW})
        rc, out, waits = confirmed_wait(self)
        self.assertEqual(rc, 0, out)
        self.assertEqual(set(waits), {65}, out)
        self.assertEqual(out.count(fix_line(65)), 1, out)

    def test_a_repo_with_no_workflow_has_no_floor(self):
        push_base(self, {".github/stamp.json": merge_stamp_text(5)})
        rc, out, waits = confirmed_wait(self)
        self.assertEqual(rc, 0, out)
        self.assertEqual(set(waits), {5}, out)
        self.assertNotIn("raise merge.deadlineMinutes", out)


class RepoDeadlineFloor(unittest.TestCase):
    """The repo's own merge.deadlineMinutes against the job caps in its own workflow files. Red while the wait is below the floor."""
    def test_the_repos_deadline_is_at_least_the_largest_job_cap_plus_five(self):
        deadline = json.loads((REPO / ".github" / "stamp.json").read_bytes())["merge"]["deadlineMinutes"]
        caps = [int(m.group(1)) for p in sorted((REPO / ".github" / "workflows").glob("*.yml"))
                for m in re.finditer(rb"^ {4}timeout-minutes: *(\d+)\r?$", p.read_bytes(), re.M)]
        self.assertTrue(caps, "no job timeout-minutes found under .github/workflows")
        self.assertGreaterEqual(deadline, max(caps) + 5,
                                f"merge.deadlineMinutes is {deadline}; the largest job cap is {max(caps)}, so it must be at least {max(caps) + 5}")


# ------------------------------------------------------------------ CI time caps: guard read, root caps, quoted caps
def captured(fn):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = fn()
    return result, out.getvalue()


def cap_workflow(cap_text):
    """A one-job workflow: job `checks` with `timeout-minutes: <cap_text>`, written as the file holds it."""
    return "\n".join([
        "name: checks", "on: push", "jobs:",
        "  checks:", "    runs-on: ubuntu-latest", f"    timeout-minutes: {cap_text}", "    steps:", "      - run: echo ok",
    ]) + "\n"


# Job checks has a literal 50 and job fresh an expression. Only the literal sets the floor, which is 55.
MIXED_WORKFLOW = "\n".join([
    "name: checks", "on: push", "jobs:",
    "  checks:", "    runs-on: ubuntu-latest", "    timeout-minutes: 50", "    steps:", "      - run: echo ok",
    "  fresh:", "    runs-on: ubuntu-latest", "    timeout-minutes: ${{ inputs.cap }}", "    steps:", "      - run: echo ok",
]) + "\n"

# Job checks has an expression cap (unknown) and job scope a literal 10.
EXPR_AND_LITERAL_WORKFLOW = "\n".join([
    "name: checks", "on: push", "jobs:",
    "  checks:", "    runs-on: ubuntu-latest", "    timeout-minutes: ${{ inputs.cap }}", "    steps:", "      - run: echo ok",
    "  scope:", "    runs-on: ubuntu-latest", "    timeout-minutes: 10", "    steps:", "      - run: echo ok",
]) + "\n"


class CapReviewRound1(Env):
    """The guard's read prints nothing (F1), caps come from the repo root (F3), and quoted or
    expression caps are read as the merge tool reads them (F5)."""
    def setUp(self):
        super().setUp()
        push_base(self, {".github/workflows/checks.yml": CHECKS_WORKFLOW})

    def test_f1_head_read_writes_nothing_to_stdout_when_a_job_is_over_seventy_percent(self):
        host = CapsHost(self.co, [check("checks", "pass", 40), check("scope", "pass", 5)], [run("success")])
        (verdict, detail), out = captured(lambda: host.head_read(7))
        self.assertEqual(verdict, "green", detail)
        self.assertEqual(out, "", "head_read is the guard's read and must print nothing")

    def test_f3_a_cancel_at_the_full_cap_is_a_timeout_when_run_from_a_subdirectory(self):
        old = os.getcwd()
        os.chdir(os.path.join(self.co, "docs", "decisions"))
        self.addCleanup(os.chdir, old)
        host = CapsHost(None, [check("checks", "cancel", 50)], [run("cancelled")])
        (ok, why), _ = captured(lambda: host.wait_checks(7, HEAD_SHA, 30))
        self.assertFalse(ok, why)
        self.assertIn(RE_CAP, why)

    def test_f5_a_double_quoted_cap_reads_as_its_number_for_the_warning(self):
        push_base(self, {".github/workflows/checks.yml": cap_workflow('"50"')})
        host = CapsHost(self.co, [check("checks", "pass", 40)], [run("success")])
        _, out = captured(lambda: host.checks(7))
        self.assertIn(CAP_LINE, out)

    def test_f5_a_single_quoted_cap_reads_as_its_number_for_a_timeout(self):
        push_base(self, {".github/workflows/checks.yml": cap_workflow("'50'")})
        host = CapsHost(self.co, [check("checks", "cancel", 50)], [run("cancelled")])
        (ok, why), _ = captured(lambda: host.wait_checks(7, HEAD_SHA, 30))
        self.assertFalse(ok, why)
        self.assertIn(RE_CAP, why)

    def test_f5_an_expression_cap_is_unknown_so_it_gives_no_warning_and_no_timeout(self):
        push_base(self, {".github/workflows/checks.yml": EXPR_AND_LITERAL_WORKFLOW})
        host = CapsHost(self.co, [check("checks", "pass", 40), check("scope", "pass", 9)], [run("success")])
        _, out = captured(lambda: host.checks(7))
        self.assertIn("job scope: 9 of 10 min", out, "the literal cap must still warn: the control proves the path is live")
        self.assertNotIn("job checks", out)
        host = CapsHost(self.co, [check("checks", "cancel", 50)], [run("cancelled")])
        (ok, why), _ = captured(lambda: host.wait_checks(7, HEAD_SHA, 30))
        self.assertFalse(ok, why)
        self.assertNotIn(RE_CAP, why)


def merge_stamp_text(deadline):
    """A base stamp.json as this suite's CONFIG, with the given merge.deadlineMinutes, so a merge can run through it."""
    merge_block = {"method": "merge", "deadlineMinutes": deadline, "afterMerge": [], "deleteBranch": True}
    return json.dumps({**CONFIG, "merge": merge_block}) + "\n"


class DeadlineRecorder(FakeHost):
    """FakeHost that records the deadline each wait is given."""
    def __init__(self, root, other, branch="feat"):
        super().__init__(root, other, branch)
        self.deadlines = []

    def wait_checks(self, n, sha, d, prior=None):
        self.deadlines.append(d)
        return super().wait_checks(n, sha, d, prior)


def confirmed_wait(env):
    """Merge the fixture PR with --confirm. -> (rc, output, the deadline each wait was given)."""
    host = DeadlineRecorder(env.co, env.other)
    rc, out = env.run_merge("7", "--confirm", host=host)
    return rc, out, host.deadlines


def fix_line(floor):
    return f"raise merge.deadlineMinutes in .github/stamp.json to at least {floor}"


class CapReviewFloor(Env):
    """Recovery rule: the floor is min(largest cap + 5, 360) (F2), and a quoted or expression cap
    is read as the merge tool reads it when it sets the floor (F5)."""
    def test_f2_a_cap_of_356_waits_the_clamped_floor_of_360_at_a_deadline_of_360(self):
        push_base(self, {".github/stamp.json": merge_stamp_text(360), ".github/workflows/checks.yml": cap_workflow("356")})
        rc, out, waits = confirmed_wait(self)
        self.assertEqual(rc, 0, out)
        self.assertEqual(set(waits), {360}, out)
        self.assertNotIn("raise merge.deadlineMinutes", out)

    def test_f2_a_cap_of_360_waits_the_clamped_floor_of_360_at_a_deadline_of_359(self):
        push_base(self, {".github/stamp.json": merge_stamp_text(359), ".github/workflows/checks.yml": cap_workflow("360")})
        rc, out, waits = confirmed_wait(self)
        self.assertEqual(rc, 0, out)
        self.assertEqual(set(waits), {360}, out)
        self.assertEqual(out.count(fix_line(360)), 1, out)

    def test_f5_a_double_quoted_cap_sets_the_floor_like_a_plain_cap(self):
        push_base(self, {".github/stamp.json": merge_stamp_text(54), ".github/workflows/checks.yml": cap_workflow('"50"')})
        rc, out, waits = confirmed_wait(self)
        self.assertEqual(rc, 0, out)
        self.assertEqual(set(waits), {55}, out)
        self.assertEqual(out.count(fix_line(55)), 1, out)

    def test_f5_an_expression_cap_sets_no_floor(self):
        push_base(self, {".github/stamp.json": merge_stamp_text(5), ".github/workflows/checks.yml": cap_workflow("${{ inputs.cap }}")})
        rc, out, waits = confirmed_wait(self)
        self.assertEqual(rc, 0, out)
        self.assertEqual(set(waits), {5}, out)
        self.assertNotIn("raise merge.deadlineMinutes", out)

    def test_f5_the_literal_cap_sets_the_floor_beside_an_expression_cap(self):
        push_base(self, {".github/stamp.json": merge_stamp_text(54), ".github/workflows/checks.yml": MIXED_WORKFLOW})
        rc, out, waits = confirmed_wait(self)
        self.assertEqual(rc, 0, out)
        self.assertEqual(set(waits), {55}, out)
        self.assertEqual(out.count(fix_line(55)), 1, out)


class DuplicateJobIds(Env):
    """F8: one job id in two workflow files keeps the larger cap, for the floor and for the warning."""
    def test_f8_the_floor_keeps_the_larger_of_two_caps_for_one_job_id(self):
        push_base(self, {".github/stamp.json": merge_stamp_text(104),
                         ".github/workflows/a.yml": cap_workflow("100"),
                         ".github/workflows/b.yml": cap_workflow("10")})
        rc, out, waits = confirmed_wait(self)
        self.assertEqual(rc, 0, out)
        self.assertEqual(set(waits), {105}, out)
        self.assertEqual(out.count(fix_line(105)), 1, out)

    def test_f8_the_warning_keeps_the_larger_of_two_caps_for_one_job_id(self):
        push_base(self, {".github/workflows/a.yml": cap_workflow("100"), ".github/workflows/b.yml": cap_workflow("10")})
        host = CapsHost(self.co, [check("checks", "pass", 60)], [run("success")])
        _, out = captured(lambda: host.checks(7))
        self.assertNotIn("job checks", out, "60 of 100 is under 70 percent: the smaller cap of 10 must not be the one kept")


class NestedCheckout(Env):
    """F9: a folder holding .git ends the search for workflows. A nested checkout with none reads none, not the parent's."""
    def setUp(self):
        super().setUp()
        push_base(self, {".github/workflows/checks.yml": CHECKS_WORKFLOW})

    def test_f9_a_nested_checkout_with_no_workflows_reads_no_cap_from_the_parent(self):
        nested = os.path.join(self.co, "nested")
        os.makedirs(nested)
        sh(nested, "git", "init", "-q")
        host = CapsHost(nested, [check("checks", "cancel", 50)], [run("cancelled")])
        (ok, why), _ = captured(lambda: host.wait_checks(7, HEAD_SHA, 30))
        self.assertNotIn(RE_CAP, why)


MAIN_WORKFLOW = "\n".join([
    "name: checks", "on: push", "jobs:",
    "  checks:", "    runs-on: ubuntu-latest", "    timeout-minutes: 50", "    steps:", "      - run: echo ok",
    "  scope:", "    runs-on: ubuntu-latest", "    timeout-minutes: 10", "    steps:", "      - run: echo ok",
    "  checks-macos:", "    runs-on: macos-latest", "    timeout-minutes: 30", "    steps:", "      - run: echo ok",
]) + "\n"


def main_run(id_, conclusion, status="completed", name="checks", event="push", path=".github/workflows/checks.yml"):
    """One run on main, as `GET actions/runs` lists it."""
    return {"id": id_, "name": name, "path": path, "event": event, "status": status, "conclusion": conclusion if status == "completed" else None,
            "head_sha": f"{id_:040x}", "html_url": f"https://github.com/o/r/actions/runs/{id_}"}


def main_job(name, conclusion, minutes=1):
    """One completed job of a main run, as `GET actions/runs/<id>/jobs` lists it: it ran from START for `minutes`."""
    return {"name": name, "status": "completed", "conclusion": conclusion, "started_at": at(0), "completed_at": at(minutes),
            "html_url": f"https://github.com/o/r/actions/runs/1/job/{len(name)}"}


class MainRunsHost(FakeHost, merge.Host):
    """FakeHost for the flow; the real Host.base_state over scripted REST. `main_runs`: main's push runs, newest first. `jobs`: run id -> jobs.
    `runs_fail` / `jobs_fail`: that read fails with this text."""
    base_state = getattr(merge.Host, "base_state", None)

    def __init__(self, root, other, main_runs, jobs, runs_fail=None, jobs_fail=None):
        FakeHost.__init__(self, root, other)
        self.ignore, self.cwd, self.warned = {}, root, set()
        self.main_runs, self.jobs, self.runs_fail, self.jobs_fail, self.reads = main_runs, jobs, runs_fail, jobs_fail, []

    def api(self, rel, *extra, method="GET", fields=None):
        self.reads.append(rel)
        assert (rel, method, fields.get("branch")) == ("actions/runs", "GET", "main"), (rel, fields)
        if self.runs_fail:
            return 1, self.runs_fail
        runs = [r for r in self.main_runs if fields.get("event") in (None, r["event"])]  # GitHub's event filter, when one is sent
        return 0, json.dumps({"total_count": len(runs), "workflow_runs": runs})

    def pages(self, rel, key=None, fields=None):
        self.reads.append(rel)
        m = re.fullmatch(r"actions/runs/(\d+)/jobs", rel)
        assert m and key == "jobs", rel
        if self.jobs_fail:
            raise merge.Stop(f"reading {rel} from GitHub failed: {self.jobs_fail}")
        return self.jobs[int(m.group(1))]


class RedMainBrake(Env):
    """c166: no batch merge onto a red main. The red-main check judges main's latest completed run, job by job (decision no-merge-onto-red-main)."""
    def setUp(self):
        super().setUp()
        push_base(self, {".github/workflows/checks.yml": MAIN_WORKFLOW})  # the caps the timeout verdict reads

    def go(self, runs, jobs, *flags, confirm=True, **kw):
        self.host = MainRunsHost(self.co, self.other, runs, jobs, **kw)
        before = self.refs()
        rc, out = self.run_merge("7", *(["--confirm"] if confirm else []), *flags)
        return rc, out, before

    def refused(self, rc, out, before):
        self.assertEqual(rc, 1, out)
        self.assertFalse(getattr(self.host, "merged", False), out)
        self.assertEqual(self.refs(), before, "a refused run claims and pushes nothing")
        self.assertFalse(self.lock_ref(), "the lock is freed")

    def merged(self, rc, out):
        self.assertEqual(rc, 0, out)
        self.assertTrue(getattr(self.host, "merged", False), out)

    # Oct 13-14: the latest main run has one failed job among passes, and a job cancelled at its cap.
    OCT14 = {901: [main_job("scope", "success"), main_job("checks", "failure", 20), main_job("checks-macos", "cancelled", 30)]}

    def test_a_red_main_refuses_and_names_the_red_job_and_the_run(self):
        rc, out, before = self.go([main_run(901, "failure")], self.OCT14)
        self.refused(rc, out, before)
        self.assertIn("checks: fail", out)
        self.assertIn("run 901", out)
        self.assertIn("https://github.com/o/r/actions/runs/901", out)
        self.assertNotIn("checks-macos", out, "a job cancelled at its cap is not a red step")
        self.assertIn("--base-red-ok", out)

    def test_a_main_run_red_only_by_a_timeout_does_not_refuse(self):
        jobs = {902: [main_job("scope", "success"), main_job("checks", "success", 20), main_job("checks-macos", "cancelled", 30)]}
        rc, out, _ = self.go([main_run(902, "failure")], jobs)
        self.merged(rc, out)

    def test_a_main_run_red_only_by_a_cancelled_twin_job_does_not_refuse(self):
        # the timeout explains the failure; the cancelled twin beside its passing job is no red job
        jobs = {903: [main_job("checks-macos", "cancelled", 30), main_job("checks", "cancelled", 2), main_job("checks", "success", 20)]}
        rc, out, _ = self.go([main_run(903, "failure")], jobs)
        self.merged(rc, out)

    def test_a_newest_run_cancelled_with_no_red_job_is_unknown_not_an_older_run(self):
        # on main the twin rule would reach across commits: the cancelled run is judged itself, never swapped for an older green one
        jobs = {904: [main_job("scope", "success"), main_job("checks", "cancelled", 2)]}
        rc, out, before = self.go([main_run(904, "cancelled"), main_run(903, "success")], jobs)
        self.refused(rc, out, before)
        self.assertIn("UNKNOWN", out)
        self.assertIn("run 904", out)

    def test_a_newest_run_cancelled_by_a_timeout_is_not_red(self):
        jobs = {904: [main_job("scope", "success"), main_job("checks-macos", "cancelled", 30)]}
        rc, out, _ = self.go([main_run(904, "cancelled"), main_run(903, "failure")], jobs)
        self.merged(rc, out)

    def test_a_failed_run_with_no_judged_job_is_red(self):
        # a broken workflow file: startup_failure and no job; or failure with every job passing
        for conclusion, jobs in (("startup_failure", []), ("failure", [main_job("checks", "success", 20)])):
            with self.subTest(conclusion=conclusion, jobs=len(jobs)):
                rc, out, before = self.go([main_run(913, conclusion)], {913: jobs})
                self.refused(rc, out, before)
                self.assertIn("run 913", out)
                self.assertIn(conclusion, out)

    def test_a_run_of_a_workflow_file_gone_from_main_is_not_judged(self):
        # a renamed or deleted workflow: its last red run stays in the page, but no new run will ever replace it
        rc, out, _ = self.go([main_run(910, "success", name="checks"), main_run(909, "failure", path=".github/workflows/old-checks.yml")],
                             {909: [main_job("checks", "failure", 20)]})
        self.merged(rc, out)

    def test_runs_are_judged_per_workflow_file_not_per_name(self):
        # the workflow's name changed in the same file: the newer run is the verdict
        rc, out, _ = self.go([main_run(912, "success", name="checks"), main_run(911, "failure", name="old-checks")], {911: [main_job("checks", "failure", 20)]})
        self.merged(rc, out)

    def green_run_of(self, event):
        rc, out, _ = self.go([main_run(915, "success", event=event), main_run(914, "failure")], {914: [main_job("checks", "failure", 20)]})
        self.merged(rc, out)

    def test_a_green_dispatch_run_clears_an_older_red_push_run(self):
        self.green_run_of("workflow_dispatch")  # `gh workflow run checks.yml --ref main`, the remedy classify prints

    def test_a_green_schedule_run_clears_an_older_red_push_run(self):
        self.green_run_of("schedule")

    def test_a_pull_request_run_is_not_judged(self):
        rc, out, _ = self.go([main_run(917, "failure", event="pull_request"), main_run(916, "success")], {917: [main_job("checks", "failure", 20)]})
        self.merged(rc, out)

    def test_a_newer_run_in_progress_is_skipped_for_the_latest_completed_one(self):
        rc, out, before = self.go([main_run(906, None, status="in_progress"), main_run(905, "failure")],
                                  {905: [main_job("checks", "failure", 20)]})
        self.refused(rc, out, before)
        self.assertIn("run 905", out)
        self.assertNotIn("run 906", out)
        self.assertNotIn("actions/runs/906/jobs", self.host.reads, "a run in progress is not judged")

    def test_a_green_latest_run_reads_no_jobs_and_merges(self):
        rc, out, _ = self.go([main_run(908, "success"), main_run(907, "failure")], {})
        self.merged(rc, out)
        self.assertEqual(self.host.reads.count("actions/runs"), 1)
        self.assertFalse([r for r in self.host.reads if r.endswith("/jobs")], "a green run needs no jobs read")

    def test_the_reason_flag_lifts_the_check_and_logs_its_reason(self):
        rc, out, _ = self.go([main_run(901, "failure")], self.OCT14, "--base-red-ok", "this batch carries the checks fix")
        self.merged(rc, out)
        self.assertIn("run 901", out)
        self.assertIn("--base-red-ok, reason: this batch carries the checks fix", out)
        self.assertNotIn("Owner override", out, "a reason flag Claude can type is not the owner's override")

    def test_the_flag_with_no_reason_does_not_lift(self):
        rc, out, before = self.go([main_run(901, "failure")], self.OCT14, "--base-red-ok", " ")
        self.refused(rc, out, before)

    def test_unreadable_runs_are_unknown_and_refuse(self):
        rc, out, before = self.go([], {}, runs_fail="gh: HTTP 500: Server Error")
        self.refused(rc, out, before)
        self.assertIn("UNKNOWN", out)
        self.assertNotIn("is red", out, "an unread run is never called red")
        self.assertIn("--base-red-ok", out)

    def test_unreadable_jobs_are_unknown_and_refuse(self):
        rc, out, before = self.go([main_run(901, "failure")], {}, jobs_fail="HTTP 404")
        self.refused(rc, out, before)
        self.assertIn("UNKNOWN", out)

    def test_the_reason_flag_lifts_unknown_and_logs_it(self):
        rc, out, _ = self.go([], {}, "--base-red-ok", "GitHub is down, owner read main", runs_fail="gh: HTTP 500")
        self.merged(rc, out)
        self.assertIn("UNKNOWN", out)
        self.assertIn("--base-red-ok, reason: GitHub is down, owner read main", out)

    def test_the_preview_reports_a_red_main_and_presses_nothing(self):
        rc, out, before = self.go([main_run(901, "failure")], self.OCT14, confirm=False)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.refs(), before)
        line = [l for l in out.splitlines() if l.strip().startswith("main run:")]
        self.assertEqual(len(line), 1, out)
        self.assertIn("red", line[0])
        self.assertIn("run 901", line[0])
        self.assertIn("--confirm refuses it", line[0])

class PinnedMismatchStopsMain(Env):
    """c189 part 1: main() itself refuses a pinned list that disagrees with protection, before any lock is taken."""
    def test_main_refuses_before_taking_the_lock(self):
        fake = self.host
        def refuse():
            raise merge.Stop("merge.requiredChecks pins gates, but the branch protection of main requires checks.")
        fake.refuse_pinned_mismatch = refuse
        with unittest.mock.patch.object(merge, "Host", lambda: fake):
            out_buf, err = io.StringIO(), io.StringIO()
            cwd = os.getcwd()
            os.chdir(self.co)
            try:
                with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err):
                    rc = merge.main(["7", "--confirm"], lock=self.lock)
            finally:
                os.chdir(cwd)
        self.assertEqual(rc, 1, out_buf.getvalue() + err.getvalue())
        self.assertIn("pins gates", err.getvalue())
        self.assertFalse(self.lock_ref())

class ProtectionHost(merge.Host):
    """Host whose branch protection read answers `contexts` (a list) or fails (None); no gh."""
    def __init__(self, required, contexts):
        super().__init__(required=required, base="main", pause=lambda s: None)
        self.contexts = contexts

    def gh(self, args, cwd=None):
        return (0, json.dumps(self.contexts)) if self.contexts is not None else (1, "HTTP 404: Not Found")

class MergeChecksFromProtection(unittest.TestCase):
    """c189 part 1: main's own stamp.json reads the required checks from branch protection, and a pinned list that disagrees with it is refused."""
    def test_main_stamp_reads_required_checks_from_protection(self):
        with open(os.path.join(HERE, "..", ".github", "stamp.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["merge"]["requiredChecks"], "protection")

    def test_a_pinned_list_that_disagrees_with_protection_is_refused_naming_both_sets(self):  # #746: pinned gates*, protection held checks*
        host = ProtectionHost(["gates", "gates-guard"], ["checks", "checks-guard"])
        with self.assertRaises(merge.Stop) as cm:
            host.refuse_pinned_mismatch()
        for name in ("gates", "gates-guard", "checks", "checks-guard"):
            self.assertIn(name, str(cm.exception))

    def test_a_pinned_list_equal_to_protection_passes_in_any_order(self):
        ProtectionHost(["b", "a"], ["a", "b"]).refuse_pinned_mismatch()

    def test_an_empty_protection_leaves_the_pinned_list_alone(self):
        ProtectionHost(["a"], []).refuse_pinned_mismatch()

    def test_an_unreadable_protection_says_so_and_keeps_the_pinned_list(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ProtectionHost(["a"], None).refuse_pinned_mismatch()
        self.assertIn("pinned", out.getvalue())

    def test_protection_mode_reads_nothing_extra(self):
        host = ProtectionHost("protection", ["x"])
        host.gh = lambda *a, **k: self.fail("a gh read was made")
        host.refuse_pinned_mismatch()

@unittest.skipIf(os.name == "nt", "a Windows process gets no SIGTERM handler run")
class SignalReleasesLock(Env):
    """c189 part 3: a run stopped by SIGTERM or SIGINT releases the merge lock (#746 left one live for 2.7 h)."""
    def stop_with(self, sig):
        child = subprocess.Popen([sys.executable, __file__, "--sigchild", self.co], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            for line in child.stdout:  # merge's own lines come first
                if line.strip() == "READY":
                    break
            else:
                self.fail("the run never reached the wait: " + child.stderr.read())
            self.assertTrue(self.lock_ref())
            child.send_signal(sig)
            child.wait(timeout=60)
        finally:
            if child.poll() is None:
                child.kill(); child.wait()
        err = child.stderr.read()
        child.stdout.close(); child.stderr.close()
        self.assertNotEqual(child.returncode, 0)
        self.assertFalse(self.lock_ref(), err)

    def test_sigterm_releases_the_lock(self):
        self.stop_with(signal.SIGTERM)

    def test_sigint_releases_the_lock(self):  # a control: Python's own KeyboardInterrupt already unwinds the finally; only SIGTERM needs the handler
        self.stop_with(signal.SIGINT)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--sigchild":
        # A run waiting on its checks for a minute, for a signal to reach. It prints READY once it holds the lock.
        class Sleep(FakeHost):
            def wait_checks(self, n, sha, d, prior=None):
                print("READY", flush=True)
                time.sleep(60)
                return True, ""
        os.chdir(sys.argv[2])
        sys.exit(merge.main(["7", "--confirm"], host=Sleep(sys.argv[2], None), lock=merge.GitLock(sys.argv[2])))
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        # A run that dies without cleanup: os._exit at the wait, so no `finally` runs.
        class Die(FakeHost):
            def wait_checks(self, n, sha, d, prior=None):
                if prior is not None:  # the wait after the claim push; the head's own wait comes first
                    os._exit(9)
                return True, ""
        os.chdir(sys.argv[2])
        sys.exit(merge.main(["7", "--confirm"], host=Die(sys.argv[2], None), lock=merge.GitLock(sys.argv[2])))
    class Slicer(unittest.TestLoader):
        def loadTestsFromModule(self, *a, **k):
            suite = select_shard(select_tests(super().loadTestsFromModule(*a, **k), os.environ.get("MERGE_TESTS", "")),
                                 os.environ.get("MERGE_SHARD", ""))
            if os.environ.get("MERGE_SHARD"):  # the count a reader sums across shards to see none dropped
                print(f"MERGE_SHARD={os.environ['MERGE_SHARD']}: {suite.countTestCases()} tests run in this shard", file=sys.stderr)
            return suite
    unittest.main(testLoader=Slicer())
