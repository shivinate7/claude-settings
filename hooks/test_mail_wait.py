#!/usr/bin/env python3
"""Cases for `mail wait`: one background command that blocks until the session's own mailbox address has a new
open message, then prints one wake line per new message and exits 0 (decision session-messages, "One route" and "Design").

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
  given, every git call of the waiter goes through it. Default: git_bounded.
- Exit codes: 0 new mail; 2 not started; 3 ended at max_seconds with no mail.
- Lock: <cache>/wait-<address with / as _>.lock, created O_EXCL, JSON {pid, ppid, session, started, deadline}.
  started is start_time(pid) at creation. A lock is stale when its pid is dead, its deadline has passed, or its
  started differs from start_time(pid); a stale lock is replaced. The waiter exits when its lock is gone or its
  ppid is dead. It removes its lock on every exit, SIGTERM included. wait() itself installs and restores its
  SIGTERM handler, so an in-process call gets the same handler the CLI gets.
- hooks/mail.py git(args, env, cache=None, timeout=TRANSFER_BOUND, input_text=None) keeps main's route on every
  platform: its child starts through _nowindow.run. git_bounded takes the same arguments and raises
  MailError("timeout") on a timeout. Its Windows branch runs when mail.WINDOWS is True, read at call time, and that
  branch never calls communicate() after kill. wait() takes git_bounded as its default run_git. Windows is unmeasured:
  on this Linux runner the cases drive that branch through subprocess._mswindows and a fake child.
- Wake subject. The subject is the first non-blank line after the header block, whether the message's lines end in LF
  or CRLF. The wake line holds no CR.
- Writes. The waiter creates its lock. Its baseline fetch writes the cache once, as the mailbox fetch always does.
  During a poll nothing is written, and no listing-*.json file is ever written.
"""
import contextlib
import io
import json
import os
import re
import signal
import subprocess
import sys
import threading
import unittest
from collections import Counter
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import test_mail  # noqa: E402  the mailbox suite's fixtures; only the helpers imported below are used
from test_mail import (MailCase, PC_BASE, Starts, cli_module, combined, fixture_env, git_subcommand,  # noqa: E402
                       in_folder, program_name, run_cli, snapshot, turn)

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
FAKE_PID = 4242  # the fake git child's pid: a tree kill names it
FAILED_GIT = (128, "", "fatal: unable to access 'store': Could not resolve host: store")  # one transient git failure
SKILL_REL =os.path.join("skills", "waiting-page", "reference", "routing-and-sessions.md")
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


