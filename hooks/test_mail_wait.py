#!/usr/bin/env python3
"""Cases for `mail wait`: one background command that blocks until the session's own mailbox address has a new
open message, then prints one line and exits 0 (decision session-messages, "One route" and "Design").

Run it from the repository root:

    python3 hooks/test_mail_wait.py

Standard library only, as hooks/test_mail.py is. The git fixtures come from that suite by import; its test classes
are not imported here. No case reads or waits on a real clock: a waiter runs on a FakeTime whose sleep runs the
case's scheduled events and then moves the clock on (P5).

Contract the builder codes against. The names are pinned in this block, and each case cites them:
- hooks/mail.py wait(env, addrs, *, clock, sleep, run_git=None, pid_alive=None, start_time=None, pid=None,
  ppid=None, interval=None, max_seconds=None) -> int. clock() gives seconds; sleep(seconds) returns None. The one
  line (new mail, not started, or ended) goes to stdout or stderr; the cases capture both. Defaults: interval 30 s,
  max_seconds 6600 s. pid_alive(pid) -> bool. start_time(pid) -> float or None, for the reuse check. pid and ppid
  are the waiter's own. run_git(args, env, cache=None, timeout=..., input_text=None) -> (code, out, err): when
  given, every git call of the waiter goes through it.
- Exit codes: 0 new mail; 2 not started; 3 ended at max_seconds with no mail.
- Lock: <cache>/wait-<address with / as _>.lock, created O_EXCL, JSON {pid, ppid, session, started, deadline}.
  started is start_time(pid) at creation. A lock is stale when its pid is dead, its deadline has passed, or its
  started differs from start_time(pid); a stale lock is replaced. The waiter exits when its lock is gone or its
  ppid is dead. It removes its lock on every exit, SIGTERM included. wait() itself installs and restores its
  SIGTERM handler, so an in-process call gets the same handler the CLI gets.
- hooks/mail.py git(args, env, cache=None, timeout=TRANSFER_BOUND, input_text=None): a timeout kills the child and
  raises MailError("timeout"). Its Windows branch runs when mail.WINDOWS is True, read at call time, and that branch
  never calls communicate() after kill. Windows is unmeasured: on this Linux runner the cases drive that branch
  through subprocess._mswindows and a fake child.
- Writes. The waiter creates its lock. Its baseline fetch writes the cache once, as the mailbox fetch always does.
  During a poll nothing is written, and no listing-*.json file is ever written.
"""
import contextlib
import io
import json
from collections import Counter
import os
import re
import signal
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import test_mail  # noqa: E402  the mailbox suite's fixtures; only the helpers imported below are used
from test_mail import (MailCase, Starts, combined, fixture_env, git_subcommand, program_name,  # noqa: E402
                       run_cli, snapshot, turn)

mail_mod = test_mail.MAIL_MODULE
MAIL_CLI = test_mail.MAIL_CLI
ADDR = "cloud/session_b"  # the waiter's own address: its env holds cse_b
OTHER = "cloud/session_c"
SENDER = "cloud/session_a"
HOUR = 3600
FAR = 10 ** 9
SLEEP_CAP = 500  # a run that ignores its deadline ends here, not in a spin
PARENT_PID, WAITER_PID, SECOND_PID = 7000, 7001, 7002
DEAD_PID, REUSED_PID, OLD_PID = 6999, 6998, 6997
PROCESS_START, REUSED_START = 500.0, 250.0
SKILL_REL = os.path.join("skills", "waiting-page", "reference", "routing-and-sessions.md")
RECORD_REL = os.path.join("docs", "decisions", "session-messages.md")


class HourEnded(BaseException):
    """Ends a simulated run from inside the fake sleep. A BaseException, so an `except Exception` in the waiter
    does not take it."""


class FakeTime:
    """An injected clock and sleep. sleep(seconds) records the call, runs the hook (it may land mail, take a file,
    delete a lock or end the run), then moves the clock on. Inside the hook, len(sleeps) is this call's number,
    counted from 1, and the clock still reads the time the poll before it ran at."""

    def __init__(self, start=0.0, hook=None, end_at=None, on_end=None):
        self.now = float(start)
        self.hook, self.end_at, self.on_end = hook, end_at, on_end
        self.sleeps = []  # the seconds each sleep call asked for
        self.clocks = []  # the clock when each sleep call began

    def clock(self):
        return self.now

    def sleep(self, seconds):
        if len(self.sleeps) >= SLEEP_CAP:
            raise HourEnded()
        self.sleeps.append(seconds)
        self.clocks.append(self.now)
        if self.hook:
            self.hook(self)
        self.now += seconds
        if self.end_at is not None and self.now > self.end_at:
            if self.on_end:
                self.on_end(self)
            raise HourEnded()


