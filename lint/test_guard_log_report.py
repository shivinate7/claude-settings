#!/usr/bin/env python3
"""Fixture tests for guard_log_report.py (reader for ~/.claude/guard.log).

Pinned contract:
- Window: the `days` calendar dates ending on now's date, inclusive. With now=2026-10-11 and
  days=7 the window is 2026-10-05 .. 2026-10-11. A line is in the window by its own date.
- by_rule counts deny/ask/noted only. A rule seen only in other decisions has no by_rule row.
- other keeps raw lines verbatim, trailing newline stripped, in log order, window applied.
- unreadable counts lines with fewer than 4 tab fields or a bad timestamp, window-independent.
  Field 5 is everything after the 4th tab, so extra tabs stay in the matched text.
- main() returns 0 and prints render(...). A missing log prints "unreadable: log not found".
- Session column: a line with six tab fields
  carries the hook's session_id as field 6, last. A line with five fields, or a "-" in field 6,
  reads as "unknown session". --session <id> keeps the lines of one session, exact match.
  --by-session prints counts per session, by rule and decision. The session value is a label
  only: it never changes a decision, a rule, or the other list.
- One reader: no file outside this one may parse guard.log lines. OneReaderTests checks it.

Run with:

    python3 lint/test_guard_log_report.py -v
"""
import ast
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_log_report as glr  # noqa: E402

NOW = datetime(2026, 10, 11, 12, 0, 0)
REVERTED = "2026-10-09T11:00:00\tBash\treverted\tshared-tree\tgit stash drop"
FIXTURE = [
    "2026-10-11T09:00:00\tBash\tdeny\tshared-tree\tgit stash",
    "2026-10-11T10:00:00\tBash\tdeny\tshared-tree\tgit reset --hard",
    "2026-10-11T10:30:00\tBash\task\tmerge-main\tgh pr merge 5",
    "2026-10-09T08:00:00\tEdit\tdeny\tguard-edit\thooks/guard.py",
    "2026-10-09T09:00:00\tBash\tnoted\tmerge-main\tgh pr merge 6",
    "2026-10-09T09:30:00\tBash\tdeny\tshared-tree\tgit checkout f.py",
    REVERTED,
    "2026-10-10T07:00:00\tBash\tdeny\tmulti\ta\tb\tc",
    "2026-10-05T00:00:00\tBash\tdeny\tedge-in\tfirst second of window",
    "2026-10-04T23:59:59\tBash\tdeny\tedge-out\tlast second before window",
    "2026-10-01T09:00:00\tBash\tdeny\told-rule\tx",
    "2026-10-01T09:05:00\tBash\treverted\told-rule\ty",
    "garbage line with no tabs",
    "not-a-date\tBash\tdeny\tbad-ts\tm",
    "2026-10-10T07:00:00\tBash\tdeny",
]


