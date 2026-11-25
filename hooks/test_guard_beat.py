#!/usr/bin/env python3
"""The progress beat of hooks/test_guard.py (decision stall-watch).

A full run of test_guard.py can print nothing for minutes, and the stall watch then reports a stall on a
healthy run. The runner owes a line at least every GUARD_HEARTBEAT seconds of quiet (default 60). The line
goes to stderr, flushed, and is appended to STALL_WATCH_BEAT when that is set. Each run class runs test_guard.py
on one family (GUARD_FAMILY=branch-worktree: 64 cases and one log check, 16-18 s per family run) and reads what it
printed. The watch classes run that family under hooks/stall_watch.py with a short limit. The defs classes run
the beat's own defs with a fake clock, so no suite runs. The run folder and its sweep are the shared helper's
(lint/_test_temp.py); its sweep is proved in lint/test_find_copies.py.

The GuardLoader classes pin how a guard start is loaded: how many times its source is compiled (GuardLoaderCount),
that a stale, corrupt or other-version cache gives the uncached verdicts (GuardLoaderCache), and where the cache
lives and that a read-only or missing cache folder changes no verdict (GuardLoaderLocation). Each runs test_guard.py
as a child on one existing family of the real suite (LOADER_FAMILY), so a case costs one child run and no clock is read.

    python3 hooks/test_guard_beat.py
"""
import ast
import importlib.util
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from collections import namedtuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
sys.path.insert(0, HERE)
import stall_watch  # noqa: E402  the watcher, and its exit code on a stall (STALL_EXIT)

RUN_FOLDER = _test_temp.run_folder()
CONFIG_DIR = os.path.join(RUN_FOLDER, "config")
os.makedirs(CONFIG_DIR)
SUITE = os.path.join(HERE, "test_guard.py")
SUITE_CMD = [sys.executable, SUITE]
WATCHER = os.path.join(HERE, "stall_watch.py")
FAMILY = "branch-worktree"
TINY = "0.001"  # a quiet stretch of a millisecond: every checkpoint that finds one beats
OFF = "100000"  # a quiet stretch no run reaches: the beat never fires
WATCH_QUIET = "8"  # the watcher's limit in seconds: above the ~2 s import and registration, far below 300 s
TIMEOUT = 900  # a bound against a hang, never an assert
BEAT = "test_guard: still running"  # the beat line's prefix; a case line starts with PASS, FAIL or SKIP
CASE_START = ("PASS", "FAIL", "SKIP")
SUMMARY = "test_guard PASS:"  # the last line of a family run that passed
# Set by a wrapper or an outer run. A child of this test must not read them. PYTHONUNBUFFERED would
# make stdout unbuffered whatever the runner flushes, so a missing flush could not show.
INHERITED = ("STALL_WATCH_BEAT", "GUARD_HEARTBEAT", "GUARD_FAMILY", "GUARD_SHARD", "GUARD_TESTS",
             "MUTATE_ONLY", "GUARD_TIMING", "PYTHONUNBUFFERED")

Run = namedtuple("Run", "rc out err")
Watched = namedtuple("Watched", "watch_rc watch_out job_rc job_out")


def case_lines(text):
    return [line for line in text.splitlines() if line.startswith(CASE_START)]


def beat_lines(text):
    return [line for line in text.splitlines() if line.startswith(BEAT)]


def suite_env(heartbeat=None, beat_file=None):
    """The environment of one family run: the caller's, minus the knobs of an outer run, plus this run's."""
    env = {k: v for k, v in os.environ.items() if k not in INHERITED}
    env["GUARD_FAMILY"] = FAMILY
    env["CLAUDE_CONFIG_DIR"] = CONFIG_DIR
    if heartbeat is not None:
        env["GUARD_HEARTBEAT"] = heartbeat
    if beat_file is not None:
        env["STALL_WATCH_BEAT"] = beat_file
    return env


