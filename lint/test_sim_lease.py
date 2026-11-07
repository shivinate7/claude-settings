#!/usr/bin/env python3
"""Tests for bin/sim-lease, the Mac-wide lease that bin/sim-test takes before its own boot.

Run: python3 lint/test_sim_lease.py. SIM_LEASE=PATH picks the tool; the default is bin/sim-lease in this repo.
No case reads this machine's load or OS: PATH shims for uname and sysctl read files in the case's own folder, and the
ps shim passes through to the real ps except for a start time that a case sets. CI and GITHUB_ACTIONS are unset for
each run. A holder is a live `sleep` child or a child already reaped, so no case depends on a pid being free.
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
    """One case: its own config dir, home, shims and load file, and holders stopped after it."""

    def setUp(self):
        base = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, base, True)
        self.cfg = os.path.join(base, "cfg")
        self.home = os.path.join(base, "home")
        self.shims = os.path.join(base, "shims")
        self.ps_dir = os.path.join(base, "ps")
        self.load_file = os.path.join(base, "loadavg")
        self.load_log = os.path.join(base, "load_reads")
        for d in (self.cfg, self.home, self.shims, self.ps_dir):
            os.makedirs(d)
        for name, text in (("uname", UNAME_SH), ("sysctl", SYSCTL_SH), ("ps", PS_SH)):
            path = os.path.join(self.shims, name)
            with open(path, "w") as f:
                f.write(text)
            os.chmod(path, 0o755)
        self.set_load("0.50", "0.50", "0.50")

    def set_load(self, one, five, fifteen):
        with open(self.load_file, "w") as f:
            f.write("{ %s %s %s }\n" % (one, five, fifteen))

    def load_reads(self):
        try:
            with open(self.load_log) as f:
                return len(f.read().splitlines())
        except FileNotFoundError:
            return 0

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items() if k not in (
            "CI", "GITHUB_ACTIONS", "CLAUDE_CONFIG_DIR", "SIM_LEASE_WAIT", "SIM_LEASE_POLL", "SIM_LEASE_TEST_UNAME",
            "SIM_LEASE_NOW", "SIM_LEASE_SKIP", "SIM_LEASE_MAX")}
        env.update(HOME=self.home, CLAUDE_CONFIG_DIR=self.cfg,
                   PATH=self.shims + os.pathsep + os.environ.get("PATH", ""), SIM_LEASE_POLL="1",
                   SIM_LEASE_TEST_LOAD=self.load_file, SIM_LEASE_TEST_LOADLOG=self.load_log,
                   SIM_LEASE_TEST_PS=self.ps_dir, SIM_LEASE_TEST_REAL_PS=REAL_PS)
        env.update(extra)
        return env

    def run_tool(self, *args, env=None):
        return subprocess.run([sys.executable, SIM_LEASE, *args], env=self.env(**(env or {})),
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

    def queue_waiter(self, device, pid, env=None):
        """Starts a take that waits in the background. Returns once status lists its pid: a condition, not a delay."""
        p = subprocess.Popen([sys.executable, SIM_LEASE, "take", "--device", device, "--pid", str(pid), "--wait", "30"],
                             env=self.env(**(env or {})), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
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

    def test_slot_2_is_refused_at_a_5_minute_load_of_60(self):
        first, second = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.set_load("0.50", "60.00", "0.50")
        r = self.take("duo", second.pid)
        self.assertEqual(r.returncode, 1, "slot 2 is not refused at a 5-minute load of 60")
        self.assertEqual(r.stdout.strip(), "", "a refused duo take prints a slot")

    def test_slot_2_is_granted_just_under_a_5_minute_load_of_60(self):
        first, second = self.spawn(), self.spawn()
        self.set_load("0.50", "59.99", "0.50")
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.assertEqual(grant(self.take("duo", second.pid)), (0, "2"),
                         "slot 2 is refused at a 5-minute load of 59.99")

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
        self.assertEqual(r.returncode, 1, "a %s take at this load is not refused with exit 1" % device)
        self.assertGreaterEqual(self.load_reads() - before, 2,
                                "a %s take does not wait: it reads the load once" % device)
        lines = [line for line in r.stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, "the refusal of a %s take is not one stderr line" % device)
        self.assertIn(needle, lines[0], "the refusal of a %s take does not name the load" % device)

    def test_a_take_waits_then_exits_1_at_a_5_minute_load_of_100(self):
        self.set_load("0.50", "100.00", "0.50")
        for device in ("duo", "pro"):
            with self.subTest(device=device):
                self.assert_waits_then_refused(device, "100")

    def test_a_take_waits_then_exits_1_at_a_1_minute_load_of_60(self):
        self.set_load("60.00", "0.50", "0.50")
        for device in ("duo", "pro"):
            with self.subTest(device=device):
                self.assert_waits_then_refused(device, "60")

    def test_a_refusal_names_the_holder(self):
        first, second = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", first.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.set_load("0.50", "100.00", "0.50")
        r = self.take("duo", second.pid)
        self.assertEqual(r.returncode, 1, "a duo take at a 5-minute load of 100 is not refused")
        self.assertTrue(mentions(r.stderr, first.pid), "the refusal does not name the holder's pid")

    def test_sim_lease_wait_sets_the_wait_when_wait_is_not_passed(self):
        self.set_load("0.50", "100.00", "0.50")
        before = self.load_reads()
        r = self.run_tool("take", "--device", "duo", "--pid", str(os.getpid()), env={"SIM_LEASE_WAIT": "2"})
        self.assertEqual(r.returncode, 1, "a take without --wait is not refused with exit 1")
        self.assertGreaterEqual(self.load_reads() - before, 2,
                                "SIM_LEASE_WAIT does not set the wait: the take does not poll")


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


class StaleWaiter(LeaseCase):
    """A waiting take stamps its queue entry with `seen`, the epoch seconds of its last poll (SIM_LEASE_NOW is the clock
    here). A waiter whose stamp is older than SIM_LEASE_SKIP is passed over and keeps its place; its next poll makes it
    fresh again."""

    def skipping_env(self, now):
        return {"SIM_LEASE_NOW": str(now), "SIM_LEASE_SKIP": "30"}

    def queue_entry(self, pid):
        """pid's entry in the queue of leases.json, or None."""
        try:
            with open(os.path.join(self.cfg, "state", "sim-lease", "leases.json")) as f:
                queue = json.load(f).get("queue", [])
        except FileNotFoundError:
            return None
        return next((e for e in queue if isinstance(e, dict) and e.get("pid") == pid), None)

    def leased(self, pid):
        """True when status lists a lease for pid."""
        return any(line.startswith("lease ") and mentions(line, pid) for line in self.status().stdout.splitlines())

    def wait_for(self, condition, failure):
        """Polls condition every 50 ms, up to 5 s, and fails with `failure` when it never holds."""
        for _ in range(100):
            if condition():
                return
            time.sleep(0.05)
        self.fail(failure)

    def test_a_stale_head_is_passed_over_and_the_next_fresh_waiter_is_granted(self):
        self.set_load("0.50", "60.00", "0.50")  # slot 2 is refused, so the holder's slot 1 is the only grant
        holder, head, later = self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the first duo take is not granted slot 1")
        stop(self.queue_waiter("duo", head.pid, env=self.skipping_env(1000)))  # SIGKILL: no cleanup, the entry stays
        self.assertIsNotNone(self.queue_entry(head.pid), "the killed head's entry is not on the queue")
        self.assertEqual(self.give(holder.pid).returncode, 0, "give of the holder's pid exits non-zero")
        r = self.take("duo", later.pid, env=self.skipping_env(1100))
        self.assertEqual(grant(r), (0, "1"), "a stale head blocks the queue: the next fresh waiter is not granted slot 1")
        self.assertIsNotNone(self.queue_entry(head.pid), "the stale head lost its place on the queue")

    def test_a_fresh_head_is_never_passed_over_so_fifo_holds(self):
        """A control: main is strict FIFO, so it holds already. The fresh head is a pro, blocked by the duo holder."""
        holder, head, later = self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.queue_waiter("pro", head.pid, env=self.skipping_env(1000))
        r = self.take("duo", later.pid, env=self.skipping_env(1010))
        self.assertEqual(r.returncode, 1, "a duo take is granted ahead of a fresh pro head")

    def test_a_poll_stamps_its_queue_entry_with_sim_lease_now(self):
        holder, head = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the first duo take is not granted slot 1")
        self.queue_waiter("pro", head.pid, env=self.skipping_env(1234))
        entry = self.queue_entry(head.pid)
        self.assertIsNotNone(entry, "the waiter's entry is not in leases.json")
        self.assertEqual(entry.get("seen"), 1234, "a poll does not stamp the queue entry's seen with SIM_LEASE_NOW")

    def test_a_stale_head_that_polls_again_gets_the_next_free_slot_ahead_of_later_waiters(self):
        self.set_load("0.50", "60.00", "0.50")
        holder, head, first_later, second_later = self.spawn(), self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the first duo take is not granted slot 1")
        stop(self.queue_waiter("duo", head.pid, env=self.skipping_env(1000)))  # the head is stale from 1100 on
        self.queue_waiter("duo", first_later.pid, env=self.skipping_env(1100))
        self.assertEqual(self.give(holder.pid).returncode, 0, "give of the holder's pid exits non-zero")
        self.wait_for(lambda: self.leased(first_later.pid),
                      "the first later waiter is not granted slot 1 past the stale head")
        self.queue_waiter("duo", head.pid, env=self.skipping_env(1100))  # the head polls again: fresh, and keeps its place
        self.wait_for(lambda: (self.queue_entry(head.pid) or {}).get("seen") == 1100,
                      "the stale head's poll does not re-stamp its queue entry")
        self.queue_waiter("duo", second_later.pid, env=self.skipping_env(1100))
        self.assertEqual(self.give(first_later.pid).returncode, 0, "give of the first later waiter exits non-zero")
        self.wait_for(lambda: self.leased(head.pid),
                      "the stale head that polled again is not granted the next free slot")
        self.assertFalse(self.leased(second_later.pid), "a later waiter is granted ahead of the head that polled again")


