#!/usr/bin/env python3
"""Fixture suite for bin/merge (lookup) and merge/launch.py (fresh-code guard).

Run: python3 merge/test_launch.py
Never touches the real ~/.claude or a real checkout. Every run uses temp dirs, a temp HOME, and
a temp global gitconfig whose insteadOf rewrite points the public repo URL at a local bare
repo. "Upstream" holds the real bin/merge and merge/launch.py plus a marker merge.py, so the
suite proves the code in this repo, and a mutant of either file goes red.
"""
from pathlib import Path
import os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://github.com/shivinate7/claude-settings"

def put(path, text):
    with open(path, "w") as f:
        f.write(text)

def sh(cwd, *cmd, env=None):
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (cmd, r.stdout, r.stderr)
    return r.stdout.strip()

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
        os.makedirs(os.path.join(self.work, "merge"))
        for f in ("bin/merge", "merge/launch.py"):
            shutil.copy(os.path.join(ROOT, f), os.path.join(self.work, f))
        put(os.path.join(self.work, "notes.txt"), "clean\n")
        self.release("v1")
        sh(self.work, "git", "remote", "add", "origin", self.bare, env=self.env)
        sh(self.work, "git", "push", "-q", "origin", "main", env=self.env)
        self.co = self.clone("co")

    def rewrite(self, target):
        # Git's config parser treats `\` as an escape inside a quoted section name, so a raw
        # Windows path here drops every backslash (`C:\Users\x` -> `C:Usersx`) and every clone
        # in the suite fails to resolve. Forward slashes parse the same on both OSes and need no
        # escaping.
        put(self.cfg, f'[user]\n\tname = t\n\temail = t@t\n[url "{target.replace(os.sep, "/")}"]\n\tinsteadOf = {URL}\n')

    def release(self, tag):
        # The stub prints its tag and, when ARGS_FILE is set, records the arguments it received.
        put(os.path.join(self.work, "merge", "merge.py"), "import os, sys\nprint('RAN %s')\n"
            "f = os.environ.get('ARGS_FILE')\nif f: open(f, 'w').write(repr(sys.argv[1:]))\n" % tag)
        sh(self.work, "git", "add", "-A", env=self.env)
        sh(self.work, "git", "commit", "-q", "-m", tag, env=self.env)
        if tag != "v1":
            sh(self.work, "git", "push", "-q", "origin", "main", env=self.env)

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

if __name__ == "__main__":
    unittest.main()
