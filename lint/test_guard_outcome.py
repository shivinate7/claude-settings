#!/usr/bin/env python3
"""Cases for bin/guard-outcome, the command that writes one outcome line to guard.log.

A session that judges a refusal writes one claim: the refusal was a false alarm, or it was right.
The claim is the refused session's own word, not a fact (owner ruling, 2026-11-23 23:02 CST). The
reader is `lint/guard_log_report.py --outcomes`; its cases live in lint/test_guard_log_report.py.

Pinned line format: six tab-separated fields, as a guard.log line has.
    time     ISO 8601 to the second, with its UTC offset
    tool     empty
    decision outcome
    rule     the rule id the claim is about
    matched  the claim (`false-alarm` or `right`), then one space and the why text when there is one
    session  CLAUDE_CODE_SESSION_ID when set; when unset, the reader reads it as unknown session
The why text is one line: newlines and tabs fold to spaces, and it is capped at 200 characters.

Exit codes: 0 and one stdout line when the claim is written. 0 and one stderr line when the log
cannot be written, with nothing raised. 2 for a claim that is neither word, with nothing written.

Every case points the command at a scratch folder, by --log or by CLAUDE_CONFIG_DIR, so the real
guard.log is never touched. Run with:

    python3 lint/test_guard_outcome.py -v
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_log_report as glr  # noqa: E402
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD_OUTCOME = os.path.join(REPO_ROOT, "bin", "guard-outcome")
RUN_FOLDER = _test_temp.run_folder()
SID = "9f2c4e1a-7b3d-4c8e-9a10-5d6e7f8a9b0c"
CALLER_ENV = ("CLAUDE_CODE_REMOTE", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CONFIG_DIR")
SPAWN_NAMES = ("sh", "bash", "env", "git", "gh", "python", "python3")  # PATH names a call could start a process by


def scratch_folder():
    return tempfile.mkdtemp(dir=RUN_FOLDER)


def read_log(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def run_outcome(args, env=None, config_dir=None):
    """Run bin/guard-outcome with args. Return (rc, stdout, stderr).

    The caller's variables the command reads are removed first, and CLAUDE_CONFIG_DIR is a scratch
    folder, so a call with no --log cannot reach the real guard.log. When the command is not in the
    tree, rc is None and stderr says so: the case's assert then fails on the behaviour it names.
    """
    if not os.path.isfile(GUARD_OUTCOME):
        return None, "", "bin/guard-outcome is not in the tree"
    child = dict(os.environ)
    for name in CALLER_ENV:
        child.pop(name, None)
    child["CLAUDE_CONFIG_DIR"] = config_dir or scratch_folder()
    child.update(env or {})
    done = subprocess.run([sys.executable, GUARD_OUTCOME] + list(args), capture_output=True,
                          text=True, env=child, timeout=60)  # a hang guard, well above one call
    return done.returncode, done.stdout, done.stderr


class OutcomeLineTests(unittest.TestCase):
    def setUp(self):
        self.folder = scratch_folder()
        self.log = os.path.join(self.folder, "guard.log")

    def claim(self, *args, env=None):
        return run_outcome(list(args) + ["--log", self.log], env=env)

    def test_one_claim_is_one_line_in_the_pinned_format(self):
        rc, out, err = self.claim("load-brake", "false-alarm", "--why", "blocked my own check",
                                  env={"CLAUDE_CODE_SESSION_ID": SID})
        self.assertEqual(rc, 0, "guard-outcome must write the claim and exit 0: %s" % err)
        self.assertTrue(os.path.exists(self.log), "guard-outcome must create the log line")
        text = read_log(self.log)
        self.assertTrue(text.endswith("\n"), "the claim line must end with a newline")
        self.assertEqual(text.count("\n"), 1, "one claim must be one line")
        fields = text[:-1].split("\t")
        self.assertEqual(len(fields), 6, "the line must be time, tool, decision, rule, matched, session")
        self.assertIsNotNone(datetime.fromisoformat(fields[0]).utcoffset(), "the time must carry a UTC offset")
        self.assertEqual(fields[1:4], ["", "outcome", "load-brake"], "tool empty, decision outcome, rule id")
        self.assertEqual(fields[4], "false-alarm blocked my own check", "matched is the claim, a space, the why")
        self.assertEqual(fields[5], SID, "the session id comes from CLAUDE_CODE_SESSION_ID")

    def test_stdout_is_one_line_naming_the_rule_and_the_claim(self):
        rc, out, err = self.claim("load-brake", "right")
        self.assertEqual(rc, 0, "guard-outcome must exit 0 on a right claim: %s" % err)
        lines = out.strip().split("\n")
        self.assertEqual(len(lines), 1, "stdout must be one line, got %r" % out)
        self.assertIn("load-brake", lines[0], "the stdout line must name the rule")
        self.assertIn("right", lines[0], "the stdout line must name the claim")

    def test_a_right_claim_without_why_writes_the_bare_claim(self):
        rc, out, err = self.claim("load-brake", "right")
        self.assertEqual(rc, 0, "guard-outcome must exit 0: %s" % err)
        fields = read_log(self.log)[:-1].split("\t")
        self.assertEqual(fields[4], "right", "with no --why, matched is the claim alone")

    def test_an_unknown_claim_exits_2_and_writes_nothing(self):
        rc, out, err = self.claim("load-brake", "maybe")
        self.assertEqual(rc, 2, "an unknown claim must exit 2: %s" % err)
        self.assertFalse(os.path.exists(self.log), "an unknown claim must write nothing")

    def test_a_rule_never_refused_is_still_written(self):
        rc, out, err = self.claim("rule-never-refused", "false-alarm")
        self.assertEqual(rc, 0, "a rule with no refusal in the log must still exit 0: %s" % err)
        self.assertTrue(os.path.exists(self.log), "a claim for a rule with no refusal must still be written")
        self.assertEqual(read_log(self.log)[:-1].split("\t")[3], "rule-never-refused")

    def test_an_unwritable_log_exits_0_with_one_stderr_line(self):
        blocker = os.path.join(self.folder, "not-a-folder")
        with open(blocker, "w", encoding="utf-8") as handle:
            handle.write("x\n")
        rc, out, err = run_outcome(["load-brake", "false-alarm", "--log", os.path.join(blocker, "guard.log")])
        self.assertEqual(rc, 0, "an unwritable log must not fail the session: %s" % err)
        lines = [line for line in err.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, "an unwritable log must print one stderr line, got %r" % err)
        self.assertNotIn("Traceback", err, "an unwritable log must not raise")

    def test_a_multi_line_why_folds_to_one_line(self):
        rc, out, err = self.claim("load-brake", "false-alarm", "--why", "first part\nsecond\tpart\nthird part")
        self.assertEqual(rc, 0, "guard-outcome must exit 0: %s" % err)
        text = read_log(self.log)
        self.assertEqual(text.count("\n"), 1, "a newline in the why must not split the line")
        fields = text[:-1].split("\t")
        self.assertEqual(len(fields), 6, "a tab in the why must not move a field")
        self.assertEqual(fields[4], "false-alarm first part second part third part",
                         "newlines and tabs in the why fold to single spaces")

    def test_a_why_longer_than_200_characters_is_capped_at_200(self):
        rc, out, err = self.claim("load-brake", "false-alarm", "--why", "Q" * 300)
        self.assertEqual(rc, 0, "guard-outcome must exit 0: %s" % err)
        kept = re.findall("Q+", read_log(self.log))
        self.assertTrue(kept, "the why text must be recorded")
        self.assertLessEqual(len(kept[0]), 200, "the why text must hold at most 200 characters")
        self.assertGreaterEqual(len(kept[0]), 150, "the why text must keep up to 200 characters, not a short cut")

    def test_without_a_session_in_the_environment_the_reader_reads_unknown(self):
        rc, out, err = self.claim("load-brake", "right")
        self.assertEqual(rc, 0, "guard-outcome must exit 0: %s" % err)
        row = glr.parse_line(read_log(self.log).rstrip("\n"))
        self.assertIsNotNone(row, "the reader must read the claim line")
        self.assertEqual(row.session, glr.UNKNOWN, "an unset session reads as unknown session")

    def test_without_log_the_claim_goes_to_the_config_dir_guard_log(self):
        folder = scratch_folder()
        rc, out, err = run_outcome(["load-brake", "false-alarm"], config_dir=folder)
        self.assertEqual(rc, 0, "guard-outcome must exit 0 with no --log: %s" % err)
        path = os.path.join(folder, "guard.log")
        self.assertTrue(os.path.exists(path), "with no --log the default is $CLAUDE_CONFIG_DIR/guard.log")
        self.assertEqual(read_log(path).count("\n"), 1, "the default log must get one claim line")

    def test_a_second_claim_appends_and_keeps_the_first_line(self):
        rc, out, err = self.claim("load-brake", "false-alarm")
        self.assertEqual(rc, 0, "guard-outcome must exit 0 on the first claim: %s" % err)
        first = read_log(self.log)
        rc, out, err = self.claim("load-brake", "right")
        self.assertEqual(rc, 0, "guard-outcome must exit 0 on the second claim: %s" % err)
        text = read_log(self.log)
        self.assertEqual(text.count("\n"), 2, "two claims must be two lines")
        self.assertTrue(text.startswith(first), "the second claim must append, not rewrite the first line")

    @unittest.skipIf(os.name == "nt", "the process shim is a POSIX shell script")
    def test_one_call_appends_one_line_and_starts_no_other_process(self):
        # The shims catch only starts that go through PATH. A start by absolute path is not seen.
        bindir = os.path.join(self.folder, "bin")
        os.mkdir(bindir)
        starts = os.path.join(self.folder, "starts.txt")
        for name in SPAWN_NAMES:
            shim = os.path.join(bindir, name)
            with open(shim, "w", encoding="utf-8") as handle:
                handle.write("#!/bin/sh\necho %s >> '%s'\nexit 0\n" % (name, starts))
            os.chmod(shim, 0o755)
        path = bindir + os.pathsep + os.environ.get("PATH", "")
        rc, out, err = self.claim("load-brake", "false-alarm", env={"PATH": path})
        self.assertEqual(rc, 0, "guard-outcome must exit 0: %s" % err)
        self.assertEqual(read_log(self.log).count("\n"), 1, "one call must append exactly one line")
        self.assertFalse(os.path.exists(starts), "the call started another process through PATH")

    def test_the_reader_parses_the_claim_as_the_first_word_of_matched(self):
        rc, out, err = self.claim("rule-never-refused", "false-alarm", "--why", "never fired")
        self.assertEqual(rc, 0, "guard-outcome must exit 0: %s" % err)
        row = glr.parse_line(read_log(self.log).rstrip("\n"))
        self.assertIsNotNone(row, "the reader must read the claim line")
        self.assertEqual((row.decision, row.rule), ("outcome", "rule-never-refused"))
        self.assertEqual(row.matched.split(" ", 1)[0], "false-alarm", "the claim is the first word of matched")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
