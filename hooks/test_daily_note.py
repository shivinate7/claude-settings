#!/usr/bin/env python3
"""Cases for hooks/daily_note.py: the once-a-day session-start note.

Run it from the repository root:

    python3 hooks/test_daily_note.py

Standard library only, and no test runner. Each case runs the note as a child process, as the
SessionStart hook does, with a scratch CLAUDE_CONFIG_DIR, scratch TEMP, TMP, APPDATA and
LOCALAPPDATA, and a clock seam: CLAUDE_DAILY_NOTE_NOW, an ISO-8601 instant with its UTC offset.
No case sleeps.

Contract the builder codes against. Every case is red until hooks/daily_note.py exists.
- The day is the America/Chicago calendar day of the seam instant. Reuse hooks/local_time.py for
  the DST rule; do not copy it. A naive timestamp in guard.log is local Central wall time.
- Reads <CLAUDE_CONFIG_DIR>/guard.log, six tab fields: time, tool, decision, rule, matched, session.
  The tally comes from lint/guard_log_report.py. Do not parse the log a second time.
- The checks read the previous Central day. A later start on the same Central day prints
  nothing, writes nothing, and runs no check.
- Failed checks, each one stdout line:
  1. A `crash` decision line (rule guard-crash) from the previous day.
  2. guard.log exists but cannot be read. The line says unknown.
  3. An agent-end reap run on a window day that was killed (a started row, no done row) or crashed
     (an error key). The reader is <config dir>/state/agent-end-payloads.jsonl. Unreadable: unknown.
  4. <config dir>/janitor/launchd-sweep.err.log is not empty and was last written on a window day.
  5. <config dir>/state/agent-end-drops.jsonl holds a drop row on a window day: a row log() wrote when
     it dropped the new row (janitor/agent_end_reap.py). One line gives the count, says "dropped", and
     ends with `Read:` and the file's path. A malformed row is skipped, and so is a row whose `at` cannot
     be converted to Central (year 9999, late, with a negative offset). A missing file is silent. A
     directory at the path is unknown, and the start still writes its stamp.
  No volume check. A day of high but steady denies, or a ramp of growing volume, prints nothing.
- Cost of checks 3, 4 and 5: they read files on disk after the stamp check, start no process, and
  write nothing beyond the stamp. Watched in this process, since main() catches every error.
- Each line: plain text, names what failed, and names the reader command by its ABSOLUTE path,
  built from the hook's own folder: <hook folder>/../lint/guard_log_report.py. Nothing else goes
  to stdout. stderr stays empty. At most 240 characters, unless its short head and whole Read:
  tail are longer than 240; then the line is those two and nothing more (lane ruling, 06:27 CST).
- Done-today stamp: under CLAUDE_CONFIG_DIR, and it records the Central day. Never under TEMP,
  TMP, APPDATA or LOCALAPPDATA.
- A crash in the note: exit 0, stdout empty, exactly one stderr line.
- Wiring: a SessionStart hook under a startup matcher runs the note in the same
  `[ -f ... ] || exit 0` shape as the other hooks, so a missing script exits 0 silently.
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
NOTE = os.path.join(ROOT, "hooks", "daily_note.py")
sys.path.insert(0, os.path.join(ROOT, "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)
SETTINGS = os.path.join(ROOT, "settings.json")
CLOCK = "CLAUDE_DAILY_NOTE_NOW"
MAX_LINE = 240
LONG_CONFIG = 150  # a long CLAUDE_CONFIG_DIR path; the agent-end tail is one path, so it fits the cap
TAIL_CONFIG = 220  # so long that the agent-end tail alone is past the cap
LONG_HOOK_FOLDER = 190  # a long hook folder: the reader tail with a short head is past the cap

YESTERDAY = "2026-10-13"  # the Central day before MORNING
TODAY = "2026-10-14"
MORNING = "2026-10-14T09:00:00-05:00"
BASELINE = ["2026-10-%02d" % day for day in range(6, 13)]  # the 7 days before YESTERDAY
HISTORY = BASELINE + [YESTERDAY]
CRASH_AT = "2026-10-13T23:30:00"  # a late-evening line on YESTERDAY, Central wall time
YESTERDAY_NOON = "2026-10-13T12:00:00-05:00"  # a run or a log write on YESTERDAY, the one window day of MORNING
LATER_SAME_DAY = "2026-10-14T15:00:00-05:00"
OLD_WRITE = "2026-10-01T12:00:00-05:00"  # an error log last written before the window
# A Claude Code session sets these. The version check would then read the real binary and write its
# cache under the config dir, so every case clears them.
SCRUBBED = ("CLAUDE_CODE_EXECPATH", "AI_AGENT")


def row(stamp, decision, rule, matched="x", tool="Bash", session="s-1"):
    return "\t".join([stamp, tool, decision, rule, matched, session]) + "\n"


def steady(rule, count, days, decision="deny"):
    """count lines of one rule on each of the days, spread across the morning."""
    return [row("%sT10:%02d:%02d" % (day, i // 60, i % 60), decision, rule)
            for day in days for i in range(count)]


def healthy_log():
    return (steady("env-file", 40, HISTORY) + steady("waiter", 30, HISTORY)
            + [row("2026-10-13T12:00:00", "ask", "force-push", "git push -f"),
               row("2026-10-13T12:01:00", "fixed", "STE", "notes.md fixed=2", "Write")])


def guard_crash(stamp):
    return row(stamp, "crash", "guard-crash", "guard_core: ImportError: boom", "", "-")


def reader_path(hook_folder):
    """The reader's absolute path, one folder up from the hook's own folder: ../lint/guard_log_report.py."""
    return os.path.normpath(os.path.join(os.path.abspath(hook_folder), "..", "lint", "guard_log_report.py"))


def unreadable_error(path):
    """The name of the error a read of PATH raises on this platform, so a case expects the name the note prints."""
    try:
        with open(path, encoding="utf-8"):
            pass
    except OSError as err:
        return type(err).__name__
    raise AssertionError("control: %s opened as a file, so it is not an unreadable log" % path)


def unreadable_payload_head(err):
    """The head of the line for an agent-end payload log that cannot be read. Both the full and the short
    form keep its state: a short head that drops "unknown" would read as clear (verification-report-unknown-reads)."""
    return "agent-end payload log cannot be read (%s): its state is unknown." % err


def session_start_commands():
    """Commands under SessionStart matchers that cover startup and that name daily_note.py."""
    with open(SETTINGS, encoding="utf-8") as handle:
        entries = json.load(handle)["hooks"]["SessionStart"]
    found = []
    for entry in entries:
        matcher = entry.get("matcher")
        if matcher is not None and "startup" not in matcher:
            continue
        found += [hook["command"] for hook in entry.get("hooks", [])
                  if "daily_note.py" in hook.get("command", "")]
    return found


class NoteCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="daily-note-case-")
        self.config = self.scratch("config")
        self.temp = self.scratch("temp")
        self.appdata = self.scratch("appdata")
        self.localappdata = self.scratch("localappdata")
        self.home = self.scratch("home")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def scratch(self, name):
        path = os.path.join(self.root, name)
        os.makedirs(path)
        return path

    def long_path(self, length, prefix, at_least=False):
        """A scratch folder whose absolute path is `length` characters long, padded from this case's root.
        at_least: a root already past `length` is kept, for a case whose claim holds at any longer path."""
        pad = length - len(os.path.join(self.root, prefix))
        if at_least:
            pad = max(pad, 1)
        else:
            self.assertGreater(pad, 0, "control: the root is too long for a %d-character path" % length)
        return self.scratch(prefix + "x" * pad)

    def require_file(self, path):
        if not os.path.isfile(path):
            self.fail("%s does not exist yet: the daily note is not built" % os.path.relpath(path, ROOT))

    def write_log(self, lines):
        with open(os.path.join(self.config, "guard.log"), "w", encoding="utf-8") as handle:
            handle.write("".join(lines))

    def append_log(self, lines):
        with open(os.path.join(self.config, "guard.log"), "a", encoding="utf-8") as handle:
            handle.write("".join(lines))

    def payload_path(self):
        return os.path.join(self.config, "state", "agent-end-payloads.jsonl")

    def write_payload(self, lines):
        os.makedirs(os.path.dirname(self.payload_path()), exist_ok=True)
        with open(self.payload_path(), "w", encoding="utf-8") as handle:
            handle.write("".join(lines))

    def drops_path(self):
        return os.path.join(self.config, "state", "agent-end-drops.jsonl")

    def write_drops(self, lines):
        os.makedirs(os.path.dirname(self.drops_path()), exist_ok=True)
        with open(self.drops_path(), "w", encoding="utf-8") as handle:
            handle.write("".join(lines))

    def stamp_day(self):
        """The Central day the done-today stamp records, or None when no stamp was written."""
        path = os.path.join(self.config, "daily-note.stamp")
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()

    def sweep_err_path(self):
        return os.path.join(self.config, "janitor", "launchd-sweep.err.log")

    def sweep_out_path(self):
        return os.path.join(self.config, "janitor", "launchd-sweep.log")

    def write_sweep_err(self, text, when):
        os.makedirs(os.path.dirname(self.sweep_err_path()), exist_ok=True)
        with open(self.sweep_err_path(), "w", encoding="utf-8") as handle:
            handle.write(text)
        stamp = datetime.fromisoformat(when).timestamp()
        os.utime(self.sweep_err_path(), (stamp, stamp))

    def env(self, config):
        env = dict(os.environ)
        for key in SCRUBBED:
            env.pop(key, None)
        env.update({"CLAUDE_CONFIG_DIR": config, "TEMP": self.temp, "TMP": self.temp,
                    "TMPDIR": self.temp, "APPDATA": self.appdata,
                    "LOCALAPPDATA": self.localappdata, "HOME": self.home,
                    "USERPROFILE": self.home})
        return env

    def run_note(self, now, script=NOTE):
        self.require_file(script)
        env = self.env(self.config)
        env[CLOCK] = now
        return subprocess.run([sys.executable, script], env=env, cwd=self.root,
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=60)

    def assert_names_reader(self, line, hook_folder):
        expected = reader_path(hook_folder)
        self.assertTrue(os.path.isabs(expected))
        self.assertIn(os.path.normcase(expected), os.path.normcase(line),
                      "the line does not print the absolute reader path %s: %r" % (expected, line))

    def assert_silent(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def failure_lines(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout.splitlines()

    def assert_short_head_kept(self, line, short, tail, keep):
        """The cut rule from the real lengths, so no temp root length is assumed. KEEP (the count or the
        lead) and the whole TAIL always print. Past the cap, the line is exactly SHORT and TAIL (lane
        ruling, 06:27 CST). Within the cap, the line fits, with its full head or the short one."""
        self.assertIn(keep, line, "the cut lost %r: %r" % (keep, line))
        self.assertTrue(line.endswith(tail), "the cut lost the Read: tail: %r" % line)
        self.assertLessEqual(len(line), max(MAX_LINE, len(short) + 1 + len(tail)),
                             "the line passes the cap by more than its short head and tail: %r" % line)
        if len(short) + 1 + len(tail) > MAX_LINE:
            self.assertEqual(line, short + " " + tail,
                             "the line is not its short head plus its whole tail: %r" % line)

    def load_note(self):
        self.require_file(NOTE)
        spec = importlib.util.spec_from_file_location("daily_note_under_test", NOTE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def in_process(self, module, now):
        """One start of the note in this process, with the env a child would get. Returns stdout and stderr."""
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ):
            for key in SCRUBBED:
                os.environ.pop(key, None)
            os.environ.update(self.env(self.config))
            os.environ[CLOCK] = now
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                module.main()
        return out.getvalue(), err.getvalue()

    def snapshot(self):
        tree = {}
        for dirpath, dirnames, filenames in os.walk(self.config):
            for name in dirnames:
                tree[os.path.relpath(os.path.join(dirpath, name), self.config) + os.sep] = None
            for name in filenames:
                path = os.path.join(dirpath, name)
                with open(path, "rb") as handle:
                    tree[os.path.relpath(path, self.config)] = handle.read()
        return tree


class FirstStartTests(NoteCase):
    def test_first_start_with_every_check_passing_prints_nothing(self):
        self.write_log(healthy_log())
        self.assert_silent(self.run_note(MORNING))

    def test_later_start_the_same_day_prints_nothing_and_writes_nothing(self):
        self.write_log(healthy_log())
        self.assert_silent(self.run_note(MORNING))
        self.append_log([guard_crash("2026-10-13T23:50:00")])  # a failing check, if it ran
        settled = self.snapshot()
        self.assert_silent(self.run_note("2026-10-14T15:00:00-05:00"))
        self.assertEqual(self.snapshot(), settled)

    def test_done_today_stamp_lives_under_config_dir_only(self):
        self.write_log(healthy_log())
        before = self.snapshot()
        self.assert_silent(self.run_note(MORNING))
        after = self.snapshot()
        added = [path for path in after if path not in before]
        self.assertTrue(added, "the first start wrote no stamp under CLAUDE_CONFIG_DIR")
        self.assertTrue(any(TODAY in path or TODAY.encode() in (after[path] or b"") for path in added),
                        "the stamp does not record the Central day %s" % TODAY)
        for folder in (self.temp, self.appdata, self.localappdata):
            self.assertEqual(os.listdir(folder), [], "the stamp leaked into %s" % folder)


class CentralDayTests(NoteCase):
    def test_the_central_day_decides_a_new_day_not_the_utc_day_or_24_hours(self):
        self.write_log(healthy_log())
        # 22:00 CDT on Oct 13 is already Oct 14 in UTC.
        self.assert_silent(self.run_note("2026-10-13T22:00:00-05:00"))
        self.append_log([guard_crash(CRASH_AT)])
        # 23:59 CDT is still the same Central day. The stamp is the only reason it is silent.
        self.assert_silent(self.run_note("2026-10-13T23:59:00-05:00"))
        # 00:01 CDT on Oct 14 is a new Central day, only 2 hours after the first start.
        lines = self.failure_lines(self.run_note("2026-10-14T00:01:00-05:00"))
        self.assertEqual(len(lines), 1)
        self.assertIn("crash", lines[0].lower())


class CheckTests(NoteCase):
    def test_guard_crash_line_from_yesterday_is_one_failure(self):
        self.write_log(healthy_log() + [guard_crash(CRASH_AT)])
        lines = self.failure_lines(self.run_note(MORNING))
        self.assertEqual(len(lines), 1)
        self.assertIn("crash", lines[0].lower())

    def test_a_day_of_high_but_steady_denies_prints_nothing(self):
        self.write_log(steady("env-file", 500, HISTORY) + steady("waiter", 300, HISTORY))
        self.assert_silent(self.run_note(MORNING))

    def test_a_volume_ramp_like_the_real_log_prints_nothing(self):
        # About 20 denies a day for a week, then 300, then 2800 on one day, all of one rule.
        week = ["2026-10-%02d" % day for day in range(6, 13)]
        self.write_log(steady("env-file", 20, week) + steady("env-file", 300, ["2026-10-13"])
                       + steady("env-file", 2800, ["2026-10-14"]))
        self.assert_silent(self.run_note("2026-10-15T09:00:00-05:00"))

    def test_steady_rules_and_a_new_small_rule_do_not_fail(self):
        self.write_log(healthy_log() + steady("cite-by-id", 3, [YESTERDAY]))
        self.assert_silent(self.run_note(MORNING))

    def test_failure_line_is_one_plain_short_line_that_names_the_reader(self):
        self.write_log(healthy_log() + [guard_crash(CRASH_AT)])
        result = self.run_note(MORNING)
        lines = self.failure_lines(result)
        self.assertEqual(len(lines), 1)
        self.assertLessEqual(len(lines[0]), MAX_LINE)
        self.assertNotIn("\x1b", result.stdout)
        self.assert_names_reader(lines[0], os.path.dirname(NOTE))

    def test_unreadable_guard_log_is_reported_as_unknown(self):
        os.makedirs(os.path.join(self.config, "guard.log"))  # a directory cannot be read as a log
        lines = self.failure_lines(self.run_note(MORNING))
        self.assertEqual(len(lines), 1)
        self.assertIn("unknown", lines[0].lower())
        self.assert_names_reader(lines[0], os.path.dirname(NOTE))


class ReaderPathTests(NoteCase):
    def test_the_printed_reader_path_follows_the_hook_folder_not_the_repo(self):
        # A layout like ~/.claude: hooks/ and lint/ side by side. The line must name that copy.
        for source in (NOTE, os.path.join(ROOT, "hooks", "local_time.py"),
                       os.path.join(ROOT, "hooks", "guard_core.py"),
                       os.path.join(ROOT, "hooks", "shared_names.py"),
                       os.path.join(ROOT, "hooks", "git_reads.py"),
                       os.path.join(ROOT, "lint", "guard_log_report.py")):
            self.require_file(source)
        layout = self.scratch("layout")
        tracked_tree.copy_tracked(layout, "hooks", "lint")  # the note and every module it reaches
        self.write_log(healthy_log() + [guard_crash(CRASH_AT)])
        lines = self.failure_lines(self.run_note(MORNING, script=os.path.join(layout, "hooks", "daily_note.py")))
        self.assertEqual(len(lines), 1)
        self.assert_names_reader(lines[0], os.path.join(layout, "hooks"))
        self.assertNotIn(os.path.normcase(reader_path(os.path.join(ROOT, "hooks"))),
                         os.path.normcase(lines[0]))

    def test_a_long_hook_folder_keeps_the_crash_line_within_the_cap_with_its_whole_reader_tail(self):
        layout = self.long_path(LONG_HOOK_FOLDER, "claude-layout-")
        tracked_tree.copy_tracked(layout, "hooks", "lint")  # the note and every module it reaches
        self.write_log(healthy_log() + [guard_crash(CRASH_AT)])
        tail = "Read: python " + reader_path(os.path.join(layout, "hooks"))
        self.assertLessEqual(len(tail), MAX_LINE, "control: the reader tail alone must fit the cap")
        lines = self.failure_lines(self.run_note(MORNING, script=os.path.join(layout, "hooks", "daily_note.py")))
        self.assertEqual(len(lines), 1, "want one crash line, got %r" % lines)
        self.assert_short_head_kept(lines[0], "1 guard crash line(s):", tail, keep="1 guard crash line(s)")

    def test_a_long_hook_folder_keeps_the_unknown_lead_and_the_whole_tail_when_guard_log_is_unreadable(self):
        layout = self.long_path(LONG_HOOK_FOLDER, "claude-layout-")
        tracked_tree.copy_tracked(layout, "hooks", "lint")  # the note and every module it reaches
        guard = os.path.join(self.config, "guard.log")
        os.makedirs(guard)  # a directory cannot be read as a log
        err = unreadable_error(guard)
        tail = "Read: python " + reader_path(os.path.join(layout, "hooks"))
        lines = self.failure_lines(self.run_note(MORNING, script=os.path.join(layout, "hooks", "daily_note.py")))
        self.assertEqual(len(lines), 1, "want one unknown line, got %r" % lines)
        self.assertIn("unknown", lines[0], "the line dropped unknown: %r" % lines[0])
        # Past the cap the line is the short head plus the whole Read: tail, and the head still says unknown.
        short = "guard.log cannot be read (%s): its state is unknown." % err
        self.assert_short_head_kept(lines[0], short, tail, keep="unknown")


class CrashTests(NoteCase):
    def test_a_crash_in_the_note_exits_zero_with_one_stderr_line(self):
        self.require_file(NOTE)
        self.write_log(healthy_log())
        # hooks/daily_note.py alone, with no sibling modules: its imports fail.
        layout = self.scratch("layout")
        os.makedirs(os.path.join(layout, "hooks"))
        copy = os.path.join(layout, "hooks", "daily_note.py")
        shutil.copyfile(NOTE, copy)
        result = self.run_note(MORNING, script=copy)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(len([line for line in result.stderr.splitlines() if line.strip()]), 1,
                         result.stderr)


class FitTests(NoteCase):
    """The cut on fit() itself, with synthetic strings: a full line of exactly MAX_LINE keeps its head, one
    character more swaps to the short head. Both tail lengths sit on either side of the sweep and agent-end
    tails the integration cases use."""

    def fit_band(self, tail_len, full_len):
        fit = self.load_note().fit
        tail = "Read: " + "t" * (tail_len - len("Read: "))
        head = "h" * (full_len - tail_len - 1)
        self.assertEqual(len(tail), tail_len, "control: the synthetic tail")
        self.assertEqual(len(head + " " + tail), full_len, "control: the synthetic full line")
        short = "daily sweep errors (12345 bytes):"
        want = head + " " + tail if full_len <= MAX_LINE else short + " " + tail
        self.assertEqual(fit(head, short, tail), want, "fit() at a %d-character full line" % full_len)

    def test_a_211_tail_keeps_the_full_head_at_exactly_240(self):
        self.fit_band(211, 240)

    def test_a_211_tail_swaps_to_the_short_head_at_241(self):
        self.fit_band(211, 241)

    def test_a_215_tail_keeps_the_full_head_at_exactly_240(self):
        self.fit_band(215, 240)

    def test_a_215_tail_swaps_to_the_short_head_at_241(self):
        self.fit_band(215, 241)


class WiringTests(NoteCase):
    def test_a_startup_session_start_hook_runs_the_note(self):
        self.assertTrue(session_start_commands(),
                        "no SessionStart hook under a startup matcher runs hooks/daily_note.py")

    def test_the_wired_command_exits_zero_and_prints_nothing_without_the_script(self):
        commands = session_start_commands()
        self.assertTrue(commands, "no SessionStart hook under a startup matcher runs hooks/daily_note.py")
        sh = shutil.which("sh")
        self.assertIsNotNone(sh, "no sh on PATH: the wired command cannot be run here")
        for command in commands:
            result = subprocess.run([sh, "-c", command], env=self.env(self.config), cwd=self.root,
                                    capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")


def json_line(record):
    return json.dumps(record) + "\n"


def run_id(pid, when):
    """An agent-end run id, "<pid>-<time_ns>", at an instant (janitor/agent_end_reap.py writes time.time_ns())."""
    return "%d-%d" % (pid, int(datetime.fromisoformat(when).timestamp()) * 10 ** 9 + 123456789)


def started_row(run):
    return json_line({"raw": "{}", "run": run, "state": "started"})


def done_row(run):
    return json_line({"raw": "{}", "run": run, "state": "done", "target": None})


def errored_row(run):
    """A run whose handler raised: the reap hook's done row carries an `error` key."""
    return json_line({"raw": "{}", "run": run, "state": "done", "error": "RuntimeError('boom')"})