def run_wait(env, fake, procs, pid=WAITER_PID, addrs=None, **extra):
    """One waiter of this session, in process. Returns (exit code, printed text). A SystemExit from a signal handler
    gives its exit code. A run that the fake clock ends returns the code "test-ended"."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = wait_fn()(env, addrs or [ADDR], clock=fake.clock, sleep=fake.sleep, pid_alive=procs.pid_alive,
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


def named_route(case, name, cause):
    """The mail.py function `name`. A missing name fails the case by assert that names the cause, never by a crash (P3)."""
    route = getattr(mail_mod, name, None)
    if route is None:
        case.fail("mail.%s is missing: %s" % (name, cause))
    return route


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
        self.assertEqual(text.splitlines(), [
            'mail: new 0a1b2c3d4e21 from cloud/session_a kind request; untrusted subject "Body marker: wake-new"; '
            'read: `mail read --addr cloud/session_b 0a1b2c3d4e21`; take: `mail take --addr cloud/session_b 0a1b2c3d4e21`'],
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

    def test_mail_open_at_start_for_this_address_does_not_wake_when_another_address_moves_the_tip(self):
        store, machine = self.fixture()
        store.seed(ADDR, "0a1b2c3d4e33", "request", SENDER, "Body marker: open-before-move\n")

        def send_elsewhere():
            store.seed(OTHER, "0a1b2c3d4e34", "request", SENDER, "Body marker: elsewhere-3\n")

        code, text, probe, _ = self.run_with_event(store, machine, send_elsewhere)
        self.assertTrue(probe.get("ran"), "the waiter never reached its second sleep, so the send to another address never ran")
        self.assertTrue(probe["moved"], "control: the send to another address did not move the mail ref")
        self.assertNotIn("mail: new ", text, "mail open at the start for this address woke the waiter when another "
                         "address moved the tip: %r" % text)
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

    def timed_out_git(self, windows, name="git"):
        """Runs the named git route (mail.git_bounded for the Windows cases) on a child whose first communicate() times
        out. Returns (the MailError raised or None, the fake children, the taskkill argvs run through the seam). The seam
        is _nowindow.run, the one home of a no-window child start: the Windows tree kill goes through it, and the recorder
        answers it without a process start. Only the Windows case patches it, since the POSIX path runs its git through
        the same function."""
        route = named_route(self, name, "the Windows timeout is not scoped to the wait")
        made, taskkills = [], []

        def factory(args, *rest, **kwargs):
            child = FakeChild(args, *rest, **kwargs)
            made.append(child)
            return child

        def recorder(argv, *rest, **kwargs):
            taskkills.append(list(argv))
            if made:
                made[-1].events.append(("taskkill", None))
            return subprocess.CompletedProcess(argv, 0)

        seam = mock.patch.object(mail_mod._nowindow, "run", recorder) if windows else contextlib.nullcontext()
        error = None
        with mock.patch.object(subprocess, "Popen", factory), \
                mock.patch.object(subprocess, "_mswindows", windows), \
                mock.patch.object(mail_mod, "WINDOWS", windows, create=True), seam:
            try:
                route(["ls-remote", "file:///nowhere", mail_mod.REF], fixture_env(self.case), timeout=3)
            except mail_mod.MailError as caught:
                error = caught
        return error, made, taskkills

    def test_timed_out_git_on_windows_never_calls_communicate_after_kill(self):
        error, made, _ = self.timed_out_git(windows=True, name="git_bounded")
        self.assertEqual(len(made), 1, "control: the helper started no child, so the timeout path never ran")
        events = made[0].events
        self.assertIn(("kill", None), events, "control: the timed-out child was never killed")
        after_kill = [name for name, _ in events[events.index(("kill", None)) + 1:]]
        self.assertNotIn("communicate", after_kill,
                         "after kill the helper called communicate() again: on Windows that call blocks while a "
                         "grandchild holds the pipes")
        self.assertEqual(str(error), "timeout", "the timed-out git call raised %r, expected MailError('timeout')" % (error,))

    def test_control_timed_out_git_on_posix_returns_timeout_without_communicate_after_kill(self):
        error, made, _ = self.timed_out_git(windows=False)
        self.assertEqual(len(made), 1, "control: the helper started no child, so the timeout path never ran")
        events = made[0].events
        self.assertIn(("kill", None), events, "control: the timed-out child was never killed")
        after_kill = [name for name, _ in events[events.index(("kill", None)) + 1:]]
        self.assertNotIn("communicate", after_kill, "control: the POSIX path called communicate() after kill")
        self.assertEqual(str(error), "timeout", "control: the POSIX timeout raised %r, expected MailError('timeout')"
                         % (error,))

    def test_timed_out_git_on_windows_kills_the_child_tree_before_a_bounded_wait(self):
        error, made, taskkills = self.timed_out_git(windows=True, name="git_bounded")
        self.assertEqual(len(made), 1, "control: the helper started no child, so the timeout path never ran")
        self.assertEqual(taskkills, [["taskkill", "/F", "/T", "/PID", str(FAKE_PID)]],
                         "the timed-out Windows child's tree was not killed with taskkill /F /T /PID through the seam: %r"
                         % taskkills)
        names = [name for name, _ in made[0].events]
        self.assertIn("taskkill", names, "control: the tree kill is missing from the child's events")
        waits = [timeout for name, timeout in made[0].events[names.index("taskkill") + 1:] if name == "wait"]
        self.assertTrue(waits and waits[-1] is not None,
                        "after the tree kill the helper did not wait on the child with a bound: %r" % waits)

    def test_timed_out_git_on_windows_never_closes_the_child_pipes(self):
        error, made, _ = self.timed_out_git(windows=True, name="git_bounded")
        self.assertEqual(len(made), 1, "control: the helper started no child, so the timeout path never ran")
        closed = [name for name in ("stdin", "stdout", "stderr") if getattr(made[0], name).closed]
        self.assertEqual(closed, [], "the helper closed the timed-out child's pipes: %r" % closed)


class Routes(MailCase):
    """The two git routes stay apart. mail.git keeps main's route on every platform, so the send path and the turn-start
    read are unchanged: its child starts through _nowindow.run, the seam SshBatchDefault patches. The Windows-safe
    timeout lives in mail.git_bounded alone, so its child starts through Popen on Windows, and the seam sees only a
    tree kill after a timeout."""

    def run_recorded(self, route, timeout=3):
        """Calls the route with Windows on, a child that never blocks, and _nowindow.run recorded. Returns (argvs run
        through the seam, argvs started through Popen)."""
        runs, starts = [], []

        def recorder(argv, *rest, **kwargs):
            runs.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, "", "")

        def factory(args, *rest, **kwargs):
            starts.append(list(args))
            return FakeChild(args, *rest, **kwargs)

        with mock.patch.object(subprocess, "Popen", factory), \
                mock.patch.object(mail_mod, "WINDOWS", True, create=True), \
                mock.patch.object(mail_mod._nowindow, "run", recorder):
            try:
                route(["ls-remote", "file:///nowhere", mail_mod.REF], fixture_env(self.case), timeout=timeout)
            except mail_mod.MailError:
                pass  # the fake child times out: the case reads what was started, not the result
        return runs, starts

    def test_on_windows_git_still_starts_its_child_through_the_seam_as_on_main(self):
        route = named_route(self, "git", "the send path and the turn-start read no longer take main's route")
        runs, starts = self.run_recorded(route)
        self.assertTrue([argv for argv in runs if program_name(argv) == "git"],
                        "mail.git with WINDOWS True did not start its git child through _nowindow.run, as on main: "
                        "the seam saw %r, and Popen started %r" % (runs, starts))

    def test_on_windows_git_bounded_starts_its_child_through_popen_not_the_seam(self):
        route = named_route(self, "git_bounded", "the Windows timeout is not scoped to the wait")

        class DoneChild(FakeChild):
            def communicate(self, input=None, timeout=None):
                self.events.append(("communicate", timeout))
                self.returncode = 0
                return b"ok\n", b""

        runs, starts = [], []

        def recorder(argv, *rest, **kwargs):
            runs.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, "", "")

        def factory(args, *rest, **kwargs):
            starts.append(list(args))
            return DoneChild(args, *rest, **kwargs)

        with mock.patch.object(subprocess, "Popen", factory), \
                mock.patch.object(mail_mod, "WINDOWS", True, create=True), \
                mock.patch.object(mail_mod._nowindow, "run", recorder):
            route(["ls-remote", "file:///nowhere", mail_mod.REF], fixture_env(self.case), timeout=3)
        self.assertEqual([argv for argv in runs if program_name(argv) == "git"], [],
                         "mail.git_bounded on Windows ran its git child through _nowindow.run: %r" % runs)
        self.assertTrue([argv for argv in starts if program_name(argv) == "git"],
                        "mail.git_bounded on Windows started no git child through Popen: %r" % starts)


class DefaultRoute(WaitCase):
    def test_wait_without_run_git_takes_its_git_calls_from_git_bounded(self):
        """With no run_git injected, wait() routes its git calls through git_bounded, the Windows-safe route. The spy keeps
        the real route, so the waiter runs as it would. The waiter ends at its first sleep, so its baseline ls-remote is
        the call under test."""
        route = named_route(self, "git_bounded", "wait() has no git_bounded route to take by default")
        store, machine = self.fixture()
        calls = []

        def spy(args, *rest, **kwargs):
            calls.append(list(args))
            return route(args, *rest, **kwargs)

        with mock.patch.object(mail_mod, "git_bounded", spy):
            run_wait(machine.env, FakeTime(end_at=0), Procs())
        self.assertTrue(any(args[:1] == ["ls-remote"] for args in calls),
                        "wait() with no run_git made no ls-remote through git_bounded: %r" % calls)


class FakeChild:
    """A git child that outlives its bound. Its first communicate() raises TimeoutExpired, as a bound does. Every later
    call is recorded and returns at once, so a helper that calls it again cannot hang this run. Its pipes are closable
    buffers, so the Windows-safe fix (kill, close the pipes, wait with a bound) runs against it too."""

    def __init__(self, args, *rest, **kwargs):
        self.args = args
        self.pid = FAKE_PID
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


class BaselineRetry(WaitCase):
    """A baseline git call that fails at start is retried on the injected clock for about 300 s. Then the waiter prints
    its not-started line, removes its lock and exits 2. The old code exits 2 at the first failure."""

    def flaky_run(self, store, machine, down, recover_at=None, hook=None):
        probe = {"failures": []}
        fake = FakeTime(hook=hook)

        def flaky_git(args, env, cache=None, timeout=mail_mod.TRANSFER_BOUND, input_text=None):
            if args and args[0] in down and (recover_at is None or fake.now < recover_at):
                probe["failures"].append(fake.now)
                return FAILED_GIT
            return mail_mod.git(args, env, cache, timeout, input_text)

        code, text = run_wait(machine.env, fake, Procs(), run_git=flaky_git)
        probe["lock_left"] = os.path.exists(lock_path(machine.cache))
        return code, text, fake, probe

    def test_baseline_ls_remote_that_never_recovers_exits_2_after_about_300_seconds(self):
        store, machine = self.fixture()
        code, text, fake, probe = self.flaky_run(store, machine, {"ls-remote"})
        self.assertGreaterEqual(len(probe["failures"]), 2, "the baseline ls-remote failed %d time(s): the waiter did not "
                                "retry it" % len(probe["failures"]))
        self.assertEqual(code, 2, "a baseline that never recovered exited %r, expected 2 (not started)" % (code,))
        self.assertRegex(text, r"(?m)^mail wait: not started: \S", "the give-up printed no not-started line: %r" % text)
        self.assertTrue(300 <= fake.now <= 330, "the waiter gave up at %s s, expected about 300 s of retries" % fake.now)
        self.assertFalse(probe["lock_left"], "the waiter left its lock behind after the baseline gave up")

    def test_baseline_fetch_that_never_recovers_exits_2_after_about_300_seconds(self):
        store, machine = self.fixture()
        code, text, fake, probe = self.flaky_run(store, machine, {"fetch"})
        self.assertGreaterEqual(len(probe["failures"]), 2, "the baseline fetch failed %d time(s): the waiter did not "
                                "retry it" % len(probe["failures"]))
        self.assertEqual(code, 2, "a baseline fetch that never recovered exited %r, expected 2 (not started)" % (code,))
        self.assertRegex(text, r"(?m)^mail wait: not started: \S", "the give-up printed no not-started line: %r" % text)
        self.assertTrue(300 <= fake.now <= 330, "the waiter gave up at %s s, expected about 300 s of retries" % fake.now)
        self.assertFalse(probe["lock_left"], "the waiter left its lock behind after the baseline gave up")

    def test_baseline_that_recovers_inside_300_seconds_proceeds_and_wakes_on_new_mail(self):
        store, machine = self.fixture()
        sent = {}

        def send_after_the_outage(fake):
            if fake.now >= 150 and not sent:
                store.seed(ADDR, "0a1b2c3d4e70", "request", SENDER, "Body marker: after-outage")
                sent["at"] = fake.now

        code, text, fake, probe = self.flaky_run(store, machine, {"ls-remote", "fetch"}, recover_at=120,
                                                 hook=send_after_the_outage)
        self.assertGreaterEqual(len(probe["failures"]), 1, "the baseline never failed, so the outage was not tested")
        self.assertTrue(sent, "the waiter never reached 150 s, so no mail landed after the outage")
        self.assertEqual(code, 0, "a baseline that recovered at 120 s made the waiter exit %r, expected 0 (new mail)"
                         % (code,))
        self.assertTrue(text.startswith("mail: new 0a1b2c3d4e70 "), "the wake line is not the new message: %r" % text)


# The blobs the CRLF cases land. The header block and its blank line end in CRLF. The body ends in CRLF, or in LF
# for the mixed case.
CRLF_MESSAGE = ("Msg 0a1b2c3d4e21 from %s to %s kind request re - try 1\r\n"
                "Reply-to: %s\r\n\r\nBody marker: crlf-subject\r\n" % (SENDER, ADDR, SENDER)).encode("utf-8")
MIXED_MESSAGE = ("Msg 0a1b2c3d4e21 from %s to %s kind request re - try 1\r\n"
                 "Reply-to: %s\r\n\r\nBody marker: mixed-subject\n" % (SENDER, ADDR, SENDER)).encode("utf-8")


class WakeLine(WaitCase):
    """The wake line names the message's address with its read and take commands, and shows the subject as untrusted,
    quoted text, cleaned and cut. A repo-address message wakes with its own --addr."""

    def wake(self, body, addr=ADDR, waiter_addrs=None, msg_id="0a1b2c3d4e21", eol="\n", body_eol=None):
        store, machine = self.fixture()
        probe = {"store": store, "addr": addr, "msg_id": msg_id}

        def land(fake):
            if len(fake.sleeps) == 2 and "sent" not in probe:
                store.seed(addr, msg_id, "request", SENDER, body, eol=eol, body_eol=body_eol)
                probe["sent"] = True

        code, text = run_wait(machine.env, FakeTime(hook=land), Procs(), addrs=waiter_addrs, max_seconds=600)
        return code, text, probe

    def stored(self, probe):
        """The blob the fixture landed for the probed message, as bytes. Asserted before the wake line, so a case
        whose line endings never reached the store cannot pass or fail on the wrong thing (P7)."""
        return probe["store"].read("mail/%s/%s.md" % (probe["addr"], probe["msg_id"]), raw=True)

    def assert_wake_names(self, text, subject, msg_id="0a1b2c3d4e21", addr=ADDR):
        """The one wake line for one message: its read and take commands with --addr, and the subject quoted after the
        word untrusted. Every case that wakes on a message asserts through here."""
        lines = text.strip().splitlines()
        self.assertEqual(len(lines), 1, "the wake printed %d lines, expected one: %r" % (len(lines), text))
        line = lines[0]
        self.assertNotIn('untrusted subject ""', line,
                         "the wake line shows an empty subject: the message's first body line was not found: %r" % line)
        self.assertIn("mail read --addr %s %s" % (addr, msg_id), line,
                      "the wake line gives no read command with --addr: %r" % line)
        self.assertIn("mail take --addr %s %s" % (addr, msg_id), line,
                      "the wake line gives no take command with --addr: %r" % line)
        self.assertIn("untrusted", line, "the wake line does not mark the subject untrusted: %r" % line)
        self.assertIn('"%s"' % subject, line, "the wake line does not quote the subject %r: %r" % (subject, line))
        self.assertLess(line.index("untrusted"), line.index('"%s"' % subject),
                        "the word untrusted does not come before the quoted subject: %r" % line)
        return line

    def test_wake_line_carries_the_read_and_take_commands_and_an_untrusted_quoted_subject(self):
        code, text, probe = self.wake("Body marker: wake-new")
        self.assertIn("sent", probe, "the send never landed: the waiter did not reach its second sleep")
        self.assertEqual(code, 0, "new mail made mail wait exit %r, expected 0" % (code,))
        self.assert_wake_names(text, "Body marker: wake-new")

    def test_crlf_message_wakes_with_its_subject_quoted_and_no_cr_in_the_line(self):
        code, text, probe = self.wake("Body marker: crlf-subject", eol="\r\n", body_eol="\r\n")
        self.assertIn("sent", probe, "the send never landed: the waiter did not reach its second sleep")
        stored = self.stored(probe)
        self.assertEqual(stored, CRLF_MESSAGE, "the store does not hold the CRLF message on every line: %r" % (stored,))
        self.assertEqual(code, 0, "new CRLF mail made mail wait exit %r, expected 0" % (code,))
        self.assert_wake_names(text, "Body marker: crlf-subject")
        self.assertNotIn("\r", text, "the wake line keeps a CR from the CRLF message: %r" % (text,))

    def test_mixed_ending_message_with_crlf_header_and_lf_body_wakes_with_its_subject_quoted(self):
        code, text, probe = self.wake("Body marker: mixed-subject", eol="\r\n", body_eol="\n")
        self.assertIn("sent", probe, "the send never landed: the waiter did not reach its second sleep")
        stored = self.stored(probe)
        self.assertEqual(stored, MIXED_MESSAGE, "the store does not hold the mixed-ending message: %r" % (stored,))
        self.assertEqual(code, 0, "new mixed-ending mail made mail wait exit %r, expected 0" % (code,))
        self.assert_wake_names(text, "Body marker: mixed-subject")
        self.assertNotIn("\r", text, "the wake line keeps a CR from the mixed-ending message: %r" % (text,))

    def test_wake_line_strips_control_c1_and_bidi_characters_from_the_subject(self):
        body = "Hello\x1b[31m\x07keepme\x9b‮gnp⁦tail"
        code, text, probe = self.wake(body)
        self.assertIn("sent", probe, "the send never landed: the waiter did not reach its second sleep")
        self.assertEqual(code, 0, "new mail made mail wait exit %r, expected 0" % (code,))
        self.assertEqual(len(text.strip().splitlines()), 1, "the wake printed more than one line: %r" % text)
        for char in ("\x1b", "\x07", "\x9b", "‮", "⁦"):
            self.assertNotIn(char, text, "the wake line keeps U+%04X from the subject: %r" % (ord(char), text))
        for word in ("Hello", "keepme", "tail"):
            self.assertIn(word, text, "the wake line lost the visible word %r: %r" % (word, text))

    def test_wake_line_cuts_the_subject_to_160_characters(self):
        code, text, probe = self.wake("W" * 300)
        self.assertIn("sent", probe, "the send never landed: the waiter did not reach its second sleep")
        wake = [line for line in text.splitlines() if line.startswith("mail: new ")]
        self.assertTrue(wake, "no wake line printed for the 300-character subject, so there is no subject to measure: %r"
                        % text)
        runs = re.findall(r"W+", wake[0])
        self.assertTrue(runs, "the wake line has no run of W from the subject: %r" % wake[0])
        longest = max(len(run) for run in runs)
        self.assertEqual(longest, 160, "the wake line shows a subject of %d characters, expected 160" % longest)

    def test_repo_address_message_wakes_with_its_own_addr(self):
        code, text, probe = self.wake("Body marker: repo-wide", addr=PC_BASE, waiter_addrs=[PC_BASE + "/S1", PC_BASE],
                                      msg_id="0a1b2c3d4e61")
        self.assertIn("sent", probe, "the repo-address send never landed: the waiter did not reach its second sleep")
        self.assertEqual(code, 0, "new repo-address mail made mail wait exit %r, expected 0" % (code,))
        self.assertIn("mail take --addr %s 0a1b2c3d4e61" % PC_BASE, text,
                      "the wake for the repo address gives no take command with its own --addr: %r" % text)


def wake_subject(mid):
    return "Body marker: new %s" % mid


def expected_wake(mid):
    """The wake line _wake_line prints for one new message of this session's address, with its wake_subject."""
    return ('mail: new %s from %s kind request; untrusted subject "%s"; read: `mail read --addr %s %s`; '
            'take: `mail take --addr %s %s`' % (mid, SENDER, wake_subject(mid), ADDR, mid, ADDR, mid))