def run_suite(heartbeat=None, beat_file=None, merged=False):
    """Run test_guard.py on FAMILY and return a Run. With merged, stdout and stderr share one file, so
    the order of lines is the order they were written; otherwise stdout is a pipe and stderr is a file.
    stderr is never a pipe: a `sleep` the suite leaves behind holds a pipe open, and the run would wait."""
    env = suite_env(heartbeat, beat_file)
    with tempfile.TemporaryFile(dir=RUN_FOLDER) as err:
        if merged:
            with tempfile.TemporaryFile(dir=RUN_FOLDER) as out:
                rc = subprocess.run(SUITE_CMD, stdout=out, stderr=subprocess.STDOUT, env=env,
                                    timeout=TIMEOUT).returncode
                out.seek(0)
                return Run(rc, out.read().decode("utf-8", "replace"), "")
        done = subprocess.run(SUITE_CMD, stdout=subprocess.PIPE, stderr=err, env=env, timeout=TIMEOUT)
        err.seek(0)
        return Run(done.returncode, done.stdout.decode("utf-8", "replace"),
                   err.read().decode("utf-8", "replace"))


def kill_job(job):
    """Kill a job this test started, and what it started, when the test ends while the job still runs."""
    try:
        os.killpg(job.pid, signal.SIGKILL)  # the job's own session (start_new_session)
    except (AttributeError, OSError):
        job.kill()


def watched_run(name, heartbeat):
    """Run one family in the background under hooks/stall_watch.py, as the stall watch runs a background job.
    The job writes its output to a file the watcher does not read, and the watcher's --log is an idle file,
    so the beat file is the only thing the watcher reads. The watcher exits 0 when the job ends, or 3 after
    WATCH_QUIET seconds with no byte. After a stall the job runs on and is waited for, so its own cleanup runs."""
    beat_file = os.path.join(RUN_FOLDER, name + "-beat.txt")
    job_file = os.path.join(RUN_FOLDER, name + "-job.txt")
    idle_file = os.path.join(RUN_FOLDER, name + "-idle.txt")
    open(beat_file, "w").close()  # the stall-watch wrapper creates the beat file first (`: > BEAT`)
    open(idle_file, "w").close()
    with open(job_file, "wb") as out:
        job = subprocess.Popen(SUITE_CMD, stdout=out, stderr=subprocess.STDOUT,
                               env=suite_env(heartbeat, beat_file), start_new_session=True)
    # The watcher counts the CPU time of the process tree it watches as life (decision stall-watch), and a family
    # run works all the while. So it watches a stand-in that blocks on a pipe, uses no CPU, and exits when the
    # job ends: the beat file stays the only thing it can read.
    standin = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
    waiter = threading.Thread(target=lambda: (job.wait(), standin.stdin.close()), daemon=True)
    waiter.start()
    try:
        watcher = subprocess.run([sys.executable, WATCHER, "--watch-pid", str(standin.pid), "--log", idle_file,
                                  "--quiet", WATCH_QUIET, "--beat", beat_file],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=TIMEOUT)
        job_rc = job.wait(timeout=TIMEOUT)
    finally:
        if job.poll() is None:
            kill_job(job)
        waiter.join(timeout=30)
        standin.wait(timeout=30)
    with open(job_file, "rb") as f:
        job_out = f.read().decode("utf-8", "replace")
    return Watched(watcher.returncode, watcher.stdout.decode("utf-8", "replace"), job_rc, job_out)


class Defs:
    """The named top-level defs of hooks/test_guard.py, run in one namespace with a fake clock (`now`) and a
    fake print (`printed`), so a beat is measured without running the suite. A def that is missing from the
    file fails here, so a moved beat cannot pass by vanishing."""

    def __init__(self, names, heartbeat=60.0, beat_file=""):
        with open(SUITE, encoding="utf-8") as f:
            tree = ast.parse(f.read(), SUITE)
        found = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        missing = [name for name in names if name not in found]
        if missing:
            raise AssertionError("hooks/test_guard.py has no top-level def %s: the beat moved, so this test "
                                 "must follow it" % missing[0])
        self.now = 0.0
        self.printed = []
        self.ns = {
            "math": math,
            "sys": sys,
            "time": types.SimpleNamespace(monotonic=lambda: self.now),
            "print": lambda *args, **kw: self.printed.append(" ".join(str(a) for a in args)),
            "GUARD_HEARTBEAT": float(heartbeat),
            "BEAT_FILE": beat_file,
            "QUIET_SINCE": [0.0],
        }
        module = ast.Module(body=[found[name] for name in names], type_ignores=[])
        ast.fix_missing_locations(module)
        exec(compile(module, SUITE, "exec"), self.ns)

    def call(self, name, *args):
        return self.ns[name](*args)


