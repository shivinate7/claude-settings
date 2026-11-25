#!/usr/bin/env python3
"""Cases for lint/check_tool_pins.py. Standard library only.

    python3 lint/test_check_tool_pins.py

A root `.tool-versions` file holds one line per tool: `<tool> <version>`. The check runs each tool's version
command and compares the version in its output to the pin, at the precision the pin states. A dotted number inside
a path is never the version; a `# match:` line names the version when the output leads with another number.
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
import check_tool_pins  # noqa: E402  the one text reader (parse_text), which the ready run calls on a head's pin file

CHECK = os.path.join(HERE, "check_tool_pins.py")
RUN_TIMEOUT = 60  # a hang guard well above a run of a few process starts
GIT_MISMATCH = "git pinned 2.56, found 2.54.0; move the pin or the tool"  # the cause; the line prefix is not pinned here
APPLE_GIT = "git version 2.54.0 (Apple Git-155)"
WINDOWS_GIT_256 = "git version 2.56.1.windows.1"
# A copy of the pattern setup-python documents for .tool-versions, written from that documentation and not read from
# its source. The JS form names its group <version>; Python spells the same named group (?P<version>...).
SETUP_PYTHON_PIN = re.compile(r"^\s*python\s*v?\s*(?P<version>[^\s]+)\s*$")
RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder
PLATFORMS = ("macos", "windows", "linux")  # the keys a `# fix:` line names
HANG_SECONDS = 600  # a hung version read; the checker's own budget ends it long before this


def platform_key():
    """The platform key a `# fix:` line names for the machine this test runs on."""
    return {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")


def fix_mark(tool, platform=None):
    """The text a case looks for in a fix command: the fix line for `platform` (this machine's by default) echoes it."""
    return "FIX-%s-%s" % ((platform or platform_key()).upper(), tool.upper())


def pin_file(tool, pin, skip=None):
    """A pin file's text: one pin, then a `# fix:` line for each platform, each echoing its own marker. `skip` leaves out
    one platform's fix line, so a case can read a machine with no fix for it."""
    lines = ["%s %s" % (tool, pin)]
    for platform in PLATFORMS:
        if platform != skip:
            lines.append("# fix: %s %s = echo %s" % (tool, platform, fix_mark(tool, platform)))
    return "\n".join(lines) + "\n"


def fake_tool(folder, log, name, output, hang=False):
    """Writes the fake `name` into `folder`. Each run appends `name` to `log`, then prints `output`; with `hang`, it sleeps
    instead of printing. Returns the path written. A hang is POSIX only: a Windows caller skips it. Other test suites import
    this one home (hooks/test_session_start.py, merge/test_merge.py)."""
    os.makedirs(folder, exist_ok=True)
    if os.name == "nt":
        path = os.path.join(folder, name + ".cmd")
        body = '@echo off\r\necho %s>>"%s"\r\necho %s\r\n' % (name, log, output)
    else:
        path = os.path.join(folder, name)
        body = "#!/bin/sh\necho %s >> %s\n" % (shlex.quote(name), shlex.quote(log))
        body += ("exec sleep %d\n" % HANG_SECONDS) if hang else ("echo %s\n" % shlex.quote(output))
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    os.chmod(path, 0o755)
    return path


def python_shim(folder, log, real=None, env=None):
    """A python3 in `folder` that appends its argv to `log` on each start, then runs the real interpreter (`real`, else this
    one) with the same argv. A case counts the lines that name a script. With `env`, each line also ends with that environment
    variable's value, or `unset` when it is not set. POSIX only."""
    if env is None:
        record = "printf '%s\\n' \"$*\" >> " + shlex.quote(log)
    else:
        record = "printf '%s %s\\n' \"$*\" \"${" + env + ":-unset}\" >> " + shlex.quote(log)
    body = "#!/bin/sh\n" + record + "\n" + "exec " + shlex.quote(real or sys.executable) + " \"$@\"\n"
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "python3")
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    os.chmod(path, 0o755)
    return path


