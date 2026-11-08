#!/usr/bin/env python3
"""Fails when a mutant's anchor in hooks/mutate_guard.py is stale, ambiguous, or otherwise unrunnable.

    python3 lint/check_mutant_anchors.py [--root <repo>]

Runs the pre-check that `hooks/mutate_guard.py` runs before any suite (`precheck_errors`): each
anchor is found exactly once in its target's files, each entry names a required case, and no two
mutants share a path. So `merge --lane-lint` shows a bad anchor before review, and no suite runs.
Prints one `FAIL <kind> ...: <label>` line per error and exits 1; exits 0 when the table is sound.
The name holds no "mutate" on purpose: bin/ci-job drops such steps from `--lint`.

Cost: one process, reads about ten source files, no suite, no network. Measured about 0.4 s.
"""
import argparse
import os
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    default_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser.add_argument("--root", default=default_root, help="repo root whose hooks/ holds the MUTATIONS table")
    args = parser.parse_args(argv)
    sys.path.insert(0, os.path.join(os.path.abspath(args.root), "hooks"))
    import mutate_guard  # noqa: E402  imported after the path is set: it judges the tree --root names

    errors = mutate_guard.precheck_errors()
    for error in errors:
        print("FAIL " + error.replace("ERROR ", "", 1))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
