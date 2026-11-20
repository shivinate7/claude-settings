#!/usr/bin/env python3
"""Cases for lint/check_posix_tests.py: a test calls a POSIX-only API only under a Windows guard.

    python3 lint/test_check_posix_tests.py

Incident: #3729 added os.killpg and signal.SIGHUP cases with no Windows guard. The Windows merge jobs went
red. It was fixed in 49dc4f5229 and 2fff1a5e79.

The check runs as a command: python3 lint/check_posix_tests.py <test file>... Exit 0 is PASS. Exit 1 is FAIL,
and each offence prints file:line. Any other exit code is no verdict, and a case fails on that.

A guarded case has a twin: the same file with the guard's condition changed to one that is not a Windows
guard, or with the string taken off the call. The twin must FAIL at the call's line. So a PASS shows that the
check read the call and honoured the guard, not that it never read the file.

Fixtures are written under this run's folder (test-temp-standard, lint/_test_temp.py).
"""
import atexit
import os
import re
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: the run folder's one home (lint/_test_temp.py)

LINT = os.path.join(HERE, "check_posix_tests.py")
RUN = os.path.realpath(_test_temp.run_folder())  # every fixture of this run lives under it, removed at exit
atexit.register(shutil.rmtree, RUN, True)

FIX = "49dc4f5229"  # the commit that added the Windows guards; its parent holds the unguarded test file
UNGUARDED_LINE = 27693  # FIX^ merge/test_merge.py: signal.SIGHUP in WorkFolderOnSignal, which has no class guard
GUARDED_LINE = 15136  # FIX^ merge/test_merge.py: signal.SIGHUP under SignalReleasesLock's class guard
SIGHUP_CALL = b"self.assert_signal_removes_work_folder(signal.SIGHUP)"

HEAD = "import os\nimport signal\nimport unittest\n\n\n"
CLASS = "class ProcessGroup(unittest.TestCase):\n"
DEF = "    def test_stop_group(self):\n"
KILL = "        os.killpg(os.getpgid(0), signal.SIGTERM)\n"
KILL_NEEDLE = "        os.killpg("  # eight spaces: a call in a method body, never the same text at column 0 in a string
STRING_CALL = "os.killpg(os.getpgid(0), signal.SIGTERM)"


def skip_if(cond):
    return HEAD + CLASS + '    @unittest.skipIf(%s, "a skip")\n' % cond + DEF + KILL


def skip_test_if(cond):
    return HEAD + CLASS + DEF + '        if %s:\n            self.skipTest("a skip")\n' % cond + KILL


def has_attr(name):
    return HEAD + CLASS + DEF + '        if hasattr(os, "%s"):\n' % name + "    " + KILL


IN_STRING = (HEAD + CLASS + "    def test_names(self):\n"
             + '        note = "%s"  # signal.SIGHUP is text here\n' % STRING_CALL
             + '        self.assertIn("killpg", note)\n')
MULTI_STRING = (HEAD + CLASS + "    def test_doc(self):\n"
                + '        text = """\n' + STRING_CALL + "\n" + "signal.SIGHUP\n" + '"""\n'
                + '        self.assertIn("killpg", text)\n')
LONE_QUOTE = (HEAD + CLASS + "    def test_stop_group(self):\n"
              + '        """Don\'t run this on Windows."""\n'
              + "        # it's the POSIX stop path\n" + KILL)


def write(case, src):
    """Write one fixture test file under the run folder and return its path. A fixture that is not Python is a bug here."""
    data = src if isinstance(src, bytes) else src.encode("utf-8")
    folder = os.path.join(RUN, case)
    os.makedirs(folder)
    path = os.path.join(folder, "test_%s.py" % case)
    with open(path, "wb") as f:
        f.write(data)
    compile(data, path, "exec")
    return path


def line_of(src, needle):
    """The 1-based line of the one line of src that holds needle. Two such lines are a fixture bug."""
    hits = [n for n, text in enumerate(src.split("\n"), 1) if needle in text]
    assert len(hits) == 1, "fixture bug: %r is on %d lines" % (needle, len(hits))
    return hits[0]


def lint(*paths):
    """Run the check on these files. Return (exit code, output). An exit code other than 0 or 1 is no verdict."""
    proc = subprocess.run([sys.executable, LINT] + list(paths), cwd=ROOT, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=120)
    out = proc.stdout.decode("utf-8", "replace")
    if proc.returncode not in (0, 1):
        raise AssertionError("no verdict: the check exited %d, output %r" % (proc.returncode, out))
    return proc.returncode, out


