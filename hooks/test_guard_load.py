#!/usr/bin/env python3
"""Unit cases for hooks/guard_load.py, the one home of the machine-load readings, the verdict and the limits (decision
one-load-definition). Standard library and unittest only.

Run: python3 hooks/test_guard_load.py. The guard's and sim-lease's agreement on the same readings is in
hooks/test_guard.py (family load-brake, the shared rows) and lint/test_sim_lease.py. This file judges the module alone:
the limits, each row's level, the texts the verdict lists, the unread listing, and the reader on this host.
"""
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import load_rows_test as test_load_rows  # noqa: E402  the shared rows and their levels (decision one-load-definition)
import guard_load  # noqa: E402  the module under test


def reading(memory=40.0, free=500.0, total=926.0):
    return {"memory_pct": memory, "disk_free_gb": free, "disk_total_gb": total}


def unread_names(verdict):
    return " ".join(verdict["unread"]).lower()


class Limits(unittest.TestCase):
    def test_the_limits_are_the_ruling_numbers(self):
        self.assertEqual((guard_load.BUSY_MEMORY, guard_load.FULL_MEMORY), (85.0, 95.0))
        self.assertEqual((guard_load.BUSY_DISK_SHARE, guard_load.BUSY_DISK_GB), (10.0, 15.0))
        self.assertEqual((guard_load.FULL_DISK_SHARE, guard_load.FULL_DISK_GB), (5.0, 5.0))
        self.assertEqual(guard_load.GIB, 2 ** 30)


class Verdict(unittest.TestCase):
    def test_each_row_has_the_level_the_ruling_gives_it(self):
        for row in test_load_rows.ROWS:
            with self.subTest(row=row["name"]):
                verdict = guard_load.load_verdict(row["reading"])
                self.assertEqual(verdict["level"], row["level"], "%s is %s, the ruling says %s"
                                 % (row["name"], verdict["level"], row["level"]))

    def test_memory_over_the_busy_line_is_busy_and_is_listed_as_its_text(self):
        verdict = guard_load.load_verdict(reading(memory=85.1))
        self.assertEqual(verdict["level"], "busy")
        self.assertEqual(verdict["busy"], ["memory 85.1% in use"], "the busy list does not name the memory reading")
        self.assertEqual(verdict["full"], [], "a busy memory reading is listed as full")

    def test_memory_at_the_busy_line_is_normal(self):
        verdict = guard_load.load_verdict(reading(memory=85.0))
        self.assertEqual((verdict["level"], verdict["busy"], verdict["full"]), ("normal", [], []),
                         "memory at 85.0% is over the busy line, which is over 85% only")

    def test_memory_over_the_full_line_is_full_and_is_listed_as_its_text(self):
        verdict = guard_load.load_verdict(reading(memory=96.0))
        self.assertEqual(verdict["level"], "full")
        self.assertEqual(verdict["full"], ["memory 96.0% in use"], "the full list does not name the memory reading")

    def test_disk_under_the_full_cap_is_full_and_is_listed_as_its_text(self):
        verdict = guard_load.load_verdict(reading(free=4.0, total=500.0))
        self.assertEqual(verdict["level"], "full")
        self.assertEqual(verdict["full"], ["disk 4.0 GB free of 500 GB"], "the full list does not name the disk reading")


