#!/usr/bin/env python3
"""Cases for lint/guard_move_proof.py, the proof that a guard-family move is a pure move. Standard library only.

    python3 lint/test_guard_move_proof.py

Each case builds a git fixture repo under this run's folder: HEAD~1 holds the base hooks/ files, HEAD the head files.
The script runs in-process with `--root` set to that repo, and the case reads its verdict line and exit code.
The importtime cases stub the timer (`median_import`), so no verdict depends on elapsed time. The one real-process
importtime case reads only that the timer ran, never the verdict.
"""
import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: every temp path comes from this run's folder
import tracked_tree  # noqa: E402  testing/tracked_tree.py: rm_tree clears read-only git files on Windows too
RUN_FOLDER = _test_temp.run_folder()  # test-temp-standard (one run folder per test run)
SCRIPT = os.path.join(HERE, "guard_move_proof.py")
IDENT = ["-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid"]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # a dataclass reads its module from sys.modules
    spec.loader.exec_module(module)
    return module


proof = load("guard_move_proof", SCRIPT)


def tearDownModule():
    tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


def tree(**modules):
    """{hooks path: text} from keyword names: tree(guard="...", guard_x="...") is hooks/guard.py and hooks/guard_x.py."""
    return {"hooks/%s.py" % name: textwrap.dedent(text) for name, text in modules.items()}


def git(root, *args):
    subprocess.run(["git", "-C", root] + list(args), check=True, capture_output=True)


def write_files(root, files):
    for rel, text in files.items():
        path = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)


def commit(root, message):
    git(root, "add", "-A")
    git(root, *IDENT, "commit", "-q", "--allow-empty", "-m", message)


def make_repo(base, head):
    """A fixture repo: HEAD~1 holds the `base` files, HEAD the `head` files (each a {path: text} map)."""
    root = tempfile.mkdtemp(prefix="guard_move_", dir=RUN_FOLDER)
    git(root, "init", "-q")
    write_files(root, base)
    commit(root, "base")
    git(root, "rm", "-r", "-q", "hooks")
    write_files(root, head)
    commit(root, "head")
    return root


