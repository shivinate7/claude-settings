#!/usr/bin/env python3
"""A hook row in settings.json must not start python where its script does nothing.
Run: python3 lint/test_hook_platform_exit.py -v

Each case runs the row's command string from settings.json (never a copy) through `sh -c`, with PATH
set to one folder of stubs. A stub python records each start. Where the script does nothing, the row
must exit 0, silent, with no python start. Where it works, the row must reach python.
- stall_watch --hook: does nothing off posix (hook() returns at once). --stop has no posix guard, so
  its row must still reach python on Windows.
- sim_boot_record (Pre and Post rows): does nothing without xcrun.
- ci_wake: watches only a `gh pr ready` call in the COMMAND (ci_wake.triggers). The row reads the
  payload first. It starts python for `gh pr ready`, with runs of spaces or tabs between the words,
  for a gh in any case, with `.exe`, quoted or with a full path, for a quoted `pr` or `ready`, and
  for `gh pr ready --undo` (python then watches nothing: the row is no parser). It starts none for
  another "ready" (`npm run ready`, a title, a description), none for the phrase in tool_response
  only, and none for `pr ready` in another case: python reads those lowercase only. It hands the
  same bytes and the exit code through. Empty stdin still reaches python, which
  reports "CI unknown". Each case asks ci_wake.triggers too, so no row hides a call python watches.
- stall_watch: only a MINGW uname exits early. Cygwin and MSYS pythons report os.name "posix".
Override the settings file with HOOK_PLATFORM_EXIT_SETTINGS.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.environ.get("HOOK_PLATFORM_EXIT_SETTINGS") or os.path.join(HERE, "..", "settings.json")
SH = shutil.which("sh")
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))   # ci_wake: the script a CiWake row guards
# Tools a row may use besides builtins. Each becomes a wrapper in the stub folder, so a row never
# finds the host's python, xcrun or uname.
PASS_THROUGH = ("cat", "grep", "sed", "tr", "head", "cut", "awk", "wc", "tee", "dirname", "basename")

# Git for Windows' bin/sh.exe puts /usr/bin (the real uname) ahead of PATH, so a stub uname would never
# run. This prefix sets PATH again, in POSIX form, before the row runs. (Same line as in
# hooks/test_wrappers.py: the two suites are standalone scripts.)
PATH_FIRST = 'if command -v cygpath >/dev/null 2>&1; then PATH=$(cygpath -up "$STUB_PATH"); export PATH; fi; '

STUB_PYTHON = '#!/bin/sh\necho "$0 $*" >> "$STUB_LOG"\ncat > "$STUB_LOG.stdin"\nexit "${STUB_RC:-0}"\n'


def rows(script):
    """[(event, command)] for every settings.json hook whose command runs hooks/<script>."""
    needle = "/%s\"" % script
    with open(SETTINGS, encoding="utf-8") as f:
        events = json.load(f)["hooks"]
    return [(ev, h["command"]) for ev, entries in events.items() for e in entries
            for h in e["hooks"] if needle in h.get("command", "")]


def run_row(command, script, payload="{}", platform="posix", xcrun=True, rc=0, uname=None):
    """-> (CompletedProcess, [python starts], python's stdin bytes or None). Bytes in and out, so no
    newline translation hides a change."""
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
        env = {"PATH": stubs, "STUB_PATH": stubs, "CLAUDE_CONFIG_DIR": cfg, "STUB_LOG": log, "STUB_RC": str(rc),
               "FAKE_UNAME": uname or "Linux"}
        if platform == "nt":
            env.update(FAKE_UNAME=uname or "MINGW64_NT-10.0-26200", OS="Windows_NT", OSTYPE="msys")
        done = subprocess.run([SH, "-c", PATH_FIRST + command], env=env, input=payload.encode("utf-8"),
                              capture_output=True, timeout=60)
        calls = open(log).read().splitlines() if os.path.exists(log) else []
        seen = open(log + ".stdin", "rb").read() if os.path.exists(log + ".stdin") else None
        return done, calls, seen


class Quiet(unittest.TestCase):
    def assert_does_nothing(self, result):
        done, calls, _ = result
        self.assertEqual(calls, [], "python started")
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, b"", b""))

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

    def test_hook_row_reaches_python_on_cygwin_and_msys_uname(self):
        for uname in ("CYGWIN_NT-10.0-26200", "MSYS_NT-10.0-26200"):
            with self.subTest(uname=uname):
                self.assert_reaches_python(
                    run_row(self.row("--hook"), self.script, platform="nt", uname=uname),
                    self.script, "--hook")

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
        # The guard is xcrun alone, not the platform.
        for ev, command in self.each_row():
            with self.subTest(event=ev):
                self.assert_reaches_python(run_row(command, self.script, platform="nt"), self.script)


class CiWake(Quiet):
    script = "ci_wake.py"

    def command(self):
        found = rows(self.script)
        self.assertEqual(len(found), 1)
        return found[0][1]

    def assert_watch(self, command, tool, want=True):
        """The row's own script must (not) watch this command, or the row case built on it proves nothing."""
        import ci_wake
        got = bool(ci_wake.triggers(command, tool == "PowerShell"))
        self.assertEqual(got, want, "ci_wake.triggers %s %r: re-point this case"
                         % ("no longer watches" if want else "now watches", command))

    @staticmethod
    def payload(command, tool="Bash", response="", response_first=False, indent=None, description="d"):
        """A PostToolUse payload as the harness sends it, tool_response included."""
        parts = [("session_id", "abc"), ("transcript_path", "/t.jsonl"), ("cwd", "/x"),
                 ("hook_event_name", "PostToolUse"), ("tool_name", tool)]
        call = ("tool_input", {"command": command, "description": description})
        reply = ("tool_response", {"stdout": response, "stderr": "", "interrupted": False})
        parts += [reply, call] if response_first else [call, reply]
        return json.dumps(dict(parts + [("tool_use_id", "toolu_1")]), indent=indent)

    def test_command_without_ready_starts_no_python(self):
        for command in ("ls -la", "gh pr view 12", "git push origin HEAD:x"):
            with self.subTest(command=command):
                self.assert_does_nothing(run_row(self.command(), self.script, self.payload(command)))

    def test_other_ready_text_starts_no_python(self):
        # "ready" in a script name, a title, a later word, a description, or another case.
        for command, tool, description in (
                ("echo already-ready", "Bash", "d"),
                ("npm run ready", "Bash", "d"),
                ("gh pr create --draft --title 'Make hooks ready'", "Bash", "d"),
                ("gh pr view 5 --json isDraft && echo ready", "Bash", "d"),
                ("echo ready pr gh", "Bash", "d"),
                ("git pull", "Bash", "Check the PR is ready"),
                ("GH PR READY 12", "Bash", "d"),
                ("gh pr Ready 7", "PowerShell", "d")):
            with self.subTest(command=command, description=description):
                self.assert_watch(command, tool, want=False)
                payload = self.payload(command, tool, description=description)
                self.assert_does_nothing(run_row(self.command(), self.script, payload))

    def test_ready_only_in_tool_response_starts_no_python(self):
        # The phrase itself in the response must not start python either: the row reads tool_input only.
        for first in (False, True):
            for out in ("Already up to date.", "Ready to merge", "READY", "Next: gh pr ready 12"):
                with self.subTest(response_first=first, out=out):
                    payload = self.payload("git pull", response=out, response_first=first)
                    self.assert_does_nothing(run_row(self.command(), self.script, payload))

    def test_command_with_ready_reaches_python_with_same_bytes(self):
        for command, tool, out in (("gh pr ready 12", "Bash", "ok"),
                                   ("gh pr ready 7", "PowerShell", "Already up to date."),
                                   ('echo "a\\b" && gh pr ready 3\nls', "Bash", "line1\nline2\\n")):
            for first in (False, True):
                with self.subTest(command=command, tool=tool, response_first=first):
                    self.assert_watch(command, tool)
                    payload = self.payload(command, tool, out, first)
                    result = run_row(self.command(), self.script, payload)
                    self.assert_reaches_python(result, self.script)
                    self.assertEqual(result[2], payload.encode("utf-8"))

    def test_gh_pr_ready_forms_reach_python(self):
        # Each form is one ci_wake.triggers watches. A row that drops one loses a CI wake.
        for command, tool in (("gh pr ready 12", "Bash"),
                              ("cd x && gh pr ready 5", "Bash"),
                              ("gh   pr    ready 5", "Bash"),
                              ("gh\tpr\tready 5", "Bash"),
                              ("echo hi\ngh pr ready 5", "Bash"),
                              ("GH_REPO=o/r gh pr ready 5", "Bash"),
                              ("gh pr ready 5 -R o/r", "Bash"),
                              ("gh.exe pr ready 5", "PowerShell"),
                              ("& gh pr ready 5", "PowerShell"),
                              # A quoted or full-path gh, a quoted word, another case of the gh word.
                              ('& "C:\\Program Files\\GitHub CLI\\gh.exe" pr ready 5', "PowerShell"),
                              ('"/c/Program Files/GitHub CLI/gh.exe" pr ready 5', "Bash"),
                              ('& "$env:LOCALAPPDATA\\Programs\\gh\\bin\\gh.exe" pr ready 5', "PowerShell"),
                              ('"gh" pr ready', "Bash"),
                              ('gh "pr" ready', "Bash"),
                              ("gh pr 'ready'", "Bash"),
                              ("gh.EXE pr ready", "PowerShell"),
                              ("GH pr ready 5", "PowerShell"),
                              # PowerShell joins a line with a backtick before the newline.
                              ("gh `\npr ready 5", "PowerShell"),
                              ("gh pr `\nready 5", "PowerShell")):
            with self.subTest(command=command, tool=tool):
                self.assert_watch(command, tool)
                payload = self.payload(command, tool)
                result = run_row(self.command(), self.script, payload)
                self.assert_reaches_python(result, self.script)
                self.assertEqual(result[2], payload.encode("utf-8"))

    def test_undo_reaches_python_and_python_decides(self):
        # The row finds the phrase and leaves flags to ci_wake.ready_call, the one home of that parse.
        command = "gh pr ready --undo 12"
        self.assert_watch(command, "Bash", want=False)
        self.assert_reaches_python(run_row(self.command(), self.script, self.payload(command)), self.script)

    def test_multi_line_payload_reaches_python_unchanged(self):
        # `i=$(cat)` drops trailing newlines only; every other byte must arrive.
        payload = self.payload("gh pr ready 12\n\techo \u00e9 \\n", response="a\r\nb", indent=2)
        result = run_row(self.command(), self.script, payload + "\n")
        self.assert_reaches_python(result, self.script)
        self.assertEqual(result[2], payload.encode("utf-8"))

    def test_empty_stdin_reaches_python(self):
        # Python, not the row, reports "CI unknown" on unreadable input.
        result = run_row(self.command(), self.script, "")
        self.assert_reaches_python(result, self.script)
        self.assertEqual(result[2], b"")

    def test_python_exit_code_reaches_the_harness(self):
        # Exit 2 is the wake. A prefilter that swallowed it would never wake the session.
        done, _, _ = run_row(self.command(), self.script, self.payload("gh pr ready 12"), rc=2)
        self.assertEqual(done.returncode, 2)

if __name__ == "__main__":
    unittest.main()