def more_line(count):
    """The line that counts the new messages past the five named. Its read command has no --addr: the waiter watches
    the session's address and the repo address, and plain mail read lists every own address."""
    return "mail: %d more new; read: `mail read`" % count


class WakeEveryNew(WaitCase):
    """A poll that finds N new open ids prints one wake line per new message, in the order open_messages returns them
    (by id, for one address), and exits 0. At most five lines: past five, the first five are named and one more line
    counts the rest."""

    def land_at_second_poll(self, new_ids, open_at_start=(), addr_of=None, waiter_addrs=None):
        """A waiter whose address holds `open_at_start` when it starts. At its second sleep, each of `new_ids` lands
        as one message, at the address `addr_of` gives it (by default ADDR). `waiter_addrs` is what the waiter watches
        (by default [ADDR]). Returns (exit code, printed text, probe)."""
        store, machine = self.fixture()
        for mid in open_at_start:
            store.seed(ADDR, mid, "request", SENDER, "Body marker: open at start %s" % mid)
        probe = {}
        addr_of = addr_of or {}

        def land(fake):
            if len(fake.sleeps) == 2 and "sent" not in probe:
                for mid in new_ids:
                    store.seed(addr_of.get(mid, ADDR), mid, "request", SENDER, wake_subject(mid))
                probe["sent"] = True

        code, text = run_wait(machine.env, FakeTime(hook=land), Procs(), addrs=waiter_addrs, max_seconds=600)
        return code, text, probe

    def test_two_new_messages_each_get_one_wake_line_in_id_order_and_exit_0(self):
        ids = ["0a1b2c3d4e50", "0a1b2c3d4e51"]
        code, text, probe = self.land_at_second_poll(ids)
        self.assertIn("sent", probe, "the sends never landed: the waiter did not reach its second sleep")
        self.assertEqual(code, 0, "two new messages made mail wait exit %r, expected 0" % (code,))
        named = [line for line in text.splitlines() if line.startswith("mail: new ")]
        self.assertEqual(len(named), 2, "two new messages printed %d wake lines, expected 2: %r" % (len(named), text))
        self.assertEqual(text.splitlines(), [expected_wake(mid) for mid in ids],
                         "the wake lines are not one per new message, in id order: %r" % text)

    def test_one_new_message_still_prints_exactly_one_wake_line(self):
        ids = ["0a1b2c3d4e52"]
        code, text, probe = self.land_at_second_poll(ids)
        self.assertIn("sent", probe, "the send never landed: the waiter did not reach its second sleep")
        self.assertEqual(code, 0, "one new message made mail wait exit %r, expected 0" % (code,))
        self.assertEqual(text.splitlines(), [expected_wake(ids[0])],
                         "one new message did not print exactly its one wake line: %r" % text)

    def test_seven_new_messages_name_the_first_five_and_count_the_other_two(self):
        ids = ["0a1b2c3d4e%02x" % n for n in range(0x60, 0x67)]
        code, text, probe = self.land_at_second_poll(ids)
        self.assertIn("sent", probe, "the sends never landed: the waiter did not reach its second sleep")
        self.assertEqual(code, 0, "seven new messages made mail wait exit %r, expected 0" % (code,))
        named = [line for line in text.splitlines() if line.startswith("mail: new ")]
        self.assertEqual(len(named), 5, "seven new messages named %d messages, expected 5: %r" % (len(named), text))
        self.assertEqual(text.splitlines(), [expected_wake(mid) for mid in ids[:5]] + [more_line(2)],
                         "seven new messages did not print the first five in id order and then 'mail: 2 more new': %r"
                         % text)

    def test_message_open_at_start_is_not_named_while_two_new_messages_wake(self):
        new, open_id = ["0a1b2c3d4e50", "0a1b2c3d4e52"], "0a1b2c3d4e51"
        code, text, probe = self.land_at_second_poll(new, open_at_start=[open_id])
        self.assertIn("sent", probe, "the sends never landed: the waiter did not reach its second sleep")
        self.assertEqual(code, 0, "two new messages with one open at the start made mail wait exit %r, expected 0"
                         % (code,))
        self.assertNotIn(open_id, text, "the message open at the start was named in a wake line: %r" % text)
        self.assertEqual(text.splitlines(), [expected_wake(mid) for mid in new],
                         "the wake lines are not one per new message: %r" % text)

    def test_five_new_messages_get_five_lines_and_no_more_line(self):
        ids = ["0a1b2c3d4e%02x" % n for n in range(0x70, 0x75)]
        code, text, probe = self.land_at_second_poll(ids)
        self.assertIn("sent", probe, "the sends never landed: the waiter did not reach its second sleep")
        self.assertEqual(code, 0, "five new messages made mail wait exit %r, expected 0" % (code,))
        self.assertEqual(text.splitlines(), [expected_wake(mid) for mid in ids],
                         "five new messages did not print five wake lines and no 'more new' line: %r" % text)

    def test_count_line_for_a_message_at_the_other_address_names_no_addr(self):
        """The waiter watches the session's address and the repo address. One new message lands at the session's address
        and five at the repo address, so six are new in one poll. The sixth message sits at the other address from the
        first one named, so a count line with --addr would miss it."""
        session, repo = PC_BASE + "/S1", PC_BASE
        ids = ["0a1b2c3d4e%02x" % n for n in range(0x90, 0x96)]
        addr_of = {mid: repo for mid in ids[1:]}
        addr_of[ids[0]] = session
        code, text, probe = self.land_at_second_poll(ids, addr_of=addr_of, waiter_addrs=[session, repo])
        self.assertIn("sent", probe, "the sends never landed: the waiter did not reach its second sleep")
        self.assertEqual(code, 0, "six new messages at two addresses made mail wait exit %r, expected 0" % (code,))
        lines = text.splitlines()
        named = [line for line in lines if line.startswith("mail: new ")]
        self.assertEqual(len(named), 5, "six new messages named %d messages, expected 5: %r" % (len(named), text))
        counted = [line for line in lines if not line.startswith("mail: new ")]
        self.assertEqual(len(counted), 1, "six new messages printed %d count lines, expected 1: %r"
                         % (len(counted), text))
        self.assertNotIn("--addr", counted[0],
                         "the count line names an address with --addr, so it does not list the message at the other "
                         "address: %r" % counted[0])
        self.assertEqual(counted[0], more_line(1),
                         "the count line for one message past five is not the plain mail read form: %r" % counted[0])