def prove(root, *args, base="HEAD~1", head="HEAD"):
    """(exit code, output) of the script run in-process on `root`."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = proof.main([base, head, "--root", root] + list(args))
    return code, out.getvalue()


def stub_timer(base_us, head_us):
    """Replaces the one timer seam: `import guard` at base reads base_us, at head head_us."""
    def fake(root, ref):
        return base_us if ref == "HEAD~1" else head_us
    return mock.patch.object(proof, "median_import", side_effect=fake)


class Proof(unittest.TestCase):
    """The one place a case runs the script on a fixture and reads its verdict."""

    def assertPass(self, base, head, *args, lines=()):
        code, text = prove(make_repo(base, head), *args)
        self.assertEqual(code, 0, text)
        self.assertTrue(text.startswith("PASS "), text)
        for line in lines:
            self.assertIn(line, text)
        return text

    def assertFail(self, base, head, *args, lines=()):
        code, text = prove(make_repo(base, head), *args)
        self.assertEqual(code, 1, text)
        self.assertTrue(text.startswith("FAIL "), text)
        for line in lines:
            self.assertIn(line, text)
        return text


class CleanMove(Proof):
    def test_a_clean_move_passes(self):
        # a and X leave guard.py for guard_x.py and guard_core.py; a's reads of X and helper resolve by import there.
        base = tree(guard="""\
            from guard_core import helper
            X = 1

            def a():
                return X + helper()

            def b():
                return 2
            """, guard_core="""\
            def helper():
                return 0
            """)
        head = tree(guard="""\
            from guard_core import X, helper
            from guard_x import a

            def b():
                return 2
            """, guard_core="""\
            X = 1

            def helper():
                return 0
            """, guard_x="""\
            from guard_core import X, helper

            def a():
                return X + helper()
            """)
        self.assertPass(base, head, lines=["4 units at base, 2 moved module"])


class BodyChange(Proof):
    def test_a_body_change_fails(self):
        self.assertFail(tree(guard="def a():\n    return 1\n"), tree(guard="def a():\n    return 2\n"),
                        lines=["changed: def a (was guard.py:1, now guard.py:1)"])

    def test_changed_naming_the_unit_passes(self):
        self.assertPass(tree(guard="def a():\n    return 1\n"), tree(guard="def a():\n    return 2\n"),
                        "--changed", "a", lines=["changed (allowed by --changed): def a"])

    def test_changed_naming_another_unit_still_fails(self):
        self.assertFail(tree(guard="def a():\n    return 1\n"), tree(guard="def a():\n    return 2\n"),
                        "--changed", "b", lines=["changed: def a (was guard.py:1, now guard.py:1)"])

    def test_a_moved_and_changed_unit_fails_without_the_flag(self):
        self.assertFail(tree(guard="def a():\n    return 1\n"), tree(guard_x="def a():\n    return Y\n"),
                        lines=["changed: def a (was guard.py:1, now guard_x.py:1)"])


class LostUnit(Proof):
    def test_a_lost_unit_fails(self):
        self.assertFail(tree(guard="def a():\n    return 1\n\ndef b():\n    return 2\n"),
                        tree(guard="def b():\n    return 2\n"),
                        lines=["lost: def a (was guard.py:1), not in any guard module at head"])


class NewUnit(Proof):
    BASE = tree(guard="def b():\n    return 2\n")
    HEAD = tree(guard="def b():\n    return 2\n\ndef c():\n    return 3\n")

    def test_a_new_unit_fails_without_new(self):
        self.assertFail(self.BASE, self.HEAD, lines=["new unit not in --new: def c at guard.py:4"])

    def test_a_new_unit_passes_when_new_names_it(self):
        self.assertPass(self.BASE, self.HEAD, "--new", "c,d", lines=["new (allowed by --new): def c at guard.py:4"])

    def test_a_new_unit_still_fails_when_new_names_another(self):
        self.assertFail(self.BASE, self.HEAD, "--new", "d", lines=["new unit not in --new: def c at guard.py:4"])


class Duplicate(Proof):
    COPY = "def a():\n    return 1\n"

    def test_a_second_copy_at_head_fails_without_new(self):
        self.assertFail(tree(guard=self.COPY), tree(guard=self.COPY, guard_x=self.COPY),
                        lines=["new unit not in --new: def a at guard.py:1 (a second copy of one in base)",
                               "defined in two modules at head: a in guard.py, guard_x.py"])

    def test_a_second_copy_with_new_still_fails_on_two_modules(self):
        # --new excuses the extra unit under rule 1 only; rule 2 holds the name to one module.
        self.assertFail(tree(guard=self.COPY), tree(guard=self.COPY, guard_x=self.COPY), "--new", "a",
                        lines=["new copy (allowed by --new): def a at guard.py:1",
                               "defined in two modules at head: a in guard.py, guard_x.py"])

    def test_a_name_already_in_the_same_two_modules_at_base_is_a_note(self):
        self.assertPass(tree(guard=self.COPY, guard_x=self.COPY), tree(guard=self.COPY, guard_x=self.COPY),
                        lines=["defined in two modules at head: a in guard.py, guard_x.py (the same two at base)"])


class FreeNames(Proof):
    def test_an_unresolved_name_in_a_moved_unit_fails(self):
        self.assertFail(tree(guard="Y = 1\n\ndef a():\n    return Y\n"),
                        tree(guard="Y = 1\n", guard_x="def a():\n    return Y\n"),
                        lines=["unresolved name `Y` in def a, now in guard_x.py:1"])

    def test_a_name_resolved_by_import_in_the_new_module_passes(self):
        self.assertPass(tree(guard="Y = 1\n\ndef a():\n    return Y\n"),
                        tree(guard='"""Guard module."""\n', guard_core="Y = 1\n",
                             guard_x="from guard_core import Y\n\ndef a():\n    return Y\n"),
                        lines=["2 moved module"])

    def test_a_function_local_and_a_parameter_are_not_global_names(self):
        self.assertPass(tree(guard="def a(p):\n    y = p\n    return y\n"),
                        tree(guard='"""Guard module."""\n', guard_x="def a(p):\n    y = p\n    return y\n"),
                        lines=["1 moved module"])

    def test_a_unit_that_stays_and_reads_a_name_moved_out_fails(self):
        """A unit that stays in guard.py reads Y, which moved to guard_core.py with no import of Y left in guard.py:
        at run time a() raises NameError. Rule 3 checks every unit in a module that lost a name, not only moved units."""
        self.assertFail(tree(guard="Y = 1\n\ndef a():\n    return Y\n"),
                        tree(guard="def a():\n    return Y\n", guard_core="Y = 1\n"),
                        lines=["unresolved name `Y` in def a", "guard_core.py"])

    def test_a_unit_that_stays_and_reads_a_name_imported_from_the_moved_module_passes(self):
        self.assertPass(tree(guard="Y = 1\n\ndef a():\n    return Y\n"),
                        tree(guard="from guard_core import Y\n\ndef a():\n    return Y\n", guard_core="Y = 1\n"),
                        lines=["1 moved module"])

    def test_a_moved_and_changed_unit_listed_in_changed_still_gets_the_free_name_check(self):
        """A unit that moved and changed, with --changed naming it, reads Y, which resolves nowhere in guard_x.py.
        --changed allows the edit, never an unresolved name."""
        self.assertFail(tree(guard="def a():\n    return 1\n"), tree(guard_x="def a():\n    return Y\n"),
                        "--changed", "a", lines=["unresolved name `Y` in def a", "guard_x.py"])

    def test_a_moved_and_changed_unit_listed_in_changed_whose_name_is_imported_passes(self):
        self.assertPass(tree(guard="Y = 1\n\ndef a():\n    return 1\n"),
                        tree(guard='"""Guard module."""\n', guard_core="Y = 1\n",
                             guard_x="from guard_core import Y\n\ndef a():\n    return Y\n"),
                        "--changed", "a", lines=["changed (allowed by --changed): def a"])

    def test_a_def_that_stays_and_calls_itself_and_a_sibling_resolves_in_its_own_module(self):
        """guard.py loses Y to guard_core.py. `walk` stays, calls itself and calls `helper`, which also stays. A def
        resolves its names in its own module, so `walk` passes with no import of `walk` or `helper`."""
        self.assertPass(tree(guard="Y = 1\n\ndef helper():\n    return Y\n\ndef walk(n):\n"
                                   "    return walk(n - 1) if n else helper()\n"),
                        tree(guard="from guard_core import Y\n\ndef helper():\n    return Y\n\ndef walk(n):\n"
                                   "    return walk(n - 1) if n else helper()\n", guard_core="Y = 1\n"),
                        lines=["1 moved module"])

    def test_a_moved_def_that_calls_a_sibling_moved_with_it_resolves_in_its_new_module(self):
        """`a` and `b` move from guard.py to guard_x.py together, and `a` calls `b`. `b` is defined in guard_x.py too,
        so `a` passes. `keep` stays in guard.py."""
        self.assertPass(tree(guard="def a():\n    return b()\n\ndef b():\n    return 1\n\ndef keep():\n    return 2\n"),
                        tree(guard="def keep():\n    return 2\n", guard_x="def a():\n    return b()\n\ndef b():\n    return 1\n"),
                        lines=["2 moved module"])


class AugAssign(Proof):
    def test_an_aug_assign_joins_the_key_of_its_target(self):
        base, head = tree(guard="X = [1]\n"), tree(guard="X = [1]\nX += [2]\n")
        self.assertFail(base, head, lines=["new unit not in --new: X at guard.py:2 (a second copy of one in base)"])
        self.assertPass(base, head, "--new", "X", lines=["new copy (allowed by --new): X at guard.py:2"])

    def test_a_moved_aug_assign_whose_target_is_not_defined_there_fails(self):
        """X comes from outside the guard family, so no guard module defines it. `X += [2]` moved to guard_x.py reads
        X at import, with no X there: NameError. An augmented assignment reads its target as well as binding it."""
        self.assertFail(tree(guard="from shared_state import X\nX += [2]\n"),
                        tree(guard='"""Guard module."""\n', guard_x="X += [2]\n"),
                        lines=["unresolved name `X`", "guard_x.py"])

    def test_a_moved_aug_assign_whose_target_is_imported_passes(self):
        self.assertPass(tree(guard="from shared_state import X\nX += [2]\n"),
                        tree(guard='"""Guard module."""\n', guard_x="from shared_state import X\n\nX += [2]\n"),
                        lines=["1 moved module"])

    def test_a_moved_aug_assign_on_an_imported_name_is_not_a_second_definer(self):
        """`X = [1]` stays in guard.py and `X += [2]` moves to guard_x.py, which imports X from guard. An augmented
        assignment does not define its target, so X is defined once, in guard.py, and the move passes."""
        self.assertPass(tree(guard="X = [1]\nX += [2]\n"),
                        tree(guard="X = [1]\n", guard_x="from guard import X\n\nX += [2]\n"),
                        lines=["1 moved module"])


class TupleAndSubscript(Proof):
    def test_a_moved_tuple_target_passes(self):
        self.assertPass(tree(guard="A, B = 1, 2\n"), tree(guard='"""Guard module."""\n', guard_x="A, B = 1, 2\n"),
                        lines=["1 moved module"])

    def test_a_changed_tuple_target_needs_its_names(self):
        base, head = tree(guard="A, B = 1, 2\n"), tree(guard="A, B = 1, 3\n")
        self.assertFail(base, head, lines=["changed: A, B (was guard.py:1, now guard.py:1)"])
        self.assertPass(base, head, "--changed", "A,B", lines=["changed (allowed by --changed): A, B"])

    def test_a_moved_subscript_target_resolves_by_import(self):
        self.assertPass(tree(guard='REG = {}\nREG["k"] = 1\n'),
                        tree(guard="REG = {}\n", guard_x='from guard import REG\n\nREG["k"] = 1\n'),
                        lines=["1 moved module"])

    def test_a_moved_subscript_target_with_an_unresolved_name_fails(self):
        self.assertFail(tree(guard='REG = {}\nREG["k"] = 1\n'),
                        tree(guard="REG = {}\n", guard_x='REG["k"] = 1\n'),
                        lines=["unresolved name `REG` in "])


LOAD_BLOCK = """\
_load_deadline = 0
while True:
    try:
        _loading = "guard_core"
        from guard_core import helper
        break
    except ImportError:
        _loading = "guard_x"
        helper = None
        break
