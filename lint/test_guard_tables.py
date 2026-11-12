#!/usr/bin/env python3
"""Guard tables: the dump of FAMILIES, LOG_CHECKS and REASON_MAY_NAME, the compare of two dumps, and the
placement case for the central tables. Standard library only.

    python3 lint/test_guard_tables.py                           the cases
    python3 lint/test_guard_tables.py --dump [DIR]              DIR's tables as JSON on stdout (DIR: the repo)
    python3 lint/test_guard_tables.py --compare BASE.json [DIR] DIR's tables against BASE.json. Content differences
                                                                (a row missing, extra or changed) and order
                                                                differences (a row kept, at another place) print
                                                                apart. Exit 1 on a content difference, else 0.

The move keeps content: a builder runs `--dump` on main into the scratchpad, then `--compare` against that file.
That is a command, not a case in CI: after the move a later lane that adds a family differs from main by design.

A dump is read in a child process running the checkout's own runner (hooks/test_guard.py), after its import, so
LOG_FAMILY is set as the run sets it. The child removes what the import leaves: the run folder ROOT and the sleep
process OWNED. One checkout's modules never meet another's, because each dump is its own process.
"""
import ast
import json
import os
import runpy
import shutil
import signal
import subprocess
import sys
import time
import unittest
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

REPO = os.path.dirname(HERE)
RUNNER = os.path.join("hooks", "test_guard.py")
SECTIONS = os.path.join("tests", "guard")
# The central tables, each with the literal it sits in today. A row whose family is not the family in force at
# its literal belongs in another file: its own family's section.
CENTRAL = (
    (RUNNER, "FAMILIES"),
    (os.path.join(SECTIONS, "s33355-misc.py"), "LOG_CHECKS"),
    (os.path.join(SECTIONS, "s30130-rule9.py"), "REASON_MAY_NAME"),
)
DROP_ENV = ("MUTATE_ONLY", "STALL_WATCH_BEAT")  # the runner's switches that are not GUARD_*
PRINT_CAP = 20  # lines printed per kind of difference; the rest are counted


def child_env():
    """The environment of a runner child: the guard's switches out, so the import reads its own checkout."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GUARD_") and k not in DROP_ENV}


def read_tables(root):
    """The tables of the runner under `root`, read after its import. Only a child process calls this."""
    # Not a guard_* name: the runner drops every guard_* module from sys.modules at its end (s30130-rule9).
    tables = runpy.run_path(os.path.join(root, RUNNER), run_name="tables_probe")
    try:
        run_root, slash = tables["ROOT"], tables["slash"]

        def placeholder(fragment):
            return fragment.replace(slash(run_root), "<ROOT>").replace(run_root, "<ROOT>")

        return {
            "families": [[name, text] for name, text in tables["FAMILIES"].items()],
            "log_checks": [[label, tables["LOG_FAMILY"].get(label)] for label, _ in tables["LOG_CHECKS"]],
            "reason_may_name": [[key, [placeholder(f) for f in frags]]
                                for key, frags in tables["REASON_MAY_NAME"].items()],
            "case_count": len(tables["CASES"]) + len(tables["LOG_CHECKS"]),
        }
    finally:
        shutil.rmtree(run_root, ignore_errors=True)
        tables["OWNED"].kill()
        tables["OWNED"].wait()
        for pid in tables["ORPHAN_PIDS"]:  # the import's own holders, as run_cases ends them
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        deadline = time.monotonic() + 5  # a signalled holder exits a moment after the signal
        while any(pid_alive(pid) for pid in tables["ORPHAN_PIDS"]) and time.monotonic() < deadline:
            time.sleep(0.05)
        left = [pid for pid in tables["ORPHAN_PIDS"] if pid_alive(pid)]
        if left:
            raise RuntimeError("the runner's import left %d holder(s) running: %s" % (len(left), left))


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


DUMPS = {}  # one child per checkout per run: the import is the cost, and every case reads the same tables


def dump(root):
    """The tables of the checkout at `root`, read by a child process once per run. The child writes to files, not
    pipes: a holder the import leaves can keep a pipe open and stall a read until it ends."""
    key = os.path.abspath(root)
    if key not in DUMPS:
        work = _test_temp.run_folder()
        try:
            out_path, err_path = os.path.join(work, "tables.json"), os.path.join(work, "stderr.txt")
            with open(out_path, "w", encoding="utf-8") as out, open(err_path, "w", encoding="utf-8") as err:
                code = subprocess.run([sys.executable, os.path.abspath(__file__), "--read", key],
                                      stdout=out, stderr=err, env=child_env()).returncode
            with open(err_path, encoding="utf-8") as f:
                err_text = f.read()
            if code != 0:
                raise RuntimeError("the runner under %s did not load (exit %d): %s"
                                   % (root, code, err_text.strip()[-1500:]))
            with open(out_path, encoding="utf-8") as f:
                DUMPS[key] = json.load(f)
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return json.loads(json.dumps(DUMPS[key]))


def moved(label, was, now, show=str):
    """Lines for the rows both sides hold, each at another place in the common order."""
    place = {key: i for i, key in enumerate(now)}
    return ["%s: row %s moved, from place %d to place %d" % (label, show(key), i, place[key])
            for i, key in enumerate(was) if place[key] != i]


def compare(base, got):
    """{"content": [...], "order": [...]}. Content: a row missing, extra or changed. Order: a row both hold, placed
    differently. A reorder alone is never content."""
    content, order = [], []
    for table, label in (("families", "FAMILIES"), ("reason_may_name", "REASON_MAY_NAME")):
        was = [(key, value) for key, value in base[table]]
        now = [(key, value) for key, value in got[table]]
        was_map, now_map = dict(was), dict(now)
        for key, value in was:
            if key not in now_map:
                content.append("%s: row %s missing" % (label, key))
            elif now_map[key] != value:
                content.append("%s: row %s changed" % (label, key))
        for key, _ in now:
            if key not in was_map:
                content.append("%s: row %s extra" % (label, key))
        order += moved(label, [key for key, _ in was if key in now_map], [key for key, _ in now if key in was_map])
    was_rows = [tuple(row) for row in base["log_checks"]]
    now_rows = [tuple(row) for row in got["log_checks"]]
    was_count, now_count = Counter(was_rows), Counter(now_rows)
    for row in sorted(was_count - now_count, key=str):
        content.append("LOG_CHECKS: row %s missing" % (row,))
    for row in sorted(now_count - was_count, key=str):
        content.append("LOG_CHECKS: row %s extra" % (row,))
    order += moved("LOG_CHECKS", [row for row in was_rows if row in now_count],
                   [row for row in now_rows if row in was_count], show=lambda row: row[0])
    return {"content": content, "order": order}


def report(result, out=sys.stdout):
    for kind in ("content", "order"):
        lines = result[kind]
        if not lines:
            print("%s differences: none" % kind, file=out)
            continue
        print("%s differences: %d" % (kind, len(lines)), file=out)
        for line in lines[:PRINT_CAP]:
            print("  " + line, file=out)
        if len(lines) > PRINT_CAP:
            print("  ... %d more" % (len(lines) - PRINT_CAP), file=out)


def section_rels(root):
    folder = os.path.join(root, SECTIONS)
    if not os.path.isdir(folder):
        return []
    return [os.path.join(SECTIONS, name) for name in sorted(os.listdir(folder)) if name.endswith(".py")]


def module_tree(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        return ast.parse(f.read(), filename=rel)


def literal_of(tree, name):
    """The module-level assignment of `name`, or None when the module holds none."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node
    return None


