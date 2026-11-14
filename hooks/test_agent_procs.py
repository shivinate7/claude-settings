#!/usr/bin/env python3
"""Cases for hooks/agent_procs.py, the one home of the per-agent process record (step agent-owned-processes),
and for the cost of the agent marker on the tool-call path. Standard library only, `unittest`.

Run it from the repository root:

    python3 hooks/test_agent_procs.py

Where the cases live. The record's behaviour is judged where it acts: the SubagentStop cases and the stop-list cases
are in janitor/test_sweep.py (class AgentOwnedProcessTests, extending the agent-end fixture), the kill-only-yours
cases are in tests/guard/s71834-agent-owned-kill.py, and the simulator lease cases are in lint/test_sim_lease.py
(class LeaseRecord). This file holds the cases that need the new module's own functions: the Office adapter and the
visible-window rule, which take injected process lists so they run on Linux. Those cases have no entry point on the
base, so they FAIL there on `hooks/agent_procs.py does not exist yet`. That failure is not a red (test-practices P3);
the post-build mutant is what proves them. The kill check's in-process cases (its start and marker reads patched, and the
kill verbs `taskkill` and `Stop-Process`, and the taskkill spellings) are in classes KillCheckWithoutReads, KillVerbs and KillVerbControls below: a guard case runs the
hook as a subprocess, so it cannot patch a read.

The cost case is a control: it passes on the base, because the recording adds nothing to the tool-call path today.
It pins the stated number, zero process starts, so a recording that starts a process there fails it.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stall_watch  # noqa: E402  the tool-call path the cost pin counts (hooks/stall_watch.py)
import guard_kill  # noqa: E402  the kill guard's agent check, read in-process (hooks/guard_kill.py)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)

try:
    import agent_procs  # noqa: E402  the one home of the per-agent record (hooks/agent_procs.py); absent on the base
except ImportError:
    agent_procs = None

AGENT = "5c0a1e7d93b2f4860"  # 17 hex characters, the id the marker carries
OTHER = "b71f3d0c2a9e56847"  # 17 hex characters, a second agent
MARKER_NAMES = ("CLAUDE_AGENT_ID", "CLAUDE_CODE_SESSION_ID")
OFFICE_IMAGES = ("EXCEL.EXE", "POWERPNT.EXE", "WINWORD.EXE")
RUN_FOLDER = None  # the run folder of this run (test-temp-standard); every case's folder is inside it


def need_module(case):
    """Fail the case with the one named cause when the module is not there yet."""
    case.assertIsNotNone(agent_procs, "hooks/agent_procs.py does not exist yet: no Office adapter, no visible-window rule")


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


def stop_child(child):
    """Kill CHILD and reap it. A case's cleanup: the child may have exited already."""
    child.kill()
    child.wait(timeout=10)


class OfficeAdapter(unittest.TestCase):
    """Item 8 and 6 (visible window): the Office adapter diffs the three Office images before and after the agent's
    run (COM-started Office has DcomLaunch as its parent, so a parent check cannot find it). Off Windows, or when no
    Office process runs, it exits early and starts nothing. These cases inject the process lists."""

    def test_the_office_diff_names_the_office_pid_the_agent_started(self):
        need_module(self)
        before = {100: "bash.exe"}
        after = {100: "bash.exe", 4242: "EXCEL.EXE", 4243: "notepad.exe"}
        self.assertEqual(agent_procs.office_started(before, after), [4242],
                         "the diff does not name the one new Office pid, 4242")

    def test_off_windows_the_office_adapter_reads_no_process_list(self):
        need_module(self)
        reads = []

        def lister():
            reads.append(1)
            return {4242: "EXCEL.EXE"}

        self.assertIsNone(agent_procs.office_snapshot("linux", lister), "the adapter took a snapshot off Windows")
        self.assertEqual(reads, [], "the adapter read the process list off Windows")

    def test_on_windows_with_no_office_process_the_adapter_exits_early(self):
        need_module(self)
        self.assertIsNone(agent_procs.office_snapshot("win32", lambda: {100: "bash.exe"}),
                          "the adapter took a snapshot with no Office process running")

    def test_a_visible_window_or_a_start_that_differs_is_reported_and_never_ended(self):
        need_module(self)
        candidates = [
            {"pid": 4242, "owner": AGENT, "visible": True, "start_ok": True},
            {"pid": 4300, "owner": None, "visible": False, "start_ok": True},
            {"pid": 4400, "owner": AGENT, "visible": False, "start_ok": False},
        ]
        self.assertEqual(agent_procs.plan_ends(candidates, AGENT), [],
                         "a visible, unclear or reused pid is in the stop plan")


