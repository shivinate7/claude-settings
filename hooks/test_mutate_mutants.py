#!/usr/bin/env python3
"""Cases for the mutant folder: hooks/mutants/<rule-slug>.py holds one file of rows per rule (decision mutants-one-file-per-rule).

    python3 hooks/test_mutate_mutants.py

The literal table MUTATIONS in hooks/mutate_guard.py takes deletes only. The list every reader gets is that table,
followed by the folder's rows in sorted slug order. With no file in the folder, that list is the table byte for byte.

The first case is the control. It reads the literal from the source text, so it pins no count and no hash, and
compares it with the module's MUTATIONS. It is green on the table as it stands on main.
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GUARD_SOURCE = os.path.join(HERE, "mutate_guard.py")
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

RUN = None  # made in setUpModule, so an import leaks no folder


def setUpModule():
    global RUN
    RUN = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def literal_table():
    """The rows of the literal MUTATIONS table, read from the source text with ast. The literal is pure data, so
    ast.literal_eval reads it. A file with no single literal MUTATIONS list fails here, not in a case."""
    with open(GUARD_SOURCE, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=GUARD_SOURCE)
    literals = [node.value for node in tree.body
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.List)
                and any(isinstance(target, ast.Name) and target.id == "MUTATIONS" for target in node.targets)]
    if len(literals) != 1:
        raise AssertionError("want one literal MUTATIONS list in %s, found %d" % (GUARD_SOURCE, len(literals)))
    return ast.literal_eval(literals[0])


def labels_of(rows):
    return [row[0] for row in rows]


class EmptyFolderIsTheTable(unittest.TestCase):
    """Control: with no folder rows, the list every reader gets is today's table, in the same order, byte for byte."""

    def test_no_folder_rows_gives_the_table_byte_for_byte(self):
        sys.path.insert(0, HERE)
        import mutate_guard  # the real module, with the real hooks/mutants folder as it stands

        table = literal_table()
        got = mutate_guard.MUTATIONS
        self.assertEqual(labels_of(got), labels_of(table), "the label order differs from the literal table")
        self.assertEqual(repr(got), repr(table), "the rows differ from the literal table")


def make_tree(name):
    """A copy of hooks/ and testing/, flat and without test files, under the run folder. Returns the copy's hooks folder.
    Each case writes its own mutant folder into it, so no case touches the checkout."""
    root = os.path.join(RUN, name)
    hooks = os.path.join(root, "hooks")
    for source, dest in ((os.path.join(REPO, "hooks"), hooks), (os.path.join(REPO, "testing"), os.path.join(root, "testing"))):
        os.makedirs(dest)
        for entry in os.listdir(source):
            if entry.endswith(".py") and not entry.startswith("test_") and os.path.isfile(os.path.join(source, entry)):
                shutil.copyfile(os.path.join(source, entry), os.path.join(dest, entry))
    return hooks


def rows_text(labels):
    """A folder file that exposes one row per label in ROWS, in the table's row shape."""
    lines = ["ROWS = ["]
    lines += ["    (%r, 'def decide', 'def decide', 'guard', 'a case name')," % label for label in labels]
    return "\n".join(lines + ["]"]) + "\n"


def write_rules(hooks, files):
    """Write (file name, text) pairs into the copy's mutants folder, in the order given (not the order a listing gives)."""
    folder = os.path.join(hooks, "mutants")
    os.makedirs(folder, exist_ok=True)
    for name, text in files:
        with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
            handle.write(text)


def import_mutate_guard(hooks):
    """Import the copy's mutate_guard in a fresh interpreter whose folder is the copy's hooks, then print its labels as JSON."""
    driver = "import json\nimport mutate_guard\nprint(json.dumps([row[0] for row in mutate_guard.MUTATIONS]))\n"
    return subprocess.run([sys.executable, "-c", driver], cwd=hooks, capture_output=True, text=True, timeout=300)


def labels_from(proc):
    return json.loads(proc.stdout.strip().splitlines()[-1])


class FolderRowsFollowTheTable(unittest.TestCase):
    """The list every reader gets is the table, then the folder's rows: one file, then files in sorted slug order."""

    def test_one_file_adds_its_rows_after_the_table(self):
        hooks = make_tree("one-file")
        write_rules(hooks, [("aa-first.py", rows_text(["first: row"]))])
        proc = import_mutate_guard(hooks)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(labels_from(proc), labels_of(literal_table()) + ["first: row"],
                         "the folder's row is missing from, or misplaced in, the list the readers get")

    def test_files_add_rows_in_sorted_slug_order_and_keep_each_file_order(self):
        hooks = make_tree("sorted")
        # Created out of order, so the listing order cannot pass. `a` sorts before `a-b`, as the slugs do.
        write_rules(hooks, [("zz-late.py", rows_text(["zz: row"])),
                            ("mm-mid.py", rows_text(["mid: row one", "mid: row two"])),
                            ("a-b.py", rows_text(["a-b: row"])),
                            ("a.py", rows_text(["a: row"]))])
        proc = import_mutate_guard(hooks)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        want = labels_of(literal_table()) + ["a: row", "a-b: row", "mid: row one", "mid: row two", "zz: row"]
        self.assertEqual(labels_from(proc), want, "the folder's rows are not in sorted slug order, or a file's rows are reordered")


