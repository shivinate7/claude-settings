#!/usr/bin/env python3
"""Guard tables: the dump of FAMILIES, LOG_CHECKS and REASON_MAY_NAME, the compare of two dumps, and the
placement case for the central tables. Standard library only.

    python3 lint/test_guard_tables.py                           the cases
    python3 lint/test_guard_tables.py --dump [DIR]              DIR's tables as JSON on stdout (DIR: the repo)
    python3 lint/test_guard_tables.py --compare BASE.json [DIR] DIR's tables against BASE.json. Content differences
                                                                (a row missing, extra or changed) and order
                                                                differences (a row kept, at another place) print
                                                                apart. The case count is content too. Exit 1 on a
                                                                content difference, else 0.

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
# The central tables, each with the literal it sits in today. A LOG_CHECKS row whose family is not the family in
# force at its literal belongs in another file: its own family's section. A PLACED row (a FAMILIES or a
# REASON_MAY_NAME key, literal or subscript, in any file) belongs to the family its own key names; see belongs_to.
CENTRAL = (
    (RUNNER, "FAMILIES"),
    (os.path.join(SECTIONS, "s33355-misc.py"), "LOG_CHECKS"),
    (RUNNER, "REASON_MAY_NAME"),
)
PLACED = ("FAMILIES", "REASON_MAY_NAME")
LOADER_FAMILY = "sections"  # the runner's own family, for the loader's refusal: its FAMILIES row sits in the runner
ANY = None  # belongs-to of a row that may sit in any section: a named family, which _family gives by name
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
            "rule_families": [[rule, sorted({case["family"] for case in tables["CASES"] if case["rule"] == rule})]
                              for rule in tables["REASON_MAY_NAME"]],
            "named_families": list(tables["NAMED_FAMILIES"]),
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
    if got.get("case_count") != base.get("case_count"):
        content.append("case count: %s, was %s" % (got.get("case_count"), base.get("case_count")))
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


def key_text(key, strings, table, line):
    """The text of a row's key: a string, or a name bound to one. Any other key is refused, never guessed."""
    if isinstance(key, ast.Constant) and isinstance(key.value, str):
        return key.value
    if isinstance(key, ast.Name) and key.id in strings:
        return strings[key.id]
    raise ValueError("a %s key at line %d is not a string or a name bound to one" % (table, line))


def rows_of(name, value, log_family):
    """[(label, family)] of the LOG_CHECKS literal: a LOG_CHECKS row takes the family the run gave its label."""
    rows = []
    for elt in value.elts:
        label = elt.elts[0]
        if not (isinstance(label, ast.Constant) and isinstance(label.value, str)):
            raise ValueError("a LOG_CHECKS row at line %d does not open with a string label" % elt.lineno)
        rows.append((label.value, log_family.get(label.value)))
    return rows


def placed_rows_in(tree, strings):
    """[(table, key, line)] for each PLACED row of a module, at any depth: a subscript store `FAMILIES[key] = ...`, and
    each key of a literal `FAMILIES = {...}`."""
    out = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store)
                and isinstance(node.value, ast.Name) and node.value.id in PLACED):
            out.append((node.value.id, key_text(node.slice, strings, node.value.id, node.lineno), node.lineno))
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in PLACED:
                    for key in node.value.keys:
                        out.append((target.id, key_text(key, strings, target.id, key.lineno), key.lineno))
    return out


def belongs_to(table, key, tables):
    """The families a PLACED row belongs to. A FAMILIES row belongs to its own family, unless the runner names it
    (ANY). A REASON_MAY_NAME row belongs to the families of the cases that name its rule: that is where its subject
    is tested, so a row placed in another family's section is a finding."""
    if table == "FAMILIES":
        return ANY if key in tables["named_families"] else {key}
    by_rule = {rule: set(families) for rule, families in tables["rule_families"]}
    return by_rule.get(key, set())


