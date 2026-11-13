#!/usr/bin/env python3
"""Tests for bin/sim-lease, the Mac-wide lease that bin/sim-test takes before its own boot.

Run: python3 lint/test_sim_lease.py. SIM_LEASE=PATH picks the tool; the default is bin/sim-lease in this repo.
No case reads this machine's load, memory or disk. PATH shims for uname and sysctl read files in the case's own folder,
and the ps shim passes through to the real ps except for a start time that a case sets. The brake's disk is the fake one
in tests/sim_lease/sitecustomize.py, which is put on PYTHONPATH. Memory is unread unless a case sets it. CI and
GITHUB_ACTIONS are unset for each run. A holder is a live `sleep` child or a child already reaped, so no case depends on
a pid being free.
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
SHIM = os.path.join(HERE, "..", "tests", "sim_lease")  # the disk seam: sitecustomize.py, put on PYTHONPATH
REAL_PS = shutil.which("ps") or "/bin/ps"
RUN_FOLDER = None
SLOT_UDID = None  # read from the tool under test in setUpModule: the one home of the device IDs

UNAME_SH = '#!/bin/sh\necho "${SIM_LEASE_TEST_UNAME:-Darwin}"\n'
SYSCTL_SH = '#!/bin/sh\necho read >> "$SIM_LEASE_TEST_LOADLOG"\ncat "$SIM_LEASE_TEST_LOAD"\n'
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


def load_slot_udid(path):
    """SLOT_UDID as the tool at PATH defines it. It is read from that file, never copied into this one."""
    loader = importlib.machinery.SourceFileLoader("sim_lease_under_test", path)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module.SLOT_UDID


def setUpModule():
    global RUN_FOLDER, SLOT_UDID
    try:
        import fcntl  # noqa: F401  sim-lease locks with it; Windows' Python has none
    except ImportError:
        raise unittest.SkipTest("bin/sim-lease is Mac-only: it needs fcntl, which this Python lacks")
    RUN_FOLDER = _test_temp.run_folder()
    SLOT_UDID = load_slot_udid(SIM_LEASE)


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


class LeaseCase(unittest.TestCase):
    """One case: its own config dir, home, shims, load file, disk file and logs, and holders stopped after it."""

    def setUp(self):
        base = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, base, True)
        self.base = base
        self.cfg = os.path.join(base, "cfg")
        self.home = os.path.join(base, "home")
        self.shims = os.path.join(base, "shims")
        self.ps_dir = os.path.join(base, "ps")
        self.load_file = os.path.join(base, "loadavg")
        self.load_log = os.path.join(base, "load_reads")
        self.disk_file = os.path.join(base, "disk")
        self.disk_log = os.path.join(base, "disk_reads")
        self.memory_file = os.path.join(base, "memory")
        self.spawn_log = os.path.join(base, "spawned")
        for d in (self.cfg, self.home, self.shims, self.ps_dir):
            os.makedirs(d)
        for name, text in (("uname", UNAME_SH), ("sysctl", SYSCTL_SH), ("ps", PS_SH)):
            path = os.path.join(self.shims, name)
            with open(path, "w") as f:
                f.write(text)
            os.chmod(path, 0o755)
        self.set_load("0.50", "0.50", "0.50")
        self.set_disk(926, 500)

    def set_load(self, one, five, fifteen):
        self.set_load_text("{ %s %s %s }" % (one, five, fifteen))

    def set_load_text(self, text):
        """The line the sysctl shim prints. An empty text makes the load unreadable."""
        with open(self.load_file, "w") as f:
            f.write(text + "\n")

    def set_disk(self, total_gb, free_gb):
        """The disk the brake reads, as TOTAL_GB and FREE_GB. The seam in tests/sim_lease/sitecustomize.py reads it."""
        with open(self.disk_file, "w") as f:
            f.write("%s %s\n" % (total_gb, free_gb))

    def set_disk_unreadable(self):
        with open(self.disk_file, "w") as f:
            f.write("unreadable\n")

    def set_memory(self, pct):
        """The memory reading the brake gets, in percent in use. The seam in tests/sim_lease/sitecustomize.py reads it."""
        with open(self.memory_file, "w") as f:
            f.write("%s\n" % pct)

    def set_memory_unreadable(self):
        with open(self.memory_file, "w") as f:
            f.write("unreadable\n")

    @staticmethod
    def count_lines(path):
        try:
            with open(path) as f:
                return len(f.read().splitlines())
        except FileNotFoundError:
            return 0

    def sysctl_calls(self):
        return self.count_lines(self.load_log)

    def brake_reads(self):
        """How many times the brake read the disk: one per poll of a waiting take."""
        return self.count_lines(self.disk_log)

    def poll_reads(self):
        """The reads a waiting take makes: each poll reads the load or the brake once."""
        return self.sysctl_calls() + self.brake_reads()

    def spawned_programs(self):
        """The program names of the child processes the tool started, one per start, as the seam logs them."""
        try:
            with open(self.spawn_log) as f:
                return set(f.read().split())
        except FileNotFoundError:
            return set()

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items() if k not in (
            "CI", "GITHUB_ACTIONS", "CLAUDE_CONFIG_DIR", "SIM_LEASE_WAIT", "SIM_LEASE_POLL", "SIM_LEASE_TEST_UNAME")}
        env.update(HOME=self.home, CLAUDE_CONFIG_DIR=self.cfg,
                   PATH=self.shims + os.pathsep + os.environ.get("PATH", ""), SIM_LEASE_POLL="1",
                   PYTHONPATH=os.pathsep.join(p for p in (SHIM, os.environ.get("PYTHONPATH", "")) if p),
                   SIM_LEASE_TEST_DISK=self.disk_file, SIM_LEASE_TEST_DISKLOG=self.disk_log,
                   SIM_LEASE_TEST_MEMORY=self.memory_file, SIM_LEASE_TEST_SPAWNLOG=self.spawn_log,
                   SIM_LEASE_TEST_LOAD=self.load_file, SIM_LEASE_TEST_LOADLOG=self.load_log,
                   SIM_LEASE_TEST_PS=self.ps_dir, SIM_LEASE_TEST_REAL_PS=REAL_PS)
        env.update(extra)
        return env

    def run_tool(self, *args, env=None, tool=None):
        return subprocess.run([sys.executable, tool or SIM_LEASE, *args], env=self.env(**(env or {})),
                              capture_output=True, text=True, timeout=60)

    def take(self, device, pid, wait=1, env=None, udid=False, tool=None):
        extra = ["--udid"] if udid else []
        return self.run_tool("take", "--device", device, "--pid", str(pid), "--wait", str(wait), *extra, env=env,
                             tool=tool)

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
        p = subprocess.Popen([sys.executable, SIM_LEASE, "take", "--device", device, "--pid", str(pid), "--wait", "30"],
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

    def test_slot_2_is_refused_when_the_disk_is_busy(self):
        first, second = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.set_disk(926, 10)
        r = self.take("duo", second.pid)
        self.assertEqual(r.returncode, 1, "slot 2 is granted on a 926 GB disk with 10 GB free")
        self.assertEqual(r.stdout.strip(), "", "a refused duo take prints a slot")

    def test_slot_2_is_granted_at_a_5_minute_load_of_99_99_when_the_disk_is_fine(self):
        first, second = self.spawn(), self.spawn()
        self.set_load("0.50", "99.99", "0.50")
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.assertEqual(grant(self.take("duo", second.pid)), (0, "2"),
                         "slot 2 is refused at a 5-minute load of 99.99 though the disk is fine: the load is read")

    def test_a_third_duo_is_not_granted_while_slots_1_and_2_are_held(self):
        first, second, third = self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.assertEqual(grant(self.take("duo", second.pid)), (0, "2"), "the second duo take is not granted slot 2")
        before = self.poll_reads()
        r = self.take("duo", third.pid, wait=2)
        self.assertEqual(r.returncode, 1, "a third duo take is granted while slots 1 and 2 are held")
        self.assertEqual(r.stdout.strip(), "", "a refused third duo take prints a slot")
        self.assertGreaterEqual(self.poll_reads() - before, 2, "the third duo take does not wait before it is refused")

    def assert_waits_then_refused(self, device, needle):
        before = self.poll_reads()
        r = self.take(device, os.getpid(), wait=2)
        self.give(os.getpid())  # a take the old code grants must not hold the pid for the next device's take
        self.assertEqual(r.returncode, 1, "a %s take on a busy disk is not refused with exit 1" % device)
        self.assertGreaterEqual(self.poll_reads() - before, 2,
                                "a %s take does not wait: it reads the brake once per poll" % device)
        lines = [line for line in r.stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, "the refusal of a %s take is not one stderr line" % device)
        self.assertIn(needle, lines[0], "the refusal of a %s take does not name the disk reading" % device)

    def test_a_take_waits_then_exits_1_when_the_disk_is_busy(self):
        self.set_disk(926, 10)
        for device in ("duo", "pro"):
            with self.subTest(device=device):
                self.assert_waits_then_refused(device, "10.0")

    def test_a_1_minute_load_of_60_does_not_refuse_a_take(self):
        self.set_load("60.00", "0.50", "0.50")
        for device, slot in (("duo", "1"), ("pro", "pro")):
            with self.subTest(device=device):
                pid = self.spawn().pid
                r = self.take(device, pid)
                self.give(pid)
                self.assertEqual(grant(r), (0, slot),
                                 "a 1-minute load of 60 refuses a %s take: the load is read" % device)

    def test_a_refusal_names_the_holder(self):
        first, second = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.set_disk(926, 10)
        r = self.take("duo", second.pid)
        self.assertEqual(r.returncode, 1, "a duo take on a 926 GB disk with 10 GB free is not refused")
        self.assertTrue(mentions(r.stderr, first.pid), "the refusal does not name the holder's pid")

    def test_sim_lease_wait_sets_the_wait_when_wait_is_not_passed(self):
        self.set_disk(926, 10)
        before = self.poll_reads()
        r = self.run_tool("take", "--device", "duo", "--pid", str(os.getpid()), env={"SIM_LEASE_WAIT": "2"})
        self.assertEqual(r.returncode, 1, "a take without --wait is not refused with exit 1")
        self.assertGreaterEqual(self.poll_reads() - before, 2,
                                "SIM_LEASE_WAIT does not set the wait: the take does not poll")


class PoolPerDevice(LeaseCase):
    """Each device is its own: a pro and a duo never block each other. A take is judged on its own device's slot and
    on the busy bar, so the load alone decides whether a second phone may boot."""

    def test_pro_is_granted_when_nothing_is_held(self):
        pid = self.spawn().pid
        self.assertEqual(grant(self.take("pro", pid)), (0, "pro"), "a pro take with nothing held is not granted pro")

    def test_duo_is_granted_slot_1_while_pro_is_held(self):
        first, second = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("pro", first.pid)), (0, "pro"), "the pro take is not granted pro")
        self.assertEqual(grant(self.take("duo", second.pid)), (0, "1"),
                         "a duo take is refused while pro is held: the pro lease still blocks the duos")

    def test_pro_is_granted_while_a_duo_is_held(self):
        first, second = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "the duo take is not granted slot 1")
        self.assertEqual(grant(self.take("pro", second.pid)), (0, "pro"),
                         "a pro take is refused while duo slot 1 is held: the duo lease still blocks the pro")

    def test_pro_is_granted_while_both_duo_slots_are_held(self):
        first, second, pro = self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.assertEqual(grant(self.take("duo", second.pid)), (0, "2"), "the second duo take is not granted slot 2")
        self.assertEqual(grant(self.take("pro", pro.pid)), (0, "pro"),
                         "a pro take is refused while both duo slots are held")

    def test_slot_2_is_granted_while_pro_and_slot_1_are_held(self):
        pro, first, second = self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("pro", pro.pid)), (0, "pro"), "the pro take is not granted pro")
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"),
                         "a duo take is refused while pro is held: the pro lease still blocks the duos")
        self.assertEqual(grant(self.take("duo", second.pid)), (0, "2"),
                         "slot 2 is refused while pro and slot 1 are held")

    def test_control_when_slot_1_gives_slot_2_keeps_its_lease_and_the_next_duo_gets_slot_1(self):
        first, second, third = self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.assertEqual(grant(self.take("duo", second.pid)), (0, "2"), "the second duo take is not granted slot 2")
        self.give(first.pid)
        self.assertIn("lease slot 2 pid %d " % second.pid, self.status().stdout,
                      "slot 2 lost its lease when slot 1 gave")
        self.assertEqual(grant(self.take("duo", third.pid)), (0, "1"),
                         "the next duo is not granted slot 1 once slot 1 gives")

    def test_a_busy_disk_refuses_a_pro_take_with_nothing_held(self):
        self.set_disk(926, 10)
        r = self.take("pro", self.spawn().pid)
        self.assertEqual(r.returncode, 1, "a pro take is granted on a busy disk with nothing held")
        self.assertEqual(r.stdout.strip(), "", "a refused pro take prints a slot")

    def test_a_busy_disk_refuses_a_duo_take_while_pro_is_held(self):
        pro, first = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("pro", pro.pid)), (0, "pro"), "the pro take is not granted pro")
        self.set_disk(926, 10)
        r = self.take("duo", first.pid)
        self.assertEqual(r.returncode, 1, "a duo take is granted on a busy disk while pro is held")
        self.assertEqual(r.stdout.strip(), "", "a refused duo take prints a slot")


class Queue(LeaseCase):
    def test_a_pro_head_is_granted_beside_a_held_duo_and_the_later_duo_takes_slot_2(self):
        holder, head, later = self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.assertEqual(grant(self.take("pro", head.pid)), (0, "pro"),
                         "the pro head is refused beside a held duo: the pro lease still blocks the duos")
        self.assertEqual(grant(self.take("duo", later.pid)), (0, "2"),
                         "the later duo is not granted slot 2 after the pro head")

    def test_a_pro_take_does_not_pass_a_queued_duo_head_when_both_duo_slots_are_held(self):
        first, second, head, later = self.spawn(), self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.assertEqual(grant(self.take("duo", second.pid)), (0, "2"), "the second duo take is not granted slot 2")
        self.queue_waiter("duo", head.pid)
        self.assertIn("waiter pid %d " % head.pid, self.status().stdout,
                      "the duo head is not queued before the pro take")
        r = self.take("pro", later.pid)
        self.assertEqual(r.returncode, 1, "a pro take is granted ahead of the queued duo head")
        self.assertEqual(r.stdout.strip(), "", "a refused pro take prints a slot")

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
        holder, pro_holder, head, later = self.spawn(), self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.assertEqual(grant(self.take("pro", pro_holder.pid)), (0, "pro"), "the pro holder is not granted pro")
        r = self.take("pro", head.pid, wait=1)
        self.assertEqual(r.returncode, 1, "a pro take is granted while pro is held")
        self.assertFalse(mentions(self.status().stdout, head.pid), "the timed-out pro take is still on the queue")
        self.assertEqual(grant(self.take("duo", later.pid)), (0, "2"),
                         "a timed-out waiter still blocks the next duo take")

    def test_a_holder_recorded_under_one_tz_is_not_reaped_under_another(self):
        holder, later = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid, env={"TZ": "UTC0"})), (0, "1"),
                         "the first duo take under TZ=UTC0 is not granted slot 1")
        self.assertEqual(grant(self.take("duo", later.pid, env={"TZ": "IST-5:30"})), (0, "2"),
                         "a holder recorded under TZ=UTC0 is reaped under TZ=IST-5:30")


class Give(LeaseCase):
    def test_give_frees_the_lease_and_is_idempotent(self):
        holder, never, later = self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.assertEqual(self.give(holder.pid).returncode, 0, "give of the holder's pid exits non-zero")
        self.assertEqual(self.give(holder.pid).returncode, 0, "a second give of the same pid exits non-zero")
        self.assertEqual(self.give(never.pid).returncode, 0, "give of a pid that holds nothing exits non-zero")
        self.assertEqual(grant(self.take("duo", later.pid)), (0, "1"), "give did not free slot 1")


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
        self.set_disk(926, 10)
        r = self.take("duo", os.getpid(), udid=True)
        self.assertEqual(r.returncode, 1, "a take --udid on a busy disk is not refused with exit 1")
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
    def test_status_lists_each_lease_and_waiter_on_its_own_line_with_the_brake_readings(self):
        self.set_disk(926, 73.6)
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
        self.assertIn("73.6", r.stdout, "status does not show the disk's free GB")
        self.assertNotIn("5-min", r.stdout, "status still shows the load averages")


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


class Brake(LeaseCase):
    """A grant reads the machine-load brake's one measure, its busy bar (decision machine-load-brake): memory over 85%,
    or disk free under the smaller of 10% of the disk and 15 GB. No load average is read, and no child process starts
    for the load. A read that fails counts as normal."""

    def test_a_high_load_does_not_refuse_a_take_when_the_disk_is_fine(self):
        self.set_load("120.00", "150.00", "130.00")
        pid = self.spawn().pid
        self.assertEqual(grant(self.take("duo", pid)), (0, "1"),
                         "a take at a 5-minute load of 150 is refused though the disk is fine: the load is read")

    def test_a_take_and_a_status_never_call_sysctl(self):
        pid = self.spawn().pid
        self.assertEqual(grant(self.take("duo", pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.status()
        calls = self.sysctl_calls()
        self.assertEqual(calls, 0, "sim-lease calls sysctl for the load: %d call(s)" % calls)

    def test_a_take_starts_no_child_process_but_uname_and_ps(self):
        pid = self.spawn().pid
        self.assertEqual(grant(self.take("duo", pid)), (0, "1"), "the first duo take is not granted slot 1")
        extra = self.spawned_programs() - {"uname", "ps"}
        self.assertFalse(extra, "sim-lease starts %s for the load: only uname and ps may start" % sorted(extra))

    def test_a_busy_disk_refuses_a_take_names_the_disk_and_leaves_the_queue(self):
        self.set_disk(926, 10)
        pid = self.spawn().pid
        r = self.take("duo", pid)
        self.assertEqual(r.returncode, 1, "a take on a 926 GB disk with 10 GB free is granted: the disk is not read")
        self.assertEqual(r.stdout.strip(), "", "a refused take prints a slot")
        lines = [line for line in r.stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, "the refusal is not one stderr line")
        self.assertIn("10.0", lines[0], "the refusal does not name the disk's free GB: %s" % lines[0])
        self.assertNotIn("1-min", lines[0], "the refusal still names the load averages: %s" % lines[0])
        self.assertFalse(mentions(self.status().stdout, pid), "the refused take is still on the queue")

    def test_an_unreadable_disk_grants_a_take_when_the_brake_is_loaded(self):
        self.set_disk_unreadable()
        pid = self.spawn().pid
        r = self.take("duo", pid)
        self.assertGreaterEqual(self.brake_reads(), 1,
                                "the brake did not read the disk: it is not loaded, so the grant below proves nothing")
        self.assertEqual(grant(r), (0, "1"), "an unreadable disk reading refuses the take: a read error counts as normal")

    def test_the_busy_bar_is_under_the_smaller_of_10_percent_and_15_gb(self):
        for total, free, granted in ((926, 14.9, False), (926, 15.0, True), (100, 9.9, False), (100, 10.0, True)):
            with self.subTest(total=total, free=free):
                self.set_disk(total, free)
                pid = self.spawn().pid
                r = self.take("duo", pid)
                self.give(pid)  # a take the old code grants must not hold slot 1 for the next subtest
                if granted:
                    self.assertEqual(grant(r), (0, "1"),
                                     "a %s GB disk with %s GB free is busy: the take is refused" % (total, free))
                else:
                    self.assertEqual(r.returncode, 1,
                                     "a %s GB disk with %s GB free is not busy: the take is granted" % (total, free))


class MemoryBrake(LeaseCase):
    """The brake's memory bar (decision machine-load-brake): memory over 85% is busy, and busy refuses every grant. A case
    sets the reading in percent through SIM_LEASE_TEST_MEMORY. Each case first checks that status shows the reading it
    set (scope before subject), so a refusal can come only from that reading."""

    def set_and_check(self, pct):
        self.set_memory(pct)
        self.assertIn("memory %.1f%% in use" % pct, self.status().stdout,
                      "scope: status does not show the memory reading the case set")

    def assert_refused_on_memory(self, r, pct, label):
        self.assertEqual(r.returncode, 1, "%s: a take on memory %.1f%% is granted: the memory bar is not read" % (label, pct))
        self.assertEqual(r.stdout.strip(), "", "%s: a refused take prints a slot" % label)
        lines = [line for line in r.stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, "%s: the refusal is not one stderr line" % label)
        self.assertIn("busy: memory %.1f%% in use" % pct, lines[0],
                      "%s: the refusal does not name memory as the busy reading: %s" % (label, lines[0]))

    def test_memory_is_unread_until_a_case_sets_it(self):
        self.assertIn("memory unread", self.status().stdout, "memory is read though no case sets it")

    def test_memory_at_85_0_is_not_busy(self):
        self.set_and_check(85.0)
        pid = self.spawn().pid
        self.assertEqual(grant(self.take("duo", pid)), (0, "1"), "memory at 85.0% is busy: the bar is over 85%")

    def test_memory_at_85_1_refuses_a_take_and_names_memory(self):
        self.set_and_check(85.1)
        pid = self.spawn().pid
        self.assert_refused_on_memory(self.take("duo", pid), 85.1, "slot 1")

    def test_memory_at_the_empty_and_full_ends(self):
        for pct, granted in ((0.0, True), (100.0, False)):
            with self.subTest(pct=pct):
                self.set_and_check(pct)
                pid = self.spawn().pid
                r = self.take("duo", pid)
                self.give(pid)  # a grant must not hold slot 1 for the next subtest
                if granted:
                    self.assertEqual(grant(r), (0, "1"), "memory at %.1f%% is busy: the take is refused" % pct)
                else:
                    self.assert_refused_on_memory(r, pct, "slot 1")

    def test_memory_busy_refuses_slot_1(self):
        self.set_and_check(90.0)
        pid = self.spawn().pid
        self.assert_refused_on_memory(self.take("duo", pid), 90.0, "slot 1")

    def test_memory_busy_refuses_a_second_duo_take(self):
        self.set_and_check(50.0)
        first, second = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "the first duo take is not granted slot 1 at 50%")
        self.set_and_check(90.0)
        self.assert_refused_on_memory(self.take("duo", second.pid), 90.0, "second duo take")

    def test_an_unreadable_memory_grants_a_take_when_the_brake_is_loaded(self):
        self.set_memory_unreadable()
        pid = self.spawn().pid
        r = self.take("duo", pid)
        self.assertGreaterEqual(self.brake_reads(), 1,
                                "the brake did not read the disk: it is not loaded, so the grant proves nothing")
        self.assertEqual(grant(r), (0, "1"), "an unreadable memory reading refuses the take: a read error counts as normal")


SYNTAX_BROKEN = "def read_load(:\n    pass\n"


class BrokenBrake(LeaseCase):
    """The brake's module cannot load. A missing guard module refuses (decision guard-hooks-fail-closed): a take then
    exits 1 with one stderr line that says the brake could not be loaded, leases nothing and leaves no queue place,
    and status says so. An unreadable reading is different: class Brake grants on it."""

    def copy_tool(self, module=None, text=None):
        """A copy of the tool under test with its hooks/ tree beside it, so the copy loads its own brake. `module` names
        the file in the copy's hooks/ that `text` replaces. Returns the copy's bin/sim-lease. The copy is copied from
        the tool under test so that a mutant run copies the mutant's files, and it lives in this case's folder."""
        root = os.path.dirname(os.path.dirname(os.path.realpath(SIM_LEASE)))
        copy = os.path.join(self.base, "copy")
        os.makedirs(os.path.join(copy, "bin"))
        shutil.copy(SIM_LEASE, os.path.join(copy, "bin", "sim-lease"))
        shutil.copytree(os.path.join(root, "hooks"), os.path.join(copy, "hooks"),
                        ignore=shutil.ignore_patterns("__pycache__", "test_*", "*.pyc"))
        if module:
            with open(os.path.join(copy, "hooks", module), "w") as f:
                f.write(text)
        return os.path.join(copy, "bin", "sim-lease")

    def assert_copy_fails_to_compile(self, module):
        """Scope before subject: the copy's module really is broken, so a refusal below is the brake's absence."""
        path = os.path.join(self.base, "copy", "hooks", module)
        with open(path) as f:
            text = f.read()
        with self.assertRaises(SyntaxError, msg="scope: the copy's %s compiles, so the brake can load" % module):
            compile(text, path, "exec")

    def state_pids(self, key):
        """The pids in the tool's own leases.json list `key` (leases or queue), read with no lock."""
        try:
            with open(os.path.join(self.cfg, "state", "sim-lease", "leases.json")) as f:
                return [e["pid"] for e in json.load(f).get(key, [])]
        except FileNotFoundError:
            return []

    def assert_take_refuses_with_brake_unloaded(self, module):
        tool = self.copy_tool(module, SYNTAX_BROKEN)
        self.assert_copy_fails_to_compile(module)
        pid = self.spawn().pid
        r = self.take("duo", pid, tool=tool)
        self.assertEqual(r.returncode, 1, "a take with %s broken is granted: a missing brake must refuse" % module)
        self.assertEqual(r.stdout.strip(), "", "a take with the brake not loaded prints a slot")
        lines = [line for line in r.stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, "the refusal with %s broken is not one stderr line" % module)
        self.assertIn("brake could not be loaded", lines[0],
                      "the refusal with %s broken does not say the brake could not be loaded: %s" % (module, lines[0]))
        self.assertNotIn(pid, self.state_pids("leases"), "the refused take leaves a lease")
        self.assertNotIn(pid, self.state_pids("queue"), "the refused take is still in the queue")

    def test_an_intact_copy_grants_slot_1(self):
        """The control for the copy harness: with nothing broken, the copy's tool loads its brake and grants. Without it
        a crash in the copy would read as a refusal."""
        tool = self.copy_tool()
        pid = self.spawn().pid
        self.assertEqual(grant(self.take("duo", pid, tool=tool)), (0, "1"),
                         "the intact copy does not grant slot 1: the copy harness is broken")

    def test_a_broken_guard_module_refuses_a_take(self):
        self.assert_take_refuses_with_brake_unloaded("guard.py")

    def test_a_broken_guard_core_refuses_a_take(self):
        self.assert_take_refuses_with_brake_unloaded("guard_core.py")

    def test_status_says_the_brake_could_not_be_loaded(self):
        tool = self.copy_tool("guard.py", SYNTAX_BROKEN)
        self.assert_copy_fails_to_compile("guard.py")
        r = self.run_tool("status", tool=tool)
        self.assertEqual(r.returncode, 0, "status exits non-zero with the brake not loaded")
        self.assertIn("brake could not be loaded", r.stdout,
                      "status does not say the brake could not be loaded: %s" % r.stdout)


class Concurrency(LeaseCase):
    def test_two_concurrent_takes_never_both_get_slot_1(self):
        for n in range(5):
            a, b = self.spawn(), self.spawn()
            procs = [subprocess.Popen([sys.executable, SIM_LEASE, "take", "--device", "duo", "--pid", str(p.pid),
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
