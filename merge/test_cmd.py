#!/usr/bin/env python3
"""Fixture suite for the launcher bin/merge.cmd (Windows) and bin/merge (elsewhere).

Run: python3 merge/test_cmd.py
Both launchers must behave the same: refuse a checkout with the wrong origin before any
pull request read, and pass every argument and the exit code of merge/launch.py through.
On Windows this runs bin/merge.cmd. On other systems it runs bin/merge, the shim that
merge.cmd starts. Plan: plans/shared-merge-tool.md. Never touches a real checkout.
"""
import os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://github.com/shivinate7/claude-settings"
LAUNCHER = [os.path.join(ROOT, "bin", "merge.cmd")] if os.name == "nt" else [sys.executable, os.path.join(ROOT, "bin", "merge")]

class Launcher(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="merge-cmd-")
        self.co = os.path.join(self.tmp, "co")
        os.makedirs(os.path.join(self.co, "merge"))
        subprocess.run(["git", "init", "-q", self.co], check=True)
        # A stub launch.py: prints its arguments, exits 7.
        with open(os.path.join(self.co, "merge", "launch.py"), "w") as f:
            f.write("import sys\nprint('ARGS', *sys.argv[1:])\nsys.exit(7)\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_launcher(self, *args):
        env = dict(os.environ, CLAUDE_SETTINGS_DIR=self.co)
        return subprocess.run(LAUNCHER + list(args), env=env, capture_output=True, text=True, timeout=60)

    def origin(self, url):
        subprocess.run(["git", "-C", self.co, "remote", "add", "origin", url], check=True)

    def test_wrong_origin_stops_before_any_run(self):
        self.origin("https://github.com/someone/else")
        r = self.run_launcher("12", "--confirm")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("is not a checkout of shivinate7/claude-settings", r.stderr)
        self.assertNotIn("ARGS", r.stdout)

    def test_arguments_and_exit_code_pass_through(self):
        self.origin(URL)
        r = self.run_launcher("12", "--confirm")
        self.assertEqual(r.returncode, 7, r.stdout + r.stderr)
        self.assertIn("ARGS", r.stdout)
        self.assertIn("12 --confirm", r.stdout)

if __name__ == "__main__":
    unittest.main()