class FolderFailsLoudly(unittest.TestCase):
    """A bad folder file ends the run and names the file. A run that drops rows must be red, never a silent skip."""

    def assert_fails_naming(self, name, files, *names):
        hooks = make_tree(name)
        write_rules(hooks, files)
        proc = import_mutate_guard(hooks)
        self.assertNotEqual(proc.returncode, 0, "the run went on past a bad folder file; its rows were dropped without a word")
        for text in names:
            self.assertIn(text, proc.stderr, "the error does not name %r" % text)

    def test_two_files_with_one_label_fail_the_run_and_name_both(self):
        self.assert_fails_naming("dup-files", [("aa-one.py", rows_text(["same row"])),
                                               ("bb-two.py", rows_text(["same row"]))],
                                 "same row", "aa-one.py", "bb-two.py")

    def test_a_folder_row_repeating_a_table_label_fails_the_run_and_names_the_file(self):
        table_label = labels_of(literal_table())[0]
        self.assert_fails_naming("dup-table", [("aa-repeat.py", rows_text([table_label]))], table_label, "aa-repeat.py")

    def test_a_file_that_fails_to_import_fails_the_run_and_names_the_file(self):
        self.assert_fails_naming("broken", [("aa-broken.py", "raise RuntimeError('probe import fails')\n")], "aa-broken.py")

    def test_a_file_with_no_rows_fails_the_run_and_names_the_file(self):
        self.assert_fails_naming("norows", [("aa-norows.py", "X = 1\n")], "aa-norows.py")

    def test_a_row_of_the_wrong_length_fails_the_run_and_names_the_file(self):
        self.assert_fails_naming("short", [("aa-short.py", "ROWS = [('only a label',)]\n")], "aa-short.py")


class FolderAddsNothingElse(unittest.TestCase):
    """Green controls beside the reds: the empty folder, and files the loader must not read as rules."""

    def test_an_empty_folder_gives_the_table(self):
        hooks = make_tree("empty")
        os.makedirs(os.path.join(hooks, "mutants"))
        proc = import_mutate_guard(hooks)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(labels_from(proc), labels_of(literal_table()))

    def test_a_non_py_file_and_a_subfolder_add_no_rows(self):
        hooks = make_tree("ignored")
        write_rules(hooks, [("README.md", "notes\n")])
        os.makedirs(os.path.join(hooks, "mutants", "nested"))
        with open(os.path.join(hooks, "mutants", "nested", "aa.py"), "w", encoding="utf-8") as handle:
            handle.write(rows_text(["nested: row"]))
        proc = import_mutate_guard(hooks)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(labels_from(proc), labels_of(literal_table()))


def repo_copy(name):
    """A copy of this checkout without its git history, under the run folder, made a git repo of its own (no commit) so the
    harness lists its files by git. The copy is what the harness runs in: the real checkout is never written."""
    root = os.path.join(RUN, name)
    shutil.copytree(REPO, root, ignore=shutil.ignore_patterns(".git", "__pycache__", "node_modules"))
    subprocess.run(["git", "init", "-q", root], check=True, capture_output=True, timeout=300)
    return root


class MutateOnlySelectsAFolderRow(unittest.TestCase):
    """The single-mutant run (MUTATE_ONLY=<label>) selects a row from the folder. A probe copies the first table row under a
    new label, so the run kills it the way it kills that row. The run must end green and name the probe in its verdicts."""

    def test_the_single_mutant_run_selects_a_folder_row(self):
        root = repo_copy("only")
        label, old, new, target, required = literal_table()[0]
        probe = "probe: MUTATE_ONLY selects a folder row"
        folder = os.path.join(root, "hooks", "mutants")
        os.makedirs(folder)
        with open(os.path.join(folder, "aa-probe.py"), "w", encoding="utf-8") as handle:
            handle.write(rows_text_of([(probe, old, new, target, required)]))
        env = dict(os.environ, MUTATE_ONLY=probe)
        proc = subprocess.run([sys.executable, os.path.join("hooks", "mutate_guard.py")], cwd=root, env=env,
                              capture_output=True, text=True, timeout=1800)
        output = proc.stdout + proc.stderr
        self.assertNotIn("ERROR no mutation named", output, "the single-mutant run does not see the folder row")
        self.assertEqual(proc.returncode, 0, output[-2000:])
        self.assertIn(probe, proc.stdout, "the run did not print a verdict for the folder row")


def rows_text_of(rows):
    """A folder file that exposes the given (label, old, new, target, required) rows in ROWS."""
    return "ROWS = [\n" + "".join("    %r,\n" % (row,) for row in rows) + "]\n"


if __name__ == "__main__":
    unittest.main()