class LeaseExpiry(LeaseCase):
    """A lease older than SIM_LEASE_MAX seconds since its grant is dropped on the next take, so the next waiter gets its
    slot. SIM_LEASE_NOW is the clock: the grant is stamped with it, as `seen` is, and a later take reads it. The default
    is 1800 s (unmeasured)."""

    def clock(self, now, max_s=None):
        extra = {"SIM_LEASE_NOW": str(now)}
        if max_s is not None:
            extra["SIM_LEASE_MAX"] = str(max_s)
        return extra

    def test_a_lease_older_than_sim_lease_max_is_dropped_for_the_next_waiter(self):
        holder, second, waiter = self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid, env=self.clock(1000, 60))), (0, "1"))
        self.assertEqual(grant(self.take("duo", second.pid, env=self.clock(1050, 60))), (0, "2"))
        r = self.take("duo", waiter.pid, wait=2, env=self.clock(1061, 60))
        self.assertEqual(grant(r), (0, "1"),
                         "a lease granted at 1000 is older than SIM_LEASE_MAX=60 at 1061, so the next waiter takes slot 1")

    def test_a_lease_younger_than_sim_lease_max_still_blocks_the_next_waiter(self):
        holder, second, waiter = self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid, env=self.clock(1000, 60))), (0, "1"))
        self.assertEqual(grant(self.take("duo", second.pid, env=self.clock(1000, 60))), (0, "2"))
        r = self.take("duo", waiter.pid, wait=1, env=self.clock(1059, 60))
        self.assertEqual(r.returncode, 1, "a lease 59 s old is under SIM_LEASE_MAX=60, so the waiter is not granted")
        lines = self.run_tool("status", env=self.clock(1059, 60)).stdout.splitlines()
        self.assertTrue(any(line.startswith("lease slot 1 ") and mentions(line, holder.pid) for line in lines),
                        "the holder keeps slot 1")

    def test_without_sim_lease_max_a_lease_older_than_1800_s_is_dropped(self):
        holder, second, waiter = self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid, env=self.clock(1000))), (0, "1"))
        self.assertEqual(grant(self.take("duo", second.pid, env=self.clock(1000))), (0, "2"))
        r = self.take("duo", waiter.pid, wait=2, env=self.clock(2801))
        self.assertEqual(grant(r), (0, "1"), "a lease granted at 1000 is 1801 s old at 2801, over the default 1800 s")


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
        self.set_load("0.50", "100.00", "0.50")
        r = self.take("duo", os.getpid(), udid=True)
        self.assertEqual(r.returncode, 1, "a take --udid at a 5-minute load of 100 is not refused with exit 1")
        self.assertEqual(r.stdout.strip(), "", "a refused take --udid prints a UDID")


