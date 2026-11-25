#!/usr/bin/env python3
"""Cases for lint/check_tool_pins.py. Standard library only.

    python3 lint/test_check_tool_pins.py

A root `.tool-versions` file holds one line per tool: `<tool> <version>`. The check runs each tool's version
command and compares the first dotted number in its output to the pin, at the precision the pin states.
A pin's comment sits on its own line. `# read: <tool> = <command>` names a version command other than
`<tool> --version`. Each repo owns its own file; with no `--file`, the check reads the root of the repo it runs in.

Each case writes its own `.tool-versions`, puts fake tools first on PATH, then runs the checker by path in a
subprocess. The cases assert on its exit code and its output. While the checker is absent, every case that
expects a verdict fails on its exit-code or output assert, never on an import error.
"""
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

CHECK = os.path.join(HERE, "check_tool_pins.py")
RUN_TIMEOUT = 60  # a hang guard well above a run of a few process starts
GIT_MISMATCH = "tool-pins: git pinned 2.56, found 2.54.0; move the pin or the tool"
APPLE_GIT = "git version 2.54.0 (Apple Git-155)"
WINDOWS_GIT_256 = "git version 2.56.1.windows.1"
# actions/setup-python reads .tool-versions with the JS form of this pattern, which names its group <version>.
# Python spells the same named group (?P<version>...).
SETUP_PYTHON_PIN = re.compile(r"^\s*python\s*v?\s*(?P<version>[^\s]+)\s*$")
RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