class ToolCallPathCost(unittest.TestCase):
    """Item 10 (control): the stall_watch call that carries the agent marker starts no process. The count runs on the
    tool-call path, the hook itself, so a recording added there that starts one fails this pin."""

    def test_a_background_call_with_an_agent_id_starts_no_process(self):
        if os.name != "posix":
            self.skipTest("the stall_watch hook is posix only: it returns before any rewrite elsewhere")
        call = {"tool_name": "Bash", "agent_id": AGENT,
                "tool_input": {"command": "sleep 1", "run_in_background": True, "description": "pin"}}
        starts = []
        real_popen = subprocess.Popen

        class CountingPopen(real_popen):
            def __init__(self, *args, **kwargs):
                starts.append(args[0] if args else kwargs.get("args"))
                super().__init__(*args, **kwargs)

        out = io.StringIO()
        with mock.patch.object(subprocess, "Popen", CountingPopen), \
                mock.patch.object(sys, "stdin", io.StringIO(json.dumps(call))), \
                contextlib.redirect_stdout(out):
            stall_watch.hook()
        command = json.loads(out.getvalue())["hookSpecificOutput"]["updatedInput"]["command"]
        self.assertIn("export CLAUDE_AGENT_ID=" + AGENT, command, "scope: the call was not marked with the agent id")
        self.assertEqual(starts, [], "the tool-call path started %d process(es): %r" % (len(starts), starts))


class KillCheckBase(unittest.TestCase):
    """The kill check's in-process cases. Each case has its own record folder under the run folder, named by
    CLAUDE_AGENT_PROCS_DIR, and one sleeping child with no agent marker: the pid the record names."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.folder, True)
        patch = mock.patch.dict(os.environ, {"CLAUDE_AGENT_PROCS_DIR": os.path.join(self.folder, "agent-procs")})
        patch.start()
        self.addCleanup(patch.stop)
        env = {k: v for k, v in os.environ.items() if k not in MARKER_NAMES}
        self.child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], cwd=self.folder, env=env,
                                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(stop_child, self.child)

    def record(self, agent, start):
        """AGENT's record names the child with START as its start (None when the start cannot be read)."""
        self.assertTrue(agent_procs.write_record(agent, {"procs": [
            {"pid": self.child.pid, "start": start, "owner": agent, "kind": "background"}]}), "scope: no record written")

    def reads_fail(self):
        """Both reads the kill check makes answer None: the process start ticks and the marker."""
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(agent_procs, "start_ticks", return_value=None))
        stack.enter_context(mock.patch.object(guard_kill, "entry_value", None))
        return stack


class KillCheckWithoutReads(KillCheckBase):
    """Finding 3: the start ticks and the marker both read None, and another agent's record lists the pid. The kill is
    refused for the calling agent, because the record names its owner. The two controls answer under the same reads: a
    pid recorded to the caller, and a pid in no record, are both allowed."""

    def test_a_pid_another_agent_records_is_refused_when_the_start_and_marker_reads_fail(self):
        self.record(OTHER, None)
        self.assertTrue(any(e.get("pid") == self.child.pid for e in agent_procs.read_record(OTHER)["procs"]),
                        "scope: the other agent's record does not list pid %d" % self.child.pid)
        with self.reads_fail():
            self.assertIsNone(agent_procs.start_ticks(self.child.pid), "scope: the start ticks still read")
            answer = guard_kill.agent_pid_kill(["kill", str(self.child.pid)], AGENT)
        self.assertEqual(answer, str(self.child.pid),
                         "the kill of pid %d, recorded to another agent, was allowed with no start and no marker read"
                         % self.child.pid)

    def test_control_a_pid_recorded_to_the_caller_is_allowed_under_the_same_reads(self):
        self.record(AGENT, None)
        with self.reads_fail():
            answer = guard_kill.agent_pid_kill(["kill", str(self.child.pid)], AGENT)
        self.assertEqual(answer, "", "control: the kill of pid %d, recorded to the calling agent, was refused"
                         % self.child.pid)

    def test_control_a_pid_in_no_record_is_allowed_under_the_same_reads(self):
        self.assertEqual(agent_procs.all_records(), {}, "scope: a record lists pid %d" % self.child.pid)
        with self.reads_fail():
            answer = guard_kill.agent_pid_kill(["kill", str(self.child.pid)], AGENT)
        self.assertEqual(answer, "", "control: a pid in no record was refused under the failed reads")


def taskkill_spellings(pid):
    """The `taskkill` spellings of one pid that the kill check must read: Git Bash's `//PID` and `//F`, the image name
    `taskkill.exe`, and the glued `/PID=<n>` form. Keyed by a label that names the spelling."""
    return {"taskkill //PID //F": ["taskkill", "//PID", str(pid), "//F"],
            "taskkill.exe /PID": ["taskkill.exe", "/PID", str(pid)],
            "taskkill /PID=": ["taskkill", "/PID=%d" % pid]}