def lock_state(path):
    """What a reader sees at this step: absent, empty, partly written (not whole JSON with the lock's fields), or whole."""
    if not os.path.exists(path):
        return "absent"
    text = read_text(path) or ""
    if not text:
        return "empty"
    try:
        record = json.loads(text)
    except ValueError:
        return "partial"
    whole = isinstance(record, dict) and {"pid", "ppid", "session", "started", "deadline"} <= set(record)
    return "whole" if whole else "partial"


class LockAtomic(WaitCase):
    """A second start must never read the lock while it is empty or partly written. A leftover empty lock is stale."""

    def test_a_second_start_never_sees_the_lock_empty_or_partly_written(self):
        """Records the lock's state at each step that creates or moves a lock file: os.open, os.fdopen, os.link and
        os.replace; a builtin open() on the lock path; and each json.dump. A plain open() creates the file empty, and
        only the dump fills it, so the state between the two is seen at the dump. Each recorder calls the real function."""
        store, machine = self.fixture()
        lock = lock_path(machine.cache)
        steps = []
        busy = [False]  # the recorder's own read of the lock goes through open(), and must not record itself
        real_open = open
        real_dump = json.dump

        def record(name):
            if busy[0]:
                return
            busy[0] = True
            try:
                steps.append((name, lock_state(lock)))
            finally:
                busy[0] = False

        def watch_os(name, real):
            def watched(*args, **kwargs):
                record(name)
                return real(*args, **kwargs)
            return watched

        def watched_open(file, *args, **kwargs):
            if file == lock:
                record("open")
            return real_open(file, *args, **kwargs)

        def watched_dump(obj, fp, *args, **kwargs):
            record("dump")
            return real_dump(obj, fp, *args, **kwargs)

        with contextlib.ExitStack() as stack:
            for name in ("open", "fdopen", "link", "replace"):
                stack.enter_context(mock.patch.object(os, name, watch_os(name, getattr(os, name))))
            stack.enter_context(mock.patch("builtins.open", watched_open))
            stack.enter_context(mock.patch.object(json, "dump", watched_dump))
            code, text = run_wait(machine.env, FakeTime(), Procs(), max_seconds=60)
        self.assertTrue(steps, "control: the waiter made no step on the lock, so the watch saw nothing")
        torn = [step for step in steps if step[1] in ("empty", "partial")]
        self.assertEqual(torn, [], "a reader at a lock step saw the lock empty or partly written: %r" % torn)

    def test_a_leftover_empty_lock_file_is_stale_and_replaced(self):
        store, machine = self.fixture()
        lock = lock_path(machine.cache)
        os.makedirs(machine.cache, exist_ok=True)
        with open(lock, "w", encoding="utf-8"):
            pass
        probe = {}

        def first_poll(fake):
            if len(fake.sleeps) == 1 and "holder" not in probe:
                probe["holder"] = (read_lock(lock) or {}).get("pid")

        try:
            code, text = run_wait(machine.env, FakeTime(hook=first_poll), Procs(), max_seconds=90)
        except Exception as error:  # a crash on the empty lock is this case's failure, named by the assert below
            self.fail("the waiter raised %s on a leftover empty lock, so it did not treat the file as stale: %s"
                      % (type(error).__name__, error))
        self.assertIn("holder", probe, "the waiter never polled with the empty lock on disk: it did not start")
        self.assertEqual(probe["holder"], WAITER_PID,
                         "an empty lock file was not replaced: it still names pid %r" % (probe["holder"],))
        self.assert_ended_quiet(code, text)