def drop_row(when, run, error="PermissionError(13, 'payload log held')"):
    """A row log() writes when it drops the new row: `at` in the log's own format (%z, so -0500 with no colon),
    the record's run (null when it has none) and the error's repr."""
    return json_line({"at": datetime.fromisoformat(when).strftime("%Y-%m-%dT%H:%M:%S%z"), "run": run, "error": error})


MALFORMED_ROWS = [
    "not json at all\n",
    json_line(["a", "list"]),
    json_line({"raw": "{}", "state": "started"}),  # no run key
    json_line({"run": 7, "state": "started"}),  # run is not a string
    json_line({"run": "12345", "state": "started"}),  # no time part after the pid
    json_line({"run": "9-" + "9" * 40, "state": "started"}),  # a time no date can hold
]


class AgentEndTests(NoteCase):
    """The agent-end check: a reap run on a window day that was killed or crashed. A line keeps its
    short head and its whole Read: tail, and fits 240 unless those two are longer (lane ruling, 06:27 CST)."""

    def window_control(self):
        """A started-only run on the window day. It always prints, so a silent case shows the check ran."""
        return [started_row(run_id(900, YESTERDAY_NOON))]

    def assert_one_run_line(self, result, count):
        lines = self.failure_lines(result)
        self.assertEqual(len(lines), 1, "want one agent-end line, got %r" % lines)
        self.assertIn("%d agent-end reap run(s)" % count, lines[0])
        self.assertTrue(lines[0].endswith("Read: " + self.payload_path()),
                        "the line does not end with its reader path: %r" % lines[0])
        return lines[0]

    def test_a_started_only_run_on_a_window_day_is_one_line_that_ends_with_its_reader(self):
        self.write_payload([started_row(run_id(101, YESTERDAY_NOON))])
        self.assert_one_run_line(self.run_note(MORNING), 1)

    def test_an_errored_run_on_a_window_day_is_one_line(self):
        self.write_payload([errored_row(run_id(102, YESTERDAY_NOON))])
        self.assert_one_run_line(self.run_note(MORNING), 1)

    def test_a_run_with_a_started_and_a_done_row_is_not_counted(self):
        run = run_id(103, YESTERDAY_NOON)
        self.write_payload([started_row(run), done_row(run)] + self.window_control())
        self.assert_one_run_line(self.run_note(MORNING), 1)

    def test_a_run_with_only_a_done_row_is_not_counted(self):
        self.write_payload([done_row(run_id(104, YESTERDAY_NOON))] + self.window_control())
        self.assert_one_run_line(self.run_note(MORNING), 1)

    def test_a_run_outside_the_window_or_on_today_is_not_counted(self):
        self.write_payload([started_row(run_id(105, "2026-10-12T12:00:00-05:00")),
                            started_row(run_id(106, "2026-10-14T10:00:00-05:00"))] + self.window_control())
        self.assert_one_run_line(self.run_note(MORNING), 1)

    def test_a_run_at_0430_utc_on_the_14th_counts_as_the_13th(self):
        self.write_payload([started_row(run_id(107, "2026-10-14T04:30:00+00:00"))])
        self.assert_one_run_line(self.run_note(MORNING), 1)

    def test_a_run_at_0530_utc_on_the_14th_is_not_counted(self):
        self.write_payload([started_row(run_id(108, "2026-10-14T05:30:00+00:00"))] + self.window_control())
        self.assert_one_run_line(self.run_note(MORNING), 1)

    def test_several_runs_give_one_line_with_their_count(self):
        self.write_payload([started_row(run_id(pid, when)) for pid, when in (
            (111, "2026-10-13T08:00:00-05:00"),
            (112, "2026-10-13T10:00:00-05:00"),
            (113, "2026-10-13T12:00:00-05:00"))])
        self.assert_one_run_line(self.run_note(MORNING), 3)

    def test_malformed_rows_are_skipped_and_do_not_count(self):
        self.write_payload(MALFORMED_ROWS + [started_row(run_id(121, YESTERDAY_NOON))])
        self.assert_one_run_line(self.run_note(MORNING), 1)

    def test_malformed_rows_alone_print_nothing_and_fail_no_run(self):
        self.write_payload(MALFORMED_ROWS)
        self.assert_silent(self.run_note(MORNING))

    def test_a_missing_payload_log_is_silent(self):
        self.assert_silent(self.run_note(MORNING))

    def test_a_payload_log_that_cannot_be_read_is_reported_as_unknown(self):
        self.config = self.long_path(LONG_CONFIG, "claude-config-", at_least=True)  # a long temp root: the cut runs
        os.makedirs(self.payload_path())  # a directory cannot be read as a log
        err = unreadable_error(self.payload_path())
        tail = "Read: " + self.payload_path()
        lines = self.failure_lines(self.run_note(MORNING))
        self.assertEqual(len(lines), 1, "want one unknown line, got %r" % lines)
        self.assertIn("unknown", lines[0], "the line dropped unknown: %r" % lines[0])
        # Past the cap the line is the short head plus the whole Read: tail, and the head still says unknown.
        self.assert_short_head_kept(lines[0], unreadable_payload_head(err), tail, keep="unknown")

    def test_a_long_config_dir_keeps_the_agent_end_line_within_the_cap_with_its_whole_reader_tail(self):
        self.config = self.long_path(LONG_CONFIG, "claude-config-", at_least=True)
        tail = "Read: " + self.payload_path()
        self.write_payload([started_row(run_id(141, YESTERDAY_NOON))])
        line = self.assert_one_run_line(self.run_note(MORNING), 1)
        # Within the cap when the short head and the whole tail fit; past it, the short head and the whole tail.
        self.assert_short_head_kept(line, "1 agent-end reap run(s) killed or crashed:", tail,
                                    keep="1 agent-end reap run(s)")

    def test_a_config_dir_so_long_that_the_reader_tail_alone_is_past_the_cap_still_prints_the_whole_tail(self):
        self.config = self.long_path(TAIL_CONFIG, "claude-config-")
        tail = "Read: " + self.payload_path()
        self.assertGreater(len(tail), MAX_LINE, "control: the reader tail alone must be past the cap")
        self.write_payload([started_row(run_id(142, YESTERDAY_NOON))])
        self.assert_one_run_line(self.run_note(MORNING), 1)

    def test_a_215_character_reader_tail_keeps_the_short_head_and_the_whole_tail(self):
        self.config = self.long_path(215 - 37, "claude-config-")  # the tail is "Read: " + config + 31 characters
        tail = "Read: " + self.payload_path()
        self.assertEqual(len(tail), 215, "control: the reader tail must be 215 characters")
        self.write_payload([started_row(run_id(pid, YESTERDAY_NOON)) for pid in (151, 152, 153)])
        lines = self.failure_lines(self.run_note(MORNING))
        self.assertEqual(len(lines), 1, "want one agent-end line, got %r" % lines)
        self.assert_short_head_kept(lines[0], "3 agent-end reap run(s) killed or crashed:", tail,
                                    keep="3 agent-end reap run(s)")

    def test_a_long_config_dir_keeps_the_unknown_lead_and_the_whole_tail_when_the_payload_log_is_unreadable(self):
        self.config = self.long_path(175, "claude-config-", at_least=True)  # a config of 175 or more: the line is past the cap
        os.makedirs(self.payload_path())  # a directory cannot be read as a log
        err = unreadable_error(self.payload_path())
        tail = "Read: " + self.payload_path()
        lines = self.failure_lines(self.run_note(MORNING))
        self.assertEqual(len(lines), 1, "want one unknown line, got %r" % lines)
        self.assertIn("unknown", lines[0], "the line dropped unknown: %r" % lines[0])
        self.assert_short_head_kept(lines[0], unreadable_payload_head(err), tail, keep="unknown")


