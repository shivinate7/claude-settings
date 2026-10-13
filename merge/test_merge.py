#!/usr/bin/env python3
"""Fixture suite for merge/merge.py, the git and GitHub halves (plan lanes 3b, 4).

Run: python3 merge/test_merge.py
No network, no real repo. Every run uses a local bare origin in a temp dir, the real
actions/stamp/stamp.mjs, and a fake Host for the git half. The lock backend is
GitLock against that origin. GhLock and the GitHub half (Host) are covered with a fake `gh` on PATH.
"""
import contextlib, io, pathlib, json, os, re, shutil, socket, stat, subprocess, sys, tempfile, threading, time, unittest, unittest.mock

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
        self.base, self.base_seq = "main", None  # base_seq: one base per pr() read, the last one repeats
        self.waits, self.seq, self.state = [], None, "green"  # waits: (sha, prior) per call; seq: scripted results, then self.checks

    def pr(self, n):
        head = merge.origin_head(self.root, self.branch)
        base = (self.base_seq.pop(0) if len(self.base_seq) > 1 else self.base_seq[0]) if self.base_seq else self.base
        return {"head": self.head_override or head, "branch": self.branch, "base": base, "state": self.pr_state,
                "mergeable": self.mergeable, "merge_state": "CLEAN", "draft": False}

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
        self.lock = merge.GitLock(self.co, now=lambda: self.now)
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

    def test_the_lock_outlives_two_waits(self):
        ttls = []
        acquire = self.lock.acquire
        self.lock.acquire = lambda b, ttl: (ttls.append(ttl), acquire(b, ttl))[1]
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertGreaterEqual(ttls[0], (2 * CONFIG["merge"]["deadlineMinutes"] + 10) * 60)  # head wait, claim wait, ten spare

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

    def test_the_dirty_tree_message_names_the_checkout_path_it_checked(self):
        o = self.other  # same dirty-file setup as above: the merge changes first.md, which is dirty in the checkout
        sh(o, "git", "fetch", "-q", "origin"); sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        put(os.path.join(o, "docs/decisions/first.md"), record("D-001", "first") + "pr edit\n")
        sh(o, "git", "commit", "-qam", "pr edits first"); sh(o, "git", "push", "-q", "origin", "feat")
        put(os.path.join(self.co, "docs/decisions/first.md"), "my edit\n")
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)
        self.assertIn(os.path.realpath(self.co), out)  # the checkout that was checked, by path

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

    def test_the_tree_is_gone_at_the_base_check(self):
        self.host.on_wait = lambda: shutil.rmtree(os.path.dirname(self.merge_tree()))
        self.assert_clean_stop(*self.run_merge("7", "--confirm"))

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

    def test_the_config_is_gone_at_the_base_check(self):
        self.host.on_wait = lambda: self.base_loses(None)
        self.assert_base_lost(*self.run_merge("7", "--confirm"))

    def test_the_kinds_are_gone_at_the_base_check(self):
        self.host.on_wait = lambda: self.base_loses(json.dumps({k: v for k, v in CONFIG.items() if k != "kinds"}))
        self.assert_base_lost(*self.run_merge("7", "--confirm"))

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
        self.now += 21 * 60  # 2 * deadlineMinutes 5 + 10, passed
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
        self.assertIn(f"lock:   the merge lock on {self.BASE} is held", out)  # say() joins its lines with spaces

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
if a[:2] == ["pr", "view"]:
    if "headRefOid" in a[-1]:
        head = git("ls-remote", "origin", "refs/heads/feat").split("\t")[0]
        lag = S.get("lag")
        if lag and lag["n"] > 0 and head != lag["prior"]:  # GitHub still shows the head before the push
            lag["n"] -= 1; save(); head = lag["prior"]
        bad = S.get("dirty_after_checks") is not None and S["checks_calls"] >= S["dirty_after_checks"]
        views = S.get("views", 0) + 1; S["views"] = views; save()  # draft_from_view=N: read N and later ones see a draft
        draft = bool(S.get("draft")) or (S.get("draft_from_view") is not None and views >= S["draft_from_view"])
        print(json.dumps({"headRefOid": head, "headRefName": "feat", "baseRefName": S.get("base", "main"), "state": "OPEN",
                          "mergeable": "CONFLICTING" if bad else "MERGEABLE", "mergeStateStatus": "DIRTY" if bad else "CLEAN",
                          "isDraft": draft}))  # set draft=True in a test; false by default
    else:
        print(json.dumps({"state": "MERGED" if S.get("oid") else "OPEN", "mergeCommit": {"oid": S["oid"]} if S.get("oid") else None}))