class MaxSecondsBounds(WaitCase):
    """bin/mail refuses a --max-seconds above 7000 or below 1 as a not-started wait, before any wait runs. The cases run
    bin/mail's main in process with its wait replaced by a recorder: an accepted value shows as a call, a refused one
    as none. No case waits on a clock."""

    def cli_wait(self, *args):
        store, machine = self.fixture()
        calls = []

        def recorder(env, addrs, **kwargs):
            calls.append(kwargs)
            return 0

        out = io.StringIO()
        code = None
        with mock.patch.object(cli_module().mail, "wait", recorder), \
                mock.patch.dict(os.environ, machine.env, clear=True), in_folder(machine.checkout), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                code = cli_module().main(["wait", *args])
            except SystemExit as exit_:
                code = exit_.code
        return code, out.getvalue(), calls

    def test_max_seconds_above_7000_is_refused_as_not_started(self):
        code, text, calls = self.cli_wait("--max-seconds", "7001")
        self.assertEqual(calls, [], "--max-seconds 7001 was accepted, so the waiter would run for 7001 s: %r" % calls)
        self.assertEqual(code, 2, "--max-seconds 7001 exited %r, expected 2" % (code,))
        self.assertIn("mail wait: not started: --max-seconds above 7000", text,
                      "--max-seconds 7001 printed no not-started line: %r" % text)

    def test_max_seconds_below_1_is_refused_as_not_started(self):
        code, text, calls = self.cli_wait("--max-seconds", "0")
        self.assertEqual(calls, [], "--max-seconds 0 was accepted, so the waiter would run: %r" % calls)
        self.assertEqual(code, 2, "--max-seconds 0 exited %r, expected 2" % (code,))
        self.assertIn("mail wait: not started: --max-seconds below 1", text,
                      "--max-seconds 0 printed no not-started line: %r" % text)