def run_main(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = glr.main(argv)
    return rc, out.getvalue()


class SummarizeTests(unittest.TestCase):
    def setUp(self):
        self.s = glr.summarize(FIXTURE, 7, NOW)

    def test_by_rule_counts_window_only(self):
        self.assertEqual(self.s["by_rule"], {
            "shared-tree": {"deny": 3, "ask": 0, "noted": 0},
            "merge-main": {"deny": 0, "ask": 1, "noted": 1},
            "guard-edit": {"deny": 1, "ask": 0, "noted": 0},
            "multi": {"deny": 1, "ask": 0, "noted": 0},
            "edge-in": {"deny": 1, "ask": 0, "noted": 0},
        })  # edge-out (1s before window) and old-rule (day 10) are absent

    def test_per_day_zero_filled_for_every_day(self):
        self.assertEqual(self.s["per_day"], {
            "2026-10-05": 1, "2026-10-06": 0, "2026-10-07": 0, "2026-10-08": 0,
            "2026-10-09": 2, "2026-10-10": 1, "2026-10-11": 2,
        })

    def test_other_is_verbatim_and_windowed(self):
        self.assertEqual(self.s["other"], [REVERTED])  # old reverted line is outside
        again = glr.summarize(iter(l + "\n" for l in FIXTURE), 7, NOW)
        self.assertEqual(again["other"], [REVERTED])  # newline stripped, any iterable

    def test_unreadable_counted_and_skipped_never_raised(self):
        self.assertEqual(self.s["unreadable"], 3)  # no tabs, bad timestamp, 3 fields
        self.assertEqual(glr.summarize([], 7, NOW)["unreadable"], 0)

    def test_extra_tabs_stay_in_matched_text_line_is_readable(self):
        # The "multi" line holds a, b, c after the rule: counted as a deny, not unreadable.
        self.assertEqual(self.s["by_rule"]["multi"]["deny"], 1)


class RenderTests(unittest.TestCase):
    def test_render_layout_and_order(self):
        text = glr.render(glr.summarize(FIXTURE, 7, NOW))
        lines = text.splitlines()
        at = lambda needle: lines.index(needle)  # noqa: E731
        rule_rows = ["| shared-tree | 3 | 0 | 0 |", "| edge-in | 1 | 0 | 0 |",
                     "| guard-edit | 1 | 0 | 0 |", "| multi | 1 | 0 | 0 |",
                     "| merge-main | 0 | 1 | 1 |"]  # deny desc, then rule name
        idx = [at(r) for r in rule_rows]
        self.assertEqual(idx, sorted(idx))
        self.assertLess(at("| rule | deny | ask | noted |"), idx[0])
        days = ["| 2026-10-%02d | %d |" % (d, n) for d, n in
                [(5, 1), (6, 0), (7, 0), (8, 0), (9, 2), (10, 1), (11, 2)]]
        didx = [at(d) for d in days]  # date order
        self.assertEqual(didx, sorted(didx))
        self.assertLess(idx[-1], at("| day | denies |"))
        self.assertLess(at("| day | denies |"), didx[0])
        fence = [i for i, l in enumerate(lines) if l.startswith("```")]
        self.assertEqual(len(fence), 2)
        self.assertLess(didx[-1], fence[0])
        self.assertEqual(lines[fence[0] + 1:fence[1]], [REVERTED])
        self.assertEqual([l for l in lines if l.strip()][-1], "unreadable: 3")
        self.assertGreater(len(lines) - 1, fence[1])  # unreadable line comes after the fence
        # Old five-field lines (no session column) render byte-identical to the golden.
        # Named failure: the stable table render.
        self.assertEqual(glr.render(glr.summarize(OLD_ONLY, 7, NOW)), GOLDEN_OLD_ONLY)


class MainTests(unittest.TestCase):
    def test_missing_log_prints_notice_and_exits_zero(self):
        gone = os.path.join(tempfile.gettempdir(), "no-such-dir-guard-log", "guard.log")
        rc, out = run_main(["--log", gone])
        self.assertEqual(rc, 0)
        self.assertIn("unreadable: log not found", out)

    def test_reads_log_file_with_days_flag(self):
        now = datetime.now().replace(microsecond=0)
        old = now - timedelta(days=365)
        body = "\n".join([
            now.isoformat() + "\tBash\tdeny\tlive-rule\tgit stash",
            old.isoformat() + "\tBash\tdeny\told-rule\tgit stash",
            "junk",
        ]) + "\n"
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "guard.log")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)
            rc, out = run_main(["--log", path, "--days", "3"])
        self.assertEqual(rc, 0)
        self.assertIn("| live-rule | 1 | 0 | 0 |", out)
        self.assertNotIn("old-rule", out)
        self.assertIn("unreadable: 1", out)

    def test_default_log_follows_claude_config_dir(self):
        # The hook writes to $CLAUDE_CONFIG_DIR or else ~/.claude (guard.py config_dir()).
        now = datetime.now().replace(microsecond=0)
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "guard.log"), "w", encoding="utf-8") as handle:
                handle.write(now.isoformat() + "\tBash\tdeny\tconfig-dir-rule\tgit stash\n")
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": folder}):
                rc, out = run_main([])
        self.assertEqual(rc, 0)
        self.assertIn("| config-dir-rule | 1 | 0 | 0 |", out)


# ----------------------------------------------------------- the session column
#
# Six fields: time, tool, decision, rule, matched, session. Session is LAST, so every old reader
# keeps its index 0..4. The writer folds whitespace in matched, so matched never holds a tab.

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
READER = "lint/guard_log_report.py"
HOOKS_DIR = os.path.join(REPO_ROOT, "hooks")
SID = "9f2c4e1a-7b3d-4c8e-9a10-5d6e7f8a9b0c"
OTHER_SID = "4d1e2f3a-0b9c-4d8e-8f7a-6b5c4d3e2f1a"
UNKNOWN = "unknown session"
BY_SESSION_HEADER = "| session | rule | deny | ask | noted |"
OLD_ONLY = [
    "2026-10-11T09:00:00\tBash\tdeny\tshared-tree\tgit stash",
    "2026-10-11T10:00:00\tBash\tdeny\tshared-tree\tgit reset --hard",
    "2026-10-11T10:30:00\tBash\task\tmerge-main\tgh pr merge 5",
    "2026-10-09T09:00:00\tBash\tnoted\tmerge-main\tgh pr merge 6",
    "2026-10-09T11:00:00\tBash\treverted\tshared-tree\tgit stash drop",
]
# Byte-exact render of OLD_ONLY at NOW, captured from the reader before the session column landed.
GOLDEN_OLD_ONLY = "\n".join([
    "| rule | deny | ask | noted |",
    "|---|---|---|---|",
    "| shared-tree | 2 | 0 | 0 |",
    "| merge-main | 0 | 1 | 1 |",
    "",
    "| day | denies |",
    "|---|---|",
    "| 2026-10-05 | 0 |",
    "| 2026-10-06 | 0 |",
    "| 2026-10-07 | 0 |",
    "| 2026-10-08 | 0 |",
    "| 2026-10-09 | 0 |",
    "| 2026-10-10 | 0 |",
    "| 2026-10-11 | 2 |",
    "",
    "```",
    "2026-10-09T11:00:00\tBash\treverted\tshared-tree\tgit stash drop",
    "```",
    "",
    "unreadable: 0",
])