def line_ends(out, text):
    """True when a line of `out` ends with `text`. The words that name the cause are pinned; the prefix of a line is not."""
    return any(line.strip().endswith(text) for line in out.splitlines())


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

    def fake(self, name, output, hang=False):
        """A fake tool on PATH. Each run appends its name to the log, then prints `output` (or hangs)."""
        fake_tool(self.bin, self.log, name, output, hang=hang)

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
        self.assertTrue(line_ends(out, "node pinned 26.11.2, found 26.11.1; move the pin or the tool"),
                        "the mismatch line must name node, its pin and the found version: %s" % out)

    def test_a_git_mismatch_fails_with_the_named_message(self):
        self.fake("git", APPLE_GIT)
        local = self.write("git 2.56\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "git 2.56 must fail against git version 2.54.0: exit %d: %s" % (rc, out))
        self.assertTrue(line_ends(out, GIT_MISMATCH), "the mismatch line must name git, its pin and the found version: %s" % out)

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
        self.assertTrue(line_ends(out, "pinprobe pinned 4.2, found 4.1.0; move the pin or the tool"),
                        "the mismatch line must name the invented tool: %s" % out)

    def test_a_missing_tool_reads_unknown_and_never_a_crash(self):
        local = self.write("pinprobe-absent 1.0\n")
        rc, out = self.run_check("--file", local)
        self.assertNotEqual(rc, 0, "a tool not on PATH must not read as clear: exit 0: %s" % out)
        self.assertNotIn("Traceback", out, "a tool not on PATH must not crash the checker: %s" % out)
        self.assertIn("unknown", out, "a tool not on PATH must print unknown: %s" % out)
        self.assertIn("pinprobe-absent", out, "the unknown line must name the tool: %s" % out)


class LocalModeTests(ToolPinsCase):

    def test_local_mode_notes_a_mismatch_and_exits_three(self):
        self.fake("git", APPLE_GIT)
        local = self.write("git 2.56\n")
        rc, out = self.run_check("--file", local, "--local")
        self.assertEqual(rc, 3, "--local must exit 3 on a mismatch, not 0 and not 1: exit %d: %s" % (rc, out))
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

    # The name is the one the decision record pins. The case proves one version command per pin, and nothing about the network.
    def test_one_process_per_pin_and_no_network(self):
        self.fake("git", WINDOWS_GIT_256)
        self.fake("python3", "Python 3.15.2")
        self.fake("node", "v26.11.1")
        local = self.write("git 2.56\n# read: python = python3 --version\npython 3.15\nnode 26.11.1\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "three pins that match must pass: exit %d: %s" % (rc, out))
        self.assertEqual(sorted(self.invoked()), ["git", "node", "python3"],
                         "each pin's version command must run exactly once, and nothing else: %s" % self.invoked())


class EmptyPinFileTests(ToolPinsCase):
    """A pin file with no pin line is refused, never read as a clear run."""

    def test_an_empty_pin_file_exits_one_and_says_no_pin_was_read(self):
        local = self.write("")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "an empty pin file must exit 1, not read as clear: exit %d: %s" % (rc, out))
        self.assertIn("no pin was read", out.lower(), "the refusal must say no pin was read: %s" % out)

    def test_a_pin_file_of_blank_lines_exits_one_and_says_no_pin_was_read(self):
        local = self.write("\n   \n\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "a pin file of blank lines must exit 1, not read as clear: exit %d: %s" % (rc, out))
        self.assertIn("no pin was read", out.lower(), "the refusal must say no pin was read: %s" % out)

    def test_a_pin_file_of_comments_only_exits_one_and_says_no_pin_was_read(self):
        local = self.write("# The tools this repo runs on.\n# None is pinned yet.\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "a pin file of comments only must exit 1, not read as clear: exit %d: %s" % (rc, out))
        self.assertIn("no pin was read", out.lower(), "the refusal must say no pin was read: %s" % out)


class VersionReadTests(ToolPinsCase):
    """The version is the number the tool prints, never a dotted number inside a path. A match line can name it."""

    def test_a_dotted_number_in_a_unix_path_is_never_the_version(self):
        self.fake("tooly", "/opt/python3.15/bin/tooly version 3.14.2")
        local = self.write("tooly 3.15\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "tooly 3.15 must fail against 3.14.2: a 3.15 inside a path is not the version: exit %d: %s" % (rc, out))
        self.assertTrue(line_ends(out, "tooly pinned 3.15, found 3.14.2; move the pin or the tool"),
                        "the mismatch must name the version the tool printed: %s" % out)

    def test_a_dotted_number_in_a_windows_path_is_never_the_version(self):
        self.fake("pytool", "C:\\Dev\\Sdk\\py3.15\\Pytool.exe version 3.14.2")
        local = self.write("pytool 3.15\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "pytool 3.15 must fail against 3.14.2: a 3.15 inside a path is not the version: exit %d: %s" % (rc, out))
        self.assertTrue(line_ends(out, "pytool pinned 3.15, found 3.14.2; move the pin or the tool"),
                        "the mismatch must name the version the tool printed: %s" % out)

    def test_a_match_line_names_the_version_when_the_output_leads_with_another_number(self):
        self.fake("swift-driver", "swift-driver version: 1.168.6 Apple Swift version 6.4.2")
        local = self.write("# read: swift = swift-driver --version\n# match: swift = Swift version (\\S+)\nswift 6.4\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "the match line must take 6.4.2 as the version, so swift 6.4 passes: exit %d: %s" % (rc, out))

    def test_without_a_match_line_the_leading_number_is_the_version_read(self):
        self.fake("swift-driver", "swift-driver version: 1.168.6 Apple Swift version 6.4.2")
        local = self.write("# read: swift = swift-driver --version\nswift 6.4\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "with no match line, swift 6.4 must fail against the first number 1.168.6: exit %d: %s" % (rc, out))
        self.assertTrue(line_ends(out, "swift pinned 6.4, found 1.168.6; move the pin or the tool"),
                        "the mismatch must name the number found: %s" % out)

    def test_a_match_line_with_no_group_exits_one_with_a_plain_message(self):
        self.fake("swift-driver", "Apple Swift version 6.4.2")
        local = self.write("# read: swift = swift-driver --version\n# match: swift = Swift version \\S+\nswift 6.4\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "a match regex with no group must exit 1: exit %d: %s" % (rc, out))
        self.assertNotIn("Traceback", out, "a match regex with no group must not crash the checker: %s" % out)
        self.assertIn("match", out.lower(), "the refusal must name the match line: %s" % out)

    def test_a_match_regex_that_does_not_compile_exits_one_with_a_plain_message(self):
        self.fake("swift-driver", "Apple Swift version 6.4.2")
        local = self.write("# read: swift = swift-driver --version\n# match: swift = Swift version (\\S+\nswift 6.4\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "a match regex that does not compile must exit 1: exit %d: %s" % (rc, out))
        self.assertNotIn("Traceback", out, "a match regex that does not compile must not crash the checker: %s" % out)
        self.assertIn("match", out.lower(), "the refusal must name the match line: %s" % out)

    def test_a_hash_inside_a_match_regex_is_not_a_trailing_comment(self):
        self.fake("swift-driver", "swift-driver version: 1.168.6 Swift#version 6.4.2")
        local = self.write("# read: swift = swift-driver --version\n# match: swift = Swift#version (\\S+)\nswift 6.4\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "a # inside a match regex must stay part of the regex, so swift 6.4 passes: exit %d: %s" % (rc, out))


class PreReleaseTests(ToolPinsCase):
    """A pre-release is a version of its own: a pin that does not state it never matches it."""

    def test_a_release_candidate_does_not_match_a_minor_pin(self):
        self.fake("python", "Python 3.15.0rc1")
        local = self.write("python 3.15\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "python 3.15 must not accept 3.15.0rc1: exit %d: %s" % (rc, out))
        self.assertIn("found 3.15.0rc1", out, "the mismatch must name the pre-release it read: %s" % out)

    def test_an_alpha_does_not_match_a_patch_pin(self):
        self.fake("python", "Python 3.15.0a2")
        local = self.write("python 3.15.0\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "python 3.15.0 must not accept 3.15.0a2: exit %d: %s" % (rc, out))
        self.assertIn("found 3.15.0a2", out, "the mismatch must name the pre-release it read: %s" % out)

    def test_a_dev_build_does_not_match_a_patch_pin(self):
        self.fake("python", "Python 3.15.0.dev1")
        local = self.write("python 3.15.0\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "python 3.15.0 must not accept 3.15.0.dev1: exit %d: %s" % (rc, out))
        self.assertIn("found 3.15.0.dev1", out, "the mismatch must name the dev build it read: %s" % out)

    def test_a_pin_that_states_a_pre_release_matches_it(self):
        self.fake("python", "Python 3.15.0rc1")
        local = self.write("python 3.15.0rc1\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "python 3.15.0rc1 must accept 3.15.0rc1: exit %d: %s" % (rc, out))


class DirectiveCaseTests(ToolPinsCase):
    """`# Read:`, `# READ:`, `# Match:` and `# MATCH:` work as `# read:` and `# match:` do."""

    def test_a_capitalised_read_line_runs_its_command(self):
        self.fake("python", "Python 2.7.18")
        self.fake("python3", "Python 3.15.2")
        local = self.write("# Read: python = python3 --version\npython 3.15\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "# Read: must run python3 --version, as # read: does: exit %d: %s" % (rc, out))
        self.assertNotIn("python", self.invoked(), "# Read: must replace the default python --version: log %s" % self.invoked())

    def test_an_upper_case_read_line_runs_its_command(self):
        self.fake("python", "Python 2.7.18")
        self.fake("python3", "Python 3.15.2")
        local = self.write("# READ: python = python3 --version\npython 3.15\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "# READ: must run python3 --version, as # read: does: exit %d: %s" % (rc, out))
        self.assertNotIn("python", self.invoked(), "# READ: must replace the default python --version: log %s" % self.invoked())

    def test_a_capitalised_match_line_takes_the_version_as_match_does(self):
        self.fake("swift-driver", "swift-driver version: 1.168.6 Apple Swift version 6.4.2")
        local = self.write("# read: swift = swift-driver --version\n# Match: swift = Swift version (\\S+)\nswift 6.4\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "# Match: must take 6.4.2 as the version, as # match: does: exit %d: %s" % (rc, out))

    def test_an_upper_case_match_line_takes_the_version_as_match_does(self):
        self.fake("swift-driver", "swift-driver version: 1.168.6 Apple Swift version 6.4.2")
        local = self.write("# read: swift = swift-driver --version\n# MATCH: swift = Swift version (\\S+)\nswift 6.4\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "# MATCH: must take 6.4.2 as the version, as # match: does: exit %d: %s" % (rc, out))


class EncodingTests(ToolPinsCase):
    """A pin file that is not UTF-8 is refused in one line. A UTF-8 byte-order mark at the start is ignored."""

    def test_a_pin_file_that_is_not_utf8_exits_one_with_one_line(self):
        self.fake("python", "Python 3.15.2")
        path = os.path.join(self.dir, ".tool-versions")
        with open(path, "wb") as f:
            f.write(b"python 3.15\n# caf\xe9\n")
        rc, out = self.run_check("--file", path)
        self.assertEqual(rc, 1, "a pin file that is not UTF-8 must exit 1: exit %d: %s" % (rc, out))
        self.assertNotIn("Traceback", out, "a pin file that is not UTF-8 must not crash the checker: %s" % out)
        self.assertEqual(len(out.strip().splitlines()), 1, "the refusal must be one line: %s" % out)

    def test_a_read_command_holding_a_nul_exits_one_with_one_line(self):
        local = self.write("# read: python = python3\x00 --version\npython 3.15\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "a read command holding a NUL must exit 1: exit %d: %s" % (rc, out))
        self.assertNotIn("Traceback", out, "a read command holding a NUL must not crash the checker: %s" % out)
        self.assertEqual(len(out.strip().splitlines()), 1, "the refusal must be one line: %s" % out)

    def test_a_utf8_byte_order_mark_at_the_file_start_is_ignored(self):
        self.fake("python", "Python 3.15.2")
        path = os.path.join(self.dir, ".tool-versions")
        with open(path, "wb") as f:
            f.write(b"\xef\xbb\xbfpython 3.15\n")
        rc, out = self.run_check("--file", path)
        self.assertEqual(rc, 0, "a UTF-8 BOM at the file start must not hide the python pin: exit %d: %s" % (rc, out))


class ReadTextTests(unittest.TestCase):
    """The ready run reads a head's pin file as text (parse_text), not as a path (parse). Both take a byte-order mark at the start the same way."""

    def tools(self, text):
        pins = check_tool_pins.parse_text(text, "lane-101:.tool-versions")[0]
        return [tool for tool, _, _ in pins]

    def test_a_byte_order_mark_at_the_start_of_the_text_does_not_rename_the_tool(self):
        self.assertEqual(self.tools("﻿python 3.15\n"), ["python"],
                         "a byte-order mark at the start of the text renamed the tool, so its pin names no tool the file pins")

    def test_control_the_same_text_without_a_byte_order_mark_reads_the_tool(self):
        self.assertEqual(self.tools("python 3.15\n"), ["python"], "control: a plain pin line does not read its tool")


class MajorOnlyPinTests(ToolPinsCase):
    """A pin that states only a major accepts any minor and patch under it, and nothing above it."""

    def test_a_major_only_pin_accepts_a_patch_release(self):
        self.fake("tint", "tint 3.2.1")
        local = self.write("tint 3\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "tint 3 must accept 3.2.1: exit %d: %s" % (rc, out))

    def test_a_major_only_pin_accepts_a_bare_major(self):
        self.fake("tint", "tint 3")
        local = self.write("tint 3\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "tint 3 must accept output `tint 3`: exit %d: %s" % (rc, out))

    def test_a_major_only_pin_fails_on_the_next_major(self):
        self.fake("tint", "tint 4.0")
        local = self.write("tint 3\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "tint 3 must fail against 4.0: exit %d: %s" % (rc, out))
        self.assertTrue(line_ends(out, "tint pinned 3, found 4.0; move the pin or the tool"),
                        "the mismatch must name the major found: %s" % out)


class FailLineTests(ToolPinsCase):
    """Without --local a mismatch line starts with FAIL, so a reader finds the failing pin by its first word."""

    def test_a_mismatch_line_without_local_starts_with_fail(self):
        self.fake("git", APPLE_GIT)
        local = self.write("git 2.56\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 1, "git 2.56 must fail against git version 2.54.0: exit %d: %s" % (rc, out))
        self.assertTrue(any(line.startswith("FAIL") and GIT_MISMATCH in line for line in out.splitlines()),
                        "the mismatch line must start with FAIL and name git, its pin and the found version: %s" % out)


class LocalExitCodeTests(ToolPinsCase):
    """With --local the exit code tells lane lint a match (0), a mismatch (3) and an unknown or refused file (1) apart."""

    def test_a_local_mismatch_exits_three(self):
        self.fake("git", APPLE_GIT)
        local = self.write("git 2.56\n")
        rc, out = self.run_check("--file", local, "--local")
        self.assertEqual(rc, 3, "--local on a mismatch must exit 3, so lane lint tells it from a match: exit %d: %s" % (rc, out))

    def test_a_local_match_exits_zero(self):
        self.fake("python", "Python 3.15.2")
        local = self.write("python 3.15\n")
        rc, out = self.run_check("--file", local, "--local")
        self.assertEqual(rc, 0, "--local on a match must exit 0: exit %d: %s" % (rc, out))

    def test_a_local_unknown_exits_one_and_names_the_tool(self):
        local = self.write("pinprobe-absent 1.0\n")
        rc, out = self.run_check("--file", local, "--local")
        self.assertEqual(rc, 1, "--local on an unknown read must exit 1: exit %d: %s" % (rc, out))
        self.assertIn("pinprobe-absent", out, "the unknown line must name the tool: %s" % out)

    def test_a_local_refused_file_exits_one(self):
        local = self.write("python 3.15 # CI python\n")
        rc, out = self.run_check("--file", local, "--local")
        self.assertEqual(rc, 1, "--local on a refused file must exit 1: exit %d: %s" % (rc, out))


class ReadLineOrderTests(ToolPinsCase):
    """A tool may have several `# read:` lines, tried in order. The first that runs and prints a version wins, so one file
    can name python3 first and python second, for a Windows runner that has only python. No tool name is hard-coded."""

    PY_READS = "# read: python = python3 --version\n# read: python = python --version\npython 3.15\n"

    def test_the_first_read_that_runs_wins_over_a_later_one(self):
        self.fake("python3", "Python 3.15.2")
        self.fake("python", "Python 2.7.18")
        local = self.write(self.PY_READS)
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "the first # read: line that runs must give the version, so python3's 3.15.2 passes: exit %d: %s" % (rc, out))
        self.assertEqual(self.invoked(), ["python3"], "the later # read: line must not run once the first printed a version: log %s" % self.invoked())

    def test_a_later_read_runs_when_the_first_program_is_absent(self):
        self.fake("python", "Python 3.15.2")
        local = self.write(self.PY_READS)
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "with python3 absent, the later python read must give the version: exit %d: %s" % (rc, out))

    def test_a_first_read_that_prints_no_version_falls_to_the_next(self):
        self.fake("python3", "no version here")
        self.fake("python", "Python 3.15.2")
        local = self.write(self.PY_READS)
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "a first read that prints no version must fall to the next read: exit %d: %s" % (rc, out))

    def test_a_tool_whose_every_read_fails_reads_unknown(self):
        # The checker's PATH is an empty folder. The host's python3 and python would answer both reads, so the case hides them.
        os.makedirs(self.bin, exist_ok=True)
        for name in ("python3", "python"):
            self.assertIsNone(shutil.which(name, path=self.bin),
                              "the PATH this case gives the checker must hide the host's %s, or its read would succeed" % name)
        local = self.write(self.PY_READS)
        rc, out = self.run_check("--file", local, extra_env={"PATH": self.bin})
        self.assertEqual(rc, 1, "a tool whose every read fails must read unknown and exit 1: exit %d: %s" % (rc, out))
        self.assertIn("python", out, "the unknown line must name the tool: %s" % out)

    def test_a_hash_inside_a_quoted_first_read_is_not_a_comment_and_that_read_wins(self):
        self.fake("pinprobe-ver", "pinprobe 4.2.7")
        local = self.write('# read: pinprobe = pinprobe-ver "a # b"\n# read: pinprobe = pinprobe-absent\npinprobe 4.2\n')
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "a # inside a quoted first read must stay part of that read, and that read must win: exit %d: %s" % (rc, out))
        self.assertEqual(self.invoked(), ["pinprobe-ver"], "the quoted first read must be the one that runs: log %s" % self.invoked())

    def test_a_lone_quote_in_a_comment_between_read_lines_keeps_the_first_read_first(self):
        self.fake("python3", "Python 3.15.2")
        self.fake("python", "Python 2.7.18")
        local = self.write("# read: python = python3 --version\n# the Windows's python is read below\n# read: python = python --version\npython 3.15\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "a lone quote in a comment must not change which read line runs first: exit %d: %s" % (rc, out))


class WindowsAppsTests(ToolPinsCase):
    """A program that resolves under a WindowsApps folder is the Store's app alias, not an install: it is skipped as not installed."""

    def test_a_program_under_a_windowsapps_folder_is_skipped_as_not_installed(self):
        self.bin = os.path.join(self.dir, "WindowsApps", "bin")
        self.fake("pinprobe", "pinprobe 4.2.7")
        local = self.write("pinprobe 4.2\n")
        rc, out = self.run_check("--file", local)
        self.assertNotIn("pinprobe", self.invoked(), "a program under a WindowsApps folder must not run: log %s" % self.invoked())
        self.assertEqual(rc, 1, "a tool skipped as not installed reads unknown and exits 1: exit %d: %s" % (rc, out))
        self.assertIn("unknown", out, "the skipped tool must print unknown: %s" % out)

    def test_the_same_program_outside_a_windowsapps_folder_is_checked(self):
        self.fake("pinprobe", "pinprobe 4.2.7")
        local = self.write("pinprobe 4.2\n")
        rc, out = self.run_check("--file", local)
        self.assertEqual(rc, 0, "the same program outside WindowsApps must be checked and match: exit %d: %s" % (rc, out))
        self.assertEqual(self.invoked(), ["pinprobe"], "the program outside WindowsApps must run: log %s" % self.invoked())


class BehindCase(ToolPinsCase):
    """The `--behind <root>` read the session start and the ready run make: one tool, one pin, one fake on PATH."""

    def behind(self, pin, found, text=None, tool="pinprobe"):
        """Writes the pin file (a fix line for every platform unless `text` is given), fakes `tool` printing `found`, and runs
        `--behind` on the folder. -> (exit code, output)."""
        self.fake(tool, "%s %s" % (tool, found))
        self.write(text if text is not None else pin_file(tool, pin))
        return self.run_check("--behind", self.dir)

    def behind_lines(self, out):
        return [line for line in out.splitlines() if "BEHIND" in line]


class BehindTests(BehindCase):
    """A tool older than its pin exits 3 with one BEHIND line that carries the fix. A newer tool is no failure."""

    def test_a_tool_older_than_its_pin_exits_three(self):
        rc, out = self.behind("9.0", "8.1.0")
        self.assertEqual(rc, 3, "--behind on a tool older than its pin did not exit 3: exit %s: %s" % (rc, out))

    def test_the_behind_line_names_the_found_version_and_the_path_it_was_read_from(self):
        rc, out = self.behind("9.0", "8.1.0")
        lines = self.behind_lines(out)
        self.assertEqual(len(lines), 1, "expected one BEHIND line, got %r" % out)
        self.assertIn("8.1.0", lines[0], "the BEHIND line does not name the version found: %s" % lines[0])
        self.assertIn(self.bin, lines[0], "the BEHIND line does not name the path the tool was read from: %s" % lines[0])

    def test_the_behind_line_carries_this_platforms_fix_and_no_other_platforms_fix(self):
        rc, out = self.behind("9.0", "8.1.0")
        lines = self.behind_lines(out)
        self.assertTrue(lines, "no BEHIND line: %s" % out)
        self.assertIn(fix_mark("pinprobe"), lines[0], "the BEHIND line does not carry this platform's fix: %s" % lines[0])
        for platform in PLATFORMS:
            if platform != platform_key():
                self.assertNotIn(fix_mark("pinprobe", platform), lines[0],
                                 "the BEHIND line carries the fix for %s, not this platform: %s" % (platform, lines[0]))

    def test_a_missing_fix_line_for_this_platform_exits_three_and_names_the_platform(self):
        rc, out = self.behind("9.0", "8.1.0", text=pin_file("pinprobe", "9.0", skip=platform_key()))
        self.assertEqual(rc, 3, "a tool behind its pin with no fix line for this platform did not exit 3: exit %s: %s" % (rc, out))
        named = [line for line in out.splitlines() if "pinprobe" in line and platform_key() in line]
        self.assertTrue(named, "the missing fix line for %s is not named: %s" % (platform_key(), out))

    def test_a_tool_newer_than_its_pin_exits_zero_and_says_ahead(self):
        rc, out = self.behind("9.0", "9.2.0")
        self.assertEqual(rc, 0, "a tool newer than its pin is no failure, but --behind exited %s: %s" % (rc, out))
        self.assertFalse(self.behind_lines(out), "a tool newer than its pin printed a BEHIND line: %s" % out)
        self.assertIn("ahead", out.lower(), "a tool newer than its pin gave no ahead note: %s" % out)

    def test_a_tool_matching_its_pin_exits_zero_with_no_behind_line(self):
        rc, out = self.behind("9.0", "9.0.2")
        self.assertEqual(rc, 0, "a tool matching its pin exited %s under --behind: %s" % (rc, out))
        self.assertFalse(self.behind_lines(out), "a tool matching its pin printed a BEHIND line: %s" % out)

    def test_a_pin_compares_numbers_so_two_nine_is_behind_two_ten(self):
        rc, out = self.behind("2.10", "2.9.0")
        self.assertEqual(rc, 3, "2.9.0 was not behind a 2.10 pin (text order would say ahead): exit %s: %s" % (rc, out))

    def test_a_release_candidate_is_behind_its_final_release(self):
        rc, out = self.behind("3.15", "3.15.0rc1")
        self.assertEqual(rc, 3, "3.15.0rc1 was not behind a 3.15 pin: exit %s: %s" % (rc, out))

    def test_a_major_only_pin_is_behind_a_lower_major(self):
        rc, out = self.behind("3", "2.9.9")
        self.assertEqual(rc, 3, "2.9.9 was not behind a major-only 3 pin: exit %s: %s" % (rc, out))

    def test_a_major_only_pin_is_ahead_of_a_higher_major(self):
        rc, out = self.behind("3", "4.0.0")
        self.assertEqual(rc, 0, "4.0.0 is no failure under a major-only 3 pin, but --behind exited %s: %s" % (rc, out))

    def test_a_tool_that_is_not_installed_exits_one_and_names_it_unknown(self):
        self.write(pin_file("pinprobe", "9.0"))
        rc, out = self.run_check("--behind", self.dir)
        self.assertEqual(rc, 1, "a tool with no version to read did not exit 1: exit %s: %s" % (rc, out))
        named = [line for line in out.splitlines() if "pinprobe" in line and "unknown" in line]
        self.assertTrue(named, "the unreadable tool is not named unknown: %s" % out)

    def test_a_tool_that_prints_no_version_exits_one_and_names_it_unknown(self):
        self.fake("pinprobe", "no version printed here")
        self.write(pin_file("pinprobe", "9.0"))
        rc, out = self.run_check("--behind", self.dir)
        self.assertEqual(rc, 1, "a tool that printed no version did not exit 1: exit %s: %s" % (rc, out))
        named = [line for line in out.splitlines() if "pinprobe" in line and "unknown" in line]
        self.assertTrue(named, "the tool that printed no version is not named unknown: %s" % out)


class FixLineTests(BehindCase):
    """A `# fix:` line reads `# fix: <tool> <macos|windows|linux> = <command>`. A malformed one is refused, never skipped."""

    def refused(self, line):
        self.fake("pinprobe", "pinprobe 8.1.0")
        self.write("pinprobe 9.0\n%s\n" % line)
        return self.run_check("--behind", self.dir)

    def test_a_fix_line_naming_an_unknown_platform_is_refused_with_its_line_number(self):
        rc, out = self.refused("# fix: pinprobe beos = echo x")
        self.assertEqual(rc, 1, "a fix line for an unknown platform was not refused: exit %s: %s" % (rc, out))
        self.assertRegex(out, r"line\s*2\b", "the refusal does not name line 2: %s" % out)

    def test_a_fix_line_for_a_tool_no_line_pins_is_refused(self):
        rc, out = self.refused("# fix: nosuchtool %s = echo x" % platform_key())
        self.assertEqual(rc, 1, "a fix line for a tool no line pins was not refused: exit %s: %s" % (rc, out))

    def test_a_fix_line_with_no_equals_sign_is_refused(self):
        rc, out = self.refused("# fix: pinprobe %s echo x" % platform_key())
        self.assertEqual(rc, 1, "a fix line with no `=` was not refused: exit %s: %s" % (rc, out))

    def test_a_fix_line_with_an_empty_command_is_refused(self):
        rc, out = self.refused("# fix: pinprobe %s =" % platform_key())
        self.assertEqual(rc, 1, "a fix line with an empty command was not refused: exit %s: %s" % (rc, out))


class BehindControlTests(BehindCase):
    """Controls, green on the old code: the default and --local exits a behind tool already had. --behind reads the same
    tools and never changes those verdicts."""

    def test_control_the_default_run_on_a_behind_tool_exits_one_with_a_fail_line(self):
        self.fake("pinprobe", "pinprobe 8.1.0")
        pin = self.write(pin_file("pinprobe", "9.0"))
        rc, out = self.run_check("--file", pin)
        self.assertEqual(rc, 1, "the default run on a tool behind its pin did not exit 1: exit %s: %s" % (rc, out))
        self.assertTrue(any(line.startswith("FAIL ") and "pinprobe" in line for line in out.splitlines()),
                        "the default run printed no FAIL line for pinprobe: %s" % out)

    def test_control_local_on_a_behind_tool_exits_three_as_a_note(self):
        self.fake("pinprobe", "pinprobe 8.1.0")
        pin = self.write(pin_file("pinprobe", "9.0"))
        rc, out = self.run_check("--file", pin, "--local")
        self.assertEqual(rc, 3, "--local on a tool behind its pin did not exit 3: exit %s: %s" % (rc, out))
        self.assertFalse(any(line.startswith("FAIL ") for line in out.splitlines()), "--local printed a FAIL line: %s" % out)


class BehindCostTests(BehindCase):
    """The cost of the read: one version command per pin, and none more (decision outcomes-mechanize-rules)."""

    def test_behind_runs_one_version_command_per_pin_and_no_more(self):
        self.fake("pinprobe", "pinprobe 9.0.0")
        self.fake("secondprobe", "secondprobe 1.0.0")
        self.write(pin_file("pinprobe", "9.0") + "secondprobe 1.0\n")
        rc, out = self.run_check("--behind", self.dir)
        self.assertEqual(rc, 0, "two tools that match their pins did not pass under --behind: exit %s: %s" % (rc, out))
        self.assertEqual(sorted(self.invoked()), ["pinprobe", "secondprobe"],
                         "--behind ran a version command other than one per pin: %r" % self.invoked())


if __name__ == "__main__":
    unittest.main()
