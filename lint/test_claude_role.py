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


CMD = os.path.join(REPO, "bin", "claude-role.cmd")


def cmd_code_lines(text):
    """The code lines of a .cmd file's text, stripped, in order. A comment line (`rem` or `::`, after any `@`) is no code, so a comment
    that names WindowsApps is no skip. Any line ending splits the text, so CRLF and LF read alike."""
    lines = []
    for line in text.splitlines():
        body = line.strip().lstrip("@").strip()
        lowered = body.lower()
        if not body or lowered.startswith("::") or lowered == "rem" or lowered.startswith("rem "):
            continue
        lines.append(body)
    return lines


def first_line_with(lines, needle):
    """The index of the first code line that names `needle`, ignoring case, else None."""
    for at, line in enumerate(lines):
        if needle.lower() in line.lower():
            return at
    return None


class ClaudeRoleCmdText(unittest.TestCase):
    """The Windows launcher's text, bin/claude-role.cmd. Static: it reads the file and never runs it. Each assert names one cause."""

    def setUp(self):
        with open(CMD, encoding="utf-8") as handle:
            self.lines = cmd_code_lines(handle.read())

    def test_the_cmd_skips_the_windowsapps_python_alias_before_it_launches_claude_role(self):
        launch = first_line_with(self.lines, "%~dp0claude-role")
        self.assertIsNotNone(launch, "bin/claude-role.cmd has no code line that launches claude-role")
        skip = first_line_with(self.lines, "windowsapps")
        self.assertIsNotNone(skip, "bin/claude-role.cmd names no WindowsApps path on a code line, so `where python` can return the "
                                   "WindowsApps alias, which exits 9009 and never starts claude")
        self.assertLess(skip, launch, "bin/claude-role.cmd filters WindowsApps only after its first launch, so the alias runs first")

    def test_the_py_3_fallback_comes_after_the_windowsapps_filter(self):
        py = first_line_with(self.lines, "py -3")
        self.assertIsNotNone(py, "bin/claude-role.cmd has no `py -3` fallback line for a machine with no other python")
        skip = first_line_with(self.lines, "windowsapps")
        self.assertIsNotNone(skip, "bin/claude-role.cmd names no WindowsApps path on a code line, so no fallback follows a filter")
        self.assertLess(skip, py, "bin/claude-role.cmd reaches its `py -3` fallback before the WindowsApps filter")

    def test_the_scanner_reads_code_lines_and_skips_comment_lines(self):
        # Scanner controls, green on the old code. A comment that names WindowsApps is no skip. A code line that names it is found,
        # including one with a comment-looking word inside quotes and one with a lone quote, so a miss below is the file's, not the reader's.
        for text in ("rem skip WindowsApps paths\r\n", ":: skip WindowsApps paths\r\n", "@rem WindowsApps\r\n"):
            with self.subTest(comment=text):
                self.assertIsNone(first_line_with(cmd_code_lines(text), "windowsapps"),
                                  "a comment line that names WindowsApps is read as a code line, so it counts as the skip")
        for text in ("for /f %%P in ('where python') do @echo %%P | findstr /v WindowsApps\r\n",
                     'echo "rem WindowsApps"\r\n', "echo it's WindowsApps\r\n"):
            with self.subTest(code=text):
                self.assertEqual(first_line_with(cmd_code_lines(text), "windowsapps"), 0,
                                 "a code line that names WindowsApps is not read as code")


if __name__ == "__main__":
    unittest.main(verbosity=2)