"""
LOAD_BLOCK_IMPORT_ONLY = """\
_load_deadline = 0
while True:
    try:
        import os
        from guard_core import helper
        break
    except ImportError:
        helper = None
        break
"""
LOAD_BLOCK_PRINTED = LOAD_BLOCK.replace("        break\n    except", "        print('loading')\n        break\n    except", 1)


class LoadBlock(Proof):
    CORE = tree(guard_core="def helper():\n    return 0\n")

    def test_an_import_only_change_and_dropped_markers_in_the_load_block_pass(self):
        self.assertPass({**self.CORE, **tree(guard=LOAD_BLOCK)}, {**self.CORE, **tree(guard=LOAD_BLOCK_IMPORT_ONLY)},
                        lines=["0 moved module"])

    def test_a_non_import_edit_in_the_load_block_fails(self):
        self.assertFail({**self.CORE, **tree(guard=LOAD_BLOCK)}, {**self.CORE, **tree(guard=LOAD_BLOCK_PRINTED)},
                        lines=["lost: statement `while True:` (was guard.py:2)"])


class HeadSyntax(Proof):
    def test_a_syntax_error_at_head_fails(self):
        self.assertFail(tree(guard="def a():\n    return 1\n"), tree(guard="def a(:\n    return 1\n"),
                        lines=["guard.py at HEAD does not parse"])


class ImportTime(Proof):
    def test_an_import_time_above_ten_percent_fails(self):
        with stub_timer(1000, 1200):
            self.assertFail(tree(guard="X = 1\n"), tree(guard="X = 1\n"), "--importtime",
                            lines=["more than 10% slower", "(+20.0%)"])

    def test_an_import_time_below_ten_percent_passes(self):
        with stub_timer(1000, 1050):
            self.assertPass(tree(guard="X = 1\n"), tree(guard="X = 1\n"), "--importtime",
                            lines=["importtime median of 5: base 1000 us, head 1050 us (+5.0%)"])

    def test_the_real_import_time_is_read(self):
        # Reads only that the timer ran: no verdict, since the timing of two identical imports is noise.
        code, text = prove(make_repo(tree(guard="import guard_core\n", guard_core="X = 1\n"),
                                     tree(guard="import guard_core\n", guard_core="X = 1\n")), "--importtime")
        self.assertIn("importtime median of 5", text)
        self.assertNotIn("did not run", text)


class BadRef(unittest.TestCase):
    def run_cli(self, *refs, base=None, head=None):
        root = make_repo(base or tree(guard="X = 1\n"), head or tree(guard="X = 1\n"))
        return subprocess.run([sys.executable, SCRIPT] + list(refs) + ["--root", root],
                              capture_output=True, text=True)

    def test_an_unreadable_base_ref_exits_two_with_unknown(self):
        done = self.run_cli("no-such-ref-for-guard-move", "HEAD")
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertTrue(done.stdout.startswith("unknown: "), done.stdout)

    def test_an_unreadable_head_ref_exits_two_with_unknown(self):
        done = self.run_cli("HEAD~1", "no-such-ref-for-guard-move")
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertTrue(done.stdout.startswith("unknown: "), done.stdout)

    def test_a_head_file_symtable_refuses_exits_two_with_unknown_and_no_traceback(self):
        """guard_x.py at head has `nonlocal q` at module level: ast.parse accepts it, symtable refuses it. The moved
        unit `a` makes the proof read guard_x.py's names, so the refusal must end as `unknown:`, never a traceback.
        The case runs the CLI in a subprocess: an in-process SyntaxError would error the case, not fail it."""
        done = self.run_cli("HEAD~1", "HEAD", base=tree(guard="def a():\n    return 1\n"),
                            head=tree(guard='"""Guard module."""\n', guard_x="nonlocal q\n\ndef a():\n    return 1\n"))
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertTrue(done.stdout.startswith("unknown: "), done.stdout)
        self.assertNotIn("Traceback", done.stderr)


class Scale(Proof):
    def test_an_empty_guard_module_passes(self):
        self.assertPass(tree(guard='"""Guard module."""\n'), tree(guard='"""Guard module."""\n'),
                        lines=["0 units at base, 0 moved module"])

    def test_a_full_size_family_move_passes(self):
        defs = ["def f%d():\n    return %d\n" % (i, i) for i in range(120)]
        base = tree(guard="\n".join(defs))
        head = tree(guard="\n".join(defs[:60]), guard_x="\n".join(defs[60:]))
        self.assertPass(base, head, lines=["120 units at base, 60 moved module"])


class TopLevelStatement(Proof):
    def test_a_changed_top_level_call_fails_even_with_changed(self):
        base, head = tree(guard='register("a")\n'), tree(guard='register("b")\n')
        self.assertFail(base, head, "--changed", "register", lines=["lost: statement `register('a')`"])


class DroppedCopy(Proof):
    def test_a_dropped_copy_fails_without_the_flag(self):
        self.assertFail(tree(guard="def a():\n    return 1\n\ndef a():\n    return 1\n"),
                        tree(guard="def a():\n    return 1\n"))

    def test_a_dropped_copy_is_lost_even_with_the_changed_flag(self):
        """The second identical `def a` is dropped and no body changed, so one unit is lost. --changed a names the
        unit, but a drop is not an edit: this fails, and says lost."""
        self.assertFail(tree(guard="def a():\n    return 1\n\ndef a():\n    return 1\n"),
                        tree(guard="def a():\n    return 1\n"), "--changed", "a",
                        lines=["lost: def a"])


class ModuleOrder(Proof):
    """A module-scope statement reads a name at import time, so the name's def or assignment must come first."""

    def test_a_module_statement_reading_a_def_above_it_fails(self):
        self.assertFail(tree(guard="def build():\n    return {}\n\nTABLE = build()\n"),
                        tree(guard="TABLE = build()\n\ndef build():\n    return {}\n"),
                        lines=["build", "guard.py"])

    def test_a_module_statement_reading_an_assignment_above_it_fails(self):
        self.assertFail(tree(guard="LIMIT = 5\nTABLE = LIMIT + 1\n"),
                        tree(guard="TABLE = LIMIT + 1\nLIMIT = 5\n"),
                        lines=["LIMIT", "guard.py"])

    def test_the_same_read_below_the_def_passes(self):
        text = tree(guard="def build():\n    return {}\n\nTABLE = build()\n")
        self.assertPass(text, text, lines=["0 moved module"])

    def test_a_class_body_reading_a_def_below_it_fails(self):
        """A class body runs when its statement does, so its read of `build` needs `build` bound above the class."""
        self.assertFail(tree(guard="def build():\n    return {}\n\nclass C:\n    T = build()\n"),
                        tree(guard="class C:\n    T = build()\n\ndef build():\n    return {}\n"),
                        lines=["`build` is read at import time at guard.py:1"])

    def test_a_generator_expression_reading_a_def_below_it_fails(self):
        """A generator expression runs when its statement does, so its read of `build` needs `build` bound above it.
        A list comprehension is inlined into its statement's table on Python 3.12 and later, so only a generator
        expression has its own scope for the import-time check to walk."""
        self.assertFail(tree(guard="def build():\n    return 1\n\nROWS = list(build() for _ in range(3))\n"),
                        tree(guard="ROWS = list(build() for _ in range(3))\n\ndef build():\n    return 1\n"),
                        lines=["`build` is read at import time at guard.py:1"])

    def test_a_def_body_reading_a_def_below_it_is_not_order_checked(self):
        self.assertPass(tree(guard="def build():\n    return {}\n\ndef show():\n    return build()\n"),
                        tree(guard="def show():\n    return build()\n\ndef build():\n    return {}\n"),
                        lines=["0 moved module"])


