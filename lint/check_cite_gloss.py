#!/usr/bin/env python3
"""Fails when a record cites a record id on its first use with no gloss. Stdlib only.

    python3 lint/check_cite_gloss.py [--base origin/main]

A record glosses each id it cites on first use (rule speak-cite-id-plus-gloss in CLAUDE.md, note
cites-lack-gloss-unchecked). The check reads the lines a change adds or edits in a record. It fails on a first cite
of a record id that has no gloss right after its closing backtick. This file is a stub: it exits 0 and prints nothing.
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