def family_in_force(tree, line):
    """The family a module-level line sits under: the last `FAMILY = "<name>"` above it, else misc (the runner's
    default family for a line outside a tagged section)."""
    family = "misc"
    for node in tree.body:
        if node.lineno >= line:
            break
        if (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "FAMILY" for t in node.targets)
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            family = node.value.value
    return family


def module_strings(root):
    """Module-level `NAME = "text"` assignments of the runner and its sections, first one wins: a key may be a name."""
    names = {}
    for rel in [RUNNER] + section_rels(root):
        for node in module_tree(root, rel).body:
            if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                    and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                names.setdefault(node.targets[0].id, node.value.value)
    return names


def rows_of(name, value, strings, log_family):
    """[(row key, family)] of one central literal. FAMILIES and REASON_MAY_NAME rows are their own family; a
    LOG_CHECKS row takes the family the run gave its label."""
    if name == "LOG_CHECKS":
        rows = []
        for elt in value.elts:
            label = elt.elts[0]
            if not (isinstance(label, ast.Constant) and isinstance(label.value, str)):
                raise ValueError("a LOG_CHECKS row at line %d does not open with a string label" % elt.lineno)
            rows.append((label.value, log_family.get(label.value)))
        return rows
    rows = []
    for key in value.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            text = key.value
        elif isinstance(key, ast.Name) and key.id in strings:
            text = strings[key.id]
        else:
            raise ValueError("a %s key at line %d is not a string or a name bound to one" % (name, key.lineno))
        rows.append((text, text))
    return rows


def central_misplaced(root, tables):
    """[(table, row, row family, family in force)] for each row of a central literal whose family is not the one in
    force at that literal. A central literal that is absent holds no row."""
    strings = module_strings(root)
    log_family = {}
    for label, family in tables["log_checks"]:
        log_family.setdefault(label, family)
    out = []
    for rel, name in CENTRAL:
        tree = module_tree(root, rel)
        node = literal_of(tree, name)
        if node is None:
            continue
        home = family_in_force(tree, node.lineno)
        for row, family in rows_of(name, node.value, strings, log_family):
            if family != home:
                out.append((name, row, family, home))
    return out