class Unread(unittest.TestCase):
    def test_an_unread_memory_reading_is_listed_and_counts_as_normal(self):
        verdict = guard_load.load_verdict(reading(memory=None))
        self.assertEqual(verdict["level"], "normal", "an unread memory reading is not normal")
        self.assertEqual((verdict["busy"], verdict["full"]), ([], []), "an unread memory reading is listed as a level")
        names = unread_names(verdict)
        self.assertIn("memory", names, "the unread list does not name memory")
        self.assertNotIn("disk", names, "the unread list names the disk, which was read")

    def test_a_disk_reading_with_one_half_unread_is_unread(self):
        verdict = guard_load.load_verdict(reading(free=None, total=926.0))
        self.assertEqual(verdict["level"], "normal")
        self.assertIn("disk", unread_names(verdict), "the unread list does not name the disk")

    def test_one_unread_reading_hides_no_other(self):
        verdict = guard_load.load_verdict(reading(memory=None, free=4.0, total=500.0))
        self.assertEqual(verdict["level"], "full", "an unread memory hides the full disk")
        self.assertEqual(verdict["full"], ["disk 4.0 GB free of 500 GB"])
        self.assertIn("memory", unread_names(verdict))
        verdict = guard_load.load_verdict(reading(memory=96.0, free=None, total=None))
        self.assertEqual(verdict["level"], "full", "an unread disk hides the full memory")
        self.assertEqual(verdict["full"], ["memory 96.0% in use"])
        self.assertIn("disk", unread_names(verdict))

    def test_both_unread_readings_are_listed(self):
        verdict = guard_load.load_verdict(reading(memory=None, free=None, total=None))
        self.assertEqual(verdict["level"], "normal")
        names = unread_names(verdict)
        self.assertIn("memory", names)
        self.assertIn("disk", names)


class Reader(unittest.TestCase):
    def test_read_load_returns_the_three_readings(self):
        read = guard_load.read_load()
        self.assertEqual(set(read), {"memory_pct", "disk_free_gb", "disk_total_gb"},
                         "read_load does not return the three readings the ruling names")
        if read["memory_pct"] is not None:
            self.assertTrue(0.0 <= read["memory_pct"] <= 100.0, "memory_pct is not a percent of memory in use")

    def test_linux_memory_reads_unread_and_is_never_clear(self):
        if not sys.platform.startswith("linux"):
            self.skipTest("Linux reads memory unread; Windows and Mac read it through the OS")
        read = guard_load.read_load()
        self.assertIsNone(read["memory_pct"], "Linux memory reads as a value, not as unread")
        self.assertIsNotNone(read["disk_free_gb"], "Linux disk reads as unread on the home drive")

    def test_a_failed_disk_read_hides_no_memory_reading(self):
        before = guard_load.read_load()
        with mock.patch("shutil.disk_usage", side_effect=OSError("fake disk failure")):
            after = guard_load.read_load()
        self.assertIsNone(after["disk_free_gb"], "a failed disk read is not unread")
        self.assertIsNone(after["disk_total_gb"], "a failed disk read is not unread")
        if before["memory_pct"] is None:
            self.assertIsNone(after["memory_pct"], "a failed disk read reads memory as a value")
        else:
            self.assertAlmostEqual(after["memory_pct"], before["memory_pct"], delta=5.0,
                                   msg="a failed disk read hides the memory reading")

    def test_read_load_starts_no_child_process(self):
        with mock.patch("subprocess.Popen") as popen, mock.patch("subprocess.run") as run, \
                mock.patch("os.system") as system:
            guard_load.read_load()
        self.assertEqual(popen.call_count + run.call_count + system.call_count, 0,
                         "read_load starts a child process")


class Standalone(unittest.TestCase):
    def test_guard_load_imports_no_guard_module_and_no_third_party_module(self):
        if not hasattr(sys, "stdlib_module_names"):
            self.skipTest("sys.stdlib_module_names needs Python 3.10")
        code = (
            "import json, os, sys\n"
            "sys.path.insert(0, %r)\n"
            "import guard_load\n"
            "hooks = sorted(n for n, m in list(sys.modules.items())\n"
            "               if getattr(m, '__file__', None) and os.path.dirname(os.path.abspath(m.__file__)) == %r)\n"
            "third = sorted({n.split('.')[0] for n in sys.modules\n"
            "                if not n.startswith('_') and n.split('.')[0] not in sys.stdlib_module_names\n"
            "                and n.split('.')[0] != 'guard_load'})\n"
            "print(json.dumps({'hooks': hooks, 'third': third}))\n") % (HERE, HERE)
        done = subprocess.run([sys.executable, "-S", "-I", "-c", code], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, "guard_load does not import on its own: %s" % done.stderr[-200:])
        loaded = json.loads(done.stdout)
        self.assertEqual(loaded["hooks"], ["guard_load"], "guard_load imports another module of hooks/")
        self.assertEqual(loaded["third"], [], "guard_load imports a module outside the standard library")


if __name__ == "__main__":
    unittest.main()
