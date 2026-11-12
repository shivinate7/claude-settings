#!/usr/bin/env python3
"""Fails when a debt record does not link its decision. Stdlib only.

    python3 lint/check_debt_decision.py [--base origin/main]

Every debt record links its decision (note debt-decision-link-unchecked, docs/debts/README.md). The check reads the
Decision part of each debt a change adds or edits. It fails when that part is not a decision slug or `none`.
It also fails when an added debt has no Decision part. This file is a stub: it exits 0 and prints nothing.
"""
import argparse
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", default="origin/main")
    ap.parse_args(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
