#!/usr/bin/env python3
"""Cases for lint/check_hook_output_pins.py. Standard library only.

    python3 lint/test_check_hook_output_pins.py

A hook names the text it prints in PRINTED_LINES. A test file that starts with that text holds a
literal copy of the printed line, and goes stale when the line changes. A declaration the check cannot
read is UNKNOWN: exit 2, never a pass.

Each case writes a fixture root under this run's folder (test-temp-standard, lint/_test_temp.py).
find_pins is read in process, and main is run as a script for the exit codes.
CHECK_HOOK_OUTPUT_PINS_UNDER_TEST overrides the module path, so a stub run can stand in for the check
(lint/red_run_stub_test.py).

Most cases plant one real pin beside the subject, so a check that finds nothing still fails them.
"""
import ast
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

MODULE = os.path.abspath(os.environ.get("CHECK_HOOK_OUTPUT_PINS_UNDER_TEST")
                         or os.path.join(HERE, "check_hook_output_pins.py"))
# Fixture text that no real hook prints, so a literal of it in this file is never a pin of the repo.
PREFIX = "Fixture line: "
FLAG = "Fixture flag: "
HOOK = "hooks/local_time.py"
SIBLING = "lint/test_sibling.py"
HOOK_TEXT = 'TIME_PREFIX = "%s"\nPRINTED_LINES = ("TIME_PREFIX",)\n' % PREFIX
REAL_PIN = 'TIME_LINE = "%s2026-07-04 10:30 CDT (UTC-05:00)\\n"' % PREFIX
RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder
_LOADED = []  # the check module, loaded on first use


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def load_check():
    """The check at MODULE. Loaded on first use, so a load error fails only the case that asked for it."""
    if not _LOADED:
        spec = importlib.util.spec_from_file_location("check_hook_output_pins_under_test", MODULE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _LOADED.append(mod)
    return _LOADED[0]


def pin(test, line, hook=HOOK, name="TIME_PREFIX"):
    return {"test": test, "line": line, "hook": hook, "name": name}


def filler(n):
    return ["F%d = %d" % (i, i) for i in range(n)]


def top_value(tree, name):
    """The value node of the module-level assignment to `name`, or None."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node.value
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return node.value
    return None


def printed_names(tree):
    """The values of the PRINTED_LINES tuple or list, or None when the module declares neither."""
    value = top_value(tree, "PRINTED_LINES")
    if not isinstance(value, (ast.Tuple, ast.List)):
        return None
    return [e.value for e in value.elts if isinstance(e, ast.Constant)]


def str_value(tree, name):
    """The text of a module-level name bound to a plain str constant, or None."""
    value = top_value(tree, name)
    return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None


class PinCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="pins_", dir=RUN_FOLDER)

    def write_lines(self, rel, lines):
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")

    def hook(self):
        self.write_lines(HOOK, HOOK_TEXT.splitlines())

    def plant_sibling(self):
        """One real pin in a lint test. A case that expects a result beside it fails when the check finds nothing."""
        self.write_lines(SIBLING, [REAL_PIN])
        return pin(SIBLING, 1)

    def find(self, root=None):
        return load_check().find_pins(root or self.root)

    def run_main(self, root=None):
        cmd = [sys.executable, MODULE, "--root", root or self.root]
        r = subprocess.run(cmd, cwd=RUN_FOLDER, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return r.returncode, r.stdout + r.stderr

    def real_tree(self, rel):
        """The ast of a file in this repo. Scope first: the file must exist before its text is read."""
        path = os.path.join(ROOT, *rel.split("/"))
        self.assertTrue(os.path.isfile(path), "scope: no %s under %s" % (rel, ROOT))
        with open(path, encoding="utf-8") as f:
            return ast.parse(f.read(), filename=path)

    def assert_unknown(self, rc, out, *names):
        # Exit 2 alone is not enough: a missing module also exits 2, so the output must name each input.
        self.assertEqual(rc, 2, "an unreadable input must exit 2, never pass:\n" + out)
        for name in names:
            self.assertIn(name, out, "exit 2 does not name %s:\n%s" % (name, out))
        self.assertNotIn("Traceback", out, "an unreadable input must not crash:\n" + out)

    def assert_unknown_declaration(self, *names):
        """The root's declaration cannot be read: find_pins raises Unknown, and main exits 2 naming each of names."""
        self.assertRaises(load_check().Unknown, self.find)
        rc, out = self.run_main()
        self.assert_unknown(rc, out, *names)

    def test_0_control_fixture_is_written_under_the_run_folder(self):
        # Green on any check: it shows the fixture lands under this run's folder and reads back.
        self.write_lines("lint/test_x.py", ["A = 1"])
        path = os.path.join(self.root, "lint", "test_x.py")
        self.assertTrue(path.startswith(RUN_FOLDER + os.sep), "fixture left the run folder: " + path)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "A = 1\n", "fixture text did not read back")

    def test_1_planted_literal_copy_in_a_lint_test_is_found(self):
        self.hook()
        self.write_lines("lint/test_planted.py", ["import os", REAL_PIN])
        self.assertEqual(self.find(), [pin("lint/test_planted.py", 2)],
                         "the literal copy of the printed line in lint/test_planted.py was not found")

    def test_1b_pins_are_sorted_by_test_then_line(self):
        self.hook()
        self.write_lines("lint/test_beta.py", ["X = 1", REAL_PIN, "Y = 2", "Z = 3", "W = 4", "V = 5", REAL_PIN])
        self.write_lines("hooks/test_shared_names.py", ["Q = 0", "R = 1", REAL_PIN])
        self.assertEqual(self.find(), [pin("hooks/test_shared_names.py", 3),
                                       pin("lint/test_beta.py", 2),
                                       pin("lint/test_beta.py", 7)],
                         "pins are not sorted by (test, line)")

    def test_1c_pin_on_the_last_line_of_a_full_size_file_is_found(self):
        self.hook()
        self.write_lines("lint/test_big.py", filler(400) + [REAL_PIN])
        self.assertEqual(self.find(), [pin("lint/test_big.py", 401)],
                         "a pin at line 401 of a 401-line test file was not found")

    def test_1d_leading_space_on_the_body_is_ignored_for_a_constant_without_one(self):
        # The body is lstripped like the constant: a body that starts with a space still pins.
        self.hook()
        self.write_lines("lint/test_lead.py", ['LEAD = " %s2026-07-04 10:30 CDT (UTC-05:00)"' % PREFIX])
        self.assertEqual(self.find(), [pin("lint/test_lead.py", 1)],
                         "a body with a leading space was not read as a pin of a constant without one")

    def test_1e_leading_space_on_the_constant_is_ignored_for_a_body_with_one(self):
        # The constant is lstripped as before, so a constant with leading spaces matches a body with one.
        self.write_lines(HOOK, ['TIME_PREFIX = "  %s"' % PREFIX, 'PRINTED_LINES = ("TIME_PREFIX",)'])
        self.write_lines("lint/test_lead.py", ['LEAD = " %s2026-07-04 10:30 CDT (UTC-05:00)"' % PREFIX])
        self.assertEqual(self.find(), [pin("lint/test_lead.py", 1)],
                         "a body with a leading space was not read as a pin of a constant with leading spaces")

    def test_2_incident_shape_pin_in_test_shared_names_is_found(self):
        # The shape of the TIME_LINE pin in hooks/test_shared_names.py, at its real line.
        self.hook()
        self.write_lines("hooks/test_shared_names.py", filler(63) + [REAL_PIN])
        self.assertEqual(self.find(), [pin("hooks/test_shared_names.py", 64)],
                         "the TIME_LINE pin at line 64 of hooks/test_shared_names.py was not found")

    def test_2b_lint_test_file_with_the_suffix_is_scanned(self):
        self.hook()
        self.write_lines("lint/traps_test.py", ["X = 1", REAL_PIN])
        self.assertEqual(self.find(), [pin("lint/traps_test.py", 2)],
                         "the literal copy in lint/traps_test.py was not found: *_test.py is not scanned")

    def test_2c_hooks_test_file_with_the_suffix_is_scanned(self):
        self.hook()
        self.write_lines("hooks/runner_test.py", ["Y = 1", REAL_PIN])
        self.assertEqual(self.find(), [pin("hooks/runner_test.py", 2)],
                         "the literal copy in hooks/runner_test.py was not found: *_test.py is not scanned")

    def test_3_use_of_the_constant_is_not_a_pin(self):
        self.hook()
        self.write_lines("hooks/test_shared_names.py", [
            "import local_time",
            'TIME_LINE = local_time.TIME_PREFIX + "2026-07-04 10:30 CDT (UTC-05:00)\\n"'])
        sibling = self.plant_sibling()
        self.assertEqual(self.find(), [sibling],
                         "a test that builds its line from the constant was read as a literal pin")

    def test_4_own_test_file_may_pin_its_hook_but_not_another_hooks_text(self):
        self.hook()
        self.write_lines("hooks/decision_watch.py", [
            'FLAG_PREFIX = "%s"' % FLAG, 'PRINTED_LINES = ("FLAG_PREFIX",)'])
        self.write_lines("hooks/test_local_time.py", [
            'PIN_REGEX = r"%s\\d{4}-\\d{2}"' % PREFIX,
            REAL_PIN,
            'FLAG_LINE = "%sthe judge model reported"' % FLAG])
        self.assertEqual(self.find(), [pin("hooks/test_local_time.py", 3, "hooks/decision_watch.py", "FLAG_PREFIX")],
                         "hooks/test_local_time.py may pin local_time's own text, and no other hook's text")

    def test_4b_hook_suffix_test_file_may_pin_its_own_hook_but_not_another_hooks_text(self):
        # hooks/<hook>_test.py is an own test too: exempt for its hook, scanned for every other one.
        self.hook()
        self.write_lines("hooks/decision_watch.py", [
            'FLAG_PREFIX = "%s"' % FLAG, 'PRINTED_LINES = ("FLAG_PREFIX",)'])
        self.write_lines("hooks/local_time_test.py", [
            REAL_PIN,
            'FLAG_LINE = "%sthe judge model reported"' % FLAG])
        self.assertEqual(self.find(), [pin("hooks/local_time_test.py", 2, "hooks/decision_watch.py", "FLAG_PREFIX")],
                         "hooks/local_time_test.py may pin local_time's own text, and no other hook's text")

    def test_5_docstrings_bare_strings_labels_and_comments_are_not_pins(self):
        self.hook()
        self.write_lines("hooks/test_shared_names.py", [
            '"""%s2026-07-04 10:30 CDT (UTC-05:00), the module docstring."""' % PREFIX,
            "import local_time",
            "def check_one():",
            '    """%s2026-07-04 10:30 CDT (UTC-05:00), a function docstring."""' % PREFIX,
            "    check(\"starts with '%s'\", True)" % PREFIX,
            "    # %s2026-07-04 10:30 CDT (UTC-05:00), a comment" % PREFIX,
            '    "%s2026-07-04 10:30 CDT (UTC-05:00)"' % PREFIX])
        sibling = self.plant_sibling()
        self.assertEqual(self.find(), [sibling],
                         "a docstring, a bare string statement, a mid-string label or a comment was read as a pin")

    def test_6a_comment_opener_inside_a_string_does_not_hide_a_pin(self):
        self.hook()
        self.write_lines("lint/test_traps.py", [
            'LABEL = "# %squoted label"' % PREFIX,
            'OTHER = "#"',
            REAL_PIN])
        self.assertEqual(self.find(), [pin("lint/test_traps.py", 3)],
                         "a '#' inside a string before a real pin moved the result")

    def test_6b_multi_line_string_with_the_text_mid_line_is_not_a_pin(self):
        self.hook()
        self.write_lines("lint/test_traps.py", [
            'BLOCK = """',
            "header line",
            "%s2026-07-04 10:30 CDT (UTC-05:00)" % PREFIX,
            '"""',
            REAL_PIN])
        self.assertEqual(self.find(), [pin("lint/test_traps.py", 5)],
                         "a triple-quoted string holding the text mid-line was read as a pin")

    def test_6c_lone_quote_in_a_comment_or_text_does_not_move_the_result(self):
        self.hook()
        self.write_lines("lint/test_traps.py", [
            "# Don't count this comment",
            'WORD = "Don\'t"',
            'OTHER = "it\'s"',
            REAL_PIN])
        self.assertEqual(self.find(), [pin("lint/test_traps.py", 4)],
                         "a lone quote in a comment or a string moved the result")

    def test_7_plain_fstring_that_starts_with_the_printed_text_is_a_pin(self):
        self.hook()
        self.write_lines("hooks/test_shared_names.py", [
            'stamp = "2026-07-04 10:30 CDT (UTC-05:00)"',
            'STAMP_LINE = f"%s{stamp}"' % PREFIX])
        self.assertEqual(self.find(), [pin("hooks/test_shared_names.py", 2)],
                         "an f-string that starts with the printed text was not found")

    def test_8a_declared_name_missing_from_the_hook_is_unknown(self):
        # A rename without a tuple update: PRINTED_LINES still names the old constant.
        self.write_lines("hooks/renamed.py", ['TIME_LINE_PREFIX = "%s"' % PREFIX, 'PRINTED_LINES = ("TIME_PREFIX",)'])
        self.assert_unknown_declaration("hooks/renamed.py", "TIME_PREFIX")

    def test_8b_a_constant_of_seven_characters_is_ignored_and_eight_is_counted(self):
        self.hook()
        self.write_lines("hooks/short.py", ['SHORT = "Local: "', 'PRINTED_LINES = ("SHORT",)'])
        self.write_lines("hooks/eight.py", ['EIGHT = "Ready ok"', 'PRINTED_LINES = ("EIGHT",)'])
        self.write_lines("lint/test_lengths.py", [
            'SHORT_TEXT = "Local: 2026-07-04 10:30"',
            'EIGHT_TEXT = "Ready ok, go"'])
        self.assertEqual(self.find(), [pin("lint/test_lengths.py", 2, "hooks/eight.py", "EIGHT")],
                         "a 7-character constant was counted, or an 8-character one was not")

    def test_8c_declared_name_bound_to_a_concatenation_is_unknown(self):
        self.write_lines("hooks/concat.py", ['TIME_PREFIX = "Fixture" + " line: "', 'PRINTED_LINES = ("TIME_PREFIX",)'])
        self.assert_unknown_declaration("hooks/concat.py", "TIME_PREFIX")

    def test_8d_declared_name_bound_to_a_number_is_unknown(self):
        self.write_lines("hooks/counted.py", ["COUNT = 1234567890", 'PRINTED_LINES = ("COUNT",)'])
        self.assert_unknown_declaration("hooks/counted.py", "COUNT")

    def test_8e_bare_name_element_of_printed_lines_is_unknown(self):
        self.write_lines("hooks/bare.py", ['TIME_PREFIX = "%s"' % PREFIX, "PRINTED_LINES = (TIME_PREFIX,)"])
        self.assert_unknown_declaration("hooks/bare.py", "TIME_PREFIX")

    def test_8f_printed_lines_that_is_a_str_and_not_a_tuple_or_list_is_unknown(self):
        self.write_lines("hooks/shape.py", ['TIME_PREFIX = "%s"' % PREFIX, 'PRINTED_LINES = "TIME_PREFIX"'])
        self.assert_unknown_declaration("hooks/shape.py", "PRINTED_LINES")

    def test_8g_annotated_printed_lines_tuple_is_read(self):
        self.write_lines(HOOK, ['TIME_PREFIX = "%s"' % PREFIX, 'PRINTED_LINES: tuple = ("TIME_PREFIX",)'])
        self.write_lines("lint/test_planted.py", [REAL_PIN])
        self.assertEqual(self.find(), [pin("lint/test_planted.py", 1)],
                         "an annotated PRINTED_LINES tuple was not read: the planted pin was not found")

    def test_8h_printed_lines_list_is_read(self):
        self.write_lines(HOOK, ['TIME_PREFIX = "%s"' % PREFIX, 'PRINTED_LINES = ["TIME_PREFIX"]'])
        self.write_lines("lint/test_planted.py", [REAL_PIN])
        self.assertEqual(self.find(), [pin("lint/test_planted.py", 1)],
                         "a PRINTED_LINES list was not read: the planted pin was not found")

    def test_8i_hook_without_printed_lines_or_with_an_empty_one_adds_no_pins(self):
        # A hook with no PRINTED_LINES is not opted in. An empty PRINTED_LINES names nothing: both are silent.
        self.hook()
        self.write_lines("hooks/plain.py", ['GREETING = "Hello there, friend"'])
        self.write_lines("hooks/quiet.py", ["PRINTED_LINES = ()"])
        self.write_lines("lint/test_other.py", ['HELLO = "Hello there, friend"'])
        sibling = self.plant_sibling()
        self.assertEqual(self.find(), [sibling],
                         "text of an undeclared hook or of an empty PRINTED_LINES was read as a pin")

    def test_9a_root_with_no_test_files_is_clean(self):
        # Empty state, a green control: no test file, so nothing to pin.
        self.hook()
        self.assertEqual(self.find(), [], "a root with no test files reported pins")
        rc, out = self.run_main()
        self.assertEqual((rc, out), (0, ""), "a root with no test files must exit 0 and print nothing:\n" + out)

    def test_9b_unparseable_hook_exits_2(self):
        self.hook()
        self.write_lines("hooks/bad.py", ["def broken(:"])
        rc, out = self.run_main()
        self.assert_unknown(rc, out, "bad.py")

    def test_9c_undecodable_hook_exits_2(self):
        self.hook()
        with open(os.path.join(self.root, "hooks", "latin.py"), "wb") as f:
            f.write(b'PRINTED_LINES = ("NAME",)\nNAME = "\xff\xfe"\n')
        rc, out = self.run_main()
        self.assert_unknown(rc, out, "latin.py")

    def test_9d_unparseable_test_file_exits_2(self):
        # A test file the scan cannot read could hide a pin, so it is unknown too, never a pass.
        self.hook()
        self.write_lines("lint/test_broken.py", ['X = """never closed'])
        rc, out = self.run_main()
        self.assert_unknown(rc, out, "test_broken.py")

    def test_10a_clean_root_exits_0_and_prints_nothing(self):
        self.hook()
        self.write_lines("hooks/test_shared_names.py", ["import local_time",
                                                        'X = local_time.TIME_PREFIX + "2026-07-04"'])
        rc, out = self.run_main()
        self.assertEqual(rc, 0, "a clean root exited %s:\n%s" % (rc, out))
        self.assertEqual(out, "", "a clean run prints nothing:\n" + out)

    def test_10b_two_pins_exit_1_with_one_fail_line_each(self):
        self.hook()
        self.write_lines("lint/test_one.py", filler(11) + [REAL_PIN])
        self.write_lines("hooks/test_shared_names.py", filler(36) + [REAL_PIN])
        rc, out = self.run_main()
        lines = out.splitlines()
        self.assertEqual(rc, 1, "two pins did not exit 1:\n" + out)
        self.assertEqual(len(lines), 2, "expected one FAIL line per pin and no other output:\n" + out)
        for want in (pin("hooks/test_shared_names.py", 37), pin("lint/test_one.py", 12)):
            hits = [ln for ln in lines
                    if ln.startswith("FAIL") and want["test"] in ln and want["hook"] in ln
                    and want["name"] in ln and re.search(r"(?<!\d)%d(?!\d)" % want["line"], ln)]
            self.assertEqual(len(hits), 1, "no FAIL line names %s line %d, %s, %s:\n%s" % (
                want["test"], want["line"], want["hook"], want["name"], out))

    def test_11a_real_repo_has_no_literal_copy_of_a_printed_line(self):
        # Scope first: the real repo has hook modules and test files for the scan to read.
        hooks = [n for n in os.listdir(os.path.join(ROOT, "hooks"))
                 if n.endswith(".py") and not n.startswith("test_")]
        self.assertTrue(hooks, "scope: no hook module under %s/hooks" % ROOT)
        tests = [n for n in os.listdir(os.path.join(ROOT, "lint")) if n.startswith("test_") and n.endswith(".py")]
        self.assertTrue(tests, "scope: no lint test file under %s/lint" % ROOT)
        found = self.find(ROOT)
        self.assertEqual(found, [], "the real repo holds literal copies of printed lines: %r" % (found,))
        rc, out = self.run_main(ROOT)
        self.assertEqual((rc, out), (0, ""), "main on the real repo must exit 0 and print nothing:\n" + out)

    def test_11b_local_time_declares_printed_lines_naming_time_prefix(self):
        names = printed_names(self.real_tree("hooks/local_time.py"))
        self.assertTrue(names is not None and "TIME_PREFIX" in names,
                        "hooks/local_time.py does not declare PRINTED_LINES naming TIME_PREFIX: %r" % (names,))

    def test_11d_local_time_printed_lines_names_the_override_prefix(self):
        tree = self.real_tree("hooks/local_time.py")
        names = printed_names(tree)
        self.assertTrue(names is not None and "OVERRIDE_ONCE_PREFIX" in names,
                        "hooks/local_time.py PRINTED_LINES does not name OVERRIDE_ONCE_PREFIX: %r" % (names,))
        self.assertIsNotNone(str_value(tree, "OVERRIDE_ONCE_PREFIX"),
                             "OVERRIDE_ONCE_PREFIX is not a str constant of hooks/local_time.py")

    def test_11e_decision_watch_printed_lines_name_str_constants_of_that_module(self):
        rel = "hooks/decision_watch.py"
        tree = self.real_tree(rel)
        names = printed_names(tree)
        self.assertEqual(names, ["UNKNOWN_PREFIX", "FLAG_PREFIX"],
                         "%s PRINTED_LINES is not (UNKNOWN_PREFIX, FLAG_PREFIX): %r" % (rel, names))
        for name in names:
            self.assertIsNotNone(str_value(tree, name),
                                 "%s names %s, which is not a str constant of that module" % (rel, name))


if __name__ == "__main__":
    unittest.main()
