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
    def run_cli(self, *refs):
        root = make_repo(tree(guard="X = 1\n"), tree(guard="X = 1\n"))
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


if __name__ == "__main__":
    unittest.main()
