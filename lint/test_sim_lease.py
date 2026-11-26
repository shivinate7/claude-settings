#!/usr/bin/env python3
"""Tests for bin/sim-lease, the Mac-wide lease that bin/sim-test takes before its own boot.

Run: python3 lint/test_sim_lease.py. SIM_LEASE=PATH picks the tool; the default is bin/sim-lease in this repo.
No case reads this machine's load, OS or devices: PATH shims for uname, sysctl and xcrun read files in the case's own
folder, and the ps shim passes through to the real ps except for a start time that a case sets. The xcrun shim answers
`simctl list devices -j` from a device list the case writes (the fleet by default) and logs each call. The device ids
here are fresh: no repo file holds them, and a take finds each phone by its name. CI and GITHUB_ACTIONS are unset for
each run. A holder is a live `sleep` child or a child already reaped, so no case depends on a pid being free.
Temp files follow decisions/test-temp-standard.md: one run folder from lint/_test_temp.py per run, removed at the end.
"""
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

RUNTIME = "com.apple.CoreSimulator.SimRuntime.iOS-27-0"
DEVICE_TYPE = "com.apple.CoreSimulator.SimDeviceType.iPhone-Duo"
# The fleet a take finds by name: (name, udid) pairs. The ids are fresh, and no repo file holds them.
FLEET_PAIRS = [("iPhone Duo", "5E7A0001-0000-4000-8000-0000000000A1"),
               ("iPhone Duo 2", "5E7A0002-0000-4000-8000-0000000000A2"),
               ("iPhone 18 Pro", "5E7A0003-0000-4000-8000-0000000000A3")]
FLEET = dict(FLEET_PAIRS)
TWIN = "5E7A0004-0000-4000-8000-0000000000A4"  # a second device named iPhone Duo, for the doubled-name case

UNAME_SH = '#!/bin/sh\necho "${SIM_LEASE_TEST_UNAME:-Darwin}"\n'
SYSCTL_SH = '#!/bin/sh\necho read >> "$SIM_LEASE_TEST_LOADLOG"\ncat "$SIM_LEASE_TEST_LOAD"\n'
# Every call is logged. A case that writes SIM_LEASE_TEST_XCRUN_RC makes the call exit with that code; the list is printed
# from SIM_LEASE_TEST_DEVICES either way.
XCRUN_SH = ('#!/bin/sh\necho "$*" >> "$SIM_LEASE_TEST_XCRUN_LOG"\n'
            'if [ -f "$SIM_LEASE_TEST_XCRUN_RC" ]; then exit "$(cat "$SIM_LEASE_TEST_XCRUN_RC")"; fi\n'
            'cat "$SIM_LEASE_TEST_DEVICES"\n')
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


def device_list(pairs):
    """`xcrun simctl list devices -j` for (name, udid) PAIRS: one runtime, every device available and shut down."""
    return json.dumps({"devices": {RUNTIME: [
        {"name": name, "udid": udid, "state": "Shutdown", "isAvailable": True, "deviceTypeIdentifier": DEVICE_TYPE}
        for name, udid in pairs]}})


