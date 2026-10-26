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
sys.path.insert(0, os.path.join(ROOT, "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)
FILES = ("landed-dirs.txt", "install.sh", "install.ps1")


def move_frozen_dirs_to_sibling(tree):
    """Cut the CONFIG_FROZEN_DIRS literal (its comments included) out of whichever hooks/guard*.py
    holds it, and write it to a new sibling module. The check must still find it there: a moved
    literal is not a drift. The holder is searched for, not named, so the literal may sit in
    guard.py or in any guard_<family>.py."""
    for path in sorted(glob.glob(os.path.join(tree, "hooks", "guard*.py"))):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        m = re.search(r"CONFIG_FROZEN_DIRS\s*=\s*\(.*?\n\)\n", text, re.DOTALL)
        if m:
            break
    else:
        raise AssertionError("the literal's anchor moved: no hooks/guard*.py holds it")
    block = m.group(0)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text.replace(block, "", 1))
    sibling = os.path.join(os.path.dirname(path), "guard_relocated.py")
    assert not os.path.exists(sibling), "the sibling name is taken: guard_relocated.py"
    with open(sibling, "w", encoding="utf-8", newline="") as f:
        f.write("import os\n\n" + block)


def run_in_copy(edit=None):
    """Copy the inputs to a temp tree, apply `edit(tree)`, run the script there."""
    tree = tempfile.mkdtemp(prefix="landed_dirs_case_")
    try:
        for rel in FILES:
            shutil.copy(os.path.join(ROOT, rel), os.path.join(tree, rel))
        shutil.copytree(os.path.join(ROOT, "skills"), os.path.join(tree, "skills"))
        tracked_tree.copy_tracked(tree, "lint", "hooks")  # the check, its imports, and every hooks/guard*.py
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
