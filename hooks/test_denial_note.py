#!/usr/bin/env python3
"""Cases for hooks/denial_note.py: the PermissionDenied hook that records a refused tool call, so
the Stop guard can ask the owner about it (lint/report_guard.py, the pending-denial check).

Run it from the repository root:

    python3 hooks/test_denial_note.py

Standard library only, and no test runner. Each case runs the hook as a child process, as the
PermissionDenied event does, with a scratch CLAUDE_CONFIG_DIR, HOME and TEMP. No case touches the
owner's ~/.claude. Temp files live in this run's folder (lint/_test_temp.py, test-temp-standard).

Contract the builder codes against. Every case is red until hooks/denial_note.py exists.
- Stdin: one JSON object with session_id, tool_name, tool_input, tool_use_id, reason, cwd and
  hook_event_name ("PermissionDenied").
- Writes one JSON line to <CLAUDE_CONFIG_DIR>/state/denials/<session_id>.jsonl, with the keys ts,
  tool_name and reason. With CLAUDE_CONFIG_DIR unset, the folder is <HOME>/.claude.
- A reason that starts with "Auto mode could not evaluate this action" is a no-verdict denial
  (a classifier outage). It writes nothing.
- A tool_name already in the file is not appended again.
- Prints nothing to stdout, exits 0, and never prints a retry decision.
- One denial creates exactly one file under the config folder.
- Wiring: settings.json has a PermissionDenied hook with no matcher (or a "*" matcher, so the
  MCP tools are covered), and its command names denial_note.py.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HOOK = os.path.join(ROOT, "hooks", "denial_note.py")
SETTINGS = os.path.join(ROOT, "settings.json")
sys.path.insert(0, os.path.join(ROOT, "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per test run (lint/_test_temp.py)

RUN = _test_temp.run_folder()
SESSION = "denial-sid-1"
ARCHIVE = "mcp__claude-code-remote__archive_session"
ADD_REPO = "mcp__claude-code-remote__add_repo"
DENIED = "Permission for archive_session was denied by the auto-mode classifier."
NO_VERDICT = "Auto mode could not evaluate this action. The classifier returned no verdict."


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)


class HookCase(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.mkdtemp(prefix="denial-", dir=RUN)
        self.config = os.path.join(self.scratch, "config")
        self.home = os.path.join(self.scratch, "home")
        self.temp = os.path.join(self.scratch, "temp")
        for path in (self.config, self.home, self.temp):
            os.makedirs(path)

    def env(self, config=True):
        env = dict(os.environ)
        env.update({"HOME": self.home, "USERPROFILE": self.home, "TEMP": self.temp,
                    "TMP": self.temp, "TMPDIR": self.temp})
        env.pop("CLAUDE_CONFIG_DIR", None)
        if config:
            env["CLAUDE_CONFIG_DIR"] = self.config
        return env

    def fire(self, data, env=None):
        if not os.path.isfile(HOOK):
            self.fail("hooks/denial_note.py does not exist yet: the PermissionDenied hook is not built")
        return subprocess.run([sys.executable, HOOK], input=json.dumps(data), env=env or self.env(),
                              cwd=self.scratch, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=30)

    def denial(self, tool=ARCHIVE, reason=DENIED, use_id="toolu_1", session=SESSION):
        return {"hook_event_name": "PermissionDenied", "session_id": session, "tool_name": tool,
                "tool_input": {"name": "x"}, "tool_use_id": use_id, "reason": reason,
                "cwd": self.scratch}

    def denials_file(self, session=SESSION):
        return os.path.join(self.config, "state", "denials", session + ".jsonl")

    def denial_rows(self, session=SESSION):
        try:
            with open(self.denials_file(session), encoding="utf-8") as handle:
                return [json.loads(line) for line in handle if line.strip()]
        except FileNotFoundError:
            return []

    def files_written(self):
        """Every regular file under the config folder, as paths relative to it."""
        found = []
        for dirpath, _, names in os.walk(self.config):
            for name in names:
                found.append(os.path.relpath(os.path.join(dirpath, name), self.config))
        return sorted(found)


class DenialNoteTests(HookCase):
    def test_a_denial_writes_one_line_and_prints_nothing(self):
        run = self.fire(self.denial())
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), "", "the hook printed on a denial: %r" % run.stdout)
        rows = self.denial_rows()
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(set(rows[0]), {"ts", "tool_name", "reason"})
        self.assertEqual(rows[0]["tool_name"], ARCHIVE)
        self.assertEqual(rows[0]["reason"], DENIED)
        self.assertTrue(isinstance(rows[0]["ts"], str) and rows[0]["ts"], rows[0])

    def test_b_no_verdict_denial_writes_nothing(self):
        run = self.fire(self.denial(reason=NO_VERDICT))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), "")
        self.assertEqual(self.files_written(), [], "a no-verdict denial wrote a file")

    def test_b2_phrase_not_at_the_start_is_a_real_denial(self):
        # The rule says "starts with". A reason that only mentions the phrase is a real denial.
        run = self.fire(self.denial(reason="Denied after review. " + NO_VERDICT))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual([row["tool_name"] for row in self.denial_rows()], [ARCHIVE])

    def test_c_same_tool_twice_writes_one_line_and_each_tool_gets_its_own(self):
        runs = [self.fire(self.denial(tool=ARCHIVE, use_id="toolu_1")),
                self.fire(self.denial(tool=ARCHIVE, use_id="toolu_2", reason=DENIED + " Again.")),
                self.fire(self.denial(tool=ADD_REPO, use_id="toolu_3", reason="Denied: add_repo."))]
        for run in runs:
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.strip(), "")
        self.assertEqual([row["tool_name"] for row in self.denial_rows()], [ARCHIVE, ADD_REPO])

    def test_cost_one_denial_creates_exactly_one_file(self):
        run = self.fire(self.denial())
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.files_written(), [os.path.join("state", "denials", SESSION + ".jsonl")])

    def test_h_unset_config_dir_falls_back_to_home_claude(self):
        run = self.fire(self.denial(), env=self.env(config=False))
        self.assertEqual(run.returncode, 0, run.stderr)
        path = os.path.join(self.home, ".claude", "state", "denials", SESSION + ".jsonl")
        self.assertTrue(os.path.isfile(path), "no denials file under HOME/.claude: %s" % path)
        self.assertEqual(self.files_written(), [], "the config folder was written with CLAUDE_CONFIG_DIR unset")


class WiringTests(unittest.TestCase):
    def test_settings_run_the_hook_for_every_denial(self):
        with open(SETTINGS, encoding="utf-8") as handle:
            entries = json.load(handle).get("hooks", {}).get("PermissionDenied", [])
        commands = [hook.get("command", "") for entry in entries
                    if entry.get("matcher") in (None, "", "*")
                    for hook in entry.get("hooks", [])]
        self.assertTrue(any("denial_note.py" in command for command in commands),
                        "no PermissionDenied hook without a matcher names denial_note.py: %r" % entries)


if __name__ == "__main__":
    unittest.main()