class GlobalDeclaration(Proof):
    def test_a_moved_unit_that_declares_global_and_assigns_it_fails(self):
        """bump moves to guard_x.py. Its `global STATE` makes the assignment rebind guard_x's STATE, not guard's."""
        self.assertFail(tree(guard="STATE = 0\n\ndef bump():\n    global STATE\n    STATE = 1\n"),
                        tree(guard="STATE = 0\n",
                             guard_x="from guard import STATE\n\ndef bump():\n    global STATE\n    STATE = 1\n"),
                        lines=["bump", "STATE"])

    def test_a_moved_unit_whose_global_target_moved_with_it_passes(self):
        """STATE and bump move to guard_x.py together. bump's `global STATE` binds the one assignment of STATE, and no
        other module defines it."""
        self.assertPass(tree(guard="STATE = 0\n\ndef bump():\n    global STATE\n    STATE = 1\n"),
                        tree(guard='"""Guard module."""\n',
                             guard_x="STATE = 0\n\ndef bump():\n    global STATE\n    STATE = 1\n"),
                        lines=["2 moved module"])

    def test_a_moved_unit_without_global_passes(self):
        self.assertPass(tree(guard="STATE = 0\n\ndef peek():\n    return STATE\n"),
                        tree(guard="STATE = 0\n", guard_x="from guard import STATE\n\ndef peek():\n    return STATE\n"),
                        lines=["1 moved module"])


