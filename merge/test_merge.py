#!/usr/bin/env python3
"""Fixture suite for merge/merge.py, the git and GitHub halves (plan lanes 3b, 4).

Run: python3 merge/test_merge.py
No network, no real repo. Every run uses a local bare origin in a temp dir, the real
actions/stamp/stamp.mjs, and a fake Host for the git half. The lock backend is
GitLock against that origin. GhLock and the GitHub half (Host) are covered with a fake `gh` on PATH.
"""
import ast, contextlib, io, pathlib, json, os, re, shutil, socket, stat, subprocess, sys, tempfile, threading, time, unittest, unittest.mock

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

def sh(cwd, *cmd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, (cmd, r.stdout, r.stderr)
    return r.stdout.strip()

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
        self.base, self.base_seq = "main", None  # base_seq: one base per pr() read, the last one repeats
        self.waits, self.seq, self.state = [], None, "green"  # waits: (sha, prior) per call; seq: scripted results, then self.checks

    def pr(self, n):
        head = merge.origin_head(self.root, self.branch)
        base = (self.base_seq.pop(0) if len(self.base_seq) > 1 else self.base_seq[0]) if self.base_seq else self.base
        return {"head": self.head_override or head, "branch": self.branch, "base": base, "state": self.pr_state,
                "mergeable": self.mergeable, "merge_state": "CLEAN", "draft": self.draft}

    def required_names(self):
        return ["gates"]

    def head_state(self, n):
        return self.state

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

class Env(unittest.TestCase):
    def setUp(self):
        self.t = os.path.realpath(tempfile.mkdtemp(prefix="test-merge-"))
        self.addCleanup(shutil.rmtree, self.t, True)
        self.bare = os.path.join(self.t, "origin.git")
        sh(self.t, "git", "init", "-q", "--bare", "-b", "main", self.bare)
        seed = os.path.join(self.t, "seed")
        sh(self.t, "git", "clone", "-q", self.bare, seed)
        sh(seed, "git", "checkout", "-q", "-b", "main")
        put(os.path.join(seed, ".github/stamp.json"), json.dumps(CONFIG))
        put(os.path.join(seed, "docs/decisions/first.md"), record("D-001", "first"))
        sh(seed, "git", "add", "-A"); sh(seed, "git", "commit", "-q", "-m", "seed"); sh(seed, "git", "push", "-q", "origin", "main")
        sh(seed, "git", "checkout", "-q", "-b", "feat")
        put(os.path.join(seed, "docs/decisions/second.md"), record("pending", "second"))
        sh(seed, "git", "add", "-A"); sh(seed, "git", "commit", "-q", "-m", "feat: second"); sh(seed, "git", "push", "-q", "origin", "feat")
        self.co, self.other = (os.path.join(self.t, n) for n in ("co", "other"))
        for d in (self.co, self.other):
            sh(self.t, "git", "clone", "-q", self.bare, d)
        self.now = time.time()
        self.host = FakeHost(self.co, self.other)
        self.lock = merge.GitLock(self.co, now=lambda: self.now, pause=lambda s: None)  # a retry pause is a no-op: a test never sleeps
        self.addCleanup(lambda: os.environ.pop("MERGE_TEST_HOOK", None))

    def run_merge(self, *args, host=None, lock=None):
        out, err = io.StringIO(), io.StringIO()
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
        return "refs/merge-lock/main" in self.refs()

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
        self.host.state = "red: gates: fail"
        rc, out = self.run_merge("7")
        self.assertIn("head checks: red: gates: fail", out)

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
        self.host.seq = [(False, "a check is red: gates: fail")]
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1)
        self.assertIn("a check is red: gates: fail", out)
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
        self.host.seq = [(False, "a check is red: gates: fail https://x")]  # the wait saw pending, then red
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
        self.assertEqual(rc, 1, out)  # owner ruling: a failed local fast-forward exits non-zero
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
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)  # owner ruling: a failed afterMerge exits non-zero
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
        lock2.read = lambda b: None
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
        sh(self.co, "git", "push", "-q", "origin", f"{sha}:refs/merge-lock/main")
        self.now += 10 ** 9
        with self.assertRaises(merge.Held):
            self.lock.acquire("main", 600)

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
        self.host.seq = [(True, ""), (False, "check gates is red")]
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
    def test_stopped_run_resumes_then_an_expired_lock_is_broken(self):
        child = subprocess.run([sys.executable, __file__, "--child", self.co], capture_output=True, text=True)
        self.assertEqual(child.returncode, 9, child.stderr)
        self.assertEqual(self.claims("feat"), 1)
        self.assertTrue(self.lock_ref())  # the run died holding the lock
        claim_head = self.head()
        rc, out = self.run_merge("7", "--confirm")  # lock still live
        self.assertEqual(rc, 1)
        self.assertIn("held", out)
        self.assertEqual(self.head(), claim_head)
        expires = merge.expiry_of(sh(self.bare, "git", "log", "-1", "--format=%B", "refs/merge-lock/main"))  # the expiry the child wrote
        self.now = expires + 1  # past that lock, whatever its ttl
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
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
    """Plan "The flow" and "Settled by the owner" item 12: the pull request's own base drives every
    step. Cause: q_max #497 merged into claude/speed-wave-2 and claimed D-720 against main."""
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
        def undo(wt, base_ref, unknown_ok=""):
            self.undo_bases.append(base_ref)
            return real_undo(wt, base_ref, unknown_ok)
        for name, fn in (("node_stamp", stamp), ("git", git), ("undo_check", undo)):
            p = unittest.mock.patch.object(merge, name, fn); p.start(); self.addCleanup(p.stop)

    def put_locks(self, *branches):
        sha = sh(self.co, "git", "commit-tree", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", "-m", "lock")
        for b in branches:
            sh(self.co, "git", "push", "-q", "origin", f"{sha}:refs/merge-lock/{b}")

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
        except SystemExit as e:  # today argparse refuses the branch argument
            rc, out = e.code, "SystemExit"
        self.assertEqual(rc, 0, out)
        refs = self.refs()
        self.assertNotIn(f"refs/merge-lock/{self.BASE}", refs)
        self.assertIn("refs/merge-lock/main", refs)

    def test_3_bare_unlock_still_unlocks_the_default_branch(self):  # guard, green today
        self.put_locks("main", self.BASE)
        rc, out = self.run_merge("--unlock")
        self.assertEqual(rc, 0, out)
        refs = self.refs()
        self.assertNotIn("refs/merge-lock/main", refs)
        self.assertIn(f"refs/merge-lock/{self.BASE}", refs)

    def test_4_a_base_that_changes_between_the_reads_stops_before_any_claim_or_push(self):
        sh(self.other, "git", "push", "-q", "origin", "origin/main:refs/heads/other-base")
        self.host.base_seq = [self.BASE, "other-base"]
        feat_before = self.head()
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.head(), feat_before)
        self.assertNotIn("claim", [m for m, _ in self.modes])
        self.assertFalse(getattr(self.host, "merged", False))
        self.assertNotIn("refs/merge-lock/", self.refs())

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

    def test_8_control_a_pr_into_the_default_branch_still_claims(self):  # green today
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
        self.assertNotIn("refs/merge-lock/", self.refs())

    def test_C_a_base_that_changes_during_the_wait_ends_the_wait_and_merges_nothing(self):
        fake = self.host
        class WaitHost(merge.Host):  # the real wait loop; every other read comes from the fake
            def __init__(h):
                super().__init__(["gates"], minute=60, now=lambda: 0, pause=lambda s: None)
                h.in_wait, h.passes = False, 0
            def pr(h, n):
                info = fake.pr(n)
                if h.in_wait:
                    h.passes += 1
                    if h.passes > 1:
                        info["base"] = "other-base"  # the second pass of the wait sees a new base
                h.base = info["base"]  # as Host.pr does: the baseline is "integ" from the reads before the wait
                return info
            def required_names(h): return ["gates"]
            def checks(h, n): return {"gates": [("pass", "")]}
            def runs(h, sha): return []
            def head_state(h, n): return "green"
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
        self.assertNotIn("refs/merge-lock/", self.refs())

