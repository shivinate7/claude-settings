#!/usr/bin/env python3
"""Fixture tests for guard_log_report.py (reader for ~/.claude/guard.log).

Pinned contract (the spec lives here until the builder lands the module):
- Window: the `days` calendar dates ending on now's date, inclusive. With now=2026-10-11 and
  days=7 the window is 2026-10-05 .. 2026-10-11. A line is in the window by its own date.
- by_rule counts deny/ask/noted only. A rule seen only in other decisions has no by_rule row.
- other keeps raw lines verbatim, trailing newline stripped, in log order, window applied.
- unreadable counts lines with fewer than 4 tab fields or a bad timestamp, window-independent.
  Field 5 is everything after the 4th tab, so extra tabs stay in the matched text.
- main() returns 0 and prints render(...). A missing log prints "unreadable: log not found".

Run with:

    python3 lint/test_guard_log_report.py -v
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime

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


class MainTests(unittest.TestCase):
    def test_missing_log_prints_notice_and_exits_zero(self):
        gone = os.path.join(tempfile.gettempdir(), "no-such-dir-guard-log", "guard.log")
        rc, out = run_main(["--log", gone])
        self.assertEqual(rc, 0)
        self.assertIn("unreadable: log not found", out)

    def test_reads_log_file_with_days_flag(self):
        now = datetime.now().replace(microsecond=0)
        old = now.replace(year=now.year - 1)
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


if __name__ == "__main__":
    unittest.main()
