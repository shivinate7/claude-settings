#!/usr/bin/env python3
"""Tests for bin/sim-lease, the Mac-wide lease that bin/sim-test takes before its own boot.

Run: python3 lint/test_sim_lease.py. SIM_LEASE=PATH picks the tool; the default is bin/sim-lease in this repo.
No case reads this machine's memory, disk, load or OS. Each case runs a copy of the tool in its own tree, beside a
copy of hooks/_nowindow.py and lint/test_support/guard_load_fake.py as hooks/guard_load.py. The fake returns the
reading the case set (set_reading) and keeps the real verdict (decision one-load-definition). The uname shim says
Darwin. The sysctl shim is a tripwire: sim-lease reads no vm.loadavg, so a case fails when sysctl runs. The ps shim
passes through to the real ps except for a start time that a case sets. CI and GITHUB_ACTIONS are unset for each run.
A holder is a live `sleep` child or a child already reaped, so no case depends on a pid being free.
Temp files follow decisions/test-temp-standard.md: one run folder from lint/_test_temp.py per run, removed at the end.
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

HERE = os.path.dirname(os.path.abspath(__file__))
SIM_LEASE = os.environ.get("SIM_LEASE") or os.path.join(HERE, "..", "bin", "sim-lease")
FAKE_GUARD_LOAD = os.path.join(HERE, "test_support", "guard_load_fake.py")
ROWS_PATH = os.path.join(HERE, "..", "hooks", "test_support", "load_rows.py")
REAL_PS = shutil.which("ps") or "/bin/ps"
RUN_FOLDER = None
SLOT_UDID = None  # read from the tool under test in setUpModule: the one home of the device IDs
ROWS_MODULE = None  # hooks/test_support/load_rows.py: the shared readings and their levels
NORMAL = {"memory_pct": 40.0, "disk_free_gb": 500.0, "disk_total_gb": 926.0}

UNAME_SH = '#!/bin/sh\necho "${SIM_LEASE_TEST_UNAME:-Darwin}"\n'
# The tripwire: sim-lease reads the load through guard_load, never through sysctl. Each run is logged twice, once to
# the load-read log that every reading shares and once to the sysctl log that only a sysctl run writes.
SYSCTL_SH = ('#!/bin/sh\necho sysctl >> "$SIM_LEASE_TEST_SYSCTLLOG"\necho read >> "$SIM_LEASE_TEST_LOADLOG"\n'
             'cat "$SIM_LEASE_TEST_LOADAVG"\n')
# A start time that a case wrote for pid P wins for `ps -o lstart= -p P`. Every other ps call is the real one.
PS_SH = """#!/bin/sh
pid= prev= lstart=
for a in "$@"; do
  [ "$prev" = -p ] && pid=$a
  [ "$a" = lstart= ] && lstart=1
  prev=$a
done
if [ -n "$lstart" ] && [ -n "$pid" ] && [ -f "$SIM_LEASE_TEST_PS/$pid" ]; then
  cat "$SIM_LEASE_TEST_PS/$pid"
  exit 0