class ImportedName(Proof):
    def test_an_import_of_a_name_the_source_module_lacks_fails(self):
        self.assertFail(tree(guard="def gate():\n    return 1\n"),
                        tree(guard="from guard_core import gate\n", guard_core='"""Guard module."""\n',
                             guard_x="def gate():\n    return 1\n"),
                        lines=["gate", "guard_core"])

    def test_an_import_from_the_module_that_holds_the_name_passes(self):
        self.assertPass(tree(guard="def gate():\n    return 1\n"),
                        tree(guard="from guard_x import gate\n", guard_x="def gate():\n    return 1\n"),
                        lines=["1 moved module"])

    def test_an_import_from_a_guard_module_missing_at_head_fails(self):
        """Runs the CLI: a missing module must end as a FAIL verdict on stdout, never as a traceback."""
        root = make_repo(tree(guard="def a():\n    return 1\n"),
                         tree(guard="from guard_missing import thing\n\ndef a():\n    return 1\n"))
        done = subprocess.run([sys.executable, SCRIPT, "HEAD~1", "HEAD", "--root", root],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertTrue(done.stdout.startswith("FAIL "), done.stdout + done.stderr)
        self.assertIn("imports from guard_missing, which is not a guard module at head", done.stdout)

    GETATTR = 'def __getattr__(name):\n    raise AttributeError(name)\n'

    def test_a_typo_imported_through_a_getattr_module_fails_when_only_the_importer_defines_it(self):
        """guard_stream.py has a module `__getattr__`, so it may serve any name at run time. Only guard_y, the importer,
        defines `typo_name`. The importer's own def does not make guard_stream provide it."""
        self.assertFail(tree(guard_stream=self.GETATTR, guard_y="def typo_name():\n    return 1\n"),
                        tree(guard_stream=self.GETATTR,
                             guard_y="from guard_stream import typo_name\n\ndef typo_name():\n    return 1\n"),
                        lines=["imports `typo_name` from guard_stream"])

    def test_a_real_name_defined_in_another_guard_module_and_reached_through_getattr_passes(self):
        text = tree(guard_stream=self.GETATTR, guard_core="def real():\n    return 1\n",
                    guard_y="from guard_stream import real\n\ndef gate():\n    return real()\n")
        self.assertPass(text, text, lines=["0 moved module"])


class MainBlock(Proof):
    """An `if __name__ == "__main__":` block runs only when its module is the script. The proof reads it as absent: an
    import in it is not checked, and a name bound only in it does not resolve."""

    def test_an_import_of_a_missing_name_inside_a_main_block_passes(self):
        text = tree(guard_x="def gate():\n    return 1\n",
                    guard_y='def a():\n    return 1\n\nif __name__ == "__main__":\n    from guard_x import nope\n')
        self.assertPass(text, text, lines=["0 moved module"])

    def test_a_moved_unit_reading_a_name_bound_only_in_a_main_block_fails(self):
        self.assertFail(tree(guard="K = 1\n\ndef a():\n    return K\n"),
                        tree(guard="K = 1\n",
                             guard_x='if __name__ == "__main__":\n    K = 1\n\ndef a():\n    return K\n'),
                        lines=["unresolved name `K` in def a", "guard_x.py"])


class FamilyTuple(Proof):
    """_FAMILY_MODULES is a tuple of guard module names. An edit under --changed may add a new guard module only."""
    BASE = tree(guard='_FAMILY_MODULES = ("guard_core", "guard_x")\n\ndef a():\n    return 1\n',
                guard_core="X = 1\n", guard_x="Y = 2\n")

    def test_dropping_a_family_entry_fails_even_with_changed(self):
        head = {**self.BASE, **tree(guard='_FAMILY_MODULES = ("guard_core",)\n\ndef a():\n    return 1\n')}
        self.assertFail(self.BASE, head, "--changed", "_FAMILY_MODULES", lines=["_FAMILY_MODULES"])

    def test_reordering_family_entries_fails_even_with_changed(self):
        head = {**self.BASE, **tree(guard='_FAMILY_MODULES = ("guard_x", "guard_core")\n\ndef a():\n    return 1\n')}
        self.assertFail(self.BASE, head, "--changed", "_FAMILY_MODULES", lines=["_FAMILY_MODULES"])

    def test_adding_a_new_guard_module_to_the_family_tuple_passes(self):
        head = {**self.BASE, **tree(guard='_FAMILY_MODULES = ("guard_core", "guard_x", "guard_y")\n\n'
                                          'def a():\n    return 1\n',
                                    guard_y='"""Guard module."""\n')}
        self.assertPass(self.BASE, head, "--changed", "_FAMILY_MODULES")

    def test_an_added_family_entry_with_no_guard_module_at_head_fails(self):
        head = {**self.BASE, **tree(guard='_FAMILY_MODULES = ("guard_core", "guard_x", "guard_z")\n\n'
                                          'def a():\n    return 1\n')}
        self.assertFail(self.BASE, head, "--changed", "_FAMILY_MODULES",
                        lines=["added entry `guard_z` is not a guard module new at head"])


class NewGuardModule(Proof):
    BASE = tree(guard='_FAMILY_MODULES = ("guard_core",)\n\ndef a():\n    return 1\n', guard_core="X = 1\n")

    def test_a_new_guard_module_missing_from_the_family_tuple_fails(self):
        self.assertFail(self.BASE, {**self.BASE, **tree(guard_y='"""Guard module."""\n')}, lines=["guard_y"])

    def test_a_new_file_outside_the_guard_family_passes(self):
        self.assertPass(self.BASE, {**self.BASE, "hooks/helper.py": "X = 2\n"})


class MovedBlock(Proof):
    """A try or if block binds a name at base. When the block moves out, a unit left in its module that reads the
    name needs an import. The block has no name of its own, so its module is not otherwise checked."""
    TRY = "try:\n    Z = 1\nexcept ImportError:\n    Z = 2\n"
    IF = "if True:\n    Z = 1\n"

    def test_a_try_block_moved_out_with_a_unit_left_reading_its_name_fails(self):
        self.assertFail(tree(guard=self.TRY + "\ndef a():\n    return Z\n"),
                        tree(guard="def a():\n    return Z\n", guard_core=self.TRY),
                        lines=["unresolved name `Z` in def a", "guard.py"])

    def test_an_if_block_moved_out_with_a_unit_left_reading_its_name_fails(self):
        self.assertFail(tree(guard=self.IF + "\ndef a():\n    return Z\n"),
                        tree(guard="def a():\n    return Z\n", guard_core=self.IF),
                        lines=["unresolved name `Z` in def a", "guard.py"])

    def test_the_unit_left_behind_importing_the_moved_name_passes(self):
        self.assertPass(tree(guard=self.TRY + "\ndef a():\n    return Z\n"),
                        tree(guard="from guard_core import Z\n\ndef a():\n    return Z\n", guard_core=self.TRY),
                        lines=["1 moved module"])


class NewUnitFreeNames(Proof):
    def test_a_new_unit_reading_an_unresolved_global_fails(self):
        self.assertFail(tree(guard="def b():\n    return 2\n"),
                        tree(guard="def b():\n    return 2\n\ndef c():\n    return MISSING_TABLE\n"),
                        "--new", "c", lines=["unresolved name `MISSING_TABLE` in def c"])

    def test_a_new_unit_reading_a_name_defined_here_and_a_builtin_passes(self):
        self.assertPass(tree(guard="TABLE = 1\n\ndef b():\n    return 2\n"),
                        tree(guard="TABLE = 1\n\ndef b():\n    return 2\n\ndef c():\n    return len(TABLE)\n"),
                        "--new", "c", lines=["new (allowed by --new): def c at guard.py"])


if __name__ == "__main__":
    unittest.main()