UNKNOWN_DUO_UDID = "AAAAAAAA-0000-4000-8000-000000000001"  # a Duo UDID that SLOT_UDID does not name


class ReuseTake(LeaseCase):
    """take --reuse UDID takes the lease of the slot that boots UDID: the lease a reuse of a booted Duo holds."""

    def reuse(self, udid, pid, wait=1, env=None):
        return self.run_tool("take", "--device", "duo", "--reuse", udid, "--pid", str(pid), "--wait", str(wait),
                             env=env)

    def lease_line(self, pid):
        """The status line of pid's lease, or '' when status lists none."""
        return next((line for line in self.status().stdout.splitlines()
                     if line.startswith("lease ") and mentions(line, pid)), "")

    def test_reuse_of_slot_1s_udid_takes_slot_1(self):
        pid = self.spawn().pid
        r = self.reuse(SLOT_UDID["1"], pid)
        self.assertEqual(r.returncode, 0, "take --reuse of slot 1's UDID is not granted: exit %d" % r.returncode)
        self.assertIn(" slot 1 ", self.lease_line(pid), "status does not show slot 1 held by the reuse's pid")

    def test_reuse_at_a_1_minute_load_of_60_is_granted(self):
        self.set_load("60.00", "0.50", "0.50")
        pid = self.spawn().pid
        r = self.reuse(SLOT_UDID["1"], pid)
        self.assertEqual(r.returncode, 0, "take --reuse at a 1-minute load of 60 is refused: a reuse skips the load bars")

    def test_reuse_waits_behind_a_live_slot_1_holder_then_exits_1(self):
        holder, second = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the first duo take is not granted slot 1")
        r = self.reuse(SLOT_UDID["1"], second.pid)
        self.assertEqual(r.returncode, 1, "take --reuse of slot 1's UDID is not refused while slot 1 is held: exit %d"
                         % r.returncode)
        self.assertTrue(mentions(r.stderr, holder.pid), "the refusal does not name the slot 1 holder")

    def test_reuse_of_a_duo_udid_outside_slot_udid_takes_slot_other_with_its_udid_in_status(self):
        self.assertNotIn(UNKNOWN_DUO_UDID, SLOT_UDID.values(), "the unknown UDID is one of SLOT_UDID's")
        pid = self.spawn().pid
        r = self.reuse(UNKNOWN_DUO_UDID, pid)
        self.assertEqual(r.returncode, 0, "take --reuse of a Duo UDID outside SLOT_UDID is refused: exit %d"
                         % r.returncode)
        line = self.lease_line(pid)
        self.assertIn(" slot other ", line, "status does not show the lease as slot other")
        self.assertIn("udid %s" % UNKNOWN_DUO_UDID, line, "status does not show the UDID of the slot other lease")


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
    def test_status_lists_each_lease_and_waiter_on_its_own_line_with_the_load(self):
        self.set_load("1.23", "4.56", "7.89")
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
        self.assertIn("4.56", r.stdout, "status does not show the 5-minute load")

    def test_status_lease_line_names_the_udid_of_the_slot(self):
        pid = self.spawn().pid
        self.assertEqual(grant(self.take("duo", pid, udid=True)), (0, SLOT_UDID["1"]),
                         "take --udid is not granted slot 1's UDID")
        line = next((ln for ln in self.status().stdout.splitlines() if ln.startswith("lease ") and mentions(ln, pid)),
                    "")
        self.assertIn("udid %s" % SLOT_UDID["1"], line, "status does not name the UDID of the lease")


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