fi
exec "$SIM_LEASE_TEST_REAL_PS" "$@"
"""


def load_module(path, name):
    """The module at PATH, run from that file. It is read from the file, never copied into this one."""
    loader = importlib.machinery.SourceFileLoader(name, path)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


def setUpModule():
    global RUN_FOLDER, SLOT_UDID, ROWS_MODULE
    RUN_FOLDER = _test_temp.run_folder()
    SLOT_UDID = load_module(SIM_LEASE, "sim_lease_under_test").SLOT_UDID
    ROWS_MODULE = load_module(ROWS_PATH, "load_rows")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


def mentions(text, pid):
    """True when `text` holds `pid` as a whole number, so pid 12 does not match 123."""
    return re.search(r"(?<!\d)%d(?!\d)" % pid, text) is not None


def grant(r):
    """(exit code, stdout) of a take. A granted take prints its slot: 1, 2 or pro."""
    return (r.returncode, r.stdout.strip())


def files_under(folder):
    return [os.path.join(d, f) for d, _, names in os.walk(folder) for f in names]


def stop(p):
    if p.poll() is None:
        p.kill()
    p.wait()


def count_lines(path):
    try:
        with open(path) as f:
            return len(f.read().splitlines())
    except FileNotFoundError:
        return 0


class LeaseCase(unittest.TestCase):
    """One case: its own config dir, home, tree, shims and reading, and holders stopped after it."""

    def setUp(self):
        self.base = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.base, True)
        self.cfg = os.path.join(self.base, "cfg")
        self.home = os.path.join(self.base, "home")
        self.shims = os.path.join(self.base, "shims")
        self.ps_dir = os.path.join(self.base, "ps")
        self.tree = os.path.join(self.base, "tree")
        self.reading_file = os.path.join(self.base, "reading.json")
        self.load_log = os.path.join(self.base, "load_reads")
        self.sysctl_log = os.path.join(self.base, "sysctl_calls")
        self.loadavg_file = os.path.join(self.base, "loadavg")
        for d in (self.cfg, self.home, self.shims, self.ps_dir, os.path.join(self.tree, "bin"),
                  os.path.join(self.tree, "hooks")):
            os.makedirs(d)
        self.tool, self.real_guard_load = self.copy_tree()
        for name, text in (("uname", UNAME_SH), ("sysctl", SYSCTL_SH), ("ps", PS_SH)):
            path = os.path.join(self.shims, name)
            with open(path, "w") as f:
                f.write(text)
            os.chmod(path, 0o755)
        self.set_loadavg("0.50", "0.50", "0.50")
        self.set_reading()

    def copy_tree(self):
        """A copy of the tool under test, beside hooks/_nowindow.py and the fake guard_load. sim-lease resolves hooks/
        from its own realpath, so the copy finds the fake and never the repo's guard_load. Returns the copy's path and
        the path of the real guard_load the fake delegates to."""
        tool_hooks = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(SIM_LEASE))), "hooks")
        tool = os.path.join(self.tree, "bin", "sim-lease")
        shutil.copy(SIM_LEASE, tool)
        shutil.copy(os.path.join(tool_hooks, "_nowindow.py"), os.path.join(self.tree, "hooks", "_nowindow.py"))
        shutil.copy(FAKE_GUARD_LOAD, os.path.join(self.tree, "hooks", "guard_load.py"))
        return tool, os.path.join(tool_hooks, "guard_load.py")

    def set_reading(self, **changes):
        """The reading the fake guard_load returns: NORMAL with the keys given. None is an unread reading."""
        with open(self.reading_file, "w") as f:
            json.dump(dict(NORMAL, **changes), f)

    def set_loadavg(self, one, five, fifteen):
        """The line the sysctl shim prints. sim-lease must never read it, so no grant may depend on it."""
        with open(self.loadavg_file, "w") as f:
            f.write("{ %s %s %s }\n" % (one, five, fifteen))

    def load_reads(self):
        return count_lines(self.load_log)

    def sysctl_calls(self):
        return count_lines(self.sysctl_log)

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items() if k not in (
            "CI", "GITHUB_ACTIONS", "CLAUDE_CONFIG_DIR", "SIM_LEASE_WAIT", "SIM_LEASE_POLL", "SIM_LEASE_TEST_UNAME")}
        env.update(HOME=self.home, CLAUDE_CONFIG_DIR=self.cfg,
                   PATH=self.shims + os.pathsep + os.environ.get("PATH", ""), SIM_LEASE_POLL="1",
                   SIM_LEASE_TEST_LOADAVG=self.loadavg_file, SIM_LEASE_TEST_LOADLOG=self.load_log,
                   SIM_LEASE_TEST_SYSCTLLOG=self.sysctl_log,
                   SIM_LEASE_TEST_PS=self.ps_dir, SIM_LEASE_TEST_REAL_PS=REAL_PS,
                   FAKE_LOAD_REAL=self.real_guard_load, FAKE_LOAD_READING=self.reading_file,
                   FAKE_LOAD_LOG=self.load_log)
        env.update(extra)
        return env

    def run_tool(self, *args, env=None):
        return subprocess.run([sys.executable, self.tool, *args], env=self.env(**(env or {})),
                              capture_output=True, text=True, timeout=60)

    def take(self, device, pid, wait=1, env=None, udid=False):
        extra = ["--udid"] if udid else []
        return self.run_tool("take", "--device", device, "--pid", str(pid), "--wait", str(wait), *extra, env=env)

    def give(self, pid):
        return self.run_tool("give", "--pid", str(pid))

    def status(self):
        return self.run_tool("status")

    def spawn(self):
        """A live holder: a child process that stays alive until the case ends."""
        p = subprocess.Popen(["sleep", "600"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        self.addCleanup(stop, p)
        return p

    def queue_waiter(self, device, pid):
        """Starts a take that waits in the background. Returns once status lists its pid: a condition, not a delay."""
        p = subprocess.Popen([sys.executable, self.tool, "take", "--device", device, "--pid", str(pid), "--wait", "30"],
                             env=self.env(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        self.addCleanup(stop, p)
        for _ in range(100):
            if mentions(self.status().stdout, pid):
                return p
            time.sleep(0.05)
        self.fail("the waiting %s take is not on the queue in status" % device)


class Slots(LeaseCase):
    def test_first_duo_gets_slot_1_then_second_gets_slot_2(self):
        first, second = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.assertEqual(grant(self.take("duo", second.pid)), (0, "2"), "the second duo take is not granted slot 2")

    def test_slot_2_is_refused_at_busy_memory(self):
        first, second = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.set_reading(memory_pct=90.0)
        r = self.take("duo", second.pid)
        self.assertEqual(r.returncode, 1, "slot 2 is granted at busy memory (90.0%)")
        self.assertEqual(r.stdout.strip(), "", "a refused duo take prints a slot")

    def test_slot_2_is_granted_just_under_the_busy_line(self):
        first, second = self.spawn(), self.spawn()
        self.set_reading(memory_pct=84.9)
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.assertEqual(grant(self.take("duo", second.pid)), (0, "2"),
                         "slot 2 is refused at memory 84.9%, under the busy line")

    def test_a_third_duo_is_not_granted_while_slots_1_and_2_are_held(self):
        first, second, third = self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.assertEqual(grant(self.take("duo", second.pid)), (0, "2"), "the second duo take is not granted slot 2")
        before = self.load_reads()
        r = self.take("duo", third.pid, wait=2)
        self.assertEqual(r.returncode, 1, "a third duo take is granted while slots 1 and 2 are held")
        self.assertEqual(r.stdout.strip(), "", "a refused third duo take prints a slot")
        self.assertGreaterEqual(self.load_reads() - before, 2, "the third duo take does not wait before it is refused")

    def assert_waits_then_refused(self, device, needle):
        before = self.load_reads()
        r = self.take(device, os.getpid(), wait=2)
        self.assertEqual(r.returncode, 1, "a %s take at this reading is not refused with exit 1" % device)
        self.assertGreaterEqual(self.load_reads() - before, 2,
                                "a %s take does not wait: it reads the load once" % device)
        lines = [line for line in r.stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, "the refusal of a %s take is not one stderr line" % device)
        self.assertIn(needle, lines[0], "the refusal of a %s take does not name the reading" % device)

    def test_a_take_waits_then_exits_1_at_full_memory(self):
        self.set_reading(memory_pct=96.0)
        for device in ("duo", "pro"):
            with self.subTest(device=device):
                self.assert_waits_then_refused(device, "96.0")

    def test_a_take_waits_then_exits_1_at_full_disk(self):
        self.set_reading(disk_free_gb=4.0)
        for device in ("duo", "pro"):
            with self.subTest(device=device):
                self.assert_waits_then_refused(device, "4.0")

    def test_a_refusal_names_the_holder(self):
        first, second = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.set_reading(memory_pct=96.0)
        r = self.take("duo", second.pid)
        self.assertEqual(r.returncode, 1, "a duo take at full memory (96.0%) is not refused")
        self.assertTrue(mentions(r.stderr, first.pid), "the refusal does not name the holder's pid")

    def test_sim_lease_wait_sets_the_wait_when_wait_is_not_passed(self):
        self.set_reading(memory_pct=96.0)
        before = self.load_reads()
        r = self.run_tool("take", "--device", "duo", "--pid", str(os.getpid()), env={"SIM_LEASE_WAIT": "2"})
        self.assertEqual(r.returncode, 1, "a take without --wait is not refused with exit 1")
        self.assertGreaterEqual(self.load_reads() - before, 2,
                                "SIM_LEASE_WAIT does not set the wait: the take does not poll")


class Readings(LeaseCase):
    """A reading decides a grant by its own level: busy refuses slot 2 only, full refuses every take, and an unread
    reading holds every take, since sim-lease does not count it as normal."""

    def test_a_busy_reading_grants_slot_1_and_refuses_slot_2(self):
        first, second = self.spawn(), self.spawn()
        self.set_reading(memory_pct=90.0)
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "a busy reading refuses slot 1")
        self.assertEqual(self.take("duo", second.pid).returncode, 1, "slot 2 is granted at busy memory (90.0%)")

    def test_a_busy_reading_grants_the_pro_pool(self):
        pid = self.spawn().pid
        self.set_reading(memory_pct=90.0)
        self.assertEqual(grant(self.take("pro", pid)), (0, "pro"),
                         "a busy reading refuses the pro pool: busy must not block a grant")

    def test_an_unread_memory_reading_holds_every_take(self):
        self.set_reading(memory_pct=None)
        for device in ("duo", "pro"):
            with self.subTest(device=device):
                r = self.take(device, os.getpid(), wait=0)
                self.assertEqual(r.returncode, 1, "a %s take with memory unread is granted" % device)
                self.assertEqual(r.stdout.strip(), "", "a %s take with memory unread prints a slot" % device)
                self.assertIn("unknown", r.stderr.lower(), "the refusal does not print memory as unknown")

    def test_an_unread_disk_reading_holds_every_take(self):
        self.set_reading(disk_free_gb=None, disk_total_gb=None)
        for device in ("duo", "pro"):
            with self.subTest(device=device):
                r = self.take(device, os.getpid(), wait=0)
                self.assertEqual(r.returncode, 1, "a %s take with the disk unread is granted" % device)
                self.assertEqual(r.stdout.strip(), "", "a %s take with the disk unread prints a slot" % device)
                self.assertIn("unknown", r.stderr.lower(), "the refusal does not print the disk as unknown")

    def test_status_prints_an_unread_reading_as_unknown(self):
        self.set_reading(memory_pct=None)
        r = self.status()
        self.assertEqual(r.returncode, 0, "status exits non-zero with memory unread")
        self.assertIn("unknown", r.stdout.lower(), "status does not print the unread memory as unknown")

    def test_a_high_load_average_does_not_hold_a_grant(self):
        self.set_loadavg("99.00", "99.00", "99.00")
        pid = self.spawn().pid
        self.assertEqual(grant(self.take("duo", pid, wait=0)), (0, "1"),
                         "a load average of 99 holds slot 1 with free memory and disk")

    def test_take_and_status_start_no_sysctl(self):
        pid = self.spawn().pid
        self.assertEqual(grant(self.take("duo", pid)), (0, "1"), "the duo take is not granted slot 1")
        self.assertEqual(self.status().returncode, 0, "status exits non-zero")
        self.assertEqual(self.sysctl_calls(), 0,
                         "sim-lease starts sysctl: the load is read through guard_load, not vm.loadavg")


class SharedRows(LeaseCase):
    """Each row of hooks/test_support/load_rows.py, as sim-lease grants it: slot 1, then slot 2 with slot 1 held, then pro
    alone. The expected grant is written from the row's level and unread readings (decision one-load-definition)."""

    def test_each_row_grants_as_its_level_and_its_unread_readings_say(self):
        for row in ROWS_MODULE.ROWS:
            with self.subTest(row=row["name"]):
                self.check_row(row)

    def check_row(self, row):
        self.set_reading(**row["reading"])
        unread = ROWS_MODULE.unread(row)
        slot_1 = row["level"] != "full" and not unread
        slot_2 = row["level"] == "normal" and not unread
        self.cfg = tempfile.mkdtemp(dir=self.base)
        first, second = self.spawn(), self.spawn()
        self.expect_take("duo", first.pid, slot_1, "1", row)
        self.expect_take("duo", second.pid, slot_2, "2", row)
        self.cfg = tempfile.mkdtemp(dir=self.base)
        self.expect_take("pro", self.spawn().pid, slot_1, "pro", row)

    def expect_take(self, device, pid, granted, slot, row):
        r = self.take(device, pid, wait=0)
        if granted:
            self.assertEqual(grant(r), (0, slot), "%s: the %s take is not granted %s" % (row["name"], device, slot))
        else:
            self.assertEqual(r.returncode, 1, "%s: the %s take is granted, and the row says refused"
                             % (row["name"], device))