def session_line(stamp, decision, rule, matched, session):
    return "\t".join([stamp, "Bash", decision, rule, matched, session])


def hours_ago(now, hours):
    return (now - timedelta(hours=hours)).isoformat(timespec="seconds")


def session_fixture(now):
    """Six lines: two of SID, one of OTHER_SID, one old five-field line, one placeholder line."""
    return [
        session_line(hours_ago(now, 1), "deny", "shared-tree", "git stash", SID),
        session_line(hours_ago(now, 2), "deny", "shared-tree", "git reset --hard", SID),
        session_line(hours_ago(now, 3), "ask", "merge-main", "gh pr merge 5", SID),
        session_line(hours_ago(now, 4), "noted", "merge-main", "gh pr merge 6", OTHER_SID),
        "\t".join([hours_ago(now, 5), "Bash", "deny", "shared-tree", "git checkout f.py"]),
        session_line(hours_ago(now, 6), "deny", "shared-tree", "git restore f.py", "-"),
    ]


EXPECTED_BY_SESSION = {
    (SID, "shared-tree", 2, 0, 0),
    (SID, "merge-main", 0, 1, 0),
    (OTHER_SID, "merge-main", 0, 0, 1),
    (UNKNOWN, "shared-tree", 2, 0, 0),  # the five-field line and the "-" line
}


