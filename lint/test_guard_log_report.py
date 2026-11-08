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
- --all-rules prints the same per-rule table with one more column, the date of the rule's first
  guard.log line (YYYY-MM-DD) or "never". Every rule id the guard emits has a row, 0 counts
  included. No hook writes an STE code now, so an STE row appears only when the log holds one.
  A rule id that only the log holds keeps its row. A line of any decision
  (override, reverted, crash too) counts as the rule having fired. A combined STE line
  (`STE007,STE008`) credits each code, and so does one the guard's logger cut at its field limit
  (`STE001,STE003 [cut]`). AllRulesTests checks the ids against the source.
- --days all reads the whole log. Any other word is refused. AllRulesTests checks it.

Run with:

    python3 lint/test_guard_log_report.py -v
"""
import ast
import contextlib
import glob
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_log_report as glr  # noqa: E402
import rule_audit  # noqa: E402
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)

RUN_FOLDER = _test_temp.run_folder()

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
# fallback the owner named (decision guard-hooks-fail-closed: an unread safety note must not vanish
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


def _report_with_reader_blocked(dw, hook, config):
    """The config report with the reader's import raising ImportError, so the split fallback reads the lines."""
    had = "guard_log_report" in sys.modules
    saved = sys.modules.get("guard_log_report")
    sys.modules["guard_log_report"] = None  # the reader's import raises ImportError
    try:
        return _report_with_config(dw, hook, config)
    finally:
        if had:
            sys.modules["guard_log_report"] = saved
        else:
            sys.modules.pop("guard_log_report", None)


# Both are later than the turn's human message, so both are in the turn.
OFFSET_UNREAD_LINES = [
    "2026-10-12T10:02:00-05:00\tBash\tnoted\tsubject-unread\tgit clean -fd\t" + SID,
    "2026-10-12T10:03:00+05:00\tBash\tnoted\tsubject-unread\tgit rebase origin/main\t-",
]


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
            blocked = _report_with_reader_blocked(dw, hook, config)
        self.assertNotesNamed(healthy)  # the fixture is live
        self.assertNotesNamed(blocked)

    def test_offset_unread_notes_come_back_healthy_and_with_the_reader_blocked(self):
        # An offset line parses to an aware datetime. Compared with the naive turn bound, it raises, and
        # config_notices then drops every notice of the turn, not only the unread subjects. Both the reader
        # and the split fallback must read it. The old-form lines in the same turn must still come back.
        dw = _load_decision_watch()
        with tempfile.TemporaryDirectory() as folder:
            hook, config = _unread_turn(folder, UNREAD_LINES + OFFSET_UNREAD_LINES)
            healthy = _report_with_config(dw, hook, config)
            blocked = _report_with_reader_blocked(dw, hook, config)
        for label, message in (("healthy", healthy), ("reader blocked", blocked)):
            self.assertNotesNamed(message)
            self.assertIn("git clean -fd", message, label + ": " + message)
            self.assertIn("git rebase origin/main", message, label + ": " + message)

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


# ------------------------------------ a guard.log line that carries its UTC offset
#
# guard_core.record() writes its time with the UTC offset: 2026-11-01T12:00:00+05:00 is 07:00 UTC. The reader
# gives `at`, the aware instant, and `when`, naive in the reading machine's local time. An old line has no
# zone: `at` is None, and window() counts it as unknown, never as inside. Every assertion here is true on any
# clock: aware datetimes compare by instant, and `when` is checked against `at`, not against a literal hour.

def utc(hour, minute=0):
    return datetime(2026, 11, 1, hour, minute, tzinfo=timezone.utc)


OLD_LINE = "2026-11-01T07:00:00\tBash\tdeny\tload-brake\tgit push\t" + SID  # no zone
PLUS_FIVE_LINE = "2026-11-01T12:00:00+05:00\tBash\tdeny\tload-brake\tgit push\t" + SID  # 07:00 UTC


class OffsetStampReadTests(unittest.TestCase):
    def test_old_line_keeps_its_naive_when_and_has_no_zone(self):
        row = glr.parse_line(OLD_LINE)
        self.assertEqual(row.when, datetime(2026, 11, 1, 7, 0))
        self.assertIsNone(row.when.tzinfo)
        self.assertIsNone(row.at)

    def test_offset_line_gives_the_utc_instant_and_a_naive_local_when(self):
        row = glr.parse_line(PLUS_FIVE_LINE)
        self.assertEqual(row.at, utc(7))
        self.assertIsNone(row.when.tzinfo)

    @unittest.skipIf(not hasattr(time, "tzset"), "no time.tzset here, so the zone cannot be forced")
    def test_offset_line_reads_as_local_wall_time_in_a_forced_non_utc_zone(self):
        # IST-5:30 is +05:30, read from the POSIX zone string, so it needs no tzdata: a machine without the zone
        # database falls back to UTC for a name such as Asia/Kolkata. The +05:00 line at 12:00 is 07:00 UTC,
        # which is 12:30 there. A reader that returns UTC-naive gives 07:00 here, so this fails where a UTC clock would pass it.
        old = os.environ.get("TZ")
        os.environ["TZ"] = "IST-5:30"
        time.tzset()
        try:
            row = glr.parse_line(PLUS_FIVE_LINE)
            self.assertEqual(row.at, utc(7))
            self.assertIsNone(row.when.tzinfo)
            self.assertEqual(row.when, datetime(2026, 11, 1, 12, 30))
        finally:
            if old is None:
                del os.environ["TZ"]
            else:
                os.environ["TZ"] = old
            time.tzset()

    def test_minus_six_line_converts_the_same_way(self):
        row = glr.parse_line("2026-11-01T16:55:00-06:00\tBash\tdeny\tload-brake\tgit push\t" + SID)
        self.assertEqual(row.at, utc(22, 55))
        self.assertIsNone(row.when.tzinfo)

    def test_at_is_the_last_field_and_a_seven_argument_row_still_builds(self):
        self.assertEqual(glr.Row._fields[-1], "at")
        row = glr.Row("line", datetime(2026, 10, 11, 9), "Bash", "deny", "rule", "matched", "sess")
        self.assertIsNone(row.at)

    def test_summarize_counts_old_and_offset_lines_alike(self):
        # days=None reads every line whatever its date, so no zone can move a line out of the count.
        s = glr.summarize([PLUS_FIVE_LINE, OLD_LINE], None, NOW)
        self.assertEqual(s["by_rule"]["load-brake"], {"deny": 2, "ask": 0, "noted": 0})
        self.assertEqual(s["unreadable"], 0)