class Procs:
    """The process table behind the waiter's injected checks: which pids are alive, and each one's start time."""

    def __init__(self):
        self.alive = {PARENT_PID, WAITER_PID, SECOND_PID, REUSED_PID, OLD_PID}
        self.starts = {REUSED_PID: REUSED_START}

    def pid_alive(self, pid):
        return pid in self.alive

    def start_time(self, pid):
        return self.starts.get(pid, PROCESS_START)


def wait_fn():
    """hooks/mail.py's wait. Until it lands, a stand-in that returns None and does nothing, so each case fails on
    its own outcome assert and never on a missing name (P3)."""
    return getattr(mail_mod, "wait", None) or no_build_wait


def no_build_wait(env, addrs, **kwargs):
    return None


def run_wait(env, fake, procs, pid=WAITER_PID, **extra):
    """One waiter of this session, in process. Returns (exit code, printed text). A SystemExit from a signal handler
    gives its exit code. A run that the fake clock ends returns the code "test-ended"."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = wait_fn()(env, [ADDR], clock=fake.clock, sleep=fake.sleep, pid_alive=procs.pid_alive,
                             start_time=procs.start_time, pid=pid, ppid=PARENT_PID, **extra)
        except SystemExit as exit_:
            code = exit_.code
        except HourEnded:
            code = "test-ended"
    return code, out.getvalue()


def lock_path(cache, addr=ADDR):
    return os.path.join(cache, "wait-%s.lock" % addr.replace("/", "_"))


def read_text(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def read_lock(path):
    try:
        return json.loads(read_text(path) or "null")
    except ValueError:
        return None


def write_lock(cache, pid, started, deadline, addr=ADDR):
    os.makedirs(cache, exist_ok=True)
    record = {"pid": pid, "ppid": PARENT_PID, "session": "cse_b", "started": started, "deadline": deadline}
    with open(lock_path(cache, addr), "w", encoding="utf-8") as handle:
        json.dump(record, handle)


def diff(before, after):
    added = sorted(path for path in after if path not in before)
    removed = sorted(path for path in before if path not in after)
    changed = sorted(path for path in before if path in after and before[path] != after[path])
    return added, removed, changed


def git_names(argv):
    return [git_subcommand(args) for args in argv if program_name(args) == "git"]


class WaitCase(MailCase):
    def fixture(self):
        """A store whose mail ref exists, so the baseline fetches, with one open message for another address, and
        the session's machine. Its env holds cse_b, so its address is ADDR."""
        store = self.store()
        store.seed(OTHER, "0a1b2c3d4e00", "inform", SENDER, "Body marker: elsewhere\n")
        return store, self.machine("b", store, session="cse_b")

    def assert_ended_quiet(self, code, text):
        self.assertEqual(code, 3, "mail wait exited %r, expected 3 (ended, no mail)" % (code,))
        self.assertIn("mail wait: ended, no mail", text, "the ended waiter printed no 'ended, no mail' line: %r" % text)


class WaitControls(WaitCase):
    def test_control_seeded_open_mail_is_listed_at_turn_start(self):
        store, machine = self.fixture()
        store.seed(ADDR, "0a1b2c3d4e01", "request", SENDER, "Body marker: control\n")
        listed = [line for line in turn(machine) if "0a1b2c3d4e01" in line]
        self.assertEqual(len(listed), 1, "control: the seeded message is not open at the session's address: %r" % listed)


