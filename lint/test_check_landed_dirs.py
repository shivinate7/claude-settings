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
import check_landed_dirs as landed  # noqa: E402  the reader the form-feed cases call (lint/check_landed_dirs.py)
FILES = ("landed-dirs.txt", "install.sh", "install.ps1")
RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


FROZEN_LITERAL = re.compile(r"CONFIG_FROZEN_DIRS\s*=\s*\(.*?\n\)\n", re.DOTALL)  # the literal, its comments included


def edit_frozen_literal(make):
    """An edit that rewrites the CONFIG_FROZEN_DIRS literal in hooks/guard_frozen.py: `make(literal)` gives its new text."""
    def edit(tree):
        path = os.path.join(tree, "hooks", "guard_frozen.py")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        m = FROZEN_LITERAL.search(text)
        assert m, "the defect's anchor moved: no CONFIG_FROZEN_DIRS literal in hooks/guard_frozen.py"
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text[:m.start()] + make(m.group(0)) + text[m.end():])
    return edit


def move_frozen_dirs_to_sibling(tree):
    """Cut the CONFIG_FROZEN_DIRS literal (its comments included) out of whichever hooks/guard*.py
    holds it, and write it to a new sibling module. The check must still find it there: a moved
    literal is not a drift. The holder is searched for, not named, so the literal may sit in
    guard.py or in any guard_<family>.py."""
    for path in sorted(glob.glob(os.path.join(tree, "hooks", "guard*.py"))):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        m = FROZEN_LITERAL.search(text)
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

    def test_a_commented_out_guard_entry_is_not_counted(self):
        # Why: a commented-out os.path.normcase("...") line in CONFIG_FROZEN_DIRS is no frozen dir, so the check
        # must not count it. A regex over the literal counts it; a read of the Python tuple does not.
        result = run_in_copy(edit_file("hooks/guard_frozen.py", "CONFIG_FROZEN_DIRS = (\n",
                                       'CONFIG_FROZEN_DIRS = (\n    # os.path.normcase("newdir"),\n'))
        self.assertEqual(result.returncode, 0,
                         "a commented-out entry was counted as a frozen dir: %s" % result.stderr)

    def test_an_unparseable_guard_source_is_refused_with_its_message(self):
        # Why: a guard file the reader cannot parse must stop the check, not pass with the literal unread.
        result = run_in_copy(add_file("hooks/guard_broken.py", "def (\n"))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("could not parse the guard source", result.stderr)

    def test_a_missing_frozen_dirs_literal_is_refused_with_its_message(self):
        # Why: with no literal there is nothing to compare the manifest against, so the check must refuse.
        result = run_in_copy(edit_file("hooks/guard_frozen.py", "CONFIG_FROZEN_DIRS = (\n",
                                       "CONFIG_FROZEN_DIRS_RENAMED = (\n"))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("could not find a CONFIG_FROZEN_DIRS = (...) literal to parse", result.stderr)

    def test_a_frozen_dirs_value_that_is_not_a_tuple_is_refused_with_its_message(self):
        # Why: the reader reads the entries of a tuple literal; a list has no tuple to read, so the check must refuse.
        result = run_in_copy(edit_frozen_literal(lambda literal: 'CONFIG_FROZEN_DIRS = ["hooks"]\n'))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("CONFIG_FROZEN_DIRS is not a tuple literal", result.stderr)

    def test_a_frozen_dirs_entry_that_is_not_normcase_is_refused_with_its_message(self):
        # Why: a bare string entry is not the normcase form the guard matches on, so the reader must refuse it.
        result = run_in_copy(edit_file("hooks/guard_frozen.py", 'os.path.normcase("lint"),', '"lint",'))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("has an entry that is not os.path.normcase", result.stderr)

    def assert_refused_loudly(self, result, cause):
        # A refusal is the check's own FAIL line, not a traceback from a crash.
        self.assertEqual(result.returncode, 1, "%s passed the check: %s" % (cause, result.stdout))
        self.assertIn("check_landed_dirs: FAIL", result.stderr, "%s was not refused with the check's message: %s"
                      % (cause, result.stderr))
        self.assertIn("CONFIG_FROZEN_DIRS", result.stderr, "the refusal does not name the frozen dirs: %s" % result.stderr)

    def test_a_second_frozen_dirs_literal_is_refused_loudly(self):
        # Why: two literals of one name leave the reader to pick one, and a guard that reads the other goes unchecked.
        result = run_in_copy(edit_frozen_literal(lambda literal: literal + literal))
        self.assert_refused_loudly(result, "a second CONFIG_FROZEN_DIRS literal")

    def test_an_augmented_frozen_dirs_assignment_is_refused_loudly(self):
        # Why: += changes the frozen set after the literal, and a reader that reads only the literal misses the change.
        result = run_in_copy(edit_frozen_literal(
            lambda literal: literal + 'CONFIG_FROZEN_DIRS += (os.path.normcase("newdir"),)\n'))
        self.assert_refused_loudly(result, "a CONFIG_FROZEN_DIRS += after the literal")

    def test_an_append_to_frozen_dirs_inside_an_if_is_refused_loudly(self):
        # Why: an append under an if changes the frozen set on some platforms only, and the reader must not skip it.
        result = run_in_copy(edit_frozen_literal(
            lambda literal: literal + 'if os.name:\n    CONFIG_FROZEN_DIRS.append(os.path.normcase("newdir"))\n'))
        self.assert_refused_loudly(result, "an append to CONFIG_FROZEN_DIRS inside an if")


