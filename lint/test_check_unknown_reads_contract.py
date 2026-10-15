#!/usr/bin/env python3
"""Fixture suite for lint/check_unknown_reads_contract.py.

A guard member whose case cannot run on this platform gets test_guard's SKIP back, and the check
must print SKIP for that member, never PASS. The stub stands in for hooks/test_guard.py, so this suite
runs on any platform and does not import the guard suite, which builds every fixture at import.
"""
import contextlib
import importlib.util
import io
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, "check_unknown_reads_contract.py")
SKIP = "skip"  # test_guard.SKIP: what a checker returns for a case that cannot run here


def load_check():
    spec = importlib.util.spec_from_file_location("check_unknown_reads_contract", CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_guard_member(returned):
    """Run the check's main() with only the guard member, against a stub test_guard whose
    subject_unread_log_case returns `returned`. Give back the printed output and the exit code."""
    stub = types.ModuleType("test_guard")
    stub.subject_unread_log_case = lambda: returned
    saved = sys.modules.get("test_guard")
    sys.modules["test_guard"] = stub
    try:
        check = load_check()
        check.MEMBERS = tuple(m for m in check.MEMBERS if m[1] is check.guard_subject_unread_member)
        out = io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out):
            try:
                check.main()
            except SystemExit as exit_:
                code = exit_.code
        return out.getvalue(), code
    finally:
        if saved is None:
            sys.modules.pop("test_guard", None)
        else:
            sys.modules["test_guard"] = saved


def guard_row(out):
    return next(line for line in out.splitlines() if line.startswith(("PASS", "FAIL", "SKIP"))
                and "guard:" in line)


class GuardMemberRow(unittest.TestCase):
    def test_a_skipped_member_prints_skip_not_pass(self):
        out, code = run_guard_member((SKIP, "stub: a POSIX stand-in git does not run here"))
        row = guard_row(out)
        self.assertIn("SKIP", row, out)
        self.assertNotIn("PASS", row, out)
        self.assertFalse(code, out)

    def test_a_passing_member_prints_pass(self):
        out, code = run_guard_member((True, "stub: the read came back clear"))
        self.assertIn("PASS", guard_row(out), out)
        self.assertFalse(code, out)

    def test_a_failing_member_prints_fail_and_exits_1(self):
        out, code = run_guard_member((False, "stub: the read was silently allowed"))
        self.assertIn("FAIL", guard_row(out), out)
        self.assertEqual(code, 1, out)


if __name__ == "__main__":
    unittest.main()