class TwoWaiters(WaitCase):
    def test_second_waiter_exits_2_and_the_first_keeps_its_lock(self):
        store, machine = self.fixture()
        procs = Procs()
        lock = lock_path(machine.cache)
        probe = {}

        def second_waiter(fake):
            if len(fake.sleeps) != 2 or probe:
                return
            probe["lock_before"] = read_text(lock)
            later = FakeTime(end_at=0)  # a second waiter that polls is ended at its first sleep
            probe["code"], probe["text"] = run_wait(machine.env, later, procs, pid=SECOND_PID, max_seconds=90)
            probe["lock_after"] = read_text(lock)

        run_wait(machine.env, FakeTime(hook=second_waiter), procs, max_seconds=90)
        self.assertTrue(probe, "the first waiter never reached its second poll, so no second waiter ran")
        self.assertEqual(probe["code"], 2, "a second waiter for one session exited %r, expected 2 (not started)"
                         % (probe["code"],))
        self.assertIn("mail wait: not started: ", probe["text"],
                      "the second waiter printed no not-started line: %r" % probe["text"])
        self.assertEqual(probe["lock_after"], probe["lock_before"], "the second waiter changed the first waiter's lock")

    def stale_run(self, lock_pid, lock_started, lock_deadline, start=0.0):
        store, machine = self.fixture()
        write_lock(machine.cache, lock_pid, lock_started, lock_deadline)
        probe = {}

        def first_poll(fake):
            if len(fake.sleeps) == 1 and "holder" not in probe:
                probe["holder"] = (read_lock(lock_path(machine.cache)) or {}).get("pid")

        code, text = run_wait(machine.env, FakeTime(start=start, hook=first_poll), Procs(), max_seconds=90)
        return code, text, probe

    def test_stale_lock_with_a_dead_pid_is_replaced_and_the_waiter_runs(self):
        code, text, probe = self.stale_run(DEAD_PID, PROCESS_START, FAR)
        self.assertIn("holder", probe, "the waiter never polled with the dead pid's lock on disk: it did not start")
        self.assertEqual(probe["holder"], WAITER_PID,
                         "a lock whose pid is dead was not replaced: it still names pid %r" % (probe["holder"],))
        self.assert_ended_quiet(code, text)

    def test_stale_lock_past_its_deadline_is_replaced_and_the_waiter_runs(self):
        code, text, probe = self.stale_run(OLD_PID, PROCESS_START, 900.0, start=1000.0)
        self.assertIn("holder", probe, "the waiter never polled with the expired lock on disk: it did not start")
        self.assertEqual(probe["holder"], WAITER_PID,
                         "a lock past its deadline was not replaced: it still names pid %r" % (probe["holder"],))
        self.assert_ended_quiet(code, text)

    def test_stale_lock_whose_pid_was_reused_is_replaced_and_the_waiter_runs(self):
        code, text, probe = self.stale_run(REUSED_PID, 100.0, FAR)
        self.assertIn("holder", probe, "the waiter never polled with the reused pid's lock on disk: it did not start")
        self.assertEqual(probe["holder"], WAITER_PID,
                         "a lock whose start time differs from its pid's was not replaced: it still names pid %r"
                         % (probe["holder"],))
        self.assert_ended_quiet(code, text)


class Wake(WaitCase):
    def wake_run(self):
        store, machine = self.fixture()
        store.seed(ADDR, "0a1b2c3d4e20", "request", SENDER, "Body marker: already open\n")
        probe = {}

        def land(fake):
            if len(fake.sleeps) == 2:  # after the poll at 30 s, before the next sleep
                store.seed(ADDR, "0a1b2c3d4e21", "request", SENDER, "Body marker: wake-new\n")
                probe["sent_at"] = fake.now

        fake = FakeTime(hook=land)
        code, text = run_wait(machine.env, fake, Procs(), max_seconds=600)
        probe["woke_at"] = fake.now
        return code, text, probe

    def test_mail_landing_for_the_address_wakes_within_one_interval(self):
        code, _, probe = self.wake_run()
        self.assertIn("sent_at", probe, "the send never landed: the waiter did not reach its second sleep")
        self.assertEqual(code, 0, "new mail for the session's address made mail wait exit %r, expected 0" % (code,))
        self.assertLessEqual(probe["woke_at"] - probe["sent_at"], 30,
                             "mail wait woke %s s after the send, over one 30 s interval"
                             % (probe["woke_at"] - probe["sent_at"]))

    def test_wake_line_names_the_new_id_sender_kind_and_first_body_line(self):
        _, text, probe = self.wake_run()
        self.assertIn("sent_at", probe, "the send never landed: the waiter did not reach its second sleep")
        self.assertEqual(text.splitlines(), ["mail: new 0a1b2c3d4e21 from cloud/session_a kind request: Body marker: wake-new"],
                         "mail wait printed the wrong wake line (the open id 0a1b2c3d4e20 is not new)")