class OffsetWindowTests(unittest.TestCase):
    def test_offset_line_is_inside_the_window_that_holds_its_instant(self):
        rows, _unknown = glr.window([PLUS_FIVE_LINE], utc(6, 30), utc(7, 30))
        self.assertEqual([row.line for row in rows], [PLUS_FIVE_LINE])

    def test_offset_line_is_outside_a_window_that_misses_its_instant(self):
        rows, _unknown = glr.window([PLUS_FIVE_LINE], utc(11, 30), utc(12, 30))
        self.assertEqual(rows, [])

    def test_window_edges_are_inclusive(self):
        at_start = "2026-11-01T11:30:00+05:00\tBash\tdeny\tload-brake\tgit push\t" + SID  # 06:30 UTC
        at_end = "2026-11-01T12:30:00+05:00\tBash\tdeny\tload-brake\tgit push\t" + SID  # 07:30 UTC
        rows, _unknown = glr.window([at_start, at_end], utc(6, 30), utc(7, 30))
        self.assertEqual([row.line for row in rows], [at_start, at_end])

    def test_old_line_is_unknown_and_never_inside(self):
        # Read as UTC, OLD_LINE is at 07:00 and sits in 06:30-07:30. Read as Central (UTC-6 in November) it
        # is at 13:00 UTC and sits in 12:30-13:30. It must sit in neither: its zone is unknown.
        rows, unknown = glr.window([OLD_LINE], utc(6, 30), utc(7, 30))
        self.assertEqual((rows, unknown), ([], 1))
        rows, unknown = glr.window([OLD_LINE], utc(12, 30), utc(13, 30))
        self.assertEqual((rows, unknown), ([], 1))

    def test_rule_filter_keeps_other_rules_out_of_rows_and_unknown(self):
        other_inside = "2026-11-01T12:00:00+05:00\tBash\tdeny\tshared-tree\tgit stash\t" + SID
        other_old = "2026-11-01T07:00:00\tBash\tdeny\tshared-tree\tgit stash\t" + SID
        lines = [PLUS_FIVE_LINE, other_inside, OLD_LINE, other_old]
        rows, unknown = glr.window(lines, utc(6, 30), utc(7, 30), rule="load-brake")
        self.assertEqual(([row.line for row in rows], unknown), ([PLUS_FIVE_LINE], 1))
        rows, unknown = glr.window(lines, utc(6, 30), utc(7, 30))
        self.assertEqual(([row.line for row in rows], unknown), ([PLUS_FIVE_LINE, other_inside], 2))

    def test_an_unreadable_line_is_neither_inside_nor_unknown(self):
        rows, unknown = glr.window(["not a guard line", OLD_LINE], utc(6, 30), utc(7, 30))
        self.assertEqual((rows, unknown), ([], 1))


CLOUD_NA = "n/a (cloud)\n"
UNKNOWN_LINE = "unknown (old lines with no zone that could fall inside): %d"
BRAKE_WINDOW = ["--between", "2026-11-01T06:30:00+00:00", "2026-11-01T07:30:00+00:00"]  # 07:00 UTC is inside
SHARED_INSIDE = "2026-11-01T12:00:00+05:00\tBash\tdeny\tshared-tree\tgit stash\t" + SID  # 07:00 UTC
OLD_SHARED = "2026-11-01T07:00:00\tBash\tdeny\tshared-tree\tgit stash\t" + SID  # no zone


def fresh_log(lines=None):
    """A guard.log path in a new folder under this run's folder. The file is written only when `lines` is given."""
    path = os.path.join(tempfile.mkdtemp(dir=RUN_FOLDER), "guard.log")
    if lines is not None:
        write_log(path, lines)
    return path


class CloudCheckOneHome(unittest.TestCase):
    """The cloud check has one home, hooks/guard_core.py's is_cloud: True only for exactly "true". This report's n/a (cloud) check
    and the brake guard in guard.py hold that one function (decision session-tiers: the brake is local-only)."""

    def helper(self):
        import guard_core
        return getattr(guard_core, "is_cloud", None)

    def test_guard_core_has_is_cloud_true_only_for_exactly_true(self):
        fn = self.helper()
        self.assertTrue(callable(fn), "guard_core has no is_cloud: the cloud check has no one home yet")
        for value, want in ((None, False), ("true", True), ("TRUE", False), ("1", False), ("", False), ("false", False)):
            with self.subTest(value=value), mock.patch.dict(os.environ):
                os.environ.pop("CLAUDE_CODE_REMOTE", None)
                if value is not None:
                    os.environ["CLAUDE_CODE_REMOTE"] = value
                self.assertIs(fn(), want)

    def test_the_report_check_holds_the_guard_core_is_cloud(self):
        fn = self.helper()
        self.assertTrue(callable(fn), "guard_core has no is_cloud: the cloud check has no one home yet")
        self.assertIs(getattr(glr, "is_cloud", None), fn, "the n/a (cloud) check does not hold guard_core.is_cloud")


