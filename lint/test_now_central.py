#!/usr/bin/env python3
"""Fixture test for bin/now-central, the one way a session reads the time in US Central. Run: python3 lint/test_now_central.py -v

Forms, each one line on stdout:
    now-central            HH:MM CST|CDT
    now-central --full     YYYY-MM-DD HH:MM CST|CDT
    now-central --iso      YYYY-MM-DDTHH:MM:SS-06:00, or -05:00 in DST; datetime.fromisoformat parses it
Any other argument, the empty string included: exit 2, usage on stderr. No argument, or one form: exit 0.

The helper's clock is hooks/local_time.py's, the one home of the Central clock. Two kinds of clock case:
- Pinned: hooks/local_time.py's central_full and central_iso at fixed instants (summer, winter, and both sides of
  each DST change). The expected strings are hand-checked against America/Chicago, so no zoneinfo runs here.
- Real clock: one case runs the helper's three forms in one bracket, t0 before the runs and t1 after them. The
  helper read its clock between the two, so its printed minute (its printed second for --iso) lies inside the
  bracket, within 60 s of the system clock. Its zoneinfo reference is built inside that case, and the case skips
  with a reason when tzdata is missing. Every helper run drops LOCAL_TIME_NOW and sets TZ=Asia/Tokyo.

The pointer cases check that each named file pins the code span it uses for the helper, and that the hook's
printed line ends with the pointer constant the hook emits (hooks/local_time.py NOW_CENTRAL_POINTER).
The guard case runs hooks/guard.py with the payload hooks/test_guard.py sends a Bash call. It does not import
hooks/test_guard.py, whose import runs that suite's whole fixture build.

Each failure names one cause. A missing helper or function fails its cases with that cause, never with a crash.
"""
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: every temp path comes from this run's folder
RUN_FOLDER = _test_temp.run_folder()  # one run folder per test run, removed at teardown
CONFIG_DIR = os.path.join(RUN_FOLDER, "cfg")  # CLAUDE_CONFIG_DIR for the hook and the guard
os.makedirs(CONFIG_DIR, exist_ok=True)
HELPER = os.path.join(ROOT_DIR, "bin", "now-central")
LAUNCHER = os.path.join(ROOT_DIR, "bin", "now-central.cmd")
HOOK = os.path.join(ROOT_DIR, "hooks", "local_time.py")
GUARD = os.path.join(ROOT_DIR, "hooks", "guard.py")
# Each named file and the code span it pins: the form that file tells a session to read the time with.
POINTER_FORMS = (
    ("output-styles/shiv-stylisms.md", "`~/.claude/bin/now-central`"),
    ("skills/project-ops/templates/brief.md", "`~/.claude/bin/now-central`"),
    ("skills/project-ops/templates/role-handoff.md", "`~/.claude/bin/now-central --full`"),
    ("skills/project-ops/templates/operating-model.md", "`~/.claude/bin/now-central --full`"),
    ("hooks/precompact_handoff_prompt.md", "`~/.claude/bin/now-central --full`"),
    ("skills/waiting-page/SKILL.md", "`~/.claude/bin/now-central --iso`"),
    ("agents/record-writer.md", "`~/.claude/bin/now-central --full`"),
)
# Fixed instants, with the expected central_full and central_iso text. Checked by hand against America/Chicago:
# a summer instant (CDT), a winter instant (CST), and both sides of each change. Spring forward is 08:00 UTC on
# 2026-03-08, fall back is 07:00 UTC on 2026-11-01.
PINNED = (
    ("summer, CDT", datetime(2026, 7, 1, 17, 0, tzinfo=timezone.utc),
     "2026-07-01 12:00 CDT", "2026-07-01T12:00:00-05:00"),
    ("winter, CST", datetime(2026, 1, 15, 18, 0, tzinfo=timezone.utc),
     "2026-01-15 12:00 CST", "2026-01-15T12:00:00-06:00"),
    ("spring forward, one minute before", datetime(2026, 3, 8, 7, 59, tzinfo=timezone.utc),
     "2026-03-08 01:59 CST", "2026-03-08T01:59:00-06:00"),
    ("spring forward, at the change", datetime(2026, 3, 8, 8, 0, tzinfo=timezone.utc),
     "2026-03-08 03:00 CDT", "2026-03-08T03:00:00-05:00"),
    ("fall back, one minute before", datetime(2026, 11, 1, 6, 59, tzinfo=timezone.utc),
     "2026-11-01 01:59 CDT", "2026-11-01T01:59:00-05:00"),
    ("fall back, at the change", datetime(2026, 11, 1, 7, 0, tzinfo=timezone.utc),
     "2026-11-01 01:00 CST", "2026-11-01T01:00:00-06:00"),
)
SHORT = re.compile(r"\d{2}:\d{2} (?:CST|CDT)\n")
FULL = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} (?:CST|CDT)\n")
ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}-0[56]:00\n")
POSIX_ONLY = unittest.skipIf(os.name == "nt", "the helper runs as a POSIX executable with a shebang")