class FalseWake(WaitCase):
    def run_with_event(self, store, machine, event):
        """A waiter with no new mail for its address. At its second sleep, event() runs once. Returns (code, text,
        probe, fake)."""
        probe = {}

        def at_second_sleep(fake):
            if len(fake.sleeps) == 2:
                probe["ran"] = True
                before = store.tip()
                probe["result"] = event()
                probe["moved"] = store.tip() != before

        fake = FakeTime(hook=at_second_sleep)
        code, text = run_wait(machine.env, fake, Procs(), max_seconds=120)
        return code, text, probe, fake

    def test_send_to_another_address_moves_the_tip_and_does_not_wake(self):
        store, machine = self.fixture()

        def send_elsewhere():
            store.seed(OTHER, "0a1b2c3d4e30", "request", SENDER, "Body marker: elsewhere-2\n")

        code, text, probe, _ = self.run_with_event(store, machine, send_elsewhere)
        self.assertTrue(probe.get("ran"), "the waiter never reached its second sleep, so no send to another address ran")
        self.assertTrue(probe["moved"], "control: the send to another address did not move the mail ref")
        self.assert_ended_quiet(code, text)

    def test_take_of_another_address_moves_the_tip_and_does_not_wake(self):
        store, machine = self.fixture()
        taker = self.machine("c", store, session="cse_c")

        def take_elsewhere():
            return run_cli(taker, "take", "--addr", OTHER, "0a1b2c3d4e00").returncode

        code, text, probe, _ = self.run_with_event(store, machine, take_elsewhere)
        self.assertTrue(probe.get("ran"), "the waiter never reached its second sleep, so no take ran")
        self.assertEqual(probe["result"], 0, "control: the take of another address's message exited %r, expected 0"
                         % (probe["result"],))
        self.assertTrue(probe["moved"], "control: the take did not move the mail ref")
        self.assert_ended_quiet(code, text)

    def test_own_send_moves_the_tip_and_does_not_wake(self):
        store, machine = self.fixture()

        def send_own():
            return run_cli(machine, "send", "--to", OTHER, "--kind", "inform",
                           "--body-file", self.body("own-send")).returncode

        code, text, probe, _ = self.run_with_event(store, machine, send_own)
        self.assertTrue(probe.get("ran"), "the waiter never reached its second sleep, so the session's send never ran")
        self.assertEqual(probe["result"], 0, "control: the session's own send exited %r, expected 0" % (probe["result"],))
        self.assertTrue(probe["moved"], "control: the session's own send did not move the mail ref")
        self.assert_ended_quiet(code, text)

    def test_mail_already_open_at_start_does_not_wake(self):
        store, machine = self.fixture()
        store.seed(ADDR, "0a1b2c3d4e32", "request", SENDER, "Body marker: open-at-start\n")
        fake = FakeTime()
        code, text = run_wait(machine.env, fake, Procs(), max_seconds=120)
        self.assertGreaterEqual(len(fake.sleeps), 1,
                                "the waiter never polled, so it did not get past the mail open at its start")
        self.assertNotIn("mail: new ", text, "mail open at the start woke the waiter: %r" % text)
        self.assert_ended_quiet(code, text)

    def test_transient_ls_remote_failure_keeps_polling(self):
        store, machine = self.fixture()
        probe = {"failed_at": None}
        fake = FakeTime()

        def flaky_git(args, env, cache=None, timeout=mail_mod.TRANSFER_BOUND, input_text=None):
            if "ls-remote" in args and fake.now >= 60 and probe["failed_at"] is None:
                probe["failed_at"] = fake.now
                return 128, "", "fatal: unable to access 'store': Could not resolve host: store"
            return mail_mod.git(args, env, cache, timeout, input_text)

        code, text = run_wait(machine.env, fake, Procs(), run_git=flaky_git, max_seconds=180)
        self.assertIsNotNone(probe["failed_at"],
                             "the transient ls-remote failure was never injected: no poll ran at 60 s or later")
        self.assertTrue([c for c in fake.clocks if c > probe["failed_at"]],
                        "the waiter stopped after one transient poll failure instead of polling again")
        self.assert_ended_quiet(code, text)