class CloudPaceReadTests(unittest.TestCase):
    """Pace number four (reports-batch-pace-numbers) reads the local brake count. In a cloud session,
    CLAUDE_CODE_REMOTE == "true" (the check merge/merge.py makes), `--between ... --rule load-brake` prints
    `n/a (cloud)`, never 0: a 0 would claim a reading that was never taken. Every other read keeps today's
    output. Each test sets or pops the variable itself, so the runner's own environment decides nothing.
    """

    def read(self, argv, remote):
        """Run main(argv) with CLAUDE_CODE_REMOTE set to `remote`, or unset when `remote` is None."""
        with mock.patch.dict(os.environ):
            os.environ.pop("CLAUDE_CODE_REMOTE", None)
            if remote is not None:
                os.environ["CLAUDE_CODE_REMOTE"] = remote
            return run_main(argv)

    def test_cloud_brake_read_prints_n_a_and_not_the_line(self):
        path = fresh_log([PLUS_FIVE_LINE])
        rc, out = self.read(["--log", path] + BRAKE_WINDOW + ["--rule", "load-brake"], "true")
        self.assertEqual((rc, out), (0, CLOUD_NA))

    def test_cloud_brake_read_with_no_log_file_prints_n_a(self):
        path = fresh_log()
        self.assertFalse(os.path.exists(path))
        rc, out = self.read(["--log", path] + BRAKE_WINDOW + ["--rule", "load-brake"], "true")
        self.assertEqual((rc, out), (0, CLOUD_NA))

    def test_local_brake_read_keeps_the_row_and_the_unknown_count(self):
        path = fresh_log([PLUS_FIVE_LINE, OLD_LINE])
        argv = ["--log", path] + BRAKE_WINDOW + ["--rule", "load-brake"]
        expected = PLUS_FIVE_LINE + "\n" + UNKNOWN_LINE % 1 + "\n"
        for remote in (None, "false"):
            with self.subTest(CLAUDE_CODE_REMOTE=remote):
                self.assertEqual(self.read(argv, remote), (0, expected))

    def test_cloud_read_of_another_rule_or_no_rule_keeps_today_output(self):
        path = fresh_log([PLUS_FIVE_LINE, SHARED_INSIDE, OLD_LINE, OLD_SHARED])
        cases = (
            ("--rule shared-tree", ["--rule", "shared-tree"], SHARED_INSIDE + "\n" + UNKNOWN_LINE % 1 + "\n"),
            ("no --rule", [], PLUS_FIVE_LINE + "\n" + SHARED_INSIDE + "\n" + UNKNOWN_LINE % 2 + "\n"),
        )
        for label, extra, expected in cases:
            with self.subTest(read=label):
                self.assertEqual(self.read(["--log", path] + BRAKE_WINDOW + extra, "true"), (0, expected))

    def test_cloud_summary_read_matches_the_local_summary(self):
        path = fresh_log([PLUS_FIVE_LINE, SHARED_INSIDE, OLD_LINE])
        argv = ["--log", path, "--days", "all", "--rule", "load-brake"]
        local = self.read(argv, None)
        self.assertIn("| load-brake | 2 | 0 | 0 |", local[1])
        self.assertEqual(self.read(argv, "true"), local)