class DropRowTests(NoteCase):
    """The drops check: one line when log() dropped a row on a window day. The drops file holds one JSON row per
    drop (janitor/agent_end_reap.py). One line gives the count, says "dropped", and ends with `Read:` and the
    file's path. The count sits in the head, before `Read:`, so a digit in the path cannot pass for it."""

    def drops_line(self, result):
        """The one drops line's head (before `Read:`). Its tail must be the drops file's path."""
        lines = self.failure_lines(result)
        self.assertEqual(len(lines), 1, "want one drops line, got %r" % lines)
        head, sep, tail = lines[0].rpartition("Read: ")
        self.assertEqual(sep, "Read: ", "the drops line has no Read: tail: %r" % lines[0])
        self.assertEqual(tail, self.drops_path(), "the drops line does not end with its reader path: %r" % lines[0])
        return head

    def assert_count(self, head, count):
        self.assertRegex(head, r"(?<!\d)%d(?!\d)" % count, "the drops line does not carry the count %d: %r" % (count, head))
        self.assertIn("dropped", head, "the drops line does not say dropped: %r" % head)

    def test_two_drop_rows_on_a_window_day_give_one_line_with_the_count(self):
        self.write_drops([drop_row(YESTERDAY_NOON, "refused-run"), drop_row(YESTERDAY_NOON, None)])
        self.assert_count(self.drops_line(self.run_note(MORNING)), 2)

    def test_a_drop_row_from_before_the_window_is_not_counted(self):
        self.write_drops([drop_row("2026-10-12T12:00:00-05:00", "old-run"), drop_row(YESTERDAY_NOON, "new-run")])
        self.assert_count(self.drops_line(self.run_note(MORNING)), 1)

    def test_a_drop_row_from_before_the_window_alone_is_silent(self):
        """The control: a row from before the window is not a failure, so the note prints nothing."""
        self.write_drops([drop_row("2026-10-12T12:00:00-05:00", "old-run")])
        self.assert_silent(self.run_note(MORNING))

    def test_malformed_drop_rows_are_skipped_and_do_not_count(self):
        self.write_drops(["not json at all\n", json_line(["a", "list"]),
                          json_line({"run": "no-at", "error": "x"}),
                          json_line({"at": "not a time", "run": "bad-at", "error": "x"}),
                          drop_row(YESTERDAY_NOON, "good-run")])
        self.assert_count(self.drops_line(self.run_note(MORNING)), 1)

    def test_a_missing_drops_file_is_silent(self):
        """The control: no drops file is no failure."""
        self.assert_silent(self.run_note(MORNING))

    def test_an_unreadable_drops_file_prints_one_unknown_line_and_still_writes_the_stamp(self):
        """A directory at the drops path cannot be read as a log. The note prints one unknown line that ends with
        the drops path, and the start still writes its stamp. The OSError branch covers it."""
        os.makedirs(self.drops_path())
        lines = self.failure_lines(self.run_note(MORNING))
        self.assertEqual(len(lines), 1, "want one unknown line, got %r" % lines)
        self.assertIn("unknown", lines[0].lower(), "the drops line does not say unknown: %r" % lines[0])
        self.assertTrue(lines[0].endswith("Read: " + self.drops_path()),
                        "the drops line does not end with its reader path: %r" % lines[0])
        self.assertEqual(self.stamp_day(), TODAY, "the start with an unreadable drops file did not write its stamp")

    def test_a_drop_row_whose_at_overflows_is_skipped_and_the_other_rows_still_count(self):
        """A row whose `at` is late on 9999-12-31 with a negative offset overflows the UTC-to-Central conversion
        (OverflowError). That row is skipped: the valid row still counts, the line still prints, and the stamp is written."""
        import local_time
        overflow_at = "9999-12-31T23:00:00-05:00"
        with self.assertRaises(OverflowError, msg="control: the row's at does not overflow the Central conversion"):
            local_time.line(lambda: datetime.strptime(overflow_at, "%Y-%m-%dT%H:%M:%S%z"))
        self.write_drops([drop_row(YESTERDAY_NOON, "good-run"), drop_row(overflow_at, "far-run")])
        result = self.run_note(MORNING)
        self.assertEqual(result.stderr, "", "the note wrote to stderr on a drop row whose at overflows: %r" % result.stderr)
        self.assert_count(self.drops_line(result), 1)
        self.assertEqual(self.stamp_day(), TODAY, "the start with an overflowing drop row did not write its stamp")


