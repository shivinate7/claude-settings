#!/usr/bin/env python3
"""Cases for the mutant folder: hooks/mutants/<rule-slug>.py holds one file of rows per rule (decision section-number-clash-ready).

    python3 hooks/test_mutate_mutants.py

The literal table MUTATIONS in hooks/mutate_guard.py takes deletes only. The list every reader gets is that table,
followed by the folder's rows in sorted slug order. With no file in the folder, that list is the table byte for byte.

The first case is the control. It reads the literal from the source text, so it pins no count and no hash, and
compares it with the module's MUTATIONS. It is green on the table as it stands on main.
"""
import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD_SOURCE = os.path.join(HERE, "mutate_guard.py")


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


if __name__ == "__main__":
    unittest.main()