class FixedDecisionTests(unittest.TestCase):
    """A `fixed` line (an STE guard rewrite) is counted under the noted column. Pinned choice: map
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


class OverrideDecisionTests(unittest.TestCase):
    """A lifted act writes a line whose decision is `override` and whose rule is the one it lifted
    (the owner override). The report counts those lines per rule and per session, so the owner
    can see which refusals an override lifted. Without it they would print under the verbatim lines."""

    LINES = [
        "2026-10-11T09:00:00\tBash\toverride\tmachine-wide-kill\tkill $(pgrep x)\tsess-a",
        "2026-10-11T09:05:00\tBash\toverride\tmachine-wide-kill\tkill 4242\tsess-a",
        "2026-10-11T09:10:00\tBash\toverride\tshared-tree\tgit stash --help -h\tsess-b",
        "2026-10-11T09:15:00\tBash\tdeny\tmachine-wide-kill\tkill 1\tsess-a",
        "2026-10-04T09:00:00\tBash\toverride\tmachine-wide-kill\toutside the window\tsess-a",
    ]

    def test_override_lines_are_counted_by_rule_and_session_not_left_verbatim(self):
        s = glr.summarize(self.LINES, 7, NOW)
        kill = s["by_rule"]["machine-wide-kill"]
        self.assertEqual((kill.get("override"), kill["deny"]), (2, 1))
        self.assertEqual(s["by_rule"]["shared-tree"].get("override"), 1)
        self.assertEqual(s["other"], [])
        self.assertEqual(s["per_day"]["2026-10-11"], 1)  # the per-day row counts denies only
        self.assertEqual(s["by_session"]["sess-a"]["machine-wide-kill"].get("override"), 2)
        self.assertEqual(s["by_session"]["sess-b"]["shared-tree"].get("override"), 1)


# ------------------------------------------------------------ the rules that never fired
#
# No constant holds the rule ids. They are string literals where the guard writes a line, so the
# expected set below is read from that source with `ast`, never copied into this file. A copy
# would go stale the day a rule is added, and the cull would trust it.

HOOK_SOURCES = sorted(p for p in glob.glob(os.path.join(HOOKS_DIR, "*.py"))
                      if not os.path.basename(p).startswith("test_"))  # every hook module; a test module writes no id
RULE_ARG = {"refuse": 2, "record": 2, "ask_command": 0}  # the position of the rule id in each guard call
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _text_constants(node):
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _text(node):
    """The text of a string literal, or None."""
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _module_bindings(tree):
    """{name: [value]} for each top-level binding. A plain assignment gives its value node. Any other binding (an
    import, a def, a class, a name unpacked from a call) gives None. A tuple of the same length unpacks pairwise."""
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            pairs = []
            for target in node.targets:
                if isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple) \
                        and len(target.elts) == len(node.value.elts):
                    pairs += list(zip(target.elts, node.value.elts))
                else:
                    pairs.append((target, node.value))
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            pairs = [(node.target, node.value)]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.setdefault(node.name, []).append(None)
            continue
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                out.setdefault((alias.asname or alias.name).split(".")[0], []).append(None)
            continue
        else:
            continue
        for target, value in pairs:
            for name in (n for n in ast.walk(target) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)):
                out.setdefault(name.id, []).append(value if name is target else None)
    return out


def _constants(bindings):
    """{name: text} for each top-level name bound once, to a string literal."""
    return {n: _text(vs[0]) for n, vs in bindings.items() if len(vs) == 1 and _text(vs[0]) is not None}


def _tables(bindings):
    """{name: Dict node} for each top-level name bound once, to a dict display."""
    return {n: vs[0] for n, vs in bindings.items() if len(vs) == 1 and isinstance(vs[0], ast.Dict)}


def _scope_chains(tree):
    """{id(call): the defs and lambdas that hold it, innermost first}. Iterative, so a long expression cannot hit
    the recursion limit."""
    held, todo = {}, [(tree, ())]
    while todo:
        node, chain = todo.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Call):
                held[id(child)] = chain
            todo.append((child, (child,) + chain if isinstance(child, _SCOPES) else chain))
    return held


def _own_nodes(scope):
    """The nodes of a def's or lambda's own body. A nested def, lambda or class is another scope: its name is bound
    here, but its body is not read here."""
    todo = list(scope.body) if isinstance(scope.body, list) else [scope.body]
    out = []
    while todo:
        node = todo.pop()
        out.append(node)
        if not isinstance(node, _SCOPES + (ast.ClassDef,)):
            todo.extend(ast.iter_child_nodes(node))
    return out


def _literal_tuples(bindings):
    """{name: [text]} for each top-level name bound once, to a tuple of string literals."""
    out = {}
    for name, vs in bindings.items():
        if len(vs) == 1 and isinstance(vs[0], ast.Tuple) and all(_text(e) is not None for e in vs[0].elts):
            out[name] = [_text(e) for e in vs[0].elts]
    return out


class _Bound:
    """What one def binds a name to: the rule ids the name can hold, and for a tuple-valued name the ids in each
    column."""

    def __init__(self):
        self.ids, self.columns = set(), {}


class _Chain:
    """What the names visible at one call hold: the nearest def that binds a name, else the module."""

    def __init__(self, reader, scopes):
        self.reader, self.scopes = reader, scopes

    def _bound(self, name):
        for scope in self.scopes:
            names = self.reader.bound_in(scope)
            if name in names:
                return names[name]
        return None

    def name(self, name):
        found = self._bound(name)
        return found.ids if found is not None else self.reader.module_ids(name)

    def column(self, name, index):
        found = self._bound(name)
        return found.columns.get(index, set()) if found is not None else set()


class _Local:
    """The names a def binds while its own assigned values are read: a name reads as the module's constant, and a
    tuple-valued name reads the columns that the first pass has read from its comprehension."""

    def __init__(self, reader, bound):
        self.reader, self.bound = reader, bound

    def name(self, name):
        return self.reader.module_ids(name)

    def column(self, name, index):
        found = self.bound.get(name)
        return found.columns.get(index, set()) if found is not None else set()


class _Reader:
    """One hook module's rule ids. A value it cannot place holds no id, so a call that passes one names nothing, as
    a variable always has (test_a_variable_rule_names_no_id). Read from the source with `ast`, never from rule_audit."""

    def __init__(self, source, base_dir):
        self.tree = ast.parse(source)
        bindings = _module_bindings(self.tree)
        self.constants, self.tables = _constants(bindings), _tables(bindings)
        self.literal_tuples = _literal_tuples(bindings)
        self.defs = {n.name: n for n in self.tree.body if isinstance(n, ast.FunctionDef)}
        self.chains = _scope_chains(self.tree)
        self.base_dir = base_dir
        self.siblings = self._sibling_imports()
        self.module = _Chain(self, ())
        self.sibling_cache, self.scope_names = {}, {}

    def _sibling_imports(self):
        """{name: module} for each `import X` that names a sibling module file under base_dir."""
        found = {}
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import) and self.base_dir:
                for alias in node.names:
                    if "." not in alias.name and os.path.isfile(os.path.join(self.base_dir, alias.name + ".py")):
                        found[alias.asname or alias.name] = alias.name
        return found

    def sibling_constant(self, local, attr):
        """The string constant `attr` of the sibling module that `local` names, or None."""
        module = self.siblings.get(local)
        if module is None:
            return None
        if module not in self.sibling_cache:
            with open(os.path.join(self.base_dir, module + ".py"), encoding="utf-8") as handle:
                self.sibling_cache[module] = _constants(_module_bindings(ast.parse(handle.read())))
        return self.sibling_cache[module].get(attr)

    def module_ids(self, name):
        return {self.constants[name]} if name in self.constants else set()

    def bound_in(self, scope):
        """{name: _Bound} for the names a def or lambda binds, read once per scope."""
        if id(scope) not in self.scope_names:
            self.scope_names[id(scope)] = self._bind(scope)
        return self.scope_names[id(scope)]

    def ids(self, expr, ctx):
        """The ids an expression can hold, read through `ctx`: a string literal, a name, a conditional's branches,
        the element of min() or max() over a tuple-valued name, or a sibling module's constant. Anything else holds
        none."""
        text = _text(expr)
        if text is not None:
            return {text}
        if isinstance(expr, ast.Name):
            return ctx.name(expr.id)
        if isinstance(expr, ast.IfExp):
            return self.ids(expr.body, ctx) | self.ids(expr.orelse, ctx)
        if isinstance(expr, ast.Subscript) and isinstance(expr.slice, ast.Constant) \
                and isinstance(expr.slice.value, int) and isinstance(expr.value, ast.Call) \
                and isinstance(expr.value.func, ast.Name) and expr.value.func.id in ("min", "max") \
                and len(expr.value.args) == 1 and isinstance(expr.value.args[0], ast.Name):
            return ctx.column(expr.value.args[0].id, expr.slice.value)
        if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
            const = self.sibling_constant(expr.value.id, expr.attr)
            return {const} if const is not None else set()
        return set()

    def column(self, table, index):
        """The ids in column `index` of a literal table: the element there of each row, when it names an id."""
        found = set()
        for row in table.values:
            if isinstance(row, ast.Tuple) and len(row.elts) > index:
                found |= self.ids(row.elts[index], self.module)
        return found

    def comprehension_columns(self, comp):
        """{index: ids} for a comprehension whose element is a tuple: an element that is the loop variable over a
        literal tuple of the module holds that tuple's strings in its column."""
        columns = {}
        if not isinstance(comp.elt, ast.Tuple):
            return columns
        for gen in comp.generators:
            if isinstance(gen.target, ast.Name) and isinstance(gen.iter, ast.Name) \
                    and gen.iter.id in self.literal_tuples:
                for index, elt in enumerate(comp.elt.elts):
                    if isinstance(elt, ast.Name) and elt.id == gen.target.id:
                        columns.setdefault(index, set()).update(self.literal_tuples[gen.iter.id])
        return columns

    def assign(self, target, value, bound, ctx):
        """Add the ids that a value gives each name it is assigned to."""
        if isinstance(target, ast.Name):
            bound[target.id].ids |= self.ids(value, ctx)
        elif isinstance(target, (ast.Tuple, ast.List)):
            if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(target.elts):
                for t, v in zip(target.elts, value.elts):
                    self.assign(t, v, bound, ctx)
            elif isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name) \
                    and value.value.id in self.tables:
                for index, t in enumerate(target.elts):
                    if isinstance(t, ast.Name):
                        bound[t.id].ids |= self.column(self.tables[value.value.id], index)

    def _bind(self, scope):
        bound, args = {}, scope.args
        for arg in args.posonlyargs + args.args + args.kwonlyargs + [args.vararg, args.kwarg]:
            if arg is not None:
                bound[arg.arg] = _Bound()
        own = _own_nodes(scope)
        for node in own:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.setdefault(node.name, _Bound())
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    bound.setdefault((alias.asname or alias.name).split(".")[0], _Bound())
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                bound.setdefault(node.id, _Bound())
            elif isinstance(node, ast.ExceptHandler) and node.name:
                bound.setdefault(node.name, _Bound())
        # The first pass reads each name bound to a comprehension, so that the second pass can read its columns.
        for node in own:
            if isinstance(node, ast.Assign) and isinstance(node.value, (ast.ListComp, ast.GeneratorExp)):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        bound[target.id].columns.update(self.comprehension_columns(node.value))
        local = _Local(self, bound)
        for node in own:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    self.assign(target, node.value, bound, local)
            elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and isinstance(node.target, ast.Name) \
                    and node.value is not None:
                bound[node.target.id].ids |= self.ids(node.value, local)
        return bound

    def forwarded(self, helper):
        """The position of the helper's parameter that one of its guard calls takes as the rule, or None."""
        params = [a.arg for a in helper.args.posonlyargs + helper.args.args]
        for node in ast.walk(helper):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                at = RULE_ARG.get(node.func.attr)
                if at is not None and len(node.args) > at and isinstance(node.args[at], ast.Name) \
                        and node.args[at].id in params:
                    return params.index(node.args[at].id)
        return None

    def rule_position(self, call):
        """The argument a guard call takes as its rule, or None. A module def named like a guard function that makes
        guard calls of its own is a helper with its own signature: a call to it takes the rule where the def forwards
        it. A def that makes none (guard.py's ask_command) keeps the guard function's position."""
        func = call.func
        if isinstance(func, ast.Name) and func.id in self.defs and any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in RULE_ARG
                for n in ast.walk(self.defs[func.id])):
            return self.forwarded(self.defs[func.id])
        return RULE_ARG.get(func.id if isinstance(func, ast.Name) else getattr(func, "attr", ""))

    def ids_written(self):
        ids = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                at = self.rule_position(node)
                if at is not None and len(node.args) > at:
                    ids |= self.ids(node.args[at], _Chain(self, self.chains.get(id(node), ())))
            elif isinstance(node, ast.FunctionDef) and node.name == "diff_rule":
                for stmt in node.body:  # a docstring is a bare string statement: it names no id
                    if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)):
                        ids |= _text_constants(stmt)
            elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Tuple) \
                    and [getattr(e, "id", "") for e in node.targets[0].elts] == ["code", "why"]:
                ids |= _text_constants(node.value)
        return ids


