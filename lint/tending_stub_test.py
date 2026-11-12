"""A stand-in for lint/tending.py, wrong on purpose. lint/test_tending.py runs against it for the red run.

    TENDING_UNDER_TEST=<absolute path to this file> python3 lint/test_tending.py

tend says "true" for every item, close returns the text unchanged, and the command line exits 0 and prints
nothing. A case that expects another verdict, exit code or rewritten file then fails on that assert, which
is a behavioural red and not a missing name (decision test-practices, P3). The cost cases pass on it, since
it starts nothing: they are controls, and their red comes from a mutant after the build.
"""
import re
import sys


def tend(entry, text, root):
    return {found.group(1): "true" for found in re.finditer(entry["item"], text, re.M)}


def close(entry, text, verdicts):
    return text


def main(argv):
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