class Give(LeaseCase):
    def test_give_frees_the_lease_and_is_idempotent(self):
        holder, never, later = self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.assertEqual(self.give(holder.pid).returncode, 0, "give of the holder's pid exits non-zero")
        self.assertEqual(self.give(holder.pid).returncode, 0, "a second give of the same pid exits non-zero")
        self.assertEqual(self.give(never.pid).returncode, 0, "give of a pid that holds nothing exits non-zero")
        self.assertEqual(grant(self.take("duo", later.pid)), (0, "1"), "give did not free slot 1")


class PoolExclusive(LeaseCase):
    def test_pro_is_granted_when_nothing_is_held(self):
        pid = self.spawn().pid
        self.assertEqual(grant(self.take("pro", pid)), (0, "pro"), "a pro take with nothing held is not granted pro")

    def test_duo_is_refused_while_pro_is_held(self):
        first, second = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("pro", first.pid)), (0, "pro"), "the pro take is not granted pro")
        self.assertEqual(self.take("duo", second.pid).returncode, 1, "a duo take is granted while pro is held")

    def test_pro_is_refused_while_a_duo_is_held(self):
        first, second = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "the duo take is not granted slot 1")
        self.assertEqual(self.take("pro", second.pid).returncode, 1, "a pro take is granted while a duo is held")