def emitted_guard_rules(source, base_dir=None):
    """The rule ids one hook source can write to guard.log, read with `ast`.

    A literal, a module-level string constant, or a name the def around the call binds to literals (or a
    conditional of them), in refuse()/record() (third argument) or ask_command() (first argument) writes an id.
    So does a constant that a module tuple or literal table holds in that place, and a constant or literal that a
    module helper named refuse() forwards as the rule. A sibling module's constant is read from base_dir. The
    diff_rule() table and the `code, why = {...}` role-scope table write ids too. A call that passes any other
    value (a parameter, a call's result, a variable of unknown value) names no id.
    """
    return _Reader(source, base_dir).ids_written()


def emitted_rules():
    """Every id a hook writes. No STE id is emitted: no hook writes one now (decision ste-guard-fixes-not-nags),
    so an STE row of --all-rules comes from the log alone."""
    ids = set()
    for path in HOOK_SOURCES:
        with open(path, encoding="utf-8") as handle:
            ids |= emitted_guard_rules(handle.read(), HOOKS_DIR)
    return ids


class EmittedRuleReaderTests(unittest.TestCase):
    """The reader that says which ids exist is itself pinned, so a red AllRulesTests names the report."""

    def test_it_reads_every_shape_that_writes_an_id_from_the_real_source(self):
        # Both readers: rule_audit's is the product, the one in this file is the oracle.
        for who, ids in (("rule_audit", rule_audit.emitted_rule_ids()), ("oracle", emitted_rules())):
            with self.subTest(reader=who):
                self.check_needles(ids)

    def check_needles(self, ids):
        for needle in ("shared-tree",                                   # refuse() literal
                       "role-diff-main-checkout", "guard-crash",        # record() after a tool-name literal
                       "bare-merge",                                    # ask_command() only
                       "builder-diff", "author-diff", "writer-diff",    # diff_rule() table
                       "builder-test-edit", "test-author-scope", "record-writer-scope",  # role-scope table
                       "agent-model-cap"):                           # guard.py and config_watch.py
            self.assertIn(needle, ids)
        self.assertEqual(sorted(i for i in ids if i.startswith("STE")), [],  # only the removed guard wrote these
                         "an STE id no hook writes would show as never-fired in a cull")
        self.assertGreaterEqual(len(ids), 40)  # a floor: a reader that finds fewer has lost a call shape

    def test_a_comment_opener_inside_a_string_hides_no_call(self):
        src = ('record(tool, "noted", "a-rule", "// not a comment /* nor this */ # nor this")\n'
               'refuse(tool, "deny", "b-rule", "x", "y")\n')
        self.assertEqual(emitted_guard_rules(src), {"a-rule", "b-rule"})

    def test_a_multi_line_string_that_only_describes_a_call_names_no_id(self):
        src = ('DOC = """\nrefuse(tool, "deny", "ghost-rule", R, m)\n"""\n'
               'record(tool, "noted", "real-rule", "m")\n')
        self.assertEqual(emitted_guard_rules(src), {"real-rule"})

    def test_a_lone_quote_in_text_hides_no_call(self):
        src = ("# don't stop here\nNOTE = \"it's\"\nrefuse(tool, \"deny\", \"after-quote\", NOTE, \"m\")\n")
        self.assertEqual(emitted_guard_rules(src), {"after-quote"})

    def test_a_variable_rule_names_no_id(self):
        self.assertEqual(emitted_guard_rules("record(tool, decision, rule, matched)\n"), set())

    def test_a_module_constant_rule_id_is_read_to_its_value(self):
        self.assertEqual(emitted_guard_rules('RID = "const-rule-id"\nrefuse(tool, "deny", RID, R, m)\n'),
                         {"const-rule-id"})

    def test_a_parameter_named_like_a_constant_is_no_constant(self):
        src = 'RID = "const-rule-id"\ndef go(RID):\n    refuse(tool, "deny", RID, R, m)\n'
        self.assertEqual(emitted_guard_rules(src), set())

    def test_a_def_local_name_assigned_a_literal_lists_that_id(self):
        src = 'def go():\n    rid = "oracle-local-rule"\n    refuse(tool, "deny", rid, R, m)\n'
        self.assertEqual(emitted_guard_rules(src), {"oracle-local-rule"})

    def test_a_def_local_name_assigned_a_conditional_of_literals_lists_both(self):
        src = 'def go(c):\n    rid = "oracle-a" if c else "oracle-b"\n    refuse(tool, "deny", rid, R, m)\n'
        self.assertEqual(emitted_guard_rules(src), {"oracle-a", "oracle-b"})

    def test_the_oracle_lists_the_ids_of_every_hook_that_writes_one(self):
        if HOOKS_DIR not in sys.path:
            sys.path.insert(0, HOOKS_DIR)
        import blind_brief
        import call_judge
        import prose_judge
        import question_form
        import reply_judge
        import sendmessage_state
        wanted = {blind_brief.RULE, prose_judge.RULE, sendmessage_state.RULE, reply_judge.JUDGE_RULE,
                  call_judge.SPAWN_RULE, call_judge.QUESTION_RULE, question_form.PAST_RULING_RULE}
        self.assertEqual(sorted(wanted - emitted_rules()), [],
                         "the oracle reads only guard*.py and config_watch.py, so these ids are not in its list")

    def test_a_helper_forwards_its_fourth_argument_as_the_rule(self):
        # call_judge's refuse(payload, tool, args, rule, reason) hands its fourth argument on as the rule.
        src = ('def refuse(payload, tool, args, rule, reason):\n'
               '    guard_core.refuse(tool, "deny", rule, reason, "")\n'
               'def go(payload, tool, args):\n'
               '    refuse(payload, tool, args, "helper-rule", "why")\n')
        self.assertEqual(emitted_guard_rules(src), {"helper-rule"})

    def test_a_helper_whose_rule_is_a_constant_leaves_its_literal_reason_unlisted(self):
        # blind_brief's refuse(payload, tool, reason, matched) takes its rule from a constant, so the literal
        # in its third argument is a reason, not an id.
        src = ('RULE = "fixed-helper-rule"\n'
               'def refuse(payload, tool, reason, matched):\n'
               '    guard_core.refuse(tool, "deny", RULE, reason, matched)\n'
               'def go(payload, tool):\n'
               '    refuse(payload, tool, "a literal reason", "m")\n')
        self.assertEqual(emitted_guard_rules(src), {"fixed-helper-rule"})

    def test_a_tuple_of_literal_constants_names_each_constant(self):
        src = ('SPAWN_RULE, QUESTION_RULE = "tuple-x", "tuple-y"\n'
               'def go(tool):\n'
               '    refuse(tool, "deny", SPAWN_RULE, R, m)\n'
               '    refuse(tool, "deny", QUESTION_RULE, R, m)\n')
        self.assertEqual(emitted_guard_rules(src), {"tuple-x", "tuple-y"})

    def test_a_name_unpacked_from_a_literal_table_names_that_column(self):
        # call_judge's JUDGES table: `prompt, model, timeout, rule, fallback = JUDGES[tool]` reads column 3.
        src = ('JUDGES = {"Agent": (1, ROUTE_RULE), "Ask": (2, "ask-rule")}\n'
               'ROUTE_RULE = "route-rule"\n'
               'def go(tool):\n'
               '    count, rule = JUDGES[tool]\n'
               '    refuse(tool, "deny", rule, R, m)\n')
        self.assertEqual(emitted_guard_rules(src), {"route-rule", "ask-rule"})

    def test_a_computed_rule_with_a_constant_branch_names_the_constant(self):
        # reply_judge: `rule = min(found)[1] if found else JUDGE_RULE`. The computed branch names no id here.
        src = ('JUDGE_RULE = "judge-const"\n'
               'def go(found):\n'
               '    rule = min(found)[1] if found else JUDGE_RULE\n'
               '    record("Stop", "noted", rule, "m")\n')
        self.assertEqual(emitted_guard_rules(src), {"judge-const"})

    def test_a_minimum_of_a_comprehension_over_a_literal_tuple_names_its_elements(self):
        # reply_judge's log_finding: the rule is the element of the literal tuple that the reason names, `min(found)[1]`.
        src = ('JUDGED = ("alpha-judged", "beta-judged")\n'
               'def go(reason):\n'
               '    found = [(reason.find(r), r) for r in JUDGED if r in reason]\n'
               '    rule = min(found)[1] if found else "fallback-rule"\n'
               '    record("Stop", "noted", rule, "m")\n')
        self.assertEqual(emitted_guard_rules(src), {"alpha-judged", "beta-judged", "fallback-rule"})