class Windows(MailCase):
    """A git child that outlives its bound can hold its pipes open through a grandchild (ssh). On Windows,
    subprocess.run then calls communicate() after kill, and that call blocks. These cases run a timed-out git call
    through CPython's own run() with a fake child that never blocks: each call is recorded, so the call after kill is
    the one that would block. Windows is unmeasured. On this Linux run only the branch is driven, by injection."""

    def timed_out_git(self, windows):
        made = []

        def factory(args, *rest, **kwargs):
            child = FakeChild(args, *rest, **kwargs)
            made.append(child)
            return child

        error = None
        with mock.patch.object(subprocess, "Popen", factory), \
                mock.patch.object(subprocess, "_mswindows", windows), \
                mock.patch.object(mail_mod, "WINDOWS", windows, create=True):
            try:
                mail_mod.git(["ls-remote", "file:///nowhere", mail_mod.REF], fixture_env(self.case), timeout=3)
            except mail_mod.MailError as caught:
                error = caught
        return error, made

    def test_timed_out_git_on_windows_never_calls_communicate_after_kill(self):
        error, made = self.timed_out_git(windows=True)
        self.assertEqual(len(made), 1, "control: the helper started no child, so the timeout path never ran")
        events = made[0].events
        self.assertIn(("kill", None), events, "control: the timed-out child was never killed")
        after_kill = [name for name, _ in events[events.index(("kill", None)) + 1:]]
        self.assertNotIn("communicate", after_kill,
                         "after kill the helper called communicate() again: on Windows that call blocks while a "
                         "grandchild holds the pipes")
        self.assertEqual(str(error), "timeout", "the timed-out git call raised %r, expected MailError('timeout')" % (error,))

    def test_control_timed_out_git_on_posix_returns_timeout_without_communicate_after_kill(self):
        error, made = self.timed_out_git(windows=False)
        self.assertEqual(len(made), 1, "control: the helper started no child, so the timeout path never ran")
        events = made[0].events
        self.assertIn(("kill", None), events, "control: the timed-out child was never killed")
        after_kill = [name for name, _ in events[events.index(("kill", None)) + 1:]]
        self.assertNotIn("communicate", after_kill, "control: the POSIX path called communicate() after kill")
        self.assertEqual(str(error), "timeout", "control: the POSIX timeout raised %r, expected MailError('timeout')"
                         % (error,))


class FakeChild:
    """A git child that outlives its bound. Its first communicate() raises TimeoutExpired, as a bound does. Every later
    call is recorded and returns at once, so a helper that calls it again cannot hang this run. Its pipes are closable
    buffers, so the Windows-safe fix (kill, close the pipes, wait with a bound) runs against it too."""

    def __init__(self, args, *rest, **kwargs):
        self.args = args
        self.pid = 0
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO()
        self.stderr = io.BytesIO()
        self.returncode = None
        self.events = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def communicate(self, input=None, timeout=None):
        self.events.append(("communicate", timeout))
        if timeout is not None:
            raise subprocess.TimeoutExpired(self.args, timeout)
        return b"", b""

    def poll(self):
        return self.returncode

    def kill(self):
        self.events.append(("kill", None))
        self.returncode = -9

    def terminate(self):
        self.events.append(("terminate", None))

    def wait(self, timeout=None):
        self.events.append(("wait", timeout))
        return self.returncode


