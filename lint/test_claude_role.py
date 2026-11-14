#!/usr/bin/env python3
"""Cases for bin/claude-role, the launcher of a local session's role (lane local-tier-file). Stdlib and unittest. POSIX only.

    python3 lint/test_claude_role.py

Each case puts a fake `claude` first on PATH. It writes the CS_SESSION_ROLE it was started with to a marker file, so a refused
role shows as no marker, and an accepted role shows as its name in the marker.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
LAUNCHER = os.path.join(REPO, "bin", "claude-role")
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

RUN_FOLDER = _test_temp.run_folder()


class ClaudeRoleLauncher(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="claude_role_cases_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.work, True)
        self.marker = os.path.join(self.work, "marker")
        fake = os.path.join(self.work, "fake-bin")
        os.makedirs(fake)
        claude = os.path.join(fake, "claude")
        with open(claude, "w", encoding="utf-8") as handle:
            handle.write('#!/bin/sh\nprintf "%s" "$CS_SESSION_ROLE" > "' + self.marker + '"\n')
        os.chmod(claude, 0o755)
        self.env = dict(os.environ, PATH=fake + os.pathsep + os.environ.get("PATH", ""), CLAUDE_CONFIG_DIR=self.work)
        self.env.pop("CS_SESSION_ROLE", None)

    def run_launcher(self, *args):
        return subprocess.run([sys.executable, LAUNCHER, *args], env=self.env, capture_output=True, text=True, timeout=60)

    def assert_refused(self, *args):
        answer = self.run_launcher(*args)
        self.assertEqual(answer.returncode, 2, "claude-role %r exits %d, want 2: %s" % (args, answer.returncode, answer.stderr))
        self.assertIn("usage", answer.stderr, "the refusal of claude-role %r names no usage" % (args,))
        self.assertFalse(os.path.exists(self.marker), "claude-role %r started claude" % (args,))

    def test_a_lane_is_refused_with_exit_2_and_claude_is_not_started(self):
        self.assert_refused("lane")

    def test_an_unknown_role_is_refused_with_exit_2_and_claude_is_not_started(self):
        self.assert_refused("boss")

    def test_no_role_is_refused_with_exit_2_and_claude_is_not_started(self):
        self.assert_refused()

    def test_a_listed_role_starts_claude_with_that_role(self):
        # Control: green on the built code. The refusals above would also hold for a launcher that never starts claude.
        for role in ("triage", "batch-runner", "coordinator"):
            with self.subTest(role=role):
                if os.path.exists(self.marker):
                    os.remove(self.marker)
                answer = self.run_launcher(role)
                self.assertEqual(answer.returncode, 0, "claude-role %s exits %d: %s" % (role, answer.returncode, answer.stderr))
                with open(self.marker, encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), role, "claude started without CS_SESSION_ROLE=%s" % role)


if __name__ == "__main__":
    unittest.main(verbosity=2)