GUARD_LITERAL ='CONFIG_FROZEN_DIRS = (\n    os.path.normcase("hooks"),\n    os.path.normcase("lint"),\n)\n'


class GuardTupleReadTests(unittest.TestCase):
    """The reader finds the literal by a line number, so a character that ends a line for str.splitlines but not for the
    parser must not move the body or the offset of the literal."""

    def assert_reads_the_same_tuple(self, head, plain_head):
        entries, body, _ = landed.find_guard_tuple(plain_head + GUARD_LITERAL, "CONFIG_FROZEN_DIRS")
        text = head + GUARD_LITERAL
        got_entries, got_body, start = landed.find_guard_tuple(text, "CONFIG_FROZEN_DIRS")
        self.assertEqual(got_entries, entries, "the entries differ when the head holds %r" % head)
        self.assertEqual(got_body, body, "the body differs when the head holds %r: %r" % (head, got_body))
        self.assertEqual(text[start:start + len(GUARD_LITERAL)], GUARD_LITERAL,
                         "the offset does not point at the literal when the head holds %r" % head)

    def test_a_form_feed_before_the_literal_reads_the_same_tuple(self):
        # Why: a form feed ends a line for str.splitlines but not for the parser, so the body and the offset shift.
        self.assert_reads_the_same_tuple("x = 1\x0c\n", "x = 1\n")

    def test_a_line_separator_in_a_comment_before_the_literal_reads_the_same_tuple(self):
        # Why: U+2028 ends a line for str.splitlines but not for the parser, so the same shift follows.
        self.assert_reads_the_same_tuple("# a b\n", "# a b\n")


RECORD_PATH =os.path.join(ROOT, "docs", "decisions", "builders-cannot-edit-tests.md")
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


def first_paragraph(section):
    """The lines of `section` before its first bullet. The home sentence is this paragraph."""
    lines = []
    for line in section.split("\n"):
        if line.startswith("- "):
            break
        lines.append(line)
    return "\n".join(lines).strip()


class HelperHomeRecordTests(unittest.TestCase):

    def home_section(self):
        # Why: a builder reads the record for where a helper goes. Each test reads that one section only,
        # so no other line of the record can satisfy it.
        with open(RECORD_PATH, encoding="utf-8") as f:
            section = record_section(f.read(), HELPER_HOME_HEADING)
        self.assertIsNotNone(section, "the decision record has no '%s' section" % HELPER_HOME_HEADING)
        return section

    def test_the_home_sentence_names_the_testing_folder_and_the_author(self):
        # Why: the home sentence is the paragraph before the first bullet. A testing/ mention in a bullet is no home.
        home = first_paragraph(self.home_section())
        self.assertIn("testing/", home, "the home sentence does not name the testing/ folder")
        self.assertIn("test-author writes it", home, "the home sentence does not say a test-author writes the helper")
        self.assertIn("private to one test", home,
                      "the home sentence does not say a helper private to one test is one")
        self.assertIn("stays inside that test file", home,
                      "the home sentence does not say a private helper stays inside that test file")

    def test_a_bullet_says_testing_is_not_installed(self):
        # Why: testing/ is not landed, so ~/.claude has no testing/ and a helper there is no install concern.
        bullets = [line for line in self.home_section().split("\n") if line.startswith("- ")]
        self.assertTrue(any("not installed" in line for line in bullets),
                        "no bullet in the section says testing/ is not installed")

    def test_the_section_names_no_underscore_home(self):
        # Why: the underscore _test_<name>.py home was dropped, so the section must not name it anywhere.
        self.assertNotIn("_test_", self.home_section(), "the section still names the underscore _test_ home")


if __name__ == "__main__":
    unittest.main()