class Cleanup(WaitCase):
    def test_waiter_stops_when_its_lock_is_deleted(self):
        store, machine = self.fixture()
        lock = lock_path(machine.cache)
        probe = {}

        def delete_lock(fake):
            if len(fake.sleeps) == 2:
                probe["at"] = len(fake.sleeps)
                probe["removed"] = os.path.exists(lock)
                if probe["removed"]:
                    os.remove(lock)

        fake = FakeTime(hook=delete_lock)
        run_wait(machine.env, fake, Procs(), max_seconds=600)
        self.assertIn("at", probe, "the waiter never reached its second sleep, so its lock was never deleted under it")
        self.assertTrue(probe["removed"], "the waiter held no lock file to delete")
        after = len(fake.sleeps) - probe["at"]
        self.assertLessEqual(after, 1, "the waiter polled %d more times after its lock was deleted" % after)

    def parent_death_run(self):
        store, machine = self.fixture()
        procs = Procs()
        lock = lock_path(machine.cache)
        probe = {}

        def parent_dies(fake):
            if len(fake.sleeps) == 2:
                probe["at"] = len(fake.sleeps)
                procs.alive.discard(PARENT_PID)

        fake = FakeTime(hook=parent_dies)
        run_wait(machine.env, fake, procs, max_seconds=600)
        return probe, fake, os.path.exists(lock)

    def test_waiter_stops_when_its_parent_pid_dies(self):
        probe, fake, _ = self.parent_death_run()
        self.assertIn("at", probe, "the waiter never reached its second sleep, so its parent never died under it")
        after = len(fake.sleeps) - probe["at"]
        self.assertLessEqual(after, 1, "the waiter polled %d more times after its parent died" % after)

    def test_waiter_removes_its_lock_when_its_parent_dies(self):
        probe, _, lock_exists = self.parent_death_run()
        self.assertIn("at", probe, "the waiter never reached its second sleep, so its parent never died under it")
        self.assertFalse(lock_exists, "the waiter left its lock behind when its parent pid died")

    def test_lock_is_removed_when_the_waiter_exits_on_new_mail(self):
        store, machine = self.fixture()
        lock = lock_path(machine.cache)

        def send_to_session(fake):
            if len(fake.sleeps) == 2:
                store.seed(ADDR, "0a1b2c3d4e40", "request", SENDER, "Body marker: exit-mail\n")

        code, _ = run_wait(machine.env, FakeTime(hook=send_to_session), Procs(), max_seconds=600)
        self.assertEqual(code, 0, "new mail made mail wait exit %r, expected 0" % (code,))
        self.assertFalse(os.path.exists(lock), "the waiter left its lock behind after it woke on mail")

    def test_lock_is_removed_when_the_waiter_reaches_max_seconds(self):
        store, machine = self.fixture()
        lock = lock_path(machine.cache)
        code, text = run_wait(machine.env, FakeTime(), Procs(), max_seconds=90)
        self.assert_ended_quiet(code, text)
        self.assertFalse(os.path.exists(lock), "the waiter left its lock behind at max_seconds")

    def test_sigterm_removes_the_lock_and_stops_polling(self):
        store, machine = self.fixture()
        lock = lock_path(machine.cache)
        probe = {}

        def terminate(fake):
            if len(fake.sleeps) != 2:
                return
            probe["at"] = len(fake.sleeps)
            handler = signal.getsignal(signal.SIGTERM)
            probe["handler_installed"] = callable(handler)
            if callable(handler):
                handler(signal.SIGTERM, None)  # a handler may end the run with SystemExit; run_wait takes that

        previous = signal.getsignal(signal.SIGTERM)
        try:
            fake = FakeTime(hook=terminate)
            run_wait(machine.env, fake, Procs(), max_seconds=600)
        finally:
            if previous is not None:
                signal.signal(signal.SIGTERM, previous)
        self.assertIn("at", probe, "the waiter never reached its second sleep, so no SIGTERM was sent")
        self.assertTrue(probe["handler_installed"],
                        "the waiter installed no SIGTERM handler, so a terminate leaves its lock behind")
        self.assertFalse(os.path.exists(lock), "SIGTERM left the lock file behind")
        after = len(fake.sleeps) - probe["at"]
        self.assertLessEqual(after, 1, "the waiter polled %d more times after SIGTERM" % after)