class ToolPinsCase(unittest.TestCase):
    """One case's folder under the run folder: a bin/ of fake tools, a log of their runs, and the pin files."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.bin = os.path.join(self.dir, "bin")
        self.log = os.path.join(self.dir, "invoked.log")

    def fake(self, name, output):
        """A fake tool on PATH. Each run appends its name to the log, then prints `output`."""
        os.makedirs(self.bin, exist_ok=True)
        if os.name == "nt":
            path = os.path.join(self.bin, name + ".cmd")
            body = '@echo off\r\necho %s>>"%s"\r\necho %s\r\n' % (name, self.log, output)
        else:
            path = os.path.join(self.bin, name)
            body = "#!/bin/sh\necho %s >> %s\necho %s\n" % (shlex.quote(name), shlex.quote(self.log), shlex.quote(output))
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        os.chmod(path, 0o755)

    def write(self, text, name=".tool-versions"):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return path

    def invoked(self):
        """The names of the fake tools that ran, in log order. Empty when none ran or the log is absent."""
        try:
            with open(self.log, encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]
        except OSError:
            return []

    def tool_env(self, extra=None):
        env = dict(os.environ)
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "CI", "GITHUB_ACTIONS"):
            env.pop(key, None)
        env["PATH"] = self.bin + os.pathsep + os.environ.get("PATH", "")
        env.update(extra or {})
        return env

    def run_check(self, *args, extra_env=None, cwd=None):
        """Run the checker by path. Returns (exit code, stdout and stderr together)."""
        try:
            proc = subprocess.run(
                [sys.executable, CHECK, *args], cwd=cwd or self.dir, env=self.tool_env(extra_env),
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=RUN_TIMEOUT)
        except subprocess.TimeoutExpired:
            self.fail("check_tool_pins.py ran past %d s: a hang, not a verdict" % RUN_TIMEOUT)
        return proc.returncode, proc.stdout + proc.stderr


class ControlTests(ToolPinsCase):
    """Green on the old code: the fake-tool harness that every verdict case relies on."""

    @unittest.skipIf(os.name == "nt", "the fake tool is a sh script here; the Windows fake is a .cmd that only a shell runs")
    def test_control_a_fake_tool_prints_its_output_and_logs_its_run(self):
        self.fake("pinprobe", "pinprobe 4.2.7")
        proc = subprocess.run(["pinprobe", "--version"], env=self.tool_env(), capture_output=True, text=True)
        self.assertEqual(proc.stdout.strip(), "pinprobe 4.2.7", "the harness must print the fake's output: %r" % proc.stdout)
        self.assertEqual(self.invoked(), ["pinprobe"], "the harness must log one run of the fake")


class MatchTests(ToolPinsCase):

    def test_a_minor_pin_accepts_a_patch_release(self):
        self.fake("python", "Python 3.15.2")
        local = self.write("python 3.15\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "python 3.15 must accept 3.15.2: exit %d: %s" % (rc, out))

    def test_the_apple_git_string_parses_to_its_first_dotted_number(self):
        self.fake("git", APPLE_GIT)
        local = self.write("git 2.54\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "git 2.54 must accept `git version 2.54.0 (Apple Git-155)`: exit %d: %s" % (rc, out))

    def test_the_windows_git_string_matches_its_minor_pin(self):
        self.fake("git", WINDOWS_GIT_256)
        local = self.write("git 2.56\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "git 2.56 must accept `git version 2.56.1.windows.1`: exit %d: %s" % (rc, out))

    def test_a_node_v_prefix_matches_an_exact_patch_pin(self):
        self.fake("node", "v26.11.1")
        local = self.write("node 26.11.1\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "node 26.11.1 must accept `v26.11.1`: exit %d: %s" % (rc, out))

    def test_an_exact_patch_pin_fails_on_another_patch(self):
        self.fake("node", "v26.11.1")
        local = self.write("node 26.11.2\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "node 26.11.2 must fail against v26.11.1: exit %d: %s" % (rc, out))
        self.assertIn("tool-pins: node pinned 26.11.2, found 26.11.1; move the pin or the tool",
                      out.splitlines(), "the mismatch line must name node, its pin and the found version: %s" % out)

    def test_a_git_mismatch_fails_with_the_named_message(self):
        self.fake("git", APPLE_GIT)
        local = self.write("git 2.56\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "git 2.56 must fail against git version 2.54.0: exit %d: %s" % (rc, out))
        self.assertIn(GIT_MISMATCH, out.splitlines(), "the mismatch line must name git, its pin and the found version: %s" % out)

    def test_the_gh_jq_and_bash_string_shapes_match_their_pins(self):
        self.fake("gh", "gh version 2.105.0 (2026-03-02)")
        self.fake("jq", "jq-1.7.1")
        self.fake("bash", "GNU bash, version 5.2.21(1)-release (x86_64-apple-darwin25.0)")
        local = self.write("gh 2.105\njq 1.7\nbash 5.2\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "gh 2.105, jq 1.7 and bash 5.2 must match their real version strings: exit %d: %s" % (rc, out))

    def test_a_pin_compares_whole_numbers_not_text_prefixes(self):
        self.fake("gh", "gh version 2.105.0 (2026-03-02)")
        local = self.write("gh 2.10\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "gh 2.10 must not accept 2.105.0, since 10 and 105 are different numbers: exit %d: %s" % (rc, out))

    def test_a_tool_added_by_one_pin_line_passes_with_no_code_change(self):
        self.fake("pinprobe", "pinprobe 4.2.7")
        local = self.write("pinprobe 4.2\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "an invented tool named by one line must be checked with no code change: exit %d: %s" % (rc, out))

    def test_a_tool_added_by_one_pin_line_fails_on_a_mismatch(self):
        self.fake("pinprobe", "pinprobe 4.1.0")
        local = self.write("pinprobe 4.2\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "an invented tool that differs from its pin must exit 1: exit %d: %s" % (rc, out))
        self.assertIn("tool-pins: pinprobe pinned 4.2, found 4.1.0; move the pin or the tool",
                      out.splitlines(), "the mismatch line must name the invented tool: %s" % out)

    def test_a_missing_tool_reads_unknown_and_never_a_crash(self):
        local = self.write("pinprobe-absent 1.0\n")
        rc, out = self.run_check("--file", local)
        self.assertNotEqual(rc, 0, "a tool not on PATH must not read as clear: exit 0: %s" % out)
        self.assertNotIn("Traceback", out, "a tool not on PATH must not crash the checker: %s" % out)
        self.assertIn("unknown", out, "a tool not on PATH must print unknown: %s" % out)
        self.assertIn("pinprobe-absent", out, "the unknown line must name the tool: %s" % out)


class LocalModeTests(ToolPinsCase):

    def test_local_mode_notes_a_mismatch_and_exits_zero(self):
        self.fake("git", APPLE_GIT)
        local = self.write("git 2.56\n")
        rc, out = self.run_check("--file", local, "--local")
        self.assertEqual(rc, 0, "--local must not fail a mismatch: exit %d: %s" % (rc, out))
        self.assertIn("git pinned 2.56, found 2.54.0", out, "--local must still note the mismatch: %s" % out)


class SyntaxTests(ToolPinsCase):

    def test_a_trailing_comment_on_a_pin_line_is_refused(self):
        self.fake("python", "Python 3.15.2")
        local = self.write("# the python this repo runs on\npython 3.15 # CI python\n")
        rc, out = self.run_check("--file", local)
        self.assertNotEqual(rc, 0, "a comment after a pin must be refused, not read as part of the pin: exit 0: %s" % out)
        self.assertIn("comment", out.lower(), "the refusal must say a comment sits after a pin: %s" % out)
        self.assertRegex(out, r"line 2\b|:2\b", "the refusal must name the offending line 2: %s" % out)

    def test_a_read_line_names_the_version_command(self):
        self.fake("python", "Python 2.7.18")
        self.fake("python3", "Python 3.15.2")
        local = self.write("# read: python = python3 --version\npython 3.15\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "# read: must run python3 --version, not python --version: exit %d: %s" % (rc, out))
        self.assertIn("python3", self.invoked(), "the # read: command must run: log %s" % self.invoked())
        self.assertNotIn("python", self.invoked(), "the default python --version must not run beside # read: ")

    def test_a_hash_inside_a_read_command_is_not_a_trailing_comment(self):
        self.fake("pinprobe-ver", "pinprobe 4.2.7")
        local = self.write('# read: pinprobe = pinprobe-ver "a # b"\npinprobe 4.2\n')
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "a # inside a quoted read command must stay part of that command: exit %d: %s" % (rc, out))
        self.assertIn("pinprobe-ver", self.invoked(), "the quoted read command must run: log %s" % self.invoked())


    def test_a_lone_quote_in_an_own_line_comment_does_not_hide_the_pin(self):
        self.fake("python", "Python 3.15.2")
        local = self.write("# the Windows's python is not pinned here\npython 3.15\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "a lone quote in a comment must not hide the python pin: exit %d: %s" % (rc, out))


class DefaultFileTests(ToolPinsCase):

    def test_with_no_file_argument_the_check_reads_the_root_of_the_repo_it_runs_in(self):
        self.fake("pinprobe", "pinprobe 4.1.0")
        repo = os.path.join(self.dir, "repo")
        os.makedirs(repo)
        init = subprocess.run(["git", "init", "-q", repo], env=self.tool_env(), capture_output=True, text=True)
        self.assertEqual(init.returncode, 0, "the fixture repo must be made: %s" % init.stderr)
        self.write("pinprobe 4.1\n", os.path.join("repo", ".tool-versions"))
        self.write("pinprobe 9.9\n")  # the folder above the repo: its pin must never be read
        rc, out = self.run_check(cwd=repo)
        self.assertEqual(rc, 0, "with no --file the check must read this repo's own .tool-versions and no other: exit %d: %s" % (rc, out))
        self.assertIn("pinprobe", self.invoked(), "this repo's pin must be checked, so its tool must run: log %s" % self.invoked())


class SetupPythonTests(ToolPinsCase):

    def test_the_setup_python_pattern_still_reads_the_python_line(self):
        self.fake("python", "Python 3.15.2")
        text = "# The python this repo runs on. This comment sits on its own line.\npython 3.15\n"
        local = self.write(text)
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "the python 3.15 line must pass with a comment on its own line above it: exit %d: %s" % (rc, out))
        versions = [m.group("version") for m in map(SETUP_PYTHON_PIN.match, text.splitlines()) if m]
        self.assertEqual(versions, ["3.15"], "setup-python's pattern must read the python line as 3.15 and skip the comment: %s" % versions)


class CostTests(ToolPinsCase):

    def test_one_process_per_pin_and_no_network(self):
        self.fake("git", WINDOWS_GIT_256)
        self.fake("python3", "Python 3.15.2")
        self.fake("node", "v26.11.1")
        local = self.write("git 2.56\n# read: python = python3 --version\npython 3.15\nnode 26.11.1\n")
        dead = {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9"}
        rc, out = self.run_check("--file", local, extra_env=dead)
        self.assertEqual(rc, 0, "three pins that match must pass with no network: exit %d: %s" % (rc, out))
        self.assertEqual(sorted(self.invoked()), ["git", "node", "python3"],
                         "each pin's version command must run exactly once, and nothing else: %s" % self.invoked())


if __name__ == "__main__":
    unittest.main()