elif a[:2] == ["pr", "checks"] and S.get("checks_broken") and S["checks_calls"] >= S.get("broken_from", 0):
    print("HTTP 500: server error"); sys.exit(1)
elif a[:2] == ["pr", "checks"]:
    seq = S["checks_seq"]; cur = seq.pop(0) if len(seq) > 1 else seq[0]; S["checks_calls"] += 1; save()
    print(json.dumps([{"name": n, "bucket": b, "link": l} for n, b, l in cur]))
    sys.exit(0 if all(b in ("pass", "skipping") for _, b, _ in cur) else 8)
elif a[:2] == ["run", "list"]:
    seq = S.get("runs_seq") or [[]]; cur = seq.pop(0) if len(seq) > 1 else seq[0]; save()
    print(json.dumps([{"name": n, "status": st, "conclusion": c} for n, st, c in cur]))
elif a[:2] == ["run", "watch"]:
    pass
elif a[:2] == ["pr", "merge"]:
    sha = a[a.index("--match-head-commit") + 1]
    if S.get("merge_fail"):
        print(S["merge_fail"]); sys.exit(1)
    if git("ls-remote", "origin", "refs/heads/feat").split("\t")[0] != sha:
        print("GraphQL: Head branch was modified. Review and try the merge again."); sys.exit(1)
    B = S.get("base", "main")
    git("fetch", "-q", "origin"); git("checkout", "-q", "-B", B, "origin/" + B)
    git("merge", "-q", "--no-ff", "-m", "merge", sha); git("push", "-q", "origin", B)
    S["oid"] = git("rev-parse", "HEAD"); save()
elif a[:2] == ["repo", "view"]:
    print(json.dumps({"defaultBranchRef": {"name": S.get("default_branch", "main")}}))
elif a[0] == "api" and a[1].endswith("/required_status_checks"):
    if S.get("contexts") is None:
        print("HTTP 404: Branch not protected"); sys.exit(1)
    print(json.dumps(S["contexts"]))
else:
    print("unhandled " + " ".join(a)); sys.exit(1)
