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
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
FILES = ("landed-dirs.txt", "install.sh", "install.ps1")
RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


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
    tree = tempfile.mkdtemp(prefix="landed_dirs_case_", dir=RUN_FOLDER)
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


def add_file(rel, text):
    """An edit that writes one file into the copy at `rel` (repo-relative, `/`-separated)."""
    def edit(tree):
        path = os.path.join(tree, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    return edit


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

    def test_file_in_a_subfolder_of_a_landed_folder_fails(self):
        # Why: install.sh's land_dir lands only the top-level files of a landed folder, so a file under
        # hooks/testdata/ never reaches ~/.claude. The check must refuse it, not pass it.
        result = run_in_copy(add_file("hooks/testdata/fixture.txt", "case\n"))
        self.assertEqual(result.returncode, 1,
                         "a file in hooks/testdata/, a subfolder of landed hooks/, passed the check: %s" % result.stdout)
        self.assertIn("fixture.txt", result.stderr)

    def test_file_at_the_top_of_a_landed_folder_still_passes(self):
        # Why: land_dir lands the top-level files of a landed folder, so the nested rule must not refuse them.
        result = run_in_copy(add_file("hooks/landed_probe.txt", "case\n"))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_file_in_a_subfolder_of_an_unlanded_folder_still_passes(self):
        # Why: testing/ is not a landed folder, so a subfolder there is no landing concern.
        result = run_in_copy(add_file("testing/nested/probe.txt", "case\n"))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_file_in_a_skill_subfolder_still_passes(self):
        # Why: land_skills_dir links each skills/<name>/ whole, so a file under a skill's subfolder is landed with it.
        def edit(tree):
            skills = os.path.join(tree, "skills")
            skill = next(n for n in sorted(os.listdir(skills)) if os.path.isfile(os.path.join(skills, n, "SKILL.md")))
            add_file("skills/%s/refs/probe.md" % skill, "case\n")(tree)
        result = run_in_copy(edit)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_file_in_a_pytest_cache_under_a_landed_folder_passes(self):
        # Why: .pytest_cache is a test tool's cache, a build leftover like __pycache__, never a shipped file.
        result = run_in_copy(add_file("hooks/.pytest_cache/v/cache/lastfailed", "case\n"))
        self.assertEqual(result.returncode, 0,
                         "a file in hooks/.pytest_cache/, a tool cache, was refused as a nested file: %s" % result.stderr)

    def test_file_in_a_mypy_cache_under_a_landed_folder_passes(self):
        # Why: .mypy_cache is a type checker's cache, a build leftover like __pycache__, never a shipped file.
        result = run_in_copy(add_file("hooks/.mypy_cache/3.11/guard.data.json", "case\n"))
        self.assertEqual(result.returncode, 0,
                         "a file in hooks/.mypy_cache/, a tool cache, was refused as a nested file: %s" % result.stderr)

    def test_file_in_a_ruff_cache_under_a_landed_folder_passes(self):
        # Why: .ruff_cache is a linter's cache, a build leftover like __pycache__, never a shipped file.
        result = run_in_copy(add_file("hooks/.ruff_cache/0.1.0/probe.msgpack", "case\n"))
        self.assertEqual(result.returncode, 0,
                         "a file in hooks/.ruff_cache/, a tool cache, was refused as a nested file: %s" % result.stderr)

    def test_file_in_a_pycache_under_a_landed_folder_still_passes(self):
        # Why: __pycache__ is already pruned; this pins that existing filter, so the cache fix cannot drop it.
        result = run_in_copy(add_file("hooks/__pycache__/guard.cpython-311.pyc", "case\n"))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_file_in_a_dot_folder_that_is_no_cache_still_fails(self):
        # Why: the cache names are an allow list. A fix that skips every dot-folder would let a hidden shipped
        # file under a landed folder pass, so a dot-folder that is no cache must still be refused.
        result = run_in_copy(add_file("hooks/.notes/probe.txt", "case\n"))
        self.assertEqual(result.returncode, 1,
                         "a file in hooks/.notes/, a dot-folder that is no cache, passed the check: %s" % result.stdout)
        self.assertIn("probe.txt", result.stderr)

    def test_a_helper_in_a_subfolder_is_refused_and_named(self):
        # Why: a subfolder of a landed folder stays refused, and the refusal names the file. The wording of the
        # message is not pinned here: the helper home is the testing/ folder, which the record names.
        result = run_in_copy(add_file("hooks/test_support/x.py", "case\n"))
        self.assertEqual(result.returncode, 1,
                         "a helper in hooks/test_support/, a subfolder of landed hooks/, passed the check: %s" % result.stdout)
        self.assertIn("hooks/test_support/x.py", result.stderr,
                      "the refusal does not name the refused helper: %s" % result.stderr)

    def test_a_file_at_the_testing_folder_is_not_reported(self):
        # Why: testing/ holds the shared test helpers (tracked_tree.py), and landed-dirs.txt does not list it,
        # so the check never reports a file there.
        result = run_in_copy(add_file("testing/x.py", "case\n"))
        self.assertIn("check_landed_dirs: ok", result.stdout,
                      "the check did not reach its ok line: %s" % result.stderr)
        self.assertEqual(result.returncode, 0, "a file at testing/x.py was reported: %s" % result.stderr)

    def test_a_file_in_a_testing_subfolder_is_not_reported(self):
        # Why: the testing/ folder is not landed, so a subfolder there is no landing concern either.
        result = run_in_copy(add_file("testing/sub/y.py", "case\n"))
        self.assertIn("check_landed_dirs: ok", result.stdout,
                      "the check did not reach its ok line: %s" % result.stderr)
        self.assertEqual(result.returncode, 0, "a file at testing/sub/y.py was reported: %s" % result.stderr)

    def test_a_helper_in_a_test_support_subfolder_still_fails_the_check(self):
        # Why: the verdict must not widen. A helper in a subfolder of a landed folder stays refused.
        result = run_in_copy(add_file("hooks/test_support/cost_probe.py", "case\n"))
        self.assertEqual(result.returncode, 1,
                         "a helper in hooks/test_support/ passed the check, so the verdict widened: %s" % result.stdout)
        self.assertIn("cost_probe.py", result.stderr, "the refusal does not name the helper: %s" % result.stderr)


RECORD_PATH = os.path.join(ROOT, "docs", "decisions", "builders-cannot-edit-tests.md")
HELPER_HOME_HEADING = "## Where a test-support helper lives"


def record_section(text, heading):
    """The lines under `heading`, up to the next `## ` heading. None when the record has no such heading."""
    lines = text.split("\n")
    starts = [i for i, line in enumerate(lines) if line.rstrip() == heading]
    if not starts:
        return None
    start = starts[0] + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start:end])


class HelperHomeRecordTests(unittest.TestCase):

    def test_the_decision_record_names_the_testing_home_for_a_test_helper(self):
        # Why: a builder reads the record for where a helper goes. The test reads that one section only,
        # so no other line of the record can satisfy it.
        with open(RECORD_PATH, encoding="utf-8") as f:
            section = record_section(f.read(), HELPER_HOME_HEADING)
        self.assertIsNotNone(section, "the decision record has no '%s' section" % HELPER_HOME_HEADING)
        self.assertIn("testing/", section,
                      "the '%s' section does not name the testing/ folder as the home" % HELPER_HOME_HEADING)
        self.assertIn("test-author writes it", section,
                      "the '%s' section does not say a test-author writes the helper" % HELPER_HOME_HEADING)
        self.assertIn("private to one test", section,
                      "the '%s' section does not say a helper private to one test is one" % HELPER_HOME_HEADING)
        self.assertIn("stays inside that test", section,
                      "the '%s' section does not say a private helper stays inside that test" % HELPER_HOME_HEADING)
        self.assertNotIn("_test_", section,
                         "the '%s' section still names the underscore _test_ home" % HELPER_HOME_HEADING)


if __name__ == "__main__":
    unittest.main()
