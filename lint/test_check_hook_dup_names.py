#!/usr/bin/env python3
"""Cases for lint/check_hook_dup_names.py. Standard library only.

    python3 lint/test_check_hook_dup_names.py

A hook module that assigns one top-level name twice keeps only the second value at import. A second
top-level RECORD_REASON replaces the first refusal text, and a wrong refusal sends the reader to the
wrong remedy.

Each case writes a fixture root under this run's folder (test-temp-standard, lint/_test_temp.py),
then runs the real script with --root on it. CHECK_HOOK_DUP_NAMES_UNDER_TEST overrides the module
path. The sweep of old run folders is proved in lint/test_find_copies.py.

A pass case also writes hooks/y.py with a real duplicate. The run must flag that sibling and nothing
else, so a script that reads no files cannot pass the case.

The cross-file cases (26 to 35) scan tests/guard/ sections. Each section's first line is
`# section <n>`, so its first statement sits on line 2. A name that two section files bind at
module level fails, with the FAIL line `NAME assigned at FILE:LINE and FILE:LINE`, the first
section in run order first. Two exceptions pass: a binding that reads its own name (an
accumulator), and FAMILY or TEMP_DIR, which hooks/test_guard.py binds and each section sets.
A rebind inside one section file is not counted. A pass case also writes a real clash in
tests/guard/, so a scan that reads no section cannot pass it. setUp writes one default section,
tests/guard/s00001-base.py, so the cases above it keep a section folder that holds a section.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

MODULE = os.environ.get("CHECK_HOOK_DUP_NAMES_UNDER_TEST") or os.path.join(HERE, "check_hook_dup_names.py")
FAIL = "check_hook_dup_names: FAIL: "
UNKNOWN = "check_hook_dup_names: UNKNOWN, "
ALLOW = "lint/hook_dup_names_allow.json"
SIBLING = "hooks/y.py"
SIBLING_LINE = FAIL + "hooks/y.py: Z assigned at lines 1, 2"
GUARD_BASE = "s00001-base.py"  # setUp writes it: it binds BASE, which no case reads
GUARD_SIBLING_A = "tests/guard/s09000-sib-a.py"
GUARD_SIBLING_B = "tests/guard/s09100-sib-b.py"
GUARD_SIBLING_LINE = FAIL + "GUARD_SIBLING assigned at %s:2 and %s:2" % (GUARD_SIBLING_A, GUARD_SIBLING_B)
RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def dup_line(rel, name, *lines):
    return FAIL + "%s: %s assigned at lines %s" % (rel, name, ", ".join(str(n) for n in lines))


def guard_dup(name, first, second):
    """The FAIL line for a name two section files bind: `first` and `second` are FILE:LINE."""
    return FAIL + "%s assigned at %s and %s" % (name, first, second)


class DupNameTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="dup_", dir=RUN_FOLDER)
        self.with_base()

    def write(self, rel, text, root=None):
        path = os.path.join(root or self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def write_section(self, fname, number, body, root=None):
        self.write("tests/guard/" + fname, "# section %d\n%s" % (number, body), root=root)

    def with_base(self, root=None):
        self.write_section(GUARD_BASE, 1, "BASE = 1\n", root=root)

    def with_clean_hook(self):
        self.write("hooks/clean.py", "CLEAN = 1\n")

    def with_guard_sibling(self):
        self.write_section("s09000-sib-a.py", 9000, "GUARD_SIBLING = 1\n")
        self.write_section("s09100-sib-b.py", 9100, "GUARD_SIBLING = 2\n")

    def assert_only_guard_sibling(self, rc, out):
        self.assertEqual(rc, 1, "the sibling clash in tests/guard/ must fail the run\n" + out)
        self.assertEqual(self.fails(out), [GUARD_SIBLING_LINE],
                         "expected the sibling FAIL line and no other: the subject passes or the sibling is unread\n" + out)

    def check(self, root=None):
        cmd = [sys.executable, MODULE, "--root", root or self.root]
        r = subprocess.run(cmd, cwd=RUN_FOLDER, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return r.returncode, r.stdout + r.stderr

    def fails(self, out):
        return [ln for ln in out.splitlines() if ln.startswith(FAIL)]

    def unknowns(self, out):
        return [ln for ln in out.splitlines() if ln.startswith(UNKNOWN)]

    def with_sibling(self):
        self.write(SIBLING, "Z = 1\nZ = 2\n")

    def assert_only_sibling(self, rc, out):
        self.assertEqual(rc, 1, "the sibling duplicate in hooks/y.py must fail the run\n" + out)
        self.assertEqual(self.fails(out), [SIBLING_LINE],
                         "expected the sibling FAIL line and no other: the subject passes or the sibling is unread\n" + out)

    def assert_unknown(self, rc, out, token):
        self.assertEqual(rc, 2, "an unreadable input must exit 2\n" + out)
        lines = self.unknowns(out)
        self.assertTrue(any(token in ln for ln in lines),
                        "no UNKNOWN line naming %r\n%s" % (token, out))
        self.assertNotIn("Traceback", out, "an unreadable input must not crash\n" + out)

    def test_0_control_fixture_is_written_under_the_run_folder(self):
        # Green on the old code: it shows the harness writes its fixtures under this run's folder.
        self.write("hooks/x.py", "A = 1\n")
        path = os.path.join(self.root, "hooks", "x.py")
        self.assertTrue(path.startswith(RUN_FOLDER + os.sep), "fixture left the run folder: " + path)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "A = 1\n", "fixture text did not read back")

    def test_1_name_assigned_twice_fails(self):
        self.write("hooks/x.py", "NAME = 1\nOTHER = 2\nNAME = 3\n")
        rc, out = self.check()
        self.assertEqual(rc, 1, "NAME assigned at lines 1 and 3 was not reported\n" + out)
        self.assertEqual(self.fails(out), [dup_line("hooks/x.py", "NAME", 1, 3)], out)

    def test_2_annotated_then_plain_assign_fails(self):
        self.write("hooks/x.py", "NAME: int = 1\nNAME = 2\n")
        rc, out = self.check()
        self.assertEqual(rc, 1, "an AnnAssign with a value and a plain Assign were not counted together\n" + out)
        self.assertEqual(self.fails(out), [dup_line("hooks/x.py", "NAME", 1, 2)], out)

    def test_3_tuple_unpack_duplicate_names_only_the_shared_name(self):
        self.write("hooks/x.py", "A, B = 1, 2\nA = 3\n")
        rc, out = self.check()
        self.assertEqual(rc, 1, "A from a tuple target and a plain Assign was not reported\n" + out)
        self.assertEqual(self.fails(out), [dup_line("hooks/x.py", "A", 1, 2)],
                         "expected A alone: B is assigned once and must not be named\n" + out)

    def test_4_list_and_starred_targets_are_counted(self):
        self.write("hooks/x.py", "[C, *D] = (1, 2, 3)\nD = 4\nE, *F = (1, 2)\nF = 5\n")
        rc, out = self.check()
        self.assertEqual(rc, 1, "a Starred name inside a List or Tuple target was not counted\n" + out)
        self.assertCountEqual(self.fails(out), [dup_line("hooks/x.py", "D", 1, 2),
                                                dup_line("hooks/x.py", "F", 3, 4)], out)

    def test_5_clean_module_passes(self):
        self.write("hooks/x.py", "A = 1\nB: int = 2\nC = (3,\n     4)\n__all__ = [\"A\"]\n")
        self.with_sibling()
        rc, out = self.check()
        self.assert_only_sibling(rc, out)

    def test_6_subscript_attribute_and_augmented_targets_pass(self):
        self.write("hooks/x.py", "WRAPPER_VALUE_FLAGS = {}\n"
                                 "WRAPPER_VALUE_FLAGS[\"timeout\"] = 1\n"
                                 "WRAPPER_VALUE_FLAGS.extra = 2\n"
                                 "COUNT = 0\n"
                                 "COUNT += 1\n")
        self.with_sibling()
        rc, out = self.check()
        self.assert_only_sibling(rc, out)

    def test_7_assignments_in_nested_scopes_do_not_count(self):
        self.write("hooks/x.py", "LIMIT = 1\n"
                                 "def f():\n"
                                 "    LIMIT = 2\n"
                                 "class K:\n"
                                 "    LIMIT = 3\n"
                                 "if True:\n"
                                 "    LIMIT = 4\n"
                                 "try:\n"
                                 "    LIMIT = 5\n"
                                 "except Exception:\n"
                                 "    pass\n"
                                 "for _ in range(1):\n"
                                 "    LIMIT = 6\n")
        self.with_sibling()
        rc, out = self.check()
        self.assert_only_sibling(rc, out)

    def test_8_bare_annotation_does_not_count(self):
        self.write("hooks/x.py", "NAME: int\nNAME = 1\n")
        self.with_sibling()
        rc, out = self.check()
        self.assert_only_sibling(rc, out)

    def test_9_names_inside_strings_and_comments_do_not_count(self):
        # Comment openers inside strings, a multi-line triple-quoted string, a triple quote inside
        # a string, and a lone apostrophe in a comment. NAME is never a top-level assignment here.
        self.write("hooks/x.py", "\n".join([
            'DOC = """',
            "NAME = 1",
            "NAME = 2",
            "# NAME = 3",
            '"""',
            'HASH = "a # not a comment, NAME = 4"',
            "QUOTE = 'it\\'s # NAME = 5'",
            "TRIPLE = '\"\"\"'",
            "# NAME = 6, and don't count it",
        ]) + "\n")
        self.with_sibling()
        rc, out = self.check()
        self.assert_only_sibling(rc, out)

    def test_10_test_modules_are_skipped(self):
        self.write("hooks/test_x.py", "NAME = 1\nNAME = 2\n")
        self.with_sibling()
        rc, out = self.check()
        self.assert_only_sibling(rc, out)

    def test_11_allowed_reassignment_passes(self):
        self.write("hooks/x.py", "NAME = 1\nNAME = 2\n")
        self.write(ALLOW, json.dumps({"hooks/x.py": {"NAME": "the second assign overrides the first on purpose"}}))
        self.with_sibling()
        rc, out = self.check()
        self.assert_only_sibling(rc, out)

    def test_12_empty_allow_reason_fails(self):
        self.write("hooks/x.py", "NAME = 1\nNAME = 2\n")
        self.write(ALLOW, json.dumps({"hooks/x.py": {"NAME": ""}}))
        rc, out = self.check()
        self.assertEqual(rc, 1, "an allowance with an empty reason passed the run\n" + out)
        self.assertTrue(any(ALLOW in ln and "reason" in ln for ln in self.fails(out)),
                        "no FAIL line naming the allow file and the empty reason\n" + out)

    def test_13_stale_allowance_for_an_unduplicated_name_fails(self):
        self.write("hooks/x.py", "NAME = 1\n")
        self.write(ALLOW, json.dumps({"hooks/x.py": {"NAME": "reason"}}))
        rc, out = self.check()
        self.assertEqual(rc, 1, "an allowance for a name that is not duplicated passed the run\n" + out)
        lines = self.fails(out)
        self.assertEqual(len(lines), 1, out)
        self.assertTrue("stale" in lines[0] and "NAME" in lines[0],
                        "the one FAIL line must call the NAME allowance stale\n" + out)

    def test_14_stale_allowance_for_a_file_that_is_gone_fails(self):
        self.write("hooks/x.py", "A = 1\n")
        self.write(ALLOW, json.dumps({"hooks/gone.py": {"NAME": "reason"}}))
        rc, out = self.check()
        self.assertEqual(rc, 1, "an allowance for a file that is gone passed the run\n" + out)
        lines = self.fails(out)
        self.assertEqual(len(lines), 1, out)
        self.assertTrue("stale" in lines[0] and "hooks/gone.py" in lines[0],
                        "the one FAIL line must call the hooks/gone.py allowance stale\n" + out)

    def test_15_missing_allow_file_means_no_allowances(self):
        self.write("hooks/x.py", "NAME = 1\nNAME = 2\n")
        rc, out = self.check()
        self.assertEqual(rc, 1, "a duplicate with no allow file passed the run\n" + out)
        self.assertEqual(self.fails(out), [dup_line("hooks/x.py", "NAME", 1, 2)], out)

    def test_16_malformed_allow_file_is_unknown(self):
        self.write("hooks/x.py", "A = 1\n")
        self.write(ALLOW, "{not json")
        rc, out = self.check()
        self.assert_unknown(rc, out, "hook_dup_names_allow.json")

    def test_17_unparseable_module_is_unknown(self):
        self.write("hooks/bad.py", "def broken(:\n")
        rc, out = self.check()
        self.assert_unknown(rc, out, "bad.py")

    def test_18_root_without_hooks_is_unknown(self):
        self.write("lint/README.md", "no hooks here\n")
        rc, out = self.check()
        self.assert_unknown(rc, out, "hooks")

    def test_19_pre_fix_shape_names_the_second_record_reason(self):
        # A second top-level RECORD_REASON after a function replaces the first refusal text. CI has no
        # copy of a real hooks/guard_merge.py to read, so this module is built with the same shape.
        self.write("hooks/guard_merge.py", "\n".join([
            'RECORD_WRITER_TIER = "triage"',
            'DEFAULT_RECORD_BRANCH = "roadmap"',
            "RECORD_REASON = (",
            '    "first refusal text"',
            ")",
            "def helper():",
            "    return RECORD_REASON",
            'RECORD_REVIEWER_ROLES = ("reviewer",)',
            "RECORD_REASON = (",
            '    "second refusal text"',
            ")",
        ]) + "\n")
        rc, out = self.check()
        self.assertEqual(rc, 1, "the second RECORD_REASON was not reported\n" + out)
        self.assertEqual(self.fails(out), [dup_line("hooks/guard_merge.py", "RECORD_REASON", 3, 9)], out)

    def test_20_full_size_module_names_the_late_duplicate(self):
        lines = ["N%d = %d" % (i, i) for i in range(400)] + ["N0 = 99"]
        self.write("hooks/x.py", "\n".join(lines) + "\n")
        rc, out = self.check()
        self.assertEqual(rc, 1, "a duplicate at line 401 of a 401-line module was not reported\n" + out)
        self.assertEqual(self.fails(out), [dup_line("hooks/x.py", "N0", 1, 401)], out)

    def test_21_todays_repo_hooks_pass(self):
        non_test = [p for p in glob.glob(os.path.join(ROOT, "hooks", "*.py"))
                    if not os.path.basename(p).startswith("test_")]
        self.assertTrue(non_test, "scope: the checkout's hooks/ has no non-test module to check")
        rc, out = self.check(root=ROOT)
        self.assertEqual(rc, 0, "today's hooks/ must pass\n" + out)
        self.assertEqual(out, "", "a clean run prints nothing\n" + out)

    def test_22_empty_allowance_for_a_missing_file_is_stale(self):
        self.write("hooks/x.py", "A = 1\n")
        self.write(ALLOW, json.dumps({"hooks/gone.py": {}}))
        rc, out = self.check()
        self.assertEqual(rc, 1, "an allowance with no names for a missing file passed the run\n" + out)
        lines = self.fails(out)
        self.assertEqual(len(lines), 1, out)
        self.assertTrue("stale" in lines[0] and "hooks/gone.py" in lines[0],
                        "the one FAIL line must call the hooks/gone.py allowance stale\n" + out)

    def test_23_root_path_with_brackets_is_still_scanned(self):
        # The root's path must reach the scan as a literal path, not as a glob pattern.
        root = os.path.join(self.root, "r[x]")
        self.with_base(root=root)
        self.write("hooks/m.py", "NAME = 1\nNAME = 2\n", root=root)
        rc, out = self.check(root=root)
        self.assertEqual(rc, 1, "a duplicate under a root named r[x] went unread\n" + out)
        self.assertEqual(self.fails(out), [dup_line("hooks/m.py", "NAME", 1, 2)], out)

    def test_24_empty_hooks_folder_is_unknown(self):
        os.makedirs(os.path.join(self.root, "hooks"))
        rc, out = self.check()
        self.assert_unknown(rc, out, "hooks")

    def test_25_hooks_with_only_test_modules_is_unknown(self):
        self.write("hooks/test_x.py", "NAME = 1\nNAME = 2\n")
        rc, out = self.check()
        self.assert_unknown(rc, out, "hooks")

    def test_26_two_sections_bind_one_name_fail(self):
        self.with_clean_hook()
        self.write_section("s00100-a.py", 100, 'LANE_PROMPT = "a"\n')
        self.write_section("s00200-b.py", 200, 'LANE_PROMPT = "b"\n')
        rc, out = self.check()
        self.assertEqual(rc, 1, "LANE_PROMPT bound in two section files was not reported\n" + out)
        self.assertEqual(self.fails(out), [guard_dup("LANE_PROMPT", "tests/guard/s00100-a.py:2",
                                                     "tests/guard/s00200-b.py:2")], out)

    def test_27_def_in_one_section_and_assign_in_another_fail(self):
        self.with_clean_hook()
        self.write_section("s00100-a.py", 100, "def LANE_PROMPT():\n    return 'a'\n")
        self.write_section("s00200-b.py", 200, 'LANE_PROMPT = "b"\n')
        rc, out = self.check()
        self.assertEqual(rc, 1, "a def in one section and an assign in another were not reported\n" + out)
        self.assertEqual(self.fails(out), [guard_dup("LANE_PROMPT", "tests/guard/s00100-a.py:2",
                                                     "tests/guard/s00200-b.py:2")], out)

    def test_28_self_read_accumulator_passes(self):
        self.with_clean_hook()
        self.with_guard_sibling()
        self.write_section("s00100-a.py", 100, "LOG_CHECKS = [1]\n")
        self.write_section("s00200-b.py", 200, "LOG_CHECKS = LOG_CHECKS + [2]\n")
        self.write_section("s00300-c.py", 300, "LOG_CHECKS = LOG_CHECKS + [3]\n")
        rc, out = self.check()
        self.assert_only_guard_sibling(rc, out)

    def test_29_rebind_that_does_not_read_its_name_fails(self):
        self.with_clean_hook()
        self.write_section("s00100-a.py", 100, "LOG_CHECKS = [1]\n")
        self.write_section("s00200-b.py", 200, "LOG_CHECKS = [2]\n")
        rc, out = self.check()
        self.assertEqual(rc, 1, "a second LOG_CHECKS that does not read the first was not reported\n" + out)
        self.assertEqual(self.fails(out), [guard_dup("LOG_CHECKS", "tests/guard/s00100-a.py:2",
                                                     "tests/guard/s00200-b.py:2")], out)

    def test_30_family_and_temp_dir_may_be_set_by_sections(self):
        self.with_clean_hook()
        self.with_guard_sibling()
        self.write("hooks/test_guard.py", 'FAMILY = "misc"\nTEMP_DIR = None\n')  # the runner binds both
        self.write_section("s00100-a.py", 100, 'FAMILY = "a"\nTEMP_DIR = None\n')
        self.write_section("s00200-b.py", 200, 'FAMILY = "b"\nTEMP_DIR = "x"\n')
        rc, out = self.check()
        self.assert_only_guard_sibling(rc, out)

    def test_31_rebind_inside_one_section_is_not_counted(self):
        self.with_clean_hook()
        self.with_guard_sibling()
        self.write_section("s00100-a.py", 100, "NAME = 1\nNAME = 2\n")
        rc, out = self.check()
        self.assert_only_guard_sibling(rc, out)

    def test_32_names_in_strings_and_comments_are_not_bindings(self):
        self.with_clean_hook()
        self.with_guard_sibling()
        self.write_section("s00100-a.py", 100, "\n".join([
            'DOC = """',
            'LANE_PROMPT = "a"',
            '"""',
            "# LANE_PROMPT = \"b\", and don't count it",
            "NOTE = \"LANE_PROMPT = 'c'  # not a binding\"",
        ]) + "\n")
        self.write_section("s00200-b.py", 200, 'LANE_PROMPT = "b"\n')
        rc, out = self.check()
        self.assert_only_guard_sibling(rc, out)

    def test_33_missing_section_folder_is_unknown(self):
        self.with_clean_hook()
        shutil.rmtree(os.path.join(self.root, "tests"))
        rc, out = self.check()
        self.assert_unknown(rc, out, "guard")

    def test_34_empty_section_folder_is_unknown(self):
        self.with_clean_hook()
        os.remove(os.path.join(self.root, "tests", "guard", GUARD_BASE))
        rc, out = self.check()
        self.assert_unknown(rc, out, "guard")

    def test_35_full_size_section_set_names_first_and_last(self):
        self.with_clean_hook()
        last = 299  # 300 section files here, and the default one from setUp makes 301
        for i in range(last + 1):
            number = 100 + 10 * i
            name = "s%05d-f%03d.py" % (number, i)
            body = 'LANE_PROMPT = "%d"\n' % i if i in (0, last) else "VALUE_%03d = %d\n" % (i, i)
            self.write_section(name, number, body)
        rc, out = self.check()
        self.assertEqual(rc, 1, "LANE_PROMPT in the first and the last of 300 section files was not reported\n" + out)
        self.assertEqual(self.fails(out), [guard_dup("LANE_PROMPT", "tests/guard/s00100-f000.py:2",
                                                     "tests/guard/s03090-f299.py:2")], out)


if __name__ == "__main__":
    unittest.main()
