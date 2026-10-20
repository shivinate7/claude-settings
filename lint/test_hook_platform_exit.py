#!/usr/bin/env python3
"""A hook row in settings.json must not start python where its script does nothing.
Run: python3 lint/test_hook_platform_exit.py -v

Each case runs the row's command string from settings.json (never a copy) through `sh -c`, with PATH
set to one folder of stubs. A stub python records each start. Where the script does nothing, the row
must exit 0, silent, with no python start. Where it works, the row must reach python.
- stall_watch --hook: does nothing off posix (hook() returns at once). --stop has no posix gate, so
  its row must still reach python on Windows.
- sim_boot_record (Pre and Post rows): does nothing without xcrun.
- ci_wake: does nothing unless the payload holds "ready" (any case). The row reads the payload
  first, so it must hand the same bytes and the exit code through.
Override the settings file with HOOK_PLATFORM_EXIT_SETTINGS.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.environ.get("HOOK_PLATFORM_EXIT_SETTINGS") or os.path.join(HERE, "..", "settings.json")
SH = shutil.which("sh")
# Tools a row may use besides builtins. Each becomes a wrapper in the stub folder, so a row never
# finds the host's python, xcrun or uname.
PASS_THROUGH = ("cat", "grep", "sed", "tr", "head", "cut", "awk", "wc", "tee", "dirname", "basename")

STUB_PYTHON = '#!/bin/sh\necho "$0 $*" >> "$STUB_LOG"\nread -r line; printf %s "$line" > "$STUB_LOG.stdin"\nexit "${STUB_RC:-0}"\n'


def rows(script):
    """[(event, command)] for every settings.json hook whose command runs hooks/<script>."""
    needle = "/%s\"" % script
    with open(SETTINGS, encoding="utf-8") as f:
        events = json.load(f)["hooks"]
    return [(ev, h["command"]) for ev, entries in events.items() for e in entries
            for h in e["hooks"] if needle in h.get("command", "")]


def run_row(command, script, payload="{}", platform="posix", xcrun=True, rc=0):
    """-> (CompletedProcess, [python starts], python's stdin or None)."""
    if SH is None:
        raise RuntimeError("no sh on PATH; these tests need Git Bash on Windows")
    with tempfile.TemporaryDirectory() as root:
        stubs, cfg = os.path.join(root, "stubs"), os.path.join(root, "cfg")
        os.makedirs(stubs)
        os.makedirs(os.path.join(cfg, "hooks"))
        open(os.path.join(cfg, "hooks", script), "w").close()  # the row passes its [ -f ] check

        def put(name, body):
            path = os.path.join(stubs, name)
            with open(path, "w", newline="\n") as f:
                f.write(body)
            os.chmod(path, 0o755)

        for name in ("python3", "python"):
            put(name, STUB_PYTHON)
        put("uname", '#!/bin/sh\necho "$FAKE_UNAME"\n')
        if xcrun:
            put("xcrun", "#!/bin/sh\nexit 0\n")
        for name in PASS_THROUGH:
            real = shutil.which(name)
            if real:
                put(name, '#!/bin/sh\nexec "%s" "$@"\n' % real.replace("\\", "/"))
        log = os.path.join(root, "calls.log")
        env = {"PATH": stubs, "CLAUDE_CONFIG_DIR": cfg, "STUB_LOG": log, "STUB_RC": str(rc),
               "FAKE_UNAME": "Linux"}
        if platform == "nt":
            env.update(FAKE_UNAME="MINGW64_NT-10.0-26200", OS="Windows_NT", OSTYPE="msys")
        done = subprocess.run([SH, "-c", command], env=env, input=payload, capture_output=True,
                              text=True, timeout=60)
        calls = open(log).read().splitlines() if os.path.exists(log) else []
        seen = open(log + ".stdin").read() if os.path.exists(log + ".stdin") else None
        return done, calls, seen


class Quiet(unittest.TestCase):
    def assert_does_nothing(self, result):
        done, calls, _ = result
        self.assertEqual(calls, [], "python started")
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""))

    def assert_reaches_python(self, result, script, flag=None):
        done, calls, _ = result
        self.assertEqual(len(calls), 1, "want one python start, got %r" % calls)
        self.assertIn(script, calls[0])
        if flag:
            self.assertIn(flag, calls[0])


class StallWatch(Quiet):
    script = "stall_watch.py"

    def row(self, flag):
        hits = [c for _ev, c in rows(self.script) if (" %s;" % flag) in c]
        self.assertEqual(len(hits), 1, "want one %s row" % flag)
        return hits[0]

    def test_hook_row_exits_before_python_off_posix(self):
        self.assert_does_nothing(run_row(self.row("--hook"), self.script, platform="nt"))

    def test_hook_row_reaches_python_on_posix(self):
        self.assert_reaches_python(run_row(self.row("--hook"), self.script), self.script, "--hook")

    def test_stop_row_still_reaches_python_off_posix(self):
        self.assert_reaches_python(run_row(self.row("--stop"), self.script, platform="nt"),
                                   self.script, "--stop")


class SimBootRecord(Quiet):
    script = "sim_boot_record.py"

    def each_row(self):
        found = rows(self.script)
        self.assertEqual(sorted(ev for ev, _ in found), ["PostToolUse", "PreToolUse"])
        return found

    def test_rows_exit_before_python_without_xcrun(self):
        for ev, command in self.each_row():
            with self.subTest(event=ev):
                self.assert_does_nothing(run_row(command, self.script, xcrun=False))

    def test_rows_reach_python_with_xcrun(self):
        for ev, command in self.each_row():
            with self.subTest(event=ev):
                self.assert_reaches_python(run_row(command, self.script), self.script)

    def test_rows_reach_python_on_windows_shell_with_xcrun(self):
        # The gate is xcrun alone, not the platform.
        for ev, command in self.each_row():
            with self.subTest(event=ev):
                self.assert_reaches_python(run_row(command, self.script, platform="nt"), self.script)


class CiWake(Quiet):
    script = "ci_wake.py"

    def command(self):
        found = rows(self.script)
        self.assertEqual(len(found), 1)
        return found[0][1]

    @staticmethod
    def payload(command, tool="Bash"):
        return json.dumps({"tool_name": tool, "tool_input": {"command": command}, "cwd": "/x"})

    def test_payload_without_ready_starts_no_python(self):
        for command in ("ls -la", "gh pr view 12", "git push origin HEAD:x"):
            with self.subTest(command=command):
                self.assert_does_nothing(run_row(self.command(), self.script, self.payload(command)))

    def test_payload_with_ready_reaches_python_with_same_stdin(self):
        for command, tool in (("gh pr ready 12", "Bash"), ("GH PR READY 12", "Bash"),
                              ("gh pr ready 7", "PowerShell")):
            with self.subTest(command=command, tool=tool):
                payload = self.payload(command, tool)
                result = run_row(self.command(), self.script, payload)
                self.assert_reaches_python(result, self.script)
                self.assertEqual(result[2], payload)

    def test_python_exit_code_reaches_the_harness(self):
        # Exit 2 is the wake. A prefilter that swallowed it would never wake the session.
        done, _, _ = run_row(self.command(), self.script, self.payload("gh pr ready 12"), rc=2)
        self.assertEqual(done.returncode, 2)


if __name__ == "__main__":
    unittest.main()
