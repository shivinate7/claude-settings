#!/usr/bin/env python3
"""The held case of debt manifest-hunk-edit-refused: an Edit that resolves the version hunk of a two-hunk
package.json conflict is allowed. The case is red on the current guard, so tests/guard/s21304-diff.py registers
it only when GUARD_HELD_CASES names the debt's slug. CI runs hooks/test_guard.py without that gate, so it never
sees the case. This file sets the gate and runs hooks/test_guard.py for that one case. The debt's Retire check
runs this file, and it exits with test_guard's code.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SLUG = "manifest-hunk-edit-refused"
CASE = "Edit that resolves the version hunk of a two-hunk package.json conflict is allowed"


def main():
    env = dict(os.environ, GUARD_HELD_CASES=SLUG, MUTATE_ONLY=CASE)
    return subprocess.run([sys.executable, os.path.join(HERE, "test_guard.py")], env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