def central_minutes(central, t0, t1):
    """Each whole minute from the minute of t0 to the minute of t1 (epoch seconds), as `central` datetimes."""
    return [datetime.fromtimestamp(s, central) for s in range(int(t0) // 60 * 60, int(t1) // 60 * 60 + 1, 60)]


def local_time_module():
    """hooks/local_time.py loaded as a module: the one home of the Central clock. Its import has no side effects."""
    spec = importlib.util.spec_from_file_location("local_time_for_now_central", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def guard_decision(command):
    """(decision, reason) the Bash guard gives `command`, read as hooks/test_guard.py reads it: the payload on
    stdin, empty stdout is an allow, anything else carries permissionDecision."""
    env = dict(os.environ)
    for name in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_PROJECT_DIR",
                 "CLAUDE_CODE_REMOTE"):
        env.pop(name, None)
    env["CLAUDE_CONFIG_DIR"] = CONFIG_DIR
    env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid())  # the suite stands in for claude
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": ROOT_DIR})
    try:
        done = subprocess.run([sys.executable, GUARD], input=payload, capture_output=True, text=True,
                              env=env, timeout=120)
    except subprocess.TimeoutExpired:
        return "error", "the guard did not return within 120 s"
    if done.returncode != 0:
        return "error", "exit %d: %s" % (done.returncode, done.stderr.strip()[:200])
    out = done.stdout.strip()
    if not out:
        return "allow", ""
    try:
        block = json.loads(out)["hookSpecificOutput"]
        return block["permissionDecision"], block.get("permissionDecisionReason", "")
    except (ValueError, KeyError, TypeError):
        return "unparsable", out[:200]


class T(unittest.TestCase):

    def helper(self, args):
        """Run bin/now-central itself, so its exec bit and shebang count. Returns (rc, stdout, stderr)."""
        if not os.path.isfile(HELPER):
            self.fail("bin/now-central is missing, so the helper's output is not produced")
        env = {k: v for k, v in os.environ.items() if k != "LOCAL_TIME_NOW"}
        env["TZ"] = "Asia/Tokyo"
        try:
            done = subprocess.run([HELPER] + list(args), stdin=subprocess.DEVNULL, capture_output=True,
                                  text=True, env=env, timeout=30)
        except subprocess.TimeoutExpired:
            self.fail("bin/now-central did not return within 30 s")
        return done.returncode, done.stdout, done.stderr

    def hook_run(self, flag, event):
        """Run hooks/local_time.py as Claude Code runs it: the payload on stdin, the real clock."""
        env = {k: v for k, v in os.environ.items() if k != "LOCAL_TIME_NOW"}
        env["CLAUDE_CONFIG_DIR"] = CONFIG_DIR
        payload = json.dumps({"hook_event_name": event, "prompt": "check", "cwd": ROOT_DIR})
        args = [sys.executable, HOOK] + ([flag] if flag else [])
        return subprocess.run(args, input=payload, capture_output=True, text=True, env=env, timeout=30)

    def central_function(self, name):
        """The central_full or central_iso function of hooks/local_time.py, or a failure that names it missing."""
        fn = getattr(local_time_module(), name, None)
        if not callable(fn):
            self.fail("hooks/local_time.py has no %s, so that form is not built" % name)
        return fn

    def pointer(self):
        """The text the hook prints after the time line: the constant the hook emits, never a copy of it."""
        pointer = getattr(local_time_module(), "NOW_CENTRAL_POINTER", None)
        if not isinstance(pointer, str):
            self.fail("hooks/local_time.py has no NOW_CENTRAL_POINTER, so the pointer the hook prints is not pinned")
        return pointer

    # The three forms: exit 0, one line, the right shape.

    @POSIX_ONLY
    def test_bare_form_is_one_hh_mm_zone_line(self):
        rc, out, _ = self.helper([])
        self.assertEqual(rc, 0, "bare form: exit code is not 0")
        self.assertIsNotNone(SHORT.fullmatch(out),
                             "bare form: output is not one 'HH:MM CST|CDT' line, got %r" % out)

    @POSIX_ONLY
    def test_full_form_is_one_date_time_zone_line(self):
        rc, out, _ = self.helper(["--full"])
        self.assertEqual(rc, 0, "--full: exit code is not 0")
        self.assertIsNotNone(FULL.fullmatch(out),
                             "--full: output is not one 'YYYY-MM-DD HH:MM CST|CDT' line, got %r" % out)

    @POSIX_ONLY
    def test_iso_form_is_one_line_of_the_central_offset(self):
        rc, out, _ = self.helper(["--iso"])
        self.assertEqual(rc, 0, "--iso: exit code is not 0")
        self.assertIsNotNone(ISO.fullmatch(out),
                             "--iso: output is not one 'YYYY-MM-DDTHH:MM:SS-06:00 or -05:00' line, got %r" % out)
        try:
            datetime.fromisoformat(out.strip())
        except ValueError as e:
            self.fail("--iso: datetime.fromisoformat does not parse the line: %s" % e)

    # Pinned clock: central_full and central_iso at fixed instants, no real clock and no zoneinfo.

    def test_central_full_is_pinned_at_summer_winter_and_both_dst_changes(self):
        fn = self.central_function("central_full")
        for name, at, full, _ in PINNED:
            with self.subTest(instant=name):
                self.assertEqual(fn(at), full, "central_full at %s is not the pinned value" % name)

    def test_central_iso_is_pinned_at_summer_winter_and_both_dst_changes(self):
        fn = self.central_function("central_iso")
        for name, at, _, iso in PINNED:
            with self.subTest(instant=name):
                self.assertEqual(fn(at), iso, "central_iso at %s is not the pinned value" % name)

    # Real clock: the one case. Its zoneinfo reference is built here, and the case skips when tzdata is missing.

    @POSIX_ONLY
    def test_real_clock_three_forms_match_the_zoneinfo_central_clock(self):
        try:
            from zoneinfo import ZoneInfo
            central = ZoneInfo("America/Chicago")
        except (ImportError, KeyError) as e:
            self.skipTest("tzdata is missing, so no America/Chicago reference can be built: %s" % e)
        t0 = time.time()
        bare = self.helper([])
        full = self.helper(["--full"])
        iso = self.helper(["--iso"])
        t1 = time.time()
        minutes = central_minutes(central, t0, t1)
        self.assertEqual(bare[0], 0, "bare form: exit code is not 0")
        self.assertEqual(full[0], 0, "--full: exit code is not 0")
        self.assertEqual(iso[0], 0, "--iso: exit code is not 0")
        want_bare = {"%s %s\n" % (d.strftime("%H:%M"), d.tzname()) for d in minutes}
        self.assertTrue(bare[1] in want_bare, "bare form: not the Central clock during the run, got %r" % bare[1])
        want_full = {"%s %s\n" % (d.strftime("%Y-%m-%d %H:%M"), d.tzname()) for d in minutes}
        self.assertTrue(full[1] in want_full,
                        "--full: the date, time or zone is not the Central clock during the run, got %r" % full[1])
        try:
            got = datetime.fromisoformat(iso[1].strip())
        except ValueError as e:
            self.fail("--iso: datetime.fromisoformat does not parse the line: %s" % e)
        lo = datetime.fromtimestamp(math.floor(t0), timezone.utc)
        hi = datetime.fromtimestamp(t1, timezone.utc)
        self.assertTrue(lo <= got <= hi, "--iso: the instant is not during the run, got %s" % got.isoformat())
        self.assertEqual(got.utcoffset(), got.astimezone(central).utcoffset(),
                         "--iso: the offset is not the Central offset at that instant")

    # Arguments: any other one, the empty string included, is exit 2 with usage on stderr.

    @POSIX_ONLY
    def test_any_other_argument_exits_2_with_usage_on_stderr(self):
        for arg in ("--bogus", "extra"):
            with self.subTest(arg=arg):
                rc, _, err = self.helper([arg])
                self.assertEqual(rc, 2, "%s: exit code is not 2" % arg)
                self.assertIn("usage", err.lower(), "%s: no usage text on stderr, got %r" % (arg, err))

    @POSIX_ONLY
    def test_empty_string_argument_exits_2(self):
        rc, _, _ = self.helper([""])
        self.assertEqual(rc, 2, 'the empty-string argument "": exit code is not 2')

    # The Windows launcher: it runs the helper and passes every argument on.

    def test_windows_launcher_exists(self):
        self.assertTrue(os.path.isfile(LAUNCHER), "bin/now-central.cmd is missing")

    def test_windows_launcher_runs_the_helper_with_its_arguments(self):
        if not os.path.isfile(LAUNCHER):
            self.fail("bin/now-central.cmd is missing")
        with open(LAUNCHER, encoding="utf-8", errors="replace") as f:
            text = f.read()
        self.assertTrue("now-central" in text, "bin/now-central.cmd does not run the now-central helper")
        self.assertTrue("%*" in text, "bin/now-central.cmd does not pass its arguments on")

    # The guard: a read-only call to the helper is allowed, bare and inside a command substitution.

    def test_bash_guard_allows_the_helper_unchanged(self):
        for command in ("~/.claude/bin/now-central", "t=$(~/.claude/bin/now-central --iso)"):
            with self.subTest(command=command):
                decision, reason = guard_decision(command)
                self.assertIn(decision, ("allow", "deny", "ask"),
                              "the guard gave no decision for %r: %s" % (command, reason))
                self.assertNotEqual(decision, "deny", "the guard refuses %r: %s" % (command, reason))
                self.assertNotEqual(decision, "ask", "the guard asks on %r: %s" % (command, reason))

    # The pointer: each named file pins its own form, and the hook's printed line ends with the pointer constant.

    def test_each_named_file_pins_the_form_it_uses(self):
        for rel, form in POINTER_FORMS:
            with self.subTest(file=rel):
                path = os.path.join(ROOT_DIR, rel)
                self.assertTrue(os.path.isfile(path), "%s is missing" % rel)
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                self.assertTrue(form in text, "%s does not name %s" % (rel, form))

    def test_hook_user_prompt_line_ends_with_the_pointer(self):
        pointer = self.pointer()
        done = self.hook_run("", "UserPromptSubmit")
        self.assertEqual(done.returncode, 0, "UserPromptSubmit: the hook exit code is not 0")
        lines = done.stdout.splitlines()
        self.assertTrue(lines and lines[0].startswith("Local time: "),
                        "UserPromptSubmit: no Local time line on stdout, got %r" % done.stdout[-200:])
        self.assertTrue(lines[0].endswith(pointer),
                        "UserPromptSubmit: the Local time line does not end with NOW_CENTRAL_POINTER")

    def test_hook_agent_line_ends_with_the_pointer(self):
        pointer = self.pointer()
        done = self.hook_run("--agent", "SubagentStart")
        self.assertEqual(done.returncode, 0, "--agent: the hook exit code is not 0")
        try:
            ctx = json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]
        except (ValueError, KeyError, TypeError) as e:
            self.fail("--agent: the hook does not print hookSpecificOutput JSON: %s" % e)
        self.assertIsInstance(ctx, str, "--agent: additionalContext is not a string")
        self.assertTrue(ctx.startswith("Local time: "), "--agent: additionalContext is not a Local time line")
        self.assertTrue(ctx.endswith(pointer), "--agent: the additionalContext line does not end with NOW_CENTRAL_POINTER")


def tearDownModule():
    """test-temp-standard: teardown removes this run's folder."""
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