# ------------------------------------------------------------ the rule id each hook logs, exactly
# A guard.log line carries the rule id as its fourth tab field. Each case drives one hook in-process, with the model
# call patched and CLAUDE_CONFIG_DIR at a folder of its own, then reads that field exactly. A substring, or the
# decision field, would pass a line that names the wrong id.

def guard_log_rows(config):
    """The guard.log lines of `config`, each as its tab fields. No file is no line."""
    try:
        with open(os.path.join(config, "guard.log"), encoding="utf-8") as handle:
            return [line.rstrip("\n").split("\t") for line in handle]
    except OSError:
        return []


def stdin_of(payload):
    """A stdin that reads as the hooks read it: text for json.load, and a .buffer for sys.stdin.buffer.read()."""
    return io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode("utf-8")), encoding="utf-8")


def reply_reason(rule):
    """A reply judge's reason that names one rule id, as the model writes it."""
    return "The reply breaks %s, so the owner gets a rewrite." % rule


class ExactGuardLogRuleTests(unittest.TestCase):
    """The rule id each hook writes to guard.log, read from that line's own rule field."""

    def config(self):
        folder = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, folder, True)
        return folder

    def logged(self, config, decision):
        return [row[3] for row in guard_log_rows(config) if len(row) >= 4 and row[2] == decision]

    def reply_rules_logged(self, rule):
        import decision_watch
        import reply_judge
        config = self.config()
        payload = {"session_id": "sess-reply", "last_assistant_message": "A finished reply for the owner."}
        verdict = {"ok": False, "reason": reply_reason(rule)}
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": config}), \
                mock.patch.object(decision_watch, "invoke_model", return_value=(verdict, None)), \
                mock.patch("sys.stdin", stdin_of(payload)), contextlib.redirect_stdout(io.StringIO()):
            reply_judge.main()
        return self.logged(config, "noted")

    def test_an_owner_override_reason_logs_the_owner_override_rule(self):
        if HOOKS_DIR not in sys.path:
            sys.path.insert(0, HOOKS_DIR)
        import override
        config = self.config()
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": config}):
            override.grant("sess-owner", "override, fix the widget", datetime.now(timezone.utc))
        self.assertEqual(self.logged(config, "override-reason"), ["owner-override"])

    def test_a_past_ruling_cite_logs_the_past_ruling_rule(self):
        if HOOKS_DIR not in sys.path:
            sys.path.insert(0, HOOKS_DIR)
        import call_judge
        import question_form
        config = self.config()
        payload = {"tool_name": "AskUserQuestion", "tool_input": {"questions": []}, "session_id": "sess-past",
                   "cwd": config}
        verdict = {"ok": False, "reason": "decisions/apps-keep-access: the owner already ruled this."}
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": config}), \
                mock.patch.object(question_form, "chat_hit", return_value=("", "")), \
                mock.patch.object(question_form, "chat_units", return_value=[("", "the question")]), \
                mock.patch.object(call_judge, "past_ruling_context",
                                  return_value=("", ["decisions/apps-keep-access"], [])), \
                mock.patch.object(call_judge, "invoke_model", return_value=(verdict, None)), \
                mock.patch("sys.stdin", stdin_of(payload)), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):  # the refusal exits after it logs
                call_judge.main()
        self.assertEqual(self.logged(config, "deny"), ["past-ruling"])

    def test_a_prose_refusal_logs_the_prose_judge_rule(self):
        if HOOKS_DIR not in sys.path:
            sys.path.insert(0, HOOKS_DIR)
        import prose_judge
        config = self.config()
        payload = {"tool_name": "Edit",
                   "tool_input": {"file_path": "docs/decisions/a-record.md", "old_string": "x", "new_string": "y"},
                   "session_id": "sess-prose", "cwd": config}
        verdict = {"ok": False, "reason": "the edit breaks the record's rules."}
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": config}), \
                mock.patch.object(prose_judge, "invoke_model", return_value=(verdict, None)), \
                mock.patch("sys.stdin", stdin_of(payload)), contextlib.redirect_stdout(io.StringIO()):
            prose_judge.main()
        self.assertEqual(self.logged(config, "deny"), ["prose-judge"])

    def test_output_never_paste_passing_output_is_logged_by_its_own_id(self):
        self.assertEqual(self.reply_rules_logged("output-never-paste-passing-output"),
                         ["output-never-paste-passing-output"])

    def test_output_start_with_point_is_logged_by_its_own_id(self):
        self.assertEqual(self.reply_rules_logged("output-start-with-point"), ["output-start-with-point"])

    def test_questions_go_to_owner_is_logged_by_its_own_id(self):
        self.assertEqual(self.reply_rules_logged("questions-go-to-owner"), ["questions-go-to-owner"])

    def test_style_cut_narration_is_logged_by_its_own_id(self):
        self.assertEqual(self.reply_rules_logged("style-cut-narration"), ["style-cut-narration"])

    def test_style_limits_kept_silently_is_logged_by_its_own_id(self):
        self.assertEqual(self.reply_rules_logged("style-limits-kept-silently"), ["style-limits-kept-silently"])

    def test_style_question_form_is_logged_by_its_own_id(self):
        self.assertEqual(self.reply_rules_logged("style-question-form"), ["style-question-form"])

    def test_style_table_gold_column_is_logged_by_its_own_id(self):
        self.assertEqual(self.reply_rules_logged("style-table-gold-column"), ["style-table-gold-column"])


