#!/usr/bin/env python3
"""Fixture suite for bin/merge (lookup) and merge/launch.py (fresh-code guard).

Run: python3 merge/test_launch.py
Never touches the real ~/.claude or a real checkout. Every run uses temp dirs, a temp HOME, and
a temp global gitconfig whose insteadOf rewrite points the public repo URL at a local bare
repo. "Upstream" holds the real bin/merge and merge/launch.py plus a marker merge.py, so the
suite proves the code in this repo, and a mutant of either file goes red.
"""
from pathlib import Path
import os, shutil, signal, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)
from proc_fixture import alive, kill_all, stop_group, wait_for, wait_gone  # noqa: E402  the one home of the signal-test helpers (testing/proc_fixture.py)
sys.path.insert(0, os.path.join(ROOT, "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
URL = "https://github.com/shivinate7/claude-settings"

def put(path, text):
    with open(path, "w") as f:
        f.write(text)

def sh(cwd, *cmd, env=None):
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (cmd, r.stdout, r.stderr)
    return r.stdout.strip()

# A stub merge.py that writes its pid and its parent's pid (the launcher's) to READY_FILE, then blocks until the test closes its stdin.
BLOCK = ("import os, sys\n"
         "tmp = os.environ['READY_FILE'] + '.tmp'\n"
         "open(tmp, 'w').write('%d %d' % (os.getpid(), os.getppid()))\n"
         "os.replace(tmp, os.environ['READY_FILE'])\n"
         "sys.stdin.read()\n")
# A stub merge.py that writes its parent's pid, then `git worktree list --porcelain` of its own tree, to LOCK_FILE.
LOCK_STUB = ("import os, subprocess\n"
             "here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n"
             "listing = subprocess.run(['git', '-C', here, 'worktree', 'list', '--porcelain'], capture_output=True, text=True).stdout\n"
             "open(os.environ['LOCK_FILE'], 'w').write('%d\\n%s' % (os.getppid(), listing))\n")

def worktrees(listing):
    """{real path: lock reason, or None when the tree is not locked} from `git worktree list --porcelain`."""
    trees, path = {}, None
    for line in listing.splitlines():
        if line.startswith("worktree "):
            path = os.path.realpath(line[len("worktree "):])
            trees[path] = None
        elif line == "locked" or line.startswith("locked "):
            trees[path] = line[len("locked"):].strip()
    return trees

class Launch(unittest.TestCase):
    def setUp(self):
        self.t = os.path.realpath(tempfile.mkdtemp(prefix="test-launch-"))
        self.addCleanup(shutil.rmtree, self.t, True)
        self.bare = os.path.join(self.t, "up.git")
        self.cfg = os.path.join(self.t, "gitconfig")
        self.home = os.path.join(self.t, "home")
        os.makedirs(self.home)
        self.tmp = os.path.join(self.t, "tmp")  # TMPDIR for the code under test: must be empty after a run
        os.makedirs(self.tmp)
        self.rewrite(self.bare)
        self.env = {**os.environ, "GIT_CONFIG_GLOBAL": self.cfg, "GIT_CONFIG_SYSTEM": os.devnull,
                    "HOME": self.home, "TMPDIR": self.tmp, "TMP": self.tmp, "TEMP": self.tmp, "USERPROFILE": self.home, "CLAUDE_CONFIG_DIR": os.path.join(self.t, "cfg")}
        for k in ("CLAUDE_SETTINGS_DIR",):
            self.env.pop(k, None)
        sh(self.t, "git", "init", "-q", "--bare", "-b", "main", self.bare, env=self.env)
        self.work = os.path.join(self.t, "work")
        sh(self.t, "git", "init", "-q", "-b", "main", self.work, env=self.env)
        os.makedirs(os.path.join(self.work, "bin"))
        shutil.copy(os.path.join(ROOT, "bin", "merge"), os.path.join(self.work, "bin", "merge"))
        tracked_tree.copy_tracked(self.work, "merge", "hooks")  # launch.py and its imports from hooks/
        # Same ignore rules as the real repo. launch.py imports the helper from the clone's hooks/, and
        # that import writes hooks/__pycache__ when bytecode is on (CI), which would read as a dirty tree.
        put(os.path.join(self.work, ".gitignore"), "__pycache__/\n*.pyc\n")
        put(os.path.join(self.work, "notes.txt"), "clean\n")
        self.release("v1")
        sh(self.work, "git", "remote", "add", "origin", self.bare, env=self.env)
        sh(self.work, "git", "push", "-q", "origin", "main", env=self.env)
        sh(self.work, "git", "push", "-q", "origin", "main:refs/heads/stable", env=self.env)
        self.co = self.clone("co")

    def rewrite(self, target):
        # Git's config parser treats `\` as an escape inside a quoted section name, so a raw
        # Windows path here drops every backslash (`C:\Users\x` -> `C:Usersx`) and every clone
        # in the suite fails to resolve. Forward slashes parse the same on both OSes and need no
        # escaping.
        # Signing is on, as in a real checkout, so the import above is what keeps these commits off the signer.
        put(self.cfg, f'[user]\n\tname = t\n\temail = t@t\n[commit]\n\tgpgsign = true\n[tag]\n\tgpgsign = true\n[url "{target.replace(os.sep, "/")}"]\n\tinsteadOf = {URL}\n')

    def release(self, tag, stable=True, body=None):
        # The stub prints its tag and, when ARGS_FILE is set, records the arguments it received.
        # stable=True moves origin's stable with main, so a case that expects the released tag still
        # checks the head the launcher fetches; stable=False leaves stable where it was.
        text = "import os, sys\nprint('RAN %s')\n" "f = os.environ.get('ARGS_FILE')\nif f: open(f, 'w').write(repr(sys.argv[1:]))\n" % tag
        put(os.path.join(self.work, "merge", "merge.py"), text if body is None else body)  # body: a stub a case needs instead
        sh(self.work, "git", "add", "-A", env=self.env)
        sh(self.work, "git", "commit", "-q", "-m", tag, env=self.env)
        if tag != "v1":
            sh(self.work, "git", "push", "-q", "origin", "main", env=self.env)
            if stable:
                sh(self.work, "git", "push", "-q", "origin", "main:refs/heads/stable", env=self.env)

    def clone(self, name):
        d = os.path.join(self.t, name)
        sh(self.t, "git", "clone", "-q", URL, d, env=self.env)
        return d

    def merge(self, *args, **env):
        e = {**self.env, **env}
        e.setdefault("CLAUDE_SETTINGS_DIR", self.co)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "merge"), *args], env=e,
                           capture_output=True, text=True, timeout=120)
        return r.returncode, r.stdout, r.stderr

    def head(self, d):
        return sh(d, "git", "rev-parse", "HEAD", env=self.env)

    # ---- lookup sources ------------------------------------------------------------------
    def test_env_var_wins_over_include(self):
        self.release("v2")
        os.makedirs(self.env["CLAUDE_CONFIG_DIR"])
        put(os.path.join(self.env["CLAUDE_CONFIG_DIR"], "CLAUDE.md"), "@/nowhere/CLAUDE.md\n")
        rc, out, err = self.merge()
        self.assertEqual((rc, out.strip()), (0, "RAN v2"), err)

    def test_include_line_with_tilde(self):
        os.makedirs(self.env["CLAUDE_CONFIG_DIR"])
        # tilde form, as install.sh writes it for a clone under HOME
        under_home = os.path.join(self.home, "co")
        shutil.move(self.co, under_home)
        self.co = under_home
        put(os.path.join(self.env["CLAUDE_CONFIG_DIR"], "CLAUDE.md"), "@~/co/CLAUDE.md\n")
        put(os.path.join(self.co, "merge", "merge.py"), "print('RAN local')\n")  # a fresh clone could not print this
        e = {k: v for k, v in self.env.items() if k != "CLAUDE_SETTINGS_DIR"}
        r = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "merge"), "--dev"], env=e, capture_output=True, text=True, timeout=120)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "RAN local"), r.stderr)

    def test_no_checkout_clones_public_repo(self):
        e = {k: v for k, v in self.env.items() if k != "CLAUDE_SETTINGS_DIR"}  # no include file either
        r = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "merge")], env=e, capture_output=True, text=True, timeout=120)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "RAN v1"), r.stderr)

    def test_wrong_origin_stops_before_any_run(self):
        sh(self.co, "git", "remote", "set-url", "origin", "https://github.com/someone/else", env=self.env)
        rc, out, err = self.merge()
        self.assertNotEqual(rc, 0)
        self.assertNotIn("RAN", out)
        self.assertIn("stopped before any PR read", err)

    # ---- fresh-code guard ----------------------------------------------------------------
    def test_runs_origin_main_not_the_checkout(self):
        self.release("v2")
        rc, out, err = self.merge()
        self.assertEqual((rc, out.strip()), (0, "RAN v2"), err)
        self.assertIn(self.head(self.work)[:12], err)  # prints the SHA it ran
        self.assertNotIn("WARNING", err)

    def test_runs_origin_stable_not_main(self):
        # The launcher runs the stable branch, the commit sessions install from (restart-plan R42 part 2).
        v1 = self.head(self.work)  # setUp pushed stable at v1
        self.release("v2", stable=False)  # main moves on; stable stays at v1
        self.assertEqual(sh(self.bare, "git", "rev-parse", "refs/heads/stable"), v1, "FIXTURE stable is not v1")
        rc, out, err = self.merge()
        self.assertEqual((rc, out.strip()), (0, "RAN v1"), err)
        self.assertIn(v1[:12], err)  # prints the SHA of stable it ran

    def drop_stable(self):
        """Origin holds no stable branch. Returns after proving it: the launcher's fetch of stable finds no ref."""
        sh(self.bare, "git", "update-ref", "-d", "refs/heads/stable", env=self.env)
        probe = subprocess.run(["git", "rev-parse", "-q", "--verify", "refs/heads/stable"], cwd=self.bare,
                               env=self.env, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(probe.returncode, 0, "FIXTURE origin still has a stable branch")

    def test_no_stable_runs_origin_main_not_the_checkout(self):
        # With no stable branch on origin, the launcher runs origin's main, not the checkout's own tree.
        # The checkout is still at v1 here, so the run must print RAN v2.
        self.drop_stable()
        self.release("v2", stable=False)
        rc, out, err = self.merge()
        self.assertEqual((rc, out.strip()), (0, "RAN v2"), err)

    def test_no_stable_warns_and_names_stable(self):
        # The fallback is never silent: one warning names stable.
        self.drop_stable()
        self.release("v2", stable=False)
        rc, out, err = self.merge()
        named = [line for line in err.splitlines() if "stable" in line]
        self.assertEqual(len(named), 1, "want one warning line naming stable, got %r" % err)

    def test_ref_main_runs_origin_main_not_stable_and_warns_nothing(self):
        # CLAUDE_SETTINGS_REF=main, the recovery, runs origin's main with no WARN, even while origin's stable sits behind it.
        v1 = self.head(self.work)  # setUp pushed stable at v1
        self.release("v2", stable=False)  # main moves on to v2; stable stays at v1
        self.assertEqual(sh(self.bare, "git", "rev-parse", "refs/heads/stable"), v1, "FIXTURE stable is not v1")
        self.assertNotEqual(self.head(self.work), v1, "FIXTURE main is not past stable")
        rc, out, err = self.merge(CLAUDE_SETTINGS_REF="main")
        self.assertEqual((rc, out.strip()), (0, "RAN v2"), err)
        self.assertNotIn("WARN", err)

    def test_dirty_checkout_untouched(self):
        self.release("v2")
        before = self.head(self.co)
        put(os.path.join(self.co, "notes.txt"), "my edit\n")
        rc, out, err = self.merge()
        self.assertEqual((rc, out.strip()), (0, "RAN v2"), err)
        self.assertEqual(self.head(self.co), before)
        self.assertEqual(Path(os.path.join(self.co, "notes.txt")).read_text(), "my edit\n")
        self.assertIn("dirty tree", err)

    def test_clean_main_behind_fast_forwards(self):
        self.release("v2")
        self.merge()
        self.assertEqual(self.head(self.co), self.head(self.work))

    def test_cloud_mirror_on_main_behind_is_not_fast_forwarded(self):
        self.release("v2")
        sh(self.co, "git", "config", "claude-settings.cloudMirror", "true", env=self.env)
        # Scope first: the marker reads back and the checkout is on main, clean and behind.
        self.assertEqual(sh(self.co, "git", "config", "--get", "claude-settings.cloudMirror", env=self.env), "true")
        self.assertEqual(sh(self.co, "git", "rev-parse", "--abbrev-ref", "HEAD", env=self.env), "main")
        self.assertEqual(sh(self.co, "git", "status", "--porcelain", env=self.env), "", "fixture: checkout tree is dirty")
        self.assertNotEqual(self.head(self.co), self.head(self.work), "fixture: checkout is not behind origin/main")
        before = self.head(self.co)
        rc, out, err = self.merge()
        self.assertEqual((rc, out.strip()), (0, "RAN v2"), err)
        self.assertEqual(self.head(self.co), before, "cloud mirror was fast-forwarded")
        lines = [ln for ln in err.splitlines() if "left as is" in ln]
        self.assertEqual(len(lines), 1, "expected one 'left as is' stderr line:\n" + err)
        self.assertIn("cloud mirror", lines[0])

    def test_cloud_mirror_false_still_fast_forwards(self):
        self.release("v2")
        sh(self.co, "git", "config", "claude-settings.cloudMirror", "false", env=self.env)
        self.assertEqual(sh(self.co, "git", "config", "--get", "claude-settings.cloudMirror", env=self.env), "false")
        rc, out, err = self.merge()
        self.assertEqual((rc, out.strip()), (0, "RAN v2"), err)
        self.assertEqual(self.head(self.co), self.head(self.work), "checkout marked false was not fast-forwarded")
        self.assertNotIn("left as is", err, "checkout marked false was left as is")

    def test_clean_other_branch_left_alone(self):
        self.release("v2")
        sh(self.co, "git", "checkout", "-q", "-b", "topic", env=self.env)
        before = self.head(self.co)
        rc, out, err = self.merge()
        self.assertEqual((rc, out.strip()), (0, "RAN v2"), err)
        self.assertEqual(self.head(self.co), before)
        self.assertIn("not on main", err)

    def test_temp_worktree_removed(self):
        self.release("v2")
        self.merge()
        self.assertEqual(len(sh(self.co, "git", "worktree", "list", env=self.env).splitlines()), 1)
        self.assertEqual(os.listdir(self.tmp), [])

    def test_temp_clone_removed_after_run_and_after_failed_clone(self):
        e = {k: v for k, v in self.env.items() if k != "CLAUDE_SETTINGS_DIR"}
        r = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "merge")], env=e, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.stdout.strip(), "RAN v1", r.stderr)
        self.assertEqual(os.listdir(self.tmp), [])
        self.rewrite(os.path.join(self.t, "gone.git"))
        r = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "merge")], env=e, capture_output=True, text=True, timeout=120)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(os.listdir(self.tmp), [])

    def test_offline_warns_and_runs_the_code_it_has(self):
        self.rewrite(os.path.join(self.t, "gone.git"))
        before = self.head(self.co)
        rc, out, err = self.merge()
        self.assertEqual((rc, out.strip()), (0, "RAN v1"), err)
        self.assertIn("WARNING", err)
        self.assertIn(before[:12], err)
        self.assertIn("fetch of origin main failed", err)

    def test_offline_after_earlier_fetch_names_distance(self):
        self.release("v2")
        sh(self.co, "git", "fetch", "-q", "origin", env=self.env)
        self.rewrite(os.path.join(self.t, "gone.git"))
        rc, out, err = self.merge()
        self.assertEqual(out.strip(), "RAN v1")
        self.assertIn("1 commit(s) behind origin/main as of the last fetch", err)

    def test_dev_runs_own_tree_and_does_not_fetch(self):
        self.release("v2")
        before = self.head(self.co)
        rc, out, err = self.merge("--dev")
        self.assertEqual((rc, out.strip()), (0, "RAN v1"), err)
        self.assertEqual(self.head(self.co), before)
        self.assertIn("--dev", err)

    def test_dev_is_not_forwarded_and_other_args_are(self):
        rec = os.path.join(self.t, "args.txt")
        rc, out, err = self.merge("--dev", "7", "--confirm", ARGS_FILE=rec)
        self.assertEqual(rc, 0, err)
        self.assertEqual(open(rec).read(), repr(["7", "--confirm"]))

    def test_checkout_that_cannot_fast_forward_is_left_as_is_and_still_runs_fresh(self):
        self.release("v2")
        put(os.path.join(self.co, "local.txt"), "local only\n")
        sh(self.co, "git", "add", "-A", env=self.env)
        sh(self.co, "git", "commit", "-q", "-m", "local", env=self.env)
        before = self.head(self.co)  # diverged from origin/main: only a merge commit could join them
        rc, out, err = self.merge()
        self.assertEqual((rc, out.strip()), (0, "RAN v2"), err)
        self.assertEqual(self.head(self.co), before)
        self.assertIn("ff-only merge refused", err)

    # ---- a run that a signal ends --------------------------------------------------------
    def fresh_trees(self):
        """The merge-fresh folders in this test's temp folder."""
        return sorted(n for n in os.listdir(self.tmp) if n.startswith("merge-fresh-"))

    def start_blocked_run(self, name):
        """bin/merge started on the BLOCK stub. -> (the Popen, the ready file). The run gets its own process group, so a
        cleanup reaches every process it started, and its stub reads to EOF, so closing stdin ends it."""
        ready = os.path.join(self.t, name + ".ready")
        err = open(os.path.join(self.t, name + ".err"), "w", encoding="utf-8")
        self.addCleanup(err.close)
        e = {**self.env, "CLAUDE_SETTINGS_DIR": self.co, "READY_FILE": ready}
        proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "bin", "merge")], env=e, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=err, start_new_session=True)
        self.addCleanup(self.stop_run, proc)
        return proc, ready

    @staticmethod
    def stop_run(proc):
        try:
            proc.stdin.close()
        except OSError:
            pass
        stop_group(proc)

    def await_exit(self, proc, what):
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            self.fail("%s did not exit within 60 s" % what)

    def test_sigterm_removes_fresh_tree(self):
        """A TERM or HUP sent to bin/merge alone ends the run, and the run takes its fresh tree and its registration with it."""
        self.release("v2", body=BLOCK)
        for sig in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=sig.name):
                before = self.fresh_trees()
                proc, ready = self.start_blocked_run(sig.name)
                self.assertTrue(wait_for(ready, 60, proc), "the stub never started")
                fresh = [n for n in self.fresh_trees() if n not in before]
                self.assertEqual(len(fresh), 1, "scope: one merge-fresh folder must exist while the run is up, got %r" % fresh)
                proc.send_signal(sig)
                self.await_exit(proc, "bin/merge after %s" % sig.name)
                left = [n for n in self.fresh_trees() if n not in before]
                self.assertEqual(left, [], "%s to bin/merge left its fresh tree behind" % sig.name)
                registered = sh(self.co, "git", "worktree", "list", "--porcelain", env=self.env).count("worktree ")
                self.assertEqual(registered, 1, "%s to bin/merge left a worktree registered in the checkout" % sig.name)

    def test_sigterm_forwards_to_child(self):
        """A TERM or HUP sent to bin/merge alone reaches the stub that the launcher runs, which is gone when bin/merge returns."""
        self.release("v2", body=BLOCK)
        for sig in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=sig.name):
                proc, ready = self.start_blocked_run(sig.name)
                self.assertTrue(wait_for(ready, 60, proc), "the stub never started")
                with open(ready, encoding="utf-8") as f:
                    child = int(f.read().split()[0])
                self.assertTrue(alive(child), "scope: the stub must run before %s" % sig.name)
                proc.send_signal(sig)
                self.await_exit(proc, "bin/merge after %s" % sig.name)
                self.assertFalse(alive(child), "%s to bin/merge did not reach the stub %d, which runs after bin/merge returned"
                                 % (sig.name, child))

    def start_killed_run(self, name):
        """bin/merge started on the BLOCK stub, with a KILL sent to its group. -> (launcher pid, stub pid). Both are killed at cleanup,
        so a red run leaves no process behind. The KILL is the one signal no handler sees: only the group reaches a child."""
        self.release("v2", body=BLOCK)
        proc, ready = self.start_blocked_run(name)
        self.assertTrue(wait_for(ready, 60, proc), "the stub never started")
        with open(ready, encoding="utf-8") as f:
            stub, launcher = (int(x) for x in f.read().split())
        self.addCleanup(kill_all, [stub, launcher])
        self.assertTrue(alive(launcher) and alive(stub), "scope: the launcher and the stub must run before the KILL")
        os.killpg(proc.pid, signal.SIGKILL)
        self.await_exit(proc, "bin/merge after a KILL to its group")
        return launcher, stub

    def test_sigkill_to_bin_merge_group_ends_the_launcher(self):
        launcher, _ = self.start_killed_run("kill-launcher")
        self.assertTrue(wait_gone(launcher, 30), "a KILL to the group of bin/merge did not end the launcher %d, which runs beside it" % launcher)

    def test_sigkill_to_bin_merge_group_ends_the_stub(self):
        _, stub = self.start_killed_run("kill-stub")
        self.assertTrue(wait_gone(stub, 30), "a KILL to the group of bin/merge did not end the stub %d, which runs after bin/merge is gone" % stub)

    def test_fresh_tree_is_locked_with_the_launcher_pid(self):
        """The fresh tree is locked while the run uses it, with the reason `merge tool, pid N`, where N is the launcher's pid,
        so a sweep that finds the tree after a dead run can tell whose it is."""
        lock_file = os.path.join(self.t, "lock.txt")
        self.release("v2", body=LOCK_STUB)
        rc, out, err = self.merge(LOCK_FILE=lock_file)
        self.assertEqual(rc, 0, err)
        with open(lock_file, encoding="utf-8") as f:
            launcher, listing = f.read().split("\n", 1)
        fresh = [p for p in worktrees(listing) if p.startswith(os.path.realpath(self.tmp) + os.sep)]
        self.assertEqual(len(fresh), 1, "scope: one fresh tree must be registered while the run is up:\n" + listing)
        reason = worktrees(listing)[fresh[0]]
        self.assertEqual(reason, "merge tool, pid %s" % launcher, "the fresh tree must be locked with the launcher's pid, got %r" % reason)

if __name__ == "__main__":
    unittest.main()