def write_log(path, lines, crlf=False):
    """Write lines with no ending on the last one, LF or CRLF between them."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(("\r\n" if crlf else "\n").join(lines))
    return path


def by_session_rows(out):
    """Return the data rows of the by-session table as (session, rule, deny, ask, noted)."""
    rows = set()
    inside = False
    for line in out.splitlines():
        if line == BY_SESSION_HEADER:
            inside = True
            continue
        if not inside:
            continue
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 5 and all(cell.isdigit() for cell in cells[2:]):
            rows.add((cells[0], cells[1], int(cells[2]), int(cells[3]), int(cells[4])))
    return rows


class SessionColumnReadTests(unittest.TestCase):
    def test_counts_match_the_same_lines_without_the_column(self):
        lines = session_fixture(NOW)
        bare = ["\t".join(line.split("\t")[:5]) for line in lines]
        with_column = glr.summarize(lines, 7, NOW)
        without = glr.summarize(bare, 7, NOW)
        self.assertEqual(with_column["by_rule"], without["by_rule"])
        self.assertEqual(with_column["per_day"], without["per_day"])
        self.assertEqual(with_column["unreadable"], without["unreadable"])

    def test_session_value_is_a_label_never_a_decision_or_a_rule(self):
        lines = [
            session_line("2026-10-11T09:00:00", "deny", "shared-tree", "git stash", "deny"),
            session_line("2026-10-11T10:00:00", "noted", "shared-tree", "git stash", "shared-tree"),
            session_line("2026-10-11T10:30:00", "ask", "merge-main", "gh pr merge 5", "ask"),
            session_line("2026-10-11T11:00:00", "reverted", "shared-tree", "git stash drop", "noted"),
        ]
        s = glr.summarize(lines, 7, NOW)
        self.assertEqual(s["by_rule"], {
            "shared-tree": {"deny": 1, "ask": 0, "noted": 1},
            "merge-main": {"deny": 0, "ask": 1, "noted": 0},
        })
        self.assertEqual(s["other"], [lines[3]])  # the reverted line, verbatim, once
        # The same lines through the CLI. The session value is a
        # label in the by-session table too. Named failure: a session id spelled "deny" counted as a decision.
        cli_now = datetime.now()
        cli = [
            session_line(hours_ago(cli_now, 1), "deny", "shared-tree", "git stash", "deny"),
            session_line(hours_ago(cli_now, 2), "noted", "shared-tree", "git stash", "shared-tree"),
            session_line(hours_ago(cli_now, 3), "ask", "merge-main", "gh pr merge 5", "ask"),
            session_line(hours_ago(cli_now, 4), "reverted", "shared-tree", "git stash drop", "noted"),
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = write_log(os.path.join(folder, "guard.log"), cli)
            rc, out = run_main(["--log", path, "--by-session", "--days", "7"])
        self.assertEqual(rc, 0)
        self.assertEqual(by_session_rows(out), {
            ("deny", "shared-tree", 1, 0, 0),
            ("shared-tree", "shared-tree", 0, 0, 1),
            ("ask", "merge-main", 0, 1, 0),
        })

    def test_crlf_old_only_matches_lf_and_counts_a_partial_last_line(self):
        now = datetime.now().replace(microsecond=0)
        lines = [
            "\t".join([hours_ago(now, 1), "Bash", "deny", "shared-tree", "git stash"]),
            "\t".join([hours_ago(now, 2), "Bash", "deny", "shared-tree", "git reset --hard"]),
            "\t".join([hours_ago(now, 3), "Bash", "ask", "merge-main", "gh pr merge 5"]),
            "\t".join([hours_ago(now, 4), "Bash", "deny", "shared-tree", "git st"]),  # no ending
        ]
        with tempfile.TemporaryDirectory() as folder:
            lf = write_log(os.path.join(folder, "lf.log"), lines)
            crlf = write_log(os.path.join(folder, "crlf.log"), lines, crlf=True)
            rc_lf, out_lf = run_main(["--log", lf, "--days", "7"])
            rc_crlf, out_crlf = run_main(["--log", crlf, "--days", "7"])
        self.assertEqual((rc_lf, rc_crlf), (0, 0))
        self.assertEqual(out_crlf, out_lf)
        self.assertIn("| shared-tree | 3 | 0 | 0 |", out_crlf)  # the partial line counts


class SessionFilterTests(unittest.TestCase):
    def test_session_filter_keeps_one_session(self):
        with tempfile.TemporaryDirectory() as folder:
            path = write_log(os.path.join(folder, "guard.log"), session_fixture(datetime.now()))
            rc, out = run_main(["--log", path, "--session", SID, "--days", "7"])
        self.assertEqual(rc, 0)
        self.assertIn("| shared-tree | 2 | 0 | 0 |", out)  # the unfiltered count is 4
        self.assertIn("| merge-main | 0 | 1 | 0 |", out)
        self.assertNotIn("| shared-tree | 4 | 0 | 0 |", out)
        self.assertNotIn("| merge-main | 0 | 1 | 1 |", out)  # OTHER_SID's noted line is out

    def test_session_filter_is_an_exact_match(self):
        with tempfile.TemporaryDirectory() as folder:
            path = write_log(os.path.join(folder, "guard.log"), session_fixture(datetime.now()))
            rc, out = run_main(["--log", path, "--session", SID[:8], "--days", "7"])
        self.assertEqual(rc, 0)
        self.assertNotIn("| shared-tree |", out)  # a prefix of the id matches no line
        self.assertNotIn("| merge-main |", out)

    def test_crlf_session_filter_keeps_one_session_and_skips_the_partial_line(self):
        now = datetime.now().replace(microsecond=0)
        lines = [
            session_line(hours_ago(now, 1), "deny", "shared-tree", "git stash", SID),
            session_line(hours_ago(now, 2), "deny", "shared-tree", "git stash", OTHER_SID),
            "\t".join([hours_ago(now, 3), "Bash", "deny", "shared-tree", "git stash"]),
            "\t".join([hours_ago(now, 4), "Bash", "deny", "shared-tree", "git st"]),  # no ending
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = write_log(os.path.join(folder, "guard.log"), lines, crlf=True)
            rc, out = run_main(["--log", path, "--session", SID, "--days", "7"])
        self.assertEqual(rc, 0)
        self.assertIn("| shared-tree | 1 | 0 | 0 |", out)  # one SID line, not 4, not 3


class SessionBySessionTests(unittest.TestCase):
    def test_by_session_counts_per_session_rule_and_decision(self):
        with tempfile.TemporaryDirectory() as folder:
            path = write_log(os.path.join(folder, "guard.log"), session_fixture(datetime.now()))
            rc, out = run_main(["--log", path, "--by-session", "--days", "7"])
        self.assertEqual(rc, 0)
        self.assertEqual(by_session_rows(out), EXPECTED_BY_SESSION)


def reads_guard_log(source):
    """True when this Python source reads guard.log lines: a string names guard.log, and a call
    splits text on a tab. The parser reads the code, so a mention in a comment or a docstring does
    not count, and a tab or a quote inside a string is data, not a token.
    """
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docstrings.add(id(first.value))
    names_log = False
    splits_tab = False
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings and "guard.log" in node.value):
            names_log = True
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "split" and node.args
                and isinstance(node.args[0], ast.Constant) and node.args[0].value == "\t"):
            splits_tab = True
    return names_log and splits_tab


def _is_tab_split(node):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "split" and bool(node.args)
            and isinstance(node.args[0], ast.Constant) and node.args[0].value == "\t")


def _is_fallback_split(node):
    """`x.split("\\t")[:5]`: the first five tab fields, nothing else."""
    if not (isinstance(node, ast.Subscript) and _is_tab_split(node.value)):
        return False
    sl = node.slice
    return (isinstance(sl, ast.Slice) and sl.lower is None
            and isinstance(sl.upper, ast.Constant) and sl.upper.value == 5)


def _int_const(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, int) else None


def _named_columns(sl):
    """The column indexes a subscript names, or None when they cannot be told. A negative index
    names a column from the end, so it is never inside 0-4 and the caller rejects it."""
    if _int_const(sl) is not None:
        return {sl.value}
    if (isinstance(sl, ast.UnaryOp) and isinstance(sl.op, ast.USub)
            and _int_const(sl.operand) is not None):
        return {-sl.operand.value}
    if isinstance(sl, ast.Slice) and sl.step is None:
        lower = 0 if sl.lower is None else _int_const(sl.lower)
        upper = _int_const(sl.upper)
        if lower is None or upper is None or lower < 0:
            return None
        return set(range(lower, upper))
    return None


def split_sites(tree):
    """Return (scope, call node, shape) for each tab split in a parsed module. scope is the nearest
    enclosing function, or "<module>". shape is "fallback5" for `x.split("\\t")[:5]`, else "plain".
    """
    fallback = {id(node.value) for node in ast.walk(tree) if _is_fallback_split(node)}
    sites = []

    def visit(node, scope):
        if _is_tab_split(node):
            sites.append((scope, node, "fallback5" if id(node) in fallback else "plain"))
        for child in ast.iter_child_nodes(node):
            child_scope = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                else scope
            visit(child, child_scope)

    visit(tree, "<module>")
    return sites


def guard_log_split_sites(source):
    """Return (scope, shape) for each tab split in a Python source that names guard.log. Only code
    counts: a mention in a docstring, a comment or a plain data string does not name the log."""
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docstrings.add(id(first.value))
    names_log = any(isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docstrings and "guard.log" in node.value
                    for node in ast.walk(tree))
    if not names_log:
        return []
    return [(scope, shape) for scope, _, shape in split_sites(tree)]


def guard_log_sites(folders=("hooks", "lint")):
    """Return (path, scope, shape) for each tab split in a non-test repo file that names guard.log."""
    found = []
    for folder in folders:
        base = os.path.join(REPO_ROOT, folder)
        for name in sorted(os.listdir(base)):
            if not name.endswith(".py") or name.startswith("test_"):
                continue
            with open(os.path.join(base, name), encoding="utf-8") as handle:
                for scope, shape in guard_log_split_sites(handle.read()):
                    found.append((folder + "/" + name, scope, shape))
    return found


# The only tab splits of guard.log lines allowed in the repo. The reader's own split, and the one
# fallback the owner named (decision gate-hooks-fail-closed: an unread safety note must not vanish
# when the reader cannot be imported). Nothing else may split a guard.log line.
ALLOWED_SPLITS = (
    ("lint/guard_log_report.py", "parse_line", "plain"),
    ("hooks/decision_watch.py", "collect_unread", "fallback5"),
)
DECISION_WATCH = os.path.join(REPO_ROOT, "hooks", "decision_watch.py")


class OneReaderTests(unittest.TestCase):
    # The scanner is ast-based. These cases pin it on the shapes a text scanner gets wrong.
    def test_scanner_finds_a_real_reader(self):
        self.assertTrue(reads_guard_log('LOG = "guard.log"\nfields = line.split("\\t")\n'))

    def test_scanner_ignores_a_comment_opener_inside_a_string(self):
        self.assertFalse(reads_guard_log('PREFIX = "# "\nLOG = "guard.log"\nparts = t.split(",")\n'))
        self.assertTrue(reads_guard_log('OPEN = "/*"\nLOG = "guard.log"\nf = x.split("\\t")\n'))

    def test_scanner_ignores_a_multi_line_string_that_only_describes_a_read(self):
        source = 'DOC = """\nRead guard.log, then line.split("\\t").\n"""\n'
        self.assertFalse(reads_guard_log(source))

    def test_scanner_ignores_a_lone_quote_in_text(self):
        self.assertFalse(reads_guard_log('def f(line):\n    """Don\'t parse guard.log here."""\n'
                                         '    return line\n'))
        self.assertTrue(reads_guard_log('LOG = "guard.log"\nNOTE = "Don\'t"\n'
                                        'f = line.split("\\t")\n'))

    def test_only_the_reader_and_the_named_fallback_split_guard_log_lines(self):
        found = guard_log_sites()
        unlisted = [site for site in found if site not in ALLOWED_SPLITS]
        missing = [site for site in ALLOWED_SPLITS if site not in found]
        self.assertEqual(unlisted, [], "unlisted guard.log splits")
        self.assertEqual(missing, [], "an allowed split is not found")

    def test_the_named_fallback_may_read_its_rule_column_but_never_the_session_column(self):
        # A safety note is found by its rule: collect_unread must read the rule column (3) to tell an
        # unread-subject line from any other, so columns 0-4 are allowed, rule included. The session
        # column (index 5), any later index, and any negative index are not: the note must not
        # depend on a session cell, which a five-field line does not carry.
        with open(DECISION_WATCH, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        func = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef) and node.name == "collect_unread")
        bound = {target.id for node in ast.walk(func) if isinstance(node, ast.Assign)
                 and _is_fallback_split(node.value) for target in node.targets
                 if isinstance(target, ast.Name)}
        self.assertTrue(bound, "collect_unread has no fallback split to check")
        # The split list may be used only through an index or a slice, never whole (a loop or a
        # join reads every column, the session one included).
        subscripted = {id(node.value) for node in ast.walk(func) if isinstance(node, ast.Subscript)}
        whole = [node.lineno for node in ast.walk(func)
                 if isinstance(node, ast.Name) and node.id in bound
                 and isinstance(node.ctx, ast.Load) and id(node) not in subscripted]
        self.assertEqual(whole, [], "the fallback's split is read whole at lines %s" % whole)
        forbidden = []
        for node in ast.walk(func):
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) \
                    and node.value.id in bound:
                columns = _named_columns(node.slice)
                if columns is None or not columns <= set(range(5)):
                    forbidden.append((node.lineno, ast.unparse(node)))
        self.assertEqual(forbidden, [], "the fallback reads a column past 4: %s" % forbidden)

    def test_a_second_split_in_another_function_is_unlisted(self):
        # In memory only: the decision_watch source plus one more function that splits a guard.log
        # line. Each shape is a mutant the unlisted check must catch.
        with open(DECISION_WATCH, encoding="utf-8") as handle:
            source = handle.read()
        for body, shape in (('return line.split("\\t")[:5]', "fallback5"),
                            ('return line.split("\\t")', "plain")):
            mutant = source + "\n\ndef other_reader(line):\n    %s\n" % body
            sites = [("hooks/decision_watch.py", scope, kind)
                     for scope, kind in guard_log_split_sites(mutant)]
            unlisted = [site for site in sites if site not in ALLOWED_SPLITS]
            self.assertEqual(unlisted, [("hooks/decision_watch.py", "other_reader", shape)],
                             "a second %s split was not unlisted" % shape)