class UnderPipe(unittest.TestCase):
    """stdout is a pipe, as under `| tail`. The beat must still reach stderr and the beat file, and the run
    must still pass: the beat changes no verdict."""

    @classmethod
    def setUpClass(cls):
        cls.beat_file = os.path.join(RUN_FOLDER, "stall-watch-beat.txt")
        open(cls.beat_file, "w").close()  # the stall-watch wrapper creates the beat file first (`: > BEAT`)
        cls.captured = run_suite(heartbeat=TINY, beat_file=cls.beat_file)

    def test_the_run_exits_zero_with_its_summary(self):
        self.assertEqual(self.captured.rc, 0, "the run with the beat on exited %d, not 0" % self.captured.rc)
        self.assertIn(SUMMARY, self.captured.out, "the run with the beat on printed no summary line")

    def test_the_run_reaches_its_cases(self):
        self.assertTrue(case_lines(self.captured.out), "no case line on stdout: the run never reached a case")

    def test_the_beat_reaches_stderr_under_a_pipe(self):
        self.assertTrue(beat_lines(self.captured.err), "no beat line on stderr while stdout was a pipe")

    def test_the_beat_file_is_appended(self):
        with open(self.beat_file, encoding="utf-8", errors="replace") as f:
            self.assertTrue(beat_lines(f.read()), "STALL_WATCH_BEAT holds no beat line after the run")


class BetweenCases(unittest.TestCase):
    """stdout and stderr share one file. A beat must fall between two case lines: that shows the beat
    fires during the run, not at import, and that each case line is flushed as it is printed (a held
    line would land after every beat). The run must also exit 0 with its summary."""

    @classmethod
    def setUpClass(cls):
        cls.captured = run_suite(heartbeat=TINY, merged=True)
        cls.lines = cls.captured.out.splitlines()

    def test_the_run_exits_zero_with_its_summary(self):
        self.assertEqual(self.captured.rc, 0, "the run with the beat on exited %d, not 0" % self.captured.rc)
        self.assertIn(SUMMARY, self.captured.out, "the run with the beat on printed no summary line")

    def test_a_beat_falls_between_the_first_two_case_lines(self):
        cases = [i for i, line in enumerate(self.lines) if line.startswith(CASE_START)]
        self.assertGreaterEqual(len(cases), 2, "fewer than two case lines: the run did not reach two cases")
        beats = [i for i, line in enumerate(self.lines) if line.startswith(BEAT)]
        self.assertTrue([i for i in beats if cases[0] < i < cases[1]],
                        "no beat between case lines %d and %d" % (cases[0] + 1, cases[1] + 1))


class DefaultRun(unittest.TestCase):
    """Control: with GUARD_HEARTBEAT unset, a short run prints no beat."""

    @classmethod
    def setUpClass(cls):
        cls.lines = run_suite(merged=True).out.splitlines()

    def test_a_short_default_run_prints_no_beat(self):
        text = "\n".join(self.lines)
        self.assertTrue(case_lines(text), "no case line in the default run")
        beats = beat_lines(text)
        self.assertFalse(beats, "a beat in a short default run: %r" % beats[:1])


class InvalidHeartbeat(unittest.TestCase):
    def test_an_invalid_value_exits_with_a_message(self):
        for value in ("abc", "0", "nan"):
            with self.subTest(value=value):
                run = run_suite(heartbeat=value, merged=True)
                self.assertNotEqual(run.rc, 0, "GUARD_HEARTBEAT=%s was accepted: the run exited 0" % value)
                self.assertIn("GUARD_HEARTBEAT", run.out,
                              "GUARD_HEARTBEAT=%s exited with no message that names it" % value)
                self.assertFalse(case_lines(run.out), "GUARD_HEARTBEAT=%s ran cases before it failed" % value)