class Queue(LeaseCase):
    def test_second_waiter_is_not_granted_ahead_of_the_head(self):
        holder, head, later = self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.queue_waiter("pro", head.pid)
        r = self.take("duo", later.pid)
        self.assertEqual(r.returncode, 1, "a duo take is granted slot 2 ahead of the queued pro head")

    def test_second_duo_is_granted_slot_2_when_no_waiter_is_queued(self):
        holder, later = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.assertEqual(grant(self.take("duo", later.pid)), (0, "2"), "the second duo take is not granted slot 2")

    def test_a_dead_holder_is_reaped_on_the_next_take(self):
        holder = self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the first duo take is not granted slot 1")
        holder.kill()
        holder.wait()
        later = self.spawn()
        self.assertEqual(grant(self.take("duo", later.pid)), (0, "1"),
                         "the dead holder still holds slot 1 on the next take")

    def test_a_live_holder_keeps_slot_1(self):
        holder, later = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.assertEqual(grant(self.take("duo", later.pid)), (0, "2"), "a live holder lost slot 1")

    def test_status_reaps_a_dead_holder(self):
        holder = self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the first duo take is not granted slot 1")
        holder.kill()
        holder.wait()
        r = self.status()
        self.assertEqual(r.returncode, 0, "status exits non-zero")
        self.assertFalse(mentions(r.stdout, holder.pid), "status still lists the dead holder")

    def test_a_reused_pid_is_reaped_on_the_next_take(self):
        holder = self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the first duo take is not granted slot 1")
        # The pid now names another process: its start time differs from the one recorded for the holder.
        with open(os.path.join(self.ps_dir, str(holder.pid)), "w") as f:
            f.write("Thu Jan  1 00:00:00 1970\n")
        later = self.spawn()
        self.assertEqual(grant(self.take("duo", later.pid)), (0, "1"),
                         "a reused pid still holds slot 1: its start time differs from the recorded one")

    def test_a_pid_with_its_recorded_start_time_keeps_slot_1(self):
        holder, later = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.assertEqual(grant(self.take("duo", later.pid)), (0, "2"),
                         "a holder whose start time is unchanged lost slot 1")

    def test_a_timed_out_take_leaves_the_queue(self):
        holder, head, later = self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the first duo take is not granted slot 1")
        r = self.take("pro", head.pid, wait=1)
        self.assertEqual(r.returncode, 1, "a pro take with a duo held is not refused")
        self.assertFalse(mentions(self.status().stdout, head.pid), "the timed-out pro take is still on the queue")
        self.assertEqual(grant(self.take("duo", later.pid)), (0, "2"),
                         "a timed-out waiter still blocks the next duo take")

    def test_a_holder_recorded_under_one_tz_is_not_reaped_under_another(self):
        holder, later = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid, env={"TZ": "UTC0"})), (0, "1"),
                         "the first duo take under TZ=UTC0 is not granted slot 1")
        self.assertEqual(grant(self.take("duo", later.pid, env={"TZ": "IST-5:30"})), (0, "2"),
                         "a holder recorded under TZ=UTC0 is reaped under TZ=IST-5:30")


