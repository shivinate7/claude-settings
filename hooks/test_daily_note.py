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
  No volume check. A day of high but steady denies, or a ramp of growing volume, prints nothing.
- Each line: plain text, at most 240 characters, names what failed, and names the reader
  command by its ABSOLUTE path, built from the hook's own folder: <hook folder>/../lint/
  guard_log_report.py. Nothing else goes to stdout. stderr stays empty.
- Done-today stamp: under CLAUDE_CONFIG_DIR, and it records the Central day. Never under TEMP,
  TMP, APPDATA or LOCALAPPDATA.
- A crash in the note: exit 0, stdout empty, exactly one stderr line.
- Wiring: a SessionStart hook under a startup matcher runs the note in the same
  `[ -f ... ] || exit 0` shape as the other hooks, so a missing script exits 0 silently.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
NOTE = os.path.join(ROOT, "hooks", "daily_note.py")
sys.path.insert(0, os.path.join(ROOT, "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)
SETTINGS = os.path.join(ROOT, "settings.json")
CLOCK = "CLAUDE_DAILY_NOTE_NOW"
MAX_LINE = 240

YESTERDAY = "2026-10-13"  # the Central day before MORNING
TODAY = "2026-10-14"
MORNING = "2026-10-14T09:00:00-05:00"
BASELINE = ["2026-10-%02d" % day for day in range(6, 13)]  # the 7 days before YESTERDAY
HISTORY = BASELINE + [YESTERDAY]
CRASH_AT = "2026-10-13T23:30:00"  # a late-evening line on YESTERDAY, Central wall time


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

    def require_file(self, path):
        if not os.path.isfile(path):
            self.fail("%s does not exist yet: the daily note is not built" % os.path.relpath(path, ROOT))

    def write_log(self, lines):
        with open(os.path.join(self.config, "guard.log"), "w", encoding="utf-8") as handle:
            handle.write("".join(lines))

    def append_log(self, lines):
        with open(os.path.join(self.config, "guard.log"), "a", encoding="utf-8") as handle:
            handle.write("".join(lines))

    def env(self, config):
        env = dict(os.environ)
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


if __name__ == "__main__":
    unittest.main()