class SweepErrorLogTests(NoteCase):
    """The daily sweep's error log: one line when it is not empty and was last written on a window day."""

    def test_a_non_empty_error_log_from_a_window_day_is_one_line_naming_both_logs(self):
        self.write_sweep_err("sweep failed\n", YESTERDAY_NOON)
        lines = self.failure_lines(self.run_note(MORNING))
        self.assertEqual(len(lines), 1, "want one sweep-error line, got %r" % lines)
        self.assertIn(self.sweep_err_path(), lines[0])
        self.assertTrue(lines[0].endswith("stdout: " + self.sweep_out_path()),
                        "the line does not end with the stdout log: %r" % lines[0])

    def test_an_empty_error_log_is_silent(self):
        self.write_sweep_err("", YESTERDAY_NOON)
        self.assert_silent(self.run_note(MORNING))

    def test_an_error_log_last_written_before_the_window_is_silent(self):
        self.write_sweep_err("old error\n", OLD_WRITE)
        self.assert_silent(self.run_note(MORNING))

    def test_missing_logs_are_silent(self):
        self.assert_silent(self.run_note(MORNING))

    def test_a_long_config_dir_keeps_the_sweep_count_and_the_whole_tail(self):
        self.config = self.scratch("claude-config-" + "x" * 100)  # a fixed name: its tail is past the cap anywhere
        tail = "Read: tail %s; stdout: %s" % (self.sweep_err_path(), self.sweep_out_path())
        self.write_sweep_err("e" * 12345, YESTERDAY_NOON)  # 12345 bytes
        lines = self.failure_lines(self.run_note(MORNING))
        self.assertEqual(len(lines), 1, "want one sweep-error line, got %r" % lines)
        self.assert_short_head_kept(lines[0], "daily sweep errors (12345 bytes):", tail, keep="12345 bytes")

    def test_a_default_config_dir_keeps_the_sweep_count_and_the_whole_tail(self):
        tail = "Read: tail %s; stdout: %s" % (self.sweep_err_path(), self.sweep_out_path())
        self.write_sweep_err("e" * 12345, YESTERDAY_NOON)  # 12345 bytes
        lines = self.failure_lines(self.run_note(MORNING))
        self.assertEqual(len(lines), 1, "want one sweep-error line, got %r" % lines)
        self.assert_short_head_kept(lines[0], "daily sweep errors (12345 bytes):", tail, keep="12345 bytes")

    def test_an_unstatable_sweep_log_is_unknown_with_its_whole_tail(self):
        self.config = self.scratch("claude-config-" + "x" * 100)
        tail = "Read: tail %s; stdout: %s" % (self.sweep_err_path(), self.sweep_out_path())
        err_path = os.path.abspath(self.sweep_err_path())
        real_stat = os.stat

        def failing_stat(path, *args, **kwargs):
            if os.path.abspath(os.fsdecode(path)) == err_path:
                raise PermissionError(13, "Permission denied", err_path)
            return real_stat(path, *args, **kwargs)

        with mock.patch("os.stat", failing_stat):
            out, err = self.in_process(self.load_note(), MORNING)
        self.assertEqual(err, "", "the note raised: %r" % err)
        lines = out.splitlines()
        self.assertEqual(len(lines), 1, "want one unknown line, got %r" % lines)
        self.assert_short_head_kept(lines[0], "launchd-sweep.err.log cannot be read (PermissionError):", tail,
                                    keep="cannot be read (PermissionError)")