"""

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

    def test_a_newest_cancelled_run_is_red_even_under_an_older_success(self):
        runs = [{"name": "gates", "status": "completed", "conclusion": "cancelled"}, {"name": "gates", "status": "completed", "conclusion": "success"}]
        red, pending = merge.Host.judge_runs(runs)
        self.assertEqual(red, ["workflow gates: cancelled"])
        self.assertEqual(pending, [])

    def test_a_cancelled_run_with_no_newer_run_of_its_name_is_red(self):
        runs = [{"name": "gates", "status": "completed", "conclusion": "success"}, {"name": "ci", "status": "completed", "conclusion": "cancelled"}]
        red, pending = merge.Host.judge_runs(runs)
        self.assertEqual(red, ["workflow ci: cancelled"])
        self.assertEqual(pending, [])

    # Incident 2026-10-13, PR 381: two gates runs started on one head in the same second. GitHub cancelled one (concurrency).
    # judge_runs must read the live twin, not the cancelled one, whatever the list order.
    def test_a_cancelled_twin_beside_a_live_run_of_its_name_waits_in_either_order(self):
        live = {"name": "gates", "status": "in_progress", "conclusion": ""}
        cancelled = {"name": "gates", "status": "completed", "conclusion": "cancelled"}
        for order, runs in (("cancelled first", [cancelled, live]), ("live first", [live, cancelled])):
            with self.subTest(order=order):
                self.assertEqual(merge.Host.judge_runs(runs), ([], ["workflow gates"]))

    def test_a_cancelled_twin_beside_a_live_run_that_succeeded_is_green_in_either_order(self):
        # The cancelled-first order has the same input as test_a_newest_cancelled_run_is_red_even_under_an_older_success,
        # which asserts red. Both cannot hold. Owner ruling needed before the build.
        success = {"name": "gates", "status": "completed", "conclusion": "success"}
        cancelled = {"name": "gates", "status": "completed", "conclusion": "cancelled"}
        for order, runs in (("cancelled first", [cancelled, success]), ("live first", [success, cancelled])):
            with self.subTest(order=order):
                self.assertEqual(merge.Host.judge_runs(runs), ([], []))

    def test_a_cancelled_twin_beside_a_live_run_that_failed_is_red_on_the_failure_in_either_order(self):
        failure = {"name": "gates", "status": "completed", "conclusion": "failure"}
        cancelled = {"name": "gates", "status": "completed", "conclusion": "cancelled"}
        for order, runs in (("cancelled first", [cancelled, failure]), ("live first", [failure, cancelled])):
            with self.subTest(order=order):
                self.assertEqual(merge.Host.judge_runs(runs), (["workflow gates: failure"], []))

    def test_a_newer_skipped_run_does_not_outrank_an_older_success_of_the_same_name(self):
        # Incident 2026-10-12, bin/merge 360: a draft PR marked ready in the same second. The skipped `opened` run is
        # newer than the green `ready_for_review` run of the same workflow. A skip never outranks a run that ran.
        runs = [{"name": "gates", "status": "completed", "conclusion": "skipped"}, {"name": "gates", "status": "completed", "conclusion": "success"}]
        self.assertEqual(merge.Host.judge_runs(runs), ([], []))

    def test_a_newer_skipped_run_does_not_hide_an_older_run_in_progress(self):
        runs = [{"name": "gates", "status": "completed", "conclusion": "skipped"}, {"name": "gates", "status": "in_progress", "conclusion": ""}]
        self.assertEqual(merge.Host.judge_runs(runs), ([], ["workflow gates"]))

    def test_a_newer_skipped_run_does_not_erase_an_older_cancelled_run(self):
        runs = [{"name": "gates", "status": "completed", "conclusion": "skipped"}, {"name": "gates", "status": "completed", "conclusion": "cancelled"}]
        self.assertEqual(merge.Host.judge_runs(runs), (["workflow gates: cancelled"], []))

    def test_a_newer_skipped_run_does_not_erase_an_older_failure(self):
        runs = [{"name": "gates", "status": "completed", "conclusion": "skipped"}, {"name": "gates", "status": "completed", "conclusion": "failure"}]
        self.assertEqual(merge.Host.judge_runs(runs), (["workflow gates: failure"], []))

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

    def test_a_draft_pr_is_refused_at_preview_before_any_claim_or_wait(self):
        self.set(draft=True)
        before = self.refs()
        rc, out = self.run_merge("7", host=self.gh_host())
        self.assert_draft_refused(rc, out, before)

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

    def test_ignoreChecks_null_stops_with_one_line_and_no_type_error(self):
        put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], ignoreChecks=None))))
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 1, out)
        lines = [l for l in out.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1, out)
        self.assertIn("ignoreChecks", lines[0])
        self.assertNotIn("TypeError", out)
        self.assertNotIn("Traceback", out)

    def one_merge_line(self, out):
        lines = [l for l in out.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1, out)
        self.assertTrue(lines[0].startswith("merge:"), out)
        self.assertNotIn("Traceback", out)
        return lines[0]

    def test_ignoreChecks_name_as_list_stops_with_one_line_and_no_type_error(self):
        put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], ignoreChecks=[{"name": ["gates"], "reason": "x"}]))))
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 1, out)
        self.assertIn("merge.ignoreChecks", self.one_merge_line(out))
        self.assertNotIn("TypeError", out)

    def test_ignoreChecks_reason_null_is_refused_like_an_empty_reason(self):
        put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], ignoreChecks=[{"name": "design", "reason": None}]))))
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 1, out)
        self.assertIn("merge.ignoreChecks", self.one_merge_line(out))

    def test_ignoreChecks_name_not_a_string_is_refused_like_a_missing_name(self):  # a check name is a string; 5 never matches one
        put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], ignoreChecks=[{"name": 5, "reason": "x"}]))))
        rc, out = self.run_merge("7")
        self.assertEqual(rc, 1, out)
        self.assertIn("merge.ignoreChecks", self.one_merge_line(out))

    def test_deadlineMinutes_must_be_a_positive_whole_number_at_preview(self):  # the file is refused at load, not at the lock
        for bad in ("45", True, 0, -5):
            with self.subTest(deadlineMinutes=bad):
                put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], deadlineMinutes=bad))))
                rc, out = self.run_merge("7")
                self.assertEqual(rc, 1, out)
                line = self.one_merge_line(out)
                self.assertIn("deadlineMinutes", line)
                self.assertIn(".github/stamp.json", line)

    def test_deadlineMinutes_as_a_string_stops_at_confirm_with_one_line_and_no_type_error(self):
        put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], deadlineMinutes="45"))))
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1, out)
        self.assertIn("deadlineMinutes", self.one_merge_line(out))
        self.assertNotIn("TypeError", out)
        self.assertFalse(self.lock_ref())

    def test_deadlineMinutes_over_the_360_cap_stops_with_one_line_at_preview_and_confirm(self):  # 360 is GitHub's longest job run
        for bad, label in ((361, "361"), (10 ** 400, "10**400")):
            put_base_config(self, json.dumps(dict(CONFIG, merge=dict(CONFIG["merge"], deadlineMinutes=bad))))
            for args in (("7",), ("7", "--confirm")):
                with self.subTest(deadlineMinutes=label, args=args):
                    rc, out = self.run_merge(*args)
                    self.assertEqual(rc, 1, out)
                    self.assertIn("deadlineMinutes", self.one_merge_line(out))
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

    def test_afterMerge_of_the_wrong_type_is_refused_at_preview(self):
        for bad in (None, 5, True, [1], [""]):
            with self.subTest(afterMerge=bad):
                self.refused_at_preview(self.config_text({"afterMerge": bad}), "afterMerge")

    def test_requiredChecks_of_the_wrong_shape_is_refused_at_preview(self):  # only "protection" or a non-empty list of non-empty strings
        for bad in ([["gates"]], [{}], [1, "gates"], [], "gates", [""]):
            with self.subTest(requiredChecks=bad):
                self.refused_at_preview(self.config_text({"requiredChecks": bad}), "requiredChecks")

    def test_deleteBranch_must_be_a_bool(self):
        for bad in ("false", 1):
            with self.subTest(deleteBranch=bad):
                self.refused_at_preview(self.config_text({"deleteBranch": bad}), "deleteBranch")

    def test_defaultBranch_must_be_a_non_empty_string(self):
        with unittest.mock.patch.object(merge, "host_default_branch", return_value="main"):  # "" must not fall back to the host
            for bad in (5, ""):
                with self.subTest(defaultBranch=bad):
                    self.refused_at_preview(self.config_text(defaultBranch=bad), "defaultBranch")

    def test_method_must_be_merge_squash_or_rebase(self):
        for bad in ("admin", "Squash"):
            with self.subTest(method=bad):
                self.refused_at_preview(self.config_text({"method": bad}), "method")

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

    def test_a_pid_too_big_for_the_os_reads_cannot_tell(self):
        self.garbled(pid=10 ** 12)

    def test_a_non_ascii_digit_pid_reads_cannot_tell(self):
        self.garbled(pid="²")

    def test_a_non_ascii_digit_started_reads_cannot_tell(self):
        self.garbled(started="²")

    def test_a_twenty_digit_started_reads_cannot_tell(self):
        self.garbled(started="1" * 20)

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
        return merge.GhLock(now=lambda: 1000.0), calls

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
