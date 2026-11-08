#!/usr/bin/env python3
"""Fixture test for bin/now-central, the one way a session reads the time in US Central. Run: python3 lint/test_now_central.py -v

Forms, each one line on stdout:
    now-central            HH:MM CST|CDT
    now-central --full     YYYY-MM-DD HH:MM CST|CDT
    now-central --iso      YYYY-MM-DDTHH:MM:SS-06:00, or -05:00 in DST; datetime.fromisoformat parses it
Any other argument: exit 2, usage on stderr. No argument, or one form: exit 0.

The helper's clock is hooks/local_time.py's, the one home of the Central clock. The clock cases check the output
against zoneinfo America/Chicago, never against local_time. The real clock is read only to bracket each run: t0
before the run, t1 after it. The helper read its clock between the two, so its printed minute (its printed second
for --iso) lies inside the bracket. A bracket is no fixed window, so load cannot make it false, and it stays
within 60 s of the system clock. Every helper run drops LOCAL_TIME_NOW and sets TZ=Asia/Tokyo: no answer may
follow either.

The pointer cases check the files that must name now-central, and the hook's printed line in both modes.
The guard case runs hooks/guard.py with the payload hooks/test_guard.py sends a Bash call. It does not import
hooks/test_guard.py, whose import runs that suite's whole fixture build.

Each failure names one cause. A missing helper fails its cases with that cause, never with a crash.
"""
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
from zoneinfo import ZoneInfo

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
CENTRAL = ZoneInfo("America/Chicago")
POINTER = "now-central"
POINTER_FILES = (
    "output-styles/shiv-stylisms.md",
    "skills/project-ops/templates/brief.md",
    "skills/project-ops/templates/role-handoff.md",
    "skills/project-ops/templates/operating-model.md",
    "hooks/precompact_handoff_prompt.md",
    "skills/waiting-page/SKILL.md",
    "agents/record-writer.md",
)
SHORT = re.compile(r"\d{2}:\d{2} (?:CST|CDT)\n")
FULL = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} (?:CST|CDT)\n")
ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}-0[56]:00\n")
POSIX_ONLY = unittest.skipIf(os.name == "nt", "the helper runs as a POSIX executable with a shebang")


def central_minutes(t0, t1):
    """Each whole minute from the minute of t0 to the minute of t1 (epoch seconds), as America/Chicago datetimes."""
    return [datetime.fromtimestamp(s, CENTRAL) for s in range(int(t0) // 60 * 60, int(t1) // 60 * 60 + 1, 60)]


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

    # The clock: each form is the Central clock within the bracket of the run.

    @POSIX_ONLY
    def test_bare_form_is_the_central_clock(self):
        t0 = time.time()
        rc, out, _ = self.helper([])
        t1 = time.time()
        self.assertEqual(rc, 0, "bare form: exit code is not 0")
        want = {"%s %s\n" % (d.strftime("%H:%M"), d.tzname()) for d in central_minutes(t0, t1)}
        self.assertTrue(out in want, "bare form: the time is not the Central clock during the run, got %r" % out)

    @POSIX_ONLY
    def test_full_form_is_the_central_clock(self):
        t0 = time.time()
        rc, out, _ = self.helper(["--full"])
        t1 = time.time()
        self.assertEqual(rc, 0, "--full: exit code is not 0")
        want = {"%s %s\n" % (d.strftime("%Y-%m-%d %H:%M"), d.tzname()) for d in central_minutes(t0, t1)}
        self.assertTrue(out in want,
                        "--full: the date, time or zone is not the Central clock during the run, got %r" % out)

    @POSIX_ONLY
    def test_iso_form_is_the_central_instant_with_its_offset(self):
        t0 = time.time()
        rc, out, _ = self.helper(["--iso"])
        t1 = time.time()
        self.assertEqual(rc, 0, "--iso: exit code is not 0")
        try:
            got = datetime.fromisoformat(out.strip())
        except ValueError as e:
            self.fail("--iso: datetime.fromisoformat does not parse the line: %s" % e)
        lo = datetime.fromtimestamp(math.floor(t0), timezone.utc)
        hi = datetime.fromtimestamp(t1, timezone.utc)
        self.assertTrue(lo <= got <= hi, "--iso: the instant is not during the run, got %s" % got.isoformat())
        self.assertEqual(got.utcoffset(), got.astimezone(CENTRAL).utcoffset(),
                         "--iso: the offset is not the Central offset at that instant")

    # Arguments: any other one is exit 2 with usage on stderr.

    @POSIX_ONLY
    def test_any_other_argument_exits_2_with_usage_on_stderr(self):
        for arg in ("--bogus", "extra"):
            with self.subTest(arg=arg):
                rc, _, err = self.helper([arg])
                self.assertEqual(rc, 2, "%s: exit code is not 2" % arg)
                self.assertIn("usage", err.lower(), "%s: no usage text on stderr, got %r" % (arg, err))

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

    # The pointer: each named file, and the hook's printed line in both modes, names now-central.

    def test_each_named_file_names_now_central(self):
        for rel in POINTER_FILES:
            with self.subTest(file=rel):
                path = os.path.join(ROOT_DIR, rel)
                self.assertTrue(os.path.isfile(path), "%s is missing" % rel)
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                self.assertTrue(POINTER in text, "%s does not name now-central" % rel)

    def test_hook_user_prompt_line_names_now_central(self):
        done = self.hook_run("", "UserPromptSubmit")
        self.assertEqual(done.returncode, 0, "UserPromptSubmit: the hook exit code is not 0")
        lines = done.stdout.splitlines()
        self.assertTrue(lines and lines[0].startswith("Local time: "),
                        "UserPromptSubmit: no Local time line on stdout, got %r" % done.stdout[-200:])
        self.assertTrue(POINTER in lines[0], "UserPromptSubmit: the Local time line does not name now-central")

    def test_hook_agent_line_names_now_central(self):
        done = self.hook_run("--agent", "SubagentStart")
        self.assertEqual(done.returncode, 0, "--agent: the hook exit code is not 0")
        try:
            ctx = json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]
        except (ValueError, KeyError, TypeError) as e:
            self.fail("--agent: the hook does not print hookSpecificOutput JSON: %s" % e)
        self.assertIsInstance(ctx, str, "--agent: additionalContext is not a string")
        self.assertTrue(ctx.startswith("Local time: "), "--agent: additionalContext is not a Local time line")
        self.assertTrue(POINTER in ctx, "--agent: the additionalContext line does not name now-central")


def tearDownModule():
    """test-temp-standard: teardown removes this run's folder."""
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