def old_merge_test():
    """merge/test_merge.py as it stood before FIX, when its POSIX-only cases had no Windows guard. The commit must be in this clone."""
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
    proc = subprocess.run(["git", "-C", ROOT, "show", FIX + "^:merge/test_merge.py"], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, env=env, timeout=120)
    if proc.returncode != 0:
        raise AssertionError("fixture: %s^ is not in this clone: %s" % (FIX, proc.stderr.decode("utf-8", "replace").strip()))
    return proc.stdout


class PosixOnlyCalls(unittest.TestCase):
    def assert_passes(self, path):
        code, out = lint(path)
        self.assertEqual(code, 0, "a POSIX-only call under a Windows guard must PASS, and the check failed it: %s" % out.strip())

    def assert_fails_at(self, path, line):
        """Scope before subject: the FAIL names the file, then it names the call's line."""
        code, out = lint(path)
        name = os.path.basename(path)
        self.assertNotEqual(code, 0, "the check passed %s, which holds a POSIX-only call with no Windows guard" % name)
        self.assertIn(name, out, "the FAIL does not name the file %s: %s" % (name, out.strip()))
        self.assertRegex(out, r"%s:%d\b" % (re.escape(name), line), "the FAIL does not name the call at %s:%d" % (name, line))
        return out

    def fail_case(self, case, src):
        self.assert_fails_at(write(case, src), line_of(src, KILL_NEEDLE))

    def pass_case(self, case, src):
        self.assert_passes(write(case, src))

    def test_unguarded_killpg_fails_and_names_file_line(self):
        self.fail_case("unguarded", HEAD + CLASS + DEF + KILL)

    def test_skipif_nt_passes(self):
        self.pass_case("skipif_nt", skip_if('os.name == "nt"'))

    def test_skipif_on_posix_does_not_excuse(self):
        self.fail_case("skipif_posix", skip_if('os.name == "posix"'))

    def test_skiptest_under_nt_branch_passes(self):
        self.pass_case("skiptest_nt", skip_test_if('os.name == "nt"'))

    def test_skiptest_under_posix_branch_does_not_excuse(self):
        self.fail_case("skiptest_posix", skip_test_if('os.name == "posix"'))

    def test_hasattr_killpg_passes(self):
        self.pass_case("hasattr_killpg", has_attr("killpg"))

    def test_hasattr_getpid_does_not_excuse(self):
        self.fail_case("hasattr_getpid", has_attr("getpid"))

    def test_call_inside_string_or_comment_passes(self):
        self.pass_case("string_comment", IN_STRING)

    def test_same_call_as_code_fails(self):
        self.fail_case("string_as_code", IN_STRING.replace('note = "%s"' % STRING_CALL, STRING_CALL))

    def test_multiline_string_holding_calls_passes(self):
        self.pass_case("multiline_string", MULTI_STRING)

    def test_call_after_multiline_string_fails_on_its_own_line(self):
        src = MULTI_STRING + KILL
        path = write("multiline_then_call", src)
        out = self.assert_fails_at(path, line_of(src, KILL_NEEDLE))
        string_line = src.split("\n").index(STRING_CALL) + 1
        self.assertNotRegex(out, r"%s:%d\b" % (re.escape(os.path.basename(path)), string_line),
                            "the text inside the multi-line string is named as a call at line %d" % string_line)

    def test_lone_quote_in_text_does_not_hide_the_call(self):
        self.fail_case("lone_quote", LONE_QUOTE)

    def test_pre_fix_test_merge_fails_on_its_unguarded_sighup(self):
        old = old_merge_test()
        lines = old.split(b"\n")
        self.assertEqual(lines[UNGUARDED_LINE - 1].strip(), SIGHUP_CALL, "fixture: the line the incident hit has moved")
        self.assertIn(b"signal.SIGHUP", lines[GUARDED_LINE - 1], "fixture: the class-guarded line is not a SIGHUP call")
        path = write("merge", old)
        out = self.assert_fails_at(path, UNGUARDED_LINE)
        self.assertNotRegex(out, r"test_merge\.py:%d\b" % GUARDED_LINE,
                            "the class-guarded SIGHUP at line %d is named as an offence" % GUARDED_LINE)


if __name__ == "__main__":
    unittest.main()
