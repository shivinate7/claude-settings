"""A stand-in for lint/check_pick_claims.py, for the red-run record only (test-practices P3).

lint/test_check_pick_claims.py runs against it through CHECK_PICK_CLAIMS_UNDER_TEST. It defines every name the
cases use and reports nothing: no claim, no finding, exit 0. A case that expects a claim or a finding then fails on
its own assertion, not on a missing name.
"""
import sys


def claims(note):
    return []


def check(steps_dir, answers_path):
    return []


if __name__ == "__main__":
    sys.exit(0)