class Cost(WaitCase):
    def measure_hour(self, move_at=None):
        """One simulated hour at the default interval. The first hook marks the end of the baseline, so the baseline's
        starts are not counted as polls. With move_at, another address gets mail at that sleep (the sha moves). The
        seed's own git starts are cut from the count: they are the case's writes, not the waiter's. Files written are
        the lock the waiter creates at its start, plus any change inside the hour."""
        store, machine = self.fixture()
        procs = Procs()
        cache = machine.cache
        marks, snaps = [], {}
        before = snapshot(cache)
        with Starts() as starts:
            def count(fake):
                if len(marks) + 1 == move_at:
                    cut = len(starts.argv)
                    store.seed(OTHER, "0a1b2c3d4e50", "inform", SENDER, "Body marker: moved\n")
                    del starts.argv[cut:]
                marks.append(len(starts.argv))
                if len(marks) == 1:
                    snaps["first"] = snapshot(cache)

            def end(fake):
                snaps["end"] = snapshot(cache)

            fake = FakeTime(hook=count, end_at=HOUR, on_end=end)
            code, _ = run_wait(machine.env, fake, procs)
        argv = starts.argv
        window = argv[marks[0]:marks[-1]] if marks else []
        polls = [args for args in window if program_name(args) == "git" and git_subcommand(args) == "ls-remote"]
        added_at_start = diff(before, snaps["first"])[0] if "first" in snaps else []
        hour = diff(snaps["first"], snaps["end"]) if "end" in snaps else ([], [], [])
        return {
            "code": code,
            "window": window,
            "polls": polls,
            "fetches": [args for args in argv if program_name(args) == "git" and git_subcommand(args) == "fetch"],
            "non_git": [args for args in argv if program_name(args) != "git"],
            "sleeps": set(fake.sleeps),
            "hour": hour,
            "locks": [path for path in added_at_start if path.endswith(".lock")],
            "listings": [path for path in snapshot(cache) if os.path.basename(path).startswith("listing-")],
        }

    def test_an_hour_at_the_default_interval_polls_120_times_and_writes_nothing(self):
        m = self.measure_hour()
        self.assertTrue(m["polls"], "control: the waiter made no ls-remote poll in the simulated hour")
        self.assertEqual(len(m["polls"]), 120, "an hour at the default interval made %d ls-remote polls, expected 120"
                         % len(m["polls"]))
        counted = dict(Counter(git_names(m["window"])))
        self.assertEqual(counted, {"ls-remote": 120}, "the polls of an unchanged hour ran git %r, expected only 120 "
                         "ls-remote" % counted)
        self.assertEqual(len(m["fetches"]), 1, "the waiter ran %d fetches, expected 1 (the baseline)" % len(m["fetches"]))
        self.assertEqual(m["sleeps"], {30}, "the waiter slept %r between polls, expected 30 s" % sorted(m["sleeps"]))
        self.assertEqual(m["non_git"], [], "the waiter started %d processes that are not git: a second long-lived process"
                         % len(m["non_git"]))
        self.assertEqual(m["hour"], ([], [], []), "the waiter changed files during the hour: added, removed, changed %r"
                         % (m["hour"],))
        self.assertEqual(len(m["locks"]), 1, "the waiter created %d lock files, expected 1" % len(m["locks"]))
        self.assertEqual(m["listings"], [], "the waiter wrote a listing file, which the wait never writes")

    def test_one_moved_sha_adds_exactly_one_fetch_and_one_grep(self):
        m = self.measure_hour(move_at=60)
        self.assertTrue(m["polls"], "control: the waiter made no ls-remote poll in the simulated hour")
        counted = dict(Counter(git_names(m["window"])))
        self.assertEqual(counted, {"ls-remote": 120, "fetch": 1, "grep": 1},
                         "an hour with one moved sha ran git %r, expected 120 ls-remote, 1 fetch and 1 grep" % counted)
        self.assertEqual(len(m["fetches"]), 2, "the hour ran %d fetches in all, expected 2 (the baseline and the move)"
                         % len(m["fetches"]))
        self.assertEqual(m["code"], "test-ended", "mail for another address ended the waiter with exit %r, expected it "
                         "to keep waiting" % (m["code"],))

    def test_the_decision_states_the_measured_doorbell_cost(self):
        text = read_text(os.path.join(REPO, RECORD_REL)) or ""
        found = re.search(r"Doorbell cost: processes (\d+); interval (\d+) s; reads per hour (\d+); files written (\d+)",
                          text)
        self.assertIsNotNone(found, "%s has no 'Doorbell cost:' line, so the doorbell's cost is not written down"
                             % RECORD_REL)
        m = self.measure_hour()
        processes, interval, reads, files = (int(value) for value in found.groups())
        self.assertEqual(processes, 1 + len(m["non_git"]), "the record says processes %d, the stand-in counted %d"
                         % (processes, 1 + len(m["non_git"])))
        measured_interval = next(iter(m["sleeps"])) if len(m["sleeps"]) == 1 else None
        self.assertEqual(interval, measured_interval, "the record says interval %d s, the stand-in slept %r"
                         % (interval, sorted(m["sleeps"])))
        self.assertEqual(reads, len(m["polls"]), "the record says reads per hour %d, the stand-in made %d polls"
                         % (reads, len(m["polls"])))
        written = len(m["locks"]) + sum(len(group) for group in m["hour"])
        self.assertEqual(files, written, "the record says files written %d, the stand-in wrote %d" % (files, written))