# ------------------------------------------- reader edge cases
#
# Decisions pinned here:
# - "-" is reserved for the placeholder. A hook id of "-" is written as "-", so it reads as
#   unknown session. --session - selects the unknown lines. A real "-" session cannot be told apart
#   in one column without an escape, and none is added.
# - The session cell is field 6 (index 5) only. A tab beyond field 6 stays in matched text, and the
#   cell never holds a raw tab.
# - --by-session prints at most BY_SESSION_ROWS rows, most denies first, then "... and K more".

class SessionReaderNitTests(unittest.TestCase):
    def test_dash_session_selects_the_unknown_lines(self):
        now = datetime.now()
        lines = [
            session_line(hours_ago(now, 1), "deny", "shared-tree", "git stash", SID),
            session_line(hours_ago(now, 2), "deny", "merge-main", "gh pr merge 5", "-"),
            "\t".join([hours_ago(now, 3), "Bash", "deny", "merge-main", "gh pr merge 6"]),
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = write_log(os.path.join(folder, "guard.log"), lines)
            rc, out = run_main(["--log", path, "--session", "-", "--days", "7"])
        self.assertEqual(rc, 0)
        self.assertIn("| merge-main | 2 | 0 | 0 |", out)  # the "-" line and the five-field line
        self.assertNotIn("| shared-tree |", out)  # SID's line is not unknown

    def test_seven_field_line_puts_no_raw_tab_in_the_session_cell(self):
        now = datetime.now()
        lines = ["\t".join([hours_ago(now, 1), "Bash", "deny", "multi", "a", "b", "c"])]
        with tempfile.TemporaryDirectory() as folder:
            path = write_log(os.path.join(folder, "guard.log"), lines)
            rc, out = run_main(["--log", path, "--by-session", "--days", "7"])
        self.assertEqual(rc, 0)
        self.assertIn("| b | multi | 1 | 0 | 0 |", out)  # field 6 only; "c" stays in matched
        for line in out.splitlines():
            if line.startswith("|"):
                self.assertNotIn("\t", line)

    def test_by_session_output_is_bounded_and_sorted_by_denies(self):
        limit = getattr(glr, "BY_SESSION_ROWS", None)  # the reader's named constant
        self.assertEqual(limit, 200)
        now = datetime.now()
        lines = []
        for i in range(3000):  # session i holds (i % 50) + 1 denies: 60 sessions hold 50
            for _ in range(i % 50 + 1):
                lines.append(session_line(hours_ago(now, 1), "deny", "rule-x", "git stash",
                                          "s%04d" % i))
        with tempfile.TemporaryDirectory() as folder:
            path = write_log(os.path.join(folder, "guard.log"), lines)
            rc, out = run_main(["--log", path, "--by-session", "--days", "7"])
        self.assertEqual(rc, 0)
        rows = by_session_rows(out)
        self.assertEqual(len(rows), limit)
        self.assertEqual(sum(1 for row in rows if row[2] == 50), 60)  # all 60 top sessions shown
        self.assertIn("... and %d more" % (3000 - limit), out)


class PlaceholderHomeTests(unittest.TestCase):
    def test_reader_names_the_placeholder_from_its_one_home(self):
        # One home: guard_core.SESSION_LOG_PLACEHOLDER. The reader may name it, never spell it.
        path = os.path.join(REPO_ROOT, "lint", "guard_log_report.py")
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)) and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                    docstrings.add(id(first.value))
        spelled = sorted(node.lineno for node in ast.walk(tree)
                         if isinstance(node, ast.Constant) and node.value == "-"
                         and id(node) not in docstrings)
        self.assertEqual(spelled, [], "the reader spells the placeholder at lines %s" % spelled)
        named = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertIn("SESSION_LOG_PLACEHOLDER", named)


