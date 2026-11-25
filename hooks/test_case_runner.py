#!/usr/bin/env python3
"""Cases for run_cases in hooks/case_runner_test.py: a run with no cases must fail, and a run whose
cases all skip must pass.

A suite that loses every case must not read as a pass. Today run_cases returns 0 for an empty list.
The control is a run whose cases all raise Skip: each prints SKIP and the run exits 0, as it always has.
"""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from case_runner_test import Skip, run_cases  # noqa: E402  the one case runner (hooks/case_runner_test.py)


def expect(cond, message):
    return [] if cond else [message]


def run_quiet(cases):
    """Run run_cases with its output held back. Returns (exit code, printed text)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = run_cases(cases)
    return code, out.getvalue()


def zero_cases_exit_one():
    """run_cases with no cases exits 1"""
    code, _ = run_quiet([])
    return expect(code == 1, f"run_cases([]) returned {code}, want 1: a run with no cases must fail")


def zero_cases_says_none_ran():
    """run_cases with no cases prints a line saying no cases ran"""
    _, text = run_quiet([])
    return expect("no cases ran" in text, f"run_cases([]) printed no line saying 'no cases ran': {text.strip()!r}")


def all_skipped_exit_zero():
    """run_cases whose cases all skip exits 0"""
    def skip_one():
        """skip one"""
        raise Skip("needs another platform")

    def skip_two():
        """skip two"""
        raise Skip("needs another platform")

    def skip_three():
        """skip three"""
        raise Skip("needs another platform")

    code, _ = run_quiet([skip_one, skip_two, skip_three])
    return expect(code == 0, f"run_cases of three skipped cases returned {code}, want 0: a skip never fails the run")


CASES = [zero_cases_exit_one, zero_cases_says_none_ran, all_skipped_exit_zero]


if __name__ == "__main__":
    sys.exit(run_cases(CASES))