class UdidTake(LeaseCase):
    """take --udid prints the granted slot's device UDID (SLOT_UDID in the tool) where take prints the slot."""

    def test_duo_slots_print_their_own_udids(self):
        first, second = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", first.pid, udid=True)), (0, SLOT_UDID["1"]),
                         "take --udid is not granted slot 1's UDID")
        self.assertEqual(grant(self.take("duo", second.pid, udid=True)), (0, SLOT_UDID["2"]),
                         "take --udid is not granted slot 2's UDID while slot 1 is held")

    def test_pro_prints_the_pro_udid(self):
        pid = self.spawn().pid
        self.assertEqual(grant(self.take("pro", pid, udid=True)), (0, SLOT_UDID["pro"]),
                         "take --udid for pro is not granted the pro UDID")

    def test_without_udid_the_take_still_prints_the_slot(self):
        pid = self.spawn().pid
        self.assertEqual(grant(self.take("duo", pid)), (0, "1"), "take without --udid no longer prints the slot")

    def test_each_slot_names_its_own_device(self):
        udids = [SLOT_UDID[slot] for slot in ("1", "2", "pro")]
        self.assertEqual(len(set(udids)), 3, "two slots name the same device UDID")

    def test_a_refused_take_udid_prints_nothing(self):
        self.set_reading(memory_pct=96.0)
        r = self.take("duo", os.getpid(), udid=True)
        self.assertEqual(r.returncode, 1, "a take --udid at full memory (96.0%) is not refused with exit 1")
        self.assertEqual(r.stdout.strip(), "", "a refused take --udid prints a UDID")