class WakeCost(WaitCase):
    """A wake's git reads, counted from the send onward: the poll that sees the mail runs ls-remote, fetch, grep, then
    the age lookup (log) and the subject read (show). Beyond the fetch and grep that a moved sha costs, a wake adds one
    git show and one git log."""

    def wake_window(self):
        store, machine = self.fixture()
        mark = {}
        with Starts() as starts:
            def send(fake):
                if len(fake.sleeps) == 2 and "at" not in mark:
                    cut = len(starts.argv)
                    store.seed(ADDR, "0a1b2c3d4e71", "request", SENDER, "Body marker: cost")
                    del starts.argv[cut:]  # the seed's own git starts are the case's writes, not the waiter's
                    mark["at"] = len(starts.argv)

            code, _ = run_wait(machine.env, FakeTime(hook=send), Procs(), max_seconds=600)
        window = starts.argv[mark["at"]:] if "at" in mark else []
        return code, window

    def test_a_wake_adds_exactly_one_git_show_and_one_git_log_beyond_fetch_and_grep(self):
        code, window = self.wake_window()
        self.assertEqual(code, 0, "control: the send did not wake the waiter: exit %r, expected 0" % (code,))
        counted = dict(Counter(git_names(window)))
        self.assertEqual(counted, {"ls-remote": 1, "fetch": 1, "grep": 1, "log": 1, "show": 1},
                         "the wake poll ran git %r, expected one each of ls-remote, fetch, grep, log and show" % counted)

    def test_the_record_names_the_wake_cost_the_hour_measured(self):
        text = read_text(os.path.join(REPO, RECORD_REL)) or ""
        self.assertIsNotNone(re.search(r"wake adds one `git show`[^\n]*`git log`", text),
                             "the record's wake cost does not name one git show and one git log")


