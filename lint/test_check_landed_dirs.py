#!/usr/bin/env python3
"""Cases for lint/check_landed_dirs.py: it must go red on a known-bad input, not only pass.

    python3 lint/test_check_landed_dirs.py

Each case copies the files the check reads (the manifest, both installers, every hooks/guard*.py)
into a temp tree, applies one defect to a copy
(never the real file), and runs the real script from that tree. The clean copy must pass first,
or a red result below would only prove the copy was broken.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FILES = ("landed-dirs.txt", "install.sh", "install.ps1")
# Every hooks/guard*.py: the frozen-dir literals may move to a sibling module (guard_core.py and
# the family modules), so the copy takes all of them, not only guard.py.
GUARD_FILES = tuple(
    os.path.relpath(p, ROOT) for p in sorted(glob.glob(os.path.join(ROOT, "hooks", "guard*.py")))
)


def move_frozen_dirs_to_sibling(tree):
    """Cut the CONFIG_FROZEN_DIRS literal (its comments included) out of guard.py and write it
    to a sibling module. The check must still find it there: a moved literal is not a drift."""
    path = os.path.join(tree, "hooks", "guard.py")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"CONFIG_FROZEN_DIRS\s*=\s*\(.*?\n\)\n", text, re.DOTALL)
    assert m, "the literal's anchor moved"
    block = m.group(0)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text.replace(block, "", 1))
    with open(os.path.join(tree, "hooks", "guard_frozen.py"), "w", encoding="utf-8",
              newline="") as f:
        f.write("import os\n\n" + block)


def run_in_copy(edit=None):
    """Copy the inputs to a temp tree, apply `edit(tree)`, run the script there."""
    tree = tempfile.mkdtemp(prefix="landed_dirs_case_")
    try:
        for rel in FILES + GUARD_FILES:
            dest = os.path.join(tree, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy(os.path.join(ROOT, rel), dest)
        shutil.copytree(os.path.join(ROOT, "skills"), os.path.join(tree, "skills"))
        os.makedirs(os.path.join(tree, "lint"))
        shutil.copy(os.path.join(HERE, "check_landed_dirs.py"), os.path.join(tree, "lint"))
        if edit:
            edit(tree)
        return subprocess.run(
            [sys.executable, os.path.join(tree, "lint", "check_landed_dirs.py")],
            capture_output=True, text=True, timeout=60,
        )
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def edit_file(rel, old, new):
    def edit(tree):
        path = os.path.join(tree, rel)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        assert old in text, "the defect's anchor moved: %r" % old
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text.replace(old, new, 1))
    return edit


class CheckLandedDirsTests(unittest.TestCase):

    def test_clean_copy_passes(self):
        result = run_in_copy()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_manifest_dir_missing_from_the_guard_literal_fails(self):
        # A new landed directory that CONFIG_FROZEN_DIRS does not freeze.
        result = run_in_copy(edit_file("landed-dirs.txt", "hooks", "hooks\nnewdir"))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("newdir", result.stderr)

    def test_guard_literal_dir_missing_from_the_manifest_fails(self):
        result = run_in_copy(edit_file("landed-dirs.txt", "hooks\n", ""))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("hooks", result.stderr)

    def test_install_sh_back_to_a_hardcoded_list_fails(self):
        result = run_in_copy(edit_file("install.sh", 'done < "$SRC/landed-dirs.txt"', "done"))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("install.sh", result.stderr)

    def test_frozen_dirs_literal_moved_to_a_sibling_module_still_passes(self):
        result = run_in_copy(move_frozen_dirs_to_sibling)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