class CompareRules(unittest.TestCase):
    """The compare on synthetic dumps: content and order are told apart, and an empty table compares clean."""

    BASE = {"families": [["a", "A"], ["b", "B"], ["c", "C"]], "reason_may_name": [["a", ["p"]]],
            "log_checks": [["x", "fa"], ["y", "fb"], ["z", "fc"]], "case_count": 3}

    def varied(self, **changes):
        got = json.loads(json.dumps(self.BASE))
        for table, rows in changes.items():
            got[table] = rows
        return got

    def test_identical_tables_differ_nowhere(self):
        self.assertEqual(compare(self.BASE, self.varied()), {"content": [], "order": []})

    def test_reordered_family_rows_are_order_only(self):
        result = compare(self.BASE, self.varied(families=[["b", "B"], ["a", "A"], ["c", "C"]]))
        self.assertEqual(result["content"], [], "a reorder was reported as content: %s" % result["content"])
        self.assertTrue(result["order"], "a reorder was not reported as an order difference")

    def test_reordered_log_checks_are_order_only(self):
        result = compare(self.BASE, self.varied(log_checks=[["z", "fc"], ["y", "fb"], ["x", "fa"]]))
        self.assertEqual(result["content"], [], "a reorder was reported as content: %s" % result["content"])
        self.assertTrue(result["order"], "a log check reorder was not reported as an order difference")

    def test_changed_family_text_is_content_not_order(self):
        result = compare(self.BASE, self.varied(families=[["a", "A"], ["b", "B2"], ["c", "C"]]))
        self.assertEqual(result["order"], [], "a changed text was reported as an order difference")
        self.assertEqual(result["content"], ["FAMILIES: row b changed"])

    def test_missing_and_extra_rows_are_content(self):
        missing = compare(self.BASE, self.varied(families=[["a", "A"], ["b", "B"]]))
        self.assertEqual(missing["content"], ["FAMILIES: row c missing"])
        extra = compare(self.BASE, self.varied(log_checks=self.BASE["log_checks"] + [["w", "fd"]]))
        self.assertEqual(extra["content"], ["LOG_CHECKS: row ('w', 'fd') extra"])

    def test_content_and_order_are_both_reported(self):
        result = compare(self.BASE, self.varied(families=[["b", "B2"], ["a", "A"], ["c", "C"]]))
        self.assertTrue(result["content"], "the changed text was not reported as content")
        self.assertTrue(result["order"], "the moved row was not reported as order")

    def test_empty_tables_compare_clean(self):
        empty = {"families": [], "reason_may_name": [], "log_checks": [], "case_count": 0}
        self.assertEqual(compare(empty, dict(empty)), {"content": [], "order": []})


class CentralTables(unittest.TestCase):
    """The tables of this checkout, read by a child, and the rows the central literals hold."""

    def setUp(self):
        self.run = RUN_FOLDER

    def test_dump_reads_all_three_tables_of_the_repo(self):
        """Scope first: the runner and the section folder exist, then the dump of each table is judged."""
        self.assertTrue(os.path.isfile(os.path.join(REPO, RUNNER)), "the runner is not at %s" % RUNNER)
        self.assertTrue(section_rels(REPO), "no section file to hold the rows")
        tables = dump(REPO)
        for table in ("families", "log_checks", "reason_may_name"):
            self.assertTrue(tables[table], "the dump of %s is empty" % table)
        self.assertGreater(tables["case_count"], 0, "the dump counts no case")

    def test_no_row_of_another_family_sits_in_a_central_table(self):
        """The debt's closure: no family row remains in a central table. Each central row sits under its own family."""
        self.assertTrue(section_rels(REPO), "no section file to hold the rows")
        misplaced = central_misplaced(REPO, dump(REPO))
        by_table = Counter(name for name, _, _, _ in misplaced)
        summary = ", ".join("%s %d" % (name, count) for name, count in sorted(by_table.items()))
        first = ["%s row %r (family %r, the table's family %r)" % (name, row, family, home)
                 for name, row, family, home in misplaced[:3]]
        self.assertEqual(len(misplaced), 0, "rows of another family sit in a central table (%s); first: %s"
                         % (summary, "; ".join(first)))

    def test_compare_mode_exits_one_on_a_content_difference(self):
        base = dump(REPO)
        base["families"] = [[name, text + " (changed)" if i == 0 else text]
                            for i, (name, text) in enumerate(base["families"])]
        path = os.path.join(self.run, "base-changed.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(base, f)
        proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--compare", path, REPO],
                              capture_output=True, text=True, encoding="utf-8", env=child_env())
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("content differences: 1", proc.stdout)


RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


def main(argv):
    if len(argv) == 2 and argv[0] == "--read":
        json.dump(read_tables(argv[1]), sys.stdout)
        return 0
    if argv[:1] == ["--dump"] and len(argv) in (1, 2):
        json.dump(dump(argv[1] if len(argv) == 2 else REPO), sys.stdout, indent=1)
        print()
        return 0
    if argv[:1] == ["--compare"] and len(argv) in (2, 3):
        with open(argv[1], encoding="utf-8") as f:
            base = json.load(f)
        result = compare(base, dump(argv[2] if len(argv) == 3 else REPO))
        report(result)
        return 1 if result["content"] else 0
    if argv:
        print("usage: test_guard_tables.py [--dump [DIR] | --compare BASE.json [DIR]]")
        return 2
    unittest.main(argv=[sys.argv[0]])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