@unittest.skipUnless(sys.platform.startswith("linux"), "the record's start ticks are read from /proc, which only Linux has")
class KillVerbs(KillCheckBase):
    """Finding 4: `taskkill /PID <n>` and `Stop-Process -Id <n>` reach the same agent check as `kill <n>`. The pid is
    another agent's: its record lists it with its start ticks, which read here."""

    def setUp(self):
        super().setUp()
        self.record(OTHER, agent_procs.start_ticks(self.child.pid))
        self.assertEqual(agent_procs.held_by_others(self.child.pid, AGENT), [OTHER],
                         "scope: the record does not name pid %d to the other agent" % self.child.pid)

    def test_control_kill_by_pid_of_another_agents_pid_is_refused(self):
        answer = guard_kill.agent_pid_kill(["kill", str(self.child.pid)], AGENT)
        self.assertEqual(answer, str(self.child.pid), "control: kill of pid %d, recorded to another agent, was allowed"
                         % self.child.pid)

    def test_taskkill_by_pid_of_another_agents_pid_is_refused(self):
        answer = guard_kill.agent_pid_kill(["taskkill", "/PID", str(self.child.pid)], AGENT)
        self.assertEqual(answer, str(self.child.pid), "taskkill /PID of pid %d, recorded to another agent, was allowed"
                         % self.child.pid)

    def test_stop_process_by_id_of_another_agents_pid_is_refused(self):
        answer = guard_kill.agent_pid_kill(["Stop-Process", "-Id", str(self.child.pid)], AGENT)
        self.assertEqual(answer, str(self.child.pid), "Stop-Process -Id of pid %d, recorded to another agent, was allowed"
                         % self.child.pid)

    def test_git_bash_double_slash_taskkill_of_another_agents_pid_is_refused(self):
        answer = guard_kill.agent_pid_kill(["taskkill", "//PID", str(self.child.pid), "//F"], AGENT)
        self.assertEqual(answer, str(self.child.pid), "taskkill //PID //F of pid %d, recorded to another agent, was allowed"
                         % self.child.pid)

    def test_taskkill_exe_by_pid_of_another_agents_pid_is_refused(self):
        answer = guard_kill.agent_pid_kill(["taskkill.exe", "/PID", str(self.child.pid)], AGENT)
        self.assertEqual(answer, str(self.child.pid), "taskkill.exe /PID of pid %d, recorded to another agent, was allowed"
                         % self.child.pid)

    def test_taskkill_equals_form_of_another_agents_pid_is_refused(self):
        answer = guard_kill.agent_pid_kill(["taskkill", "/PID=%d" % self.child.pid], AGENT)
        self.assertEqual(answer, str(self.child.pid), "taskkill /PID=<n> of pid %d, recorded to another agent, was allowed"
                         % self.child.pid)


@unittest.skipUnless(sys.platform.startswith("linux"), "the record's start ticks are read from /proc, which only Linux has")
class KillVerbControls(KillCheckBase):
    """Controls for the taskkill spellings: a pid the calling agent owns, and a pid in no record, are allowed in every
    spelling. They pass on the old code, which reads none of these spellings. They hold the fix to allowing an own or
    unrecorded pid, so it cannot pass by refusing every taskkill."""

    def test_control_an_own_pid_is_allowed_in_each_taskkill_spelling(self):
        self.record(AGENT, agent_procs.start_ticks(self.child.pid))
        self.assertEqual(agent_procs.recorded_owners(self.child.pid), [AGENT],
                         "scope: the record does not name pid %d to the calling agent" % self.child.pid)
        for label, tokens in taskkill_spellings(self.child.pid).items():
            with self.subTest(spelling=label):
                answer = guard_kill.agent_pid_kill(tokens, AGENT)
                self.assertEqual(answer, "", "control: %s of pid %d, recorded to the calling agent, was refused"
                                 % (label, self.child.pid))

    def test_control_an_unrecorded_pid_is_allowed_in_each_taskkill_spelling(self):
        self.assertEqual(agent_procs.all_records(), {}, "scope: a record lists pid %d" % self.child.pid)
        for label, tokens in taskkill_spellings(self.child.pid).items():
            with self.subTest(spelling=label):
                answer = guard_kill.agent_pid_kill(tokens, AGENT)
                self.assertEqual(answer, "", "control: %s of pid %d, in no record, was refused" % (label, self.child.pid))


if __name__ == "__main__":
    unittest.main()