class StartCostTests(NoteCase):
    """The cost stated for checks 3 and 4: files on disk after the stamp check, no process, and nothing
    written beyond the stamp. Watched in this process, since main() catches every error and exits 0."""

    def fail_both_checks(self):
        self.write_payload([started_row(run_id(131, YESTERDAY_NOON))])
        self.write_sweep_err("sweep failed\n", YESTERDAY_NOON)

    def touched_paths(self, module, now):
        """Every path the note opens or stats during one start, as absolute paths, with what it printed."""
        touched = []
        real_open, real_stat = open, os.stat

        def spy_open(file, *args, **kwargs):
            if isinstance(file, (str, bytes, os.PathLike)):
                touched.append(os.path.abspath(os.fsdecode(file)))
            return real_open(file, *args, **kwargs)

        def spy_stat(path, *args, **kwargs):
            if isinstance(path, (str, bytes, os.PathLike)):
                touched.append(os.path.abspath(os.fsdecode(path)))
            return real_stat(path, *args, **kwargs)

        with mock.patch("builtins.open", spy_open), mock.patch("os.stat", spy_stat):
            out, err = self.in_process(module, now)
        return touched, out, err

    def test_the_first_start_reads_both_logs_and_a_second_start_reads_neither(self):
        self.fail_both_checks()
        module = self.load_note()
        first, out1, err1 = self.touched_paths(module, MORNING)
        self.assertEqual(err1, "", "the note raised on the first start: %r" % err1)
        self.assertIn(self.payload_path(), first, "the first start never read the agent-end payload log")
        self.assertIn(self.sweep_err_path(), first, "the first start never checked the sweep error log")
        self.assertEqual(len(out1.splitlines()), 2,
                         "control: both checks should print a line on the first start, got %r" % out1)
        second, out2, err2 = self.touched_paths(module, LATER_SAME_DAY)
        self.assertEqual(out2, "", "a second start on the same day printed: %r" % out2)
        self.assertNotIn(self.payload_path(), second, "a second start on the same day read the payload log")
        self.assertNotIn(self.sweep_err_path(), second, "a second start on the same day checked the sweep error log")

    def test_the_first_start_starts_no_process(self):
        self.fail_both_checks()
        module = self.load_note()
        started = []
        targets = ("subprocess.Popen", "subprocess.run", "subprocess.call", "subprocess.check_call",
                   "subprocess.check_output", "os.system", "os.fork", "os.posix_spawn",
                   "os.posix_spawnp", "os.spawnv", "os.execv")
        with contextlib.ExitStack() as stack:
            for target in targets:
                stack.enter_context(mock.patch(target, side_effect=refuse_process(target, started), create=True))
            out, err = self.in_process(module, MORNING)
        self.assertEqual(started, [], "the first start started a process: %r" % started)
        self.assertEqual(err, "", "the note raised while a process call was refused: %r" % err)
        self.assertEqual(len(out.splitlines()), 2,
                         "control: both checks should print a line, got %r" % out)

    def test_the_first_start_reads_the_drops_file_and_a_second_start_does_not(self):
        self.write_drops([drop_row(YESTERDAY_NOON, "refused-run")])
        module = self.load_note()
        first, _out1, err1 = self.touched_paths(module, MORNING)
        self.assertEqual(err1, "", "the note raised on the first start: %r" % err1)
        self.assertIn(self.drops_path(), first, "the first start never read the drops file")
        second, _out2, _err2 = self.touched_paths(module, LATER_SAME_DAY)
        self.assertNotIn(self.drops_path(), second, "a second start on the same day read the drops file")

    def test_the_first_start_writes_only_the_stamp(self):
        self.fail_both_checks()
        before = self.snapshot()
        result = self.run_note(MORNING)
        after = self.snapshot()
        lines = self.failure_lines(result)
        self.assertEqual(len(lines), 2, "control: both checks should print a line, got %r" % lines)
        added = sorted(path for path in after if path not in before)
        self.assertEqual(added, ["daily-note.stamp"], "the first start wrote more than the stamp: %r" % added)
        changed = sorted(path for path in before if path in after and before[path] != after[path])
        self.assertEqual(changed, [], "the first start changed existing files: %r" % changed)


def refuse_process(name, started):
    """A stand-in for a process start: it records the call and raises, so a start that makes it fails loudly."""
    def refuse(*args, **kwargs):
        started.append(name)
        raise RuntimeError("%s starts a process" % name)
    return refuse


if __name__ == "__main__":
    unittest.main()
