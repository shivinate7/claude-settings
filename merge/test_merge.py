#!/usr/bin/env python3
"""Fixture suite for merge/merge.py, the git half (plan lane 3b).

Run: python3 merge/test_merge.py
No network, no real repo. Every run uses a local bare origin in a temp dir, the real
actions/stamp/stamp.mjs, and a fake Host (the GitHub half is lane 4). The lock backend is
GitLock against that origin. GhLock is covered with a fake `gh` on PATH.
"""
import contextlib, io, json, os, shutil, stat, subprocess, sys, tempfile, threading, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import merge  # noqa: E402

os.environ.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                  GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

def sh(cwd, *cmd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, (cmd, r.stdout, r.stderr)
    return r.stdout.strip()

def put(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)

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

    def pr(self, n):
        head = merge.origin_head(self.root, self.branch)
        return {"head": self.head_override or head, "branch": self.branch, "base": "main", "state": "OPEN",
                "mergeable": self.mergeable, "merge_state": "CLEAN"}

    def wait_checks(self, n, sha, d):
        if self.on_wait:
            self.on_wait()
        return self.checks

    def merge(self, n, method, sha):
        if self.refuse:
            return None, self.refuse
        o = self.other
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", "main", "origin/main")
        sh(o, "git", "merge", "-q", "--no-ff", "-m", f"merge #{n}", sha)
        sh(o, "git", "push", "-q", "origin", "main")
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

    def test_full_merge_claims_pushes_merges_syncs_cleans(self):
        mark = os.path.join(self.t, "after.txt")
        cfg = dict(CONFIG, merge=dict(CONFIG["merge"], afterMerge=[f"echo ran > {mark}"]))
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

    def test_local_main_moves_by_fetch_when_no_worktree_holds_it(self):
        sh(self.co, "git", "checkout", "-q", "-b", "side")
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertEqual(sh(self.co, "git", "rev-parse", "main"), sh(self.co, "git", "rev-parse", "origin/main"))
        self.assertEqual(sh(self.co, "git", "rev-parse", "--abbrev-ref", "HEAD"), "side")

    def test_dirty_main_tree_is_left_alone_and_the_merge_stays(self):
        put(os.path.join(self.co, "scratch.txt"), "x")
        sh(self.co, "git", "add", "scratch.txt")
        old = sh(self.co, "git", "rev-parse", "main")
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertIn("uncommitted", out)
        self.assertEqual(sh(self.co, "git", "rev-parse", "main"), old)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))

    def test_after_merge_failure_is_reported_and_the_merge_stays(self):
        sh(self.other, "git", "checkout", "-q", "main")
        cfg = dict(CONFIG, merge=dict(CONFIG["merge"], afterMerge=["exit 3"]))
        put(os.path.join(self.other, ".github/stamp.json"), json.dumps(cfg))
        sh(self.other, "git", "commit", "-qam", "cfg"); sh(self.other, "git", "push", "-q", "origin", "main")
        sh(self.co, "git", "pull", "-q", "--ff-only")
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertIn("FAILED (exit 3)", out)
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))

    def test_conflicting_pr_is_refused_before_any_claim(self):
        self.host.mergeable = "CONFLICTING"
        before = self.head()
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1)
        self.assertIn("CONFLICTING", out)
        self.assertEqual(self.head(), before)
        self.assertFalse(self.lock_ref())

    def test_config_without_merge_method_is_refused_never_guessed(self):
        sh(self.co, "git", "checkout", "-q", "main")
        cfg = dict(CONFIG, merge={"deadlineMinutes": 5})
        put(os.path.join(self.co, ".github/stamp.json"), json.dumps(cfg))
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1)
        self.assertIn("merge.method", out)
        self.assertFalse(self.lock_ref())

    def test_confirm_without_github_half_is_refused_before_the_lock(self):
        rc, out = self.run_merge("7", "--confirm", host=merge.Host())
        self.assertEqual(rc, 1)
        self.assertIn("lane 4", out)
        self.assertFalse(self.lock_ref())

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
        self.host.checks = (False, "required check `build` is red")
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 1)
        self.assertIn("`build` is red", out)
        self.assertIn("id: pending", self.show("feat", "docs/decisions/second.md"))
        self.assertEqual(self.claims("feat"), 1)  # the claim commit stays in history, reverted
        self.assertFalse(self.lock_ref())

    def test_red_check_after_a_push_in_the_wait_reverts_nothing(self):
        self.host.checks = (False, "red")
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
        self.now += 16 * 60  # deadlineMinutes 5 + 10, passed
        rc, out = self.run_merge("7", "--confirm")
        self.assertEqual(rc, 0, out)
        self.assertIn("resumed", out)
        self.assertEqual(self.claims(), 1)  # no second claim
        self.assertIn("id: D-002", self.show("main", "docs/decisions/second.md"))
        self.assertFalse(self.lock_ref())

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
        gh = os.path.join(bindir, "gh"); put(gh, FAKE_GH); os.chmod(gh, os.stat(gh).st_mode | stat.S_IXUSR)
        self.state = os.path.join(t, "state"); os.makedirs(self.state)
        old = {k: os.environ.get(k) for k in ("PATH", "FAKE_GH_DIR")}
        os.environ["PATH"] = bindir + os.pathsep + old["PATH"]; os.environ["FAKE_GH_DIR"] = self.state
        self.addCleanup(lambda: [os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None) for k, v in old.items()])
        self.now = 1000.0
        self.lock = merge.GhLock(now=lambda: self.now)

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

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        # A run that dies without cleanup: os._exit at the wait, so no `finally` runs.
        class Die(FakeHost):
            def wait_checks(self, n, sha, d):
                os._exit(9)
        os.chdir(sys.argv[2])
        sys.exit(merge.main(["7", "--confirm"], host=Die(sys.argv[2], None), lock=merge.GitLock(sys.argv[2])))
    unittest.main()