class Unlock(Env):
    def test_unlock_removes_a_live_lock_and_reads_nothing_first(self):
        sha = sh(self.co, "git", "commit-tree", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", "-m", "unreadable, not ours")
        sh(self.co, "git", "push", "-q", "origin", f"{sha}:refs/merge-lock/main")
        rc, out = self.run_merge("--unlock")
        self.assertEqual(rc, 0, out)
        self.assertFalse(self.lock_ref())

    def test_unlock_with_no_lock_is_fine(self):
        self.assertEqual(self.run_merge("--unlock")[0], 0)

    def test_unlock_of_a_missing_ref_says_so_and_never_says_the_lock_was_removed(self):  # round 2: the ref is absent, nothing was removed
        rc, out = self.run_merge("--unlock", "main")
        self.assertEqual(rc, 0, out)
        self.assertNotRegex(out, r"lock on main removed")
        self.assertRegex(out, r"(?i)no (merge )?lock|not found|does not exist|nothing to remove")

FAKE_GH = r'''#!/usr/bin/env python3
import hashlib, json, os, sys
d = os.environ["FAKE_GH_DIR"]; a = sys.argv[1:]; assert a[0] == "api"; a = a[1:]
method = "GET"; fields = {}; jq = None; path = None; i = 0
while i < len(a):
    if a[i] == "-X": method = a[i + 1]; i += 2
    elif a[i] == "-f": k, v = a[i + 1].split("=", 1); fields[k] = v; i += 2
    elif a[i] == "--jq": jq = a[i + 1]; i += 2
    else: path = a[i]; i += 1
p = path.split("/git/", 1)[1]; ref = os.path.join(d, "ref")
def out(v): print(v); sys.exit(0)
def fail(m): print(m); sys.exit(1)
if p == "ref/heads/main": out("head1")
if p == "commits/head1": out("tree1")
if p == "commits" and method == "POST":
    sha = hashlib.sha1(fields["message"].encode()).hexdigest(); open(os.path.join(d, sha), "w").write(fields["message"]); out(sha)
if p.startswith("commits/"):
    out(open(os.path.join(d, p[8:])).read() if jq == ".message" else "tree1")
if p == "refs" and method == "POST":
    if os.path.exists(ref): fail("HTTP 422: Reference already exists")
    open(ref, "w").write(fields["sha"]); out("{}")
if p == "ref/merge-lock/main" and method == "GET":
    if not os.path.exists(ref): fail("HTTP 404: Not Found")
    out(open(ref).read())
if p == "refs/merge-lock/main" and method == "DELETE":
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


FAKE_GH_PR = r"""#!/usr/bin/env python3
import json, os, subprocess, sys
d = os.environ["FAKE_GH_DIR"]; a = sys.argv[1:]
sp = os.path.join(d, "state.json"); S = json.load(open(sp))
def save(): json.dump(S, open(sp, "w"))
def log(): open(os.path.join(d, "calls.log"), "a").write(" ".join(a) + "\n")
def git(*c): return subprocess.run(["git", *c], capture_output=True, text=True, cwd=S.get("other") if c[0] != "ls-remote" else None).stdout.strip()
log()
hold = S.get("hold")  # {"on": [...], "seconds": N}: the first such call starts a helper that keeps this process's stdout open, as a detached git or gh helper can
if hold and a[:2] == hold["on"] and not os.path.exists(os.path.join(d, "held")):
    open(os.path.join(d, "held"), "w").close()
    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(%d)" % hold["seconds"]])
if a[:2] == ["pr", "view"]:
    if "headRefOid" in a[-1] and "mergeCommit" not in a[-1]:  # the wait's head read; a state read may ask for headRefOid too
        head = git("ls-remote", "origin", "refs/heads/feat").split("\t")[0]
        lag = S.get("lag")
        if lag and lag["n"] > 0 and head != lag["prior"]:  # GitHub still shows the head before the push
            lag["n"] -= 1; save(); head = lag["prior"]
        vf = S.get("view_fail")  # {"n", "msg", "after"}: once the head is off `after` (the pre-claim head), the next n reads fail with msg
        if vf and vf["n"] > 0 and head != vf["after"]:
            vf["n"] -= 1; S["view_failed"] = S.get("view_failed", 0) + 1; save()
            print(vf["msg"]); sys.exit(1)
        bad = S.get("dirty_after_checks") is not None and S["checks_calls"] >= S["dirty_after_checks"]
        views = S.get("views", 0) + 1; S["views"] = views; save()  # draft_from_view=N: read N and later ones see a draft
        draft = bool(S.get("draft")) or (S.get("draft_from_view") is not None and views >= S["draft_from_view"])
        print(json.dumps({"headRefOid": head, "headRefName": "feat", "baseRefName": S.get("base", "main"), "state": "OPEN",
                          "mergeable": "CONFLICTING" if bad else "MERGEABLE", "mergeStateStatus": "DIRTY" if bad else "CLEAN",
                          "isDraft": draft}))  # set draft=True in a test; false by default
    else:  # the state read. state_read_fail: its plain-text failure. state_head: the head GitHub reports (default: the branch head)
        if S.get("state_read_fail"):
            print(S["state_read_fail"]); sys.exit(1)
        print(json.dumps({"state": "MERGED" if S.get("oid") else "OPEN", "mergeCommit": {"oid": S["oid"]} if S.get("oid") else None,
                          "headRefOid": S.get("state_head") or git("ls-remote", "origin", "refs/heads/feat").split("\t")[0]}))
elif a[:2] == ["pr", "checks"] and S.get("checks_fail") and S["checks_fail"]["n"] > 0:  # {"n", "msg"}: the next n reads fail with msg, then it answers
    S["checks_fail"]["n"] -= 1; S["checks_failed"] = S.get("checks_failed", 0) + 1; save()
    print(S["checks_fail"]["msg"]); sys.exit(1)
elif a[:2] == ["pr", "checks"] and S.get("checks_broken") and S["checks_calls"] >= S.get("broken_from", 0):
    print("HTTP 404: Not Found"); sys.exit(1)  # a 4xx is a refusal, not a network error: the wait's read reverts (a 5xx is a network stop, see GhHalf)
elif a[:2] == ["pr", "checks"]:
    seq = S["checks_seq"]; cur = seq.pop(0) if len(seq) > 1 else seq[0]; S["checks_calls"] += 1; save()
    print(json.dumps([{"name": n, "bucket": b, "link": l} for n, b, l in cur]))
    sys.exit(0 if all(b in ("pass", "skipping") for _, b, _ in cur) else 8)
elif a[:2] == ["run", "list"]:
    rf = S.get("runs_fail_first")  # [text, ...]: the first len() calls fail, one text each, then it answers
    if rf:
        S["runs_fail_first"] = rf[1:]; S["runs_failed"] = S.get("runs_failed", 0) + 1; save()
        print(rf[0]); sys.exit(1)
    if S.get("runs_fail"):  # the text of every failing `gh run list`
        print(S["runs_fail"]); sys.exit(1)
    seq = S.get("runs_seq") or [[]]; cur = seq.pop(0) if len(seq) > 1 else seq[0]; save()
    print(json.dumps([{"name": n, "status": st, "conclusion": c} for n, st, c in cur]))
elif a[:2] == ["run", "watch"]:
    pass
elif a[:2] == ["pr", "merge"]:
    sha = a[a.index("--match-head-commit") + 1]
    if S.get("merge_fail"):
        print(S["merge_fail"]); sys.exit(1)
    seq = S.get("merge_replies") or []  # [msg, lands(, code)] per call, the last repeats. lands: the merge reaches the server first; msg: the reply ("" for none); code: the exit status, 1 unless given
    ent = (seq.pop(0) if len(seq) > 1 else seq[0]) if seq else ["", True]
    msg, lands, code = ent[0], ent[1], (ent[2] if len(ent) > 2 else 1)
    if seq: save()
    if not lands:
        print(msg); sys.exit(code)
    if git("ls-remote", "origin", "refs/heads/feat").split("\t")[0] != sha:
        print("GraphQL: Head branch was modified. Review and try the merge again."); sys.exit(1)
    B = S.get("base", "main")
    git("fetch", "-q", "origin"); git("checkout", "-q", "-B", B, "origin/" + B)
    git("merge", "-q", "--no-ff", "-m", "merge", sha); git("push", "-q", "origin", B)
    S["oid"] = git("rev-parse", "HEAD"); save()
    if msg: print(msg); sys.exit(code)
elif a[:2] == ["repo", "view"]:
    print(json.dumps({"defaultBranchRef": {"name": S.get("default_branch", "main")}}))
elif a[0] == "api" and a[1].endswith("/required_status_checks"):
    af = S.get("api_fail")  # {"msg", "after_checks"}: once the checks have been read that many times, each read fails with msg
    if af and S["checks_calls"] >= af["after_checks"]:
        S["api_failed"] = S.get("api_failed", 0) + 1; save()
        print(af["msg"]); sys.exit(1)
    if S.get("contexts") is None:
        print("HTTP 404: Branch not protected"); sys.exit(1)
    print(json.dumps(S["contexts"]))
else:
    print("unhandled " + " ".join(a)); sys.exit(1)
"""

# The text real gh prints for a network failure (the q_max PR 833 incident, 2026-10-13).
NET_TLS = 'Post "https://api.github.com/graphql": net/http: TLS handshake timeout'
# Network texts NET_ERROR must match (review round 2): a Windows socket, a deadline, a refused connect; git's name lookup.
NET_WSARECV = 'Post "https://api.github.com/graphql": read tcp 10.0.0.5:51322->140.82.112.6:443: wsarecv: An existing connection was forcibly closed by the remote host'
NET_DEADLINE = 'Post "https://api.github.com/graphql": context deadline exceeded'
NET_REFUSED = 'Post "https://api.github.com/graphql": dial tcp 140.82.112.6:443: connect: connection refused'
NET_HOST = "fatal: unable to access 'https://github.com/shivinate7/claude-settings/': Could not resolve host: github.com"

# Rate-limit texts (the q_max PR 874 incident, 2026-10-14: every check green, `gh run list` answered HTTP 403). The request id and the
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
        bindir = os.path.join(self.t, "bin"); os.makedirs(bindir)
        gh = os.path.join(bindir, "gh"); put_shim(gh, FAKE_GH_PR)
        self.state = os.path.join(self.t, "ghstate"); os.makedirs(self.state)
        old = {k: os.environ.get(k) for k in ("PATH", "FAKE_GH_DIR")}
        os.environ["PATH"] = bindir + os.pathsep + old["PATH"]; os.environ["FAKE_GH_DIR"] = self.state
        self.addCleanup(lambda: [os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None) for k, v in old.items()])
        self.ticks, self.paused = 0, []
        self.set(checks_seq=[[("gates", "pass", "")]])

    def set(self, **kw):
        p = os.path.join(self.state, "state.json")
        f = pathlib.Path(p)
        s = json.loads(f.read_text()) if f.exists() else {"other": self.other, "checks_calls": 0}
        s.update(kw)
        f.write_text(json.dumps(s))

    def calls(self):
        return pathlib.Path(self.state, "calls.log").read_text()

    def gh_host(self, required=("gates",), pause=None, ignore=None):
        def tick(s):
            self.ticks += 1
            self.paused.append(s)
            assert self.ticks < 200, "the wait never ended"
            self.now += s
            if pause:
                pause()
        return merge.Host(required if required == "protection" else list(required), "main", minute=60, now=lambda: self.now, pause=tick, ignore=ignore)

    def go(self, **kw):
        return self.run_merge("7", "--confirm", host=self.gh_host(**kw))

    def test_5_base_aware_protection_mode_reads_the_protection_of_the_base(self):
        sh(self.other, "git", "fetch", "-q", "origin")
        sh(self.other, "git", "push", "-q", "origin", "origin/main:refs/heads/integ")
        self.set(base="integ", contexts=["gates"])
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
        self.assertIn("pr merge 7", self.calls())
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
        self.assertNotIn("pr merge", self.calls())
        self.assertFalse(self.lock_ref())
        self.set(view_fail=None)  # the network is back: the next run resumes the claim and merges
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertIn("resumed", out)
        self.assertEqual(self.claims("main"), 1)

    def test_a_real_refusal_in_the_wait_reverts_the_claim_and_is_not_retried(self):
        self.set(view_fail={"n": 1, "msg": "GraphQL: Pull request is not mergeable", "after": self.head()})
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.gh_state("view_failed"), 1, out)  # tried once
        self.assertIn("reverted on feat", out)
        self.assertNotIn("pr merge", self.calls())
        self.assertTrue(self.reverted())
        self.assertFalse(self.lock_ref())

    def test_a_lost_merge_reply_then_not_mergeable_reads_merged_and_carries_on(self):
        self.set(merge_replies=[[NET_TLS, True], ["GraphQL: Pull request is not mergeable: already closed", False]])  # the merge lands, its reply is lost
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("reverted on", out)
        self.assertEqual(self.calls().count("pr merge"), 2)
        self.assertIn("state,mergeCommit", self.calls())  # the retry's answer is not trusted: the PR state is read
        self.assertEqual(self.claims("main"), 1)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))
        self.assertFalse(self.lock_ref())

    def test_a_lost_merge_reply_then_404_reads_merged_and_carries_on(self):
        self.set(merge_replies=[[NET_TLS, True], ["HTTP 404: Not Found", False]])  # a stale ref on the retry
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("reverted on", out)
        self.assertEqual(self.calls().count("pr merge"), 2)
        self.assertIn("state,mergeCommit", self.calls())
        self.assertEqual(self.claims("main"), 1)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))
        self.assertFalse(self.lock_ref())

    def test_a_plain_already_merged_answer_on_the_first_merge_reads_the_state_and_carries_on(self):
        self.set(merge_replies=[["Pull request #7 is already merged", True]])  # no network error before it
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("reverted on", out)
        self.assertEqual(self.calls().count("pr merge"), 1)
        self.assertIn("state,mergeCommit", self.calls())
        self.assertEqual(self.claims("main"), 1)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))
        self.assertFalse(self.lock_ref())

    def test_a_red_check_named_eof_is_a_refusal_not_a_network_retry(self):
        self.set(checks_seq=[[("gates", "pass", ""), ("EOF lint", "fail", "https://x/y")]])  # "EOF" in the JSON must not match the network pattern
        rc, out = self.go()
        self.assertEqual(self.paused, [], out)  # no retry, so no pause
        self.assertEqual(rc, 1, out)
        self.assertIn("a check is red: EOF lint: fail", out)
        self.assertNotIn("network", out.lower())
        self.assertNotIn("pr merge", self.calls())
        self.assertEqual(self.claims("feat"), 0)  # refused before the claim push

    def test_four_network_errors_on_the_merge_read_merged_and_carry_on(self):
        self.set(merge_replies=[[NET_TLS, True], [NET_TLS, False]])  # the first merge lands, its reply and the three retries are lost
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.calls().count("pr merge"), 4)
        self.assertIn("state,mergeCommit", self.calls())
        self.assertNotIn("reverted on", out)
        self.assertEqual(self.claims("main"), 1)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))
        self.assertFalse(self.lock_ref())

    def test_four_network_errors_on_the_merge_with_the_pr_open_stop_without_a_revert(self):
        self.set(merge_replies=[[NET_TLS, False]])  # nothing lands: four calls, all lost
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.calls().count("pr merge"), 4)
        self.assertIn("state,mergeCommit", self.calls())  # the PR state is read: OPEN
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
        self.assertNotIn("pr merge", self.calls())
        self.assertIn("network", out.lower())
        self.assertIn("Claim record numbers", self.feat_subjects())  # the claim stays
        self.assertFalse(self.lock_ref())

    def test_a_git_fetch_could_not_resolve_host_after_the_claim_push_stops_without_a_revert(self):
        rc, out = self.go_with_fetch_after_push(NET_HOST)
        self.assertNotIn("reverted on", out)
        self.assertEqual(rc, 1, out)
        self.assertNotIn("pr merge", self.calls())
        self.assertIn("Claim record numbers", self.feat_subjects())  # the claim stays
        self.assertFalse(self.lock_ref())

    def lost_reply_reads_merged(self, msg):
        """The merge lands, its reply is `msg`, and the retries are lost too. The PR reads MERGED at the proven head: carry on."""
        self.set(merge_replies=[[msg, True], [msg, False]])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("reverted on", out)
        self.assertIn("state,mergeCommit", self.calls())  # the PR state is read
        self.assertEqual(self.claims("main"), 1)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))
        self.assertFalse(self.lock_ref())

    def test_a_lost_merge_reply_with_a_wsarecv_error_reads_merged_and_carries_on(self):
        self.lost_reply_reads_merged(NET_WSARECV)

    def test_a_network_error_then_a_real_not_mergeable_reply_reverts_the_claim(self):
        self.set(merge_replies=[[NET_TLS, False], ["GraphQL: Pull Request is not mergeable", False]])  # the retry gets a real refusal
        rc, out = self.go()
        self.assertIn("reverted on feat", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.calls().count("pr merge"), 2)  # the refusal is not retried
        self.assertTrue(self.reverted())
        self.assertFalse(self.lock_ref())

    def test_already_merged_at_another_head_is_not_this_runs_merge_and_stops_without_a_revert(self):
        before = self.head()  # the branch head before the claim push: not the proven sha
        self.set(merge_replies=[["Pull request #7 is already merged", True]], state_head=before)
        rc, out = self.go()
        self.assertNotIn("reverted on", out)
        self.assertEqual(rc, 1, out)
        self.assertIn("state,mergeCommit", self.calls())
        self.assertIn("Claim record numbers", self.feat_subjects())  # the claim stays
        self.assertFalse(self.lock_ref())

    def test_already_merged_then_a_plain_state_read_failure_reverts_nothing(self):
        self.set(merge_replies=[["Pull request #7 is already merged", False]],
                 state_read_fail="GraphQL: Could not resolve to a PullRequest with the number of 7.")
        rc, out = self.go()
        self.assertNotIn("reverted on", out)
        self.assertEqual(rc, 1, out)
        self.assertIn("state,mergeCommit", self.calls())
        self.assertIn("Claim record numbers", self.feat_subjects())  # the claim stays
        self.assertFalse(self.lock_ref())

    # ---- lane merge-net-holes (owner ruling "Retry 3 times"): only a proven refusal reverts the claim

    def test_a_merge_that_exits_zero_while_the_pr_reads_open_stops_without_a_revert(self):
        self.set(merge_replies=[["", False, 0]])  # gh exits 0 and says nothing; nothing landed; the PR reads OPEN
        rc, out = self.go()
        self.assertNotIn("reverted on", out)
        self.assertEqual(rc, 1, out)
        self.assertIn("state,mergeCommit", self.calls())
        self.assertIn("Claim record numbers", self.feat_subjects())  # the claim stays
        self.assertFalse(self.lock_ref())

    def required_read_fails_after_the_claim(self, msg):
        """The required-checks read fails with `msg` from the wait after the claim push on. Retried 3 times, then a stop: no revert."""
        self.set(contexts=["gates"], api_fail={"msg": msg, "after_checks": 1})
        rc, out = self.go(required="protection")
        self.assertNotIn("reverted on", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.gh_state("api_failed"), 4, out)  # one try and three retries
        self.assertIn("Claim record numbers", self.feat_subjects())  # the claim stays
        self.assertFalse(self.lock_ref())

    def test_a_required_check_read_with_gh_server_error_502_stops_without_a_revert(self):
        self.required_read_fails_after_the_claim("gh: Server Error (HTTP 502)")

    def merge_reply_is_retried_then_stops(self, msg):
        """Every merge try answers `msg` and nothing lands: a network-class error, retried 3 times, then a stop. The PR reads OPEN: no revert."""
        self.set(merge_replies=[[msg, False]])
        rc, out = self.go()
        self.assertNotIn("reverted on", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.calls().count("pr merge"), 4, out)  # one try and three retries
        self.assertIn("state,mergeCommit", self.calls())
        self.assertIn("Claim record numbers", self.feat_subjects())  # the claim stays
        self.assertFalse(self.lock_ref())

    def test_a_merge_reply_something_went_wrong_is_retried_then_stops_without_a_revert(self):
        self.merge_reply_is_retried_then_stops("GraphQL: Something went wrong while executing your query on this domain.")

    def fetch_fails_after_the_claim_push(self, msg):
        """The fetch of main after the claim push fails with `msg`, a network-class error: the claim stays, nothing is reverted."""
        rc, out = self.go_with_fetch_after_push(msg)
        self.assertNotIn("reverted on", out)
        self.assertEqual(rc, 1, out)
        self.assertNotIn("pr merge", self.calls())
        self.assertIn("Claim record numbers", self.feat_subjects())  # the claim stays
        self.assertFalse(self.lock_ref())

    def test_a_git_fetch_http2_stream_error_after_the_claim_push_stops_without_a_revert(self):
        self.fetch_fails_after_the_claim_push("fatal: unable to access 'https://github.com/shivinate7/claude-settings/': HTTP/2 stream 1 was not closed cleanly: INTERNAL_ERROR (err 2)")

    def test_a_merge_that_may_have_landed_with_an_unreadable_state_says_to_finish_by_hand(self):
        self.set(merge_replies=[[NET_TLS, True], [NET_TLS, False]],  # the merge lands, its reply and the retries are lost
                 state_read_fail="GraphQL: Could not resolve to a PullRequest with the number of 7.")
        rc, out = self.go()
        self.assertNotIn("reverted on", out)
        self.assertEqual(rc, 1, out)
        self.assertIn("by hand", out)  # the owner's next steps are named, not only "Run again"
        self.assertRegex(out, r"(?i)after-?merge")
        self.assertRegex(out, r"(?i)check (?:the|#7)")

    def test_a_real_first_refusal_reverts_the_claim_and_is_not_retried(self):  # pin: a proven refusal still reverts
        self.set(merge_replies=[["GraphQL: Pull Request is not mergeable", False]])
        rc, out = self.go()
        self.assertIn("reverted on feat", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.calls().count("pr merge"), 1)  # a refusal is not retried
        self.assertTrue(self.reverted())
        self.assertFalse(self.lock_ref())

    def test_a_run_list_http_500_with_green_checks_is_a_network_error_not_not_green(self):
        # oversight report (q_max #853): every check is green, gh run list answers HTTP 500
        self.set(runs_fail="HTTP 500: Internal Server Error (https://api.github.com/repos/o/r/actions/runs?head_sha=abc)")
        before = self.head()
        rc, out = self.go()
        self.assertNotIn("not green", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.calls().count("run list"), 4, out)  # one try and three retries
        self.assertIn("network", out.lower())
        self.assertNotIn("pr merge", self.calls())
        self.assertEqual(self.head(), before)  # nothing claimed or pushed
        self.assertFalse(self.lock_ref())

    def run_list_fails_wrapped(self, msg):
        """Every check is green and `gh run list` fails with the wrapped line `msg`: a network error, retried 3 times, then a stop. Nothing is claimed."""
        self.set(runs_fail=msg)
        before = self.head()
        rc, out = self.go()
        self.assertNotIn("not green", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.calls().count("run list"), 4, out)  # one try and three retries
        self.assertIn("network", out.lower())
        self.assertNotIn("pr merge", self.calls())
        self.assertEqual(self.head(), before)  # nothing claimed or pushed
        self.assertFalse(self.lock_ref())

    def test_a_wrapped_run_list_http_502_is_a_network_error_retried_then_stopped(self):
        self.run_list_fails_wrapped("failed to get runs: HTTP 502: 502 Bad Gateway (https://api.github.com/repos/o/r/actions/runs?head_sha=abc)")
        self.assertEqual(self.paused, [merge.NET_PAUSE] * 3)  # a plain network error waits the normal pause

    def test_a_wrapped_run_list_http_429_is_a_network_error_retried_then_stopped(self):
        self.run_list_fails_wrapped("failed to get runs: HTTP 429: Too Many Requests (https://api.github.com/repos/o/r/actions/runs?head_sha=abc)")
        self.assertEqual(self.paused, [merge.RATE_WAIT_CAP] * 3)  # a 429 is a rate limit: the cap

    # ---- lane merge-rate-limit (owner ruling "Retry 3 times", merge-net-retry): a rate-limit 403 or a 429 is a network fault, never "not green" (q_max PR 874, 2026-10-14)

    def test_a_run_list_rate_limit_403_is_a_network_error_retried_then_stopped(self):
        self.run_list_fails_wrapped(RATE_403)  # the incident text: 4 calls, a network stop, never "not green"
        self.assertEqual(self.paused, [merge.RATE_WAIT_CAP] * 3)  # a rate limit waits the cap. Its request timestamp is no reset time.

    def test_a_run_list_secondary_rate_limit_403_is_a_network_error_retried_then_stopped(self):
        self.run_list_fails_wrapped(RATE_SECONDARY_403)
        self.assertEqual(self.paused, [merge.RATE_WAIT_CAP] * 3)

    def test_a_run_list_rate_limit_403_that_clears_on_the_retry_lets_the_merge_go_on(self):
        self.set(runs_fail_first=[RATE_403])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("not green", out)
        self.assertEqual(self.gh_state("runs_failed"), 1)
        self.assertEqual(self.paused[0], merge.RATE_WAIT_CAP, self.paused)  # the first pause is the retry's
        self.assertEqual(self.claims("main"), 1)
        self.assertFalse(self.lock_ref())

    def test_a_retry_after_in_the_gh_text_never_changes_the_rate_wait(self):
        self.set(runs_fail_first=["Retry-After: 17\n" + RATE_403])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.paused[0], merge.RATE_WAIT_CAP, self.paused)  # the header's 17 s is ignored

    def checks_read_fails(self, msg, n=99):
        """Every check is green and `gh pr checks` fails n times with `msg`. A network-class text: retried 3 times, then a stop. Nothing is claimed."""
        self.set(checks_fail={"n": n, "msg": msg})
        before = self.head()
        rc, out = self.go()
        self.assertNotIn("not green", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.gh_state("checks_failed"), 4, out)  # one try and three retries
        self.assertIn("network", out.lower())
        self.assertNotIn("pr merge", self.calls())
        self.assertEqual(self.head(), before)  # nothing claimed or pushed
        self.assertFalse(self.lock_ref())

    def test_a_pr_checks_http_429_is_a_network_error_retried_then_stopped(self):
        self.checks_read_fails("HTTP 429: Too Many Requests (https://api.github.com/graphql)")
        self.assertEqual(self.paused, [merge.RATE_WAIT_CAP] * 3)  # a 429 is a rate limit: the cap

    def test_a_pr_checks_rate_limit_403_is_a_network_error_retried_then_stopped(self):
        self.checks_read_fails(RATE_GQL_403)
        self.assertEqual(self.paused, [merge.RATE_WAIT_CAP] * 3)

    def test_a_pr_checks_graphql_rate_limit_already_exceeded_is_a_network_error_retried_then_stopped(self):
        self.checks_read_fails(RATE_GQL_ALREADY)  # owner's word: it retries like the 403
        self.assertEqual(self.paused, [merge.RATE_WAIT_CAP] * 3)

    def test_a_retry_after_on_a_pr_checks_429_never_changes_the_rate_wait(self):
        self.set(checks_fail={"n": 1, "msg": "Retry-After: 17\nHTTP 429: Too Many Requests (https://api.github.com/graphql)"})
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.gh_state("checks_failed"), 1)
        self.assertEqual(self.paused[0], merge.RATE_WAIT_CAP, self.paused)  # the header's 17 s is ignored

    def test_a_required_check_read_with_a_rate_limit_403_stops_without_a_revert(self):
        self.required_read_fails_after_the_claim(RATE_API_403)  # `gh api` form: the claim stays, 4 tries

    def test_a_required_check_read_with_a_secondary_rate_limit_403_stops_without_a_revert(self):
        self.required_read_fails_after_the_claim(RATE_API_SECONDARY_403)

    def test_a_merge_reply_secondary_rate_limit_403_is_retried_then_stops_without_a_revert(self):
        self.merge_reply_is_retried_then_stops(RATE_GQL_403)

    def test_a_plain_403_on_run_list_is_a_refusal_not_retried_and_not_a_network_stop(self):  # (d): green before the lane, a guard
        self.set(runs_fail=PLAIN_403)
        before = self.head()
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.calls().count("run list"), 1, out)  # a refusal is not retried
        self.assertEqual(self.paused, [])  # no retry pause
        self.assertIn("HTTP 403", out)  # the refusal's own text
        self.assertNotIn("network", out.lower())
        self.assertNotIn("pr merge", self.calls())
        self.assertEqual(self.head(), before)
        self.assertFalse(self.lock_ref())

    def test_a_plain_403_on_the_required_check_read_reverts_the_claim_and_is_not_retried(self):  # (d): a guard
        self.set(contexts=["gates"], api_fail={"msg": PLAIN_403_API, "after_checks": 1})
        rc, out = self.go(required="protection")
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.gh_state("api_failed"), 1, out)  # tried once
        self.assertIn("reverted on feat", out)
        self.assertNotIn("network", out.lower())
        self.assertTrue(self.reverted())
        self.assertFalse(self.lock_ref())

    def test_a_merge_lock_read_that_fails_once_with_a_json_error_is_retried_and_the_run_goes_on(self):
        # Windows credential manager (PR 411, 2026-10-13 20:35): ls-remote of the lock ref fails once, then works
        real_git = merge.git
        hits = []
        def flaky(cwd, *a, input=None):
            if a[:1] == ("ls-remote",) and a[-1] == "refs/merge-lock/main" and not hits:
                hits.append(1)
                return 1, "unexpected end of JSON input"
            return real_git(cwd, *a, input=input)
        with unittest.mock.patch.object(merge, "git", flaky):
            rc, out = self.go()
        self.assertEqual(hits, [1])  # the first read failed
        self.assertNotIn("cannot read the merge lock", out)
        self.assertEqual(rc, 0, out)
        self.assertIn("pr merge", self.calls())
        self.assertEqual(self.claims("main"), 1)
        self.assertFalse(self.lock_ref())

    def test_a_refusal_whose_text_names_an_http_502_title_reverts_and_is_not_retried(self):
        self.set(merge_replies=[['GraphQL: Pull Request is not mergeable: #7 "Fix (HTTP 502 retry)"', False]])  # a real refusal; its text carries a 5xx-looking title
        rc, out = self.go()
        self.assertIn("reverted on feat", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.calls().count("pr merge"), 1)  # a refusal is not retried
        self.assertNotIn(merge.NET_PAUSE, self.paused)  # no network-retry pause
        self.assertTrue(self.reverted())
        self.assertFalse(self.lock_ref())

    def test_a_red_check_named_http_500_is_a_refusal_that_reverts_and_is_not_retried(self):
        # the wait after the claim push reads the red check; its name carries "HTTP 500"
        self.set(checks_seq=[[("gates", "pass", "")], [("gates", "pass", "")],
                             [("gates", "pass", ""), ("build: HTTP 500 guard", "fail", "https://x/y")]])
        rc, out = self.go()
        self.assertIn("a check is red: build: HTTP 500 guard: fail", out)
        self.assertIn("reverted on feat", out)
        self.assertEqual(rc, 1, out)
        self.assertNotIn("pr merge", self.calls())
        self.assertNotIn(merge.NET_PAUSE, self.paused)  # no network-retry pause
        self.assertNotIn("network", out.lower())
        self.assertTrue(self.reverted())
        self.assertFalse(self.lock_ref())

    def test_green_run_watches_the_run_and_merges_pinned_to_the_claim_head(self):
        self.set(checks_seq=[[("gates", "pending", "https://github.com/o/r/actions/runs/99/job/1")], [("gates", "pass", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        log = self.calls()
        self.assertIn("run watch 99 --exit-status", log)
        self.assertIn("pr merge 7 --merge --match-head-commit " + sh(self.co, "git", "rev-parse", "origin/main^2"), log)
        self.assertNotIn("--admin", log)
        self.assertNotIn("--delete-branch", log)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))
        self.assertFalse(self.lock_ref())

    def test_red_required_check_reverts_the_claim_and_merges_nothing(self):
        self.set(checks_seq=[[("gates", "fail", "https://x/y"), ("other", "pass", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("a check is red: gates: fail", out)
        self.assertNotIn("pr merge", self.calls())
        self.assertTrue(self.reverted())
        self.assertFalse(self.lock_ref())

    def test_a_red_check_that_is_not_required_still_stops_the_merge(self):
        self.set(checks_seq=[[("gates", "pass", ""), ("lint", "fail", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("a check is red: lint: fail", out)
        self.assertNotIn("pr merge", self.calls())
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
            self.assertNotIn("pr merge", self.calls())

    def test_one_red_entry_under_a_name_makes_the_name_red(self):
        self.set(checks_seq=[[("gates", "fail", ""), ("gates", "pass", "")]])  # a last-entry-wins map would pass
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("a check is red: gates: fail", out)
        self.assertNotIn("pr merge", self.calls())

    def test_a_name_is_green_only_when_every_entry_passed(self):
        self.set(checks_seq=[[("gates", "pending", ""), ("gates", "pass", "")]])  # pending then pass: never green
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("Still pending: gates", out)

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
        self.assertNotIn("pr merge", self.calls())

    def test_a_fast_run_watch_pauses_a_full_minute(self):
        self.gh_host().block(["gates"], {"gates": [("pending", "https://x/actions/runs/5/job/1")]})
        self.assertEqual(self.paused, [60])

    def test_dirty_in_the_wait_reverts_the_claim(self):
        self.set(checks_seq=[[("gates", "pending", "")], [("gates", "pass", "")]], dirty_after_checks=1)
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("went DIRTY", out)
        self.assertNotIn("pr merge", self.calls())
        self.assertTrue(self.reverted())

    def test_force_push_in_the_wait_reverts_nothing_and_merges_nothing(self):
        self.set(checks_seq=[[("gates", "pending", "")], [("gates", "pass", "")]])
        rival = []
        rc, out = self.go(pause=lambda: rival.append(self.competitor_push()))
        self.assertEqual(rc, 1)
        self.assertIn("head moved", out)
        self.assertEqual(self.head(), rival[0])  # the rival's head stands: no revert on top of it
        self.assertNotIn("pr merge", self.calls())
        self.assertFalse(self.lock_ref())

    def test_match_head_commit_refuses_a_moved_head(self):
        old = self.head()
        self.competitor_push()
        commit, msg = self.gh_host().merge(7, "merge", old)
        self.assertIsNone(commit)
        self.assertIn("Head branch was modified", msg)

    def test_protection_refusal_reverts_the_claim_and_prints_gh_whole(self):
        self.set(merge_fail="GH006: Protected branch update failed for refs/heads/main. 2 of 2 required status checks are expected.")
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("the merge was refused", out)
        self.assertIn("GH006: Protected branch update failed", out)
        self.assertNotIn("--admin", self.calls())
        self.assertTrue(self.reverted())
        self.assertNotIn("merge #", sh(self.co, "git", "log", "origin/main", "--format=%s"))

    def test_protection_names_come_from_the_api_and_the_deadline_stops_the_wait(self):
        self.set(contexts=["gates", "needed"], checks_seq=[[("gates", "pass", "")]])
        rc, out = self.go(required="protection")
        self.assertEqual(rc, 1)
        self.assertIn("deadline of 5 minutes passed. Still pending: needed", out)
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
        self.set(checks_seq=[[("gates", "fail", "https://x/y")]])
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("gates: fail", out)
        self.assertEqual(self.head(), before)
        self.assertNotIn("pr merge", self.calls())
        self.assertFalse(self.lock_ref())

    def test_head_pending_then_red_pushes_no_claim(self):
        before = self.head()
        self.set(checks_seq=[[("gates", "pending", "")], [("gates", "fail", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertEqual(self.head(), before)
        self.assertNotIn("pr merge", self.calls())

    def test_head_pending_then_green_claims_and_waits_again(self):
        self.set(checks_seq=[[("gates", "pending", "")], [("gates", "pass", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.claims("main"), 1)
        self.assertGreaterEqual(self.paused.count(60), 1)  # the head's own pending check was waited on

    def test_the_preview_names_the_head_state(self):
        for seq, want in (([("gates", "pass", "")], "head checks: green"), ([("gates", "pending", "")], "head checks: pending: gates"),
                          ([("gates", "fail", "")], "head checks: red: gates: fail")):
            self.set(checks_seq=[seq])
            rc, out = self.run_merge("7", host=self.gh_host())
            self.assertEqual(rc, 0, out)
            self.assertIn(want, out)

    def test_banchi_604_a_pending_check_that_is_not_required_goes_red_after_the_required_are_green(self):
        # The head reads green on `gates`, `design` still pending, then red. The old wait ended on the green required check.
        before = self.head()
        self.set(checks_seq=[[("gates", "pass", ""), ("design", "pending", "")], [("gates", "pass", ""), ("design", "fail", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("a check is red: design: fail", out)
        self.assertEqual(self.head(), before)  # stopped at the head wait: nothing claimed
        self.assertNotIn("pr merge", self.calls())

    def test_banchi_604_same_in_the_wait_after_the_claim_push(self):
        self.set(checks_seq=[[("gates", "pass", ""), ("design", "pass", "")], [("gates", "pass", ""), ("design", "pending", "")],
                             [("gates", "pass", ""), ("design", "fail", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("a check is red: design: fail", out)
        self.assertNotIn("pr merge", self.calls())
        self.assertTrue(self.reverted())

    def test_a_pending_check_that_is_not_required_is_waited_on_then_merges_on_green(self):
        self.set(checks_seq=[[("gates", "pass", ""), ("design", "pending", "")], [("gates", "pass", ""), ("design", "pass", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertGreaterEqual(self.paused.count(60), 1)
        self.assertIn("pr merge", self.calls())

    def test_skipped_and_neutral_count_as_passed(self):
        self.set(checks_seq=[[("gates", "pass", ""), ("a", "skipping", ""), ("b", "pass", "")]])  # gh buckets neutral as pass
        rc, out = self.go()
        self.assertEqual(rc, 0, out)

    def test_a_required_check_that_is_skipped_reads_green(self):
        # B skips whole jobs on a docs-only PR. A skipped required check is not red, not pending, and the run judge agrees.
        red, pending, _ = merge.Host.classify({"gates": [("pass", "")], "gates-windows": [("skipping", "")]}, ["gates", "gates-windows"])
        self.assertEqual((red, pending), ([], []))
        runs = [{"name": "gates", "status": "completed", "conclusion": c} for c in ("success", "skipped", "neutral")]
        self.assertEqual(merge.Host.judge_runs(runs), ([], []))
        self.set(checks_seq=[[("gates", "skipping", ""), ("scope", "pass", "")]])  # a required check skipped beside a passing check reads green
        rc, out = self.go()
        self.assertEqual(rc, 0, out)

    def test_a_head_where_no_check_ran_is_unproven_not_green(self):
        # Incident 2026-10-12: PR #352 merged while every check on f18b6d9 skipped. The synchronize run skipped as a draft.
        red, pending, _ = merge.Host.classify({"gates": [("skipping", "")], "gates-windows": [("skipping", "")]}, ["gates", "gates-windows"])
        self.assertEqual(pending, [])
        self.assertTrue(any("no check ran on this head" in r for r in red), red)
        self.assertTrue(any("gh workflow run gates.yml --ref" in r for r in red), red)
        self.assertTrue(any("gh pr ready" in r for r in red), red)

    def test_a_docs_only_head_whose_scope_check_passed_is_not_unproven(self):
        red, pending, _ = merge.Host.classify({"scope": [("pass", "")], "gates": [("skipping", "")], "gates-windows": [("skipping", "")]}, ["gates", "gates-windows"])
        self.assertEqual((red, pending), ([], []))

    def test_a_run_list_where_every_run_skipped_and_none_pending_is_red(self):
        red, pending = merge.Host.judge_runs([{"name": "gates", "status": "completed", "conclusion": "skipped"}])
        self.assertEqual(red, ["workflow gates: skipped, no job ran"])
        self.assertEqual(pending, [])

    def test_a_success_run_and_a_skipped_run_on_the_same_head_are_green(self):
        runs = [{"name": "gates", "status": "completed", "conclusion": "success"}, {"name": "gates-windows", "status": "completed", "conclusion": "skipped"}]
        self.assertEqual(merge.Host.judge_runs(runs), ([], []))

    def test_an_older_cancelled_run_under_a_newer_success_of_the_same_name_is_superseded(self):
        # gh lists the newest run first. Only the newest run per workflow name counts.
        runs = [{"name": "gates", "status": "completed", "conclusion": "success"}, {"name": "gates", "status": "completed", "conclusion": "cancelled"}]
        self.assertEqual(merge.Host.judge_runs(runs), ([], []))

    def test_a_cancelled_run_beside_a_success_of_its_name_is_superseded(self):
        # Owner ruling 2026-10-13, option (a): on one head, a run of a name that ran outranks a cancelled run of that name.
        runs = [{"name": "gates", "status": "completed", "conclusion": "cancelled"}, {"name": "gates", "status": "completed", "conclusion": "success"}]
        self.assertEqual(merge.Host.judge_runs(runs), ([], []))

    def test_a_cancelled_run_with_no_newer_run_of_its_name_is_red(self):
        runs = [{"name": "gates", "status": "completed", "conclusion": "success"}, {"name": "ci", "status": "completed", "conclusion": "cancelled"}]
        red, pending = merge.Host.judge_runs(runs)
        self.assertEqual(red, ["workflow ci: cancelled"])
        self.assertEqual(pending, [])

    # Incident 2026-10-13, PR 381: two gates runs started on one head in the same second. GitHub cancelled one (concurrency).
    # judge_runs must read the live twin, not the cancelled one, whatever the list order.
    def test_a_cancelled_twin_beside_a_run_of_its_name_is_judged_by_the_run_that_ran_in_either_order(self):
        # Rows, one outcome each: a live twin waits; a succeeded twin is green (owner ruling 2026-10-13, option (a):
        # a run that ran outranks a cancelled run of its name); a failed twin is red on the failure. Either order.
        cancelled = {"name": "gates", "status": "completed", "conclusion": "cancelled"}
        rows = (
            ("live", {"name": "gates", "status": "in_progress", "conclusion": ""}, ([], ["workflow gates"])),
            ("succeeded", {"name": "gates", "status": "completed", "conclusion": "success"}, ([], [])),
            ("failed", {"name": "gates", "status": "completed", "conclusion": "failure"}, (["workflow gates: failure"], [])),
        )
        for twin, other, want in rows:
            for order, runs in (("cancelled first", [cancelled, other]), ("twin first", [other, cancelled])):
                with self.subTest(twin=twin, order=order):
                    self.assertEqual(merge.Host.judge_runs(runs), want)

    def test_a_newer_skipped_run_does_not_outrank_hide_or_erase_an_older_run_of_its_name(self):
        # Incident 2026-10-12, bin/merge 360: a draft PR marked ready in the same second. The skipped `opened` run is
        # newer than the green `ready_for_review` run of the same workflow. A skip never outranks a run that ran.
        # Rows: the older run is a success, in progress, cancelled, or failed. Each row is one pure judge_runs input.
        skipped = {"name": "gates", "status": "completed", "conclusion": "skipped"}
        rows = (
            ("success", {"name": "gates", "status": "completed", "conclusion": "success"}, ([], [])),
            ("in progress", {"name": "gates", "status": "in_progress", "conclusion": ""}, ([], ["workflow gates"])),
            ("cancelled", {"name": "gates", "status": "completed", "conclusion": "cancelled"}, (["workflow gates: cancelled"], [])),
            ("failure", {"name": "gates", "status": "completed", "conclusion": "failure"}, (["workflow gates: failure"], [])),
        )
        for older, run, want in rows:
            with self.subTest(older=older):
                self.assertEqual(merge.Host.judge_runs([skipped, run]), want)

    def test_a_head_where_every_check_skipped_is_refused_with_the_remedy(self):
        before = self.head()
        self.set(checks_seq=[[("gates", "skipping", "")]], runs_seq=[[("gates", "completed", "skipped")]])
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertIn("no check ran on this head", out)
        self.assertIn("gh workflow run gates.yml --ref", out)
        self.assertNotIn("pr merge", self.calls())
        self.assertEqual(self.head(), before)

    def test_a_newer_skipped_run_on_the_wait_path_does_not_refuse_an_older_success(self):
        # Incident 2026-10-12, bin/merge 360: the same race through run_state. Checks pass; the runs are skipped then success.
        before = self.head()
        self.set(checks_seq=[[("gates", "pass", "")]], runs_seq=[[("gates", "completed", "skipped"), ("gates", "completed", "success")]])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertIn("pr merge", self.calls())
        self.assertNotEqual(self.head(), before)

    def test_a_missing_required_check_beside_a_skipped_one_is_pending_not_red(self):
        # B1: nothing has reported gates yet. The skipped gates-windows row is not proof that no check ran.
        red, pending, _ = merge.Host.classify({"gates-windows": [("skipping", "")]}, ["gates", "gates-windows"])
        self.assertEqual((red, pending), ([], ["gates"]))

    def test_a_skipped_head_with_a_run_in_progress_waits_for_the_run(self):
        # B1: the skipped rows are old. The gates run is still in progress with no job rows, so the wait holds.
        self.set(checks_seq=[[("gates", "skipping", "")]], runs_seq=[[("gates", "in_progress", "")], [("gates", "completed", "skipped")]])
        rc, out = self.go()
        self.assertGreaterEqual(self.paused.count(60), 1, out)
        self.assertEqual(rc, 1, out)
        self.assertIn("no check ran on this head", out)
        self.assertNotIn("pr merge", self.calls())

    def test_the_remedy_run_in_progress_beside_old_skipped_rows_waits(self):
        # B1: the remedy's own run. Old skipped rows and a run in progress hold the wait, then the pass lets it merge.
        self.set(checks_seq=[[("gates", "skipping", "")], [("gates", "pass", "")]], runs_seq=[[("gates", "in_progress", "")], [("gates", "completed", "success")]])
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertGreaterEqual(self.paused.count(60), 1, out)

    def test_an_older_run_still_in_progress_holds_the_wait_under_a_newer_success(self):
        # B2: gh lists the newest run first. The older in-progress run is read as pending before the dedup.
        runs = [{"name": "gates", "status": "completed", "conclusion": "success"}, {"name": "gates", "status": "in_progress", "conclusion": ""}]
        self.assertEqual(merge.Host.judge_runs(runs), ([], ["workflow gates"]))

    def test_the_no_check_ran_remedy_names_the_real_branch(self):
        self.set(checks_seq=[[("gates", "skipping", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertIn("gh workflow run gates.yml --ref feat", out)
        self.assertNotIn("<branch>", out)

    def test_cancelled_and_unknown_buckets_stop_the_run(self):
        for bucket in ("cancel", "startup_failure"):
            self.set(checks_seq=[[("gates", "pass", ""), ("x", bucket, "")]])
            rc, out = self.go()
            self.assertEqual(rc, 1, bucket)
            self.assertIn(f"x: {bucket}", out)
        self.assertNotIn("pr merge", self.calls())

    def test_an_ignore_entry_without_a_reason_refuses_the_config(self):
        for bad in ({"name": "design"}, {"name": "design", "reason": "  "}, {"reason": "r"}):
            cfg = dict(CONFIG, merge=dict(CONFIG["merge"], ignoreChecks=[bad]))
            put_base_config(self, json.dumps(cfg))
            rc, out = self.run_merge("7", "--confirm")
            self.assertEqual(rc, 1)
            self.assertIn("merge.ignoreChecks", out)
            self.assertFalse(self.lock_ref())

    def test_an_ignored_red_check_is_reported_and_the_merge_goes_on(self):
        self.set(checks_seq=[[("gates", "pass", ""), ("design", "fail", ""), ("slow", "pending", "")]])
        rc, out = self.go(ignore={"design": "flaky upstream", "slow": "nightly"})
        self.assertEqual(rc, 0, out)
        self.assertIn("design (flaky upstream): fail", out)
        self.assertIn("pr merge", self.calls())

    def test_the_preview_lists_a_pending_check_that_is_not_required(self):
        self.set(checks_seq=[[("gates", "pass", ""), ("design", "pending", "")]])
        rc, out = self.run_merge("7", host=self.gh_host())
        self.assertIn("head checks: pending: design", out)

    def test_a_required_check_is_never_ignored(self):
        before = self.head()
        rc, out = self.go(ignore={"gates": "flaky"})
        self.assertEqual(rc, 1)
        self.assertIn("A required check is never ignored", out)
        self.assertEqual(self.head(), before)
        self.assertNotIn("pr merge", self.calls())

    def test_classify_keeps_an_absent_required_name_pending_even_when_ignored(self):
        red, pending, _ = merge.Host.classify({"a": [("pass", "")]}, ["a", "b"], {"b": "x"})
        self.assertEqual(pending, ["b"])

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
        self.set(checks_seq=[[("gates", "pass", "")], [("gates", "pass", ""), ("late", "fail", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("late: fail", out)
        self.assertIn(merge.SETTLE_SECONDS, self.paused)
        self.assertEqual(self.head(), before)  # stopped at the head wait: nothing claimed

    def test_a_failed_read_in_the_wait_reverts_the_claim(self):
        before = self.head()
        self.set(checks_broken=True, broken_from=2)  # the head and its settle read fine, the wait after the claim push does not
        self.set(checks_seq=[[("gates", "pass", "")]])
        rc, out = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("gh pr checks failed", out)
        self.assertNotEqual(self.head(), before)  # the claim was pushed, then reverted
        self.assertTrue(self.reverted())
        self.assertFalse(self.lock_ref())

    # ---- no .github/stamp.json: the defaults (owner ruling 2026-10-10)

    def test_no_config_preview_uses_the_defaults_and_names_the_file_once(self):
        drop_config(self)
        rc, out = self.run_merge("7", host=self.gh_host())
        self.assertEqual(rc, 0, out)
        self.assertIn("gh pr merge --merge", out)  # method "merge"
        self.assertIn("run 0 afterMerge command(s)", out)  # afterMerge empty
        named = [l for l in out.splitlines() if ".github/stamp.json" in l]
        self.assertEqual(len(named), 1, out)
        self.assertIn("default", named[0].lower())
        self.assertIn("repo view", self.calls())  # defaultBranch from the host

    def test_no_config_takes_the_default_branch_from_the_host(self):
        drop_config(self)
        self.set(default_branch="trunk")
        rc, out = self.run_merge("7", host=self.gh_host())
        self.assertIn("is not the default branch (trunk)", out)

    def test_no_config_merges_on_the_defaults_and_claims_nothing(self):
        drop_config(self)
        self.set(contexts=["gates"])
        self.host = None  # main builds the real Host from the defaults: requiredChecks "protection"
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        log = self.calls()
        self.assertIn("branches/main/protection/required_status_checks", log)
        self.assertIn("pr merge 7 --merge --match-head-commit", log)
        self.assertEqual(self.claims(), 0)
        self.assertIn("id: pending", self.show("main", "docs/decisions/second.md"))
        named = [l for l in out.splitlines() if ".github/stamp.json" in l]
        self.assertEqual(len(named), 1, out)
        self.assertIn("default", named[0].lower())

    def test_no_config_waits_the_default_45_minutes(self):
        drop_config(self)
        self.set(contexts=["gates"], checks_seq=[[("gates", "pending", "")]])
        rc, out = self.go(required="protection")
        self.assertEqual(rc, 1)
        self.assertIn("the deadline of 45 minutes passed", out)
        self.assertNotIn("pr merge", self.calls())

    def test_no_config_never_runs_stamp(self):
        drop_config(self)
        mark = stamp_marker(self)
        self.set(contexts=["gates"])
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
            self.assertNotIn("pr merge", self.calls())

    def test_a_partial_merge_block_takes_the_defaults_for_the_missing_fields(self):
        put_base_config(self, json.dumps({"defaultBranch": "main", "merge": {"method": "squash"}}))
        self.set(contexts=["gates"])
        self.host = None  # main builds the Host from the filled defaults: requiredChecks "protection"
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        log = self.calls()
        self.assertIn("pr merge 7 --squash --match-head-commit", log)  # method from the file
        self.assertIn("branches/main/protection/required_status_checks", log)  # requiredChecks default
        filled = [l for l in out.splitlines() if all(f in l for f in ("deadlineMinutes", "requiredChecks", "afterMerge"))]
        self.assertEqual(len(filled), 1, out)  # one line names the fields it filled
        self.assertNotIn("method", filled[0])  # the file's own field is not filled

    def test_a_config_without_defaultBranch_reads_it_from_the_host(self):
        put_base_config(self, json.dumps({"merge": dict(CONFIG["merge"])}))
        self.set(default_branch="trunk")
        rc, out = self.run_merge("7", host=self.gh_host())
        self.assertEqual(rc, 0, out)
        self.assertIn("repo view", self.calls())
        self.assertIn("main is not the default branch (trunk)", out)

    def assert_draft_refused(self, rc, out, before):
        self.assertEqual(rc, 1, out)
        lines = [l for l in out.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1, out)
        self.assertTrue(lines[0].startswith("merge:"), out)
        self.assertIn("draft", lines[0])
        self.assertEqual(self.refs(), before)  # no claim pushed
        self.assertEqual(self.ticks, 0, "waited on a draft")
        self.assertNotIn("pr checks", self.calls())
        self.assertNotIn("pr merge", self.calls())
        self.assertNotIn("Traceback", out)

    def test_a_draft_pr_previews_with_the_undo_check_and_claims_nothing_or_waits(self):  # re-pointed: a draft is a preview now
        self.set(draft=True)
        before = self.refs()
        real, seen = merge.undo_check, []
        def spy(wt, base_ref, unknown_ok=""):
            seen.append((base_ref, sh(wt, "git", "rev-parse", "HEAD")))  # the check runs on the PR head's worktree
            return real(wt, base_ref, unknown_ok)
        with unittest.mock.patch.object(merge, "undo_check", spy):
            rc, out = self.run_merge("7", host=self.gh_host())
        self.assertEqual(rc, 0, out)
        self.assertIn("draft", out.lower())
        self.assertEqual(seen, [("origin/main", self.head("feat"))])
        self.assertEqual(self.refs(), before)  # no claim pushed
        self.assertEqual(self.ticks, 0, "waited on a draft")
        self.assertNotIn("pr merge", self.calls())
        self.assertNotIn("Traceback", out)

    def test_a_pr_that_turns_draft_after_the_preview_read_is_refused_at_confirm(self):  # guard: green once merge.py checks draft under the lock
        put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], requiredChecks=["gates"]))))  # complete: no defaults notice in the output
        self.set(draft_from_view=2)  # read 1 is main's read at the top of --confirm; read 2 is confirm's read under the lock
        before = self.refs()
        rc, out = self.run_merge("7", "--confirm", host=self.gh_host())
        self.assert_draft_refused(rc, out, before)

    def test_a_draft_pr_is_refused_at_confirm_before_any_claim_or_wait(self):
        self.set(draft=True)
        before = self.refs()
        rc, out = self.run_merge("7", "--confirm", host=self.gh_host())
        self.assert_draft_refused(rc, out, before)

def put_base_config(env, text):
    """Commit `text` as .github/stamp.json on origin's main from the other clone. env.co keeps its local checkout."""
    o = env.other
    sh(o, "git", "fetch", "-q", "origin")
    sh(o, "git", "checkout", "-q", "-B", "main", "origin/main")
    put(os.path.join(o, ".github/stamp.json"), text)
    sh(o, "git", "commit", "-qam", "base config")
    sh(o, "git", "push", "-q", "origin", "main")
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
    sh(env.co, "git", "fetch", "-q", "origin")

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
                                              [{"name": ["gates"], "reason": "x"}],
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

    def test_deadlineMinutes_360_is_accepted_at_preview_and_confirm(self):  # the cap's edge: a guard, green today
        put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], deadlineMinutes=360))))
        for args in (("7",), ("7", "--confirm")):
            with self.subTest(args=args):
                rc, out = self.run_merge(*args)
                self.assertEqual(rc, 0, out)

    def config_text(self, fields=None, **top):
        """A complete merge block (no defaults notice), with `fields` replaced and `top` keys set at the top level."""
        block = dict({"method": "merge", "deadlineMinutes": 5, "requiredChecks": ["gates"], "afterMerge": [], "deleteBranch": True}, **(fields or {}))
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
        rows += [("requiredChecks", self.config_text({"requiredChecks": v})) for v in ([["gates"]], [{}], [1, "gates"], [], "gates", [""])]
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

    def test_a_valid_config_with_every_field_is_accepted_at_preview(self):  # the control: green today and after the fix
        for fields in ({"method": "squash", "requiredChecks": "protection", "afterMerge": ["true"], "deleteBranch": False},
                       {"method": "rebase", "requiredChecks": ["gates"], "afterMerge": ["true", "echo x"], "deleteBranch": True}):
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
        def second_is_red(wt, base, unknown_ok=""):
            calls.append(base)
            if len(calls) == 2:
                raise merge.Stop("the branch silently undoes earlier work: main moved during the wait")
            return real(wt, base, unknown_ok)
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
        rc, out = self.run_merge("7")  # the exit code is not pinned here: see the report
        self.assertIn("silently undoes", out)
        self.assertIn("first.md", out)
        self.assertIn("draft", out.lower())
        self.assertEqual(self.refs(), before)
        self.assertFalse(self.lock_ref())
        self.assertEqual(self.host.waits, [])
        self.assertEqual(self.worktrees(), 1)

    def test_a_ready_preview_reports_a_dropped_line(self):  # today preview never runs the check at all
        SilentUndo.stale_feat(self)
        before = self.refs()
        rc, out = self.run_merge("7")
        self.assertIn("silently undoes", out)
        self.assertIn("first.md", out)
        self.assertEqual(self.refs(), before)
        self.assertFalse(self.lock_ref())
        self.assertEqual(self.host.waits, [])

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

    def test_a_closed_or_merged_pr_is_refused_at_preview_and_the_check_never_runs(self):  # control: green today
        real, calls = merge.undo_check, []
        def spy(wt, base_ref, unknown_ok=""):
            calls.append(base_ref)
            return real(wt, base_ref, unknown_ok)
        before = self.refs()
        with unittest.mock.patch.object(merge, "undo_check", spy):
            for state in ("CLOSED", "MERGED"):
                self.host.pr_state = state
                rc, out = self.run_merge("7")
                self.assertEqual(rc, 1, out)
                self.assertIn("the pull request is " + state, out)
        self.assertEqual(calls, [])
        self.assertEqual(self.refs(), before)


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
    """q_max PR 402: stamp.mjs --claim prints Record-claim: on stdout, but its regenerate step
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
    One scan is one call of check_silent_undo.check. Cause: q_max #855 ran two scans of about 35 min each."""

    def counted(self, fn):
        sys.path.insert(0, os.path.join(HERE, "..", "lint"))
        import check_silent_undo as undo
        real_check, real_undo = undo.check, merge.undo_check
        scans, undos = [], []

        def spy_check(*a, **k):
            scans.append(a[1])
            return real_check(*a, **k)

        def spy_undo(wt, base_ref, unknown_ok=""):
            undos.append(base_ref)
            return real_undo(wt, base_ref, unknown_ok)
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
        self.assertEqual(rc, 0, out)
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
        sh(self.co, "git", "push", "-q", "origin", f"{sha}:refs/merge-lock/main")

    def lock_msg(self):
        sh(self.co, "git", "fetch", "-q", "origin", "refs/merge-lock/main")
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

    def new_message(self, host, pid, expires=None, platform=None):
        return (f"merge lock\nexpires: {int(expires or self.now + 600)}\nowner: abc123\n"
                f"pr: 445\nbranch: b\nhost: {host}\npid: {pid}\nstarted: 1790000000\nplatform: {platform or sys.platform}")

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
    def test_held_says_dead_for_a_lock_on_this_host_whose_pid_is_gone(self):
        out = self.held(self.new_message(socket.gethostname(), dead_pid()))
        for want in ("PR #445", "branch b", "dead", "merge --unlock"):
            self.assertIn(want, out)
        self.assertNotIn("Cannot tell", out)

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
            if "/git/ref/merge-lock/" in p:
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
            if "/git/ref/merge-lock/" in a[0]:
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
    """merge.is_net on the output of one failed gh or git call. Round 2: a wrapped 5xx or 429 line, and a JSON body with gh's
    error line after it. The false-match cases stay green: a PR title, a check name, a refusal that quotes a 5xx."""
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
                    '[{"name":"gates: HTTP 502","bucket":"fail","link":""}]',
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
        # Round 3: an unanchored `HTTP 5xx (url)` alternative matched refusal text. A real refusal must revert, not retry into NetStop.
        for out in ("X Pull request #7 is not mergeable: Retry on HTTP 502 (https://github.com/o/r/issues/12)",
                    "X Pull request #7 is not mergeable: Retry on HTTP 429 (https://github.com/o/r/issues/12)"):
            with self.subTest(out=out):
                self.assertFalse(merge.is_net(1, out))

    def test_a_real_server_error_or_wrapped_run_line_is_a_network_error(self):
        # Round 3 guard: the anchor fix must keep the 5xx and 429 forms gh really prints, bare or after `: `.
        for out in ("Server Error (HTTP 502)",
                    "HTTP 502 (https://api.github.com/repos/o/r/branches/main/protection/required_status_checks)",
                    "failed to get runs: HTTP 502 (https://api.github.com/repos/o/r/actions/runs?head_sha=abc)",
                    "HTTP 429: Too Many Requests",
                    "failed to get runs: HTTP 429: Too Many Requests (https://api.github.com/repos/o/r/actions/runs?head_sha=abc)"):
            with self.subTest(out=out):
                self.assertTrue(merge.is_net(1, out))

    def test_a_wrapped_5xx_with_no_space_after_its_colon_is_not_a_network_error(self):
        # Round 1 fix guard: the anchor edit must keep the space in `: ` before the message, or `HTTP 502:x (url)` matches.
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
    """merge.is_net on a rate-limited gh call (lane merge-rate-limit). A rate-limit 403 is a network fault. A permission 403 is a refusal.
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
    """retry_net and Host.gh on a rate-limited call (lane merge-rate-limit): how many tries, and how long each wait is. The pause is a
    recorder, so nothing sleeps. Headers are ignored (orchestrator ruling 2026-10-14): a rate-limit text (403 or 429, any form) waits
    merge.RATE_WAIT_CAP per retry, whatever a `Retry-After` or `X-Ratelimit-Reset` line says. Any other network error waits merge.NET_PAUSE."""
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
        return merge.Host(required=["gates"], base="main", minute=60, now=lambda: self.NOW, pause=self.pauses.append)

    def retry(self, *seq):
        """-> merge.retry_net's result over the replies `seq`."""
        self.calls = 0
        def call():
            self.calls += 1
            return seq[min(self.calls, len(seq)) - 1]
        return merge.retry_net(call, self.pauses.append)

    # retry_net: the tries
    def test_a_rate_limit_403_is_retried_with_the_rate_wait(self):
        self.assertEqual(self.retry((1, RATE_403), (1, RATE_SECONDARY_403), (0, "[]")), (0, "[]", 2))
        self.assertEqual(self.pauses, [merge.RATE_WAIT_CAP] * 2)  # a rate limit waits the cap, not NET_PAUSE

    def test_the_wait_cap_is_60_seconds(self):  # orchestrator's call, 2026-10-14: the one value, so the other cases read the constant
        self.assertEqual(merge.RATE_WAIT_CAP, 60)

    def test_a_graphql_rate_limit_already_exceeded_is_retried_with_the_rate_wait(self):
        self.assertEqual(self.retry((1, RATE_GQL_ALREADY), (0, "[]")), (0, "[]", 1))
        self.assertEqual(self.pauses, [merge.RATE_WAIT_CAP])

    def test_a_rate_limit_403_that_never_clears_is_tried_four_times(self):
        self.assertEqual(self.retry((1, RATE_403)), (1, RATE_403, 3))
        self.assertEqual(self.calls, 4)  # one try and three retries
        self.assertEqual(self.pauses, [merge.RATE_WAIT_CAP] * 3)

    def test_a_429_is_retried_with_the_rate_wait(self):
        self.assertEqual(self.retry((1, R429), (0, "[]")), (0, "[]", 1))
        self.assertEqual(self.pauses, [merge.RATE_WAIT_CAP])

    def test_a_plain_403_is_not_retried(self):  # (d): green before the lane, a guard
        for out in (PLAIN_403, PLAIN_403_BRANCH, PLAIN_403_API):
            with self.subTest(out=out[:70]):
                self.pauses.clear()
                self.assertEqual(self.retry((1, out), (0, "[]")), (1, out, 0))
                self.assertEqual(self.pauses, [])

    def test_a_plain_network_error_waits_the_normal_pause_whatever_its_headers(self):  # the NET_PAUSE half of the rule
        for out in (NET_TLS, "failed to get runs: HTTP 502: 502 Bad Gateway (https://api.github.com/repos/o/r/actions/runs?head_sha=abc)",
                    "Retry-After: 5\n" + NET_TLS):
            with self.subTest(out=out[:40]):
                self.pauses.clear()
                self.assertEqual(self.retry((1, out), (0, "[]")), (0, "[]", 1))
                self.assertEqual(self.pauses, [merge.NET_PAUSE])

    def test_a_retry_after_never_changes_the_rate_wait(self):  # a Retry-After of 5 s or 600 s is no wait: every rate-limit text waits the cap
        for text in (R429, RATE_403, RATE_SECONDARY_403, RATE_GQL_ALREADY):
            for header in ("Retry-After: 5", "retry-after: 17", "Retry-After: 600"):
                with self.subTest(text=text[:40], header=header):
                    self.pauses.clear()
                    self.assertEqual(self.retry((1, header + "\n" + text), (0, "[]")), (0, "[]", 1))
                    self.assertEqual(self.pauses, [merge.RATE_WAIT_CAP])

    # Host.gh: a reset header is ignored, near, far or past (orchestrator ruling 2026-10-14). The reset time is no wait.
    def test_a_reset_time_never_changes_the_rate_wait_on_a_429_or_a_rate_limit_403(self):
        for text in (R429, RATE_403):
            for header in (f"X-Ratelimit-Reset: {int(self.NOW) + 5}", f"X-Ratelimit-Reset: {int(self.NOW) + 23}",
                           f"X-RateLimit-Reset: {int(self.NOW) + 3600}"):
                with self.subTest(text=text[:40], header=header):
                    self.pauses.clear()
                    self.replies((1, header + "\n" + text), (0, "[]"))
                    self.assertEqual(self.host().gh(["run", "list"]), (0, "[]"))
                    self.assertEqual(self.pauses, [merge.RATE_WAIT_CAP])

    def test_a_reset_time_already_past_waits_the_rate_wait_never_a_negative_time(self):
        self.replies((1, f"X-Ratelimit-Reset: {int(self.NOW) - 100}\n" + R429), (0, "[]"))
        self.host().gh(["run", "list"])
        self.assertEqual(self.pauses, [merge.RATE_WAIT_CAP])  # a fixed cap: no time is computed from the header

    def test_a_rate_limit_waits_the_rate_wait_whatever_its_timestamp_says(self):
        self.replies((1, RATE_403), (0, "[]"))  # "timestamp 2026-10-14 12:26:42 UTC" is the request's time, not a reset
        self.host().gh(["run", "list"])
        self.assertEqual(self.pauses, [merge.RATE_WAIT_CAP])

    def test_a_rate_limit_that_never_clears_is_a_net_stop_after_three_retries(self):  # (e)
        self.replies((1, RATE_403))
        with self.assertRaises(merge.NetStop) as cm:
            self.host().gh(["run", "list"])
        self.assertEqual(self.calls, 4)
        self.assertEqual(self.pauses, [merge.RATE_WAIT_CAP] * 3)
        self.assertIn("API rate limit exceeded", str(cm.exception))  # the stop shows gh's own words

    def test_a_plain_403_is_returned_at_once_by_host_gh(self):  # (d): a guard
        self.replies((1, PLAIN_403))
        self.assertEqual(self.host().gh(["run", "list"]), (1, PLAIN_403))
        self.assertEqual((self.calls, self.pauses), (1, []))

    def test_a_rate_wait_in_host_gh_prints_one_line_before_the_wait(self):  # item 3, Host.gh: red on 2cc181d
        self.replies((1, RATE_403), (0, "[]"))
        buf, snapshots = io.StringIO(), []
        host = merge.Host(required=["gates"], base="main", minute=60, now=lambda: self.NOW, pause=lambda s: snapshots.append(buf.getvalue()))
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            self.assertEqual(host.gh(["run", "list"]), (0, "[]"))
        assert_one_rate_wait_line(self, buf.getvalue(), snapshots)

    def test_a_plain_403_prints_no_wait_line(self):  # control: green on 2cc181d, a guard
        self.replies((1, PLAIN_403))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            self.assertEqual(self.host().gh(["run", "list"]), (1, PLAIN_403))
        self.assertNotRegex(buf.getvalue(), r"(?i)\bwait")

class GhLockReadRetry(unittest.TestCase):
    """GhLock.read on a network error: retried as GitLock is (round 2: GhLock is in scope). merge.sh is the only seam,
    so the test holds wherever the retry sits, in read or in api."""
    def run_read(self, replies):
        """The ref reads answer `replies` in order, the last repeats. -> the read's result. self.reads and self.pauses count the calls."""
        seq, self.reads, self.pauses = list(replies), 0, []
        def fake_sh(args, cwd=None, input=None, env=None):
            if args[:2] == ["gh", "api"] and "/git/ref/merge-lock/" in args[2]:
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
    """GitLock.read on a failing ls-remote. A network text stops with NetStop after three retries. Any other text stops at once.
    No test held either path before round 2."""
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
            "Flow.test_afterMerge_runs_in_git_bash_not_the_wsl_stub",
            "Flow.test_full_merge_claims_pushes_merges_syncs_cleans",
            "GhHalf.test_an_empty_required_list_is_refused",
            "LockHolder.test_a_lock_with_no_platform_line_reads_cannot_tell_never_dead",
            "LockHolder.test_held_says_dead_for_a_lock_on_this_host_whose_pid_is_gone",
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
        super().__init__(required=["gates"], base="main", minute=60, now=lambda: self.clock[0], pause=self.advance)

    def advance(self, s):
        self.pauses.append(s)
        self.clock[0] += s
        assert len(self.pauses) < 500, "the wait never ended"

    def read(self):
        """Each fake gh read costs READ_SECONDS of fake time, as a real call does."""
        self.clock[0] += READ_SECONDS

    def pr(self, n):
        self.read()
        return {"head": self.head_at(self.clock[0]), "branch": "feat", "base": "main", "state": "OPEN",
                "mergeable": "MERGEABLE", "merge_state": "CLEAN", "draft": False}

    def checks(self, n):
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
        host = ClockedHost(lambda t: {"gates": [("pending" if t < 600 else "pass", "")]})
        ok, why, lines, waits, end = self.wait(host, 15)
        self.assertTrue(ok, why)
        self.assertTrue(waits, "no `merge: waiting on` line during the 10-minute wait")
        self.assertIn("gates", waits[0][1])  # the first line names the pending check
        self.assert_gaps_within(lines, 0.0, end)

    def test_a_lagging_head_never_goes_120_seconds_without_a_line(self):
        # The head reads as the prior one for 600 s; the checks are pending until 900 s.
        host = ClockedHost(lambda t: {"gates": [("pending" if t < 900 else "pass", "")]},
                           head_at=lambda t: "old" if t < 600 else "sha")
        ok, why, lines, _, end = self.wait(host, 30, prior="old")
        self.assertTrue(ok, why)
        self.assert_gaps_within(lines, 0.0, end)

    def test_a_change_in_the_pending_set_prints_at_once(self):
        def checks_at(t):
            if t < 60:
                return {"gates": [("pending", "")]}
            if t < 300:
                return {"gates": [("pending", "")], "design": [("pending", "")]}
            return {"gates": [("pass", "")], "design": [("pass", "")]}
        host = ClockedHost(checks_at)
        ok, why, _, waits, _ = self.wait(host, 15)
        self.assertTrue(ok, why)
        design = [t for t, l in waits if "design" in l]
        # The change is first read at about 64 s (a read costs 2 s, the loop pauses 60 s). It must print before the next 60 s pass.
        self.assertTrue(design and design[0] < 120, f"a new pending check named at {design[:1]}; lines at {[round(t) for t, _ in waits]}")

    def test_a_wait_that_is_green_on_the_first_read_prints_no_waiting_line(self):
        host = ClockedHost(lambda t: {"gates": [("pass", "")]})
        ok, why, _, waits, _ = self.wait(host, 15)
        self.assertTrue(ok, why)
        self.assertEqual(waits, [])

    def test_a_green_wait_says_what_it_checks_before_the_first_read(self):
        """A start line, not a waiting line: the wait names the checks it reads before its first gh call (fake time 0)."""
        host = ClockedHost(lambda t: {"gates": [("pass", "")]})
        ok, why, lines, _, _ = self.wait(host, 15)
        self.assertTrue(ok, why)
        self.assertTrue(lines and lines[0][0] < READ_SECONDS, f"no line before the first read; lines {lines}")
        self.assertIn("gates", lines[0][1])

class SilentWait(Env):
    """Silence seen on q_max PR 855 (2026-10-13): merge printed only the launch line for minutes. A long step printed
    nothing before it started. A `gh` call whose helper keeps its stdout open also blocks silently (measured:
    subprocess.run waits for the pipe, not the child). Each case holds one call that way and checks that merge
    prints a line before the call blocks. Not a GhHalf subclass: the GhHalf tests must not run twice."""
    set, calls, gh_host, go = GhHalf.set, GhHalf.calls, GhHalf.gh_host, GhHalf.go

    def setUp(self):  # the fake-gh setup of GhHalf.setUp, without its tests
        Env.setUp(self)
        bindir = os.path.join(self.t, "bin"); os.makedirs(bindir)
        gh = os.path.join(bindir, "gh"); put_shim(gh, FAKE_GH_PR)
        self.state = os.path.join(self.t, "ghstate"); os.makedirs(self.state)
        old = {k: os.environ.get(k) for k in ("PATH", "FAKE_GH_DIR")}
        os.environ["PATH"] = bindir + os.pathsep + old["PATH"]; os.environ["FAKE_GH_DIR"] = self.state
        self.addCleanup(lambda: [os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None) for k, v in old.items()])
        self.ticks, self.paused = 0, []
        self.set(checks_seq=[[("gates", "pass", "")]])

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
        seen, _, _ = self.hold_run(["pr", "checks"], 12, self.gh_host())
        self.assert_names_the_held_step(seen, "gh pr checks")

    def test_a_held_merge_call_names_its_step_before_it_blocks(self):
        seen, rc, out = self.hold_run(["pr", "merge"], 12, self.gh_host())
        self.assertEqual(rc, 0, out)
        self.assert_names_the_held_step(seen, "gh pr merge")

    def test_red_required_check_beside_skipped_jobs_refuses_at_once(self):
        self.set(checks_seq=[[("gates", "fail", "https://x/gates"), ("scope", "skipping", ""), ("gate-windows", "skipping", "")]],
                 runs_seq=[[("gates", "completed", "failure"), ("gate-windows", "completed", "skipped")]])
        rc, out = self.go(required=("gates", "scope"))
        self.assertEqual(rc, 1, out)
        self.assertIn("a check is red", out)
        self.assertEqual(self.paused, [], "a red head waited before it refused")
        self.assertNotIn("pr merge", self.calls())

    def test_zero_contexts_and_a_required_name_with_no_run_say_what_they_wait_on(self):
        self.set(checks_seq=[[]], runs_seq=[[("gate", "in_progress", None)]])
        rc, out = self.go(required=("gate",))
        self.assertEqual(rc, 1, out)
        self.assertIn("waiting on gate", out)
        self.assertIn("workflow gate", out)

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

        def scan(cwd, upstream, head, default=None):
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
        host = merge.Host(required=["gates"], base="main", minute=60, now=lambda: 0.0, pause=lambda s: None)
        before = self.first_call_text(host, lambda h: h.merge(7, "merge", "sha"))
        self.assertRegex(before, r"(?m)^merge: merging #7", f"printed before the merge call: {before!r}")

# ---- the records page is rebuilt at merge time --------------------------------------------------------------------

# The records-only mode the builder adds to lint/hook_catalog.py: it writes docs/records.md and nothing else. The merge
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

    def on(self, branch, files, msg="records"):
        """Push one commit to origin/<branch> from the second clone, as a person or another run would."""
        o = self.other
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", branch, f"origin/{branch}")
        for rel, text in files.items():
            put_lf(os.path.join(o, rel), text)
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-qm", msg); sh(o, "git", "push", "-q", "origin", branch)

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
    """Owner ruling 2026-10-14 13:18 CDT: the records index is rebuilt at merge time, the way record numbers are claimed
    from the slug form at merge. Lane records-index, round 1. Red on 1ac9851: merge.py never runs a records generator.

    The builder's contract for merge/merge.py. The seam is confirm() and preview(), beside do_claim and commit_claim.
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
        for p in (unittest.mock.patch.object(merge, "RECORDS", self.prog, create=True),  # create: red on 1ac9851 is a failure, not an error
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
        # Regression pin, green on 1ac9851: a lane merged into an integration branch must not carry the page, or the
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
        # Re-pointed from the --root-only pin (stale, owner ruling test-strategy-reset). The merge tool runs the records-only
        # mode, RECORDS_ONLY, and no other argument. Red on 392cc37: the call is --root <wt> with no mode flag.
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
        self.host.seq = [(True, ""), (False, "a check is red: gates: fail")]  # the head is green, the rebuild commit is red
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

    def test_main_gaining_an_unrelated_change_during_the_wait_still_merges_a_fresh_page(self):
        self.kinds_off()
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT})
        self.host.on_wait = lambda: self.on("main", {"notes.txt": "unrelated\n"}, "untooled push")
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertTrue(getattr(self.host, "merged", False), out)
        self.assertEqual(self.show("main", "docs/records.md"), page("gap-one").strip())

    def test_the_preview_on_a_non_default_base_says_nothing_about_the_page(self):
        # Pin, green on 6fb3ac0. The records line sits inside the default-branch block of preview(), so a pull request
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
        # Red on 6fb3ac0. The preview says the page needs a rebuild. Confirm skips the rebuild on a resumed head,
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
        # Regression pin, green on 1ac9851. The tool runs the generator on every repo, so an empty repo must stay empty.
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
        # Red on 6fb3ac0. records_stale() reads any conflict as "cannot be proved fresh" and reverts the claim. Here only
        # the generated page conflicts (add/add on both sides), so the tool rebuilds it on the merged tree and goes on.
        self.kinds_off()
        self.on("main", {"debts/main-gap.md": DEBT_TEXT.replace("Gap one", "Main gap"), "docs/records.md": "records\n- main-gap\n"},
                "a debt and a hand-written page on main")
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT})
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertTrue(getattr(self.host, "merged", False), out)
        page = self.show("main", "docs/records.md")
        self.assertIn("gap-one", page)
        self.assertIn("main-gap", page)
        self.assertEqual(page, self.generated("origin/main"))

    def test_a_conflict_on_another_file_still_refuses_and_reverts(self):
        # Pin, green on 6fb3ac0. A conflict outside the generated page must still stop the merge. This blocks a blanket
        # -X ours or -X theirs that would silence every conflict.
        self.kinds_off()
        self.on("main", {"notes.txt": "main side\n"}, "a note on main")
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT, "notes.txt": "head side\n"}, "a debt and a note")
        before = self.head()
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
    its merge commit may carry the records page alone (the records-only mode, RECORDS_ONLY). Red on 392cc37: the whole
    generator refuses a root with hooks/ and no settings.json, and it writes docs/catalog.md into the merge."""
    def test_a_page_edited_on_both_sides_with_no_records_stops_the_merge(self):
        # Red on 392cc37: the generator writes nothing here, so the page with conflict markers is committed and merged.
        self.kinds_off()
        self.on("main", {"docs/records.md": "records\n- base\n"}, "a hand-written page")
        o = self.other
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        sh(o, "git", "merge", "-q", "--no-edit", "origin/main")
        put_lf(os.path.join(o, "docs", "records.md"), "records\n- head\n")
        sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-qm", "the head edits the page"); sh(o, "git", "push", "-q", "origin", "feat")
        self.on("main", {"docs/records.md": "records\n- main\n"}, "main edits the page")
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
        # Red on 741a17e: the heal looks for seven-character markers only. A page with nine-character markers passes that look.
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
        self.on("main", {"docs/records.md": "records\n- main\n"}, "main edits the page")
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
        self.drop("main", "docs/records.md", "main drops the page")

    def test_a_page_deleted_on_main_and_edited_on_the_head_with_no_records_stops_the_merge(self):
        # Red on 741a17e: the generator writes nothing here, and the head's page has no marker, so the head's page is committed to main.
        self.delete_edit_setup()
        before, head_before = self.rev("origin/main"), self.head()
        rc, out = self.run_merge("7", "--confirm")
        self.assertNotIn("docs/records.md", self.tree_names("origin/main"), "the defect: the head's page reaches main")
        self.assertEqual(rc, 1, out)
        lines = [l for l in out.splitlines() if l.startswith("merge: ") and "records" in l]
        self.assertTrue(lines, out)
        self.assertFalse(getattr(self.host, "merged", False), out)
        self.assertEqual(self.rev("origin/main"), before)
        self.assertEqual(self.head(), head_before)  # nothing pushed to feat
        self.assertFalse(self.lock_ref())
        self.assertEqual(self.worktrees(), 1)

    def test_a_generated_page_deleted_on_main_with_records_rebuilds_and_merges(self):
        # The control, red on 741a17e: a root with a record folder. The head's page is the generator's output for its debt, and main
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
        # Red on 392cc37: "hook_catalog: cannot read settings.json", so the records page cannot be rebuilt.
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
        # Red on 392cc37: the root renders a catalog, so the generator writes docs/catalog.md and the merge brings it in.
        self.kinds_off()
        self.on("feat", {"settings.json": "{}\n", "hooks/.gitkeep": "", "skills/.gitkeep": "",
                         "decisions/subagent-model-cap.md": "# Subagent model cap\n\nOwner ruling. The table names each role model.\n",
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
    third wait only (len(host.waits) == 3). These pin keep paths that had no test: green on 392cc37, the code already keeps."""
    def setUp(self):
        super().setUp()
        self.calls, self.prog = os.path.join(self.t, "records-calls.log"), os.path.join(self.t, "records.py")
        put(self.prog, FAKE_RECORDS)
        for p in (unittest.mock.patch.object(merge, "RECORDS", self.prog, create=True),
                  unittest.mock.patch.dict(os.environ, {"RECORDS_CALLS": self.calls})):
            p.start(); self.addCleanup(p.stop)

    def heal_setup(self):
        """A debt and a hand-written page on main; the head adds a debt. The head's rebuild commits one page, and the heal merges both."""
        self.kinds_off()
        self.on("main", {"debts/main-gap.md": DEBT_TEXT.replace("Gap one", "Main gap"), "docs/records.md": "records\n- main-gap\n"},
                "a debt and a hand-written page on main")
        self.on("feat", {"debts/gap-one.md": DEBT_TEXT})

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
        self.host.seq = [(True, ""), (True, ""), (False, "a check is red: gates: fail")]
        rc, out = self.run_merge("7", "--confirm")
        self.assert_kept(rc, out)
        self.assertIn("are not green", out)
        self.assertIn("gates: fail", out)

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
    exits non-zero, with no traceback. Red on 392cc37: the import error is a traceback."""
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
    """The records page path has one home, lint/hook_catalog.py. merge.py imports it and holds no copy.
    Red on d027e3d: merge.py:16 is a literal copy of the path."""
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
        self.assertEqual(merge.RECORDS_PAGE, ast.literal_eval(homes[0]))


def assert_one_rate_wait_line(test, text, snapshots):
    """A rate wait prints one line that says it waits, why (a rate limit) and for how long (60 s). `snapshots` holds the
    captured output at each pause: the line must already be there when the wait starts, so a 60 s wait never looks like a hang."""
    lines = [ln for ln in text.splitlines() if re.search(r"wait", ln, re.I)]
    test.assertEqual(len(lines), 1, f"want one wait line, got {text!r}")
    test.assertRegex(lines[0], r"(?i)rate[ -]limit", "the wait line must say why it waits")
    test.assertRegex(lines[0], r"\b60 ?s(econds)?\b", "the wait line must say how long")
    test.assertEqual(len(snapshots), 1, "one rate wait is one pause")
    test.assertIn(lines[0], snapshots[0], "the wait line must print before the wait starts")

class GhLockRateRetry(unittest.TestCase):
    """GhLock on a rate-limit 403 (lane merge-rate-limit, review round 1). Each step of acquire, release, unlock and the lock read
    answers [rate limit, then success]: the step is retried with RATE_WAIT_CAP pauses. A permission 403 stops at once. merge.sh is
    the seam, so the test holds wherever the retry sits. self.pauses records every pause; nothing sleeps."""
    NOW = 1000.0
    OLD, NEW, BASE, TREE = "oldlock", "newlock", "base1", "tree1"
    EXPIRED = (0, merge.lock_message(10, 0.0))  # expires at 10: expired at NOW
    LIVE = (0, "merge lock\nexpires: 2000\nowner: x")
    DEFAULT = {"lock-read": [(1, "gh: Not Found (HTTP 404)")], "lock-commit-read": [EXPIRED], "base-ref": [(0, BASE)],
               "base-tree": [(0, TREE)], "lock-commit-post": [(0, NEW)], "refs-post": [(0, "")], "delete": [(0, "")]}
    OK = {"base-ref": (0, BASE), "base-tree": (0, TREE), "lock-commit-post": (0, NEW), "refs-post": (0, "")}

    def setUp(self):
        self.pauses, self.calls, self.replies = [], {}, {}
        p = unittest.mock.patch.object(merge, "sh", self.fake_sh)
        p.start(); self.addCleanup(p.stop)

    @staticmethod
    def step_of(args):
        """Names the gh call by its step: the method and path, and for a GET of a commit, its --jq."""
        if list(args[:2]) != ["gh", "api"]:
            return "not-gh-api"
        rest = list(args[2:])
        method = "GET"
        if rest[:1] == ["-X"]:
            method, rest = rest[1], rest[2:]
        path = rest[0]
        jq = rest[rest.index("--jq") + 1] if "--jq" in rest else ""
        if method == "DELETE" and path.endswith("/git/refs/merge-lock/main"):
            return "delete"
        if method == "POST" and path.endswith("/git/commits"):
            return "lock-commit-post"
        if method == "POST" and path.endswith("/git/refs"):
            return "refs-post"
        if "/git/ref/merge-lock/" in path:
            return "lock-read"
        if "/git/ref/heads/" in path:
            return "base-ref"
        if "/git/commits/" in path:
            return "base-tree" if jq == ".tree.sha" else "lock-commit-read"
        return "unhandled"

    def fake_sh(self, args, cwd=None, input=None, env=None):
        step = self.step_of(args)
        self.calls[step] = self.calls.get(step, 0) + 1
        seq = self.replies.get(step) or self.DEFAULT.get(step)
        if not seq:
            return 1, f"unhandled {step}: {' '.join(args)}"
        return seq.pop(0) if len(seq) > 1 else seq[0]

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

    def test_a_clean_acquire_takes_the_lock_without_a_pause(self):  # control: green on 8459b59
        self.assertEqual(self.acquire(), self.NEW)
        self.assertEqual((self.calls.get("delete", 0), self.pauses), (0, []))

    def test_a_clean_acquire_over_an_expired_lock_deletes_it_once(self):  # control: green on 8459b59
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
                self.assertEqual(self.pauses, [merge.RATE_WAIT_CAP])

    def test_a_rate_limited_expired_lock_delete_is_retried_before_the_lock_is_replaced(self):
        self.reply("lock-read", (0, self.OLD))
        self.reply("delete", (1, RATE_API_403), (0, ""))
        self.assertEqual(self.acquire(), self.NEW)
        self.assertEqual(self.calls["delete"], 2)
        self.assertEqual(self.pauses, [merge.RATE_WAIT_CAP])

    def test_a_404_after_a_rate_limited_expired_lock_delete_counts_as_done(self):
        self.reply("lock-read", (0, self.OLD))
        self.reply("delete", (1, RATE_API_403), (1, "gh: Not Found (HTTP 404)"))
        self.assertEqual(self.acquire(), self.NEW)
        self.assertEqual(self.calls["delete"], 2)
        self.assertEqual(self.pauses, [merge.RATE_WAIT_CAP])

    def test_a_rate_limited_read_of_the_lock_commit_is_retried_and_keeps_its_expiry(self):
        self.reply("lock-read", (0, self.OLD))
        self.reply("lock-commit-read", (1, RATE_API_403), self.LIVE)
        got = self.lock().read("main")
        self.assertEqual(got[1], 2000)  # base: inf, a live lock for ever
        self.assertEqual(self.pauses, [merge.RATE_WAIT_CAP])

    def test_a_permission_403_on_the_lock_commit_stops_at_once(self):  # guard: green on 8459b59, red if a 403 with no rate text is retried
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
        self.assertEqual(self.pauses, [merge.RATE_WAIT_CAP])

    def test_a_rate_limited_release_delete_is_retried_and_a_404_after_it_counts_as_done(self):
        self.reply("lock-read", (0, "tok"))
        self.reply("lock-commit-read", self.LIVE)
        self.reply("delete", (1, RATE_API_403), (1, "gh: Not Found (HTTP 404)"))
        out = release_out(self, self.lock(), "tok")
        self.assertNotIn("the lock release failed", out)
        self.assertEqual(self.calls["delete"], 2)
        self.assertEqual(self.pauses, [merge.RATE_WAIT_CAP])

    # review round 2: a 404 inside a rate-limit text is no "ref gone"; a lock read that cannot finish is a NetStop; a wait prints a line.
    RATE_404_ID = RATE_API_403.replace("309471439", "4040404")  # the user id holds "404": a rate limit a bare "404" check reads as gone
    LOCK_5XX = '{"message":"Server Error"}gh: Server Error (HTTP 502)'  # gh's own 5xx line after the body, as GH_API_TAIL reads it

    def test_the_404_fixture_is_a_rate_limit_whose_text_holds_404(self):  # control: the trigger of item 1
        self.assertTrue(merge.is_net(1, self.RATE_404_ID))
        self.assertIsNotNone(merge.RATE_LIMIT.search(self.RATE_404_ID))
        self.assertIn("404", self.RATE_404_ID)

    def test_a_rate_limit_whose_text_holds_404_is_never_a_removed_lock(self):  # item 1: red on 2cc181d
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
        self.assertEqual(self.pauses, [merge.RATE_WAIT_CAP] * 3)

    def run_unlock(self, lock):
        """`merge --unlock main` over the fake gh. The one git call (the checkout's root) answers at once. -> (rc, stdout and stderr)."""
        self.reply("not-gh-api", (0, "/repo"))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = merge.main(["--unlock", "main"], lock=lock)
        return rc, buf.getvalue()

    def test_unlock_main_on_a_rate_limit_whose_text_holds_404_stops_and_never_says_removed(self):  # item 1, the CLI line: red on 2cc181d
        self.reply("delete", (1, self.RATE_404_ID))
        rc, out = self.run_unlock(self.lock())
        self.assertEqual(rc, 1, out)
        self.assertNotRegex(out, r"lock on main removed")
        self.assertIn("API rate limit exceeded", out)  # the stop shows gh's own words
        self.assertEqual(self.calls["delete"], 4)

    def test_unlock_main_on_a_missing_ref_says_so_and_never_says_removed(self):  # item 1: red on 2cc181d
        self.reply("delete", (1, "gh: Not Found (HTTP 404)"))
        rc, out = self.run_unlock(self.lock())
        self.assertEqual(rc, 0, out)
        self.assertNotRegex(out, r"lock on main removed")
        self.assertRegex(out, r"(?i)no (merge )?lock|not found|does not exist|nothing to remove")

    def test_a_rate_limit_outlasting_the_retries_on_the_lock_commit_read_is_a_net_stop(self):  # item 2: red on 2cc181d
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
        self.assertEqual(self.pauses, [merge.RATE_WAIT_CAP] * 3)

    def test_a_network_error_outlasting_the_retries_on_the_lock_commit_read_is_a_net_stop(self):  # item 2: red on 2cc181d
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

    def test_a_rate_limit_on_the_lock_commit_read_never_reads_as_a_held_lock(self):  # item 2, the acquire path: red on 2cc181d
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

    def test_a_rate_wait_on_the_lock_path_prints_one_line_before_the_wait(self):  # item 3: red on 2cc181d
        self.reply("lock-commit-post", (1, RATE_API_403), self.OK["lock-commit-post"])
        buf, snapshots = io.StringIO(), []
        lock = merge.GhLock(now=lambda: self.NOW, pause=lambda s: snapshots.append(buf.getvalue()))
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            self.assertEqual(lock.acquire("main", 600), self.NEW)
        self.assertEqual(self.calls["lock-commit-post"], 2)
        assert_one_rate_wait_line(self, buf.getvalue(), snapshots)

    def test_a_clean_acquire_prints_no_wait_line(self):  # control: green on 2cc181d
        buf, snapshots = io.StringIO(), []
        lock = merge.GhLock(now=lambda: self.NOW, pause=lambda s: snapshots.append(buf.getvalue()))
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            self.assertEqual(lock.acquire("main", 600), self.NEW)
        self.assertEqual(snapshots, [])
        self.assertNotRegex(buf.getvalue(), r"(?i)\bwait")

class HostDefaultBranchRateRetry(unittest.TestCase):
    """host_default_branch (`gh repo view`) on a rate-limit error (lane merge-rate-limit, review round 1). It retries like Host.gh:
    RATE_WAIT_CAP per retry, three retries, then NetStop. The function has no pause parameter, so the pauses are recorded by
    patching merge.time.sleep. A fix must call time.sleep at call time, or this test sleeps for real."""
    def patched(self, *seq):
        """merge.sh answers `seq` in order (the last repeats). merge.time.sleep records. -> (gh calls, pauses)."""
        seq, calls, pauses = list(seq), [], []
        def fake(args, cwd=None, input=None, env=None):
            calls.append(args)
            return seq.pop(0) if len(seq) > 1 else seq[0]
        for target in ((merge, "sh", fake), (merge.time, "sleep", pauses.append)):
            p = unittest.mock.patch.object(*target)
            p.start(); self.addCleanup(p.stop)
        return calls, pauses

    def test_a_rate_limited_repo_view_is_retried_and_returns_the_default_branch(self):
        calls, pauses = self.patched((1, RATE_GQL_ALREADY), (0, '{"defaultBranchRef":{"name":"trunk"}}'))
        try:
            got = merge.host_default_branch("/repo")
        except merge.Stop as e:
            self.fail(f"host_default_branch stopped on a rate limit: {e}")
        self.assertEqual(got, "trunk")
        self.assertEqual((len(calls), pauses), (2, [merge.RATE_WAIT_CAP]))

    def test_a_rate_limit_that_never_clears_is_a_net_stop_after_three_retries(self):
        calls, pauses = self.patched((1, RATE_GQL_ALREADY))
        try:
            merge.host_default_branch("/repo")
        except merge.NetStop:
            pass
        except merge.Stop as e:
            self.fail(f"a rate limit that never clears stopped as a plain Stop, not a NetStop: {e}")
        else:
            self.fail("host_default_branch returned without a stop")
        self.assertEqual((len(calls), pauses), (4, [merge.RATE_WAIT_CAP] * 3))

    def test_a_permission_403_stops_at_once(self):  # guard: green on 8459b59
        calls, pauses = self.patched((1, PLAIN_403_API))
        with self.assertRaises(merge.Stop):
            merge.host_default_branch("/repo")
        self.assertEqual((len(calls), pauses), (1, []))

if __name__ == "__main__":
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
            return select_tests(super().loadTestsFromModule(*a, **k), os.environ.get("MERGE_TESTS", ""))
    unittest.main(testLoader=Slicer())