class Usage(LeaseCase):
    def test_a_usage_error_exits_2(self):
        for label, args in (("a take with no device", ["take"]), ("a take with an unknown device",
                                                                  ["take", "--device", "nope"])):
            with self.subTest(label):
                self.assertEqual(self.run_tool(*args).returncode, 2, "%s does not exit 2" % label)

    def assert_usage_error(self, args, label):
        r = self.run_tool(*args)
        self.assertEqual(r.returncode, 2, "%s does not exit 2" % label)
        lines = [line for line in r.stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, "%s does not print one usage line" % label)

    def test_take_with_no_pid_is_a_usage_error(self):
        self.assert_usage_error(["take", "--device", "duo"], "a take with no --pid")

    def test_give_with_no_pid_is_a_usage_error(self):
        self.assert_usage_error(["give"], "a give with no --pid")


class Status(LeaseCase):
    def test_status_lists_each_lease_and_waiter_on_its_own_line_with_the_readings(self):
        self.set_reading(memory_pct=42.5, disk_free_gb=123.4, disk_total_gb=926.0)
        holder, head = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.queue_waiter("pro", head.pid)
        r = self.status()
        self.assertEqual(r.returncode, 0, "status exits non-zero")
        lines = r.stdout.splitlines()
        self.assertEqual(sum(mentions(line, holder.pid) for line in lines), 1,
                         "the lease is not on exactly one status line")
        self.assertEqual(sum(mentions(line, head.pid) for line in lines), 1,
                         "the waiter is not on exactly one status line")
        self.assertIn("42.5", r.stdout, "status does not show the memory reading")
        self.assertIn("123.4", r.stdout, "status does not show the disk's free GB")