def setUpModule():
    global RUN_FOLDER
    try:
        import fcntl  # noqa: F401  sim-lease locks with it; Windows' Python has none
    except ImportError:
        raise unittest.SkipTest("bin/sim-lease is Mac-only: it needs fcntl, which this Python lacks")
    RUN_FOLDER = _test_temp.run_folder()


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
        self.devices = os.path.join(base, "devices.json")
        self.xcrun_log = os.path.join(base, "xcrun_calls")
        self.xcrun_rc = os.path.join(base, "xcrun_rc")
        for d in (self.cfg, self.home, self.shims, self.ps_dir):
            os.makedirs(d)
        for name, text in (("uname", UNAME_SH), ("sysctl", SYSCTL_SH), ("ps", PS_SH), ("xcrun", XCRUN_SH)):
            path = os.path.join(self.shims, name)
            with open(path, "w") as f:
                f.write(text)
            os.chmod(path, 0o755)
        self.set_load("0.50", "0.50", "0.50")
        self.set_fleet(FLEET_PAIRS)

    def set_load(self, one, five, fifteen):
        with open(self.load_file, "w") as f:
            f.write("{ %s %s %s }\n" % (one, five, fifteen))

    def set_fleet(self, pairs):
        """The device list the xcrun shim prints for `simctl list devices -j`: (name, udid) PAIRS."""
        with open(self.devices, "w") as f:
            f.write(device_list(pairs))

    def set_devices_text(self, text):
        with open(self.devices, "w") as f:
            f.write(text)

    def set_xcrun_rc(self, code):
        with open(self.xcrun_rc, "w") as f:
            f.write("%d\n" % code)

    def xcrun_calls(self):
        try:
            with open(self.xcrun_log) as f:
                return len(f.read().splitlines())
        except FileNotFoundError:
            return 0

    def leases(self):
        """The lease records in leases.json, or [] when the file is absent."""
        try:
            with open(os.path.join(self.cfg, "state", "sim-lease", "leases.json")) as f:
                return json.load(f)["leases"]
        except FileNotFoundError:
            return []

    def load_reads(self):
        try:
            with open(self.load_log) as f:
                return len(f.read().splitlines())
        except FileNotFoundError:
            return 0

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items() if k not in (
            "CI", "GITHUB_ACTIONS", "CLAUDE_CONFIG_DIR", "SIM_LEASE_WAIT", "SIM_LEASE_POLL", "SIM_LEASE_TEST_UNAME")}
        env.update(HOME=self.home, CLAUDE_CONFIG_DIR=self.cfg,
                   PATH=self.shims + os.pathsep + os.environ.get("PATH", ""), SIM_LEASE_POLL="1",
                   SIM_LEASE_TEST_LOAD=self.load_file, SIM_LEASE_TEST_LOADLOG=self.load_log,
                   SIM_LEASE_TEST_PS=self.ps_dir, SIM_LEASE_TEST_REAL_PS=REAL_PS,
                   SIM_LEASE_TEST_DEVICES=self.devices, SIM_LEASE_TEST_XCRUN_LOG=self.xcrun_log,
                   SIM_LEASE_TEST_XCRUN_RC=self.xcrun_rc)
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

    def assert_waits_then_refused(self, device, needle):
        before = self.load_reads()
        r = self.take(device, os.getpid(), wait=2)
        self.assertEqual(r.returncode, 1, "a %s take at this load is not refused with exit 1" % device)
        self.assertGreaterEqual(self.load_reads() - before, 2,
                                "a %s take does not wait: it reads the load once" % device)
        lines = [line for line in r.stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, "the refusal of a %s take is not one stderr line" % device)
        self.assertIn(needle, lines[0], "the refusal of a %s take does not name the load" % device)

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
            time.sleep(0.05)  # poll interval of a condition wait; the try count is the deadline
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

    def test_duo_is_granted_beside_a_held_pro_when_the_load_brake_allows(self):
        # Ruling sims-load-brake-only (owner, 21:59 CST Nov 12): no pairing; only the load brake limits a grant.
        holder, duo = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("pro", holder.pid)), (0, "pro"), "the pro take is not granted pro")
        self.assertEqual(grant(self.take("duo", duo.pid)), (0, "1"),
                         "a duo take beside the held pro is not granted slot 1 at a load the brake allows")

    def test_duo_beside_a_held_pro_is_refused_only_when_the_load_brake_refuses(self):
        holder = self.spawn()
        self.assertEqual(grant(self.take("pro", holder.pid)), (0, "pro"), "the pro take is not granted pro")
        for one, five, needle in (("0.50", "100.00", "100"), ("60.00", "0.50", "60")):
            with self.subTest(one=one, five=five):
                self.set_load(one, five, "0.50")
                self.assert_waits_then_refused("duo", needle)

    def test_pro_is_granted_beside_a_held_duo_when_the_load_brake_allows(self):
        # Ruling sims-load-brake-only (owner, 21:59 CST Nov 12): no pairing; only the load brake limits a grant.
        holder, pro = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the duo take is not granted slot 1")
        self.assertEqual(grant(self.take("pro", pro.pid)), (0, "pro"),
                         "a pro take beside the held duo is not granted pro at a load the brake allows")

    def test_pro_beside_a_held_duo_is_refused_only_when_the_load_brake_refuses(self):
        holder = self.spawn()
        self.assertEqual(grant(self.take("duo", holder.pid)), (0, "1"), "the duo take is not granted slot 1")
        for one, five, needle in (("0.50", "100.00", "100"), ("60.00", "0.50", "60")):
            with self.subTest(one=one, five=five):
                self.set_load(one, five, "0.50")
                self.assert_waits_then_refused("pro", needle)

    def test_a_second_pro_is_refused_beside_a_held_pro(self):
        # The pro slot is one slot. At a load the brake allows, a second pro waits, is refused, and the refusal names the
        # held pro. Once that pro gives back, a pro take is granted.
        self.set_load("0.50", "0.50", "0.50")
        holder, second = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("pro", holder.pid)), (0, "pro"), "the pro holder take is not granted pro")
        before = self.load_reads()
        r = self.take("pro", second.pid, wait=2)
        self.assertEqual(r.returncode, 1, "a second pro take beside the held pro is granted")
        self.assertEqual(r.stdout.strip(), "", "a refused second pro take prints a slot")
        self.assertGreaterEqual(self.load_reads() - before, 2, "a second pro take beside the held pro does not wait")
        lines = [line for line in r.stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, "the refusal of a second pro take is not one stderr line")
        self.assertIn("slot pro pid %d" % holder.pid, lines[0],
                      "the refusal of a second pro take does not name the held pro")
        self.give(holder.pid)
        self.assertEqual(grant(self.take("pro", second.pid)), (0, "pro"),
                         "a pro take is not granted once the held pro gives back")