class DefaultInterval(unittest.TestCase):
    def test_the_unset_interval_is_at_most_120_seconds(self):
        value = Defs(["parse_heartbeat"]).call("parse_heartbeat", "")  # "" is GUARD_HEARTBEAT unset
        self.assertTrue(0 < value <= 120, "the unset GUARD_HEARTBEAT is %r seconds: decision stall-watch wants "
                                          "a line at least every 120 s" % value)


class BeatCost(unittest.TestCase):
    """A quiet stretch of N seconds at interval I writes about N / I beat lines to the beat file, however
    many checkpoints it holds: the cost is set by the quiet time, not by the number of cases."""

    def checkpoints(self, defs, seconds, step):
        """One checkpoint every `step` seconds for `seconds` of quiet, the clock moving with them."""
        count = int(round(seconds / step))
        for i in range(1, count + 1):
            defs.now = i * step
            defs.call("beat", "case %d, before it runs" % i)
        return count

    def test_a_full_quiet_stretch_writes_one_line_per_interval(self):
        beat_file = os.path.join(RUN_FOLDER, "cost-full.txt")
        open(beat_file, "w").close()
        defs = Defs(["beat"], heartbeat=10.0, beat_file=beat_file)
        count = self.checkpoints(defs, seconds=100, step=0.5)  # 200 checkpoints in 100 s at I = 10 s
        with open(beat_file, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertEqual(len(lines), 100 // 10, "%d s of quiet at I = 10 s over %d checkpoints wrote %d beat "
                                                "lines, want 10: one per interval" % (100, count, len(lines)))
        self.assertEqual(len(defs.printed), len(lines), "a beat was appended to the file but not printed")

    def test_a_stretch_with_no_quiet_time_writes_nothing(self):
        beat_file = os.path.join(RUN_FOLDER, "cost-empty.txt")
        open(beat_file, "w").close()
        defs = Defs(["beat"], heartbeat=10.0, beat_file=beat_file)
        for i in range(50):  # the clock never moves: no quiet time at all
            defs.call("beat", "case %d, before it runs" % i)
        with open(beat_file, encoding="utf-8") as f:
            self.assertEqual(f.read(), "", "a beat was written with no quiet time: the interval check is gone")


class WatchedBeatOn(unittest.TestCase):
    """The beat on, under the watcher. The watcher reads only the beat file, so a run with no stall proves the
    beat reached the watcher. The job must pass first: a crash at import would also end with no stall."""

    @classmethod
    def setUpClass(cls):
        cls.watched = watched_run("watch-on", TINY)

    def test_the_job_exits_zero_with_its_summary(self):
        self.assertEqual(self.watched.job_rc, 0, "the watched run with the beat on exited %r, not 0"
                         % self.watched.job_rc)
        self.assertIn(SUMMARY, self.watched.job_out, "the watched run with the beat on printed no summary line")

    def test_the_watcher_reports_no_stall(self):
        self.assertNotIn("STALL", self.watched.watch_out, "the watcher reported a stall with the beat on")
        self.assertEqual(self.watched.watch_rc, 0, "the watcher exited %r, not 0" % self.watched.watch_rc)

    def test_the_watcher_relays_the_beat_from_the_beat_file(self):
        self.assertTrue(beat_lines(self.watched.watch_out), "the watcher relayed no beat line from the beat file")


class WatchedBeatOff(unittest.TestCase):
    """Control: the beat off, at the same watcher limit. No byte reaches the watcher for WATCH_QUIET seconds,
    so it must report a stall on a healthy run. Without it, the no-stall arm would pass on a watcher that
    never fires."""

    @classmethod
    def setUpClass(cls):
        cls.watched = watched_run("watch-off", OFF)

    def test_the_job_exits_zero_with_its_summary(self):
        self.assertEqual(self.watched.job_rc, 0, "the watched run with the beat off exited %r, not 0"
                         % self.watched.job_rc)
        self.assertIn(SUMMARY, self.watched.job_out, "the watched run with the beat off printed no summary line")

    def test_the_watcher_reports_a_stall(self):
        self.assertEqual(self.watched.watch_rc, stall_watch.STALL_EXIT,
                         "the watcher exited %r with the beat off, not a stall" % self.watched.watch_rc)
        self.assertIn("STALL", self.watched.watch_out, "the watcher exited with no STALL report")


# ---- the guard loader cases (GuardLoaderCount, GuardLoaderCache, GuardLoaderLocation) ----
# The child runs one existing family of the real suite: its allow and deny cases carry the expected verdicts, which
# main gives uncached, so a family that passes under the loader gives the uncached verdicts. The family is small and
# holds both kinds. A section folder of its own cannot run: the sections depend on one another (LOG_CHECKS_EXTRA).
LOADER_FAMILY = "sendmessage-session-id"
GUARD = os.path.join(HERE, "guard.py")
CACHE_ENV = ("PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX", "PYTHONPATH")  # set or stripped per case, never inherited
# A sitecustomize that logs one line per compile() call: the compiled file, and the argv of the process that compiled
# it. The audit hook reads no clock. It is the count the loader cases read; a compile is what a cached start skips.
PROBE_SITE = """import os, sys
LOG = os.environ.get("LOADER_PROBE_LOG", "")
BUSY = [False]


def hook(event, args):
    if not LOG or BUSY[0] or event != "compile":
        return
    BUSY[0] = True
    try:
        fd = os.open(LOG, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
        os.write(fd, ("%s\\t%s\\n" % (args[1], sys.argv[0] if sys.argv else "-c")).encode())
        os.close(fd)
    finally:
        BUSY[0] = False


sys.addaudithook(hook)
"""


def base_env():
    """The caller's environment, minus the knobs of an outer run and the cache knobs each case sets itself."""
    return {k: v for k, v in os.environ.items() if k not in INHERITED + CACHE_ENV}


def probe_folder(root):
    """A folder with the probe sitecustomize in it, for PYTHONPATH. Returns the folder."""
    folder = os.path.join(root, "probe")
    os.makedirs(folder)
    with open(os.path.join(folder, "sitecustomize.py"), "w", encoding="utf-8") as handle:
        handle.write(PROBE_SITE)
    return folder


def loader_env(cache=None, probe=None, log=None):
    """The environment of one child run of test_guard.py on LOADER_FAMILY. `cache` sets PYTHONPYCACHEPREFIX; None
    leaves the cache at the guard's own __pycache__ beside it. `probe` and `log` turn on the compile probe."""
    env = base_env()
    env["CLAUDE_CONFIG_DIR"] = CONFIG_DIR
    env["GUARD_FAMILY"] = LOADER_FAMILY
    if cache is not None:
        env["PYTHONPYCACHEPREFIX"] = cache
    if probe is not None:
        env["PYTHONPATH"] = probe
        env["LOADER_PROBE_LOG"] = log
    return env


def loader_run(env):
    """Run test_guard.py as a child with `env`, on LOADER_FAMILY. Returns a Run."""
    with tempfile.TemporaryFile(dir=RUN_FOLDER) as out, tempfile.TemporaryFile(dir=RUN_FOLDER) as err:
        done = subprocess.run(SUITE_CMD, stdout=out, stderr=err, env=env, timeout=TIMEOUT)
        out.seek(0)
        err.seek(0)
        return Run(done.returncode, out.read().decode("utf-8", "replace"), err.read().decode("utf-8", "replace"))


def cache_file(prefix):
    """The path Python writes the guard's own bytecode to, with `prefix` as the cache root (None: beside the guard)."""
    saved = sys.pycache_prefix
    sys.pycache_prefix = prefix
    try:
        return importlib.util.cache_from_source(GUARD)
    finally:
        sys.pycache_prefix = saved


def read_bytes_or_none(path):
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as handle:
        return handle.read()


def write_bytes(path, data):
    with open(path, "wb") as handle:
        handle.write(data)


def compiles_of(log, target):
    """How many compiles of `target` the probe logged, outside test_guard.py's own process (its argv ends in test_guard.py)."""
    if not os.path.exists(log):
        return 0
    want = os.path.realpath(target)
    with open(log, encoding="utf-8") as handle:
        rows = [line.rstrip("\n").split("\t") for line in handle if line.strip()]
    return sum(1 for row in rows
               if len(row) == 2 and os.path.realpath(row[0]) == want and not row[1].endswith("test_guard.py"))


def loader_clean(test, run, what):
    """Fail the test unless the child passed every case of the family. The FAIL lines name the case whose verdict moved,
    and a crashed run shows the tail of its stderr, so the failure names the input."""
    if run.rc != 0 or SUMMARY not in run.out:
        wrong = [line for line in run.out.splitlines() if line.startswith(("FAIL", "test_guard FAIL"))]
        detail = "; ".join(wrong[:3]) or run.err.strip()[-300:] or "no output"
        test.fail("%s: the guard did not give the uncached verdict on every case of %s (rc %s): %s"
                  % (what, LOADER_FAMILY, run.rc, detail))


def stale(data):
    """The guard's source changed after this cache was written: the mtime the cache records no longer matches the file."""
    return data[:8] + bytes([data[8] ^ 1]) + data[9:]


def corrupt(data):
    """The header is right and the marshal body is not: every byte past the 16-byte header is flipped."""
    return data[:16] + bytes(byte ^ 0x5A for byte in data[16:])


def other_version(data):
    """A magic number no CPython writes: the cache is not this interpreter's."""
    return b"\x00\x00\x00\x00" + data[4:]


class GuardLoaderCount(unittest.TestCase):
    """A cached start compiles the guard's source once from a cold cache, and not at all from a warm one."""

    @classmethod
    def setUpClass(cls):
        # Two runs of the family on one cache root: the cold run writes the cache, the warm run finds it. Each run
        # writes its own probe log, so the two counts do not mix.
        cls.root = tempfile.mkdtemp(dir=RUN_FOLDER)
        cls.cache = os.path.join(cls.root, "pyc")
        probe = probe_folder(cls.root)
        cls.logs = [os.path.join(cls.root, "cold.log"), os.path.join(cls.root, "warm.log"),
                    os.path.join(cls.root, "host.log")]
        cls.runs = [loader_run(loader_env(cache=cls.cache, probe=probe, log=cls.logs[0])),
                    loader_run(loader_env(cache=cls.cache, probe=probe, log=cls.logs[1]))]
        # The host's own setting: this session's shell sets PYTHONDONTWRITEBYTECODE=1, and the guard children inherit
        # it. A cold run under it writes no cache, so the count here is the loader's real gain on this host.
        host_env = loader_env(cache=os.path.join(cls.root, "host-pyc"), probe=probe, log=cls.logs[2])
        host_env["PYTHONDONTWRITEBYTECODE"] = "1"
        cls.runs.append(loader_run(host_env))

    def test_cold_start_compiles_the_guard_once(self):
        loader_clean(self, self.runs[0], "the cold-cache run")
        compiles = compiles_of(self.logs[0], GUARD)
        self.assertEqual(compiles, 1,
                         "guard.py was compiled from source %d times in a cold-cache run of %s; a cached start "
                         "compiles it once" % (compiles, LOADER_FAMILY))

    def test_warm_start_compiles_nothing(self):
        loader_clean(self, self.runs[1], "the warm-cache run")
        compiles = compiles_of(self.logs[1], GUARD)
        self.assertEqual(compiles, 0,
                         "guard.py was compiled from source %d times in a warm-cache run of %s; a cached start "
                         "compiles nothing" % (compiles, LOADER_FAMILY))

    def test_host_env_cold_start_compiles_the_guard_once(self):
        # Under PYTHONDONTWRITEBYTECODE=1 a cache is not written unless the loader writes it anyway. Whether it should is
        # the owner's call (it overrides the user's setting), so this case is red until that call is made.
        loader_clean(self, self.runs[2], "the cold-cache run under PYTHONDONTWRITEBYTECODE=1")
        compiles = compiles_of(self.logs[2], GUARD)
        self.assertEqual(compiles, 1,
                         "guard.py was compiled from source %d times in a cold run of %s under "
                         "PYTHONDONTWRITEBYTECODE=1; a cached start compiles it once" % (compiles, LOADER_FAMILY))

    def test_probe_counts_one_compile_per_script_start_and_one_per_module_cache_fill(self):
        # The instrument's own control: a script compiles on every start, a cached import compiles once. Green on
        # main, because the probe, not the guard, is what it checks.
        root = tempfile.mkdtemp(dir=RUN_FOLDER)
        stand = os.path.join(root, "stand")
        os.makedirs(stand)
        module = os.path.join(stand, "standin_mod.py")
        script = os.path.join(stand, "standin_script.py")
        for path in (module, script):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("VALUE = 1\n")
        log = os.path.join(root, "control.log")
        env = base_env()
        env["PYTHONPYCACHEPREFIX"] = os.path.join(root, "pyc")
        env["PYTHONPATH"] = probe_folder(root)
        env["LOADER_PROBE_LOG"] = log
        importer = [sys.executable, "-c", "import sys; sys.path.insert(0, %r); import standin_mod" % stand]
        starter = [sys.executable, script]
        for command in (importer, importer, starter, starter):
            subprocess.run(command, env=env, capture_output=True, timeout=60, check=True)
        self.assertEqual(compiles_of(log, module), 1,
                         "a cached import of standin_mod.py should compile it once in two starts")
        self.assertEqual(compiles_of(log, script), 2,
                         "a script should compile on each of its two starts")


class GuardLoaderCache(unittest.TestCase):
    """A stale, corrupt or other-version cache gives the uncached verdicts."""

    @classmethod
    def setUpClass(cls):
        # One warm run writes the guard's cache under a cache root of this class's own. Each case tampers with the
        # bytes it wrote, restored first, so no case reads another case's tampered file.
        cls.root = tempfile.mkdtemp(dir=RUN_FOLDER)
        cls.cache = os.path.join(cls.root, "pyc")
        cls.path = cache_file(cls.cache)
        cls.warm = loader_run(loader_env(cache=cls.cache))
        cls.warm_bytes = read_bytes_or_none(cls.path)

    def tampered_run(self, tamper, what):
        if self.warm_bytes is None:
            self.fail("no guard cache was written at %s by a guard call, so there is no cache to tamper with (%s)"
                      % (self.path, what))
        write_bytes(self.path, tamper(self.warm_bytes))
        run = loader_run(loader_env(cache=self.cache))
        loader_clean(self, run, what)

    def test_stale_cache_gives_the_uncached_verdicts(self):
        self.tampered_run(stale, "a stale cache, its recorded source mtime no longer matching")

    def test_corrupt_cache_gives_the_uncached_verdicts(self):
        self.tampered_run(corrupt, "a corrupt cache, its header right and its body flipped")

    def test_other_version_cache_gives_the_uncached_verdicts(self):
        self.tampered_run(other_version, "a cache written by another version, its magic number wrong")


class GuardLoaderLocation(unittest.TestCase):
    """The guard's cache lives beside the guard, and a read-only or missing cache folder changes no verdict."""

    def test_guard_cache_is_written_beside_the_guard(self):
        path = cache_file(None)   # the default: hooks/__pycache__/guard.<tag>.pyc
        if os.path.isfile(path):
            os.remove(path)   # a cache, not a source file: removing it makes the run show whether a start writes it
        run = loader_run(loader_env())
        loader_clean(self, run, "the default-location run")
        self.assertTrue(os.path.isfile(path),
                        "no guard cache at %s after a guard call: the guard's source is compiled on every call" % path)

    def test_read_only_cache_folder_changes_no_verdict(self):
        root = tempfile.mkdtemp(dir=RUN_FOLDER)
        readonly = os.path.join(root, "readonly")
        os.makedirs(readonly)
        os.chmod(readonly, 0o555)
        try:
            run = loader_run(loader_env(cache=readonly))
        finally:
            os.chmod(readonly, 0o755)
        loader_clean(self, run, "a read-only cache folder")

    def test_missing_cache_folder_changes_no_verdict(self):
        root = tempfile.mkdtemp(dir=RUN_FOLDER)
        blocker = os.path.join(root, "not-a-folder")
        write_bytes(blocker, b"")   # a file where the cache folder would sit: the folder cannot be made
        run = loader_run(loader_env(cache=os.path.join(blocker, "pyc")))
        loader_clean(self, run, "a missing cache folder")


if __name__ == "__main__":
    try:
        result = unittest.main(exit=False, verbosity=2).result
    finally:
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder
    sys.exit(0 if result.wasSuccessful() else 1)