# The refresh mail's cost line, in the decision's "Refresh mail cost:" form (decision merge-mail-refreshes-sessions).
REFRESH_COST = (r"Refresh mail cost: processes (\d+) long-lived; timers (\d+); per merge: (\d+) ls-remote, (\d+) fetch, "
                r"(\d+) commit, (\d+) push; per session: (\d+) install per new sha; files written (\d+) \(last-installed sha\)")
REFRESH_SHAS = ["%040x" % number for number in (1, 2, 3)]  # three merges, so three new shas


@unittest.skipIf(os.name == "nt", test_mail.NT_NO_STUB)
class RefreshWait(WaitCase):
    """`mail wait` on a cloud session refreshes when the ref moves on a new main sha, as a turn start does, and prints the
    same line. A refresh is not mail, so the wait keeps waiting to its deadline (decision merge-mail-refreshes-sessions)."""

    def cloud_waiter(self):
        store = self.store()
        store.seed(OTHER, "0a1b2c3d4e00", "inform", SENDER, "Body marker: elsewhere\n")
        script, log = test_mail.fake_installer(self.case, "wait-install")
        return store, self.cloud_machine(store, "b", "sess-b", script), log

    def test_a_moved_ref_with_a_new_sha_refreshes_inside_the_wait_and_the_wait_keeps_waiting(self):
        store, waiter, log = self.cloud_waiter()

        def land(fake):
            if len(fake.sleeps) == 2:  # after the poll at 30 s, before the next sleep
                store.publish(test_mail.REFRESH_PATH, "main moved to %s\n" % test_mail.SHA_A)

        code, text = run_wait(waiter.env, FakeTime(hook=land), Procs(), max_seconds=600)
        self.assertEqual(len(test_mail.read_lines(log)), 1,
                         "a wait that saw a new main sha ran the install %d times, expected 1"
                         % len(test_mail.read_lines(log)))
        self.assertIn("main moved to %s; refreshed" % test_mail.SHA_A, text.splitlines(),
                      "the wait printed no 'refreshed' line for the new sha: %r" % text)
        self.assert_ended_quiet(code, text)

    def test_a_move_for_an_installed_sha_runs_no_install_in_the_wait(self):
        store, waiter, log = self.cloud_waiter()
        store.publish(test_mail.REFRESH_PATH, "main moved to %s\n" % test_mail.SHA_A)
        turn(waiter)
        self.assertEqual(len(test_mail.read_lines(log)), 1,
                         "control: the turn start ran %d installs, expected 1" % len(test_mail.read_lines(log)))

        def land(fake):
            if len(fake.sleeps) == 2:
                store.seed(OTHER, "0a1b2c3d4e03", "inform", SENDER, "Body marker: other\n")

        code, text = run_wait(waiter.env, FakeTime(hook=land), Procs(), max_seconds=600)
        self.assertEqual(len(test_mail.read_lines(log)), 1,
                         "a wait that saw a move for an installed sha ran the install again: %d runs"
                         % len(test_mail.read_lines(log)))
        self.assert_ended_quiet(code, text)