# ------------------------------------ unread notes survive an unimportable reader
#
# collect_unread names the unread subjects of a turn from guard.log. When the reader cannot be
# imported, those notes must still come back. collect_unread falls back to a local split of the
# line: the first five fields, extra fields ignored. So a five-field and a six-field line both count.

UNREAD_LINES = [
    "2026-10-12T10:00:00\tBash\tnoted\tsubject-unread\tgit reset --hard HEAD\t-",  # six fields
    "2026-10-12T10:01:00\tBash\tnoted\tsubject-unread\tgit checkout -- f.py",      # five fields
]


def _unread_turn(folder, guard_lines):
    """A transcript with one Edit to a settings file and one merge, and guard.log lines in a config
    folder. Returns (hook payload, config folder)."""
    proj = os.path.join(folder, "proj")
    os.makedirs(os.path.join(proj, ".claude"))
    target = os.path.join(proj, ".claude", "settings.local.json")
    records = [
        {"type": "user", "timestamp": "2026-09-22T10:00:00.000Z",
         "message": {"role": "user", "content": [
             {"type": "text", "text": "tune the settings and merge"}]}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": target}}]}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "gh pr merge 5 --squash"}}]}},
    ]
    transcript = os.path.join(folder, "transcript.jsonl")
    with open(transcript, "w", encoding="utf-8") as handle:
        handle.write("".join(json.dumps(rec) + "\n" for rec in records))
    config = os.path.join(folder, "config")
    os.makedirs(config)
    with open(os.path.join(config, "guard.log"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(guard_lines) + "\n")
    return {"transcript_path": transcript, "cwd": proj}, config


def _report_with_config(dw, hook, config):
    saved = os.environ.get("CLAUDE_CONFIG_DIR")
    os.environ["CLAUDE_CONFIG_DIR"] = config
    try:
        return dw.config_report(hook)
    finally:
        if saved is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = saved


def _load_decision_watch():
    spec = importlib.util.spec_from_file_location(
        "decision_watch_unread", os.path.join(REPO_ROOT, "hooks", "decision_watch.py"))
    dw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dw)
    return dw


class UnreadNotesFailOpenTests(unittest.TestCase):
    def assertNotesNamed(self, message):
        self.assertIn("The guard could not read the subject", message, message)
        self.assertIn("git reset --hard HEAD", message, message)
        self.assertIn("git checkout -- f.py", message, message)
        self.assertIn("Config files changed this turn", message, message)
        self.assertIn("Merges into main this turn", message, message)

    def test_two_unread_notes_come_back_with_the_reader_blocked(self):
        dw = _load_decision_watch()
        with tempfile.TemporaryDirectory() as folder:
            hook, config = _unread_turn(folder, UNREAD_LINES)
            healthy = _report_with_config(dw, hook, config)
            had = "guard_log_report" in sys.modules
            saved = sys.modules.get("guard_log_report")
            sys.modules["guard_log_report"] = None  # the reader's import raises ImportError
            try:
                blocked = _report_with_config(dw, hook, config)
            finally:
                if had:
                    sys.modules["guard_log_report"] = saved
                else:
                    sys.modules.pop("guard_log_report", None)
        self.assertNotesNamed(healthy)  # the fixture is live
        self.assertNotesNamed(blocked)

    def test_two_unread_notes_come_back_with_a_stale_guard_core(self):
        # The reader imports SESSION_LOG_PLACEHOLDER from guard_core at load. A guard_core that lacks
        # the name makes that import fail, with the reader itself present.
        dw = _load_decision_watch()
        if HOOKS_DIR not in sys.path:
            sys.path.insert(0, HOOKS_DIR)
        import guard_core
        had_name = hasattr(guard_core, "SESSION_LOG_PLACEHOLDER")
        saved_name = getattr(guard_core, "SESSION_LOG_PLACEHOLDER", None)
        had_reader = "guard_log_report" in sys.modules
        saved_reader = sys.modules.get("guard_log_report")
        with tempfile.TemporaryDirectory() as folder:
            hook, config = _unread_turn(folder, UNREAD_LINES)
            try:
                if had_name:
                    delattr(guard_core, "SESSION_LOG_PLACEHOLDER")
                sys.modules.pop("guard_log_report", None)
                blocked = _report_with_config(dw, hook, config)
            finally:
                if had_name:
                    guard_core.SESSION_LOG_PLACEHOLDER = saved_name
                if had_reader:
                    sys.modules["guard_log_report"] = saved_reader
                else:
                    sys.modules.pop("guard_log_report", None)
        self.assertNotesNamed(blocked)


class FixedDecisionTests(unittest.TestCase):
    """A `fixed` line (an STE gate rewrite) is counted under the noted column. Pinned choice: map
    fixed to noted, the smaller change. A column of its own would change every old-only table, and
    GOLDEN_OLD_ONLY would break. The rule column still tells the STE codes apart from guard notes."""

    LINES = [
        session_line("2026-10-11T09:00:00", "fixed", "STE007,STE008", "notes.md fixed=2", SID),
        session_line("2026-10-11T10:00:00", "noted", "STE-fallback", "notes.md fallback=crash", SID),
        session_line("2026-10-11T11:00:00", "fixed", "STE007,STE008", "other.md fixed=2", OTHER_SID),
    ]

    def test_fixed_counts_under_noted_by_rule(self):
        s = glr.summarize(self.LINES, 7, NOW)
        self.assertEqual(s["by_rule"]["STE007,STE008"], {"deny": 0, "ask": 0, "noted": 2})
        self.assertEqual(s["by_rule"]["STE-fallback"], {"deny": 0, "ask": 0, "noted": 1})
        # A fixed line is never an other line.
        self.assertEqual(s["other"], [])
        # The session filter
        # keeps only that session's fixed lines. Named failure: a fixed line lost or moved to another session.
        one = glr.summarize(self.LINES, 7, NOW, SID)
        self.assertEqual(one["by_rule"]["STE007,STE008"], {"deny": 0, "ask": 0, "noted": 1})

    def test_report_and_by_session_show_fixed_in_the_noted_column(self):
        now = datetime.now().replace(microsecond=0)
        lines = [
            session_line(hours_ago(now, 1), "fixed", "STE007,STE008", "notes.md fixed=2", SID),
            session_line(hours_ago(now, 2), "fixed", "STE007,STE008", "b.md fixed=2", OTHER_SID),
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = write_log(os.path.join(folder, "guard.log"), lines)
            rc, out = run_main(["--log", path, "--by-session", "--days", "7"])
            rc_one, one = run_main(["--log", path, "--session", SID, "--days", "7"])
        self.assertEqual((rc, rc_one), (0, 0))
        self.assertIn("| STE007,STE008 | 0 | 0 | 2 |", out)
        self.assertIn("| %s | STE007,STE008 | 0 | 0 | 1 |" % SID, out)
        self.assertIn("| STE007,STE008 | 0 | 0 | 1 |", one)
        self.assertNotIn("| STE007,STE008 | 0 | 0 | 2 |", one)

    # STE denies and sweep blocks count in the deny column, as rows of their own: the reader groups
    # by rule, and an STE line's rule is its STE codes, so a guard row and an STE row never share one.
    def test_ste_denies_are_own_rows_beside_guard_rows_in_the_deny_column(self):
        lines = [
            session_line("2026-10-11T09:00:00", "deny", "shared-tree", "git stash", SID),
            session_line("2026-10-11T10:00:00", "deny", "STE008", "notes.md denied=1", SID),
            session_line("2026-10-11T11:00:00", "deny", "STE001,STE008", "b.md denied=2", OTHER_SID),
            session_line("2026-10-11T12:00:00", "deny", "STE008", "c.md denied=1", SID),
        ]
        s = glr.summarize(lines, 7, NOW)
        self.assertEqual(s["by_rule"]["shared-tree"], {"deny": 1, "ask": 0, "noted": 0})
        self.assertEqual(s["by_rule"]["STE008"], {"deny": 2, "ask": 0, "noted": 0})
        self.assertEqual(s["by_rule"]["STE001,STE008"], {"deny": 1, "ask": 0, "noted": 0})
        self.assertEqual(s["per_day"]["2026-10-11"], 4)
        out = glr.render(s)
        self.assertIn("| shared-tree | 1 | 0 | 0 |", out)
        self.assertIn("| STE008 | 2 | 0 | 0 |", out)
        self.assertIn("| STE001,STE008 | 1 | 0 | 0 |", out)


if __name__ == "__main__":
    unittest.main()
