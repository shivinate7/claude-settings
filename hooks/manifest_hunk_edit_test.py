#!/usr/bin/env python3
"""The Retire check of debt manifest-hunk-edit-refused: the held case, an Edit that resolves the version hunk of a
two-hunk package.json conflict, must go green. The case lives in tests/held/, outside the folder CI runs, so
hooks/test_guard.py never sees it. This file copies the section files of tests/guard/ and the held file into one run
folder, points GUARD_SECTION_DIR at it, runs only that case, and exits with test_guard's code.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)

CASE = "Edit that resolves the version hunk of a two-hunk package.json conflict is allowed"


def main():
    run = _test_temp.run_folder()
    try:
        sections = os.path.join(run, "sections")
        os.makedirs(sections)
        guard_dir = os.path.join(REPO, "tests", "guard")
        for name in os.listdir(guard_dir):
            if name.endswith(".py"):
                shutil.copy(os.path.join(guard_dir, name), sections)
        shutil.copy(os.path.join(REPO, "tests", "held", "s21305-held.py"), sections)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GUARD_", "MUTATE_ONLY"))}
        env.update(GUARD_SECTION_DIR=sections, MUTATE_ONLY=CASE)
        return subprocess.run([sys.executable, os.path.join(HERE, "test_guard.py")], env=env).returncode
    finally:
        shutil.rmtree(run, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