class Queue(LeaseCase):
    def test_second_waiter_is_not_granted_ahead_of_the_head(self):
        # The head waits on the one pro slot, held by another pro lease. Slot 1 is free and the load allows a grant,
        # so only the queue keeps the later duo out.
        pro_holder, head, later = self.spawn(), self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("pro", pro_holder.pid)), (0, "pro"), "the pro holder take is not granted pro")
        self.queue_waiter("pro", head.pid)
        r = self.take("duo", later.pid)
        self.assertEqual(r.returncode, 1, "a duo take is granted ahead of the queued pro head")

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
        self.set_load("0.50", "100.00", "0.50")
        r = self.take("pro", head.pid, wait=1)
        self.assertEqual(r.returncode, 1, "a pro take at a 5-minute load of 100 is not refused")
        self.assertFalse(mentions(self.status().stdout, head.pid), "the timed-out pro take is still on the queue")
        self.set_load("0.50", "0.50", "0.50")
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
    """take --udid prints the granted slot's device UDID: the id of the device the slot names in the device list."""

    def test_duo_slots_print_their_own_udids(self):
        first, second = self.spawn(), self.spawn()
        self.assertEqual(grant(self.take("duo", first.pid, udid=True)), (0, FLEET["iPhone Duo"]),
                         "take --udid is not granted the id of the device named iPhone Duo for slot 1")
        self.assertEqual(grant(self.take("duo", second.pid, udid=True)), (0, FLEET["iPhone Duo 2"]),
                         "take --udid is not granted the id of the device named iPhone Duo 2 for slot 2 while slot 1 is held")

    def test_pro_prints_the_pro_udid(self):
        pid = self.spawn().pid
        self.assertEqual(grant(self.take("pro", pid, udid=True)), (0, FLEET["iPhone 18 Pro"]),
                         "take --udid for pro is not granted the id of the device named iPhone 18 Pro")

    def test_without_udid_the_take_still_prints_the_slot(self):
        pid = self.spawn().pid
        self.assertEqual(grant(self.take("duo", pid)), (0, "1"), "take without --udid no longer prints the slot")

    def test_each_slot_names_its_own_device(self):
        first, second, pro = self.spawn(), self.spawn(), self.spawn()
        got = [self.take("duo", first.pid, udid=True), self.take("duo", second.pid, udid=True),
               self.take("pro", pro.pid, udid=True)]
        self.assertTrue(all(r.returncode == 0 for r in got), "a slot of the three is not granted")
        self.assertEqual(len({r.stdout.strip() for r in got}), 3, "two slots print the same device UDID")

    def test_a_refused_take_udid_prints_nothing(self):
        self.set_load("0.50", "100.00", "0.50")
        r = self.take("duo", os.getpid(), udid=True)
        self.assertEqual(r.returncode, 1, "a take --udid at a 5-minute load of 100 is not refused with exit 1")
        self.assertEqual(r.stdout.strip(), "", "a refused take --udid prints a UDID")


