#!/usr/bin/env python3
"""Fixture test for bin/verdict. Run: python lint/test_verdict.py -v"""
import os, subprocess, sys, tempfile, unittest
V = os.environ.get("VERDICT_UNDER_TEST") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "verdict")

def run(code, log=None):
    env = dict(os.environ)
    env.pop("VERDICT_LOG", None)
    if log: env["VERDICT_LOG"] = log
    with tempfile.TemporaryDirectory() as d:
        script = os.path.join(d, "fx.py")
        open(script, "w").write(code)
        return subprocess.run([sys.executable, V, sys.executable, script], capture_output=True, text=True, env=env)

class T(unittest.TestCase):
    def test_pass(self):
        r = run("print('noisy')")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.startswith("PASS "))
        self.assertNotIn("noisy", r.stdout)

    def test_fail_line_excerpt_and_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "v.log")
            r = run("import sys\nprint('one')\nprint('FAIL boom')\nprint('err', file=sys.stderr)\nsys.exit(7)", log)
            self.assertEqual(r.returncode, 7)
            first = r.stdout.splitlines()[0]
            self.assertTrue(first.startswith("FAIL ") and " rc=7 " in first and f"log={log}" in first, first)
            self.assertIn("FAIL boom", r.stdout.splitlines()[1:])
            self.assertNotIn("one", r.stdout.splitlines()[1:])
            full = open(log).read()
            self.assertIn("one", full)
            self.assertIn("err", full)

    def test_tail_when_no_hot_line_and_cap(self):
        r = run("print('\\n'.join(f'l{i}' for i in range(100)))\nraise SystemExit(1)")
        body = r.stdout.splitlines()[1:]
        self.assertEqual(len(body), 30)
        self.assertEqual(body[-1], "l99")

    def test_reused_log_is_not_truncated(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "v.log")
            run("print('first-run')", log)
            run("print('second-run')", log)
            full = open(log).read()
            self.assertIn("first-run", full)
            self.assertIn("second-run", full)

    @unittest.skipIf(os.name == "nt", "POSIX signals")
    def test_signal_kill(self):
        r = run("import os, signal\nos.kill(os.getpid(), signal.SIGTERM)")
        self.assertEqual(r.returncode, 128 + 15)
        self.assertIn("killed by signal 15", r.stdout)

if __name__ == "__main__":
    unittest.main()