@unittest.skipIf(os.name == "nt", test_mail.NT_NO_STUB)
class RefreshCost(MailCase):
    """The refresh mail's cost. One simulated run: three merges each send one notice, and two cloud sessions each start a
    turn after each merge. Every number on the decision's "Refresh mail cost:" line is counted here."""

    def simulate(self):
        store = self.store()
        store.seed("cloud/sess-c", "0a1b2c3d4e10", "inform", "cloud/sess-a", "Body marker: open\n")  # a live store: each merge fetches
        sender = self.machine("merge", store, origin=test_mail.ORIGIN)
        send = named_route(self, "send_refresh", "hooks/mail.py send_refresh(env, repo_slug, sha) is not built")
        receivers, scripts, logs = {}, {}, {}
        for name, session in (("b", "sess-b"), ("c", "sess-d")):
            scripts[name], logs[name] = test_mail.fake_installer(self.case, "install-" + name)
            receivers[name] = self.cloud_machine(store, name, session, scripts[name])
        sends, started = [], []
        real_start = threading.Thread.start

        def counted(thread):
            started.append(thread)
            return real_start(thread)

        with mock.patch.object(threading.Thread, "start", counted), Starts() as total:
            for sha in REFRESH_SHAS:
                first = len(total.argv)
                send(sender.env, "acme-widgets", sha)
                sends.append(total.argv[first:])
                for name in sorted(receivers):
                    turn(receivers[name])
        per_merge = set()
        for argv in sends:
            subs = Counter(git_subcommand(args) for args in argv if program_name(args) == "git")
            per_merge.add((subs["ls-remote"], subs["fetch"], subs["commit-tree"], subs["push"]))
        others = [args for args in total.argv if program_name(args) != "git" and args[0] not in scripts.values()]
        # The top-level files the refresh leaves in a cache, less what a moved turn already writes: the cache's own config
        # and HEAD, the FETCH_HEAD that git fetch writes, and the listing file. What is left is the refresh's own file.
        files = {}
        for name in receivers:
            cache = receivers[name].cache
            files[name] = [entry for entry in os.listdir(cache) if os.path.isfile(os.path.join(cache, entry))
                           and entry not in ("config", "HEAD", "FETCH_HEAD") and not entry.startswith("listing-")] \
                if os.path.isdir(cache) else []
        return {"per_merge": per_merge, "timers": len(started), "others": others,
                "installs": {name: len(test_mail.read_lines(logs[name])) for name in receivers},
                "files": {name: len(found) for name, found in files.items()}}

    def test_the_decision_states_the_measured_refresh_cost(self):
        text = read_text(os.path.join(REPO, RECORD_REL)) or ""
        found = re.search(REFRESH_COST, text)
        self.assertIsNotNone(found, "%s has no 'Refresh mail cost:' line, so the refresh mail's cost is not written down"
                             % RECORD_REL)
        m = self.simulate()
        self.assertEqual(len(m["per_merge"]), 1, "the three merges ran git with %r, not one set of counts"
                         % sorted(m["per_merge"]))
        processes, timers, ls_remote, fetch, commit, push, per_sha, files = (int(value) for value in found.groups())
        self.assertEqual((ls_remote, fetch, commit, push), next(iter(m["per_merge"])),
                         "the record says per merge %d ls-remote, %d fetch, %d commit, %d push; the stand-in counted %r"
                         % (ls_remote, fetch, commit, push, sorted(m["per_merge"])))
        self.assertEqual(processes, len(m["others"]), "the record says processes %d, the stand-in started %d processes "
                         "that are not git or an install" % (processes, len(m["others"])))
        self.assertEqual(timers, m["timers"], "the record says timers %d, the stand-in started %d threads"
                         % (timers, m["timers"]))
        self.assertEqual({count / len(REFRESH_SHAS) for count in m["installs"].values()}, {per_sha},
                         "the record says %d install per new sha per session, the stand-in ran %r installs for %d shas"
                         % (per_sha, sorted(m["installs"].values()), len(REFRESH_SHAS)))
        self.assertEqual(set(m["files"].values()), {files}, "the record says files written %d per session, the stand-in "
                         "wrote %r" % (files, sorted(m["files"].values())))


if __name__ == "__main__":
    unittest.main()