class NameLookup(LeaseCase):
    """A take finds each phone by its exact name in `xcrun simctl list devices -j`. A name with no device, a name on
    two devices, or a list that cannot be read is refused: no id is guessed, and no lease or queue place is kept."""

    def test_iphone_duo_does_not_match_iphone_duo_2(self):
        # Only iPhone Duo 2 is listed. A duo take needs the device named iPhone Duo, so it is refused, and no UDID of
        # iPhone Duo 2 is printed for it.
        self.set_fleet([FLEET_PAIRS[1], FLEET_PAIRS[2]])
        pid = self.spawn().pid
        r = self.take("duo", pid, udid=True)
        self.assertEqual(r.returncode, 1, "a duo take with no device named iPhone Duo is not refused with exit 1")
        self.assertEqual(r.stdout.strip(), "", "a duo take with no device named iPhone Duo prints a UDID")

    def test_a_missing_pro_does_not_refuse_a_duo(self):
        # Control: the duo names are the only ones a duo take reads.
        self.set_fleet([FLEET_PAIRS[0], FLEET_PAIRS[1]])
        pid = self.spawn().pid
        self.assertEqual(grant(self.take("duo", pid)), (0, "1"),
                         "a duo take is refused because no device is named iPhone 18 Pro")

    def test_two_devices_of_one_name_refuse_with_both_ids_and_leave_no_lease(self):
        self.set_fleet([FLEET_PAIRS[0], ("iPhone Duo", TWIN), FLEET_PAIRS[1], FLEET_PAIRS[2]])
        pid = self.spawn().pid
        r = self.take("duo", pid)
        self.assertEqual(r.returncode, 1, "a duo take with two devices named iPhone Duo is not refused with exit 1")
        self.assertTrue(FLEET["iPhone Duo"] in r.stderr and TWIN in r.stderr,
                        "the refusal does not name both ids of the two iPhone Duo devices")
        self.assertEqual(self.leases(), [], "a refused duo take left a lease")
        self.assertFalse(mentions(self.status().stdout, pid), "a refused duo take left a queue place")

    def test_a_missing_name_refuses_with_the_fix(self):
        self.set_fleet([FLEET_PAIRS[0], FLEET_PAIRS[1]])
        pid = self.spawn().pid
        r = self.take("pro", pid)
        self.assertEqual(r.returncode, 1, "a pro take with no device named iPhone 18 Pro is not refused with exit 1")
        self.assertIn("iPhone 18 Pro", r.stderr, "the refusal does not name the missing device")
        self.assertIn("simctl", r.stderr, "the refusal does not name the fix (the owner's simctl rename or create)")

    def test_a_list_that_exits_non_zero_refuses_as_unknown(self):
        self.set_xcrun_rc(1)
        pid = self.spawn().pid
        r = self.take("duo", pid)
        self.assertEqual(r.returncode, 1, "a duo take whose simctl list exits non-zero is not refused with exit 1")
        self.assertIn("unknown", r.stderr.lower(), "the refusal of an unreadable device list does not say unknown")

    def test_a_list_that_prints_bad_json_refuses_as_unknown(self):
        self.set_devices_text("not json {")
        pid = self.spawn().pid
        r = self.take("duo", pid)
        self.assertEqual(r.returncode, 1, "a duo take whose simctl list prints bad JSON is not refused with exit 1")
        self.assertIn("unknown", r.stderr.lower(), "the refusal of a bad device list does not say unknown")

    def test_the_lease_entry_carries_the_udid_it_granted(self):
        pid = self.spawn().pid
        self.assertEqual(grant(self.take("duo", pid)), (0, "1"), "the duo take is not granted slot 1")
        entry = next((e for e in self.leases() if e.get("pid") == pid), {})
        self.assertEqual(entry.get("udid"), FLEET["iPhone Duo"], "the lease entry does not carry the udid it granted")

    def test_a_waiting_take_reads_the_device_list_at_most_once(self):
        # Control: the list is read once per take, before the queue, never once per poll. A wait of 2 s polls at 1 s.
        self.set_load("0.50", "100.00", "0.50")
        pid = os.getpid()
        r = self.take("duo", pid, wait=2)
        self.assertEqual(r.returncode, 1, "a duo take at a 5-minute load of 100 is not refused with exit 1")
        self.assertLessEqual(self.xcrun_calls(), 1, "a waiting take reads the device list once per poll")

    def test_a_ci_or_non_darwin_take_reads_no_device_list(self):
        # Control: a no-op take never reaches the lookup.
        for label, env in (("uname Linux", {"SIM_LEASE_TEST_UNAME": "Linux"}), ("CI=true", {"CI": "true"}),
                           ("GITHUB_ACTIONS=true", {"GITHUB_ACTIONS": "true"})):
            with self.subTest(label):
                if os.path.exists(self.xcrun_log):
                    os.remove(self.xcrun_log)
                pid = self.spawn().pid
                self.assertEqual(grant(self.take("duo", pid, env=env, udid=True)), (0, "none"),
                                 "%s: take --udid is not a no-op that prints none" % label)
                self.assertEqual(self.xcrun_calls(), 0, "%s: a no-op take made a simctl call" % label)


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