class FastExit(WaitCase):
    def unset_env(self, machine):
        env = dict(machine.env)
        env.pop("MAILBOX_REPO")
        return env

    def test_unset_mailbox_repo_exits_2_at_once_on_every_start(self):
        store, machine = self.fixture()
        results = []
        for _ in range(5):
            fake = FakeTime()
            with Starts() as starts:
                code, text = run_wait(self.unset_env(machine), fake, Procs(), max_seconds=600)
            results.append((code, text, fake.sleeps, starts.git_starts()))
        self.assertEqual([r[0] for r in results], [2] * 5, "starts with MAILBOX_REPO unset exited %r, expected 2 each"
                         % [r[0] for r in results])
        self.assertTrue(all("mail wait: not started: " in r[1] for r in results),
                        "a start with MAILBOX_REPO unset printed no not-started line: %r" % [r[1] for r in results])
        self.assertEqual([len(r[2]) for r in results], [0] * 5, "a start with MAILBOX_REPO unset slept")
        self.assertEqual([len(r[3]) for r in results], [0] * 5, "a start with MAILBOX_REPO unset ran git")

    def test_held_lock_exits_2_at_once_on_every_start_and_keeps_the_holder(self):
        store, machine = self.fixture()
        procs = Procs()
        write_lock(machine.cache, WAITER_PID, PROCESS_START, FAR)
        results = []
        for _ in range(5):
            fake = FakeTime()
            with Starts() as starts:
                code, text = run_wait(machine.env, fake, procs, pid=SECOND_PID, max_seconds=600)
            results.append((code, text, fake.sleeps, starts.git_starts()))
        self.assertEqual([r[0] for r in results], [2] * 5, "starts under a held lock exited %r, expected 2 each"
                         % [r[0] for r in results])
        self.assertTrue(all("mail wait: not started: " in r[1] for r in results),
                        "a start under a held lock printed no not-started line: %r" % [r[1] for r in results])
        self.assertEqual([len(r[2]) for r in results], [0] * 5, "a start under a held lock slept")
        self.assertEqual([len(r[3]) for r in results], [0] * 5, "a start under a held lock ran git")
        holder = (read_lock(lock_path(machine.cache)) or {}).get("pid")
        self.assertEqual(holder, WAITER_PID, "a refused start changed the holder's lock: it now names pid %r" % (holder,))

    def test_cli_without_mailbox_repo_prints_the_not_started_line_and_exits_2(self):
        store, machine = self.fixture()
        raw = subprocess.run([sys.executable, MAIL_CLI, "wait"], env=self.unset_env(machine), cwd=machine.checkout,
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        self.assertEqual(raw.returncode, 2, "mail wait without MAILBOX_REPO exited %d: %s"
                         % (raw.returncode, combined(raw)))
        self.assertIn("mail wait: not started: ", combined(raw),
                      "mail wait without MAILBOX_REPO printed no not-started line: %r" % combined(raw))

    def test_cli_without_an_address_prints_the_not_started_line_and_exits_2(self):
        store = self.store()
        machine = self.machine("n", store)  # no session id and no origin: the session has no address
        raw = run_cli(machine, "wait")
        self.assertEqual(raw.returncode, 2, "mail wait without an address exited %d: %s" % (raw.returncode, combined(raw)))
        self.assertIn("mail wait: not started: ", combined(raw),
                      "mail wait without an address printed no not-started line: %r" % combined(raw))


class SkillReads(unittest.TestCase):
    def skill_sentences(self):
        text = read_text(os.path.join(REPO, SKILL_REL)) or ""
        return re.split(r"(?<=[.!?])\s+|\n+", text)

    def test_skill_says_a_session_does_not_restart_after_exit_2(self):
        hits = [s for s in self.skill_sentences()
                if re.search(r"\bexit 2\b", s) and re.search(r"\bwait\b", s) and re.search(r"\brestart", s)
                and re.search(r"\b(not|never)\b", s)]
        self.assertTrue(hits, "%s has no sentence that says a session does not restart after mail wait exits 2" % SKILL_REL)

    def test_skill_says_a_session_restarts_at_most_once_after_exit_3(self):
        hits = [s for s in self.skill_sentences()
                if re.search(r"\bexit 3\b", s) and re.search(r"\bwait\b", s) and re.search(r"\brestart", s)
                and re.search(r"at most once", s)]
        self.assertTrue(hits, "%s has no sentence that says a session restarts at most once after mail wait exits 3"
                        % SKILL_REL)


class Deadline(WaitCase):
    def test_exits_3_at_max_seconds_on_the_injected_clock(self):
        store, machine = self.fixture()
        fake = FakeTime()
        code, text = run_wait(machine.env, fake, Procs(), max_seconds=300)
        self.assert_ended_quiet(code, text)
        self.assertTrue(300 <= fake.now <= 330, "the waiter ended at %s s, expected 300 to 330 (max_seconds 300 and one "
                        "interval)" % fake.now)

    def test_default_max_ends_before_the_two_hour_background_cap(self):
        store, machine = self.fixture()
        fake = FakeTime()
        code, text = run_wait(machine.env, fake, Procs())
        self.assert_ended_quiet(code, text)
        self.assertLess(fake.now, 7200, "the default max ends the waiter at %s s, past the 2 h background cap" % fake.now)
        self.assertGreaterEqual(fake.now, 6600, "the default max ended the waiter at %s s, expected 6600 s" % fake.now)


if __name__ == "__main__":
    unittest.main()