def central_misplaced(root, tables):
    """[(table, row, belongs to, family in force)] for each row out of its family: a LOG_CHECKS row of the central
    literal whose family is not the one in force at that literal, and each PLACED row in the runner or a section
    file that no family it belongs to sits under. The runner's own rows sit under LOADER_FAMILY. A CENTRAL literal
    that is absent is an error: an empty table never passes for a missing one."""
    strings = module_strings(root)
    log_family = {}
    for label, family in tables["log_checks"]:
        log_family.setdefault(label, family)
    out = []
    for rel, name in CENTRAL:
        tree = module_tree(root, rel)
        node = literal_of(tree, name)
        if node is None:
            raise ValueError("%s has no literal %s, so the placement check has nothing to judge there" % (rel, name))
        if name == "LOG_CHECKS":
            home = family_in_force(tree, node.lineno)
            for row, family in rows_of(name, node.value, log_family):
                if family != home:
                    out.append((name, row, family, home))
    for rel in [RUNNER] + section_rels(root):
        tree = module_tree(root, rel)
        for table, key, line in placed_rows_in(tree, strings):
            home = LOADER_FAMILY if rel == RUNNER else family_in_force(tree, line)
            belongs = belongs_to(table, key, tables)
            if belongs is not ANY and home not in belongs:
                out.append((table, key, ", ".join(sorted(belongs)) or "no case", home))
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

    def test_changed_case_count_is_content(self):
        result = compare(self.BASE, dict(self.varied(), case_count=4))
        self.assertEqual(result["content"], ["case count: 4, was 3"],
                         "a changed case count was not reported as content")

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

    def test_every_row_sits_in_its_own_family(self):
        """The debt's closure, widened to subscript rows: each FAMILIES and REASON_MAY_NAME row, in the runner or a
        section, sits under a family it belongs to. Each LOG_CHECKS row of the central literal sits under its own."""
        self.assertTrue(os.path.isfile(os.path.join(REPO, RUNNER)), "the runner is not at %s" % RUNNER)
        self.assertTrue(section_rels(REPO), "no section file to hold the rows")
        misplaced = central_misplaced(REPO, dump(REPO))
        by_table = Counter(name for name, _, _, _ in misplaced)
        summary = ", ".join("%s %d" % (name, count) for name, count in sorted(by_table.items()))
        first = ["%s row %r (belongs to %s, sits under %r)" % (name, row, belongs, home)
                 for name, row, belongs, home in misplaced[:3]]
        self.assertEqual(len(misplaced), 0, "rows sit outside their family (%s); first: %s"
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


def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        return f.read()


def write(root, rel, text):
    with open(os.path.join(root, rel), "w", encoding="utf-8") as f:
        f.write(text)


def synthetic_tables(rule_families=(), named=()):
    """The tables a dump would hold, for a check on planted files: no child process, and no real rule or family."""
    return {"families": [], "reason_may_name": [], "log_checks": [], "case_count": 0,
            "rule_families": [[rule, list(families)] for rule, families in rule_families],
            "named_families": list(named)}


class PlantedRows(unittest.TestCase):
    """The placement check on planted files: a checkout-shaped folder under the run, with the runner and every real
    section linked in, and one planted section file or a planted runner."""

    def setUp(self):
        self.run = RUN_FOLDER

    def planted_tree(self, name, section=None, runner_text=None):
        root = os.path.join(self.run, name)
        os.makedirs(os.path.join(root, "hooks"))
        os.makedirs(os.path.join(root, SECTIONS))
        if runner_text is None:
            os.symlink(os.path.join(REPO, RUNNER), os.path.join(root, RUNNER))
        else:
            write(root, RUNNER, runner_text)
        for entry in os.listdir(os.path.join(REPO, SECTIONS)):
            if entry.endswith(".py"):
                os.symlink(os.path.join(REPO, SECTIONS, entry), os.path.join(root, SECTIONS, entry))
        if section is not None:
            write(root, os.path.join(SECTIONS, "zz_planted.py"), section)
        return root

    def flagged(self, root, table, row, tables=None):
        """The check's findings for one row of one table, by table and key."""
        return [(found_table, found_row) for found_table, found_row, _, _ in
                central_misplaced(root, tables or synthetic_tables())
                if (found_table, found_row) == (table, row)]

    def test_planted_family_row_in_another_family_section_is_reported(self):
        root = self.planted_tree("family-row", section='# section 99999\nFAMILY = "frozen"\n'
                                 'FAMILIES["shared-tree"] = "planted in frozen"\n')
        self.assertEqual(self.flagged(root, "FAMILIES", "shared-tree"), [("FAMILIES", "shared-tree")],
                         "the FAMILIES row planted in another family's section was not reported")

    def test_planted_reason_row_in_another_family_section_is_reported(self):
        root = self.planted_tree("reason-row", section='# section 99999\nFAMILY = "frozen"\n'
                                 'REASON_MAY_NAME["handoff-unread"] = ()\n')
        tables = synthetic_tables(rule_families=[("handoff-unread", ["handoff-unread"])])
        self.assertEqual(self.flagged(root, "REASON_MAY_NAME", "handoff-unread", tables),
                         [("REASON_MAY_NAME", "handoff-unread")],
                         "the REASON_MAY_NAME row planted in another family's section was not reported")

    def test_planted_family_row_in_the_runner_is_reported(self):
        """The runner is a central place: its only FAMILIES row is the loader's own, so a family row there is a finding."""
        runner_text = read(REPO, RUNNER) + '\nFAMILIES["frozen"] = "planted in the runner"\n'
        root = self.planted_tree("runner-row", runner_text=runner_text)
        self.assertEqual(self.flagged(root, "FAMILIES", "frozen"), [("FAMILIES", "frozen")],
                         "the FAMILIES row planted in the runner was not reported")

    def test_central_literal_missing_from_its_file_is_an_error_not_an_empty_table(self):
        """A CENTRAL entry whose literal is gone must stop the check, never pass as an empty table."""
        runner_text = read(REPO, RUNNER)
        self.assertIn("REASON_MAY_NAME = {}\n", runner_text, "the runner no longer holds the empty literal to remove")
        root = self.planted_tree("no-literal", runner_text=runner_text.replace("REASON_MAY_NAME = {}\n", "", 1))
        with self.assertRaisesRegex(ValueError, "REASON_MAY_NAME"):
            central_misplaced(root, synthetic_tables())

    def test_control_family_row_in_its_own_section_is_not_reported(self):
        root = self.planted_tree("own-row", section='# section 99999\nFAMILY = "frozen"\n'
                                 'FAMILIES["frozen"] = "planted in its own family"\n')
        self.assertEqual(self.flagged(root, "FAMILIES", "frozen"), [], "a row in its own family's section was reported")

    def test_control_named_family_row_may_sit_in_any_section(self):
        root = self.planted_tree("named-row", section='# section 99999\nFAMILY = "frozen"\n'
                                 'FAMILIES["argv"] = "planted: argv is named by its case"\n')
        tables = synthetic_tables(named=["argv"])
        self.assertEqual(self.flagged(root, "FAMILIES", "argv", tables), [],
                         "a named family's row was reported outside its section")


UNKNOWN_FAMILY = "no-such-family"
UNKNOWN_RUNS = {}  # one child run per run: the case reads the same outcome each time


def runner_child(folder, family=None):
    """The runner, in a child process, on the section files of `folder`, under GUARD_FAMILY=`family` when one is given.
    -> (rc, output, a process left in the child's group). rc is None when the child does not end in 300 s. The child
    leads its own process group, so a process a section starts is in that group, and the group is ended here whatever
    the child did. The group reading is None off POSIX, where there is no group to read."""
    env = child_env()
    env["GUARD_SECTION_DIR"] = folder
    if family is not None:
        env["GUARD_FAMILY"] = family
    log = os.path.join(folder, "child-output.txt")
    posix = os.name != "nt"
    with open(log, "w", encoding="utf-8") as out:
        child = subprocess.Popen([sys.executable, os.path.join(REPO, RUNNER)], env=env, stdout=out,
                                 stderr=subprocess.STDOUT, **({"start_new_session": True} if posix else {}))
        try:
            try:
                rc = child.wait(timeout=300)
            except subprocess.TimeoutExpired:
                rc = None
            left = group_has_members(child.pid) if posix else None  # read before the group is ended below
        finally:
            if posix:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except OSError:
                    pass  # the group has already ended
            child.wait()
    return rc, read(folder, "child-output.txt"), left


def unknown_family_run():
    """The runner, in a child process, on the real sections plus one marker section that writes a file when it runs,
    under a GUARD_FAMILY that names no family. -> (rc, output, marker written, a process left in the child's group)."""
    if UNKNOWN_FAMILY not in UNKNOWN_RUNS:
        folder = os.path.join(RUN_FOLDER, "unknown-family")
        os.makedirs(folder)
        for entry in os.listdir(os.path.join(REPO, SECTIONS)):
            if entry.endswith(".py"):
                os.symlink(os.path.join(REPO, SECTIONS, entry), os.path.join(folder, entry))
        marker = os.path.join(folder, "ran.txt")
        write(folder, "s99999-marker.py", '# section 99999\nopen(%r, "w").close()\n' % marker)
        rc, out, left = runner_child(folder, UNKNOWN_FAMILY)
        UNKNOWN_RUNS[UNKNOWN_FAMILY] = (rc, out, os.path.exists(marker), left)
    return UNKNOWN_RUNS[UNKNOWN_FAMILY]


def group_has_members(pgid):
    """True while any process is still in the process group `pgid`, even after its leader has ended."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True


class UnknownFamily(unittest.TestCase):
    """GUARD_FAMILY names no family. The runner refuses it before any section runs, and a refusal leaves no process a
    section started."""

    def test_refusal_names_the_families_it_knows(self):
        rc, out, _, _ = unknown_family_run()
        self.assertEqual(rc, 1, "the run did not refuse the unknown family: " + out[-300:])
        self.assertIn("is not a family. Want one of:", out)
        self.assertIn("load-brake", out, "the refusal does not list the families it knows")

    def test_refusal_comes_before_any_section_runs(self):
        rc, out, marker, _ = unknown_family_run()
        self.assertEqual(rc, 1, "the run did not refuse the unknown family: " + out[-300:])
        self.assertFalse(marker, "a section ran before the refusal")

    def test_refusal_leaves_no_child_process(self):
        if os.name == "nt":
            self.skipTest("a process group is read on POSIX only")
        rc, out, _, left = unknown_family_run()
        self.assertEqual(rc, 1, "the run did not refuse the unknown family: " + out[-300:])
        self.assertFalse(left, "a process the sections started is still running after the refusal")


class SectionScan(unittest.TestCase):
    """The loader's early scan reads each section file's FAMILIES rows before any section runs, so a syntax error and
    a refused family both stop the run there."""

    def test_syntax_error_in_a_section_names_that_file(self):
        folder = os.path.join(RUN_FOLDER, "broken-section")
        os.makedirs(folder)
        write(folder, "s00001-broken.py", "# section 1\n_x = )\n")
        rc, out, _ = runner_child(folder)
        self.assertEqual(rc, 1, "the run did not stop on a section that does not parse: " + out[-300:])
        self.assertIn('File "%s", line 2' % os.path.join(folder, "s00001-broken.py"), out,
                      "the syntax error does not name the section file it sits in")

    def test_early_scan_lists_every_real_family(self):
        """The refusal lists the names the early scan knows: those the section files set, and the runner's own. The list
        holds every family the run holds, and no other."""
        rc, out, _, _ = unknown_family_run()
        self.assertEqual(rc, 1, "the run did not refuse the unknown family: " + out[-300:])
        self.assertIn("Want one of: ", out, "the refusal lists no families")
        listed = set(out.split("Want one of: ", 1)[1].splitlines()[0].split(", "))
        held = {name for name, _ in dump(REPO)["families"]}
        self.assertFalse(held - listed, "the early scan does not know these real families: %s" % sorted(held - listed))
        self.assertFalse(listed - held,
                         "the early scan lists families the run does not hold: %s" % sorted(listed - held))


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