class NoOp(LeaseCase):
    def assert_no_op(self, label, env=None):
        pid = self.spawn().pid
        r = self.take("duo", pid, env=env)
        self.assertEqual(grant(r), (0, "none"), "%s: take is not a no-op that prints none" % label)
        self.assertEqual(self.give(pid).returncode, 0, "%s: give exits non-zero" % label)
        self.assertEqual(files_under(self.cfg), [], "%s: a file was written" % label)

    def test_a_host_that_is_not_darwin_takes_none_and_writes_no_file(self):
        self.assert_no_op("uname Linux", env={"SIM_LEASE_TEST_UNAME": "Linux"})

    def test_ci_or_github_actions_makes_it_a_no_op(self):
        for name in ("CI", "GITHUB_ACTIONS"):
            with self.subTest(variable=name):
                self.assert_no_op("%s=true" % name, env={name: "true"})

    def test_take_udid_on_a_no_op_prints_none_and_writes_no_file(self):
        for label, env in (("uname Linux", {"SIM_LEASE_TEST_UNAME": "Linux"}), ("CI=true", {"CI": "true"}),
                           ("GITHUB_ACTIONS=true", {"GITHUB_ACTIONS": "true"})):
            with self.subTest(label):
                pid = self.spawn().pid
                r = self.take("duo", pid, env=env, udid=True)
                self.assertEqual(grant(r), (0, "none"), "%s: take --udid is not a no-op that prints none" % label)
                self.assertEqual(files_under(self.cfg), [], "%s: take --udid wrote a file" % label)

    def test_an_empty_ci_is_not_a_no_op(self):
        pid = self.spawn().pid
        self.assertEqual(grant(self.take("duo", pid, env={"CI": ""})), (0, "1"),
                         "an empty CI turns the lease off: take is not granted slot 1")

    def assert_takes_a_lease_on_darwin(self, name, value):
        pid = self.spawn().pid
        self.assertEqual(grant(self.take("duo", pid, env={name: value})), (0, "1"),
                         "%s=%s turns the lease off on Darwin: take is not granted slot 1" % (name, value))
        self.assertTrue(os.path.isfile(os.path.join(self.cfg, "state", "sim-lease", "leases.json")),
                        "%s=%s on Darwin writes no lease file" % (name, value))

    def test_ci_false_on_darwin_takes_a_lease(self):
        self.assert_takes_a_lease_on_darwin("CI", "false")

    def test_github_actions_false_on_darwin_takes_a_lease(self):
        self.assert_takes_a_lease_on_darwin("GITHUB_ACTIONS", "false")

    def test_a_no_op_on_darwin_prints_one_stderr_line_saying_no_lease_was_taken(self):
        pid = self.spawn().pid
        r = self.take("duo", pid, env={"CI": "true"})
        self.assertEqual(grant(r), (0, "none"), "CI=true on Darwin is not a no-op that prints none")
        lines = [line for line in r.stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, "a no-op take on Darwin does not print one stderr line")
        self.assertTrue("no lease" in lines[0].lower() and "taken" in lines[0].lower(),
                        "the no-op stderr line does not say no lease was taken")


class Concurrency(LeaseCase):
    def test_two_concurrent_takes_never_both_get_slot_1(self):
        for n in range(5):
            a, b = self.spawn(), self.spawn()
            procs = [subprocess.Popen([sys.executable, self.tool, "take", "--device", "duo", "--pid", str(p.pid),
                                       "--wait", "3"], env=self.env(), stdin=subprocess.DEVNULL,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for p in (a, b)]
            outs = []
            for proc in procs:
                out, _ = proc.communicate(timeout=60)
                outs.append((proc.returncode, out.strip()))
            self.assertEqual(sorted(outs), [(0, "1"), (0, "2")],
                             "two concurrent duo takes are not granted slots 1 and 2 (round %d)" % n)
            self.give(a.pid)
            self.give(b.pid)


if __name__ == "__main__":
    unittest.main()
