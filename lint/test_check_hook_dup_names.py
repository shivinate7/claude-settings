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
RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def dup_line(rel, name, *lines):
    return FAIL + "%s: %s assigned at lines %s" % (rel, name, ", ".join(str(n) for n in lines))


class DupNameTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="dup_", dir=RUN_FOLDER)

    def write(self, rel, text):
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

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


if __name__ == "__main__":
    unittest.main()