def run_cli(argv):
    """Run main(argv); return (exit code, stdout, stderr). A refused flag exits 2 and is a result."""
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = glr.main(argv)
    except SystemExit as exc:
        rc = exc.code
    return rc, out.getvalue(), err.getvalue()


def _cells(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def rule_table(out):
    """The per-rule table of a report as {rule: {column name: cell}}. Columns are read by header
    name, so the optional override column and the first-seen column's own name do not matter."""
    lines = out.splitlines()
    head = next((i for i, line in enumerate(lines) if line.startswith("| rule |")), None)
    if head is None:
        raise AssertionError("no per-rule table in the report:\n" + out)
    names = _cells(lines[head])
    rows = {}
    for line in lines[head + 2:]:
        if not line.startswith("|"):
            break
        cells = _cells(line)
        rows[cells[0]] = dict(zip(names[1:], cells[1:]))
    return rows


def first_seen(row):
    """The one column that is no count: the date of the rule's first line, or "never"."""
    extra = [cell for name, cell in row.items() if name not in ("deny", "ask", "noted", "override")]
    if len(extra) != 1 or not re.fullmatch(r"never|\d{4}-\d\d-\d\d", extra[0]):
        raise AssertionError("expected one first-seen column holding YYYY-MM-DD or never: %r" % (row,))
    return extra[0]


def counts(row):
    return tuple(int(row[name]) for name in ("deny", "ask", "noted"))


def days_ago(n):
    return (datetime.now().date() - timedelta(days=n)).isoformat()


def stamped(n, decision, rule, matched="x"):
    """A five-field guard.log line n days back, at noon so a day boundary never moves it."""
    return "\t".join([days_ago(n) + "T12:00:00", "Bash", decision, rule, matched])


class AllRulesTests(unittest.TestCase):
    def report(self, lines, *flags):
        with tempfile.TemporaryDirectory() as folder:
            path = write_log(os.path.join(folder, "guard.log"), lines)
            rc, out, err = run_cli(["--log", path] + list(flags))
        self.assertEqual(rc, 0, "the report refused its flags: %s" % err)
        return out

    def test_a_rule_with_no_lines_shows_0_and_never(self):
        out = self.report([stamped(1, "deny", "shared-tree")], "--all-rules", "--days", "7")
        row = rule_table(out)["git-env-set"]
        self.assertEqual((counts(row), first_seen(row)), ((0, 0, 0), "never"))

    def test_every_rule_of_an_empty_log_shows_0_and_never(self):
        rows = rule_table(self.report([], "--all-rules", "--days", "all"))
        self.assertTrue(rows)
        self.assertEqual({(counts(r), first_seen(r)) for r in rows.values()}, {((0, 0, 0), "never")})

    def test_a_rule_with_lines_shows_its_counts_and_first_date(self):
        out = self.report([
            stamped(3, "deny", "shared-tree"), stamped(2, "ask", "shared-tree"),
            stamped(1, "deny", "shared-tree"), stamped(0, "noted", "shared-tree"),
            stamped(2, "deny", "retired-rule"),  # an id no source emits any more keeps its row
        ], "--all-rules", "--days", "7")
        rows = rule_table(out)
        self.assertEqual((counts(rows["shared-tree"]), first_seen(rows["shared-tree"])),
                         ((2, 1, 1), days_ago(3)))
        self.assertEqual((counts(rows["retired-rule"]), first_seen(rows["retired-rule"])),
                         ((1, 0, 0), days_ago(2)))
        self.assertEqual(first_seen(rows["git-env-set"]), "never")  # its neighbours stay silent

    def test_a_line_of_any_decision_means_the_rule_fired(self):
        # A lifted refusal, a revert and a crash are lines. `never` would let a cull delete a rule that acted.
        out = self.report([stamped(5, "override", "machine-wide-kill"),
                           stamped(4, "reverted", "agent-model-cap"),
                           stamped(3, "crash", "guard-crash")], "--all-rules", "--days", "7")
        rows = rule_table(out)
        self.assertEqual([first_seen(rows[r]) for r in ("machine-wide-kill", "agent-model-cap", "guard-crash")],
                         [days_ago(5), days_ago(4), days_ago(3)])

    def test_a_combined_ste_line_credits_each_code(self):
        # The guard writes the codes it found as one id, `STE007,STE008`. STE007 fired on that line.
        out = self.report([stamped(2, "deny", "STE007,STE008")], "--all-rules", "--days", "7")
        rows = rule_table(out)
        self.assertEqual((first_seen(rows["STE007"]), first_seen(rows["STE008"])), (days_ago(2), days_ago(2)))
        self.assertNotIn("STE009", rows)  # a code the log never held has no row: no hook emits it

    def test_an_empty_log_lists_no_ste_row(self):
        rows = rule_table(self.report([], "--all-rules", "--days", "all"))
        self.assertEqual(sorted(r for r in rows if r.startswith("STE")), [])

    def test_a_log_with_one_ste_code_lists_that_row_and_no_other_ste_row(self):
        rows = rule_table(self.report([stamped(2, "deny", "STE008")], "--all-rules", "--days", "7"))
        self.assertEqual(sorted(r for r in rows if r.startswith("STE")), ["STE008"])
        self.assertEqual((counts(rows["STE008"]), first_seen(rows["STE008"])), ((1, 0, 0), days_ago(2)))

    def test_the_listed_ids_equal_the_ids_the_guard_and_the_other_guards_emit(self):
        listed = set(rule_table(self.report([], "--all-rules", "--days", "all")))
        expected = emitted_rules()
        self.assertEqual(
            (sorted(expected - listed), sorted(listed - expected)), ([], []),
            "left: emitted by the source but not listed (a rule that never fired would not show); "
            "right: listed but emitted nowhere (a stale copy)")

    def test_rule_audit_reads_the_same_ids_as_the_independent_reader(self):
        got, expected = rule_audit.emitted_rule_ids(), emitted_rules()
        self.assertEqual(
            (sorted(expected - got), sorted(got - expected)), ([], []),
            "left: the oracle reads it, rule_audit does not (a rule that never fired would not show); "
            "right: rule_audit reads it, the oracle does not")

    def cut_id(self):
        """The rule field the deleted STE guard's logger wrote for a combined id past its 40-character
        limit. An old guard.log still holds such lines, and nothing writes them now. The cut is made
        by guard_core.log_cut, so the mark is never copied here. Returns (field, the codes it kept)."""
        import guard_core
        codes = ["STE%03d" % n for n in (1, 3, 7, 8, 11, 12, 13, 14)]
        field = guard_core.log_cut(",".join(codes), 40)
        kept = field.split(" ")[0].split(",")
        self.assertTrue(field.endswith(" [cut]"), "the fixture is no longer cut: %r" % field)
        self.assertTrue(2 <= len(kept) < len(codes), kept)
        return field, kept

    def test_a_code_seen_only_in_a_cut_combined_line_gets_its_count_and_first_date(self):
        # The old guard's logger cut the rule field at 40 characters and marked it ` [cut]`. The cut id is no
        # longer a clean combined id, but the codes it kept did fire: `never` would let a cull delete them.
        field, kept = self.cut_id()
        out = self.report([stamped(3, "deny", field), stamped(1, "ask", field)], "--all-rules", "--days", "7")
        rows = rule_table(out)
        for code in kept:
            self.assertEqual((counts(rows[code]), first_seen(rows[code])), ((1, 1, 0), days_ago(3)), code)
        self.assertNotIn("STE009", rows)  # a code the line never held has no row

    def test_a_cut_combined_line_outside_the_window_still_dates_each_code(self):
        field, kept = self.cut_id()
        rows = rule_table(self.report([stamped(400, "deny", field)], "--all-rules", "--days", "7"))
        for code in kept:
            self.assertEqual((counts(rows[code]), first_seen(rows[code])), ((0, 0, 0), days_ago(400)), code)

    def test_a_plain_ste_line_outside_the_window_keeps_its_row_and_no_other_ste_row_shows(self):
        # The log holds the code, so the row stays and a cull sees its date. No STE code the log lacks is listed.
        rows = rule_table(self.report([stamped(400, "deny", "STE008")], "--all-rules", "--days", "7"))
        self.assertEqual(sorted(r for r in rows if r.startswith("STE")), ["STE008"])
        self.assertEqual((counts(rows["STE008"]), first_seen(rows["STE008"])), ((0, 0, 0), days_ago(400)))

    def test_days_all_reads_the_whole_log(self):
        lines = [stamped(400, "deny", "waiter"), stamped(1, "deny", "waiter")]
        everything = rule_table(self.report(lines, "--days", "all"))
        self.assertEqual(everything["waiter"]["deny"], "2")
        week = rule_table(self.report(lines, "--days", "7"))
        self.assertEqual(week["waiter"]["deny"], "1")  # the same log, one week: the old line is out

    def test_days_all_with_all_rules_dates_the_first_line_and_counts_it(self):
        out = self.report([stamped(400, "deny", "waiter"), stamped(1, "deny", "waiter")],
                          "--all-rules", "--days", "all")
        row = rule_table(out)["waiter"]
        self.assertEqual((counts(row), first_seen(row)), ((2, 0, 0), days_ago(400)))

    def test_days_refuses_a_word_other_than_all(self):
        rc, out, err = run_cli(["--log", os.devnull, "--days", "soon"])
        self.assertEqual(rc, 2)
        self.assertIn("--days", err)

    def test_without_the_flag_a_silent_rule_is_not_listed(self):
        out = self.report([stamped(1, "deny", "shared-tree")], "--days", "7")
        self.assertIn("| shared-tree | 1 | 0 | 0 |", out)
        self.assertNotIn("git-env-set", out)


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
