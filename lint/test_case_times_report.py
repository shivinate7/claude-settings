#!/usr/bin/env python3
"""The per-case time reader, lint/case_times_report.py: which cases it flags, and what it prints when a read fails.

The reader reads the job row files in one folder (`--dir`), groups the rows by (suite, group), and flags a case
whose time is at least FLAG_RATIO times its group's median and at least FLAG_FLOOR_S seconds. A group under
MIN_GROUP cases is not judged. The spec gives 5 for MIN_GROUP and names no constant for it, so it is held here as
a literal. FLAG_RATIO and FLAG_FLOOR_S are read from the reader's source with ast, never copied here.

Each case runs the reader in a child process and asserts on its printed output. Each case first shows the reader
flags a decisive outlier (100 times its median, 25 s) before it asserts a negative: an empty output never passes for
"nothing flagged" (decision test-practices, P7), and a missing reader fails on that first behaviour assert, never on
a constant. Times here are fixed JSON values, never measured (rule P5).
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
READER = os.path.join(REPO, "lint", "case_times_report.py")
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

RUN_TIMEOUT = 120  # a hang guard, well above any run here
MIN_GROUP = 5  # the spec: a group under 5 cases is not judged
DECISIVE_MEDIAN = 0.25
DECISIVE_OUTLIER = 25.0  # 100 times the median and over any floor the spec names
NORMAL = ["normal_a", "normal_b", "normal_c", "normal_d"]
RUN = None


def setUpModule():
    global RUN
    RUN = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)


def reader_constant(name):
    """The value of a module-level constant in the reader's source, or None when the reader does not define it."""
    if not os.path.exists(READER):
        return None
    with open(READER, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name \
                and node.value is not None:
            return ast.literal_eval(node.value)
    return None


def thresholds(test):
    ratio = reader_constant("FLAG_RATIO")
    floor = reader_constant("FLAG_FLOOR_S")
    test.assertIsNotNone(ratio, "lint/case_times_report.py defines no FLAG_RATIO constant")
    test.assertIsNotNone(floor, "lint/case_times_report.py defines no FLAG_FLOOR_S constant")
    return ratio, floor


def fresh(test, suffix=""):
    folder = os.path.join(RUN, test.id().replace(".", "_") + suffix)
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    return folder


def row(suite, group, case, seconds, outcome="pass"):
    return {"suite": suite, "group": group, "case": case, "s": seconds, "fixture_s": 0.0, "outcome": outcome}


def write_job(folder, job, rows):
    with open(os.path.join(folder, job + ".jsonl"), "w", encoding="utf-8") as f:
        for item in rows:
            f.write(json.dumps(item) + "\n")


def group_rows(suite, median, names, outlier_name=None, outlier_s=None, group=None):
    """`names` cases at `median`, plus one outlier at `outlier_s` when named. group defaults to the suite."""
    group = suite if group is None else group
    rows = [row(suite, group, "T.%s" % name, median) for name in names]
    if outlier_name is not None:
        rows.append(row(suite, group, "T.%s" % outlier_name, outlier_s))
    return rows


def run_reader(folder, jobs=None):
    """Runs the reader on one folder. `jobs` is the comma-separated job names the run expects, in env CASE_TIMES_JOBS."""
    env = {k: v for k, v in os.environ.items() if k not in ("CASE_TIMES", "PYTHONPATH", "CASE_TIMES_JOBS")}
    if jobs is not None:
        env["CASE_TIMES_JOBS"] = jobs
    return subprocess.run([sys.executable, READER, "--dir", folder], env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=RUN_TIMEOUT)


def decisive_control(test):
    """Writes one group whose outlier is decisively flagged, runs the reader, and asserts the outlier is printed."""
    folder = fresh(test, "_control")
    write_job(folder, "control", group_rows("lint/fixture_control.py", DECISIVE_MEDIAN, NORMAL,
                                            "control_outlier", DECISIVE_OUTLIER))
    result = run_reader(folder)
    test.assertIn("control_outlier", result.stdout,
                  "the reader did not flag a case 100 times its group median (%g s): output %r"
                  % (DECISIVE_OUTLIER, result.stdout[-200:]))
    return folder


class Flags(unittest.TestCase):
    def test_ten_times_median_over_floor_flagged(self):
        decisive_control(self)
        ratio, floor = thresholds(self)
        median = DECISIVE_MEDIAN
        self.assertGreaterEqual(ratio * median, floor, "fixture: the ratio edge must reach the floor")
        folder = fresh(self)
        write_job(folder, "edge", group_rows("lint/fixture_edge.py", median, NORMAL, "boundary_edge", ratio * median))
        write_job(folder, "under", group_rows("lint/fixture_under.py", median, NORMAL, "boundary_under",
                                              0.95 * ratio * median))
        result = run_reader(folder)
        self.assertEqual(result.returncode, 0, "the reader exits %d, want 0: %s"
                         % (result.returncode, result.stderr[-300:]))
        self.assertIn("boundary_edge", result.stdout,
                      "a case at exactly FLAG_RATIO x the median (%g x) was not flagged" % ratio)
        self.assertNotIn("boundary_under", result.stdout,
                         "a case at 0.95 x FLAG_RATIO was flagged, below the ratio")

    def test_under_floor_not_flagged(self):
        decisive_control(self)
        ratio, floor = thresholds(self)
        folder = fresh(self)
        small = floor / (4.0 * ratio)  # the probe is 2 x ratio times this median, yet under the floor
        write_job(folder, "floor", group_rows("lint/fixture_floor.py", small, NORMAL, "floor_probe", floor / 2.0))
        result = run_reader(folder)
        self.assertNotIn("floor_probe", result.stdout,
                         "a case under FLAG_FLOOR_S (%g s) was flagged" % floor)

    def test_small_group_not_judged(self):
        decisive_control(self)
        folder = fresh(self)
        write_job(folder, "five", group_rows("lint/fixture_five.py", DECISIVE_MEDIAN, NORMAL,
                                             "five_control", DECISIVE_OUTLIER))
        write_job(folder, "four", group_rows("lint/fixture_four.py", DECISIVE_MEDIAN, NORMAL[:3],
                                             "four_probe", DECISIVE_OUTLIER))
        result = run_reader(folder)
        self.assertIn("five_control", result.stdout, "a group of %d cases was not judged" % MIN_GROUP)
        self.assertNotIn("four_probe", result.stdout, "a group of %d cases was judged" % (MIN_GROUP - 1))

    def test_guard_grouped_by_family(self):
        decisive_control(self)
        folder = fresh(self)
        guard = "hooks/test_guard.py"
        rows = group_rows(guard, DECISIVE_MEDIAN, NORMAL, "guard_probe_merge", DECISIVE_OUTLIER, group="merge")
        rows += [row(guard, "pure", "T.guard_pure_%d" % i, 5.0) for i in range(5)]
        write_job(folder, "guard", rows)
        result = run_reader(folder)
        self.assertIn("guard_probe_merge", result.stdout,
                      "the outlier in family merge was not flagged: the guard rows were not grouped by family")
        for i in range(5):
            self.assertNotIn("guard_pure_%d" % i, result.stdout,
                             "a case of the slow family pure was flagged: the guard rows were grouped by suite")

    def test_shard_files_merge_by_suite(self):
        decisive_control(self)
        folder = fresh(self)
        suite = "lint/fixture_shard.py"
        write_job(folder, "checks-a", [row(suite, suite, "T.shard_normal_%d" % i, DECISIVE_MEDIAN)
                                       for i in range(3)])
        write_job(folder, "checks-b", [row(suite, suite, "T.shard_normal_3", DECISIVE_MEDIAN),
                                       row(suite, suite, "T.shard_probe", DECISIVE_OUTLIER)])
        result = run_reader(folder)
        self.assertIn("shard_probe", result.stdout,
                      "the outlier was not flagged: the two shard files were not merged by suite into %d cases"
                      % MIN_GROUP)

    def test_bad_file_unknown_exit_zero(self):
        decisive_control(self)
        bad = fresh(self, "_bad")
        with open(os.path.join(bad, "broken.jsonl"), "w", encoding="utf-8") as f:
            f.write("{not json\n")
        broken = run_reader(bad)
        self.assertEqual(broken.returncode, 0, "a bad row file made the reader exit %d, want 0" % broken.returncode)
        self.assertIn("unknown", broken.stdout.lower(),
                      "a bad row file did not print unknown: %r" % broken.stdout[-200:])
        empty = fresh(self, "_empty")
        none = run_reader(empty)
        self.assertEqual(none.returncode, 0, "an empty folder made the reader exit %d, want 0" % none.returncode)
        self.assertIn("unknown", none.stdout.lower(), "an empty folder did not print unknown: %r" % none.stdout[-200:])


class JobFiles(unittest.TestCase):
    """The report names the job files it read, one line each: `read: <path>`. A job the run expects (env
    CASE_TIMES_JOBS, comma-separated) with no `<job>.jsonl` under the folder is listed as `missing: <job>`."""

    def test_prints_each_job_file_read(self):
        decisive_control(self)
        folder = fresh(self)
        write_job(folder, "checks-a", [row("lint/fixture_read_a.py", "lint/fixture_read_a.py", "T.read_a", 0.5)])
        write_job(folder, "checks-b", [row("lint/fixture_read_b.py", "lint/fixture_read_b.py", "T.read_b", 0.5)])
        result = run_reader(folder)
        lines = result.stdout.splitlines()
        for job in ("checks-a", "checks-b"):
            path = os.path.join(folder, job + ".jsonl")
            self.assertIn("read: " + path, lines,
                          "the report did not print the job file it read as 'read: <path>' on its own line: %r"
                          % result.stdout[-300:])

    def test_named_job_without_a_file_is_listed_missing(self):
        decisive_control(self)
        folder = fresh(self)
        write_job(folder, "checks-a", [row("lint/fixture_named_a.py", "lint/fixture_named_a.py", "T.named_a", 0.5)])
        result = run_reader(folder, jobs="checks-a,nightly")
        self.assertEqual(result.returncode, 0, "the reader exits %d, want 0: %s"
                         % (result.returncode, result.stderr[-300:]))
        lines = result.stdout.splitlines()
        self.assertIn("missing: nightly", lines,
                      "a named job with no file was not listed as 'missing: <job>': %r" % result.stdout[-300:])
        self.assertNotIn("missing: checks-a", lines, "a named job with a file was listed as missing")


class Literal(unittest.TestCase):
    """The flag thresholds by literal value: 10 times the group median, and 1.0 s. No constant is read here."""

    def test_floor_near_one_second_not_flagged(self):
        decisive_control(self)
        folder = fresh(self)
        # median 0.09 s, probe 0.99 s: 11 times the median, which the ratio alone flags; only the 1.0 s floor keeps it out
        write_job(folder, "floor_edge", group_rows("lint/fixture_floor_edge.py", 0.09, NORMAL, "floor_edge_probe", 0.99))
        result = run_reader(folder)
        self.assertNotIn("floor_edge_probe", result.stdout,
                         "a case at 0.99 s (11 times its group median) was flagged: the 1.0 s floor did not hold")

    def test_nine_point_nine_times_not_flagged(self):
        decisive_control(self)
        folder = fresh(self)
        # median 0.5 s, probe 4.95 s: 9.9 times the median, over the 1.0 s floor, so only the ratio can keep it out
        write_job(folder, "nine", group_rows("lint/fixture_nine.py", 0.5, NORMAL, "nine_point_nine_probe", 4.95))
        result = run_reader(folder)
        self.assertNotIn("nine_point_nine_probe", result.stdout,
                         "a case at 9.9 times its group median (4.95 s over 0.5 s) was flagged")

    def test_ten_times_and_one_second_flagged(self):
        decisive_control(self)
        folder = fresh(self)
        # median 0.1 s, probe 1.0 s: exactly 10 times the median and exactly the 1.0 s floor
        write_job(folder, "edge", group_rows("lint/fixture_edge_literal.py", 0.1, NORMAL, "ten_x_one_second_probe", 1.0))
        result = run_reader(folder)
        self.assertIn("ten_x_one_second_probe", result.stdout,
                      "a case at 10 times its group median (1.0 s over 0.1 s) and at the 1.0 s floor was not flagged")

    def test_ten_times_under_one_second_not_flagged(self):
        decisive_control(self)
        folder = fresh(self)
        # median 0.05 s, probe 0.5 s: 10 times the median, under the 1.0 s floor
        write_job(folder, "floor", group_rows("lint/fixture_floor_literal.py", 0.05, NORMAL, "ten_x_under_floor_probe", 0.5))
        result = run_reader(folder)
        self.assertNotIn("ten_x_under_floor_probe", result.stdout,
                         "a case at 10 times its group median (0.5 s over 0.05 s) but under 1.0 s was flagged")

    def test_skipped_rows_left_out_of_the_median(self):
        decisive_control(self)
        folder = fresh(self)
        suite = "lint/fixture_skip_median.py"
        # four passes at 0.5 s and a probe at 4.9 s (9.8 times the median): not flagged. Six skips at 0 s would
        # drop the median to 0 s if they counted, and then the probe would be flagged.
        rows = [row(suite, suite, "T.skip_normal_%d" % i, 0.5) for i in range(4)]
        rows.append(row(suite, suite, "T.skip_probe", 4.9))
        rows += [row(suite, suite, "T.skipped_%d" % i, 0.0, outcome="skip") for i in range(6)]
        write_job(folder, "skips", rows)
        result = run_reader(folder)
        self.assertNotIn("skip_probe", result.stdout,
                         "a case at 9.8 times its group median was flagged: the skipped rows moved the median")


if __name__ == "__main__":
    unittest.main()
